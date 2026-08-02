# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError

_LOCKED_STATES = ('approved', 'published', 'archived')


class EducationTopic(models.Model):
    _name = 'education.topic'
    _inherit = ['education.abstract.mixin', 'mail.thread']
    _description = 'Curriculum Topic'
    _order = 'subject_id, academic_level_id, sequence, name'

    name = fields.Char(required=True, index=True)
    code = fields.Char(size=20, help='Short uppercase code used in skill codes, e.g. F (Fractions), GRA (Grammar)')
    curriculum_version_id = fields.Many2one(
        'education.curriculum.version', required=True, index=True, ondelete='cascade',
        help='Topics belong to a specific curriculum version, not the curriculum itself — '
             'different versions can have entirely different topic structures.',
    )
    curriculum_id = fields.Many2one(related='curriculum_version_id.curriculum_id', store=True, index=True)
    subject_id = fields.Many2one(related='curriculum_version_id.subject_id', store=True, index=True)
    board_id = fields.Many2one(related='curriculum_version_id.board_id', store=True, index=True)
    academic_level_id = fields.Many2one(related='curriculum_version_id.academic_level_id', store=True, index=True)
    country_id = fields.Many2one(related='board_id.country_id', store=True, index=True)

    description = fields.Text(translate=True)
    sequence = fields.Integer(default=10)

    subtopic_ids = fields.One2many('education.subtopic', 'topic_id', string='Subtopics')
    learning_objective_ids = fields.One2many('education.learning.objective', 'topic_id', string='Learning Objectives')
    skill_ids = fields.One2many('education.skill', 'topic_id', string='Skills')
    # Not copied when a topic is cloned into a new version: prerequisite_topic_id
    # would still point at the old version's topic, which needs a remapping pass
    # this simplified Phase-1 clone doesn't perform. Prerequisites must be
    # re-added manually on the new version.
    prerequisite_ids = fields.One2many('education.prerequisite', 'topic_id', string='Prerequisites', copy=False)

    def write(self, vals):
        for rec in self:
            if rec.curriculum_version_id.state in _LOCKED_STATES and set(vals.keys()) - {'active', 'tag_ids'}:
                raise UserError(
                    "This topic belongs to a %s curriculum version and can no longer be edited. "
                    "Use 'Create New Version' on the curriculum version to make changes."
                    % rec.curriculum_version_id.state
                )
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.curriculum_version_id.state in _LOCKED_STATES:
                raise UserError(
                    "Cannot add topics to a %s curriculum version. Use 'Create New Version' instead."
                    % rec.curriculum_version_id.state
                )
        return records

    @api.depends('name', 'subject_id.code', 'academic_level_id.name')
    def _compute_display_name(self):
        for rec in self:
            parts = [p for p in (rec.subject_id.code, rec.academic_level_id.name, rec.name) if p]
            rec.display_name = ' / '.join(parts)
