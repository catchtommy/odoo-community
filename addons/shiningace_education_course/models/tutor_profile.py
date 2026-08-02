# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields, models


class TutorProfile(models.Model):
    _inherit = 'tutor.profile'

    def get_today_lesson_assignments(self):
        """Curriculum lesson assignments for this tutor's occurrences happening today.

        A plain search helper (not a stored field) — called directly by the
        portal template, since "today" is UI-relative and there is no need to
        keep a per-tutor stored field for something already cheap to search.
        """
        today_start = fields.Datetime.to_string(fields.Date.context_today(self))
        today_end = fields.Datetime.to_string(fields.Date.context_today(self) + timedelta(days=1))
        return self.env['education.lesson.assignment'].search([
            ('tutor_id', 'in', self.ids),
            ('start_datetime', '>=', today_start),
            ('start_datetime', '<', today_end),
        ])
