# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ProgressReport(models.Model):
    _name = 'progress.report'
    _description = 'Student Progress Report'
    _order = 'report_date desc'

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


class CourseAssignment(models.Model):
    _name = 'course.assignment'
    _description = 'Course Assignment'
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
        ('draft', 'Draft'), ('assigned', 'Assigned'), ('completed', 'Completed'), ('cancelled', 'Cancelled'),
    ], string='Status', default='draft')
    attachment_ids = fields.Many2many('ir.attachment', string='Attachments')
    submission_ids = fields.One2many('assignment.submission', 'assignment_id', string='Submissions')


class AssignmentSubmission(models.Model):
    _name = 'assignment.submission'
    _description = 'Assignment Submission'

    assignment_id = fields.Many2one('course.assignment', string='Assignment', required=True, ondelete='cascade')
    student_id = fields.Many2one('student.profile', string='Student', required=True, ondelete='cascade')
    submission_date = fields.Datetime(string='Submitted On', default=fields.Datetime.now)
    status = fields.Selection([
        ('pending', 'Pending'), ('submitted', 'Submitted'), ('graded', 'Graded'), ('late', 'Late'),
    ], string='Status', default='pending')
    score = fields.Float(string='Score')
    max_score = fields.Float(string='Max Score', default=100)
    feedback = fields.Text(string='Feedback')
    attachment_ids = fields.Many2many('ir.attachment', string='Attachments')
