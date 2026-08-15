# -*- coding: utf-8 -*-
import base64
import calendar
import io
from datetime import datetime, time, timedelta

import xlsxwriter

from odoo import api, fields, models, tools


class TuitionTutorWiseReport(models.Model):
    """SQL-view model: one row per (date, tutor, category, subject), aggregated counts."""

    _name = 'tuition.tutor.wise.report'
    _description = 'Tutor-wise Report (SQL View)'
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
                    )::integer AS effective_classes
                FROM base
                GROUP BY report_date, tutor_id, category_id, subject_id, category_subject
            )
            """
        )


class TuitionTutorWiseWizard(models.TransientModel):
    """Interactive report wizard: date range + tutor/category/subject filters."""

    _name = 'tuition.tutor.wise.wizard'
    _description = 'Tutor-wise Report Wizard'
    _inherit = 'tuition.date.range.wizard.mixin'

    from_date = fields.Date(
        string='From Date',
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    to_date = fields.Date(
        string='To Date',
        default=lambda self: fields.Date.context_today(self).replace(
            day=calendar.monthrange(fields.Date.context_today(self).year, fields.Date.context_today(self).month)[1]
        ),
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
        from_date = fields.Date.to_date(vals.get('from_date')) or fields.Date.context_today(self).replace(day=1)
        to_date = fields.Date.to_date(vals.get('to_date')) or fields.Date.context_today(self).replace(day=calendar.monthrange(fields.Date.context_today(self).year, fields.Date.context_today(self).month)[1])
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
            group_clause = "occ.tutor_id"
            order_clause = "occ.tutor_id"
            cat_subject_expr = "NULL"
            cat_id_expr = "NULL::integer"
            subj_id_expr = "NULL::integer"
        else:
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
                tutor_id, category_id, subject_id, category_subject,
                total_classes, total_demos, completed_classes, cancelled_classes, effective_classes,
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
    """One line per (tutor, category, subject) combination."""

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
