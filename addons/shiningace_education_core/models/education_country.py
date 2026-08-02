# -*- coding: utf-8 -*-
from odoo import api, fields, models


class EducationCountry(models.Model):
    _name = 'education.country'
    _inherit = ['education.abstract.mixin']
    _description = 'Education Country'
    _order = 'name asc'

    name = fields.Char(string='Country Name', required=True, index=True)
    code = fields.Char(string='Country Code', size=10, index=True, help='Short code, e.g. UK, US, IN')

    education_system_ids = fields.One2many('education.education.system', 'country_id', string='Education Systems')
    board_ids = fields.One2many('education.exam.board', 'country_id', string='Exam Boards')

    education_system_count = fields.Integer(compute='_compute_counts', string='Education System Count')
    board_count = fields.Integer(compute='_compute_counts', string='Exam Board Count')

    _code_unique = models.Constraint('UNIQUE(code)', 'Country code must be unique.')

    @api.depends('education_system_ids', 'board_ids')
    def _compute_counts(self):
        for rec in self:
            rec.education_system_count = len(rec.education_system_ids)
            rec.board_count = len(rec.board_ids)

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.name} ({rec.code})" if rec.code else rec.name

    def action_view_education_systems(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Education Systems',
            'res_model': 'education.education.system',
            'view_mode': 'list,form',
            'domain': [('country_id', '=', self.id)],
            'context': {'default_country_id': self.id},
        }

    def action_view_exam_boards(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Exam Boards',
            'res_model': 'education.exam.board',
            'view_mode': 'list,form',
            'domain': [('country_id', '=', self.id)],
            'context': {'default_country_id': self.id},
        }
