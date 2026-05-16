from odoo import models, fields, api


class QbTopic(models.Model):
    _name = 'qb.topic'
    _description = 'Question Bank Topic'
    _order = 'subject_id, name'

    name = fields.Char(string='Topic', required=True)
    subject_id = fields.Many2one('qb.subject', string='Subject', required=True, ondelete='cascade')
    description = fields.Text(string='Description')
    active = fields.Boolean(default=True)

    question_count = fields.Integer(compute='_compute_question_count', string='Questions')

    def _compute_question_count(self):
        QbQuestion = self.env['qb.question']
        for rec in self:
            rec.question_count = QbQuestion.search_count([('topic_id', '=', rec.id)])
