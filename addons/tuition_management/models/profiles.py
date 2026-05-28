# -*- coding: utf-8 -*-
import pytz
from odoo import api, fields, models

_TIMEZONE_LIST = [(tz, tz) for tz in sorted(pytz.all_timezones)]


class StudentProfile(models.Model):
    _name = 'student.profile'
    _description = 'Student Profile'

    # Personal Information
    first_name = fields.Char(string='First Name', required=True)
    middle_name = fields.Char(string='Middle Name')
    last_name = fields.Char(string='Last Name', required=True)
    email = fields.Char(string='Email Address')
    phone = fields.Char(string='Phone Number')
    country_code = fields.Char(string='Country Code', default='+1')
    timezone = fields.Selection(_TIMEZONE_LIST, string='Timezone', default='UTC')
    status = fields.Selection(
        selection=[('active', 'Active'), ('inactive', 'Inactive')],
        string='Status',
        default='active',
        required=True,
    )

    # Academic Information
    age = fields.Integer(string='Age')
    grade_id = fields.Many2one('grade.master', string='Grade')
    subjects_ids = fields.Many2many('subject.master', string='Subjects')
    
    # Address fields
    address_line_1 = fields.Char(string='Address Line 1')
    address_line_2 = fields.Char(string='Address Line 2')
    address_line_3 = fields.Char(string='Address Line 3')
    address_line_4 = fields.Char(string='Address Line 4')
    zip_code = fields.Char(string='Zip Code')

    def init(self):
        self.env.cr.execute(
            "UPDATE student_profile SET status = 'active' WHERE status IS NULL"
        )


class TutorProfile(models.Model):
    _name = 'tutor.profile'
    _description = 'Tutor Profile'

    # Personal Information
    first_name = fields.Char(string='First Name', required=True)
    middle_name = fields.Char(string='Middle Name')
    last_name = fields.Char(string='Last Name', required=True)
    email = fields.Char(string='Email Address')
    phone = fields.Char(string='Phone Number')
    country_code = fields.Char(string='Country Code', default='+1')
    timezone = fields.Selection(_TIMEZONE_LIST, string='Timezone', default='UTC')
    status = fields.Selection(
        selection=[('active', 'Active'), ('inactive', 'Inactive')],
        string='Status',
        default='active',
        required=True,
    )
    
    # Professional Information
    subjects_ids = fields.Many2many('subject.master', string='Subjects')
    
    # Address fields
    address_line_1 = fields.Char(string='Address Line 1')
    address_line_2 = fields.Char(string='Address Line 2')
    address_line_3 = fields.Char(string='Address Line 3')
    address_line_4 = fields.Char(string='Address Line 4')
    zip_code = fields.Char(string='Zip Code')

    def init(self):
        self.env.cr.execute(
            "UPDATE tutor_profile SET status = 'active' WHERE status IS NULL"
        )


class ParentProfile(models.Model):
    _name = 'parent.profile'
    _description = 'Parent Profile'

    # Personal Information
    first_name = fields.Char(string='First Name', required=True)
    middle_name = fields.Char(string='Middle Name')
    last_name = fields.Char(string='Last Name', required=True)
    email = fields.Char(string='Email Address')
    phone = fields.Char(string='Phone Number')
    country_code = fields.Char(string='Country Code', default='+1')
    timezone = fields.Selection(_TIMEZONE_LIST, string='Timezone', default='UTC')
    status = fields.Selection(
        selection=[('active', 'Active'), ('inactive', 'Inactive')],
        string='Status',
        default='active',
        required=True,
    )
    
    # Relationships
    student_ids = fields.Many2many('student.profile', string='Students', help='Students under this parent')
    
    # Address fields
    address_line_1 = fields.Char(string='Address Line 1')
    address_line_2 = fields.Char(string='Address Line 2')
    address_line_3 = fields.Char(string='Address Line 3')
    address_line_4 = fields.Char(string='Address Line 4')
    zip_code = fields.Char(string='Zip Code')

    def init(self):
        self.env.cr.execute(
            "UPDATE parent_profile SET status = 'active' WHERE status IS NULL"
        )


class SubjectMaster(models.Model):
    _name = 'subject.master'
    _description = 'Subject'

    name = fields.Char(required=True)
    code = fields.Char()
    description = fields.Text()


class GradeMaster(models.Model):
    _name = 'grade.master'
    _description = 'Grade'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
