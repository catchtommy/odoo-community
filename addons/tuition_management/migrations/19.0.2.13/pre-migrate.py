# -*- coding: utf-8 -*-


def migrate(cr, version):
    # tutor.payment.run.payment_timezone is new. Runs created before it were
    # calculated with UTC period bounds, so record that instead of letting the
    # ORM fill them with the field's default.
    cr.execute("SELECT to_regclass('tutor_payment_run')")
    if not cr.fetchone()[0]:
        return
    cr.execute("ALTER TABLE tutor_payment_run ADD COLUMN IF NOT EXISTS payment_timezone varchar")
    cr.execute("UPDATE tutor_payment_run SET payment_timezone = 'UTC' WHERE payment_timezone IS NULL")
