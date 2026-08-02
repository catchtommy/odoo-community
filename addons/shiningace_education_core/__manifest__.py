# -*- coding: utf-8 -*-
{
    'name': 'Education Core',
    'version': '19.0.1.0.0',
    'category': 'Education',
    'summary': 'Shared foundation for the ShiningAce Curriculum Management suite',
    'description': """
Education Core
==============
Shared foundation module for the Curriculum Management suite:

- Countries, Education Systems, Exam Boards, Academic Levels, Subjects
- Reusable tagging
- Shared abstract mixin (multi-company, tags, RAG-ready metadata fields)
- Shared security groups used by all downstream education_* modules

All other Curriculum Management modules depend on this module. It carries
no dependency on the retired ``shiningace_curriculum`` prototype module —
see README.md for the migration note.
    """,
    'author': 'ShiningAce',
    'website': 'https://www.shiningace.com',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'portal'],
    'data': [
        'security/education_security.xml',
        'security/ir.model.access.csv',
        'views/education_country_views.xml',
        'views/education_education_system_views.xml',
        'views/education_exam_board_views.xml',
        'views/education_academic_level_views.xml',
        'views/education_subject_views.xml',
        'views/education_curriculum_tag_views.xml',
        'views/education_core_menus.xml',
    ],
    'demo': [
        'demo/education_core_demo.xml',
    ],
    'installable': True,
    'application': True,
    'pre_init_hook': '_check_shiningace_curriculum_not_installed',
}
