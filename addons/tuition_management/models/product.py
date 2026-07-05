# -*- coding: utf-8 -*-
from odoo import models, fields


class ProductTemplateTuitionExt(models.Model):
    _inherit = 'product.template'

    subject_id = fields.Many2one(
        'subject.master', string='Subject',
        help='Subject this product represents. Used to restrict which products can be picked '
             'as a tuition plan for a given subscription (matched against the enrolled course\'s subject).'
    )


class ProductProductTuitionExt(models.Model):
    _inherit = 'product.product'

    subject_id = fields.Many2one(related='product_tmpl_id.subject_id', store=True)
    tuition_classes_per_week = fields.Integer(
        string='Tuition: Classes per Week',
        default=0,
        help='Classes per week this specific variant represents (e.g. the "2x/Week" variant of a subject product). '
             'Selecting this product as a tuition plan will auto-fill the subscription plan allowance.'
    )
