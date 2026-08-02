# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestLessonContent(TransactionCase):

    def setUp(self):
        super().setUp()
        self.env.user.group_ids |= self.env.ref('shiningace_education_core.group_education_curriculum_manager')
        subject = self.env['education.subject'].create({'name': 'Test Maths', 'code': 'ZM'})
        curriculum = self.env['education.curriculum'].create({'name': 'GCSE Maths', 'subject_id': subject.id})
        self.version = self.env['education.curriculum.version'].create({
            'curriculum_id': curriculum.id, 'version_label': 'v1', 'version_number': 1,
        })
        self.topic = self.env['education.topic'].create({'name': 'Algebra', 'curriculum_version_id': self.version.id})
        self.lesson = self.env['education.lesson'].create({'name': 'Lesson 1', 'topic_id': self.topic.id})
        self.content_type = self.env['education.content.type'].search([('code', '=', 'worksheet')], limit=1)
        if not self.content_type:
            self.content_type = self.env['education.content.type'].create({'name': 'Worksheet', 'code': 'worksheet'})

    def test_content_requires_payload(self):
        with self.assertRaises(ValidationError):
            self.env['education.lesson.content'].create({
                'name': 'Empty Content', 'lesson_id': self.lesson.id, 'content_type_id': self.content_type.id,
            })

    def test_content_new_version_keeps_history(self):
        content = self.env['education.lesson.content'].create({
            'name': 'Worksheet v1', 'lesson_id': self.lesson.id, 'content_type_id': self.content_type.id,
            'body': '<p>Hello</p>', 'state': 'published',
        })
        new_content = content.action_new_version()
        self.assertEqual(new_content.version, 2)
        self.assertEqual(new_content.previous_version_id, content)
        self.assertEqual(new_content.state, 'draft')
        self.assertEqual(content.state, 'published')

    def test_resource_requires_payload(self):
        with self.assertRaises(ValidationError):
            self.env['education.resource'].create({'name': 'Empty Resource', 'content_type_id': self.content_type.id})

    def test_lesson_publish_workflow(self):
        self.assertEqual(self.lesson.state, 'draft')
        self.lesson.action_publish()
        self.assertEqual(self.lesson.state, 'published')
        self.lesson.action_archive_lesson()
        self.assertEqual(self.lesson.state, 'archived')
