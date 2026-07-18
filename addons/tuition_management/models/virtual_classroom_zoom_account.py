# -*- coding: utf-8 -*-
from odoo import fields, models


class VirtualClassroomZoomAccount(models.Model):
    _name = 'virtual.classroom.zoom.account'
    _description = 'Virtual Classroom Zoom Account'
    _order = 'sequence, id'

    name = fields.Char(string='Label', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    account_id = fields.Char(string='Account ID', required=True)
    client_id = fields.Char(string='Client ID', required=True)
    client_secret = fields.Char(string='Client Secret', required=True, groups='base.group_system')
    host_email = fields.Char(
        string='Host Email',
        required=True,
        help="Zoom user (email or user ID) that will host meetings created by this "
             "account. Server-to-Server OAuth apps have no signed-in user, so the "
             "literal 'me' does not resolve and must not be used here.",
    )
    last_checked_at = fields.Datetime(string='Last Checked', readonly=True)
    last_check_error = fields.Text(string='Last Check Error', readonly=True)
