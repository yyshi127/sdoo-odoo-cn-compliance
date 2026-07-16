from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestChinaRiskCenterDisplay(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(su=True)
        cls.country = cls.env.ref("base.cn")
        cls.currency = cls.env.ref("base.CNY")
        cls.country_pack = cls.env.ref(
            "sudo_country_pack_cn.compliance_country_pack_cn"
        )
        cls.company = cls.env["res.company"].create(
            {
                "name": "China Risk Center Display Test Company",
                "country_id": cls.country.id,
                "account_fiscal_country_id": cls.country.id,
                "currency_id": cls.currency.id,
            }
        )
        cls.profile = cls.env["sudo.compliance.profile"].with_company(
            cls.company
        ).create(
            {
                "company_id": cls.company.id,
                "country_id": cls.country.id,
                "country_pack_id": cls.country_pack.id,
            }
        )
        cls.rule = cls.env["sudo.compliance.rule"].create(
            {
                "name": "China Risk Center Display Test Rule",
                "code": "CN-RISK-DISPLAY-TEST",
                "country_id": cls.country.id,
                "domain_key": "CN.RISK.DISPLAY.TEST",
            }
        )
        cls.rule_version = cls.env["sudo.compliance.rule.version"].create(
            {
                "rule_id": cls.rule.id,
                "version": "TEST-1",
                "effective_from": "2026-01-01",
                "next_review_date": "2027-01-01",
                "evaluator_type": "manual",
                "requires_human_review": True,
            }
        )

    def _finding(self):
        assessment = self.env["sudo.compliance.assessment"].with_company(
            self.company
        ).create(
            {
                "profile_id": self.profile.id,
                "evaluation_date": "2026-07-01",
                "period_start": "2026-06-01",
                "period_end": "2026-06-30",
                "rule_version_ids": [Command.set(self.rule_version.ids)],
            }
        )
        finding = self.env["sudo.compliance.finding"]._create_engine(
            {
                "assessment_id": assessment.id,
                "rule_id": self.rule.id,
                "rule_version_id": self.rule_version.id,
                "result": "fail",
                "risk_level": "high",
                "title": "Risk center display finding",
                "summary": "A risk that should be easy to read.",
                "recommendation": "Review and remediate.",
                "evidence_required": "Keep formal evidence.",
                "requires_human_review": True,
                "result_details_json": {"affected_count": 1},
                "checksum": "c" * 64,
            }
        )
        assessment._engine_write({"state": "completed"})
        return finding

    def test_finding_exposes_period_next_action_and_evidence_status(self):
        finding = self._finding()

        self.assertIn("2026-06-01", finding.cn_risk_period_label)
        self.assertIn("2026-06-30", finding.cn_risk_period_label)
        self.assertIn("人工复核", finding.cn_risk_next_action)
        self.assertEqual(finding.cn_risk_evidence_state, "none")
        self.assertEqual(finding.cn_risk_evidence_count, 0)
        self.assertEqual(finding.cn_risk_verified_evidence_count, 0)

    def test_country_pack_advertises_risk_action_guidance(self):
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_risk_action_guidance"
            ]
        )

    def test_remediation_task_exposes_rescan_stage_and_navigation(self):
        finding = self._finding()
        task = self.env["sudo.compliance.task"].create_from_finding(finding)

        task._transition_write({"state": "pending_review"})
        self.assertEqual(task.cn_remediation_rescan_stage, "ready_for_rescan")

        task._transition_write(
            {
                "verification_state": "pending_rescan",
                "verification_assessment_id": finding.assessment_id.id,
            }
        )
        self.assertEqual(task.cn_remediation_rescan_stage, "pending_rescan")

        action = task.action_cn_open_remediation_verification_assessment()
        self.assertEqual(action["res_model"], "sudo.compliance.assessment")
        self.assertEqual(action["res_id"], finding.assessment_id.id)

    def test_country_pack_advertises_remediation_rescan_visibility(self):
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_remediation_rescan_visibility"
            ]
        )

    def test_finding_exposes_rule_basis_status_and_navigation(self):
        finding = self._finding()

        self.assertEqual(finding.cn_risk_rule_basis_state, "missing")
        self.assertEqual(finding.cn_risk_rule_source_count, 0)

        action = finding.action_cn_open_risk_rule_version()
        self.assertEqual(action["res_model"], "sudo.compliance.rule.version")
        self.assertEqual(action["res_id"], self.rule_version.id)

    def test_finding_exposes_traceability_gaps_and_evidence_navigation(self):
        finding = self._finding()

        self.assertEqual(finding.cn_traceability_state, "blocked")
        self.assertGreater(finding.cn_traceability_gap_count, 0)
        self.assertTrue(finding.cn_traceability_next_action)

        action = finding.action_cn_open_traceability_evidence()
        self.assertEqual(action["res_model"], "sudo.compliance.evidence")
        self.assertIn(("finding_id", "=", finding.id), action["domain"])

    def test_remediation_task_exposes_traceability_gaps(self):
        finding = self._finding()
        task = self.env["sudo.compliance.task"].create_from_finding(finding)

        self.assertEqual(
            task.cn_remediation_traceability_state,
            "action_required",
        )
        self.assertGreater(task.cn_remediation_traceability_gap_count, 0)

        task._transition_write({"verification_state": "pending_rescan"})
        self.assertEqual(task.cn_remediation_traceability_state, "blocked")

    def test_country_pack_advertises_risk_rule_basis_visibility(self):
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_risk_rule_basis_visibility"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_traceability_matrix_visibility"
            ]
        )
