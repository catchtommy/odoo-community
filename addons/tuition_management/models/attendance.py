# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError


class AttendanceRecord(models.Model):
    _name = 'attendance.record'
    _description = 'Attendance Record'

    class_schedule_occurrence_id = fields.Many2one('class.schedule.occurrence', string='Schedule Occurrence', ondelete='set null')
    student_id = fields.Many2one('student.profile', string='Student', required=True, ondelete='cascade')
    attendance_date = fields.Date(string='Attendance Date', required=True)
    status = fields.Selection([
        ('present', 'Present'), ('absent', 'Absent'), ('cancelled', 'Cancelled'),
    ], string='Status', default=False)  # No default — must be explicitly selected
    remarks = fields.Text(string='Remarks')
    course_id = fields.Many2one('course.master', string='Course', related='class_schedule_occurrence_id.course_id', store=True, readonly=True)
    tutor_id = fields.Many2one('tutor.profile', string='Tutor', related='class_schedule_occurrence_id.tutor_id', store=True, readonly=True)


class MarkAttendanceWizard(models.TransientModel):
    _name = 'mark.attendance.wizard'
    _description = 'Mark Attendance Wizard'

    occurrence_id = fields.Many2one('class.schedule.occurrence', string='Lesson', required=True)
    line_ids = fields.One2many('mark.attendance.wizard.line', 'wizard_id', string='Students')

    # Academic Traceability
    topic_covered = fields.Text(string='What Was Taught')
    class_rating = fields.Selection([
        ('excellent', 'Excellent – Class went very well, full engagement, objectives exceeded'),
        ('good', 'Good – Smooth session, objectives met'),
        ('satisfactory', 'Satisfactory – Session completed, minor gaps'),
    ], string='How the Class Went')
    next_steps = fields.Text(string='What Students Need Next')
    homework = fields.Text(string='Homework')
    tutor_comments = fields.Text(string='Tutor Comments')
    has_technical_issues = fields.Boolean(string='Technical Issues Encountered?', default=False)
    technical_issue_type = fields.Selection([
        ('tutor_issue', 'Tutor\'s Issue'),
        ('student_issue', 'Student\'s Issue'),
        ('platform_issue', 'Shiningace Platform Issue'),
    ], string='Technical Issue Type')
    technical_issue_details = fields.Text(string='Technical Issue Details')
    any_student_present = fields.Boolean(
        string='Any Student Present', compute='_compute_any_student_present', store=False)

    @api.depends('line_ids', 'line_ids.status')
    def _compute_any_student_present(self):
        for rec in self:
            rec.any_student_present = any(l.status == 'present' for l in rec.line_ids if l.status)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            occ = rec.occurrence_id
            if occ:
                rec.write({
                    'topic_covered': occ.topic_covered or False,
                    'class_rating': occ.class_rating or False,
                    'next_steps': occ.next_steps or False,
                    'homework': occ.homework or False,
                    'tutor_comments': occ.tutor_comments or False,
                    'has_technical_issues': occ.has_technical_issues,
                    'technical_issue_type': occ.technical_issue_type or False,
                    'technical_issue_details': occ.technical_issue_details or False,
                })
        return records

    def action_confirm(self):
        self.ensure_one()
        occurrence = self.occurrence_id
        is_admin = self.env.user.has_group('base.group_system') or self.env.user.has_group('base.group_erp_manager')

        # Every student line must have a status explicitly selected — status can't be a
        # hard-required field on the line model itself, since the wizard is initialized
        # with blank-status placeholder lines (one per enrolled student) before the user
        # fills them in; enforce it here instead, at confirm time.
        missing = self.line_ids.filtered(lambda l: not l.status)
        if missing:
            raise UserError(
                'Please select an attendance status for: %s.'
                % ', '.join(missing.mapped('student_id.name'))
            )

        # Validate mandatory academic fields (only required if at least one student is present)
        all_absent = self.line_ids and all(l.status == 'absent' for l in self.line_ids)
        if not all_absent:
            if not self.topic_covered:
                raise UserError('Please fill in "What Was Taught" before confirming attendance.')
            if not self.class_rating:
                raise UserError('Please select "How the Class Went" before confirming attendance.')
        if self.has_technical_issues and not self.technical_issue_type:
            raise UserError('Please select the type of technical issue encountered.')
        if self.has_technical_issues and not self.technical_issue_details:
            raise UserError('Please describe the technical issues encountered.')

        existing_records = self.env['attendance.record'].search([('class_schedule_occurrence_id', '=', occurrence.id)])
        wizard_student_ids = self.line_ids.mapped('student_id').ids
        to_delete = existing_records.filtered(lambda r: r.student_id.id not in wizard_student_ids)
        if to_delete:
            to_delete.sudo().unlink()
        # Only process lines where status has been explicitly selected; skip blank rows
        active_lines = self.line_ids.filtered(lambda l: l.status)
        if not active_lines:
            if to_delete:
                occurrence.write({'lesson_status': 'scheduled'})
            return {'type': 'ir.actions.act_window_close'}
        for line in active_lines:
            existing = self.env['attendance.record'].search([
                ('class_schedule_occurrence_id', '=', occurrence.id),
                ('student_id', '=', line.student_id.id),
            ], limit=1)
            vals = {
                'class_schedule_occurrence_id': occurrence.id,
                'student_id': line.student_id.id,
                'attendance_date': occurrence.start_datetime.date(),
                'status': line.status, 'remarks': line.remarks,
            }
            if existing:
                existing.write(vals)
            else:
                self.env['attendance.record'].create(vals)
        all_statuses = [line.status for line in active_lines]
        if all_statuses and all(s == 'absent' for s in all_statuses):
            occurrence.write({'lesson_status': 'under_review'})
        elif occurrence.lesson_status in ('scheduled', 'rescheduled'):
            occurrence.write({'lesson_status': 'completed'})
        # Save academic traceability fields to occurrence
        occurrence.write({
            'topic_covered': self.topic_covered,
            'class_rating': self.class_rating,
            'next_steps': self.next_steps,
            'homework': self.homework,
            'tutor_comments': self.tutor_comments,
            'has_technical_issues': self.has_technical_issues,
            'technical_issue_type': self.technical_issue_type if self.has_technical_issues else False,
            'technical_issue_details': self.technical_issue_details if self.has_technical_issues else False,
        })
        return {'type': 'ir.actions.act_window_close'}


class MarkAttendanceWizardLine(models.TransientModel):
    _name = 'mark.attendance.wizard.line'
    _description = 'Mark Attendance Wizard Line'

    wizard_id = fields.Many2one('mark.attendance.wizard', string='Wizard', required=True, ondelete='cascade')
    student_id = fields.Many2one('student.profile', string='Student', required=True)
    status = fields.Selection([
        ('present', 'Present'), ('absent', 'Absent'),
    ], string='Status')  # No default — user must explicitly choose. No "Cancelled" option:
    # cancelling a lesson only happens through the Cancel Lesson wizard (models/schedule.py),
    # which captures a reason — marking attendance must never cancel the lesson.
    remarks = fields.Text(string='Remarks')
