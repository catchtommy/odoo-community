# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import timedelta


class AttendanceRecord(models.Model):
    _name = 'attendance.record'
    _description = 'Attendance Record'

    class_schedule_occurrence_id = fields.Many2one('class.schedule.occurrence', string='Schedule Occurrence', ondelete='set null')
    student_id = fields.Many2one('student.profile', string='Student', required=True, ondelete='cascade')
    attendance_date = fields.Date(string='Attendance Date', required=True)
    status = fields.Selection([
        ('present', 'Present'), ('absent', 'Absent'), ('cancelled', 'Cancelled'),
    ], string='Status', default='absent')
    billable = fields.Boolean(string='Billable', default=True)
    remarks = fields.Text(string='Remarks')
    course_id = fields.Many2one('course.master', string='Course', related='class_schedule_occurrence_id.course_id', store=True, readonly=True)
    tutor_id = fields.Many2one('tutor.profile', string='Tutor', related='class_schedule_occurrence_id.tutor_id', store=True, readonly=True)


class MarkAttendanceWizard(models.TransientModel):
    _name = 'mark.attendance.wizard'
    _description = 'Mark Attendance Wizard'

    occurrence_id = fields.Many2one('class.schedule.occurrence', string='Lesson', required=True)
    line_ids = fields.One2many('mark.attendance.wizard.line', 'wizard_id', string='Students')

    def action_confirm(self):
        self.ensure_one()
        occurrence = self.occurrence_id
        is_admin = self.env.user.has_group('base.group_system') or self.env.user.has_group('base.group_erp_manager')
        existing_records = self.env['attendance.record'].search([('class_schedule_occurrence_id', '=', occurrence.id)])
        wizard_student_ids = self.line_ids.mapped('student_id').ids
        to_delete = existing_records.filtered(lambda r: r.student_id.id not in wizard_student_ids)
        if to_delete:
            to_delete.sudo().unlink()
        if not self.line_ids:
            if to_delete:
                occurrence.write({'lesson_status': 'scheduled'})
            return {'type': 'ir.actions.act_window_close'}
        for line in self.line_ids:
            if line.status == 'cancelled' and not is_admin:
                raise UserError("Only administrators can mark attendance as 'Cancelled'.")
            existing = self.env['attendance.record'].search([
                ('class_schedule_occurrence_id', '=', occurrence.id),
                ('student_id', '=', line.student_id.id),
            ], limit=1)
            vals = {
                'class_schedule_occurrence_id': occurrence.id,
                'student_id': line.student_id.id,
                'attendance_date': occurrence.start_datetime.date(),
                'status': line.status, 'billable': line.billable, 'remarks': line.remarks,
            }
            if existing:
                existing.write(vals)
            else:
                self.env['attendance.record'].create(vals)
        all_statuses = [line.status for line in self.line_ids]
        if all_statuses and all(s == 'cancelled' for s in all_statuses):
            occurrence.write({'lesson_status': 'cancelled'})
        elif occurrence.lesson_status in ('scheduled', 'rescheduled'):
            occurrence.write({'lesson_status': 'completed'})
        return {'type': 'ir.actions.act_window_close'}


class MarkAttendanceWizardLine(models.TransientModel):
    _name = 'mark.attendance.wizard.line'
    _description = 'Mark Attendance Wizard Line'

    wizard_id = fields.Many2one('mark.attendance.wizard', string='Wizard', required=True, ondelete='cascade')
    student_id = fields.Many2one('student.profile', string='Student', required=True)
    status = fields.Selection([
        ('present', 'Present'), ('absent', 'Absent'), ('cancelled', 'Cancelled'),
    ], string='Status', default='present', required=True)
    billable = fields.Boolean(string='Billable', default=True)
    remarks = fields.Text(string='Remarks')


class CancelLessonWizard(models.TransientModel):
    _name = 'cancel.lesson.wizard'
    _description = 'Cancel Lesson Wizard'

    occurrence_id = fields.Many2one('class.schedule.occurrence', string='Lesson', required=True)
    reason = fields.Selection([
        ('platform_issue', 'Platform Issue'), ('tutor_issue', 'Tutor Issue'),
        ('admin_issue', 'Admin Issue'), ('student_cancelled', 'Student Cancelled'),
    ], string='Cancellation Reason')
    note = fields.Text(string='Note')
    reschedule = fields.Boolean(string='Reschedule this lesson?', default=False)
    new_date = fields.Datetime(string='New Date & Time')
    new_tutor_id = fields.Many2one('tutor.profile', string='New Tutor')

    def action_confirm_cancel(self):
        self.ensure_one()
        occ = self.occurrence_id
        occ.sudo().write({'lesson_status': 'cancelled', 'cancellation_reason': self.reason, 'cancellation_note': self.note})
        enrollments = self.env['course.enrollment'].search([('course_id', '=', occ.course_id.id), ('status', '=', 'active')])
        existing_att = {att.student_id.id: att for att in occ.attendance_ids}
        for student in enrollments.mapped('student_id'):
            if student.id in existing_att:
                existing_att[student.id].sudo().write({'status': 'cancelled'})
            else:
                self.env['attendance.record'].sudo().create({
                    'class_schedule_occurrence_id': occ.id, 'student_id': student.id,
                    'attendance_date': occ.start_datetime.date() if occ.start_datetime else fields.Date.today(),
                    'status': 'cancelled', 'billable': False,
                })
        if self.reschedule and self.new_date:
            duration = (occ.stop_datetime - occ.start_datetime) if occ.stop_datetime and occ.start_datetime else timedelta(minutes=60)
            self.env['class.schedule.occurrence'].sudo().create({
                'name': '%s (Rescheduled)' % (occ.name or 'Lesson'),
                'schedule_id': occ.schedule_id.id if occ.schedule_id else False,
                'start_datetime': self.new_date, 'stop_datetime': self.new_date + duration,
                'course_id': occ.course_id.id,
                'tutor_id': self.new_tutor_id.id if self.new_tutor_id else occ.tutor_id.id,
                'lesson_status': 'scheduled', 'is_rescheduled': True, 'rescheduled_from_id': occ.id,
            })
        return {'type': 'ir.actions.act_window_close'}
