from odoo import models, fields, api, _


class ShiningAceQuestionType(models.Model):
    """
    Question types supported by the system, mirroring Moodle's question types.
    """
    _name = 'shiningace.question.type'
    _description = 'ShiningAce Question Type'
    _order = 'sequence, name'

    name = fields.Char(string='Type Name', required=True, translate=True)
    code = fields.Char(
        string='Code',
        required=True,
        size=50,
        help="Internal code matching Moodle question type identifiers"
    )
    description = fields.Text(string='Description', translate=True)
    sequence = fields.Integer(string='Sequence', default=10)
    icon = fields.Char(string='Icon', help="CSS class for icon")

    # Configuration
    allow_multiple_answers = fields.Boolean(
        string='Allow Multiple Answers',
        default=False,
        help="Whether this question type supports multiple correct answers"
    )
    has_choices = fields.Boolean(
        string='Has Choices',
        default=True,
        help="Whether this question type uses predefined choices/options"
    )
    has_numerical_answer = fields.Boolean(
        string='Has Numerical Answer',
        default=False,
        help="Whether this question type uses numerical input"
    )
    has_text_answer = fields.Boolean(
        string='Has Text Answer',
        default=False,
        help="Whether this question type uses free text input"
    )
    has_matching = fields.Boolean(
        string='Has Matching',
        default=False,
        help="Whether this question type uses matching pairs"
    )
    has_drag_drop = fields.Boolean(
        string='Has Drag and Drop',
        default=False,
        help="Whether this question type uses drag and drop"
    )
    has_cloze = fields.Boolean(
        string='Has Cloze (Embedded Answers)',
        default=False,
        help="Whether this question type uses embedded answers (gap-fill)"
    )
    has_essay = fields.Boolean(
        string='Has Essay',
        default=False,
        help="Whether this question type requires essay-style answers"
    )
    has_calculated = fields.Boolean(
        string='Has Calculated',
        default=False,
        help="Whether this question type uses calculated/numeric formulae"
    )
    supports_images = fields.Boolean(string='Supports Images', default=True)
    supports_latex = fields.Boolean(string='Supports LaTeX', default=True)
    supports_feedback = fields.Boolean(string='Supports Feedback', default=True)

    # LLM metadata
    llm_prompt_template = fields.Text(
        string='LLM Prompt Template',
        help="Template prompt for LLM question generation for this type"
    )
    llm_eval_template = fields.Text(
        string='LLM Evaluation Template',
        help="Template prompt for LLM-based answer evaluation"
    )

    active = fields.Boolean(string='Active', default=True)

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Question type code must be unique!'),
    ]

    @api.model
    def _get_moodle_types(self):
        """
        Returns mapping of Moodle question types to our codes.
        This covers all standard Moodle question types.
        """
        return {
            'multichoice': 'multichoice',
            'truefalse': 'truefalse',
            'shortanswer': 'shortanswer',
            'numerical': 'numerical',
            'calculated': 'calculated',
            'calculatedsimple': 'calculated_simple',
            'calculatedmulti': 'calculated_multi',
            'essay': 'essay',
            'matching': 'matching',
            'draganddrop': 'drag_drop',
            'draganddropimage': 'drag_drop_image',
            'draganddropmarker': 'drag_drop_marker',
            'cloze': 'cloze',
            'description': 'description',
            'randomsamatch': 'random_short_match',
        }
