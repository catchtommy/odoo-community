# -*- coding: utf-8 -*-
from odoo import api, fields, models


class TuitionPricingWizard(models.TransientModel):
    """Read-only pricing browser: products x pricelist tiers, no Sales app access needed."""

    _name = 'tuition.pricing.wizard'
    _description = 'Tuition Pricing Wizard'

    filter_pricelist_id = fields.Many2one('product.pricelist', string='Pricelist')
    filter_product_id = fields.Many2one('product.product', string='Product')
    filter_currency_id = fields.Many2one('res.currency', string='Currency')
    filter_company_id = fields.Many2one('res.company', string='Company')
    filter_number_of_classes = fields.Float(string='Number of Classes')
    line_ids = fields.One2many('tuition.pricing.wizard.line', 'wizard_id', string='Lines')

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        if 'line_ids' in fields_list:
            vals['line_ids'] = [(0, 0, line) for line in self._get_line_values()]
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

        products = self.env['product.product'].search(
            [('id', '=', filter_product_id)] if filter_product_id else [('sale_ok', '=', True)])

        lines = []
        for pricelist in pricelists:
            items = pricelist.item_ids.filtered(
                lambda i: i.product_id in products or (
                    not i.product_id and i.product_tmpl_id in products.product_tmpl_id
                )
            )
            if filter_number_of_classes:
                items = items.filtered(lambda i: (i.min_quantity or 0.0) == filter_number_of_classes)
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
        self.ensure_one()
        self._refresh_lines()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Pricing',
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }

    def action_clear_filters(self):
        self.ensure_one()
        self.write({
            'filter_pricelist_id': False,
            'filter_product_id': False,
            'filter_currency_id': False,
            'filter_company_id': False,
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
