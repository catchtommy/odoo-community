# -*- coding: utf-8 -*-
from odoo import api, fields, models


class EducationSubtopic(models.Model):
    _name = 'education.subtopic'
    _inherit = ['education.abstract.mixin', 'education.curriculum.approval.mixin']
    _description = 'Curriculum Subtopic'
    _order = 'topic_id, sequence, name'
    _parent_store = True
    _parent_name = 'parent_subtopic_id'

    name = fields.Char(required=True, index=True)
    topic_id = fields.Many2one('education.topic', required=True, index=True, ondelete='cascade')
    curriculum_version_id = fields.Many2one(related='topic_id.curriculum_version_id', store=True, index=True)
    curriculum_id = fields.Many2one(related='topic_id.curriculum_id', store=True, index=True)
    parent_subtopic_id = fields.Many2one('education.subtopic', string='Parent Subtopic', index=True, ondelete='cascade')
    parent_path = fields.Char(index=True)
    child_subtopic_ids = fields.One2many('education.subtopic', 'parent_subtopic_id', string='Child Subtopics')
    sequence = fields.Integer(default=10)
    description = fields.Text(translate=True)

    learning_objective_ids = fields.One2many('education.learning.objective', 'subtopic_id', string='Learning Objectives')

    @api.depends('name', 'topic_id.name')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.topic_id.name} / {rec.name}" if rec.topic_id else rec.name
