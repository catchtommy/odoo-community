# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

from odoo.addons.tuition_management.controllers.portal_tutor import TutorPortal


class TutorPortalCurriculum(TutorPortal):
    """Tutor-facing curriculum browsing + "propose a change" routes.

    Follows the same convention as every other tutor portal route in
    tuition_management/controllers/portal_tutor.py: resolve the tutor via
    _get_tutor(), do all ORM work with sudo(), and enforce access with an
    explicit Python check rather than relying on ir.rule (which is only a
    defense-in-depth backstop here — see
    shiningace_education_course/security/education_curriculum_access_security.xml).
    """

    # ── access helpers ──────────────────────────────────────────────

    def _tutor_courses(self, tutor):
        return request.env['course.master'].sudo().search([
            '|', ('tutor_id', '=', tutor.id), ('tutor_ids', 'in', tutor.id),
        ])

    def _tutor_curriculum_access(self, tutor, curriculum):
        """Return 'contribute', 'view', or None."""
        if not tutor or not curriculum or not curriculum.exists():
            return None
        has_grant = request.env['education.curriculum.access'].sudo().search_count([
            ('tutor_id', '=', tutor.id),
            ('curriculum_id', '=', curriculum.id),
            ('active', '=', True),
        ])
        if has_grant:
            return 'contribute'
        courses = self._tutor_courses(tutor)
        has_course_link = request.env['education.course.curriculum'].sudo().search_count([
            ('curriculum_id', '=', curriculum.id),
            ('course_id', 'in', courses.ids),
        ])
        return 'view' if has_course_link else None

    def _tutor_curricula(self, tutor):
        """(all curricula the tutor can view, ids the tutor can contribute to)."""
        access_grants = request.env['education.curriculum.access'].sudo().search([
            ('tutor_id', '=', tutor.id), ('active', '=', True),
        ])
        contribute_curricula = access_grants.curriculum_id
        courses = self._tutor_courses(tutor)
        course_curricula = request.env['education.course.curriculum'].sudo().search([
            ('course_id', 'in', courses.ids),
        ]).curriculum_id
        return contribute_curricula | course_curricula, contribute_curricula

    def _visible_to(self, records, tutor):
        """Filter a recordset of approval-mixin records to what this tutor
        may see: approved content, or their own pending/rejected proposals."""
        user_id = request.env.user.id
        return records.filtered(
            lambda r: r.approval_state == 'approved' or r.proposed_by_id.id == user_id
        )

    def _next_or(self, post, default):
        """Allow delete routes to be posted from more than one page (the
        curriculum detail page and the "My Proposals" list) and return the
        tutor to wherever they actually came from. Only accepts our own
        curriculum URLs as a redirect target — never an open redirect."""
        next_url = post.get('next')
        if next_url and next_url.startswith('/my/tutor/curriculum'):
            return next_url
        return default

    def _with_error(self, url, error):
        sep = '&' if '?' in url else '?'
        return '%s%serror=%s' % (url, sep, error)

    def _can_edit_proposal(self, record):
        """A tutor may only edit/delete their OWN proposal, and only while
        it hasn't been approved yet — once approved it's live curriculum
        structure and only a curriculum manager can change it."""
        return bool(record) and record.exists() and \
            record.proposed_by_id.id == request.env.user.id and record.approval_state != 'approved'

    def _delete_topic_proposal(self, topic):
        """Delete a tutor's own pending/rejected topic, cascading through
        its own not-yet-approved subtopics/lessons first (Lesson.topic_id
        is ondelete='restrict', so a naive topic.unlink() fails as soon as
        the tutor has also proposed a subtopic or lesson under it — which
        is the normal workflow). Refuses (returns an error code, deletes
        nothing) if anything underneath has already been approved, since
        that's live curriculum structure a tutor can no longer touch here.
        """
        subtopics = topic.subtopic_ids
        lessons = request.env['education.lesson'].sudo().search([
            '|', ('topic_id', '=', topic.id), ('subtopic_id', 'in', subtopics.ids),
        ])
        if any(r.approval_state == 'approved' for r in subtopics) or \
                any(r.approval_state == 'approved' for r in lessons):
            return 'topic_in_use'
        lessons.unlink()
        subtopics.unlink()
        topic.with_context(education_tutor_proposal=True).unlink()
        return None

    def _delete_subtopic_proposal(self, subtopic):
        """Same cascade reasoning as _delete_topic_proposal, one level down."""
        lessons = request.env['education.lesson'].sudo().search([('subtopic_id', '=', subtopic.id)])
        if any(r.approval_state == 'approved' for r in lessons):
            return 'subtopic_in_use'
        lessons.unlink()
        subtopic.unlink()
        return None

    def _delete_lesson_proposal(self, lesson):
        """Delete a tutor's own pending/rejected lesson. LessonContent is
        ondelete='cascade' from lesson_id, so it doesn't block the unlink,
        but refuse if any of its content has already been approved — that's
        live curriculum content a tutor can no longer remove here."""
        if any(r.approval_state == 'approved' for r in lesson.content_ids):
            return 'lesson_in_use'
        lesson.unlink()
        return None

    # ── curriculum list ──────────────────────────────────────────────

    @http.route(['/my/tutor/curriculum'], type='http', auth='user', website=True)
    def portal_tutor_curriculum_list(self, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        all_curricula, contribute_curricula = self._tutor_curricula(tutor)
        return request.render('shiningace_education_course.portal_tutor_curriculum_list', {
            'user': request.env.user,
            'is_tutor': True, 'is_student': False, 'is_parent': False,
            'tutor': tutor,
            'curricula': all_curricula.sorted('name'),
            'contribute_ids': set(contribute_curricula.ids),
            'page_name': 'tutor_curriculum',
        })

    # ── curriculum detail (read-only tree + propose forms) ────────────

    @http.route(['/my/tutor/curriculum/<int:curriculum_id>'], type='http', auth='user', website=True)
    def portal_tutor_curriculum_detail(self, curriculum_id, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        curriculum = request.env['education.curriculum'].sudo().browse(curriculum_id)
        access = self._tutor_curriculum_access(tutor, curriculum)
        if not access:
            return request.redirect('/my/tutor/curriculum')

        version = curriculum.sudo().version_ids.filtered(lambda v: v.state == 'published')[:1]
        topics = self._visible_to(version.topic_ids, tutor).sorted('sequence') if version else request.env['education.topic']

        all_subtopics = self._visible_to(topics.subtopic_ids, tutor)
        subtopics_by_topic = {}
        for sub in all_subtopics.sorted('sequence'):
            subtopics_by_topic.setdefault(sub.topic_id.id, []).append(sub)

        lessons = request.env['education.lesson'].sudo().search([('topic_id', 'in', topics.ids)]) if topics else request.env['education.lesson']
        lessons = self._visible_to(lessons, tutor)
        lessons_by_topic, lessons_by_subtopic = {}, {}
        for lesson in lessons.sorted('sequence'):
            if lesson.subtopic_id:
                lessons_by_subtopic.setdefault(lesson.subtopic_id.id, []).append(lesson)
            else:
                lessons_by_topic.setdefault(lesson.topic_id.id, []).append(lesson)

        topic_rows = []
        for topic in topics:
            sub_rows = []
            for sub in subtopics_by_topic.get(topic.id, []):
                sub_rows.append({'subtopic': sub, 'lessons': lessons_by_subtopic.get(sub.id, [])})
            topic_rows.append({
                'topic': topic,
                'subtopics': sub_rows,
                'lessons': lessons_by_topic.get(topic.id, []),
            })

        return request.render('shiningace_education_course.portal_tutor_curriculum_detail', {
            'user': request.env.user,
            'is_tutor': True, 'is_student': False, 'is_parent': False,
            'tutor': tutor,
            'curriculum': curriculum,
            'version': version,
            'can_contribute': access == 'contribute',
            'topic_rows': topic_rows,
            'proposed_flash': kw.get('proposed'),
            'page_name': 'tutor_curriculum',
        })

    # ── lesson content list (contribute-only detail of a single lesson) ─

    @http.route(['/my/tutor/curriculum/<int:curriculum_id>/lesson/<int:lesson_id>'], type='http', auth='user', website=True)
    def portal_tutor_curriculum_lesson_detail(self, curriculum_id, lesson_id, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        curriculum = request.env['education.curriculum'].sudo().browse(curriculum_id)
        access = self._tutor_curriculum_access(tutor, curriculum)
        lesson = request.env['education.lesson'].sudo().browse(lesson_id)
        if not access or not lesson.exists() or lesson.topic_id.curriculum_id.id != curriculum.id:
            return request.redirect('/my/tutor/curriculum/%d' % curriculum_id)
        if lesson.approval_state != 'approved' and lesson.proposed_by_id.id != request.env.user.id:
            return request.redirect('/my/tutor/curriculum/%d' % curriculum_id)

        content_items = self._visible_to(lesson.content_ids, tutor).sorted('sequence')
        content_types = request.env['education.content.type'].sudo().search([], order='sequence')
        objectives = lesson.objective_ids.sorted('sequence')
        lesson_plans = lesson.lesson_plan_ids.sorted('sequence')
        return request.render('shiningace_education_course.portal_tutor_curriculum_lesson_detail', {
            'user': request.env.user,
            'is_tutor': True, 'is_student': False, 'is_parent': False,
            'tutor': tutor,
            'curriculum': curriculum,
            'lesson': lesson,
            'content_items': content_items,
            'content_types': content_types,
            'objectives': objectives,
            'lesson_plans': lesson_plans,
            'can_contribute': access == 'contribute',
            'page_name': 'tutor_curriculum',
        })

    # ── lesson assignments at course level (mirrors the admin course-form
    #    "View Lesson Assignments" button, scoped to what a tutor can see) ──

    @http.route(['/my/tutor/courses/<int:course_id>/lesson-assignments'], type='http', auth='user', website=True)
    def portal_tutor_course_lesson_assignments(self, course_id, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        course = request.env['course.master'].sudo().browse(course_id)
        if not course.exists() or not self._tutor_has_course_access(tutor, course):
            return request.redirect('/my/tutor/courses')

        assignments = request.env['education.lesson.assignment'].sudo().search(
            [('course_id', '=', course.id)], order='start_datetime desc',
        )
        return request.render('shiningace_education_course.portal_tutor_course_lesson_assignments', {
            'user': request.env.user,
            'is_tutor': True, 'is_student': False, 'is_parent': False,
            'tutor': tutor,
            'course': course,
            'assignments': assignments,
            'page_name': 'tutor_course_detail',
        })

    # ── my proposals ─────────────────────────────────────────────────

    @http.route(['/my/tutor/curriculum/proposals'], type='http', auth='user', website=True)
    def portal_tutor_curriculum_proposals(self, **kw):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        uid = request.env.user.id
        proposals = []
        for model, icon in (
            ('education.topic', 'fa-sitemap'), ('education.subtopic', 'fa-list'),
            ('education.lesson', 'fa-book'), ('education.lesson.content', 'fa-file-o'),
        ):
            recs = request.env[model].sudo().search([('proposed_by_id', '=', uid)], order='id desc')
            for rec in recs:
                if model == 'education.lesson.content':
                    curriculum_id = rec.lesson_id.topic_id.curriculum_id.id
                    delete_url = '/my/tutor/curriculum/%d/lesson/%d/content/%d/delete' % (
                        curriculum_id, rec.lesson_id.id, rec.id)
                elif model == 'education.lesson':
                    curriculum_id = rec.curriculum_id.id
                    delete_url = '/my/tutor/curriculum/%d/lesson/%d/delete' % (curriculum_id, rec.id)
                elif model == 'education.subtopic':
                    curriculum_id = rec.curriculum_id.id
                    delete_url = '/my/tutor/curriculum/%d/subtopic/%d/delete' % (curriculum_id, rec.id)
                else:  # education.topic
                    curriculum_id = rec.curriculum_id.id
                    delete_url = '/my/tutor/curriculum/%d/topic/%d/delete' % (curriculum_id, rec.id)
                proposals.append({
                    'model': model, 'icon': icon, 'record': rec,
                    'delete_url': delete_url,
                    'can_delete': self._can_edit_proposal(rec),
                    'label': {
                        'education.topic': 'Topic', 'education.subtopic': 'Subtopic',
                        'education.lesson': 'Lesson', 'education.lesson.content': 'Lesson Content',
                    }[model],
                })
        return request.render('shiningace_education_course.portal_tutor_curriculum_proposals', {
            'user': request.env.user,
            'is_tutor': True, 'is_student': False, 'is_parent': False,
            'tutor': tutor,
            'proposals': proposals,
            'page_name': 'tutor_curriculum',
        })

    # ── propose: new topic ───────────────────────────────────────────

    @http.route(['/my/tutor/curriculum/<int:curriculum_id>/topic/new'], type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_tutor_curriculum_topic_new(self, curriculum_id, **post):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        curriculum = request.env['education.curriculum'].sudo().browse(curriculum_id)
        if self._tutor_curriculum_access(tutor, curriculum) != 'contribute':
            return request.redirect('/my/tutor/curriculum')
        name = (post.get('name') or '').strip()
        version = curriculum.sudo().version_ids.filtered(lambda v: v.state == 'published')[:1]
        if name and version:
            request.env['education.topic'].sudo().with_context(education_tutor_proposal=True).create({
                'name': name,
                'curriculum_version_id': version.id,
                'approval_state': 'pending',
                'proposed_by_id': request.env.user.id,
            })
        return request.redirect('/my/tutor/curriculum/%d?proposed=topic' % curriculum_id)

    # ── edit / delete: own pending or rejected topic proposal ────────

    @http.route(['/my/tutor/curriculum/<int:curriculum_id>/topic/<int:topic_id>/edit'], type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_tutor_curriculum_topic_edit(self, curriculum_id, topic_id, **post):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        topic = request.env['education.topic'].sudo().browse(topic_id)
        if self._tutor_curriculum_access(tutor, request.env['education.curriculum'].sudo().browse(curriculum_id)) \
                and self._can_edit_proposal(topic) and topic.curriculum_id.id == curriculum_id:
            name = (post.get('name') or '').strip()
            if name:
                topic.with_context(education_tutor_proposal=True).write({'name': name})
        return request.redirect('/my/tutor/curriculum/%d' % curriculum_id)

    @http.route(['/my/tutor/curriculum/<int:curriculum_id>/topic/<int:topic_id>/delete'], type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_tutor_curriculum_topic_delete(self, curriculum_id, topic_id, **post):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        topic = request.env['education.topic'].sudo().browse(topic_id)
        target = self._next_or(post, '/my/tutor/curriculum/%d' % curriculum_id)
        error = None
        if not self._can_edit_proposal(topic) or topic.curriculum_id.id != curriculum_id:
            error = 'not_allowed'
        else:
            error = self._delete_topic_proposal(topic)
        if error:
            return request.redirect(self._with_error(target, error))
        return request.redirect(target)

    # ── propose: new subtopic ────────────────────────────────────────

    @http.route(['/my/tutor/curriculum/<int:curriculum_id>/topic/<int:topic_id>/subtopic/new'], type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_tutor_curriculum_subtopic_new(self, curriculum_id, topic_id, **post):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        curriculum = request.env['education.curriculum'].sudo().browse(curriculum_id)
        topic = request.env['education.topic'].sudo().browse(topic_id)
        if self._tutor_curriculum_access(tutor, curriculum) != 'contribute' or topic.curriculum_id.id != curriculum.id:
            return request.redirect('/my/tutor/curriculum')
        name = (post.get('name') or '').strip()
        if name:
            request.env['education.subtopic'].sudo().create({
                'name': name,
                'topic_id': topic.id,
                'approval_state': 'pending',
                'proposed_by_id': request.env.user.id,
            })
        return request.redirect('/my/tutor/curriculum/%d?proposed=subtopic' % curriculum_id)

    # ── edit / delete: own pending or rejected subtopic proposal ─────

    @http.route(['/my/tutor/curriculum/<int:curriculum_id>/subtopic/<int:subtopic_id>/edit'], type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_tutor_curriculum_subtopic_edit(self, curriculum_id, subtopic_id, **post):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        subtopic = request.env['education.subtopic'].sudo().browse(subtopic_id)
        if self._can_edit_proposal(subtopic) and subtopic.curriculum_id.id == curriculum_id:
            name = (post.get('name') or '').strip()
            if name:
                subtopic.write({'name': name})
        return request.redirect('/my/tutor/curriculum/%d' % curriculum_id)

    @http.route(['/my/tutor/curriculum/<int:curriculum_id>/subtopic/<int:subtopic_id>/delete'], type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_tutor_curriculum_subtopic_delete(self, curriculum_id, subtopic_id, **post):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        subtopic = request.env['education.subtopic'].sudo().browse(subtopic_id)
        target = self._next_or(post, '/my/tutor/curriculum/%d' % curriculum_id)
        error = None
        if not self._can_edit_proposal(subtopic) or subtopic.curriculum_id.id != curriculum_id:
            error = 'not_allowed'
        else:
            error = self._delete_subtopic_proposal(subtopic)
        if error:
            return request.redirect(self._with_error(target, error))
        return request.redirect(target)

    # ── propose: new lesson (topic-level or subtopic-level) ──────────

    @http.route(['/my/tutor/curriculum/<int:curriculum_id>/topic/<int:topic_id>/lesson/new'], type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_tutor_curriculum_lesson_new(self, curriculum_id, topic_id, **post):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        curriculum = request.env['education.curriculum'].sudo().browse(curriculum_id)
        topic = request.env['education.topic'].sudo().browse(topic_id)
        if self._tutor_curriculum_access(tutor, curriculum) != 'contribute' or topic.curriculum_id.id != curriculum.id:
            return request.redirect('/my/tutor/curriculum')
        name = (post.get('name') or '').strip()
        subtopic_id = post.get('subtopic_id')
        subtopic = request.env['education.subtopic'].sudo().browse(int(subtopic_id)) if subtopic_id else None
        if not subtopic or not subtopic.exists() or subtopic.topic_id.id != topic.id:
            # lessons may only be proposed under a subtopic, never directly on a topic
            return request.redirect('/my/tutor/curriculum/%d' % curriculum_id)
        if name:
            request.env['education.lesson'].sudo().create({
                'name': name,
                'topic_id': topic.id,
                'subtopic_id': subtopic.id,
                'approval_state': 'pending',
                'proposed_by_id': request.env.user.id,
            })
        return request.redirect('/my/tutor/curriculum/%d?proposed=lesson' % curriculum_id)

    # ── delete: own pending or rejected lesson proposal ──────────────

    @http.route(['/my/tutor/curriculum/<int:curriculum_id>/lesson/<int:lesson_id>/delete'], type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_tutor_curriculum_lesson_delete(self, curriculum_id, lesson_id, **post):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        lesson = request.env['education.lesson'].sudo().browse(lesson_id)
        target = self._next_or(post, '/my/tutor/curriculum/%d' % curriculum_id)
        error = None
        if not self._can_edit_proposal(lesson) or lesson.topic_id.curriculum_id.id != curriculum_id:
            error = 'not_allowed'
        else:
            error = self._delete_lesson_proposal(lesson)
        if error:
            return request.redirect(self._with_error(target, error))
        return request.redirect(target)

    # ── propose: new lesson content ──────────────────────────────────

    @http.route(['/my/tutor/curriculum/<int:curriculum_id>/lesson/<int:lesson_id>/content/new'], type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_tutor_curriculum_content_new(self, curriculum_id, lesson_id, **post):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        curriculum = request.env['education.curriculum'].sudo().browse(curriculum_id)
        lesson = request.env['education.lesson'].sudo().browse(lesson_id)
        if self._tutor_curriculum_access(tutor, curriculum) != 'contribute' or lesson.topic_id.curriculum_id.id != curriculum.id:
            return request.redirect('/my/tutor/curriculum')
        name = (post.get('name') or '').strip()
        external_url = (post.get('external_url') or '').strip()
        body = (post.get('body') or '').strip()
        content_type = request.env['education.content.type'].sudo().browse(0)
        content_type_id = post.get('content_type_id')
        if content_type_id:
            content_type = request.env['education.content.type'].sudo().browse(int(content_type_id))
        if not content_type.exists():
            content_type = request.env['education.content.type'].sudo().search([], limit=1, order='sequence')
        upload = request.httprequest.files.get('content_file')
        vals = {
            'name': name,
            'lesson_id': lesson.id,
            'content_type_id': content_type.id if content_type else False,
            'external_url': external_url or False,
            'body': body or False,
            'approval_state': 'pending',
            'proposed_by_id': request.env.user.id,
        }
        if upload and upload.filename:
            import base64
            vals['content_file'] = base64.b64encode(upload.read())
            vals['content_filename'] = upload.filename
        if name and content_type and (external_url or body or upload):
            request.env['education.lesson.content'].sudo().create(vals)
        return request.redirect('/my/tutor/curriculum/%d/lesson/%d?proposed=content' % (curriculum_id, lesson_id))

    # ── delete: own pending or rejected lesson content proposal ──────

    @http.route(['/my/tutor/curriculum/<int:curriculum_id>/lesson/<int:lesson_id>/content/<int:content_id>/delete'], type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def portal_tutor_curriculum_content_delete(self, curriculum_id, lesson_id, content_id, **post):
        tutor = self._get_tutor()
        if not tutor:
            return request.redirect('/my')
        content = request.env['education.lesson.content'].sudo().browse(content_id)
        target = self._next_or(post, '/my/tutor/curriculum/%d/lesson/%d' % (curriculum_id, lesson_id))
        if not self._can_edit_proposal(content) or content.lesson_id.id != lesson_id \
                or content.lesson_id.topic_id.curriculum_id.id != curriculum_id:
            return request.redirect(self._with_error(target, 'not_allowed'))
        content.unlink()
        return request.redirect(target)
