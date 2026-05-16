# -*- coding: utf-8 -*-
from datetime import date
from odoo import models, fields, api
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta
import calendar


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


class BulkBillingPreview(models.TransientModel):
    _name = 'bulk.billing.preview'
    _description = 'Bulk Billing Preview'

    month = fields.Selection(
        selection=lambda self: [(str(i), calendar.month_name[i]) for i in range(1, 13)],
        string='Billing Month',
        readonly=True
    )
    year = fields.Integer(string='Billing Year', readonly=True)
    line_ids = fields.One2many('bulk.billing.preview.line', 'preview_id', string='Invoice Previews')
    total_invoices = fields.Integer(string="Total Invoices to Generate", compute='_compute_totals')
    total_revenue = fields.Float(string="Total Estimated Revenue", compute='_compute_totals')

    @api.depends('line_ids')
    def _compute_totals(self):
        for rec in self:
            rec.total_invoices = len(rec.line_ids)
            rec.total_revenue = sum(rec.line_ids.mapped('total_amount'))

    def action_generate_invoices(self):
        self.ensure_one()
        generated_invoices = self.env['account.move']
        for preview_line in self.line_ids:
            invoice = preview_line._generate_consolidated_invoice()
            if invoice:
                generated_invoices |= invoice
        
        if not generated_invoices:
            raise UserError("No invoices were generated. This may be because all subscriptions have already been invoiced for this period.")

        # Return an action to view the newly created invoices
        return {
            'type': 'ir.actions.act_window',
            'name': 'Generated Invoices',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', generated_invoices.ids)],
        }


class BulkBillingPreviewLine(models.TransientModel):
    _name = 'bulk.billing.preview.line'
    _description = 'Bulk Billing Preview Line (per Parent)'

    preview_id = fields.Many2one('bulk.billing.preview', ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string='Parent/Bill To', readonly=True)
    total_amount = fields.Float(string='Total Invoice Amount', readonly=True)
    detail_ids = fields.One2many('bulk.billing.preview.detail', 'line_id', string='Invoice Details')
    subscription_ids = fields.Many2many('tuition.subscription', string='Subscriptions', readonly=True)
    has_existing_invoice = fields.Boolean(string='Invoice Exists', compute='_compute_has_existing_invoice')

    @api.depends('partner_id', 'preview_id.month', 'preview_id.year')
    def _compute_has_existing_invoice(self):
        import calendar
        for rec in self:
            if not rec.partner_id or not rec.preview_id:
                rec.has_existing_invoice = False
                continue
            month = int(rec.preview_id.month)
            year = rec.preview_id.year
            start_date = fields.Date.to_date(f'{year}-{month:02d}-01')
            last_day = calendar.monthrange(year, month)[1]
            end_date = fields.Date.to_date(f'{year}-{month:02d}-{last_day}')
            
            existing = self.env['account.move'].search_count([
                ('partner_id', '=', rec.partner_id.id),
                ('move_type', '=', 'out_invoice'),
                ('state', '!=', 'cancel'),
                ('invoice_date', '>=', start_date),
                ('invoice_date', '<=', end_date)
            ])
            rec.has_existing_invoice = existing > 0

    def _generate_consolidated_invoice(self):
        self.ensure_one()
        
        all_lines = []
        all_unapplied_adjustments = self.env['tuition.adjustment']
        
        for sub in self.subscription_ids:
            try:
                preview_vals = sub._build_preview_vals()
                all_lines.extend(preview_vals.get('lines', []))
                if preview_vals.get('unapplied_adj_ids'):
                    all_unapplied_adjustments |= self.env['tuition.adjustment'].browse(preview_vals.get('unapplied_adj_ids'))
            except UserError:
                continue
        
        if not all_lines:
            return self.env['account.move']

        # Create a single Sale Order for the parent
        payment_term = self.env['account.payment.term'].sudo().search([('name', 'ilike', '15')], limit=1)
        misc_product = self.env['product.product'].sudo().search([('type', '=', 'service')], limit=1)
        
        order_lines = []
        for line in all_lines:
            product = self.env['product.product'].sudo().browse(line['product_id']) if line.get('product_id') else misc_product
            if not product: continue
            order_lines.append((0, 0, {
                'product_id': product.id,
                'product_uom_qty': line['quantity'],
                'price_unit': line['unit_price'],
                'name': line['description']
            }))

        month_str = f"{calendar.month_name[int(self.preview_id.month)]} {self.preview_id.year}"
        order = self.env['sale.order'].sudo().create({
            'partner_id': self.partner_id.id,
            'payment_term_id': payment_term.id if payment_term else False,
            'order_line': order_lines,
            'note': f'Consolidated Tuition Invoice for {month_str}',
            'tuition_subscription_ids': [(6, 0, self.subscription_ids.ids)],
        })
        order.action_confirm()

        # Create and post the invoice
        invoice = order._create_invoices()
        
        # Link the invoice explicitly to the parent so the portal can see it purely by partner_id
        parent_profile = self.env['parent.profile'].sudo().search([('partner_id', '=', self.partner_id.id)], limit=1)
        invoice.sudo().write({
            'tuition_subscription_ids': [(6, 0, self.subscription_ids.ids)],
            'parent_profile_id': parent_profile.id if parent_profile else False,
        })
        
        invoice.sudo().action_post()

        # Mark adjustments as applied and update next billing dates
        if all_unapplied_adjustments:
            all_unapplied_adjustments.write({'applied_in_invoice': True, 'invoice_id': invoice.id})
        
        billing_date = fields.Date.to_date(f'{self.preview_id.year}-{self.preview_id.month}-01')
        next_billing_date = billing_date + relativedelta(months=1)
        self.subscription_ids.write({'next_billing_date': next_billing_date})

        return invoice

class BulkBillingPreviewDetail(models.TransientModel):
    _name = 'bulk.billing.preview.detail'
    _description = 'Bulk Billing Preview Detail (per Subscription Line)'

    line_id = fields.Many2one('bulk.billing.preview.line', ondelete='cascade')
    student_id = fields.Many2one('student.profile', string='Student', readonly=True)
    course_name = fields.Char(string='Course', readonly=True)
    description = fields.Char(string='Description', readonly=True)
    unit_price = fields.Float(string='Amount', readonly=True)
    subtotal = fields.Float(string='Subtotal', readonly=True)
