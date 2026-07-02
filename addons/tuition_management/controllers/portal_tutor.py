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

        filter_course_id = kw.get('course_id', '').strip()
        filter_student_name = kw.get('student_name', '').strip()

        tutor_domain = [
            '|',
            ('tutor_id', '=', tutor.id),
            ('tutor_ids', 'in', tutor.id),
        ]
        all_tutor_courses = request.env['course.master'].sudo().search(tutor_domain)

        domain = list(tutor_domain)
        if filter_course_id:
            try:
                domain.append(('id', '=', int(filter_course_id)))
            except (ValueError, TypeError):
                pass
        if filter_student_name:
            domain.append(('enrollment_ids.student_id.name', 'ilike', filter_student_name))

        courses = request.env['course.master'].sudo().search(domain)

        start_utc, end_utc, _mon, _sun, _lbl = self._tz_week_bounds(0)
        lesson_count = request.env['class.schedule.occurrence'].sudo().search_count([
            ('tutor_id', '=', tutor.id),
            ('start_datetime', '>=', start_utc),
            ('start_datetime', '<=', end_utc),
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
            'all_tutor_courses': all_tutor_courses,
            'course_data': course_data,
            'lesson_count': lesson_count,
            'user_tz': self._get_user_tz(),
            'page_name': 'tutor_courses',
            'filter_course_id': filter_course_id,
            'filter_student_name': filter_student_name,
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

        start_utc, end_utc, _mon, _sun, _lbl = self._tz_week_bounds(0)
        # Only show this tutor's assigned lessons for this week
        this_week_lessons = request.env['class.schedule.occurrence'].sudo().search([
            ('course_id', '=', course.id),
            ('tutor_id', '=', tutor.id),
            ('start_datetime', '>=', start_utc),
            ('start_datetime', '<=', end_utc),
        ], order='start_datetime asc')

        # Fetch the very next upcoming session for this course (any tutor) so
        # supporting/monitoring tutors who aren't assigned to the lesson can still
        # see and launch it from the course detail page.
        # Use NOT IN cancelled/completed rather than = 'scheduled' because generated
        # occurrences may carry lesson_status 'pending' or False.
        next_session = request.env['class.schedule.occurrence'].sudo().search([
            ('course_id', '=', course.id),
            ('lesson_status', 'not in', ['cancelled', 'completed']),
            ('start_datetime', '>=', datetime.utcnow()),
        ], order='start_datetime asc', limit=1)

        enrolled_students = course.enrollment_ids.filtered(lambda e: e.status == 'active')
        active_enrollments = course.enrollment_ids.filtered(lambda e: e.status == 'active')
        course_assignments = course.assignment_ids
        course_progress_reports = request.env['progress.report'].sudo().search([
            ('course_id', '=', course.id),
        ], order='report_date desc')

        vc_provider_labels = {'bbb': 'BigBlueButton', 'zoom': 'Zoom', 'google_meet': 'Google Meet'}

        # Pre-format datetimes in tutor's timezone
        next_session_dt_str = self._fmt_dt(next_session.start_datetime) if next_session else '—'
        week_lesson_times = {
            l.id: self._fmt_dt(l.start_datetime, '%a %d %b, %H:%M %Z')
            for l in this_week_lessons
        }

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
            'next_session_dt_str': next_session_dt_str,
            'week_lesson_times': week_lesson_times,
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

        today = self._tz_today()
        start_of_week = today - timedelta(days=today.weekday())

        # Date range params override the week preset
        from_date_str = kw.get('from_date', '').strip()
        to_date_str = kw.get('to_date', '').strip()
        using_custom_range = bool(from_date_str or to_date_str)

        if using_custom_range:
            week = 'custom'
            try:
                start_date = fields.Date.from_string(from_date_str) if from_date_str else today - timedelta(days=30)
            except (ValueError, TypeError):
                start_date = today - timedelta(days=30)
            try:
                end_date = fields.Date.from_string(to_date_str) if to_date_str else today + timedelta(days=90)
            except (ValueError, TypeError):
                end_date = today + timedelta(days=90)
        elif week == 'next':
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

        start_utc, end_utc = self._tz_date_bounds(start_date, end_date)
        domain = [
            ('tutor_id', '=', tutor.id),
            ('start_datetime', '>=', start_utc),
            ('start_datetime', '<=', end_utc),
        ]

        # Extra filters
        filter_student = kw.get('student_name', '').strip()
        filter_status = kw.get('status', '').strip()
        filter_attendance = kw.get('attendance', '').strip()

        if filter_student:
            domain.append(('attendance_ids.student_id.name', 'ilike', filter_student))
        if filter_status:
            domain.append(('lesson_status', '=', filter_status))
        if filter_attendance == 'marked':
            domain.append(('attendance_marked', '=', True))
        elif filter_attendance == 'pending':
            domain.append(('attendance_marked', '=', False))

        occurrences = request.env['class.schedule.occurrence'].sudo().search(domain, order='start_datetime asc')
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
            'filter_from_date': from_date_str,
            'filter_to_date': to_date_str,
            'filter_student': filter_student,
            'filter_status': filter_status,
            'filter_attendance': filter_attendance,
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

        today = self._tz_today()
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
        start_utc, end_utc = self._tz_date_bounds(start_date, end_date)

        occurrences = request.env['class.schedule.occurrence'].sudo().search([
            ('course_id', '=', course.id),
            ('tutor_id', '=', tutor.id),
            ('start_datetime', '>=', start_utc),
            ('start_datetime', '<=', end_utc),
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
        if occurrence.lesson_status == 'cancelled':
            return request.redirect(f'/my/tutor/courses/{occurrence.course_id.id}')

        enrolled = occurrence.course_id.enrollment_ids.filtered(lambda e: e.status == 'active')
        active_student_ids = set(enrolled.mapped('student_id').ids)
        existing_att = {att.student_id.id: att for att in occurrence.attendance_ids}

        # Include cancelled students only if attendance was already recorded for this occurrence
        cancelled_student_ids = set(existing_att.keys()) - active_student_ids
        all_student_ids = list(active_student_ids | cancelled_student_ids)
        all_students = request.env['student.profile'].sudo().browse(all_student_ids)

        valid_statuses = {'present', 'absent'}
        student_data = []
        for s in all_students:
            att = existing_att.get(s.id)
            student_data.append({
                'student': s,
                'status': att.status if att and att.status in valid_statuses else 'present',
                'remarks': att.remarks if att else '',
            })

        occurrence_dt_str = self._fmt_dt(occurrence.start_datetime, '%a, %d %b %Y %H:%M %Z')
        return request.render('tuition_management.portal_tutor_attendance', {
            'user': request.env.user,
            'is_tutor': True, 'is_student': False, 'is_parent': False,
            'tutor': tutor,
            'occurrence': occurrence,
            'occurrence_dt_str': occurrence_dt_str,
            'course': occurrence.course_id,
            'student_data': student_data,
            'back_url': f'/my/tutor/courses/{occurrence.course_id.id}',
            'page_name': 'tutor_attendance',
            'user_tz': self._get_user_tz(),
            'csrf_token': request.csrf_token(),
            'technical_issue_types': [
                ('tutor_issue', "Tutor's Issue"),
                ('student_issue', "Student's Issue"),
                ('platform_issue', 'Shiningace Platform Issue'),
            ],
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
        if lesson_status not in ('completed', 'scheduled'):
            lesson_status = 'completed'

        enrolled = occurrence.course_id.enrollment_ids.filtered(lambda e: e.status == 'active')
        students = enrolled.mapped('student_id')

        all_statuses = []
        for s in students:
            status = kw.get(f'status_{s.id}', 'present')
            if status not in ('present', 'absent'):
                status = 'present'
            all_statuses.append(status)
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
                'remarks': remarks,
            }
            if existing:
                existing.sudo().write(vals)
            else:
                request.env['attendance.record'].sudo().create(vals)

        # Determine lesson status automatically
        if students and all(s == 'absent' for s in all_statuses):
            new_lesson_status = 'under_review'
        elif occurrence.lesson_status == 'scheduled':
            new_lesson_status = 'completed'
        else:
            new_lesson_status = occurrence.lesson_status

        # Save academic traceability fields
        has_technical = kw.get('has_technical_issues') == 'on'
        occurrence.sudo().write({
            'lesson_status': new_lesson_status,
            'topic_covered': kw.get('topic_covered', '').strip() or False,
            'class_rating': kw.get('class_rating') or False,
            'next_steps': kw.get('next_steps', '').strip() or False,
            'homework': kw.get('homework', '').strip() or False,
            'tutor_comments': kw.get('tutor_comments', '').strip() or False,
            'has_technical_issues': has_technical,
            'technical_issue_type': kw.get('technical_issue_type') if has_technical else False,
            'technical_issue_details': kw.get('technical_issue_details', '').strip() if has_technical else False,
        })
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

        is_draft = kw.get('draft', '0') == '1'
        vals = {
            'name': kw.get('name', ''),
            'course_id': course.id,
            'assignment_type': kw.get('assignment_type', 'homework'),
            'due_date': kw.get('due_date') or False,
            'description': kw.get('description', ''),
            'status': 'draft' if is_draft else 'assigned',
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
        # Ensure access tokens exist so portal users can download via /web/content/{id}?access_token=...
        all_attachments = assignment.attachment_ids | assignment.submission_ids.mapped('attachment_ids')
        missing_token = all_attachments.filtered(lambda a: not a.access_token)
        if missing_token:
            missing_token.generate_access_token()
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

    @http.route(['/my/tutor/assignment/<int:assignment_id>/edit'], type='http',
                auth='user', website=True, methods=['POST'], csrf=True)
    def portal_tutor_assignment_edit(self, assignment_id, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        assignment = request.env['course.assignment'].sudo().browse(assignment_id)
        if not assignment.exists() or not self._tutor_has_course_access(tutor, assignment.course_id):
            return request.redirect('/my/tutor/courses')

        vals = {}
        if kw.get('name'):
            vals['name'] = kw['name'].strip()
        if kw.get('assignment_type'):
            vals['assignment_type'] = kw['assignment_type']
        if kw.get('due_date'):
            vals['due_date'] = kw['due_date']
        elif 'due_date' in kw:
            vals['due_date'] = False
        if kw.get('description') is not None:
            vals['description'] = kw['description']

        if vals:
            assignment.sudo().write(vals)

        uploaded_file = kw.get('attachment')
        if uploaded_file and hasattr(uploaded_file, 'filename') and uploaded_file.filename:
            att = request.env['ir.attachment'].sudo().create({
                'name': uploaded_file.filename,
                'datas': base64.b64encode(uploaded_file.read()),
                'res_model': 'course.assignment',
                'res_id': assignment.id,
                'type': 'binary',
            })
            assignment.sudo().write({'attachment_ids': [(4, att.id)]})

        return request.redirect(f'/my/tutor/assignment/{assignment_id}?saved=1')

    @http.route(['/my/tutor/assignment/<int:assignment_id>/delete'], type='http',
                auth='user', website=True, methods=['POST'], csrf=True)
    def portal_tutor_assignment_delete(self, assignment_id, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        assignment = request.env['course.assignment'].sudo().browse(assignment_id)
        if not assignment.exists() or not self._tutor_has_course_access(tutor, assignment.course_id):
            return request.redirect('/my/tutor/courses')
        course_id = assignment.course_id.id
        assignment.sudo().unlink()
        return request.redirect(f'/my/tutor/courses/{course_id}/assignments?deleted=1')

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
        feedback = kw.get('feedback', '')
        action = kw.get('action', 'complete')

        submission.sudo().write({
            'score': score,
            'feedback': feedback,
            'reviewed_by': tutor.id,
            'review_date': fields.Date.today(),
        })

        if action == 'rework':
            submission.sudo().write({'status': 'rework'})
            submission.assignment_id.sudo().write({'status': 'assigned'})
        else:
            submission.sudo().write({'status': 'completed'})
            submission.assignment_id.sudo().write({'status': 'completed'})

        return request.redirect(f'/my/tutor/assignment/{submission.assignment_id.id}?graded=1')

    @http.route(['/my/tutor/all-assignments'], type='http', auth='user', website=True)
    def portal_tutor_all_assignments(self, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        courses = request.env['course.master'].sudo().search([
            '|', ('tutor_id', '=', tutor.id), ('tutor_ids', 'in', tutor.id),
        ])
        domain = [('course_id', 'in', courses.ids)]
        filter_course_id = kw.get('course_id', '')
        filter_status = kw.get('status', '')
        filter_submission = kw.get('submission', '')
        filter_student = kw.get('student_name', '').strip()
        if filter_course_id:
            try:
                domain.append(('course_id', '=', int(filter_course_id)))
            except (ValueError, TypeError):
                pass
        if filter_status:
            domain.append(('status', '=', filter_status))
        if filter_submission == 'has':
            domain.append(('submission_ids', '!=', False))
        elif filter_submission == 'none':
            domain.append(('submission_ids', '=', False))
        if filter_student:
            domain.append(('submission_ids.student_id.name', 'ilike', filter_student))
        assignments = request.env['course.assignment'].sudo().search(domain, order='due_date desc')
        return request.render('tuition_management.portal_tutor_all_assignments', {
            'user': request.env.user,
            'is_tutor': True, 'is_student': False, 'is_parent': False,
            'tutor': tutor,
            'assignments': assignments,
            'tutor_courses': courses,
            'page_name': 'tutor_all_assignments',
            'page_title': 'All Assignments',
            'filter_course_id': filter_course_id,
            'filter_status': filter_status,
            'filter_submission': filter_submission,
            'filter_student': filter_student,
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
        domain = [('course_id', 'in', courses.ids)]
        filter_course_id = kw.get('course_id', '')
        filter_student = kw.get('student_name', '').strip()
        if filter_course_id:
            try:
                domain.append(('course_id', '=', int(filter_course_id)))
            except (ValueError, TypeError):
                pass
        if filter_student:
            domain.append(('student_id.name', 'ilike', filter_student))
        reports = request.env['progress.report'].sudo().search(domain, order='report_date desc')
        return request.render('tuition_management.portal_tutor_all_progress', {
            'user': request.env.user,
            'is_tutor': True, 'is_student': False, 'is_parent': False,
            'tutor': tutor,
            'reports': reports,
            'tutor_courses': courses,
            'page_name': 'tutor_progress',
            'page_title': 'Progress Reports',
            'filter_course_id': filter_course_id,
            'filter_student': filter_student,
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
            'overall_rating': kw.get('overall_rating', '') or False,
            'score': float(kw.get('score', 0) or 0),
            'max_score': float(kw.get('max_score', 100) or 100),
            'comments': kw.get('comments', ''),
            'strengths': kw.get('strengths', ''),
            'areas_for_improvement': kw.get('areas_for_improvement', ''),
            'homework_notes': kw.get('homework_notes', ''),
            'tutor_id': tutor.id,
        }
        request.env['progress.report'].sudo().create(vals)
        return request.redirect(f'/my/tutor/courses/{course_id}?progress_created=1')

    def _tutor_has_report_access(self, tutor, report):
        """True if the tutor created the report or teaches the course it belongs to."""
        if report.tutor_id and report.tutor_id == tutor:
            return True
        return self._tutor_has_course_access(tutor, report.course_id)

    @http.route(['/my/tutor/progress/<int:report_id>/edit'], type='http', auth='user', website=True)
    def portal_tutor_progress_edit(self, report_id, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        report = request.env['progress.report'].sudo().browse(report_id)
        if not report.exists() or not self._tutor_has_report_access(tutor, report):
            return request.redirect('/my/tutor/progress')
        course = report.course_id
        enrolled_students = course.enrollment_ids.filtered(lambda e: e.status == 'active')
        return request.render('tuition_management.portal_tutor_progress_edit', {
            'user': request.env.user,
            'is_tutor': True, 'is_student': False, 'is_parent': False,
            'tutor': tutor,
            'report': report,
            'course': course,
            'enrolled_students': enrolled_students,
            'page_name': 'tutor_progress',
            'page_title': 'Edit Progress Report',
            'csrf_token': request.csrf_token(),
        })

    @http.route(['/my/tutor/progress/<int:report_id>/update'], type='http',
                auth='user', website=True, methods=['POST'], csrf=True)
    def portal_tutor_progress_update(self, report_id, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        report = request.env['progress.report'].sudo().browse(report_id)
        if not report.exists() or not self._tutor_has_report_access(tutor, report):
            return request.redirect('/my/tutor/progress')
        vals = {
            'name': kw.get('name', report.name),
            'student_id': int(kw.get('student_id', report.student_id.id)),
            'report_date': kw.get('report_date') or fields.Date.today(),
            'overall_rating': kw.get('overall_rating', '') or False,
            'score': float(kw.get('score', 0) or 0),
            'max_score': float(kw.get('max_score', 100) or 100),
            'comments': kw.get('comments', ''),
            'strengths': kw.get('strengths', ''),
            'areas_for_improvement': kw.get('areas_for_improvement', ''),
            'homework_notes': kw.get('homework_notes', ''),
        }
        report.sudo().write(vals)
        return request.redirect('/my/tutor/progress?updated=1')

    @http.route(['/my/tutor/progress/<int:report_id>/delete'], type='http',
                auth='user', website=True, methods=['POST'], csrf=True)
    def portal_tutor_progress_delete(self, report_id, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        report = request.env['progress.report'].sudo().browse(report_id)
        if not report.exists() or not self._tutor_has_report_access(tutor, report):
            return request.redirect('/my/tutor/progress')
        report.sudo().unlink()
        return request.redirect('/my/tutor/progress?deleted=1')

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
