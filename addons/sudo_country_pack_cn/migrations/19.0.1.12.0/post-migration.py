from odoo import SUPERUSER_ID, api

from odoo.addons.sudo_country_pack_cn.hooks import (
    update_country_pack_metadata,
)


def migrate(cr, _version):
    cr.execute(
        """
            UPDATE sudo_cn_vat_period_reconciliation_run
               SET accounting_basis = 'invoice_tax_totals',
                   invoice_output_tax_amount = ledger_output_tax_amount,
                   invoice_input_tax_amount = ledger_input_tax_amount
             WHERE engine_version = '19.0.1'
        """
    )
    env = api.Environment(cr, SUPERUSER_ID, {})
    update_country_pack_metadata(env)
