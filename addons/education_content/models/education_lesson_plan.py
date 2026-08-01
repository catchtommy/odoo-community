# -*- coding: utf-8 -*-
from odoo import fields, models


class EducationLessonPlan(models.Model):
    _name = 'education.lesson.plan'
    _inherit = ['education.abstract.mixin']
    _description = 'Lesson Plan'
    _order = 'lesson_id, sequence'

    name = fields.Char(required=True, default='Lesson Plan')
    lesson_id = fields.Many2one('education.lesson', required=True, index=True, ondelete='cascade')
    topic_id = fields.Many2one(related='lesson_id.topic_id', store=True, index=True)
    curriculum_version_id = fields.Many2one(related='lesson_id.curriculum_version_id', store=True, index=True)
    plan_text = fields.Html(translate=True, help='Teaching plan body: starter / main / plenary, examples, differentiation, etc.')
    duration_minutes = fields.Integer(string='Duration (min)')
    sequence = fields.Integer(default=10)
    state = fields.Selection(
        selection=[('draft', 'Draft'), ('published', 'Published')], default='draft', required=True,
    )
