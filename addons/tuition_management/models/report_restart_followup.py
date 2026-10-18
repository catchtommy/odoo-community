# -*- coding: utf-8 -*-
import base64
import calendar
import io

import xlsxwriter
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

from .tz_utils import format_local_dt


def _default_to_date(wizard):
    """End of the month three months from now."""
    end = fields.Date.context_today(wizard) + relativedelta(months=3)
    return end.replace(day=calendar.monthrange(end.year, end.month)[1])


class TuitionRestartFollowupWizard(models.TransientModel):
    """Cancelled courses whose parent said they may restart, by expected restart
    date, so the team can chase them. Overdue = expected date already passed."""

    _name = 'tuition.restart.followup.wizard'
    _description = 'Restart Follow-up Report Wizard'
    _inherit = 'tuition.date.range.wizard.mixin'

    from_date = fields.Date(
        string='Expected Restart From',
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    to_date = fields.Date(string='Expected Restart To', default=lambda self: _default_to_date(self))
    include_overdue = fields.Boolean(
        string='Include Overdue', default=True,
        help='Also list parents whose expected restart date is before "From" and who have not restarted yet.')
    hide_restarted = fields.Boolean(
        string='Hide Already Restarted', default=True,
        help='Hide students already enrolled in a new course for the same subject after the cancellation.')
    filter_category_id = fields.Many2one('subject.category', string='Category')
    filter_subject_id = fields.Many2one('subject.master', string='Subject')
    line_ids = fields.One2many('tuition.restart.followup.wizard.line', 'wizard_id', string='Lines')

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        if 'line_ids' in fields_list:
            today = fields.Date.context_today(self)
            from_date = fields.Date.to_date(vals.get('from_date')) or today.replace(day=1)
            to_date = fields.Date.to_date(vals.get('to_date')) or _default_to_date(self)
            vals['line_ids'] = [(0, 0, line) for line in self._get_line_values(
                from_date, to_date, include_overdue=vals.get('include_overdue', True),
                hide_restarted=vals.get('hide_restarted', True),
                tz_name=vals.get('report_tz') or self._default_report_tz(),
            )]
        return vals

    @api.model
    def _restarted_course(self, course, student):
        """A later, non-cancelled course for the same student and subject."""
        if not student or not course.subject_id:
            return self.env['course.master']
        enrolments = self.env['course.enrollment'].sudo().search([
            ('student_id', '=', student.id),
            ('course_id', '!=', course.id),
            ('course_id.subject_id', '=', course.subject_id.id),
            ('course_id.status', '!=', 'cancelled'),
            ('create_date', '>', course.cancelled_datetime),
        ], order='create_date', limit=1)
        return enrolments.course_id

    def _get_line_values(self, from_date, to_date, include_overdue=True, hide_restarted=True,
                         filter_category_id=None, filter_subject_id=None, tz_name='UTC'):
        if from_date > to_date:
            return []
        tz_name = self._valid_tz_name(tz_name)
        today = fields.Date.context_today(self)
        domain = [
            ('status', '=', 'cancelled'),
            ('resume_interest', '=', 'yes'),
            ('expected_restart_date', '<=', to_date),
        ]
        if include_overdue:
            # Everything in the range, plus anything already past its expected date.
            domain += ['|', ('expected_restart_date', '>=', from_date), ('expected_restart_date', '<', today)]
        else:
            domain.append(('expected_restart_date', '>=', from_date))
        if filter_category_id:
            domain += [
                '|',
                ('category_id', '=', filter_category_id),
                '&', ('category_id', '=', False), ('subject_id.category_id', '=', filter_category_id),
            ]
        if filter_subject_id:
            domain.append(('subject_id', '=', filter_subject_id))
        courses = self.env['course.master'].search(domain, order='expected_restart_date, id')

        contacts_of = self.env['tuition.course.discontinue.wizard']._course_contacts
        lines = []
        for course in courses:
            for contact in contacts_of(course):
                student = self.env['student.profile'].browse(contact.get('student_id') or [])
                restarted = self._restarted_course(course, student)
                if hide_restarted and restarted:
                    continue
                lines.append(dict(
                    contact,
                    course_id=course.id,
                    subject_id=course.subject_id.id,
                    tutor_id=course.tutor_id.id,
                    expected_restart_date=course.expected_restart_date,
                    days_to_restart=(course.expected_restart_date - today).days,
                    restart_note=course.restart_note,
                    cancellation_reason=course.cancellation_reason,
                    cancellation_stage_id=course.cancellation_stage_id.id,
                    cancelled_on_display=format_local_dt(course.cancelled_datetime, tz_name) if course.cancelled_datetime else '',
                    restarted_course_id=restarted.id,
                ))
        return lines

    def _refresh_lines(self):
        for rec in self:
            rec._check_date_range()
            rec.line_ids.unlink()
            for line in self._get_line_values(
                rec.from_date, rec.to_date,
                include_overdue=rec.include_overdue,
                hide_restarted=rec.hide_restarted,
                filter_category_id=rec.filter_category_id.id or None,
                filter_subject_id=rec.filter_subject_id.id or None,
                tz_name=rec.report_tz,
            ):
                line['wizard_id'] = rec.id
                self.env['tuition.restart.followup.wizard.line'].create(line)

    def action_refresh(self):
        # Refresh in place — must NOT return a new act_window action, or the
        # client pushes a second, duplicate breadcrumb/header for the same record.
        self.ensure_one()
        self._refresh_lines()

    def action_clear_filters(self):
        self.ensure_one()
        self.write({
            'from_date': fields.Date.context_today(self).replace(day=1),
            'to_date': _default_to_date(self),
            'include_overdue': True,
            'hide_restarted': True,
            'filter_category_id': False,
            'filter_subject_id': False,
            'report_tz': self._default_report_tz(),
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Restart Follow-up Report',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }

    def action_export_excel(self):
        self.ensure_one()
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Restart Follow-up')

        title_fmt = workbook.add_format({'bold': True, 'font_size': 13})
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#2E86AB', 'font_color': '#FFFFFF', 'border': 1, 'align': 'center'})
        cell_fmt = workbook.add_format({'border': 1, 'valign': 'top'})
        date_fmt = workbook.add_format({'border': 1, 'valign': 'top', 'num_format': 'dd/mm/yyyy'})
        num_fmt = workbook.add_format({'border': 1, 'valign': 'top', 'align': 'center'})
        overdue_fmt = workbook.add_format({'border': 1, 'valign': 'top', 'align': 'center', 'font_color': '#C62828', 'bold': True})
        wrap_fmt = workbook.add_format({'border': 1, 'text_wrap': True, 'valign': 'top'})

        sheet.write(0, 0, 'Restart Follow-up Report', title_fmt)
        sheet.write(1, 0, f"Expected restart: {self.from_date} to {self.to_date}"
                          + (" (including overdue)" if self.include_overdue else ""))

        headers = [
            'Expected Restart', 'Days to Restart', 'Parent', 'Parent Email', 'Parent Phone', 'Student',
            'Course', 'Subject', 'Tutor', 'Restart Notes', 'Cancellation Reason', 'Cancelled On', 'Restarted In',
        ]
        col_widths = [16, 14, 22, 26, 16, 22, 28, 18, 20, 35, 40, 22, 28]
        for col, (h, w) in enumerate(zip(headers, col_widths)):
            sheet.write(3, col, h, header_fmt)
            sheet.set_column(col, col, w)

        for row_idx, line in enumerate(self.line_ids, start=4):
            sheet.write(row_idx, 0, line.expected_restart_date, date_fmt)
            sheet.write(row_idx, 1, line.days_to_restart, overdue_fmt if line.days_to_restart < 0 else num_fmt)
            values = [
                line.parent_name, line.parent_email, line.parent_phone, line.student_name,
                line.course_id.name, line.subject_id.name, line.tutor_id.name,
            ]
            for col, val in enumerate(values, start=2):
                sheet.write(row_idx, col, val or '', cell_fmt)
            sheet.write(row_idx, 9, line.restart_note or '', wrap_fmt)
            sheet.write(row_idx, 10, line.cancellation_reason or '', wrap_fmt)
            sheet.write(row_idx, 11, line.cancelled_on_display or '', cell_fmt)
            sheet.write(row_idx, 12, line.restarted_course_id.name or '', cell_fmt)

        workbook.close()
        attachment = self.env['ir.attachment'].create({
            'name': f'Restart_Followup_Report_{self.from_date}_{self.to_date}.xlsx',
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


class TuitionRestartFollowupWizardLine(models.TransientModel):
    """One line per (cancelled course the parent may restart, student)."""

    _name = 'tuition.restart.followup.wizard.line'
    _description = 'Restart Follow-up Report Line'
    _order = 'expected_restart_date, course_id, id'

    wizard_id = fields.Many2one('tuition.restart.followup.wizard', required=True, ondelete='cascade')
    expected_restart_date = fields.Date(string='Expected Restart', readonly=True)
    days_to_restart = fields.Integer(string='Days to Restart', readonly=True,
                                     help='Negative = the expected restart date has passed.')
    course_id = fields.Many2one('course.master', string='Course', readonly=True)
    subject_id = fields.Many2one('subject.master', string='Subject', readonly=True)
    tutor_id = fields.Many2one('tutor.profile', string='Tutor', readonly=True)
    restart_note = fields.Text(string='Restart Notes', readonly=True)
    cancellation_reason = fields.Text(string='Cancellation Reason', readonly=True)
    cancellation_stage_id = fields.Many2one('course.cancellation.stage', string='Cancelled', readonly=True)
    cancelled_on_display = fields.Char(string='Cancelled On', readonly=True)
    restarted_course_id = fields.Many2one('course.master', string='Restarted In', readonly=True)
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
