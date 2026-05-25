# -*- coding: utf-8 -*-
"""
om_curriculum_base — Core Curriculum Intelligence Models
=========================================================
Hierarchy: Country → Exam Board → Grade Group → Grade Level
    _constraints = [
        models.Constraint(
            'UNIQUE(code)',
            'Country code must be unique.',
        ),
    ]               → Subject → Topic → Skill

Skill Code Format:  {SubjectCode}.{GradeLevel}.{TopicCode}.{SkillNumber}
Example:            M.5.F.3  |  S.7.CE.1  |  E.6.GRA.2
"""

import logging
from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# LEARNING COUNTRY
# ─────────────────────────────────────────────────────────────────────────────

class LearningCountry(models.Model):
    _name = 'learning.country'
    _description = 'Learning Country'
    _order = 'name asc'

    name = fields.Char(
        string='Country Name',
        required=True,
        index=True,
    )
    code = fields.Char(
        string='Country Code',
        size=10,
        index=True,
        help='Short code, e.g. UK, US, IN',
    )
    active = fields.Boolean(default=True)

    # Reverse relations for smart buttons
    board_ids = fields.One2many('exam.board', 'country_id', string='Exam Boards')
    group_ids = fields.One2many('grade.group', 'country_id', string='Grade Groups')

    board_count = fields.Integer(compute='_compute_counts', string='Boards')
    group_count = fields.Integer(compute='_compute_counts', string='Grade Groups')

    _code_unique = models.Constraint('UNIQUE(code)', 'Country code must be unique.')

    @api.depends('board_ids', 'group_ids')
    def _compute_counts(self):
        for rec in self:
            rec.board_count = len(rec.board_ids)
            rec.group_count = len(rec.group_ids)

    def name_get(self):
        return [(rec.id, f"{rec.name} ({rec.code})" if rec.code else rec.name) for rec in self]


# ─────────────────────────────────────────────────────────────────────────────
# EXAM BOARD
# ─────────────────────────────────────────────────────────────────────────────

class ExamBoard(models.Model):
    _name = 'exam.board'
    _description = 'Exam Board'
    _order = 'country_id, name'

    name = fields.Char(string='Board Name', required=True, index=True)
    code = fields.Char(string='Board Code', size=20, index=True)
    country_id = fields.Many2one(
        'learning.country',
        string='Country',
        required=True,
        index=True,
        ondelete='restrict',
    )
    description = fields.Text(string='Description')
    active = fields.Boolean(default=True)

    topic_count = fields.Integer(compute='_compute_topic_count', string='Topics')

    _code_country_unique = models.Constraint('UNIQUE(code, country_id)', 'Board code must be unique per country.')

    @api.depends()
    def _compute_topic_count(self):
        # Group count for performance
        data = self.env['curriculum.topic'].read_group(
            [('board_id', 'in', self.ids)],
            ['board_id'],
            ['board_id'],
        )
        count_map = {d['board_id'][0]: d['board_id_count'] for d in data}
        for rec in self:
            rec.topic_count = count_map.get(rec.id, 0)

    def name_get(self):
        return [(rec.id, f"{rec.name} [{rec.country_id.code or rec.country_id.name}]") for rec in self]


# ─────────────────────────────────────────────────────────────────────────────
# GRADE GROUP
# ─────────────────────────────────────────────────────────────────────────────

class GradeGroup(models.Model):
    _name = 'grade.group'
    _description = 'Grade Group'
    _order = 'country_id, sequence, name'

    name = fields.Char(string='Group Name', required=True, index=True)
    country_id = fields.Many2one(
        'learning.country',
        string='Country',
        required=True,
        index=True,
        ondelete='restrict',
    )
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(default=True)

    level_ids = fields.One2many('grade.level', 'group_id', string='Grade Levels')
    level_count = fields.Integer(compute='_compute_level_count', string='Levels')

    @api.depends('level_ids')
    def _compute_level_count(self):
        for rec in self:
            rec.level_count = len(rec.level_ids)


# ─────────────────────────────────────────────────────────────────────────────
# GRADE LEVEL
# ─────────────────────────────────────────────────────────────────────────────

class GradeLevel(models.Model):
    _name = 'grade.level'
    _description = 'Grade Level'
    _order = 'group_id, sequence, name'

    name = fields.Char(string='Grade Level', required=True, index=True)
    code = fields.Char(string='Grade Code', size=10, index=True)
    group_id = fields.Many2one(
        'grade.group',
        string='Grade Group',
        required=True,
        index=True,
        ondelete='restrict',
    )
    country_id = fields.Many2one(
        related='group_id.country_id',
        string='Country',
        store=True,
        index=True,
    )
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(default=True)

    topic_count = fields.Integer(compute='_compute_topic_count', string='Topics')

    @api.depends()
    def _compute_topic_count(self):
        data = self.env['curriculum.topic'].read_group(
            [('grade_id', 'in', self.ids)],
            ['grade_id'],
            ['grade_id'],
        )
        count_map = {d['grade_id'][0]: d['grade_id_count'] for d in data}
        for rec in self:
            rec.topic_count = count_map.get(rec.id, 0)

    def name_get(self):
        return [(rec.id, f"{rec.group_id.name} — {rec.name}" if rec.group_id else rec.name) for rec in self]


# ─────────────────────────────────────────────────────────────────────────────
# CURRICULUM SUBJECT
# ─────────────────────────────────────────────────────────────────────────────

class CurriculumSubject(models.Model):
    _name = 'curriculum.subject'
    _description = 'Curriculum Subject'
    _order = 'name asc'

    name = fields.Char(string='Subject Name', required=True, index=True)
    code = fields.Char(
        string='Subject Code',
        required=True,
        size=10,
        index=True,
        help='Short uppercase code used in Skill Codes, e.g. M (Maths), E (English), S (Science)',
    )
    description = fields.Text(string='Description')
    active = fields.Boolean(default=True)

    topic_count = fields.Integer(compute='_compute_topic_count', string='Topics')
    skill_count = fields.Integer(compute='_compute_skill_count', string='Skills')

    _code_unique = models.Constraint('UNIQUE(code)', 'Subject code must be unique.')

    @api.depends()
    def _compute_topic_count(self):
        data = self.env['curriculum.topic'].read_group(
            [('subject_id', 'in', self.ids)],
            ['subject_id'],
            ['subject_id'],
        )
        count_map = {d['subject_id'][0]: d['subject_id_count'] for d in data}
        for rec in self:
            rec.topic_count = count_map.get(rec.id, 0)

    @api.depends()
    def _compute_skill_count(self):
        data = self.env['curriculum.skill'].read_group(
            [('subject_id', 'in', self.ids)],
            ['subject_id'],
            ['subject_id'],
        )
        count_map = {d['subject_id'][0]: d['subject_id_count'] for d in data}
        for rec in self:
            rec.skill_count = count_map.get(rec.id, 0)

    @api.constrains('code')
    def _check_code_uppercase(self):
        for rec in self:
            if rec.code and rec.code != rec.code.upper():
                raise ValidationError("Subject code must be UPPERCASE (e.g. M, E, S, SCI).")


# ─────────────────────────────────────────────────────────────────────────────
# CURRICULUM TOPIC
# ─────────────────────────────────────────────────────────────────────────────

class CurriculumTopic(models.Model):
    _name = 'curriculum.topic'
    _description = 'Curriculum Topic'
    _order = 'subject_id, grade_id, sequence, name'

    name = fields.Char(string='Topic Name', required=True, index=True)
    code = fields.Char(
        string='Topic Code',
        size=20,
        index=True,
        help='Short uppercase code used in Skill Codes, e.g. F (Fractions), GRA (Grammar)',
    )
    board_id = fields.Many2one(
        'exam.board',
        string='Exam Board',
        index=True,
        ondelete='restrict',
    )
    country_id = fields.Many2one(
        related='board_id.country_id',
        string='Country',
        store=True,
        index=True,
    )
    grade_id = fields.Many2one(
        'grade.level',
        string='Grade Level',
        required=True,
        index=True,
        ondelete='restrict',
    )
    group_id = fields.Many2one(
        related='grade_id.group_id',
        string='Grade Group',
        store=True,
        index=True,
    )
    subject_id = fields.Many2one(
        'curriculum.subject',
        string='Subject',
        required=True,
        index=True,
        ondelete='restrict',
    )
    description = fields.Text(string='Description')
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(default=True)

    skill_ids = fields.One2many('curriculum.skill', 'topic_id', string='Skills')
    skill_count = fields.Integer(compute='_compute_skill_count', string='Skills', store=True)

    @api.depends('skill_ids')
    def _compute_skill_count(self):
        for rec in self:
            rec.skill_count = len(rec.skill_ids)

    def name_get(self):
        result = []
        for rec in self:
            parts = []
            if rec.subject_id:
                parts.append(rec.subject_id.code or rec.subject_id.name)
            if rec.grade_id:
                parts.append(rec.grade_id.name)
            parts.append(rec.name)
            result.append((rec.id, ' / '.join(parts)))
        return result

    @api.constrains('code')
    def _check_code_uppercase(self):
        for rec in self:
            if rec.code and rec.code != rec.code.upper():
                raise ValidationError("Topic code must be UPPERCASE (e.g. F, GRA, CE).")


# ─────────────────────────────────────────────────────────────────────────────
# CURRICULUM SKILL
# ─────────────────────────────────────────────────────────────────────────────

class CurriculumSkill(models.Model):
    _name = 'curriculum.skill'
    _description = 'Curriculum Skill (Micro Learning Outcome)'
    _order = 'topic_id, sequence, id'

    name = fields.Char(string='Skill Description', required=True, index=True)
    unique_skill_code = fields.Char(
        string='Skill Code',
        index=True,
        readonly=True,
        copy=False,
        help='Auto-generated. Format: SubjectCode.Grade.TopicCode.SkillNumber — e.g. M.5.F.3',
    )

    topic_id = fields.Many2one(
        'curriculum.topic',
        string='Topic',
        required=True,
        index=True,
        ondelete='restrict',
    )

    # Stored related fields for fast filtering / search
    subject_id = fields.Many2one(
        related='topic_id.subject_id',
        string='Subject',
        store=True,
        index=True,
    )
    grade_id = fields.Many2one(
        related='topic_id.grade_id',
        string='Grade Level',
        store=True,
        index=True,
    )
    board_id = fields.Many2one(
        related='topic_id.board_id',
        string='Exam Board',
        store=True,
        index=True,
    )
    country_id = fields.Many2one(
        related='topic_id.country_id',
        string='Country',
        store=True,
        index=True,
    )

    difficulty_level = fields.Selection(
        selection=[
            ('foundation', 'Foundation'),
            ('core', 'Core'),
            ('extended', 'Extended'),
            ('advanced', 'Advanced'),
        ],
        string='Difficulty Level',
        default='core',
        index=True,
    )
    sequence = fields.Integer(string='Sequence', default=10)
    notes = fields.Text(string='Notes / Context')
    active = fields.Boolean(default=True)

    _skill_code_unique = models.Constraint('UNIQUE(unique_skill_code)', 'Skill code must be unique across the system.')

    # ── Skill Code Auto-Generation ──────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        """Auto-generate unique_skill_code on creation if not provided."""
        records = super().create(vals_list)
        for record in records:
            if not record.unique_skill_code:
                record.unique_skill_code = self._generate_skill_code(record)
        return records

    def _generate_skill_code(self, skill):
        """
        Generate skill code in format: {SubjectCode}.{GradeLevel}.{TopicCode}.{SkillNumber}

        Example: M.5.F.3
        """
        topic = skill.topic_id
        if not topic:
            return False

        subject_code = (topic.subject_id.code or 'X').upper().strip()
        grade_name = (topic.grade_id.code or topic.grade_id.name or 'G').upper().strip().replace(' ', '')
        topic_code = (topic.code or self._auto_topic_code(topic.name)).upper().strip()

        # Determine next sequential number for this topic
        existing = self.search([
            ('topic_id', '=', topic.id),
            ('id', '!=', skill.id),
            ('unique_skill_code', '!=', False),
        ], order='id asc')

        next_num = len(existing) + 1

        # Ensure uniqueness by incrementing if collision occurs
        candidate = f"{subject_code}.{grade_name}.{topic_code}.{next_num}"
        while self.search_count([('unique_skill_code', '=', candidate)]) > 0:
            next_num += 1
            candidate = f"{subject_code}.{grade_name}.{topic_code}.{next_num}"

        _logger.debug("Generated skill code: %s for skill: %s", candidate, skill.name)
        return candidate

    @staticmethod
    def _auto_topic_code(topic_name):
        """
        Auto-derive a topic code from topic name if no code is set.
        Takes first letter of each word, max 4 chars.
        e.g. 'Fractions' → 'F', 'Cell Energy' → 'CE'
        """
        if not topic_name:
            return 'T'
        words = topic_name.strip().split()
        code = ''.join(w[0] for w in words if w)[:4]
        return code.upper() or 'T'

    def regenerate_skill_code(self):
        """Manual action to regenerate skill codes (use carefully)."""
        for skill in self:
            skill.unique_skill_code = self._generate_skill_code(skill)
        return True
