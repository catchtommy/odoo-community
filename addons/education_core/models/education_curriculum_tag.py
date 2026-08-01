# -*- coding: utf-8 -*-
from odoo import fields, models


class EducationCurriculumTag(models.Model):
    _name = 'education.curriculum.tag'
    _description = 'Education Tag'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    color = fields.Integer(string='Color')
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint('UNIQUE(name)', 'A tag with this name already exists.')
