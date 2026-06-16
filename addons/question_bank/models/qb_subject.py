from odoo import models, fields, api


class QbSubject(models.Model):
    _name = 'qb.subject'
    _description = 'Question Bank Subject'
    _order = 'name'

    name = fields.Char(string='Subject', required=True)
    description = fields.Text(string='Description')
    color = fields.Integer(string='Color Index', default=0)
    active = fields.Boolean(default=True)

    topic_ids = fields.One2many('qb.topic', 'subject_id', string='Topics')
    topic_count = fields.Integer(compute='_compute_counts', string='Topic Count')
    question_count = fields.Integer(compute='_compute_counts', string='Question Count')

    @api.depends('topic_ids')
    def _compute_counts(self):
        QbQuestion = self.env['qb.question']
        for rec in self:
            rec.topic_count = len(rec.topic_ids)
            rec.question_count = QbQuestion.search_count([('subject_id', '=', rec.id)])

    def action_view_questions(self):
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} — Questions',
            'res_model': 'qb.question',
            'view_mode': 'list,kanban,form',
            'domain': [('subject_id', '=', self.id)],
            'context': {'default_subject_id': self.id},
        }
