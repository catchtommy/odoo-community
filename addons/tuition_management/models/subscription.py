# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError, AccessError
from dateutil.relativedelta import relativedelta
from datetime import date
from .user_permission import require_permission, user_has_permission


class TuitionSubscription(models.Model):
    _name = 'tuition.subscription'
    _description = 'Tuition Subscription'
    _order = 'create_date desc'

    name = fields.Char(string='Reference', compute='_compute_name', store=True)
    student_id = fields.Many2one('student.profile', string='Student', required=True, ondelete='restrict')
    parent_id = fields.Many2one('parent.profile', string='Parent',
                                related='student_id.parent_id', store=True, readonly=True)
    enrollment_id = fields.Many2one('course.enrollment', string='Enrollment', ondelete='restrict',
                                    domain="[('student_id', '=', student_id)]")
    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company,
        domain=lambda self: [('id', 'in', self.env.user.company_ids.ids)],
        help="Legal entity this subscription is billed under. Plan lines can only use products/pricing "
             "lists that belong to this company (or are shared across companies).",
    )
    currency_id = fields.Many2one(
        'res.currency', string='Currency', required=True,
        default=lambda self: self.env.company.currency_id,
        domain=[('active', '=', True)],
        help="Billing currency for this subscription. Plan lines can only use a Pricing List in this currency.",
    )
    company_currency_ids = fields.Many2many(
        related='company_id.tuition_currency_ids', string='Company Allowed Currencies',
        help="Technical field used to restrict the Currency field's dropdown to this "
             "subscription's company's configured currencies, reactively (not just on "
             "onchange) so it's also correct for already-saved subscriptions.",
    )
    plan_line_ids = fields.One2many('tuition.plan.line', 'subscription_id', string='Plan History')
    adjustment_ids = fields.One2many('tuition.adjustment', 'subscription_id', string='Adjustments')
    invoice_ids = fields.Many2many('account.move', 'account_move_tuition_subscription_rel', 'subscription_id', 'move_id', string='Invoices')
    discount_ids = fields.One2many('tuition.discount', 'subscription_id', string='Discounts')
    current_plan_id = fields.Many2one('tuition.plan.line', string='Current Plan', compute='_compute_current_plan', store=False)
    current_plan_product = fields.Char(string='Current Plan', compute='_compute_current_plan', store=False)
    current_plan_price = fields.Float(string='Monthly Price', compute='_compute_current_plan', store=False)
    next_billing_date = fields.Date(
        string='Next Billing Date',
        compute='_compute_next_billing_date',
        store=True,
        readonly=False,
        help="Auto-calculated: 1st of the month after the last invoice. "
             "If no invoice exists yet, defaults to the current plan's start date.",
    )
    state = fields.Selection([('active', 'Active'), ('paused', 'Paused'), ('cancelled', 'Cancelled')],
                             string='Status', default='active', required=True)
    invoice_count = fields.Integer(compute='_compute_invoice_count', string='Invoices')
    unapplied_adjustment_count = fields.Integer(compute='_compute_unapplied_adjustments', string='Pending Adjustments')
    total_adjustments_applied = fields.Float(compute='_compute_totals', string='Total Adjustments Applied')
    monthly_revenue = fields.Float(compute='_compute_totals', string='Monthly Revenue')
    can_edit_billing_date = fields.Boolean(
        string='Can Edit Billing Date',
        compute='_compute_can_edit_billing_date',
    )
    can_add_plan = fields.Boolean(
        string='Can Add Plan',
        compute='_compute_can_add_plan',
    )
    can_edit_plan = fields.Boolean(
        string='Can Edit Plan',
        compute='_compute_can_edit_plan',
    )

    @api.depends('student_id', 'enrollment_id')
    def _compute_name(self):
        for rec in self:
            parts = [p for p in [rec.student_id.name, rec.enrollment_id.course_id.name if rec.enrollment_id else ''] if p]
            rec.name = ' / '.join(parts) if parts else 'New Subscription'

    @api.onchange('company_id')
    def _onchange_company_id(self):
        allowed = self.company_id.tuition_currency_ids
        if len(allowed) == 1:
            self.currency_id = allowed
        elif self.currency_id and self.currency_id not in allowed:
            self.currency_id = False
        return {'domain': {'currency_id': [('id', 'in', allowed.ids)]}}

    @api.depends('plan_line_ids', 'plan_line_ids.state')
    def _compute_current_plan(self):
        for rec in self:
            # state == 'active' already implies approved + date check (see TuitionPlanLine._compute_state)
            plans = rec.plan_line_ids.filtered(lambda p: p.state == 'active')
            plan = plans[0] if plans else False
            rec.current_plan_id = plan.id if plan else False
            rec.current_plan_product = plan.product_id.name if plan else ''
            rec.current_plan_price = plan.price if plan else 0.0

    @api.depends('invoice_ids', 'invoice_ids.state', 'invoice_ids.invoice_date',
                 'plan_line_ids', 'plan_line_ids.state', 'plan_line_ids.start_date')
    def _compute_next_billing_date(self):
        """
        Derive next billing date without any manual input:
          • Last posted invoice → next = 1st of the month after that invoice date
          • No invoices yet     → current plan's start_date (always the 1st by constraint)
          • No approved plan    → False (cron skips this subscription)
        """
        for rec in self:
            posted = rec.sudo().invoice_ids.filtered(
                lambda m: m.state == 'posted' and m.invoice_date
            ).sorted('invoice_date', reverse=True)
            if posted:
                last_date = posted[0].invoice_date
                rec.next_billing_date = last_date.replace(day=1) + relativedelta(months=1)
            elif rec.current_plan_id and rec.current_plan_id.start_date:
                rec.next_billing_date = rec.current_plan_id.start_date
            else:
                rec.next_billing_date = False

    @api.depends_context('uid')
    def _compute_can_edit_billing_date(self):
        can_edit = (
            self.env.user.has_group('base.group_system') or
            user_has_permission(self.env.user, 'subscription_edit_billing_date')
        )
        for rec in self:
            rec.can_edit_billing_date = can_edit

    @api.depends_context('uid')
    def _compute_can_add_plan(self):
        can_add = (
            self.env.user.has_group('base.group_system') or
            user_has_permission(self.env.user, 'subscription_add_plan')
        )
        for rec in self:
            rec.can_add_plan = can_add

    @api.depends_context('uid')
    def _compute_can_edit_plan(self):
        can_edit = (
            self.env.user.has_group('base.group_system') or
            user_has_permission(self.env.user, 'subscription_edit_plan')
        )
        for rec in self:
            rec.can_edit_plan = can_edit

    @api.depends('invoice_ids', 'invoice_ids.state')
    def _compute_invoice_count(self):
        for rec in self:
            # Use sudo() to bypass account.move ACL — non-accounting users can
            # still see the count on the subscription list without needing full
            # access to the accounting module.
            rec.invoice_count = len(
                rec.sudo().invoice_ids.filtered(lambda m: m.state != 'cancel')
            )

    def _compute_unapplied_adjustments(self):
        for rec in self:
            # Only count approved (not yet applied) adjustments
            rec.unapplied_adjustment_count = len(
                rec.adjustment_ids.filtered(lambda a: a.state == 'approved')
            )

    def _compute_totals(self):
        for rec in self:
            rec.total_adjustments_applied = sum(rec.adjustment_ids.filtered(lambda a: a.applied_in_invoice).mapped('amount'))
            rec.monthly_revenue = rec.current_plan_id.price if rec.current_plan_id else 0.0

    def _get_billing_partner(self):
        """Resolve the contact billing should be addressed to: parent if linked, else the student."""
        self.ensure_one()
        partner = self.student_id.partner_id
        parent_profile = self.env['parent.profile'].sudo().search(
            [('student_ids', 'in', [self.student_id.id])], limit=1)
        if parent_profile and parent_profile.partner_id:
            partner = parent_profile.partner_id
        return partner

    def _get_invoice_pricelist(self):
        """Pricelist to bill this subscription with — the one used on its current plan line."""
        self.ensure_one()
        return self.current_plan_id.pricelist_id or self.env['product.pricelist'].sudo().search([
            ('currency_id', '=', self.currency_id.id),
            ('company_id', 'in', [self.company_id.id, False]),
        ], limit=1)

    @api.constrains('enrollment_id', 'state')
    def _check_unique_enrollment_subscription(self):
        for rec in self:
            if not rec.enrollment_id:
                continue
            duplicate = self.search([
                ('id', '!=', rec.id),
                ('enrollment_id', '=', rec.enrollment_id.id),
                ('state', '!=', 'cancelled'),
            ], limit=1)
            if duplicate:
                raise ValidationError(
                    "Enrollment '%s' already has an active subscription (%s). "
                    "An enrollment can only have one active subscription at a time — "
                    "cancel the existing one first." % (rec.enrollment_id.name, duplicate.name)
                )

    def action_view_invoices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Invoices',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.sudo().invoice_ids.ids), ('state', '!=', 'cancel')],
        }

    def _build_preview_vals(self):
        self.ensure_one()
        if self.state != 'active':
            raise UserError("Cannot generate invoice for a %s subscription." % self.state)
        plan = self.current_plan_id
        if not plan:
            raise UserError("No active plan for subscription %s." % self.name)
        billing_partner = self._get_billing_partner()
        if not billing_partner:
            raise UserError("Student %s has no linked contact." % self.student_id.name)
        month_label = fields.Date.today().strftime('%B %Y')
        base_price = plan.price
        lines = [{'description': '%s - %s' % (plan.product_id.name, month_label), 'product_id': plan.product_id.id,
                  'quantity': 1, 'unit_price': base_price, 'subtotal': base_price, 'line_type': 'plan'}]
        total_discounts = 0.0
        today = fields.Date.today()
        for disc in self.discount_ids.filtered(lambda d: d.state == 'active'):
            disc_amount = disc._compute_discount_amount(base_price)
            if disc_amount:
                label = '[Discount] %s' % disc.name
                if disc.discount_type == 'percentage': label += ' (%.2f%%)' % disc.value
                lines.append({'description': label, 'product_id': False, 'quantity': 1,
                              'unit_price': -abs(disc_amount), 'subtotal': -abs(disc_amount), 'line_type': 'discount'})
                total_discounts += abs(disc_amount)
        total_adjustments = 0.0
        unapplied = self.adjustment_ids.filtered(lambda a: a.state == 'approved')
        for adj in unapplied:
            lines.append({'description': '[%s] %s' % (dict(adj._fields['adjustment_type'].selection).get(adj.adjustment_type, ''), adj.description),
                          'product_id': False, 'quantity': 1, 'unit_price': adj.signed_amount, 'subtotal': adj.signed_amount, 'line_type': 'adjustment'})
            total_adjustments += adj.signed_amount
        return {'partner_id': billing_partner.id, 'month_label': month_label, 'base_price': base_price,
                'total_discounts': total_discounts, 'total_adjustments': total_adjustments,
                'total_amount': base_price - total_discounts + total_adjustments,
                'lines': lines, 'plan_id': plan.id, 'unapplied_adj_ids': unapplied.ids}

    def action_pause(self): self.write({'state': 'paused'})
    def action_activate(self): self.write({'state': 'active'})
    def action_cancel(self): self.write({'state': 'cancelled'})

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records.filtered('enrollment_id'):
            rec.enrollment_id.subscription_id = rec.id
        return records

    def write(self, vals):
        if vals.get('enrollment_id'):
            for rec in self:
                self.env['course.enrollment'].browse(vals['enrollment_id']).subscription_id = rec.id
        if 'next_billing_date' in vals:
            if not (self.env.user.has_group('base.group_system') or
                    user_has_permission(self.env.user, 'subscription_edit_billing_date')):
                raise AccessError(
                    "You do not have permission to manually edit the Next Billing Date.\n"
                    "Contact your administrator to enable the 'Edit Next Billing Date' permission."
                )
        return super().write(vals)


class TuitionDiscount(models.Model):
    _name = 'tuition.discount'
    _description = 'Tuition Subscription Discount'
    _order = 'date_start desc'

    subscription_id = fields.Many2one('tuition.subscription', required=True, ondelete='cascade')
    student_id = fields.Many2one('student.profile', related='subscription_id.student_id', store=True, readonly=True)
    name = fields.Char(string='Discount Name', required=True)
    discount_type = fields.Selection([('percentage', 'Percentage (%)'), ('amount', 'Fixed Amount')],
                                     string='Type', required=True, default='percentage')
    value = fields.Float(string='Value', required=True)
    date_start = fields.Date(string='From', default=fields.Date.today)
    date_end = fields.Date(string='Until')
    active = fields.Boolean(string='Enabled', default=True)
    description = fields.Char(string='Notes')
    approval_state = fields.Selection(
        [('draft', 'Draft'), ('approved', 'Approved')],
        default='draft', required=True)  # hidden backend field
    state = fields.Selection([
        ('pending_approval', 'Pending Approval'),
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ], string='Status', compute='_compute_state', store=True)

    @api.depends('approval_state', 'active', 'date_end')
    def _compute_state(self):
        today = fields.Date.today()
        for rec in self:
            if rec.approval_state == 'draft':
                rec.state = 'pending_approval'
            elif not rec.active or (rec.date_end and rec.date_end < today):
                rec.state = 'inactive'
            else:
                rec.state = 'active'

    def init(self):
        self.env.cr.execute(
            "UPDATE tuition_discount SET approval_state = 'approved' WHERE approval_state IS NULL"
        )

    def action_approve(self):
        require_permission(self.env.user, 'subscription_approve')
        self.write({'approval_state': 'approved'})

    def action_set_draft(self):
        self.write({'approval_state': 'draft'})

    def _compute_discount_amount(self, base_price):
        self.ensure_one()
        return base_price * (self.value / 100.0) if self.discount_type == 'percentage' else abs(self.value)


class TuitionPlanLine(models.Model):
    _name = 'tuition.plan.line'
    _description = 'Tuition Plan Line'
    _order = 'start_date desc'

    subscription_id = fields.Many2one('tuition.subscription', required=True, ondelete='cascade')
    student_id = fields.Many2one('student.profile', related='subscription_id.student_id', store=True, readonly=True)
    product_id = fields.Many2one('product.product', string='Plan Product', required=True)
    product_tmpl_id = fields.Many2one(related='product_id.product_tmpl_id', store=True)
    pricelist_id = fields.Many2one('product.pricelist', string='Pricing List',
                                   help="Pricing list this plan's price/currency were taken from. "
                                        "Restricted to the subscription's currency and the selected product.")
    price = fields.Float(string='Monthly Price', required=True)
    currency_id = fields.Many2one('res.currency', string='Currency', related='subscription_id.currency_id',
                                  store=True, readonly=True)
    classes_per_week = fields.Integer(string='Classes per Week', required=True, default=1)
    classes_per_week_selection = fields.Selection(
        [(str(i), str(i)) for i in range(1, 8)], string='Classes per Week',
        compute='_compute_classes_per_week_selection', inverse='_inverse_classes_per_week_selection',
        required=True)
    start_date = fields.Date(string='Start Date', required=True)
    end_date = fields.Date(string='End Date')
    state = fields.Selection([
        ('pending_approval', 'Pending Approval'),
        ('active', 'Active'), ('scheduled', 'Scheduled'), ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ], string='Status', compute='_compute_state', store=True)
    approval_state = fields.Selection(
        [('draft', 'Draft'), ('approved', 'Approved')],
        default='draft', required=True)  # hidden backend field — drives state compute
    notes = fields.Char(string='Notes')
    has_invoices = fields.Boolean(string='Has Invoices', compute='_compute_has_invoices', store=False)

    def init(self):
        self.env.cr.execute(
            "UPDATE tuition_plan_line SET approval_state = 'approved' WHERE approval_state IS NULL"
        )
        # One-time (idempotent) fix-up for plan lines whose stored `state` predates the
        # 'cancelled' branch in _compute_state(): a plan line under an already-cancelled
        # subscription would otherwise keep reading as active/scheduled/expired forever,
        # since a stored compute only recomputes on a write to a dependency, not
        # retroactively when a new dependency/branch is added.
        self.env.cr.execute("""
            UPDATE tuition_plan_line pl
            SET state = 'cancelled'
            FROM tuition_subscription s
            WHERE pl.subscription_id = s.id AND s.state = 'cancelled' AND pl.state != 'cancelled'
        """)

    @api.model_create_multi
    def create(self, vals_list):
        require_permission(self.env.user, 'subscription_add_plan')
        return super().create(vals_list)

    def action_approve(self):
        require_permission(self.env.user, 'subscription_approve')
        self.write({'approval_state': 'approved'})

    def action_set_draft(self):
        self.write({'approval_state': 'draft'})

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            if self.product_id.tuition_classes_per_week:
                self.classes_per_week = self.product_id.tuition_classes_per_week
            if self.subscription_id:
                matches = self._search_matching_pricelists()
                self.pricelist_id = matches.id if len(matches) == 1 else False
            self._compute_price_from_pricelist()

    @api.onchange('pricelist_id')
    def _onchange_pricelist_id(self):
        self._compute_price_from_pricelist()

    @api.onchange('classes_per_week')
    def _onchange_classes_per_week(self):
        if self.product_id and self.subscription_id:
            matches = self._search_matching_pricelists()
            if self.pricelist_id not in matches:
                self.pricelist_id = matches.id if len(matches) == 1 else False
        self._compute_price_from_pricelist()

    @api.onchange('classes_per_week_selection')
    def _onchange_classes_per_week_selection(self):
        # Onchange dispatch writes the edited field straight to cache and never
        # calls its `inverse`, so the sync to `classes_per_week` has to happen
        # here explicitly (inverse only runs on an actual write()/create()).
        self.classes_per_week = int(self.classes_per_week_selection) if self.classes_per_week_selection else 0
        self._onchange_classes_per_week()

    def _search_matching_pricelists(self):
        """Pricelists matching this line's currency/company/product, with a tier
        applicable at the current quantity (classes per week)."""
        self.ensure_one()
        if not (self.product_id and self.subscription_id):
            return self.env['product.pricelist']
        return self.env['product.pricelist'].sudo().search([
            ('currency_id', '=', self.subscription_id.currency_id.id),
            ('company_id', 'in', [self.subscription_id.company_id.id, False]),
            '&', '|', ('item_ids.product_id', '=', self.product_id.id),
                      ('item_ids.product_tmpl_id', '=', self.product_id.product_tmpl_id.id),
            ('item_ids.min_quantity', '<=', self.classes_per_week or 1),
        ])

    @api.depends('classes_per_week')
    def _compute_classes_per_week_selection(self):
        for rec in self:
            rec.classes_per_week_selection = str(rec.classes_per_week) if rec.classes_per_week else False

    def _inverse_classes_per_week_selection(self):
        for rec in self:
            rec.classes_per_week = int(rec.classes_per_week_selection) if rec.classes_per_week_selection else 0

    def _compute_price_from_pricelist(self):
        if self.pricelist_id and self.product_id:
            partner = self.subscription_id._get_billing_partner() if self.subscription_id else None
            self.price = self.pricelist_id._get_product_price(
                self.product_id, self.classes_per_week or 1.0, partner=partner or None)
        else:
            self.price = 0.0

    @api.depends('start_date', 'end_date', 'approval_state', 'subscription_id.state')
    def _compute_state(self):
        today = fields.Date.today()
        for rec in self:
            if rec.subscription_id.state == 'cancelled':
                # A cancelled subscription (e.g. from cancelling its course) must never
                # leave a plan line reading as active/scheduled — this overrides the
                # date/approval-based state below regardless of the line's own dates.
                rec.state = 'cancelled'
            elif rec.approval_state == 'draft':
                rec.state = 'pending_approval'
            elif rec.start_date and rec.start_date > today:
                rec.state = 'scheduled'
            elif rec.end_date and rec.end_date < today:
                rec.state = 'expired'
            else:
                rec.state = 'active'

    def _compute_has_invoices(self):
        for rec in self:
            rec.has_invoices = bool(self.env['account.move'].sudo().search([
                '|', ('tuition_subscription_id', '=', rec.subscription_id.id),
                     ('tuition_subscription_ids', 'in', [rec.subscription_id.id]),
                ('tuition_plan_line_id', '=', rec.id), ('state', '!=', 'cancel'),
            ], limit=1))

    def unlink(self):
        require_permission(self.env.user, 'subscription_plan_delete')
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

    @api.constrains('product_id', 'pricelist_id', 'subscription_id')
    def _check_company_consistency(self):
        for rec in self:
            company = rec.subscription_id.company_id
            if not company:
                continue
            if rec.product_id.company_id and rec.product_id.company_id != company:
                raise ValidationError(
                    "Product '%s' belongs to company '%s', but this subscription is billed "
                    "under company '%s'. Either leave the Company field blank on the product "
                    "(shared across companies) or assign it to '%s'."
                    % (rec.product_id.display_name, rec.product_id.company_id.name,
                       company.name, company.name)
                )
            if rec.pricelist_id.company_id and rec.pricelist_id.company_id != company:
                raise ValidationError(
                    "Pricing list '%s' belongs to company '%s', but this subscription is "
                    "billed under company '%s'. Either leave the Company field blank on the "
                    "pricing list or assign it to '%s'."
                    % (rec.pricelist_id.display_name, rec.pricelist_id.company_id.name,
                       company.name, company.name)
                )

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
        # Content fields: editable only when plan is pending approval.
        # end_date is excluded from the state gate: it can be changed regardless
        # of plan status, as long as the user has the subscription_edit_plan permission.
        CONTENT_FIELDS = {'product_id', 'pricelist_id', 'price', 'classes_per_week', 'notes', 'start_date'}
        if vals.keys() & CONTENT_FIELDS:
            require_permission(self.env.user, 'subscription_edit_plan')
            for rec in self:
                if rec.state != 'pending_approval':
                    raise UserError(
                        "Plan details can only be edited when status is 'Pending Approval'. "
                        "'%s' is currently '%s'." % (rec.product_id.name or 'plan', rec.state)
                    )
        if 'end_date' in vals and not self.env.user.has_group('base.group_system'):
            require_permission(self.env.user, 'subscription_edit_plan')
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
    approval_state = fields.Selection(
        [('draft', 'Draft'), ('approved', 'Approved')],
        default='draft', required=True)  # hidden backend field
    state = fields.Selection([
        ('pending_approval', 'Pending Approval'),
        ('approved', 'Approved'),
        ('applied', 'Applied'),
    ], string='Status', compute='_compute_state', store=True)

    @api.depends('approval_state', 'applied_in_invoice')
    def _compute_state(self):
        for rec in self:
            if rec.approval_state == 'draft':
                rec.state = 'pending_approval'
            elif rec.applied_in_invoice:
                rec.state = 'applied'
            else:
                rec.state = 'approved'

    def init(self):
        self.env.cr.execute(
            "UPDATE tuition_adjustment SET approval_state = 'approved' WHERE approval_state IS NULL"
        )

    def action_approve(self):
        require_permission(self.env.user, 'subscription_approve')
        self.write({'approval_state': 'approved'})

    def action_set_draft(self):
        for rec in self:
            if rec.applied_in_invoice:
                raise UserError("Cannot reset to Pending Approval — this adjustment has already been applied to an invoice.")
        self.write({'approval_state': 'draft'})

    @api.depends('amount', 'adjustment_type')
    def _compute_signed_amount(self):
        for rec in self:
            rec.signed_amount = abs(rec.amount) if rec.adjustment_type == 'extra_charge' else -abs(rec.amount)


class AccountMove(models.Model):
    _inherit = 'account.move'

    tuition_subscription_id = fields.Many2one('tuition.subscription', string='Tuition Subscription', ondelete='set null', index=True)
    tuition_subscription_ids = fields.Many2many('tuition.subscription', 'account_move_tuition_subscription_rel', 'move_id', 'subscription_id', string='Tuition Subscriptions')
    tuition_plan_line_id = fields.Many2one('tuition.plan.line', string='Tuition Plan', ondelete='set null', index=True)
    parent_profile_id = fields.Many2one('parent.profile', string='Parent Profile', ondelete='set null', index=True)
