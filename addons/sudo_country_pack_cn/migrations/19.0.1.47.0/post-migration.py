from odoo import Command, SUPERUSER_ID, api

from odoo.addons.sudo_country_pack_cn.hooks import update_country_pack_metadata


RULE_SOURCE_LINKS = {
    "rule_version_cn_cross_border_ready_001_draft": (
        "source_cn_cit_law_2018_candidate",
        "source_cn_iit_law_2018_candidate",
        "source_cn_tax_collection_law_2015_candidate",
    ),
}


def migrate(cr, _version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    update_country_pack_metadata(env)
    for version_xmlid, source_xmlids in RULE_SOURCE_LINKS.items():
        version = env.ref(
            f"sudo_country_pack_cn.{version_xmlid}",
            raise_if_not_found=False,
        )
        if (
            not version
            or version.state != "draft"
            or version.professional_review_state != "pending"
        ):
            continue
        sources = env["sudo.compliance.authority.source"]
        for source_xmlid in source_xmlids:
            source = env.ref(
                f"sudo_country_pack_cn.{source_xmlid}",
                raise_if_not_found=False,
            )
            if source:
                sources |= source
        missing_sources = sources - version.authority_source_ids
        if missing_sources:
            version.with_context(install_mode=True).write(
                {
                    "authority_source_ids": [
                        Command.link(source.id) for source in missing_sources
                    ],
                    "checksum": False,
                    "test_run_at": False,
                    "test_state": "untested",
                }
            )
