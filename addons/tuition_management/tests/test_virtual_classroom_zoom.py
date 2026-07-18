# -*- coding: utf-8 -*-
import itertools
from datetime import timedelta
from unittest.mock import patch, MagicMock

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged


def _response(status_code=200, json_data=None, text=''):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.json.return_value = json_data or {}
    return resp


def _host_from_url(url):
    return url.split('/users/')[1].split('/meetings')[0]


def _token_post_side_effect(meeting_ids):
    """POST dispatch: token endpoint always succeeds; meeting-creation
    endpoint returns an incrementing meeting id from `meeting_ids`."""
    def _side_effect(url, **kwargs):
        if url == 'https://zoom.us/oauth/token':
            return _response(200, {'access_token': 'tok'})
        meeting_id = next(meeting_ids)
        return _response(200, {
            'id': meeting_id,
            'join_url': 'https://zoom.us/j/%s' % meeting_id,
            'start_url': 'https://zoom.us/s/%s' % meeting_id,
        })
    return _side_effect


def _availability_get_side_effect(states):
    """GET dispatch for the 'list live meetings' call, keyed by host_email
    embedded in the URL. `states` maps host_email -> 'free' | 'busy' | 'error'.
    Any host not in the map defaults to 'free'."""
    def _side_effect(url, **kwargs):
        state = states.get(_host_from_url(url), 'free')
        if state == 'error':
            return _response(500, text='boom')
        if state == 'busy':
            return _response(200, {'total_records': 1})
        return _response(200, {'total_records': 0})
    return _side_effect


@tagged('post_install', '-at_install')
class TestVirtualClassroomZoom(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.course = cls.env['course.master'].create({
            'name': 'Algebra 101',
            'virtual_provider_default': 'zoom',
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

    def _make_account(self, name, sequence, host_email):
        return self.env['virtual.classroom.zoom.account'].create({
            'name': name,
            'sequence': sequence,
            'account_id': '%s-account' % name,
            'client_id': '%s-client' % name,
            'client_secret': '%s-secret' % name,
            'host_email': host_email,
        })

    def test_zoom_creates_new_meeting_per_occurrence(self):
        self._make_account('Account1', 10, 'acc1@example.com')
        occ_a = self.make_occurrence('Lesson A')
        occ_b = self.make_occurrence('Lesson B')

        with patch('odoo.addons.tuition_management.providers.zoom.requests.post') as post, \
             patch('odoo.addons.tuition_management.providers.zoom.requests.get') as get:
            post.side_effect = _token_post_side_effect(itertools.count(1))
            get.side_effect = _availability_get_side_effect({})

            meeting_a = self.service.start_meeting(occ_a, 'zoom')
            meeting_b = self.service.start_meeting(occ_b, 'zoom')

        self.assertNotEqual(meeting_a.id, meeting_b.id)
        self.assertEqual(meeting_a.occurrence_id, occ_a)
        self.assertEqual(meeting_b.occurrence_id, occ_b)
        self.assertEqual(meeting_a.course_id, meeting_b.course_id)
        self.assertNotEqual(meeting_a.join_url, meeting_b.join_url)

    def test_zoom_availability_scan_skips_busy_accounts(self):
        occ = self.make_occurrence('Lesson')
        acc1 = self._make_account('Account1', 10, 'acc1@example.com')
        acc2 = self._make_account('Account2', 20, 'acc2@example.com')

        with patch('odoo.addons.tuition_management.providers.zoom.requests.post') as post, \
             patch('odoo.addons.tuition_management.providers.zoom.requests.get') as get:
            post.side_effect = _token_post_side_effect(itertools.count(1))
            get.side_effect = _availability_get_side_effect({'acc1@example.com': 'busy'})

            meeting = self.service.start_meeting(occ, 'zoom')

        self.assertEqual(meeting.zoom_account_id, acc2)

    def test_zoom_all_accounts_busy_raises_usererror(self):
        occ = self.make_occurrence('Lesson')
        self._make_account('Account1', 10, 'acc1@example.com')

        with patch('odoo.addons.tuition_management.providers.zoom.requests.post') as post, \
             patch('odoo.addons.tuition_management.providers.zoom.requests.get') as get:
            post.side_effect = _token_post_side_effect(itertools.count(1))
            get.side_effect = _availability_get_side_effect({'acc1@example.com': 'busy'})

            with self.assertRaises(UserError):
                self.service.start_meeting(occ, 'zoom')

    def test_zoom_account_check_error_is_skipped(self):
        occ = self.make_occurrence('Lesson')
        acc1 = self._make_account('Account1', 10, 'acc1@example.com')
        acc2 = self._make_account('Account2', 20, 'acc2@example.com')

        with patch('odoo.addons.tuition_management.providers.zoom.requests.post') as post, \
             patch('odoo.addons.tuition_management.providers.zoom.requests.get') as get:
            post.side_effect = _token_post_side_effect(itertools.count(1))
            get.side_effect = _availability_get_side_effect({'acc1@example.com': 'error'})

            meeting = self.service.start_meeting(occ, 'zoom')

        self.assertEqual(meeting.zoom_account_id, acc2)
        self.assertTrue(acc1.last_check_error)

    def test_bbb_reuse_unaffected(self):
        occ_a = self.make_occurrence('Lesson A')
        occ_b = self.make_occurrence('Lesson B')
        self.env['ir.config_parameter'].sudo().set_param(
            'tuition_management.bbb_server_url', 'https://bbb.example.com/bigbluebutton/')
        self.env['ir.config_parameter'].sudo().set_param('tuition_management.bbb_secret', 'secret')

        bbb_ok = _response(200, text='<response><returncode>SUCCESS</returncode></response>')
        with patch('odoo.addons.tuition_management.providers.bbb.requests.get', return_value=bbb_ok):
            meeting_a = self.service.start_meeting(occ_a, 'bbb')
            meeting_b = self.service.start_meeting(occ_b, 'bbb')

        self.assertEqual(meeting_a, meeting_b)
        count = self.env['virtual.classroom.meeting'].search_count([
            ('course_id', '=', self.course.id), ('provider', '=', 'bbb'),
        ])
        self.assertEqual(count, 1)

    def test_student_join_url_does_not_reuse_other_occurrence_zoom_meeting(self):
        self._make_account('Account1', 10, 'acc1@example.com')
        occ_a = self.make_occurrence('Lesson A')
        occ_b = self.make_occurrence('Lesson B')
        grade = self.env['grade.master'].create({'name': 'Grade 8 Zoom Test'})
        partner = self.env['res.partner'].create({'name': 'Sam Student Contact'})
        student = self.env['student.profile'].create({
            'name': 'Sam Student', 'partner_id': partner.id, 'grade_id': grade.id,
        })
        self.env['course.enrollment'].create({
            'student_id': student.id,
            'course_id': self.course.id,
            'status': 'active',
        })

        with patch('odoo.addons.tuition_management.providers.zoom.requests.post') as post, \
             patch('odoo.addons.tuition_management.providers.zoom.requests.get') as get:
            post.side_effect = _token_post_side_effect(itertools.count(1))
            get.side_effect = _availability_get_side_effect({})

            self.service.start_meeting(occ_a, 'zoom')
            join_url_b = self.service.get_student_join_url(occ_b, student)

        self.assertEqual(join_url_b, 'https://zoom.us/j/2')
        self.assertNotEqual(occ_a.virtual_meeting_id, occ_b.virtual_meeting_id)

    def test_constraint_unique_occurrence_provider(self):
        occ = self.make_occurrence('Lesson')
        self.env['virtual.classroom.meeting'].create({
            'occurrence_id': occ.id, 'provider': 'zoom', 'state': 'ready',
        })
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self.env['virtual.classroom.meeting'].create({
                    'occurrence_id': occ.id, 'provider': 'zoom', 'state': 'ready',
                })
