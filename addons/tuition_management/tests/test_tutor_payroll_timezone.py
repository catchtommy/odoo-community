# -*- coding: utf-8 -*-
from datetime import date, datetime, timedelta

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestTutorPayrollTimezone(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls.env['subject.category'].create({'name': 'Payroll TZ'})
        cls.subject = cls.env['subject.master'].create({
            'name': 'Payroll TZ Maths',
            'category_id': cls.category.id,
        })
        cls.tutor = cls.env['tutor.profile'].create({
            'name': 'Payroll TZ Tutor',
            'phone': '5550303',
            'subject_ids': [(6, 0, [cls.subject.id])],
        })
        cls.course = cls.env['course.master'].create({
            'name': 'Payroll TZ Course',
            'category_id': cls.category.id,
            'subject_id': cls.subject.id,
        })
        # Oct 31, 8pm US/Eastern = Nov 1, 05:30 Asia/Kolkata
        cls.lesson_8pm_us = cls._make_lesson(datetime(2026, 11, 1, 0, 0))
        # Oct 31, 7pm US/Eastern = Nov 1, 04:30 Asia/Kolkata, but still Oct 31 in UTC
        cls.lesson_7pm_us = cls._make_lesson(datetime(2026, 10, 31, 23, 0))
        # Last minute of Oct 31, and first minute of Nov 1, in Asia/Kolkata
        cls.lesson_ist_last = cls._make_lesson(datetime(2026, 10, 31, 18, 29))
        cls.lesson_ist_first = cls._make_lesson(datetime(2026, 10, 31, 18, 30))

    @classmethod
    def _make_lesson(cls, start):
        return cls.env['class.schedule.occurrence'].create({
            'name': 'Payroll TZ lesson %s' % start,
            'course_id': cls.course.id,
            'tutor_id': cls.tutor.id,
            'lesson_status': 'completed',
            'start_datetime': start,
            'stop_datetime': start + timedelta(hours=1),
        })

    def _make_run(self, timezone, period_from='2026-10-01', period_to='2026-10-31'):
        return self.env['tutor.payment.run'].create({
            'payment_period_from': period_from,
            'payment_period_to': period_to,
            'payment_timezone': timezone,
        })

    def _make_rate(self, hourly, effective_from, effective_to=False):
        return self.env['tutor.subject.rate'].create({
            'tutor_id': self.tutor.id,
            'category_id': self.category.id,
            'subject_id': self.subject.id,
            'standard_hourly_rate': hourly,
            'effective_from': effective_from,
            'effective_to': effective_to,
        })

    def test_october_run_in_india_excludes_lessons_on_nov_1_ist(self):
        lessons = self._make_run('Asia/Kolkata')._find_payable_lessons()
        self.assertIn(self.lesson_ist_last, lessons)
        self.assertNotIn(self.lesson_ist_first, lessons)
        self.assertNotIn(self.lesson_7pm_us, lessons)
        self.assertNotIn(self.lesson_8pm_us, lessons)

    def test_october_run_in_us_includes_all_oct_31_us_lessons(self):
        lessons = self._make_run('US/Eastern')._find_payable_lessons()
        for lesson in (self.lesson_ist_last, self.lesson_ist_first, self.lesson_7pm_us, self.lesson_8pm_us):
            self.assertIn(lesson, lessons)

    def test_november_run_in_india_picks_up_lessons_october_left_out(self):
        lessons = self._make_run('Asia/Kolkata', '2026-11-01', '2026-11-30')._find_payable_lessons()
        self.assertNotIn(self.lesson_ist_last, lessons)
        for lesson in (self.lesson_ist_first, self.lesson_7pm_us, self.lesson_8pm_us):
            self.assertIn(lesson, lessons)

    def test_preview_uses_rate_for_lesson_local_date(self):
        self._make_rate(10.0, '2026-01-01', '2026-10-31')
        self._make_rate(20.0, '2026-11-01')
        run = self._make_run('Asia/Kolkata', '2026-11-01', '2026-11-30')
        run.action_generate_preview()
        # Oct 31 in UTC, but Nov 1 in the run's timezone.
        line = run.line_ids.filtered(lambda l: l.lesson_id == self.lesson_7pm_us)
        self.assertEqual(line.rate_used, 20.0)

    def test_local_date_uses_run_timezone(self):
        self.assertEqual(self._make_run('Asia/Kolkata')._lesson_local_date(self.lesson_8pm_us), date(2026, 11, 1))
        self.assertEqual(self._make_run('US/Eastern', '2026-09-01', '2026-09-30')._lesson_local_date(self.lesson_8pm_us), date(2026, 10, 31))

    def test_timezone_is_locked_once_approved(self):
        self._make_rate(10.0, '2026-01-01')
        run = self._make_run('Asia/Kolkata')
        run.action_generate_preview()
        run.action_approve()
        with self.assertRaises(UserError):
            run.write({'payment_timezone': 'US/Eastern'})

    def test_default_timezone_comes_from_user(self):
        run_model = self.env['tutor.payment.run']
        self.env.user.tz = 'Asia/Kolkata'
        self.assertEqual(run_model._default_payment_timezone(), 'Asia/Kolkata')

    def test_default_timezone_falls_back_for_non_common_user_tz(self):
        self.env.user.tz = 'Asia/Calcutta'
        run = self.env['tutor.payment.run'].create({
            'payment_period_from': '2026-10-01',
            'payment_period_to': '2026-10-31',
        })
        self.assertEqual(run.payment_timezone, 'US/Eastern')
