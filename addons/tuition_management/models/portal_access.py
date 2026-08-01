# -*- coding: utf-8 -*-
import random
import re
from odoo import models, fields, api
from odoo.exceptions import UserError


class PortalAccessWizard(models.TransientModel):
    _name = 'portal.access.wizard'
    _description = 'Portal Access Wizard'

    profile_model = fields.Char(string='Profile Model', required=True)
    profile_id = fields.Integer(string='Profile ID', required=True)
    name = fields.Char(string='Name', readonly=True)
    email = fields.Char(string='Email', readonly=True)
    login = fields.Char(string='Login (Username)', required=True)
    password = fields.Char(string='Password', required=True)
    confirm_password = fields.Char(string='Confirm Password', required=True)
    is_existing_user = fields.Boolean(string='Existing User', readonly=True)
    existing_user_id = fields.Many2one('res.users', string='Existing Portal User', readonly=True)

    @api.model
    def _generate_login_from_name(self, name):
        base_login = re.sub(r'[^a-z0-9]', '', (name or 'user').lower()) or 'user'
        login, counter = base_login, 1
        while self.env['res.users'].sudo().with_context(active_test=False).search([('login', '=', login)], limit=1):
            counter += 1
            login = '%s%d' % (base_login, counter)
        return login

    @api.model
    def _generate_password(self):
        words = ['apple', 'brave', 'cloud', 'delta', 'eagle', 'flame', 'grace', 'honey',
                 'ivory', 'jewel', 'knack', 'lemon', 'mango', 'noble', 'ocean', 'pearl',
                 'quest', 'river', 'solar', 'tiger', 'ultra', 'vivid', 'whale', 'xenon',
                 'yacht', 'zebra', 'amber', 'blaze', 'coral', 'drift', 'ember', 'frost']
        return '%s%s@%d' % (random.choice(words).capitalize(), random.choice(words).capitalize(), random.randint(1000, 9999))

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        profile_model = res.get('profile_model') or self.env.context.get('default_profile_model')
        profile_id = res.get('profile_id') or self.env.context.get('default_profile_id')
        profile_name = res.get('name') or self.env.context.get('default_name', '')
        if profile_model and profile_id:
            profile = self.env[profile_model].browse(profile_id)
            if profile.exists() and profile.partner_id:
                user = self.env['res.users'].sudo().search([('partner_id', '=', profile.partner_id.id)], limit=1)
                if user:
                    pwd = self._generate_password()
                    res.update({'is_existing_user': True, 'existing_user_id': user.id,
                                'login': user.login, 'password': pwd, 'confirm_password': pwd})
                    return res
        if not res.get('login') or res.get('login') == res.get('email'):
            res['login'] = self._generate_login_from_name(profile_name)
        pwd = self._generate_password()
        res.update({'password': pwd, 'confirm_password': pwd})
        return res

    def action_generate_password(self):
        self.ensure_one()
        pwd = self._generate_password()
        self.write({'password': pwd, 'confirm_password': pwd})
        return {'type': 'ir.actions.act_window', 'res_model': 'portal.access.wizard',
                'view_mode': 'form', 'res_id': self.id, 'target': 'new'}

    def _assign_portal_group(self, user):
        group_portal = self.env.ref('base.group_portal')
        user.sudo().write({'group_ids': [(6, 0, [group_portal.id])]})
        self.env.invalidate_all()

    def action_create_portal_user(self):
        self.ensure_one()
        if self.password != self.confirm_password:
            raise UserError("Passwords do not match.")
        if len(self.password) < 6:
            raise UserError("Password must be at least 6 characters.")
        profile = self.env[self.profile_model].browse(self.profile_id)
        if not profile.exists():
            raise UserError("Profile record not found.")
        domain = [('login', '=', self.login)]
        if self.is_existing_user and self.existing_user_id:
            domain.append(('id', '!=', self.existing_user_id.id))
        duplicate = self.env['res.users'].sudo().with_context(active_test=False).search(domain, limit=1)
        if duplicate:
            raise UserError(f"The username '{self.login}' is already taken by {duplicate.name}.")
        if self.is_existing_user and self.existing_user_id:
            user = self.existing_user_id.sudo()
            update_vals = {'password': self.password, 'active': True}
            if self.login and self.login != user.login:
                update_vals['login'] = self.login
                if user.partner_id: user.partner_id.sudo().write({'email': self.login})
                if hasattr(profile, 'email'): profile.sudo().write({'email': self.login})
            user.write(update_vals)
            self._assign_portal_group(user)
            return {'type': 'ir.actions.client', 'tag': 'display_notification',
                    'params': {'title': 'Portal Access Updated', 'message': f'Updated for {self.name}. Login: {self.login}',
                               'type': 'success', 'sticky': False, 'next': {'type': 'ir.actions.act_window_close'}}}

        if not profile.partner_id:
            country = getattr(profile, 'country_code', '') or ''
            phonen = getattr(profile, 'phone', '') or ''
            # sudo(): auto-provisioning a linked Contact is an internal
            # implementation detail, not something that should require the
            # acting user to separately hold Sales/Contact-Creation access.
            partner = self.env['res.partner'].sudo().create({
                'name': profile.name, 'email': profile.email,
                'phone': f"{country}{phonen}"
            })
            profile.partner_id = partner.id
        else:
            partner = profile.partner_id
            if not partner.email: partner.email = profile.email
        existing_user = self.env['res.users'].sudo().with_context(active_test=False).search([('partner_id', '=', partner.id)], limit=1)
        if existing_user:
            existing_user.sudo().write({'login': self.login, 'password': self.password, 'active': True})
            self._assign_portal_group(existing_user.sudo())
        else:
            new_user = self.env['res.users'].sudo().with_context(no_reset_password=True).create(
                {'partner_id': partner.id, 'login': self.login, 'password': self.password, 'active': True})
            self._assign_portal_group(new_user)
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': 'Portal Access Activated', 'message': f'Created for {self.name}. Login: {self.login}',
                           'type': 'success', 'sticky': False, 'next': {'type': 'ir.actions.act_window_close'}}}

    def action_deactivate_portal_user(self):
        self.ensure_one()
        if self.is_existing_user and self.existing_user_id:
            self.existing_user_id.sudo().write({'active': False})
            return {'type': 'ir.actions.client', 'tag': 'display_notification',
                    'params': {'title': 'Deactivated', 'message': f'Access disabled for {self.name}.',
                               'type': 'warning', 'sticky': False, 'next': {'type': 'ir.actions.act_window_close'}}}
        raise UserError("No existing portal user found to deactivate.")
