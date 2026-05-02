# -*- coding: utf-8 -*-
from odoo import http, fields
from odoo.http import request
from datetime import timedelta, datetime
from types import SimpleNamespace
import base64

from .portal_mixin import PortalMixin


class TutorPortal(http.Controller, PortalMixin):
    """Tutor-specific portal routes."""

    def _tutor_has_course_access(self, tutor, course):
        """Return True if tutor is the primary tutor OR in the supporting tutors set."""
        return course.tutor_id == tutor or tutor in course.tutor_ids

    # ──────────────────────────────────────────────
    # COURSES
    # ──────────────────────────────────────────────

    @http.route(['/my/tutor/courses'], type='http', auth='user', website=True)
    def portal_tutor_dashboard(self, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        # Show courses where this tutor is the primary tutor OR in the supporting tutors set
        courses = request.env['course.master'].sudo().search([
            '|',
            ('tutor_id', '=', tutor.id),
            ('tutor_ids', 'in', tutor.id),
        ])
        today = fields.Date.today()
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        lesson_count = request.env['class.schedule.occurrence'].sudo().search_count([
            ('tutor_id', '=', tutor.id),
            ('start_datetime', '>=', datetime.combine(start_of_week, datetime.min.time())),
            ('start_datetime', '<=', datetime.combine(end_of_week, datetime.max.time())),
        ])
        course_data = []
        for c in courses:
            course_data.append({
                'course': c,
                'student_count': c.student_count,
                'assignment_count': len(c.assignment_ids),
            })
        return request.render('tuition_management.portal_tutor_dashboard', {
            'user': request.env.user,
            'is_tutor': True, 'is_student': False, 'is_parent': False,
            'tutor': tutor,
            'courses': courses,
            'course_data': course_data,
            'lesson_count': lesson_count,
            'user_tz': self._get_user_tz(),
            'page_name': 'tutor_courses',
        })

    @http.route(['/my/tutor/courses/<int:course_id>'], type='http', auth='user', website=True)
    def portal_tutor_course_detail(self, course_id, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        course = request.env['course.master'].sudo().browse(course_id)
        # Allow access if this tutor is the primary tutor OR in the supporting tutors set
        if not course.exists() or (course.tutor_id != tutor and tutor not in course.tutor_ids):
            return request.redirect('/my/tutor/courses')

        today = fields.Date.today()
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        # Only show this tutor's assigned lessons for this week
        this_week_lessons = request.env['class.schedule.occurrence'].sudo().search([
            ('course_id', '=', course.id),
            ('tutor_id', '=', tutor.id),
            ('start_datetime', '>=', datetime.combine(start_of_week, datetime.min.time())),
            ('start_datetime', '<=', datetime.combine(end_of_week, datetime.max.time())),
        ], order='start_datetime asc')

        # Fetch the very next upcoming session for this course (any tutor) so
        # supporting/monitoring tutors who aren't assigned to the lesson can still
        # see and launch it from the course detail page.
        # Use NOT IN cancelled/completed rather than = 'scheduled' because generated
        # occurrences may carry lesson_status 'pending' or False.
        next_session = request.env['class.schedule.occurrence'].sudo().search([
            ('course_id', '=', course.id),
            ('lesson_status', 'not in', ['cancelled', 'completed', 'no_show']),
            ('start_datetime', '>=', datetime.utcnow()),
        ], order='start_datetime asc', limit=1)

        enrolled_students = course.enrollment_ids.filtered(lambda e: e.status == 'active')
        active_enrollments = course.enrollment_ids.filtered(lambda e: e.status == 'active')
        course_assignments = course.assignment_ids
        course_progress_reports = request.env['progress.report'].sudo().search([
            ('course_id', '=', course.id),
        ], order='report_date desc')

        vc_provider_labels = {'bbb': 'BigBlueButton', 'zoom': 'Zoom', 'google_meet': 'Google Meet'}

        return request.render('tuition_management.portal_tutor_course_detail', {
            'user': request.env.user,
            'is_tutor': True, 'is_student': False, 'is_parent': False,
            'tutor': tutor,
            'course': course,
            'this_week_lessons': this_week_lessons,
            'next_session': next_session,
            'active_enrollments': active_enrollments,
            'active_enrollment_count': len(active_enrollments),
            'enrolled_students': enrolled_students,
            'course_assignments': course_assignments,
            'course_progress_reports': course_progress_reports,
            'lessons_url': f'/my/tutor/courses/{course.id}/lessons',
            'assignments_url': f'/my/tutor/courses/{course.id}/assignments',
            'page_name': 'tutor_course_detail',
            'page_title': course.name,
            'user_tz': self._get_user_tz(),
            'vc_provider_labels': vc_provider_labels,
            'vc_error': kw.get('vc_error'),
            'vc_success': kw.get('vc_success'),
        })

    @http.route(['/my/tutor/courses/<int:course_id>/update-provider'], type='http',
                auth='user', website=True, methods=['POST'], csrf=True)
    def portal_tutor_update_provider(self, course_id, provider=None, **kw):
        """Allow tutor/admin to change the course VC provider from the portal course page."""
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        course = request.env['course.master'].sudo().browse(course_id)
        # Allow access if this tutor is the primary tutor OR in the supporting tutors set
        if not course.exists() or (course.tutor_id != tutor and tutor not in course.tutor_ids):
            return request.redirect('/my/tutor/courses')
        valid_providers = {'bbb', 'zoom', 'google_meet'}
        if provider not in valid_providers:
            return request.redirect(f'/my/tutor/courses/{course_id}?vc_error=Invalid+provider+selected')
        course.sudo().write({'virtual_provider_default': provider})
        return request.redirect(f'/my/tutor/courses/{course_id}?vc_success=Provider+updated+successfully')

    # ──────────────────────────────────────────────
    # SCHEDULE
    # ──────────────────────────────────────────────

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
            local_dt = self._to_user_tz(occ.start_datetime)
            occ_data.append({
                'occ': occ,
                'date_str': local_dt.strftime('%a, %d %b %Y') if local_dt else '',
                'time_str': local_dt.strftime('%I:%M %p') if local_dt else '',
            })
        return request.render('tuition_management.portal_tutor_schedule', {
            'user': request.env.user,
            'is_tutor': True, 'is_student': False, 'is_parent': False,
            'tutor': tutor,
            'occ_data': occ_data,
            'current_week': week,
            'user_tz': self._get_user_tz(),
            'page_name': 'tutor_schedule',
            'page_title': 'My Schedule',
            'csrf_token': request.csrf_token(),
            'vc_error': kw.get('vc_error'),
        })

    # ──────────────────────────────────────────────
    # LESSONS
    # ──────────────────────────────────────────────

    @http.route(['/my/tutor/courses/<int:course_id>/lessons',
                 '/my/tutor/courses/<int:course_id>/lessons/'], type='http', auth='user', website=True)
    def portal_tutor_lessons(self, course_id, week='this', **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my/tutor/courses')
        course = request.env['course.master'].sudo().browse(course_id)
        if not course.exists():
            return request.redirect('/my/tutor/courses')
        if not self._tutor_has_course_access(tutor, course):
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
            ('tutor_id', '=', tutor.id),
            ('start_datetime', '>=', datetime.combine(start_date, datetime.min.time())),
            ('start_datetime', '<=', datetime.combine(end_date, datetime.max.time())),
        ], order='start_datetime asc')

        occ_data = []
        for occ in occurrences:
            try:
                local_dt = self._to_user_tz(occ.start_datetime)
                date_str = local_dt.strftime('%a, %d %b %Y') if local_dt else ''
                time_str = local_dt.strftime('%I:%M %p') if local_dt else ''
            except Exception:
                date_str = str(occ.start_datetime) if occ.start_datetime else ''
                time_str = ''
            occ_data.append({'occ': occ, 'date_str': date_str, 'time_str': time_str})

        return request.render('tuition_management.portal_tutor_lessons', {
            'user': request.env.user,
            'is_tutor': True, 'is_student': False, 'is_parent': False,
            'tutor': tutor,
            'course': course,
            'occurrences': occurrences,
            'occ_data': occ_data,
            'current_week': week,
            'user_tz': self._get_user_tz(),
            'back_url': f'/my/tutor/courses/{course.id}',
            'page_name': 'tutor_lessons',
            'csrf_token': request.csrf_token(),
            'vc_error': kw.get('vc_error'),
        })

    # ──────────────────────────────────────────────
    # ATTENDANCE
    # ──────────────────────────────────────────────

    @http.route(['/my/tutor/lesson/<int:occurrence_id>/attendance'], type='http', auth='user', website=True)
    def portal_tutor_attendance_form(self, occurrence_id, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my/tutor/courses')
        occurrence = request.env['class.schedule.occurrence'].sudo().browse(occurrence_id)
        if not occurrence.exists():
            return request.redirect('/my/tutor/courses')
        if occurrence.tutor_id and occurrence.tutor_id != tutor:
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
            'is_tutor': True, 'is_student': False, 'is_parent': False,
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
        if occurrence.tutor_id and occurrence.tutor_id != tutor:
            return request.redirect('/my/tutor/courses')

        lesson_status = kw.get('lesson_status', 'completed')
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
        return request.redirect(f'/my/tutor/courses/{occurrence.course_id.id}')

    # ──────────────────────────────────────────────
    # ASSIGNMENTS
    # ──────────────────────────────────────────────

    @http.route(['/my/tutor/courses/<int:course_id>/assignments'], type='http', auth='user', website=True)
    def portal_tutor_assignments(self, course_id, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        course = request.env['course.master'].sudo().browse(course_id)
        if not course.exists() or not self._tutor_has_course_access(tutor, course):
            return request.redirect('/my/tutor/courses')
        return request.render('tuition_management.portal_tutor_assignments', {
            'user': request.env.user,
            'is_tutor': True, 'is_student': False, 'is_parent': False,
            'tutor': tutor,
            'course': course,
            'assignments': course.assignment_ids,
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
        if not course.exists() or not self._tutor_has_course_access(tutor, course):
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
        if not assignment.exists() or not self._tutor_has_course_access(tutor, assignment.course_id):
            return request.redirect('/my/tutor/courses')
        return request.render('tuition_management.portal_tutor_assignment_detail', {
            'user': request.env.user,
            'is_tutor': True, 'is_student': False, 'is_parent': False,
            'tutor': tutor,
            'assignment': assignment,
            'course': assignment.course_id,
            'submissions': assignment.submission_ids,
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
        if not submission.exists() or not self._tutor_has_course_access(tutor, submission.assignment_id.course_id):
            return request.redirect('/my/tutor/courses')
        try:
            score = float(kw.get('score', 0))
        except (ValueError, TypeError):
            score = 0
        submission.sudo().write({
            'score': score,
            'feedback': kw.get('feedback', ''),
            'status': 'graded',
        })
        return request.redirect(f'/my/tutor/assignment/{submission.assignment_id.id}?graded=1')

    @http.route(['/my/tutor/all-assignments'], type='http', auth='user', website=True)
    def portal_tutor_all_assignments(self, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        courses = request.env['course.master'].sudo().search([
            '|', ('tutor_id', '=', tutor.id), ('tutor_ids', 'in', tutor.id),
        ])
        assignments = request.env['course.assignment'].sudo().search([
            ('course_id', 'in', courses.ids),
        ], order='due_date desc')
        return request.render('tuition_management.portal_tutor_all_assignments', {
            'user': request.env.user,
            'is_tutor': True, 'is_student': False, 'is_parent': False,
            'tutor': tutor,
            'assignments': assignments,
            'tutor_courses': courses,
            'page_name': 'tutor_all_assignments',
            'page_title': 'All Assignments',
        })

    # ──────────────────────────────────────────────
    # PROGRESS REPORTS
    # ──────────────────────────────────────────────

    @http.route(['/my/tutor/progress'], type='http', auth='user', website=True)
    def portal_tutor_progress(self, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        courses = request.env['course.master'].sudo().search([
            '|', ('tutor_id', '=', tutor.id), ('tutor_ids', 'in', tutor.id),
        ])
        reports = request.env['progress.report'].sudo().search([
            ('course_id', 'in', courses.ids),
        ], order='report_date desc')
        return request.render('tuition_management.portal_tutor_all_progress', {
            'user': request.env.user,
            'is_tutor': True, 'is_student': False, 'is_parent': False,
            'tutor': tutor,
            'reports': reports,
            'tutor_courses': courses,
            'page_name': 'tutor_progress',
            'page_title': 'Progress Reports',
        })

    @http.route(['/my/tutor/courses/<int:course_id>/progress/new'], type='http', auth='user', website=True)
    def portal_tutor_progress_new(self, course_id, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        course = request.env['course.master'].sudo().browse(course_id)
        if not course.exists() or not self._tutor_has_course_access(tutor, course):
            return request.redirect('/my/tutor/courses')
        enrolled_students = course.enrollment_ids.filtered(lambda e: e.status == 'active')
        return request.render('tuition_management.portal_tutor_progress_new', {
            'user': request.env.user,
            'is_tutor': True, 'is_student': False, 'is_parent': False,
            'tutor': tutor,
            'course': course,
            'enrolled_students': enrolled_students,
            'page_name': 'tutor_course_detail',
            'page_title': 'New Progress Report',
            'csrf_token': request.csrf_token(),
        })

    @http.route(['/my/tutor/courses/<int:course_id>/progress/create'], type='http',
                auth='user', website=True, methods=['POST'], csrf=True)
    def portal_tutor_progress_create(self, course_id, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        course = request.env['course.master'].sudo().browse(course_id)
        if not course.exists() or not self._tutor_has_course_access(tutor, course):
            return request.redirect('/my/tutor/courses')
        vals = {
            'name': kw.get('name', 'Progress Report'),
            'course_id': course.id,
            'student_id': int(kw.get('student_id', 0)),
            'report_date': kw.get('report_date') or fields.Date.today(),
            'overall_rating': kw.get('overall_rating', ''),
            'score': float(kw.get('score', 0) or 0),
            'max_score': float(kw.get('max_score', 100) or 100),
            'comments': kw.get('comments', ''),
            'strengths': kw.get('strengths', ''),
        }
        request.env['progress.report'].sudo().create(vals)
        return request.redirect(f'/my/tutor/courses/{course_id}?progress_created=1')

    # ──────────────────────────────────────────────
    # PAYMENTS
    # ──────────────────────────────────────────────

    @http.route(['/my/tutor/payments'], type='http', auth='user', website=True)
    def portal_tutor_payments(self, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        payment_summaries = request.env['tutor.payment.summary'].sudo().search([
            ('tutor_id', '=', tutor.id),
            ('payment_status', 'in', ['approved', 'paid']),
        ], order='payment_run_id desc, id desc')
        paid_bills = self._prepare_tutor_payment_rows(
            payment_summaries.filtered(lambda summary: summary.payment_status == 'paid')
        )
        pending_bills = self._prepare_tutor_payment_rows(
            payment_summaries.filtered(lambda summary: summary.payment_status == 'approved')
        )
        return request.render('tuition_management.portal_tutor_payments', {
            'user': request.env.user,
            'is_tutor': True, 'is_student': False, 'is_parent': False,
            'tutor': tutor,
            'paid_bills': paid_bills,
            'pending_bills': pending_bills,
            'total_paid': sum(bill.amount_total for bill in paid_bills),
            'total_pending': sum(bill.amount_residual for bill in pending_bills),
            'page_name': 'tutor_payments',
            'page_title': 'Payments',
        })

    def _prepare_tutor_payment_rows(self, summaries):
        """Expose payroll summaries through the fields used by the existing portal template."""
        rows = []
        for summary in summaries:
            run = summary.payment_run_id
            paid_date = run.paid_date.date() if run.paid_date else False
            invoice_date = paid_date or run.payment_period_to or run.payment_period_from
            rows.append(SimpleNamespace(
                id=summary.id,
                name=run.name,
                invoice_date=invoice_date,
                amount_total=summary.gross_pay,
                amount_residual=0.0 if summary.payment_status == 'paid' else summary.gross_pay,
                payment_state='paid' if summary.payment_status == 'paid' else 'not_paid',
                state='posted',
                payment_status=summary.payment_status,
                payment_run_id=run,
                summary=summary,
            ))
        return rows
