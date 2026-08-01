# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StudentProfile(models.Model):
    _inherit = 'student.profile'

    progress_ids = fields.One2many('education.student.progress', 'student_id', string='Curriculum Progress')
    completed_lesson_count = fields.Integer(compute='_compute_lesson_progress_counts')
    in_progress_lesson_count = fields.Integer(compute='_compute_lesson_progress_counts')

    @api.depends('progress_ids.status')
    def _compute_lesson_progress_counts(self):
        for rec in self:
            rec.completed_lesson_count = len(rec.progress_ids.filtered(lambda p: p.status == 'completed'))
            rec.in_progress_lesson_count = len(rec.progress_ids.filtered(lambda p: p.status == 'in_progress'))
