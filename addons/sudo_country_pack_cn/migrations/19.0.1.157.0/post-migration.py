from odoo import SUPERUSER_ID, api

from odoo.addons.sudo_country_pack_cn.hooks import update_country_pack_metadata


CHECKSUM_MODELS = (
    (
        "sudo.cn.vat.account.mapping",
        "cn_vat_account_mapping.canonical_checksum_migrated",
    ),
    (
        "sudo.cn.cit.accounting.scope",
        "cn_cit_accounting_scope.canonical_checksum_migrated",
    ),
    (
        "sudo.cn.iit.accounting.scope",
        "cn_iit_accounting_scope.canonical_checksum_migrated",
    ),
)


def _language_codes(env):
    codes = {"en_US", "zh_CN"}
    codes.update(
        env["res.lang"]
        .with_context(active_test=False)
        .search([])
        .mapped("code")
    )
    return sorted(code for code in codes if code)


def _migrate_checksum(env, record, event_key, languages):
    old_checksum = record.verification_checksum
    if not old_checksum:
        return
    canonical_checksum = record._current_checksum()
    if old_checksum == canonical_checksum:
        return
    matched_language = next(
        (
            language
            for language in languages
            if record._checksum_for_language(language) == old_checksum
        ),
        None,
    )
    if not matched_language:
        return

    env.cr.execute(
        f"""
            UPDATE {record._table}
               SET verification_checksum = %s
             WHERE id = %s
               AND verification_checksum = %s
        """,
        (canonical_checksum, record.id, old_checksum),
    )
    if not env.cr.rowcount:
        return
    record.invalidate_recordset(["verification_checksum"])
    env["sudo.compliance.audit.event"]._log_records(
        record,
        event_key,
        previous_state="verified",
        new_state="verified",
        details={
            "reason": "locale_independent_checksum_upgrade",
            "matched_legacy_language": matched_language,
            "previous_checksum": old_checksum,
            "canonical_language": "en_US",
            "canonical_checksum": canonical_checksum,
        },
    )


def migrate(cr, _version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    languages = _language_codes(env)
    for model_name, event_key in CHECKSUM_MODELS:
        records = (
            env[model_name]
            .sudo()
            .with_context(active_test=False)
            .search(
                [
                    ("state", "=", "verified"),
                    ("verification_checksum", "!=", False),
                ]
            )
        )
        for record in records:
            _migrate_checksum(
                env,
                record.with_company(record.company_id),
                event_key,
                languages,
            )
    update_country_pack_metadata(env)
