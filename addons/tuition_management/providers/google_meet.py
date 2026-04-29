# -*- coding: utf-8 -*-
import requests

from odoo.exceptions import UserError

from .base import VirtualClassroomProvider


class GoogleMeetProvider(VirtualClassroomProvider):
    code = 'google_meet'

    def _access_token(self):
        payload = {
            'client_id': self._param('google_client_id'),
            'client_secret': self._param('google_client_secret'),
            'refresh_token': self._param('google_refresh_token'),
            'grant_type': 'refresh_token',
        }
        self._require_config({
            'Client ID': payload['client_id'],
            'Client Secret': payload['client_secret'],
            'Refresh Token': payload['refresh_token'],
        }, 'Google Meet')

        response = requests.post('https://oauth2.googleapis.com/token', data=payload, timeout=20)
        if response.status_code >= 400:
            raise UserError('Google OAuth token refresh failed: %s' % response.text[:300])
        return response.json().get('access_token')

    def create_or_get_meeting(self, meeting):
        if meeting.google_event_id and meeting.join_url:
            return {}

        occurrence = meeting.occurrence_id
        organizer = self._param('google_organizer_email')
        self._require_config({'Workspace Organizer Email': organizer}, 'Google Meet')

        event_id = meeting.google_event_id or 'tuitionocc%s' % occurrence.id
        request_id = 'tuition-occ-%s' % occurrence.id
        payload = {
            'id': event_id,
            'summary': occurrence.name,
            'start': {'dateTime': occurrence.start_datetime.isoformat() + 'Z', 'timeZone': 'UTC'},
            'end': {'dateTime': occurrence.stop_datetime.isoformat() + 'Z', 'timeZone': 'UTC'},
            'conferenceData': {
                'createRequest': {
                    'requestId': request_id,
                    'conferenceSolutionKey': {'type': 'hangoutsMeet'},
                },
            },
        }
        response = requests.post(
            'https://www.googleapis.com/calendar/v3/calendars/%s/events' % organizer,
            params={'conferenceDataVersion': 1},
            json=payload,
            headers={'Authorization': 'Bearer %s' % self._access_token()},
            timeout=20,
        )
        if response.status_code == 409:
            response = requests.get(
                'https://www.googleapis.com/calendar/v3/calendars/%s/events/%s' % (organizer, event_id),
                params={'conferenceDataVersion': 1},
                headers={'Authorization': 'Bearer %s' % self._access_token()},
                timeout=20,
            )
        if response.status_code >= 400:
            raise UserError('Google Calendar event creation failed: %s' % response.text[:300])

        data = response.json()
        entry_points = data.get('conferenceData', {}).get('entryPoints', [])
        meet_url = next(
            (entry.get('uri') for entry in entry_points if entry.get('entryPointType') == 'video'),
            data.get('hangoutLink'),
        )
        return {
            'external_id': data.get('id'),
            'google_event_id': data.get('id'),
            'google_conference_id': data.get('conferenceData', {}).get('conferenceId'),
            'meeting_id': data.get('conferenceData', {}).get('conferenceId'),
            'join_url': meet_url,
            'host_url': meet_url,
            'provider_payload': data,
        }
