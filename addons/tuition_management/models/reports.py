# -*- coding: utf-8 -*-
import base64
import calendar
import io
from datetime import datetime, time, timedelta
import xlsxwriter

from odoo import api, fields, models, tools
from odoo.exceptions import UserError


class TuitionReportMixin(models.AbstractModel):
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


class TuitionClassStatusReport(models.Model):
    _name = 'tuition.class.status.report'
    _description = 'Class Status Report'
    _inherit = 'tuition.report.mixin'
    _auto = False
    _order = 'report_date desc'

    report_date = fields.Date(string='Class Date', readonly=True)
    total_scheduled_classes = fields.Integer(string='Scheduled Classes', readonly=True)
    pending_classes = fields.Integer(string='Classes in Pending', readonly=True)
    total_demos = fields.Integer(string='Demos', readonly=True)
    completed_classes = fields.Integer(string='Completed Classes', readonly=True)
    cancelled_classes = fields.Integer(string='Cancelled Classes', readonly=True)
    rescheduled_classes = fields.Integer(string='Rescheduled Classes', readonly=True)
    billable_actual_classes = fields.Integer(string='Billable Actual Classes', readonly=True)

    def init(self):
        super().init()
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW tuition_class_status_report AS (
                SELECT
                    ((occ.start_datetime::date - DATE '1970-01-01')::integer + 1) AS id,
                    occ.start_datetime::date AS report_date,
                    COUNT(*) FILTER (WHERE NOT COALESCE(occ.is_demo, FALSE))::integer AS total_scheduled_classes,
                    COUNT(*) FILTER (
                        WHERE NOT COALESCE(occ.is_demo, FALSE)
                          AND occ.lesson_status IN ('scheduled', 'under_review')
                    )::integer AS pending_classes,
                    COUNT(*) FILTER (WHERE COALESCE(occ.is_demo, FALSE))::integer AS total_demos,
                    COUNT(*) FILTER (
                        WHERE NOT COALESCE(occ.is_demo, FALSE)
                          AND occ.lesson_status = 'completed'
                    )::integer AS completed_classes,
                    COUNT(*) FILTER (
                        WHERE NOT COALESCE(occ.is_demo, FALSE)
                          AND occ.lesson_status = 'cancelled'
                    )::integer AS cancelled_classes,
                    COUNT(*) FILTER (
                        WHERE NOT COALESCE(occ.is_demo, FALSE)
                          AND (COALESCE(occ.is_rescheduled, FALSE) OR occ.lesson_status = 'rescheduled')
                    )::integer AS rescheduled_classes,
                    GREATEST(
                        COUNT(*) FILTER (
                            WHERE NOT COALESCE(occ.is_demo, FALSE)
                              AND occ.lesson_status = 'completed'
                        )
                        - COUNT(*) FILTER (
                            WHERE COALESCE(occ.is_demo, FALSE)
                        ),
                        0
                    )::integer AS billable_actual_classes
                FROM class_schedule_occurrence occ
                WHERE occ.start_datetime IS NOT NULL
                GROUP BY occ.start_datetime::date
            )
            """
        )


class TuitionSubjectWiseReport(models.Model):
    _name = 'tuition.subject.wise.report'
    _description = 'Subject-wise Report'
    _inherit = 'tuition.report.mixin'
    _auto = False
    _order = 'category_id, subject_id, report_date desc'

    report_date = fields.Date(string='Class Date', readonly=True)
    category_id = fields.Many2one('subject.category', string='Category', readonly=True)
    subject_id = fields.Many2one('subject.master', string='Subject', readonly=True)
    total_classes = fields.Integer(string='Classes', readonly=True)
    total_demos = fields.Integer(string='Demos', readonly=True)
    total_sessions = fields.Integer(string='Total', readonly=True)

    def _dimension_domain(self):
        domain = []
        if self.category_id:
            domain += [
                '|',
                ('course_id.category_id', '=', self.category_id.id),
                '&', ('course_id.category_id', '=', False), ('course_id.subject_id.category_id', '=', self.category_id.id),
            ]
        if self.subject_id:
            domain.append(('course_id.subject_id', '=', self.subject_id.id))
        return domain

    def init(self):
        super().init()
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW tuition_subject_wise_report AS (
                WITH base AS (
                    SELECT
                        occ.start_datetime::date AS report_date,
                        COALESCE(course.category_id, subject.category_id) AS category_id,
                        course.subject_id AS subject_id,
                        COALESCE(occ.is_demo, FALSE) AS is_demo
                    FROM class_schedule_occurrence occ
                    JOIN course_master course ON course.id = occ.course_id
                    LEFT JOIN subject_master subject ON subject.id = course.subject_id
                    WHERE occ.start_datetime IS NOT NULL
                )
                SELECT
                    (
                        ('x' || substr(md5(
                            report_date::text || '-' || COALESCE(category_id::text, '0') || '-' || COALESCE(subject_id::text, '0')
                        ), 1, 8))::bit(32)::bigint % 2147483647
                    )::integer + 1 AS id,
                    report_date,
                    category_id,
                    subject_id,
                    COUNT(*) FILTER (WHERE NOT is_demo)::integer AS total_classes,
                    COUNT(*) FILTER (WHERE is_demo)::integer AS total_demos,
                    COUNT(*)::integer AS total_sessions
                FROM base
                GROUP BY report_date, category_id, subject_id
            )
            """
        )


class TuitionTutorWiseReport(models.Model):
    _name = 'tuition.tutor.wise.report'
    _description = 'Tutor-wise Report'
    _inherit = 'tuition.report.mixin'
    _auto = False
    _order = 'tutor_id, category_id, subject_id, report_date desc'

    report_date = fields.Date(string='Class Date', readonly=True)
    tutor_id = fields.Many2one('tutor.profile', string='Tutor', readonly=True)
    category_id = fields.Many2one('subject.category', string='Category', readonly=True)
    subject_id = fields.Many2one('subject.master', string='Subject', readonly=True)
    category_subject = fields.Char(string='Category + Subject', readonly=True)
    total_classes = fields.Integer(string='Classes', readonly=True)
    total_demos = fields.Integer(string='Demos', readonly=True)
    completed_classes = fields.Integer(string='Completed', readonly=True)
    cancelled_classes = fields.Integer(string='Cancelled', readonly=True)
    effective_classes = fields.Integer(string='Effective', readonly=True)

    def _dimension_domain(self):
        domain = []
        if self.tutor_id:
            domain.append(('tutor_id', '=', self.tutor_id.id))
        if self.category_id:
            domain += [
                '|',
                ('course_id.category_id', '=', self.category_id.id),
                '&', ('course_id.category_id', '=', False), ('course_id.subject_id.category_id', '=', self.category_id.id),
            ]
        if self.subject_id:
            domain.append(('course_id.subject_id', '=', self.subject_id.id))
        return domain

    def init(self):
        super().init()
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW tuition_tutor_wise_report AS (
                WITH base AS (
                    SELECT
                        occ.start_datetime::date AS report_date,
                        occ.tutor_id AS tutor_id,
                        COALESCE(course.category_id, subject.category_id) AS category_id,
                        course.subject_id AS subject_id,
                        COALESCE(category.name, 'Uncategorised') || ' - ' || COALESCE(subject.name, 'No Subject') AS category_subject,
                        COALESCE(occ.is_demo, FALSE) AS is_demo,
                        occ.lesson_status
                    FROM class_schedule_occurrence occ
                    JOIN course_master course ON course.id = occ.course_id
                    LEFT JOIN subject_master subject ON subject.id = course.subject_id
                    LEFT JOIN subject_category category ON category.id = COALESCE(course.category_id, subject.category_id)
                    WHERE occ.start_datetime IS NOT NULL
                )
                SELECT
                    (
                        ('x' || substr(md5(
                            report_date::text || '-' || COALESCE(tutor_id::text, '0') || '-'
                            || COALESCE(category_id::text, '0') || '-' || COALESCE(subject_id::text, '0')
                        ), 1, 8))::bit(32)::bigint % 2147483647
                    )::integer + 1 AS id,
                    report_date,
                    tutor_id,
                    category_id,
                    subject_id,
                    category_subject,
                    COUNT(*) FILTER (WHERE NOT is_demo)::integer AS total_classes,
                    COUNT(*) FILTER (WHERE is_demo)::integer AS total_demos,
                    COUNT(*) FILTER (WHERE NOT is_demo AND lesson_status = 'completed')::integer AS completed_classes,
                    COUNT(*) FILTER (WHERE NOT is_demo AND lesson_status = 'cancelled')::integer AS cancelled_classes,
                    (
                        COUNT(*) FILTER (WHERE NOT is_demo AND lesson_status = 'completed')
                        + COUNT(*) FILTER (WHERE is_demo)
                        - COUNT(*) FILTER (WHERE NOT is_demo AND lesson_status = 'cancelled')
                    )::integer AS effective_classes
                FROM base
                GROUP BY report_date, tutor_id, category_id, subject_id, category_subject
            )
            """
        )


class TuitionDateRangeWizardMixin(models.AbstractModel):
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


class TuitionClassStatusWizard(models.TransientModel):
    _name = 'tuition.class.status.wizard'
    _description = 'Class Status Report'
    _inherit = 'tuition.date.range.wizard.mixin'

    from_date = fields.Date(
        string='From Date',
        default=lambda self: (fields.Date.context_today(self).replace(day=1) - timedelta(days=1)).replace(day=1),
    )
    to_date = fields.Date(
        string='To Date',
        default=lambda self: fields.Date.context_today(self).replace(day=1) - timedelta(days=1),
    )
    group_by = fields.Selection(
        [('day', 'Day'), ('week', 'Week'), ('month', 'Month')],
        string='Group By',
        default='day',
    )
    line_ids = fields.One2many('tuition.class.status.wizard.line', 'wizard_id', string='Lines')

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        today = fields.Date.context_today(self)
        from_date = fields.Date.to_date(vals.get('from_date')) or (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        to_date = fields.Date.to_date(vals.get('to_date')) or today.replace(day=1) - timedelta(days=1)
        if 'line_ids' in fields_list:
            vals['line_ids'] = [(0, 0, line) for line in self._get_line_values(from_date, to_date, vals.get('group_by', 'day'))]
        return vals

    def _get_line_values(self, from_date, to_date, group_by='day'):
        if from_date > to_date:
            return []
        if group_by == 'week':
            group_expr = "date_trunc('week', occ.start_datetime)::date"
        elif group_by == 'month':
            group_expr = "date_trunc('month', occ.start_datetime)::date"
        else:
            group_expr = "occ.start_datetime::date"
        self.env.cr.execute(
            f"""
            SELECT
                {group_expr} AS report_date,
                COUNT(*) FILTER (WHERE NOT COALESCE(occ.is_demo, FALSE))::integer AS total_scheduled_classes,
                COUNT(*) FILTER (
                    WHERE NOT COALESCE(occ.is_demo, FALSE)
                      AND occ.lesson_status = 'scheduled'
                )::integer AS pending_classes,
                COUNT(*) FILTER (
                    WHERE NOT COALESCE(occ.is_demo, FALSE)
                      AND occ.lesson_status = 'under_review'
                )::integer AS under_review_classes,
                COUNT(*) FILTER (WHERE COALESCE(occ.is_demo, FALSE))::integer AS total_demos,
                COUNT(*) FILTER (
                    WHERE NOT COALESCE(occ.is_demo, FALSE)
                      AND occ.lesson_status = 'completed'
                      AND NOT COALESCE(occ.attendance_marked, FALSE)
                )::integer AS attendance_pending_classes,
                COUNT(*) FILTER (
                    WHERE NOT COALESCE(occ.is_demo, FALSE)
                      AND occ.lesson_status = 'completed'
                )::integer AS completed_classes,
                COUNT(*) FILTER (
                    WHERE NOT COALESCE(occ.is_demo, FALSE)
                      AND occ.lesson_status = 'cancelled'
                )::integer AS cancelled_classes,
                COUNT(*) FILTER (
                    WHERE NOT COALESCE(occ.is_demo, FALSE)
                      AND (COALESCE(occ.is_rescheduled, FALSE) OR occ.lesson_status = 'rescheduled')
                )::integer AS rescheduled_classes,
                GREATEST(
                    COUNT(*) FILTER (
                        WHERE NOT COALESCE(occ.is_demo, FALSE)
                          AND occ.lesson_status = 'completed'
                    ) - COUNT(*) FILTER (WHERE COALESCE(occ.is_demo, FALSE)),
                    0
                )::integer AS billable_actual_classes
            FROM class_schedule_occurrence occ
            WHERE occ.start_datetime >= %s
              AND occ.start_datetime <= %s
            GROUP BY {group_expr}
            ORDER BY {group_expr}
            """,
            (
                datetime.combine(from_date, time.min),
                datetime.combine(to_date, time.max),
            ),
        )
        return [
            {
                'report_date': row[0],
                'total_scheduled_classes': row[1],
                'pending_classes': row[2],
                'under_review_classes': row[3],
                'total_demos': row[4],
                'attendance_pending_classes': row[5],
                'completed_classes': row[6],
                'cancelled_classes': row[7],
                'rescheduled_classes': row[8],
                'billable_actual_classes': row[9],
            }
            for row in self.env.cr.fetchall()
        ]

    def _refresh_lines(self):
        for rec in self:
            rec._check_date_range()
            rec.line_ids.unlink()
            for line in self._get_line_values(rec.from_date, rec.to_date, rec.group_by or 'day'):
                line['wizard_id'] = rec.id
                self.env['tuition.class.status.wizard.line'].create(line)

    def action_refresh(self):
        self.ensure_one()
        self._refresh_lines()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Class Status Report',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }

    def action_clear_filters(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        self.write({
            'from_date': (today.replace(day=1) - timedelta(days=1)).replace(day=1),
            'to_date': today.replace(day=1) - timedelta(days=1),
            'group_by': 'day',
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Class Status Report',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }

    def action_export_excel(self):
        self.ensure_one()
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Class Status Report')

        # Formats
        title_fmt = workbook.add_format({'bold': True, 'font_size': 13})
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#2E86AB', 'font_color': '#FFFFFF', 'border': 1, 'align': 'center'})
        date_fmt = workbook.add_format({'num_format': 'dd/mm/yyyy', 'border': 1})
        num_fmt = workbook.add_format({'num_format': '#,##0', 'border': 1, 'align': 'center'})
        total_fmt = workbook.add_format({'bold': True, 'num_format': '#,##0', 'bg_color': '#F0F0F0', 'border': 1, 'align': 'center'})
        total_lbl_fmt = workbook.add_format({'bold': True, 'bg_color': '#F0F0F0', 'border': 1})

        sheet.write(0, 0, 'Class Status Report', title_fmt)
        sheet.write(1, 0, f"Period: {self.from_date} to {self.to_date}")

        headers = ['Date', 'Scheduled', 'Pending', 'Under Review', 'Demos', 'Attendance Pending', 'Completed', 'Cancelled', 'Rescheduled', 'Billable']
        col_widths = [14, 12, 12, 14, 10, 18, 12, 12, 14, 10]
        for col, (h, w) in enumerate(zip(headers, col_widths)):
            sheet.write(3, col, h, header_fmt)
            sheet.set_column(col, col, w)

        totals = [0] * 9
        for row_idx, line in enumerate(self.line_ids, start=4):
            sheet.write(row_idx, 0, line.report_date, date_fmt)
            nums = [
                line.total_scheduled_classes, line.pending_classes, line.under_review_classes,
                line.total_demos, line.attendance_pending_classes,
                line.completed_classes, line.cancelled_classes, line.rescheduled_classes,
                line.billable_actual_classes,
            ]
            for col, val in enumerate(nums, start=1):
                sheet.write(row_idx, col, val, num_fmt)
                totals[col - 1] += val

        total_row = 4 + len(self.line_ids)
        sheet.write(total_row, 0, 'Total', total_lbl_fmt)
        for col, val in enumerate(totals, start=1):
            sheet.write(total_row, col, val, total_fmt)

        workbook.close()
        xlsx_data = output.getvalue()
        attachment = self.env['ir.attachment'].create({
            'name': f'Class_Status_Report_{self.from_date}_{self.to_date}.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(xlsx_data),
            'res_model': self._name,
            'res_id': self.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }


class TuitionClassStatusWizardLine(models.TransientModel):
    _name = 'tuition.class.status.wizard.line'
    _description = 'Class Status Report Line'
    _order = 'report_date'

    wizard_id = fields.Many2one('tuition.class.status.wizard', required=True, ondelete='cascade')
    report_date = fields.Date(string='Date', readonly=True)
    total_scheduled_classes = fields.Integer(string='Scheduled', readonly=True)
    pending_classes = fields.Integer(string='Pending', readonly=True)
    under_review_classes = fields.Integer(string='Under Review', readonly=True)
    total_demos = fields.Integer(string='Demos', readonly=True)
    attendance_pending_classes = fields.Integer(string='Attendance Pending', readonly=True)
    completed_classes = fields.Integer(string='Completed', readonly=True)
    cancelled_classes = fields.Integer(string='Cancelled', readonly=True)
    rescheduled_classes = fields.Integer(string='Rescheduled', readonly=True)
    billable_actual_classes = fields.Integer(string='Billable', readonly=True)

    def _get_date_range(self):
        group_by = self.wizard_id.group_by or 'day'
        report_date = self.report_date
        if group_by == 'week':
            from_dt = datetime.combine(report_date, time.min)
            to_dt = datetime.combine(report_date + timedelta(days=6), time.max)
        elif group_by == 'month':
            last_day = calendar.monthrange(report_date.year, report_date.month)[1]
            from_dt = datetime.combine(report_date, time.min)
            to_dt = datetime.combine(report_date.replace(day=last_day), time.max)
        else:
            from_dt = datetime.combine(report_date, time.min)
            to_dt = datetime.combine(report_date, time.max)
        return from_dt, to_dt

    def _occurrence_action(self, label, extra_domain):
        self.ensure_one()
        from_dt, to_dt = self._get_date_range()
        domain = [
            ('start_datetime', '>=', from_dt),
            ('start_datetime', '<=', to_dt),
        ] + extra_domain
        return {
            'type': 'ir.actions.act_window',
            'name': label,
            'res_model': 'class.schedule.occurrence',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {'create': False},
            'target': 'current',
        }

    def action_view_scheduled(self):
        return self._occurrence_action('Scheduled Classes', [('is_demo', '=', False)])

    def action_view_pending(self):
        return self._occurrence_action('Pending Classes', [('is_demo', '=', False), ('lesson_status', '=', 'scheduled')])

    def action_view_under_review(self):
        return self._occurrence_action('Under Review Classes', [('is_demo', '=', False), ('lesson_status', '=', 'under_review')])

    def action_view_demos(self):
        return self._occurrence_action('Demo Classes', [('is_demo', '=', True)])

    def action_view_attendance_pending(self):
        return self._occurrence_action('Attendance Pending', [('is_demo', '=', False), ('lesson_status', '=', 'completed'), ('attendance_marked', '=', False)])

    def action_view_completed(self):
        return self._occurrence_action('Completed Classes', [('is_demo', '=', False), ('lesson_status', '=', 'completed')])

    def action_view_cancelled(self):
        return self._occurrence_action('Cancelled Classes', [('is_demo', '=', False), ('lesson_status', '=', 'cancelled')])

    def action_view_rescheduled(self):
        return self._occurrence_action('Rescheduled Classes', [('is_demo', '=', False), '|', ('is_rescheduled', '=', True), ('lesson_status', '=', 'rescheduled')])

    def action_view_billable(self):
        return self._occurrence_action('Billable Classes', [('is_demo', '=', False), ('lesson_status', '=', 'completed')])


class TuitionSubjectWiseWizard(models.TransientModel):
    _name = 'tuition.subject.wise.wizard'
    _description = 'Subject-wise Report'
    _inherit = 'tuition.date.range.wizard.mixin'

    from_date = fields.Date(
        string='From Date',
        default=lambda self: fields.Date.context_today(self) - timedelta(days=30),
    )
    filter_category_id = fields.Many2one('subject.category', string='Category')
    filter_subject_id = fields.Many2one('subject.master', string='Subject')
    line_ids = fields.One2many('tuition.subject.wise.wizard.line', 'wizard_id', string='Lines')

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        from_date = fields.Date.to_date(vals.get('from_date')) or fields.Date.context_today(self) - timedelta(days=30)
        to_date = fields.Date.to_date(vals.get('to_date')) or fields.Date.context_today(self)
        if 'line_ids' in fields_list:
            vals['line_ids'] = [(0, 0, line) for line in self._get_line_values(from_date, to_date)]
        return vals

    def _get_line_values(self, from_date, to_date, filter_category_id=None, filter_subject_id=None):
        if from_date > to_date:
            return []
        extra_where = []
        params = [
            datetime.combine(from_date, time.min),
            datetime.combine(to_date, time.max),
        ]
        if filter_category_id:
            extra_where.append("AND COALESCE(course.category_id, subject.category_id) = %s")
            params.append(filter_category_id)
        if filter_subject_id:
            extra_where.append("AND course.subject_id = %s")
            params.append(filter_subject_id)
        extra_sql = '\n            '.join(extra_where)
        self.env.cr.execute(
            f"""
            SELECT
                COALESCE(course.category_id, subject.category_id) AS category_id,
                course.subject_id AS subject_id,
                COUNT(*) FILTER (WHERE NOT COALESCE(occ.is_demo, FALSE))::integer AS total_classes,
                COUNT(*) FILTER (WHERE COALESCE(occ.is_demo, FALSE))::integer AS total_demos,
                COUNT(*)::integer AS total_sessions
            FROM class_schedule_occurrence occ
            JOIN course_master course ON course.id = occ.course_id
            LEFT JOIN subject_master subject ON subject.id = course.subject_id
            WHERE occ.start_datetime >= %s
              AND occ.start_datetime <= %s
              {extra_sql}
            GROUP BY COALESCE(course.category_id, subject.category_id), course.subject_id
            ORDER BY COALESCE(course.category_id, subject.category_id), course.subject_id
            """,
            params,
        )
        return [
            {
                'category_id': category_id,
                'subject_id': subject_id,
                'total_classes': total_classes,
                'total_demos': total_demos,
                'total_sessions': total_sessions,
            }
            for category_id, subject_id, total_classes, total_demos, total_sessions in self.env.cr.fetchall()
        ]

    def _refresh_lines(self):
        for rec in self:
            rec._check_date_range()
            rec.line_ids.unlink()
            for line in self._get_line_values(
                rec.from_date, rec.to_date,
                filter_category_id=rec.filter_category_id.id or None,
                filter_subject_id=rec.filter_subject_id.id or None,
            ):
                line['wizard_id'] = rec.id
                self.env['tuition.subject.wise.wizard.line'].create(line)

    def action_refresh(self):
        self.ensure_one()
        self._refresh_lines()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Subject-wise Report',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }

    def action_clear_filters(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        self.write({
            'from_date': today - timedelta(days=30),
            'to_date': today,
            'filter_category_id': False,
            'filter_subject_id': False,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Subject-wise Report',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }

    def action_export_excel(self):
        self.ensure_one()
        import xlsxwriter
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Subject-wise Report')

        title_fmt = workbook.add_format({'bold': True, 'font_size': 13})
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#2E86AB', 'font_color': '#FFFFFF', 'border': 1, 'align': 'center'})
        cell_fmt = workbook.add_format({'border': 1})
        num_fmt = workbook.add_format({'num_format': '#,##0', 'border': 1, 'align': 'center'})
        total_fmt = workbook.add_format({'bold': True, 'num_format': '#,##0', 'bg_color': '#F0F0F0', 'border': 1, 'align': 'center'})
        total_lbl_fmt = workbook.add_format({'bold': True, 'bg_color': '#F0F0F0', 'border': 1})

        sheet.write(0, 0, 'Subject-wise Report', title_fmt)
        sheet.write(1, 0, f"Period: {self.from_date} to {self.to_date}")

        headers = ['Category', 'Subject', 'Classes', 'Demos', 'Total']
        col_widths = [20, 25, 12, 10, 10]
        for col, (h, w) in enumerate(zip(headers, col_widths)):
            sheet.write(3, col, h, header_fmt)
            sheet.set_column(col, col, w)

        totals = [0, 0, 0]
        for row_idx, line in enumerate(self.line_ids, start=4):
            sheet.write(row_idx, 0, line.category_id.name or '', cell_fmt)
            sheet.write(row_idx, 1, line.subject_id.name or '', cell_fmt)
            sheet.write(row_idx, 2, line.total_classes, num_fmt)
            sheet.write(row_idx, 3, line.total_demos, num_fmt)
            sheet.write(row_idx, 4, line.total_sessions, num_fmt)
            totals[0] += line.total_classes
            totals[1] += line.total_demos
            totals[2] += line.total_sessions

        total_row = 4 + len(self.line_ids)
        sheet.write(total_row, 0, 'Total', total_lbl_fmt)
        sheet.write(total_row, 1, '', total_lbl_fmt)
        for col, val in enumerate(totals, start=2):
            sheet.write(total_row, col, val, total_fmt)

        workbook.close()
        xlsx_data = output.getvalue()
        attachment = self.env['ir.attachment'].create({
            'name': f'Subject_wise_Report_{self.from_date}_{self.to_date}.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(xlsx_data),
            'res_model': self._name,
            'res_id': self.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }


class TuitionSubjectWiseWizardLine(models.TransientModel):
    _name = 'tuition.subject.wise.wizard.line'
    _description = 'Subject-wise Report Line'
    _order = 'category_id, subject_id'

    wizard_id = fields.Many2one('tuition.subject.wise.wizard', required=True, ondelete='cascade')
    category_id = fields.Many2one('subject.category', string='Category', readonly=True)
    subject_id = fields.Many2one('subject.master', string='Subject', readonly=True)
    total_classes = fields.Integer(string='Classes', readonly=True)
    total_demos = fields.Integer(string='Demos', readonly=True)
    total_sessions = fields.Integer(string='Total', readonly=True)

    def _dimension_domain(self):
        self.ensure_one()
        return self.wizard_id._subject_dimension_domain(self.category_id, self.subject_id)

    def action_open_classes(self):
        return self.wizard_id._open_occurrences(
            'Subject Classes',
            self._dimension_domain() + [('is_demo', '=', False)],
        )

    def action_open_demos(self):
        return self.wizard_id._open_occurrences(
            'Subject Demos',
            self._dimension_domain() + [('is_demo', '=', True)],
        )

    def action_open_total(self):
        return self.wizard_id._open_occurrences('Subject Total Sessions', self._dimension_domain())


class TuitionTutorWiseWizard(models.TransientModel):
    _name = 'tuition.tutor.wise.wizard'
    _description = 'Tutor-wise Report'
    _inherit = 'tuition.date.range.wizard.mixin'

    from_date = fields.Date(
        string='From Date',
        default=lambda self: fields.Date.context_today(self) - timedelta(days=7),
    )
    filter_tutor_id = fields.Many2one('tutor.profile', string='Tutor')
    filter_category_id = fields.Many2one('subject.category', string='Category')
    filter_subject_id = fields.Many2one('subject.master', string='Subject')
    group_by = fields.Selection(
        [('tutor_subject', 'Tutor + Subject'), ('tutor', 'Tutor Only')],
        string='Group By',
        default='tutor_subject',
    )
    line_ids = fields.One2many('tuition.tutor.wise.wizard.line', 'wizard_id', string='Lines')

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        from_date = fields.Date.to_date(vals.get('from_date')) or fields.Date.context_today(self) - timedelta(days=7)
        to_date = fields.Date.to_date(vals.get('to_date')) or fields.Date.context_today(self)
        if 'line_ids' in fields_list:
            vals['line_ids'] = [(0, 0, line) for line in self._get_line_values(from_date, to_date)]
        return vals

    def _get_line_values(self, from_date, to_date, filter_tutor_id=None, filter_category_id=None, filter_subject_id=None, group_by='tutor_subject'):
        if from_date > to_date:
            return []
        extra_where = []
        params = [
            datetime.combine(from_date, time.min),
            datetime.combine(to_date, time.max),
        ]
        if filter_tutor_id:
            extra_where.append("AND occ.tutor_id = %s")
            params.append(filter_tutor_id)
        if filter_category_id:
            extra_where.append("AND COALESCE(course.category_id, subject.category_id) = %s")
            params.append(filter_category_id)
        if filter_subject_id:
            extra_where.append("AND course.subject_id = %s")
            params.append(filter_subject_id)
        extra_sql = '\n              '.join(extra_where)

        if group_by == 'tutor':
            select_extra = ""
            group_clause = "occ.tutor_id"
            order_clause = "occ.tutor_id"
            cat_subject_expr = "NULL"
            cat_id_expr = "NULL::integer"
            subj_id_expr = "NULL::integer"
        else:
            select_extra = ""
            group_clause = "occ.tutor_id, COALESCE(course.category_id, subject.category_id), course.subject_id, COALESCE(category.name, 'Uncategorised') || ' - ' || COALESCE(subject.name, 'No Subject')"
            order_clause = "occ.tutor_id, category_subject"
            cat_id_expr = "COALESCE(course.category_id, subject.category_id)"
            subj_id_expr = "course.subject_id"
            cat_subject_expr = "COALESCE(category.name, 'Uncategorised') || ' - ' || COALESCE(subject.name, 'No Subject')"

        self.env.cr.execute(
            f"""
            SELECT
                occ.tutor_id,
                {cat_id_expr} AS category_id,
                {subj_id_expr} AS subject_id,
                {cat_subject_expr} AS category_subject,
                COUNT(*) FILTER (WHERE NOT COALESCE(occ.is_demo, FALSE))::integer AS total_classes,
                COUNT(*) FILTER (WHERE COALESCE(occ.is_demo, FALSE))::integer AS total_demos,
                COUNT(*) FILTER (
                    WHERE NOT COALESCE(occ.is_demo, FALSE)
                      AND occ.lesson_status = 'completed'
                )::integer AS completed_classes,
                COUNT(*) FILTER (
                    WHERE NOT COALESCE(occ.is_demo, FALSE)
                      AND occ.lesson_status = 'cancelled'
                )::integer AS cancelled_classes,
                (
                    COUNT(*) FILTER (
                        WHERE NOT COALESCE(occ.is_demo, FALSE)
                          AND occ.lesson_status = 'completed'
                    )
                    + COUNT(*) FILTER (WHERE COALESCE(occ.is_demo, FALSE))
                    - COUNT(*) FILTER (
                        WHERE NOT COALESCE(occ.is_demo, FALSE)
                          AND occ.lesson_status = 'cancelled'
                    )
                )::integer AS effective_classes
            FROM class_schedule_occurrence occ
            JOIN course_master course ON course.id = occ.course_id
            LEFT JOIN subject_master subject ON subject.id = course.subject_id
            LEFT JOIN subject_category category ON category.id = COALESCE(course.category_id, subject.category_id)
            WHERE occ.start_datetime >= %s
              AND occ.start_datetime <= %s
              {extra_sql}
            GROUP BY {group_clause}
            ORDER BY {order_clause}
            """,
            params,
        )
        return [
            {
                'tutor_id': tutor_id,
                'category_id': category_id,
                'subject_id': subject_id,
                'category_subject': category_subject,
                'total_classes': total_classes,
                'total_demos': total_demos,
                'completed_classes': completed_classes,
                'cancelled_classes': cancelled_classes,
                'effective_classes': effective_classes,
            }
            for (
                tutor_id,
                category_id,
                subject_id,
                category_subject,
                total_classes,
                total_demos,
                completed_classes,
                cancelled_classes,
                effective_classes,
            ) in self.env.cr.fetchall()
        ]

    def _refresh_lines(self):
        for rec in self:
            rec._check_date_range()
            rec.line_ids.unlink()
            for line in self._get_line_values(
                rec.from_date, rec.to_date,
                filter_tutor_id=rec.filter_tutor_id.id or None,
                filter_category_id=rec.filter_category_id.id or None,
                filter_subject_id=rec.filter_subject_id.id or None,
                group_by=rec.group_by or 'tutor_subject',
            ):
                line['wizard_id'] = rec.id
                self.env['tuition.tutor.wise.wizard.line'].create(line)

    def action_refresh(self):
        self.ensure_one()
        self._refresh_lines()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Tutor-wise Report',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }

    def action_clear_filters(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        self.write({
            'from_date': today - timedelta(days=7),
            'to_date': today,
            'filter_tutor_id': False,
            'filter_category_id': False,
            'filter_subject_id': False,
            'group_by': 'tutor_subject',
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Tutor-wise Report',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }

    def action_export_excel(self):
        self.ensure_one()
        import xlsxwriter
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Tutor-wise Report')

        title_fmt = workbook.add_format({'bold': True, 'font_size': 13})
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#2E86AB', 'font_color': '#FFFFFF', 'border': 1, 'align': 'center'})
        cell_fmt = workbook.add_format({'border': 1})
        num_fmt = workbook.add_format({'num_format': '#,##0', 'border': 1, 'align': 'center'})
        total_fmt = workbook.add_format({'bold': True, 'num_format': '#,##0', 'bg_color': '#F0F0F0', 'border': 1, 'align': 'center'})
        total_lbl_fmt = workbook.add_format({'bold': True, 'bg_color': '#F0F0F0', 'border': 1})

        sheet.write(0, 0, 'Tutor-wise Report', title_fmt)
        sheet.write(1, 0, f"Period: {self.from_date} to {self.to_date}")

        headers = ['Tutor', 'Category + Subject', 'Classes', 'Demos', 'Completed', 'Cancelled', 'Effective']
        col_widths = [25, 30, 10, 10, 12, 12, 12]
        for col, (h, w) in enumerate(zip(headers, col_widths)):
            sheet.write(3, col, h, header_fmt)
            sheet.set_column(col, col, w)

        totals = [0, 0, 0, 0, 0]
        for row_idx, line in enumerate(self.line_ids, start=4):
            sheet.write(row_idx, 0, line.tutor_id.name or '', cell_fmt)
            sheet.write(row_idx, 1, line.category_subject or '', cell_fmt)
            sheet.write(row_idx, 2, line.total_classes, num_fmt)
            sheet.write(row_idx, 3, line.total_demos, num_fmt)
            sheet.write(row_idx, 4, line.completed_classes, num_fmt)
            sheet.write(row_idx, 5, line.cancelled_classes, num_fmt)
            sheet.write(row_idx, 6, line.effective_classes, num_fmt)
            totals[0] += line.total_classes
            totals[1] += line.total_demos
            totals[2] += line.completed_classes
            totals[3] += line.cancelled_classes
            totals[4] += line.effective_classes

        total_row = 4 + len(self.line_ids)
        sheet.write(total_row, 0, 'Total', total_lbl_fmt)
        sheet.write(total_row, 1, '', total_lbl_fmt)
        for col, val in enumerate(totals, start=2):
            sheet.write(total_row, col, val, total_fmt)

        workbook.close()
        xlsx_data = output.getvalue()
        attachment = self.env['ir.attachment'].create({
            'name': f'Tutor_wise_Report_{self.from_date}_{self.to_date}.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(xlsx_data),
            'res_model': self._name,
            'res_id': self.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }


class TuitionTutorWiseWizardLine(models.TransientModel):
    _name = 'tuition.tutor.wise.wizard.line'
    _description = 'Tutor-wise Report Line'
    _order = 'tutor_id, category_subject'

    wizard_id = fields.Many2one('tuition.tutor.wise.wizard', required=True, ondelete='cascade')
    tutor_id = fields.Many2one('tutor.profile', string='Tutor', readonly=True)
    category_id = fields.Many2one('subject.category', string='Category', readonly=True)
    subject_id = fields.Many2one('subject.master', string='Subject', readonly=True)
    category_subject = fields.Char(string='Category + Subject', readonly=True)
    total_classes = fields.Integer(string='Classes', readonly=True)
    total_demos = fields.Integer(string='Demos', readonly=True)
    completed_classes = fields.Integer(string='Completed', readonly=True)
    cancelled_classes = fields.Integer(string='Cancelled', readonly=True)
    effective_classes = fields.Integer(string='Effective', readonly=True)

    def _dimension_domain(self):
        self.ensure_one()
        domain = self.wizard_id._subject_dimension_domain(self.category_id, self.subject_id)
        if self.tutor_id:
            domain.append(('tutor_id', '=', self.tutor_id.id))
        return domain

    def action_open_classes(self):
        return self.wizard_id._open_occurrences(
            'Tutor Classes',
            self._dimension_domain() + [('is_demo', '=', False)],
        )

    def action_open_demos(self):
        return self.wizard_id._open_occurrences(
            'Tutor Demos',
            self._dimension_domain() + [('is_demo', '=', True)],
        )

    def action_open_completed(self):
        return self.wizard_id._open_occurrences(
            'Tutor Completed Classes',
            self._dimension_domain() + [('is_demo', '=', False), ('lesson_status', '=', 'completed')],
        )

    def action_open_cancelled(self):
        return self.wizard_id._open_occurrences(
            'Tutor Cancelled Classes',
            self._dimension_domain() + [('is_demo', '=', False), ('lesson_status', '=', 'cancelled')],
        )

    def action_open_effective(self):
        return self.wizard_id._open_occurrences(
            'Tutor Effective Classes',
            self._dimension_domain() + [
                '|',
                '&', ('is_demo', '=', False), ('lesson_status', '=', 'completed'),
                '&', ('is_demo', '=', True), ('lesson_status', '!=', 'cancelled'),
            ],
        )
