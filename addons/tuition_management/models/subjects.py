# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.fields import Domain


class SubjectCategory(models.Model):
    _name = 'subject.category'
    _description = 'Subject Category'

    name = fields.Char(string='Category Name', required=True)
    description = fields.Text(string='Description')
    active = fields.Boolean(
        string='Active', default=True,
        help='Inactive categories stay on records already using them but are '
             'hidden when selecting a category for new records.')
    grade_ids = fields.Many2many(
        'grade.master',
        'subject_category_grade_rel',
        'category_id',
        'grade_id',
        string='Grades',
    )
    subject_ids = fields.One2many(
        'subject.master', 'category_id', string='Subjects',
        context={'active_test': False})


class SubjectMaster(models.Model):
    _name = 'subject.master'
    _description = 'Subject Master'
    
    name = fields.Char(string='Subject Name', required=True)
    category_id = fields.Many2one('subject.category', string='Category', required=True)
    description = fields.Text(string='Description')
    active = fields.Boolean(
        string='Active', default=True,
        help='Inactive subjects stay on records already using them but are '
             'hidden when selecting a subject for new records.')

    _order = 'category_id, name'

    @api.depends('name', 'category_id', 'category_id.name')
    def _compute_display_name(self):
        for rec in self:
            if rec.category_id:
                rec.display_name = '%s - %s' % (rec.category_id.name, rec.name)
            else:
                rec.display_name = rec.name

    @api.model
    def _name_search(self, name='', domain=None, operator='ilike', limit=None, order=None):
        """Allow searching by category name or subject name."""
        domain = domain or []
        if name:
            domain = ['|', '|',
                       ('name', operator, name),
                       ('category_id.name', operator, name),
                       ('display_name', operator, name)] + domain
        return self._search(domain, limit=limit, order=order)

    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        if self.env.context.get('active_test', True):
            # Subjects under an inactive category are hidden from pickers too.
            domain = Domain(domain or Domain.TRUE) & Domain(
                ['|', ('category_id', '=', False), ('category_id.active', '=', True)])
        return super().name_search(name, domain, operator, limit)
