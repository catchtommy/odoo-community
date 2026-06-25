from odoo import models, fields, api, _


class ShiningAceQuestionTag(models.Model):
    """
    Tags for categorising and filtering questions.
    Supports hierarchical tagging and colour coding.
    """
    _name = 'shiningace.question.tag'
    _description = 'ShiningAce Question Tag'
    _order = 'name'

    name = fields.Char(string='Tag Name', required=True, translate=True)
    color = fields.Integer(string='Color Index', default=0)
    active = fields.Boolean(string='Active', default=True)

    question_ids = fields.Many2many(
        'shiningace.question',
        'shiningace_question_tag_rel',
        'tag_id',
        'question_id',
        string='Questions'
    )
    question_count = fields.Integer(
        string='Question Count',
        compute='_compute_question_count',
        store=True
    )

    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    _sql_constraints = [
        ('name_company_uniq', 'UNIQUE(name, company_id)', 'Tag name must be unique per company!'),
    ]

    @api.depends('question_ids')
    def _compute_question_count(self):
        for record in self:
            record.question_count = len(record.question_ids)

    def name_get(self):
        result = []
        for record in self:
            result.append((record.id, record.name))
        return result
