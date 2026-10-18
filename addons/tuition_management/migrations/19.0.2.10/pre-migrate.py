# -*- coding: utf-8 -*-

# class.schedule.one_time_reason changed from free text to a selection.
_REASON_KEYS = {
    'mock test': 'mock_test',
    'mock_test': 'mock_test',
    'review session': 'review_session',
    'review sessions': 'review_session',
    'review_session': 'review_session',
    'parent meeting': 'parent_meeting',
    'parent_meeting': 'parent_meeting',
    'reschedule': 'reschedule',
}


def migrate(cr, version):
    cr.execute("""
        SELECT data_type FROM information_schema.columns
         WHERE table_name = 'class_schedule' AND column_name = 'one_time_reason'
    """)
    row = cr.fetchone()
    if not row or row[0] != 'text':
        return

    # Text that matches no option is kept in one_time_reason_note (the session's Notes).
    cr.execute("ALTER TABLE class_schedule ADD COLUMN IF NOT EXISTS one_time_reason_note text")
    cr.execute("SELECT id, one_time_reason, is_reschedule FROM class_schedule WHERE one_time_reason IS NOT NULL")
    for sched_id, text, is_reschedule in cr.fetchall():
        key = _REASON_KEYS.get(' '.join(text.lower().split()))
        note = None if key else text
        if not key and is_reschedule:
            key = 'reschedule'
        cr.execute(
            "UPDATE class_schedule SET one_time_reason = %s, one_time_reason_note = %s WHERE id = %s",
            (key, note, sched_id),
        )
    cr.execute("ALTER TABLE class_schedule ALTER COLUMN one_time_reason TYPE varchar")
