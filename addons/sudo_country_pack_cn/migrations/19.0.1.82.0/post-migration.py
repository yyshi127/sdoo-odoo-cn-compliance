from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.sudo_country_pack_cn.hooks import (
        ensure_cn_vat_reconciliation_rule_fact_links,
        update_country_pack_metadata,
    )

    update_country_pack_metadata(env)
    ensure_cn_vat_reconciliation_rule_fact_links(env)
