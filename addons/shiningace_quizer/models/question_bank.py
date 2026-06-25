from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import base64
import json


class ShiningAceQuestion(models.Model):
    """
    Core question bank model - stores all questions across all subjects.
    Designed for rich content (LaTeX equations, images, graphs) and
    structured for LLM consumption.
    """
    _name = 'shiningace.question'
    _description = 'ShiningAce Question'
    _order = 'create_date desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # Basic Information
    name = fields.Char(string='Question Name', required=True, index=True, tracking=True)
    question_text = fields.Html(
        string='Question Text',
        required=True,
        help="Main question content. Supports HTML and LaTeX (use $$...$$ for equations)."
    )
    question_text_plain = fields.Text(
        string='Question Text (Plain)',
        compute='_compute_plain_text',
        store=True,
        help="Plain text version for LLM consumption and search indexing"
    )
    default_mark = fields.Float(string='Default Mark', default=1.0, required=True)
    general_feedback = fields.Html(
        string='General Feedback',
        help="Feedback shown after answering, supports HTML and LaTeX"
    )

    # Type and Subject
    question_type_id = fields.Many2one(
        'shiningace.question.type',
        string='Question Type',
        required=True,
        tracking=True
    )
    subject_id = fields.Many2one(
        'shiningace.subject',
        string='Subject',
        required=True,
        tracking=True
    )
    difficulty_level = fields.Selection([
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
        ('very_hard', 'Very Hard'),
    ], string='Difficulty Level', default='medium', tracking=True, index=True)
    difficulty_score = fields.Float(
        string='Difficulty Score',
        default=5.0,
        help="Numerical difficulty score (1-10 scale)"
    )
    estimated_time = fields.Integer(
        string='Estimated Time (minutes)',
        help="Estimated time to answer in minutes"
    )

    # Categorization
    tags = fields.Many2many('shiningace.question.tag', string='Tags')
    topic = fields.Char(string='Topic', help="Specific topic within the subject", index=True)
    bloom_taxonomy = fields.Selection([
        ('remember', 'Remember'),
        ('understand', 'Understand'),
        ('apply', 'Apply'),
        ('analyze', 'Analyze'),
        ('evaluate', 'Evaluate'),
        ('create', 'Create'),
    ], string='Bloom\'s Taxonomy Level', help="Cognitive level according to Bloom's taxonomy")

    # Rich Content
    question_latex = fields.Text(
        string='Question (LaTeX)',
        help="LaTeX source for the question (alt rendering)"
    )
    has_images = fields.Boolean(string='Has Images', compute='_check_rich_content', store=True)
    has_latex = fields.Boolean(string='Has LaTeX', compute='_check_rich_content', store=True)
    has_graph = fields.Boolean(string='Has Graphs/Diagrams', help="Manually set if question includes graphs")
    image_ids = fields.One2many(
        'shiningace.question.image',
        'question_id',
        string='Images'
    )

    # Question-type specific data (JSON)
    type_config = fields.Text(
        string='Type Configuration',
        help="JSON configuration specific to question type (e.g., shuffle options for MC)"
    )

    # Answer Management
    answer_ids = fields.One2many(
        'shiningace.question.answer',
        'question_id',
        string='Answers/Choices',
        copy=True
    )
    feedback_ids = fields.One2many(
        'shiningace.question.feedback',
        'question_id',
        string='Feedback'
    )
    correct_answer_count = fields.Integer(
        string='Correct Answers',
        compute='_compute_answer_stats',
        store=True
    )
    total_answer_count = fields.Integer(
        string='Total Answers',
        compute='_compute_answer_stats',
        store=True
    )

    # Answer fields for types without choices
    numerical_answer = fields.Float(string='Numerical Answer')
    numerical_tolerance = fields.Float(string='Numerical Tolerance', default=0.0)
    text_answer = fields.Text(string='Text Answer')
    text_answer_format = fields.Selection([
        ('plain', 'Plain Text'),
        ('html', 'HTML'),
        ('latex', 'LaTeX'),
    ], string='Text Answer Format', default='plain')

    # For matching questions
    matching_pairs = fields.One2many(
        'shiningace.question.matching',
        'question_id',
        string='Matching Pairs'
    )

    # For drag and drop
    drag_items = fields.One2many(
        'shiningace.question.dragdrop',
        'question_id',
        string='Drag & Drop Items'
    )

    # For calculated questions
    calculated_formula = fields.Text(
        string='Formula',
        help="Formula for calculated questions, e.g. {a} + {b}"
    )
    calculated_vars = fields.Text(
        string='Variables',
        help="JSON defining variables: min, max, step, distribution"
    )
    calculated_answer_format = fields.Char(
        string='Answer Format',
        default='0.00',
        help="Number format for calculated answer, e.g. 0.00"
    )

    # For cloze questions
    cloze_text = fields.Text(
        string='Cloze/Gap-fill Text',
        help="Text with embedded answers using {1:MC:option1~option2} syntax (Moodle-compatible)"
    )

    # Metadata
    reference = fields.Char(string='Reference', help="External reference ID (e.g., Moodle question ID)")
    moodle_id = fields.Integer(
        string='Moodle Question ID',
        help="Original question ID from Moodle export"
    )
    moodle_xml = fields.Text(
        string='Moodle XML',
        help="Original Moodle XML export data for reference"
    )
    version = fields.Integer(string='Version', default=1)
    usage_count = fields.Integer(
        string='Usage Count',
        default=0,
        help="How many times this question has been used in exams/homework"
    )
    last_used_date = fields.Datetime(string='Last Used')

    # LLM metadata
    llm_embedding = fields.Binary(
        string='LLM Embedding',
        attachment=True,
        help="Vector embedding for LLM-based question retrieval (future use)"
    )
    llm_metadata = fields.Text(
        string='LLM Metadata',
        help="JSON metadata for LLM consumption: concepts, keywords, dependencies"
    )

    # State
    state = fields.Selection([
        ('draft', 'Draft'),
        ('review', 'Under Review'),
        ('approved', 'Approved'),
        ('archived', 'Archived'),
    ], string='Status', default='draft', tracking=True, index=True)
    reviewed_by = fields.Many2one('res.users', string='Reviewed By')
    reviewed_date = fields.Datetime(string='Reviewed Date')

    # Company
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    active = fields.Boolean(string='Active', default=True)

    # SQL Constraints
    _sql_constraints = [
        ('check_mark_positive', 'CHECK(default_mark > 0)', 'Default mark must be positive!'),
        ('check_difficulty', 'CHECK(difficulty_score >= 1 AND difficulty_score <= 10)',
         'Difficulty score must be between 1 and 10!'),
    ]

    # ---------------------------
    # Compute Methods
    # ---------------------------
    @api.depends('question_text')
    def _compute_plain_text(self):
        for record in self:
            if record.question_text:
                # Strip HTML tags for plain text version
                from odoo.tools import html2plaintext
                plain = html2plaintext(record.question_text)
                # Limit length to avoid huge fields
                record.question_text_plain = plain[:5000]
            else:
                record.question_text_plain = ''

    @api.depends('question_text')
    def _check_rich_content(self):
        for record in self:
            record.has_images = False
            record.has_latex = False
            if record.question_text:
                if '<img' in record.question_text or 'src=' in record.question_text:
                    record.has_images = True
                if '$$' in record.question_text or '\\(' in record.question_text or '\\[' in record.question_text:
                    record.has_latex = True

    @api.depends('answer_ids', 'answer_ids.is_correct')
    def _compute_answer_stats(self):
        for record in self:
            answers = record.answer_ids
            record.total_answer_count = len(answers)
            record.correct_answer_count = len(answers.filtered('is_correct'))

    # ---------------------------
    # Constraints & Validations
    # ---------------------------
    @api.constrains('question_type_id', 'answer_ids')
    def _check_answers(self):
        for record in self:
            if record.question_type_id.code in ('multichoice', 'truefalse'):
                if not record.answer_ids:
                    raise ValidationError(_(
                        'Questions of type "%s" require at least one answer/choice.') %
                        record.question_type_id.name
                    )
                if record.question_type_id.code == 'truefalse':
                    if len(record.answer_ids) != 2:
                        raise ValidationError(_(
                            'True/False questions require exactly two answers (True and False).'))

    # ---------------------------
    # CRUD Overrides
    # ---------------------------
    @api.model_create_multi
    def create(self, vals_list):
        questions = super().create(vals_list)
        for question in questions:
            # Log creation in chatter
            question.message_post(
                body=_('Question created: %s') % question.name,
                subject=_('Question Created')
            )
        return questions

    def write(self, vals):
        if 'state' in vals and vals.get('state') == 'review':
            vals['reviewed_by'] = self.env.user.id
            vals['reviewed_date'] = fields.Datetime.now()
        return super().write(vals)

    def action_approve(self):
        self.state = 'approved'

    def action_review(self):
        self.state = 'review'

    def action_draft(self):
        self.state = 'draft'

    def action_archive(self):
        self.state = 'archived'
        self.active = False

    # ---------------------------
    # Utility Methods
    # ---------------------------
    def get_structured_data(self):
        """
        Returns structured question data in a format suitable for LLM consumption.
        """
        self.ensure_one()
        data = {
            'id': self.id,
            'name': self.name,
            'question_text': self.question_text_plain or self.question_text,
            'question_type': self.question_type_id.code,
            'subject': self.subject_id.name,
            'difficulty': self.difficulty_level,
            'difficulty_score': self.difficulty_score,
            'bloom_taxonomy': self.bloom_taxonomy,
            'topic': self.topic,
            'tags': [t.name for t in self.tags],
            'answers': [
                {
                    'text': ans.html2plaintext(ans.answer_text) if ans.answer_text else ans.answer_text_plain,
                    'is_correct': ans.is_correct,
                    'fraction': ans.fraction,
                }
                for ans in self.answer_ids
            ],
            'numerical_answer': self.numerical_answer,
            'text_answer': self.text_answer,
            'moodle_id': self.moodle_id,
        }
        if self.llm_metadata:
            try:
                data.update(json.loads(self.llm_metadata))
            except (json.JSONDecodeError, TypeError):
                pass
        return data

    def action_increment_usage(self):
        self.usage_count += 1
        self.last_used_date = fields.Datetime.now()


class ShiningAceQuestionImage(models.Model):
    """
    Stores images embedded in questions.
    """
    _name = 'shiningace.question.image'
    _description = 'ShiningAce Question Image'
    _order = 'sequence, id'

    question_id = fields.Many2one('shiningace.question', string='Question', required=True, ondelete='cascade')
    name = fields.Char(string='Image Name', required=True)
    image_data = fields.Binary(string='Image Data', required=True, attachment=True)
    image_alt_text = fields.Char(string='Alt Text', help="Accessibility alt text")
    mime_type = fields.Char(string='MIME Type', default='image/png')
    sequence = fields.Integer(string='Sequence', default=10)
    is_inline = fields.Boolean(
        string='Inline Image',
        default=False,
        help="Whether this image is embedded inline in the question text"
    )
    url = fields.Char(string='Image URL', help="External URL if image is hosted externally")


class ShiningAceQuestionMatching(models.Model):
    """
    For matching-type questions: pairs of questions and answers to be matched.
    """
    _name = 'shiningace.question.matching'
    _description = 'ShiningAce Question Matching Pairs'
    _order = 'sequence, id'

    question_id = fields.Many2one('shiningace.question', string='Question', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    question_text = fields.Html(string='Question/Stimulus', required=True, help="The item to match from")
    answer_text = fields.Html(string='Answer/Match', required=True, help="The correct match")
    feedback = fields.Html(string='Feedback', help="Feedback for this specific pair")


class ShiningAceQuestionDragDrop(models.Model):
    """
    For drag-and-drop questions: items that can be dragged.
    """
    _name = 'shiningace.question.dragdrop'
    _description = 'ShiningAce Question Drag & Drop Items'
    _order = 'sequence, id'

    question_id = fields.Many2one('shiningace.question', string='Question', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    item_type = fields.Selection([
        ('text', 'Text'),
        ('image', 'Image'),
    ], string='Item Type', default='text')
    item_text = fields.Html(string='Item Text', help="Text for drag item")
    item_image = fields.Binary(string='Item Image', attachment=True)
    drop_zone = fields.Char(string='Drop Zone', help="Identifier for the correct drop zone")
    drop_zone_label = fields.Char(string='Drop Zone Label', help="Display label for the drop zone")
    infinite = fields.Boolean(string='Infinite', default=False, help="Can be used multiple times")
