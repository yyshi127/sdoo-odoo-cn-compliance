from odoo import fields


PACK_VERSION = "19.0.1.142.0"

SETUP_DEFAULTS = {
    "registration_name": "统一社会信用代码登记",
    "registration_type": "unified_social_credit_code",
    "registration_authority": "市场监督管理部门",
}

# These are candidate obligations, not published legal conclusions. They remain
# unknown until an official source and company-level applicability are reviewed.
CN_OBLIGATION_TEMPLATES = (
    {
        "code": "CN-VAT",
        "name": "增值税申报与缴纳",
        "domain_key": "CN.VAT_INVOICE",
        "authority": "主管税务机关",
        "filing_required": True,
        "filing_frequency": "other",
        "filing_type": "cn_vat_return",
    },
    {
        "code": "CN-CIT",
        "name": "企业所得税预缴与年度汇算清缴",
        "domain_key": "CN.CIT",
        "authority": "主管税务机关",
        "filing_required": True,
        "filing_frequency": "other",
        "filing_type": "cn_cit_return",
    },
    {
        "code": "CN-IIT-WHT",
        "name": "个人所得税扣缴申报",
        "domain_key": "CN.PAYROLL_IIT",
        "authority": "主管税务机关",
        "filing_required": True,
        "filing_frequency": "other",
        "filing_type": "cn_iit_withholding_return",
    },
    {
        "code": "CN-SURCHARGE",
        "name": "附加税费申报",
        "domain_key": "CN.OTHER_TAXES",
        "authority": "主管税务机关",
        "filing_required": True,
        "filing_frequency": "other",
        "filing_type": "cn_surcharge_return",
    },
    {
        "code": "CN-STAMP-DUTY",
        "name": "印花税申报",
        "domain_key": "CN.OTHER_TAXES",
        "authority": "主管税务机关",
        "filing_required": True,
        "filing_frequency": "other",
        "filing_type": "cn_stamp_duty_return",
    },
    {
        "code": "CN-SOCIAL-INSURANCE",
        "name": "社会保险费申报缴纳",
        "domain_key": "CN.PAYROLL_IIT",
        "authority": "主管征收及社会保险经办机构",
        "filing_required": True,
        "filing_frequency": "other",
        "filing_type": "cn_social_insurance_return",
    },
    {
        "code": "CN-RECORDS",
        "name": "财税资料与电子凭证留存",
        "domain_key": "CN.ACCOUNTING",
        "authority": "主管财政及税务机关",
        "filing_required": False,
        "filing_frequency": "ongoing",
        "filing_type": False,
    },
)


def post_init_hook(env):
    update_country_pack_metadata(env)
    ensure_cn_accounting_rule_fact_links(env)
    ensure_cn_vat_reconciliation_rule_fact_links(env)
    ensure_cn_cit_reconciliation_rule_fact_links(env)
    ensure_cn_iit_reconciliation_rule_fact_links(env)
    profiles = ensure_cn_profiles(env)
    seed_cn_obligations(env, profiles)


def country_pack_capabilities():
    return {
        "schema_version": 1,
        "setup_defaults": {
            **SETUP_DEFAULTS,
            "registration_label": "统一社会信用代码",
        },
        "authority_classes": [
            "财政部门",
            "税务机关",
            "市场监督管理部门",
            "社会保险经办机构",
        ],
        "domains": [
            "identity",
            "accounting",
            "vat_invoice",
            "cit",
            "payroll_iit",
            "other_taxes",
            "cross_border",
            "filing_payment",
        ],
        "engine": "sudo.compliance.engine",
        "features": {
            "jurisdiction": True,
            "jurisdiction_governance": True,
            "local_rule_scope": True,
            "external_dataset": True,
            "einvoice_normalized_ledger": True,
            "einvoice_xbrl_parser": False,
            "reconciliation": True,
            "vat_period_reconciliation": True,
            "reconciliation_fact_bridge": True,
            "filing_control": True,
            "controlled_ai": True,
            "china_controlled_ai_guidance": True,
            "china_ai_guidance_visibility": True,
            "china_ai_obligation_context": True,
            "china_ai_filing_archive_context": True,
            "china_ai_fact_and_evidence_context": True,
            "china_ai_data_basis_context": True,
            "china_ai_risk_resolution_context": True,
            "china_report_ai_guidance_snapshot": True,
            "china_report_evidence_link_snapshot": True,
            "china_report_risk_closure_snapshot": True,
            "source_governance": True,
            "rule_nature_governance": True,
            "tax_impact_review": True,
            "vat_adjustment_report": True,
            "formal_compliance_report": True,
            "china_report_readiness": True,
            "china_evidence_center": True,
            "china_process_visibility": True,
            "china_risk_action_guidance": True,
            "china_filing_center": True,
            "china_data_readiness_center": True,
            "china_assessment_data_basis": True,
            "china_assessment_accounting_basis": True,
            "china_accounting_ledger_basis_fact": True,
            "china_vat_reconciliation_risk_summary_fact": True,
            "china_cit_reconciliation_risk_summary_fact": True,
            "china_iit_reconciliation_risk_summary_fact": True,
            "china_reconciliation_risk_visibility": True,
            "china_assessment_required_dataset_type_coverage": True,
            "china_assessment_obligation_basis": True,
            "china_remediation_rescan_visibility": True,
            "china_remediation_progress_visibility": True,
            "china_remediation_tax_impact_visibility": True,
            "china_risk_rule_basis_visibility": True,
            "china_report_center_visibility": True,
            "china_report_obligation_readiness": True,
            "china_report_remediation_verification": True,
            "china_report_rescan_gate": True,
            "china_report_filing_archive_gate": True,
            "china_report_current_rule_governance_gate": True,
            "china_report_ai_guidance_readiness": True,
            "china_filing_archive_field_label_clarity": True,
            "china_report_filing_archive_snapshot": True,
            "china_report_fact_basis_visibility": True,
            "china_report_data_basis_snapshot": True,
            "china_traceability_matrix_visibility": True,
            "china_workbench_tax_domain_overview": True,
            "china_obligation_readiness_visibility": True,
            "china_workbench_cross_border_overview": True,
            "china_cross_border_transaction_register": True,
            "china_cross_border_rule_facts": True,
            "china_cross_border_risk_visibility": True,
            "china_risk_fact_basis_visibility": True,
            "china_risk_data_basis_visibility": True,
            "china_risk_tax_impact_visibility": True,
            "china_risk_closure_status_summary": True,
            "china_remediation_responsibility_visibility": True,
            "china_workbench_filing_archive_summary": True,
            "china_workbench_state_badge_clarity": True,
            "china_risk_card_state_badge_clarity": True,
            "china_report_readiness_badge_clarity": True,
            "china_archive_evidence_badge_clarity": True,
            "china_formal_report_badge_clarity": True,
            "china_data_readiness_badge_clarity": True,
            "china_workbench_data_readiness_summary": True,
            "china_workbench_accounting_ledger_basis": True,
            "china_workbench_remediation_rescan_summary": True,
            "china_workbench_ai_guidance_summary": True,
            "china_workbench_closed_loop_readiness": True,
            "china_workbench_conclusion_boundary": True,
            "china_workbench_next_best_action": True,
            "china_delivery_acceptance_runner": True,
            "china_delivery_manifest_audit": True,
            "china_delivery_acceptance_profiles": True,
            "china_delivery_acceptance_summary": True,
            "china_delivery_bundle_builder": True,
            "china_delivery_artifact_verifier": True,
            "china_delivery_runbook": True,
            "china_delivery_preview_access_runbook": True,
            "china_delivery_status_summary": True,
            "china_delivery_objective_coverage": True,
            "china_business_uat_checklist": True,
            "china_production_signoff_template": True,
            "china_delivery_preview_health_checker": True,
            "china_delivery_index": True,
            "china_delivery_readiness_gates": True,
            "china_delivery_preview_health_gate": True,
            "china_delivery_preview_url_match_gate": True,
            "china_delivery_strict_readiness_exit": True,
            "china_delivery_source_control_traceability": True,
            "china_delivery_source_control_clean_gate": True,
            "china_delivery_commit_consistency_gate": True,
            "china_delivery_preview_module_gate": True,
            "china_real_data_closed_loop_checker": True,
            "china_controlled_demo_profile_preparer": True,
            "china_controlled_demo_closed_loop_preparer": True,
            "vat_filing_payment_archive": True,
            "cit_filing_normalization": True,
            "cit_accounting_reconciliation": True,
            "cit_governed_rule_candidates": True,
            "cit_filing_settlement_archive": True,
            "iit_withholding_normalization": True,
            "payroll_summary_normalization": True,
            "iit_accounting_reconciliation": True,
            "iit_governed_rule_candidates": True,
            "iit_filing_settlement_archive": True,
            "official_source_change_monitoring": True,
            "china_compliance_workbench": True,
            "china_risk_center": True,
            "china_remediation_tracker": True,
            "multi_company": True,
        },
        "governance": {
            "rule_release_requires_professional_signoff": True,
            "rule_release_requires_nature_classification": True,
            "candidate_obligations_only": True,
        },
    }


def update_country_pack_metadata(env):
    country_pack = env.ref(
        "sudo_country_pack_cn.compliance_country_pack_cn",
        raise_if_not_found=False,
    )
    if country_pack:
        country_pack.write(
            {
                "version": PACK_VERSION,
                "capability_json": country_pack_capabilities(),
            }
        )
    return country_pack


def ensure_cn_accounting_rule_fact_links(env):
    version = env.ref(
        "sudo_country_pack_cn.rule_version_cn_acc_period_001_draft",
        raise_if_not_found=False,
    )
    if not version:
        return False
    facts = env["sudo.compliance.fact.definition"].browse()
    for xmlid in (
        "sudo_country_pack_cn.fact_cn_unposted_move_count_v1",
        "sudo_country_pack_cn.fact_cn_posted_move_count_v1",
        "sudo_country_pack_cn.fact_cn_posted_invoice_count_v1",
        "sudo_country_pack_cn.fact_cn_account_ledger_basis_detail_v1",
    ):
        fact = env.ref(xmlid, raise_if_not_found=False)
        if fact:
            facts |= fact
    if facts:
        version.write({"required_fact_ids": [(6, 0, facts.ids)]})
    return True


def ensure_cn_vat_reconciliation_rule_fact_links(env):
    version = env.ref(
        "sudo_country_pack_cn.rule_version_cn_vat_reconciliation_ready_001_draft",
        raise_if_not_found=False,
    )
    if not version:
        return False
    facts = env["sudo.compliance.fact.definition"].browse()
    for xmlid in (
        "sudo_country_pack_cn.fact_cn_vat_reconciliation_conclusion_state_v1",
        "sudo_country_pack_cn.fact_cn_vat_reconciliation_blocking_count_v1",
        "sudo_country_pack_cn.fact_cn_vat_reconciliation_difference_count_v1",
        "sudo_country_pack_cn.fact_cn_vat_reconciliation_warning_count_v1",
        "sudo_country_pack_cn.fact_cn_vat_reconciliation_detail_v1",
        "sudo_country_pack_cn.fact_cn_vat_reconciliation_risk_summary_v1",
    ):
        fact = env.ref(xmlid, raise_if_not_found=False)
        if fact:
            facts |= fact
    if facts:
        version.write({"required_fact_ids": [(6, 0, facts.ids)]})
    return True


def _ensure_cn_reconciliation_rule_fact_links(env, version_xmlids, fact_xmlids):
    facts = env["sudo.compliance.fact.definition"].browse()
    for xmlid in fact_xmlids:
        fact = env.ref(xmlid, raise_if_not_found=False)
        if fact:
            facts |= fact
    if not facts:
        return False
    updated = False
    for version_xmlid in version_xmlids:
        version = env.ref(version_xmlid, raise_if_not_found=False)
        if version:
            version.write({"required_fact_ids": [(6, 0, facts.ids)]})
            updated = True
    return updated


def ensure_cn_cit_reconciliation_rule_fact_links(env):
    return _ensure_cn_reconciliation_rule_fact_links(
        env,
        (
            "sudo_country_pack_cn.rule_version_cn_cit_reconciliation_ready_001_draft",
            "sudo_country_pack_cn.rule_version_cn_cit_reconciliation_control_001_draft",
        ),
        (
            "sudo_country_pack_cn.fact_cn_cit_reconciliation_conclusion_state_v1",
            "sudo_country_pack_cn.fact_cn_cit_reconciliation_blocking_count_v1",
            "sudo_country_pack_cn.fact_cn_cit_reconciliation_difference_count_v1",
            "sudo_country_pack_cn.fact_cn_cit_reconciliation_warning_count_v1",
            "sudo_country_pack_cn.fact_cn_cit_reconciliation_detail_v1",
            "sudo_country_pack_cn.fact_cn_cit_reconciliation_risk_summary_v1",
        ),
    )


def ensure_cn_iit_reconciliation_rule_fact_links(env):
    return _ensure_cn_reconciliation_rule_fact_links(
        env,
        (
            "sudo_country_pack_cn.rule_version_cn_iit_reconciliation_ready_001_draft",
            "sudo_country_pack_cn.rule_version_cn_iit_reconciliation_control_001_draft",
        ),
        (
            "sudo_country_pack_cn.fact_cn_iit_reconciliation_conclusion_state_v1",
            "sudo_country_pack_cn.fact_cn_iit_reconciliation_blocking_count_v1",
            "sudo_country_pack_cn.fact_cn_iit_reconciliation_difference_count_v1",
            "sudo_country_pack_cn.fact_cn_iit_reconciliation_warning_count_v1",
            "sudo_country_pack_cn.fact_cn_iit_reconciliation_detail_v1",
            "sudo_country_pack_cn.fact_cn_iit_reconciliation_risk_summary_v1",
        ),
    )


def ensure_cn_profiles(env):
    country = env.ref("base.cn", raise_if_not_found=False)
    country_pack = env.ref(
        "sudo_country_pack_cn.compliance_country_pack_cn",
        raise_if_not_found=False,
    )
    if not country or not country_pack:
        return env["sudo.compliance.profile"]

    companies = env["res.company"].search(
        [
            "|",
            ("partner_id.country_id", "=", country.id),
            ("account_fiscal_country_id", "=", country.id),
        ]
    )
    profile_model = env["sudo.compliance.profile"]
    profiles = profile_model
    for company in companies:
        profile = profile_model.search(
            [
                ("company_id", "=", company.id),
                ("country_id", "=", country.id),
            ],
            limit=1,
        )
        if profile:
            if not profile.country_pack_id:
                profile.country_pack_id = country_pack
            profiles |= profile
            continue

        profiles |= profile_model.create(
            {
                "company_id": company.id,
                "country_id": country.id,
                "country_pack_id": country_pack.id,
                "fiscal_year_end_month": int(
                    company.fiscalyear_last_month or 12
                ),
                "fiscal_year_end_day": int(company.fiscalyear_last_day or 31),
                "notes": (
                    "由中国财税合规国家包初始化。请核实企业登记、纳税人身份、"
                    "适用辖区、财年依据和各项候选义务；未确认前不得启用正式扫描。"
                ),
            }
        )
    return profiles


def seed_cn_obligations(env, profiles=None):
    country = env.ref("base.cn", raise_if_not_found=False)
    if not country:
        return env["sudo.compliance.obligation"]

    if profiles is None:
        profiles = env["sudo.compliance.profile"].search(
            [("country_id", "=", country.id), ("active", "=", True)]
        )
    else:
        profiles = profiles.filtered(lambda profile: profile.country_id == country)

    obligation_model = env["sudo.compliance.obligation"].sudo()
    created = obligation_model
    for profile in profiles:
        existing_codes = set(
            obligation_model.search(
                [("profile_id", "=", profile.id)]
            ).mapped("code")
        )
        tracking_start = fields.Date.context_today(profile)
        for template in CN_OBLIGATION_TEMPLATES:
            if template["code"] in existing_codes:
                continue
            values = dict(template)
            values.update(
                {
                    "profile_id": profile.id,
                    "applicability": "unknown",
                    "effective_from": tracking_start,
                    "justification": (
                        "中国国家包初始化的候选义务。尚未完成官方来源治理、"
                        "公司级适用性判断和专业签核，不构成申报结论。"
                    ),
                }
            )
            created |= obligation_model.create(values)
            existing_codes.add(template["code"])
    return created
