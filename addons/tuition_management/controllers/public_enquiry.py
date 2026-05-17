# -*- coding: utf-8 -*-
import json
from odoo import http
from odoo.http import request


class PublicEnquiryController(http.Controller):

    def _get_enquiry_render_values(self, extra=None):
        grades = request.env['grade.master'].sudo().search([], order='name')
        categories = request.env['subject.category'].sudo().search([], order='name')
        subjects = request.env['subject.master'].sudo().search([], order='name')
        # Build a {category_id: [{id, name}, ...]} map for JS filtering of subjects
        subjects_by_category = {}
        for s in subjects:
            cat_id = str(s.category_id.id) if s.category_id else '0'
            subjects_by_category.setdefault(cat_id, []).append({'id': s.id, 'name': s.name})
        # Build a {category_id: [{id, name}, ...]} map for JS filtering of grades
        grades_by_category = {}
        for g in grades:
            for cat in g.category_ids:
                grades_by_category.setdefault(str(cat.id), []).append({'id': g.id, 'name': g.name})
            if not g.category_ids:
                grades_by_category.setdefault('0', []).append({'id': g.id, 'name': g.name})
        values = {
            'grades': grades,
            'categories': categories,
            'subjects': subjects,
            'subjects_by_category_json': json.dumps(subjects_by_category),
            'grades_by_category_json': json.dumps(grades_by_category),
            'success': False,
            'error': False,
            'form_data': {},
            'csrf_token': request.csrf_token(),
        }
        if extra:
            values.update(extra)
        return values

    @http.route('/enquiry', type='http', auth='public', website=True, sitemap=True)
    def enquiry_form(self, **kw):
        return request.render('tuition_management.public_enquiry_form', self._get_enquiry_render_values())

    @http.route('/enquiry/submit', type='http', auth='public', website=True, methods=['POST'], csrf=True)
    def enquiry_submit(self, **post):
        base_values = self._get_enquiry_render_values()

        form_data = {
            'parent_name': post.get('parent_name', '').strip(),
            'email': post.get('email', '').strip(),
            'country_code': post.get('country_code', '').strip(),
            'phone': post.get('phone', '').strip(),
            'student_name': post.get('student_name', '').strip(),
            'student_age': post.get('student_age', '').strip(),
            'grade_id': post.get('grade_id', ''),
            'category_id': post.get('category_id', ''),
            'subject_id': post.get('subject_id', ''),
            'notes': post.get('notes', '').strip(),
        }

        error = None

        # Validate required fields
        if not form_data['parent_name']:
            error = 'Parent / Guardian name is required.'
        elif not form_data['student_name']:
            error = 'Student name is required.'
        elif not form_data['grade_id']:
            error = 'Please select a grade.'
        elif not form_data['subject_id']:
            error = 'Please select a subject.'
        elif not form_data['email'] and not form_data['phone']:
            error = 'Please provide either an email address or a phone number.'

        if error:
            return request.render('tuition_management.public_enquiry_form', dict(base_values, error=error, form_data=form_data))

        # Find the first stage (New)
        first_stage = request.env['enquiry.stage'].sudo().search([], order='sequence asc', limit=1)

        # Create the enquiry
        vals = {
            'name': form_data['parent_name'],
            'email': form_data['email'] or False,
            'country_code': form_data['country_code'] or False,
            'phone': form_data['phone'] or False,
            'student_name': form_data['student_name'],
            'student_age': int(form_data['student_age']) if form_data.get('student_age') else 0,
            'grade_id': int(form_data['grade_id']),
            'subject_id': int(form_data['subject_id']),
            'notes': form_data['notes'] or False,
        }
        if form_data['category_id']:
            vals['category_id'] = int(form_data['category_id'])
        if first_stage:
            vals['stage_id'] = first_stage.id

        try:
            request.env['enquiry'].sudo().create(vals)
        except Exception:
            return request.render('tuition_management.public_enquiry_form',
                dict(base_values, error='Something went wrong. Please try again later.', form_data=form_data))

        return request.render('tuition_management.public_enquiry_form', dict(base_values, success=True))