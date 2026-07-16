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

    def test_completed_clean_assessment_is_report_ready(self):
        assessment = self._assessment()
        assessment.invalidate_recordset()

        self.assertEqual(assessment.cn_report_readiness_state, "ready")
        self.assertTrue(assessment.cn_report_can_prepare)
        self.assertEqual(assessment.cn_report_issue_count, 0)
        self.assertIn("正式合规报告", assessment.cn_report_next_action)

    def test_incomplete_assessment_requires_scan_completion(self):
        assessment = self._assessment(state="draft")
        assessment.invalidate_recordset()

        self.assertEqual(assessment.cn_report_readiness_state, "needs_scan")
        self.assertFalse(assessment.cn_report_can_prepare)
        self.assertIn("规则扫描", assessment.cn_report_next_action)

    def test_country_pack_advertises_report_readiness_badge_clarity(self):
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_report_readiness_badge_clarity"
            ]
        )

    def test_readiness_navigation_actions_are_scoped_to_assessment(self):
        assessment = self._assessment()

        finding_action = assessment.action_cn_open_report_readiness_findings()
        self.assertEqual(finding_action["res_model"], "sudo.compliance.finding")
        self.assertIn(("assessment_id", "=", assessment.id), finding_action["domain"])

        task_action = assessment.action_cn_open_report_readiness_tasks()
        self.assertEqual(task_action["res_model"], "sudo.compliance.task")
        self.assertIn(("assessment_id", "=", assessment.id), task_action["domain"])
