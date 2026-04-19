# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class PublicEnquiryController(http.Controller):

    @http.route('/enquiry', type='http', auth='public', website=True, sitemap=True)
    def enquiry_form(self, **kw):
        grades = request.env['grade.master'].sudo().search([], order='name')
        subjects = request.env['subject.master'].sudo().search([], order='name')
        values = {
            'grades': grades,
            'subjects': subjects,
            'success': False,
            'error': False,
            'form_data': {},
            'csrf_token': request.csrf_token(),
        }
        return request.render('tuition_management.public_enquiry_form', values)

    @http.route('/enquiry/submit', type='http', auth='public', website=True, methods=['POST'], csrf=True)
    def enquiry_submit(self, **post):
        grades = request.env['grade.master'].sudo().search([], order='name')
        subjects = request.env['subject.master'].sudo().search([], order='name')
        csrf = request.csrf_token()

        form_data = {
            'parent_name': post.get('parent_name', '').strip(),
            'email': post.get('email', '').strip(),
            'country_code': post.get('country_code', '').strip(),
            'phone': post.get('phone', '').strip(),
            'student_name': post.get('student_name', '').strip(),
            'grade_id': post.get('grade_id', ''),
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
            return request.render('tuition_management.public_enquiry_form', {
                'grades': grades,
                'subjects': subjects,
                'success': False,
                'error': error,
                'form_data': form_data,
                'csrf_token': csrf,
            })

        # Find the first stage (New)
        first_stage = request.env['enquiry.stage'].sudo().search([], order='sequence asc', limit=1)

        # Create the enquiry
        vals = {
            'name': form_data['parent_name'],
            'email': form_data['email'] or False,
            'country_code': form_data['country_code'] or False,
            'phone': form_data['phone'] or False,
            'student_name': form_data['student_name'],
            'grade_id': int(form_data['grade_id']),
            'subject_id': int(form_data['subject_id']),
            'notes': form_data['notes'] or False,
        }
        if first_stage:
            vals['stage_id'] = first_stage.id

        try:
            request.env['enquiry'].sudo().create(vals)
        except Exception as e:
            return request.render('tuition_management.public_enquiry_form', {
                'grades': grades,
                'subjects': subjects,
                'success': False,
                'error': 'Something went wrong. Please try again later.',
                'form_data': form_data,
                'csrf_token': csrf,
            })

        return request.render('tuition_management.public_enquiry_form', {
            'grades': grades,
            'subjects': subjects,
            'success': True,
            'error': False,
            'form_data': {},
            'csrf_token': csrf,
        })