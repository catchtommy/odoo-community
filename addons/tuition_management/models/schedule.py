# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, time, timedelta
import pytz


class ClassSchedule(models.Model):
    _name = 'class.schedule'
    _description = 'Class Schedule'

    course_id = fields.Many2one('course.master', string='Course', required=True, ondelete='cascade')
    tutor_id = fields.Many2one('tutor.profile', string='Tutor', required=True)
    schedule_type = fields.Selection([('one_time', 'One Time'), ('recurring', 'Recurring')],
                                     string='Schedule Type', default='recurring')
    schedule_hour = fields.Integer(string='Hour', default=9)
    schedule_minute = fields.Integer(string='Minute', default=0)
    schedule_hour_sel = fields.Selection(
        selection=[(str(h), '%02d' % h) for h in range(24)],
        string='Hour', compute='_compute_time_sel', inverse='_set_hour_sel', store=False)
    schedule_minute_sel = fields.Selection(
        selection=[(str(m), '%02d' % m) for m in range(60)],
        string='Minute', compute='_compute_time_sel', inverse='_set_minute_sel', store=False)
    schedule_duration = fields.Integer(string='Duration (Minutes)', default=60)
    timezone = fields.Selection([
        ('US/Eastern', 'US/Eastern'), ('US/Central', 'US/Central'), ('US/Mountain', 'US/Mountain'),
        ('US/Pacific', 'US/Pacific'), ('Europe/London', 'Europe/London'), ('Europe/Paris', 'Europe/Paris'),
        ('Asia/Kolkata', 'Asia/Kolkata'), ('Asia/Tokyo', 'Asia/Tokyo'), ('Australia/Sydney', 'Australia/Sydney'), ('UTC', 'UTC'),
    ], string='Timezone', default=lambda self: self.env.user.tz or 'UTC')
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
    start_date = fields.Date(string='Start Date', default=fields.Date.today)
    end_date = fields.Date(string='End Date')
    schedule_date = fields.Date(string='Date')  # used for one_time schedules only
    is_reschedule = fields.Boolean(string='Is a Reschedule?', default=False)
    rescheduled_from_id = fields.Many2one(
        'class.schedule.occurrence', string='Replaces Cancelled Class',
        domain=[('lesson_status', '=', 'cancelled')],
        help='Link to the cancelled occurrence that this one-time class replaces')
    occurrence_ids = fields.One2many('class.schedule.occurrence', 'schedule_id', string='Occurrences')

    # NOTE: virtual_provider_default has been moved to course.master.
    # This field is kept only for data migration. Do NOT set on new schedules.
    virtual_provider_default = fields.Selection([
        ('zoom', 'Zoom'),
        ('bbb', 'BigBlueButton'),
        ('google_meet', 'Google Meet'),
    ], string='[Deprecated] Schedule Provider')

    available_tutor_ids = fields.Many2many('tutor.profile', string='Available Tutors', compute='_compute_available_tutors', store=False)
    fallback_tutor_ids = fields.Many2many('tutor.profile', string='Subject/Grade Tutors', compute='_compute_available_tutors', store=False)
    all_eligible_tutor_ids = fields.Many2many('tutor.profile', string='Course-Eligible Tutors', compute='_compute_available_tutors', store=False)
    no_tutor_available = fields.Boolean(string='No Tutor Available', compute='_compute_available_tutors', store=False)

    @api.depends('schedule_hour', 'schedule_minute')
    def _compute_time_sel(self):
        for rec in self:
            rec.schedule_hour_sel = str(rec.schedule_hour)
            rec.schedule_minute_sel = str(rec.schedule_minute)

    def _set_hour_sel(self):
        for rec in self:
            rec.schedule_hour = int(rec.schedule_hour_sel or 0)

    def _set_minute_sel(self):
        for rec in self:
            rec.schedule_minute = int(rec.schedule_minute_sel or 0)

    @api.onchange('course_id', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday',
                  'saturday', 'sunday', 'schedule_hour', 'schedule_minute',
                  'start_date', 'schedule_date', 'schedule_type')
    def _onchange_schedule_for_tutor_domain(self):
        """Restrict the tutor dropdown to tutors eligible for this course (category + subject + grade)."""
        eligible_ids = self.all_eligible_tutor_ids.ids
        return {
            'domain': {
                'tutor_id': [('id', 'in', eligible_ids)] if eligible_ids else [],
            }
        }

    @api.onchange('tutor_id', 'schedule_date', 'schedule_hour', 'schedule_minute',
                  'schedule_duration', 'monday', 'tuesday', 'wednesday', 'thursday',
                  'friday', 'saturday', 'sunday', 'start_date', 'end_date',
                  'timezone', 'schedule_type')
    def _onchange_check_overbooking(self):
        """Warn if the selected tutor already has a lesson overlapping the proposed schedule."""
        if not self.tutor_id:
            return
        conflicts = self._find_tutor_schedule_conflicts()
        if not conflicts:
            return
        lines = []
        for occ in conflicts[:5]:
            start_str = occ.start_datetime.strftime('%a %d %b %Y %H:%M') if occ.start_datetime else '?'
            lines.append('• %s  (%s)  —  Course: %s' % (
                occ.name or '?', start_str, occ.course_id.name or '—'))
        if len(conflicts) > 5:
            lines.append('… and %d more conflict(s).' % (len(conflicts) - 5))
        return {
            'warning': {
                'title': 'Tutor Overbooking — %s' % self.tutor_id.name,
                'message': (
                    'The following existing lesson(s) overlap with this schedule:\n\n%s\n\n'
                    'Please choose a different tutor or adjust the schedule time.'
                ) % '\n'.join(lines),
            }
        }

    def _find_tutor_schedule_conflicts(self):
        """Return existing non-cancelled occurrences that overlap the proposed time slots."""
        if not self.tutor_id:
            return self.env['class.schedule.occurrence']
        tz = pytz.timezone(self.timezone or 'UTC')
        duration = self.schedule_duration or 60
        day_fields = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        slots = []

        if self.schedule_type == 'one_time':
            if not self.schedule_date:
                return self.env['class.schedule.occurrence']
            local_dt = tz.localize(datetime.combine(
                self.schedule_date, time(self.schedule_hour, self.schedule_minute)))
            utc_start = local_dt.astimezone(pytz.utc).replace(tzinfo=None)
            slots.append((utc_start, utc_start + timedelta(minutes=duration)))
        else:
            if not self.start_date or not self.end_date:
                return self.env['class.schedule.occurrence']
            day_map = {d: i for i, d in enumerate(day_fields)}
            selected = [day_map[d] for d in day_fields if getattr(self, d, False)]
            if not selected:
                return self.env['class.schedule.occurrence']
            today = fields.Date.today()
            check_end = min(self.end_date, today + timedelta(days=90))
            current = max(self.start_date, today)
            while current <= check_end:
                if current.weekday() in selected:
                    local_dt = tz.localize(datetime.combine(
                        current, time(self.schedule_hour, self.schedule_minute)))
                    utc_start = local_dt.astimezone(pytz.utc).replace(tzinfo=None)
                    slots.append((utc_start, utc_start + timedelta(minutes=duration)))
                current += timedelta(days=1)

        if not slots:
            return self.env['class.schedule.occurrence']

        min_start = min(s[0] for s in slots)
        max_end = max(s[1] for s in slots)
        domain = [
            ('tutor_id', '=', self.tutor_id.id),
            ('lesson_status', 'not in', ['cancelled']),
            ('start_datetime', '<', max_end),
            ('stop_datetime', '>', min_start),
        ]
        if self.id:
            domain.append(('schedule_id', '!=', self.id))
        candidates = self.env['class.schedule.occurrence'].search(domain)
        conflicts = self.env['class.schedule.occurrence']
        for occ in candidates:
            if not occ.start_datetime or not occ.stop_datetime:
                continue
            for s_start, s_end in slots:
                if occ.start_datetime < s_end and occ.stop_datetime > s_start:
                    conflicts |= occ
                    break
        return conflicts

    @api.constrains(
        'tutor_id', 'schedule_hour', 'schedule_minute', 'schedule_duration',
        'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
        'start_date', 'end_date', 'schedule_date', 'schedule_type', 'timezone', 'status',
    )
    def _check_no_tutor_overbooking(self):
        for rec in self:
            if not rec.tutor_id or rec.status == 'cancelled':
                continue
            conflicts = rec._find_tutor_schedule_conflicts()
            if conflicts:
                lines = []
                for c in conflicts[:5]:
                    dt_str = (c.start_datetime.strftime('%a %d %b %Y %H:%M UTC')
                              if c.start_datetime else '?')
                    lines.append('  • %s  (%s)  —  %s' % (c.name or '?', dt_str, c.course_id.name or '—'))
                raise ValidationError(
                    'Cannot save: tutor "%s" already has a lesson at the same time:\n\n%s\n\n'
                    'Please choose a different tutor or adjust the schedule time.'
                    % (rec.tutor_id.name, '\n'.join(lines))
                )
    def _onchange_tutor_id_warn(self):
        """Inform the user when the selected tutor is different from existing course tutors."""
        if not self.tutor_id or not self.course_id:
            return
        course = self.course_id
        if not course.tutor_id:
            # No tutor yet — fine, this will become the primary
            return
        if self.tutor_id not in course.tutor_ids:
            existing = ', '.join(t.name for t in course.tutor_ids)
            return {
                'warning': {
                    'title': 'Multiple Tutors',
                    'message': (
                        'This course is already managed by: %s.\n\n'
                        'Adding a schedule with %s will give them portal access to this course '
                        'alongside the existing tutor(s).'
                    ) % (existing, self.tutor_id.name),
                }
            }

    @api.depends('schedule_hour', 'schedule_minute', 'monday', 'tuesday', 'wednesday',
                 'thursday', 'friday', 'saturday', 'sunday', 'course_id',
                 'start_date', 'schedule_type', 'schedule_date')
    def _compute_available_tutors(self):
        day_fields = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        for rec in self:
            if not rec.course_id:
                rec.available_tutor_ids = rec.fallback_tutor_ids = rec.all_eligible_tutor_ids = self.env['tutor.profile']
                rec.no_tutor_available = False
                continue
            category = rec.course_id.category_id
            subject = rec.course_id.subject_id
            grade = rec.course_id.grade_id
            selected_days = [d for d in day_fields if getattr(rec, d, False)]
            schedule_time = rec.schedule_hour + rec.schedule_minute / 60.0
            target_date = (
                rec.schedule_date if rec.schedule_type == 'one_time' and rec.schedule_date
                else rec.start_date or fields.Date.today()
            )
            # Build domain filtering by course category + subject + grade
            tutor_domain = []
            if category and subject:
                tutor_domain = [
                    ('tutor_subject_rate_ids.category_id', '=', category.id),
                    ('tutor_subject_rate_ids.subject_id', '=', subject.id),
                    ('tutor_subject_rate_ids.active_flag', '=', True),
                    '|', ('tutor_subject_rate_ids.effective_from', '=', False),
                         ('tutor_subject_rate_ids.effective_from', '<=', target_date),
                    '|', ('tutor_subject_rate_ids.effective_to', '=', False),
                         ('tutor_subject_rate_ids.effective_to', '>=', target_date),
                ]
            elif subject:
                tutor_domain = [('subject_ids', 'in', [subject.id])]
            if grade:
                tutor_domain.append(('grade_ids', 'in', [grade.id]))
            all_tutors = self.env['tutor.profile'].search(tutor_domain if tutor_domain else [])
            available = self.env['tutor.profile']
            if selected_days:
                for tutor in all_tutors:
                    if all(tutor.availability_ids.filtered(
                        lambda a, d=day: a.day_of_week == d and a.start_time <= schedule_time < a.end_time
                    ) for day in selected_days):
                        available |= tutor
            rec.all_eligible_tutor_ids = all_tutors
            if available:
                rec.available_tutor_ids = available
                rec.fallback_tutor_ids = self.env['tutor.profile']
                rec.no_tutor_available = False
            else:
                rec.available_tutor_ids = self.env['tutor.profile']
                rec.fallback_tutor_ids = all_tutors
                rec.no_tutor_available = bool(selected_days)

    @api.depends('course_id', 'tutor_id', 'schedule_type')
    def _compute_name(self):
        for rec in self:
            parts = [p for p in [rec.course_id.name or '', rec.tutor_id.name or '',
                                  dict(rec._fields['schedule_type'].selection).get(rec.schedule_type, '')] if p]
            rec.name = ' - '.join(parts) if parts else 'New Schedule'

    def _generate_occurrences(self):
        today = fields.Date.today()
        now = fields.Datetime.now()
        for record in self:
            # Only remove future unstarted scheduled occurrences; never touch past ones
            record.occurrence_ids.filtered(
                lambda o: o.lesson_status == 'scheduled' and o.start_datetime and o.start_datetime >= now
            ).sudo().unlink()
            if record.schedule_type == 'one_time':
                if not record.schedule_date:
                    continue
                effective_date = record.schedule_date
                tz = pytz.timezone(record.timezone or 'UTC')
                local_dt = tz.localize(fields.Datetime.to_datetime(effective_date).replace(
                    hour=record.schedule_hour, minute=record.schedule_minute, second=0))
                utc_start = local_dt.astimezone(pytz.utc).replace(tzinfo=None)
                occ_name = f"{record.course_id.name or 'Class'} - {effective_date.strftime('%a %b %d, %Y')}"
                if record.is_reschedule and record.rescheduled_from_id:
                    occ_name += ' (Rescheduled)'
                self.env['class.schedule.occurrence'].sudo().create([{
                    'schedule_id': record.id, 'course_id': record.course_id.id,
                    'tutor_id': record.tutor_id.id if record.tutor_id else False,
                    'name': occ_name,
                    'start_datetime': utc_start,
                    'stop_datetime': utc_start + timedelta(minutes=record.schedule_duration or 60),
                    'is_rescheduled': record.is_reschedule and bool(record.rescheduled_from_id),
                    'rescheduled_from_id': record.rescheduled_from_id.id if record.is_reschedule and record.rescheduled_from_id else False,
                }])
                continue
            if not record.start_date or not record.end_date:
                continue
            day_map = {'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3, 'friday': 4, 'saturday': 5, 'sunday': 6}
            selected_days = [day_map[d] for d in day_map if getattr(record, d)]
            tz = pytz.timezone(record.timezone or 'UTC')
            # For existing records, generate only from today onwards to avoid recreating past occurrences
            generate_from = max(record.start_date, today)
            occurrences, current_date = [], generate_from
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
                        # Provider is NOT stored per-occurrence; resolved dynamically from course at runtime
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
            record._sync_tutor_to_course()
        return records

    def _sync_tutor_to_course(self):
        """Auto-set course tutor from schedule if not set; warn if adding a new tutor to an already-managed course."""
        self.ensure_one()
        course = self.course_id
        if not course or not self.tutor_id:
            return
        if not course.tutor_id:
            # No primary tutor yet — auto-assign from this schedule
            course.sudo().write({
                'tutor_id': self.tutor_id.id,
                'tutor_ids': [(4, self.tutor_id.id)],
            })
            course.message_post(
                body='Primary tutor auto-set to <b>%s</b> from schedule.' % self.tutor_id.name,
                subtype_xmlid='mail.mt_note',
            )
        elif self.tutor_id not in course.tutor_ids:
            # New tutor not yet on course — add them and log a notice
            course.sudo().write({'tutor_ids': [(4, self.tutor_id.id)]})
            course.message_post(
                body=(
                    '&#8505; A new schedule was added with tutor <b>%s</b>. '
                    'This tutor has been added to the course and will have portal access alongside '
                    'the existing tutor(s): <b>%s</b>.'
                ) % (
                    self.tutor_id.name,
                    ', '.join(t.name for t in course.tutor_ids - self.tutor_id),
                ),
                subtype_xmlid='mail.mt_note',
            )

    def write(self, vals):
        trigger_fields = ['start_date', 'end_date', 'schedule_date', 'schedule_hour', 'schedule_minute', 'schedule_duration',
                          'timezone', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
                          'schedule_type', 'course_id', 'is_reschedule', 'rescheduled_from_id']
        # When editing a recurring schedule, advance start_date to today so only
        # future occurrences are (re)generated; past occurrences are left untouched.
        if any(f in vals for f in trigger_fields) and 'start_date' not in vals:
            today = fields.Date.today()
            if any(r.schedule_type == 'recurring' and r.start_date and r.start_date < today for r in self):
                vals = dict(vals, start_date=today)
        res = super().write(vals)
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

    @api.constrains('schedule_type', 'start_date', 'end_date', 'schedule_date')
    def _check_required_dates(self):
        for rec in self:
            if rec.schedule_type == 'one_time' and not rec.schedule_date:
                raise UserError('Please set a Date for a one-time schedule.')
            if rec.schedule_type == 'recurring' and (not rec.start_date or not rec.end_date):
                raise UserError('Please set Start Date and End Date for a recurring schedule.')

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
    start_datetime = fields.Datetime(string='Start (UTC)', required=True)
    stop_datetime = fields.Datetime(string='Stop (UTC)', required=True)
    start_local_display = fields.Char(
        string='Local Time',
        compute='_compute_start_local_display',
        store=False,
    )
    course_id = fields.Many2one('course.master', string='Course', store=True)
    tutor_id = fields.Many2one('tutor.profile', string='Tutor', store=True)
    attendance_ids = fields.One2many('attendance.record', 'class_schedule_occurrence_id', string='Attendance')
    attendance_marked = fields.Boolean(string='Attendance Marked', compute='_compute_attendance_marked', store=True)
    lesson_status = fields.Selection([
        ('scheduled', 'Scheduled'), ('completed', 'Completed'), ('cancelled', 'Cancelled'),
        ('under_review', 'Under Review'),
    ], string='Lesson Status', default='scheduled')
    cancellation_reason = fields.Selection([
        ('platform_issue', 'Platform Issue'), ('tutor_issue', 'Tutor Issue'),
        ('admin_issue', 'Admin Issue'), ('student_cancelled', 'Student Cancelled'),
    ], string='Cancellation Reason')
    cancellation_note = fields.Text(string='Cancellation Note')
    is_rescheduled = fields.Boolean(string='Rescheduled', default=False)
    rescheduled_from_id = fields.Many2one('class.schedule.occurrence', string='Rescheduled From')
    is_demo = fields.Boolean(string='Is Demo Session', default=False)

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
    # Provider is NOT stored on the occurrence. It is always resolved dynamically from
    # the parent course so that changing the course provider affects all future sessions.
    virtual_provider = fields.Selection([
        ('zoom', 'Zoom'),
        ('bbb', 'BigBlueButton'),
        ('google_meet', 'Google Meet'),
    ], string='Classroom Provider', compute='_compute_virtual_provider', store=False)
    virtual_meeting_id = fields.Many2one(
        'virtual.classroom.meeting',
        string='Virtual Meeting',
        readonly=True,
        copy=False,
    )
    virtual_meeting_state = fields.Selection(
        related='virtual_meeting_id.state',
        string='Meeting State',
        readonly=True,
    )

    @api.depends('attendance_ids')
    def _compute_attendance_marked(self):
        for rec in self:
            rec.attendance_marked = bool(rec.attendance_ids)

    @api.depends('start_datetime', 'schedule_id', 'schedule_id.timezone')
    def _compute_start_local_display(self):
        for rec in self:
            if not rec.start_datetime:
                rec.start_local_display = ''
                continue
            tz_name = (rec.schedule_id.timezone if rec.schedule_id else None) or 'UTC'
            try:
                tz = pytz.timezone(tz_name)
            except pytz.UnknownTimeZoneError:
                tz = pytz.utc
            local_dt = rec.start_datetime.replace(tzinfo=pytz.utc).astimezone(tz)
            rec.start_local_display = local_dt.strftime('%d %b %Y, %H:%M') + ' (' + tz_name + ')'

    @api.depends('course_id', 'course_id.virtual_provider_default')
    def _compute_virtual_provider(self):
        """Always resolve provider from course. Sessions never own the provider."""
        for rec in self:
            rec.virtual_provider = rec.course_id.virtual_provider_default or 'bbb'

    def write(self, vals):
        if vals.get('lesson_status') == 'cancelled':
            if not self.env.user.has_group('base.group_system') and not self.env.user.has_group('base.group_erp_manager'):
                raise UserError("Only administrators or managers can cancel a lesson.")
        reschedule_fields = {'tutor_id'}
        if reschedule_fields & set(vals.keys()) and 'lesson_status' not in vals:
            for rec in self:
                if rec.lesson_status == 'scheduled':
                    vals = dict(vals, is_rescheduled=True)
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
        if self.start_datetime and self.start_datetime > fields.Datetime.now():
            raise UserError("Attendance cannot be marked for a future class. Please wait until the class has started.")
        # Active enrollments always shown
        active_enrollments = self.env['course.enrollment'].search([
            ('course_id', '=', self.course_id.id), ('status', '=', 'active')
        ])
        active_student_ids = set(active_enrollments.mapped('student_id').ids)

        # Cancelled students only shown if attendance already recorded for this occurrence
        existing_attendance = {att.student_id.id: att for att in self.attendance_ids}
        cancelled_student_ids = set(existing_attendance.keys()) - active_student_ids

        all_student_ids = list(active_student_ids | cancelled_student_ids)

        wizard = self.env['mark.attendance.wizard'].create({'occurrence_id': self.id})
        valid_statuses = {'present', 'absent'}
        lines = [(0, 0, {'wizard_id': wizard.id, 'student_id': sid,
                         'status': (existing_attendance[sid].status if sid in existing_attendance and existing_attendance[sid].status in valid_statuses else 'present'),
                         'remarks': existing_attendance[sid].remarks if sid in existing_attendance else ''})
                 for sid in all_student_ids]
        if lines: wizard.write({'line_ids': lines})
        return {'type': 'ir.actions.act_window', 'name': f'Mark Attendance - {self.name}',
                'res_model': 'mark.attendance.wizard', 'view_mode': 'form', 'res_id': wizard.id, 'target': 'new'}

    def action_cancel_lesson(self):
        self.ensure_one()
        wizard = self.env['cancel.lesson.wizard'].create({'occurrence_id': self.id})
        return {'type': 'ir.actions.act_window', 'name': 'Cancel Lesson',
                'res_model': 'cancel.lesson.wizard', 'view_mode': 'form', 'res_id': wizard.id, 'target': 'new'}

    def action_start_virtual_class(self):
        self.ensure_one()
        # Provider is resolved from course, not stored on occurrence
        provider = self.course_id.virtual_provider_default or 'bbb'
        service = self.env['virtual.classroom.service']
        meeting = service.start_meeting(self, provider)
        url = service.get_tutor_start_url(meeting, self.tutor_id)
        if not url:
            raise UserError('Virtual classroom was created, but no launch URL was returned.')
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }

    def action_open_virtual_classroom_wizard(self):
        self.ensure_one()
        # Provider comes from course only — no per-occurrence override
        provider = self.course_id.virtual_provider_default or 'bbb'
        return {
            'type': 'ir.actions.act_window',
            'name': 'Start Virtual Class',
            'res_model': 'virtual.classroom.start.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_occurrence_id': self.id,
                'default_provider': provider,
            },
        }

    def action_reset_virtual_meeting(self):
        for occurrence in self:
            if occurrence.virtual_meeting_id:
                occurrence.virtual_meeting_id.action_mark_cancelled()
            occurrence.write({'virtual_meeting_id': False})
        return True


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
                # Provider is resolved dynamically from course at runtime — not stored
            })

        return {'type': 'ir.actions.act_window_close'}
