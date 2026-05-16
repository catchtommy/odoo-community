import json
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class QbQuestion(models.Model):
    _name = 'qb.question'
    _description = 'Question Bank Question'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    _rec_name = 'name'

    # ── Core ─────────────────────────────────────────────────────────────
    name = fields.Char(string='Question Title', required=True, tracking=True)
    question_type = fields.Selection([
        ('mcq',        'Multiple Choice (MCQ)'),
        ('true_false', 'True / False'),
        ('fill_blank', 'Fill in the Blank'),
    ], string='Type', required=True, default='mcq', tracking=True)
    state = fields.Selection([
        ('draft',    'Draft'),
        ('approved', 'Approved'),
    ], default='draft', tracking=True, string='Status')
    active = fields.Boolean(default=True)

    # ── Classification ────────────────────────────────────────────────────
    subject_id = fields.Many2one('qb.subject', string='Subject', tracking=True,
                                  index=True)
    topic_id = fields.Many2one('qb.topic', string='Topic',
                                domain="[('subject_id','=',subject_id)]",
                                index=True)
    difficulty = fields.Selection([
        ('easy',   'Easy'),
        ('medium', 'Medium'),
        ('hard',   'Hard'),
    ], string='Difficulty', default='medium', tracking=True)
    marks = fields.Float(string='Marks', default=1.0)
    tag_ids = fields.Many2many('qb.tag', 'qb_question_tag_rel',
                                'question_id', 'tag_id', string='Tags')

    # ── Rich content ──────────────────────────────────────────────────────
    question_html = fields.Html(string='Question Content', sanitize=False)
    explanation   = fields.Html(string='Explanation / Solution', sanitize=False)

    # LaTeX equation (stored separately so it can be rendered with MathJax)
    latex_equation = fields.Text(
        string='LaTeX Equation',
        help='Enter a LaTeX equation e.g.  x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}',
    )

    # Graph config as JSON
    graph_json = fields.Text(
        string='Graph Config (JSON)',
        help='JSON graph configuration e.g. {"type":"line","equation":"y=x^2"}',
    )

    # Images via ir.attachment
    image_ids = fields.Many2many(
        'ir.attachment',
        'qb_question_attachment_rel',
        'question_id', 'attachment_id',
        string='Images',
        domain=[('mimetype', 'like', 'image/')],
    )

    # ── MCQ options ───────────────────────────────────────────────────────
    option_ids = fields.One2many('qb.question.option', 'question_id', string='Options')

    # ── True / False ──────────────────────────────────────────────────────
    true_false_answer = fields.Selection([
        ('true',  'True'),
        ('false', 'False'),
    ], string='Correct Answer (T/F)')

    # ── Fill in the Blank ─────────────────────────────────────────────────
    blank_answer = fields.Char(string='Correct Answer')

    # ── Computed stats ────────────────────────────────────────────────────
    option_count = fields.Integer(compute='_compute_option_stats', store=True)
    correct_option_count = fields.Integer(compute='_compute_option_stats', store=True)
    difficulty_color = fields.Char(compute='_compute_difficulty_color')

    # ─────────────────────────────────────────────────────────────────────
    @api.depends('option_ids', 'option_ids.is_correct')
    def _compute_option_stats(self):
        for rec in self:
            rec.option_count = len(rec.option_ids)
            rec.correct_option_count = sum(1 for o in rec.option_ids if o.is_correct)

    def _compute_difficulty_color(self):
        color_map = {'easy': '#28a745', 'medium': '#fd7e14', 'hard': '#dc3545'}
        for rec in self:
            rec.difficulty_color = color_map.get(rec.difficulty, '#6c757d')

    # ── Constraints ───────────────────────────────────────────────────────
    @api.constrains('option_ids', 'question_type')
    def _check_mcq(self):
        for rec in self:
            if rec.question_type == 'mcq':
                if len(rec.option_ids) < 2:
                    raise ValidationError(
                        'MCQ questions must have at least 2 options.')
                if not any(o.is_correct for o in rec.option_ids):
                    raise ValidationError(
                        'MCQ questions must have at least one correct answer marked.')

    @api.constrains('question_type', 'true_false_answer')
    def _check_true_false(self):
        for rec in self:
            if rec.question_type == 'true_false' and not rec.true_false_answer:
                raise ValidationError(
                    'Please select the correct answer for the True/False question.')

    @api.constrains('question_type', 'blank_answer')
    def _check_fill_blank(self):
        for rec in self:
            if rec.question_type == 'fill_blank' and not (rec.blank_answer or '').strip():
                raise ValidationError(
                    'Please provide the correct answer for the Fill-in-the-Blank question.')

    # ── Graph JSON validation ─────────────────────────────────────────────
    @api.constrains('graph_json')
    def _check_graph_json(self):
        for rec in self:
            if rec.graph_json:
                try:
                    json.loads(rec.graph_json)
                except (ValueError, TypeError):
                    raise ValidationError('Graph Config must be valid JSON.')

    # ── Onchange ──────────────────────────────────────────────────────────
    @api.onchange('subject_id')
    def _onchange_subject(self):
        self.topic_id = False
        return {'domain': {'topic_id': [('subject_id', '=', self.subject_id.id)]}}

    @api.onchange('question_type')
    def _onchange_question_type(self):
        """Clear type-specific fields when switching type."""
        if self.question_type != 'mcq':
            self.option_ids = [(5, 0, 0)]
        if self.question_type != 'true_false':
            self.true_false_answer = False
        if self.question_type != 'fill_blank':
            self.blank_answer = False

    # ── Actions ───────────────────────────────────────────────────────────
    def action_approve(self):
        self.write({'state': 'approved'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    def action_duplicate(self):
        new = self.copy({
            'name': f'{self.name} (Copy)',
            'state': 'draft',
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'qb.question',
            'res_id': new.id,
            'view_mode': 'form',
            'target': 'current',
        }


class QbQuestionOption(models.Model):
    _name = 'qb.question.option'
    _description = 'MCQ Option'
    _order = 'sequence, id'

    question_id = fields.Many2one(
        'qb.question', string='Question',
        required=True, ondelete='cascade', index=True,
    )
    sequence    = fields.Integer(string='Order', default=10)
    option_text = fields.Html(
        string='Option Text', sanitize=False,
        help='Supports HTML, LaTeX (wrap in \\( ... \\)), and images.',
    )
    is_correct  = fields.Boolean(string='Correct Answer')
    explanation = fields.Text(string='Option Explanation')
