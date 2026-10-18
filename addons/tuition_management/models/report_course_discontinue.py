# -*- coding: utf-8 -*-
import base64
import calendar
import io

import xlsxwriter

from odoo import api, fields, models

from .tz_utils import format_local_dt


def _with_code(code, phone):
    return ' '.join(p for p in (code, phone) if p) if phone else ''


class TuitionCourseDiscontinueWizard(models.TransientModel):
    """Interactive report wizard: courses cancelled in a date range, one line per
    enrolled student, with the cancellation reason and parent/student contacts."""

    _name = 'tuition.course.discontinue.wizard'
    _description = 'Course Discontinue Report Wizard'
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
    filter_category_id = fields.Many2one('subject.category', string='Category')
    filter_subject_id = fields.Many2one('subject.master', string='Subject')
    filter_tutor_id = fields.Many2one('tutor.profile', string='Tutor')
    # Defaults to true discontinuations (after enrolment); empty = all stages.
    filter_stage_ids = fields.Many2many(
        'course.cancellation.stage', string='Cancelled',
        default=lambda self: self._default_stage_ids())
    line_ids = fields.One2many('tuition.course.discontinue.wizard.line', 'wizard_id', string='Lines')

    def _default_stage_ids(self):
        return self.env.ref('tuition_management.cancellation_stage_after_enrolment', raise_if_not_found=False)

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        today = fields.Date.context_today(self)
        from_date = fields.Date.to_date(vals.get('from_date')) or today.replace(day=1)
        to_date = fields.Date.to_date(vals.get('to_date')) or today.replace(day=calendar.monthrange(today.year, today.month)[1])
        if 'line_ids' in fields_list:
            vals['line_ids'] = [(0, 0, line) for line in self._get_line_values(
                from_date, to_date, filter_stage_ids=self._default_stage_ids().ids or None,
                tz_name=vals.get('report_tz') or self._default_report_tz(),
            )]
        return vals

    def _get_line_values(self, from_date, to_date, filter_category_id=None, filter_subject_id=None,
                         filter_tutor_id=None, filter_stage_ids=None, tz_name='UTC'):
        if from_date > to_date:
            return []
        tz_name = self._valid_tz_name(tz_name)
        start, end = self._local_dates_to_utc(from_date, to_date, tz_name)
        domain = [
            ('status', '=', 'cancelled'),
            ('cancelled_datetime', '>=', start),
            ('cancelled_datetime', '<', end),
        ]
        if filter_category_id:
            domain += [
                '|',
                ('category_id', '=', filter_category_id),
                '&', ('category_id', '=', False), ('subject_id.category_id', '=', filter_category_id),
            ]
        if filter_subject_id:
            domain.append(('subject_id', '=', filter_subject_id))
        if filter_tutor_id:
            domain.append(('tutor_ids', 'in', filter_tutor_id))
        if filter_stage_ids:
            domain.append(('cancellation_stage_id', 'in', filter_stage_ids))
        courses = self.env['course.master'].search(domain, order='cancelled_datetime desc, id desc')

        lines = []
        for course in courses:
            base = {
                'course_id': course.id,
                'category_id': (course.category_id or course.subject_id.category_id).id,
                'subject_id': course.subject_id.id,
                'tutor_id': course.tutor_id.id,
                'cancelled_datetime': course.cancelled_datetime,
                'cancelled_on_display': format_local_dt(course.cancelled_datetime, tz_name),
                'cancelled_by_id': course.cancelled_by_id.id,
                'cancellation_reason': course.cancellation_reason,
                'cancellation_stage_id': course.cancellation_stage_id.id,
                'resume_interest': course.resume_interest,
                'expected_restart_date': course.expected_restart_date,
            }
            lines += [dict(base, **contact) for contact in self._course_contacts(course)]
        return lines

    def _course_contacts(self, course):
        """Student/parent contact values, one dict per student: from the enrolments,
        or -- for a course cancelled before anyone enrolled (e.g. after a demo) --
        from the enquiry the course was created for. Always at least one dict."""
        contacts = []
        for student in course.enrollment_ids.mapped('student_id'):
            parent = student.parent_id
            contacts.append({
                'student_id': student.id,
                'student_name': student.name,
                'student_email': student.email or '',
                'student_phone': _with_code(student.country_code, student.phone),
                'parent_id': parent.id,
                'parent_name': parent.name or '',
                'parent_email': parent.email or '',
                'parent_phone': _with_code(parent.country_code, parent.phone),
            })
        if contacts:
            return contacts
        for enquiry in self.env['enquiry'].sudo().search([('course_id', '=', course.id)]):
            student, parent = enquiry.student_profile_id, enquiry.parent_profile_id
            contacts.append({
                'student_id': student.id,
                'student_name': student.name or enquiry.student_name or '',
                'student_email': student.email or '',
                'student_phone': _with_code(student.country_code, student.phone),
                'parent_id': parent.id,
                'parent_name': parent.name or enquiry.name or '',
                'parent_email': parent.email or enquiry.email or '',
                'parent_phone': _with_code(parent.country_code or enquiry.country_code, parent.phone or enquiry.phone),
            })
        return contacts or [{}]

    def _refresh_lines(self):
        for rec in self:
            rec._check_date_range()
            rec.line_ids.unlink()
            for line in self._get_line_values(
                rec.from_date, rec.to_date,
                filter_category_id=rec.filter_category_id.id or None,
                filter_subject_id=rec.filter_subject_id.id or None,
                filter_tutor_id=rec.filter_tutor_id.id or None,
                filter_stage_ids=rec.filter_stage_ids.ids or None,
                tz_name=rec.report_tz,
            ):
                line['wizard_id'] = rec.id
                self.env['tuition.course.discontinue.wizard.line'].create(line)

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
            'filter_category_id': False,
            'filter_subject_id': False,
            'filter_tutor_id': False,
            'filter_stage_ids': [(6, 0, self._default_stage_ids().ids)],
            'report_tz': self._default_report_tz(),
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Course Discontinue Report',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }

    def action_export_excel(self):
        self.ensure_one()
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Course Discontinue Report')

        title_fmt = workbook.add_format({'bold': True, 'font_size': 13})
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#2E86AB', 'font_color': '#FFFFFF', 'border': 1, 'align': 'center'})
        cell_fmt = workbook.add_format({'border': 1, 'valign': 'top'})
        wrap_fmt = workbook.add_format({'border': 1, 'text_wrap': True, 'valign': 'top'})

        sheet.write(0, 0, 'Course Discontinue Report', title_fmt)
        sheet.write(1, 0, f"Period: {self.from_date} to {self.to_date} ({self._get_report_tz_name()})")

        headers = [
            'Cancelled On', 'Cancelled', 'Course', 'Category', 'Subject', 'Tutor', 'Student', 'Student Email',
            'Student Phone', 'Parent', 'Parent Email', 'Parent Phone', 'Cancellation Reason', 'Cancelled By',
            'May Restart?', 'Expected Restart',
        ]
        col_widths = [22, 30, 28, 16, 18, 20, 22, 26, 16, 22, 26, 16, 45, 18, 12, 16]
        for col, (h, w) in enumerate(zip(headers, col_widths)):
            sheet.write(3, col, h, header_fmt)
            sheet.set_column(col, col, w)

        for row_idx, line in enumerate(self.line_ids, start=4):
            values = [
                line.cancelled_on_display, line.cancellation_stage_id.name, line.course_id.name,
                line.category_id.name, line.subject_id.name, line.tutor_id.name, line.student_name,
                line.student_email, line.student_phone, line.parent_name, line.parent_email, line.parent_phone,
            ]
            for col, val in enumerate(values):
                sheet.write(row_idx, col, val or '', cell_fmt)
            sheet.write(row_idx, 12, line.cancellation_reason or '', wrap_fmt)
            sheet.write(row_idx, 13, line.cancelled_by_id.name or '', cell_fmt)
            sheet.write(row_idx, 14, dict(line._fields['resume_interest'].selection).get(line.resume_interest, ''), cell_fmt)
            sheet.write(row_idx, 15, line.expected_restart_date.strftime('%d %b %Y') if line.expected_restart_date else '', cell_fmt)

        summary_row = 4 + len(self.line_ids) + 1
        sheet.write(summary_row, 0, f"Courses cancelled: {len(self.line_ids.mapped('course_id'))}", title_fmt)
        for offset, stage in enumerate(self.line_ids.mapped('cancellation_stage_id'), start=1):
            count = len(self.line_ids.filtered(lambda l: l.cancellation_stage_id == stage).mapped('course_id'))
            sheet.write(summary_row + offset, 0, f"  {stage.name}: {count}")

        workbook.close()
        attachment = self.env['ir.attachment'].create({
            'name': f'Course_Discontinue_Report_{self.from_date}_{self.to_date}.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(output.getvalue()),
            'res_model': self._name,
            'res_id': self.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }


class TuitionCourseDiscontinueWizardLine(models.TransientModel):
    """One line per (cancelled course, enrolled student)."""

    _name = 'tuition.course.discontinue.wizard.line'
    _description = 'Course Discontinue Report Line'
    _order = 'cancelled_datetime desc, course_id, id'

    wizard_id = fields.Many2one('tuition.course.discontinue.wizard', required=True, ondelete='cascade')
    course_id = fields.Many2one('course.master', string='Course', readonly=True)
    category_id = fields.Many2one('subject.category', string='Category', readonly=True)
    subject_id = fields.Many2one('subject.master', string='Subject', readonly=True)
    tutor_id = fields.Many2one('tutor.profile', string='Tutor', readonly=True)
    cancelled_datetime = fields.Datetime(string='Cancelled At (UTC)', readonly=True)
    cancelled_on_display = fields.Char(string='Cancelled On', readonly=True)
    cancelled_by_id = fields.Many2one('res.users', string='Cancelled By', readonly=True)
    cancellation_reason = fields.Text(string='Cancellation Reason', readonly=True)
    cancellation_stage_id = fields.Many2one('course.cancellation.stage', string='Cancelled', readonly=True)
    resume_interest = fields.Selection([('yes', 'Yes'), ('no', 'No')], string='May Restart?', readonly=True)
    expected_restart_date = fields.Date(string='Expected Restart', readonly=True)
    student_id = fields.Many2one('student.profile', string='Student Profile', readonly=True)
    student_name = fields.Char(string='Student', readonly=True)
    student_email = fields.Char(string='Student Email', readonly=True)
    student_phone = fields.Char(string='Student Phone', readonly=True)
    parent_id = fields.Many2one('parent.profile', string='Parent Profile', readonly=True)
    parent_name = fields.Char(string='Parent', readonly=True)
    parent_email = fields.Char(string='Parent Email', readonly=True)
    parent_phone = fields.Char(string='Parent Phone', readonly=True)

    def action_open_course(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.course_id.name,
            'res_model': 'course.master',
            'view_mode': 'form',
            'res_id': self.course_id.id,
            'target': 'current',
        }
