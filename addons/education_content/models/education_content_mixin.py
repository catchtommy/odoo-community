# -*- coding: utf-8 -*-
from odoo import fields, models


class EducationContentMixin(models.AbstractModel):
    """Fields shared by every content-bearing model (education.lesson.content,
    education.resource): version/language/download/preview/publish/expiry/
    visibility/ordering, as required by the spec for every learning content item.
    """
    _name = 'education.content.mixin'
    _description = 'Education Content Mixin'

    version = fields.Integer(default=1)
    language_id = fields.Many2one('res.lang', string='Language')
    is_downloadable = fields.Boolean(default=True)
    is_previewable = fields.Boolean(default=True)
    publish_date = fields.Datetime()
    expiry_date = fields.Datetime(help='Leave empty for content with no expiry.')
    visibility = fields.Selection(
        selection=[
            ('internal', 'Internal Only'),
            ('tutor', 'Tutor'),
            ('student', 'Student'),
            ('public', 'Public'),
        ],
        default='internal', required=True, index=True,
    )
    sequence = fields.Integer(default=10)
    state = fields.Selection(
        selection=[('draft', 'Draft'), ('published', 'Published'), ('archived', 'Archived')],
        default='draft', required=True, index=True,
    )
