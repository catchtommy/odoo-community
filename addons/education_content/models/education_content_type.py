# -*- coding: utf-8 -*-
from odoo import fields, models


class EducationContentType(models.Model):
    """Master-data model for content types (Rich Text, PDF, Video, Worksheet, ...).

    A Selection field couldn't be extended by an administrator without a code
    change, so content types are records instead — the ~20 built-ins are
    seeded via data/education_content_type_data.xml (noupdate="1", so admin
    additions/edits survive module upgrades) and new ones can be added freely.
    """
    _name = 'education.content.type'
    _description = 'Learning Content Type'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True, help='Internal technical code, e.g. pdf, video, worksheet')
    icon = fields.Char(help='Font Awesome icon class, e.g. fa-file-pdf-o')
    is_previewable = fields.Boolean(default=True)
    is_downloadable = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint('UNIQUE(code)', 'Content type code must be unique.')
