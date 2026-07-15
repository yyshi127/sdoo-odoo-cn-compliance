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
                cls.env.ref(
                    "sudo_country_pack_cn."
                    "rule_version_cn_einvoice_reconciliation_ready_001_draft"
                ).id,
                cls.env.ref(
                    "sudo_country_pack_cn."
                    "rule_version_cn_vat_reconciliation_ready_001_draft"
                ).id,
            ]
        )
        cls.sources = cls.env["sudo.compliance.authority.source"].browse(
            [
                cls.env.ref(
                    "sudo_country_pack_cn."
                    "source_cn_accounting_law_2024_candidate"
                ).id,
                cls.env.ref(
                    "sudo_country_pack_cn."
                    "source_cn_accounting_archives_order_79_candidate"
                ).id,
                cls.env.ref(
                    "sudo_country_pack_cn.source_cn_vat_law_2024_candidate"
                ).id,
                cls.env.ref(
                    "sudo_country_pack_cn."
                    "source_cn_vat_regulation_order_826_candidate"
                ).id,
                cls.env.ref(
                    "sudo_country_pack_cn."
                    "source_cn_invoice_measures_2023_candidate"
                ).id,
                cls.env.ref(
                    "sudo_country_pack_cn."
                    "source_cn_tax_collection_law_2015_candidate"
                ).id,
                cls.env.ref(
                    "sudo_country_pack_cn."
                    "source_cn_electronic_voucher_standard_2025_candidate"
                ).id,
            ]
        )

    def test_packaged_china_rules_remain_unpublished_drafts(self):
        self.assertEqual(set(self.versions.mapped("state")), {"draft"})
        self.assertEqual(
            set(self.versions.mapped("professional_review_state")),
            {"pending"},
        )
        self.assertTrue(
            all(version.authority_source_ids for version in self.versions)
        )
        self.assertEqual(
            set(self.versions.mapped("authority_source_ids").ids),
            set(self.sources.ids),
        )
        self.assertFalse(
            self.env["sudo.compliance.rule.version"].search_count(
                [
                    ("rule_id.code", "like", "CN-%"),
                    ("state", "=", "active"),
                ]
            )
        )

    def test_official_url_candidates_remain_ungoverned_drafts(self):
        self.assertEqual(set(self.sources.mapped("status")), {"draft"})
        self.assertEqual(set(self.sources.mapped("snapshot_kind")), {"other"})
        self.assertTrue(
            all(not source.content_hash for source in self.sources)
        )
        self.assertTrue(
            all(not source.snapshot_attachment_id for source in self.sources)
        )
        self.assertTrue(all(not source.reviewer_id for source in self.sources))
        self.assertTrue(
            all(not source.reviewed_at for source in self.sources)
        )
        self.assertEqual(
            set(self.sources.mapped("country_id").ids),
            {self.env.ref("base.cn").id},
        )
        self.assertTrue(
            all(
                source.official_url.startswith("https://")
                for source in self.sources
            )
        )

    def test_all_packaged_draft_cases_evaluate_as_expected(self):
        cases = self.versions.mapped("test_case_ids")
        self.assertEqual(len(cases), 14)
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
