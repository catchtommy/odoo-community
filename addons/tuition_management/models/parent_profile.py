# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from .tz_utils import get_tz_selection, DEFAULT_TIMEZONE
from .user_permission import require_permission, user_has_permission
from .phone_codes import COUNTRY_PHONE_CODES


class ParentProfile(models.Model):
    _name = 'parent.profile'
    _description = 'Parent Profile'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Full Name', required=True)
    partner_id = fields.Many2one('res.partner', string='Contact', required=True, ondelete='cascade')
    email = fields.Char(string='Email')
    phone = fields.Char(string='Phone')
    country_code = fields.Selection(COUNTRY_PHONE_CODES, string='Country Code', default='+1')
    timezone = fields.Selection(selection=get_tz_selection, string='Timezone', required=True, default=DEFAULT_TIMEZONE)
    status = fields.Selection(
        selection=[('active', 'Active'), ('inactive', 'Inactive')],
        string='Status',
        default='active',
        required=True,
    )
    address_line_1 = fields.Char(string='Address Line 1')
    address_line_2 = fields.Char(string='Address Line 2')
    address_line_3 = fields.Char(string='Address Line 3')
    address_line_4 = fields.Char(string='Address Line 4')
    zip_code = fields.Char(string='Zip Code')
    student_ids = fields.One2many('student.profile', 'parent_id', string='Children')
    notes = fields.Text(string='Notes')
    has_portal_access = fields.Boolean(string='Has Portal Access', compute='_compute_portal_access', store=True)
    can_edit_parent = fields.Boolean(string='Can Edit Parent', compute='_compute_can_edit_parent')

    @api.depends_context('uid')
    def _compute_can_edit_parent(self):
        can_edit = (
            self.env.user.has_group('base.group_system') or
            user_has_permission(self.env.user, 'parent_edit')
        )
        for rec in self:
            rec.can_edit_parent = can_edit

    @api.depends('partner_id.user_ids')
    def _compute_portal_access(self):
        for rec in self:
            rec.has_portal_access = bool(rec.partner_id.user_ids)

    def action_invite_to_portal(self):
        self.ensure_one()
        if not self.email:
            raise UserError("Email is required to create a portal login.")
        ctx = {'default_profile_model': 'parent.profile', 'default_profile_id': self.id,
               'default_name': self.name, 'default_email': self.email, 'default_login': self.email}
        if self.partner_id:
            user = self.env['res.users'].sudo().search([('partner_id', '=', self.partner_id.id)], limit=1)
            if user:
                ctx.update({'default_is_existing_user': True, 'default_existing_user_id': user.id, 'default_login': user.login})
        return {'type': 'ir.actions.act_window', 'name': 'Manage Portal Access',
                'res_model': 'portal.access.wizard', 'view_mode': 'form', 'target': 'new', 'context': ctx}

    @api.constrains('email', 'phone')
    def _check_contact_info(self):
        for rec in self:
            if not rec.email and not rec.phone:
                raise ValidationError("Please provide either an email address or a phone number for the parent.")
            if rec.phone and not rec.country_code:
                raise ValidationError("Please provide a country code when providing a phone number.")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('partner_id'):
                partner_vals = {
                    'name': vals.get('name', 'Unknown Parent'),
                    'email': vals.get('email'),
                    'phone': '%s%s' % (vals.get('country_code', ''), vals.get('phone', '')) if vals.get('phone') else False,
                }
                partner = self.env['res.partner'].create(partner_vals)
                vals['partner_id'] = partner.id
        records = super().create(vals_list)
        return records

    def write(self, vals):
        require_permission(self.env.user, 'parent_edit')
        res = super().write(vals)
        for rec in self:
            if rec.partner_id:
                partner_vals = {}
                if 'name' in vals: partner_vals['name'] = rec.name
                if 'email' in vals: partner_vals['email'] = rec.email
                if 'phone' in vals or 'country_code' in vals:
                    partner_vals['phone'] = '%s%s' % (rec.country_code or '', rec.phone or '')
                if partner_vals:
                    rec.partner_id.write(partner_vals)
        return res

    def unlink(self):
        require_permission(self.env.user, 'parent_delete')
        return super().unlink()
