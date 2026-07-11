# -*- coding: utf-8 -*-
from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    requires_shift_management = fields.Boolean(
        string="Requires Shift Management",
        default=False,
        help="Only employees with this enabled appear in the Shift Management "
             "app (Dashboard, Add Shift, Shifts).",
    )
