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

    def test_workbench_summarizes_profile_setup_state(self):
        self.profile.invalidate_recordset()

        self.assertEqual(self.profile.cn_workbench_period_label, "尚未扫描")
        self.assertEqual(self.profile.cn_workbench_status, "setup_required")
        self.assertIn("完善", self.profile.cn_workbench_next_action)
        self.assertEqual(self.profile.cn_workbench_high_risk_count, 0)
        self.assertEqual(self.profile.cn_workbench_open_task_count, 0)
        self.assertEqual(self.profile.cn_workbench_underpayment_amount, 0)

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
