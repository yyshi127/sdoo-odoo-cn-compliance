from odoo import SUPERUSER_ID, api

from odoo.addons.sudo_country_pack_cn.hooks import update_country_pack_metadata


def migrate(cr, _version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    update_country_pack_metadata(env)
