"""
Post-migration script: remove stale website-editor copies of the landing page view.

When the website editor saves a page it creates a per-website ir.ui.view copy
(website_id is set, arch_updated=True). That copy overrides the XML-defined view
and prevents module upgrades from taking effect on production servers.

This script runs automatically during  `odoo-bin -u shiningace_website`  and
deletes any such copies so the canonical XML view takes over.
"""
import logging

_logger = logging.getLogger(__name__)

VIEW_KEY = 'shiningace_website.landing_page'


def migrate(cr, version):
    cr.execute(
        """
        SELECT id, name, website_id, arch_updated
          FROM ir_ui_view
         WHERE key = %s
           AND website_id IS NOT NULL
        """,
        (VIEW_KEY,),
    )
    rows = cr.fetchall()

    if not rows:
        _logger.info("post-migrate shiningace_website: no stale website copies found for %s", VIEW_KEY)
        return

    ids_to_delete = [row[0] for row in rows]
    for row in rows:
        _logger.warning(
            "post-migrate shiningace_website: deleting stale website copy "
            "id=%s name=%r website_id=%s arch_updated=%s",
            *row,
        )

    cr.execute(
        "DELETE FROM ir_ui_view WHERE id = ANY(%s)",
        (ids_to_delete,),
    )
    _logger.info(
        "post-migrate shiningace_website: deleted %d stale view copy/copies for %s",
        len(ids_to_delete),
        VIEW_KEY,
    )
