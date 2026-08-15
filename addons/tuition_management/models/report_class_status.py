# -*- coding: utf-8 -*-
import base64
import calendar
import io
from datetime import datetime, time, timedelta

import xlsxwriter

from odoo import api, fields, models, tools


class TuitionClassStatusReport(models.Model):
    """SQL-view model: one row per class date, aggregated counts."""

    _name = 'tuition.class.status.report'
    _description = 'Class Status Report (SQL View)'
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
                        WHERE occ.lesson_status = 'completed'
                    )::integer AS completed_classes,
                    COUNT(*) FILTER (
                        WHERE NOT COALESCE(occ.is_demo, FALSE)
                          AND occ.lesson_status = 'cancelled'
                    )::integer AS cancelled_classes,
                    COUNT(*) FILTER (
                        WHERE NOT COALESCE(occ.is_demo, FALSE)
                          AND (COALESCE(occ.is_rescheduled, FALSE) OR occ.lesson_status = 'rescheduled')
                    )::integer AS rescheduled_classes,
                    COUNT(*) FILTER (
                        WHERE NOT COALESCE(occ.is_demo, FALSE)
                          AND occ.lesson_status = 'completed'
                    )::integer AS billable_actual_classes
                FROM class_schedule_occurrence occ
                WHERE occ.start_datetime IS NOT NULL
                GROUP BY occ.start_datetime::date
            )
            """
        )


class TuitionClassStatusWizard(models.TransientModel):
    """Interactive report wizard: date range + group-by, with per-row drill-down."""

    _name = 'tuition.class.status.wizard'
    _description = 'Class Status Report Wizard'
    _inherit = 'tuition.date.range.wizard.mixin'

    from_date = fields.Date(
        string='From Date',
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    to_date = fields.Date(
        string='To Date',
        default=lambda self: fields.Date.context_today(self).replace(
            day=calendar.monthrange(
                fields.Date.context_today(self).year,
                fields.Date.context_today(self).month,
            )[1]
        ),
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
        from_date = fields.Date.to_date(vals.get('from_date')) or today.replace(day=1)
        to_date = fields.Date.to_date(vals.get('to_date')) or today.replace(day=calendar.monthrange(today.year, today.month)[1])
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
                    WHERE occ.lesson_status IN ('scheduled', 'under_review')
                )::integer AS pending_classes,
                COUNT(*) FILTER (
                    WHERE occ.lesson_status = 'under_review'
                )::integer AS under_review_classes,
                COUNT(*) FILTER (WHERE COALESCE(occ.is_demo, FALSE))::integer AS total_demos,
                COUNT(*) FILTER (
                    WHERE occ.lesson_status = 'completed'
                      AND NOT COALESCE(occ.attendance_marked, FALSE)
                )::integer AS attendance_pending_classes,
                COUNT(*) FILTER (
                    WHERE occ.lesson_status = 'completed'
                )::integer AS completed_classes,
                COUNT(*) FILTER (
                    WHERE NOT COALESCE(occ.is_demo, FALSE)
                      AND occ.lesson_status = 'cancelled'
                )::integer AS cancelled_classes,
                COUNT(*) FILTER (
                    WHERE NOT COALESCE(occ.is_demo, FALSE)
                      AND (COALESCE(occ.is_rescheduled, FALSE) OR occ.lesson_status = 'rescheduled')
                )::integer AS rescheduled_classes,
                COUNT(*) FILTER (
                    WHERE NOT COALESCE(occ.is_demo, FALSE)
                      AND occ.lesson_status = 'completed'
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
        # Refresh in place — must NOT return a new act_window action, or the
        # client pushes a second, duplicate breadcrumb/header for the same record.
        self.ensure_one()
        self._refresh_lines()

    def action_clear_filters(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        self.write({
            'from_date': today.replace(day=1),
            'to_date': today.replace(day=calendar.monthrange(today.year, today.month)[1]),
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
    """One line per grouped date period; each column has its own drill-down action."""

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
        return self._occurrence_action(
            'Pending Classes',
            [('lesson_status', 'in', ['scheduled', 'under_review'])],
        )

    def action_view_under_review(self):
        return self._occurrence_action('Under Review Classes', [('lesson_status', '=', 'under_review')])

    def action_view_demos(self):
        return self._occurrence_action('Demo Classes', [('is_demo', '=', True)])

    def action_view_attendance_pending(self):
        return self._occurrence_action(
            'Attendance Pending',
            [('lesson_status', '=', 'completed'), ('attendance_marked', '=', False)],
        )

    def action_view_completed(self):
        return self._occurrence_action('Completed Classes', [('lesson_status', '=', 'completed')])

    def action_view_cancelled(self):
        return self._occurrence_action('Cancelled Classes', [('is_demo', '=', False), ('lesson_status', '=', 'cancelled')])

    def action_view_rescheduled(self):
        return self._occurrence_action(
            'Rescheduled Classes',
            [('is_demo', '=', False), '|', ('is_rescheduled', '=', True), ('lesson_status', '=', 'rescheduled')],
        )

    def action_view_billable(self):
        return self._occurrence_action('Billable Classes', [('is_demo', '=', False), ('lesson_status', '=', 'completed')])
