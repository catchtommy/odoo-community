"""
Post-migration: delete stale website-editor copies of the landing page view
so the updated XML (with login button) takes effect on every server.
"""
import logging

_logger = logging.getLogger(__name__)

VIEW_KEY = 'shiningace_website.landing_page'


def migrate(cr, version):
    cr.execute(
        "SELECT id, website_id FROM ir_ui_view WHERE key = %s AND website_id IS NOT NULL",
        (VIEW_KEY,),
    )
    rows = cr.fetchall()
    if not rows:
        _logger.info("post-migrate shiningace_website 1.0.2: no stale copies found")
        return

    ids = [r[0] for r in rows]
    _logger.warning(
        "post-migrate shiningace_website 1.0.2: deleting stale website copies ids=%s", ids
    )
    cr.execute("DELETE FROM ir_ui_view WHERE id = ANY(%s)", (ids,))
    _logger.info("post-migrate shiningace_website 1.0.2: deleted %d copy/copies", len(ids))
