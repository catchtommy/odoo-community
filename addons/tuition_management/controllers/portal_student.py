# -*- coding: utf-8 -*-
from odoo import http, fields
from odoo.http import request
from datetime import timedelta, datetime, date
from calendar import monthrange
import base64
import json
import re

from .portal_mixin import PortalMixin


class StudentPortal(http.Controller, PortalMixin):
    """Student-specific portal routes."""

    # ──────────────────────────────────────────────
    # SCHEDULE
    # ──────────────────────────────────────────────

    @http.route(['/my/student/schedule'], type='http', auth='user', website=True)
    def portal_student_schedule(self, week='this', view_mode='week', **kw):
        student = self._get_student()
        if not student:
            return request.redirect('/my')
        enrollments = request.env['course.enrollment'].sudo().search([
            ('student_id', '=', student.id), ('status', '=', 'active'),
        ])
        course_ids = enrollments.mapped('course_id').ids

        if view_mode == 'month':
            try:
                month_offset = int(kw.get('month_offset', 0))
            except (ValueError, TypeError):
                month_offset = 0
            today = self._tz_today()
            raw_month = today.month + month_offset
            target_year = today.year + (raw_month - 1) // 12
            target_month = ((raw_month - 1) % 12) + 1
            first_day = date(target_year, target_month, 1)
            last_day = date(target_year, target_month, monthrange(target_year, target_month)[1])
            start_utc, end_utc = self._tz_date_bounds(first_day, last_day)
            period_label = first_day.strftime('%B %Y')
            week_offset = 0
        else:
            view_mode = 'week'
            month_offset = 0
            try:
                week_offset = int(kw.get('week_offset', 0))
            except (ValueError, TypeError):
                week_offset = 0
            start_utc, end_utc, start_of_week, end_of_week, week_label = self._tz_week_bounds(week_offset)
            period_label = week_label

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
            'month_offset': month_offset,
            'view_mode': view_mode,
            'period_label': period_label,
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
    def portal_my_assignments(self, status_filter='all', **kw):
        student = self._get_student()
        if not student:
            return request.redirect('/my')
        course_ids = request.env['course.enrollment'].sudo().search([
            ('student_id', '=', student.id), ('status', '=', 'active'),
        ]).mapped('course_id').ids
        all_assignments = request.env['course.assignment'].sudo().search([
            ('course_id', 'in', course_ids),
            ('status', 'in', ['assigned', 'pending_review', 'completed']),
        ], order='create_date desc')
        submission_map = {}
        for asgn in all_assignments:
            sub = asgn.submission_ids.filtered(lambda s: s.student_id.id == student.id)
            submission_map[asgn.id] = sub[:1]

        def _display_status(asgn):
            sub = submission_map.get(asgn.id)
            if sub and sub.status == 'rework':
                return 'rework'
            if sub and sub.status == 'completed':
                return 'completed'
            if sub and sub.status == 'pending_review':
                return 'under_review'
            if sub:
                return 'submitted'
            return 'pending'

        if status_filter == 'pending':
            assignments = all_assignments.filtered(lambda a: _display_status(a) in ('pending', 'rework'))
        elif status_filter and status_filter != 'all':
            assignments = all_assignments.filtered(lambda a: _display_status(a) == status_filter)
        else:
            assignments = all_assignments

        status_counts = {'pending': 0, 'under_review': 0, 'submitted': 0, 'completed': 0}
        for asgn in all_assignments:
            disp = _display_status(asgn)
            if disp in ('pending', 'rework'):
                status_counts['pending'] += 1
            elif disp == 'under_review':
                status_counts['under_review'] += 1
            elif disp == 'submitted':
                status_counts['submitted'] += 1
            elif disp == 'completed':
                status_counts['completed'] += 1

        return request.render('tuition_management.portal_student_assignments', {
            'user': request.env.user,
            'is_student': True, 'is_tutor': False, 'is_parent': False,
            'assignments': assignments,
            'submission_map': submission_map,
            'student': student,
            'page_name': 'assignments',
            'status_filter': status_filter,
            'status_counts': status_counts,
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
        # Ensure access tokens exist so portal users can download via /web/content/{id}?access_token=...
        all_attachments = assignment.attachment_ids | (submission.attachment_ids if submission else request.env['ir.attachment'])
        missing_token = all_attachments.filtered(lambda a: not a.access_token)
        if missing_token:
            missing_token.generate_access_token()

        all_atts = assignment.attachment_ids | (submission.attachment_ids if submission else request.env['ir.attachment'])
        annotatable_atts = all_atts.filtered(
            lambda a: self._resolve_mimetype(a) == 'application/pdf'
                      or self._resolve_mimetype(a).startswith('image/')
        )
        return request.render('tuition_management.portal_student_assignment_detail', {
            'user': request.env.user,
            'is_student': True, 'is_tutor': False, 'is_parent': False,
            'assignment': assignment,
            'submission': submission,
            'student': student,
            'page_name': 'assignment_detail',
            'csrf_token': request.csrf_token(),
            'annotatable_atts': annotatable_atts,
        })

    # ──────────────────────────────────────────────
    # HELPERS
    # ──────────────────────────────────────────────

    _IMG_EXTS = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg'}

    def _resolve_mimetype(self, att):
        mt = att.mimetype or ''
        if not mt or mt == 'application/octet-stream':
            ext = (att.name or '').rsplit('.', 1)[-1].lower()
            if ext == 'pdf':
                mt = 'application/pdf'
            elif ext in self._IMG_EXTS:
                mt = 'image/' + ext
        return mt

    def _annotatable_attachment_ids(self, attachments):
        ids = set()
        for att in attachments:
            mt = self._resolve_mimetype(att)
            if mt == 'application/pdf' or mt.startswith('image/'):
                ids.add(att.id)
        return ids

    @http.route(['/my/assignments/<int:assignment_id>/annotate/<int:attachment_id>'],
                type='http', auth='user', website=True)
    def portal_annotate_assignment(self, assignment_id, attachment_id, **kw):
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
        att = request.env['ir.attachment'].sudo().browse(attachment_id)
        if not att.exists():
            return request.redirect('/my/assignments/%d' % assignment_id)
        if not att.access_token:
            att.generate_access_token()
        mt = self._resolve_mimetype(att)
        att_json = json.dumps([{
            'id': att.id,
            'name': att.name,
            'mimetype': mt,
            'access_token': att.access_token or '',
        }])
        submission = request.env['assignment.submission'].sudo().search([
            ('assignment_id', '=', assignment.id), ('student_id', '=', student.id),
        ], limit=1)
        already_submitted = bool(submission and att in submission.submitted_resource_ids)
        return request.render('tuition_management.portal_student_annotate', {
            'user': request.env.user,
            'is_student': True, 'is_tutor': False, 'is_parent': False,
            'assignment': assignment,
            'attachment': att,
            'annotation_attachments_json': att_json,
            'student': student,
            'page_name': 'assignment_detail',
            'csrf_token': request.csrf_token(),
            'already_submitted': already_submitted,
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
        source_attachment_id = kw.get('source_attachment_id')
        resource = request.env['ir.attachment']
        if source_attachment_id and source_attachment_id.isdigit():
            candidate = request.env['ir.attachment'].sudo().browse(int(source_attachment_id))
            if candidate.exists() and candidate in assignment.attachment_ids:
                resource = candidate
                vals['submitted_resource_ids'] = [(4, resource.id)]

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
        annotated_image = kw.get('annotated_image', '')
        if annotated_image and annotated_image.startswith('data:'):
            header, b64data = annotated_image.split(',', 1)
            m = re.match(r'data:(application/pdf|image/(\w+))', header)
            if m:
                is_pdf = m.group(1) == 'application/pdf'
                ext = 'pdf' if is_pdf else m.group(2)
                if resource:
                    base_name = resource.name.rsplit('.', 1)[0] if resource.name else resource.name
                    ann_name = '%s.%s' % (base_name, ext)
                else:
                    ann_name = '%s.%s' % (assignment.name, ext)
                ann_vals = {
                    'name': ann_name,
                    'datas': b64data.encode('ascii'),
                    'res_model': 'assignment.submission',
                    'type': 'binary',
                }
                if is_pdf:
                    ann_vals['mimetype'] = 'application/pdf'
                ann_att = request.env['ir.attachment'].sudo().create(ann_vals)
                attachment_ids.append(ann_att.id)

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

    @http.route(['/my/assignments/<int:assignment_id>/submission/delete-file/<int:att_id>'],
                type='http', auth='user', website=True, methods=['POST'])
    def portal_submission_delete_file(self, assignment_id, att_id, **kw):
        student = self._get_student()
        if not student:
            return request.redirect('/my/assignments')
        assignment = request.env['course.assignment'].sudo().browse(assignment_id)
        if not assignment.exists():
            return request.redirect('/my/assignments')
        submission = request.env['assignment.submission'].sudo().search([
            ('assignment_id', '=', assignment.id), ('student_id', '=', student.id),
        ], limit=1)
        if submission:
            attachment = request.env['ir.attachment'].sudo().browse(att_id)
            if attachment.exists() and attachment in submission.attachment_ids:
                attachment.unlink()
        return request.redirect(f'/my/assignments/{assignment_id}')
