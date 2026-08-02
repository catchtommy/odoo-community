# -*- coding: utf-8 -*-
{
    'name': 'Education Content',
    'version': '19.0.1.0.0',
    'category': 'Education',
    'summary': 'Lessons, lesson plans and learning content/resources',
    'description': """
Education Content
==================
Builds on education_curriculum to provide:

- Lessons and Lesson Plans attached to a curriculum Topic/Subtopic
- Extensible Content Types (Rich Text, PDF, Video, Worksheet, Quiz, ...)
- Lesson Content items (version/language/visibility/publish/expiry/ordering)
- Standalone, reusable Resources shared across multiple lessons
    """,
    'author': 'ShiningAce',
    'website': 'https://www.shiningace.com',
    'license': 'LGPL-3',
    'depends': ['shiningace_education_curriculum'],
    'data': [
        'security/education_content_security.xml',
        'security/ir.model.access.csv',
        'data/education_content_type_data.xml',
        'views/education_content_type_views.xml',
        'views/education_content_category_views.xml',
        'views/education_lesson_content_views.xml',
        'views/education_lesson_plan_views.xml',
        'views/education_resource_views.xml',
        'views/education_lesson_views.xml',
        'views/education_content_menus.xml',
    ],
    'demo': [
        'demo/education_content_demo.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'shiningace_education_content/static/src/content_preview/content_preview_utils.js',
            'shiningace_education_content/static/src/content_preview/content_preview_dialog.js',
            'shiningace_education_content/static/src/content_preview/content_preview_dialog.xml',
            'shiningace_education_content/static/src/content_preview/content_preview_button.js',
            'shiningace_education_content/static/src/content_preview/content_preview_button.xml',
        ],
    },
    'installable': True,
    'application': False,
}
