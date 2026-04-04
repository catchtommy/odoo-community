# -*- coding: utf-8 -*-
from odoo import http, fields
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal
from datetime import timedelta, datetime
import base64


class TuitionPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        partner = request.env.user.partner_id

        # Detect user type
        student = request.env['student.profile'].sudo().search([('partner_id', '=', partner.id)], limit=1)
        tutor = request.env['tutor.profile'].sudo().search([('partner_id', '=', partner.id)], limit=1)
        parent = request.env['parent.profile'].sudo().search([('partner_id', '=', partner.id)], limit=1)

        if student:
            values['is_student'] = True
            if 'course_count' in counters:
                values['course_count'] = request.env['course.enrollment'].sudo().search_count([
                    ('student_id', '=', student.id), ('status', '=', 'active'),
                ])
            if 'assignment_count' in counters:
                course_ids = request.env['course.enrollment'].sudo().search([
                    ('student_id', '=', student.id), ('status', '=', 'active'),
                ]).mapped('course_id').ids
                values['assignment_count'] = request.env['course.assignment'].sudo().search_count([
                    ('course_id', 'in', course_ids), ('status', 'in', ['assigned']),
                ])
        if tutor:
            values['is_tutor'] = True
            if 'tutor_course_count' in counters:
                values['tutor_course_count'] = request.env['course.master'].sudo().search_count([
                    ('tutor_id', '=', tutor.id), ('status', '=', 'active'),
                ])
        if parent:
            values['is_parent'] = True
            if 'child_count' in counters:
                values['child_count'] = len(parent.student_ids)

        return values

    def _get_student(self):
        return request.env['student.profile'].sudo().search(
            [('partner_id', '=', request.env.user.partner_id.id)], limit=1)

    def _get_tutor(self):
        return request.env['tutor.profile'].sudo().search(
            [('partner_id', '=', request.env.user.partner_id.id)], limit=1)

    def _get_parent(self):
        return request.env['parent.profile'].sudo().search(
            [('partner_id', '=', request.env.user.partner_id.id)], limit=1)

    # ──────────────────────────────────────────────
    # STUDENT PORTAL
    # ──────────────────────────────────────────────

    @http.route(['/my/courses'], type='http', auth='user', website=True)
    def portal_my_courses(self, **kw):
        student = self._get_student()
        if not student:
            return request.redirect('/my')
        enrollments = request.env['course.enrollment'].sudo().search([
            ('student_id', '=', student.id), ('status', '=', 'active'),
        ])
        return request.render('tuition_management.portal_student_courses', {
            'student': student,
            'enrollments': enrollments,
            'page_name': 'courses',
        })

    @http.route(['/my/courses/<int:course_id>'], type='http', auth='user', website=True)
    def portal_course_detail(self, course_id, **kw):
        student = self._get_student()
        if not student:
            return request.redirect('/my')
        course = request.env['course.master'].sudo().browse(course_id)
        if not course.exists():
            return request.redirect('/my/courses')
        enrollment = request.env['course.enrollment'].sudo().search([
            ('student_id', '=', student.id), ('course_id', '=', course.id),
            ('status', '=', 'active'),
        ], limit=1)
        if not enrollment:
            return request.redirect('/my/courses')

        today = fields.Date.today()
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        this_week_lessons = request.env['class.schedule.occurrence'].sudo().search([
            ('course_id', '=', course.id),
            ('start_datetime', '>=', datetime.combine(start_of_week, datetime.min.time())),
            ('start_datetime', '<=', datetime.combine(end_of_week, datetime.max.time())),
        ], order='start_datetime asc', limit=10)

        # Next upcoming lesson
        next_lesson = request.env['class.schedule.occurrence'].sudo().search([
            ('course_id', '=', course.id),
            ('start_datetime', '>=', fields.Datetime.now()),
            ('lesson_status', '=', 'scheduled'),
        ], order='start_datetime asc', limit=1)

        student_reports = course.progress_report_ids.filtered(lambda r: r.student_id.id == student.id)
        course_assignments = course.assignment_ids.filtered(lambda a: a.status in ['assigned', 'completed'])

        return request.render('tuition_management.portal_student_course_dashboard', {
            'course': course,
            'enrollment': enrollment,
            'student': student,
            'this_week_lessons': this_week_lessons,
            'next_lesson': next_lesson,
            'student_reports': student_reports[:5],
            'course_assignments': course_assignments,
            'page_name': 'course_detail',
        })

    @http.route(['/my/courses/<int:course_id>/lessons'], type='http', auth='user', website=True)
    def portal_course_lessons(self, course_id, week='this', **kw):
        student = self._get_student()
        if not student:
            return request.redirect('/my')
        course = request.env['course.master'].sudo().browse(course_id)
        if not course.exists():
            return request.redirect('/my/courses')
        enrollment = request.env['course.enrollment'].sudo().search([
            ('student_id', '=', student.id), ('course_id', '=', course.id),
            ('status', '=', 'active'),
        ], limit=1)
        if not enrollment:
            return request.redirect('/my/courses')

        today = fields.Date.today()
        start_of_week = today - timedelta(days=today.weekday())
        if week == 'next':
            start_date = start_of_week + timedelta(days=7)
            end_date = start_date + timedelta(days=6)
        elif week == 'all':
            start_date = today
            end_date = today + timedelta(days=90)
        else:
            week = 'this'
            start_date = start_of_week
            end_date = start_of_week + timedelta(days=6)

        occurrences = request.env['class.schedule.occurrence'].sudo().search([
            ('course_id', '=', course.id),
            ('start_datetime', '>=', datetime.combine(start_date, datetime.min.time())),
            ('start_datetime', '<=', datetime.combine(end_date, datetime.max.time())),
        ], order='start_datetime asc')

        return request.render('tuition_management.portal_student_lessons', {
            'course': course,
            'student': student,
            'occurrences': occurrences,
            'current_week': week,
            'page_name': 'course_lessons',
        })

    @http.route(['/my/assignments'], type='http', auth='user', website=True)
    def portal_my_assignments(self, **kw):
        student = self._get_student()
        if not student:
            return request.redirect('/my')
        course_ids = request.env['course.enrollment'].sudo().search([
            ('student_id', '=', student.id), ('status', '=', 'active'),
        ]).mapped('course_id').ids
        assignments = request.env['course.assignment'].sudo().search([
            ('course_id', 'in', course_ids), ('status', 'in', ['assigned', 'completed']),
        ], order='due_date asc')
        return request.render('tuition_management.portal_student_assignments', {
            'assignments': assignments,
            'student': student,
            'page_name': 'assignments',
        })

    @http.route(['/my/assignments/<int:assignment_id>'], type='http', auth='user', website=True)
    def portal_assignment_detail(self, assignment_id, **kw):
        student = self._get_student()
        if not student:
            return request.redirect('/my/assignments')
        assignment = request.env['course.assignment'].sudo().browse(assignment_id)
        if not assignment.exists():
            return request.redirect('/my/assignments')
        enrollment = request.env['course.enrollment'].sudo().search([
            ('student_id', '=', student.id), ('course_id', '=', assignment.course_id.id),
            ('status', '=', 'active'),
        ], limit=1)
        if not enrollment:
            return request.redirect('/my/assignments')
        submission = request.env['assignment.submission'].sudo().search([
            ('assignment_id', '=', assignment.id), ('student_id', '=', student.id),
        ], limit=1)
        return request.render('tuition_management.portal_student_assignment_detail', {
            'assignment': assignment,
            'submission': submission,
            'student': student,
            'page_name': 'assignment_detail',
        })

    @http.route(['/my/assignments/<int:assignment_id>/submit'], type='http', auth='user',
                website=True, methods=['POST'], csrf=True)
    def portal_assignment_submit(self, assignment_id, **kw):
        student = self._get_student()
        if not student:
            return request.redirect('/my/assignments')
        assignment = request.env['course.assignment'].sudo().browse(assignment_id)
        if not assignment.exists():
            return request.redirect('/my/assignments')
        enrollment = request.env['course.enrollment'].sudo().search([
            ('student_id', '=', student.id), ('course_id', '=', assignment.course_id.id),
            ('status', '=', 'active'),
        ], limit=1)
        if not enrollment:
            return request.redirect('/my/assignments')

        submission = request.env['assignment.submission'].sudo().search([
            ('assignment_id', '=', assignment.id), ('student_id', '=', student.id),
        ], limit=1)
        vals = {
            'assignment_id': assignment.id,
            'student_id': student.id,
            'status': 'submitted',
            'submission_date': fields.Datetime.now(),
        }
        uploaded_file = kw.get('submission_file')
        attachment_ids = []
        if uploaded_file and uploaded_file.filename:
            attachment = request.env['ir.attachment'].sudo().create({
                'name': uploaded_file.filename,
                'datas': base64.b64encode(uploaded_file.read()),
                'res_model': 'assignment.submission',
                'type': 'binary',
            })
            attachment_ids.append(attachment.id)
        if submission:
            submission.sudo().write(vals)
            if attachment_ids:
                submission.sudo().write({'attachment_ids': [(4, aid) for aid in attachment_ids]})
        else:
            if attachment_ids:
                vals['attachment_ids'] = [(6, 0, attachment_ids)]
            request.env['assignment.submission'].sudo().create(vals)
        return request.redirect(f'/my/assignments/{assignment_id}?submitted=1')

    # ──────────────────────────────────────────────
    # TUTOR PORTAL
    # ──────────────────────────────────────────────

    @http.route(['/my/tutor/courses'], type='http', auth='user', website=True)
    def portal_tutor_courses(self, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        courses = request.env['course.master'].sudo().search([
            ('tutor_id', '=', tutor.id), ('status', '=', 'active'),
        ])
        today = fields.Date.today()
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        this_week_lessons = request.env['class.schedule.occurrence'].sudo().search([
            ('tutor_id', '=', tutor.id),
            ('start_datetime', '>=', datetime.combine(start_of_week, datetime.min.time())),
            ('start_datetime', '<=', datetime.combine(end_of_week, datetime.max.time())),
        ], order='start_datetime asc')
        return request.render('tuition_management.portal_tutor_dashboard', {
            'tutor': tutor,
            'courses': courses,
            'this_week_lessons': this_week_lessons,
            'page_name': 'tutor_courses',
        })

    # ──────────────────────────────────────────────
    # PARENT PORTAL
    # ──────────────────────────────────────────────

    @http.route(['/my/parent/children'], type='http', auth='user', website=True)
    def portal_parent_children(self, **kw):
        parent = self._get_parent()
        if not parent:
            return request.redirect('/my')
        children = parent.student_ids
        child_data = []
        for child in children:
            enrollments = request.env['course.enrollment'].sudo().search([
                ('student_id', '=', child.id), ('status', '=', 'active'),
            ])
            child_data.append({'student': child, 'enrollments': enrollments})
        return request.render('tuition_management.portal_parent_dashboard', {
            'parent': parent,
            'child_data': child_data,
            'page_name': 'parent_children',
        })