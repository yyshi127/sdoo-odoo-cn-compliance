from odoo import api, SUPERUSER_ID

def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.sudo_country_pack_cn.hooks import (
        seed_cn_obligations,
        update_country_pack_metadata,
    )

    update_country_pack_metadata(env)
    seed_cn_obligations(env)
