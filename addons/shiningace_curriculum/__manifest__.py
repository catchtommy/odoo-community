# -*- coding: utf-8 -*-
{
    'name': 'ShiningAce Curriculum',
    'version': '19.0.1.0.0',
    'category': 'Education',
    'summary': 'Hierarchical curriculum management: Country → Board → Grade → Subject → Topic → Skill',
    'description': """
        om_curriculum_base
        ==================
        Core curriculum intelligence system for education platforms.

        Supports:
        - Multi-country curriculum structures
        - Exam board variations (GCSE, IB, SAT, CBSE, etc.)
        - Hierarchical curriculum mapping
        - Auto-generated skill codes
        - Large-scale skill datasets (100k+ records)
        - Future AI + assessment integration
    """,
    'author': 'ShiningAce',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/curriculum_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
