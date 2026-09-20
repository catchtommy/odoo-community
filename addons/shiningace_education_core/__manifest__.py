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
    'depends': ['base', 'web', 'mail', 'portal'],
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
    'assets': {
        'web.assets_backend': [
            'shiningace_education_core/static/src/js/mathjax_loader.js',
            'shiningace_education_core/static/src/js/math_typeset.js',
            'shiningace_education_core/static/src/js/mathlive_loader.js',
            'shiningace_education_core/static/src/fields/education_math_text_field.css',
            'shiningace_education_core/static/src/fields/equation_editor_dialog.js',
            'shiningace_education_core/static/src/fields/equation_editor_dialog.xml',
            'shiningace_education_core/static/src/fields/education_math_text_field.js',
            'shiningace_education_core/static/src/fields/education_math_text_field.xml',
        ],
        # Not 'web.assets_frontend': on a normal page load this build only
        # pulls *CSS* from that bundle (t-js="false" in
        # web/views/webclient_templates.xml) — its JS only actually runs via
        # 'web.assets_frontend_minimal' (loaded promptly, deferred) or
        # 'web.assets_frontend_lazy' (loaded lazily, e.g. on first
        # interaction/idle — too late/unreliable for something that should
        # typeset the page as soon as it loads). Registering the loader
        # under plain 'web.assets_frontend' silently put it in the lazy
        # bucket, which is why it wasn't reliably firing on tutor portal
        # pages.
        'web.assets_frontend_minimal': [
            'shiningace_education_core/static/src/js/mathjax_loader.js',
        ],
    },
    'installable': True,
    'application': True,
    'pre_init_hook': '_check_shiningace_curriculum_not_installed',
}
