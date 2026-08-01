# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class EducationSkill(models.Model):
    """A micro learning outcome, uniquely coded for fast lookup/search.

    Lives here (education_curriculum), not in education_core, because it
    FKs education.topic — lower modules must never depend on higher ones.
    """
    _name = 'education.skill'
    _inherit = ['education.abstract.mixin']
    _description = 'Curriculum Skill (Micro Learning Outcome)'
    _order = 'topic_id, sequence, id'

    name = fields.Char(string='Skill Description', required=True, index=True)
    unique_skill_code = fields.Char(
        string='Skill Code', index=True, readonly=True, copy=False,
        help='Auto-generated. Format: SubjectCode.LevelCode.TopicCode.N — e.g. M.Y7.F.3',
    )
    topic_id = fields.Many2one('education.topic', required=True, index=True, ondelete='restrict')
    curriculum_id = fields.Many2one(related='topic_id.curriculum_id', store=True, index=True)
    curriculum_version_id = fields.Many2one(related='topic_id.curriculum_version_id', store=True, index=True)
    subject_id = fields.Many2one(related='topic_id.subject_id', store=True, index=True)
    academic_level_id = fields.Many2one(related='topic_id.academic_level_id', store=True, index=True)
    board_id = fields.Many2one(related='topic_id.board_id', store=True, index=True)
    country_id = fields.Many2one(related='topic_id.country_id', store=True, index=True)

    difficulty_level = fields.Selection(
        selection=[
            ('foundation', 'Foundation'),
            ('core', 'Core'),
            ('extended', 'Extended'),
            ('advanced', 'Advanced'),
        ],
        default='core', index=True,
    )
    sequence = fields.Integer(default=10)
    notes = fields.Text()

    _skill_code_unique = models.Constraint('UNIQUE(unique_skill_code)', 'Skill code must be unique across the system.')

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if not record.unique_skill_code:
                record.unique_skill_code = self._generate_skill_code(record)
        return records

    def _generate_skill_code(self, skill):
        topic = skill.topic_id
        if not topic:
            return False

        subject_code = (topic.subject_id.code or 'X').upper().strip()
        level_code = (topic.academic_level_id.code or topic.academic_level_id.name or 'L').upper().strip().replace(' ', '')
        topic_code = (topic.code or self._auto_topic_code(topic.name)).upper().strip()

        existing_count = self.search_count([('topic_id', '=', topic.id), ('id', '!=', skill.id)])
        next_num = existing_count + 1
        candidate = f"{subject_code}.{level_code}.{topic_code}.{next_num}"
        while self.search_count([('unique_skill_code', '=', candidate)]):
            next_num += 1
            candidate = f"{subject_code}.{level_code}.{topic_code}.{next_num}"

        _logger.debug("Generated skill code: %s for skill: %s", candidate, skill.name)
        return candidate

    @staticmethod
    def _auto_topic_code(topic_name):
        if not topic_name:
            return 'T'
        words = topic_name.strip().split()
        code = ''.join(w[0] for w in words if w)[:4]
        return code.upper() or 'T'

    def regenerate_skill_code(self):
        for skill in self:
            skill.unique_skill_code = self._generate_skill_code(skill)
        return True
