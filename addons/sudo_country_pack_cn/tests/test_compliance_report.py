from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestChinaFormalComplianceReport(TransactionCase):
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
                "name": "China Formal Report Test Company",
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
                "name": "正式报告测试规则",
                "code": "CN-REPORT-TEST",
                "country_id": cls.country.id,
                "domain_key": "CN.REPORT.TEST",
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
        manager_group = cls.env.ref(
            "sudo_global_finance.group_compliance_manager"
        )
        user_group = cls.env.ref(
            "sudo_global_finance.group_compliance_user"
        )
        approver_group = cls.env.ref(
            "sudo_country_pack_cn.group_cn_report_approver"
        )
        cls.manager = cls._user(
            "cn_report_manager",
            "China Report Manager",
            manager_group,
        )
        cls.approver = cls._user(
            "cn_report_approver",
            "China Report Approver",
            approver_group,
        )
        cls.reader = cls._user(
            "cn_report_reader",
            "China Report Reader",
            user_group,
        )
        cls.same_person = cls._user(
            "cn_report_same_person",
            "China Report Same Person",
            manager_group | approver_group,
        )

    @classmethod
    def _user(cls, login, name, groups, company=None):
        company = company or cls.company
        return cls.env["res.users"].create(
            {
                "name": name,
                "login": login,
                "company_id": company.id,
                "company_ids": [Command.set(company.ids)],
                "group_ids": [Command.set(groups.ids)],
            }
        )

    def setUp(self):
        super().setUp()
        self.assessment, self.finding = self._assessment("base")

    def _assessment(
        self,
        suffix,
        *,
        result="fail",
        source_warning=False,
        professional_warning=False,
        review=True,
    ):
        assessment = self.env["sudo.compliance.assessment"].with_company(
            self.company
        ).create(
            {
                "profile_id": self.profile.id,
                "evaluation_date": "2026-07-01",
                "period_start": "2026-06-01",
                "period_end": "2026-06-30",
                "rule_version_ids": [Command.set(self.rule_version.ids)],
                "note": "正式报告测试评估说明。",
            }
        )
        finding = self.env["sudo.compliance.finding"]._create_engine(
            {
                "assessment_id": assessment.id,
                "rule_id": self.rule.id,
                "rule_version_id": self.rule_version.id,
                "result": result,
                "risk_level": "high" if result == "fail" else "medium",
                "title": f"正式报告测试结论 {suffix}",
                "summary": "根据受控事实快照形成的测试专业结论。",
                "legal_basis": "测试规则依据快照。",
                "recommendation": "核对事实并完成受控整改复核。",
                "evidence_required": "保存复核工作底稿和整改证据。",
                "requires_human_review": True,
                "source_warning": source_warning,
                "professional_warning": professional_warning,
                "professional_snapshot_json": {
                    "state": "approved" if not professional_warning else "pending"
                },
                "source_snapshot_json": [
                    {
                        "name": "测试官方来源快照",
                        "status": "valid" if not source_warning else "pending_review",
                    }
                ],
                "result_details_json": {"affected_count": 1},
                "checksum": (suffix.encode().hex() + "a" * 64)[:64],
            }
        )
        assessment._engine_write(
            {
                "state": "completed",
                "started_at": "2026-07-01 09:00:00",
                "completed_at": "2026-07-01 09:01:00",
            }
        )
        if review:
            finding.with_user(self.manager).write(
                {"review_notes": "已核对规则事实与报告边界，需要进入整改流程。"}
            )
            finding.with_user(self.manager).action_require_correction()
        return assessment, finding

    def _fact_snapshot(
        self,
        finding,
        suffix="base",
        quality_state="complete",
        key=None,
        value=1,
        value_type="integer",
    ):
        key = key or f"cn.report.fact.{finding.id}.{suffix}"
        definition = self.env["sudo.compliance.fact.definition"].search(
            [("key", "=", key)], limit=1
        )
        if not definition:
            definition = self.env["sudo.compliance.fact.definition"].create(
                {
                    "name": f"Formal report fact {suffix}",
                    "label": f"Formal report fact {suffix}",
                    "key": key,
                    "version": "TEST-1",
                    "country_id": self.country.id,
                    "value_type": value_type,
                    "provider_key": f"formal_report_fact_{suffix}",
                    "provider_version": "1",
                    "source_model": "account.move",
                    "source_description": "Controlled formal report test fact.",
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
                "checksum": suffix[:1].ljust(64, "f"),
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

    def _reviewed_tax_impact_case(
        self,
        finding,
        *,
        direction="potential_underpayment",
        amount=240.0,
    ):
        attachment = self.env["ir.attachment"].with_user(self.manager).create(
            {
                "name": "formal-report-tax-impact.txt",
                "raw": b"formal report tax impact evidence",
            }
        )
        case = self.env["sudo.cn.tax.impact.case"].with_user(
            self.manager
        ).with_company(self.company).create(
            {
                "title": "Formal report tax impact case",
                "profile_id": self.profile.id,
                "period_start": finding.assessment_id.period_start,
                "period_end": finding.assessment_id.period_end,
                "assessment_id": finding.assessment_id.id,
                "finding_ids": [Command.set(finding.ids)],
                "impact_direction": direction,
                "quantification_state": "preliminary",
                "impact_amount": amount,
                "analysis": (
                    "Controlled report test analysis explains the tax impact calculation."
                ),
                "assumptions_limitations": (
                    "Controlled report assumptions and limitations are documented."
                ),
                "source_reference": "REPORT-TAX-IMPACT-TEST",
                "evidence_attachment_ids": [Command.set(attachment.ids)],
            }
        )
        case.with_user(self.manager).action_submit()
        case.with_user(self.same_person).write(
            {
                "review_notes": (
                    "Independent controlled review confirms report tax impact amount."
                )
            }
        )
        case.with_user(self.same_person).action_review()
        return case

    def _verified_report_evidence(self, finding):
        task = self.env["sudo.compliance.task"].with_user(
            self.manager
        ).create_from_finding(finding)
        evidence = self.env["sudo.compliance.evidence"].with_user(
            self.reader
        ).with_company(self.company).create(
            {
                "name": "Formal report remediation evidence",
                "company_id": self.company.id,
                "task_id": task.id,
                "evidence_type": "remediation_proof",
                "external_reference": "DMS/CN/REPORT-EVIDENCE-001",
                "evidence_date": "2026-07-12",
                "issuer": "Controlled test evidence issuer",
            }
        )
        evidence.with_user(self.reader).action_submit()
        evidence.with_user(self.manager).write(
            {"review_notes": "Controlled evidence verified for report traceability."}
        )
        evidence.with_user(self.manager).action_verify()
        return evidence, task

    def _report(self, assessment=None, preparer=None, reviewer=None, **values):
        assessment = assessment or self.assessment
        preparer = preparer or self.manager
        reviewer = reviewer or self.approver
        defaults = {
            "title": "中国财税合规管理正式报告",
            "assessment_id": assessment.id,
            "executive_summary": (
                "本报告汇总受控规则扫描、人工复核、整改状态和税务影响，"
                "供管理层在限定范围内决策。"
            ),
            "scope_statement": (
                "报告覆盖测试公司二零二六年六月期间、已冻结规则版本、"
                "Odoo 事实快照及报告中列示的证据。"
            ),
            "limitation_statement": (
                "测试环境中的中国候选纳税义务仍需逐项确认适用性和官方来源；"
                "本报告仅按当前受控配置披露限制，不替代真实申报判断。"
            ),
            "management_response": (
                "管理层已指定责任人核对高风险事项，并按整改任务期限补充证据后复扫。"
            ),
            "reviewer_id": reviewer.id,
        }
        defaults.update(values)
        return self.env["sudo.cn.compliance.report"].with_user(
            preparer
        ).with_company(self.company).create(defaults)

    def _issue(self, report, approver=None, pdf=None):
        approver = approver or self.approver
        pdf = pdf or b"%PDF-1.4\nSdoo governed report\n%%EOF"
        report.with_user(approver).write(
            {
                "review_notes": (
                    "已独立核验报告范围、源快照、复核状态、限制和结论边界，同意签发。"
                )
            }
        )
        with patch.object(
            type(report),
            "_render_issued_pdf",
            return_value=pdf,
        ):
            report.with_user(approver).action_issue()
        report.invalidate_recordset()
        return report

    def _vat_run(self, suffix):
        run = self.env["sudo.cn.vat.period.reconciliation.run"].with_company(
            self.company
        ).enqueue(
            self.profile,
            "2026-06-01",
            "2026-06-30",
            f"VAT-{suffix}",
        )
        run.with_company(self.company)._process()
        run.invalidate_recordset()
        return run

    def _authority_source(self, suffix):
        attachment = self.env["ir.attachment"].create(
            {
                "name": f"formal-report-filing-source-{suffix}.pdf",
                "raw": f"official filing deadline source {suffix}".encode(),
                "mimetype": "application/pdf",
            }
        )
        source = self.env["sudo.compliance.authority.source"].create(
            {
                "name": f"Formal report filing authority source {suffix}",
                "country_id": self.country.id,
                "authority": "State Taxation Administration",
                "source_type": "form_instruction",
                "official_url": "https://www.chinatax.gov.cn/",
                "official_version": f"FORMAL-{suffix}",
                "published_date": "2026-01-01",
                "next_review_date": "2027-12-31",
                "snapshot_kind": "official_document",
                "snapshot_attachment_id": attachment.id,
            }
        )
        source.action_compute_hash()
        return source

    def _review_obligations_not_applicable(self, suffix="obligation"):
        source = self._authority_source(suffix)
        self.profile.obligation_ids.write(
            {
                "applicability": "not_applicable",
                "authority_source_id": source.id,
                "justification": (
                    "Controlled test review marks these candidate obligations "
                    "not applicable so another limitation can be isolated."
                ),
            }
        )
        self.profile.invalidate_recordset()
        return source

    def _filing_archive(self, suffix):
        run = self._vat_run(suffix)
        action = run.action_open_cn_filing_archive()
        defaults = {
            key.removeprefix("default_"): value
            for key, value in action["context"].items()
            if key.startswith("default_")
        }
        source = self._authority_source(suffix)
        obligation = self.env["sudo.compliance.obligation"].browse(
            defaults["obligation_id"]
        )
        obligation.write(
            {
                "applicability": "applicable",
                "effective_from": "2026-01-01",
                "authority_source_id": source.id,
                "justification": "Controlled test authority basis for filing archive.",
            }
        )
        defaults.update(
            {
                "due_date": "2026-07-15",
                "authority_source_id": source.id,
                "due_date_basis": "Controlled test due date basis.",
            }
        )
        return self.env["sudo.compliance.filing"].with_company(self.company).create(
            defaults
        )

    def test_submission_freezes_explainable_snapshot_and_audit(self):
        report = self._report()

        report.with_user(self.manager).action_submit()
        report.invalidate_recordset()

        self.assertEqual(report.state, "submitted")
        self.assertEqual(report.conclusion_state, "limited_action_required")
        self.assertEqual(report.snapshot_json["schema"], "sdoo.cn.compliance-report.v1")
        self.assertEqual(report.snapshot_json["assessment"]["id"], self.assessment.id)
        self.assertEqual(report.snapshot_json["findings"][0]["checksum"], self.finding.checksum)
        self.assertEqual(
            report.snapshot_json["findings"][0]["closure_state"],
            self.finding.cn_closure_state,
        )
        self.assertEqual(
            report.snapshot_json["findings"][0]["closure_summary"],
            self.finding.cn_closure_summary,
        )
        self.assertEqual(report.finding_closure_blocked_count, 1)
        self.assertEqual(report.finding_closure_action_required_count, 0)
        self.assertEqual(report.finding_closure_ready_count, 0)
        self.assertEqual(
            report.snapshot_json["obligation_readiness"]["state"],
            "attention",
        )
        self.assertEqual(
            report.snapshot_json["obligation_readiness"]["candidate_count"],
            len(self.profile.obligation_ids),
        )
        self.assertEqual(report.snapshot_json["filing_archive"]["state"], "not_started")
        self.assertEqual(report.snapshot_json["filing_archive"]["archive_count"], 0)
        self.assertEqual(report.snapshot_json["data_basis"]["state"], "missing")
        self.assertGreater(
            report.snapshot_json["data_basis"]["missing_type_count"],
            0,
        )
        self.assertIn(
            "Electronic invoices",
            report.snapshot_json["data_basis"]["missing_type_summary"],
        )
        self.assertEqual(report.snapshot_json["fact_basis"]["state"], "blocked")
        self.assertEqual(report.fact_snapshot_count, 0)
        self.assertEqual(report.finding_without_fact_count, 1)
        self.assertEqual(report.cn_report_fact_basis_state, "blocked")
        self.assertEqual(report.finding_count, 1)
        self.assertEqual(report.high_count, 1)
        self.assertEqual(len(report.snapshot_checksum), 64)
        self.assertEqual(report.snapshot_integrity_state, "verified")
        with self.assertRaises(UserError):
            report.with_user(self.manager).write({"title": "Cannot mutate"})
        event = self.env["sudo.compliance.audit.event"].search(
            [
                ("event_key", "=", "cn_compliance_report.submitted"),
                ("record_id", "=", report.id),
            ],
            limit=1,
        )
        self.assertEqual(event.details_json["snapshot_checksum"], report.snapshot_checksum)

    def test_submission_freezes_evidence_link_context(self):
        evidence, task = self._verified_report_evidence(self.finding)
        report = self._report()

        report.with_user(self.manager).action_submit()
        report.invalidate_recordset()

        evidence_row = report.snapshot_json["evidence"][0]
        self.assertEqual(evidence_row["id"], evidence.id)
        self.assertEqual(evidence_row["integrity_state"], "verified")
        self.assertEqual(
            evidence_row["links"]["finding"]["id"],
            self.finding.id,
        )
        self.assertEqual(
            evidence_row["links"]["finding"]["checksum"],
            self.finding.checksum,
        )
        self.assertEqual(evidence_row["links"]["task"]["id"], task.id)
        self.assertEqual(
            evidence_row["links"]["assessment"]["id"],
            self.assessment.id,
        )

    def test_submission_summarizes_report_fact_basis(self):
        snapshot = self._fact_snapshot(self.finding, "complete")
        report = self._report()

        report.with_user(self.manager).action_submit()
        report.invalidate_recordset()

        self.assertEqual(report.snapshot_json["fact_basis"]["state"], "ready")
        self.assertEqual(report.snapshot_json["fact_basis"]["snapshot_count"], 1)
        self.assertEqual(report.fact_snapshot_count, 1)
        self.assertEqual(report.fact_issue_count, 0)
        self.assertEqual(report.finding_without_fact_count, 0)
        self.assertEqual(report.cn_report_fact_basis_state, "ready")
        self.assertIn(
            snapshot.checksum,
            report.snapshot_json["findings"][0]["fact_snapshot_checksums"],
        )

    def test_submission_includes_reconciliation_risk_summary(self):
        snapshot = self._fact_snapshot(
            self.finding,
            "cit_recon",
            key="cn.reconciliation.cit.risk_summary",
            value={
                "risk_status": "difference_review_required",
                "next_action": "Review CIT accounting and filing differences.",
                "counts": {
                    "difference_count": 3,
                    "blocking_issue_count": 1,
                    "warning_issue_count": 2,
                },
                "material_differences": [
                    {"code": "CIT-REV-DIFF", "amount": "300.00"}
                ],
                "top_issues": [{"code": "CIT-DIFF-001"}],
            },
            value_type="json",
        )
        report = self._report()

        report.with_user(self.manager).action_submit()
        report.invalidate_recordset()

        summary = report.snapshot_json["findings"][0][
            "reconciliation_risk_summary"
        ]
        self.assertEqual(summary["state"], "difference_review_required")
        self.assertIn("differences 3", summary["summary"])
        self.assertIn("CIT-DIFF-001", summary["summary"])
        self.assertEqual(
            summary["next_action"],
            "Review CIT accounting and filing differences.",
        )
        self.assertEqual(summary["checksum"], snapshot.checksum)

    def test_submission_includes_finding_tax_impact_summary(self):
        case = self._reviewed_tax_impact_case(self.finding, amount=240.0)
        report = self._report()

        report.with_user(self.manager).action_submit()
        report.invalidate_recordset()

        summary = report.snapshot_json["findings"][0]["tax_impact_summary"]
        self.assertEqual(case.integrity_state, "verified")
        self.assertEqual(summary["state"], "reviewed")
        self.assertEqual(summary["case_count"], 1)
        self.assertEqual(summary["pending_count"], 0)
        self.assertEqual(summary["reviewed_underpayment_amount"], "240.00")
        self.assertEqual(summary["case_ids"], case.ids)

    def test_submission_freezes_ai_guidance_summary(self):
        action = self.finding.with_user(self.manager).action_generate_cn_ai_guidance()
        analysis = self.env["sudo.compliance.ai.analysis"].browse(
            action["res_id"]
        )
        report = self._report()

        report.with_user(self.manager).action_submit()
        report.invalidate_recordset()

        finding_summary = report.snapshot_json["findings"][0][
            "ai_guidance_summary"
        ]
        self.assertEqual(finding_summary["analysis_count"], 1)
        self.assertEqual(finding_summary["latest_analysis_id"], analysis.id)
        self.assertEqual(
            finding_summary["current_input_checksum"],
            analysis.input_checksum,
        )
        self.assertTrue(finding_summary["input_is_current"])
        self.assertEqual(
            finding_summary["latest_record_checksum"],
            analysis.record_checksum,
        )
        self.assertEqual(report.snapshot_json["ai_guidance"]["generated_count"], 1)
        self.assertEqual(report.snapshot_json["ai_guidance"]["current_count"], 1)
        self.assertEqual(report.snapshot_json["ai_guidance"]["stale_count"], 0)
        self.assertEqual(
            report.snapshot_json["ai_analysis_metadata"][0]["input_checksum"],
            analysis.input_checksum,
        )
        self.assertEqual(
            report.snapshot_json["ai_analysis_metadata"][0]["prompt_version"],
            "cn-compliance-guidance-v1",
        )

    def test_pending_obligations_require_report_limitation(self):
        report = self._report(limitation_statement="")

        with self.assertRaisesRegex(
            UserError,
            "Tax obligation applicability is not fully confirmed",
        ):
            report.with_user(self.manager).action_submit()

        report.limitation_statement = (
            "中国候选纳税义务仍处于测试确认阶段，报告结论仅用于受控演示环境。"
        )
        report.with_user(self.manager).action_submit()
        report.invalidate_recordset()

        self.assertTrue(report.has_material_limitations)
        self.assertEqual(
            report.snapshot_json["obligation_readiness"]["pending_review_count"],
            len(self.profile.obligation_ids),
        )
        self.assertIn(
            "obligation_readiness",
            report.snapshot_json,
        )

    def test_incomplete_data_basis_requires_report_limitation(self):
        self._review_obligations_not_applicable("data-basis-limit")
        report = self._report(limitation_statement="")

        with self.assertRaisesRegex(
            UserError,
            "Assessment data basis is incomplete",
        ):
            report.with_user(self.manager).action_submit()

        payload = report._snapshot_payload()
        self.assertEqual(payload["obligation_readiness"]["state"], "ready")
        self.assertEqual(payload["data_basis"]["state"], "missing")
        self.assertGreater(payload["data_basis"]["missing_type_count"], 0)
        self.assertEqual(
            report._derive_conclusion(payload)[0],
            "limited_action_required",
        )

    def test_unsealed_filing_archive_blocks_formal_submission(self):
        filing = self._filing_archive("formal-submit")
        report = self._report()

        with self.assertRaisesRegex(
            UserError,
            "Filing/payment archives are not sealed",
        ):
            report.with_user(self.manager).action_submit()

        payload = report._snapshot_payload()
        self.assertEqual(payload["filing_archive"]["archive_count"], 1)
        self.assertEqual(payload["filing_archive"]["issue_count"], 1)
        self.assertEqual(payload["filing_archive"]["state"], "blocked")
        self.assertEqual(payload["filing_archive"]["archives"][0]["id"], filing.id)
        self.assertEqual(report._derive_conclusion(payload)[0], "limited_action_required")

    def test_report_center_exposes_stage_next_action_and_navigation(self):
        report = self._report()

        self.assertEqual(report.cn_report_center_stage, "draft")
        self.assertEqual(report.cn_report_center_integrity_state, "unsealed")
        self.assertTrue(report.cn_report_center_next_action)

        report.with_user(self.manager).action_submit()
        report.invalidate_recordset()

        self.assertEqual(report.cn_report_center_stage, "approval")
        self.assertEqual(report.cn_report_center_integrity_state, "verified")
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_formal_report_badge_clarity"
            ]
        )
        self.assertTrue(report.cn_report_center_next_action)
        self.assertEqual(
            report.action_cn_open_report_findings()["res_model"],
            "sudo.compliance.finding",
        )
        self.assertIn(
            ("assessment_id", "=", self.assessment.id),
            report.action_cn_open_report_findings()["domain"],
        )
        self.assertEqual(
            report.action_cn_open_report_tasks()["res_model"],
            "sudo.compliance.task",
        )
        self.assertIn(
            ("assessment_id", "=", self.assessment.id),
            report.action_cn_open_report_tasks()["domain"],
        )
        self.assertEqual(report.cn_report_traceability_state, "blocked")
        self.assertGreater(report.cn_report_traceability_gap_count, 0)
        self.assertTrue(report.cn_report_traceability_next_action)
        self.assertEqual(
            report.action_cn_open_report_evidence()["res_model"],
            "sudo.compliance.evidence",
        )

        self._issue(report)
        report.invalidate_recordset()

        self.assertEqual(report.cn_report_center_stage, "issued")
        self.assertEqual(report.cn_report_center_integrity_state, "verified")

    def test_country_pack_advertises_report_center_visibility(self):
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_report_center_visibility"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_report_obligation_readiness"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_report_remediation_verification"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_report_filing_archive_snapshot"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_report_fact_basis_visibility"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_report_data_basis_snapshot"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_report_ai_guidance_snapshot"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_report_evidence_link_snapshot"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_report_risk_closure_snapshot"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_traceability_matrix_visibility"
            ]
        )

    def test_unreviewed_or_unsigned_findings_block_formal_submission(self):
        unreviewed, _finding = self._assessment("unreviewed", review=False)
        report = self._report(unreviewed)
        with self.assertRaisesRegex(UserError, "未完成人工复核"):
            report.with_user(self.manager).action_submit()

        unsigned, _finding = self._assessment(
            "unsigned",
            professional_warning=True,
        )
        report = self._report(unsigned)
        with self.assertRaisesRegex(UserError, "真人专业签核"):
            report.with_user(self.manager).action_submit()

    def test_source_change_after_submission_requires_return_and_resubmit(self):
        report = self._report()
        report.with_user(self.manager).action_submit()
        self.assessment.note = "报告提交后发生变化的评估说明。"

        with self.assertRaisesRegex(UserError, "源资料在提交后发生变化"):
            report.with_user(self.approver).write(
                {"review_notes": "已复核但发现源资料发生变化，应退回重新冻结快照。"}
            )
            report.with_user(self.approver).action_issue()

        report.with_user(self.approver).action_return_to_draft()
        report.invalidate_recordset()
        self.assertEqual(report.state, "draft")
        self.assertFalse(report.snapshot_checksum)
        self.assertFalse(report.conclusion_state)

    def test_independent_approver_issues_immutable_pdf(self):
        report = self._report()
        report.with_user(self.manager).action_submit()

        self._issue(report)

        self.assertEqual(report.state, "issued")
        self.assertEqual(report.issued_by_id, self.approver)
        self.assertEqual(len(report.approval_checksum), 64)
        self.assertEqual(len(report.issued_pdf_sha256), 64)
        self.assertEqual(report.approval_integrity_state, "verified")
        self.assertEqual(report.pdf_integrity_state, "verified")
        download = report.with_user(self.reader).action_download_issued_pdf()
        self.assertEqual(download["type"], "ir.actions.act_url")
        with self.assertRaisesRegex(UserError, "封存 PDF"):
            report.action_preview()
        with self.assertRaisesRegex(AccessError, "受控字段"):
            report.with_user(self.manager).write({"issued_at": fields.Datetime.now()})
        with self.assertRaisesRegex(UserError, "不允许删除"):
            report.with_user(self.manager).unlink()

    def test_pdf_tampering_is_detected_and_download_blocked(self):
        report = self._report()
        report.with_user(self.manager).action_submit()
        self._issue(report)
        attachment = self.env["ir.attachment"].sudo().search(
            [
                ("res_model", "=", report._name),
                ("res_id", "=", report.id),
                ("res_field", "=", "issued_pdf"),
            ],
            limit=1,
        )
        self.assertTrue(attachment)

        attachment.raw = b"tampered formal report"
        report.invalidate_recordset()

        self.assertEqual(report.pdf_integrity_state, "checksum_mismatch")
        with self.assertRaisesRegex(UserError, "完整性异常"):
            report.action_download_issued_pdf()

    def test_approval_tampering_is_detected_and_download_blocked(self):
        report = self._report()
        report.with_user(self.manager).action_submit()
        self._issue(report)

        self.env.cr.execute(
            "UPDATE sudo_cn_compliance_report SET review_notes = %s WHERE id = %s",
            ("数据库层篡改后的批准意见。", report.id),
        )
        report.invalidate_recordset()

        self.assertEqual(
            report.approval_integrity_state,
            "checksum_mismatch",
        )
        with self.assertRaisesRegex(UserError, "批准记录.*完整性异常"):
            report.action_download_issued_pdf()

    def test_open_verification_task_prevents_clear_conclusion(self):
        assessment, finding = self._assessment(
            "verification-pass",
            result="pass",
            review=False,
        )
        finding.with_user(self.manager).write(
            {"review_notes": "已确认本次复扫结果通过，但原整改任务仍待授权人员确认关闭。"}
        )
        finding.with_user(self.manager).action_confirm_review()
        task = self.env["sudo.compliance.task"].create_from_finding(self.finding)
        task._transition_write(
            {
                "state": "pending_review",
                "verification_state": "pending_rescan",
                "verification_assessment_id": assessment.id,
            }
        )
        report = self._report(assessment)

        report.with_user(self.manager).action_submit()
        report.invalidate_recordset()

        self.assertEqual(report.open_task_count, 1)
        self.assertEqual(report.remediation_task_count, 1)
        self.assertEqual(report.remediation_verified_count, 0)
        self.assertEqual(report.remediation_pending_verification_count, 1)
        self.assertEqual(report.conclusion_state, "limited_action_required")
        self.assertEqual(
            report.snapshot_json["tasks"][0]["verification_assessment_id"],
            assessment.id,
        )

    def test_closed_task_without_verification_still_requires_action(self):
        task = self.env["sudo.compliance.task"].create_from_finding(self.finding)
        task._transition_write(
            {
                "state": "done",
                "verification_state": "failed",
                "completion_notes": (
                    "整改处理已经登记，但验证复扫尚未通过，报告不得视为完全闭环。"
                ),
            }
        )
        report = self._report()

        report.with_user(self.manager).action_submit()
        report.invalidate_recordset()

        self.assertEqual(report.open_task_count, 0)
        self.assertEqual(report.remediation_task_count, 1)
        self.assertEqual(report.remediation_verified_count, 0)
        self.assertEqual(report.remediation_pending_verification_count, 1)
        self.assertEqual(report.conclusion_state, "limited_action_required")
        self.assertEqual(
            report.snapshot_json["tasks"][0]["verification_state"],
            "failed",
        )

    def test_same_person_approval_requires_recorded_exception(self):
        report = self._report(
            preparer=self.same_person,
            reviewer=self.same_person,
        )
        with self.assertRaisesRegex(UserError, "职责未分离"):
            report.with_user(self.same_person).action_submit()

        report.independence_exception_reason = (
            "测试环境只有一名同时具备编制和批准权限的人员，已由管理层记录受控例外。"
        )
        report.with_user(self.same_person).action_submit()
        self._issue(report, approver=self.same_person)

        self.assertEqual(report.state, "issued")
        event = self.env["sudo.compliance.audit.event"].search(
            [
                ("event_key", "=", "cn_compliance_report.issued"),
                ("record_id", "=", report.id),
            ],
            limit=1,
        )
        self.assertFalse(event.details_json["independent_approval"])

    def test_new_issue_supersedes_previous_report_without_rewriting_pdf(self):
        first = self._report()
        first.with_user(self.manager).action_submit()
        self._issue(first, pdf=b"%PDF-1.4\nfirst\n%%EOF")
        first_pdf_checksum = first.issued_pdf_sha256

        second = self._report(title="中国财税合规管理正式报告第二版")
        self.assertEqual(second.supersedes_id, first)
        second.with_user(self.manager).action_submit()
        self._issue(second, pdf=b"%PDF-1.4\nsecond\n%%EOF")
        first.invalidate_recordset()

        self.assertEqual(first.state, "superseded")
        self.assertEqual(first.issued_pdf_sha256, first_pdf_checksum)
        self.assertEqual(second.state, "issued")
        self.assertEqual(second.revision, 2)

    def test_withdrawal_preserves_artifact_and_audit_history(self):
        report = self._report()
        report.with_user(self.manager).action_submit()
        self._issue(report)
        pdf_checksum = report.issued_pdf_sha256
        report.with_user(self.manager).withdrawal_reason = (
            "签发后发现报告使用范围发生变化，管理层决定撤回并重新执行扫描。"
        )

        report.with_user(self.manager).action_withdraw()
        report.invalidate_recordset()

        self.assertEqual(report.state, "withdrawn")
        self.assertEqual(report.issued_pdf_sha256, pdf_checksum)
        self.assertEqual(report.pdf_integrity_state, "verified")
        event = self.env["sudo.compliance.audit.event"].search(
            [
                ("event_key", "=", "cn_compliance_report.withdrawn"),
                ("record_id", "=", report.id),
            ],
            limit=1,
        )
        self.assertEqual(event.details_json["pdf_sha256"], pdf_checksum)

    def test_read_only_user_cannot_prepare_or_mutate_report(self):
        with self.assertRaisesRegex(AccessError, "只有合规管理员"):
            self._report(preparer=self.reader)
        report = self._report()
        with self.assertRaises(AccessError):
            report.with_user(self.reader).write({"title": "无权修改"})

    def test_report_is_company_isolated_and_reviewer_must_have_company(self):
        other_company = self.env["res.company"].create(
            {
                "name": "China Formal Report Other Company",
                "country_id": self.country.id,
                "account_fiscal_country_id": self.country.id,
                "currency_id": self.currency.id,
            }
        )
        manager_group = self.env.ref(
            "sudo_global_finance.group_compliance_manager"
        )
        approver_group = self.env.ref(
            "sudo_country_pack_cn.group_cn_report_approver"
        )
        other_manager = self._user(
            "cn_report_other_manager",
            "China Report Other Manager",
            manager_group,
            company=other_company,
        )
        other_approver = self._user(
            "cn_report_other_approver",
            "China Report Other Approver",
            approver_group,
            company=other_company,
        )
        report = self._report()
        report_model = self.env["sudo.cn.compliance.report"].with_user(
            other_manager
        ).with_company(other_company)

        self.assertFalse(report_model.search([("id", "=", report.id)]))
        with self.assertRaises(AccessError):
            report.with_user(other_manager).with_company(other_company).read(
                ["name"]
            )
        with self.assertRaises(ValidationError):
            self._report(reviewer=other_approver)

    def test_only_designated_approver_can_return_or_issue(self):
        approver_group = self.env.ref(
            "sudo_country_pack_cn.group_cn_report_approver"
        )
        alternate_approver = self._user(
            "cn_report_alternate_approver",
            "China Report Alternate Approver",
            approver_group,
        )
        report = self._report()
        report.with_user(self.manager).action_submit()

        with self.assertRaises(AccessError):
            report.with_user(alternate_approver).write(
                {
                    "review_notes": (
                        "This alternate approver was not designated for the "
                        "controlled report approval."
                    )
                }
            )
        with self.assertRaises(AccessError):
            report.with_user(alternate_approver).action_return_to_draft()
        with self.assertRaises(AccessError):
            report.with_user(alternate_approver).action_issue()

    def test_report_html_preserves_boundary_and_non_net_tax_impact(self):
        report = self._report()
        report.with_user(self.manager).action_submit()
        action = self.env.ref(
            "sudo_country_pack_cn.action_report_cn_formal_compliance"
        )

        html, _report_type = action._render_qweb_html(
            action.report_name,
            report.ids,
        )

        self.assertFalse(action.binding_model_id)
        self.assertIn("不是纳税申报表".encode(), html)
        self.assertIn("不计算净额".encode(), html)
        self.assertIn("AI 分析仅为辅助材料".encode(), html)
        self.assertIn("待验证复扫".encode(), html)
        self.assertIn("风险闭环阻断".encode(), html)
        self.assertIn("风险闭环待处理".encode(), html)
        self.assertIn("风险闭环可报告".encode(), html)
        self.assertIn("风险闭环".encode(), html)
        self.assertIn(self.finding.cn_closure_summary.encode(), html)
        self.assertIn("预览稿，尚未签发".encode(), html)
        self.assertIn(report.snapshot_checksum.encode(), html)
