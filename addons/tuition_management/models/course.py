# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import timedelta, date
import pytz


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
    portal_user_id = fields.Many2one('res.users', string='Portal User', compute='_compute_portal_user', store=False)
    has_portal_access = fields.Boolean(string='Has Portal Access', compute='_compute_portal_user', store=False)

    def _compute_portal_user(self):
        for rec in self:
            if rec.partner_id:
                user = self.env['res.users'].sudo().search([('partner_id', '=', rec.partner_id.id)], limit=1)
                rec.portal_user_id = user.id if user else False
                rec.has_portal_access = bool(user)
            else:
                rec.portal_user_id = False
                rec.has_portal_access = False

    def action_invite_to_portal(self):
        """Open wizard to set portal credentials for this parent."""
        self.ensure_one()
        if not self.email:
            raise models.UserError("Email is required to create a portal login.")
        return {
            'type': 'ir.actions.act_window',
            'name': 'Set Portal Access',
            'res_model': 'portal.access.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_profile_model': 'parent.profile',
                'default_profile_id': self.id,
                'default_name': self.name,
                'default_email': self.email,
                'default_login': self.email,
            },
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
    portal_user_id = fields.Many2one('res.users', string='Portal User', compute='_compute_portal_user', store=False)
    has_portal_access = fields.Boolean(string='Has Portal Access', compute='_compute_portal_user', store=False)

    def _compute_portal_user(self):
        for rec in self:
            if rec.partner_id:
                user = self.env['res.users'].sudo().search([('partner_id', '=', rec.partner_id.id)], limit=1)
                rec.portal_user_id = user.id if user else False
                rec.has_portal_access = bool(user)
            else:
                rec.portal_user_id = False
                rec.has_portal_access = False

    def action_invite_to_portal(self):
        """Open wizard to set portal credentials for this student."""
        self.ensure_one()
        if not self.email:
            raise models.UserError("Email is required to create a portal login.")
        return {
            'type': 'ir.actions.act_window',
            'name': 'Set Portal Access',
            'res_model': 'portal.access.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_profile_model': 'student.profile',
                'default_profile_id': self.id,
                'default_name': self.name,
                'default_email': self.email,
                'default_login': self.email,
            },
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
    portal_user_id = fields.Many2one('res.users', string='Portal User', compute='_compute_portal_user', store=False)
    has_portal_access = fields.Boolean(string='Has Portal Access', compute='_compute_portal_user', store=False)

    def _compute_portal_user(self):
        for rec in self:
            if rec.partner_id:
                user = self.env['res.users'].sudo().search([('partner_id', '=', rec.partner_id.id)], limit=1)
                rec.portal_user_id = user.id if user else False
                rec.has_portal_access = bool(user)
            else:
                rec.portal_user_id = False
                rec.has_portal_access = False

    def action_invite_to_portal(self):
        """Open wizard to set portal credentials for this tutor."""
        self.ensure_one()
        if not self.email:
            raise models.UserError("Email is required to create a portal login.")
        return {
            'type': 'ir.actions.act_window',
            'name': 'Set Portal Access',
            'res_model': 'portal.access.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_profile_model': 'tutor.profile',
                'default_profile_id': self.id,
                'default_name': self.name,
                'default_email': self.email,
                'default_login': self.email,
            },
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

    def unlink(self):
        """Prevent deletion of lessons that have a status other than scheduled."""
        protected = self.filtered(lambda r: r.lesson_status and r.lesson_status != 'scheduled')
        if protected:
            raise models.UserError(
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

    def action_create_portal_user(self):
        """Create portal user with admin-set password."""
        self.ensure_one()
        if self.password != self.confirm_password:
            raise models.UserError("Passwords do not match.")
        if len(self.password) < 6:
            raise models.UserError("Password must be at least 6 characters.")

        # Get the profile record
        profile = self.env[self.profile_model].browse(self.profile_id)
        if not profile.exists():
            raise models.UserError("Profile record not found.")

        # Create or find partner
        if not profile.partner_id:
            partner = self.env['res.partner'].create({
                'name': profile.name,
                'email': profile.email,
                'phone': f"{getattr(profile, 'country_code', '') or ''}{getattr(profile, 'phone', '') or ''}",
            })
            profile.partner_id = partner.id
        else:
            partner = profile.partner_id
            if not partner.email:
                partner.email = profile.email

        # Check if user already exists
        existing_user = self.env['res.users'].sudo().search([
            '|',
            ('partner_id', '=', partner.id),
            ('login', '=', self.login),
        ], limit=1)

        group_portal = self.env.ref('base.group_portal')

        if existing_user:
            # Update existing user
            existing_user.sudo().write({
                'password': self.password,
                'active': True,
            })
            # Ensure portal group is assigned
            if group_portal not in existing_user.sudo().mapped('group_ids'):
                existing_user.sudo().write({'group_ids': [(4, group_portal.id)]})
        else:
            # Create new portal user
            self.env['res.users'].sudo().with_context(no_reset_password=True).create({
                'partner_id': partner.id,
                'login': self.login,
                'password': self.password,
                'group_ids': [(6, 0, [group_portal.id])],
                'active': True,
            })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Portal Access Activated',
                'message': f'Portal login created for {self.name}. Login: {self.login}',
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

