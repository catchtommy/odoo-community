# -*- coding: utf-8 -*-
import base64
import io
from datetime import datetime, time, timedelta

import xlsxwriter

from odoo import api, fields, models, tools


class TuitionSubjectWiseReport(models.Model):
    """SQL-view model: one row per (date, category, subject), aggregated counts."""

    _name = 'tuition.subject.wise.report'
    _description = 'Subject-wise Report (SQL View)'
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


class TuitionSubjectWiseWizard(models.TransientModel):
    """Interactive report wizard: date range + category/subject filters."""

    _name = 'tuition.subject.wise.wizard'
    _description = 'Subject-wise Report Wizard'
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
    """One line per (category, subject) combination."""

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
