# -*- coding: utf-8 -*-
from odoo import fields, models


class EducationAbstractMixin(models.AbstractModel):
    """Shared fields for (almost) every model in the Curriculum Management suite.

    Provides multi-company support, reusable tagging, and RAG-ready metadata
    fields (``keywords`` / ``ai_description`` / ``embedding_synced``) so a
    future ``education_ai`` module can add embeddings/vector search without
    any schema changes to the models that inherit this mixin.
    """
    _name = 'education.abstract.mixin'
    _description = 'Education Abstract Mixin'

    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Company', default=lambda self: self.env.company, index=True,
    )
    tag_ids = fields.Many2many('education.curriculum.tag', string='Tags')

    keywords = fields.Char(
        translate=True,
        help='Free-text search keywords for this record. Used by full-text search '
             'and, in future, by embeddings-based retrieval (RAG).',
    )
    ai_description = fields.Text(
        string='AI Description',
        translate=True,
        help='Long-form description/summary intended for embeddings and AI generation '
             'features (lesson plans, quizzes, revision notes). Kept separate from any '
             'UI-facing description field so it can be authored or AI-generated independently.',
    )
    embedding_synced = fields.Boolean(
        string='Embedding Synced',
        default=False,
        help='Set by education_ai once this record has been vectorized for RAG retrieval.',
    )
