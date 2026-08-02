# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class EducationLearningObjective(models.Model):
    _name = 'education.learning.objective'
    _inherit = ['education.abstract.mixin']
    _description = 'Learning Objective'
    _order = 'topic_id, subtopic_id, sequence'

    name = fields.Char(string='Objective', required=True, help='e.g. "Understand equivalent fractions"')
    topic_id = fields.Many2one('education.topic', index=True, ondelete='cascade')
    subtopic_id = fields.Many2one('education.subtopic', index=True, ondelete='cascade')
    curriculum_version_id = fields.Many2one(
        compute='_compute_curriculum_version_id', store=True, index=True,
        comodel_name='education.curriculum.version',
    )
    curriculum_id = fields.Many2one(
        compute='_compute_curriculum_id', store=True, index=True,
        comodel_name='education.curriculum',
    )
    bloom_level = fields.Selection(
        selection=[
            ('remember', 'Remember'),
            ('understand', 'Understand'),
            ('apply', 'Apply'),
            ('analyze', 'Analyze'),
            ('evaluate', 'Evaluate'),
            ('create', 'Create'),
        ],
        string='Bloom Taxonomy Level',
    )
    expected_completion_minutes = fields.Integer(string='Expected Completion Time (min)')
    sequence = fields.Integer(default=10)

    @api.depends('topic_id.curriculum_version_id', 'subtopic_id.curriculum_version_id')
    def _compute_curriculum_version_id(self):
        for rec in self:
            rec.curriculum_version_id = rec.topic_id.curriculum_version_id or rec.subtopic_id.curriculum_version_id

    @api.depends('topic_id.curriculum_id', 'subtopic_id.curriculum_id')
    def _compute_curriculum_id(self):
        for rec in self:
            rec.curriculum_id = rec.topic_id.curriculum_id or rec.subtopic_id.curriculum_id

    @api.onchange('topic_id')
    def _onchange_topic_id(self):
        # A learning objective is either topic-level or subtopic-level, never
        # both (see _check_exactly_one_parent) — picking one clears the other
        # instead of making the user discover the conflict at save time.
        if self.topic_id and self.subtopic_id:
            self.subtopic_id = False

    @api.onchange('subtopic_id')
    def _onchange_subtopic_id(self):
        if self.subtopic_id and self.topic_id:
            self.topic_id = False

    @api.constrains('topic_id', 'subtopic_id')
    def _check_exactly_one_parent(self):
        for rec in self:
            if bool(rec.topic_id) == bool(rec.subtopic_id):
                raise ValidationError("A learning objective must be linked to exactly one Topic or one Subtopic.")

    @api.model_create_multi
    def create(self, vals_list):
        # Odoo only auto-triggers @api.constrains for fields present in the
        # create vals; if a caller omits both topic_id and subtopic_id
        # entirely (rather than passing one of them), the constrain above
        # would silently never run. Force the check explicitly so "neither
        # set" is always caught.
        records = super().create(vals_list)
        records._check_exactly_one_parent()
        return records
