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
