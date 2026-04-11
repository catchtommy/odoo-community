# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from datetime import date, datetime, timedelta


class TuitionDashboardController(http.Controller):

    @http.route('/tuition/dashboard/data', type='json', auth='user')
    def dashboard_data(self):
        """Return dashboard statistics."""
        today = date.today()
        tomorrow = today + timedelta(days=1)

        courses = request.env['course.master'].search_count([])
        active_courses = request.env['course.master'].search_count([('status', '=', 'active')])
        enrollments = request.env['course.enrollment'].search_count([])
        active_enrollments = request.env['course.enrollment'].search_count([('status', '=', 'active')])
        enquiries = request.env['enquiry'].search_count([])
        new_enquiries = request.env['enquiry'].search_count([('is_enrolled', '=', False)])
        demo_sessions = request.env['demo.session'].search_count([])
        upcoming_demos = request.env['demo.session'].search_count([
            ('status', '=', 'scheduled'),
            ('scheduled_datetime', '>=', datetime.combine(today, datetime.min.time())),
        ])
        today_schedules = request.env['class.schedule.occurrence'].search_count([
            ('start_datetime', '>=', datetime.combine(today, datetime.min.time())),
            ('start_datetime', '<', datetime.combine(tomorrow, datetime.min.time())),
        ])
        students = request.env['student.profile'].search_count([])
        tutors = request.env['tutor.profile'].search_count([])

        return {
            'courses': courses,
            'active_courses': active_courses,
            'enrollments': enrollments,
            'active_enrollments': active_enrollments,
            'enquiries': enquiries,
            'new_enquiries': new_enquiries,
            'demo_sessions': demo_sessions,
            'upcoming_demos': upcoming_demos,
            'today_schedules': today_schedules,
            'students': students,
            'tutors': tutors,
        }
