# -*- coding: utf-8 -*-
from . import models
from . import controllers
import logging

_logger = logging.getLogger(__name__)


def _create_default_enquiry_stages(env):
    """Post-init hook — ensure exactly 5 clean stages exist."""
    cr = env.cr
    _logger.info("=== ENQUIRY STAGE POST-INIT CLEANUP ===")

    cr.execute("SELECT id, name FROM enquiry_stage ORDER BY name, id")
    _logger.info("Before cleanup: %s", cr.fetchall())

    # Dedup: keep MIN(id) per name
    cr.execute("""
        SELECT name, MIN(id) as keep_id, array_agg(id ORDER BY id) as all_ids
        FROM enquiry_stage GROUP BY name HAVING COUNT(*) > 1
    """)
    for name, keep_id, all_ids in cr.fetchall():
        delete_ids = [i for i in all_ids if i != keep_id]
        if delete_ids:
            cr.execute("UPDATE enquiry SET stage_id = %s WHERE stage_id = ANY(%s)", (keep_id, delete_ids))
            cr.execute("DELETE FROM ir_model_data WHERE model='enquiry.stage' AND res_id = ANY(%s)", (delete_ids,))
            cr.execute("DELETE FROM enquiry_stage WHERE id = ANY(%s)", (delete_ids,))

    # Remove non-official
    official = ['New', 'Demo Scheduled', 'Demo Completed', 'Enrolled', 'Lost']
    cr.execute("SELECT id FROM enquiry_stage WHERE name != ALL(%s)", (official,))
    bad = [r[0] for r in cr.fetchall()]
    if bad:
        cr.execute("SELECT id FROM enquiry_stage WHERE name='New' ORDER BY id LIMIT 1")
        new_id = cr.fetchone()
        if new_id:
            cr.execute("UPDATE enquiry SET stage_id = %s WHERE stage_id = ANY(%s)", (new_id[0], bad))
        cr.execute("DELETE FROM ir_model_data WHERE model='enquiry.stage' AND res_id = ANY(%s)", (bad,))
        cr.execute("DELETE FROM enquiry_stage WHERE id = ANY(%s)", (bad,))

    # Ensure all 5 exist
    for name, seq, is_enr in [('New',10,False),('Demo Scheduled',20,False),('Demo Completed',30,False),('Enrolled',40,True),('Lost',50,False)]:
        cr.execute("SELECT id FROM enquiry_stage WHERE name=%s", (name,))
        if not cr.fetchone():
            cr.execute(
                "INSERT INTO enquiry_stage (name,sequence,is_enrolled_stage,create_uid,write_uid,create_date,write_date) VALUES (%s,%s,%s,1,1,now(),now())",
                (name, seq, is_enr))

    cr.execute("SELECT id, name FROM enquiry_stage ORDER BY sequence")
    _logger.info("After cleanup: %s", cr.fetchall())
