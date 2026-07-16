from odoo.addons.sudo_country_pack_cn.hooks import update_country_pack_metadata


def migrate(env, version):
    update_country_pack_metadata(env)
