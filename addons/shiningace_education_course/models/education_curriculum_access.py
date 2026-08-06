# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class EducationCurriculumAccess(models.Model):
    """Explicit grant letting a specific tutor propose changes (new Topics/
    Subtopics/Lessons/Content) to a specific curriculum.

    This is deliberately separate from *view* access: a tutor can always
    view a curriculum linked (via education.course.curriculum) to a course
    they teach, with no grant needed — this model only controls the
    stronger "may contribute" permission, e.g. a tutor assigned to SAT Math
    courses should not automatically be allowed to edit SAT English just
    because they can see it.

    Revocation is done by archiving (active=False), not deleting, to keep
    an auditable history of who was granted access and when.
    """
    _name = 'education.curriculum.access'
    _description = 'Curriculum Contributor Access'
    _order = 'curriculum_id, tutor_id'

    curriculum_id = fields.Many2one('education.curriculum', required=True, index=True, ondelete='cascade')
    tutor_id = fields.Many2one('tutor.profile', required=True, index=True, ondelete='cascade')
    granted_by = fields.Many2one('res.users', default=lambda self: self.env.user, readonly=True)
    granted_date = fields.Datetime(default=fields.Datetime.now, readonly=True)
    active = fields.Boolean(default=True)

    @api.constrains('curriculum_id', 'tutor_id', 'active')
    def _check_no_duplicate_active_grant(self):
        for rec in self:
            if not rec.active:
                continue
            duplicate = self.search([
                ('id', '!=', rec.id),
                ('curriculum_id', '=', rec.curriculum_id.id),
                ('tutor_id', '=', rec.tutor_id.id),
                ('active', '=', True),
            ], limit=1)
            if duplicate:
                raise ValidationError(
                    "%s already has active contributor access to %s." % (rec.tutor_id.name, rec.curriculum_id.name)
                )
