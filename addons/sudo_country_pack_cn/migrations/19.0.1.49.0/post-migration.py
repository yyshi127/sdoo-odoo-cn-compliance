def migrate(env, version):
    from odoo.addons.sudo_country_pack_cn.hooks import (
        seed_cn_obligations,
        update_country_pack_metadata,
    )

    update_country_pack_metadata(env)
    seed_cn_obligations(env)
