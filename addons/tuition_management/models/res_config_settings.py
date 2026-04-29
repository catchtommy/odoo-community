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
        string='Host Email',
        config_parameter='tuition_management.zoom_host_email',
    )
    vc_bbb_server_url = fields.Char(
        string='Server URL',
        config_parameter='tuition_management.bbb_server_url',
    )
    vc_bbb_secret = fields.Char(
        string='Secret',
        config_parameter='tuition_management.bbb_secret',
    )
    vc_google_client_id = fields.Char(
        string='Client ID',
        config_parameter='tuition_management.google_client_id',
    )
    vc_google_client_secret = fields.Char(
        string='Client Secret',
        config_parameter='tuition_management.google_client_secret',
    )
    vc_google_redirect_uri = fields.Char(
        string='Redirect URI',
        config_parameter='tuition_management.google_redirect_uri',
    )
    vc_google_organizer_email = fields.Char(
        string='Workspace Organizer Email',
        config_parameter='tuition_management.google_organizer_email',
    )
    vc_google_refresh_token = fields.Char(
        string='OAuth Refresh Token',
        config_parameter='tuition_management.google_refresh_token',
    )
