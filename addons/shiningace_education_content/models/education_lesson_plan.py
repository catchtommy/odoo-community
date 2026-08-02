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
    summary = fields.Text(help="A high-level overview of the lesson's core focus.")
    key_concepts = fields.Html(help='Key theoretical points covered.')
    agenda = fields.Html(
        help='Step-by-step breakdown of the lesson (e.g. Warm-up, Direct Instruction, '
             'Guided Practice, Exit Ticket/Assessment).',
    )
    exam_tip = fields.Text(
        string='Exam / Test-Taking Tip',
        help='A specific test-taking tip tailored to the relevant exam format, if this '
             'curriculum is exam-prep (SAT, AP, GCSE, etc.). Leave blank otherwise.',
    )
    plan_text = fields.Html(
        string='Additional Notes', translate=True,
        help='Freeform notes that don\'t fit the structured fields above.',
    )
    duration_minutes = fields.Integer(string='Duration (min)')
    sequence = fields.Integer(default=10)
    state = fields.Selection(
        selection=[('draft', 'Draft'), ('published', 'Published')], default='draft', required=True,
    )
