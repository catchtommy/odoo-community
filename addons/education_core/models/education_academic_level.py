# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class EducationAcademicLevel(models.Model):
    """Hierarchical academic level: Year, Grade, Stage, Foundation, Higher, Programme,
    Semester, Term, or any custom label an education system needs.

    A single self-referential model (rather than separate "group"/"level" models)
    keeps the hierarchy open-ended: a Key Stage can contain Years, a Programme can
    contain Semesters which contain Terms, etc. ``level_type`` distinguishes a
    grouping node from a leaf node for UI purposes only; nesting depth is unlimited.
    """
    _name = 'education.academic.level'
    _inherit = ['education.abstract.mixin']
    _description = 'Education Academic Level'
    _order = 'education_system_id, sequence, name'
    _parent_store = True

    name = fields.Char(string='Level Name', required=True, index=True)
    code = fields.Char(string='Level Code', size=10, index=True)
    level_type = fields.Selection(
        selection=[
            ('group', 'Grouping (e.g. Key Stage, Programme)'),
            ('level', 'Level (e.g. Year, Grade, Semester, Term)'),
        ],
        string='Type', default='level', required=True,
    )
    education_system_id = fields.Many2one('education.education.system', string='Education System',
                                           required=True, index=True, ondelete='restrict')
    country_id = fields.Many2one(related='education_system_id.country_id', store=True, index=True)
    parent_id = fields.Many2one('education.academic.level', string='Parent Level', index=True, ondelete='restrict')
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many('education.academic.level', 'parent_id', string='Child Levels')
    sequence = fields.Integer(default=10)

    @api.constrains('parent_id')
    def _check_parent_not_recursive(self):
        if self._has_cycle():
            raise ValidationError("An academic level cannot be its own ancestor.")

    @api.depends('name', 'parent_id.name')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.parent_id.name} / {rec.name}" if rec.parent_id else rec.name
