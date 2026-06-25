from odoo import models, fields, api


class ShiningAceQuestionFeedback(models.Model):
    """
    Feedback associated with questions. Supports:
    - General feedback (shown after any answer)
    - Feedback for correct/incorrect/partially correct answers
    - Per-answer feedback
    """
    _name = 'shiningace.question.feedback'
    _description = 'ShiningAce Question Feedback'
    _order = 'sequence, id'

    question_id = fields.Many2one(
        'shiningace.question',
        string='Question',
        required=True,
        ondelete='cascade',
        index=True
    )
    sequence = fields.Integer(string='Sequence', default=10)
    feedback_type = fields.Selection([
        ('general', 'General Feedback'),
        ('correct', 'Correct Answer Feedback'),
        ('incorrect', 'Incorrect Answer Feedback'),
        ('partially_correct', 'Partially Correct Feedback'),
        ('answer_specific', 'Answer-Specific Feedback'),
    ], string='Feedback Type', required=True, default='general')

    feedback_text = fields.Html(
        string='Feedback Text',
        required=True,
        help="Feedback content. Supports HTML and LaTeX ($$...$$)."
    )
    feedback_latex = fields.Text(
        string='Feedback (LaTeX)',
        help="LaTeX source for feedback"
    )

    has_images = fields.Boolean(string='Has Images', compute='_check_rich_content', store=True)
    has_latex = fields.Boolean(string='Has LaTeX', compute='_check_rich_content', store=True)

    # Condition for answer-specific feedback
    answer_id = fields.Many2one(
        'shiningace.question.answer',
        string='Related Answer',
        help="Link this feedback to a specific answer choice"
    )

    @api.depends('feedback_text')
    def _check_rich_content(self):
        for record in self:
            record.has_images = False
            record.has_latex = False
            if record.feedback_text:
                if '<img' in record.feedback_text:
                    record.has_images = True
                if '$$' in record.feedback_text or '\\(' in record.feedback_text:
                    record.has_latex = True
