# -*- coding: utf-8 -*-
from odoo import fields, models


class EducationCurriculum(models.Model):
    """Reverse-relation fields needed to scope which tutors may view/
    contribute to a curriculum — added here (not on the base model in
    shiningace_education_curriculum) because both education.curriculum.access
    and education.course.curriculum/course.master only exist once this
    module (which bridges curriculum <-> tuition_management) is installed.
    """
    _inherit = 'education.curriculum'

    access_ids = fields.One2many(
        'education.curriculum.access', 'curriculum_id', string='Contributor Access Grants',
    )
    course_curriculum_ids = fields.One2many(
        'education.course.curriculum', 'curriculum_id', string='Course Assignments',
    )
