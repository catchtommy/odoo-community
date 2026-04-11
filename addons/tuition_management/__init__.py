# -*- coding: utf-8 -*-
from . import models
from . import controllers


def _create_default_enquiry_stages(env):
    """Create default enquiry stages only if they don't exist. Called on install."""
    Stage = env['enquiry.stage']
    defaults = [
        ('New', 10, False),
        ('Demo Scheduled', 20, False),
        ('Enrolled', 40, True),
        ('Lost', 50, False),
    ]
    for name, sequence, is_enrolled in defaults:
        if not Stage.search([('name', '=', name)], limit=1):
            Stage.create({'name': name, 'sequence': sequence, 'is_enrolled_stage': is_enrolled})
