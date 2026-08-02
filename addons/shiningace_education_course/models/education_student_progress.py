# -*- coding: utf-8 -*-
from odoo import fields, models


class EducationStudentProgress(models.Model):
    """Per-student, per-lesson completion tracking.

    Kept minimal in Phase 1 so the "lesson taught -> progress recorded" loop
    closes within education_course's own scope. The future education_progress
    module is expected to build analytics/rollups over this table rather than
    redefining it.
    """
    _name = 'education.student.progress'
    _inherit = ['education.abstract.mixin']
    _description = 'Student Lesson Progress'
    _order = 'student_id, lesson_id'

    student_id = fields.Many2one('student.profile', required=True, index=True, ondelete='cascade')
    lesson_id = fields.Many2one('education.lesson', required=True, index=True, ondelete='cascade')
    curriculum_version_id = fields.Many2one(related='lesson_id.curriculum_version_id', store=True, index=True)

    status = fields.Selection(
        selection=[
            ('not_started', 'Not Started'),
            ('in_progress', 'In Progress'),
            ('completed', 'Completed'),
            ('needs_review', 'Needs Review'),
        ],
        default='not_started', required=True, index=True,
    )
    completion_date = fields.Datetime()
    mastery_score = fields.Float(help='Populated later by assessment/progress modules.')

    _student_lesson_unique = models.Constraint(
        'UNIQUE(student_id, lesson_id)', 'Progress for this student/lesson combination already exists.',
    )
