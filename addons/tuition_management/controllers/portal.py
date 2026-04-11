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
                'student': student,
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

            # This week's lesson count
            start_of_week = today - timedelta(days=today.weekday())
            end_of_week = start_of_week + timedelta(days=6)
            this_week_lesson_count = request.env['class.schedule.occurrence'].sudo().search_count([
                ('tutor_id', '=', tutor.id),
                ('start_datetime', '>=', datetime.combine(start_of_week, datetime.min.time())),
                ('start_datetime', '<=', datetime.combine(end_of_week, datetime.max.time())),
            ])

            # Upcoming lessons (next 7 days, max 10)
            upcoming_lessons = request.env['class.schedule.occurrence'].sudo().search([
                ('tutor_id', '=', tutor.id),
                ('start_datetime', '>=', fields.Datetime.now()),
                ('start_datetime', '<=', datetime.combine(today + timedelta(days=7), datetime.max.time())),
            ], order='start_datetime asc', limit=10)

            values.update({
                'tutor': tutor,
                'tutor_course_count': len(courses),
                'today_sessions': today_sessions,
                'total_students': len(set(student_ids)),
                'tutor_courses': courses,
                'this_week_lesson_count': this_week_lesson_count,
                'upcoming_lessons': upcoming_lessons,
            })
            return request.render('tuition_management.portal_tutor_home_dashboard', values)
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

    @http.route(['/my/student/schedule'], type='http', auth='user', website=True)
    def portal_student_schedule(self, week='this', **kw):
        student = self._get_student()
        if not student:
            return request.redirect('/my')
        enrollments = request.env['course.enrollment'].sudo().search([
            ('student_id', '=', student.id), ('status', '=', 'active'),
        ])
        course_ids = enrollments.mapped('course_id').ids

        today = fields.Date.today()
        try:
            week_offset = int(kw.get('week_offset', 0))
        except (ValueError, TypeError):
            week_offset = 0
        start_of_week = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
        end_of_week = start_of_week + timedelta(days=6)
        week_label = '%s — %s' % (start_of_week.strftime('%d %b'), end_of_week.strftime('%d %b %Y'))
        if week_offset == 0:
            week_label = 'This Week (%s)' % week_label

        occurrences = request.env['class.schedule.occurrence'].sudo().search([
            ('course_id', 'in', course_ids),
            ('start_datetime', '>=', datetime.combine(start_of_week, datetime.min.time())),
            ('start_datetime', '<=', datetime.combine(end_of_week, datetime.max.time())),
        ], order='start_datetime asc')

        attendance = request.env['attendance.record'].sudo().search([
            ('student_id', '=', student.id),
            ('class_schedule_occurrence_id', 'in', occurrences.ids),
        ])
        attendance_map = {a.class_schedule_occurrence_id.id: a.status for a in attendance}

        occ_data = []
        for occ in occurrences:
            try:
                date_str = occ.start_datetime.strftime('%a, %d %b %Y') if occ.start_datetime else ''
                time_str = occ.start_datetime.strftime('%I:%M %p') if occ.start_datetime else ''
            except Exception:
                date_str = str(occ.start_datetime) if occ.start_datetime else ''
                time_str = ''
            att_status = attendance_map.get(occ.id, '')
            occ_data.append({
                'occ': occ,
                'date_str': date_str,
                'time_str': time_str,
                'att_status': att_status,
            })

        return request.render('tuition_management.portal_student_schedule', {
            'user': request.env.user,
            'is_student': True,
            'is_tutor': False,
            'is_parent': False,
            'student': student,
            'occ_data': occ_data,
            'week_offset': week_offset,
            'week_label': week_label,
            'page_name': 'student_schedule',
            'page_title': 'My Schedule',
        })

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

        # Weekly occurrences with prev/next navigation
        today = fields.Date.today()
        try:
            week_offset = int(kw.get('week_offset', 0))
        except (ValueError, TypeError):
            week_offset = 0
        start_of_week = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
        end_of_week = start_of_week + timedelta(days=6)
        week_label = '%s — %s' % (start_of_week.strftime('%d %b'), end_of_week.strftime('%d %b %Y'))
        if week_offset == 0:
            week_label = 'This Week (%s)' % week_label

        occurrences = request.env['class.schedule.occurrence'].sudo().search([
            ('course_id', '=', course.id),
            ('start_datetime', '>=', datetime.combine(start_of_week, datetime.min.time())),
            ('start_datetime', '<=', datetime.combine(end_of_week, datetime.max.time())),
        ], order='start_datetime asc')

        attendance = request.env['attendance.record'].sudo().search([
            ('student_id', '=', enrollment.student_id.id),
            ('class_schedule_occurrence_id', 'in', occurrences.ids)
        ])
        attendance_map = {a.class_schedule_occurrence_id.id: a.status for a in attendance}
        progress_reports = request.env['progress.report'].sudo().search([
            ('course_id', '=', course.id),
            ('student_id', '=', enrollment.student_id.id),
        ], order='report_date desc')

        values = {
            'user': request.env.user,
            'is_student': bool(student),
            'is_parent': bool(parent),
            'is_tutor': False,
            'enrollment': enrollment,
            'course': course,
            'assignments': assignments,
            'occurrences': occurrences,
            'attendance_map': attendance_map,
            'progress_reports': progress_reports,
            'week_offset': week_offset,
            'week_label': week_label,
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
        # Pre-compute student submission for template (avoid lambda in QWeb)
        for asgn in assignments:
            asgn.student_submission = asgn.submission_ids.filtered(lambda s: s.student_id.id == student.id)
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
    def portal_tutor_dashboard(self, **kw):
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

        # Pre-compute active enrollments (avoid lambda in QWeb)
        active_enrollments = course.enrollment_ids.filtered(lambda e: e.status == 'active')
        active_enrollment_count = len(active_enrollments)

        return request.render('tuition_management.portal_tutor_course_detail', {
            'user': request.env.user,
            'is_tutor': True,
            'is_student': False,
            'is_parent': False,
            'tutor': tutor,
            'course': course,
            'this_week_lessons': this_week_lessons,
            'active_enrollments': active_enrollments,
            'active_enrollment_count': active_enrollment_count,
            'enrolled_students': enrolled_students,
            'course_assignments': course_assignments,
            'active_enrollments': active_enrollments,
            'active_enrollment_count': active_enrollment_count,
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

    # ──────────────────────────────────────────────
    # PARENT PORTAL
    # ──────────────────────────────────────────────

    @http.route(['/my/parent/schedule'], type='http', auth='user', website=True)
    def portal_parent_schedule(self, **kw):
        parent = self._get_parent()
        if not parent:
            return request.redirect('/my')
        child_ids = parent.student_ids.ids
        course_ids = request.env['course.enrollment'].sudo().search([
            ('student_id', 'in', child_ids), ('status', '=', 'active'),
        ]).mapped('course_id').ids

        today = fields.Date.today()
        try:
            week_offset = int(kw.get('week_offset', 0))
        except (ValueError, TypeError):
            week_offset = 0
        start_of_week = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
        end_of_week = start_of_week + timedelta(days=6)
        week_label = '%s — %s' % (start_of_week.strftime('%d %b'), end_of_week.strftime('%d %b %Y'))
        if week_offset == 0:
            week_label = 'This Week (%s)' % week_label

        occurrences = request.env['class.schedule.occurrence'].sudo().search([
            ('course_id', 'in', course_ids),
            ('start_datetime', '>=', datetime.combine(start_of_week, datetime.min.time())),
            ('start_datetime', '<=', datetime.combine(end_of_week, datetime.max.time())),
        ], order='start_datetime asc')

        # Build attendance map for all children
        attendance = request.env['attendance.record'].sudo().search([
            ('student_id', 'in', child_ids),
            ('class_schedule_occurrence_id', 'in', occurrences.ids),
        ])
        att_by_occ = {}
        for a in attendance:
            att_by_occ.setdefault(a.class_schedule_occurrence_id.id, []).append({
                'student_name': a.student_id.name,
                'status': a.status,
            })

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
                'attendance': att_by_occ.get(occ.id, []),
            })

        return request.render('tuition_management.portal_parent_schedule', {
            'user': request.env.user,
            'is_parent': True,
            'is_student': False,
            'is_tutor': False,
            'parent': parent,
            'occ_data': occ_data,
            'week_offset': week_offset,
            'week_label': week_label,
            'page_name': 'parent_schedule',
            'page_title': 'Schedules',
        })

    @http.route(['/my/parent/progress'], type='http', auth='user', website=True)
    def portal_parent_progress(self, **kw):
        parent = self._get_parent()
        if not parent:
            return request.redirect('/my')
        child_data = []
        for child in parent.student_ids:
            reports = request.env['progress.report'].sudo().search([
                ('student_id', '=', child.id),
            ], order='report_date desc', limit=20)
            total_att = request.env['attendance.record'].sudo().search_count([
                ('student_id', '=', child.id)])
            present_att = request.env['attendance.record'].sudo().search_count([
                ('student_id', '=', child.id), ('status', '=', 'present')])
            att_rate = ('%d%%' % round(present_att * 100 / total_att)) if total_att else '—'
            child_data.append({
                'student': child,
                'reports': reports,
                'attendance_rate': att_rate,
            })
        return request.render('tuition_management.portal_parent_progress', {
            'user': request.env.user,
            'is_parent': True,
            'is_student': False,
            'is_tutor': False,
            'parent': parent,
            'child_data': child_data,
            'page_name': 'parent_progress',
            'page_title': 'Progress',
        })

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