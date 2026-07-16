from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestChinaControlledAiGuidance(TransactionCase):
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
                "name": "China AI Guidance Test Company",
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
                "name": "China AI Guidance Test Rule",
                "code": "CN-AI-GUIDANCE-TEST",
                "country_id": cls.country.id,
                "domain_key": "CN.AI.GUIDANCE.TEST",
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
        cls.user = cls.env["res.users"].create(
            {
                "name": "China AI Guidance User",
                "login": "cn_ai_guidance_user",
                "company_id": cls.company.id,
                "company_ids": [Command.set(cls.company.ids)],
                "group_ids": [
                    Command.set(
                        cls.env.ref(
                            "sudo_global_finance.group_compliance_user"
                        ).ids
                    )
                ],
            }
        )

    def _reset_obligations(self):
        self.profile.obligation_ids.write(
            {
                "applicability": "unknown",
                "authority_source_id": False,
                "justification": "Reset for controlled AI guidance test isolation.",
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
                "title": "AI guidance controlled finding",
                "summary": "A controlled risk summary.",
                "legal_basis": "Official source basis snapshot.",
                "recommendation": "Review facts and remediate.",
                "evidence_required": "Keep controlled evidence.",
                "requires_human_review": True,
                "source_warning": False,
                "professional_warning": False,
                "result_details_json": {"affected_count": 1},
                "checksum": "b" * 64,
            }
        )
        assessment._engine_write({"state": "completed"})
        return finding

    def test_generate_controlled_ai_guidance_snapshot(self):
        self._reset_obligations()
        finding = self._finding()

        self.assertEqual(finding.cn_ai_guidance_state, "limited")
        self.assertTrue(finding.cn_ai_guidance_next_action)
        self.assertTrue(finding.cn_ai_guidance_input_checksum)

        action = finding.with_user(self.user).action_generate_cn_ai_guidance()
        analysis = self.env["sudo.compliance.ai.analysis"].browse(
            action["res_id"]
        )
        finding.invalidate_recordset()

        self.assertEqual(analysis.finding_id, finding)
        self.assertEqual(analysis.provider_key, "sdoo_cn_controlled_guidance")
        self.assertEqual(analysis.jurisdiction_code, "CN")
        self.assertEqual(analysis.state, "fallback")
        self.assertEqual(analysis.prompt_version, "cn-compliance-guidance-v1")
        self.assertTrue(analysis.input_checksum)
        self.assertTrue(analysis.output_checksum)
        self.assertTrue(analysis.record_checksum)
        self.assertIn("AI 分析仅为辅助材料", analysis.analysis)
        self.assertEqual(analysis.input_snapshot_json["rule_code"], self.rule.code)
        self.assertIn("obligation_readiness", analysis.input_snapshot_json)
        self.assertEqual(
            analysis.input_snapshot_json["obligation_readiness"]["state"],
            "attention",
        )
        self.assertEqual(
            analysis.input_snapshot_json["obligation_readiness"][
                "pending_review_count"
            ],
            len(self.profile.obligation_ids),
        )
        self.assertEqual(finding.cn_ai_guidance_state, "generated")
        self.assertEqual(
            finding.cn_ai_guidance_input_checksum,
            analysis.input_checksum,
        )

    def test_ai_guidance_visibility_marks_limited_inputs(self):
        self._reset_obligations()
        finding = self._finding()
        finding._engine_write(
            {
                "source_warning": True,
                "missing_fact_keys": ["cn.missing.fact"],
            }
        )
        finding.invalidate_recordset()

        self.assertEqual(finding.cn_ai_guidance_state, "limited")
        self.assertTrue(finding.cn_ai_guidance_next_action)
        self.assertTrue(finding.cn_ai_guidance_input_checksum)

    def test_country_pack_advertises_controlled_ai_guidance(self):
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_controlled_ai_guidance"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_ai_guidance_visibility"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_ai_obligation_context"
            ]
        )

    def test_ai_guidance_marks_ready_after_obligations_are_reviewed(self):
        self._reset_obligations()
        source = self.env.ref(
            "sudo_country_pack_cn.source_cn_tax_collection_law_2015_candidate"
        )
        self.profile.obligation_ids.write(
            {
                "applicability": "not_applicable",
                "authority_source_id": source.id,
                "justification": "Reviewed as not applicable for the controlled AI guidance test.",
            }
        )
        finding = self._finding()

        self.assertEqual(finding.cn_ai_guidance_state, "ready")
        payload = finding._cn_ai_guidance_input()
        self.assertEqual(payload["obligation_readiness"]["state"], "ready")
        self.assertEqual(payload["obligation_readiness"]["pending_review_count"], 0)
