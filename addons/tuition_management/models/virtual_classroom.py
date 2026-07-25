# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class VirtualClassroomMeeting(models.Model):
    _name = 'virtual.classroom.meeting'
    _description = 'Virtual Classroom Meeting'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    occurrence_id = fields.Many2one(
        'class.schedule.occurrence',
        string='Lesson',
        required=True,
        ondelete='cascade',
        index=True,
    )
    course_id = fields.Many2one(
        'course.master',
        string='Course',
        related='occurrence_id.course_id',
        store=True,
        index=True,
    )
    tutor_id = fields.Many2one(
        'tutor.profile',
        string='Tutor',
        related='occurrence_id.tutor_id',
        store=True,
        index=True,
    )
    provider = fields.Selection([
        ('zoom', 'Zoom'),
        ('bbb', 'BigBlueButton'),
        ('google_meet', 'Google Meet'),
    ], required=True, index=True, tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('creating', 'Creating'),
        ('ready', 'Ready'),
        ('failed', 'Failed'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ], default='draft', tracking=True, index=True)
    external_id = fields.Char(index=True)
    meeting_id = fields.Char(index=True)
    join_url = fields.Char(string='Participant URL')
    host_url = fields.Char(string='Host URL', groups='base.group_user')
    moderator_url = fields.Char(string='Moderator URL', groups='base.group_user')
    google_event_id = fields.Char(index=True)
    google_conference_id = fields.Char(index=True)
    provider_payload = fields.Json(groups='base.group_system')
    error_message = fields.Text(readonly=True)
    last_sync_at = fields.Datetime(readonly=True)
    expires_at = fields.Datetime()
    zoom_account_id = fields.Many2one(
        'virtual.classroom.zoom.account',
        string='Zoom Account Used',
        index=True,
        readonly=True,
    )
    google_account_id = fields.Many2one(
        'virtual.classroom.google.account',
        string='Google Meet Account Used',
        index=True,
        readonly=True,
    )

    _uniq_occurrence_provider = models.Constraint(
        'unique(occurrence_id, provider)',
        'A meeting already exists for this lesson and provider.',
    )

    def action_retry(self):
        for meeting in self:
            self.env['virtual.classroom.service'].start_meeting(meeting.occurrence_id, meeting.provider)
        return True

    def action_mark_cancelled(self):
        self.write({'state': 'cancelled'})
        return True

    def action_force_regenerate(self):
        """Discard this meeting's remote Zoom/Google Meet room entirely and
        create a brand new one in its place — unlike Retry (which only fills
        in a failed/expired row), this also works on a 'ready' meeting, so it's
        the way to pick up a settings/config fix (e.g. a corrected Zoom
        registration setting) for a class that was already started once."""
        service = self.env['virtual.classroom.service']
        for meeting in self:
            provider = service._provider(meeting.provider)
            try:
                provider.cancel_meeting(meeting)
            except Exception as exc:
                _logger.warning(
                    'Failed to cancel old meeting %s during force-regenerate: %s',
                    meeting.id, exc,
                )
            meeting.occurrence_id.sudo().write({'virtual_meeting_id': False})
            meeting.write({
                'state': 'cancelled',
                'meeting_id': False,
                'external_id': False,
                'join_url': False,
                'host_url': False,
                'moderator_url': False,
                'google_event_id': False,
                'google_conference_id': False,
                'provider_payload': False,
                'error_message': False,
                'expires_at': False,
                'zoom_account_id': False,
                'google_account_id': False,
            })
            service.start_meeting(meeting.occurrence_id, meeting.provider)
        return True

    def _cron_expire_meetings(self):
        now = fields.Datetime.now()
        meetings = self.sudo().search([
            ('state', '=', 'ready'),
            ('provider', 'in', ('zoom', 'google_meet')),
            ('expires_at', '<=', now),
        ])
        service = self.env['virtual.classroom.service']
        for meeting in meetings:
            service.expire_meeting(meeting)


class VirtualClassroomStartWizard(models.TransientModel):
    _name = 'virtual.classroom.start.wizard'
    _description = 'Start Virtual Classroom Wizard'

    occurrence_id = fields.Many2one(
        'class.schedule.occurrence',
        string='Lesson',
        required=True,
        readonly=True,
    )
    # Provider is resolved from the course — not chosen per session
    provider = fields.Selection(
        related='occurrence_id.course_id.virtual_provider_default',
        string='Provider',
        readonly=True,
    )

    def action_start_class(self):
        self.ensure_one()
        # Resolve provider exclusively from course
        provider = self.occurrence_id.course_id.virtual_provider_default or 'bbb'
        service = self.env['virtual.classroom.service']
        meeting = service.start_meeting(self.occurrence_id, provider)
        url = service.get_tutor_start_url(meeting, self.occurrence_id.tutor_id)
        if not url:
            raise UserError('Virtual classroom was created, but no launch URL was returned.')
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }
