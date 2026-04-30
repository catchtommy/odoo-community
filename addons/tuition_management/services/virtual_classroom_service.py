# -*- coding: utf-8 -*-
from urllib.parse import urlparse

from odoo import fields, models
from odoo.exceptions import AccessError, UserError

from ..providers import PROVIDERS


class VirtualClassroomService(models.AbstractModel):
    _name = 'virtual.classroom.service'
    _description = 'Virtual Classroom Orchestration Service'

    def _provider(self, provider_code):
        provider_cls = PROVIDERS.get(provider_code)
        if not provider_cls:
            raise UserError('Unsupported classroom provider: %s' % provider_code)
        return provider_cls(self.env)

    def _lock_occurrence(self, occurrence):
        self.env.cr.execute(
            'SELECT id FROM class_schedule_occurrence WHERE id = %s FOR UPDATE',
            [occurrence.id],
        )

    def _is_manager(self):
        return (
            self.env.user.has_group('base.group_system')
            or self.env.user.has_group('base.group_erp_manager')
            or self.env.user.has_group('tuition_management.group_virtual_classroom_manager')
        )

    def _can_start(self, occurrence):
        if self._is_manager():
            return True
        tutor = self.env['tutor.profile'].sudo().search([
            ('partner_id', '=', self.env.user.partner_id.id),
        ], limit=1)
        return bool(tutor and occurrence.tutor_id.id == tutor.id)

    def _legacy_provider(self, course):
        legacy = course.virtual_class_platform
        return 'bbb' if legacy == 'bigbluebutton' else legacy

    def _selected_provider(self, occurrence, provider_code=False):
        """
        Provider resolution order (single source of truth = course):
        1. Explicitly passed provider_code (only used internally, never from per-session UI)
        2. Course-level virtual_provider_default  ← canonical source
        3. Legacy platform field (migration compatibility)
        4. Fallback: BigBlueButton (system default)
        """
        provider = provider_code or occurrence.course_id.virtual_provider_default
        if not provider:
            provider = self._legacy_provider(occurrence.course_id)
        if provider == 'bigbluebutton':
            provider = 'bbb'
        if not provider or provider not in PROVIDERS:
            provider = 'bbb'
        return provider

    def _ensure_meeting(self, occurrence, provider_code):
        self._lock_occurrence(occurrence)

        existing = occurrence.virtual_meeting_id
        if existing and existing.provider != provider_code and existing.state == 'ready':
            raise UserError(
                'This course already has a %s meeting. Reset it before changing provider.'
                % dict(existing._fields['provider'].selection).get(existing.provider)
            )

        # One room per course — search at course level, not occurrence level
        meeting = self.env['virtual.classroom.meeting'].sudo().search([
            ('course_id', '=', occurrence.course_id.id),
            ('provider', '=', provider_code),
        ], limit=1)
        if meeting and meeting.state == 'ready' and (meeting.host_url or meeting.moderator_url) and provider_code != 'bbb':
            occurrence.sudo().write({'virtual_meeting_id': meeting.id})
            return meeting

        if not meeting:
            meeting = self.env['virtual.classroom.meeting'].sudo().create({
                'occurrence_id': occurrence.id,
                'provider': provider_code,
                'state': 'creating',
            })

        meeting.write({'state': 'creating', 'error_message': False})
        try:
            vals = self._provider(provider_code).create_or_get_meeting(meeting) or {}
            vals.update({'state': 'ready', 'last_sync_at': fields.Datetime.now()})
            meeting.write(vals)
            # Link meeting to occurrence; provider is resolved from course, not stored on occurrence
            occurrence.sudo().write({'virtual_meeting_id': meeting.id})
        except Exception as exc:
            meeting.write({
                'state': 'failed',
                'error_message': str(exc),
                'last_sync_at': fields.Datetime.now(),
            })
            raise

        return meeting

    def start_meeting(self, occurrence, provider_code=False):
        occurrence.ensure_one()
        if occurrence.lesson_status in ('cancelled', 'completed'):
            raise UserError('You cannot start a cancelled or completed lesson.')
        if not self._can_start(occurrence):
            raise AccessError('You cannot start this class.')

        provider_code = self._selected_provider(occurrence, provider_code)
        return self._ensure_meeting(occurrence, provider_code)

    def get_tutor_start_url(self, meeting, tutor=False):
        meeting.ensure_one()
        # Use the logged-in user's name (works for both tutor and admin)
        display_name = tutor.name if tutor else self.env.user.name
        return self._provider(meeting.provider).get_moderator_url(meeting, display_name)

    def _is_local_url(self, url):
        if not url:
            return False
        parsed = urlparse(url)
        return parsed.hostname in ('localhost', '127.0.0.1')

    def _legacy_join_url(self, occurrence):
        # Provider always from course
        provider = occurrence.course_id.virtual_provider_default or self._legacy_provider(occurrence.course_id)
        if provider == 'bigbluebutton':
            provider = 'bbb'
        if provider == 'bbb':
            return False
        url = occurrence.course_id.google_meet_static_url or occurrence.course_id.virtual_class_url
        if self._is_local_url(url):
            raise UserError('The configured classroom URL points to localhost. Use the lesson Join button after the tutor starts the class, or update the course URL.')
        return url

    def get_student_join_url(self, occurrence, student):
        occurrence.ensure_one()
        enrollment = self.env['course.enrollment'].sudo().search([
            ('student_id', '=', student.id),
            ('course_id', '=', occurrence.course_id.id),
            ('status', '=', 'active'),
        ], limit=1)
        if not enrollment:
            raise AccessError('You cannot join this class.')
        if occurrence.lesson_status == 'cancelled':
            raise UserError('This class has been cancelled.')

        meeting = occurrence.virtual_meeting_id
        # Also check course-level meeting (one room per course — any session can reuse it)
        if not (meeting and meeting.state == 'ready'):
            provider_code = self._selected_provider(occurrence)
            meeting = self.env['virtual.classroom.meeting'].sudo().search([
                ('course_id', '=', occurrence.course_id.id),
                ('provider', '=', provider_code),
                ('state', '=', 'ready'),
            ], limit=1)
        if meeting and meeting.state == 'ready':
            display_name = student.name or self.env.user.name
            return self._provider(meeting.provider).get_attendee_url(meeting, display_name)

        legacy_url = self._legacy_join_url(occurrence)
        if legacy_url:
            return legacy_url

        provider_code = self._selected_provider(occurrence)
        meeting = self._ensure_meeting(occurrence, provider_code)
        display_name = student.name or self.env.user.name
        return self._provider(meeting.provider).get_attendee_url(meeting, display_name)
