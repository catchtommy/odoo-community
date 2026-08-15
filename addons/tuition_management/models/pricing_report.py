# -*- coding: utf-8 -*-
from odoo import api, fields, models


class TuitionPricingWizard(models.TransientModel):
    """Read-only pricing browser: products x pricelist tiers, no Sales app access needed."""

    _name = 'tuition.pricing.wizard'
    _description = 'Tuition Pricing Wizard'

    def _compute_display_name(self):
        # No meaningful `name` field on this wizard — the default implementation
        # falls back to "model,id" (e.g. "tuition.pricing.wizard,3"), which is
        # confusing shown as the breadcrumb title. Show "Pricing" instead.
        for rec in self:
            rec.display_name = 'Pricing'

    def _default_filter_company_id(self):
        company = self.env['res.company'].search([('name', 'ilike', 'US Shiningace')], limit=1)
        return company or self.env.company

    def _default_filter_currency_id(self):
        return self._currency_for_company(self._default_filter_company_id())

    def _currency_for_company(self, company):
        usd = self.env.ref('base.USD', raise_if_not_found=False) or self.env['res.currency'].search(
            [('name', '=', 'USD')], limit=1)
        allowed = company.tuition_currency_ids
        if allowed:
            return usd if usd in allowed else allowed[:1]
        return usd

    filter_company_id = fields.Many2one('res.company', string='Company', default=_default_filter_company_id)
    filter_currency_id = fields.Many2one('res.currency', string='Currency', default=_default_filter_currency_id)
    filter_product_id = fields.Many2one('product.product', string='Product')
    filter_pricelist_id = fields.Many2one('product.pricelist', string='Pricelist')
    filter_number_of_classes = fields.Selection(
        [(str(n), str(n)) for n in range(1, 8)],
        string='Number of Classes',
        help='Number of classes per week.',
    )
    line_ids = fields.One2many('tuition.pricing.wizard.line', 'wizard_id', string='Lines')

    allowed_currency_ids = fields.Many2many('res.currency', compute='_compute_allowed_currency_ids')
    allowed_product_ids = fields.Many2many('product.product', compute='_compute_allowed_product_ids')
    allowed_pricelist_ids = fields.Many2many('product.pricelist', compute='_compute_allowed_pricelist_ids')

    @api.depends('filter_company_id')
    def _compute_allowed_currency_ids(self):
        all_currencies = self.env['res.currency'].search([])
        for rec in self:
            rec.allowed_currency_ids = rec.filter_company_id.tuition_currency_ids or all_currencies

    @api.depends('filter_company_id', 'filter_currency_id')
    def _compute_allowed_product_ids(self):
        for rec in self:
            pricelists = rec._pricelists_for_filters(exclude_pricelist=True, exclude_product=True)
            rec.allowed_product_ids = rec._products_for_pricelists(pricelists)

    @api.depends('filter_company_id', 'filter_currency_id', 'filter_product_id')
    def _compute_allowed_pricelist_ids(self):
        for rec in self:
            rec.allowed_pricelist_ids = rec._pricelists_for_filters(exclude_pricelist=True)

    def _pricelists_for_filters(self, exclude_pricelist=False, exclude_product=False):
        domain = []
        if self.filter_company_id:
            domain.append(('company_id', 'in', [self.filter_company_id.id, False]))
        if self.filter_currency_id:
            domain.append(('currency_id', '=', self.filter_currency_id.id))
        if not exclude_pricelist and self.filter_pricelist_id:
            domain.append(('id', '=', self.filter_pricelist_id.id))
        pricelists = self.env['product.pricelist'].search(domain)
        if not exclude_product and self.filter_product_id:
            pricelists = pricelists.filtered(lambda pl: self._pricelist_has_product(pl, self.filter_product_id))
        return pricelists

    @staticmethod
    def _pricelist_has_product(pricelist, product):
        items = pricelist.item_ids
        return product in items.product_id or product.product_tmpl_id in items.product_tmpl_id

    def _products_for_pricelists(self, pricelists):
        items = pricelists.item_ids
        products = items.product_id
        tmpl_products = self.env['product.product'].search([
            ('product_tmpl_id', 'in', items.product_tmpl_id.ids),
            ('sale_ok', '=', True),
        ])
        return products | tmpl_products

    @api.onchange('filter_company_id')
    def _onchange_filter_company_id(self):
        self.filter_currency_id = self._currency_for_company(self.filter_company_id)
        self.filter_product_id = False
        self.filter_pricelist_id = False

    @api.onchange('filter_currency_id')
    def _onchange_filter_currency_id(self):
        self.filter_product_id = False
        self.filter_pricelist_id = False

    @api.onchange('filter_product_id')
    def _onchange_filter_product_id(self):
        if self.filter_pricelist_id and self.filter_product_id and not self._pricelist_has_product(
                self.filter_pricelist_id, self.filter_product_id):
            self.filter_pricelist_id = False

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        if 'line_ids' in fields_list:
            vals['line_ids'] = [(0, 0, line) for line in self._get_line_values(
                filter_company_id=vals.get('filter_company_id'),
                filter_currency_id=vals.get('filter_currency_id'),
            )]
        return vals

    def _get_line_values(self, filter_pricelist_id=None, filter_product_id=None,
                          filter_currency_id=None, filter_company_id=None,
                          filter_number_of_classes=None):
        pricelist_domain = []
        if filter_pricelist_id:
            pricelist_domain.append(('id', '=', filter_pricelist_id))
        if filter_currency_id:
            pricelist_domain.append(('currency_id', '=', filter_currency_id))
        if filter_company_id:
            pricelist_domain.append(('company_id', 'in', [filter_company_id, False]))
        pricelists = self.env['product.pricelist'].search(pricelist_domain)

        if filter_product_id:
            product_domain = [('id', '=', filter_product_id)]
        else:
            product_domain = [('sale_ok', '=', True)]
            if filter_company_id:
                product_domain.append(('company_id', 'in', [filter_company_id, False]))
        products = self.env['product.product'].search(product_domain)

        lines = []
        for pricelist in pricelists:
            items = pricelist.item_ids.filtered(
                lambda i: i.product_id in products or (
                    not i.product_id and i.product_tmpl_id in products.product_tmpl_id
                )
            )
            if filter_number_of_classes:
                items = items.filtered(lambda i: (i.min_quantity or 0.0) == float(filter_number_of_classes))
            for item in items:
                product = item.product_id or products.filtered(
                    lambda p: p.product_tmpl_id == item.product_tmpl_id)[:1]
                if not product:
                    continue
                price = pricelist._get_product_price(product, item.min_quantity or 1.0)
                lines.append({
                    'product_id': product.id,
                    'pricelist_id': pricelist.id,
                    'number_of_classes': item.min_quantity,
                    'price': price,
                    'currency_id': pricelist.currency_id.id,
                    'company_id': pricelist.company_id.id,
                })
        lines.sort(key=lambda l: (l['product_id'], l['pricelist_id'], l['number_of_classes']))
        return lines

    def _refresh_lines(self):
        for rec in self:
            rec.line_ids.unlink()
            for line in rec._get_line_values(
                filter_pricelist_id=rec.filter_pricelist_id.id or None,
                filter_product_id=rec.filter_product_id.id or None,
                filter_currency_id=rec.filter_currency_id.id or None,
                filter_company_id=rec.filter_company_id.id or None,
                filter_number_of_classes=rec.filter_number_of_classes or None,
            ):
                line['wizard_id'] = rec.id
                self.env['tuition.pricing.wizard.line'].create(line)

    def action_refresh(self):
        # Refresh in place — must NOT return a new act_window action, or the
        # client pushes a second, duplicate breadcrumb/header for the same record.
        self.ensure_one()
        self._refresh_lines()

    def action_clear_filters(self):
        self.ensure_one()
        company = self._default_filter_company_id()
        self.write({
            'filter_pricelist_id': False,
            'filter_product_id': False,
            'filter_company_id': company.id,
            'filter_currency_id': self._currency_for_company(company).id,
            'filter_number_of_classes': False,
        })
        return self.action_refresh()


class TuitionPricingWizardLine(models.TransientModel):
    """One line per (product, pricelist, number of classes) tier."""

    _name = 'tuition.pricing.wizard.line'
    _description = 'Tuition Pricing Wizard Line'
    _order = 'product_id, pricelist_id, number_of_classes'

    wizard_id = fields.Many2one('tuition.pricing.wizard', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    pricelist_id = fields.Many2one('product.pricelist', string='Pricelist', readonly=True)
    number_of_classes = fields.Float(string='Number of Classes', readonly=True)
    price = fields.Monetary(string='Price', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
