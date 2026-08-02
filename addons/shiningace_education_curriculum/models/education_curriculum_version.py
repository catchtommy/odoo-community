# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

# Identity fields that must never change once a version has left draft — doing so
# would silently rewrite which curriculum/version-number a published version
# represents. Everything else (workflow state, admin notes, dates, tags) stays
# editable; true *content* immutability is enforced on education.topic and its
# children, which refuse structural edits once their version is locked.
_LOCKED_IDENTITY_FIELDS = {'curriculum_id', 'version_number'}


class EducationCurriculumVersion(models.Model):
    """The workflowed, contentful unit of a curriculum.

    Publishing never mutates an already-published version's structure — to
    change a published curriculum, a new version is created (see the "New
    Version" wizard) and goes through the workflow independently. This is
    what guarantees old versions stay accessible and courses keep using the
    exact version they were assigned to (see education_course).
    """
    _name = 'education.curriculum.version'
    _inherit = ['education.abstract.mixin', 'mail.thread', 'mail.activity.mixin']
    _description = 'Curriculum Version'
    _order = 'curriculum_id, version_number desc'

    curriculum_id = fields.Many2one('education.curriculum', required=True, index=True, ondelete='restrict', tracking=True)
    version_label = fields.Char(required=True, default='v1', tracking=True)
    version_number = fields.Integer(required=True, default=1)
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('review', 'Review'),
            ('approved', 'Approved'),
            ('published', 'Published'),
            ('archived', 'Archived'),
        ],
        default='draft', required=True, index=True, tracking=True,
    )

    effective_from = fields.Date()
    effective_to = fields.Date()
    language_id = fields.Many2one('res.lang', string='Language')

    reviewer_id = fields.Many2one('res.users')
    approved_by = fields.Many2one('res.users', readonly=True)
    approved_date = fields.Datetime(readonly=True)
    published_date = fields.Datetime(readonly=True)
    archived_date = fields.Datetime(readonly=True)
    parent_version_id = fields.Many2one('education.curriculum.version', string='Cloned From', readonly=True)

    topic_ids = fields.One2many('education.topic', 'curriculum_version_id', string='Topics')
    topic_count = fields.Integer(compute='_compute_topic_count')
    review_ids = fields.One2many('education.curriculum.review', 'curriculum_version_id', string='Approval History')

    subject_id = fields.Many2one(related='curriculum_id.subject_id', store=True, index=True)
    board_id = fields.Many2one(related='curriculum_id.board_id', store=True, index=True)
    academic_level_id = fields.Many2one(related='curriculum_id.academic_level_id', store=True, index=True)

    _curriculum_version_unique = models.Constraint(
        'UNIQUE(curriculum_id, version_number)', 'Version number must be unique per curriculum.',
    )

    @api.depends('topic_ids')
    def _compute_topic_count(self):
        for rec in self:
            rec.topic_count = len(rec.topic_ids)

    # ------------------------------------------------------------------
    # Immutability guard
    # ------------------------------------------------------------------
    def write(self, vals):
        protected = set(vals.keys()) & _LOCKED_IDENTITY_FIELDS
        locking_states = {'approved', 'published', 'archived'}
        if protected:
            for rec in self:
                if rec.state in locking_states:
                    raise UserError(
                        "This curriculum version is %s — its identity (curriculum/version number) "
                        "can no longer be changed. Use 'Create New Version' instead." % rec.state
                    )
        return super().write(vals)

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def _log_review(self, action, state_from, state_to, comments=False):
        for rec in self:
            self.env['education.curriculum.review'].create({
                'curriculum_version_id': rec.id,
                'reviewer_id': self.env.user.id,
                'action': action,
                'comments': comments,
                'state_from': state_from,
                'state_to': state_to,
            })

    def action_submit_review(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError("Only draft versions can be submitted for review.")
            if not rec.topic_ids:
                raise UserError("Add at least one topic before submitting for review.")
            rec.state = 'review'
            rec._log_review('submitted', 'draft', 'review')

    def action_approve(self):
        if not (self.env.user.has_group('shiningace_education_core.group_education_reviewer')
                or self.env.user.has_group('shiningace_education_core.group_education_curriculum_manager')):
            raise UserError("You are not allowed to approve curriculum versions.")
        for rec in self:
            if rec.state != 'review':
                raise UserError("Only versions in review can be approved.")
            rec.write({'state': 'approved', 'approved_by': self.env.user.id, 'approved_date': fields.Datetime.now()})
            rec._log_review('approved', 'review', 'approved')

    def action_reject(self, comments=False):
        for rec in self:
            if rec.state != 'review':
                raise UserError("Only versions in review can be rejected.")
            rec.state = 'draft'
            rec._log_review('rejected', 'review', 'draft', comments=comments)

    def action_publish(self):
        if not self.env.user.has_group('shiningace_education_core.group_education_curriculum_manager'):
            raise UserError("Only a Curriculum Manager can publish a curriculum version.")
        for rec in self:
            if rec.state != 'approved':
                raise UserError("Only approved versions can be published.")
            rec.write({'state': 'published', 'published_date': fields.Datetime.now()})
            rec._log_review('published', 'approved', 'published')

    def action_archive(self):
        if not self.env.user.has_group('shiningace_education_core.group_education_curriculum_manager'):
            raise UserError("Only a Curriculum Manager can archive a curriculum version.")
        for rec in self:
            if rec.state != 'published':
                raise UserError("Only published versions can be archived.")
            rec.write({'state': 'archived', 'archived_date': fields.Datetime.now()})
            rec._log_review('archived', 'published', 'archived')

    def action_reset_draft(self):
        for rec in self:
            if rec.state not in ('review',):
                raise UserError("Only versions in review can be reset to draft.")
            rec.state = 'draft'
            rec._log_review('commented', 'review', 'draft', comments='Reset to draft')

    # ------------------------------------------------------------------
    # New version cloning
    # ------------------------------------------------------------------
    def action_create_new_version(self):
        self.ensure_one()
        next_number = max(self.curriculum_id.version_ids.mapped('version_number'), default=0) + 1
        new_version = self.copy({
            'version_label': f"v{next_number}",
            'version_number': next_number,
            'state': 'draft',
            'parent_version_id': self.id,
            'approved_by': False,
            'approved_date': False,
            'published_date': False,
            'archived_date': False,
        })
        for topic in self.topic_ids:
            topic.copy({'curriculum_version_id': new_version.id})
        return {
            'type': 'ir.actions.act_window',
            'name': 'New Curriculum Version',
            'res_model': 'education.curriculum.version',
            'view_mode': 'form',
            'res_id': new_version.id,
        }
