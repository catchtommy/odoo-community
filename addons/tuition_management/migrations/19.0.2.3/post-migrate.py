# -*- coding: utf-8 -*-


def migrate(cr, version):
    # tuition_subscription.pricelist_id ("Billing Pricelist") was replaced by a
    # direct currency_id ("Currency") field, and pricelist_id itself moved down
    # to tuition_plan_line. Derive the new field's value from a plan line's
    # pricelist where one exists, falling back to the company currency.
    cr.execute("""
        UPDATE tuition_subscription s
           SET currency_id = COALESCE(
                (SELECT pl.currency_id
                   FROM tuition_plan_line tpl
                   JOIN product_pricelist pl ON pl.id = tpl.pricelist_id
                  WHERE tpl.subscription_id = s.id
                  ORDER BY tpl.id DESC LIMIT 1),
                (SELECT currency_id FROM res_company ORDER BY id LIMIT 1)
           )
         WHERE currency_id IS NULL
    """)
