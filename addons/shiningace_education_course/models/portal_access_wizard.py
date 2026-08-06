# -*- coding: utf-8 -*-
from odoo import models

_PROFILE_GROUP_XMLIDS = {
    'tutor.profile': 'shiningace_education_core.group_education_tutor',
    'student.profile': 'shiningace_education_core.group_education_student',
}


class PortalAccessWizard(models.TransientModel):
    """tuition_management works standalone without the Curriculum Management
    suite installed, so it only ever assigns base.group_portal itself. Once
    shiningace_education_course IS installed, a tutor/student portal login
    also needs the corresponding education group so the curriculum ACL/
    ir.rule scoping (see education_curriculum_security.xml /
    education_content_security.xml) actually applies to them.
    """
    _inherit = 'portal.access.wizard'

    def _assign_portal_group(self, user):
        super()._assign_portal_group(user)
        group_xmlid = _PROFILE_GROUP_XMLIDS.get(self.profile_model)
        if not group_xmlid:
            return
        group = self.env.ref(group_xmlid, raise_if_not_found=False)
        if group:
            user.sudo().write({'group_ids': [(4, group.id)]})
