# -*- coding: utf-8 -*-
import logging
import uuid
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

# A "Login as" link is only valid for a short window between the admin
# clicking the button (server-side token creation) and the browser
# actually loading it. Single-use on top of that.
TOKEN_VALIDITY_MINUTES = 2


class LoginAsToken(models.TransientModel):
    """One-time, short-lived token that lets the admin's *next* request
    switch the session to the target portal user's account, without
    needing (or storing) that user's password.

    Kept separate from the actual session switch so that the button click
    (an RPC on the backend form) only ever returns a URL to open — the
    browser, not the server, then navigates to it.
    """
    _name = 'tuition.login.as.token'
    _description = 'Admin "Login As" One-Time Token'

    token = fields.Char(required=True, index=True)
    admin_user_id = fields.Many2one('res.users', required=True, index=True)
    target_user_id = fields.Many2one('res.users', required=True)
    profile_model = fields.Char()
    profile_id = fields.Integer()
    used = fields.Boolean(default=False)

    @api.model
    def _check_can_login_as(self, actor, target_user):
        """Who may impersonate whom. Any internal user who can reach the
        Users → Students/Tutors/Parents screens may use "Login as", but only
        full admins may switch into an internal (non-portal) account —
        otherwise a staff member could use a tutor who also has a backend
        login to pick up rights they don't have themselves."""
        if not actor.has_group('base.group_user'):
            raise AccessError('Only internal users can log in as another user.')
        if not actor.has_group('base.group_system') and not target_user.share:
            raise AccessError('Only administrators can log in as an internal user.')

    @api.model
    def _action_login_as(self, profile, role):
        """Shared body of <student|tutor|parent>.profile.action_login_as_<role>():
        find the profile's portal user, issue a one-time token and return
        the URL that performs the session switch."""
        profile.ensure_one()
        # The caller must be able to see this profile themselves — "Login
        # as" must not become a way around record rules on the profiles.
        profile.check_access('read')
        if not profile.has_portal_access:
            raise UserError('This %s does not have portal access yet.' % role)
        user = self.env['res.users'].sudo().search([
            ('partner_id', '=', profile.partner_id.id),
        ], limit=1)
        if not user:
            raise UserError('No portal user found for this %s.' % role)
        self._check_can_login_as(self.env.user, user)
        token = self._create_for(
            self.env.user, user, profile_model=profile._name, profile_id=profile.id)
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/login_as/%s' % token,
            'target': 'self',
        }

    @api.model
    def _create_for(self, admin_user, target_user, profile_model=False, profile_id=False):
        token = uuid.uuid4().hex
        self.sudo().create({
            'token': token,
            'admin_user_id': admin_user.id,
            'target_user_id': target_user.id,
            'profile_model': profile_model,
            'profile_id': profile_id,
        })
        return token

    @api.model
    def _consume(self, token, admin_uid):
        """Validate and burn a token, returning the record's target_user_id
        and profile pointer. Raises if the token is missing, expired,
        already used, or was not the one issued to this admin."""
        cutoff = fields.Datetime.now() - timedelta(minutes=TOKEN_VALIDITY_MINUTES)
        rec = self.sudo().search([
            ('token', '=', token),
            ('admin_user_id', '=', admin_uid),
            ('used', '=', False),
            ('create_date', '>=', cutoff),
        ], limit=1)
        if not rec:
            raise AccessError('This "Login as" link is invalid or has expired. Please click the button again.')
        rec.write({'used': True})
        return rec


class LoginAsLog(models.Model):
    """Persistent audit trail of every time an admin used "Login as" to view
    the portal as a student/tutor/parent. Kept as its own model (rather than
    chatter on the profile) so it works uniformly across all three profile
    models regardless of whether they have the mail.thread mixin, and stays
    easy to review as a single list."""
    _name = 'tuition.login.as.log'
    _description = 'Admin "Login As" Audit Log'
    _order = 'create_date desc'
    _rec_name = 'target_user_id'

    admin_user_id = fields.Many2one('res.users', string='Admin', required=True, readonly=True)
    target_user_id = fields.Many2one('res.users', string='Logged In As', required=True, readonly=True)
    role = fields.Selection([
        ('student', 'Student'),
        ('tutor', 'Tutor'),
        ('parent', 'Parent'),
    ], required=True, readonly=True)
    profile_model = fields.Char(readonly=True)
    profile_id = fields.Integer(readonly=True)
    profile_name = fields.Char(string='Profile', readonly=True)

    @api.model
    def _log(self, admin_user, target_user, role, profile):
        self.sudo().create({
            'admin_user_id': admin_user.id,
            'target_user_id': target_user.id,
            'role': role,
            'profile_model': profile._name,
            'profile_id': profile.id,
            'profile_name': profile.display_name,
        })
        _logger.info(
            'Admin "Login as": %s (uid %s) logged in as %s user %s (uid %s) via %s #%s',
            admin_user.login, admin_user.id, role, target_user.login, target_user.id,
            profile._name, profile.id,
        )

    def action_open_profile(self):
        self.ensure_one()
        if not self.profile_model or not self.profile_id:
            raise UserError('The source profile record is no longer available.')
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.profile_model,
            'res_id': self.profile_id,
            'view_mode': 'form',
            'target': 'current',
        }
