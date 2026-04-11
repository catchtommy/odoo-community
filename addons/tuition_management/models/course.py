# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import timedelta, date
import pytz
from dateutil.relativedelta import relativedelta


class SubjectCategory(models.Model):
    _name = 'subject.category'
    _description = 'Subject Category'

    name = fields.Char(string='Category Name', required=True)
    description = fields.Text(string='Description')


class SubjectMaster(models.Model):
    _name = 'subject.master'
    _description = 'Subject Master'

    name = fields.Char(string='Subject Name', required=True)
    category_id = fields.Many2one('subject.category', string='Category')
    description = fields.Text(string='Description')


class GradeMaster(models.Model):
    _name = 'grade.master'
    _description = 'Grade Master'

    name = fields.Char(string='Grade Name', required=True)


class ParentProfile(models.Model):
    _name = 'parent.profile'
    _description = 'Parent Profile'

    name = fields.Char(string='Full Name', required=True)
    email = fields.Char(string='Email')
    country_code = fields.Char(string='Country Code', default='+1')
    phone = fields.Char(string='Phone')
    student_ids = fields.One2many('student.profile', 'parent_id', string='Students')
    address_line_1 = fields.Char(string='Address Line 1')
    address_line_2 = fields.Char(string='Address Line 2')
    address_line_3 = fields.Char(string='Address Line 3')
    address_line_4 = fields.Char(string='Address Line 4')
    zip_code = fields.Char(string='Zip Code')
    partner_id = fields.Many2one('res.partner', string='Contact')
    notes = fields.Html(string='Notes')

    # Portal access info (computed)
    portal_user_id = fields.Many2one('res.users', string='Portal User', compute='_compute_portal_access', store=False)
    portal_login = fields.Char(string='Portal Login', compute='_compute_portal_access', store=False)
    has_portal_access = fields.Boolean(string='Has Portal Access', compute='_compute_portal_access', store=False)

    @api.depends('partner_id')
    def _compute_portal_access(self):
        for rec in self:
            user = self.env['res.users'].sudo().search([('partner_id', '=', rec.partner_id.id)], limit=1) if rec.partner_id else self.env['res.users']
            rec.portal_user_id = user.id if user else False
            rec.portal_login = user.login if user else ''
            rec.has_portal_access = bool(user)

    def action_invite_to_portal(self):
        """Open wizard to set or update portal credentials for this parent."""
        self.ensure_one()
        if not self.email:
            raise UserError("Email is required to create a portal login.")
        ctx = {
            'default_profile_model': 'parent.profile',
            'default_profile_id': self.id,
            'default_name': self.name,
            'default_email': self.email,
            'default_login': self.email,
        }
        # Check for existing portal user
        if self.partner_id:
            user = self.env['res.users'].sudo().search([('partner_id', '=', self.partner_id.id)], limit=1)
            if user:
                ctx['default_is_existing_user'] = True
                ctx['default_existing_user_id'] = user.id
                ctx['default_login'] = user.login
        return {
            'type': 'ir.actions.act_window',
            'name': 'Manage Portal Access',
            'res_model': 'portal.access.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': ctx,
        }


class StudentProfile(models.Model):
    _name = 'student.profile'
    _description = 'Student Profile'

    name = fields.Char(string='Full Name', required=True)
    email = fields.Char(string='Email')
    country_code = fields.Char(string='Country Code', default='+1')
    phone = fields.Char(string='Phone')
    grade_id = fields.Many2one('grade.master', string='Grade')
    subjects_ids = fields.Many2many('subject.master', string='Subjects')
    parent_id = fields.Many2one('parent.profile', string='Parent')
    partner_id = fields.Many2one('res.partner', string='Contact')
    address_line_1 = fields.Char(string='Address Line 1')
    address_line_2 = fields.Char(string='Address Line 2')
    address_line_3 = fields.Char(string='Address Line 3')
    address_line_4 = fields.Char(string='Address Line 4')
    zip_code = fields.Char(string='Zip Code')
    active = fields.Boolean(default=True)

    # Portal access info (computed)
    portal_user_id = fields.Many2one('res.users', string='Portal User', compute='_compute_portal_access', store=False)
    portal_login = fields.Char(string='Portal Login', compute='_compute_portal_access', store=False)
    has_portal_access = fields.Boolean(string='Has Portal Access', compute='_compute_portal_access', store=False)

    @api.depends('partner_id')
    def _compute_portal_access(self):
        for rec in self:
            user = self.env['res.users'].sudo().search([('partner_id', '=', rec.partner_id.id)], limit=1) if rec.partner_id else self.env['res.users']
            rec.portal_user_id = user.id if user else False
            rec.portal_login = user.login if user else ''
            rec.has_portal_access = bool(user)

    def action_invite_to_portal(self):
        """Open wizard to set or update portal credentials for this student."""
        self.ensure_one()
        if not self.email:
            raise UserError("Email is required to create a portal login.")
        ctx = {
            'default_profile_model': 'student.profile',
            'default_profile_id': self.id,
            'default_name': self.name,
            'default_email': self.email,
            'default_login': self.email,
        }
        if self.partner_id:
            user = self.env['res.users'].sudo().search([('partner_id', '=', self.partner_id.id)], limit=1)
            if user:
                ctx['default_is_existing_user'] = True
                ctx['default_existing_user_id'] = user.id
                ctx['default_login'] = user.login
        return {
            'type': 'ir.actions.act_window',
            'name': 'Manage Portal Access',
            'res_model': 'portal.access.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': ctx,
        }

    def action_view_parent(self):
        self.ensure_one()
        if self.parent_id:
            return {
                'type': 'ir.actions.act_window',
                'name': 'Parent',
                'res_model': 'parent.profile',
                'view_mode': 'form',
                'res_id': self.parent_id.id,
            }


class TutorProfile(models.Model):
    _name = 'tutor.profile'
    _description = 'Tutor Profile'

    name = fields.Char(string='Full Name', required=True)
    email = fields.Char(string='Email')
    country_code = fields.Char(string='Country Code', default='+1')
    phone = fields.Char(string='Phone')
    subject_ids = fields.Many2many('subject.master', string='Subjects')
    availability_ids = fields.One2many('tutor.availability', 'tutor_id', string='Availability')
    partner_id = fields.Many2one('res.partner', string='Contact')
    portal_user_id = fields.Many2one('res.users', string='Portal User', compute='_compute_portal_access', store=False)
    portal_login = fields.Char(string='Portal Login', compute='_compute_portal_access', store=False)
    has_portal_access = fields.Boolean(string='Has Portal Access', compute='_compute_portal_access', store=False)
    active = fields.Boolean(default=True)

    @api.depends('partner_id')
    def _compute_portal_access(self):
        for rec in self:
            user = self.env['res.users'].sudo().search([('partner_id', '=', rec.partner_id.id)], limit=1) if rec.partner_id else self.env['res.users']
            rec.portal_user_id = user.id if user else False
            rec.portal_login = user.login if user else ''
            rec.has_portal_access = bool(user)

    def action_invite_to_portal(self):
        """Open wizard to set or update portal credentials for this tutor."""
        self.ensure_one()
        if not self.email:
            raise UserError("Email is required to create a portal login.")
        ctx = {
            'default_profile_model': 'tutor.profile',
            'default_profile_id': self.id,
            'default_name': self.name,
            'default_email': self.email,
            'default_login': self.email,
        }
        if self.partner_id:
            user = self.env['res.users'].sudo().search([('partner_id', '=', self.partner_id.id)], limit=1)
            if user:
                ctx['default_is_existing_user'] = True
                ctx['default_existing_user_id'] = user.id
                ctx['default_login'] = user.login
        return {
            'type': 'ir.actions.act_window',
            'name': 'Manage Portal Access',
            'res_model': 'portal.access.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': ctx,
        }


class TutorAvailability(models.Model):
    _name = 'tutor.availability'
    _description = 'Tutor Availability'

    tutor_id = fields.Many2one('tutor.profile', string='Tutor', required=True, ondelete='cascade')
    day_of_week = fields.Selection([
        ('monday', 'Monday'),
        ('tuesday', 'Tuesday'),
        ('wednesday', 'Wednesday'),
        ('thursday', 'Thursday'),
        ('friday', 'Friday'),
        ('saturday', 'Saturday'),
        ('sunday', 'Sunday'),
    ], string='Day of Week', required=True)
    start_time = fields.Float(string='Start Time')
    end_time = fields.Float(string='End Time')


class TuitionTimeSlot(models.Model):
    _name = 'tuition.time.slot'
    _description = 'Time Slot'

    hour = fields.Integer(string='Hour', required=True)
    minute = fields.Integer(string='Minute', required=True)
    name = fields.Char(string='Time', compute='_compute_name', store=True)

    @api.depends('hour', 'minute')
    def _compute_name(self):
        for rec in self:
            rec.name = f'{rec.hour:02d}:{rec.minute:02d}'


class CourseMaster(models.Model):
    _name = 'course.master'
    _description = 'Course Master'

    name = fields.Char(string='Course Name', required=True)
    subject_id = fields.Many2one('subject.master', string='Subject')
    grade_id = fields.Many2one('grade.master', string='Grade')
    status = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
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


class CourseEnrollment(models.Model):
    _name = 'course.enrollment'
    _description = 'Course Enrollment'

    name = fields.Char(string='Enrollment Reference', required=True, copy=False, readonly=True, default='New')
    course_id = fields.Many2one('course.master', string='Course', required=True, ondelete='cascade')
    student_id = fields.Many2one('student.profile', string='Student', required=True, ondelete='cascade')
    fee = fields.Float(string='Fee')
    fee_type = fields.Selection([
        ('per_lesson', 'Per Lesson'),
        ('fixed_monthly', 'Fixed Monthly'),
    ], string='Fee Type', default='per_lesson')
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.company.currency_id)
    discount_amount = fields.Float(string='Discount Amount')
    net_fee = fields.Float(string='Net Fee', compute='_compute_net_fee', store=True)
    status = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='active')
    invoice_type = fields.Selection([
        ('one_time', 'One Time'),
        ('recurring', 'Recurring'),
    ], string='Invoice Type', default='one_time')
    billing_cycle = fields.Selection([
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
    ], string='Billing Cycle')
    invoice_start_date = fields.Date(string='Invoice Start Date')
    invoice_generation_date = fields.Integer(string='Invoice Generation Day', help='Day of month for invoice generation')

    @api.depends('fee', 'discount_amount')
    def _compute_net_fee(self):
        for rec in self:
            rec.net_fee = rec.fee - (rec.discount_amount or 0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('course.enrollment') or 'New'
        return super().create(vals_list)


class ClassSchedule(models.Model):
    _name = 'class.schedule'
    _description = 'Class Schedule'

    name = fields.Char(string='Schedule Name', compute='_compute_name', store=True)
    course_id = fields.Many2one('course.master', string='Course', required=True, ondelete='cascade')
    tutor_id = fields.Many2one('tutor.profile', string='Tutor')
    schedule_type = fields.Selection([
        ('one_time', 'One Time'),
        ('recurring', 'Recurring'),
    ], string='Schedule Type', default='recurring')
    schedule_hour = fields.Integer(string='Hour', default=9)
    schedule_minute = fields.Integer(string='Minute', default=0)
    schedule_duration = fields.Integer(string='Duration (Minutes)', default=60)
    timezone = fields.Selection([
        ('US/Eastern', 'US/Eastern'),
        ('US/Central', 'US/Central'),
        ('US/Mountain', 'US/Mountain'),
        ('US/Pacific', 'US/Pacific'),
        ('Europe/London', 'Europe/London'),
        ('Europe/Paris', 'Europe/Paris'),
        ('Asia/Kolkata', 'Asia/Kolkata'),
        ('Asia/Tokyo', 'Asia/Tokyo'),
        ('Australia/Sydney', 'Australia/Sydney'),
        ('UTC', 'UTC'),
    ], string='Timezone', default='UTC')
    status = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='active')
    monday = fields.Boolean(string='Monday')
    tuesday = fields.Boolean(string='Tuesday')
    wednesday = fields.Boolean(string='Wednesday')
    thursday = fields.Boolean(string='Thursday')
    friday = fields.Boolean(string='Friday')
    saturday = fields.Boolean(string='Saturday')
    sunday = fields.Boolean(string='Sunday')
    start_date = fields.Date(string='Start Date')
    end_date = fields.Date(string='End Date')
    occurrence_ids = fields.One2many('class.schedule.occurrence', 'schedule_id', string='Occurrences')

    @api.depends('course_id', 'tutor_id', 'schedule_type')
    def _compute_name(self):
        for rec in self:
            parts = []
            if rec.course_id:
                parts.append(rec.course_id.name or '')
            if rec.tutor_id:
                parts.append(rec.tutor_id.name or '')
            if rec.schedule_type:
                parts.append(dict(rec._fields['schedule_type'].selection).get(rec.schedule_type, ''))
            rec.name = ' - '.join(parts) if parts else 'New Schedule'

    def _generate_occurrences(self):
        """Generate individual occurrence records for recurring schedules."""
        for record in self:
            # Only delete occurrences that are still in 'scheduled' status
            scheduled_occurrences = record.occurrence_ids.filtered(lambda o: o.lesson_status == 'scheduled')
            scheduled_occurrences.sudo().unlink()

            if not record.start_date or not record.end_date:
                continue

            day_map = {
                'monday': 0, 'tuesday': 1, 'wednesday': 2,
                'thursday': 3, 'friday': 4, 'saturday': 5, 'sunday': 6,
            }
            selected_days = []
            for day_name, day_num in day_map.items():
                if getattr(record, day_name):
                    selected_days.append(day_num)

            if not selected_days and record.schedule_type == 'one_time':
                selected_days = [record.start_date.weekday()]

            tz = pytz.timezone(record.timezone or 'UTC')
            occurrences = []
            current_date = record.start_date
            while current_date <= record.end_date:
                if current_date.weekday() in selected_days:
                    local_dt = tz.localize(
                        fields.Datetime.to_datetime(current_date).replace(
                            hour=record.schedule_hour,
                            minute=record.schedule_minute,
                            second=0,
                        )
                    )
                    utc_start = local_dt.astimezone(pytz.utc).replace(tzinfo=None)
                    utc_stop = utc_start + timedelta(minutes=record.schedule_duration or 60)
                    occurrences.append({
                        'schedule_id': record.id,
                        'name': f"{record.course_id.name or 'Class'} - {current_date.strftime('%a %b %d, %Y')}",
                        'start_datetime': utc_start,
                        'stop_datetime': utc_stop,
                        'course_id': record.course_id.id,
                        'tutor_id': record.tutor_id.id if record.tutor_id else False,
                    })
                current_date += timedelta(days=1)

            if occurrences:
                self.env['class.schedule.occurrence'].sudo().create(occurrences)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            record._generate_occurrences()
        return records

    def write(self, vals):
        res = super().write(vals)
        trigger_fields = [
            'start_date', 'end_date', 'schedule_hour', 'schedule_minute',
            'schedule_duration', 'timezone', 'monday', 'tuesday', 'wednesday',
            'thursday', 'friday', 'saturday', 'sunday', 'schedule_type', 'course_id',
        ]
        if any(f in vals for f in trigger_fields):
            for record in self:
                record._generate_occurrences()
        return res


class ClassScheduleOccurrence(models.Model):
    _name = 'class.schedule.occurrence'
    _description = 'Class Schedule Occurrence'
    _order = 'start_datetime'

    name = fields.Char(string='Name', required=True)
    schedule_id = fields.Many2one('class.schedule', string='Schedule', ondelete='set null')
    start_datetime = fields.Datetime(string='Start', required=True)
    stop_datetime = fields.Datetime(string='Stop', required=True)
    course_id = fields.Many2one('course.master', string='Course', store=True)
    tutor_id = fields.Many2one('tutor.profile', string='Tutor', store=True)
    attendance_ids = fields.One2many('attendance.record', 'class_schedule_occurrence_id', string='Attendance')
    attendance_marked = fields.Boolean(string='Attendance Marked', compute='_compute_attendance_marked', store=True)
    lesson_status = fields.Selection([
        ('scheduled', 'Scheduled'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('no_show', 'No Show'),
    ], string='Lesson Status', default='scheduled')

    @api.depends('attendance_ids')
    def _compute_attendance_marked(self):
        for rec in self:
            rec.attendance_marked = bool(rec.attendance_ids)

    def write(self, vals):
        # Only admin/managers can cancel a lesson
        if vals.get('lesson_status') == 'cancelled':
            if not self.env.user.has_group('base.group_system') and not self.env.user.has_group('base.group_erp_manager'):
                raise UserError(
                    "Only administrators or managers can cancel a lesson. "
                    "Please contact your administrator."
                )
        return super().write(vals)

    def unlink(self):
        """Prevent deletion of lessons that have a status other than scheduled."""
        protected = self.filtered(lambda r: r.lesson_status and r.lesson_status != 'scheduled')
        if protected:
            raise UserError(
                "Cannot delete lessons that have been completed, cancelled, or marked as no-show. "
                "You can only delete lessons with 'Scheduled' status."
            )
        return super().unlink()

    def action_mark_attendance(self):
        """Open the mark attendance wizard for this occurrence."""
        self.ensure_one()
        # Get enrolled students for this course
        enrollments = self.env['course.enrollment'].search([
            ('course_id', '=', self.course_id.id),
            ('status', '=', 'active'),
        ])
        student_ids = enrollments.mapped('student_id').ids

        # Create wizard with student lines
        wizard = self.env['mark.attendance.wizard'].create({
            'occurrence_id': self.id,
            'lesson_status': self.lesson_status or 'scheduled',
        })
        # Pre-populate student lines
        existing_attendance = {att.student_id.id: att for att in self.attendance_ids}
        lines = []
        for student_id in student_ids:
            existing = existing_attendance.get(student_id)
            lines.append((0, 0, {
                'wizard_id': wizard.id,
                'student_id': student_id,
                'status': existing.status if existing else 'present',
                'billable': existing.billable if existing else True,
                'remarks': existing.remarks if existing else '',
            }))
        if lines:
            wizard.write({'line_ids': lines})

        return {
            'type': 'ir.actions.act_window',
            'name': f'Mark Attendance - {self.name}',
            'res_model': 'mark.attendance.wizard',
            'view_mode': 'form',
            'res_id': wizard.id,
            'target': 'new',
        }


class MarkAttendanceWizard(models.TransientModel):
    _name = 'mark.attendance.wizard'
    _description = 'Mark Attendance Wizard'

    occurrence_id = fields.Many2one('class.schedule.occurrence', string='Lesson', required=True)
    lesson_status = fields.Selection([
        ('scheduled', 'Scheduled'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('no_show', 'No Show'),
    ], string='Lesson Status', required=True)
    line_ids = fields.One2many('mark.attendance.wizard.line', 'wizard_id', string='Students')

    def action_confirm(self):
        """Confirm attendance and update lesson status."""
        self.ensure_one()
        occurrence = self.occurrence_id

        # Create or update attendance records
        for line in self.line_ids:
            existing = self.env['attendance.record'].search([
                ('class_schedule_occurrence_id', '=', occurrence.id),
                ('student_id', '=', line.student_id.id),
            ], limit=1)
            vals = {
                'class_schedule_occurrence_id': occurrence.id,
                'student_id': line.student_id.id,
                'attendance_date': occurrence.start_datetime.date(),
                'status': line.status,
                'billable': line.billable,
                'remarks': line.remarks,
            }
            if existing:
                existing.write(vals)
            else:
                self.env['attendance.record'].create(vals)

        # Update lesson status
        occurrence.write({'lesson_status': self.lesson_status})

        return {'type': 'ir.actions.act_window_close'}


class MarkAttendanceWizardLine(models.TransientModel):
    _name = 'mark.attendance.wizard.line'
    _description = 'Mark Attendance Wizard Line'

    wizard_id = fields.Many2one('mark.attendance.wizard', string='Wizard', required=True, ondelete='cascade')
    student_id = fields.Many2one('student.profile', string='Student', required=True)
    status = fields.Selection([
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
        ('excused', 'Excused'),
    ], string='Status', default='present', required=True)
    billable = fields.Boolean(string='Billable', default=True)
    remarks = fields.Text(string='Remarks')


class AttendanceRecord(models.Model):
    _name = 'attendance.record'
    _description = 'Attendance Record'

    class_schedule_occurrence_id = fields.Many2one('class.schedule.occurrence', string='Schedule Occurrence', ondelete='set null')
    student_id = fields.Many2one('student.profile', string='Student', required=True, ondelete='cascade')
    attendance_date = fields.Date(string='Attendance Date', required=True)
    status = fields.Selection([
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
        ('excused', 'Excused'),
    ], string='Status', default='absent')
    billable = fields.Boolean(string='Billable', default=True)
    remarks = fields.Text(string='Remarks')
    course_id = fields.Many2one('course.master', string='Course', related='class_schedule_occurrence_id.course_id', store=True, readonly=True)
    tutor_id = fields.Many2one('tutor.profile', string='Tutor', related='class_schedule_occurrence_id.tutor_id', store=True, readonly=True)


class ProgressReport(models.Model):
    _name = 'progress.report'
    _description = 'Student Progress Report'
    _order = 'report_date desc'

    name = fields.Char(string='Title', required=True)
    course_id = fields.Many2one('course.master', string='Course', required=True, ondelete='cascade')
    student_id = fields.Many2one('student.profile', string='Student', required=True, ondelete='cascade')
    class_schedule_occurrence_id = fields.Many2one('class.schedule.occurrence', string='Class Session')
    report_date = fields.Date(string='Date', required=True, default=fields.Date.today)
    tutor_id = fields.Many2one('tutor.profile', string='Tutor')
    overall_rating = fields.Selection([
        ('excellent', 'Excellent'),
        ('good', 'Good'),
        ('satisfactory', 'Satisfactory'),
        ('needs_improvement', 'Needs Improvement'),
        ('poor', 'Poor'),
    ], string='Overall Rating')
    strengths = fields.Text(string='Strengths')
    areas_for_improvement = fields.Text(string='Areas for Improvement')
    comments = fields.Text(string='Comments')
    homework_notes = fields.Text(string='Homework / Next Steps')
    score = fields.Float(string='Score')
    max_score = fields.Float(string='Max Score', default=100)


class CourseAssignment(models.Model):
    _name = 'course.assignment'
    _description = 'Course Assignment'
    _order = 'due_date'

    name = fields.Char(string='Title', required=True)
    course_id = fields.Many2one('course.master', string='Course', required=True, ondelete='cascade')
    description = fields.Html(string='Description')
    assignment_type = fields.Selection([
        ('homework', 'Homework'),
        ('quiz', 'Quiz'),
        ('test', 'Test'),
        ('project', 'Project'),
        ('worksheet', 'Worksheet'),
        ('other', 'Other'),
    ], string='Type', default='homework')
    due_date = fields.Date(string='Due Date')
    assigned_date = fields.Date(string='Assigned Date', default=fields.Date.today)
    status = fields.Selection([
        ('draft', 'Draft'),
        ('assigned', 'Assigned'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft')
    attachment_ids = fields.Many2many('ir.attachment', string='Attachments')
    submission_ids = fields.One2many('assignment.submission', 'assignment_id', string='Submissions')


class AssignmentSubmission(models.Model):
    _name = 'assignment.submission'
    _description = 'Assignment Submission'

    assignment_id = fields.Many2one('course.assignment', string='Assignment', required=True, ondelete='cascade')
    student_id = fields.Many2one('student.profile', string='Student', required=True, ondelete='cascade')
    submission_date = fields.Datetime(string='Submitted On', default=fields.Datetime.now)
    status = fields.Selection([
        ('pending', 'Pending'),
        ('submitted', 'Submitted'),
        ('graded', 'Graded'),
        ('late', 'Late'),
    ], string='Status', default='pending')
    score = fields.Float(string='Score')
    max_score = fields.Float(string='Max Score', default=100)
    feedback = fields.Text(string='Feedback')
    attachment_ids = fields.Many2many('ir.attachment', string='Attachments')


class PortalAccessWizard(models.TransientModel):
    _name = 'portal.access.wizard'
    _description = 'Portal Access Wizard'

    profile_model = fields.Char(string='Profile Model', required=True)
    profile_id = fields.Integer(string='Profile ID', required=True)
    name = fields.Char(string='Name', readonly=True)
    email = fields.Char(string='Email', readonly=True)
    login = fields.Char(string='Login (Username)', required=True)
    password = fields.Char(string='Password', required=True)
    confirm_password = fields.Char(string='Confirm Password', required=True)
    is_existing_user = fields.Boolean(string='Existing User', readonly=True)
    existing_user_id = fields.Many2one('res.users', string='Existing Portal User', readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        # Auto-detect existing portal user
        profile_model = res.get('profile_model') or self.env.context.get('default_profile_model')
        profile_id = res.get('profile_id') or self.env.context.get('default_profile_id')
        if profile_model and profile_id:
            profile = self.env[profile_model].browse(profile_id)
            if profile.exists() and profile.partner_id:
                user = self.env['res.users'].sudo().search([
                    ('partner_id', '=', profile.partner_id.id)
                ], limit=1)
                if user:
                    res['is_existing_user'] = True
                    res['existing_user_id'] = user.id
                    res['login'] = user.login
        return res

    def _assign_portal_group(self, user):
        """Force user to be portal-only: remove ALL groups, add only portal group using ORM."""
        group_portal = self.env.ref('base.group_portal')
        user.sudo().write({'group_ids': [(6, 0, [group_portal.id])]})
        self.env.invalidate_all()

    def action_create_portal_user(self):
        """Create or update portal user with admin-set credentials."""
        self.ensure_one()
        if self.password != self.confirm_password:
            raise UserError("Passwords do not match.")
        if len(self.password) < 6:
            raise UserError("Password must be at least 6 characters.")
        profile = self.env[self.profile_model].browse(self.profile_id)
        if not profile.exists():
            raise UserError("Profile record not found.")
        domain = [('login', '=', self.login)]
        if self.is_existing_user and self.existing_user_id:
            domain.append(('id', '!=', self.existing_user_id.id))
        duplicate = self.env['res.users'].sudo().with_context(active_test=False).search(domain, limit=1)
        if duplicate:
            raise UserError(f"The username '{self.login}' is already taken by {duplicate.name}.")
        if self.is_existing_user and self.existing_user_id:
            user = self.existing_user_id.sudo()
            update_vals = {'password': self.password, 'active': True}
            if self.login and self.login != user.login:
                update_vals['login'] = self.login
                if user.partner_id:
                    user.partner_id.sudo().write({'email': self.login})
                if hasattr(profile, 'email'):
                    profile.sudo().write({'email': self.login})
            user.write(update_vals)
            self._assign_portal_group(user)
            return {'type': 'ir.actions.client', 'tag': 'display_notification',
                    'params': {'title': 'Portal Access Updated',
                               'message': f'Updated for {self.name}. Login: {self.login}',
                               'type': 'success', 'sticky': False,
                               'next': {'type': 'ir.actions.act_window_close'}}}
        if not profile.partner_id:
            partner = self.env['res.partner'].create({
                'name': profile.name, 'email': profile.email,
                'phone': f"{getattr(profile, 'country_code', '') or ''}{getattr(profile, 'phone', '') or ''}",
            })
            profile.partner_id = partner.id
        else:
            partner = profile.partner_id
            if not partner.email:
                partner.email = profile.email
        existing_user = self.env['res.users'].sudo().with_context(active_test=False).search(
            [('partner_id', '=', partner.id)], limit=1)
        if existing_user:
            existing_user.sudo().write({'login': self.login, 'password': self.password, 'active': True})
            self._assign_portal_group(existing_user.sudo())
        else:
            new_user = self.env['res.users'].sudo().with_context(no_reset_password=True).create({
                'partner_id': partner.id, 'login': self.login,
                'password': self.password, 'active': True,
            })
            self._assign_portal_group(new_user)
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': 'Portal Access Activated',
                           'message': f'Created for {self.name}. Login: {self.login}',
                           'type': 'success', 'sticky': False,
                           'next': {'type': 'ir.actions.act_window_close'}}}

    def action_deactivate_portal_user(self):
        self.ensure_one()
        if self.is_existing_user and self.existing_user_id:
            self.existing_user_id.sudo().write({'active': False})
            return {'type': 'ir.actions.client', 'tag': 'display_notification',
                    'params': {'title': 'Deactivated',
                               'message': f'Access disabled for {self.name}.',
                               'type': 'warning', 'sticky': False,
                               'next': {'type': 'ir.actions.act_window_close'}}}
        raise UserError("No existing portal user found to deactivate.")

    def action_fix_portal_users(self):
        group_portal = self.env.ref('base.group_portal')
        for model_name in ['student.profile', 'tutor.profile', 'parent.profile']:
            for profile in self.env[model_name].sudo().search([('partner_id', '!=', False)]):
                user = self.env['res.users'].sudo().search(
                    [('partner_id', '=', profile.partner_id.id)], limit=1)
                if user and user.id != self.env.ref('base.user_admin').id:
                    self.env.cr.execute(
                        "DELETE FROM res_groups_users_rel WHERE uid=%s AND gid!=%s",
                        (user.id, group_portal.id))
                    self.env.cr.execute(
                        "INSERT INTO res_groups_users_rel(gid,uid) SELECT %s,%s "
                        "WHERE NOT EXISTS(SELECT 1 FROM res_groups_users_rel WHERE gid=%s AND uid=%s)",
                        (group_portal.id, user.id, group_portal.id, user.id))
        self.env.invalidate_all()
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': 'Fixed', 'message': 'All portal users corrected.',
                           'type': 'success', 'sticky': False,
                           'next': {'type': 'ir.actions.act_window_close'}}}

# ============================================================

class TuitionSubscription(models.Model):
    _name = 'tuition.subscription'
    _description = 'Tuition Subscription'
    _order = 'create_date desc'

    name = fields.Char(string='Reference', compute='_compute_name', store=True)
    student_id = fields.Many2one('student.profile', string='Student', required=True,
                                 ondelete='restrict')
    enrollment_id = fields.Many2one(
        'course.enrollment', string='Enrollment', ondelete='restrict',
        domain="[('student_id', '=', student_id)]")
    plan_line_ids = fields.One2many('tuition.plan.line', 'subscription_id', string='Plan History')
    adjustment_ids = fields.One2many('tuition.adjustment', 'subscription_id',
                                     string='Adjustments')
    invoice_ids = fields.One2many('account.move', 'tuition_subscription_id', string='Invoices')
    current_plan_id = fields.Many2one('tuition.plan.line', string='Current Plan',
                                      compute='_compute_current_plan', store=False)
    current_plan_product = fields.Char(string='Current Plan',
                                       compute='_compute_current_plan', store=False)
    current_plan_price = fields.Float(string='Monthly Price',
                                      compute='_compute_current_plan', store=False)
    next_billing_date = fields.Date(string='Next Billing Date')
    state = fields.Selection([
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='active', required=True)
    invoice_count = fields.Integer(compute='_compute_invoice_count', string='Invoices')
    unapplied_adjustment_count = fields.Integer(
        compute='_compute_unapplied_adjustments', string='Pending Adjustments')
    total_adjustments_applied = fields.Float(
        compute='_compute_totals', string='Total Adjustments Applied')
    monthly_revenue = fields.Float(compute='_compute_totals', string='Monthly Revenue')

    @api.depends('student_id', 'enrollment_id')
    def _compute_name(self):
        for rec in self:
            parts = []
            if rec.student_id:
                parts.append(rec.student_id.name)
            if rec.enrollment_id and rec.enrollment_id.course_id:
                parts.append(rec.enrollment_id.course_id.name)
            rec.name = ' / '.join(parts) if parts else 'New Subscription'

    @api.depends('plan_line_ids', 'plan_line_ids.state',
                 'plan_line_ids.start_date', 'plan_line_ids.end_date')
    def _compute_current_plan(self):
        today = fields.Date.today()
        for rec in self:
            plans = rec.plan_line_ids.filtered(
                lambda p: p.state == 'active'
                and p.start_date <= today
                and (not p.end_date or p.end_date >= today)
            )
            plan = plans[0] if plans else False
            rec.current_plan_id = plan.id if plan else False
            rec.current_plan_product = plan.product_id.name if plan else ''
            rec.current_plan_price = plan.price if plan else 0.0

    def _compute_invoice_count(self):
        for rec in self:
            rec.invoice_count = len(rec.invoice_ids)

    def _compute_unapplied_adjustments(self):
        for rec in self:
            rec.unapplied_adjustment_count = len(
                rec.adjustment_ids.filtered(lambda a: not a.applied_in_invoice))

    def _compute_totals(self):
        for rec in self:
            applied = rec.adjustment_ids.filtered(lambda a: a.applied_in_invoice)
            rec.total_adjustments_applied = sum(applied.mapped('amount'))
            plan = rec.current_plan_id
            rec.monthly_revenue = plan.price if plan else 0.0

    def action_view_invoices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Invoices',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('tuition_subscription_id', '=', self.id)],
        }

    def action_schedule_plan_change(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Schedule Plan Change',
            'res_model': 'tuition.plan.change.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_subscription_id': self.id},
        }

    def action_add_adjustment(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Add Adjustment',
            'res_model': 'tuition.adjustment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_subscription_id': self.id},
        }

    def action_generate_invoice(self):
        self.ensure_one()
        invoice = self._generate_invoice()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Invoice',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': invoice.id,
        }

    def action_pause(self):
        self.write({'state': 'paused'})

    def action_activate(self):
        self.write({'state': 'active'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def _generate_invoice(self):
        self.ensure_one()
        if self.state != 'active':
            raise UserError("Cannot generate invoice for a %s subscription." % self.state)
        plan = self.current_plan_id
        if not plan:
            raise UserError("No active plan for subscription %s." % self.name)
        partner = self.student_id.partner_id
        if not partner:
            raise UserError("Student %s has no linked contact." % self.student_id.name)
        # Look up parent for billing
        billing_partner = partner
        parent_profile = self.env['parent.profile'].sudo().search(
            [('student_ids', 'in', [self.student_id.id])], limit=1)
        if parent_profile and parent_profile.partner_id:
            billing_partner = parent_profile.partner_id
        month_label = fields.Date.today().strftime('%B %Y')
        lines = [(0, 0, {
            'name': '%s - %s' % (plan.product_id.name, month_label),
            'product_id': plan.product_id.id,
            'quantity': 1,
            'price_unit': plan.price,
        })]
        unapplied = self.adjustment_ids.filtered(lambda a: not a.applied_in_invoice)
        for adj in unapplied:
            lines.append((0, 0, {
                'name': '[Adjustment] %s' % (adj.description or 'Adjustment'),
                'quantity': 1,
                'price_unit': adj.amount,
            }))
        invoice = self.env['account.move'].sudo().create({
            'move_type': 'out_invoice',
            'partner_id': billing_partner.id,
            'tuition_subscription_id': self.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': lines,
            'narration': 'Tuition: %s | %s | %s' % (
                self.student_id.name, plan.product_id.name, month_label),
        })
        unapplied.write({'applied_in_invoice': True, 'invoice_id': invoice.id})
        today = fields.Date.today()
        self.next_billing_date = today.replace(day=1) + relativedelta(months=1)
        return invoice

    @api.model
    def _cron_generate_monthly_invoices(self):
        today = fields.Date.today()
        subs = self.search([('state', '=', 'active'), ('next_billing_date', '<=', today)])
        for sub in subs:
            try:
                sub._generate_invoice()
            except Exception as e:
                self.env['ir.logging'].sudo().create({
                    'name': 'tuition.subscription',
                    'type': 'server',
                    'level': 'ERROR',
                    'message': 'Invoice failed for %s: %s' % (sub.name, str(e)),
                    'path': 'models/course.py',
                    'func': '_cron_generate_monthly_invoices',
                    'line': '0',
                })


class TuitionPlanLine(models.Model):
    _name = 'tuition.plan.line'
    _description = 'Tuition Plan Line'
    _order = 'start_date desc'

    subscription_id = fields.Many2one('tuition.subscription', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Plan Product', required=True)
    price = fields.Float(string='Monthly Price', required=True)
    start_date = fields.Date(string='Start Date', required=True)
    end_date = fields.Date(string='End Date')
    state = fields.Selection([
        ('active', 'Active'),
        ('scheduled', 'Scheduled'),
        ('expired', 'Expired'),
    ], string='Status', compute='_compute_state', store=True)
    notes = fields.Char(string='Notes')

    @api.depends('start_date', 'end_date')
    def _compute_state(self):
        today = fields.Date.today()
        for rec in self:
            if rec.start_date and rec.start_date > today:
                rec.state = 'scheduled'
            elif rec.end_date and rec.end_date < today:
                rec.state = 'expired'
            else:
                rec.state = 'active'

    @api.constrains('start_date')
    def _check_start_date(self):
        from odoo.exceptions import ValidationError
        for rec in self:
            if rec.start_date and rec.start_date.day != 1:
                raise ValidationError(
                    "Plan start date must be the 1st of a month. Got: %s" % rec.start_date)


class TuitionAdjustment(models.Model):
    _name = 'tuition.adjustment'
    _description = 'Tuition Manual Adjustment'
    _order = 'date desc'

    subscription_id = fields.Many2one('tuition.subscription', required=True, ondelete='cascade')
    student_id = fields.Many2one('student.profile', related='subscription_id.student_id',
                                 store=True)
    date = fields.Date(string='Date', required=True, default=fields.Date.today)
    description = fields.Char(string='Description', required=True)
    amount = fields.Float(string='Amount', required=True,
                          help='Positive = charge, Negative = credit/refund')
    adjustment_type = fields.Selection([
        ('charge', 'Extra Charge'),
        ('credit', 'Credit / Refund'),
        ('discount', 'Discount'),
        ('other', 'Other'),
    ], string='Type', default='other')
    applied_in_invoice = fields.Boolean(string='Applied', default=False)
    invoice_id = fields.Many2one('account.move', string='Invoice', readonly=True)


class AccountMoveTuitionExt(models.Model):
    _inherit = 'account.move'

    tuition_subscription_id = fields.Many2one(
        'tuition.subscription', string='Tuition Subscription',
        ondelete='set null', index=True)


class TuitionPlanChangeWizard(models.TransientModel):
    _name = 'tuition.plan.change.wizard'
    _description = 'Schedule Plan Change'

    subscription_id = fields.Many2one('tuition.subscription', required=True)
    product_id = fields.Many2one('product.product', string='New Plan Product', required=True)
    price = fields.Float(string='Monthly Price', required=True)
    start_date = fields.Date(string='Effective From (auto: 1st of next month)',
                             compute='_compute_start_date', store=True, readonly=False)
    notes = fields.Char(string='Notes')

    @api.depends('subscription_id')
    def _compute_start_date(self):
        today = fields.Date.today()
        first_next = today.replace(day=1) + relativedelta(months=1)
        for rec in self:
            rec.start_date = first_next

    @api.onchange('product_id')
    def _onchange_product(self):
        if self.product_id:
            self.price = self.product_id.lst_price or 0.0

    def action_confirm(self):
        self.ensure_one()
        sub = self.subscription_id
        if self.start_date.day != 1:
            raise UserError("Plan change must start on the 1st of a month.")
        today = fields.Date.today()
        end_prev = self.start_date - relativedelta(days=1)
        current = sub.plan_line_ids.filtered(
            lambda p: p.state == 'active' and (not p.end_date or p.end_date >= today))
        if current:
            current[0].write({'end_date': end_prev})
        scheduled = sub.plan_line_ids.filtered(lambda p: p.state == 'scheduled')
        if scheduled:
            scheduled.write({'end_date': end_prev})
        self.env['tuition.plan.line'].create({
            'subscription_id': sub.id,
            'product_id': self.product_id.id,
            'price': self.price,
            'start_date': self.start_date,
            'notes': self.notes or '',
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Plan Change Scheduled',
                'message': "Plan '%s' effective from %s." % (
                    self.product_id.name, self.start_date.strftime('%d %b %Y')),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }


class TuitionAdjustmentWizard(models.TransientModel):
    _name = 'tuition.adjustment.wizard'
    _description = 'Add Manual Adjustment'

    subscription_id = fields.Many2one('tuition.subscription', required=True)
    adjustment_type = fields.Selection([
        ('charge', 'Extra Charge'),
        ('credit', 'Credit / Refund'),
        ('discount', 'Discount'),
        ('other', 'Other'),
    ], string='Type', required=True, default='other')
    description = fields.Char(string='Description', required=True)
    amount = fields.Float(string='Amount', required=True,
                          help='Positive for charge, negative for credit/refund')
    date = fields.Date(string='Date', default=fields.Date.today, required=True)

    @api.onchange('adjustment_type')
    def _onchange_type(self):
        if self.adjustment_type == 'charge' and self.amount < 0:
            self.amount = abs(self.amount)
        elif self.adjustment_type in ('credit', 'discount') and self.amount > 0:
            self.amount = -abs(self.amount)

    def action_confirm(self):
        self.ensure_one()
        self.env['tuition.adjustment'].create({
            'subscription_id': self.subscription_id.id,
            'date': self.date,
            'description': self.description,
            'amount': self.amount,
            'adjustment_type': self.adjustment_type,
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Adjustment Added',
                'message': "Adjustment '%s' added." % self.description,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
# END BILLING SYSTEM