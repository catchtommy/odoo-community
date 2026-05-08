# -*- coding: utf-8 -*-
from datetime import datetime, time, timedelta

from odoo import fields, models
from odoo.exceptions import UserError


class TuitionReportMixin(models.AbstractModel):
    """Shared drill-down helpers for read-only SQL-view report models."""

    _name = 'tuition.report.mixin'
    _description = 'Tuition Report Drill-down Helpers'

    def _date_domain(self):
        self.ensure_one()
        start = datetime.combine(self.report_date, time.min)
        end = start + timedelta(days=1)
        return [('start_datetime', '>=', start), ('start_datetime', '<', end)]

    def _dimension_domain(self):
        return []

    def _occurrence_action(self, name, metric_domain):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': 'class.schedule.occurrence',
            'view_mode': 'list,form,calendar',
            'domain': self._date_domain() + self._dimension_domain() + metric_domain,
            'context': {'create': False},
        }

    def action_open_scheduled_classes(self):
        return self._occurrence_action('Scheduled Classes', [('is_demo', '=', False)])

    def action_open_demos(self):
        return self._occurrence_action('Demo Classes', [('is_demo', '=', True)])

    def action_open_completed_classes(self):
        return self._occurrence_action(
            'Completed Classes',
            [('is_demo', '=', False), ('lesson_status', '=', 'completed')],
        )

    def action_open_cancelled_classes(self):
        return self._occurrence_action(
            'Cancelled Classes',
            [('is_demo', '=', False), ('lesson_status', '=', 'cancelled')],
        )

    def action_open_rescheduled_classes(self):
        return self._occurrence_action(
            'Rescheduled Classes',
            [('is_demo', '=', False), '|', ('is_rescheduled', '=', True), ('lesson_status', '=', 'rescheduled')],
        )

    def action_open_effective_classes(self):
        return self._occurrence_action(
            'Effective Classes',
            [
                '|',
                '&', ('is_demo', '=', False), ('lesson_status', '=', 'completed'),
                '&', ('is_demo', '=', True), ('lesson_status', '!=', 'cancelled'),
            ],
        )

    def action_open_total_sessions(self):
        return self._occurrence_action('Total Sessions', [])

    def action_open_happened_classes(self):
        return self.action_open_completed_classes()

    def action_open_billable_classes(self):
        return self.action_open_completed_classes()

    def init(self):
        self.env.cr.execute(
            """
            CREATE INDEX IF NOT EXISTS tuition_report_occurrence_start_idx
                ON class_schedule_occurrence (start_datetime);
            CREATE INDEX IF NOT EXISTS tuition_report_occurrence_course_idx
                ON class_schedule_occurrence (course_id);
            CREATE INDEX IF NOT EXISTS tuition_report_occurrence_tutor_idx
                ON class_schedule_occurrence (tutor_id);
            CREATE INDEX IF NOT EXISTS tuition_report_occurrence_metrics_idx
                ON class_schedule_occurrence (lesson_status, is_demo, is_rescheduled);
            """
        )


class TuitionDateRangeWizardMixin(models.AbstractModel):
    """Shared date-range helpers and drill-down for all report wizards."""

    _name = 'tuition.date.range.wizard.mixin'
    _description = 'Tuition Date Range Report Helpers'

    from_date = fields.Date(string='From Date')
    to_date = fields.Date(string='To Date', default=fields.Date.context_today)

    def _check_date_range(self):
        for rec in self:
            if rec.from_date and rec.to_date and rec.from_date > rec.to_date:
                raise UserError('From Date must be on or before To Date.')

    def _date_range_domain(self):
        self.ensure_one()
        self._check_date_range()
        return [
            ('start_datetime', '>=', datetime.combine(self.from_date, time.min)),
            ('start_datetime', '<=', datetime.combine(self.to_date, time.max)),
        ]

    def _subject_dimension_domain(self, category, subject):
        domain = []
        if category:
            domain += [
                '|',
                ('course_id.category_id', '=', category.id),
                '&',
                ('course_id.category_id', '=', False),
                ('course_id.subject_id.category_id', '=', category.id),
            ]
        if subject:
            domain.append(('course_id.subject_id', '=', subject.id))
        return domain

    def _open_occurrences(self, name, domain):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': 'class.schedule.occurrence',
            'view_mode': 'list,form,calendar',
            'domain': self._date_range_domain() + domain,
            'context': {'create': False},
        }

    def action_close_report(self):
        """Navigate back to the Tuition dashboard instead of falling back to Discuss."""
        return {
            'type': 'ir.actions.client',
            'tag': 'tuition_dashboard',
        }
