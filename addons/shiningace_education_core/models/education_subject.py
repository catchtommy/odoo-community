# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class EducationSubject(models.Model):
    _name = 'education.subject'
    _inherit = ['education.abstract.mixin', 'mail.thread']
    _description = 'Education Subject'
    _order = 'name asc'

    name = fields.Char(string='Subject Name', required=True, index=True, tracking=True,
                        help='e.g. Mathematics, English, Biology, Computer Science')
    code = fields.Char(
        string='Subject Code', required=True, size=10, index=True,
        help='Short uppercase code, e.g. M (Maths), E (English), S (Science). Used in skill codes.',
    )
    description = fields.Text(translate=True)

    _code_unique = models.Constraint('UNIQUE(code)', 'Subject code must be unique.')

    @api.constrains('code')
    def _check_code_uppercase(self):
        for rec in self:
            if rec.code and rec.code != rec.code.upper():
                raise ValidationError("Subject code must be UPPERCASE (e.g. M, E, S, SCI).")

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"[{rec.code}] {rec.name}" if rec.code else rec.name
