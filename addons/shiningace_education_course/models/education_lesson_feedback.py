# -*- coding: utf-8 -*-
from odoo import fields, models


class EducationLessonFeedback(models.Model):
    _name = 'education.lesson.feedback'
    _inherit = ['education.abstract.mixin']
    _description = 'Lesson Feedback'
    _order = 'date desc'

    lesson_assignment_id = fields.Many2one('education.lesson.assignment', required=True, index=True, ondelete='cascade')
    author_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user)
    feedback_type = fields.Selection(
        selection=[('tutor', 'Tutor'), ('student', 'Student'), ('parent', 'Parent')],
        required=True, default='tutor',
    )
    rating = fields.Selection([('1', '1'), ('2', '2'), ('3', '3'), ('4', '4'), ('5', '5')], string='Rating')
    comments = fields.Text()
    date = fields.Datetime(default=fields.Datetime.now, required=True)
