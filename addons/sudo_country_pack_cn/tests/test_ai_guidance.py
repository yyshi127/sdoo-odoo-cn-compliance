from odoo import Command, fields
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

    def _finding(self, source_warning=False, missing_fact_keys=None):
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
                "source_warning": source_warning,
                "professional_warning": False,
                "missing_fact_keys": missing_fact_keys or [],
                "result_details_json": {"affected_count": 1},
                "checksum": "b" * 64,
            }
        )
        assessment._engine_write({"state": "completed"})
        return finding

    def _fact_snapshot(
        self,
        finding,
        suffix="base",
        quality_state="complete",
        key=None,
        value=1,
        value_type="integer",
    ):
        key = key or f"cn.ai.guidance.fact.{finding.id}.{suffix}"
        definition = self.env["sudo.compliance.fact.definition"].search(
            [("key", "=", key)], limit=1
        )
        if not definition:
            definition = self.env["sudo.compliance.fact.definition"].create(
                {
                    "name": f"AI guidance fact {suffix}",
                    "label": f"AI guidance fact {suffix}",
                    "key": key,
                    "version": "TEST-1",
                    "country_id": self.country.id,
                    "value_type": value_type,
                    "provider_key": f"ai_guidance_fact_{suffix}",
                    "provider_version": "1",
                    "source_model": "account.move",
                    "source_description": "Controlled AI guidance test fact.",
                    "completeness_method": "full_domain",
                }
            )
        snapshot = self.env["sudo.compliance.fact.snapshot"]._create_engine(
            {
                "assessment_id": finding.assessment_id.id,
                "definition_id": definition.id,
                "value_json": value,
                "captured_at": fields.Datetime.now(),
                "source_model": "account.move",
                "source_domain_json": [("company_id", "=", self.company.id)],
                "record_count": 1,
                "aggregation_method": "controlled_test",
                "is_complete": quality_state == "complete",
                "is_full_dataset": quality_state == "complete",
                "quality_state": quality_state,
                "provider_key": definition.provider_key,
                "provider_version": "1",
                "checksum": suffix[:1].ljust(64, "a"),
            }
        )
        self.env.cr.execute(
            """
            INSERT INTO sudo_compliance_finding_fact_snapshot_rel
                        (finding_id, snapshot_id)
                 VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            (finding.id, snapshot.id),
        )
        finding.invalidate_recordset()
        return snapshot

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
        self.assertIn("data_basis", analysis.input_snapshot_json)
        self.assertIn("filing_archive", analysis.input_snapshot_json)
        self.assertEqual(
            analysis.input_snapshot_json["obligation_readiness"]["state"],
            "attention",
        )
        self.assertEqual(
            analysis.input_snapshot_json["filing_archive"]["state"],
            "not_started",
        )
        self.assertEqual(
            analysis.input_snapshot_json["data_basis"]["state"],
            "missing",
        )
        self.assertGreater(
            analysis.input_snapshot_json["data_basis"]["missing_type_count"],
            0,
        )
        self.assertIn("Data basis: state=missing", analysis.analysis)
        self.assertIn("Electronic invoices", analysis.analysis)
        self.assertEqual(
            analysis.input_snapshot_json["obligation_readiness"][
                "pending_review_count"
            ],
            len(self.profile.obligation_ids),
        )
        self.assertIn("Filing/payment archive", analysis.analysis)
        self.assertEqual(finding.cn_ai_guidance_state, "generated")
        self.assertEqual(
            finding.cn_ai_guidance_input_checksum,
            analysis.input_checksum,
        )

    def test_ai_guidance_visibility_marks_limited_inputs(self):
        self._reset_obligations()
        finding = self._finding(
            source_warning=True,
            missing_fact_keys=["cn.missing.fact"],
        )
        finding.invalidate_recordset()

        self.assertEqual(finding.cn_ai_guidance_state, "limited")
        self.assertTrue(finding.cn_ai_guidance_next_action)
        self.assertTrue(finding.cn_ai_guidance_input_checksum)

    def test_ai_guidance_includes_fact_basis_and_remediation_evidence(self):
        self._reset_obligations()
        finding = self._finding()
        self._fact_snapshot(finding, "complete")
        self._fact_snapshot(
            finding,
            "vat_recon",
            key="cn.reconciliation.vat.risk_summary",
            value={
                "risk_status": "difference_review_required",
                "next_action": "Review VAT differences before report sign-off.",
                "counts": {
                    "difference_count": 2,
                    "blocking_issue_count": 1,
                    "warning_issue_count": 1,
                },
                "material_differences": {"output_tax": "88.00"},
                "top_issues": [{"code": "VAT-AI-DIFF"}],
            },
            value_type="json",
        )
        task = self.env["sudo.compliance.task"].create_from_finding(finding)
        evidence = self.env["sudo.compliance.evidence"].create(
            {
                "name": "AI guidance remediation proof",
                "company_id": self.company.id,
                "task_id": task.id,
                "evidence_type": "remediation_proof",
                "external_reference": "DMS/CN/AI-GUIDANCE-001",
            }
        )
        evidence.action_submit()
        evidence.review_notes = (
            "Reviewed controlled remediation evidence for AI guidance context."
        )
        evidence.action_verify()
        finding.invalidate_recordset()

        payload = finding._cn_ai_guidance_input()
        self.assertEqual(payload["fact_basis"]["state"], "ready")
        self.assertEqual(payload["fact_basis"]["snapshot_count"], 2)
        self.assertEqual(payload["fact_basis"]["issue_count"], 0)
        self.assertEqual(payload["remediation_evidence"]["state"], "verified")
        self.assertEqual(payload["remediation_evidence"]["evidence_count"], 1)
        self.assertEqual(
            payload["remediation_evidence"]["verified_evidence_count"],
            1,
        )
        self.assertEqual(
            payload["reconciliation_risk"]["state"],
            "difference_review_required",
        )
        self.assertIn("VAT-AI-DIFF", payload["reconciliation_risk"]["summary"])
        self.assertEqual(payload["tax_impact"]["state"], "none")
        self.assertEqual(payload["remediation_progress"]["progress"], 33)
        self.assertIn("证据已验证 1/1", payload["remediation_progress"]["summary"])

        action = finding.with_user(self.user).action_generate_cn_ai_guidance()
        analysis = self.env["sudo.compliance.ai.analysis"].browse(
            action["res_id"]
        )
        self.assertIn("Fact basis: state=ready", analysis.analysis)
        self.assertIn("Reconciliation risk: state=difference_review_required", analysis.analysis)
        self.assertIn("Tax impact: state=none", analysis.analysis)
        self.assertIn(
            "Remediation evidence: state=verified",
            analysis.analysis,
        )
        self.assertIn("Remediation progress: progress=33%", analysis.analysis)
        self.assertEqual(
            analysis.input_snapshot_json["remediation_evidence"]["state"],
            "verified",
        )
        self.assertEqual(
            analysis.input_snapshot_json["reconciliation_risk"]["state"],
            "difference_review_required",
        )

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
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_ai_filing_archive_context"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_ai_fact_and_evidence_context"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_ai_data_basis_context"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_ai_risk_resolution_context"
            ]
        )

    def test_ai_guidance_stays_limited_until_filing_archives_exist(self):
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

        self.assertEqual(finding.cn_ai_guidance_state, "limited")
        payload = finding._cn_ai_guidance_input()
        self.assertEqual(payload["obligation_readiness"]["state"], "ready")
        self.assertEqual(payload["obligation_readiness"]["pending_review_count"], 0)
        self.assertEqual(payload["filing_archive"]["state"], "not_started")
