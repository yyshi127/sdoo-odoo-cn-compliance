from odoo import Command, SUPERUSER_ID, api

from odoo.addons.sudo_country_pack_cn.hooks import (
    update_country_pack_metadata,
)


RULE_SOURCE_LINKS = {
    "rule_version_cn_base_reg_001_draft": (
        "source_cn_tax_collection_law_2015_candidate",
    ),
    "rule_version_cn_acc_period_001_draft": (
        "source_cn_accounting_law_2024_candidate",
    ),
    "rule_version_cn_vat_inv_ready_001_draft": (
        "source_cn_vat_law_2024_candidate",
        "source_cn_vat_regulation_order_826_candidate",
        "source_cn_invoice_measures_2023_candidate",
    ),
    "rule_version_cn_acc_evidence_001_draft": (
        "source_cn_accounting_law_2024_candidate",
        "source_cn_accounting_archives_order_79_candidate",
        "source_cn_electronic_voucher_standard_2025_candidate",
    ),
    "rule_version_cn_profile_tax_001_draft": (
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
        if not missing_sources:
            continue
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
