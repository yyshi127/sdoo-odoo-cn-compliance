from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestChinaComplianceWorkbench(TransactionCase):
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
                "name": "China Workbench Test Company",
                "currency_id": cls.currency_cny.id,
                "country_id": cls.country_cn.id,
                "account_fiscal_country_id": cls.country_cn.id,
            }
        )
        cls.profile = cls.env["sudo.compliance.profile"].with_company(
            cls.company
        ).create(
            {
                "company_id": cls.company.id,
                "country_id": cls.country_cn.id,
                "country_pack_id": cls.country_pack.id,
            }
        )
        cls.province = cls.env["res.country.state"].create(
            {
                "name": "China Workbench Test Province",
                "code": "CN-WB",
                "country_id": cls.country_cn.id,
            }
        )
        cls.foreign_country = cls.env.ref("base.us")
        cls.env.user.groups_id = [
            Command.link(cls.env.ref("sudo_global_finance.group_compliance_manager").id)
        ]

    def _classification(self, **overrides):
        attachment = self.env["ir.attachment"].create(
            {
                "name": "workbench-cross-border.txt",
                "raw": b"controlled cross border classification evidence",
            }
        )
        values = {
            "profile_id": self.profile.id,
            "valid_from": "2026-01-01",
            "province_id": self.province.id,
            "local_jurisdiction_name": "Workbench Test Local Tax Office",
            "local_jurisdiction_code": "CN-WB-LOCAL",
            "tax_authority_name": "Workbench Test Tax Authority",
            "tax_authority_code": "CN-WB-TAX",
            "vat_taxpayer_status": "general",
            "vat_filing_frequency": "monthly",
            "cit_taxpayer_status": "nonresident_no_establishment",
            "cit_collection_method": "withholding",
            "pit_withholding_status": "yes",
            "accounting_regime": "asbe",
            "source_type": "electronic_tax_bureau",
            "source_date": "2026-01-01",
            "source_reference": "WORKBENCH-CROSS-BORDER",
            "scope_note": "Controlled identity snapshot used to surface cross-border and withholding boundaries.",
            "evidence_attachment_ids": [Command.set(attachment.ids)],
        }
        values.update(overrides)
        classification = self.env["sudo.cn.taxpayer.classification"].create(values)
        classification.action_verify()
        return classification

    def _cross_border_transaction(self, **overrides):
        attachment = self.env["ir.attachment"].create(
            {
                "name": "workbench-cross-border-transaction.txt",
                "raw": b"controlled cross border transaction evidence",
            }
        )
        values = {
            "profile_id": self.profile.id,
            "period_start": "2026-01-01",
            "period_end": "2026-01-31",
            "transaction_date": "2026-01-15",
            "transaction_type": "service_fee",
            "counterparty_name": "US Service Provider",
            "counterparty_country_id": self.foreign_country.id,
            "related_party": True,
            "contract_reference": "CB-TEST-001",
            "payment_reference": "PAY-CB-001",
            "service_or_asset_location": "United States",
            "currency_id": self.currency_cny.id,
            "amount": 12000.0,
            "withholding_considered": True,
            "withholding_note": "Withholding was considered for this controlled test fact.",
            "evidence_attachment_ids": [Command.set(attachment.ids)],
        }
        values.update(overrides)
        return self.env["sudo.cn.cross.border.transaction"].create(values)

    def test_country_pack_advertises_china_workbench_feature(self):
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_compliance_workbench"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"]["china_risk_center"]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_remediation_tracker"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_report_readiness"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_evidence_center"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_process_visibility"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_workbench_tax_domain_overview"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_obligation_readiness_visibility"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_workbench_cross_border_overview"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_cross_border_transaction_register"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_cross_border_rule_facts"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_workbench_filing_archive_summary"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_workbench_state_badge_clarity"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_workbench_data_readiness_summary"
            ]
        )

    def test_workbench_summarizes_profile_setup_state(self):
        self.profile.invalidate_recordset()

        self.assertEqual(self.profile.cn_workbench_period_label, "尚未扫描")
        self.assertEqual(self.profile.cn_workbench_status, "setup_required")
        self.assertIn("完善", self.profile.cn_workbench_next_action)
        self.assertEqual(self.profile.cn_workbench_high_risk_count, 0)
        self.assertEqual(self.profile.cn_workbench_open_task_count, 0)
        self.assertEqual(self.profile.cn_workbench_underpayment_amount, 0)
        self.assertEqual(self.profile.cn_workbench_data_state, "not_started")
        self.assertEqual(self.profile.cn_workbench_dataset_count, 0)
        self.assertEqual(self.profile.cn_workbench_ready_dataset_count, 0)
        self.assertTrue(self.profile.cn_workbench_data_next_action)
        self.assertEqual(self.profile.cn_workbench_scan_state, "not_started")
        self.assertEqual(self.profile.cn_workbench_risk_state, "not_started")
        self.assertEqual(
            self.profile.cn_workbench_remediation_state,
            "not_started",
        )
        self.assertEqual(self.profile.cn_workbench_report_state, "not_started")
        self.assertEqual(self.profile.cn_workbench_evidence_state, "not_started")
        self.assertEqual(self.profile.cn_workbench_evidence_count, 0)
        self.assertEqual(self.profile.cn_workbench_verified_evidence_count, 0)
        self.assertEqual(
            self.profile.cn_workbench_filing_archive_state,
            "not_started",
        )
        self.assertEqual(self.profile.cn_workbench_filing_archive_count, 0)
        self.assertEqual(self.profile.cn_workbench_sealed_filing_archive_count, 0)
        self.assertEqual(self.profile.cn_workbench_filing_archive_issue_count, 0)
        self.assertTrue(self.profile.cn_workbench_filing_archive_next_action)
        self.assertEqual(self.profile.cn_workbench_package_label, "中国财税合规包")
        self.assertIn("增值税", self.profile.cn_workbench_scope_label)
        self.assertIn("企业所得税", self.profile.cn_workbench_scope_label)
        self.assertIn("个人所得税", self.profile.cn_workbench_scope_label)
        self.assertEqual(self.profile.cn_workbench_vat_domain_state, "not_started")
        self.assertEqual(self.profile.cn_workbench_cit_domain_state, "not_started")
        self.assertEqual(self.profile.cn_workbench_iit_domain_state, "not_started")
        self.assertTrue(self.profile.cn_workbench_vat_next_action)
        self.assertTrue(self.profile.cn_workbench_cit_next_action)
        self.assertTrue(self.profile.cn_workbench_iit_next_action)
        self.assertEqual(
            self.profile.cn_workbench_obligation_count,
            len(self.profile.obligation_ids),
        )
        self.assertEqual(self.profile.cn_workbench_obligation_state, "attention")
        self.assertEqual(self.profile.cn_workbench_pending_obligation_count, 7)
        self.assertEqual(self.profile.cn_workbench_applicable_obligation_count, 0)
        self.assertEqual(self.profile.cn_workbench_filing_obligation_count, 0)
        self.assertTrue(self.profile.cn_workbench_obligation_next_action)
        self.assertEqual(self.profile.cn_workbench_cross_border_state, "not_started")
        self.assertTrue(self.profile.cn_workbench_cross_border_basis)
        self.assertTrue(self.profile.cn_workbench_cross_border_next_action)
        self.assertEqual(self.profile.cn_workbench_cross_border_transaction_count, 0)
        self.assertEqual(self.profile.cn_workbench_cross_border_pending_count, 0)

    def test_workbench_summarizes_pending_data_readiness(self):
        self.env["sudo.cn.external.dataset"].create(
            {
                "profile_id": self.profile.id,
                "dataset_type": "vat_filing",
                "period_start": "2026-01-01",
                "period_end": "2026-01-31",
                "coverage_scope": "partial",
                "declared_record_count": 10,
                "currency_id": self.currency_cny.id,
            }
        )
        self.profile.invalidate_recordset()

        self.assertEqual(self.profile.cn_workbench_data_state, "attention")
        self.assertEqual(self.profile.cn_workbench_dataset_count, 1)
        self.assertEqual(self.profile.cn_workbench_ready_dataset_count, 0)
        self.assertIn("封存", self.profile.cn_workbench_data_next_action)

    def test_workbench_surfaces_cross_border_identity_boundary(self):
        self.profile._write_import({"status": "active"})
        classification = self._classification()

        self.profile.invalidate_recordset()

        self.assertEqual(self.profile.cn_workbench_cross_border_state, "attention")
        self.assertIn(
            classification.cit_collection_method,
            self.profile.cn_workbench_cross_border_basis,
        )
        self.assertTrue(self.profile.cn_workbench_cross_border_next_action)
        action = self.profile.action_cn_open_workbench_taxpayer_classifications()
        self.assertEqual(action["res_model"], "sudo.cn.taxpayer.classification")
        self.assertIn(("profile_id", "=", self.profile.id), action["domain"])

    def test_workbench_surfaces_cross_border_transaction_register(self):
        self.profile._write_import({"status": "active"})
        transaction = self._cross_border_transaction()

        self.profile.invalidate_recordset()

        self.assertEqual(self.profile.cn_workbench_cross_border_state, "attention")
        self.assertEqual(self.profile.cn_workbench_cross_border_transaction_count, 1)
        self.assertEqual(self.profile.cn_workbench_cross_border_pending_count, 1)
        action = self.profile.action_cn_open_workbench_cross_border_transactions()
        self.assertEqual(action["res_model"], "sudo.cn.cross.border.transaction")
        self.assertIn(("profile_id", "=", self.profile.id), action["domain"])
        self.assertEqual(transaction.cn_cross_border_readiness_state, "draft")

    def test_cross_border_transaction_review_freezes_checksum(self):
        self.profile._write_import({"status": "active"})
        transaction = self._cross_border_transaction()

        transaction.action_submit()
        self.assertEqual(transaction.state, "submitted")
        transaction.review_notes = (
            "Manager reviewed withholding consideration, evidence and limitations."
        )
        transaction.action_mark_reviewed()

        self.assertEqual(transaction.state, "reviewed")
        self.assertEqual(transaction.cn_cross_border_readiness_state, "reviewed")
        self.assertEqual(len(transaction.snapshot_checksum), 64)
        with self.assertRaises(AccessError):
            transaction.write({"amount": 13000.0})

    def test_cross_border_fact_provider_exposes_period_snapshot(self):
        self.profile._write_import({"status": "active"})
        transaction = self._cross_border_transaction()
        assessment = self.env["sudo.compliance.assessment"].with_company(
            self.company
        ).create(
            {
                "profile_id": self.profile.id,
                "evaluation_date": "2026-01-31",
                "period_start": "2026-01-01",
                "period_end": "2026-01-31",
                "note": "Cross-border fact provider test assessment.",
            }
        )
        engine = self.env["sudo.compliance.engine"]

        pending = engine._provide_cn_cross_border_pending_review_count(
            assessment,
            None,
        )
        detail = engine._provide_cn_cross_border_detail(assessment, None)
        self.assertEqual(pending["value"], 1)
        self.assertEqual(detail["value"]["schema"], "sdoo.cn.cross-border-facts.v1")
        self.assertEqual(detail["value"]["pending_transaction_ids"], transaction.ids)

        transaction.action_submit()
        transaction.review_notes = (
            "Manager reviewed withholding consideration, evidence and limitations."
        )
        transaction.action_mark_reviewed()

        pending = engine._provide_cn_cross_border_pending_review_count(
            assessment,
            None,
        )
        reviewed = engine._provide_cn_cross_border_reviewed_transaction_count(
            assessment,
            None,
        )
        detail = engine._provide_cn_cross_border_detail(assessment, None)
        self.assertEqual(pending["value"], 0)
        self.assertEqual(reviewed["value"], 1)
        self.assertIn(
            transaction.snapshot_checksum,
            detail["value"]["reviewed_snapshot_checksums"],
        )

    def test_workbench_navigation_actions_are_scoped_to_profile(self):
        action = self.profile.action_cn_open_workbench_assessments()
        self.assertEqual(action["res_model"], "sudo.compliance.assessment")
        self.assertIn(("profile_id", "=", self.profile.id), action["domain"])

        finding_action = self.profile.action_cn_open_workbench_findings()
        self.assertEqual(finding_action["res_model"], "sudo.compliance.finding")
        self.assertIn(
            ("assessment_id.profile_id", "=", self.profile.id),
            finding_action["domain"],
        )

        task_action = self.profile.action_cn_open_workbench_tasks()
        self.assertEqual(task_action["res_model"], "sudo.compliance.task")
        self.assertIn(
            ("assessment_id.profile_id", "=", self.profile.id),
            task_action["domain"],
        )
        self.assertIn(("task_type", "=", "remediation"), task_action["domain"])

        report_action = self.profile.action_cn_open_workbench_reports()
        self.assertEqual(report_action["res_model"], "sudo.cn.compliance.report")
        self.assertIn(("profile_id", "=", self.profile.id), report_action["domain"])

        readiness_action = self.profile.action_cn_open_workbench_report_readiness()
        self.assertEqual(readiness_action["res_model"], "sudo.compliance.assessment")
        self.assertIn(("profile_id", "=", self.profile.id), readiness_action["domain"])

        evidence_action = self.profile.action_cn_open_workbench_evidence_center()
        self.assertEqual(evidence_action["res_model"], "sudo.compliance.evidence")
        self.assertIn(("company_id", "=", self.company.id), evidence_action["domain"])

        cross_border_action = self.profile.action_cn_open_workbench_cross_border_transactions()
        self.assertEqual(
            cross_border_action["res_model"],
            "sudo.cn.cross.border.transaction",
        )
        self.assertIn(("profile_id", "=", self.profile.id), cross_border_action["domain"])

        obligation_action = self.profile.action_cn_open_workbench_obligations()
        self.assertEqual(obligation_action["res_model"], "sudo.compliance.obligation")
        self.assertIn(("profile_id", "=", self.profile.id), obligation_action["domain"])

        filing_action = self.profile.action_cn_open_workbench_filing_center()
        self.assertEqual(filing_action["res_model"], "sudo.compliance.filing")
        self.assertIn(("profile_id", "=", self.profile.id), filing_action["domain"])

    def test_workbench_marks_obligation_readiness_after_review(self):
        source = self.env.ref(
            "sudo_country_pack_cn.source_cn_tax_collection_law_2015_candidate"
        )
        self.profile.obligation_ids.write(
            {
                "applicability": "not_applicable",
                "authority_source_id": source.id,
                "justification": "Reviewed as not applicable for the controlled workbench test.",
            }
        )
        vat_obligation = self.profile.obligation_ids.filtered(
            lambda obligation: obligation.code == "CN-VAT"
        )
        vat_obligation.write(
            {
                "applicability": "applicable",
                "justification": "Reviewed as applicable for the controlled workbench test.",
            }
        )

        self.profile.invalidate_recordset()

        self.assertEqual(self.profile.cn_workbench_obligation_state, "ready")
        self.assertEqual(self.profile.cn_workbench_pending_obligation_count, 0)
        self.assertEqual(self.profile.cn_workbench_applicable_obligation_count, 1)
        self.assertEqual(self.profile.cn_workbench_filing_obligation_count, 1)
