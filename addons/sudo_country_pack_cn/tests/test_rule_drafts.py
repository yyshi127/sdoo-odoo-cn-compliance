from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestChinaRuleDrafts(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.versions = cls.env["sudo.compliance.rule.version"].browse(
            [
                cls.env.ref(
                    "sudo_country_pack_cn.rule_version_cn_base_reg_001_draft"
                ).id,
                cls.env.ref(
                    "sudo_country_pack_cn.rule_version_cn_acc_period_001_draft"
                ).id,
                cls.env.ref(
                    "sudo_country_pack_cn.rule_version_cn_vat_inv_ready_001_draft"
                ).id,
                cls.env.ref(
                    "sudo_country_pack_cn.rule_version_cn_acc_evidence_001_draft"
                ).id,
                cls.env.ref(
                    "sudo_country_pack_cn.rule_version_cn_profile_tax_001_draft"
                ).id,
            ]
        )

    def test_packaged_china_rules_remain_unpublished_drafts(self):
        self.assertEqual(set(self.versions.mapped("state")), {"draft"})
        self.assertEqual(
            set(self.versions.mapped("professional_review_state")),
            {"pending"},
        )
        self.assertFalse(self.versions.mapped("authority_source_ids"))
        self.assertFalse(
            self.env["sudo.compliance.rule.version"].search_count(
                [
                    ("rule_id.code", "like", "CN-%"),
                    ("state", "=", "active"),
                ]
            )
        )

    def test_all_packaged_draft_cases_evaluate_as_expected(self):
        cases = self.versions.mapped("test_case_ids")
        self.assertEqual(len(cases), 10)
        for case in cases:
            self.assertTrue(case._run_case(), case.display_name)
            self.assertEqual(case.last_result, case.expected_result)
            self.assertEqual(case.test_status, "passed")

    def test_drafts_cannot_pass_publish_gate_without_official_sources(self):
        for version in self.versions:
            with self.assertRaises(UserError):
                version._check_publish_gate()

    def test_drafts_are_not_selected_for_formal_assessment(self):
        country = self.env.ref("base.cn")
        company = self.env["res.company"].create(
            {
                "name": "China Draft Rule Selection Test Company",
                "currency_id": self.env.ref("base.CNY").id,
                "country_id": country.id,
                "account_fiscal_country_id": country.id,
            }
        )
        profile = self.env["sudo.compliance.profile"].with_company(
            company
        ).create(
            {
                "company_id": company.id,
                "country_id": country.id,
                "country_pack_id": self.env.ref(
                    "sudo_country_pack_cn.compliance_country_pack_cn"
                ).id,
            }
        )
        assessment = self.env["sudo.compliance.assessment"].create(
            {
                "profile_id": profile.id,
                "evaluation_date": "2026-07-15",
                "period_start": "2026-01-01",
                "period_end": "2026-06-30",
            }
        )

        selected = self.env["sudo.compliance.engine"]._select_versions(
            assessment
        )

        self.assertFalse(selected & self.versions)
