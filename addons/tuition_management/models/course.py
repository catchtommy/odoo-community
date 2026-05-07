# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta
import pytz


class CourseMaster(models.Model):
    _name = 'course.master'
    _description = 'Course Master'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Course Name', required=True)
    subject_id = fields.Many2one('subject.master', string='Subject', tracking=True)
    grade_id = fields.Many2one('grade.master', string='Grade')
    status = fields.Selection([
        ('draft', 'Draft'), ('active', 'Active'), ('completed', 'Completed'), ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)
    start_date = fields.Date(string='Start Date')
    end_date = fields.Date(string='End Date')
    category_id = fields.Many2one(
        'subject.category',
        string='Category',
        store=True,
    )
    tutor_id = fields.Many2one('tutor.profile', string='Primary Tutor', tracking=True)
    tutor_ids = fields.Many2many(
        'tutor.profile',
        'course_master_tutor_rel',
        'course_id',
        'tutor_id',
        string='Tutors',
        tracking=True,
    )
    eligible_tutor_ids = fields.Many2many(
        'tutor.profile',
        string='Eligible Tutors',
        compute='_compute_eligible_tutor_ids',
        store=False,
    )

    @api.onchange('subject_id')
    def _onchange_subject_id(self):
        if self.subject_id and self.subject_id.category_id:
            self.category_id = self.subject_id.category_id
        elif not self.subject_id:
            pass  # Keep category when subject cleared so user can re-filter

    @api.onchange('category_id')
    def _onchange_category_id(self):
        if self.subject_id and self.subject_id.category_id != self.category_id:
            self.subject_id = False

    @api.depends('subject_id', 'grade_id')
    def _compute_eligible_tutor_ids(self):
        tutor_model = self.env['tutor.profile']
        for rec in self:
            if rec.subject_id:
                domain = [('subject_ids', 'in', rec.subject_id.ids)]
                if rec.grade_id:
                    # Include tutors who match the grade OR have no grades set (teach all grades)
                    domain += ['|', ('grade_ids', 'in', rec.grade_id.ids), ('grade_ids', '=', False)]
                rec.eligible_tutor_ids = tutor_model.search(domain)
            else:
                rec.eligible_tutor_ids = tutor_model.browse()
    coordinator_id = fields.Many2one('res.users', string='Coordinator')
    schedule_ids = fields.One2many('class.schedule', 'course_id', string='Schedules')
    schedule_id = fields.Many2one(
        'class.schedule',
        string='Primary Schedule',
        compute='_compute_chatter_tracked_relations',
        store=True,
        tracking=True,
    )
    enrollment_ids = fields.One2many('course.enrollment', 'course_id', string='Enrollments')
    subscription_plan_id = fields.Many2one(
        'tuition.plan.line',
        string='Subscription Plan',
        compute='_compute_chatter_tracked_relations',
        store=True,
        tracking=True,
    )
    progress_report_ids = fields.One2many('progress.report', 'course_id', string='Progress Reports')
    assignment_ids = fields.One2many('course.assignment', 'course_id', string='Assignments')
    occurrence_ids = fields.One2many('class.schedule.occurrence', 'course_id', string='Schedule Occurrences')
    demo_session_ids = fields.One2many('demo.session', 'course_id', string='Demo Sessions')

    # Virtual Classroom — provider is defined ONLY at course level.
    # All scheduled sessions inherit the provider dynamically from here.
    virtual_provider_default = fields.Selection([
        ('bbb', 'BigBlueButton'),
        ('zoom', 'Zoom'),
        ('google_meet', 'Google Meet'),
    ], string='Virtual Classroom Provider', default='bbb', required=True, tracking=True)
    google_meet_static_url = fields.Char(string='Static Google Meet URL')
    # Legacy static classroom fields — kept for data migration only
    virtual_class_platform = fields.Selection([
        ('zoom', 'Zoom'),
        ('google_meet', 'Google Meet'),
        ('bigbluebutton', 'BigBlueButton'),
        ('microsoft_teams', 'Microsoft Teams'),
        ('other', 'Other'),
    ], string='Legacy Platform')
    virtual_class_url = fields.Char(string='Legacy Meeting URL')
    virtual_class_meeting_id = fields.Char(string='Legacy Meeting ID')
    virtual_class_passcode = fields.Char(string='Legacy Passcode')
    virtual_class_notes = fields.Text(string='Legacy Virtual Class Notes')

    student_count = fields.Integer(string='Total Students', compute='_compute_student_count')

    @api.depends('enrollment_ids')
    def _compute_student_count(self):
        for rec in self:
            rec.student_count = len(rec.enrollment_ids.filtered(lambda e: e.status == 'active'))

    @api.depends(
        'schedule_ids',
        'schedule_ids.create_date',
        'enrollment_ids',
        'enrollment_ids.subscription_id',
        'enrollment_ids.subscription_id.plan_line_ids',
        'enrollment_ids.subscription_id.plan_line_ids.state',
        'enrollment_ids.subscription_id.plan_line_ids.start_date',
        'enrollment_ids.subscription_id.plan_line_ids.end_date',
    )
    def _compute_chatter_tracked_relations(self):
        today = fields.Date.today()
        for rec in self:
            rec.schedule_id = rec.schedule_ids[:1].id if rec.schedule_ids else False
            plans = rec.enrollment_ids.mapped('subscription_id.plan_line_ids').filtered(
                lambda plan: plan.state == 'active'
                and plan.start_date
                and plan.start_date <= today
                and (not plan.end_date or plan.end_date >= today)
            )
            rec.subscription_plan_id = plans[:1].id if plans else False

    @api.model_create_multi
    def create(self, vals_list):
        # Enforce BigBlueButton as the default provider at ORM level
        for vals in vals_list:
            vals.setdefault('virtual_provider_default', 'bbb')
        records = super().create(vals_list)
        for rec in records:
            # Sync primary tutor into tutor_ids set
            if rec.tutor_id and rec.tutor_id not in rec.tutor_ids:
                rec.sudo().write({'tutor_ids': [(4, rec.tutor_id.id)]})
            rec._subscribe_related_partners()
            rec.message_post(
                body='Course created: %s.' % rec.name,
                subtype_xmlid='mail.mt_note',
            )
            if rec.tutor_id:
                rec._post_tutor_assigned_message()
            else:
                rec._schedule_tutor_assignment_activity()
        return records

    def write(self, vals):
        old_tutors = {rec.id: rec.tutor_id for rec in self}
        res = super().write(vals)
        if {'enrollment_ids', 'tutor_id', 'tutor_ids'} & set(vals.keys()):
            for rec in self:
                rec._subscribe_related_partners()
        if 'tutor_id' in vals:
            for rec in self.filtered('tutor_id'):
                if old_tutors.get(rec.id) != rec.tutor_id:
                    # Keep tutor_ids in sync — primary tutor is always in the set
                    if rec.tutor_id and rec.tutor_id not in rec.tutor_ids:
                        rec.sudo().write({'tutor_ids': [(4, rec.tutor_id.id)]})
                    rec._post_tutor_assigned_message()
        return res

    def _subscribe_related_partners(self):
        for rec in self:
            partner_ids = []
            # Subscribe all tutors (primary + supporting)
            for tutor in rec.tutor_ids:
                if tutor.partner_id:
                    partner_ids.append(tutor.partner_id.id)
            if rec.tutor_id and rec.tutor_id.partner_id:
                partner_ids.append(rec.tutor_id.partner_id.id)
            for student in rec.enrollment_ids.mapped('student_id'):
                if student.partner_id:
                    partner_ids.append(student.partner_id.id)
                if student.parent_id.partner_id:
                    partner_ids.append(student.parent_id.partner_id.id)
            if partner_ids:
                rec.message_subscribe(partner_ids=list(set(partner_ids)))

    def _post_tutor_assigned_message(self):
        self.ensure_one()
        self.message_post(
            body='Tutor assigned: %s.' % self.tutor_id.name,
            subtype_xmlid='mail.mt_note',
        )

    def _schedule_tutor_assignment_activity(self):
        todo_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if not todo_type:
            return
        for rec in self:
            user = rec.coordinator_id or self.env.user
            existing = rec.activity_ids.filtered(lambda a: a.summary == 'Assign tutor')
            if not existing:
                rec.activity_schedule(
                    'mail.mail_activity_data_todo',
                    date_deadline=fields.Date.today(),
                    summary='Assign tutor',
                    note='Assign a tutor before the course begins.',
                    user_id=user.id,
                )

    @api.model
    def _cron_schedule_subscription_renewal_activities(self):
        """Sample native activity automation for plans ending in the next 14 days."""
        today = fields.Date.today()
        deadline = today + timedelta(days=14)
        plans = self.env['tuition.plan.line'].search([
            ('state', '=', 'active'),
            ('end_date', '>=', today),
            ('end_date', '<=', deadline),
        ])
        for plan in plans:
            course = plan.subscription_id.enrollment_id.course_id
            if not course:
                continue
            existing = course.activity_ids.filtered(
                lambda a: a.summary == 'Renew subscription'
                and a.date_deadline == plan.end_date
            )
            if existing:
                continue
            course.activity_schedule(
                'mail.mail_activity_data_todo',
                date_deadline=plan.end_date,
                summary='Renew subscription',
                note='Review renewal for %s.' % plan.subscription_id.name,
                user_id=(course.coordinator_id or self.env.user).id,
            )

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

    def action_start_virtual_class(self):
        """Start the virtual classroom for this course and open the host URL (admin backend)."""
        self.ensure_one()
        service = self.env['virtual.classroom.service']
        provider = self.virtual_provider_default or 'bbb'
        occurrence = self.env['class.schedule.occurrence'].search([
            ('course_id', '=', self.id),
            ('lesson_status', '=', 'scheduled'),
        ], order='start_datetime asc', limit=1)
        if not occurrence:
            raise UserError("No scheduled lessons found for this course.")
        meeting = service.start_meeting(occurrence, provider)
        url = service.get_tutor_start_url(meeting, self.tutor_id)
        if not url:
            raise UserError("Could not generate a virtual classroom URL.")
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }

    def action_cancel_course(self):
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

        # Delete all future occurrences regardless of status
        future_occurrences = self.env['class.schedule.occurrence'].with_context(force_delete_lesson=True).sudo().search([
            ('course_id', '=', self.id),
            ('start_datetime', '>=', now),
        ])
        if future_occurrences:
            future_occurrences.unlink()

        # Mark past unmarked/scheduled occurrences as cancelled
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
        records = super().create(vals_list)
        for rec in records.filtered('course_id'):
            rec.course_id._subscribe_related_partners()
            rec.course_id.message_post(
                body='Student enrolled: %s.' % rec.student_id.name,
                subtype_xmlid='mail.mt_note',
            )
        return records

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


class ClassScheduleOccurrence(models.Model):
    _name = 'class.schedule.occurrence'
    _description = 'Class Schedule Occurrence'

    name = fields.Char(string='Name', required=True)
    class_schedule_id = fields.Many2one('class.schedule', string='Schedule', required=True, ondelete='cascade')
    course_id = fields.Many2one('course.master', string='Course', ondelete='cascade')
    tutor_id = fields.Many2one('tutor.profile', string='Tutor', ondelete='set null')
    student_ids = fields.Many2many('student.profile', string='Students')
    start_datetime = fields.Datetime(string='Start Time', required=True)
    end_datetime = fields.Datetime(string='End Time', required=True)
    status = fields.Selection([
        ('scheduled', 'Scheduled'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='scheduled')
    attendance_marked = fields.Boolean(string='Attendance Marked', default=False)
    lesson_status = fields.Selection([
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='Lesson Status', default='pending')

    @api.model
    def create(self, vals):
        # Automatically set the course_id based on the class_schedule_id
        if vals.get('class_schedule_id'):
            schedule = self.env['class.schedule'].browse(vals['class_schedule_id'])
            vals['course_id'] = schedule.course_id.id if schedule.course_id else False
        return super(ClassScheduleOccurrence, self).create(vals)

    def write(self, vals):
        # Prevent changing course_id once set
        if 'course_id' in vals:
            raise UserError("You cannot change the course directly. Modify the schedule or enrollment instead.")
        return super(ClassScheduleOccurrence, self).write(vals)

    def action_mark_attendance(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Mark Attendance',
            'res_model': 'attendance.sheet',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_occurrence_id': self.id},
        }

    def action_view_attendance(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Attendance Records',
            'res_model': 'attendance.sheet',
            'view_mode': 'tree,form',
            'domain': [('occurrence_id', '=', self.id)],
        }

    def action_complete_lesson(self):
        self.ensure_one()
        self.write({'lesson_status': 'completed'})
        # Additional logic for completing a lesson can be added here

    def action_cancel_lesson(self):
        self.ensure_one()
        self.write({'lesson_status': 'cancelled'})
        # Additional logic for cancelling a lesson can be added here

    def action_no_show(self):
        self.ensure_one()
        self.write({'lesson_status': 'no_show'})
        # Additional logic for marking a lesson as no-show can be added here


class ClassScheduleOccurrenceDemo(models.Model):
    _inherit = 'class.schedule.occurrence'
    
    is_demo = fields.Boolean(string='Is Demo Session', default=False)
