from odoo import models, fields


class QbTag(models.Model):
    _name = 'qb.tag'
    _description = 'Question Bank Tag'
    _order = 'name'

    name = fields.Char(string='Tag', required=True)
    color = fields.Integer(string='Color', default=0)
