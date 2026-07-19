# -*- coding: utf-8 -*-
from odoo import fields, models


class VirtualClassroomGoogleAccount(models.Model):
    _name = 'virtual.classroom.google.account'
    _description = 'Virtual Classroom Google Meet Host Account'
    _order = 'sequence, id'

    name = fields.Char(string='Label', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    host_email = fields.Char(
        string='Workspace Host Email',
        required=True,
        help="Google Workspace user whose calendar will host meetings created "
             "via domain-wide delegation. Must be a real user in your Workspace domain.",
    )
    last_checked_at = fields.Datetime(string='Last Checked', readonly=True)
    last_check_error = fields.Text(string='Last Check Error', readonly=True)
