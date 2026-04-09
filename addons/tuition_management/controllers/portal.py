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
            values['student_redirect'] = '/my/courses'
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
            values['tutor_redirect'] = '/my/tutor/courses'
            if 'tutor_course_count' in counters:
                values['tutor_course_count'] = request.env['course.master'].sudo().search_count([
                    ('tutor_id', '=', tutor.id), ('status', '=', 'active'),
                ])
        if parent:
            values['is_parent'] = True
            if 'child_count' in counters:
                values['child_count'] = len(parent.student_ids)

        return values

    @http.route(['/my', '/my/home'], type='http', auth='user', website=True)
    def home(self, **kw):
        """Redirect tutor/student directly to their dashboard."""
        partner = request.env.user.partner_id
        tutor = request.env['tutor.profile'].sudo().search([('partner_id', '=', partner.id)], limit=1)
        if tutor:
            return request.redirect('/my/tutor/courses')
        student = request.env['student.profile'].sudo().search([('partner_id', '=', partner.id)], limit=1)
        if student:
            return request.redirect('/my/courses')
        parent = request.env['parent.profile'].sudo().search([('partner_id', '=', partner.id)], limit=1)
        if parent:
            return request.redirect('/my/parent/children')
        return super().home(**kw)

    @http.route(['/my/logout'], type='http', auth='user', website=True)
    def portal_logout(self, **kw):
        return request.redirect('/web/session/logout?redirect=/web/login')

    @http.route(['/my/logout'], type='http', auth='public', website=True)
    def portal_logout(self, **kw):
        request.session.logout(keep_db=True)
        return request.redirect('/web/login')

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
    # PROFILE MANAGEMENT
    # ──────────────────────────────────────────────

    @http.route(['/my/profile'], type='http', auth='user', website=True)
    def portal_my_profile(self, **kw):
        user = request.env.user
        partner = user.partner_id
        student = self._get_student()
        tutor = self._get_tutor()
        parent = self._get_parent()
        profile = student or tutor or parent
        role = 'Student' if student else ('Tutor' if tutor else ('Parent' if parent else 'User'))
        back_url = '/my/tutor/courses' if tutor else ('/my/courses' if student else ('/my/parent/children' if parent else '/my'))
        return request.render('tuition_management.portal_user_profile', {
            'user': user,
            'partner': partner,
            'profile': profile,
            'role': role,
            'is_student': bool(student),
            'is_tutor': bool(tutor),
            'is_parent': bool(parent),
            'success': kw.get('success'),
            'error': kw.get('error'),
            'page_name': 'profile',
            'back_url': back_url,
            'csrf_token': request.csrf_token(),
        })

    @http.route(['/my/profile/save'], type='http', auth='user', website=True,
                methods=['POST'], csrf=True)
    def portal_profile_save(self, **kw):
        user = request.env.user
        partner = user.partner_id
        student = self._get_student()
        tutor = self._get_tutor()
        parent = self._get_parent()
        profile = student or tutor or parent

        name = (kw.get('name') or '').strip()
        email = (kw.get('email') or '').strip()
        phone = (kw.get('phone') or '').strip()
        new_password = (kw.get('new_password') or '').strip()
        confirm_password = (kw.get('confirm_password') or '').strip()

        if not name:
            return request.redirect('/my/profile?error=Name is required.')

        # Update profile
        if profile:
            write_vals = {'name': name}
            if email:
                write_vals['email'] = email
            if hasattr(profile, 'phone') and phone:
                write_vals['phone'] = phone
            profile.sudo().write(write_vals)

        # Update partner
        partner_vals = {'name': name}
        if email:
            partner_vals['email'] = email
        if phone:
            partner_vals['phone'] = phone
        partner.sudo().write(partner_vals)

        # Update password if provided
        if new_password:
            if len(new_password) < 6:
                return request.redirect('/my/profile?error=Password must be at least 6 characters.')
            if new_password != confirm_password:
                return request.redirect('/my/profile?error=Passwords do not match.')
            try:
                user.sudo().write({'password': new_password})
            except Exception as e:
                return request.redirect(f'/my/profile?error=Failed to update password: {e}')

        return request.redirect('/my/profile?success=1')

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

        # Pre-format datetimes to avoid QWeb formatting errors
        occ_data = []
        for occ in occurrences:
            try:
                date_str = occ.start_datetime.strftime('%a, %d %b %Y') if occ.start_datetime else ''
                time_str = occ.start_datetime.strftime('%I:%M %p') if occ.start_datetime else ''
            except Exception:
                date_str = str(occ.start_datetime) if occ.start_datetime else ''
                time_str = ''
            occ_data.append({'occ': occ, 'date_str': date_str, 'time_str': time_str})

        return request.render('tuition_management.portal_student_lessons', {
            'course': course,
            'student': student,
            'occurrences': occurrences,
            'occ_data': occ_data,
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
            'csrf_token': request.csrf_token(),
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
        lesson_count = request.env['class.schedule.occurrence'].sudo().search_count([
            ('tutor_id', '=', tutor.id),
            ('start_datetime', '>=', datetime.combine(start_of_week, datetime.min.time())),
            ('start_datetime', '<=', datetime.combine(end_of_week, datetime.max.time())),
        ])
        # Precompute student count per course
        course_data = []
        for c in courses:
            course_data.append({
                'course': c,
                'student_count': c.student_count,
                'assignment_count': len(c.assignment_ids),
            })
        return request.render('tuition_management.portal_tutor_dashboard', {
            'tutor': tutor,
            'courses': courses,
            'course_data': course_data,
            'lesson_count': lesson_count,
            'page_name': 'tutor_courses',
        })

    @http.route(['/my/tutor/courses/<int:course_id>'], type='http', auth='user', website=True)
    def portal_tutor_course_detail(self, course_id, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        course = request.env['course.master'].sudo().browse(course_id)
        if not course.exists() or course.tutor_id.id != tutor.id:
            return request.redirect('/my/tutor/courses')

        today = fields.Date.today()
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        this_week_lessons = request.env['class.schedule.occurrence'].sudo().search([
            ('course_id', '=', course.id),
            ('start_datetime', '>=', datetime.combine(start_of_week, datetime.min.time())),
            ('start_datetime', '<=', datetime.combine(end_of_week, datetime.max.time())),
        ], order='start_datetime asc')

        enrolled_students = course.enrollment_ids.filtered(lambda e: e.status == 'active')
        course_assignments = course.assignment_ids

        return request.render('tuition_management.portal_tutor_course_detail', {
            'tutor': tutor,
            'course': course,
            'this_week_lessons': this_week_lessons,
            'enrolled_students': enrolled_students,
            'course_assignments': course_assignments,
            'lessons_url': f'/my/tutor/courses/{course.id}/lessons',
            'assignments_url': f'/my/tutor/courses/{course.id}/assignments',
            'page_name': 'tutor_course_detail',
        })

    @http.route(['/my/tutor/courses/<int:course_id>/lessons',
                 '/my/tutor/courses/<int:course_id>/lessons/'], type='http', auth='user', website=True)
    def portal_tutor_lessons(self, course_id, week='this', **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my/tutor/courses')
        course = request.env['course.master'].sudo().browse(course_id)
        if not course.exists():
            return request.redirect('/my/tutor/courses')
        if course.tutor_id and course.tutor_id.id != tutor.id:
            return request.redirect('/my/tutor/courses')

        today = fields.Date.today()
        start_of_week = today - timedelta(days=today.weekday())
        if week == 'next':
            start_date = start_of_week + timedelta(days=7)
            end_date = start_date + timedelta(days=6)
        elif week == 'all':
            start_date = today
            end_date = today + timedelta(days=90)
        elif week == 'past':
            start_date = today - timedelta(days=30)
            end_date = today - timedelta(days=1)
        else:
            week = 'this'
            start_date = start_of_week
            end_date = start_of_week + timedelta(days=6)

        occurrences = request.env['class.schedule.occurrence'].sudo().search([
            ('course_id', '=', course.id),
            ('start_datetime', '>=', datetime.combine(start_date, datetime.min.time())),
            ('start_datetime', '<=', datetime.combine(end_date, datetime.max.time())),
        ], order='start_datetime asc')

        # Pre-format datetimes to avoid QWeb formatting errors
        occ_data = []
        for occ in occurrences:
            try:
                date_str = occ.start_datetime.strftime('%a, %d %b %Y') if occ.start_datetime else ''
                time_str = occ.start_datetime.strftime('%I:%M %p') if occ.start_datetime else ''
            except Exception:
                date_str = str(occ.start_datetime) if occ.start_datetime else ''
                time_str = ''
            occ_data.append({
                'occ': occ,
                'date_str': date_str,
                'time_str': time_str,
            })

        return request.render('tuition_management.portal_tutor_lessons', {
            'tutor': tutor,
            'course': course,
            'occurrences': occurrences,
            'occ_data': occ_data,
            'current_week': week,
            'back_url': f'/my/tutor/courses/{course.id}',
            'page_name': 'tutor_lessons',
        })

    @http.route(['/my/tutor/lesson/<int:occurrence_id>/attendance'], type='http', auth='user', website=True)
    def portal_tutor_attendance_form(self, occurrence_id, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my/tutor/courses')
        occurrence = request.env['class.schedule.occurrence'].sudo().browse(occurrence_id)
        if not occurrence.exists():
            return request.redirect('/my/tutor/courses')
        if occurrence.tutor_id and occurrence.tutor_id.id != tutor.id:
            return request.redirect('/my/tutor/courses')

        enrolled = occurrence.course_id.enrollment_ids.filtered(lambda e: e.status == 'active')
        students = enrolled.mapped('student_id')
        existing_att = {att.student_id.id: att for att in occurrence.attendance_ids}

        student_data = []
        for s in students:
            att = existing_att.get(s.id)
            student_data.append({
                'student': s,
                'status': att.status if att else 'present',
                'billable': att.billable if att else True,
                'remarks': att.remarks if att else '',
            })

        return request.render('tuition_management.portal_tutor_attendance', {
            'tutor': tutor,
            'occurrence': occurrence,
            'course': occurrence.course_id,
            'student_data': student_data,
            'back_url': f'/my/tutor/courses/{occurrence.course_id.id}',
            'page_name': 'tutor_attendance',
            'csrf_token': request.csrf_token(),
        })

    @http.route(['/my/tutor/lesson/<int:occurrence_id>/attendance/save'], type='http',
                auth='user', website=True, methods=['POST'], csrf=True)
    def portal_tutor_attendance_save(self, occurrence_id, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my/tutor/courses')
        occurrence = request.env['class.schedule.occurrence'].sudo().browse(occurrence_id)
        if not occurrence.exists():
            return request.redirect('/my/tutor/courses')
        if occurrence.tutor_id and occurrence.tutor_id.id != tutor.id:
            return request.redirect('/my/tutor/courses')

        lesson_status = kw.get('lesson_status', 'completed')
        # Only allow tutor to set completed; cancel is admin-only
        if lesson_status not in ('completed', 'scheduled', 'no_show'):
            lesson_status = 'completed'

        enrolled = occurrence.course_id.enrollment_ids.filtered(lambda e: e.status == 'active')
        students = enrolled.mapped('student_id')

        for s in students:
            status = kw.get(f'status_{s.id}', 'present')
            billable = kw.get(f'billable_{s.id}', '') == 'on'
            remarks = kw.get(f'remarks_{s.id}', '')

            existing = request.env['attendance.record'].sudo().search([
                ('class_schedule_occurrence_id', '=', occurrence.id),
                ('student_id', '=', s.id),
            ], limit=1)
            vals = {
                'class_schedule_occurrence_id': occurrence.id,
                'student_id': s.id,
                'attendance_date': occurrence.start_datetime.date(),
                'status': status,
                'billable': billable,
                'remarks': remarks,
            }
            if existing:
                existing.sudo().write(vals)
            else:
                request.env['attendance.record'].sudo().create(vals)

        occurrence.sudo().write({'lesson_status': lesson_status})
        course_id = occurrence.course_id.id
        return request.redirect(f'/my/tutor/courses/{course_id}')

    @http.route(['/my/tutor/courses/<int:course_id>/assignments'], type='http', auth='user', website=True)
    def portal_tutor_assignments(self, course_id, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        course = request.env['course.master'].sudo().browse(course_id)
        if not course.exists() or course.tutor_id.id != tutor.id:
            return request.redirect('/my/tutor/courses')

        assignments = course.assignment_ids
        return request.render('tuition_management.portal_tutor_assignments', {
            'tutor': tutor,
            'course': course,
            'assignments': assignments,
            'page_name': 'tutor_assignments',
            'csrf_token': request.csrf_token(),
        })

    @http.route(['/my/tutor/courses/<int:course_id>/assignments/create'], type='http',
                auth='user', website=True, methods=['POST'], csrf=True)
    def portal_tutor_assignment_create(self, course_id, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        course = request.env['course.master'].sudo().browse(course_id)
        if not course.exists() or course.tutor_id.id != tutor.id:
            return request.redirect('/my/tutor/courses')

        vals = {
            'name': kw.get('name', ''),
            'course_id': course.id,
            'assignment_type': kw.get('assignment_type', 'homework'),
            'due_date': kw.get('due_date') or False,
            'description': kw.get('description', ''),
            'status': 'assigned',
            'assigned_date': fields.Date.today(),
        }

        assignment = request.env['course.assignment'].sudo().create(vals)

        uploaded_file = kw.get('attachment')
        if uploaded_file and uploaded_file.filename:
            attachment = request.env['ir.attachment'].sudo().create({
                'name': uploaded_file.filename,
                'datas': base64.b64encode(uploaded_file.read()),
                'res_model': 'course.assignment',
                'res_id': assignment.id,
                'type': 'binary',
            })
            assignment.sudo().write({'attachment_ids': [(4, attachment.id)]})

        return request.redirect(f'/my/tutor/courses/{course_id}/assignments?created=1')

    @http.route(['/my/tutor/assignment/<int:assignment_id>'], type='http', auth='user', website=True)
    def portal_tutor_assignment_detail(self, assignment_id, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        assignment = request.env['course.assignment'].sudo().browse(assignment_id)
        if not assignment.exists() or assignment.course_id.tutor_id.id != tutor.id:
            return request.redirect('/my/tutor/courses')

        submissions = assignment.submission_ids
        return request.render('tuition_management.portal_tutor_assignment_detail', {
            'tutor': tutor,
            'assignment': assignment,
            'course': assignment.course_id,
            'submissions': submissions,
            'page_name': 'tutor_assignment_detail',
            'csrf_token': request.csrf_token(),
        })

    @http.route(['/my/tutor/submission/<int:submission_id>/grade'], type='http',
                auth='user', website=True, methods=['POST'], csrf=True)
    def portal_tutor_grade_submission(self, submission_id, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        submission = request.env['assignment.submission'].sudo().browse(submission_id)
        if not submission.exists() or submission.assignment_id.course_id.tutor_id.id != tutor.id:
            return request.redirect('/my/tutor/courses')

        score = kw.get('score', 0)
        feedback = kw.get('feedback', '')
        try:
            score = float(score)
        except (ValueError, TypeError):
            score = 0

        submission.sudo().write({
            'score': score,
            'feedback': feedback,
            'status': 'graded',
        })

        return request.redirect(f'/my/tutor/assignment/{submission.assignment_id.id}?graded=1')

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