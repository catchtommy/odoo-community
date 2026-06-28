# -*- coding: utf-8 -*-
from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    tutor_profile_id = fields.Many2one(
        'tutor.profile',
        string='Tutor Profile',
        compute='_compute_tutor_profile_id',
        store=False,
    )

    def _compute_tutor_profile_id(self):
        for emp in self:
            emp.tutor_profile_id = self.env['tutor.profile'].search(
                [('employee_id', '=', emp.id)], limit=1
            )

    # Synced fields: hr.employee field → tutor field
    _TUTOR_SYNC_MAP = [
        ('name', 'name'),
        ('work_email', 'email'),
        ('work_phone', 'phone'),
        ('tz', 'timezone'),
    ]

    def write(self, vals):
        result = super().write(vals)
        if self.env.context.get('syncing_tutor_employee'):
            return result
        tutor_vals = {tf: vals[ef] for ef, tf in self._TUTOR_SYNC_MAP if ef in vals}
        if not tutor_vals:
            return result
        for emp in self:
            tutor = self.env['tutor.profile'].search([('employee_id', '=', emp.id)], limit=1)
            if tutor:
                tutor.with_context(syncing_tutor_employee=True).write(tutor_vals)
        return result

    def action_open_tutor_profile(self):
        self.ensure_one()
        tutor = self.env['tutor.profile'].search([('employee_id', '=', self.id)], limit=1)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'tutor.profile',
            'res_id': tutor.id,
            'view_mode': 'form',
            'target': 'current',
        }
