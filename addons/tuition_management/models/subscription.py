# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from dateutil.relativedelta import relativedelta
from datetime import date


class TuitionSubscription(models.Model):
    _name = 'tuition.subscription'
    _description = 'Tuition Subscription'
    _order = 'create_date desc'

    name = fields.Char(string='Reference', compute='_compute_name', store=True)
    student_id = fields.Many2one('student.profile', string='Student', required=True, ondelete='restrict')
    enrollment_id = fields.Many2one('course.enrollment', string='Enrollment', ondelete='restrict',
                                    domain="[('student_id', '=', student_id)]")
    plan_line_ids = fields.One2many('tuition.plan.line', 'subscription_id', string='Plan History')
    adjustment_ids = fields.One2many('tuition.adjustment', 'subscription_id', string='Adjustments')
    invoice_ids = fields.Many2many('account.move', 'account_move_tuition_subscription_rel', 'subscription_id', 'move_id', string='Invoices')
    discount_ids = fields.One2many('tuition.discount', 'subscription_id', string='Discounts')
    current_plan_id = fields.Many2one('tuition.plan.line', string='Current Plan', compute='_compute_current_plan', store=False)
    current_plan_product = fields.Char(string='Current Plan', compute='_compute_current_plan', store=False)
    current_plan_price = fields.Float(string='Monthly Price', compute='_compute_current_plan', store=False)
    next_billing_date = fields.Date(string='Next Billing Date')
    state = fields.Selection([('active', 'Active'), ('paused', 'Paused'), ('cancelled', 'Cancelled')],
                             string='Status', default='active', required=True)
    invoice_count = fields.Integer(compute='_compute_invoice_count', string='Invoices')
    unapplied_adjustment_count = fields.Integer(compute='_compute_unapplied_adjustments', string='Pending Adjustments')
    total_adjustments_applied = fields.Float(compute='_compute_totals', string='Total Adjustments Applied')
    monthly_revenue = fields.Float(compute='_compute_totals', string='Monthly Revenue')

    @api.depends('student_id', 'enrollment_id')
    def _compute_name(self):
        for rec in self:
            parts = [p for p in [rec.student_id.name, rec.enrollment_id.course_id.name if rec.enrollment_id else ''] if p]
            rec.name = ' / '.join(parts) if parts else 'New Subscription'

    @api.depends('plan_line_ids', 'plan_line_ids.state', 'plan_line_ids.start_date', 'plan_line_ids.end_date')
    def _compute_current_plan(self):
        today = fields.Date.today()
        for rec in self:
            plans = rec.plan_line_ids.filtered(lambda p: p.state == 'active' and p.start_date <= today and (not p.end_date or p.end_date >= today))
            plan = plans[0] if plans else False
            rec.current_plan_id = plan.id if plan else False
            rec.current_plan_product = plan.product_id.name if plan else ''
            rec.current_plan_price = plan.price if plan else 0.0

    def _compute_invoice_count(self):
        for rec in self:
            rec.invoice_count = len(rec.invoice_ids)

    def _compute_unapplied_adjustments(self):
        for rec in self:
            rec.unapplied_adjustment_count = len(rec.adjustment_ids.filtered(lambda a: not a.applied_in_invoice))

    def _compute_totals(self):
        for rec in self:
            rec.total_adjustments_applied = sum(rec.adjustment_ids.filtered(lambda a: a.applied_in_invoice).mapped('amount'))
            rec.monthly_revenue = rec.current_plan_id.price if rec.current_plan_id else 0.0

    def action_view_invoices(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': 'Invoices', 'res_model': 'account.move',
                'view_mode': 'list,form', 'domain': [('id', 'in', self.invoice_ids.ids)]}

    def action_generate_invoice(self):
        self.ensure_one()
        today = fields.Date.today()
        # check both via many2one and many2many
        existing = self.env['account.move'].sudo().search([
            '|', ('tuition_subscription_id', '=', self.id),
                 ('tuition_subscription_ids', 'in', [self.id]),
            ('invoice_date', '>=', today.replace(day=1)), ('state', '!=', 'cancel'),
        ], limit=1)
        if existing:
            return {
                'type': 'ir.actions.act_window', 'name': 'Duplicate Invoice Warning',
                'res_model': 'tuition.invoice.confirm.wizard', 'view_mode': 'form', 'target': 'new',
                'context': {
                    'default_subscription_id': self.id, 'default_existing_invoice_id': existing.id,
                    'default_existing_invoice_name': existing.name, 'default_existing_invoice_date': str(existing.invoice_date),
                    'default_existing_invoice_amount': existing.amount_total, 'default_existing_invoice_state': existing.payment_state,
                },
            }
        return self._open_invoice_preview()

    def _open_invoice_preview(self):
        self.ensure_one()
        preview_vals = self._build_preview_vals()
        wizard = self.env['tuition.invoice.preview.wizard'].create({
            'subscription_id': self.id, 'partner_id': preview_vals['partner_id'],
            'month_label': preview_vals['month_label'], 'base_price': preview_vals['base_price'],
            'total_discounts': preview_vals['total_discounts'], 'total_adjustments': preview_vals['total_adjustments'],
            'total_amount': preview_vals['total_amount'], 'line_ids': [(0, 0, l) for l in preview_vals['lines']],
        })
        return {'type': 'ir.actions.act_window', 'name': 'Invoice Preview',
                'res_model': 'tuition.invoice.preview.wizard', 'view_mode': 'form', 'res_id': wizard.id, 'target': 'new'}

    def _build_preview_vals(self):
        self.ensure_one()
        if self.state != 'active':
            raise UserError("Cannot generate invoice for a %s subscription." % self.state)
        plan = self.current_plan_id
        if not plan:
            raise UserError("No active plan for subscription %s." % self.name)
        partner = self.student_id.partner_id
        if not partner:
            raise UserError("Student %s has no linked contact." % self.student_id.name)
        billing_partner = partner
        parent_profile = self.env['parent.profile'].sudo().search([('student_ids', 'in', [self.student_id.id])], limit=1)
        if parent_profile and parent_profile.partner_id:
            billing_partner = parent_profile.partner_id
        month_label = fields.Date.today().strftime('%B %Y')
        base_price = plan.price
        lines = [{'description': '%s - %s' % (plan.product_id.name, month_label), 'product_id': plan.product_id.id,
                  'quantity': 1, 'unit_price': base_price, 'subtotal': base_price, 'line_type': 'plan'}]
        total_discounts = 0.0
        today = fields.Date.today()
        for disc in self.discount_ids.filtered(lambda d: d.active and (not d.date_start or d.date_start <= today) and (not d.date_end or d.date_end >= today)):
            disc_amount = disc._compute_discount_amount(base_price)
            if disc_amount:
                label = '[Discount] %s' % disc.name
                if disc.discount_type == 'percentage': label += ' (%.2f%%)' % disc.value
                lines.append({'description': label, 'product_id': False, 'quantity': 1,
                              'unit_price': -abs(disc_amount), 'subtotal': -abs(disc_amount), 'line_type': 'discount'})
                total_discounts += abs(disc_amount)
        total_adjustments = 0.0
        unapplied = self.adjustment_ids.filtered(lambda a: not a.applied_in_invoice)
        for adj in unapplied:
            lines.append({'description': '[%s] %s' % (dict(adj._fields['adjustment_type'].selection).get(adj.adjustment_type, ''), adj.description),
                          'product_id': False, 'quantity': 1, 'unit_price': adj.signed_amount, 'subtotal': adj.signed_amount, 'line_type': 'adjustment'})
            total_adjustments += adj.signed_amount
        return {'partner_id': billing_partner.id, 'month_label': month_label, 'base_price': base_price,
                'total_discounts': total_discounts, 'total_adjustments': total_adjustments,
                'total_amount': base_price - total_discounts + total_adjustments,
                'lines': lines, 'plan_id': plan.id, 'unapplied_adj_ids': unapplied.ids}

    def _generate_invoice(self):
        self.ensure_one()
        preview_vals = self._build_preview_vals()
        self._create_sale_order(preview_vals)
        today = fields.Date.today()
        self.next_billing_date = today.replace(day=1) + relativedelta(months=1)

    def _create_sale_order(self, preview_vals):
        self.ensure_one()
        payment_term = self.env['account.payment.term'].sudo().search([('name', 'ilike', '15')], limit=1)
        if not payment_term:
            payment_term = self.env['account.payment.term'].sudo().search([], limit=1)
        misc_product = self.env['product.product'].sudo().search([('type', '=', 'service')], limit=1)
        order_lines = []
        for line in preview_vals['lines']:
            product = self.env['product.product'].sudo().browse(line['product_id']) if line.get('product_id') else misc_product
            if not product: continue
            order_lines.append((0, 0, {'product_id': product.id, 'product_uom_qty': line['quantity'],
                                       'price_unit': line['unit_price'], 'name': line['description']}))
        order = self.env['sale.order'].sudo().create({
            'partner_id': preview_vals['partner_id'], 'payment_term_id': payment_term.id if payment_term else False,
            'tuition_subscription_id': self.id,
            'tuition_subscription_ids': [(4, self.id)],
            'order_line': order_lines,
            'note': 'Tuition: %s | %s' % (self.student_id.name, preview_vals['month_label']),
        })
        order.action_confirm()
        invoice = self.env['account.move'].sudo().search([('invoice_origin', 'like', order.name), ('move_type', '=', 'out_invoice')], limit=1)
        if not invoice: invoice = order._create_invoices()
        invoice.sudo().write({
            'tuition_subscription_id': self.id,
            'tuition_subscription_ids': [(4, self.id)],
            'tuition_plan_line_id': preview_vals.get('plan_id')
        })
        invoice.sudo().action_post()
        if preview_vals.get('unapplied_adj_ids'):
            self.env['tuition.adjustment'].browse(preview_vals['unapplied_adj_ids']).write({'applied_in_invoice': True, 'invoice_id': invoice.id})
        return order

    def action_pause(self): self.write({'state': 'paused'})
    def action_activate(self): self.write({'state': 'active'})
    def action_cancel(self): self.write({'state': 'cancelled'})

    def action_schedule_plan_change(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': 'Schedule Plan Change',
                'res_model': 'tuition.plan.change.wizard', 'view_mode': 'form', 'target': 'new',
                'context': {'default_subscription_id': self.id}}

    def action_add_adjustment(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': 'Add Adjustment',
                'res_model': 'tuition.adjustment.wizard', 'view_mode': 'form', 'target': 'new',
                'context': {'default_subscription_id': self.id}}

    @api.model
    def _cron_generate_monthly_invoices(self):
        today = fields.Date.today()
        for sub in self.search([('state', '=', 'active'), ('next_billing_date', '<=', today)]):
            try:
                sub._generate_invoice()
            except Exception as e:
                self.env['ir.logging'].sudo().create({
                    'name': 'tuition.subscription', 'type': 'server', 'level': 'ERROR',
                    'message': 'Invoice failed for %s: %s' % (sub.name, str(e)),
                    'path': 'models/subscription.py', 'func': '_cron_generate_monthly_invoices', 'line': '0',
                })


class TuitionDiscount(models.Model):
    _name = 'tuition.discount'
    _description = 'Tuition Subscription Discount'
    _order = 'date_start desc'

    subscription_id = fields.Many2one('tuition.subscription', required=True, ondelete='cascade')
    name = fields.Char(string='Discount Name', required=True)
    discount_type = fields.Selection([('percentage', 'Percentage (%)'), ('amount', 'Fixed Amount')],
                                     string='Type', required=True, default='percentage')
    value = fields.Float(string='Value', required=True)
    date_start = fields.Date(string='From', default=fields.Date.today)
    date_end = fields.Date(string='Until')
    active = fields.Boolean(string='Active', default=True)
    description = fields.Char(string='Notes')

    def _compute_discount_amount(self, base_price):
        self.ensure_one()
        return base_price * (self.value / 100.0) if self.discount_type == 'percentage' else abs(self.value)


class TuitionPlanLine(models.Model):
    _name = 'tuition.plan.line'
    _description = 'Tuition Plan Line'
    _order = 'start_date desc'

    subscription_id = fields.Many2one('tuition.subscription', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Plan Product', required=True)
    price = fields.Float(string='Monthly Price', required=True)
    classes_per_week = fields.Integer(string='Classes per Week', required=True, default=1)
    start_date = fields.Date(string='Start Date', required=True)
    end_date = fields.Date(string='End Date')
    state = fields.Selection([('active', 'Active'), ('scheduled', 'Scheduled'), ('expired', 'Expired')],
                             string='Status', compute='_compute_state', store=True)
    notes = fields.Char(string='Notes')
    has_invoices = fields.Boolean(string='Has Invoices', compute='_compute_has_invoices', store=False)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.price = self.product_id.lst_price or 0.0
            tmpl = self.product_id.product_tmpl_id
            if tmpl and tmpl.tuition_classes_per_week:
                self.classes_per_week = tmpl.tuition_classes_per_week

    @api.depends('start_date', 'end_date')
    def _compute_state(self):
        today = fields.Date.today()
        for rec in self:
            if rec.start_date and rec.start_date > today: rec.state = 'scheduled'
            elif rec.end_date and rec.end_date < today: rec.state = 'expired'
            else: rec.state = 'active'

    def _compute_has_invoices(self):
        for rec in self:
            rec.has_invoices = bool(self.env['account.move'].sudo().search([
                '|', ('tuition_subscription_id', '=', rec.subscription_id.id),
                     ('tuition_subscription_ids', 'in', [rec.subscription_id.id]),
                ('tuition_plan_line_id', '=', rec.id), ('state', '!=', 'cancel'),
            ], limit=1))

    def unlink(self):
        for rec in self:
            if self.env['account.move'].sudo().search([
                '|', ('tuition_subscription_id', '=', rec.subscription_id.id),
                     ('tuition_subscription_ids', 'in', [rec.subscription_id.id]),
                ('tuition_plan_line_id', '=', rec.id), ('state', '!=', 'cancel')
            ], limit=1):
                raise UserError("Cannot delete plan '%s' because it has invoices linked to it." % (rec.product_id.name or 'plan'))
        return super().unlink()

    @api.constrains('start_date')
    def _check_start_date(self):
        for rec in self:
            if rec.start_date and rec.start_date.day != 1:
                raise ValidationError("Plan start date must be the 1st of a month. Got: %s" % rec.start_date)

    @api.constrains('subscription_id', 'start_date', 'end_date')
    def _check_no_overlapping_plans(self):
        far_future = date(9999, 12, 31)
        for rec in self:
            if not rec.subscription_id or not rec.start_date:
                continue
            start = rec.start_date
            end = rec.end_date or far_future
            others = self.search([
                ('id', '!=', rec.id),
                ('subscription_id', '=', rec.subscription_id.id),
                ('start_date', '!=', False),
            ])
            for o in others:
                o_start = o.start_date
                o_end = o.end_date or far_future
                # overlap if ranges intersect
                if o_start <= end and start <= o_end:
                    raise ValidationError(
                        "Plan dates overlap with another plan (%s). Only one plan may be active at the same time for a subscription." % (o.product_id.name or 'plan')
                    )

    def write(self, vals):
        if 'start_date' in vals:
            for rec in self:
                if self.env['account.move'].sudo().search([('tuition_plan_line_id', '=', rec.id), ('state', '!=', 'cancel')], limit=1):
                    raise UserError("Cannot change start date of plan '%s' because it already has invoices." % (rec.product_id.name or 'plan'))
        return super().write(vals)


class TuitionAdjustment(models.Model):
    _name = 'tuition.adjustment'
    _description = 'Tuition Manual Adjustment'
    _order = 'date desc'

    subscription_id = fields.Many2one('tuition.subscription', required=True, ondelete='cascade')
    student_id = fields.Many2one('student.profile', related='subscription_id.student_id', store=True)
    date = fields.Date(string='Date', required=True, default=fields.Date.today)
    description = fields.Char(string='Description', required=True)
    amount = fields.Float(string='Amount', required=True)
    adjustment_type = fields.Selection([
        ('extra_charge', 'Extra Charge'), ('discount', 'Discount'), ('refund', 'Refund to Customer'),
    ], string='Type', default='extra_charge', required=True)
    signed_amount = fields.Float(string='Signed Amount', compute='_compute_signed_amount', store=True)
    applied_in_invoice = fields.Boolean(string='Applied', default=False)
    invoice_id = fields.Many2one('account.move', string='Invoice', readonly=True)

    @api.depends('amount', 'adjustment_type')
    def _compute_signed_amount(self):
        for rec in self:
            rec.signed_amount = abs(rec.amount) if rec.adjustment_type == 'extra_charge' else -abs(rec.amount)


class AccountMoveTuitionExt(models.Model):
    _inherit = 'account.move'

    tuition_subscription_id = fields.Many2one('tuition.subscription', string='Tuition Subscription', ondelete='set null', index=True)
    tuition_subscription_ids = fields.Many2many('tuition.subscription', 'account_move_tuition_subscription_rel', 'move_id', 'subscription_id', string='Tuition Subscriptions')
    tuition_plan_line_id = fields.Many2one('tuition.plan.line', string='Tuition Plan', ondelete='set null', index=True)


class SaleOrderTuitionExt(models.Model):
    _inherit = 'sale.order'

    tuition_subscription_id = fields.Many2one('tuition.subscription', string='Tuition Subscription', ondelete='set null', index=True)
    tuition_subscription_ids = fields.Many2many('tuition.subscription', 'sale_order_tuition_subscription_rel', 'order_id', 'subscription_id', string='Tuition Subscriptions')


class TuitionPlanChangeWizard(models.TransientModel):
    _name = 'tuition.plan.change.wizard'
    _description = 'Schedule Plan Change'

    subscription_id = fields.Many2one('tuition.subscription', required=True)
    product_id = fields.Many2one('product.product', string='New Plan Product', required=True)
    price = fields.Float(string='Monthly Price', required=True)
    classes_per_week = fields.Integer(string='Classes per Week', required=True, default=1)
    start_date = fields.Date(string='Effective From', compute='_compute_start_date', store=True, readonly=False)
    notes = fields.Char(string='Notes')

    @api.depends('subscription_id')
    def _compute_start_date(self):
        first_next = fields.Date.today().replace(day=1) + relativedelta(months=1)
        for rec in self: rec.start_date = first_next

    @api.onchange('product_id')
    def _onchange_product(self):
        if self.product_id:
            self.price = self.product_id.lst_price or 0.0
            tmpl = self.product_id.product_tmpl_id
            if tmpl and tmpl.tuition_classes_per_week:
                self.classes_per_week = tmpl.tuition_classes_per_week

    def action_confirm(self):
        self.ensure_one()
        sub = self.subscription_id
        if self.start_date.day != 1:
            raise UserError("Plan change must start on the 1st of a month.")
        today = fields.Date.today()
        end_prev = self.start_date - relativedelta(days=1)
        current = sub.plan_line_ids.filtered(lambda p: p.state == 'active' and (not p.end_date or p.end_date >= today))
        if current: current[0].write({'end_date': end_prev})
        scheduled = sub.plan_line_ids.filtered(lambda p: p.state == 'scheduled')
        if scheduled: scheduled.write({'end_date': end_prev})
        self.env['tuition.plan.line'].create({'subscription_id': sub.id, 'product_id': self.product_id.id,
                                              'price': self.price, 'classes_per_week': self.classes_per_week,
                                              'start_date': self.start_date, 'notes': self.notes or ''})
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': 'Plan Change Scheduled',
                           'message': "Plan '%s' effective from %s." % (self.product_id.name, self.start_date.strftime('%d %b %Y')),
                           'type': 'success', 'sticky': False, 'next': {'type': 'ir.actions.act_window_close'}}}


class TuitionInvoicePreviewWizardLine(models.TransientModel):
    _name = 'tuition.invoice.preview.wizard.line'
    _description = 'Invoice Preview Line'

    wizard_id = fields.Many2one('tuition.invoice.preview.wizard', ondelete='cascade')
    description = fields.Char(string='Description', readonly=True)
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    quantity = fields.Float(string='Qty', readonly=True, default=1)
    unit_price = fields.Float(string='Unit Price', readonly=True)
    subtotal = fields.Float(string='Subtotal', readonly=True)
    line_type = fields.Char(string='Type', readonly=True)


class TuitionInvoicePreviewWizard(models.TransientModel):
    _name = 'tuition.invoice.preview.wizard'
    _description = 'Invoice Preview'

    subscription_id = fields.Many2one('tuition.subscription', required=True)
    partner_id = fields.Many2one('res.partner', string='Bill To', readonly=True)
    month_label = fields.Char(string='Billing Month', readonly=True)
    base_price = fields.Float(string='Base Price', readonly=True)
    total_discounts = fields.Float(string='Total Discounts', readonly=True)
    total_adjustments = fields.Float(string='Total Adjustments', readonly=True)
    total_amount = fields.Float(string='Total Amount', readonly=True)
    line_ids = fields.One2many('tuition.invoice.preview.wizard.line', 'wizard_id', string='Lines')

    def action_confirm(self):
        self.ensure_one()
        sub = self.subscription_id
        preview_vals = sub._build_preview_vals()
        order = sub._create_sale_order(preview_vals)
        today = fields.Date.today()
        sub.next_billing_date = today.replace(day=1) + relativedelta(months=1)
        invoice = self.env['account.move'].sudo().search([('tuition_subscription_id', '=', sub.id),
                                                          ('move_type', '=', 'out_invoice'), ('state', '=', 'posted')],
                                                         order='id desc', limit=1)
        if invoice:
            return {'type': 'ir.actions.act_window', 'name': 'Invoice', 'res_model': 'account.move', 'view_mode': 'form', 'res_id': invoice.id}
        return {'type': 'ir.actions.act_window', 'name': 'Sale Order', 'res_model': 'sale.order', 'view_mode': 'form', 'res_id': order.id}

    def action_discard(self):
        return {'type': 'ir.actions.act_window_close'}


class TuitionInvoiceConfirmWizard(models.TransientModel):
    _name = 'tuition.invoice.confirm.wizard'
    _description = 'Duplicate Invoice Warning'

    subscription_id = fields.Many2one('tuition.subscription', required=True)
    existing_invoice_id = fields.Many2one('account.move', string='Existing Invoice', readonly=True)
    existing_invoice_name = fields.Char(string='Invoice #', readonly=True)
    existing_invoice_date = fields.Char(string='Invoice Date', readonly=True)
    existing_invoice_amount = fields.Float(string='Amount', readonly=True)
    existing_invoice_state = fields.Char(string='Payment State', readonly=True)

    def action_proceed(self):
        self.ensure_one()
        return self.subscription_id._open_invoice_preview()

    def action_cancel(self):
        return {'type': 'ir.actions.act_window_close'}


class TuitionAdjustmentWizard(models.TransientModel):
    _name = 'tuition.adjustment.wizard'
    _description = 'Add Manual Adjustment'

    subscription_id = fields.Many2one('tuition.subscription', required=True)
    adjustment_type = fields.Selection([
        ('extra_charge', 'Extra Charge'), ('discount', 'Discount'), ('refund', 'Refund to Customer'),
    ], string='Type', required=True, default='extra_charge')
    description = fields.Char(string='Description', required=True)
    amount = fields.Float(string='Amount', required=True)
    date = fields.Date(string='Date', default=fields.Date.today, required=True)

    def action_confirm(self):
        self.ensure_one()
        self.env['tuition.adjustment'].create({'subscription_id': self.subscription_id.id, 'date': self.date,
                                               'description': self.description, 'amount': abs(self.amount),
                                               'adjustment_type': self.adjustment_type})
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': 'Adjustment Added', 'message': "Adjustment '%s' added." % self.description,
                           'type': 'success', 'sticky': False, 'next': {'type': 'ir.actions.act_window_close'}}}
