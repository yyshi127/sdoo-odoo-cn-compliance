from odoo import api, SUPERUSER_ID

def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    from odoo.addons.sudo_country_pack_cn.hooks import update_country_pack_metadata

    update_country_pack_metadata(env)
