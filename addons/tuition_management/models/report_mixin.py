# -*- coding: utf-8 -*-
from datetime import datetime, time, timedelta

import pytz

from odoo import fields, models
from odoo.exceptions import UserError

from .tz_utils import get_tz_selection, DEFAULT_TIMEZONE, tz_abbr


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
            [('lesson_status', '=', 'completed')],
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
    # Dates in the filters and in the result rows are interpreted in this
    # timezone; start_datetime is stored in UTC.
    report_tz = fields.Selection(
        selection=get_tz_selection,
        string='Timezone',
        default=lambda self: self._default_report_tz(),
    )

    def _default_report_tz(self):
        return self.env.user.tz or DEFAULT_TIMEZONE

    @staticmethod
    def _valid_tz_name(tz_name):
        try:
            pytz.timezone(tz_name or 'UTC')
        except pytz.UnknownTimeZoneError:
            return 'UTC'
        return tz_name or 'UTC'

    def _get_report_tz_name(self):
        self.ensure_one()
        return self._valid_tz_name(self.report_tz)

    @classmethod
    def _local_dates_to_utc(cls, from_date, to_date, tz_name):
        """Return naive UTC datetimes [start, end) covering from_date 00:00 to
        the end of to_date, both taken as local dates in tz_name."""
        tz = pytz.timezone(cls._valid_tz_name(tz_name))

        def to_utc(day):
            local = tz.localize(datetime.combine(day, time.min))
            return local.astimezone(pytz.utc).replace(tzinfo=None)

        return to_utc(from_date), to_utc(to_date + timedelta(days=1))

    @classmethod
    def _tz_abbr_on(cls, day, tz_name):
        """Short timezone code in effect on a local date (EST vs EDT etc.)."""
        start, _end = cls._local_dates_to_utc(day, day, tz_name)
        return tz_abbr(cls._valid_tz_name(tz_name), start + timedelta(hours=12))

    def _drilldown_views(self):
        """Lesson list that shows times in the report timezone, with its code."""
        return [
            (self.env.ref('tuition_management.view_report_occurrence_drilldown_list').id, 'list'),
            (False, 'form'),
            (False, 'calendar'),
        ]

    def _compute_display_name(self):
        # These wizards have no meaningful `name` field, so the default
        # implementation falls back to "model,id" (e.g. "tuition.class.status.wizard,5"),
        # which is confusing shown as the breadcrumb title. Use the model's
        # own description instead ("Class Status Report Wizard" -> "Class Status Report").
        for rec in self:
            rec.display_name = rec._description.removesuffix(' Wizard')

    def _check_date_range(self):
        for rec in self:
            if rec.from_date and rec.to_date and rec.from_date > rec.to_date:
                raise UserError('From Date must be on or before To Date.')

    def _date_range_domain(self):
        self.ensure_one()
        self._check_date_range()
        start, end = self._local_dates_to_utc(self.from_date, self.to_date, self.report_tz)
        return [('start_datetime', '>=', start), ('start_datetime', '<', end)]

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
            'views': self._drilldown_views(),
            'domain': self._date_range_domain() + domain,
            'context': {'create': False, 'tz': self._get_report_tz_name()},
        }

    def action_close_report(self):
        """Navigate back to the Tuition dashboard instead of falling back to Discuss."""
        return {
            'type': 'ir.actions.client',
            'tag': 'tuition_dashboard',
        }
