# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    vc_zoom_client_id = fields.Char(
        string='Client ID',
        config_parameter='tuition_management.zoom_client_id',
    )
    vc_zoom_client_secret = fields.Char(
        string='Client Secret',
        config_parameter='tuition_management.zoom_client_secret',
    )
    vc_zoom_account_id = fields.Char(
        string='Account ID',
        config_parameter='tuition_management.zoom_account_id',
    )
    vc_zoom_host_email = fields.Char(
        string='Preferred Host Email',
        config_parameter='tuition_management.zoom_host_email',
        help='Optional. When set, this Zoom user is tried first (if free) before '
             'the system checks other active users under the master account. '
             'Leave blank to let it pick freely.',
    )
    vc_bbb_server_url = fields.Char(
        string='Server URL',
        config_parameter='tuition_management.bbb_server_url',
    )
    vc_bbb_secret = fields.Char(
        string='Secret',
        config_parameter='tuition_management.bbb_secret',
    )
    vc_google_service_account_email = fields.Char(
        string='Service Account Email',
        config_parameter='tuition_management.google_service_account_email',
    )
    vc_google_service_account_private_key = fields.Char(
        string='Service Account Private Key',
        config_parameter='tuition_management.google_service_account_private_key',
    )
