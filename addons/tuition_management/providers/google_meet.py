# -*- coding: utf-8 -*-
import base64
import json
import logging
import time
from datetime import timedelta

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from odoo import fields
from odoo.exceptions import UserError

from .base import VirtualClassroomProvider

_logger = logging.getLogger(__name__)

TOKEN_URL = 'https://oauth2.googleapis.com/token'
CALENDAR_SCOPE = 'https://www.googleapis.com/auth/calendar'
MEET_SCOPE = 'https://www.googleapis.com/auth/meetings.space.created'


def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=')


class GoogleMeetProvider(VirtualClassroomProvider):
    code = 'google_meet'

    def _service_account(self):
        service_email = self._param('google_service_account_email')
        private_key = self._param('google_service_account_private_key')
        self._require_config({
            'Service Account Email': service_email,
            'Service Account Private Key': private_key,
        }, 'Google Meet')
        if private_key:
            # Tolerate pasting the private_key value straight out of the
            # downloaded service-account JSON file, where line breaks are
            # escaped as literal "\n" characters rather than real newlines
            # (a real PEM body never legitimately contains a literal backslash-n).
            private_key = private_key.strip().strip('"')
            if '\\n' in private_key and '\n' not in private_key:
                private_key = private_key.replace('\\n', '\n')
        return service_email, private_key

    def _jwt_assertion(self, host_email, scope):
        service_email, private_key_pem = self._service_account()

        now = int(time.time())
        header = {'alg': 'RS256', 'typ': 'JWT'}
        claims = {
            'iss': service_email,
            'sub': host_email,
            'scope': scope,
            'aud': TOKEN_URL,
            'iat': now,
            'exp': now + 3600,
        }
        unsigned_token = b'.'.join([
            _b64url(json.dumps(header).encode()),
            _b64url(json.dumps(claims).encode()),
        ])

        try:
            key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
        except ValueError as exc:
            raise UserError('Google service account private key is invalid: %s' % exc)

        signature = key.sign(unsigned_token, padding.PKCS1v15(), hashes.SHA256())
        return b'.'.join([unsigned_token, _b64url(signature)]).decode()

    def _access_token(self, host_email, scope=CALENDAR_SCOPE):
        response = requests.post(
            TOKEN_URL,
            data={
                'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
                'assertion': self._jwt_assertion(host_email, scope),
            },
            timeout=20,
        )
        if response.status_code >= 400:
            raise UserError('Google authentication failed: %s' % response.text[:300])
        return response.json().get('access_token')

    def _account_is_busy(self, account, duration_minutes=60):
        token = self._access_token(account.host_email)
        now = fields.Datetime.now()
        time_min = now.isoformat() + 'Z'
        time_max = (now + timedelta(minutes=duration_minutes)).isoformat() + 'Z'

        response = requests.post(
            'https://www.googleapis.com/calendar/v3/freeBusy',
            json={
                'timeMin': time_min,
                'timeMax': time_max,
                'items': [{'id': 'primary'}],
            },
            headers={'Authorization': 'Bearer %s' % token},
            timeout=20,
        )
        if response.status_code >= 400:
            raise UserError('Google availability check failed: %s' % response.text[:300])
        data = response.json()
        busy_slots = data.get('calendars', {}).get('primary', {}).get('busy', [])
        return bool(busy_slots)

    def _get_available_account(self):
        accounts = self.env['virtual.classroom.google.account'].sudo().search(
            [('active', '=', True)], order='sequence, id'
        )
        if not accounts:
            self._require_config({'Host Accounts': False}, 'Google Meet')

        for account in accounts:
            try:
                busy = self._account_is_busy(account)
            except Exception as exc:
                _logger.warning(
                    'Google Meet account %s availability check failed: %s',
                    account.name, exc,
                )
                account.sudo().write({
                    'last_checked_at': fields.Datetime.now(),
                    'last_check_error': str(exc),
                })
                continue
            account.sudo().write({
                'last_checked_at': fields.Datetime.now(),
                'last_check_error': False,
            })
            if not busy:
                return account

        raise UserError('All configured Google Meet accounts are currently in use. Please choose another platform or try again shortly.')

    def _create_open_space(self, host_email):
        """Create the Meet space directly via the Meet API with accessType
        OPEN baked in at creation time, so invited participants can join the
        call immediately instead of waiting in the "Asking to be let in"
        queue for the host to admit them. A space created implicitly via the
        Calendar API's conferenceData.createRequest cannot reliably be
        patched afterwards (the Meet API rejects it with "Permission denied
        on resource Space" even with valid auth, since Calendar-created
        spaces aren't addressable the same way) — creating it directly here
        avoids that entirely."""
        token = self._access_token(host_email, scope=MEET_SCOPE)
        response = requests.post(
            'https://meet.googleapis.com/v2/spaces',
            json={'config': {'accessType': 'OPEN'}},
            headers={'Authorization': 'Bearer %s' % token},
            timeout=20,
        )
        if response.status_code >= 400:
            raise UserError('Google Meet space creation failed: %s' % response.text[:300])
        return response.json()

    def create_or_get_meeting(self, meeting):
        account = self._get_available_account()

        occurrence = meeting.occurrence_id
        event_id = 'tuitionocc%s' % occurrence.id

        space = self._create_open_space(account.host_email)
        meet_url = space.get('meetingUri')
        meeting_code = space.get('meetingCode') or (space.get('name') or '').rsplit('/', 1)[-1]

        payload = {
            'id': event_id,
            'summary': occurrence.name,
            'location': meet_url,
            'description': 'Join the class: %s' % meet_url if meet_url else occurrence.name,
            'start': {'dateTime': occurrence.start_datetime.isoformat() + 'Z', 'timeZone': 'UTC'},
            'end': {'dateTime': occurrence.stop_datetime.isoformat() + 'Z', 'timeZone': 'UTC'},
        }
        token = self._access_token(account.host_email)
        response = requests.post(
            'https://www.googleapis.com/calendar/v3/calendars/%s/events' % account.host_email,
            json=payload,
            headers={'Authorization': 'Bearer %s' % token},
            timeout=20,
        )
        if response.status_code == 409:
            response = requests.get(
                'https://www.googleapis.com/calendar/v3/calendars/%s/events/%s' % (account.host_email, event_id),
                headers={'Authorization': 'Bearer %s' % token},
                timeout=20,
            )
        if response.status_code >= 400:
            raise UserError('Google Calendar event creation failed: %s' % response.text[:300])

        data = response.json()
        return {
            'external_id': space.get('name'),
            'google_event_id': data.get('id'),
            'google_conference_id': meeting_code,
            'meeting_id': meeting_code,
            'join_url': meet_url,
            'host_url': meet_url,
            'provider_payload': {'space': space, 'event': data},
            'google_account_id': account.id,
        }
