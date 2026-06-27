# -*- coding: utf-8 -*-
from odoo import http, fields
from odoo.http import request
from datetime import timedelta, datetime
import base64

from .portal_mixin import PortalMixin


class StudentPortal(http.Controller, PortalMixin):
    """Student-specific portal routes."""

    # ──────────────────────────────────────────────
    # SCHEDULE
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

        try:
            week_offset = int(kw.get('week_offset', 0))
        except (ValueError, TypeError):
            week_offset = 0
        start_utc, end_utc, start_of_week, end_of_week, week_label = self._tz_week_bounds(week_offset)

        occurrences = request.env['class.schedule.occurrence'].sudo().search([
            ('course_id', 'in', course_ids),
            ('start_datetime', '>=', start_utc),
            ('start_datetime', '<=', end_utc),
        ], order='start_datetime asc')

        attendance = request.env['attendance.record'].sudo().search([
            ('student_id', '=', student.id),
            ('class_schedule_occurrence_id', 'in', occurrences.ids),
        ])
        attendance_map = {a.class_schedule_occurrence_id.id: a.status for a in attendance}

        occ_data = []
        for occ in occurrences:
            try:
                local_dt = self._to_user_tz(occ.start_datetime)
                date_str = local_dt.strftime('%a, %d %b %Y') if local_dt else ''
                time_str = local_dt.strftime('%I:%M %p') if local_dt else ''
            except Exception:
                date_str = str(occ.start_datetime) if occ.start_datetime else ''
                time_str = ''
            # Determine session live-state for student waiting-room logic
            # One room per course — check course-level meeting, not occurrence-level
            meeting = occ.virtual_meeting_id
            if not (meeting and meeting.state == 'ready'):
                provider_code = occ.virtual_provider or occ.course_id.virtual_provider_default or 'bbb'
                meeting = request.env['virtual.classroom.meeting'].sudo().search([
                    ('course_id', '=', occ.course_id.id),
                    ('provider', '=', provider_code),
                    ('state', '=', 'ready'),
                ], limit=1)
            meeting_live = bool(meeting and meeting.state == 'ready')
            provider = occ.virtual_provider  # computed from course
            occ_data.append({
                'occ': occ,
                'date_str': date_str,
                'time_str': time_str,
                'att_status': attendance_map.get(occ.id, ''),
                'meeting_live': meeting_live,
                'provider': provider,
            })

        return request.render('tuition_management.portal_student_schedule', {
            'user': request.env.user,
            'is_student': True, 'is_tutor': False, 'is_parent': False,
            'student': student,
            'occ_data': occ_data,
            'week_offset': week_offset,
            'week_label': week_label,
            'user_tz': self._get_user_tz(),
            'page_name': 'student_schedule',
            'page_title': 'My Schedule',
            'vc_error': kw.get('vc_error'),
        })

    # ──────────────────────────────────────────────
    # COURSES
    # ──────────────────────────────────────────────

    @http.route(['/my/courses'], type='http', auth='user', website=True)
    def portal_my_courses(self, **kw):
        student = self._get_student()
        if not student:
            return request.redirect('/my')
        enrollments = request.env['course.enrollment'].sudo().search([
            ('student_id', '=', student.id), ('status', '=', 'active'),
        ])
        try:
            return request.render('tuition_management.portal_student_courses', {
                'user': request.env.user,
                'is_student': True, 'is_tutor': False, 'is_parent': False,
                'student': student,
                'enrollments': enrollments,
                'page_name': 'my_courses',
            })
        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.error("TEMPLATE ERROR /my/courses: %s", e)
            raise

    @http.route(['/my/courses/<int:course_id>'], type='http', auth='user', website=True)
    def portal_course_detail(self, course_id, **kw):
        partner = request.env.user.partner_id
        student = request.env['student.profile'].sudo().search([('partner_id', '=', partner.id)], limit=1)
        parent = request.env['parent.profile'].sudo().search([('partner_id', '=', partner.id)], limit=1)

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
            return request.redirect('/my')

        course = enrollment.course_id
        assignments = request.env['course.assignment'].sudo().search([
            ('course_id', '=', course.id)
        ])

        try:
            week_offset = int(kw.get('week_offset', 0))
        except (ValueError, TypeError):
            week_offset = 0
        start_utc, end_utc, start_of_week, end_of_week, week_label = self._tz_week_bounds(week_offset)

        occurrences = request.env['class.schedule.occurrence'].sudo().search([
            ('course_id', '=', course.id),
            ('start_datetime', '>=', start_utc),
            ('start_datetime', '<=', end_utc),
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

        # Next upcoming session for the Join button on course detail
        from datetime import datetime as _dt
        next_session = request.env['class.schedule.occurrence'].sudo().search([
            ('course_id', '=', course.id),
            ('lesson_status', '=', 'scheduled'),
            ('start_datetime', '>=', _dt.utcnow()),
        ], order='start_datetime asc', limit=1)
        provider_code = course.virtual_provider_default or 'bbb'
        course_meeting_live = False
        if next_session:
            live_meeting = request.env['virtual.classroom.meeting'].sudo().search([
                ('course_id', '=', course.id),
                ('provider', '=', provider_code),
                ('state', '=', 'ready'),
            ], limit=1)
            course_meeting_live = bool(live_meeting)

        return request.render('tuition_management.portal_course_detail', {
            'user': request.env.user,
            'is_student': bool(student), 'is_parent': bool(parent), 'is_tutor': False,
            'enrollment': enrollment,
            'course': course,
            'assignments': assignments,
            'occurrences': occurrences,
            'attendance_map': attendance_map,
            'progress_reports': progress_reports,
            'week_offset': week_offset,
            'week_label': week_label,
            'user_tz': self._get_user_tz(),
            'page_name': 'my_courses',
            'page_title': course.name,
            'next_session': next_session,
            'course_meeting_live': course_meeting_live,
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

        today = self._tz_today()
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
        start_utc, end_utc = self._tz_date_bounds(start_date, end_date)

        occurrences = request.env['class.schedule.occurrence'].sudo().search([
            ('course_id', '=', course.id),
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

        return request.render('tuition_management.portal_student_lessons', {
            'user': request.env.user,
            'is_student': True, 'is_tutor': False, 'is_parent': False,
            'course': course,
            'student': student,
            'occurrences': occurrences,
            'occ_data': occ_data,
            'current_week': week,
            'user_tz': self._get_user_tz(),
            'page_name': 'course_lessons',
            'vc_error': kw.get('vc_error'),
        })

    # ──────────────────────────────────────────────
    # ASSIGNMENTS
    # ──────────────────────────────────────────────

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
        submission_map = {}
        for asgn in assignments:
            sub = asgn.submission_ids.filtered(lambda s: s.student_id.id == student.id)
            submission_map[asgn.id] = sub
        return request.render('tuition_management.portal_student_assignments', {
            'user': request.env.user,
            'is_student': True, 'is_tutor': False, 'is_parent': False,
            'assignments': assignments,
            'submission_map': submission_map,
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
            'is_student': True, 'is_tutor': False, 'is_parent': False,
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
            'notes': kw.get('student_note', ''),
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
            submission = request.env['assignment.submission'].sudo().create(vals)
        # Move assignment to pending_review when student submits
        assignment.sudo().write({'status': 'pending_review'})
        return request.redirect(f'/my/assignments/{assignment_id}?submitted=1')
