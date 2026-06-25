from odoo import models, fields, api


class ShiningAceExamQuestion(models.Model):
    """
    Link table between exams and questions.
    Stores per-question settings within an exam.
    """
    _name = 'shiningace.exam.question'
    _description = 'ShiningAce Exam Question'
    _order = 'sequence, id'

    exam_id = fields.Many2one(
        'shiningace.exam',
        string='Exam',
        required=True,
        ondelete='cascade',
        index=True
    )
    question_id = fields.Many2one(
        'shiningace.question',
        string='Question',
        required=True,
        ondelete='restrict',
        domain=[('state', 'in', ('approved',))],
        index=True
    )
    sequence = fields.Integer(string='Sequence', default=10)

    # Override settings for this exam
    mark = fields.Float(string='Mark', required=True, default=1.0)
    is_required = fields.Boolean(string='Required', default=True)
    shuffle_answers = fields.Boolean(
        string='Shuffle Answers',
        help="Override shuffle setting for this specific question"
    )

    # Answer tracking
    is_answered = fields.Boolean(string='Answered', readonly=True)
    is_correct = fields.Boolean(string='Correct', readonly=True)
    obtained_mark = fields.Float(string='Obtained Mark', readonly=True, default=0.0)
    student_answer = fields.Text(string='Student Answer', readonly=True)

    # Feedback
    feedback_given = fields.Html(string='Feedback Given')
    grader_notes = fields.Text(string='Grader Notes')

    # Question type info for display
    question_type_name = fields.Char(
        string='Question Type',
        related='question_id.question_type_id.name',
        store=True
    )
    question_subject = fields.Char(
        string='Subject',
        related='question_id.subject_id.name',
        store=True
    )
    difficulty = fields.Selection(
        string='Difficulty',
        related='question_id.difficulty_level',
        store=True
    )

    _sql_constraints = [
        ('exam_question_uniq', 'UNIQUE(exam_id, question_id)',
         'A question can only be added once to an exam!'),
    ]

    @api.onchange('question_id')
    def _onchange_question_id(self):
        if self.question_id:
            self.mark = self.question_id.default_mark
