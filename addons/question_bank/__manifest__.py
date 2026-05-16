{
    'name': 'Question Bank',
    'version': '19.0.1.0.0',
    'category': 'Education',
    'summary': 'Modern question authoring tool for schools and exams',
    'description': """
        Question Bank for ShiningAce
        ============================
        Create and manage MCQ, True/False, and Fill-in-the-Blank questions
        with rich content: LaTeX math, images, graphs, and HTML.
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
        'views/qb_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'question_bank/static/src/css/question_bank.css',
            'question_bank/static/src/xml/question_editor.xml',
            'question_bank/static/src/js/question_editor.js',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
    'icon': 'question_bank/static/description/icon.png',
}
