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
                cls.env.ref(
                    "sudo_country_pack_cn."
                    "rule_version_cn_cit_reconciliation_ready_001_draft"
                ).id,
                cls.env.ref(
                    "sudo_country_pack_cn."
                    "rule_version_cn_cit_reconciliation_control_001_draft"
                ).id,
                cls.env.ref(
                    "sudo_country_pack_cn."
                    "rule_version_cn_iit_reconciliation_ready_001_draft"
                ).id,
                cls.env.ref(
                    "sudo_country_pack_cn."
                    "rule_version_cn_iit_reconciliation_control_001_draft"
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
                cls.env.ref(
                    "sudo_country_pack_cn.source_cn_cit_law_2018_candidate"
                ).id,
                cls.env.ref(
                    "sudo_country_pack_cn."
                    "source_cn_cit_regulation_2024_candidate"
                ).id,
                cls.env.ref(
                    "sudo_country_pack_cn.source_cn_iit_law_2018_candidate"
                ).id,
                cls.env.ref(
                    "sudo_country_pack_cn."
                    "source_cn_iit_regulation_2018_candidate"
                ).id,
                cls.env.ref(
                    "sudo_country_pack_cn."
                    "source_cn_iit_withholding_measures_2018_candidate"
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

    def test_packaged_rules_have_explicit_non_statutory_natures(self):
        expected = {
            "CN-BASE-REG-001": "data_readiness",
            "CN-ACC-PERIOD-001": "internal_control",
            "CN-VAT-INV-READY-001": "data_readiness",
            "CN-ACC-EVIDENCE-001": "internal_control",
            "CN-PROFILE-TAX-001": "data_readiness",
            "CN-DATA-EINV-RECON-001": "data_readiness",
            "CN-DATA-VAT-RECON-001": "data_readiness",
            "CN-DATA-CIT-RECON-001": "data_readiness",
            "CN-CIT-RECON-CTRL-001": "internal_control",
            "CN-DATA-IIT-RECON-001": "data_readiness",
            "CN-IIT-RECON-CTRL-001": "internal_control",
        }
        actual = {
            version.rule_id.code: version.cn_rule_nature
            for version in self.versions
        }

        self.assertEqual(actual, expected)
        self.assertTrue(all(self.versions.mapped("requires_human_review")))
        self.assertTrue(
            all(
                "cn_rule_nature" in version._checksum_payload()
                for version in self.versions
            )
        )

    def test_release_readiness_exposes_all_current_blockers(self):
        self.assertEqual(
            set(self.versions.mapped("cn_release_state")),
            {"source_governance"},
        )
        self.assertFalse(any(self.versions.mapped("cn_governance_ready")))
        for version in self.versions:
            self.assertIn("官方来源", version.cn_release_blockers)
            self.assertIn("规则测试", version.cn_release_blockers)
            self.assertIn("专业签核", version.cn_release_blockers)

    def test_rule_nature_is_immutable_after_a_version_exists(self):
        rule = self.versions[0].rule_id
        replacement = (
            "internal_control"
            if rule.cn_rule_nature == "data_readiness"
            else "data_readiness"
        )

        with self.assertRaisesRegex(UserError, "不能改写规则性质"):
            rule.write({"cn_rule_nature": replacement})

    def test_china_publish_gate_requires_rule_nature(self):
        rule = self.env["sudo.compliance.rule"].create(
            {
                "name": "未分类中国测试规则",
                "code": "CN-TEST-NATURE-MISSING",
                "country_id": self.env.ref("base.cn").id,
                "domain_key": "CN.TEST",
            }
        )
        version = self.env["sudo.compliance.rule.version"].create(
            {
                "rule_id": rule.id,
                "version": "DRAFT-TEST",
                "effective_from": "2026-01-01",
                "next_review_date": "2026-12-31",
                "evaluator_type": "manual",
                "requires_human_review": True,
            }
        )

        with self.assertRaisesRegex(UserError, "必须明确规则性质"):
            version._check_publish_gate()

    def test_control_rule_publish_gate_requires_human_review(self):
        rule = self.env["sudo.compliance.rule"].create(
            {
                "name": "无人工复核边界测试规则",
                "code": "CN-TEST-REVIEW-MISSING",
                "country_id": self.env.ref("base.cn").id,
                "domain_key": "CN.TEST",
                "cn_rule_nature": "data_readiness",
            }
        )
        version = self.env["sudo.compliance.rule.version"].create(
            {
                "rule_id": rule.id,
                "version": "DRAFT-TEST",
                "effective_from": "2026-01-01",
                "next_review_date": "2026-12-31",
                "evaluator_type": "manual",
                "requires_human_review": False,
            }
        )

        with self.assertRaisesRegex(UserError, "必须设置人工复核"):
            version._check_publish_gate()

    def test_overdue_official_source_blocks_china_publish_gate(self):
        version = self.versions[0]
        source = version.authority_source_ids[0]
        source.write({"next_review_date": "2000-01-01"})

        with self.assertRaisesRegex(UserError, "超过复核日期"):
            version._check_publish_gate()

    def test_official_url_candidates_remain_ungoverned_drafts(self):
        expected_urls = {
            "source_cn_accounting_law_2024_candidate": (
                "https://kjs.mof.gov.cn/zhengcefabu/202408/"
                "t20240812_3941615.htm"
            ),
            "source_cn_accounting_archives_order_79_candidate": (
                "https://www.gov.cn/gongbao/content/2016/"
                "content_5041555.htm"
            ),
            "source_cn_vat_law_2024_candidate": (
                "https://fgk.chinatax.gov.cn/zcfgk/c100009/"
                "c5237365/content.html"
            ),
            "source_cn_vat_regulation_order_826_candidate": (
                "https://fgk.chinatax.gov.cn/zcfgk/c100010/"
                "c5246349/content.html"
            ),
            "source_cn_invoice_measures_2023_candidate": (
                "https://fgk.chinatax.gov.cn/zcfgk/c100010/"
                "c5195084/content.html"
            ),
            "source_cn_tax_collection_law_2015_candidate": (
                "https://fgk.chinatax.gov.cn/zcfgk/c100009/"
                "c5195081/content.html"
            ),
            "source_cn_electronic_voucher_standard_2025_candidate": (
                "https://www.mof.gov.cn/jrttts/202505/"
                "t20250521_3964264.htm"
            ),
            "source_cn_cit_law_2018_candidate": (
                "https://fgk.chinatax.gov.cn/zcfgk/c100009/"
                "c5193018/content.html"
            ),
            "source_cn_cit_regulation_2024_candidate": (
                "https://xzfg.moj.gov.cn/law/download?LawID=1741&type=pdf"
            ),
            "source_cn_iit_law_2018_candidate": (
                "https://fgk.chinatax.gov.cn/zcfgk/c100009/"
                "c5193028/content.html"
            ),
            "source_cn_iit_regulation_2018_candidate": (
                "https://www.chinatax.gov.cn/chinatax/n810219/n810744/"
                "n3752930/n3752974/c3963364/content.html"
            ),
            "source_cn_iit_withholding_measures_2018_candidate": (
                "https://www.chinatax.gov.cn/chinatax/n810341/n810765/"
                "n3359382/201812/c4182700/content.html"
            ),
        }
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
        for xml_id, expected_url in expected_urls.items():
            source = self.env.ref(f"sudo_country_pack_cn.{xml_id}")
            self.assertEqual(source.official_url, expected_url)

    def test_all_packaged_draft_cases_evaluate_as_expected(self):
        cases = self.versions.mapped("test_case_ids")
        self.assertEqual(len(cases), 28)
        for case in cases:
            self.assertTrue(case._run_case(), case.display_name)
            self.assertEqual(case.last_result, case.expected_result)
            self.assertEqual(case.test_status, "passed")

    def test_cit_control_handler_preserves_tri_state_reason_codes(self):
        version = self.env.ref(
            "sudo_country_pack_cn."
            "rule_version_cn_cit_reconciliation_control_001_draft"
        )
        scenarios = (
            ("aligned", 0, 0, 0, "pass", "controlled_amounts_aligned"),
            (
                "differences",
                0,
                2,
                0,
                "fail",
                "differences_require_review",
            ),
            (
                "insufficient_data",
                2,
                0,
                0,
                "unknown",
                "data_not_comparable",
            ),
            (
                "aligned",
                0,
                0,
                1,
                "unknown",
                "warnings_require_review",
            ),
            (
                "aligned",
                0,
                1,
                0,
                "unknown",
                "inconsistent_reconciliation_state",
            ),
            (
                "aligned",
                -1,
                0,
                0,
                "unknown",
                "invalid_fact_payload",
            ),
        )
        engine = self.env["sudo.compliance.engine"]
        for state, blocking, differences, warnings, result, reason in scenarios:
            output = engine.evaluate_rule_payload(
                version,
                {
                    "cn.reconciliation.cit.conclusion_state": state,
                    "cn.reconciliation.cit.blocking_issue_count": blocking,
                    "cn.reconciliation.cit.difference_issue_count": differences,
                    "cn.reconciliation.cit.warning_issue_count": warnings,
                    "cn.reconciliation.cit.detail": {},
                },
                {},
            )
            self.assertEqual(output["result"], result)
            self.assertEqual(output["details"]["reason"], reason)
            self.assertTrue(output["requires_human_review"])

    def test_iit_control_handler_preserves_tri_state_reason_codes(self):
        version = self.env.ref(
            "sudo_country_pack_cn."
            "rule_version_cn_iit_reconciliation_control_001_draft"
        )
        scenarios = (
            ("aligned", 0, 0, 0, "pass", "controlled_amounts_aligned"),
            (
                "differences",
                0,
                2,
                0,
                "fail",
                "differences_require_review",
            ),
            (
                "insufficient_data",
                2,
                0,
                0,
                "unknown",
                "data_not_comparable",
            ),
            (
                "aligned",
                0,
                0,
                1,
                "unknown",
                "warnings_require_review",
            ),
            (
                "aligned",
                0,
                1,
                0,
                "unknown",
                "inconsistent_reconciliation_state",
            ),
            (
                "aligned",
                -1,
                0,
                0,
                "unknown",
                "invalid_fact_payload",
            ),
        )
        engine = self.env["sudo.compliance.engine"]
        for state, blocking, differences, warnings, result, reason in scenarios:
            output = engine.evaluate_rule_payload(
                version,
                {
                    "cn.reconciliation.iit.conclusion_state": state,
                    "cn.reconciliation.iit.blocking_issue_count": blocking,
                    "cn.reconciliation.iit.difference_issue_count": differences,
                    "cn.reconciliation.iit.warning_issue_count": warnings,
                    "cn.reconciliation.iit.detail": {},
                },
                {},
            )
            self.assertEqual(output["result"], result)
            self.assertEqual(output["details"]["reason"], reason)
            self.assertTrue(output["requires_human_review"])

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
