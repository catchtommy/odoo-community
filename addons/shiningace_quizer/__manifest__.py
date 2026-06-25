{
    'name': 'ShiningAce Quizer - Question Bank & Exam Management',
    'version': '1.0.0',
    'category': 'Education',
    'sequence': 100,
    'summary': 'Centralised question bank, exam and homework management with Moodle XML import support',
    'description': """
ShiningAce Quizer
=================
A comprehensive Odoo module for managing question banks, exams, and homework.

Key Features:
-------------
* Create and store questions across multiple subjects
* Support for all Moodle question types:
  - Multiple Choice (single/multiple answers)
  - True/False
  - Short Answer
  - Numerical
  - Calculated (simple)
  - Essay
  - Matching
  - Drag and Drop (text/images)
  - Cloze (embedded answers / gap-fill)
* Rich content support: equations (LaTeX), images, and graphs
* Dual HTML / LaTeX editors for questions, answers, and feedback
* Moodle XML import for bulk question import
* Exam and homework creation using question bank
* Centralised reusable question repository suitable for:
  Mathematics, English, Physics, Chemistry, and other subjects
* LLM-ready data design for future AI integration

Future Considerations:
---------------------
* The structured data model supports LLM consumption for
  automated question generation, marking, and feedback.
    """,
    'depends': [
        'base',
        'web',
        'mail',
    ],
    'data': [
        'security/shiningace_quizer_security.xml',
        'security/ir.model.access.csv',
        'data/subject_data.xml',
        'data/question_type_data.xml',
        'data/difficulty_data.xml',
        'views/actions.xml',
        'views/question_bank_views.xml',
        'views/question_answer_views.xml',
        'views/question_feedback_views.xml',
        'views/exam_views.xml',
        'views/exam_question_views.xml',
        'views/homework_views.xml',
        'views/subject_views.xml',
        'views/question_type_views.xml',
        'views/tag_views.xml',
        'views/moodle_import_views.xml',
        'views/menu_views.xml',
        'wizards/import_moodle_wizard_views.xml',
        'wizards/question_editor_wizard_views.xml',
    ],
    'demo': [
        'demo/demo_questions.xml',
        'demo/demo_exam.xml',
        'demo/demo_homework.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'shiningace_quizer/static/src/scss/shiningace_quizer.scss',
            'shiningace_quizer/static/src/js/question_editor.js',
            'shiningace_quizer/static/src/js/latex_preview.js',
            'shiningace_quizer/static/src/xml/question_editor_templates.xml',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
    'author': 'ShiningAce',
    'website': 'https://www.shiningace.com',
    'support': 'support@shiningace.com',
    'images': ['static/description/banner.png'],
}
