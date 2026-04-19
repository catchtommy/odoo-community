# -*- coding: utf-8 -*-
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
