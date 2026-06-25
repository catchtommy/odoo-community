from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import timedelta


class ShiningAceExam(models.Model):
    """
    Exam management model. Exams are composed of questions from the question bank.
    Supports scheduled exams with time limits, random question selection, etc.
    """
    _name = 'shiningace.exam'
    _description = 'ShiningAce Exam'
    _order = 'exam_date desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Exam Name', required=True, tracking=True)
    code = fields.Char(string='Exam Code', size=20, help="Short code for reference")
    subject_id = fields.Many2one('shiningace.subject', string='Subject', required=True, tracking=True)
    description = fields.Text(string='Description')
    instructions = fields.Html(string='Instructions')

    # Scheduling
    exam_date = fields.Datetime(string='Exam Date', tracking=True)
    duration_minutes = fields.Integer(string='Duration (minutes)', default=60, required=True)
    start_time = fields.Datetime(string='Start Time')
    end_time = fields.Datetime(string='End Time')
    time_limit_minutes = fields.Integer(string='Time Limit (minutes)', help="Time limit to complete the exam")

    # Grading
    total_marks = fields.Float(
        string='Total Marks',
        compute='_compute_total_marks',
        store=True
    )
    passing_marks = fields.Float(string='Passing Marks', default=0)
    pass_percentage = fields.Float(string='Pass Percentage', default=40.0,
                                    help="Percentage of total marks required to pass")
    auto_grade = fields.Boolean(string='Auto Grade', default=True,
                                 help="Automatically grade objective-type questions")

    # Question Selection
    question_ids = fields.One2many(
        'shiningace.exam.question',
        'exam_id',
        string='Exam Questions',
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
        ('random_by_difficulty', 'Random by Difficulty'),
    ], string='Question Selection Method', default='manual', required=True)

    random_question_count = fields.Integer(
        string='Number of Questions',
        default=10,
        help="Number of questions to randomly select"
    )
    random_difficulty = fields.Selection([
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
        ('very_hard', 'Very Hard'),
        ('all', 'All Levels'),
    ], string='Difficulty Filter', default='all')
    random_tag_ids = fields.Many2many(
        'shiningace.question.tag',
        'shiningace_exam_tag_rel',
        string='Tag Filters'
    )

    # Shuffle options
    shuffle_questions = fields.Boolean(string='Shuffle Questions', default=False)
    shuffle_answers = fields.Boolean(string='Shuffle Answers Within Questions', default=False)

    # State
    state = fields.Selection([
        ('draft', 'Draft'),
        ('ready', 'Ready'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('graded', 'Graded'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)

    # Attempts
    max_attempts = fields.Integer(string='Maximum Attempts', default=1)
    attempts_count = fields.Integer(string='Attempts Count', compute='_compute_attempts_count')

    # Grading info
    graded_by = fields.Many2one('res.users', string='Graded By')
    graded_date = fields.Datetime(string='Graded Date')

    # Company
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    active = fields.Boolean(string='Active', default=True)

    _sql_constraints = [
        ('code_company_uniq', 'UNIQUE(code, company_id)', 'Exam code must be unique per company!'),
    ]

    @api.depends('question_ids', 'question_ids.mark')
    def _compute_total_marks(self):
        for record in self:
            record.total_marks = sum(record.question_ids.mapped('mark'))

    @api.depends('question_ids')
    def _compute_question_count(self):
        for record in self:
            record.question_count = len(record.question_ids)

    def _compute_attempts_count(self):
        for record in self:
            record.attempts_count = self.env['shiningace.exam.attempt'].search_count(
                [('exam_id', '=', record.id)]
            )

    @api.constrains('duration_minutes')
    def _check_duration(self):
        for record in self:
            if record.duration_minutes <= 0:
                raise ValidationError(_('Exam duration must be positive.'))

    @api.constrains('pass_percentage')
    def _check_pass_percentage(self):
        for record in self:
            if record.pass_percentage < 0 or record.pass_percentage > 100:
                raise ValidationError(_('Pass percentage must be between 0 and 100.'))

    def action_ready(self):
        self.state = 'ready'

    def action_start(self):
        self.state = 'in_progress'

    def action_complete(self):
        self.state = 'completed'

    def action_grade(self):
        self.state = 'graded'
        self.graded_by = self.env.user.id
        self.graded_date = fields.Datetime.now()

    def action_draft(self):
        self.state = 'draft'

    def action_cancel(self):
        self.state = 'cancelled'

    def action_generate_random_questions(self):
        """Generate random questions based on selection criteria."""
        self.ensure_one()
        domain = [('subject_id', '=', self.subject_id.id), ('state', '=', 'approved')]

        if self.random_difficulty != 'all':
            domain.append(('difficulty_level', '=', self.random_difficulty))

        if self.random_tag_ids:
            domain.append(('tags', 'in', self.random_tag_ids.ids))

        # Find available questions not already in the exam
        existing_question_ids = self.question_ids.mapped('question_id.id')
        if existing_question_ids:
            domain.append(('id', 'not in', existing_question_ids))

        questions = self.env['shiningace.question'].search(
            domain,
            limit=self.random_question_count,
            order='id'
        )

        ExamQuestion = self.env['shiningace.exam.question']
        for question in questions:
            ExamQuestion.create({
                'exam_id': self.id,
                'question_id': question.id,
                'mark': question.default_mark,
                'sequence': len(self.question_ids) + 1,
            })
