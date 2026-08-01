# -*- coding: utf-8 -*-
from odoo import fields, models


class EducationCurriculumNewVersionWizard(models.TransientModel):
    """Confirmation dialog wrapping education.curriculum.version.action_create_new_version().

    Kept as a thin wizard (rather than a direct button on the version form)
    so users get an explicit "you are about to clone N topics into a new
    draft version" confirmation before the clone happens.
    """
    _name = 'education.curriculum.new.version.wizard'
    _description = 'Create New Curriculum Version'

    source_version_id = fields.Many2one('education.curriculum.version', required=True, readonly=True)
    topic_count = fields.Integer(related='source_version_id.topic_count', readonly=True)

    def action_confirm(self):
        self.ensure_one()
        return self.source_version_id.action_create_new_version()
