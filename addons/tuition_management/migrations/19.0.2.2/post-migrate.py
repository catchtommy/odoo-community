# -*- coding: utf-8 -*-


def migrate(cr, version):
    # tuition_classes_per_week moved from product.template to product.product
    # (per-variant tiering, e.g. "1x/Week" vs "2x/Week" of the same subject).
    # The old template column is still physically present; copy it down to
    # every variant of that template so existing data isn't lost.
    cr.execute("""
        UPDATE product_product pp
           SET tuition_classes_per_week = pt.tuition_classes_per_week
          FROM product_template pt
         WHERE pp.product_tmpl_id = pt.id
           AND COALESCE(pp.tuition_classes_per_week, 0) = 0
           AND COALESCE(pt.tuition_classes_per_week, 0) != 0
    """)
