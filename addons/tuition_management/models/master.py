# -*- coding: utf-8 -*-
from odoo import models, fields, api


class SubjectMasterExt(models.Model):
    _inherit = 'subject.master'

    category_id = fields.Many2one('subject.category', string='Category')


class GradeMaster(models.Model):
    _name = 'grade.master'
    _description = 'Grade Master'

    name = fields.Char(string='Grade Name', required=True)


class TuitionTimeSlot(models.Model):
    _name = 'tuition.time.slot'
    _description = 'Time Slot'

    hour = fields.Integer(string='Hour', required=True)
    minute = fields.Integer(string='Minute', required=True)
    name = fields.Char(string='Time', compute='_compute_name', store=True)

    @api.depends('hour', 'minute')
    def _compute_name(self):
        for rec in self:
            rec.name = f'{rec.hour:02d}:{rec.minute:02d}'
