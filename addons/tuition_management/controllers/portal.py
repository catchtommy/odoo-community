# -*- coding: utf-8 -*-
import pytz
from odoo import http, fields
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal
from datetime import timedelta

from .portal_mixin import PortalMixin


class TuitionPortal(CustomerPortal, PortalMixin):
    """Core portal: home counters, dashboard routing, profile, logout."""

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        partner = request.env.user.partner_id

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

    # ──────────────────────────────────────────────
    # DASHBOARD / HOME
    # ──────────────────────────────────────────────

    @http.route(['/my', '/my/home', '/my/dashboard'], type='http', auth='user', website=True)
    def home(self, **kw):
        partner = request.env.user.partner_id
        student = self._get_student()
        tutor = self._get_tutor()
        parent = self._get_parent()

        values = {
            'user': request.env.user,
            'is_student': bool(student),
            'is_tutor': bool(tutor),
            'is_parent': bool(parent),
        }

        today = self._tz_today()

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
            # Next upcoming session for the student dashboard card
            next_session = request.env['class.schedule.occurrence'].sudo().search([
                ('course_id', 'in', course_ids),
                ('lesson_status', '=', 'scheduled'),
                ('start_datetime', '>=', fields.Datetime.now()),
            ], order='start_datetime asc', limit=1)
            next_session_live = bool(next_session and next_session.virtual_meeting_id
                                     and next_session.virtual_meeting_id.state == 'ready')
            next_session_dt_str = (
                self._fmt_dt(next_session.start_datetime, '%a %d %b %Y, %H:%M %Z')
                if next_session else '—'
            )
            start_of_week = today - timedelta(days=today.weekday())
            end_of_week = start_of_week + timedelta(days=6)
            week_start_utc, week_end_utc = self._tz_date_bounds(start_of_week, end_of_week)
            week_lesson_count = request.env['class.schedule.occurrence'].sudo().search_count([
                ('course_id', 'in', course_ids),
                ('start_datetime', '>=', week_start_utc),
                ('start_datetime', '<=', week_end_utc),
            ])
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
                'next_session': next_session,
                'next_session_live': next_session_live,
                'next_session_dt_str': next_session_dt_str,
                'week_lesson_count': week_lesson_count,
            })
            return request.render('tuition_management.portal_student_dashboard', values)

        if tutor:
            courses = request.env['course.master'].sudo().search([('tutor_id', '=', tutor.id)])
            today_start_utc, today_end_utc = self._tz_date_bounds(today, today)
            today_sessions = request.env['class.schedule.occurrence'].sudo().search_count([
                ('tutor_id', '=', tutor.id),
                ('start_datetime', '>=', today_start_utc),
                ('start_datetime', '<=', today_end_utc),
            ])
            student_ids = request.env['course.enrollment'].sudo().search([
                ('course_id', 'in', courses.ids), ('status', '=', 'active')
            ]).mapped('student_id').ids
            start_of_week = today - timedelta(days=today.weekday())
            end_of_week = start_of_week + timedelta(days=6)
            week_start_utc, week_end_utc = self._tz_date_bounds(start_of_week, end_of_week)
            this_week_lesson_count = request.env['class.schedule.occurrence'].sudo().search_count([
                ('tutor_id', '=', tutor.id),
                ('start_datetime', '>=', week_start_utc),
                ('start_datetime', '<=', week_end_utc),
            ])
            _, next_week_end_utc = self._tz_date_bounds(today + timedelta(days=7), today + timedelta(days=7))
            upcoming_lessons = request.env['class.schedule.occurrence'].sudo().search([
                ('tutor_id', '=', tutor.id),
                ('start_datetime', '>=', fields.Datetime.now()),
                ('start_datetime', '<=', next_week_end_utc),
            ], order='start_datetime asc', limit=10)
            # Pre-format lesson times in the tutor's timezone for the template
            lesson_times = {}
            for lesson in upcoming_lessons:
                lesson_times[lesson.id] = self._fmt_dt(lesson.start_datetime, '%a %d %b %Y, %H:%M %Z')
            values.update({
                'tutor': tutor,
                'tutor_course_count': len(courses),
                'today_sessions': today_sessions,
                'total_students': len(set(student_ids)),
                'tutor_courses': courses,
                'this_week_lesson_count': this_week_lesson_count,
                'upcoming_lessons': upcoming_lessons,
                'lesson_times': lesson_times,
                'user_tz': self._get_user_tz(),
            })
            return request.render('tuition_management.portal_tutor_home_dashboard', values)

        if parent:
            child_data = []
            total_enrollments = 0
            all_course_ids = []
            for child in parent.student_ids:
                enrollments = request.env['course.enrollment'].sudo().search([
                    ('student_id', '=', child.id), ('status', '=', 'active')])
                total_enrollments += len(enrollments)
                all_course_ids += enrollments.mapped('course_id').ids
                child_data.append({'student': child, 'enrollments': enrollments})
            child_partners = parent.student_ids.mapped('partner_id').ids
            all_partners = list(set([parent.partner_id.id] + child_partners)) if parent.partner_id else child_partners
            invoices = request.env['account.move'].sudo().search([
                ('partner_id', 'in', all_partners),
                ('move_type', '=', 'out_invoice'),
                ('payment_state', '!=', 'paid'),
                ('state', '=', 'posted'),
            ])
            # Next upcoming session across all children — informational only, no join option for parents.
            next_session = request.env['class.schedule.occurrence'].sudo().search([
                ('course_id', 'in', all_course_ids),
                ('lesson_status', '=', 'scheduled'),
                ('start_datetime', '>=', fields.Datetime.now()),
            ], order='start_datetime asc', limit=1)
            next_session_dt_str = (
                self._fmt_dt(next_session.start_datetime, '%a %d %b %Y, %H:%M %Z')
                if next_session else '—'
            )
            next_session_student = None
            if next_session:
                enr = request.env['course.enrollment'].sudo().search([
                    ('course_id', '=', next_session.course_id.id),
                    ('student_id', 'in', parent.student_ids.ids),
                    ('status', '=', 'active'),
                ], limit=1)
                next_session_student = enr.student_id if enr else None
            values.update({
                'child_count': len(parent.student_ids),
                'child_data': child_data,
                'total_enrollments': total_enrollments,
                'unpaid_invoices': len(invoices),
                'amount_due': sum(invoices.mapped('amount_residual')),
                'next_session': next_session,
                'next_session_dt_str': next_session_dt_str,
                'next_session_student': next_session_student,
            })
            return request.render('tuition_management.portal_parent_dashboard', values)

        return super().home(**kw)

    # ──────────────────────────────────────────────
    # LOGOUT
    # ──────────────────────────────────────────────

    @http.route(['/my/logout'], type='http', auth='public', website=True)
    def portal_logout(self, **kw):
        request.session.logout(keep_db=True)
        return request.redirect('/web/login')

    # ──────────────────────────────────────────────
    # PROFILE
    # ──────────────────────────────────────────────

    @http.route(['/my/profile'], type='http', auth='user', website=True)
    def portal_my_profile(self, **kw):
        user = request.env.user
        partner = user.partner_id
        student = self._get_student()
        tutor = self._get_tutor()
        parent = self._get_parent()
        countries = request.env['res.country'].sudo().search([], order='name asc')
        return request.render('tuition_management.portal_user_profile', {
            'user': user,
            'is_student': bool(student),
            'is_tutor': bool(tutor),
            'is_parent': bool(parent),
            'partner': partner,
            'countries': countries,
            'success': kw.get('success'),
            'error': kw.get('error'),
            'page_name': 'settings',
            'csrf_token': request.csrf_token(),
        })

    @http.route(['/my/profile/save'], type='http', auth='user', website=True,
                methods=['POST'], csrf=True)
    def portal_profile_save(self, **kw):
        user = request.env.user
        partner = user.partner_id

        email    = (kw.get('email')    or '').strip()
        phone    = (kw.get('phone')    or '').strip()
        street   = (kw.get('street')   or '').strip()
        street2  = (kw.get('street2')  or '').strip()
        city     = (kw.get('city')     or '').strip()
        zip_code = (kw.get('zip')      or '').strip()
        new_password     = (kw.get('new_password')     or '').strip()
        confirm_password = (kw.get('confirm_password') or '').strip()

        # Build partner update dict from submitted fields
        partner_vals = {}
        if email:
            partner_vals['email'] = email
        if phone:
            partner_vals['phone'] = phone
        partner_vals['street']  = street
        partner_vals['street2'] = street2
        partner_vals['city']    = city
        partner_vals['zip']     = zip_code
        country_id = kw.get('country_id')
        if country_id:
            try:
                partner_vals['country_id'] = int(country_id)
            except (ValueError, TypeError):
                pass
        if partner_vals:
            partner.sudo().write(partner_vals)

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