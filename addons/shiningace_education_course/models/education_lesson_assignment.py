# -*- coding: utf-8 -*-
from odoo import fields, models


class EducationLessonAssignment(models.Model):
    """Bridges scheduling and curriculum content: links one class.schedule.occurrence
    (the calendar slot, from tuition_management) to one education.lesson (the
    curriculum content to teach). This is what resolves "today's lesson" for
    the tutor/student portal pages.

    Unrelated to tuition_management's ``course.assignment`` model, which means
    "homework" in that app — same English word, different concept.
    """
    _name = 'education.lesson.assignment'
    _inherit = ['education.abstract.mixin', 'mail.thread']
    _description = 'Lesson Assignment (Schedule ↔ Curriculum Lesson)'
    _order = 'class_schedule_occurrence_id'

    class_schedule_occurrence_id = fields.Many2one(
        'class.schedule.occurrence', string='Scheduled Occurrence', required=True, index=True, ondelete='cascade',
    )
    course_id = fields.Many2one(related='class_schedule_occurrence_id.course_id', store=True, index=True)
    tutor_id = fields.Many2one(related='class_schedule_occurrence_id.tutor_id', store=True, index=True)
    start_datetime = fields.Datetime(related='class_schedule_occurrence_id.start_datetime', store=True)

    lesson_id = fields.Many2one('education.lesson', required=True, index=True, ondelete='restrict')
    topic_id = fields.Many2one(related='lesson_id.topic_id', store=True, index=True)

    status = fields.Selection(
        selection=[
            ('planned', 'Planned'),
            ('in_progress', 'In Progress'),
            ('completed', 'Completed'),
            ('skipped', 'Skipped'),
        ],
        default='planned', required=True, index=True, tracking=True,
    )
    actual_duration_minutes = fields.Integer(string='Actual Duration (min)')
    notes = fields.Text(help="Tutor's freeform notes on how the lesson went.")

    feedback_ids = fields.One2many('education.lesson.feedback', 'lesson_assignment_id', string='Feedback')

    _occurrence_unique = models.Constraint(
        'UNIQUE(class_schedule_occurrence_id)',
        'This scheduled occurrence already has a curriculum lesson assigned.',
    )
