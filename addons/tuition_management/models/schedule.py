# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import timedelta
import pytz


class ClassSchedule(models.Model):
    _name = 'class.schedule'
    _description = 'Class Schedule'

    name = fields.Char(string='Schedule Name', compute='_compute_name', store=True)
    course_id = fields.Many2one('course.master', string='Course', required=True, ondelete='cascade')
    tutor_id = fields.Many2one('tutor.profile', string='Tutor', required=True)
    schedule_type = fields.Selection([('one_time', 'One Time'), ('recurring', 'Recurring')],
                                     string='Schedule Type', default='recurring')
    schedule_hour = fields.Integer(string='Hour', default=9)
    schedule_minute = fields.Integer(string='Minute', default=0)
    schedule_duration = fields.Integer(string='Duration (Minutes)', default=60)
    timezone = fields.Selection([
        ('US/Eastern', 'US/Eastern'), ('US/Central', 'US/Central'), ('US/Mountain', 'US/Mountain'),
        ('US/Pacific', 'US/Pacific'), ('Europe/London', 'Europe/London'), ('Europe/Paris', 'Europe/Paris'),
        ('Asia/Kolkata', 'Asia/Kolkata'), ('Asia/Tokyo', 'Asia/Tokyo'), ('Australia/Sydney', 'Australia/Sydney'), ('UTC', 'UTC'),
    ], string='Timezone', default='UTC')
    status = fields.Selection([
        ('draft', 'Draft'), ('active', 'Active'), ('completed', 'Completed'), ('cancelled', 'Cancelled'),
    ], string='Status', default='active')
    monday = fields.Boolean(string='Monday')
    tuesday = fields.Boolean(string='Tuesday')
    wednesday = fields.Boolean(string='Wednesday')
    thursday = fields.Boolean(string='Thursday')
    friday = fields.Boolean(string='Friday')
    saturday = fields.Boolean(string='Saturday')
    sunday = fields.Boolean(string='Sunday')
    start_date = fields.Date(string='Start Date', required=True)
    end_date = fields.Date(string='End Date', required=True)
    occurrence_ids = fields.One2many('class.schedule.occurrence', 'schedule_id', string='Occurrences')

    available_tutor_ids = fields.Many2many('tutor.profile', string='Available Tutors', compute='_compute_available_tutors', store=False)
    fallback_tutor_ids = fields.Many2many('tutor.profile', string='Subject/Grade Tutors', compute='_compute_available_tutors', store=False)
    no_tutor_available = fields.Boolean(string='No Tutor Available', compute='_compute_available_tutors', store=False)

    @api.onchange('available_tutor_ids', 'fallback_tutor_ids', 'no_tutor_available')
    def _onchange_tutor_list(self):
        tutor_ids = (self.fallback_tutor_ids if self.no_tutor_available else self.available_tutor_ids).ids
        return {'domain': {'tutor_id': [('id', 'in', tutor_ids)] if tutor_ids else []}}

    @api.depends('schedule_hour', 'schedule_minute', 'monday', 'tuesday', 'wednesday',
                 'thursday', 'friday', 'saturday', 'sunday', 'course_id')
    def _compute_available_tutors(self):
        day_fields = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        for rec in self:
            if not rec.course_id:
                rec.available_tutor_ids = rec.fallback_tutor_ids = self.env['tutor.profile']
                rec.no_tutor_available = False
                continue
            subject, grade = rec.course_id.subject_id, rec.course_id.grade_id
            selected_days = [d for d in day_fields if getattr(rec, d, False)]
            schedule_time = rec.schedule_hour + rec.schedule_minute / 60.0
            tutor_domain = []
            if subject: tutor_domain.append(('subject_ids', 'in', [subject.id]))
            if grade: tutor_domain.append(('grade_ids', 'in', [grade.id]))
            all_tutors = self.env['tutor.profile'].search(tutor_domain if tutor_domain else [])
            available = self.env['tutor.profile']
            if selected_days and schedule_time:
                for tutor in all_tutors:
                    if all(tutor.availability_ids.filtered(lambda a, d=day: a.day_of_week == d and a.start_time <= schedule_time < a.end_time) for day in selected_days):
                        available |= tutor
            if available:
                rec.available_tutor_ids = available
                rec.fallback_tutor_ids = self.env['tutor.profile']
                rec.no_tutor_available = False
            else:
                rec.available_tutor_ids = self.env['tutor.profile']
                rec.fallback_tutor_ids = all_tutors
                rec.no_tutor_available = bool(selected_days and schedule_time)

    @api.depends('course_id', 'tutor_id', 'schedule_type')
    def _compute_name(self):
        for rec in self:
            parts = [p for p in [rec.course_id.name or '', rec.tutor_id.name or '',
                                  dict(rec._fields['schedule_type'].selection).get(rec.schedule_type, '')] if p]
            rec.name = ' - '.join(parts) if parts else 'New Schedule'

    def _generate_occurrences(self):
        for record in self:
            record.occurrence_ids.filtered(lambda o: o.lesson_status == 'scheduled').sudo().unlink()
            if not record.start_date or not record.end_date:
                continue
            day_map = {'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3, 'friday': 4, 'saturday': 5, 'sunday': 6}
            selected_days = [day_map[d] for d in day_map if getattr(record, d)]
            if not selected_days and record.schedule_type == 'one_time':
                selected_days = [record.start_date.weekday()]
            tz = pytz.timezone(record.timezone or 'UTC')
            occurrences, current_date = [], record.start_date
            while current_date <= record.end_date:
                if current_date.weekday() in selected_days:
                    local_dt = tz.localize(fields.Datetime.to_datetime(current_date).replace(
                        hour=record.schedule_hour, minute=record.schedule_minute, second=0))
                    utc_start = local_dt.astimezone(pytz.utc).replace(tzinfo=None)
                    occurrences.append({
                        'schedule_id': record.id, 'course_id': record.course_id.id,
                        'tutor_id': record.tutor_id.id if record.tutor_id else False,
                        'name': f"{record.course_id.name or 'Class'} - {current_date.strftime('%a %b %d, %Y')}",
                        'start_datetime': utc_start, 'stop_datetime': utc_start + timedelta(minutes=record.schedule_duration or 60),
                    })
                current_date += timedelta(days=1)
            if occurrences:
                self.env['class.schedule.occurrence'].sudo().create(occurrences)

    def _get_selected_weekday_count(self):
        self.ensure_one()
        day_fields = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        return sum(1 for d in day_fields if getattr(self, d, False))

    def _get_course_active_enrollments(self):
        self.ensure_one()
        if not self.course_id:
            return self.env['course.enrollment']
        return self.env['course.enrollment'].sudo().search([
            ('course_id', '=', self.course_id.id),
            ('status', '=', 'active'),
        ])

    def _get_min_classes_per_week_allowed(self):
        """Return the strictest (minimum) classes_per_week among active subscriptions for enrolled students."""
        self.ensure_one()
        enrollments = self._get_course_active_enrollments()
        if not enrollments:
            return False

        subs = self.env['tuition.subscription'].sudo().search([
            ('enrollment_id', 'in', enrollments.ids),
            ('state', '=', 'active'),
        ])
        if not subs:
            return False

        # pick each subscription's current plan line and take the minimum allowance
        allowances = []
        for sub in subs:
            plan = sub.current_plan_id
            if plan and plan.classes_per_week:
                allowances.append(plan.classes_per_week)
        return min(allowances) if allowances else False

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            record._generate_occurrences()
        return records

    def write(self, vals):
        res = super().write(vals)
        trigger_fields = ['start_date', 'end_date', 'schedule_hour', 'schedule_minute', 'schedule_duration',
                          'timezone', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday', 'schedule_type', 'course_id']
        if any(f in vals for f in trigger_fields):
            for record in self:
                record._generate_occurrences()
        if 'tutor_id' in vals:
            now = fields.Datetime.now()
            for record in self:
                future_unmarked = record.occurrence_ids.filtered(lambda o: o.start_datetime and o.start_datetime >= now and not o.attendance_marked)
                if future_unmarked:
                    future_unmarked.sudo().write({'tutor_id': vals['tutor_id']})
        return res

    def unlink(self):
        now = fields.Datetime.now()
        for record in self:
            all_occurrences = self.env['class.schedule.occurrence'].with_context(force_delete_lesson=True).sudo().search([
                ('schedule_id', '=', record.id)
            ])

            future_occurrences = all_occurrences.filtered(
                lambda o: o.start_datetime and o.start_datetime >= now
            )
            if future_occurrences:
                future_occurrences.unlink()

            past_occurrences = all_occurrences - future_occurrences
            if past_occurrences:
                past_occurrences.with_context(force_delete_lesson=True).sudo().write({'schedule_id': False})

        return super(ClassSchedule, self).unlink()

    def action_delete_schedule(self):
        self.ensure_one()
        return self.unlink()

    @api.constrains('schedule_type', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')
    def _check_weekday_selected(self):
        day_fields = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        for rec in self:
            if rec.schedule_type == 'recurring':
                if not any(getattr(rec, d, False) for d in day_fields):
                    raise UserError('Please select at least one day of the week for a recurring schedule.')

    @api.constrains('start_date', 'end_date')
    def _check_date_range(self):
        for rec in self:
            if rec.start_date and rec.end_date and rec.end_date < rec.start_date:
                raise UserError('End Date must be on or after Start Date.')

    @api.onchange('start_date')
    def _onchange_start_date_default_end(self):
        for rec in self:
            if not rec.start_date:
                continue
            # default end date to 1 year from start date if end_date is empty or invalid
            suggested = rec.start_date.replace(year=rec.start_date.year + 1)
            if not rec.end_date or rec.end_date < rec.start_date:
                rec.end_date = suggested


class ClassScheduleOccurrence(models.Model):
    _name = 'class.schedule.occurrence'
    _description = 'Class Schedule Occurrence'
    _order = 'start_datetime asc'

    name = fields.Char(string='Name', required=True)
    schedule_id = fields.Many2one('class.schedule', string='Schedule', ondelete='set null')
    start_datetime = fields.Datetime(string='Start', required=True)
    stop_datetime = fields.Datetime(string='Stop', required=True)
    course_id = fields.Many2one('course.master', string='Course', store=True)
    tutor_id = fields.Many2one('tutor.profile', string='Tutor', store=True)
    attendance_ids = fields.One2many('attendance.record', 'class_schedule_occurrence_id', string='Attendance')
    attendance_marked = fields.Boolean(string='Attendance Marked', compute='_compute_attendance_marked', store=True)
    lesson_status = fields.Selection([
        ('scheduled', 'Scheduled'), ('completed', 'Completed'), ('cancelled', 'Cancelled'),
        ('no_show', 'No Show'), ('rescheduled', 'Rescheduled'),
    ], string='Lesson Status', default='scheduled')
    cancellation_reason = fields.Selection([
        ('platform_issue', 'Platform Issue'), ('tutor_issue', 'Tutor Issue'),
        ('admin_issue', 'Admin Issue'), ('student_cancelled', 'Student Cancelled'),
    ], string='Cancellation Reason')
    cancellation_note = fields.Text(string='Cancellation Note')
    is_rescheduled = fields.Boolean(string='Rescheduled', default=False)
    rescheduled_from_id = fields.Many2one('class.schedule.occurrence', string='Rescheduled From')

    @api.depends('attendance_ids')
    def _compute_attendance_marked(self):
        for rec in self:
            rec.attendance_marked = bool(rec.attendance_ids)

    def write(self, vals):
        if vals.get('lesson_status') == 'cancelled':
            if not self.env.user.has_group('base.group_system') and not self.env.user.has_group('base.group_erp_manager'):
                raise UserError("Only administrators or managers can cancel a lesson.")
        reschedule_fields = {'tutor_id'}
        if reschedule_fields & set(vals.keys()) and 'lesson_status' not in vals:
            for rec in self:
                if rec.lesson_status == 'scheduled':
                    vals = dict(vals, lesson_status='rescheduled')
                    break
        return super().write(vals)

    def unlink(self):
        if self.env.context.get('force_delete_lesson'):
            return super(ClassScheduleOccurrence, self).unlink()
        if self.filtered(lambda r: r.lesson_status and r.lesson_status != 'scheduled'):
            raise UserError("Cannot delete lessons that have been completed, cancelled, or marked as no-show.")
        return super(ClassScheduleOccurrence, self).unlink()

    def action_mark_attendance(self):
        self.ensure_one()
        enrollments = self.env['course.enrollment'].search([('course_id', '=', self.course_id.id), ('status', '=', 'active')])
        wizard = self.env['mark.attendance.wizard'].create({'occurrence_id': self.id})
        existing_attendance = {att.student_id.id: att for att in self.attendance_ids}
        lines = [(0, 0, {'wizard_id': wizard.id, 'student_id': sid,
                         'status': existing_attendance[sid].status if sid in existing_attendance else 'present',
                         'billable': existing_attendance[sid].billable if sid in existing_attendance else True,
                         'remarks': existing_attendance[sid].remarks if sid in existing_attendance else ''})
                 for sid in enrollments.mapped('student_id').ids]
        if lines: wizard.write({'line_ids': lines})
        return {'type': 'ir.actions.act_window', 'name': f'Mark Attendance - {self.name}',
                'res_model': 'mark.attendance.wizard', 'view_mode': 'form', 'res_id': wizard.id, 'target': 'new'}

    def action_cancel_lesson(self):
        self.ensure_one()
        wizard = self.env['cancel.lesson.wizard'].create({'occurrence_id': self.id})
        return {'type': 'ir.actions.act_window', 'name': 'Cancel Lesson',
                'res_model': 'cancel.lesson.wizard', 'view_mode': 'form', 'res_id': wizard.id, 'target': 'new'}


class ScheduleDeleteWizard(models.TransientModel):
    _name = 'schedule.delete.wizard'
    _description = 'Schedule Delete Confirmation Wizard'

    schedule_id = fields.Many2one('class.schedule', string='Schedule', required=True)
    message = fields.Text(string='Warning Message')
    line_ids = fields.One2many('schedule.delete.wizard.line', 'wizard_id', string='Unmarked Past Lessons')

    def action_confirm_delete(self):
        self.ensure_one()
        if self.schedule_id.exists():
            self.schedule_id.sudo().with_context(force_delete=True).unlink()
        return {'type': 'ir.actions.act_window_close'}

    def action_cancel(self):
        return {'type': 'ir.actions.act_window_close'}


class ScheduleDeleteWizardLine(models.TransientModel):
    _name = 'schedule.delete.wizard.line'
    _description = 'Schedule Delete Wizard Line'

    wizard_id = fields.Many2one('schedule.delete.wizard', string='Wizard', ondelete='cascade')
    occurrence_id = fields.Many2one('class.schedule.occurrence', string='Lesson')
    lesson_name = fields.Char(string='Lesson')
    lesson_date = fields.Datetime(string='Date')
    tutor_name = fields.Char(string='Tutor')


class CancelLessonWizard(models.TransientModel):
    _name = 'cancel.lesson.wizard'
    _description = 'Cancel Lesson Wizard'

    occurrence_id = fields.Many2one('class.schedule.occurrence', string='Lesson', required=True)
    reason = fields.Selection([
        ('platform_issue', 'Platform Issue'),
        ('tutor_issue', 'Tutor Issue'),
        ('admin_issue', 'Admin Issue'),
        ('student_cancelled', 'Student Cancelled'),
    ], string='Cancellation Reason')
    note = fields.Text(string='Note')
    reschedule = fields.Boolean(string='Reschedule this lesson?', default=False)
    new_date = fields.Datetime(string='New Date & Time')
    new_tutor_id = fields.Many2one('tutor.profile', string='New Tutor')

    def action_confirm_cancel(self):
        self.ensure_one()
        occ = self.occurrence_id

        # Cancel the current lesson
        occ.sudo().write({
            'lesson_status': 'cancelled',
            'cancellation_reason': self.reason,
            'cancellation_note': self.note,
        })

        # Mark all attendance as cancelled, create if not existing
        enrollments = self.env['course.enrollment'].search([
            ('course_id', '=', occ.course_id.id),
            ('status', '=', 'active'),
        ])
        student_ids = enrollments.mapped('student_id')
        existing_att = {att.student_id.id: att for att in occ.attendance_ids}
        for student in student_ids:
            if student.id in existing_att:
                existing_att[student.id].sudo().write({'status': 'cancelled'})
            else:
                self.env['attendance.record'].sudo().create({
                    'class_schedule_occurrence_id': occ.id,
                    'student_id': student.id,
                    'attendance_date': occ.start_datetime.date() if occ.start_datetime else fields.Date.today(),
                    'status': 'cancelled',
                    'billable': False,
                })

        # Reschedule if requested
        if self.reschedule and self.new_date:
            duration = (occ.stop_datetime - occ.start_datetime) if occ.stop_datetime and occ.start_datetime else timedelta(minutes=60)
            new_occ = self.env['class.schedule.occurrence'].sudo().create({
                'name': '%s (Rescheduled)' % (occ.name or 'Lesson'),
                'schedule_id': occ.schedule_id.id if occ.schedule_id else False,
                'start_datetime': self.new_date,
                'stop_datetime': self.new_date + duration,
                'course_id': occ.course_id.id,
                'tutor_id': self.new_tutor_id.id if self.new_tutor_id else occ.tutor_id.id,
                'lesson_status': 'scheduled',
                'is_rescheduled': True,
                'rescheduled_from_id': occ.id,
            })

        return {'type': 'ir.actions.act_window_close'}
