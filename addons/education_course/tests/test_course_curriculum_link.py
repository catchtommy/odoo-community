# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCourseCurriculumLink(TransactionCase):

    def setUp(self):
        super().setUp()
        self.env.user.group_ids |= self.env.ref('education_core.group_education_curriculum_manager')
        subject = self.env['education.subject'].create({'name': 'Test Maths', 'code': 'ZM'})
        curriculum = self.env['education.curriculum'].create({'name': 'GCSE Maths', 'subject_id': subject.id})
        self.version = self.env['education.curriculum.version'].create({
            'curriculum_id': curriculum.id, 'version_label': 'v1', 'version_number': 1,
        })
        self.env['education.topic'].create({'name': 'Algebra', 'curriculum_version_id': self.version.id})
        self.version.action_submit_review()
        self.version.action_approve()
        self.version.action_publish()
        self.course = self.env['course.master'].create({'name': 'Demo Course'})

    def test_cannot_assign_unpublished_version(self):
        draft_version = self.env['education.curriculum.version'].create({
            'curriculum_id': self.version.curriculum_id.id, 'version_label': 'v2', 'version_number': 2,
        })
        with self.assertRaises(ValidationError):
            self.env['education.course.curriculum'].create({
                'course_id': self.course.id, 'curriculum_version_id': draft_version.id,
            })

    def test_assigning_new_version_never_mutates_old_link(self):
        link1 = self.env['education.course.curriculum'].create({
            'course_id': self.course.id, 'curriculum_version_id': self.version.id,
        })
        new_version_action = self.version.action_create_new_version()
        new_version = self.env['education.curriculum.version'].browse(new_version_action['res_id'])
        new_version.action_submit_review()
        new_version.action_approve()
        new_version.action_publish()

        link2 = self.env['education.course.curriculum'].create({
            'course_id': self.course.id, 'curriculum_version_id': new_version.id, 'is_primary': False,
        })

        self.assertEqual(link1.curriculum_version_id, self.version)
        self.assertEqual(link2.curriculum_version_id, new_version)
        self.assertEqual(self.course.primary_curriculum_version_id, self.version)
        self.assertEqual(len(self.course.course_curriculum_ids), 2)

    def test_duplicate_assignment_blocked(self):
        self.env['education.course.curriculum'].create({
            'course_id': self.course.id, 'curriculum_version_id': self.version.id,
        })
        with self.assertRaises(Exception):
            self.env['education.course.curriculum'].create({
                'course_id': self.course.id, 'curriculum_version_id': self.version.id,
            })
