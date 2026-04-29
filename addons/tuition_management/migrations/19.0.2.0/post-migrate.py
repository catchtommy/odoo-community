# -*- coding: utf-8 -*-


def migrate(cr, version):
    cr.execute("""
        UPDATE course_master
           SET virtual_provider_default = CASE
                WHEN virtual_class_platform = 'bigbluebutton' THEN 'bbb'
                WHEN virtual_class_platform IN ('zoom', 'google_meet') THEN virtual_class_platform
                ELSE virtual_provider_default
           END
         WHERE virtual_provider_default IS NULL
           AND virtual_class_platform IN ('zoom', 'google_meet', 'bigbluebutton')
    """)
    cr.execute("""
        UPDATE course_master
           SET google_meet_static_url = virtual_class_url
         WHERE google_meet_static_url IS NULL
           AND virtual_class_platform = 'google_meet'
           AND virtual_class_url IS NOT NULL
    """)
    cr.execute("""
        UPDATE class_schedule_occurrence occ
           SET virtual_provider = course.virtual_provider_default
          FROM course_master course
         WHERE occ.course_id = course.id
           AND occ.virtual_provider IS NULL
           AND course.virtual_provider_default IS NOT NULL
    """)
    cr.execute("""
        UPDATE virtual_classroom_meeting
           SET host_url = NULL,
               moderator_url = NULL,
               join_url = NULL
         WHERE provider = 'bbb'
           AND (
                host_url LIKE 'http://localhost%%'
                OR host_url LIKE 'https://localhost%%'
                OR host_url LIKE 'http://127.0.0.1%%'
                OR host_url LIKE 'https://127.0.0.1%%'
                OR moderator_url LIKE 'http://localhost%%'
                OR moderator_url LIKE 'https://localhost%%'
                OR moderator_url LIKE 'http://127.0.0.1%%'
                OR moderator_url LIKE 'https://127.0.0.1%%'
                OR join_url LIKE 'http://localhost%%'
                OR join_url LIKE 'https://localhost%%'
                OR join_url LIKE 'http://127.0.0.1%%'
                OR join_url LIKE 'https://127.0.0.1%%'
           )
    """)
