# -*- coding: utf-8 -*-
from odoo import api, fields, models


class EducationCurriculum(models.Model):
    """A curriculum identity/container, e.g. "GCSE Mathematics (AQA)".

    Carries no workflow state itself — all structure (topics, subtopics,
    learning objectives, skills) and the Draft/Review/Approved/Published/
    Archived lifecycle live on education.curriculum.version, so a single
    curriculum can have unlimited versions across time without ever losing
    or overwriting an older one.
    """
    _name = 'education.curriculum'
    _inherit = ['education.abstract.mixin', 'mail.thread', 'mail.activity.mixin']
    _description = 'Curriculum'
    _order = 'name'

    name = fields.Char(required=True, index=True, tracking=True)
    code = fields.Char(index=True)
    description = fields.Text(translate=True)
    subject_id = fields.Many2one('education.subject', required=True, index=True, ondelete='restrict', tracking=True)
    education_system_id = fields.Many2one('education.education.system', index=True, ondelete='restrict')
    board_id = fields.Many2one('education.exam.board', string='Exam Board', index=True, ondelete='restrict')
    academic_level_id = fields.Many2one('education.academic.level', index=True, ondelete='restrict')

    version_ids = fields.One2many('education.curriculum.version', 'curriculum_id', string='Versions')
    version_count = fields.Integer(compute='_compute_version_count')
    current_version_id = fields.Many2one(
        'education.curriculum.version', compute='_compute_current_version_id', string='Latest Published Version',
        help='The most recently published version, shown for convenience when browsing. '
             'Never used programmatically to resolve "the" version of a course\'s curriculum — '
             'courses always point at a specific pinned version (see education_course).',
    )

    @api.depends('version_ids')
    def _compute_version_count(self):
        for rec in self:
            rec.version_count = len(rec.version_ids)

    @api.depends('version_ids.state', 'version_ids.published_date')
    def _compute_current_version_id(self):
        for rec in self:
            published = rec.version_ids.filtered(lambda v: v.state == 'published')
            rec.current_version_id = max(published, key=lambda v: v.published_date or v.create_date) if published else False

    def action_view_versions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Curriculum Versions',
            'res_model': 'education.curriculum.version',
            'view_mode': 'list,form',
            'domain': [('curriculum_id', '=', self.id)],
            'context': {'default_curriculum_id': self.id},
        }

    def action_view_structure_tree(self):
        """Open the Curriculum -> Version -> Topic -> Subtopic -> Learning Objectives/Skills
        collapsible tree client action (see static/src/curriculum_tree).

        Uses `active_id` (not a custom context key) because that is the one
        context key Odoo's action service persists into the browser URL/
        history for client actions — anything else breaks the browser back
        button, since it can't reconstruct which curriculum to show.
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'education_curriculum_tree',
            'name': self.name,
            'context': {'active_id': self.id},
        }

    def action_create_first_version(self):
        self.ensure_one()
        version = self.env['education.curriculum.version'].create({
            'curriculum_id': self.id,
            'version_label': 'v1',
            'version_number': 1,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Curriculum Version',
            'res_model': 'education.curriculum.version',
            'view_mode': 'form',
            'res_id': version.id,
        }
