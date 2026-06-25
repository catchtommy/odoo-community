from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ShiningAceSubject(models.Model):
    """
    Subject/Category for organising question banks.
    E.g., Mathematics, English, Physics, Chemistry, etc.
    """
    _name = 'shiningace.subject'
    _description = 'ShiningAce Subject'
    _order = 'name'
    _parent_store = True
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Subject Name', required=True, translate=True)
    code = fields.Char(string='Subject Code', size=20, help="Short code/abbreviation e.g. MATH101")
    description = fields.Text(string='Description', translate=True)
    color = fields.Integer(string='Color Index', default=0)

    # Hierarchical structure for sub-subjects
    parent_id = fields.Many2one('shiningace.subject', string='Parent Subject', ondelete='cascade')
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many('shiningace.subject', 'parent_id', string='Sub-Subjects')

    # Relations
    question_ids = fields.One2many('shiningace.question', 'subject_id', string='Questions')
    question_count = fields.Integer(
        string='Question Count',
        compute='_compute_question_count',
        store=True
    )
    exam_ids = fields.One2many('shiningace.exam', 'subject_id', string='Exams')
    exam_count = fields.Integer(
        string='Exam Count',
        compute='_compute_exam_count',
        store=True
    )
    homework_ids = fields.One2many('shiningace.homework', 'subject_id', string='Homework')
    homework_count = fields.Integer(
        string='Homework Count',
        compute='_compute_homework_count',
        store=True
    )

    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    active = fields.Boolean(string='Active', default=True)

    # SQL Constraints
    _sql_constraints = [
        ('name_company_uniq',
         'UNIQUE(name, company_id)',
         'Subject name must be unique per company!'),
        ('code_company_uniq',
         'UNIQUE(code, company_id)',
         'Subject code must be unique per company!'),
    ]

    @api.depends('question_ids')
    def _compute_question_count(self):
        for record in self:
            record.question_count = self.env['shiningace.question'].search_count(
                [('subject_id', '=', record.id)]
            )

    @api.depends('exam_ids')
    def _compute_exam_count(self):
        for record in self:
            record.exam_count = self.env['shiningace.exam'].search_count(
                [('subject_id', '=', record.id)]
            )

    @api.depends('homework_ids')
    def _compute_homework_count(self):
        for record in self:
            record.homework_count = self.env['shiningace.homework'].search_count(
                [('subject_id', '=', record.id)]
            )

    def name_get(self):
        result = []
        for record in self:
            name = record.name
            if record.code:
                name = f'[{record.code}] {name}'
            if record.parent_id:
                name = f'{record.parent_id.name} / {name}'
            result.append((record.id, name))
        return result

    @api.constrains('parent_id')
    def _check_hierarchy(self):
        if not self._check_recursion():
            raise ValidationError(_('Error! You cannot create recursive subject hierarchies.'))
