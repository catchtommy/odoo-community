# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class EducationLessonContent(models.Model):
    _name = 'education.lesson.content'
    _inherit = ['education.abstract.mixin', 'education.content.mixin', 'mail.thread']
    _description = 'Lesson Content'
    _order = 'lesson_id, sequence'

    name = fields.Char(required=True, index=True)
    lesson_id = fields.Many2one('education.lesson', required=True, index=True, ondelete='cascade')
    content_type_id = fields.Many2one('education.content.type', required=True, index=True, ondelete='restrict')
    content_category_id = fields.Many2one('education.content.category', index=True)

    attachment_id = fields.Many2one('ir.attachment', string='File', ondelete='restrict')
    external_url = fields.Char(help='For External URL / YouTube content types.')
    body = fields.Html(translate=True, help='For Rich Text content type.')

    previous_version_id = fields.Many2one('education.lesson.content', string='Previous Version', readonly=True)

    _index_lesson_sequence = models.Index('(lesson_id, sequence)')
    _index_type = models.Index('(content_type_id)')
    _index_state_visibility = models.Index('(state, visibility)')

    @api.constrains('attachment_id', 'external_url', 'body')
    def _check_has_payload(self):
        for rec in self:
            if not (rec.attachment_id or rec.external_url or rec.body):
                raise ValidationError(
                    f"Content '{rec.name}' needs a file, an external URL, or rich text body."
                )

    @api.model_create_multi
    def create(self, vals_list):
        # See education.learning.objective.create(): constrains only auto-fire
        # for fields present in vals, so force the check when all three
        # payload fields are omitted entirely.
        records = super().create(vals_list)
        records._check_has_payload()
        return records

    def action_new_version(self):
        """Create a new content record carrying the version forward, keeping the old one for history."""
        self.ensure_one()
        return self.copy({
            'version': self.version + 1,
            'previous_version_id': self.id,
            'state': 'draft',
        })
