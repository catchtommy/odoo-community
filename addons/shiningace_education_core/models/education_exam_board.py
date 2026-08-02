# -*- coding: utf-8 -*-
from odoo import api, fields, models


class EducationExamBoard(models.Model):
    _name = 'education.exam.board'
    _inherit = ['education.abstract.mixin', 'mail.thread']
    _description = 'Education Exam Board'
    _order = 'country_id, name'

    name = fields.Char(string='Board Name', required=True, index=True, tracking=True,
                        help='e.g. AQA, Edexcel, Cambridge, IB, College Board')
    code = fields.Char(string='Board Code', size=20, index=True)
    country_id = fields.Many2one('education.country', string='Country', required=True, index=True, ondelete='restrict')
    education_system_id = fields.Many2one(
        'education.education.system', string='Education System', index=True, ondelete='restrict',
        domain="[('country_id', '=', country_id)]",
    )
    description = fields.Text(translate=True)

    _code_country_unique = models.Constraint('UNIQUE(code, country_id)', 'Board code must be unique per country.')

    @api.depends('name', 'country_id.code')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.name} [{rec.country_id.code}]" if rec.country_id else rec.name
