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
        """Single master Server-to-Server OAuth app, built from ir.config_parameter.
        Used only when no virtual.classroom.zoom.account records are configured.
        With the granular admin scopes below, this one app can list and act on
        behalf of every user under the Zoom account, so host_email here is just
        an optional "try this one first" preference — it is never required.

        Required scopes (Zoom's newer apps use granular scopes, not the old
        classic user:read:admin/meeting:write:admin):
          - user:read:list_users:admin      (List Users — confirmed working name)
          - meeting:read:list_meetings:admin (check a user's live meetings)
          - meeting:write:meeting:admin      (create a meeting for a user)
          - meeting:delete:meeting:admin     (cancel/delete a meeting)
        If Zoom still rejects a call with an "Invalid access token, does not
        contain scopes: [...]" error, the bracketed name it returns is the
        exact scope to add — the error text is deliberately surfaced by this
        provider's UserErrors rather than swallowed, so it's visible in the UI."""
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
        cached = getattr(account, '_cached_token', None)
        if cached:
            return cached

        self._require_config({
            'Account ID': account.account_id,
            'Client ID': account.client_id,
            'Client Secret': account.client_secret,
        }, 'Zoom')

        response = requests.post(
            'https://zoom.us/oauth/token',
            params={'grant_type': 'account_credentials', 'account_id': account.account_id},
            auth=(account.client_id, account.client_secret),
            timeout=20,
        )
        if response.status_code >= 400:
            raise UserError('Zoom authentication failed: %s' % response.text[:300])
        token = response.json().get('access_token')
        try:
            account._cached_token = token
        except AttributeError:
            pass
        return token

    def _user_is_busy(self, token, host_email):
        response = requests.get(
            'https://api.zoom.us/v2/users/%s/meetings' % host_email,
            params={'type': 'live'},
            headers={'Authorization': 'Bearer %s' % token},
            timeout=20,
        )
        if response.status_code >= 400:
            raise UserError('Zoom availability check failed: %s' % response.text[:300])
        data = response.json()
        return bool(data.get('total_records') or data.get('meetings'))

    def _account_is_busy(self, account):
        token = self._access_token(account)
        return self._user_is_busy(token, account.host_email)

    def _list_active_users(self, token):
        """Fetch every active user under the master account via Zoom's List
        Users API, following pagination. Requires the master app to carry the
        granular scope user:read:list_users:admin (the old classic scope
        user:read:admin does not work on newer Marketplace apps)."""
        users = []
        next_page_token = ''
        while True:
            params = {'status': 'active', 'page_size': 300}
            if next_page_token:
                params['next_page_token'] = next_page_token
            response = requests.get(
                'https://api.zoom.us/v2/users',
                params=params,
                headers={'Authorization': 'Bearer %s' % token},
                timeout=20,
            )
            if response.status_code >= 400:
                raise UserError('Zoom user list retrieval failed: %s' % response.text[:300])
            data = response.json()
            users.extend(data.get('users') or [])
            next_page_token = data.get('next_page_token')
            if not next_page_token:
                break
        emails = [u.get('email') for u in users]
        _logger.info('Zoom List Users returned %d user(s): %s', len(users), emails)
        return users

    def _pick_from_pool(self, candidates):
        """Manually curated accounts (virtual.classroom.zoom.account) — each
        row is its own separate app/account registration with its own token."""
        for account in candidates:
            try:
                busy = self._account_is_busy(account)
            except Exception as exc:
                _logger.warning(
                    'Zoom account %s availability check failed: %s',
                    getattr(account, 'name', None) or account.account_id, exc,
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

        raise UserError('All configured Zoom accounts are currently in use. Please choose another platform or try again shortly.')

    def _pick_from_master(self, master):
        """Auto-discovery mode: one master app, one token, every active user
        under the account is a candidate host — no manual account list needed."""
        token = self._access_token(master)
        users = self._list_active_users(token)
        if not users:
            raise UserError('No active Zoom users were found under the configured master account.')

        emails = [u.get('email') for u in users if u.get('email')]
        if master.host_email and master.host_email in emails:
            emails.remove(master.host_email)
            emails.insert(0, master.host_email)

        for email in emails:
            try:
                busy = self._user_is_busy(token, email)
            except Exception as exc:
                _logger.warning('Zoom user %s availability check failed: %s', email, exc)
                continue
            _logger.info('Zoom user %s is %s', email, 'busy' if busy else 'free')
            if not busy:
                _logger.info('Zoom master auto-discovery picked host: %s', email)
                return SimpleNamespace(
                    id=False,
                    account_id=master.account_id,
                    client_id=master.client_id,
                    client_secret=master.client_secret,
                    host_email=email,
                    _cached_token=token,
                )

        raise UserError('All Zoom users under the configured master account are currently in use. Please choose another platform or try again shortly.')

    def _get_available_account(self):
        accounts = self.env['virtual.classroom.zoom.account'].sudo().search(
            [('active', '=', True)], order='sequence, id'
        )
        if accounts:
            return self._pick_from_pool(list(accounts))

        master = self._legacy_account()
        if not master:
            self._require_config({'Account ID': False, 'Client ID': False, 'Client Secret': False}, 'Zoom')
        return self._pick_from_master(master)

    def create_or_get_meeting(self, meeting):
        account = self._get_available_account()
        _logger.info(
            'Zoom: starting class for occurrence %s using host %s (pool account: %s)',
            meeting.occurrence_id.id, account.host_email,
            getattr(account, 'name', None) or (account.id and 'pool row %s' % account.id) or 'master auto-discovery',
        )

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
                    # approval_type: 0 means "registration required, auto-approve
                    # registrants" — it does NOT mean "no registration". That was
                    # sending students to a Zoom registration page instead of
                    # straight into the meeting, and the real per-registrant join
                    # link only arrived by email afterwards. 2 = no registration
                    # required at all, so join_url works directly.
                    'approval_type': 2,
                },
            },
            headers={'Authorization': 'Bearer %s' % self._access_token(account)},
            timeout=20,
        )
        if response.status_code >= 400:
            raise UserError('Zoom meeting creation failed: %s' % response.text[:300])

        data = response.json()
        _logger.info(
            'Zoom: created meeting %s for occurrence %s (host %s)',
            data.get('id'), occurrence.id, account.host_email,
        )
        return {
            'external_id': str(data.get('id') or ''),
            'meeting_id': str(data.get('id') or ''),
            'join_url': data.get('join_url'),
            'host_url': data.get('start_url'),
            'provider_payload': data,
            'zoom_account_id': account.id if getattr(account, 'id', False) else False,
        }

    def cancel_meeting(self, meeting):
        """Delete the scheduled meeting so its join/start URLs stop working
        for anyone joining fresh. A live session already in progress on
        Zoom's infrastructure is not disconnected by this — only future
        joins are blocked.

        Deleting a meeting only needs a valid token from an app authorized on
        the Zoom account that owns it — not the specific host's own
        credentials — so when the meeting was created via master-account
        auto-discovery (no zoom_account_id pool row, just a host email picked
        at creation time) we still have everything needed by falling back to
        the same master app used to create it."""
        if not meeting.meeting_id:
            return True
        account = meeting.zoom_account_id or self._legacy_account()
        if not account:
            return True
        response = requests.delete(
            'https://api.zoom.us/v2/meetings/%s' % meeting.meeting_id,
            headers={'Authorization': 'Bearer %s' % self._access_token(account)},
            timeout=20,
        )
        if response.status_code >= 400 and response.status_code != 404:
            raise UserError('Zoom meeting deletion failed: %s' % response.text[:300])
        return True
