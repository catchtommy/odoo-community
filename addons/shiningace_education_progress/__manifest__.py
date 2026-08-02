# -*- coding: utf-8 -*-
{
    'name': 'Education Progress',
    'version': '19.0.1.0.0',
    'category': 'Education',
    'summary': 'Learning analytics and progress reporting (future phase)',
    'description': """
Education Progress (future phase — not yet implemented)
=========================================================
Will build analytics/rollups (completion trends, weak-topic identification,
tutor comments aggregation, AI recommendations surface) over the base
education.student.progress table already introduced by education_course in
Phase 1, plus assessment scores from education_assessment once that module
exists. Deliberately does not redefine education.student.progress — see
README.md.
    """,
    'author': 'ShiningAce',
    'website': 'https://www.shiningace.com',
    'license': 'LGPL-3',
    'depends': ['shiningace_education_course', 'shiningace_education_assessment'],
    'data': [],
    'installable': False,
    'application': False,
}
