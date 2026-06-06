# -*- coding: utf-8 -*-
from datetime import date
from odoo import models, fields, api
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta
import calendar
from .user_permission import require_permission


class BulkBillingWizard(models.TransientModel):
    _name = 'bulk.billing.wizard'
    _description = 'Bulk Billing Generation Wizard'

    month = fields.Selection(
        selection=lambda self: [(str(i), calendar.month_name[i]) for i in range(1, 13)],
        string='Billing Month',
        required=True,
    )
    year = fields.Integer(
        string='Billing Year',
        required=True,
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        today = date.today()
        last_month = today - relativedelta(months=1)
        if 'month' in fields_list:
            res['month'] = str(last_month.month)
        if 'year' in fields_list:
            res['year'] = today.year
        return res

    def action_preview_invoices(self):
        self.ensure_one()
        require_permission(self.env.user, 'parent_invoice_generate')
        # Check for an existing run for this month/year
        existing = self.env['parent.billing.run'].search([
            ('month', '=', self.month),
            ('year', '=', self.year),
        ], limit=1)
        if existing:
            import calendar as _cal
            period = f"{_cal.month_name[int(self.month)]} {self.year}"
            raise UserError(
                f"A parent invoicing run already exists for {period} (Ref: {existing.name}, "
                f"Status: {dict(existing._fields['state'].selection).get(existing.state, existing.state)}). "
                f"Please open the existing run from the 'Parent Invoicing Runs' menu."
            )
        # Create a persistent billing run and redirect to it for admin review & approval.
        run = self.env['parent.billing.run'].create({
            'month': self.month,
            'year': self.year,
        })
        run.action_generate_preview()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Billing Run – {run.period_label}',
            'res_model': 'parent.billing.run',
            'view_mode': 'form',
            'res_id': run.id,
            'target': 'current',
        }
