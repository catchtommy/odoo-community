# -*- coding: utf-8 -*-
import base64
import io

import xlsxwriter
from markupsafe import Markup
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, time, timedelta
import pytz
from .tz_utils import get_tz_selection, DEFAULT_TIMEZONE, COMMON_TIMEZONES
from .user_permission import user_has_permission


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
    timezone = fields.Selection(
        selection=get_tz_selection,
        string='Timezone',
        default=lambda self: self.env.user.tz or DEFAULT_TIMEZONE,
    )
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
    one_time_reason = fields.Text(string='Reason for One-Time Session')  # used for one_time schedules only
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
    partial_tutor_ids = fields.Many2many('tutor.profile', string='Partially Available Tutors', compute='_compute_available_tutors', store=False)
    assignable_tutor_ids = fields.Many2many('tutor.profile', string='Assignable Tutors', compute='_compute_available_tutors', store=False)
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

    def _get_availability_values(self):
        """Trigger availability compute and return values as a plain dict.
        Accessing computed fields here caches their values so that the ORM's
        onchange snapshot-diff mechanism picks them up for snapshot1."""
        r = self._calc_availability()
        # Explicitly set the field values on self so the ORM cache is populated
        # BEFORE snapshot1 is taken.  We use _compute_available_tutors() here
        # which sets them via the normal compute path (protected context).
        self._compute_available_tutors()
        return r

    def _availability_onchange_values(self, availability):
        """Return explicit x2many values so the web client refreshes reliably."""
        return {
            'all_eligible_tutor_ids': [(6, 0, availability['all_eligible'].ids)],
            'available_tutor_ids': [(6, 0, availability['available'].ids)],
            'partial_tutor_ids': [(6, 0, availability['partial'].ids)],
            'fallback_tutor_ids': [(6, 0, availability['fallback'].ids)],
            'assignable_tutor_ids': [(6, 0, availability['assignable'].ids)],
            'no_tutor_available': availability['no_tutor_available'],
        }

    @staticmethod
    def _float_to_time_parts(time_float):
        hours = int(time_float or 0)
        minutes = int(round(((time_float or 0) - hours) * 60))
        hours += minutes // 60
        minutes = minutes % 60
        return hours, minutes

    @api.onchange('course_id', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday',
                  'saturday', 'sunday',
                  'schedule_hour_sel', 'schedule_minute_sel',
                  'schedule_duration', 'start_date', 'end_date', 'schedule_date', 'schedule_type', 'timezone')
    def _onchange_schedule_for_tutor_domain(self):
        """Recompute availability and restrict tutor dropdown.

        The web client applies returned values, then diffs the onchange
        snapshot. Returning the availability x2many values explicitly keeps the
        tags, warning panel, and tutor domain in sync on every edit.
        """
        # Sync hour/minute selection widgets → integer fields so the availability
        # compute sees up-to-date values when schedule_hour_sel / schedule_minute_sel
        # change.  Only sync when the selection widget is the source of truth
        # (i.e. it disagrees with the integer).  This avoids the "double-onchange"
        # reset: returning schedule_hour/schedule_minute in the value dict causes
        # the web client to re-trigger this same onchange, at which point
        # schedule_hour_sel / schedule_minute_sel are stale ("0") and would
        # overwrite the user's choice with zero.
        if self.schedule_hour_sel is not None:
            sel_hour = int(self.schedule_hour_sel)
            if sel_hour != self.schedule_hour:
                self.schedule_hour = sel_hour
        if self.schedule_minute_sel is not None:
            sel_min = int(self.schedule_minute_sel)
            if sel_min != self.schedule_minute:
                self.schedule_minute = sel_min

        availability = self._get_availability_values()
        value = self._availability_onchange_values(availability)
        # Do NOT return schedule_hour / schedule_minute in the value dict.
        # Returning them triggers a second onchange (they are also in the
        # trigger list) where the web-client sends stale selection values,
        # causing the minute to silently reset to 00.
        if self.tutor_id and self.tutor_id not in availability['assignable']:
            value['tutor_id'] = False

        return {
            'value': value,
        }

    @api.onchange('tutor_id', 'schedule_date', 'schedule_hour', 'schedule_minute',
                  'schedule_hour_sel', 'schedule_minute_sel',
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
        tz = pytz.timezone(self.timezone or self.env.user.tz or DEFAULT_TIMEZONE)
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

    @api.depends('schedule_hour', 'schedule_minute', 'schedule_hour_sel', 'schedule_minute_sel',
                 'schedule_duration', 'monday', 'tuesday', 'wednesday',
                 'thursday', 'friday', 'saturday', 'sunday', 'course_id',
                 'start_date', 'schedule_type', 'schedule_date', 'timezone')
    def _compute_available_tutors(self):
        """Assign availability fields from the shared _calc_availability helper."""
        for rec in self:
            r = rec._calc_availability()
            rec.all_eligible_tutor_ids = r['all_eligible']
            rec.available_tutor_ids    = r['available']
            rec.partial_tutor_ids      = r['partial']
            rec.fallback_tutor_ids     = r['fallback']
            rec.assignable_tutor_ids   = r['assignable']
            rec.no_tutor_available     = r['no_tutor_available']

    def _calc_availability(self):
        """Core availability logic for this single record.
        Returns a plain dict so both the @api.depends compute and the
        @api.onchange can use the same logic without ORM cache side-effects."""
        rec = self
        empty = self.env['tutor.profile']
        day_fields = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

        if not rec.course_id:
            return {'all_eligible': empty, 'available': empty,
                    'partial': empty, 'fallback': empty, 'assignable': empty,
                    'no_tutor_available': False}

        category = rec.course_id.category_id or rec.course_id.subject_id.category_id
        subject = rec.course_id.subject_id
        # Use schedule_hour/minute (ints). The sel-inverse may or may not have
        # run yet — read the raw int fields which are always reliable.
        schedule_hour   = rec.schedule_hour   or 0
        schedule_minute = rec.schedule_minute or 0
        schedule_time    = schedule_hour + schedule_minute / 60.0
        duration_hours   = (rec.schedule_duration or 60) / 60.0
        schedule_end_time = schedule_time + duration_hours

        target_date = (
            rec.schedule_date if rec.schedule_type == 'one_time' and rec.schedule_date
            else rec.start_date or fields.Date.today()
        )
        all_tutors = self.env['tutor.profile'].get_eligible_tutors(
            category,
            subject,
            target_date,
        ) if category and subject else empty

        # Derive selected schedule dates. For recurring schedules we need a real
        # date per selected weekday so timezone conversion can also shift the
        # tutor's local day, not just the local clock time.
        if rec.schedule_type == 'one_time' and rec.schedule_date:
            selected_dates = [rec.schedule_date]
        else:
            selected_weekdays = [d for d in day_fields if getattr(rec, d, False)]
            today = fields.Date.today()
            base_date = max(rec.start_date or today, today)
            weekday_index = {day: idx for idx, day in enumerate(day_fields)}
            selected_dates = []
            for day in selected_weekdays:
                delta = (weekday_index[day] - base_date.weekday()) % 7
                selected_dates.append(base_date + timedelta(days=delta))

        if not selected_dates:
            return {'all_eligible': all_tutors, 'available': empty,
                    'partial': empty, 'fallback': empty, 'assignable': all_tutors,
                    'no_tutor_available': False}

        # Resolve schedule timezone — mirrors the field's Python default so it
        # works correctly even before the field default is applied on new records.
        sched_tz_name = rec.timezone or self.env.user.tz or DEFAULT_TIMEZONE
        try:
            sched_tz = pytz.timezone(sched_tz_name)
        except pytz.UnknownTimeZoneError:
            sched_tz = pytz.timezone(DEFAULT_TIMEZONE)

        def _to_tutor_local(slot_date, time_float, tutor_tz_name):
            hours, minutes = self._float_to_time_parts(time_float)
            naive_date = slot_date + timedelta(days=hours // 24)
            naive_time = time(hours % 24, minutes)
            schedule_dt = sched_tz.localize(datetime.combine(naive_date, naive_time))
            if not tutor_tz_name:
                tutor_tz_name = DEFAULT_TIMEZONE
            try:
                tutor_tz = pytz.timezone(tutor_tz_name)
            except pytz.UnknownTimeZoneError:
                tutor_tz = pytz.timezone(DEFAULT_TIMEZONE)
            return schedule_dt.astimezone(tutor_tz)

        def _slot_covered_by_availability(tutor, start_dt, end_dt):
            """Return whether the whole slot is covered in tutor local time."""
            cursor = start_dt
            while cursor < end_dt:
                day_end = min(
                    end_dt,
                    cursor.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1),
                )
                day_name = cursor.strftime('%A').lower()
                start_float = cursor.hour + cursor.minute / 60.0
                end_float = day_end.hour + day_end.minute / 60.0
                if day_end.date() > cursor.date() and end_float == 0:
                    end_float = 24.0
                avail = tutor.availability_ids.filtered(lambda a, d=day_name: a.day_of_week == d)
                day_full = any(a.start_time <= start_float and a.end_time >= end_float for a in avail)
                if not day_full:
                    return False
                cursor = day_end
            return True

        available = empty
        for tutor in all_tutors:
            tutor_tz = tutor.timezone or DEFAULT_TIMEZONE
            days_full = []
            for slot_date in selected_dates:
                t_start = _to_tutor_local(slot_date, schedule_time, tutor_tz)
                t_end = _to_tutor_local(slot_date, schedule_end_time, tutor_tz)
                day_full = _slot_covered_by_availability(tutor, t_start, t_end)
                days_full.append(day_full)

            if all(days_full):
                available |= tutor

        if available:
            return {'all_eligible': all_tutors, 'available': available,
                    'partial': empty, 'fallback': empty,
                    'assignable': all_tutors,
                    'no_tutor_available': False}
        else:
            return {'all_eligible': all_tutors, 'available': empty,
                    'partial': empty, 'fallback': all_tutors, 'assignable': all_tutors,
                    'no_tutor_available': True}

    @api.onchange('tutor_id')
    def _onchange_tutor_rate_matrix_warning(self):
        """Warn (non-blocking) when the selected tutor has no pricing matrix
        for the course's category and subject."""
        if not self.tutor_id or not self.course_id:
            return
        category = self.course_id.category_id
        subject = self.course_id.subject_id
        if not category or not subject:
            return
        if self.tutor_id.employment_type == 'permanent':
            has_rate = self.env['tutor.fixed.rate'].search_count([
                ('tutor_id', '=', self.tutor_id.id),
                ('active_flag', '=', True),
            ])
        else:
            has_rate = self.env['tutor.subject.rate'].search_count([
                ('tutor_id', '=', self.tutor_id.id),
                ('category_id', '=', category.id),
                ('subject_id', '=', subject.id),
                ('active_flag', '=', True),
            ])
        if not has_rate:
            return {
                'warning': {
                    'title': 'Missing Pricing Matrix',
                    'message': (
                        f'{self.tutor_id.name} does not have a pricing rate configured '
                        f'for {category.name} / {subject.name}.\n\n'
                        f'You can still save the schedule, but billing may not work correctly '
                        f'until a rate is added in the Tutor Pricing Matrix.'
                    ),
                }
            }

    @api.depends('course_id', 'tutor_id', 'schedule_type')
    def _compute_name(self):
        for rec in self:
            parts = [p for p in [rec.course_id.name or '', rec.tutor_id.name or '',
                                  dict(rec._fields['schedule_type'].selection).get(rec.schedule_type, '')] if p]
            rec.name = ' - '.join(parts) if parts else 'New Schedule'

    def _generate_occurrences(self):
        today = fields.Date.today()
        now = fields.Datetime.now()
        Occ = self.env['class.schedule.occurrence'].sudo()
        for record in self:
            # Use a direct DB search (bypasses ORM cache) so that multiple calls within
            # the same transaction don't leave behind stale occurrence batches.
            future_scheduled = Occ.search([
                ('schedule_id', '=', record.id),
                ('lesson_status', '=', 'scheduled'),
                ('start_datetime', '>=', now),
            ])
            future_scheduled.unlink()
            if record.schedule_type == 'one_time':
                if not record.schedule_date:
                    continue
                effective_date = record.schedule_date
                tz = pytz.timezone(record.timezone or 'UTC')
                local_dt = tz.localize(fields.Datetime.to_datetime(effective_date).replace(
                    hour=record.schedule_hour, minute=record.schedule_minute, second=0))
                utc_start = local_dt.astimezone(pytz.utc).replace(tzinfo=None)
                # Skip if a non-cancelled occurrence already exists for this datetime (dedup guard)
                existing = Occ.search([
                    ('schedule_id', '=', record.id),
                    ('start_datetime', '=', utc_start),
                    ('lesson_status', '!=', 'cancelled'),
                ], limit=1)
                if existing:
                    continue
                occ_name = f"{record.course_id.name or 'Class'} - {effective_date.strftime('%a %b %d, %Y')}"
                if record.is_reschedule and record.rescheduled_from_id:
                    occ_name += ' (Rescheduled)'
                Occ.create([{
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
            # Determine where to start generating: never before today, and skip today if
            # a non-cancelled occurrence already exists in today's UTC window (dedup guard via DB search).
            today_start_utc = datetime.combine(today, time(0, 0, 0))
            today_end_utc = today_start_utc + timedelta(days=1)
            today_has_occurrence = Occ.search([
                ('schedule_id', '=', record.id),
                ('start_datetime', '>=', today_start_utc),
                ('start_datetime', '<', today_end_utc),
                ('lesson_status', '!=', 'cancelled'),
            ], limit=1)
            generate_from = max(record.start_date, today + timedelta(days=1) if today_has_occurrence else today)
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
                Occ.create(occurrences)

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

    @api.model
    def get_common_timezones(self):
        """Return the same timezone list used in the schedule form, as [[value, label], ...]."""
        return COMMON_TIMEZONES

    @api.model
    def get_user_timezone(self):
        """Return the user's timezone from their role profile (student/tutor/parent),
        falling back to Odoo user tz, then UTC."""
        partner = self.env.user.partner_id
        for model in ('student.profile', 'tutor.profile', 'parent.profile'):
            profile = self.env[model].sudo().search(
                [('partner_id', '=', partner.id)], limit=1)
            if profile and profile.timezone:
                return profile.timezone
        return self.env.user.tz or 'UTC'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            record._generate_occurrences()
            record._sync_tutor_to_course()
            record._warn_missing_tutor_rate()
            record._log_schedule_created()
        return records

    def _log_schedule_created(self):
        self.ensure_one()
        if not self.course_id:
            return

        time_str = '%02d:%02d' % (self.schedule_hour, self.schedule_minute)
        tz_str = self.timezone or 'UTC'

        if self.schedule_type == 'one_time':
            date_str = self.schedule_date.strftime('%d %b %Y') if self.schedule_date else '—'
            schedule_str = '%s at %s (%s)' % (date_str, time_str, tz_str)
        else:
            day_names = [
                d.capitalize() for d in
                ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                if getattr(self, d)
            ]
            days_str = ', '.join(day_names) if day_names else '—'
            date_range = ''
            if self.start_date:
                date_range = ' from %s' % self.start_date.strftime('%d %b %Y')
                if self.end_date:
                    date_range += ' to %s' % self.end_date.strftime('%d %b %Y')
            schedule_str = '%s at %s (%s)%s' % (days_str, time_str, tz_str, date_range)

        reason_line = Markup('')
        if self.schedule_type == 'one_time' and self.one_time_reason:
            reason_line = Markup('<br/>Reason: <b>%s</b>') % self.one_time_reason

        body = Markup(
            '<b>Schedule Created</b><br/>'
            'Created by: <b>%s</b><br/>'
            'Tutor: <b>%s</b><br/>'
            'Time: <b>%s</b>%s'
        ) % (
            self.env.user.name,
            self.tutor_id.name if self.tutor_id else '—',
            schedule_str,
            reason_line,
        )

        self.course_id.message_post(
            body=body,
            subtype_xmlid='mail.mt_note',
        )

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
            for record in self:
                record._warn_missing_tutor_rate()
        return res

    def _warn_missing_tutor_rate(self):
        """Post a chatter warning if the assigned tutor has no pricing rate for
        the course's category + subject. Non-blocking — the schedule is saved."""
        self.ensure_one()
        if not self.tutor_id or not self.course_id:
            return
        category = self.course_id.category_id
        subject = self.course_id.subject_id
        if not category or not subject:
            return
        if self.tutor_id.employment_type == 'permanent':
            has_rate = self.env['tutor.fixed.rate'].search_count([
                ('tutor_id', '=', self.tutor_id.id),
                ('active_flag', '=', True),
            ])
        else:
            has_rate = self.env['tutor.subject.rate'].search_count([
                ('tutor_id', '=', self.tutor_id.id),
                ('category_id', '=', category.id),
                ('subject_id', '=', subject.id),
                ('active_flag', '=', True),
            ])
        if not has_rate:
            self.course_id.message_post(
                body=(
                    '⚠️ <b>Missing Pricing Rate</b>: Tutor <b>%s</b> has no active pricing rate '
                    'configured for <b>%s / %s</b>. '
                    'Please add a rate in the Tutor Pricing Matrix to ensure correct billing.'
                ) % (self.tutor_id.name, category.name, subject.name),
                subtype_xmlid='mail.mt_note',
            )

    def unlink(self):
        now = fields.Datetime.now()
        deletion_logs = []
        for record in self:
            if record.course_id:
                deletion_logs.append((record.course_id, record._build_schedule_deleted_log()))
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

        result = super(ClassSchedule, self).unlink()
        for course, body in deletion_logs:
            course.message_post(body=body, subtype_xmlid='mail.mt_note')
        return result

    def _build_schedule_deleted_log(self):
        self.ensure_one()
        time_str = '%02d:%02d' % (self.schedule_hour, self.schedule_minute)
        tz_str = self.timezone or 'UTC'

        if self.schedule_type == 'one_time':
            date_str = self.schedule_date.strftime('%d %b %Y') if self.schedule_date else '—'
            schedule_str = '%s at %s (%s)' % (date_str, time_str, tz_str)
        else:
            day_names = [
                d.capitalize() for d in
                ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                if getattr(self, d)
            ]
            days_str = ', '.join(day_names) if day_names else '—'
            date_range = ''
            if self.start_date:
                date_range = ' from %s' % self.start_date.strftime('%d %b %Y')
                if self.end_date:
                    date_range += ' to %s' % self.end_date.strftime('%d %b %Y')
            schedule_str = '%s at %s (%s)%s' % (days_str, time_str, tz_str, date_range)

        return Markup(
            '<b>Schedule Deleted</b><br/>'
            'Deleted by: <b>%s</b><br/>'
            'Tutor: <b>%s</b><br/>'
            'Time: <b>%s</b>'
        ) % (
            self.env.user.name,
            self.tutor_id.name if self.tutor_id else '—',
            schedule_str,
        )

    @api.constrains('schedule_type', 'start_date', 'end_date', 'schedule_date', 'one_time_reason')
    def _check_required_dates(self):
        for rec in self:
            if rec.schedule_type == 'one_time' and not rec.schedule_date:
                raise UserError('Please set a Date for a one-time schedule.')
            if rec.schedule_type == 'one_time' and not (rec.one_time_reason or '').strip():
                raise UserError('Please provide a reason for the one-time session.')
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
    calendar_label = fields.Char(
        string='Calendar Label',
        compute='_compute_calendar_label',
        store=False,
    )
    course_id = fields.Many2one('course.master', string='Course', store=True)
    tutor_id = fields.Many2one('tutor.profile', string='Tutor', store=True)
    attendance_ids = fields.One2many('attendance.record', 'class_schedule_occurrence_id', string='Attendance')
    attendance_marked = fields.Boolean(string='Attendance Marked', compute='_compute_attendance_marked', store=True)
    attendance_present_count = fields.Integer(string='Present', compute='_compute_attendance_counts', store=True)
    attendance_absent_count = fields.Integer(string='Absent', compute='_compute_attendance_counts', store=True)
    attendance_student_ids = fields.Many2many(
        'student.profile', string='Students',
        compute='_compute_attendance_student_ids',
        search='_search_attendance_student_ids',
    )
    report_student_id = fields.Many2one(
        'student.profile', string='Student',
        compute='_compute_report_student_id',
        search='_search_report_student_id',
        store=False,
    )
    lesson_status = fields.Selection([
        ('scheduled', 'Scheduled'), ('completed', 'Completed'), ('cancelled', 'Cancelled'),
        ('under_review', 'Under Review'),
    ], string='Lesson Status', default='scheduled')
    cancellation_reason = fields.Selection([
        ('platform_issue', 'Platform Issue'), ('tutor_issue', 'Tutor Issue'),
        ('admin_issue', 'Admin Issue'), ('student_cancelled', 'Student Cancelled'),
    ], string='Cancellation Reason')
    cancellation_note = fields.Text(string='Cancellation Note')
    cancellation_date = fields.Datetime(string='Cancelled On', readonly=True)
    cancelled_by = fields.Many2one('res.users', string='Cancelled By', readonly=True)
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

    @api.depends('attendance_ids.student_id')
    def _compute_attendance_student_ids(self):
        for rec in self:
            rec.attendance_student_ids = rec.attendance_ids.mapped('student_id')

    def _search_attendance_student_ids(self, operator, value):
        return [('attendance_ids.student_id', operator, value)]

    def _compute_report_student_id(self):
        for rec in self:
            rec.report_student_id = False

    def _search_report_student_id(self, operator, value):
        return [('attendance_ids.student_id', operator, value)]

    @api.depends('attendance_ids.status')
    def _compute_attendance_counts(self):
        for rec in self:
            rec.attendance_present_count = len(rec.attendance_ids.filtered(lambda a: a.status == 'present'))
            rec.attendance_absent_count = len(rec.attendance_ids.filtered(lambda a: a.status == 'absent'))

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

    @api.depends('name', 'course_id', 'tutor_id', 'start_datetime', 'schedule_id', 'schedule_id.timezone')
    def _compute_calendar_label(self):
        """Rich label for calendar event cards: course · time · tutor."""
        for rec in self:
            parts = []
            if rec.course_id:
                parts.append(rec.course_id.name or '')
            if rec.start_datetime:
                tz_name = (rec.schedule_id.timezone if rec.schedule_id else None) or 'UTC'
                try:
                    tz = pytz.timezone(tz_name)
                except pytz.UnknownTimeZoneError:
                    tz = pytz.utc
                local_dt = rec.start_datetime.replace(tzinfo=pytz.utc).astimezone(tz)
                parts.append(local_dt.strftime('%H:%M'))
            if rec.tutor_id:
                parts.append(rec.tutor_id.name or '')
            rec.calendar_label = ' · '.join(filter(None, parts)) or rec.name

    @api.depends('course_id', 'course_id.virtual_provider_default')
    def _compute_virtual_provider(self):
        """Always resolve provider from course. Sessions never own the provider."""
        for rec in self:
            rec.virtual_provider = rec.course_id.virtual_provider_default or 'bbb'

    _LESSON_LOG_EXCLUDE = frozenset({'tutor_id', 'exclude_from_payroll'})

    _LESSON_LOG_LABELS = {
        'lesson_status': 'Lesson Status',
        'cancellation_reason': 'Cancellation Reason',
        'cancellation_note': 'Cancellation Note',
        'start_datetime': 'Start Time',
        'stop_datetime': 'End Time',
        'topic_covered': 'What Was Taught',
        'class_rating': 'Class Rating',
        'next_steps': 'Next Steps',
        'homework': 'Homework',
        'tutor_comments': 'Tutor Comments',
        'has_technical_issues': 'Technical Issues',
        'technical_issue_type': 'Technical Issue Type',
        'technical_issue_details': 'Technical Issue Details',
    }

    def _get_selection_label(self, field_name, value):
        if value is False or value is None:
            return '—'
        field = self._fields.get(field_name)
        if field and hasattr(field, 'selection'):
            sel = field.selection
            if callable(sel):
                sel = sel(self)
            for key, label in sel:
                if key == value:
                    return label
        return str(value)

    def _format_lesson_field(self, field_name, value):
        if value is False or value is None:
            return '—'
        field = self._fields.get(field_name)
        if not field:
            return str(value)
        if field.type == 'selection':
            return self._get_selection_label(field_name, value)
        if field.type == 'datetime':
            tz_name = (self.schedule_id.timezone if self.schedule_id else None) or 'UTC'
            try:
                tz = pytz.timezone(tz_name)
            except pytz.UnknownTimeZoneError:
                tz = pytz.utc
            if isinstance(value, str):
                value = fields.Datetime.from_string(value)
            local_dt = value.replace(tzinfo=pytz.utc).astimezone(tz)
            return local_dt.strftime('%d %b %Y %H:%M') + ' (%s)' % tz_name
        if field.type == 'boolean':
            return 'Yes' if value else 'No'
        if field.type == 'text' and value:
            return (value[:80] + '…') if len(value) > 80 else value
        return str(value) if value else '—'

    def write(self, vals):
        if vals.get('lesson_status') == 'cancelled':
            # Dedicated "Cancel Lesson" permission (distinct from "Cancel
            # Courses", which governs cancelling a whole course.master
            # record) — respects the app's own fine-grained permission
            # system rather than hardcoding Odoo's generic System/Access-
            # Rights admin groups. user_has_permission already lets
            # base.group_system through automatically.
            if not user_has_permission(self.env.user, 'lesson_cancel'):
                raise UserError("Only administrators or managers with the 'Cancel Lesson' permission can cancel a lesson.")
            # Cancellation must always go through the "Cancel Lesson" wizard (or the
            # course-cancellation cascade) so a reason is captured — this flag is only
            # ever set by those two call sites, closing off inline field edits, the
            # statusbar, or any other direct write as a way to cancel a lesson.
            if not self.env.context.get('allow_lesson_cancel'):
                raise UserError('Lessons can only be cancelled through the "Cancel Lesson" action, so the reason is captured.')
        reschedule_fields = {'tutor_id'}
        if reschedule_fields & set(vals.keys()) and 'lesson_status' not in vals:
            for rec in self:
                if rec.lesson_status == 'scheduled':
                    vals = dict(vals, is_rescheduled=True)
                    break

        is_cancellation = vals.get('lesson_status') == 'cancelled'
        tracked = {} if is_cancellation else {
            f: l for f, l in self._LESSON_LOG_LABELS.items()
            if f in vals and f not in self._LESSON_LOG_EXCLUDE
        }

        old_vals = {}
        if tracked:
            for rec in self:
                old_vals[rec.id] = {f: getattr(rec, f) for f in tracked}

        result = super().write(vals)

        if tracked:
            for rec in self:
                changes = []
                for fname, label in tracked.items():
                    old = old_vals.get(rec.id, {}).get(fname)
                    new = getattr(rec, fname)
                    if old != new:
                        old_str = rec._format_lesson_field(fname, old)
                        new_str = rec._format_lesson_field(fname, new)
                        changes.append((label, old_str, new_str))
                if changes and rec.course_id:
                    lines = Markup('').join(
                        Markup('<br/>• <b>%s:</b> %s → %s') % (label, old_str, new_str)
                        for label, old_str, new_str in changes
                    )
                    body = Markup(
                        '<b>Lesson Updated</b> — %s<br/>'
                        'Updated by: <b>%s</b>%s'
                    ) % (rec.name or '—', self.env.user.name, lines)
                    rec.course_id.message_post(body=body, subtype_xmlid='mail.mt_note')

        return result

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
        if self.lesson_status == 'cancelled':
            raise UserError("Attendance cannot be marked for a cancelled lesson.")
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
                         'status': (existing_attendance[sid].status if sid in existing_attendance and existing_attendance[sid].status in valid_statuses else False),
                         'remarks': existing_attendance[sid].remarks if sid in existing_attendance else ''})
                 for sid in all_student_ids]
        if lines: wizard.write({'line_ids': lines})
        return {'type': 'ir.actions.act_window', 'name': f'Mark Attendance - {self.name}',
                'res_model': 'mark.attendance.wizard', 'view_mode': 'form', 'res_id': wizard.id, 'target': 'new'}

    def action_export_attendance_excel(self):
        if not self:
            raise UserError("Please select at least one record to export.")

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Attendance Report')

        title_fmt = workbook.add_format({'bold': True, 'font_size': 13})
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#2E86AB', 'font_color': '#FFFFFF', 'border': 1, 'align': 'center'})
        text_fmt = workbook.add_format({'border': 1})
        num_fmt = workbook.add_format({'num_format': '#,##0', 'border': 1, 'align': 'center'})

        sheet.write(0, 0, 'Attendance Report', title_fmt)

        lesson_status_labels = dict(self._fields['lesson_status'].selection)
        headers = ['Date & Time', 'Course', 'Tutor', 'Lesson Status', 'Attendance Submitted', 'Present', 'Absent']
        col_widths = [26, 22, 18, 14, 18, 10, 10]
        for col, (h, w) in enumerate(zip(headers, col_widths)):
            sheet.write(2, col, h, header_fmt)
            sheet.set_column(col, col, w)

        for row_idx, occ in enumerate(self.sorted('start_datetime'), start=3):
            sheet.write(row_idx, 0, occ.start_local_display or '', text_fmt)
            sheet.write(row_idx, 1, occ.course_id.name or '', text_fmt)
            sheet.write(row_idx, 2, occ.tutor_id.name or '', text_fmt)
            sheet.write(row_idx, 3, lesson_status_labels.get(occ.lesson_status, ''), text_fmt)
            sheet.write(row_idx, 4, 'Yes' if occ.attendance_marked else 'No', text_fmt)
            sheet.write(row_idx, 5, occ.attendance_present_count, num_fmt)
            sheet.write(row_idx, 6, occ.attendance_absent_count, num_fmt)

        workbook.close()
        xlsx_data = output.getvalue()
        attachment = self.env['ir.attachment'].create({
            'name': f'Attendance_Report_{fields.Date.context_today(self)}.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(xlsx_data),
            'res_model': self._name,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    def action_cancel_lesson(self):
        self.ensure_one()
        wizard = self.env['cancel.lesson.wizard'].create({'occurrence_id': self.id})
        return {'type': 'ir.actions.act_window', 'name': 'Cancel Lesson',
                'res_model': 'cancel.lesson.wizard', 'view_mode': 'form', 'res_id': wizard.id, 'target': 'new'}

    def action_view_cancellation_details(self):
        self.ensure_one()
        view_id = self.env.ref('tuition_management.view_cancellation_details_form').id
        return {
            'type': 'ir.actions.act_window',
            'name': 'Cancellation Details',
            'res_model': 'class.schedule.occurrence',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(view_id, 'form')],
            'target': 'new',
            'flags': {'mode': 'readonly'},
        }

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
        occ.sudo().with_context(allow_lesson_cancel=True).write({
            'lesson_status': 'cancelled',
            'cancellation_reason': self.reason,
            'cancellation_note': self.note,
            'cancellation_date': fields.Datetime.now(),
            'cancelled_by': self.env.uid,
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
