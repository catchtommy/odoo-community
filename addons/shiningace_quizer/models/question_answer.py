from odoo import models, fields, api, _


class ShiningAceQuestionAnswer(models.Model):
    """
    Answer options/choices for questions.
    Supports rich content (HTML, LaTeX, images) for both answers and feedback.
    """
    _name = 'shiningace.question.answer'
    _description = 'ShiningAce Question Answer'
    _order = 'sequence, id'

    question_id = fields.Many2one(
        'shiningace.question',
        string='Question',
        required=True,
        ondelete='cascade',
        index=True
    )
    sequence = fields.Integer(string='Sequence', default=10)

    # Answer content - rich text supporting HTML + LaTeX
    answer_text = fields.Html(
        string='Answer Text',
        required=True,
        help="The answer/choice text. Supports HTML and LaTeX ($$...$$)."
    )
    answer_text_plain = fields.Text(
        string='Answer Text (Plain)',
        compute='_compute_plain_text',
        store=True,
        help="Plain text version for LLM consumption"
    )
    answer_latex = fields.Text(
        string='Answer (LaTeX)',
        help="LaTeX source for the answer (alternative rendering)"
    )

    # Correctness
    is_correct = fields.Boolean(
        string='Is Correct',
        default=False,
        help="Whether this answer is correct (for multi-choice types)"
    )
    fraction = fields.Float(
        string='Grade Fraction',
        default=0.0,
        help="Fraction of total grade (0.0 to 1.0). "
             "For MC, correct = 1.0, incorrect = 0.0. "
             "For multiple-answer, can be partial (e.g., 0.5)"
    )

    # Feedback per answer
    feedback = fields.Html(
        string='Feedback',
        help="Specific feedback for this answer choice. Supports HTML and LaTeX."
    )
    feedback_latex = fields.Text(
        string='Feedback (LaTeX)',
        help="LaTeX source for the feedback"
    )

    # Format indicators
    has_images = fields.Boolean(string='Has Images', compute='_check_rich_content', store=True)
    has_latex = fields.Boolean(string='Has LaTeX', compute='_check_rich_content', store=True)

    # For numerical answers
    numerical_answer = fields.Float(string='Numerical Answer')
    numerical_tolerance = fields.Float(string='Tolerance', default=0)

    # View helper
    answer_preview = fields.Html(
        string='Answer Preview',
        compute='_compute_answer_preview',
        help="Shortened preview of the answer text"
    )

    # Constraints
    _sql_constraints = [
        ('check_fraction', 'CHECK(fraction >= 0.0 AND fraction <= 1.0)',
         'Fraction must be between 0.0 and 1.0!'),
    ]

    @api.depends('answer_text')
    def _compute_plain_text(self):
        for record in self:
            if record.answer_text:
                from odoo.tools import html2plaintext
                record.answer_text_plain = html2plaintext(record.answer_text)[:2000]
            else:
                record.answer_text_plain = ''

    @api.depends('answer_text')
    def _check_rich_content(self):
        for record in self:
            record.has_images = False
            record.has_latex = False
            if record.answer_text:
                if '<img' in record.answer_text:
                    record.has_images = True
                if '$$' in record.answer_text or '\\(' in record.answer_text:
                    record.has_latex = True

    @api.depends('answer_text', 'sequence')
    def _compute_answer_preview(self):
        for record in self:
            if record.answer_text:
                from odoo.tools import html2plaintext
                text = html2plaintext(record.answer_text)
                if len(text) > 100:
                    text = text[:97] + '...'
                record.answer_preview = text
            else:
                record.answer_preview = ''
