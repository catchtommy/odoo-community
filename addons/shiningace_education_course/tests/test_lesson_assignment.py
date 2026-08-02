# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestLessonAssignment(TransactionCase):

    def setUp(self):
        super().setUp()
        self.env.user.group_ids |= self.env.ref('shiningace_education_core.group_education_curriculum_manager')

        subject = self.env['education.subject'].create({'name': 'Test Maths', 'code': 'ZM'})
        curriculum = self.env['education.curriculum'].create({'name': 'GCSE Maths', 'subject_id': subject.id})
        version = self.env['education.curriculum.version'].create({
            'curriculum_id': curriculum.id, 'version_label': 'v1', 'version_number': 1,
        })
        topic = self.env['education.topic'].create({'name': 'Algebra', 'curriculum_version_id': version.id})
        self.lesson = self.env['education.lesson'].create({'name': 'Lesson 1', 'topic_id': topic.id, 'state': 'published'})

        self.tutor = self.env['tutor.profile'].create({'name': 'Demo Tutor'})
        self.course = self.env['course.master'].create({'name': 'Demo Course'})
        schedule = self.env['class.schedule'].create({
            'course_id': self.course.id, 'tutor_id': self.tutor.id,
            'schedule_type': 'one_time', 'schedule_date': '2026-01-05',
        })
        self.occurrence = self.env['class.schedule.occurrence'].create({
            'name': 'Occurrence 1',
            'schedule_id': schedule.id,
            'course_id': self.course.id,
            'tutor_id': self.tutor.id,
            'start_datetime': '2026-01-05 09:00:00',
            'stop_datetime': '2026-01-05 10:00:00',
        })

    def test_lesson_assignment_links_occurrence_and_lesson(self):
        assignment = self.env['education.lesson.assignment'].create({
            'class_schedule_occurrence_id': self.occurrence.id, 'lesson_id': self.lesson.id,
        })
        self.assertEqual(assignment.course_id, self.course)
        self.assertEqual(assignment.tutor_id, self.tutor)
        self.assertEqual(assignment.status, 'planned')

    def test_lesson_assignment_unique_per_occurrence(self):
        self.env['education.lesson.assignment'].create({
            'class_schedule_occurrence_id': self.occurrence.id, 'lesson_id': self.lesson.id,
        })
        with self.assertRaises(Exception):
            self.env['education.lesson.assignment'].create({
                'class_schedule_occurrence_id': self.occurrence.id, 'lesson_id': self.lesson.id,
            })

    def test_attendance_record_computes_lesson_assignment(self):
        self.env['education.lesson.assignment'].create({
            'class_schedule_occurrence_id': self.occurrence.id, 'lesson_id': self.lesson.id,
        })
        student = self.env['res.partner'].create({'name': 'Demo Partner'})
        grade = self.env['grade.master'].create({'name': 'Year 7'})
        student_profile = self.env['student.profile'].create({
            'name': 'Demo Student', 'partner_id': student.id, 'grade_id': grade.id,
        })
        attendance = self.env['attendance.record'].create({
            'class_schedule_occurrence_id': self.occurrence.id,
            'student_id': student_profile.id,
            'attendance_date': '2026-01-05',
            'status': 'present',
        })
        self.assertEqual(attendance.lesson_assignment_id.lesson_id, self.lesson)
