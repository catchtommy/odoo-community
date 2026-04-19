# -*- coding: utf-8 -*-
from odoo import http, fields
from odoo.http import request
from datetime import timedelta, datetime

from .portal_mixin import PortalMixin


class ParentPortal(http.Controller, PortalMixin):
    """Parent-specific portal routes."""

    # ──────────────────────────────────────────────
    # CHILDREN
    # ──────────────────────────────────────────────

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
            'is_parent': True, 'is_student': False, 'is_tutor': False,
            'parent': parent,
            'child_data': child_data,
            'child_count': len(children),
            'total_enrollments': total_enrollments,
            'unpaid_invoices': len(invoices),
            'amount_due': sum(invoices.mapped('amount_residual')),
            'page_name': 'parent_children',
            'page_title': 'My Children',
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
            'is_parent': True, 'is_student': False, 'is_tutor': False,
            'child': child,
            'enrollments': enrollments,
            'progress_reports': progress_reports,
            'attendance_records': attendance_records,
            'attendance_rate': attendance_rate,
            'page_name': 'parent_children',
            'page_title': child.name,
        })

    # ──────────────────────────────────────────────
    # SCHEDULE
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
                local_dt = self._to_user_tz(occ.start_datetime)
                date_str = local_dt.strftime('%a, %d %b %Y') if local_dt else ''
                time_str = local_dt.strftime('%I:%M %p') if local_dt else ''
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
            'is_parent': True, 'is_student': False, 'is_tutor': False,
            'parent': parent,
            'occ_data': occ_data,
            'week_offset': week_offset,
            'week_label': week_label,
            'user_tz': self._get_user_tz(),
            'page_name': 'parent_schedule',
            'page_title': 'Schedules',
        })

    # ──────────────────────────────────────────────
    # PROGRESS
    # ──────────────────────────────────────────────

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
            'is_parent': True, 'is_student': False, 'is_tutor': False,
            'parent': parent,
            'child_data': child_data,
            'page_name': 'parent_progress',
            'page_title': 'Progress',
        })

    # ──────────────────────────────────────────────
    # INVOICES
    # ──────────────────────────────────────────────

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

    # ──────────────────────────────────────────────
    # PROGRESS REPORT DETAIL
    # ──────────────────────────────────────────────

    @http.route(['/my/progress-report/<int:report_id>'], type='http', auth='user', website=True)
    def portal_progress_report_detail(self, report_id, **kw):
        parent = self._get_parent()
        student = self._get_student()
        if not parent and not student:
            return request.redirect('/my')

        report = request.env['progress.report'].sudo().browse(report_id)
        if not report.exists():
            return request.redirect('/my')

        if parent:
            allowed_student_ids = parent.student_ids.ids if parent.student_ids else []
        else:
            allowed_student_ids = [student.id] if student else []

        if report.student_id.id not in allowed_student_ids:
            return request.redirect('/my')

        return request.render('tuition_management.portal_progress_report_detail', {
            'user': request.env.user,
            'is_parent': bool(parent),
            'is_student': bool(student),
            'is_tutor': False,
            'report': report,
            'page_name': 'parent_progress',
        })
