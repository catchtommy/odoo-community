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
    is_multi_currency = fields.Boolean(
        string='Spans Multiple Currencies', compute='_compute_totals', store=True,
        help="True when the included billing lines span more than one currency — in that "
             "case Total Amount is not a meaningful single figure; see Total by Currency instead.",
    )
    total_amount_by_currency = fields.Char(
        string='Total by Currency', compute='_compute_totals', store=True,
        help="Per-currency breakdown of the included billing lines' totals.",
    )

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
    has_live_invoices = fields.Boolean(
        string='Has Live Invoices', compute='_compute_has_live_invoices',
        help="Whether this run still has at least one non-cancelled invoice linked to it.",
    )

    @api.depends('line_ids.invoice_id', 'line_ids.invoice_id.state')
    def _compute_has_live_invoices(self):
        for rec in self:
            rec.has_live_invoices = rec._has_live_invoices()

    @api.depends('month', 'year')
    def _compute_period_label(self):
        for rec in self:
            if rec.month and rec.year:
                rec.period_label = f"{calendar.month_name[int(rec.month)]} {rec.year}"
            else:
                rec.period_label = ''

    @api.depends('line_ids.total_amount', 'line_ids.state', 'line_ids.currency_id')
    def _compute_totals(self):
        for rec in self:
            included = rec.line_ids.filtered(lambda l: l.state == 'included')
            rec.total_parents = len(included)
            rec.total_lines = len(rec.line_ids)
            rec.total_amount = sum(included.mapped('total_amount'))

            currencies = included.mapped('currency_id')
            rec.is_multi_currency = len(currencies) > 1
            by_currency = {}
            for line in included:
                currency = line.currency_id or rec.env.company.currency_id
                by_currency[currency] = by_currency.get(currency, 0.0) + line.total_amount
            rec.total_amount_by_currency = ' · '.join(
                self._format_currency_amount(currency, amount)
                for currency, amount in sorted(by_currency.items(), key=lambda kv: kv[0].name)
            )

    @api.model
    def _format_currency_amount(self, currency, amount):
        formatted = f"{currency.round(amount):,.{currency.decimal_places}f}"
        if currency.position == 'before':
            return f"{currency.symbol}{formatted}"
        return f"{formatted} {currency.symbol}"

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

    def _has_live_invoices(self):
        """Whether this run still has at least one non-cancelled invoice linked to it."""
        self.ensure_one()
        return bool(self.line_ids.mapped('invoice_id').filtered(lambda m: m.state != 'cancel'))

    def unlink(self):
        for run in self:
            if run.state == 'approved':
                raise UserError("Approved billing runs cannot be deleted.")
            if run.state == 'invoiced' and run._has_live_invoices():
                raise UserError(
                    "This billing run has invoices linked to it and cannot be deleted. "
                    "Cancel/remove those invoices first, or reset the run to Draft."
                )
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
        failed_lines = self.env['parent.billing.run.line']
        for line in included_lines:
            try:
                invoice = line._generate_invoice()
            except UserError as e:
                line.error_message = str(e)
                failed_lines |= line
                continue
            line.error_message = False
            if invoice:
                generated_invoices |= invoice

        if not generated_invoices:
            # Force the per-line error_message writes above to persist even though we're
            # about to raise — an uncaught exception rolls back the whole transaction,
            # which would otherwise wipe out the very diagnostics we just recorded.
            self.env.cr.commit()
            raise UserError(
                "No invoices were generated. This may be because all subscriptions "
                "have already been invoiced for this period, or because every included "
                "line failed — see the Error column for details."
            )

        self.write({
            'state': 'invoiced',
            'invoiced_by': self.env.user.id,
            'invoiced_date': fields.Datetime.now(),
        })
        summary = '<b>%d invoice(s)</b> generated by <b>%s</b>.' % (
            len(generated_invoices), self.env.user.name
        )
        if failed_lines:
            summary += ' <b>%d line(s) failed</b> and were skipped — see the Error column on those lines.' % len(failed_lines)
        self.message_post(body=summary, subtype_xmlid='mail.mt_note')

        return {
            'type': 'ir.actions.act_window',
            'name': 'Generated Invoices',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', generated_invoices.ids)],
        }

    def action_reset_to_draft(self):
        for run in self:
            if run.state == 'approved':
                # Approved runs never have invoices yet — generation atomically moves
                # the run straight to 'invoiced'. Only the approver may undo this.
                require_permission(self.env.user, 'parent_invoice_approve')
            elif run.state == 'invoiced':
                if run._has_live_invoices():
                    raise UserError(
                        "This billing run has invoices linked to it and cannot be reset to Draft. "
                        "Cancel/remove those invoices first."
                    )
            elif run.state not in ('draft', 'preview'):
                raise UserError(
                    "Only Draft, Preview, Approved, or Invoiced (with no linked invoices) "
                    "runs can be reset to Draft."
                )
            run.line_ids.unlink()
            run.write({
                'state': 'draft',
                'approved_by': False,
                'approved_date': False,
            })
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

    def action_view_billing_lines_by_company(self):
        """Open this run's billing lines as a standalone, grouped list — one section per
        Company (then Currency), each with its own accurate subtotal. Embedded one2many
        list widgets don't support default groupby, so this opens a real window action
        instead, where Odoo's native per-group aggregates work correctly."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Billing Lines by Company',
            'res_model': 'parent.billing.run.line',
            'view_mode': 'list,form',
            'views': [
                (self.env.ref('tuition_management.view_parent_billing_run_line_list_grouped').id, 'list'),
                (self.env.ref('tuition_management.view_parent_billing_run_line_form').id, 'form'),
            ],
            'search_view_id': self.env.ref('tuition_management.view_parent_billing_run_line_search').id,
            'domain': [('run_id', '=', self.id)],
            'context': {'group_by': ['company_id', 'currency_id']},
        }

    # ──────────────────────────────────────────────
    #  Internal helpers
    # ──────────────────────────────────────────────

    def _build_billing_lines(self):
        """
        Compute which subscriptions are due in this period and create
        one parent.billing.run.line per (billing partner, currency, company) —
        a parent whose subscriptions span multiple currencies and/or companies
        gets one billing line, and later one invoice, per combination.
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

        by_group = {}
        missing_students = []

        for sub in subs_to_bill:
            billing_partner = sub._get_billing_partner()
            if not billing_partner:
                missing_students.append(sub.student_id.name or 'Unknown Student')
                continue

            currency = sub.currency_id or self.env.company.currency_id
            company = sub.company_id or self.env.company
            key = (billing_partner.id, currency.id, company.id)
            if key not in by_group:
                by_group[key] = {'partner_id': billing_partner.id, 'subscription_ids': []}
            by_group[key]['subscription_ids'].append(sub.id)

        if not by_group:
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

        for (partner_id, _currency_id, _company_id), data in by_group.items():
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
    error_message = fields.Char(
        string='Error', copy=False,
        help="Set when invoice generation failed for this line (e.g. a company/currency "
             "mismatch). Cleared automatically once generation succeeds.",
    )
    has_existing_invoice = fields.Boolean(
        string='Invoice Exists', compute='_compute_has_existing_invoice',
    )
    currency_id = fields.Many2one(
        'res.currency', string='Currency', compute='_compute_currency_id', store=True,
    )
    company_id = fields.Many2one(
        'res.company', string='Company', compute='_compute_company_id', store=True,
    )

    @api.depends('subscription_ids', 'subscription_ids.currency_id')
    def _compute_currency_id(self):
        for rec in self:
            sub = rec.subscription_ids[:1]
            rec.currency_id = sub.currency_id if sub else rec.env.company.currency_id

    @api.depends('subscription_ids', 'subscription_ids.company_id')
    def _compute_company_id(self):
        for rec in self:
            sub = rec.subscription_ids[:1]
            rec.company_id = sub.company_id if sub else rec.env.company

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
        """Generate a consolidated Odoo customer invoice for this billing line, directly
        (no intermediate sale order/quotation)."""
        self.ensure_one()
        if self.invoice_id:
            return self.invoice_id

        if self.has_existing_invoice:
            raise UserError(
                "An invoice already exists for %s covering %s %s. Refusing to generate a "
                "duplicate. This can happen after resetting a run and regenerating it — "
                "the earlier successful invoice isn't retracted, so re-running would bill "
                "this parent twice. If a second invoice is genuinely needed (e.g. a "
                "correction), create it manually instead of via this run."
                % (self.partner_id.display_name,
                   calendar.month_name[int(self.run_id.month)], self.run_id.year)
            )

        all_lines = []
        all_unapplied_adjustments = self.env['tuition.adjustment']
        skip_reasons = []

        for sub in self.subscription_ids:
            try:
                preview_vals = sub._build_preview_vals()
                all_lines.extend(preview_vals.get('lines', []))
                if preview_vals.get('unapplied_adj_ids'):
                    all_unapplied_adjustments |= self.env['tuition.adjustment'].browse(
                        preview_vals.get('unapplied_adj_ids')
                    )
            except UserError as e:
                skip_reasons.append('%s: %s' % (sub.name, e))
                continue

        if not all_lines:
            if skip_reasons:
                raise UserError(
                    "No billable lines could be generated for this parent this period:\n- "
                    + '\n- '.join(skip_reasons)
                )
            raise UserError(
                "No billable lines could be generated for this parent this period "
                "(no subscriptions produced any charges)."
            )

        # Grouping in _build_billing_lines guarantees every subscription on this line
        # shares the same company — that company is authoritative for this invoice.
        subscription_company = self.subscription_ids[:1].company_id or self.env.company

        payment_term = self.env['account.payment.term'].sudo().search([
            ('name', 'ilike', '15'),
            ('company_id', 'in', [subscription_company.id, False]),
        ], limit=1)
        # A payment term with no installment lines produces no due date at all when
        # used — treat it the same as not having found one, rather than assigning a
        # broken term to the invoice.
        if payment_term and not payment_term.line_ids:
            payment_term = self.env['account.payment.term']
        misc_product = self.env['product.product'].sudo().search(
            [('type', '=', 'service')], limit=1
        )

        invoice_lines = []
        for line in all_lines:
            product = (
                self.env['product.product'].sudo().browse(line['product_id'])
                if line.get('product_id') else misc_product
            )
            if not product:
                continue
            if product.company_id and product.company_id != subscription_company:
                raise UserError(
                    "Cannot generate this invoice: product '%s' belongs to company '%s', but "
                    "this subscription is billed under company '%s'. Either leave the Company "
                    "field blank on the product (shared across companies) or assign it to '%s'."
                    % (product.display_name, product.company_id.name,
                       subscription_company.name, subscription_company.name)
                )
            invoice_lines.append((0, 0, {
                'product_id': product.id,
                'quantity': line['quantity'],
                'price_unit': line['unit_price'],
                'name': line['description'],
            }))

        month_str = (
            f"{calendar.month_name[int(self.run_id.month)]} {self.run_id.year}"
        )
        pricelist = self.subscription_ids[:1]._get_invoice_pricelist()
        if pricelist.company_id and pricelist.company_id != subscription_company:
            raise UserError(
                "Cannot generate this invoice: the pricing list '%s' belongs to company '%s', "
                "but this subscription is billed under company '%s'. Either leave the Company "
                "field blank on the pricing list or assign it to '%s'."
                % (pricelist.display_name, pricelist.company_id.name,
                   subscription_company.name, subscription_company.name)
            )

        parent_profile = self.env['parent.profile'].sudo().search(
            [('partner_id', '=', self.partner_id.id)], limit=1
        )
        invoice_date = fields.Date.today()
        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'company_id': subscription_company.id,
            'currency_id': pricelist.currency_id.id,
            'invoice_date': invoice_date,
            'invoice_line_ids': invoice_lines,
            'narration': f'Consolidated Tuition Invoice for {month_str}',
            'tuition_subscription_ids': [(6, 0, self.subscription_ids.ids)],
            'parent_profile_id': parent_profile.id if parent_profile else False,
        }
        if payment_term:
            invoice_vals['invoice_payment_term_id'] = payment_term.id
        else:
            # No payment term to derive installment due dates from — due immediately.
            # Set this explicitly rather than relying on compute-timing during create(),
            # since an unset due date on the receivable line fails validation on posting.
            invoice_vals['invoice_date_due'] = invoice_date
        invoice = self.env['account.move']
        try:
            invoice = self.env['account.move'].sudo().create(invoice_vals)
            invoice.sudo().action_post()
        except Exception:
            # Don't leave a dangling draft invoice behind if posting failed partway
            # through — especially important because a later diagnostic commit
            # (see action_generate_invoices) can otherwise persist it.
            if invoice and invoice.state == 'draft':
                invoice.sudo().unlink()
            raise

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
