# -*- coding: utf-8 -*-


def migrate(cr, version):
    cr.execute("""
        UPDATE tuition_plan_line
           SET currency_id = (
                SELECT currency_id FROM res_company ORDER BY id LIMIT 1
           )
         WHERE currency_id IS NULL
    """)
    cr.execute("""
        UPDATE tuition_subscription
           SET pricelist_id = (
                SELECT pl.id FROM product_pricelist pl
                JOIN res_company c ON c.currency_id = pl.currency_id
                WHERE pl.company_id IS NULL OR pl.company_id = c.id
                ORDER BY pl.id LIMIT 1
           )
         WHERE pricelist_id IS NULL
    """)
