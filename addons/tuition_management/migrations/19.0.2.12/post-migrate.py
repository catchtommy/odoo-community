# -*- coding: utf-8 -*-


def migrate(cr, version):
    # course.master.cancellation_stage_id is new: classify courses cancelled
    # before it existed by whether they ever had an enrolment.
    cr.execute("""
        SELECT name, res_id FROM ir_model_data
         WHERE module = 'tuition_management'
           AND name IN ('cancellation_stage_before_enrolment', 'cancellation_stage_after_enrolment')
    """)
    stage = dict(cr.fetchall())
    if len(stage) < 2:
        return
    cr.execute("""
        UPDATE course_master c
           SET cancellation_stage_id = CASE
                   WHEN EXISTS (SELECT 1 FROM course_enrollment e WHERE e.course_id = c.id) THEN %s
                   ELSE %s
               END
         WHERE c.status = 'cancelled' AND c.cancellation_stage_id IS NULL
    """, (stage['cancellation_stage_after_enrolment'], stage['cancellation_stage_before_enrolment']))
