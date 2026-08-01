# -*- coding: utf-8 -*-
from . import models

from odoo.exceptions import UserError


def _check_shiningace_curriculum_not_installed(env):
    """Guard against installing alongside the retired prototype module.

    ``shiningace_curriculum`` was a throwaway prototype (no production data)
    that this suite replaces with equivalent, renamed models. It must be
    uninstalled first to avoid confusion between the two model sets.
    """
    module = env['ir.module.module'].search([
        ('name', '=', 'shiningace_curriculum'),
        ('state', '=', 'installed'),
    ], limit=1)
    if module:
        raise UserError(
            "The 'shiningace_curriculum' module is still installed and has been "
            "superseded by 'education_core' / 'education_curriculum'. Please "
            "uninstall 'shiningace_curriculum' (Apps > Uninstall) before "
            "installing this module. See education_core/README.md for details."
        )
