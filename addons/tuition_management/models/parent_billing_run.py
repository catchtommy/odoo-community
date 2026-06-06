# -*- coding: utf-8 -*-
import calendar
from datetime import date
from dateutil.relativedelta import relativedelta
from odoo import api, fields, models
from odoo.exceptions import UserError
from .user_permission import require_permission


class ParentBillingRun(models.Model):
    """
    Persistent parent invoicing run — mirrors TutorPaymentRun.
    Flow: draft → preview → approved → invoiced
    Invoices are only created AFTER admin approval.
    """
    _name = 'parent.billing.run'
    _description = 'Parent Invoicing Run'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'year desc, month desc, id desc'

    name = fields.Char(
        string='Reference', required=True, copy=False,
        readonly=True, default='New',
    )
    month = fields.Selection(
        selection=[(str(i), calendar.month_name[i]) for i in range(1, 13)],
        string='Billing Month', required=True, tracking=True,
    )
    year = fields.Integer(string='Billing Year', required=True, tracking=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        today = date.today()
        if 'month' in fields_list and 'month' not in res:
            res['month'] = str(today.month)
        if 'year' in fields_list and not res.get('year'):
            res['year'] = today.year
        return res
    period_label = fields.Char(string='Period', compute='_compute_period_label', store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('preview', 'Preview'),
        ('approved', 'Approved'),
        ('invoiced', 'Invoiced'),
    ], string='Status', default='draft', required=True, tracking=True)

    line_ids = fields.One2many('parent.billing.run.line', 'run_id', string='Billing Lines')

    total_parents = fields.Integer(string='Total Parents', compute='_compute_totals', store=True)
    total_lines = fields.Integer(string='Total Lines', compute='_compute_totals', store=True)
    total_amount = fields.Float(string='Total Amount', compute='_compute_totals', store=True)

    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id,
    )
    notes = fields.Text(string='Notes')

    created_by = fields.Many2one(
        'res.users', string='Created By',
        default=lambda self: self.env.user, readonly=True,
    )
    created_date = fields.Datetime(
        string='Created Date', default=fields.Datetime.now, readonly=True,
    )
    approved_by = fields.Many2one('res.users', string='Approved By', readonly=True, tracking=True)
    approved_date = fields.Datetime(string='Approved Date', readonly=True)
    invoiced_by = fields.Many2one('res.users', string='Invoiced By', readonly=True, tracking=True)
    invoiced_date = fields.Datetime(string='Invoiced Date', readonly=True)

    @api.depends('month', 'year')
    def _compute_period_label(self):
        for rec in self:
            if rec.month and rec.year:
                rec.period_label = f"{calendar.month_name[int(rec.month)]} {rec.year}"
            else:
                rec.period_label = ''

    @api.depends('line_ids.total_amount', 'line_ids.state')
    def _compute_totals(self):
        for rec in self:
            included = rec.line_ids.filtered(lambda l: l.state == 'included')
            rec.total_parents = len(included)
            rec.total_lines = len(rec.line_ids)
            rec.total_amount = sum(included.mapped('total_amount'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('parent.billing.run') or 'New'
                )
        return super().create(vals_list)

    @api.constrains('month', 'year')
    def _check_unique_period(self):
        for rec in self:
            if not rec.month or not rec.year:
                continue
            duplicate = self.search([
                ('id', '!=', rec.id),
                ('month', '=', rec.month),
                ('year', '=', rec.year),
            ], limit=1)
            if duplicate:
                period = f"{calendar.month_name[int(rec.month)]} {rec.year}"
                raise UserError(
                    f"A parent invoicing run already exists for {period} (Ref: {duplicate.name}). "
                    f"Please open the existing run instead of creating a new one."
                )

    def write(self, vals):
        if {'month', 'year'} & set(vals):
            locked = self.filtered(lambda r: r.state in ('approved', 'invoiced'))
            if locked:
                raise UserError("Approved or invoiced billing runs cannot have their period changed.")
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda r: r.state in ('approved', 'invoiced')):
            raise UserError("Approved or invoiced billing runs cannot be deleted.")
        return super().unlink()

    # ──────────────────────────────────────────────
    #  Actions
    # ──────────────────────────────────────────────

    def action_generate_preview(self):
        """Build billing lines from subscriptions due in the period."""
        for run in self:
            require_permission(self.env.user, 'parent_invoice_generate')
            if run.state not in ('draft', 'preview'):
                raise UserError("Only Draft or Preview runs can be regenerated.")
            run.line_ids.unlink()
            run._build_billing_lines()
            run.write({'state': 'preview'})
            run.message_post(
                body='Preview generated by <b>%s</b>. %d parent(s) found.' % (
                    self.env.user.name, len(run.line_ids)
                ),
                subtype_xmlid='mail.mt_note',
            )
        return True

    def action_approve(self):
        """Admin reviews and approves — does NOT yet create invoices."""
        require_permission(self.env.user, 'parent_invoice_approve')
        for run in self:
            if run.state != 'preview':
                raise UserError("Only Preview runs can be approved.")
            if not run.line_ids.filtered(lambda l: l.state == 'included'):
                raise UserError("There are no included lines to approve. "
                                "Generate a preview with at least one included line first.")
            run.write({
                'state': 'approved',
                'approved_by': self.env.user.id,
                'approved_date': fields.Datetime.now(),
            })
            run.message_post(
                body='Billing run <b>approved</b> by <b>%s</b>. Ready to generate invoices.' % self.env.user.name,
                subtype_xmlid='mail.mt_note',
            )
        return True

    def action_generate_invoices(self):
        """Create Odoo invoices for all included lines (only available after Approved)."""
        self.ensure_one()
        if self.state != 'approved':
            raise UserError("Only Approved billing runs can generate invoices.")

        included_lines = self.line_ids.filtered(lambda l: l.state == 'included')
        if not included_lines:
            raise UserError("No included billing lines to invoice.")

        generated_invoices = self.env['account.move']
        for line in included_lines:
            invoice = line._generate_invoice()
            if invoice:
                generated_invoices |= invoice

        if not generated_invoices:
            raise UserError(
                "No invoices were generated. This may be because all subscriptions "
                "have already been invoiced for this period."
            )

        self.write({
            'state': 'invoiced',
            'invoiced_by': self.env.user.id,
            'invoiced_date': fields.Datetime.now(),
        })
        self.message_post(
            body='<b>%d invoice(s)</b> generated by <b>%s</b>.' % (
                len(generated_invoices), self.env.user.name
            ),
            subtype_xmlid='mail.mt_note',
        )

        return {
            'type': 'ir.actions.act_window',
            'name': 'Generated Invoices',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', generated_invoices.ids)],
        }

    def action_reset_to_draft(self):
        for run in self:
            if run.state not in ('draft', 'preview'):
                raise UserError("Only Draft or Preview runs can be reset to Draft.")
            run.line_ids.unlink()
            run.write({'state': 'draft'})
            run.message_post(body='Reset to Draft.', subtype_xmlid='mail.mt_note')
        return True

    def action_view_invoices(self):
        """Open all invoices linked to this billing run."""
        self.ensure_one()
        invoice_ids = self.line_ids.mapped('invoice_id').ids
        return {
            'type': 'ir.actions.act_window',
            'name': 'Invoices',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', invoice_ids)],
        }

    # ──────────────────────────────────────────────
    #  Internal helpers
    # ──────────────────────────────────────────────

    def _build_billing_lines(self):
        """
        Compute which subscriptions are due in this period and create
        one parent.billing.run.line per billing partner.
        """
        year, month_int = self.year, int(self.month)
        last_day = calendar.monthrange(year, month_int)[1]
        period_end = fields.Date.to_date(f'{year}-{month_int:02d}-{last_day}')

        subs_to_bill = self.env['tuition.subscription'].search([
            ('state', '=', 'active'),
            ('next_billing_date', '<=', period_end),
        ])

        if not subs_to_bill:
            raise UserError(
                "No active subscriptions found with a billing date on or before %s." % period_end
            )

        by_partner = {}
        missing_students = []

        for sub in subs_to_bill:
            # Resolve billing partner: parent first, then student
            billing_partner = False
            parent_profile = self.env['parent.profile'].sudo().search(
                [('student_ids', 'in', [sub.student_id.id])], limit=1
            )
            if parent_profile and parent_profile.partner_id:
                billing_partner = parent_profile.partner_id
            if not billing_partner and sub.student_id.partner_id:
                billing_partner = sub.student_id.partner_id

            if not billing_partner:
                missing_students.append(sub.student_id.name or 'Unknown Student')
                continue

            key = billing_partner.id
            if key not in by_partner:
                by_partner[key] = {'partner_id': key, 'subscription_ids': []}
            by_partner[key]['subscription_ids'].append(sub.id)

        if not by_partner:
            raise UserError(
                "Could not determine a billing partner for any subscriptions.\n\n"
                "Students missing a linked Contact:\n- " + "\n- ".join(set(missing_students))
            )

        # Log missing students as a warning message on the run
        if missing_students:
            self.message_post(
                body='⚠️ The following students were skipped (no billing contact): %s'
                     % ', '.join(set(missing_students)),
                subtype_xmlid='mail.mt_note',
            )

        for partner_id, data in by_partner.items():
            subs = self.env['tuition.subscription'].browse(data['subscription_ids'])
            detail_vals = []
            total = 0.0

            for sub in subs:
                try:
                    preview_vals = sub._build_preview_vals()
                    total += preview_vals.get('total_amount', 0.0)
                    for line in preview_vals.get('lines', []):
                        detail_vals.append((0, 0, {
                            'student_id': sub.student_id.id,
                            'course_name': sub.enrollment_id.course_id.name or '',
                            'description': line.get('description', ''),
                            'unit_price': line.get('unit_price', 0.0),
                            'quantity': line.get('quantity', 1.0),
                            'subtotal': line.get('subtotal', 0.0),
                            'product_id': line.get('product_id'),
                        }))
                except UserError:
                    continue

            if detail_vals:
                self.env['parent.billing.run.line'].create({
                    'run_id': self.id,
                    'partner_id': partner_id,
                    'subscription_ids': [(6, 0, subs.ids)],
                    'total_amount': total,
                    'detail_ids': detail_vals,
                    'state': 'included',
                })


class ParentBillingRunLine(models.Model):
    """One line per billing partner (parent) in a billing run."""
    _name = 'parent.billing.run.line'
    _description = 'Parent Billing Run Line'
    _order = 'partner_id'

    run_id = fields.Many2one(
        'parent.billing.run', string='Billing Run',
        required=True, ondelete='cascade',
    )
    run_state = fields.Selection(related='run_id.state', string='Run Status', store=True)
    partner_id = fields.Many2one('res.partner', string='Bill To (Parent)', readonly=True)
    subscription_ids = fields.Many2many(
        'tuition.subscription', string='Subscriptions', readonly=True,
    )
    detail_ids = fields.One2many(
        'parent.billing.run.detail', 'line_id', string='Line Details',
    )
    total_amount = fields.Float(string='Total Amount', readonly=True)
    state = fields.Selection([
        ('included', 'Included'),
        ('excluded', 'Excluded'),
    ], string='Line Status', default='included', required=True)
    invoice_id = fields.Many2one(
        'account.move', string='Invoice', readonly=True, copy=False,
    )
    notes = fields.Char(string='Notes / Override Reason')
    has_existing_invoice = fields.Boolean(
        string='Invoice Exists', compute='_compute_has_existing_invoice',
    )
    currency_id = fields.Many2one(related='run_id.currency_id', store=True)

    @api.depends('partner_id', 'run_id.month', 'run_id.year')
    def _compute_has_existing_invoice(self):
        for rec in self:
            if not rec.partner_id or not rec.run_id.month:
                rec.has_existing_invoice = False
                continue
            month_int = int(rec.run_id.month)
            year = rec.run_id.year
            start_date = fields.Date.to_date(f'{year}-{month_int:02d}-01')
            last_day = calendar.monthrange(year, month_int)[1]
            end_date = fields.Date.to_date(f'{year}-{month_int:02d}-{last_day}')
            count = self.env['account.move'].search_count([
                ('partner_id', '=', rec.partner_id.id),
                ('move_type', '=', 'out_invoice'),
                ('state', '!=', 'cancel'),
                ('invoice_date', '>=', start_date),
                ('invoice_date', '<=', end_date),
            ])
            rec.has_existing_invoice = count > 0

    def action_exclude(self):
        for line in self:
            if line.run_id.state in ('approved', 'invoiced'):
                raise UserError("Cannot exclude lines from an Approved or Invoiced run.")
            line.state = 'excluded'

    def action_include(self):
        for line in self:
            if line.run_id.state in ('approved', 'invoiced'):
                raise UserError("Cannot change lines in an Approved or Invoiced run.")
            line.state = 'included'

    def _generate_invoice(self):
        """
        Generate a consolidated Odoo invoice for this billing line.
        Mirrors BulkBillingPreviewLine._generate_consolidated_invoice.
        """
        self.ensure_one()
        if self.invoice_id:
            return self.invoice_id

        all_lines = []
        all_unapplied_adjustments = self.env['tuition.adjustment']

        for sub in self.subscription_ids:
            try:
                preview_vals = sub._build_preview_vals()
                all_lines.extend(preview_vals.get('lines', []))
                if preview_vals.get('unapplied_adj_ids'):
                    all_unapplied_adjustments |= self.env['tuition.adjustment'].browse(
                        preview_vals.get('unapplied_adj_ids')
                    )
            except UserError:
                continue

        if not all_lines:
            return self.env['account.move']

        payment_term = self.env['account.payment.term'].sudo().search(
            [('name', 'ilike', '15')], limit=1
        )
        misc_product = self.env['product.product'].sudo().search(
            [('type', '=', 'service')], limit=1
        )

        order_lines = []
        for line in all_lines:
            product = (
                self.env['product.product'].sudo().browse(line['product_id'])
                if line.get('product_id') else misc_product
            )
            if not product:
                continue
            order_lines.append((0, 0, {
                'product_id': product.id,
                'product_uom_qty': line['quantity'],
                'price_unit': line['unit_price'],
                'name': line['description'],
            }))

        month_str = (
            f"{calendar.month_name[int(self.run_id.month)]} {self.run_id.year}"
        )
        order = self.env['sale.order'].sudo().create({
            'partner_id': self.partner_id.id,
            'payment_term_id': payment_term.id if payment_term else False,
            'order_line': order_lines,
            'note': f'Consolidated Tuition Invoice for {month_str}',
            'tuition_subscription_ids': [(6, 0, self.subscription_ids.ids)],
        })
        order.action_confirm()

        invoice = order._create_invoices()

        parent_profile = self.env['parent.profile'].sudo().search(
            [('partner_id', '=', self.partner_id.id)], limit=1
        )
        invoice.sudo().write({
            'tuition_subscription_ids': [(6, 0, self.subscription_ids.ids)],
            'parent_profile_id': parent_profile.id if parent_profile else False,
        })
        invoice.sudo().action_post()

        # Mark adjustments and advance next billing date
        if all_unapplied_adjustments:
            all_unapplied_adjustments.write({
                'applied_in_invoice': True,
                'invoice_id': invoice.id,
            })

        billing_date = fields.Date.to_date(
            f'{self.run_id.year}-{int(self.run_id.month):02d}-01'
        )
        next_billing_date = billing_date + relativedelta(months=1)
        self.subscription_ids.write({'next_billing_date': next_billing_date})

        self.write({'invoice_id': invoice.id})
        return invoice


class ParentBillingRunDetail(models.Model):
    """Per-subscription line detail within a billing run line."""
    _name = 'parent.billing.run.detail'
    _description = 'Parent Billing Run Detail'

    line_id = fields.Many2one(
        'parent.billing.run.line', string='Billing Line',
        required=True, ondelete='cascade',
    )
    student_id = fields.Many2one('student.profile', string='Student', readonly=True)
    course_name = fields.Char(string='Course', readonly=True)
    description = fields.Char(string='Description', readonly=True)
    quantity = fields.Float(string='Qty', readonly=True, default=1.0)
    unit_price = fields.Float(string='Unit Price', readonly=True)
    subtotal = fields.Float(string='Subtotal', readonly=True)
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
