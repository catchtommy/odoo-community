# -*- coding: utf-8 -*-
from odoo import fields
from odoo.addons.mail.tests.common import MailCommon
from odoo.tests.common import tagged


@tagged('post_install', '-at_install')
class TestTuitionChatter(MailCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls.env['subject.category'].create({'name': 'STEM'})
        cls.subject = cls.env['subject.master'].create({
            'name': 'Mathematics',
            'category_id': cls.category.id,
        })
        cls.grade = cls.env['grade.master'].create({'name': 'Grade 8'})
        for name, sequence, is_enrolled in [
            ('New', 10, False),
            ('Demo Scheduled', 20, False),
            ('Demo Completed', 30, False),
            ('Enrolled', 40, True),
            ('Lost', 50, False),
        ]:
            stage = cls.env['enquiry.stage'].search([('name', '=', name)], limit=1)
            if stage:
                stage.write({'sequence': sequence, 'is_enrolled_stage': is_enrolled})
            else:
                cls.env['enquiry.stage'].create({
                    'name': name,
                    'sequence': sequence,
                    'is_enrolled_stage': is_enrolled,
                })

    def _create_enquiry(self):
        return self.env['enquiry'].create({
            'name': 'Pat Parent',
            'student_name': 'Sam Student',
            'phone': '5550101',
            'subject_id': self.subject.id,
            'grade_id': self.grade.id,
            'enquiry_source': 'website',
        })

    def test_chatter_rendering(self):
        enquiry_arch = self.env.ref('tuition_management.view_enquiry_form').arch_db
        course_arch = self.env.ref('tuition_management.view_course_master_form').arch_db

        self.assertIn('<chatter/>', enquiry_arch)
        self.assertIn('<chatter/>', course_arch)

    def test_enquiry_chatter_tracking_activity_message_followers(self):
        enquiry = self._create_enquiry()

        for field_name in [
            'status',
            'parent_profile_id',
            'student_profile_id',
            'assigned_user_id',
            'enquiry_source',
        ]:
            self.assertTrue(enquiry._fields[field_name].tracking, field_name)
        self.assertIn('stage_id', enquiry._track_get_fields())

        follower_partner_ids = enquiry.message_follower_ids.partner_id.ids
        self.assertIn(enquiry.parent_profile_id.partner_id.id, follower_partner_ids)
        self.assertIn(enquiry.student_profile_id.partner_id.id, follower_partner_ids)
        self.assertTrue(enquiry.activity_ids.filtered(lambda activity: activity.summary == 'Follow up enquiry'))
        self.assertTrue(enquiry.message_ids.filtered(lambda message: 'Enquiry created' in message.body))

        enquiry.with_context(mail_notrack=False).write({'status': 'demo_scheduled'})
        self.assertEqual(enquiry.stage_id.name, 'Demo Scheduled')
        self.assertTrue(enquiry.message_ids.filtered(lambda message: 'Demo scheduled' in message.body))

    def test_course_chatter_tracking_activity_message_followers(self):
        course = self.env['course.master'].create({
            'name': 'Math Coaching',
            'subject_id': self.subject.id,
            'status': 'draft',
        })

        for field_name in [
            'status',
            'tutor_id',
            'subject_id',
            'schedule_id',
            'subscription_plan_id',
        ]:
            self.assertTrue(course._fields[field_name].tracking, field_name)
        self.assertIn('status', course._track_get_fields())
        self.assertIn('tutor_id', course._track_get_fields())

        self.assertTrue(course.activity_ids.filtered(lambda activity: activity.summary == 'Assign tutor'))
        self.assertTrue(course.message_ids.filtered(lambda message: 'Course created' in message.body))

        tutor = self.env['tutor.profile'].create({
            'name': 'Tina Tutor',
            'phone': '5550202',
            'subject_ids': [(6, 0, [self.subject.id])],
        })
        self.env['tutor.subject.rate'].create({
            'tutor_id': tutor.id,
            'category_id': self.category.id,
            'subject_id': self.subject.id,
            'standard_hourly_rate': 40.0,
            'demo_rate_type': 'percentage',
            'demo_percentage': 50.0,
            'effective_from': fields.Date.today(),
        })
        course.with_context(mail_notrack=False).write({'tutor_id': tutor.id, 'status': 'active'})

        follower_partner_ids = course.message_follower_ids.partner_id.ids
        self.assertIn(tutor.partner_id.id, follower_partner_ids)
        self.assertTrue(course.message_ids.filtered(lambda message: 'Tutor assigned' in message.body))

    def test_subscription_renewal_activity_automation(self):
        course = self.env['course.master'].create({'name': 'Renewal Course'})
        student = self.env['student.profile'].create({
            'name': 'Renewal Student',
            'phone': '5550303',
            'grade_id': self.grade.id,
        })
        enrollment = self.env['course.enrollment'].create({
            'course_id': course.id,
            'student_id': student.id,
        })
        product = self.env['product.product'].create({
            'name': 'Monthly Tuition',
            'type': 'service',
            'list_price': 100.0,
        })
        subscription = self.env['tuition.subscription'].create({
            'student_id': student.id,
            'enrollment_id': enrollment.id,
            'next_billing_date': fields.Date.today(),
        })
        today = fields.Date.today()
        plan_start = today.replace(day=1)
        plan_end = fields.Date.end_of(today, 'month')
        self.env['tuition.plan.line'].create({
            'subscription_id': subscription.id,
            'product_id': product.id,
            'price': 100.0,
            'classes_per_week': 1,
            'start_date': plan_start,
            'end_date': plan_end,
        })

        self.env['course.master']._cron_schedule_subscription_renewal_activities()

        self.assertTrue(course.activity_ids.filtered(lambda activity: activity.summary == 'Renew subscription'))
