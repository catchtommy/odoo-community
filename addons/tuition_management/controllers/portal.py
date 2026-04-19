# -*- coding: utf-8 -*-
import pytz
from odoo import http, fields
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal
from datetime import timedelta, datetime

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
            courses = request.env['course.master'].sudo().search([('tutor_id', '=', tutor.id)])
            today_sessions = request.env['class.schedule.occurrence'].sudo().search_count([
                ('tutor_id', '=', tutor.id),
                ('start_datetime', '>=', fields.Datetime.now().replace(hour=0, minute=0, second=0)),
                ('start_datetime', '<=', fields.Datetime.now().replace(hour=23, minute=59, second=59)),
            ])
            student_ids = request.env['course.enrollment'].sudo().search([
                ('course_id', 'in', courses.ids), ('status', '=', 'active')
            ]).mapped('student_id').ids
            start_of_week = today - timedelta(days=today.weekday())
            end_of_week = start_of_week + timedelta(days=6)
            this_week_lesson_count = request.env['class.schedule.occurrence'].sudo().search_count([
                ('tutor_id', '=', tutor.id),
                ('start_datetime', '>=', datetime.combine(start_of_week, datetime.min.time())),
                ('start_datetime', '<=', datetime.combine(end_of_week, datetime.max.time())),
            ])
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
        profile = student or tutor or parent
        role = 'Student' if student else ('Tutor' if tutor else ('Parent' if parent else 'User'))
        back_url = '/my/tutor/courses' if tutor else ('/my/courses' if student else ('/my/parent/children' if parent else '/my'))
        return request.render('tuition_management.portal_user_profile', {
            'user': user,
            'is_student': bool(student),
            'is_tutor': bool(tutor),
            'is_parent': bool(parent),
            'partner': partner,
            'profile': profile,
            'role': role,
            'success': kw.get('success'),
            'error': kw.get('error'),
            'page_name': 'profile',
            'back_url': back_url,
            'csrf_token': request.csrf_token(),
            'timezones': sorted(pytz.all_timezones),
            'current_timezone': profile.timezone if profile and hasattr(profile, 'timezone') and profile.timezone else 'UTC',
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

        if profile:
            write_vals = {'name': name}
            if email:
                write_vals['email'] = email
            if hasattr(profile, 'phone') and phone:
                write_vals['phone'] = phone
            tz = (kw.get('timezone') or '').strip()
            if tz and hasattr(profile, 'timezone'):
                write_vals['timezone'] = tz
            profile.sudo().write(write_vals)

        partner_vals = {'name': name}
        if email:
            partner_vals['email'] = email
        if phone:
            partner_vals['phone'] = phone
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