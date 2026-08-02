# -*- coding: utf-8 -*-
from odoo import fields, models


class EducationCurriculumReview(models.Model):
    """Append-only approval-history / audit log for a curriculum version.

    Created automatically by education.curriculum.version's workflow actions.
    ACLs (see security/ir.model.access.csv) grant create+read only — no
    write/unlink for non-administrators — so the audit trail cannot be
    altered after the fact.
    """
    _name = 'education.curriculum.review'
    _description = 'Curriculum Review / Approval History'
    _order = 'review_date desc, id desc'

    curriculum_version_id = fields.Many2one('education.curriculum.version', required=True, index=True, ondelete='cascade')
    curriculum_id = fields.Many2one(related='curriculum_version_id.curriculum_id', store=True, index=True)
    reviewer_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user)
    review_date = fields.Datetime(default=fields.Datetime.now, required=True)
    action = fields.Selection(
        selection=[
            ('submitted', 'Submitted for Review'),
            ('commented', 'Commented'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('published', 'Published'),
            ('archived', 'Archived'),
        ],
        required=True,
    )
    comments = fields.Text()
    state_from = fields.Char()
    state_to = fields.Char()
