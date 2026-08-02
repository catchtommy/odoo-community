# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    # Prior to 19.0.2.7, seq_course_enrollment/seq_enquiry had no
    # company_id=False, so ir.sequence.next_by_code() silently returned
    # False for any company other than the install-time one, and the
    # calling code's `or 'New'` fallback stored the literal string "New"
    # as a permanent record name. Backfill those stuck rows now that the
    # sequences are fixed.
    env = api.Environment(cr, SUPERUSER_ID, {})

    cr.execute("SELECT id FROM course_enrollment WHERE name IN ('New', 'new') ORDER BY id")
    for (record_id,) in cr.fetchall():
        seq = env['ir.sequence'].next_by_code('course.enrollment')
        cr.execute("UPDATE course_enrollment SET name = %s WHERE id = %s", (seq, record_id))

    cr.execute("SELECT id FROM enquiry WHERE enquiry_name IN ('New', 'new') ORDER BY id")
    for (record_id,) in cr.fetchall():
        seq = env['ir.sequence'].next_by_code('enquiry')
        cr.execute("UPDATE enquiry SET enquiry_name = %s WHERE id = %s", (seq, record_id))
