# -*- coding: utf-8 -*-
import pytz
from datetime import datetime, timedelta
from odoo.http import request


class PortalMixin:
    """Shared helper methods for all portal controllers."""

    def _get_student(self):
        return request.env['student.profile'].sudo().search(
            [('partner_id', '=', request.env.user.partner_id.id)], limit=1)

    def _get_tutor(self):
        return request.env['tutor.profile'].sudo().search(
            [('partner_id', '=', request.env.user.partner_id.id)], limit=1)

    def _get_parent(self):
        return request.env['parent.profile'].sudo().search(
            [('partner_id', '=', request.env.user.partner_id.id)], limit=1)

    def _get_role_flags(self, student=None, tutor=None, parent=None):
        return {
            'is_student': bool(student if student is not None else self._get_student()),
            'is_tutor':   bool(tutor   if tutor   is not None else self._get_tutor()),
            'is_parent':  bool(parent  if parent  is not None else self._get_parent()),
        }

    def _get_user_tz(self):
        """
        Return the user's timezone string.
        Priority: Odoo user tz (Settings → Users → Calendar tab)
                  → profile timezone field → UTC.
        """
        if request.env.user.tz:
            return request.env.user.tz
        profile = self._get_student() or self._get_tutor() or self._get_parent()
        if profile and hasattr(profile, 'timezone') and profile.timezone:
            return profile.timezone
        return 'UTC'

    def _user_pytz(self):
        """Return a pytz timezone object for the current user."""
        try:
            return pytz.timezone(self._get_user_tz())
        except Exception:
            return pytz.UTC

    def _tz_today(self):
        """Return today's date object in the user's timezone."""
        return datetime.now(self._user_pytz()).date()

    def _tz_week_bounds(self, week_offset=0):
        """
        Return (start_utc, end_utc, monday_local, sunday_local, week_label).
        Day boundaries are Mon 00:00 → Sun 23:59:59 in the user's timezone,
        then converted to naive UTC for Odoo ORM queries.
        """
        user_tz = self._user_pytz()
        local_today = datetime.now(user_tz).date()
        monday = local_today - timedelta(days=local_today.weekday()) + timedelta(weeks=week_offset)
        sunday = monday + timedelta(days=6)

        start_utc = (user_tz.localize(datetime(monday.year, monday.month, monday.day, 0, 0, 0))
                     .astimezone(pytz.UTC).replace(tzinfo=None))
        end_utc   = (user_tz.localize(datetime(sunday.year, sunday.month, sunday.day, 23, 59, 59))
                     .astimezone(pytz.UTC).replace(tzinfo=None))

        week_label = '%s — %s' % (monday.strftime('%d %b'), sunday.strftime('%d %b %Y'))
        if week_offset == 0:
            week_label = 'This Week (%s)' % week_label

        return start_utc, end_utc, monday, sunday, week_label

    def _tz_date_bounds(self, start_date, end_date):
        """
        Return (start_utc, end_utc) as naive UTC datetimes for an arbitrary
        date range with 00:00/23:59:59 boundaries in the user's timezone.
        """
        user_tz = self._user_pytz()
        start_utc = (user_tz.localize(datetime(start_date.year, start_date.month, start_date.day, 0, 0, 0))
                     .astimezone(pytz.UTC).replace(tzinfo=None))
        end_utc   = (user_tz.localize(datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59))
                     .astimezone(pytz.UTC).replace(tzinfo=None))
        return start_utc, end_utc

    def _to_user_tz(self, dt):
        """Convert a naive UTC datetime to the user's timezone."""
        if not dt:
            return dt
        utc_dt = pytz.UTC.localize(dt) if dt.tzinfo is None else dt
        return utc_dt.astimezone(self._user_pytz())

    def _fmt_dt(self, dt, fmt='%a %d %b %Y, %H:%M %Z'):
        """Convert UTC datetime to user timezone and return a formatted string."""
        local = self._to_user_tz(dt)
        if not local:
            return '—'
        return local.strftime(fmt)
