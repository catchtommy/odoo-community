# -*- coding: utf-8 -*-
import logging
from types import SimpleNamespace

import requests

from odoo import fields
from odoo.exceptions import UserError

from .base import VirtualClassroomProvider

_logger = logging.getLogger(__name__)


class ZoomProvider(VirtualClassroomProvider):
    code = 'zoom'

    def _legacy_account(self):
        """Single-account fallback built from ir.config_parameter, used only
        when no virtual.classroom.zoom.account records are configured."""
        account_id = self._param('zoom_account_id')
        client_id = self._param('zoom_client_id')
        client_secret = self._param('zoom_client_secret')
        host_email = self._param('zoom_host_email')
        if not (account_id and client_id and client_secret):
            return None
        return SimpleNamespace(
            id=False,
            account_id=account_id,
            client_id=client_id,
            client_secret=client_secret,
            host_email=host_email,
        )

    def _access_token(self, account):
        self._require_config({
            'Account ID': account.account_id,
            'Client ID': account.client_id,
            'Client Secret': account.client_secret,
            'Host Email': account.host_email,
        }, 'Zoom')

        response = requests.post(
            'https://zoom.us/oauth/token',
            params={'grant_type': 'account_credentials', 'account_id': account.account_id},
            auth=(account.client_id, account.client_secret),
            timeout=20,
        )
        if response.status_code >= 400:
            raise UserError('Zoom authentication failed: %s' % response.text[:300])
        return response.json().get('access_token')

    def _account_is_busy(self, account):
        token = self._access_token(account)
        response = requests.get(
            'https://api.zoom.us/v2/users/%s/meetings' % account.host_email,
            params={'type': 'live'},
            headers={'Authorization': 'Bearer %s' % token},
            timeout=20,
        )
        if response.status_code >= 400:
            raise UserError('Zoom availability check failed: %s' % response.text[:300])
        data = response.json()
        return bool(data.get('total_records') or data.get('meetings'))

    def _get_available_account(self):
        accounts = self.env['virtual.classroom.zoom.account'].sudo().search(
            [('active', '=', True)], order='sequence, id'
        )
        if not accounts:
            legacy = self._legacy_account()
            candidates = [legacy] if legacy else []
        else:
            candidates = list(accounts)

        if not candidates:
            self._require_config({'Account ID': False, 'Client ID': False, 'Client Secret': False}, 'Zoom')

        for account in candidates:
            try:
                busy = self._account_is_busy(account)
            except Exception as exc:
                _logger.warning(
                    'Zoom account %s availability check failed: %s',
                    getattr(account, 'name', None) or account.account_id, exc,
                )
                if getattr(account, 'id', False):
                    account.sudo().write({
                        'last_checked_at': fields.Datetime.now(),
                        'last_check_error': str(exc),
                    })
                continue
            if getattr(account, 'id', False):
                account.sudo().write({
                    'last_checked_at': fields.Datetime.now(),
                    'last_check_error': False,
                })
            if not busy:
                return account

        raise UserError('All configured Zoom accounts are currently in use. Please choose another platform or try again shortly.')

    def create_or_get_meeting(self, meeting):
        account = self._get_available_account()

        occurrence = meeting.occurrence_id
        duration = 60
        if occurrence.start_datetime and occurrence.stop_datetime:
            duration = int((occurrence.stop_datetime - occurrence.start_datetime).total_seconds() / 60)

        response = requests.post(
            'https://api.zoom.us/v2/users/%s/meetings' % account.host_email,
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
            headers={'Authorization': 'Bearer %s' % self._access_token(account)},
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
            'zoom_account_id': account.id if getattr(account, 'id', False) else False,
        }
