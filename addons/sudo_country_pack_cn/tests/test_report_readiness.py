from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestChinaReportReadiness(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.country_cn = cls.env.ref("base.cn")
        cls.currency_cny = cls.env.ref("base.CNY")
        cls.country_pack = cls.env.ref(
            "sudo_country_pack_cn.compliance_country_pack_cn"
        )
        cls.env = cls.env(su=True)
        cls.company = cls.env["res.company"].create(
            {
                "name": "China Report Readiness Test Company",
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
        cls.rule = cls.env["sudo.compliance.rule"].create(
            {
                "code": "CN-REPORT-READINESS-RESCAN",
                "name": "Report readiness rescan gate",
                "country_id": cls.country_cn.id,
                "domain_key": "CN.VAT_INVOICE",
            }
        )
    def _assessment(self, state="completed"):
        assessment = self.env["sudo.compliance.assessment"].with_company(
            self.company
        ).create(
            {
                "profile_id": self.profile.id,
                "evaluation_date": "2026-07-01",
                "period_start": "2026-06-01",
                "period_end": "2026-06-30",
            }
        )
        if state == "completed":
            assessment._engine_write({"state": "completed"})
        return assessment

    def _finding(self, assessment, suffix):
        rule_version = self.env["sudo.compliance.rule.version"].create(
            {
                "rule_id": self.rule.id,
                "version": f"TEST-{suffix}",
                "effective_from": "2026-01-01",
                "next_review_date": "2027-01-01",
                "evaluator_type": "manual",
                "requires_human_review": True,
            }
        )
        return self.env["sudo.compliance.finding"]._create_engine(
            {
                "assessment_id": assessment.id,
                "rule_id": self.rule.id,
                "rule_version_id": rule_version.id,
                "result": "fail",
                "risk_level": "high",
                "title": f"Report readiness rescan finding {suffix}",
                "summary": "Synthetic finding for report readiness rescan gate.",
                "recommendation": "Complete remediation and verification rescan.",
                "evidence_required": "Keep remediation evidence and rescan result.",
                "requires_human_review": True,
                "checksum": (suffix[:1] or "r") * 64,
            }
        )

    def test_completed_clean_assessment_discloses_limitations(self):
        assessment = self._assessment()
        assessment.invalidate_recordset()

        self.assertEqual(assessment.cn_report_readiness_state, "limited")
        self.assertTrue(assessment.cn_report_can_prepare)
        self.assertGreater(assessment.cn_report_issue_count, 0)
        self.assertIn("limitations", assessment.cn_report_next_action)

    def test_incomplete_assessment_requires_scan_completion(self):
        assessment = self._assessment(state="draft")
        assessment.invalidate_recordset()

        self.assertEqual(assessment.cn_report_readiness_state, "needs_scan")
        self.assertFalse(assessment.cn_report_can_prepare)
        self.assertIn("rule scan", assessment.cn_report_next_action)

    def test_country_pack_advertises_report_readiness_badge_clarity(self):
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_report_readiness_badge_clarity"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_report_rescan_gate"
            ]
        )

    def test_report_readiness_blocks_pending_or_failed_rescans(self):
        assessment = self._assessment()
        pending_finding = self._finding(assessment, "pending")
        failed_finding = self._finding(assessment, "failed")
        verified_finding = self._finding(assessment, "verified")
        pending = self.env["sudo.compliance.task"].create_from_finding(
            pending_finding
        )
        failed = self.env["sudo.compliance.task"].create_from_finding(
            failed_finding
        )
        verified = self.env["sudo.compliance.task"].create_from_finding(
            verified_finding
        )
        for finding in pending_finding | failed_finding | verified_finding:
            finding.write({"review_notes": "Reviewed for rescan gate test."})
            finding.action_confirm_review()
        pending._transition_write(
            {
                "state": "pending_review",
                "verification_state": "pending_rescan",
                "verification_assessment_id": assessment.id,
            }
        )
        failed._transition_write(
            {
                "state": "pending_review",
                "verification_state": "failed",
                "verification_assessment_id": assessment.id,
            }
        )
        verified._transition_write(
            {
                "state": "done",
                "verification_state": "verified",
                "verification_assessment_id": assessment.id,
            }
        )
        assessment.invalidate_recordset()

        self.assertEqual(assessment.cn_report_readiness_state, "needs_remediation")
        self.assertFalse(assessment.cn_report_can_prepare)
        self.assertEqual(assessment.cn_report_rescan_state, "failed")
        self.assertEqual(assessment.cn_report_pending_rescan_count, 1)
        self.assertEqual(assessment.cn_report_failed_rescan_count, 1)
        self.assertEqual(assessment.cn_report_verified_remediation_count, 1)
        self.assertIn("failed", assessment.cn_report_rescan_next_action)

    def test_readiness_navigation_actions_are_scoped_to_assessment(self):
        assessment = self._assessment()

        finding_action = assessment.action_cn_open_report_readiness_findings()
        self.assertEqual(finding_action["res_model"], "sudo.compliance.finding")
        self.assertIn(("assessment_id", "=", assessment.id), finding_action["domain"])

        task_action = assessment.action_cn_open_report_readiness_tasks()
        self.assertEqual(task_action["res_model"], "sudo.compliance.task")
        self.assertIn(("assessment_id", "=", assessment.id), task_action["domain"])
