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

    @http.route(['/my', '/my/home', '/my/dashboard'], type='http', auth='user', website=True)
    def home(self, **kw):
        partner = request.env.user.partner_id
        student = request.env['student.profile'].sudo().search([('partner_id', '=', partner.id)], limit=1)
        tutor = request.env['tutor.profile'].sudo().search([('partner_id', '=', partner.id)], limit=1)
        parent = request.env['parent.profile'].sudo().search([('partner_id', '=', partner.id)], limit=1)

        values = {
            'user': request.env.user,
            'is_student': bool(student),
            'is_tutor': bool(tutor),
            'is_parent': bool(parent),
        }

        today = fields.Date.today()

        if student:
            enrollments = request.env['course.enrollment'].sudo().search([
                ('student_id', '=', student.id), ('status', '=', 'active')])
            course_ids = enrollments.mapped('course_id').ids
            assignments = request.env['course.assignment'].sudo().search([
                ('course_id', 'in', course_ids), ('status', 'in', ['assigned'])])
            invoices = request.env['account.move'].sudo().search([
                ('partner_id', '=', partner.id),
                ('move_type', '=', 'out_invoice'),
                ('payment_state', '!=', 'paid'),
                ('state', '=', 'posted'),
            ])
            total_sessions = request.env['attendance.record'].sudo().search_count([
                ('student_id', '=', student.id)])
            present_sessions = request.env['attendance.record'].sudo().search_count([
                ('student_id', '=', student.id), ('status', '=', 'present')])
            attendance_rate = ('%d%%' % round(present_sessions * 100 / total_sessions)) if total_sessions else '—'
            values.update({
                'course_count': len(enrollments),
                'pending_assignments': len(assignments),
                'unpaid_invoices': len(invoices),
                'amount_due': sum(invoices.mapped('amount_residual')),
                'attendance_rate': attendance_rate,
                'recent_courses': enrollments[:5],
                'upcoming_assignments': assignments[:5],
                'today': today,
            })
            return request.render('tuition_management.portal_student_dashboard', values)

        if tutor:
            courses = request.env['course.master'].sudo().search([
                ('tutor_id', '=', tutor.id)])
            today_sessions = request.env['class.schedule.occurrence'].sudo().search_count([
                ('tutor_id', '=', tutor.id),
                ('start_datetime', '>=', fields.Datetime.now().replace(hour=0, minute=0, second=0)),
                ('start_datetime', '<=', fields.Datetime.now().replace(hour=23, minute=59, second=59)),
            ])
            student_ids = request.env['course.enrollment'].sudo().search([
                ('course_id', 'in', courses.ids), ('status', '=', 'active')
            ]).mapped('student_id').ids
            values.update({
                'tutor_course_count': len(courses),
                'today_sessions': today_sessions,
                'total_students': len(set(student_ids)),
                'tutor_courses': courses,
            })
            return request.render('tuition_management.portal_tutor_dashboard', values)
        if parent:
            child_data = []
            total_enrollments = 0
            for child in parent.student_ids:
                enrollments = request.env['course.enrollment'].sudo().search([
                    ('student_id', '=', child.id), ('status', '=', 'active')])
                total_enrollments += len(enrollments)
                child_data.append({'student': child, 'enrollments': enrollments})
            child_partners = parent.student_ids.mapped('partner_id').ids
            all_partners = list(set([parent.partner_id.id] + child_partners)) if parent.partner_id else child_partners
            invoices = request.env['account.move'].sudo().search([
                ('partner_id', 'in', all_partners),
                ('move_type', '=', 'out_invoice'),
                ('payment_state', '!=', 'paid'),
                ('state', '=', 'posted'),
            ])
            values.update({
                'child_count': len(parent.student_ids),
                'child_data': child_data,
                'total_enrollments': total_enrollments,
                'unpaid_invoices': len(invoices),
                'amount_due': sum(invoices.mapped('amount_residual')),
            })
            return request.render('tuition_management.portal_parent_dashboard', values)

        return super().home(**kw)

    @http.route(['/my/logout'], type='http', auth='public', website=True)
    def portal_logout(self, **kw):
        request.session.logout(keep_db=True)
        return request.redirect('/web/login')

    @http.route(['/my/tuition/invoices'], type='http', auth='user', website=True)
    def portal_tuition_invoices(self, **kw):
        parent = self._get_parent()
        student = self._get_student()
        if not parent and not student:
            return request.redirect('/my')

        if parent:
            child_partners = parent.student_ids.mapped('partner_id').ids if parent.student_ids else []
            parent_partner = [parent.partner_id.id] if parent.partner_id else []
            partner_ids = list(set(parent_partner + child_partners))
            invoices = request.env['account.move'].sudo().search([
                ('move_type', '=', 'out_invoice'),
                ('partner_id', 'in', partner_ids),
                ('tuition_subscription_id', '!=', False),
            ], order='invoice_date desc')
        else:
            partner_id = student.partner_id.id if student.partner_id else 0
            invoices = request.env['account.move'].sudo().search([
                ('move_type', '=', 'out_invoice'),
                ('partner_id', '=', partner_id),
                ('tuition_subscription_id', '!=', False),
            ], order='invoice_date desc')

        return request.render('tuition_management.portal_parent_invoices', {
            'user': request.env.user,
            'is_parent': bool(parent),
            'is_student': bool(student),
            'is_tutor': False,
            'invoices': invoices,
            'page_name': 'tuition_invoices',
        })

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
            'user': request.env.user,
            'is_student': bool(student),
            'is_tutor': bool(tutor),
            'is_parent': bool(parent),
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
            'user': request.env.user,
            'is_student': True,
            'is_tutor': False,
            'is_parent': False,
            'student': student,
            'enrollments': enrollments,
            'page_name': 'courses',
        })

    @http.route(['/my/courses/<int:course_id>'], type='http', auth='user', website=True)
    def portal_course_detail(self, course_id, **kw):
        partner = request.env.user.partner_id
        student = request.env['student.profile'].sudo().search([('partner_id', '=', partner.id)], limit=1)
        parent = request.env['parent.profile'].sudo().search([('partner_id', '=', partner.id)], limit=1)

        # Find enrollment — student or parent's child
        enrollment = None
        if student:
            enrollment = request.env['course.enrollment'].sudo().search([
                ('id', '=', course_id), ('student_id', '=', student.id)
            ], limit=1)
        if not enrollment and parent:
            child_ids = parent.student_ids.ids
            enrollment = request.env['course.enrollment'].sudo().search([
                ('id', '=', course_id), ('student_id', 'in', child_ids)
            ], limit=1)

        if not enrollment:
            return request.redirect('/my/dashboard')

        course = enrollment.course_id
        assignments = request.env['course.assignment'].sudo().search([
            ('course_id', '=', course.id)
        ])
        occurrences = request.env['class.schedule.occurrence'].sudo().search([
            ('course_id', '=', course.id)
        ], order='start_datetime desc', limit=20)
        attendance = request.env['attendance.record'].sudo().search([
            ('student_id', '=', enrollment.student_id.id),
            ('class_schedule_occurrence_id', 'in', occurrences.ids)
        ])
        attendance_map = {a.class_schedule_occurrence_id.id: a.status for a in attendance}
        progress_reports = request.env['progress.report'].sudo().search([
            ('course_id', '=', course.id),
            ('student_id', '=', enrollment.student_id.id),
        ], order='report_date desc')
        next_lesson = request.env['class.schedule.occurrence'].sudo().search([
            ('course_id', '=', course.id),
            ('start_datetime', '>=', fields.Datetime.now()),
            ('lesson_status', '=', 'scheduled'),
        ], order='start_datetime asc', limit=1)
        now = fields.Datetime.now()
        time_remaining = None
        if next_lesson and next_lesson.start_datetime:
            delta = next_lesson.start_datetime - now
            total_minutes = int(delta.total_seconds() // 60)
            if total_minutes > 0:
                days = total_minutes // 1440
                hours = (total_minutes % 1440) // 60
                mins = total_minutes % 60
                if days > 0:
                    time_remaining = '%dd %dh %dm' % (days, hours, mins)
                elif hours > 0:
                    time_remaining = '%dh %dm' % (hours, mins)
                else:
                    time_remaining = '%d minutes' % mins

        values = {
            'user': request.env.user,
            'is_student': bool(student),
            'is_parent': bool(parent),
            'enrollment': enrollment,
            'course': course,
            'assignments': assignments,
            'occurrences': occurrences,
            'attendance_map': attendance_map,
            'progress_reports': progress_reports,
            'next_lesson': next_lesson,
            'time_remaining': time_remaining,
            'page_name': 'my_courses',
            'page_title': course.name,
        }
        return request.render('tuition_management.portal_course_detail', values)

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
            'user': request.env.user,
            'is_student': True,
            'is_tutor': False,
            'is_parent': False,
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
            'user': request.env.user,
            'is_student': True,
            'is_tutor': False,
            'is_parent': False,
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
            'user': request.env.user,
            'is_student': True,
            'is_tutor': False,
            'is_parent': False,
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
            ('tutor_id', '=', tutor.id),
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
            'user': request.env.user,
            'is_tutor': True,
            'is_student': False,
            'is_parent': False,
            'tutor': tutor,
            'courses': courses,
            'course_data': course_data,
            'lesson_count': lesson_count,
            'page_name': 'tutor_courses',
        })

    @http.route(['/my/tutor/progress-reports'], type='http', auth='user', website=True)
    def portal_tutor_progress_reports(self, course_id=None, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        domain = [('tutor_id', '=', tutor.id)]
        courses = request.env['course.master'].sudo().search([('tutor_id', '=', tutor.id)])
        selected_course = None
        if course_id:
            domain.append(('course_id', '=', int(course_id)))
            selected_course = request.env['course.master'].sudo().browse(int(course_id))
        reports = request.env['progress.report'].sudo().search(domain, order='report_date desc')
        return request.render('tuition_management.portal_tutor_progress_reports', {
            'user': request.env.user,
            'is_tutor': True, 'is_student': False, 'is_parent': False,
            'tutor': tutor, 'reports': reports, 'courses': courses,
            'selected_course': selected_course, 'course_id': course_id,
            'page_name': 'tutor_progress_reports', 'page_title': 'Progress Reports',
        })

    @http.route('/my/tutor/progress-reports/create', type='http', auth='user', website=True)
    def tutor_progress_report_create(self, course_id=None, back_url=None, **kwargs):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        course = None
        if course_id:
            course = request.env['course.master'].sudo().browse(int(course_id))
            if not course.exists():
                course = None
        courses = request.env['course.master'].sudo().search([('tutor_id', '=', tutor.id)])
        students = request.env['student.profile'].sudo().search([])
        if not back_url:
            back_url = '/my/tutor/progress-reports'
        return request.render('tuition_management.portal_tutor_progress_report_form', {
            'tutor': tutor,
            'course': course,
            'courses': courses,
            'students': students,
            'report': None,
            'back_url': back_url,
            'csrf_token': request.csrf_token(),
        })

    @http.route(['/my/tutor/progress-reports/create/save'], type='http', auth='user', website=True, methods=['POST'])
    def portal_tutor_progress_report_create_save(self, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        course_id = int(kw.get('course_id') or 0)
        student_id = int(kw.get('student_id') or 0)
        if not course_id or not student_id:
            return request.redirect('/my/tutor/progress-reports')
        report = request.env['progress.report'].sudo().create({
            'name': kw.get('name') or 'Progress Report',
            'course_id': course_id,
            'student_id': student_id,
            'tutor_id': tutor.id,
            'report_date': kw.get('report_date') or fields.Date.today(),
            'overall_rating': kw.get('overall_rating') or False,
            'score': float(kw.get('score') or 0),
            'max_score': float(kw.get('max_score') or 100),
            'strengths': kw.get('strengths', ''),
            'areas_for_improvement': kw.get('areas_for_improvement', ''),
            'comments': kw.get('comments', ''),
            'homework_notes': kw.get('homework_notes', ''),
        })
        return request.redirect('/my/tutor/progress-reports/%d/edit?saved=1' % report.id)

    @http.route(['/my/tutor/progress-reports/<int:report_id>/edit'], type='http', auth='user', website=True)
    def portal_tutor_progress_report_edit(self, report_id, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        report = request.env['progress.report'].sudo().browse(report_id)
        if not report.exists() or report.tutor_id.id != tutor.id:
            return request.redirect('/my/tutor/progress-reports')
        courses = request.env['course.master'].sudo().search([('tutor_id', '=', tutor.id)])
        enrollments = request.env['course.enrollment'].sudo().search([
            ('course_id', '=', report.course_id.id), ('status', '=', 'active')
        ])
        return request.render('tuition_management.portal_tutor_progress_report_form', {
            'user': request.env.user,
            'is_tutor': True, 'is_student': False, 'is_parent': False,
            'tutor': tutor, 'courses': courses, 'enrollments': enrollments,
            'preselect_course': report.course_id, 'report': report,
            'saved': kw.get('saved'),
            'page_name': 'tutor_progress_reports', 'page_title': 'Edit Progress Report',
        })

    @http.route(['/my/tutor/progress-reports/<int:report_id>/save'], type='http', auth='user', website=True, methods=['POST'])
    def portal_tutor_progress_report_save(self, report_id, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        report = request.env['progress.report'].sudo().browse(report_id)
        if not report.exists() or report.tutor_id.id != tutor.id:
            return request.redirect('/my/tutor/progress-reports')
        report.write({
            'name': kw.get('name') or report.name,
            'report_date': kw.get('report_date') or report.report_date,
            'overall_rating': kw.get('overall_rating') or False,
            'score': float(kw.get('score') or 0),
            'max_score': float(kw.get('max_score') or 100),
            'strengths': kw.get('strengths', ''),
            'areas_for_improvement': kw.get('areas_for_improvement', ''),
            'comments': kw.get('comments', ''),
            'homework_notes': kw.get('homework_notes', ''),
        })
        return request.redirect('/my/tutor/progress-reports/%d/edit?saved=1' % report_id)

    @http.route(['/my/tutor/progress-reports/<int:report_id>/delete'], type='http', auth='user', website=True, methods=['POST'])
    def portal_tutor_progress_report_delete(self, report_id, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        report = request.env['progress.report'].sudo().browse(report_id)
        if report.exists() and report.tutor_id.id == tutor.id:
            report.unlink()
        return request.redirect('/my/tutor/progress-reports?deleted=1')

    @http.route(['/my/tutor/progress-reports/students'], type='http', auth='user', website=True)
    def portal_tutor_progress_report_students(self, course_id=None, **kw):
        tutor = self._get_tutor()
        if not tutor or not course_id:
            return request.make_response('[]', headers=[('Content-Type', 'application/json')])
        enrollments = request.env['course.enrollment'].sudo().search([
            ('course_id', '=', int(course_id)), ('status', '=', 'active')
        ])
        import json
        data = [{'id': e.student_id.id, 'name': e.student_id.name} for e in enrollments]
        return request.make_response(json.dumps(data), headers=[('Content-Type', 'application/json')])

    @http.route(['/my/tutor/payments'], type='http', auth='user', website=True)
    def portal_tutor_payments(self, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        domain = [('move_type', 'in', ['in_invoice', 'in_receipt'])]
        if tutor.partner_id:
            domain.append(('partner_id', '=', tutor.partner_id.id))
        else:
            domain.append(('id', '=', False))
        invoices = request.env['account.move'].sudo().search(domain, order='invoice_date desc')
        total_paid = sum(invoices.filtered(lambda i: i.payment_state == 'paid').mapped('amount_total'))
        total_pending = sum(invoices.filtered(lambda i: i.payment_state != 'paid' and i.state == 'posted').mapped('amount_residual'))
        return request.render('tuition_management.portal_tutor_payments', {
            'user': request.env.user,
            'is_tutor': True,
            'is_student': False,
            'is_parent': False,
            'tutor': tutor,
            'invoices': invoices,
            'total_paid': total_paid,
            'total_pending': total_pending,
            'page_name': 'tutor_payments',
            'page_title': 'My Payments',
        })

    @http.route(['/my/tutor/schedule'], type='http', auth='user', website=True)
    def portal_tutor_schedule(self, week='this', **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
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
            ('tutor_id', '=', tutor.id),
            ('start_datetime', '>=', datetime.combine(start_date, datetime.min.time())),
            ('start_datetime', '<=', datetime.combine(end_date, datetime.max.time())),
        ], order='start_datetime asc')
        occ_data = []
        for occ in occurrences:
            occ_data.append({
                'occ': occ,
                'date_str': occ.start_datetime.strftime('%a, %d %b %Y') if occ.start_datetime else '',
                'time_str': occ.start_datetime.strftime('%H:%M') if occ.start_datetime else '',
            })
        return request.render('tuition_management.portal_tutor_schedule', {
            'user': request.env.user,
            'is_tutor': True,
            'is_student': False,
            'is_parent': False,
            'tutor': tutor,
            'occ_data': occ_data,
            'current_week': week,
            'page_name': 'tutor_schedule',
            'page_title': 'My Schedule',
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
            'user': request.env.user,
            'is_tutor': True,
            'is_student': False,
            'is_parent': False,
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
            'user': request.env.user,
            'is_tutor': True,
            'is_student': False,
            'is_parent': False,
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
            'user': request.env.user,
            'is_tutor': True,
            'is_student': False,
            'is_parent': False,
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
            'user': request.env.user,
            'is_tutor': True,
            'is_student': False,
            'is_parent': False,
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
            'user': request.env.user,
            'is_tutor': True,
            'is_student': False,
            'is_parent': False,
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

    @http.route('/my/tutor/assignments', type='http', auth='user', website=True)
    def tutor_all_assignments(self, **kwargs):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my/tutor/courses')
        courses = request.env['course.master'].sudo().search([('tutor_id', '=', tutor.id)])
        assignments = request.env['course.assignment'].sudo().search(
            [('course_id', 'in', courses.ids)], order='due_date asc'
        )
        return request.render('tuition_management.portal_tutor_all_assignments', {
            'tutor': tutor,
            'assignments': assignments,
            'courses': courses,
            'page_name': 'tutor_all_assignments',
        })

    # ──────────────────────────────────────────────
    # PARENT PORTAL
    # ──────────────────────────────────────────────

    @http.route(['/my/parent/children/<int:student_id>'], type='http', auth='user', website=True)
    def portal_parent_child_detail(self, student_id, **kw):
        parent = self._get_parent()
        if not parent:
            return request.redirect('/my')
        child = parent.student_ids.filtered(lambda s: s.id == student_id)
        if not child:
            return request.redirect('/my/parent/children')
        child = child[0]
        enrollments = request.env['course.enrollment'].sudo().search([
            ('student_id', '=', child.id), ('status', '=', 'active'),
        ])
        progress_reports = request.env['progress.report'].sudo().search([
            ('student_id', '=', child.id),
        ], order='report_date desc', limit=20)
        attendance_records = request.env['attendance.record'].sudo().search([
            ('student_id', '=', child.id),
        ], order='id desc', limit=30)
        total = len(attendance_records)
        present = len(attendance_records.filtered(lambda a: a.status == 'present'))
        attendance_rate = ('%d%%' % round(present * 100 / total)) if total else '—'
        return request.render('tuition_management.portal_parent_child_detail', {
            'user': request.env.user,
            'is_parent': True,
            'is_student': False,
            'is_tutor': False,
            'child': child,
            'enrollments': enrollments,
            'progress_reports': progress_reports,
            'attendance_records': attendance_records,
            'attendance_rate': attendance_rate,
            'page_name': 'parent_children',
            'page_title': child.name,
        })

    @http.route(['/my/parent/children'], type='http', auth='user', website=True)
    def portal_parent_children(self, **kw):
        parent = self._get_parent()
        if not parent:
            return request.redirect('/my')
        children = parent.student_ids
        child_data = []
        total_enrollments = 0
        for child in children:
            enrollments = request.env['course.enrollment'].sudo().search([
                ('student_id', '=', child.id), ('status', '=', 'active'),
            ])
            total_enrollments += len(enrollments)
            child_data.append({'student': child, 'enrollments': enrollments})
        child_partners = parent.student_ids.mapped('partner_id').ids
        all_partners = list(set([parent.partner_id.id] + child_partners)) if parent.partner_id else child_partners
        invoices = request.env['account.move'].sudo().search([
            ('partner_id', 'in', all_partners),
            ('move_type', '=', 'out_invoice'),
            ('payment_state', '!=', 'paid'),
            ('state', '=', 'posted'),
        ])
        return request.render('tuition_management.portal_parent_dashboard', {
            'user': request.env.user,
            'is_parent': True,
            'is_student': False,
            'is_tutor': False,
            'parent': parent,
            'child_data': child_data,
            'child_count': len(children),
            'total_enrollments': total_enrollments,
            'unpaid_invoices': len(invoices),
            'amount_due': sum(invoices.mapped('amount_residual')),
            'page_name': 'parent_children',
            'page_title': 'My Children',
        })

    @http.route(['/my/tutor/courses/<int:course_id>/assignments/new'], type='http', auth='user', website=True)
    def portal_tutor_assignment_new(self, course_id, back_url=None, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        course = request.env['course.master'].sudo().browse(course_id)
        if not course.exists() or course.tutor_id.id != tutor.id:
            return request.redirect('/my/tutor/courses')
        if not back_url:
            back_url = '/my/tutor/courses/%d' % course_id
        return request.render('tuition_management.portal_tutor_assignment_new', {
            'user': request.env.user,
            'is_tutor': True,
            'is_student': False,
            'is_parent': False,
            'tutor': tutor,
            'course': course,
            'back_url': back_url,
            'page_name': 'tutor_course_detail',
            'csrf_token': request.csrf_token(),
        })


