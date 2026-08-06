# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.exceptions import UserError


class EducationCurriculumApprovalMixin(models.AbstractModel):
    """Shared moderation fields for curriculum content a tutor can propose
    (Topic, Subtopic, Lesson, Lesson Content).

    Defaults to 'approved' so every existing record and everything created
    through the normal backend (curriculum manager) flow is unaffected —
    only the tutor-portal proposal routes explicitly create records with
    approval_state='pending'.
    """
    _name = 'education.curriculum.approval.mixin'
    _description = 'Education Curriculum Approval Mixin'

    approval_state = fields.Selection(
        selection=[
            ('approved', 'Approved'),
            ('pending', 'Pending Review'),
            ('rejected', 'Rejected'),
        ],
        default='approved', required=True, index=True, tracking=True,
    )
    proposed_by_id = fields.Many2one('res.users', string='Proposed By', readonly=True)
    reviewed_by_id = fields.Many2one('res.users', string='Reviewed By', readonly=True)
    review_date = fields.Datetime(readonly=True)
    review_notes = fields.Text()

    def _check_can_review_proposal(self):
        if not (self.env.user.has_group('shiningace_education_core.group_education_reviewer')
                or self.env.user.has_group('shiningace_education_core.group_education_curriculum_manager')):
            raise UserError("You are not allowed to approve or reject curriculum proposals.")

    def action_approve_proposal(self):
        self._check_can_review_proposal()
        for rec in self:
            if rec.approval_state != 'pending':
                raise UserError("Only pending proposals can be approved.")
            rec.write({
                'approval_state': 'approved',
                'reviewed_by_id': self.env.user.id,
                'review_date': fields.Datetime.now(),
            })

    def action_reject_proposal(self, notes=False):
        self._check_can_review_proposal()
        for rec in self:
            if rec.approval_state != 'pending':
                raise UserError("Only pending proposals can be rejected.")
            rec.write({
                'approval_state': 'rejected',
                'reviewed_by_id': self.env.user.id,
                'review_date': fields.Datetime.now(),
                'review_notes': notes or rec.review_notes,
            })
