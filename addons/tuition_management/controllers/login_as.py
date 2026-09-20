# -*- coding: utf-8 -*-
import logging
import time

from werkzeug.urls import url_quote_plus

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request

_logger = logging.getLogger(__name__)

# "Return to Admin" switches straight back to the admin account with no
# password check — by design, since the admin already proved their identity
# to start the impersonation. But that also means the impersonated session
# is a standing no-password path back to full admin for as long as it
# carries the marker below. Capping it well under the normal session
# timeout limits how long a forgotten/open tab (or a stolen session cookie)
# stays exploitable as an admin backdoor.
RETURN_TO_ADMIN_VALIDITY_SECONDS = 30 * 60


def _switch_session_to(session, env, user):
    """Flip the current session over to `user` without needing their
    password — mirrors what odoo.http.Session.finalize() does for a normal
    login, minus the credential check (the caller has already established
    that switching is authorized)."""
    user_env = env(user=user.id)
    user_context = dict(user_env['res.users'].context_get())
    session.should_rotate = True
    session.update({
        'db': user_env.registry.db_name,
        'login': user.login,
        'uid': user.id,
        'context': user_context,
        'session_token': user._compute_session_token(session.sid),
    })


class LoginAsController(http.Controller):

    @http.route('/web/login_as/<string:token>', type='http', auth='user', website=False)
    def login_as(self, token, **kw):
        """Consumes a one-time token created by
        <student|tutor|parent>.profile.action_login_as_<role>() and switches
        the *current* session (the one in the newly-opened window) over to
        the target portal user, so the admin sees exactly what that user
        sees. Restricted to full admins."""
        env = request.env
        if not env.user.has_group('base.group_system'):
            raise AccessError('Only administrators can log in as another user.')

        token_rec = env['tuition.login.as.token']._consume(token, env.user.id)
        target_user = token_rec.target_user_id
        if not target_user.exists() or not target_user.active:
            return request.redirect('/odoo')

        profile = False
        role = False
        if token_rec.profile_model and token_rec.profile_id:
            profile = env[token_rec.profile_model].sudo().browse(token_rec.profile_id)
            role = {
                'student.profile': 'student',
                'tutor.profile': 'tutor',
                'parent.profile': 'parent',
            }.get(token_rec.profile_model)
        if role and profile and profile.exists():
            env['tuition.login.as.log']._log(env.user, target_user, role, profile)

        admin_uid = env.user.id
        admin_login = env.user.login
        session = request.session
        _switch_session_to(session, env, target_user)
        # Remember who we came from so the impersonated portal session can
        # offer a one-click "Return to Admin" — set *after* the switch so
        # these keys live in the impersonated session, not the admin's.
        # login_as_admin_expiry caps how long that shortcut stays usable
        # (see RETURN_TO_ADMIN_VALIDITY_SECONDS above).
        session['login_as_admin_uid'] = admin_uid
        session['login_as_admin_login'] = admin_login
        session['login_as_admin_expiry'] = time.time() + RETURN_TO_ADMIN_VALIDITY_SECONDS

        return request.redirect('/my/dashboard')

    @http.route('/web/login_as/return', type='http', auth='user', website=False)
    def login_as_return(self, **kw):
        """Switches back to the admin account that started a "Login as"
        session. Only works from inside a session that actually carries the
        login_as_admin_uid marker set by login_as() above."""
        session = request.session
        admin_uid = session.get('login_as_admin_uid')
        expiry = session.get('login_as_admin_expiry')
        session.pop('login_as_admin_uid', None)
        session.pop('login_as_admin_login', None)
        session.pop('login_as_admin_expiry', None)
        if not admin_uid:
            return request.redirect('/my/dashboard')
        if not expiry or time.time() > expiry:
            # The shortcut back to admin has expired — the admin must log
            # out and back in with their own credentials instead.
            message = url_quote_plus('Your admin session has expired. Please log out and log back in as admin.')
            return request.redirect('/my/dashboard?vc_error=%s' % message)

        env = request.env
        admin_user = env['res.users'].sudo().browse(admin_uid)
        if not admin_user.exists() or not admin_user.active or not admin_user.has_group('base.group_system'):
            return request.redirect('/my/dashboard')

        _switch_session_to(session, env, admin_user)
        return request.redirect('/odoo')
