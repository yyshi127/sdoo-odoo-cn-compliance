from odoo import fields


PACK_VERSION = "19.0.1.37.0"

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
