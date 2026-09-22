# -*- coding: utf-8 -*-
import hashlib
import logging
import requests
import xml.etree.ElementTree as ET
from urllib.parse import urlencode
from urllib.parse import urlparse

from odoo.exceptions import UserError

from .base import VirtualClassroomProvider

_logger = logging.getLogger(__name__)


class BBBProvider(VirtualClassroomProvider):
    code = 'bbb'

    def _api_url(self, action, params):
        server_url = (self._param('bbb_server_url') or '').rstrip('/')
        secret = self._param('bbb_secret')
        self._require_config({'Server URL': server_url, 'Secret': secret}, 'BigBlueButton')
        parsed_url = urlparse(server_url)
        if parsed_url.scheme not in ('http', 'https') or not parsed_url.netloc:
            raise UserError('BBB Server URL must include http:// or https:// and a hostname.')
        if parsed_url.hostname in ('localhost', '127.0.0.1'):
            raise UserError('BBB Server URL must be the public BigBlueButton server URL, not localhost.')

        query = urlencode(params)
        checksum = hashlib.sha1((action + query + secret).encode('utf-8')).hexdigest()
        return '%s/bigbluebutton/api/%s?%s&checksum=%s' % (server_url, action, query, checksum)

    def _join_url(self, meeting_id, password, full_name):
        return self._api_url('join', {
            'fullName': full_name or 'Participant',
            'meetingID': meeting_id,
            'password': password,
            'redirect': 'true',
        })

    def create_or_get_meeting(self, meeting):
        occurrence = meeting.occurrence_id
        meeting_id = meeting.meeting_id or 'tuition-occ-%s' % occurrence.id
        moderator_password = 'mod-%s' % occurrence.id
        attendee_password = 'att-%s' % occurrence.id

        duration = 60
        if occurrence.start_datetime and occurrence.stop_datetime:
            duration = int((occurrence.stop_datetime - occurrence.start_datetime).total_seconds() / 60)

        try:
            response = requests.get(self._api_url('create', {
                'name': occurrence.name,
                'meetingID': meeting_id,
                'moderatorPW': moderator_password,
                'attendeePW': attendee_password,
                'duration': duration,
            }), timeout=20)
        except requests.exceptions.RequestException as exc:
            # A network-level failure (timeout, connection refused, DNS,
            # etc.) previously propagated as a bare requests exception,
            # which the portal controllers don't catch (they only catch
            # AccessError/UserError) — it surfaced as an unhandled 500
            # instead of the friendly "vc_error" banner. Wrapping it here
            # makes BBB being unreachable behave the same as any other
            # configuration/room error.
            raise UserError('Could not reach the BBB server: %s' % exc)
        if response.status_code >= 400:
            raise UserError('BBB room creation failed: %s' % response.text[:300])

        root = ET.fromstring(response.text)
        if root.findtext('returncode') != 'SUCCESS':
            raise UserError('BBB room creation failed: %s' % (root.findtext('message') or response.text[:300]))

        moderator_url = self._join_url(
            meeting_id, moderator_password, occurrence.tutor_id.name or self.env.user.name)
        attendee_url = self._join_url(meeting_id, attendee_password, 'Student')
        return {
            'external_id': meeting_id,
            'meeting_id': meeting_id,
            'host_url': moderator_url,
            'moderator_url': moderator_url,
            'join_url': attendee_url,
            'provider_payload': {
                'meetingID': meeting_id,
                'moderatorPW': moderator_password,
                'attendeePW': attendee_password,
            },
        }

    def get_attendee_url(self, meeting, display_name):
        payload = meeting.provider_payload or {}
        meeting_id = payload.get('meetingID') or meeting.meeting_id
        password = payload.get('attendeePW') or 'att-%s' % meeting.occurrence_id.id
        if not meeting_id or not password:
            return meeting.join_url
        return self._join_url(meeting_id, password, display_name)

    def get_moderator_url(self, meeting, display_name):
        payload = meeting.provider_payload or {}
        meeting_id = payload.get('meetingID') or meeting.meeting_id
        password = payload.get('moderatorPW') or 'mod-%s' % meeting.occurrence_id.id
        if not meeting_id or not password:
            return meeting.host_url or meeting.moderator_url
        return self._join_url(meeting_id, password, display_name)

    def cancel_meeting(self, meeting):
        """Actually end the room on the BBB server (kicking anyone still in
        it), rather than the base no-op — used by Reset Virtual Classroom
        (action_force_regenerate) so a genuinely-still-alive room is really
        torn down before a fresh one is created in its place, not just
        forgotten about on our side while it keeps running on BBB."""
        payload = meeting.provider_payload or {}
        meeting_id = payload.get('meetingID') or meeting.meeting_id
        password = payload.get('moderatorPW') or 'mod-%s' % meeting.occurrence_id.id
        if not meeting_id:
            return True
        try:
            response = requests.get(self._api_url('end', {
                'meetingID': meeting_id,
                'password': password,
            }), timeout=10)
        except requests.exceptions.RequestException as exc:
            _logger.warning('BBB end-meeting request failed for %s: %s', meeting_id, exc)
            return False
        try:
            root = ET.fromstring(response.text)
        except ET.ParseError:
            return False
        # returncode=FAILED here typically just means "wasn't running
        # anyway" (e.g. already ended/deleted) — not worth raising over,
        # this is best-effort cleanup either way.
        return root.findtext('returncode') == 'SUCCESS'
