# -*- coding: utf-8 -*-
from odoo.exceptions import UserError


class VirtualClassroomProvider:
    code = None

    def __init__(self, env):
        self.env = env
        self.params = env['ir.config_parameter'].sudo()

    def _param(self, key):
        return self.params.get_param('tuition_management.%s' % key)

    def create_or_get_meeting(self, meeting):
        raise NotImplementedError

    def get_attendee_url(self, meeting, display_name):
        return meeting.join_url

    def get_moderator_url(self, meeting, display_name):
        return meeting.host_url or meeting.moderator_url

    def cancel_meeting(self, meeting):
        return True

    def _require_config(self, values, label):
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise UserError('%s integration is not configured: %s.' % (label, ', '.join(missing)))
