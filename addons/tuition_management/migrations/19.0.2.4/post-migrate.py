# -*- coding: utf-8 -*-


def migrate(cr, version):
    # tuition_subscription.company_id is new. Where a subscription already has
    # invoices, infer its company from the most recent one (more accurate than
    # blindly defaulting everyone to the installing company); otherwise fall
    # back to the first company.
    cr.execute("""
        UPDATE tuition_subscription s
           SET company_id = COALESCE(
                (SELECT am.company_id
                   FROM account_move_tuition_subscription_rel rel
                   JOIN account_move am ON am.id = rel.move_id
                  WHERE rel.subscription_id = s.id
                  ORDER BY am.id DESC LIMIT 1),
                (SELECT id FROM res_company ORDER BY id LIMIT 1)
           )
         WHERE company_id IS NULL
    """)
