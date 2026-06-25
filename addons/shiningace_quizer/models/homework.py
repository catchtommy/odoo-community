from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ShiningAceHomework(models.Model):
    """
    Homework management model. Assignments composed of questions from the question bank.
    Can be assigned to students with due dates and grading.
    """
    _name = 'shiningace.homework'
    _description = 'ShiningAce Homework'
    _order = 'due_date desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Homework Title', required=True, tracking=True)
    subject_id = fields.Many2one('shiningace.subject', string='Subject', required=True, tracking=True)
    description = fields.Html(string='Description')
    instructions = fields.Html(string='Instructions')

    # Scheduling
    assigned_date = fields.Date(string='Assigned Date', default=fields.Date.today)
    due_date = fields.Date(string='Due Date', required=True, tracking=True)
    submission_deadline = fields.Datetime(string='Submission Deadline')

    # Grading
    total_marks = fields.Float(
        string='Total Marks',
        compute='_compute_total_marks',
        store=True
    )
    auto_grade = fields.Boolean(string='Auto Grade', default=True)

    # Questions
    question_ids = fields.One2many(
        'shiningace.homework.question',
        'homework_id',
        string='Homework Questions',
        copy=True
    )
    question_count = fields.Integer(
        string='Question Count',
        compute='_compute_question_count',
        store=True
    )

    selection_method = fields.Selection([
        ('manual', 'Manual Selection'),
        ('random', 'Random from Subject'),
        ('random_by_tags', 'Random by Tags'),
    ], string='Question Selection Method', default='manual', required=True)

    random_question_count = fields.Integer(string='Number of Questions', default=5)
    random_tag_ids = fields.Many2many(
        'shiningace.question.tag',
        'shiningace_homework_tag_rel',
        string='Tag Filters'
    )

    # Attempts
    allow_multiple_attempts = fields.Boolean(string='Allow Multiple Attempts', default=False)
    max_attempts = fields.Integer(string='Maximum Attempts', default=3)

    # State
    state = fields.Selection([
        ('draft', 'Draft'),
        ('assigned', 'Assigned'),
        ('submitted', 'Submitted'),
        ('graded', 'Graded'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    # Company
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    active = fields.Boolean(string='Active', default=True)

    @api.depends('question_ids', 'question_ids.mark')
    def _compute_total_marks(self):
        for record in self:
            record.total_marks = sum(record.question_ids.mapped('mark'))

    @api.depends('question_ids')
    def _compute_question_count(self):
        for record in self:
            record.question_count = len(record.question_ids)

    @api.constrains('due_date')
    def _check_due_date(self):
        for record in self:
            if record.due_date and record.assigned_date and record.due_date < record.assigned_date:
                raise ValidationError(_('Due date cannot be before the assigned date!'))

    def action_assign(self):
        self.state = 'assigned'

    def action_submit(self):
        self.state = 'submitted'

    def action_grade(self):
        self.state = 'graded'

    def action_draft(self):
        self.state = 'draft'

    def action_cancel(self):
        self.state = 'cancelled'

    def action_generate_random_questions(self):
        """Generate random questions based on selection criteria."""
        self.ensure_one()
        domain = [('subject_id', '=', self.subject_id.id), ('state', '=', 'approved')]

        if self.random_tag_ids:
            domain.append(('tags', 'in', self.random_tag_ids.ids))

        existing_ids = self.question_ids.mapped('question_id.id')
        if existing_ids:
            domain.append(('id', 'not in', existing_ids))

        questions = self.env['shiningace.question'].search(
            domain,
            limit=self.random_question_count,
            order='id'
        )

        HwQuestion = self.env['shiningace.homework.question']
        for question in questions:
            HwQuestion.create({
                'homework_id': self.id,
                'question_id': question.id,
                'mark': question.default_mark,
                'sequence': len(self.question_ids) + 1,
            })


class ShiningAceHomeworkQuestion(models.Model):
    """
    Link table between homework and questions.
    """
    _name = 'shiningace.homework.question'
    _description = 'ShiningAce Homework Question'
    _order = 'sequence, id'

    homework_id = fields.Many2one(
        'shiningace.homework',
        string='Homework',
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
    mark = fields.Float(string='Mark', required=True, default=1.0)
    is_required = fields.Boolean(string='Required', default=True)

    # Answer tracking
    is_answered = fields.Boolean(string='Answered', readonly=True)
    is_correct = fields.Boolean(string='Correct', readonly=True)
    obtained_mark = fields.Float(string='Obtained Mark', readonly=True, default=0.0)
    student_answer = fields.Text(string='Student Answer', readonly=True)

    # Feedback
    feedback_given = fields.Html(string='Feedback Given')
    grader_notes = fields.Text(string='Grader Notes')

    # Related fields for display
    question_type_name = fields.Char(
        string='Question Type',
        related='question_id.question_type_id.name',
        store=True
    )
    difficulty = fields.Selection(
        string='Difficulty',
        related='question_id.difficulty_level',
        store=True
    )

    _sql_constraints = [
        ('homework_question_uniq', 'UNIQUE(homework_id, question_id)',
         'A question can only be added once to a homework assignment!'),
    ]

    @api.onchange('question_id')
    def _onchange_question_id(self):
        if self.question_id:
            self.mark = self.question_id.default_mark
