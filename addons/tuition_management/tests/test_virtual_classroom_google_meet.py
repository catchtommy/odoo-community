# -*- coding: utf-8 -*-
import itertools
from datetime import timedelta
from unittest.mock import patch, MagicMock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


def _response(status_code=200, json_data=None, text=''):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.json.return_value = json_data or {}
    return resp


def _token_post_side_effect(space_ids):
    """POST dispatch: token endpoint and freeBusy always succeed; each call
    to create a Meet space returns a unique, incrementing meeting URL from
    `space_ids`; calendar event creation just echoes a static event id."""
    def _side_effect(url, **kwargs):
        if url == 'https://oauth2.googleapis.com/token':
            return _response(200, {'access_token': 'tok'})
        if url == 'https://www.googleapis.com/calendar/v3/freeBusy':
            return _response(200, {'calendars': {'primary': {'busy': []}}})
        if url == 'https://meet.googleapis.com/v2/spaces':
            space_id = next(space_ids)
            return _response(200, {
                'name': 'spaces/space-%s' % space_id,
                'meetingUri': 'https://meet.google.com/%s' % space_id,
                'meetingCode': 'code-%s' % space_id,
            })
        return _response(200, {'id': 'event-id'})
    return _side_effect


def _availability_post_side_effect(states, space_ids):
    """POST dispatch: token endpoint always succeeds; freeBusy results are
    consumed in call order from `states` (one entry per candidate host, in
    sequence order); Meet space creation returns an incrementing meeting URL."""
    def _side_effect(url, **kwargs):
        if url == 'https://oauth2.googleapis.com/token':
            return _response(200, {'access_token': 'tok'})
        if url == 'https://www.googleapis.com/calendar/v3/freeBusy':
            state = next(states)
            if state == 'error':
                return _response(500, text='boom')
            busy = [{'start': 'x', 'end': 'y'}] if state == 'busy' else []
            return _response(200, {'calendars': {'primary': {'busy': busy}}})
        if url == 'https://meet.googleapis.com/v2/spaces':
            space_id = next(space_ids)
            return _response(200, {
                'name': 'spaces/space-%s' % space_id,
                'meetingUri': 'https://meet.google.com/%s' % space_id,
                'meetingCode': 'code-%s' % space_id,
            })
        return _response(200, {'id': 'event-id'})
    return _side_effect


@tagged('post_install', '-at_install')
class TestVirtualClassroomGoogleMeet(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Isolate from any real host accounts already configured in this
        # database (e.g. by an admin testing the feature live) so the
        # availability scan only ever sees the accounts this test creates.
        cls.env['virtual.classroom.google.account'].search([]).write({'active': False})
        cls.course = cls.env['course.master'].create({
            'name': 'Geometry 101',
            'virtual_provider_default': 'google_meet',
        })
        cls.service = cls.env['virtual.classroom.service']
        now = fields.Datetime.now()

        def make_occurrence(name):
            return cls.env['class.schedule.occurrence'].create({
                'name': name,
                'course_id': cls.course.id,
                'start_datetime': now,
                'stop_datetime': now + timedelta(hours=1),
            })

        cls.make_occurrence = staticmethod(make_occurrence)

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()

        cls.env['ir.config_parameter'].sudo().set_param(
            'tuition_management.google_service_account_email', 'svc@project.iam.gserviceaccount.com')
        cls.env['ir.config_parameter'].sudo().set_param(
            'tuition_management.google_service_account_private_key', cls.private_key_pem)

    def _make_account(self, name, sequence, host_email):
        return self.env['virtual.classroom.google.account'].create({
            'name': name,
            'sequence': sequence,
            'host_email': host_email,
        })

    def test_google_meet_creates_new_meeting_per_occurrence(self):
        self._make_account('Account1', 10, 'acc1@example.com')
        occ_a = self.make_occurrence('Lesson A')
        occ_b = self.make_occurrence('Lesson B')

        with patch('odoo.addons.tuition_management.providers.google_meet.requests.post') as post:
            post.side_effect = _token_post_side_effect(itertools.count(1))

            meeting_a = self.service.start_meeting(occ_a, 'google_meet')
            meeting_b = self.service.start_meeting(occ_b, 'google_meet')

        self.assertNotEqual(meeting_a.id, meeting_b.id)
        self.assertEqual(meeting_a.occurrence_id, occ_a)
        self.assertEqual(meeting_b.occurrence_id, occ_b)
        self.assertEqual(meeting_a.course_id, meeting_b.course_id)
        self.assertNotEqual(meeting_a.join_url, meeting_b.join_url)
        self.assertEqual(meeting_a.google_account_id.host_email, 'acc1@example.com')

    def test_google_meet_private_key_with_escaped_newlines_is_normalized(self):
        # Simulates pasting the private_key value straight out of the
        # downloaded service-account JSON file, where real newlines are
        # escaped as literal "\n" two-character sequences.
        escaped_key = self.private_key_pem.replace('\n', '\\n')
        self.env['ir.config_parameter'].sudo().set_param(
            'tuition_management.google_service_account_private_key', escaped_key)
        try:
            self._make_account('Account1', 10, 'acc1@example.com')
            occ = self.make_occurrence('Lesson')

            with patch('odoo.addons.tuition_management.providers.google_meet.requests.post') as post:
                post.side_effect = _token_post_side_effect(itertools.count(1))

                meeting = self.service.start_meeting(occ, 'google_meet')

            self.assertEqual(meeting.state, 'ready')
        finally:
            self.env['ir.config_parameter'].sudo().set_param(
                'tuition_management.google_service_account_private_key', self.private_key_pem)

    def test_google_meet_availability_scan_skips_busy_accounts(self):
        occ = self.make_occurrence('Lesson')
        acc1 = self._make_account('Account1', 10, 'acc1@example.com')
        acc2 = self._make_account('Account2', 20, 'acc2@example.com')

        with patch('odoo.addons.tuition_management.providers.google_meet.requests.post') as post:
            post.side_effect = _availability_post_side_effect(
                iter(['busy', 'free']), itertools.count(1))

            meeting = self.service.start_meeting(occ, 'google_meet')

        self.assertEqual(meeting.google_account_id, acc2)

    def test_google_meet_all_accounts_busy_raises_usererror(self):
        occ = self.make_occurrence('Lesson')
        self._make_account('Account1', 10, 'acc1@example.com')

        with patch('odoo.addons.tuition_management.providers.google_meet.requests.post') as post:
            post.side_effect = _availability_post_side_effect(iter(['busy']), itertools.count(1))

            with self.assertRaises(UserError):
                self.service.start_meeting(occ, 'google_meet')

    def test_google_meet_account_check_error_is_skipped(self):
        occ = self.make_occurrence('Lesson')
        acc1 = self._make_account('Account1', 10, 'acc1@example.com')
        acc2 = self._make_account('Account2', 20, 'acc2@example.com')

        with patch('odoo.addons.tuition_management.providers.google_meet.requests.post') as post:
            post.side_effect = _availability_post_side_effect(iter(['error', 'free']), itertools.count(1))

            meeting = self.service.start_meeting(occ, 'google_meet')

        self.assertEqual(meeting.google_account_id, acc2)
        self.assertTrue(acc1.last_check_error)

    def test_google_meet_gets_expires_at_set(self):
        self._make_account('Account1', 10, 'acc1@example.com')
        occ = self.make_occurrence('Lesson')

        with patch('odoo.addons.tuition_management.providers.google_meet.requests.post') as post:
            post.side_effect = _token_post_side_effect(itertools.count(1))
            meeting = self.service.start_meeting(occ, 'google_meet')

        self.assertEqual(meeting.expires_at, occ.stop_datetime + timedelta(minutes=30))

    def test_google_meet_cron_expires_past_due_meeting_and_revokes_access(self):
        self._make_account('Account1', 10, 'acc1@example.com')
        occ = self.make_occurrence('Lesson')

        with patch('odoo.addons.tuition_management.providers.google_meet.requests.post') as post:
            post.side_effect = _token_post_side_effect(itertools.count(1))
            meeting = self.service.start_meeting(occ, 'google_meet')

        meeting.write({'expires_at': fields.Datetime.now() - timedelta(minutes=1)})

        with patch('odoo.addons.tuition_management.providers.google_meet.requests.post') as post, \
             patch('odoo.addons.tuition_management.providers.google_meet.requests.patch') as patch_req:
            post.side_effect = _token_post_side_effect(itertools.count(100))
            patch_req.return_value = _response(200, {})
            self.env['virtual.classroom.meeting']._cron_expire_meetings()

        self.assertEqual(meeting.state, 'expired')
        self.assertTrue(patch_req.called)

    def test_google_meet_cron_leaves_not_yet_due_meeting_untouched(self):
        self._make_account('Account1', 10, 'acc1@example.com')
        occ = self.make_occurrence('Lesson')

        with patch('odoo.addons.tuition_management.providers.google_meet.requests.post') as post:
            post.side_effect = _token_post_side_effect(itertools.count(1))
            meeting = self.service.start_meeting(occ, 'google_meet')

        with patch('odoo.addons.tuition_management.providers.google_meet.requests.patch') as patch_req:
            self.env['virtual.classroom.meeting']._cron_expire_meetings()

        self.assertEqual(meeting.state, 'ready')
        self.assertFalse(patch_req.called)

    def test_student_join_url_does_not_reuse_other_occurrence_google_meeting(self):
        self._make_account('Account1', 10, 'acc1@example.com')
        occ_a = self.make_occurrence('Lesson A')
        occ_b = self.make_occurrence('Lesson B')
        grade = self.env['grade.master'].create({'name': 'Grade 8 Google Meet Test'})
        partner = self.env['res.partner'].create({'name': 'Sam Student Contact'})
        student = self.env['student.profile'].create({
            'name': 'Sam Student', 'partner_id': partner.id, 'grade_id': grade.id,
        })
        self.env['course.enrollment'].create({
            'student_id': student.id,
            'course_id': self.course.id,
            'status': 'active',
        })

        with patch('odoo.addons.tuition_management.providers.google_meet.requests.post') as post:
            post.side_effect = _token_post_side_effect(itertools.count(1))

            self.service.start_meeting(occ_a, 'google_meet')
            join_url_b = self.service.get_student_join_url(occ_b, student)

        self.assertEqual(join_url_b, 'https://meet.google.com/2')
        self.assertNotEqual(occ_a.virtual_meeting_id, occ_b.virtual_meeting_id)
