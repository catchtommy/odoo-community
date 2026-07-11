# -*- coding: utf-8 -*-
from datetime import timedelta, datetime, date

import pytz

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .tz_utils import get_tz_selection, COMMON_TIMEZONES, DEFAULT_TIMEZONE

MORNING_RANGE = (5.0, 12.0)   # 05:00 - 12:00, employee-local time
EVENING_RANGE = (17.0, 24.0)  # 17:00 - 24:00, employee-local time


class EmployeeShift(models.Model):
    _name = "employee.shift"
    _description = "Employee Shift"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Shift Name", required=True)
    start_datetime = fields.Datetime(string="Start", required=True)
    end_datetime = fields.Datetime(string="End", required=True)
    employee_ids = fields.Many2many(
        comodel_name="hr.employee",
        string="Employees",
        relation="employee_shift_rel",
        column1="shift_id",
        column2="employee_id",
    )

    template_id = fields.Many2one("shift.template", string="Shift Template", ondelete="set null")
    native_tz = fields.Selection(selection=get_tz_selection, string="Native Timezone")
    start_date = fields.Date(
        string="Start Date",
        default=lambda self: fields.Date.context_today(self),
        help="Calendar date the shift starts on. Start time is derived from the Shift Template.",
    )
    end_date = fields.Date(
        string="End Date",
        help="Calendar date the shift ends on (the next day for overnight shifts). End time is derived from the Shift Template.",
    )

    color = fields.Integer(string="Color")

    display_name = fields.Char(string="Calendar Title", compute="_compute_display_name")

    @api.depends('name', 'employee_ids')
    def _compute_display_name(self):
        for rec in self:
            if rec.employee_ids:
                employees = ", ".join(rec.employee_ids.mapped('name'))
                rec.display_name = "%s - %s" % (rec.name, employees)
            else:
                rec.display_name = rec.name

    @api.constrains('start_datetime', 'end_datetime')
    def _check_dates(self):
        for rec in self:
            if rec.end_datetime and rec.start_datetime:
                if rec.end_datetime <= rec.start_datetime:
                    raise ValidationError("End datetime must be after start datetime.")

    @api.constrains('employee_ids', 'start_datetime', 'end_datetime')
    def _check_overlapping_shifts(self):
        for rec in self:
            if not rec.employee_ids or not rec.start_datetime or not rec.end_datetime:
                continue
            overlapping = self.search([
                ('id', '!=', rec.id),
                ('employee_ids', 'in', rec.employee_ids.ids),
                ('start_datetime', '<', rec.end_datetime),
                ('end_datetime', '>', rec.start_datetime),
            ])
            if not overlapping:
                continue
            conflicting_names = set()
            for other in overlapping:
                conflicting_names |= set((rec.employee_ids & other.employee_ids).mapped('name'))
            raise ValidationError(
                "The following employee(s) already have an overlapping shift: %s."
                % ", ".join(sorted(conflicting_names))
            )

    @api.onchange('template_id', 'start_date', 'end_date')
    def _onchange_template_id(self):
        """Fetch the shift name, native timezone, and start/end datetimes
        from the selected template, anchored on the chosen start_date/end_date
        range.

        start_date/end_date are plain Date fields (no timezone component) so
        the user always gets exactly the calendar dates they picked, regardless
        of their browser's local timezone offset from UTC — using a Datetime
        field for this anchor previously caused the picked date to silently
        shift by a day depending on the offset.

        end_date defaults to the template's natural rollover date (the next
        day for an overnight shift, otherwise the same day) whenever it isn't
        already set to a valid date on/after start_date, but can be pushed
        further out by the user for a shift that spans multiple days.
        """
        for rec in self:
            if not rec.template_id:
                continue
            rec.name = rec.template_id.name
            rec.native_tz = rec.template_id.base_tz

            start_date = rec.start_date or fields.Date.context_today(rec)
            rec.start_date = start_date

            if not rec.end_date or rec.end_date < start_date:
                rec.end_date = rec.template_id.default_end_date(start_date)
            end_date = rec.end_date

            rec.start_datetime = rec.template_id._localize_time_to_utc(start_date, rec.template_id.start_time)
            rec.end_datetime = rec.template_id._localize_time_to_utc(end_date, rec.template_id.end_time)

    def name_get(self):
        result = []
        for rec in self:
            if rec.employee_ids:
                employees = ", ".join(rec.employee_ids.mapped('name'))
                result.append((rec.id, "%s - %s" % (rec.name, employees)))
            else:
                result.append((rec.id, rec.name))
        return result

    @staticmethod
    def _hex_to_int_color(value):
        """Map a hex color or numeric input to a small integer color index (0-10).
        This maps arbitrary hex values into the calendar's limited color palette.
        """
        # If a hex color like '#ff0000' is provided, hash it into 0..10
        if isinstance(value, str) and value.startswith('#'):
            try:
                return int(value.lstrip('#'), 16) % 11
            except Exception:
                return 0
        try:
            return int(value) % 11
        except Exception:
            return 0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'color' in vals:
                vals['color'] = self._hex_to_int_color(vals.get('color'))
        return super(EmployeeShift, self).create(vals_list)

    def write(self, vals):
        if 'color' in vals:
            vals['color'] = self._hex_to_int_color(vals.get('color'))
        return super(EmployeeShift, self).write(vals)

    def create_for_week(self):
        """Duplicate this shift for the next 6 days to cover a full week."""
        for rec in self:
            if not rec.start_datetime or not rec.end_datetime:
                continue
            start_dt = fields.Datetime.to_datetime(rec.start_datetime)
            end_dt = fields.Datetime.to_datetime(rec.end_datetime)
            for i in range(1, 7):
                vals = {
                    'name': rec.name,
                    'start_datetime': fields.Datetime.to_string(start_dt + timedelta(days=i)),
                    'end_datetime': fields.Datetime.to_string(end_dt + timedelta(days=i)),
                    'employee_ids': [(6, 0, rec.employee_ids.ids)],
                    'color': rec.color,
                }
                # create expects a list when using model_create_multi; use env create
                self.env['employee.shift'].create([vals])
        return True

    def action_open_week_wizard(self):
        self.ensure_one()
        return {
            'name': 'Create Shifts for Range',
            'type': 'ir.actions.act_window',
            'res_model': 'shift.week.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_shift_id': self.id, 'default_start_date': False, 'default_end_date': False},
        }

    # ------------------------------------------------------------------
    # Timezone helpers
    # ------------------------------------------------------------------

    @api.model
    def _local_day_bounds_utc(self, date_val, tz_name):
        """Return (start_utc, end_utc) naive datetimes spanning the local
        calendar day `date_val` in timezone `tz_name`."""
        tz = pytz.timezone(tz_name or DEFAULT_TIMEZONE)
        start_local = tz.localize(datetime(date_val.year, date_val.month, date_val.day, 0, 0, 0))
        end_local = start_local + timedelta(days=1)
        return (
            start_local.astimezone(pytz.UTC).replace(tzinfo=None),
            end_local.astimezone(pytz.UTC).replace(tzinfo=None),
        )

    def _local_hour(self, tz_name):
        """Return this shift's start_datetime as a local hour-of-day float (e.g. 9.5 = 09:30)."""
        self.ensure_one()
        tz = pytz.timezone(tz_name or DEFAULT_TIMEZONE)
        dt_local = pytz.UTC.localize(self.start_datetime).astimezone(tz)
        return dt_local.hour + dt_local.minute / 60.0

    def _serialize_for_dashboard(self):
        return [{
            'id': s.id,
            'name': s.name,
            'start_datetime': fields.Datetime.to_string(s.start_datetime),
            'end_datetime': fields.Datetime.to_string(s.end_datetime),
            'native_tz': s.native_tz or False,
            'color': s.color,
            'template_id': s.template_id.id if s.template_id else False,
            'employees': [{'id': e.id, 'name': e.name} for e in s.employee_ids],
        } for s in self]

    # ------------------------------------------------------------------
    # RPC endpoints consumed by the OWL dashboard / Add Shift modal
    # ------------------------------------------------------------------

    @api.model
    def get_common_timezones(self):
        return COMMON_TIMEZONES

    @api.model
    def get_user_timezone(self):
        employee = self.env.user.employee_id
        return (employee.tz if employee else False) or self.env.user.tz or DEFAULT_TIMEZONE

    @api.model
    def create_from_template(self, template_id, employee_ids, dates):
        """Create one employee.shift per date in `dates` (list of 'YYYY-MM-DD'
        strings), all assigned to `employee_ids`, with times/tz inherited from
        the shift.template `template_id`. Returns the list of created ids."""
        template = self.env['shift.template'].browse(template_id)
        if not template.exists():
            raise ValidationError("Shift Template not found.")
        if not employee_ids:
            raise ValidationError("Select at least one employee.")
        if not dates:
            raise ValidationError("Select at least one date.")
        ineligible = self.env['hr.employee'].browse(employee_ids).filtered(
            lambda e: not e.requires_shift_management)
        if ineligible:
            raise ValidationError(
                "The following employee(s) are not configured for shift management: %s."
                % ", ".join(ineligible.mapped('name'))
            )

        created = self.browse()
        for date_str in dates:
            date_val = fields.Date.from_string(date_str)
            end_date_val = template.default_end_date(date_val)
            start_dt_utc, end_dt_utc = template._localize_to_utc(date_val)
            vals = {
                'name': template.name,
                'start_datetime': fields.Datetime.to_string(start_dt_utc),
                'end_datetime': fields.Datetime.to_string(end_dt_utc),
                'employee_ids': [(6, 0, employee_ids)],
                'template_id': template.id,
                'native_tz': template.base_tz,
                'start_date': date_str,
                'end_date': fields.Date.to_string(end_date_val),
                'color': template.color,
            }
            created |= self.create(vals)
        return created.ids

    @api.model
    def _period_bounds_utc(self, view, date_str, tz):
        """Return (start_utc, end_utc, anchor_date) spanning the whole period
        the dashboard is displaying: a single local calendar day for 'daily'/
        'today', or the full Monday-Sunday local week for 'weekly'/'monthly'
        (a superset covering the visible range is fine for monthly)."""
        tz = tz or DEFAULT_TIMEZONE
        anchor = fields.Date.from_string(date_str) if date_str else fields.Date.context_today(self)

        if view in ('weekly', 'monthly'):
            monday = anchor - timedelta(days=anchor.weekday())
            period_start_utc, _ = self._local_day_bounds_utc(monday, tz)
            _, period_end_utc = self._local_day_bounds_utc(monday + timedelta(days=6), tz)
            return period_start_utc, period_end_utc, monday

        day_start_utc, day_end_utc = self._local_day_bounds_utc(anchor, tz)
        return day_start_utc, day_end_utc, anchor

    @api.model
    def get_dashboard_data(self, view, date_str, tz):
        """Aggregated data for the dashboard's Daily or Weekly view, computed
        in the caller's chosen timezone `tz`. `date_str` is the 'YYYY-MM-DD'
        anchor date (any day of the week for the weekly view)."""
        tz = tz or DEFAULT_TIMEZONE

        if view == 'weekly':
            week_start_utc, week_end_utc, monday = self._period_bounds_utc(view, date_str, tz)
            shifts = self.search([('start_datetime', '<', week_end_utc), ('end_datetime', '>', week_start_utc)])

            week_grid = []
            for i in range(7):
                day = monday + timedelta(days=i)
                day_start_utc, day_end_utc = self._local_day_bounds_utc(day, tz)
                day_shifts = shifts.filtered(lambda s, ds=day_start_utc, de=day_end_utc: s.start_datetime < de and s.end_datetime > ds)
                week_grid.append({
                    'date': fields.Date.to_string(day),
                    'shifts': day_shifts._serialize_for_dashboard(),
                })
            return {'view': 'weekly', 'anchor': fields.Date.to_string(monday), 'week_grid': week_grid}

        day_start_utc, day_end_utc, anchor = self._period_bounds_utc(view, date_str, tz)
        shifts = self.search([('start_datetime', '<', day_end_utc), ('end_datetime', '>', day_start_utc)])
        now_utc = fields.Datetime.now()
        current_shifts = shifts.filtered(lambda s: s.start_datetime <= now_utc <= s.end_datetime)
        return {
            'view': 'daily',
            'date': fields.Date.to_string(anchor),
            'shifts': shifts._serialize_for_dashboard(),
            'current_shifts': current_shifts._serialize_for_dashboard(),
        }

    @api.model
    def get_leave_overview(self, view, date_str, tz, employee_ids=False):
        """Employees with an active leave application (pending approval or
        approved — i.e. any state except Refused/Cancelled) overlapping the
        whole period the dashboard is displaying: a single local calendar day
        for 'daily'/'today', or the full local week for 'weekly'/'monthly'."""
        period_start_utc, period_end_utc, _ = self._period_bounds_utc(view, date_str, tz)

        domain = [
            ('state', 'in', ['confirm', 'validate1', 'validate']),
            ('date_from', '<', period_end_utc),
            ('date_to', '>', period_start_utc),
        ]
        if employee_ids:
            domain.append(('employee_id', 'in', employee_ids))
        leaves = self.env['hr.leave'].sudo().search(domain)
        return [{
            'employee_id': leave.employee_id.id,
            'employee_name': leave.employee_id.name,
            'date_from': fields.Datetime.to_string(leave.date_from),
            'date_to': fields.Datetime.to_string(leave.date_to),
            'state': leave.state,
        } for leave in leaves]

    @api.model
    def get_currently_active(self):
        """Union of employees scheduled on a shift active right now and
        employees currently checked in (hr.attendance), each tagged with
        which of those is true, for the dashboard's Current Shift avatars."""
        now_utc = fields.Datetime.now()
        active_shifts = self.search([('start_datetime', '<=', now_utc), ('end_datetime', '>=', now_utc)])
        scheduled_names = {emp.id: emp.name for s in active_shifts for emp in s.employee_ids}

        # attendance_state is a non-stored compute, so query hr.attendance directly
        # for employees with an open (not checked-out) attendance record.
        open_attendances = self.env['hr.attendance'].sudo().search([('check_out', '=', False)])
        checked_in_employees = open_attendances.employee_id

        result = {}
        for emp in checked_in_employees:
            result[emp.id] = {'id': emp.id, 'name': emp.name, 'checked_in': True, 'scheduled': emp.id in scheduled_names}
        for emp_id, name in scheduled_names.items():
            if emp_id not in result:
                result[emp_id] = {'id': emp_id, 'name': name, 'checked_in': False, 'scheduled': True}
        return list(result.values())

    @api.model
    def search_shifts(self, domain_filters):
        """Combined search for the dashboard's search/filter bar.
        domain_filters: {employee_id, date_from, date_to, time_range, tz}
        time_range is 'morning' | 'evening' | {'start': float, 'end': float}."""
        domain_filters = domain_filters or {}
        tz = domain_filters.get('tz') or DEFAULT_TIMEZONE
        domain = []

        employee_id = domain_filters.get('employee_id')
        if employee_id:
            domain.append(('employee_ids', 'in', [employee_id]))

        date_from = domain_filters.get('date_from')
        if date_from:
            day_start_utc, _ = self._local_day_bounds_utc(fields.Date.from_string(date_from), tz)
            domain.append(('end_datetime', '>', day_start_utc))

        date_to = domain_filters.get('date_to')
        if date_to:
            _, day_end_utc = self._local_day_bounds_utc(fields.Date.from_string(date_to), tz)
            domain.append(('start_datetime', '<', day_end_utc))

        shifts = self.search(domain)

        time_range = domain_filters.get('time_range')
        if time_range == 'morning':
            bounds = MORNING_RANGE
        elif time_range == 'evening':
            bounds = EVENING_RANGE
        elif isinstance(time_range, dict) and time_range.get('start') is not None and time_range.get('end') is not None:
            bounds = (float(time_range['start']), float(time_range['end']))
        else:
            bounds = None

        if bounds:
            lo, hi = bounds
            shifts = shifts.filtered(lambda s: lo <= s._local_hour(tz) < hi)

        return shifts._serialize_for_dashboard()


# Wizard transient model for creating shifts in a date range
class ShiftWeekWizard(models.TransientModel):
    _name = 'shift.week.wizard'
    _description = 'Create Shifts for Date Range'

    shift_id = fields.Many2one('employee.shift', string='Shift', required=True)
    start_date = fields.Date(string='Start Date', required=True)
    end_date = fields.Date(string='End Date', required=True)

    def apply_create(self):
        self.ensure_one()
        if self.end_date < self.start_date:
            raise models.ValidationError('End Date must be on or after Start Date')
        shift = self.shift_id
        # extract time components from original shift datetimes
        orig_start = fields.Datetime.to_datetime(shift.start_datetime)
        orig_end = fields.Datetime.to_datetime(shift.end_datetime)
        for n in range((self.end_date - self.start_date).days + 1):
            cur_date = self.start_date + timedelta(days=n)
            new_start_dt = datetime.combine(cur_date, orig_start.time())
            new_end_dt = datetime.combine(cur_date, orig_end.time())
            vals = {
                'name': shift.name,
                'start_datetime': fields.Datetime.to_string(new_start_dt),
                'end_datetime': fields.Datetime.to_string(new_end_dt),
                'employee_ids': [(6, 0, shift.employee_ids.ids)],
                'color': shift.color,
            }
            self.env['employee.shift'].create(vals)
        return {'type': 'ir.actions.act_window_close'}
