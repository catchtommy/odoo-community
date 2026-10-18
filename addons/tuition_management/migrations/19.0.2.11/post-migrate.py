# -*- coding: utf-8 -*-


def migrate(cr, version):
    # course.master.cancelled_datetime (exact cancellation time, used by the
    # Course Discontinue Report) replaces the date-only cancelled_date. Backfill
    # cancelled courses from cancelled_date, else end_date (set to the
    # cancellation day by the old Cancel Course flow); midday UTC keeps the day
    # stable across most timezones.
    cr.execute("""
        SELECT column_name FROM information_schema.columns
         WHERE table_name = 'course_master' AND column_name = 'cancelled_date'
    """)
    source = "COALESCE(cancelled_date, end_date)" if cr.fetchone() else "end_date"
    cr.execute(f"""
        UPDATE course_master
           SET cancelled_datetime = {source} + TIME '12:00'
         WHERE status = 'cancelled'
           AND cancelled_datetime IS NULL
           AND {source} IS NOT NULL
    """)
