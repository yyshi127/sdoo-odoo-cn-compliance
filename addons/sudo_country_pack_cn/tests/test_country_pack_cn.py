from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.sudo_country_pack_cn.hooks import (
    CN_OBLIGATION_TEMPLATES,
    SETUP_DEFAULTS,
    ensure_cn_profiles,
    seed_cn_obligations,
)


@tagged("post_install", "-at_install")
class TestChinaCountryPack(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.country_cn = cls.env.ref("base.cn")
        cls.currency_cny = cls.env.ref("base.CNY")
        cls.country_pack = cls.env.ref(
            "sudo_country_pack_cn.compliance_country_pack_cn"
        )
        cls.company = cls.env["res.company"].create(
            {
                "name": "China Compliance Test Company",
                "currency_id": cls.currency_cny.id,
                "country_id": cls.country_cn.id,
                "account_fiscal_country_id": cls.country_cn.id,
            }
        )

    def _create_profile(self, company=None):
        company = company or self.company
        return self.env["sudo.compliance.profile"].with_company(company).create(
            {
                "company_id": company.id,
                "country_id": self.country_cn.id,
                "country_pack_id": self.country_pack.id,
            }
        )

    def test_country_pack_is_registered_without_active_rules(self):
        self.assertEqual(self.country_pack.code, "CN")
        self.assertEqual(self.country_pack.country_id, self.country_cn)
        setup_defaults = self.country_pack.capability_json["setup_defaults"]
        for key, value in SETUP_DEFAULTS.items():
            self.assertEqual(setup_defaults[key], value)
        self.assertEqual(setup_defaults["registration_label"], "统一社会信用代码")
        self.assertTrue(
            self.country_pack.capability_json["governance"][
                "candidate_obligations_only"
            ]
        )
        features = self.country_pack.capability_json["features"]
        self.assertTrue(features["external_dataset"])
        self.assertTrue(features["reconciliation"])
        self.assertTrue(features["reconciliation_fact_bridge"])
        self.assertTrue(features["rule_nature_governance"])
        self.assertTrue(features["cit_governed_rule_candidates"])
        self.assertTrue(features["cit_filing_settlement_archive"])
        self.assertTrue(features["iit_withholding_normalization"])
        self.assertTrue(
            self.country_pack.capability_json["governance"][
                "rule_release_requires_nature_classification"
            ]
        )
        rules = self.env["sudo.compliance.rule"].search(
            [("code", "like", "CN-%")]
        )
        self.assertEqual(len(rules), 9)
        self.assertFalse(
            rules.mapped("version_ids").filtered(
                lambda version: version.state == "active"
            )
        )

    def test_setup_wizard_uses_china_registration_defaults(self):
        defaults = self.env["sudo.compliance.setup.wizard"].with_company(
            self.company
        ).default_get(
            [
                "company_id",
                "country_id",
                "country_pack_id",
                "registration_name",
                "registration_type",
                "registration_authority",
            ]
        )

        self.assertEqual(defaults["country_id"], self.country_cn.id)
        self.assertEqual(defaults["country_pack_id"], self.country_pack.id)
        self.assertEqual(
            defaults["registration_type"], "unified_social_credit_code"
        )
        self.assertEqual(defaults["registration_authority"], "市场监督管理部门")

    def test_profile_receives_only_unknown_candidate_obligations(self):
        profile = self._create_profile()

        self.assertEqual(
            len(profile.obligation_ids), len(CN_OBLIGATION_TEMPLATES)
        )
        self.assertEqual(
            set(profile.obligation_ids.mapped("applicability")), {"unknown"}
        )
        self.assertFalse(profile.obligation_ids.mapped("authority_source_id"))
        self.assertTrue(
            all(
                "不构成申报结论" in (obligation.justification or "")
                for obligation in profile.obligation_ids
            )
        )
        self.assertTrue(profile._activation_issues())
        self.assertEqual(
            set(profile.obligation_ids.mapped("domain_key")),
            {
                "CN.ACCOUNTING",
                "CN.CIT",
                "CN.OTHER_TAXES",
                "CN.PAYROLL_IIT",
                "CN.VAT_INVOICE",
            },
        )

    def test_china_activation_requires_controlled_registration_evidence(self):
        profile = self._create_profile()
        self.assertIn(
            "未建立有效的统一社会信用代码受控登记记录",
            profile._cn_activation_issues(),
        )
        registration = self.env["sudo.compliance.registration"].create(
            {
                "name": "统一社会信用代码登记",
                "profile_id": profile.id,
                "registration_type": "unified_social_credit_code",
                "registration_number": "91310000TEST000004",
                "authority": "市场监督管理部门",
                "valid_from": "2000-01-01",
                "state": "active",
            }
        )
        self.assertIn(
            "统一社会信用代码登记尚未上传证明附件线索",
            profile._cn_activation_issues(),
        )
        attachment = self.env["ir.attachment"].create(
            {"name": "business-license.txt", "raw": b"test evidence clue"}
        )
        registration.evidence_attachment_ids = [Command.set(attachment.ids)]
        self.assertIn(
            "未建立当前有效的中国纳税人身份快照",
            profile._cn_activation_issues(),
        )
        province = self.env["res.country.state"].search(
            [("country_id", "=", self.country_cn.id)], limit=1
        )
        if not province:
            province = self.env["res.country.state"].create(
                {
                    "name": "中国合规测试辖区",
                    "code": "ZCT",
                    "country_id": self.country_cn.id,
                }
            )
        identity_attachment = self.env["ir.attachment"].create(
            {"name": "taxpayer-profile.txt", "raw": b"controlled identity"}
        )
        classification = self.env[
            "sudo.cn.taxpayer.classification"
        ].create(
            {
                "profile_id": profile.id,
                "valid_from": "2000-01-01",
                "province_id": province.id,
                "local_jurisdiction_name": "测试市辖区",
                "local_jurisdiction_code": "CN-TEST-LOCAL",
                "tax_authority_name": "测试主管税务机关",
                "vat_taxpayer_status": "general",
                "vat_filing_frequency": "monthly",
                "cit_taxpayer_status": "resident",
                "cit_collection_method": "accounts_based",
                "pit_withholding_status": "yes",
                "accounting_regime": "asbe",
                "source_type": "electronic_tax_bureau",
                "source_date": "2026-01-01",
                "source_reference": "TEST-TAXPAYER-PROFILE",
                "scope_note": "测试身份快照，仅验证档案激活门禁。",
                "evidence_attachment_ids": [
                    Command.set(identity_attachment.ids)
                ],
            }
        )
        classification.action_verify()

        self.assertFalse(profile._cn_activation_issues())

    def test_leaving_china_clears_china_registration_defaults(self):
        wizard = self.env["sudo.compliance.setup.wizard"].new(
            {
                "company_id": self.company.id,
                "country_id": self.country_cn.id,
                **SETUP_DEFAULTS,
            }
        )
        wizard.country_id = self.env.ref("base.us")

        wizard._onchange_country_id()

        self.assertEqual(wizard.registration_name, "主要公司登记")
        self.assertFalse(wizard.registration_type)
        self.assertFalse(wizard.registration_authority)

    def test_obligation_seeding_is_idempotent(self):
        profile = self._create_profile()
        before = len(profile.obligation_ids)

        seed_cn_obligations(self.env, profile)
        seed_cn_obligations(self.env, profile)

        self.assertEqual(len(profile.obligation_ids), before)
        self.assertEqual(
            len(set(profile.obligation_ids.mapped("code"))), before
        )

    def test_profiles_and_obligations_are_company_isolated(self):
        other_company = self.env["res.company"].create(
            {
                "name": "Other China Compliance Test Company",
                "currency_id": self.currency_cny.id,
                "country_id": self.country_cn.id,
                "account_fiscal_country_id": self.country_cn.id,
            }
        )
        first_profile = self._create_profile()
        second_profile = self._create_profile(other_company)

        self.assertNotEqual(first_profile.company_id, second_profile.company_id)
        self.assertEqual(
            set(first_profile.obligation_ids.mapped("code")),
            set(second_profile.obligation_ids.mapped("code")),
        )
        self.assertFalse(
            first_profile.obligation_ids
            & second_profile.obligation_ids
        )

    def test_existing_china_company_profile_initialization_is_idempotent(self):
        profiles = ensure_cn_profiles(self.env).filtered(
            lambda profile: profile.company_id == self.company
        )
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles.country_pack_id, self.country_pack)

        repeated = ensure_cn_profiles(self.env).filtered(
            lambda profile: profile.company_id == self.company
        )
        self.assertEqual(repeated, profiles)
        self.assertEqual(
            len(repeated.obligation_ids), len(CN_OBLIGATION_TEMPLATES)
        )

    def test_cn_seed_action_rejects_non_china_profile(self):
        country_us = self.env.ref("base.us")
        us_company = self.env["res.company"].create(
            {
                "name": "Non China Compliance Test Company",
                "currency_id": self.env.ref("base.USD").id,
                "country_id": country_us.id,
                "account_fiscal_country_id": country_us.id,
            }
        )
        profile = self.env["sudo.compliance.profile"].with_company(
            us_company
        ).create(
            {
                "company_id": us_company.id,
                "country_id": country_us.id,
            }
        )

        with self.assertRaises(UserError):
            profile.action_seed_cn_obligations()
