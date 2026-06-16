# -*- coding: utf-8 -*-
from odoo import models, fields, api


class QbQuestionTag(models.Model):
    _name = 'qb.question.tag'
    _description = 'Question Tag'
    _order = 'name'

    name = fields.Char(string='Tag Name', required=True, translate=True)
    color = fields.Integer(string='Color Index')
    question_count = fields.Integer(compute='_compute_question_count', string='# Questions')
    
    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'Tag name must be unique!')
    ]
    
    @api.depends()
    def _compute_question_count(self):
        for tag in self:
            tag.question_count = self.env['qb.question'].search_count([
                ('tag_ids', 'in', tag.id)
            ])
