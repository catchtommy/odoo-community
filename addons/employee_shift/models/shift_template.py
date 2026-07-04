# -*- coding: utf-8 -*-
from datetime import datetime, timedelta

import pytz

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .tz_utils import get_tz_selection, DEFAULT_TIMEZONE


class ShiftTemplate(models.Model):
    _name = "shift.template"
    _description = "Shift Template"
    _order = "start_time"

    name = fields.Char(string="Shift Name", required=True)
    start_time = fields.Float(string="Start Time", required=True, help="Time of day, e.g. 9.5 = 09:30")
    end_time = fields.Float(string="End Time", required=True, help="Time of day. If earlier than Start Time, the shift is treated as overnight (ends the next day).")
    base_tz = fields.Selection(selection=get_tz_selection, string="Base Timezone", required=True, default=DEFAULT_TIMEZONE)
    color = fields.Integer(string="Color")
    active = fields.Boolean(default=True)

    display_name = fields.Char(string="Display Name", compute="_compute_display_name")

    @api.depends('name', 'start_time', 'end_time', 'base_tz')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = "%s (%s–%s %s)" % (
                rec.name,
                rec._format_float_time(rec.start_time),
                rec._format_float_time(rec.end_time),
                rec.base_tz or '',
            )

    @staticmethod
    def _format_float_time(value):
        hours = int(value)
        minutes = int(round((value - hours) * 60))
        if minutes == 60:
            hours, minutes = hours + 1, 0
        return "%02d:%02d" % (hours, minutes)

    @api.constrains('start_time', 'end_time')
    def _check_times(self):
        for rec in self:
            if rec.start_time == rec.end_time:
                raise ValidationError("Start Time and End Time cannot be the same.")
            if not (0 <= rec.start_time < 24) or not (0 <= rec.end_time < 24):
                raise ValidationError("Start Time and End Time must be between 00:00 and 23:59.")

    def _localize_time_to_utc(self, date_val, time_val):
        """Given a date and a time-of-day float (e.g. 9.5 = 09:30), return the
        naive UTC datetime (the format Odoo Datetime fields expect), honoring
        this template's base_tz."""
        self.ensure_one()
        tz = pytz.timezone(self.base_tz or DEFAULT_TIMEZONE)
        hours, remainder = divmod(time_val, 1)
        minutes = round(remainder * 60)
        local_dt = tz.localize(datetime(date_val.year, date_val.month, date_val.day, int(hours), int(minutes)))
        return local_dt.astimezone(pytz.UTC).replace(tzinfo=None)

    def default_end_date(self, start_date):
        """The calendar date End Time naturally falls on for a shift starting
        on start_date: the next day if the shift is overnight (end_time <
        start_time), otherwise the same day."""
        self.ensure_one()
        return start_date + timedelta(days=1) if self.end_time < self.start_time else start_date

    def _localize_to_utc(self, date_val):
        """Given a date, return (start_dt_utc, end_dt_utc) as naive UTC datetimes,
        honoring this template's base_tz. If end_time < start_time the shift is
        overnight and the end datetime rolls over to the next day."""
        self.ensure_one()
        end_date_val = self.default_end_date(date_val)
        start_dt_utc = self._localize_time_to_utc(date_val, self.start_time)
        end_dt_utc = self._localize_time_to_utc(end_date_val, self.end_time)
        return start_dt_utc, end_dt_utc
