# -*- coding: utf-8 -*-
from odoo import fields, models


class EducationContentCategory(models.Model):
    _name = 'education.content.category'
    _description = 'Content Category'
    _order = 'sequence, name'
    _parent_store = True

    name = fields.Char(required=True, translate=True)
    parent_id = fields.Many2one('education.content.category', string='Parent Category', index=True, ondelete='cascade')
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many('education.content.category', 'parent_id', string='Child Categories')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
