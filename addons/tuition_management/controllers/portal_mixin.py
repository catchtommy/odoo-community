# -*- coding: utf-8 -*-
import pytz
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
        """Return dict with is_student/is_tutor/is_parent flags."""
        return {
            'is_student': bool(student if student is not None else self._get_student()),
            'is_tutor': bool(tutor if tutor is not None else self._get_tutor()),
            'is_parent': bool(parent if parent is not None else self._get_parent()),
        }

    def _get_user_tz(self):
        """Return the timezone string from the current user's profile, default UTC."""
        profile = self._get_student() or self._get_tutor() or self._get_parent()
        if profile and hasattr(profile, 'timezone') and profile.timezone:
            return profile.timezone
        return 'UTC'

    def _to_user_tz(self, dt):
        """Convert a naive UTC datetime to the user's profile timezone."""
        if not dt:
            return dt
        tz_name = self._get_user_tz()
        try:
            user_tz = pytz.timezone(tz_name)
        except Exception:
            user_tz = pytz.UTC
        utc_dt = pytz.UTC.localize(dt) if dt.tzinfo is None else dt
        return utc_dt.astimezone(user_tz)
