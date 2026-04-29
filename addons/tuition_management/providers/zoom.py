# -*- coding: utf-8 -*-
import requests

from odoo.exceptions import UserError

from .base import VirtualClassroomProvider


class ZoomProvider(VirtualClassroomProvider):
    code = 'zoom'

    def _access_token(self):
        account_id = self._param('zoom_account_id')
        client_id = self._param('zoom_client_id')
        client_secret = self._param('zoom_client_secret')
        self._require_config({
            'Account ID': account_id,
            'Client ID': client_id,
            'Client Secret': client_secret,
        }, 'Zoom')

        response = requests.post(
            'https://zoom.us/oauth/token',
            params={'grant_type': 'account_credentials', 'account_id': account_id},
            auth=(client_id, client_secret),
            timeout=20,
        )
        if response.status_code >= 400:
            raise UserError('Zoom authentication failed: %s' % response.text[:300])
        return response.json().get('access_token')

    def create_or_get_meeting(self, meeting):
        if meeting.meeting_id and meeting.join_url and meeting.host_url:
            return {}

        occurrence = meeting.occurrence_id
        duration = 60
        if occurrence.start_datetime and occurrence.stop_datetime:
            duration = int((occurrence.stop_datetime - occurrence.start_datetime).total_seconds() / 60)

        host_email = self._param('zoom_host_email') or 'me'
        response = requests.post(
            'https://api.zoom.us/v2/users/%s/meetings' % host_email,
            json={
                'topic': occurrence.name,
                'type': 2,
                'start_time': occurrence.start_datetime.isoformat() + 'Z',
                'duration': duration,
                'timezone': 'UTC',
                'settings': {
                    'waiting_room': True,
                    'join_before_host': False,
                    'approval_type': 0,
                },
            },
            headers={'Authorization': 'Bearer %s' % self._access_token()},
            timeout=20,
        )
        if response.status_code >= 400:
            raise UserError('Zoom meeting creation failed: %s' % response.text[:300])

        data = response.json()
        return {
            'external_id': str(data.get('id') or ''),
            'meeting_id': str(data.get('id') or ''),
            'join_url': data.get('join_url'),
            'host_url': data.get('start_url'),
            'provider_payload': data,
        }
