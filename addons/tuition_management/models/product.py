# -*- coding: utf-8 -*-
from odoo import models, fields


class ProductProductTuitionExt(models.Model):
    _inherit = 'product.product'

    tuition_classes_per_week = fields.Integer(
        string='Tuition: Classes per Week',
        default=0,
        help='Classes per week this specific variant represents (e.g. the "2x/Week" variant of a subject product). '
             'Selecting this product as a tuition plan will auto-fill the subscription plan allowance.'
    )
