# -*- coding: utf-8 -*-
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
        default=lambda self: str((fields.Date.today() - relativedelta(months=1)).month)
    )
    year = fields.Integer(
        string='Billing Year',
        required=True,
        default=lambda self: (fields.Date.today() - relativedelta(months=1)).year
    )

    def action_preview_invoices(self):
        self.ensure_one()
        # Default to first of the month
        billing_date = fields.Date.to_date(f'{self.year}-{self.month}-01')
        last_day = calendar.monthrange(self.year, int(self.month))[1]
        period_end = fields.Date.to_date(f'{self.year}-{self.month}-{last_day}')
        
        # Find active subscriptions billing this month OR strictly before period end
        subs_to_bill = self.env['tuition.subscription'].search([
            ('state', '=', 'active'),
            ('next_billing_date', '<=', period_end)
        ])

        if not subs_to_bill:
            raise UserError("No active subscriptions found for billing in the selected period (due on or before %s)." % period_end)

        invoices_by_parent = {}
        missing_contacts_students = []
        
        for sub in subs_to_bill:
            # Determine billing partner:
            # 1) Parent profile linked to the student
            billing_partner = False
            parent_profile = self.env['parent.profile'].sudo().search([('student_ids', 'in', [sub.student_id.id])], limit=1)
            if parent_profile and parent_profile.partner_id:
                billing_partner = parent_profile.partner_id
            
            # 2) Fallback: Contact linked directly to the student
            if not billing_partner and sub.student_id.partner_id:
                billing_partner = sub.student_id.partner_id

            if not billing_partner:
                missing_contacts_students.append(sub.student_id.name or 'Unknown Student')
                continue # Cannot bill without a contact

            if billing_partner.id not in invoices_by_parent:
                invoices_by_parent[billing_partner.id] = {
                    'partner_id': billing_partner.id,
                    'subscription_ids': [],
                    'total_amount': 0.0,
                }
            invoices_by_parent[billing_partner.id]['subscription_ids'].append(sub.id)

        if not invoices_by_parent:
            raise UserError(
                "Could not determine a billing partner for any of the due subscriptions.\n\n"
                "The following students are missing a linked Contact (or their Parent is missing a linked Contact):\n- " 
                + "\n- ".join(set(missing_contacts_students))
            )

        # Create preview records
        preview_lines = []
        for partner_id, data in invoices_by_parent.items():
            line_details = []
            total_invoice_amount = 0
            
            subscriptions = self.env['tuition.subscription'].browse(data['subscription_ids'])
            for sub in subscriptions:
                try:
                    # Use existing logic to get preview values for each subscription
                    preview_vals = sub._build_preview_vals()
                    total_invoice_amount += preview_vals.get('total_amount', 0.0)
                    
                    # Create detailed lines for this subscription
                    for line in preview_vals.get('lines', []):
                        line_details.append((0, 0, {
                            'student_id': sub.student_id.id,
                            'course_name': sub.enrollment_id.course_id.name or '',
                            'description': line.get('description'),
                            'unit_price': line.get('unit_price'),
                            'subtotal': line.get('subtotal'),
                        }))
                except UserError:
                    # Skip subs that can't be billed (e.g., no active plan)
                    continue

            if line_details:
                preview_lines.append((0, 0, {
                    'partner_id': partner_id,
                    'total_amount': total_invoice_amount,
                    'detail_ids': line_details,
                    'subscription_ids': [(6, 0, subscriptions.ids)]
                }))

        if not preview_lines:
            raise UserError("No billable lines could be generated for the selected period. Ensure subscriptions have active plans.")

        # Create the parent preview record
        preview = self.env['bulk.billing.preview'].create({
            'month': self.month,
            'year': self.year,
            'line_ids': preview_lines,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': f'Invoice Preview - {calendar.month_name[int(self.month)]} {self.year}',
            'res_model': 'bulk.billing.preview',
            'view_mode': 'form',
            'res_id': preview.id,
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
