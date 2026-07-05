# -*- coding: utf-8 -*-


def migrate(cr, version):
    # tuition_subscription.pricelist_id ("Billing Pricelist") was replaced by a
    # direct currency_id ("Currency") field. The old pricelist_id column is
    # still physically present; use its currency as the new field's value,
    # falling back to the company currency where no pricelist was ever set.
    cr.execute("""
        UPDATE tuition_subscription s
           SET currency_id = COALESCE(
                (SELECT pl.currency_id FROM product_pricelist pl WHERE pl.id = s.pricelist_id),
                (SELECT currency_id FROM res_company ORDER BY id LIMIT 1)
           )
         WHERE currency_id IS NULL
    """)
