# -*- coding: utf-8 -*-
import logging
import time

from odoo import models
from odoo.http import SESSION_ROTATION_EXCLUDED_PATHS, SessionExpiredException, request

_logger = logging.getLogger(__name__)

# Full admins get a much tighter idle timeout than Odoo's normal session
# lifetime (which defaults to 7 days) — an admin backend/portal session
# left open and unattended is a standing high-privilege target, especially
# now that "Login as" can hand it straight back to full admin with no
# password (see controllers/login_as.py). 30 minutes matches the
# RETURN_TO_ADMIN_VALIDITY_SECONDS window used there.
ADMIN_IDLE_TIMEOUT_SECONDS = 30 * 60

# Requests the browser fires on its own — presence heartbeats, notification
# long-polling, websocket housekeeping — must NOT count as "activity", or
# an admin who has simply walked away with a tab open would never actually
# time out even though nobody is doing anything. Odoo core already drew
# this same line for a related purpose (deciding when it's safe to rotate
# the session id), so it's reused here rather than re-guessed.
IDLE_TIMEOUT_IGNORED_PATHS = SESSION_ROTATION_EXCLUDED_PATHS + (
    '/bus/has_missed_notifications',
    '/bus/websocket_worker_bundle',
    '/websocket/health',
)

SESSION_ACTIVITY_KEY = 'tm_admin_last_activity'


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _pre_dispatch(cls, rule, args):
        super()._pre_dispatch(rule, args)
        cls._enforce_admin_idle_timeout()

    @classmethod
    def _enforce_admin_idle_timeout(cls):
        session = request.session
        if not session.uid:
            # Not logged in — nothing to time out.
            return

        # Some routes (auth='none') deliberately blank request.env's uid to
        # None for the duration of that request regardless of the actual
        # logged-in session, leaving request.env.user an EMPTY recordset —
        # calling has_group() on that raises (ensure_one on 0 records).
        # There's nothing meaningful to check in that case; the next normal
        # (auth='user'/'public') request from this same session will still
        # go through the real check below.
        user = request.env.user
        if not user or not user.has_group('base.group_system'):
            # Only admins get this tighter policy; everyone else keeps
            # Odoo's normal (much longer) session lifetime. Drop any stale
            # marker in case this session used to belong to an admin who
            # since lost the group.
            if SESSION_ACTIVITY_KEY in session:
                session.pop(SESSION_ACTIVITY_KEY, None)
            return

        if request.httprequest.path in IDLE_TIMEOUT_IGNORED_PATHS:
            # Background traffic — check, but don't refresh, the timer.
            last_activity = session.get(SESSION_ACTIVITY_KEY)
            if last_activity is not None and time.time() - last_activity > ADMIN_IDLE_TIMEOUT_SECONDS:
                session.pop(SESSION_ACTIVITY_KEY, None)
                raise SessionExpiredException('Your admin session expired after 30 minutes of inactivity.')
            return

        now = time.time()
        last_activity = session.get(SESSION_ACTIVITY_KEY)
        if last_activity is not None and now - last_activity > ADMIN_IDLE_TIMEOUT_SECONDS:
            session.pop(SESSION_ACTIVITY_KEY, None)
            _logger.info('Admin %s logged out after %ss of inactivity.', request.env.user.login, ADMIN_IDLE_TIMEOUT_SECONDS)
            raise SessionExpiredException('Your admin session expired after 30 minutes of inactivity.')

        session[SESSION_ACTIVITY_KEY] = now
