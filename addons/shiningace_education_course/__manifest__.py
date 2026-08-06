# -*- coding: utf-8 -*-
{
    'name': 'Education Course Bridge',
    'version': '19.0.1.0.0',
    'category': 'Education',
    'summary': 'Bridges the Curriculum Management suite to Tuition Management courses',
    'description': """
Education Course Bridge
========================
Connects education_curriculum / education_content to the existing Tuition
Management app WITHOUT duplicating any of its models. Extends
(``_inherit``) course.master, student.profile, tutor.profile,
attendance.record and mark.attendance.wizard, and adds:

- education.course.curriculum: pins a specific (never "latest") curriculum
  version to a course
- education.lesson.assignment: links a class.schedule.occurrence (the
  calendar slot) to an education.lesson (the curriculum content taught)
- education.lesson.feedback, education.student.progress

Tutor/student portal pages already provided by tuition_management are
extended via QWeb inheritance — no new routes are introduced.
    """,
    'author': 'ShiningAce',
    'website': 'https://www.shiningace.com',
    'license': 'LGPL-3',
    'depends': ['shiningace_education_core', 'shiningace_education_curriculum', 'shiningace_education_content', 'tuition_management'],
    'data': [
        'security/education_course_security.xml',
        'security/ir.model.access.csv',
        'security/education_curriculum_access_security.xml',
        'views/education_course_curriculum_views.xml',
        'views/education_curriculum_access_views.xml',
        'views/education_lesson_assignment_views.xml',
        'views/education_student_progress_views.xml',
        'views/course_master_views.xml',
        'views/portal_tutor_lesson_ext.xml',
        'views/portal_tutor_curriculum_views.xml',
        'views/portal_tutor_course_curriculum_ext.xml',
        'views/portal_layout_ext.xml',
        'views/education_course_menus.xml',
    ],
    'demo': [
        'demo/education_course_demo.xml',
    ],
    'installable': True,
    'application': False,
}
