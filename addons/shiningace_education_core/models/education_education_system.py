# -*- coding: utf-8 -*-
from odoo import api, fields, models


class EducationEducationSystem(models.Model):
    _name = 'education.education.system'
    _inherit = ['education.abstract.mixin', 'mail.thread']
    _description = 'Education System'
    _order = 'country_id, name'

    name = fields.Char(string='System Name', required=True, index=True, tracking=True,
                        help='e.g. UK National Curriculum, CBSE, IB, Common Core')
    code = fields.Char(string='System Code', size=20, index=True)
    country_id = fields.Many2one('education.country', string='Country', required=True, index=True, ondelete='restrict')
    description = fields.Text(translate=True)

    board_ids = fields.One2many('education.exam.board', 'education_system_id', string='Exam Boards')
    academic_level_ids = fields.One2many('education.academic.level', 'education_system_id', string='Academic Levels')

    board_count = fields.Integer(compute='_compute_counts')
    academic_level_count = fields.Integer(compute='_compute_counts')

    _code_country_unique = models.Constraint('UNIQUE(code, country_id)', 'System code must be unique per country.')

    @api.depends('board_ids', 'academic_level_ids')
    def _compute_counts(self):
        for rec in self:
            rec.board_count = len(rec.board_ids)
            rec.academic_level_count = len(rec.academic_level_ids)

    @api.depends('name', 'country_id.code')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.name} [{rec.country_id.code}]" if rec.country_id else rec.name

    def action_view_exam_boards(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Exam Boards',
            'res_model': 'education.exam.board',
            'view_mode': 'list,form',
            'domain': [('education_system_id', '=', self.id)],
            'context': {'default_education_system_id': self.id, 'default_country_id': self.country_id.id},
        }

    def action_view_academic_levels(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Academic Levels',
            'res_model': 'education.academic.level',
            'view_mode': 'list,form',
            'domain': [('education_system_id', '=', self.id)],
            'context': {'default_education_system_id': self.id},
        }
