# -*- coding: utf-8 -*-
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCurriculumWorkflow(TransactionCase):

    def setUp(self):
        super().setUp()
        self.env.user.group_ids |= self.env.ref('education_core.group_education_curriculum_manager')
        self.subject = self.env['education.subject'].create({'name': 'Test Maths', 'code': 'ZM'})
        self.curriculum = self.env['education.curriculum'].create({
            'name': 'GCSE Mathematics', 'subject_id': self.subject.id,
        })
        self.version = self.env['education.curriculum.version'].create({
            'curriculum_id': self.curriculum.id, 'version_label': 'v1', 'version_number': 1,
        })
        self.topic = self.env['education.topic'].create({
            'name': 'Algebra', 'curriculum_version_id': self.version.id,
        })

    def test_full_workflow_happy_path(self):
        self.version.action_submit_review()
        self.assertEqual(self.version.state, 'review')
        self.version.action_approve()
        self.assertEqual(self.version.state, 'approved')
        self.assertTrue(self.version.approved_by)
        self.version.action_publish()
        self.assertEqual(self.version.state, 'published')
        self.version.action_archive()
        self.assertEqual(self.version.state, 'archived')
        self.assertEqual(len(self.version.review_ids), 4)

    def test_cannot_submit_without_topics(self):
        empty_version = self.env['education.curriculum.version'].create({
            'curriculum_id': self.curriculum.id, 'version_label': 'v2', 'version_number': 2,
        })
        with self.assertRaises(UserError):
            empty_version.action_submit_review()

    def test_cannot_publish_from_draft(self):
        with self.assertRaises(UserError):
            self.version.action_publish()

    def test_cannot_edit_topic_once_published(self):
        self.version.action_submit_review()
        self.version.action_approve()
        self.version.action_publish()
        with self.assertRaises(UserError):
            self.topic.write({'name': 'Algebra Renamed'})
        with self.assertRaises(UserError):
            self.env['education.topic'].create({
                'name': 'New Topic', 'curriculum_version_id': self.version.id,
            })

    def test_cannot_change_identity_once_locked(self):
        other_curriculum = self.env['education.curriculum'].create({
            'name': 'Other Curriculum', 'subject_id': self.subject.id,
        })
        self.version.action_submit_review()
        self.version.action_approve()
        with self.assertRaises(UserError):
            self.version.write({'curriculum_id': other_curriculum.id})

    def test_learning_objective_requires_exactly_one_parent(self):
        with self.assertRaises(ValidationError):
            self.env['education.learning.objective'].create({'name': 'Bad objective'})
        with self.assertRaises(ValidationError):
            subtopic = self.env['education.subtopic'].create({'name': 'Sub', 'topic_id': self.topic.id})
            self.env['education.learning.objective'].create({
                'name': 'Bad objective', 'topic_id': self.topic.id, 'subtopic_id': subtopic.id,
            })
