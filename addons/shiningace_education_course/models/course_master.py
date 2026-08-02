# -*- coding: utf-8 -*-
from odoo import api, fields, models


class CourseMaster(models.Model):
    _inherit = 'course.master'

    course_curriculum_ids = fields.One2many('education.course.curriculum', 'course_id', string='Curriculum Assignments')
    curriculum_ids = fields.Many2many(
        'education.curriculum', string='Curricula', compute='_compute_curriculum_ids',
        help='Convenience view of the curricula attached to this course via its curriculum assignments.',
    )
    primary_curriculum_version_id = fields.Many2one(
        'education.curriculum.version', string='Primary Curriculum Version', compute='_compute_primary_curriculum_version_id',
    )
    lesson_assignment_ids = fields.One2many('education.lesson.assignment', 'course_id', string='Lesson Assignments')

    @api.depends('course_curriculum_ids.curriculum_id')
    def _compute_curriculum_ids(self):
        for rec in self:
            rec.curriculum_ids = rec.course_curriculum_ids.curriculum_id

    @api.depends('course_curriculum_ids.is_primary', 'course_curriculum_ids.curriculum_version_id')
    def _compute_primary_curriculum_version_id(self):
        for rec in self:
            primary = rec.course_curriculum_ids.filtered('is_primary')[:1]
            rec.primary_curriculum_version_id = primary.curriculum_version_id

    def action_assign_curriculum_version(self):
        """Open a pre-filled form to pin a (published) curriculum version to this course.

        Always creates a new education.course.curriculum row — an existing
        assignment's curriculum_version_id is never mutated in place, so a
        course's history of "which version was taught when" is preserved.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Assign Curriculum Version',
            'res_model': 'education.course.curriculum',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_course_id': self.id,
                'default_is_primary': not bool(self.course_curriculum_ids),
            },
        }

    def action_view_lesson_assignments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Lesson Assignments',
            'res_model': 'education.lesson.assignment',
            'view_mode': 'list,form',
            'domain': [('course_id', '=', self.id)],
        }
