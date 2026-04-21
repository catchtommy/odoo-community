# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta
import pytz


class CourseMaster(models.Model):
    _name = 'course.master'
    _description = 'Course Master'

    name = fields.Char(string='Course Name', required=True)
    subject_id = fields.Many2one('subject.master', string='Subject')
    grade_id = fields.Many2one('grade.master', string='Grade')
    status = fields.Selection([
        ('draft', 'Draft'), ('active', 'Active'), ('completed', 'Completed'), ('cancelled', 'Cancelled'),
    ], string='Status', default='draft')
    start_date = fields.Date(string='Start Date')
    end_date = fields.Date(string='End Date')
    tutor_id = fields.Many2one('tutor.profile', string='Tutor')
    coordinator_id = fields.Many2one('res.users', string='Coordinator')
    schedule_ids = fields.One2many('class.schedule', 'course_id', string='Schedules')
    enrollment_ids = fields.One2many('course.enrollment', 'course_id', string='Enrollments')
    progress_report_ids = fields.One2many('progress.report', 'course_id', string='Progress Reports')
    assignment_ids = fields.One2many('course.assignment', 'course_id', string='Assignments')
    occurrence_ids = fields.One2many('class.schedule.occurrence', 'course_id', string='Schedule Occurrences')

    # Virtual Classroom
    virtual_class_platform = fields.Selection([
        ('zoom', 'Zoom'),
        ('google_meet', 'Google Meet'),
        ('bigbluebutton', 'BigBlueButton'),
        ('microsoft_teams', 'Microsoft Teams'),
        ('other', 'Other'),
    ], string='Platform')
    virtual_class_url = fields.Char(string='Meeting URL')
    virtual_class_meeting_id = fields.Char(string='Meeting ID')
    virtual_class_passcode = fields.Char(string='Passcode')
    virtual_class_notes = fields.Text(string='Virtual Class Notes')

    student_count = fields.Integer(string='Total Students', compute='_compute_student_count')

    @api.depends('enrollment_ids')
    def _compute_student_count(self):
        for rec in self:
            rec.student_count = len(rec.enrollment_ids.filtered(lambda e: e.status == 'active'))

    def action_enroll_student(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Enroll Student',
            'res_model': 'course.enrollment',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_course_id': self.id},
        }

    def action_view_enrolled_students(self):
        self.ensure_one()
        student_ids = self.enrollment_ids.filtered(lambda e: e.status == 'active').mapped('student_id').ids
        return {
            'type': 'ir.actions.act_window',
            'name': f'Students - {self.name}',
            'res_model': 'student.profile',
            'view_mode': 'list,form',
            'domain': [('id', 'in', student_ids)],
        }

    def action_view_schedule_calendar(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Calendar - {self.name}',
            'res_model': 'class.schedule.occurrence',
            'view_mode': 'calendar,list',
            'domain': [('course_id', '=', self.id)],
        }

    def action_add_progress_report(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'New Progress Report',
            'res_model': 'progress.report',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_course_id': self.id,
                'default_tutor_id': self.tutor_id.id if self.tutor_id else False,
            },
        }

    def action_view_progress_reports(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Progress Reports - {self.name}',
            'res_model': 'progress.report',
            'view_mode': 'list,form',
            'domain': [('course_id', '=', self.id)],
            'context': {
                'default_course_id': self.id,
                'default_tutor_id': self.tutor_id.id if self.tutor_id else False,
            },
        }

    def action_view_assignments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Assignments - {self.name}',
            'res_model': 'course.assignment',
            'view_mode': 'list,form',
            'domain': [('course_id', '=', self.id)],
            'context': {'default_course_id': self.id},
        }

    def action_cancel_course(self):
        """Initiate course cancellation with validations."""
        self.ensure_one()
        now = fields.Datetime.now()

        # Validation 1: future schedules with attendance marked
        future_with_attendance = self.env['class.schedule.occurrence'].search([
            ('course_id', '=', self.id),
            ('start_datetime', '>=', now),
            ('attendance_marked', '=', True),
        ])
        if future_with_attendance:
            raise ValidationError(
                "Unable to cancel the course. Attendance is already marked for future schedules. "
                "Please correct attendance before cancelling."
            )

        # Validation 2: unpaid/pending invoices
        enrollment_ids = self.enrollment_ids.ids
        if enrollment_ids:
            subscriptions = self.env['tuition.subscription'].search([
                ('enrollment_id', 'in', enrollment_ids),
            ])
            if subscriptions:
                pending_invoices = self.env['account.move'].search([
                    ('tuition_subscription_id', 'in', subscriptions.ids),
                    ('move_type', '=', 'out_invoice'),
                    ('payment_state', 'in', ['not_paid', 'partial']),
                    ('state', '=', 'posted'),
                ])
                if pending_invoices:
                    raise ValidationError(
                        "Cannot cancel the course as there are pending invoices associated with enrolments."
                    )

        # Check for past/current schedules without attendance
        unmarked_occurrences = self.env['class.schedule.occurrence'].search([
            ('course_id', '=', self.id),
            ('start_datetime', '<', now),
            ('attendance_marked', '=', False),
            ('lesson_status', '=', 'scheduled'),
        ])

        if unmarked_occurrences:
            wizard = self.env['course.cancel.wizard'].create({
                'course_id': self.id,
                'message': 'Some schedules do not have attendance marked. If you proceed with cancellation, '
                           'these schedules will be marked as Cancelled.',
            })
            for occ in unmarked_occurrences:
                self.env['course.cancel.wizard.line'].create({
                    'wizard_id': wizard.id,
                    'occurrence_id': occ.id,
                    'schedule_date': occ.start_datetime,
                    'lesson_name': occ.name,
                    'tutor_name': occ.tutor_id.name if occ.tutor_id else '',
                })
            return {
                'type': 'ir.actions.act_window',
                'name': 'Confirm Course Cancellation',
                'res_model': 'course.cancel.wizard',
                'view_mode': 'form',
                'res_id': wizard.id,
                'target': 'new',
            }

        self._execute_cancellation()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Course Cancelled',
                'message': f'Course "{self.name}" has been cancelled successfully.',
                'type': 'warning',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    def _execute_cancellation(self):
        """Execute all cascading cancellation updates."""
        self.ensure_one()
        tomorrow = fields.Date.today() + timedelta(days=1)
        now = fields.Datetime.now()

        for schedule in self.schedule_ids:
            schedule.write({'end_date': tomorrow, 'status': 'cancelled'})

        future_occurrences = self.env['class.schedule.occurrence'].search([
            ('course_id', '=', self.id),
            ('start_datetime', '>=', now),
            ('lesson_status', '=', 'scheduled'),
        ])
        if future_occurrences:
            future_occurrences.sudo().write({'lesson_status': 'cancelled'})

        past_unmarked = self.env['class.schedule.occurrence'].search([
            ('course_id', '=', self.id),
            ('start_datetime', '<', now),
            ('attendance_marked', '=', False),
            ('lesson_status', '=', 'scheduled'),
        ])
        if past_unmarked:
            past_unmarked.sudo().write({'lesson_status': 'cancelled'})

        for enrollment in self.enrollment_ids:
            enrollment.write({'status': 'cancelled'})

        subscriptions = self.env['tuition.subscription'].search([
            ('enrollment_id', 'in', self.enrollment_ids.ids),
        ])
        if subscriptions:
            subscriptions.write({'state': 'cancelled'})

        self.write({'status': 'cancelled'})


class CourseEnrollment(models.Model):
    _name = 'course.enrollment'
    _description = 'Course Enrollment'

    name = fields.Char(string='Enrollment Reference', required=True, copy=False, readonly=True, default='New')
    course_id = fields.Many2one('course.master', string='Course', required=True, ondelete='cascade')
    student_id = fields.Many2one('student.profile', string='Student', required=True, ondelete='cascade')
    status = fields.Selection([
        ('draft', 'Draft'), ('active', 'Active'), ('completed', 'Completed'), ('cancelled', 'Cancelled'),
    ], string='Status', default='active')
    subscription_id = fields.Many2one('tuition.subscription', string='Subscription', ondelete='set null')
    sub_plan_name = fields.Char(string='Plan', compute='_compute_sub_info', store=False)
    sub_price = fields.Float(string='Monthly Price', compute='_compute_sub_info', store=False)
    sub_state = fields.Selection(related='subscription_id.state', string='Subscription Status', store=False)
    sub_next_billing = fields.Date(related='subscription_id.next_billing_date', string='Next Billing', store=False)

    @api.depends('subscription_id', 'subscription_id.current_plan_product', 'subscription_id.current_plan_price')
    def _compute_sub_info(self):
        for rec in self:
            rec.sub_plan_name = rec.subscription_id.current_plan_product or '' if rec.subscription_id else ''
            rec.sub_price = rec.subscription_id.current_plan_price or 0.0 if rec.subscription_id else 0.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('course.enrollment') or 'New'
        return super().create(vals_list)

    def action_create_subscription(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'New Subscription',
            'res_model': 'tuition.subscription',
            'view_mode': 'form',
            'target': 'current',
            'context': {'default_student_id': self.student_id.id, 'default_enrollment_id': self.id},
        }


class CourseCancelWizard(models.TransientModel):
    _name = 'course.cancel.wizard'
    _description = 'Course Cancellation Confirmation'

    course_id = fields.Many2one('course.master', string='Course', required=True, readonly=True)
    message = fields.Text(string='Warning', readonly=True)
    line_ids = fields.One2many('course.cancel.wizard.line', 'wizard_id', string='Unmarked Schedules')

    def action_confirm_cancel(self):
        self.ensure_one()
        self.course_id._execute_cancellation()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Course Cancelled',
                'message': 'Course "%s" has been cancelled successfully.' % self.course_id.name,
                'type': 'warning',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    def action_discard(self):
        return {'type': 'ir.actions.act_window_close'}


class CourseCancelWizardLine(models.TransientModel):
    _name = 'course.cancel.wizard.line'
    _description = 'Course Cancel Wizard Line'

    wizard_id = fields.Many2one('course.cancel.wizard', required=True, ondelete='cascade')
    occurrence_id = fields.Many2one('class.schedule.occurrence', string='Lesson', readonly=True)
    schedule_date = fields.Datetime(string='Date', readonly=True)
    lesson_name = fields.Char(string='Session', readonly=True)
    tutor_name = fields.Char(string='Tutor', readonly=True)