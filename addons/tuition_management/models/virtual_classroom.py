# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


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
