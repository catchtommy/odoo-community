# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCurriculumVersioning(TransactionCase):

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

    def test_version_number_unique_per_curriculum(self):
        with self.assertRaises(Exception):
            self.env['education.curriculum.version'].create({
                'curriculum_id': self.curriculum.id, 'version_label': 'dup', 'version_number': 1,
            })

    def test_create_new_version_clones_topics_as_draft(self):
        self.version.action_submit_review()
        self.version.action_approve()
        self.version.action_publish()

        action = self.version.action_create_new_version()
        new_version = self.env['education.curriculum.version'].browse(action['res_id'])

        self.assertEqual(new_version.state, 'draft')
        self.assertEqual(new_version.version_number, 2)
        self.assertEqual(new_version.parent_version_id, self.version)
        self.assertEqual(len(new_version.topic_ids), 1)
        self.assertNotEqual(new_version.topic_ids.id, self.version.topic_ids.id)
        # original, published version is untouched
        self.assertEqual(self.version.state, 'published')
        self.assertEqual(len(self.version.topic_ids), 1)

    def test_prerequisite_cycle_detection(self):
        topic_b = self.env['education.topic'].create({
            'name': 'Fractions', 'curriculum_version_id': self.version.id,
        })
        self.env['education.prerequisite'].create({
            'topic_id': self.topic.id, 'prerequisite_topic_id': topic_b.id,
        })
        with self.assertRaises(ValidationError):
            self.env['education.prerequisite'].create({
                'topic_id': topic_b.id, 'prerequisite_topic_id': self.topic.id,
            })

    def test_skill_code_auto_generated_and_unique(self):
        skill1 = self.env['education.skill'].create({'name': 'Skill A', 'topic_id': self.topic.id})
        skill2 = self.env['education.skill'].create({'name': 'Skill B', 'topic_id': self.topic.id})
        self.assertTrue(skill1.unique_skill_code)
        self.assertNotEqual(skill1.unique_skill_code, skill2.unique_skill_code)
