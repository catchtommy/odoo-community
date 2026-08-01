# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class EducationCourseCurriculum(models.Model):
    """Pins a specific curriculum version to a course.

    Never points at "the latest version" — this row's curriculum_version_id
    is the mechanism that guarantees a course keeps using the exact version
    it was assigned to. Changing versions always means creating a new row
    (see course.master.action_assign_curriculum_version()), never editing
    curriculum_version_id on an existing one.
    """
    _name = 'education.course.curriculum'
    _inherit = ['education.abstract.mixin']
    _description = 'Course ↔ Curriculum Version Assignment'
    _order = 'course_id, assigned_date desc'

    course_id = fields.Many2one('course.master', required=True, index=True, ondelete='cascade')
    curriculum_version_id = fields.Many2one(
        'education.curriculum.version', string='Curriculum Version', required=True, index=True, ondelete='restrict',
    )
    curriculum_id = fields.Many2one(related='curriculum_version_id.curriculum_id', store=True, index=True)
    is_primary = fields.Boolean(default=True)
    assigned_date = fields.Datetime(default=fields.Datetime.now, required=True)
    assigned_by = fields.Many2one('res.users', default=lambda self: self.env.user)

    _course_version_unique = models.Constraint(
        'UNIQUE(course_id, curriculum_version_id)', 'This curriculum version is already assigned to this course.',
    )

    @api.constrains('curriculum_version_id')
    def _check_version_assignable(self):
        for rec in self:
            if rec.curriculum_version_id.state != 'published':
                raise ValidationError(
                    "Only a Published curriculum version can be assigned to a course "
                    "(current state: %s)." % rec.curriculum_version_id.state
                )
