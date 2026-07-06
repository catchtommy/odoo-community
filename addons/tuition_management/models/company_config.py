# -*- coding: utf-8 -*-
from odoo import models, fields
from .user_permission import require_permission


class ResCompanyTuitionExt(models.Model):
    _inherit = 'res.company'

    tuition_currency_ids = fields.Many2many(
        'res.currency', 'res_company_tuition_currency_rel', 'company_id', 'currency_id',
        string='Allowed Billing Currencies',
        help="Currencies selectable on a tuition subscription billed under this company. "
             "If exactly one is set, it is auto-selected as the subscription's default currency.",
    )

    def write(self, vals):
        if 'tuition_currency_ids' in vals:
            require_permission(self.env.user, 'company_currency_config')
        return super().write(vals)
