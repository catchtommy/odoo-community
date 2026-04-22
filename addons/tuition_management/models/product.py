# -*- coding: utf-8 -*-
from odoo import models, fields


class ProductTemplateTuitionExt(models.Model):
    _inherit = 'product.template'

    tuition_classes_per_week = fields.Integer(
        string='Tuition: Classes per Week',
        default=0,
        help='If set, selecting this product as a tuition plan will auto-fill the subscription plan allowance (classes per week).'
    )
