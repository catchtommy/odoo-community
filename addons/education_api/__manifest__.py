# -*- coding: utf-8 -*-
{
    'name': 'Education API',
    'version': '19.0.1.0.0',
    'category': 'Education',
    'summary': 'REST APIs for Curriculum, Lessons, Progress, Assessments (future phase)',
    'description': """
Education API (future phase — not yet implemented)
======================================================
Will provide authenticated JSON REST endpoints for Curriculum, Lesson,
Topics, Resources, Student Progress, Assessments and Question Bank, built as
plain Odoo http.Controller routes (matching the existing pattern already
used in tuition_management/controllers/) — no third-party REST framework.
    """,
    'author': 'ShiningAce',
    'website': 'https://www.shiningace.com',
    'license': 'LGPL-3',
    'depends': ['education_ai'],
    'data': [],
    'installable': False,
    'application': False,
}
