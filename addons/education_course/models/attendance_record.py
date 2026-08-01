# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AttendanceRecord(models.Model):
    _inherit = 'attendance.record'

    lesson_assignment_id = fields.Many2one(
        'education.lesson.assignment', string='Curriculum Lesson', compute='_compute_lesson_assignment_id', store=True,
        help='The curriculum lesson taught during this occurrence, if one was assigned.',
    )

    @api.depends('class_schedule_occurrence_id')
    def _compute_lesson_assignment_id(self):
        assignments = self.env['education.lesson.assignment'].search([
            ('class_schedule_occurrence_id', 'in', self.class_schedule_occurrence_id.ids),
        ])
        by_occurrence = {a.class_schedule_occurrence_id.id: a for a in assignments}
        for rec in self:
            rec.lesson_assignment_id = by_occurrence.get(rec.class_schedule_occurrence_id.id, False)
