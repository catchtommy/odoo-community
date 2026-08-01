# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class EducationResource(models.Model):
    """Library-style resource reusable across many lessons (e.g. a general
    "Periodic Table PDF"), as opposed to education.lesson.content which
    belongs to exactly one lesson.
    """
    _name = 'education.resource'
    _inherit = ['education.abstract.mixin', 'education.content.mixin', 'mail.thread']
    _description = 'Learning Resource'
    _order = 'name'

    name = fields.Char(required=True, index=True)
    content_type_id = fields.Many2one('education.content.type', required=True, index=True, ondelete='restrict')
    subject_id = fields.Many2one('education.subject', index=True, ondelete='restrict')
    academic_level_id = fields.Many2one('education.academic.level', index=True, ondelete='restrict')

    attachment_id = fields.Many2one('ir.attachment', string='File', ondelete='restrict')
    external_url = fields.Char()

    lesson_ids = fields.Many2many('education.lesson', string='Used in Lessons')
    lesson_count = fields.Integer(compute='_compute_lesson_count')

    @api.depends('lesson_ids')
    def _compute_lesson_count(self):
        for rec in self:
            rec.lesson_count = len(rec.lesson_ids)

    @api.constrains('attachment_id', 'external_url')
    def _check_has_payload(self):
        for rec in self:
            if not (rec.attachment_id or rec.external_url):
                raise ValidationError(f"Resource '{rec.name}' needs a file or an external URL.")

    @api.model_create_multi
    def create(self, vals_list):
        # See education.learning.objective.create(): constrains only auto-fire
        # for fields present in vals, so force the check when both payload
        # fields are omitted entirely.
        records = super().create(vals_list)
        records._check_has_payload()
        return records
