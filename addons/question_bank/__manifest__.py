{
    'name': 'Question Bank',
    'version': '19.0.2.0.0',
    'category': 'Education',
    'summary': 'Moodle-style Question Bank Management System',
    'description': """
        Question Bank for ShiningAce
        ============================
        Comprehensive question bank management system with Moodle-style interface:
        
        Key Features:
        * Question Bank with grid view and advanced filters
        * Multiple question types (MCQ, True/False, Fill in Blank)
        * Question versioning and history
        * Tags and metadata management
        * Bulk actions (move, tag, duplicate, delete)
        * Import from Moodle XML
        * Question preview and inline editing
        * Usage statistics and analytics
        * Shared question pools
        * LaTeX and image support
    """,
    'author': 'ShiningAce',
    'depends': ['base', 'web', 'mail'],
    'data': [
        'security/qb_groups.xml',
        'security/ir.model.access.csv',
        'views/qb_subject_views.xml',
        'views/qb_topic_views.xml',
        'views/qb_tag_views.xml',
        'views/qb_question_views.xml',
        'views/qb_question_bank_views.xml',
        'views/qb_question_tag_views.xml',
        'views/qb_moodle_import_views.xml',
        'views/qb_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'question_bank/static/src/css/question_bank.css',
            'question_bank/static/src/xml/question_editor.xml',
            'question_bank/static/src/js/mathjax_loader.js',
            'question_bank/static/src/js/question_editor.js',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
    'icon': 'question_bank/static/description/icon.png',
}
