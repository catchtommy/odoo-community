# -*- coding: utf-8 -*-
from odoo import models


class MarkAttendanceWizard(models.TransientModel):
    _inherit = 'mark.attendance.wizard'

    def action_confirm(self):
        result = super().action_confirm()
        occurrence = self.occurrence_id
        if occurrence.lesson_status == 'completed':
            assignment = self.env['education.lesson.assignment'].search([
                ('class_schedule_occurrence_id', '=', occurrence.id),
            ], limit=1)
            if assignment and assignment.status != 'completed':
                assignment.status = 'completed'
        return result
