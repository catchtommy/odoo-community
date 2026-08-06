# -*- coding: utf-8 -*-
from odoo import api, fields, models


class EducationLesson(models.Model):
    """A curriculum teaching unit (e.g. "Fractions — Lesson 3: Equivalent Fractions").

    Distinct from ``class.schedule.occurrence`` (tuition_management), which is
    a specific calendar time-slot. ``education_course`` bridges the two via
    ``education.lesson.assignment``.
    """
    _name = 'education.lesson'
    _inherit = ['education.abstract.mixin', 'education.curriculum.approval.mixin', 'mail.thread']
    _description = 'Lesson'
    _order = 'topic_id, sequence, name'

    name = fields.Char(required=True, index=True)
    topic_id = fields.Many2one('education.topic', required=True, index=True, ondelete='restrict')
    subtopic_id = fields.Many2one(
        'education.subtopic', index=True, ondelete='restrict', domain="[('topic_id', '=', topic_id)]",
    )
    curriculum_version_id = fields.Many2one(related='topic_id.curriculum_version_id', store=True, index=True)
    subject_id = fields.Many2one(related='topic_id.subject_id', store=True, index=True)

    sequence = fields.Integer(default=10)
    duration_minutes = fields.Integer(string='Planned Duration (min)', default=60)
    objective_ids = fields.Many2many('education.learning.objective', string='Learning Objectives')

    lesson_plan_ids = fields.One2many('education.lesson.plan', 'lesson_id', string='Lesson Plans')
    content_ids = fields.One2many('education.lesson.content', 'lesson_id', string='Content')
    content_count = fields.Integer(compute='_compute_content_count')

    state = fields.Selection(
        selection=[('draft', 'Draft'), ('published', 'Published'), ('archived', 'Archived')],
        default='draft', required=True, index=True, tracking=True,
        help='Lesson materials can be edited/republished independently of the curriculum '
             'approval cycle, since they are teaching material, not curriculum structure.',
    )

    @api.depends('content_ids')
    def _compute_content_count(self):
        for rec in self:
            rec.content_count = len(rec.content_ids)

    def action_publish(self):
        self.write({'state': 'published'})

    def action_archive_lesson(self):
        self.write({'state': 'archived'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})
