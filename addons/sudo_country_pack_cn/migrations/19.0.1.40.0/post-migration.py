def migrate(env, version):
    from odoo.addons.sudo_country_pack_cn.hooks import update_country_pack_metadata

    update_country_pack_metadata(env)
