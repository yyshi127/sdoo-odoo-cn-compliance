from odoo import SUPERUSER_ID, api

from odoo.addons.sudo_country_pack_cn.hooks import update_country_pack_metadata
from odoo.addons.sudo_country_pack_cn.models.rule_governance import (
    backfill_cn_rule_natures,
)


def migrate(cr, _version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    backfill_cn_rule_natures(env)
    update_country_pack_metadata(env)
