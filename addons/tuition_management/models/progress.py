# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError


class ProgressReport(models.Model):
    _name = 'progress.report'
    _description = 'Student Progress Report'
    _order = 'report_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Title', required=True)
    course_id = fields.Many2one('course.master', string='Course', required=True, ondelete='cascade')
    student_id = fields.Many2one('student.profile', string='Student', required=True, ondelete='cascade')
    class_schedule_occurrence_id = fields.Many2one('class.schedule.occurrence', string='Class Session')
    report_date = fields.Date(string='Date', required=True, default=fields.Date.today)
    tutor_id = fields.Many2one('tutor.profile', string='Tutor')
    overall_rating = fields.Selection([
        ('excellent', 'Excellent'), ('good', 'Good'), ('satisfactory', 'Satisfactory'),
        ('needs_improvement', 'Needs Improvement'), ('poor', 'Poor'),
    ], string='Overall Rating')
    strengths = fields.Text(string='Strengths')
    areas_for_improvement = fields.Text(string='Areas for Improvement')
    comments = fields.Text(string='Comments')
    homework_notes = fields.Text(string='Homework / Next Steps')
    score = fields.Float(string='Score')
    max_score = fields.Float(string='Max Score', default=100)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted (Under Review)'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Status', default='draft', tracking=True, copy=False)
    rejection_reason = fields.Text(string='Rejection Reason')

    @api.model_create_multi
    def create(self, vals_list):
        # When a portal user (tutor) creates a progress report, auto-submit it
        # so it goes straight to "Under Review" without needing a manual Submit step.
        if self.env.user.share:  # share=True means portal/public user
            for vals in vals_list:
                if vals.get('state', 'draft') == 'draft':
                    vals['state'] = 'submitted'
        return super().create(vals_list)

    def action_submit(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError('Only draft reports can be submitted.')
            rec.write({'state': 'submitted'})
            rec.message_post(body='Progress report submitted for admin approval.', subtype_xmlid='mail.mt_note')

    def action_approve(self):
        for rec in self:
            if rec.state != 'submitted':
                raise UserError('Only submitted reports can be approved.')
            rec.write({'state': 'approved', 'rejection_reason': False})
            rec.message_post(body='Progress report approved and is now visible in the parent portal.', subtype_xmlid='mail.mt_note')

    def action_reject(self):
        for rec in self:
            if rec.state != 'submitted':
                raise UserError('Only submitted reports can be rejected.')
            rec.write({'state': 'rejected'})
            rec.message_post(body='Progress report rejected and returned to the tutor.', subtype_xmlid='mail.mt_note')

    def action_reset_to_draft(self):
        for rec in self:
            rec.write({'state': 'draft'})
            rec.message_post(body='Progress report reset to draft.', subtype_xmlid='mail.mt_note')


class CourseAssignment(models.Model):
    _name = 'course.assignment'
    _description = 'Course Assignment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'due_date'

    name = fields.Char(string='Title', required=True)
    course_id = fields.Many2one('course.master', string='Course', required=True, ondelete='cascade')
    description = fields.Html(string='Description')
    assignment_type = fields.Selection([
        ('homework', 'Homework'), ('quiz', 'Quiz'), ('test', 'Test'),
        ('project', 'Project'), ('worksheet', 'Worksheet'), ('other', 'Other'),
    ], string='Type', default='homework')
    due_date = fields.Date(string='Due Date')
    assigned_date = fields.Date(string='Assigned Date', default=fields.Date.today)
    status = fields.Selection([
        ('draft', 'Draft'),
        ('assigned', 'Assigned'),
        ('pending_review', 'Pending Review'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True)
    attachment_ids = fields.Many2many('ir.attachment', string='Attachments')
    submission_ids = fields.One2many('assignment.submission', 'assignment_id', string='Submissions')

    def action_assign(self):
        for rec in self:
            if rec.status == 'draft':
                rec.write({'status': 'assigned'})
                rec.message_post(body='Assignment published to students.', subtype_xmlid='mail.mt_note')

    def action_complete(self):
        for rec in self:
            if rec.status == 'assigned':
                rec.write({'status': 'completed'})

    def action_cancel(self):
        for rec in self:
            rec.write({'status': 'cancelled'})


class AssignmentSubmission(models.Model):
    _name = 'assignment.submission'
    _description = 'Assignment Submission'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'submission_date desc'

    assignment_id = fields.Many2one('course.assignment', string='Assignment', required=True, ondelete='cascade')
    student_id = fields.Many2one('student.profile', string='Student', required=True, ondelete='cascade')
    submission_date = fields.Datetime(string='Submitted On', default=fields.Datetime.now)
    status = fields.Selection([
        ('pending', 'Pending'),
        ('submitted', 'Submitted'),
        ('pending_review', 'Pending Review'),
        ('completed', 'Completed'),
        ('rework', 'Rework Required'),
    ], string='Status', default='pending', tracking=True)
    # Tutor review fields
    review_status = fields.Selection([
        ('pass', 'Pass'),
        ('fail', 'Fail'),
        ('needs_revision', 'Needs Revision'),
    ], string='Review Status', tracking=True)
    score = fields.Float(string='Score', tracking=True)
    max_score = fields.Float(string='Max Score', default=100)
    feedback = fields.Text(string='Tutor Feedback', tracking=True)
    notes = fields.Text(string='Student Note')
    attachment_ids = fields.Many2many('ir.attachment', 'assignment_submission_attachment_rel',
                                      'submission_id', 'attachment_id', string='Student Attachments')
    reviewed_by = fields.Many2one('tutor.profile', string='Reviewed By', readonly=True)
    review_date = fields.Datetime(string='Review Date', readonly=True)

    def action_submit_review(self):
        """Tutor marks submission as completed with feedback."""
        self.ensure_one()
        tutor = self.env['tutor.profile'].sudo().search(
            [('partner_id', '=', self.env.user.partner_id.id)], limit=1
        )
        vals = {
            'status': 'completed',
            'review_date': fields.Datetime.now(),
        }
        if tutor:
            vals['reviewed_by'] = tutor.id
        self.write(vals)
        # Move assignment to completed when all submissions are done
        self.assignment_id.sudo().write({'status': 'completed'})
        self.message_post(
            body=(
                f'<b>Submission reviewed and completed.</b><br/>'
                f'Score: {self.score} / {self.max_score}<br/>'
                f'Feedback: {self.feedback or "—"}'
            ),
            subtype_xmlid='mail.mt_note',
        )

    def action_request_rework(self):
        """Tutor requests rework: submission marked rework, assignment back to assigned."""
        self.ensure_one()
        tutor = self.env['tutor.profile'].sudo().search(
            [('partner_id', '=', self.env.user.partner_id.id)], limit=1
        )
        vals = {
            'status': 'rework',
            'review_date': fields.Datetime.now(),
        }
        if tutor:
            vals['reviewed_by'] = tutor.id
        self.write(vals)
        self.assignment_id.sudo().write({'status': 'assigned'})
        self.message_post(
            body=(
                f'<b>Rework requested.</b><br/>'
                f'Feedback: {self.feedback or "—"}'
            ),
            subtype_xmlid='mail.mt_note',
        )

    def action_mark_under_review(self):
        """Move to Pending Review."""
        for rec in self:
            if rec.status in ('submitted', 'pending'):
                rec.write({'status': 'pending_review'})
                rec.assignment_id.sudo().write({'status': 'pending_review'})
                rec.message_post(body='Submission is now under review.', subtype_xmlid='mail.mt_note')

    def action_reopen(self):
        """Allow tutor to re-open a completed submission for editing."""
        for rec in self:
            if rec.status == 'completed':
                rec.write({'status': 'pending_review'})
                rec.message_post(body='Submission reopened for review.', subtype_xmlid='mail.mt_note')
