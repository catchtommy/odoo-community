# -*- coding: utf-8 -*-
import json
import logging
import re

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

STUDENT_INDEX_RE = re.compile(r'^student_name\[(\d+)\]$')


class PublicEnquiryController(http.Controller):

    def _get_enquiry_render_values(self, extra=None):
        grades = request.env['grade.master'].sudo().search([], order='sequence, name')
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

        student_indices = sorted({int(m.group(1)) for k in post if (m := STUDENT_INDEX_RE.match(k))})
        students = [{
            'student_name': post.get(f'student_name[{idx}]', '').strip(),
            'student_age': post.get(f'student_age[{idx}]', '').strip(),
            'category_id': post.get(f'category_id[{idx}]', ''),
            'subject_id': post.get(f'subject_id[{idx}]', ''),
            'grade_id': post.get(f'grade_id[{idx}]', ''),
        } for idx in student_indices]

        form_data = {
            'parent_name': post.get('parent_name', '').strip(),
            'email': post.get('email', '').strip(),
            'country_code': post.get('country_code', '').strip(),
            'phone': post.get('phone', '').strip(),
            'notes': post.get('notes', '').strip(),
            'students': students,
        }

        error = None

        # Validate parent-level required fields
        if not form_data['parent_name']:
            error = 'Parent / Guardian name is required.'
        elif not form_data['email'] and not form_data['phone']:
            error = 'Please provide either an email address or a phone number.'
        elif not students:
            error = 'Please add at least one student.'
        else:
            for i, student in enumerate(students, start=1):
                if not student['student_name']:
                    error = f'Student {i}: name is required.'
                elif not student['grade_id']:
                    error = f'Student {i}: please select a grade.'
                elif not student['subject_id']:
                    error = f'Student {i}: please select a subject.'
                if error:
                    break

        if error:
            return request.render('tuition_management.public_enquiry_form', dict(base_values, error=error, form_data=form_data))

        try:
            for student in students:
                student['student_age'] = int(student['student_age']) if student['student_age'] else 0
                student['grade_id'] = int(student['grade_id'])
                student['subject_id'] = int(student['subject_id'])
                student['category_id'] = int(student['category_id']) if student['category_id'] else False
        except ValueError:
            return request.render('tuition_management.public_enquiry_form',
                dict(base_values, error='Please check the Student Age, Grade and Subject fields.', form_data=form_data))

        # Find the first stage (New)
        first_stage = request.env['enquiry.stage'].sudo().search([], order='sequence asc', limit=1)

        common_vals = {
            'name': form_data['parent_name'],
            'email': form_data['email'] or False,
            'country_code': form_data['country_code'] or False,
            'phone': form_data['phone'] or False,
            'notes': form_data['notes'] or False,
            # Website submissions come from an anonymous visitor — the field's
            # default (self.env.user) would otherwise assign this to Odoo's
            # built-in "Public User" record, which is meaningless as a staff
            # assignment. Leave it unset so it's assigned manually.
            'assigned_user_id': False,
        }
        if first_stage:
            common_vals['stage_id'] = first_stage.id

        def student_vals(student, extra=None):
            vals = dict(common_vals, student_name=student['student_name'], student_age=student['student_age'],
                        grade_id=student['grade_id'], subject_id=student['subject_id'])
            if student['category_id']:
                vals['category_id'] = student['category_id']
            if extra:
                vals.update(extra)
            return vals

        try:
            # Create the first student's enquiry exactly as the single-student
            # flow always has. If the email/phone matches an existing parent,
            # enquiry.create() -> _auto_create_parent_and_student() will leave
            # parent_profile_id unset and flag possible_duplicate_parent_id
            # instead of creating a duplicate parent — staff resolve that from
            # the Enquiry form in the backend, never on this public page.
            first = request.env['enquiry'].sudo().create(student_vals(students[0]))

            if len(students) > 1:
                batch = request.env['enquiry.batch'].sudo().create({'source': 'website'})
                first.sudo().write({'enquiry_batch_id': batch.id})
                # Forward the resolved parent (if any) to the remaining
                # siblings so they attach to the same parent instead of each
                # independently re-running duplicate-parent detection.
                extra = {'enquiry_batch_id': batch.id}
                if first.parent_profile_id:
                    extra['parent_profile_id'] = first.parent_profile_id.id
                rest_vals = [student_vals(student, extra) for student in students[1:]]
                request.env['enquiry'].sudo().create(rest_vals)
        except Exception:
            _logger.exception("Public enquiry submission failed. form_data=%s", form_data)
            return request.render('tuition_management.public_enquiry_form',
                dict(base_values, error='Something went wrong. Please try again later.', form_data=form_data))

        return request.render('tuition_management.public_enquiry_form', dict(base_values, success=True))
