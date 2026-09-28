# -*- coding: utf-8 -*-


def migrate(cr, version):
    # Before 19.0.2.9 a demo session's status was never updated from its
    # lesson, so every demo stayed "scheduled" even after the lesson was
    # completed, cancelled or marked all-absent. Backfill from the lesson.
    cr.execute("""
        UPDATE demo_session ds
           SET status = CASE occ.lesson_status
                            WHEN 'completed' THEN 'completed'
                            WHEN 'cancelled' THEN 'cancelled'
                            WHEN 'under_review' THEN 'no_show'
                            ELSE 'scheduled'
                        END
          FROM class_schedule_occurrence occ
         WHERE occ.id = ds.schedule_occurrence_id
           AND ds.status IS DISTINCT FROM CASE occ.lesson_status
                            WHEN 'completed' THEN 'completed'
                            WHEN 'cancelled' THEN 'cancelled'
                            WHEN 'under_review' THEN 'no_show'
                            ELSE 'scheduled'
                        END
    """)
