# -*- coding: utf-8 -*-
{
    'name': 'Education Curriculum',
    'version': '19.0.1.0.0',
    'category': 'Education',
    'summary': 'Curriculum hierarchy, versioning and approval workflow',
    'description': """
Education Curriculum
=====================
Builds on education_core to provide:

- Curriculum and unlimited Curriculum Versions (Draft > Review > Approved > Published > Archived)
- Topics, Subtopics, Learning Objectives, Skills, Prerequisites
- Stored approval history (education.curriculum.review)
- "New Version" wizard that clones a version's structure into a fresh draft

Published curriculum versions are never edited in place; changes always
happen via a new version, so courses that pinned an older version keep
working unchanged.
    """,
    'author': 'ShiningAce',
    'website': 'https://www.shiningace.com',
    'license': 'LGPL-3',
    'depends': ['shiningace_education_core'],
    'data': [
        'security/education_curriculum_security.xml',
        'security/ir.model.access.csv',
        'views/education_curriculum_tree_action.xml',
        'views/education_curriculum_views.xml',
        'views/education_topic_views.xml',
        'views/education_subtopic_views.xml',
        'views/education_learning_objective_views.xml',
        'views/education_skill_views.xml',
        'views/education_prerequisite_views.xml',
        'wizard/education_curriculum_new_version_wizard_views.xml',
        'views/education_curriculum_version_views.xml',
        'views/education_curriculum_menus.xml',
    ],
    'demo': [
        'demo/education_curriculum_demo.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'shiningace_education_curriculum/static/src/curriculum_tree/curriculum_tree.js',
            'shiningace_education_curriculum/static/src/curriculum_tree/curriculum_tree.xml',
            'shiningace_education_curriculum/static/src/curriculum_list/curriculum_list_controller.js',
        ],
    },
    'installable': True,
    'application': False,
}
