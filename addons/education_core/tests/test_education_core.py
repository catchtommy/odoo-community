# -*- coding: utf-8 -*-
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestEducationCore(TransactionCase):

    def setUp(self):
        super().setUp()
        self.country = self.env['education.country'].create({'name': 'Testland', 'code': 'ZZ'})
        self.system = self.env['education.education.system'].create({
            'name': 'Testland National Curriculum', 'code': 'ZZ-NC', 'country_id': self.country.id,
        })

    def test_country_code_unique(self):
        with self.assertRaises(Exception):
            self.env['education.country'].create({'name': 'Duplicate', 'code': 'ZZ'})

    def test_subject_code_uppercase_constraint(self):
        with self.assertRaises(ValidationError):
            self.env['education.subject'].create({'name': 'Test Subject', 'code': 'zx'})

    def test_subject_code_unique(self):
        self.env['education.subject'].create({'name': 'Test Subject', 'code': 'ZX'})
        with self.assertRaises(Exception):
            self.env['education.subject'].create({'name': 'Test Subject 2', 'code': 'ZX'})

    def test_academic_level_hierarchy(self):
        group = self.env['education.academic.level'].create({
            'name': 'Key Stage 3', 'level_type': 'group', 'education_system_id': self.system.id,
        })
        level = self.env['education.academic.level'].create({
            'name': 'Year 7', 'level_type': 'level', 'education_system_id': self.system.id,
            'parent_id': group.id,
        })
        self.assertEqual(level.country_id, self.country)
        self.assertIn(level, group.child_ids)

    def test_academic_level_no_recursive_parent(self):
        level = self.env['education.academic.level'].create({
            'name': 'Year 7', 'education_system_id': self.system.id,
        })
        # Odoo's built-in _parent_store recursion guard raises UserError before
        # our own @api.constrains check would run.
        with self.assertRaises(UserError):
            level.parent_id = level.id

    def test_country_smart_button_action(self):
        board = self.env['education.exam.board'].create({
            'name': 'AQA', 'code': 'AQA', 'country_id': self.country.id,
        })
        action = self.country.action_view_exam_boards()
        self.assertEqual(action['res_model'], 'education.exam.board')
        boards = self.env['education.exam.board'].search(action['domain'])
        self.assertEqual(boards, board)
