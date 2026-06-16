# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class QbQuestionBulkAction(models.TransientModel):
    _name = 'qb.question.bulk.action'
    _description = 'Question Bulk Action Wizard'

    action_type = fields.Selection([
        ('change_state', 'Change State'),
        ('change_subject', 'Change Subject/Topic'),
        ('add_tags', 'Add Tags'),
        ('remove_tags', 'Remove Tags'),
        ('change_difficulty', 'Change Difficulty'),
        ('duplicate', 'Duplicate Questions'),
        ('delete', 'Delete Questions'),
    ], string='Action', required=True, default='change_state')
    
    # State change
    new_state = fields.Selection([
        ('draft', 'Draft'),
        ('approved', 'Approved'),
    ], string='New State')
    
    # Subject/Topic change
    new_subject_id = fields.Many2one('qb.subject', string='New Subject')
    new_topic_id = fields.Many2one('qb.topic', string='New Topic')
    
    # Tags
    tag_ids = fields.Many2many('qb.question.tag', string='Tags')
    
    # Difficulty
    new_difficulty = fields.Selection([
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    ], string='New Difficulty')
    
    # Stats
    question_count = fields.Integer(compute='_compute_question_count', string='Questions Selected')
    
    def _compute_question_count(self):
        for rec in self:
            rec.question_count = len(self.env.context.get('active_ids', []))
    
    def action_apply(self):
        """Apply the bulk action"""
        self.ensure_one()
        
        active_ids = self.env.context.get('active_ids', [])
        if not active_ids:
            raise UserError(_('No questions selected.'))
        
        questions = self.env['qb.question'].browse(active_ids)
        
        if self.action_type == 'change_state':
            if not self.new_state:
                raise UserError(_('Please select a new state.'))
            questions.write({'state': self.new_state})
            message = _('%d question(s) moved to %s.') % (len(questions), dict(self._fields['new_state'].selection).get(self.new_state))
            
        elif self.action_type == 'change_subject':
            vals = {}
            if self.new_subject_id:
                vals['subject_id'] = self.new_subject_id.id
            if self.new_topic_id:
                vals['topic_id'] = self.new_topic_id.id
            if vals:
                questions.write(vals)
                message = _('%d question(s) updated.') % len(questions)
            else:
                raise UserError(_('Please select a subject or topic.'))
                
        elif self.action_type == 'add_tags':
            if not self.tag_ids:
                raise UserError(_('Please select tags to add.'))
            for question in questions:
                question.tag_ids = [(4, tag.id) for tag in self.tag_ids]
            message = _('%d question(s) tagged.') % len(questions)
            
        elif self.action_type == 'remove_tags':
            if not self.tag_ids:
                raise UserError(_('Please select tags to remove.'))
            for question in questions:
                question.tag_ids = [(3, tag.id) for tag in self.tag_ids]
            message = _('%d question(s) untagged.') % len(questions)
            
        elif self.action_type == 'change_difficulty':
            if not self.new_difficulty:
                raise UserError(_('Please select a difficulty level.'))
            questions.write({'difficulty': self.new_difficulty})
            message = _('%d question(s) difficulty changed.') % len(questions)
            
        elif self.action_type == 'duplicate':
            count = 0
            for question in questions:
                question.action_duplicate_question()
                count += 1
            message = _('%d question(s) duplicated.') % count
            
        elif self.action_type == 'delete':
            count = len(questions)
            questions.unlink()
            message = _('%d question(s) deleted.') % count
        
        else:
            raise UserError(_('Invalid action type.'))
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Bulk Action Complete'),
                'message': message,
                'type': 'success',
                'sticky': False,
            }
        }
