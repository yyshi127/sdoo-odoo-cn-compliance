from odoo import Command, fields
from odoo.tests import TransactionCase, tagged

from odoo.addons.sudo_country_pack_cn.models.risk_center import (
    _closure_summary_values,
)


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

    def test_risk_and_remediation_labels_are_chinese(self):
        finding_fields = self.env["sudo.compliance.finding"]._fields
        finding_labels = {
            "cn_risk_action_summary": "风险行动摘要",
            "cn_risk_remediation_urgency": "整改紧迫度",
            "cn_risk_fact_summary": "事实摘要",
            "cn_reconciliation_risk_state": "勾稽风险",
            "cn_risk_data_basis_state": "数据基础",
            "cn_traceability_state": "可追溯性",
            "cn_closure_state": "闭环状态",
            "cn_cross_border_fact_state": "跨境事实",
            "cn_tax_impact_state": "税务影响",
        }
        for field_name, expected_label in finding_labels.items():
            self.assertEqual(finding_fields[field_name].string, expected_label)

        task_fields = self.env["sudo.compliance.task"]._fields
        task_labels = {
            "cn_remediation_action_summary": "整改行动摘要",
            "cn_remediation_urgency": "整改紧迫度",
            "cn_remediation_traceability_state": "可追溯性",
            "cn_remediation_data_basis_state": "数据基础",
            "cn_remediation_tax_impact_state": "整改税务影响",
            "cn_remediation_progress": "整改进度",
            "cn_remediation_blocker_summary": "整改阻断事项",
        }
        for field_name, expected_label in task_labels.items():
            self.assertEqual(task_fields[field_name].string, expected_label)

    def _finding(self):
        assessment = self.env["sudo.compliance.assessment"].with_company(
            self.company
        ).create(
            {
                "profile_id": self.profile.id,
                "evaluation_date": "2026-12-31",
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

    def _cross_border_transaction(self):
        attachment = self.env["ir.attachment"].create(
            {
                "name": "risk-center-cross-border.txt",
                "raw": b"risk center cross border evidence",
            }
        )
        return self.env["sudo.cn.cross.border.transaction"].with_company(
            self.company
        ).create(
            {
                "profile_id": self.profile.id,
                "period_start": "2026-06-01",
                "period_end": "2026-06-30",
                "transaction_date": "2026-06-18",
                "transaction_type": "service_fee",
                "counterparty_name": "Risk Center Foreign Provider",
                "counterparty_country_id": self.env.ref("base.us").id,
                "currency_id": self.currency.id,
                "amount": 18000.0,
                "withholding_considered": True,
                "evidence_attachment_ids": [Command.set(attachment.ids)],
            }
        )

    def _cross_border_assessment(self):
        rule = self.env["sudo.compliance.rule"].search(
            [("code", "=", "CN-CROSS-BORDER-CTRL-001")], limit=1
        )
        if not rule:
            rule = self.env["sudo.compliance.rule"].create(
                {
                    "name": "Risk Center Cross-Border Display Test Rule",
                    "code": "CN-CROSS-BORDER-CTRL-001",
                    "country_id": self.country.id,
                    "domain_key": "CN.CROSS_BORDER",
                }
            )
        version = self.env["sudo.compliance.rule.version"].search(
            [
                ("rule_id", "=", rule.id),
                ("version", "=", "RISK-CENTER-FACT-TEST"),
            ],
            limit=1,
        )
        if not version:
            version = self.env["sudo.compliance.rule.version"].create(
                {
                    "rule_id": rule.id,
                    "version": "RISK-CENTER-FACT-TEST",
                    "effective_from": "2026-01-01",
                    "next_review_date": "2027-01-01",
                    "evaluator_type": "manual",
                    "requires_human_review": True,
                }
            )
        assessment = self.env["sudo.compliance.assessment"].with_company(
            self.company
        ).create(
            {
                "profile_id": self.profile.id,
                "evaluation_date": "2026-07-01",
                "period_start": "2026-06-01",
                "period_end": "2026-06-30",
                "rule_version_ids": [Command.set(version.ids)],
                "note": "Risk center cross-border fact visibility test.",
            }
        )
        pending = self.env["sudo.cn.cross.border.transaction"].search_count(
            [
                ("profile_id", "=", self.profile.id),
                ("state", "!=", "reviewed"),
            ]
        )
        reviewed = self.env["sudo.cn.cross.border.transaction"].search_count(
            [
                ("profile_id", "=", self.profile.id),
                ("state", "=", "reviewed"),
            ]
        )
        finding = self.env["sudo.compliance.finding"]._create_engine(
            {
                "assessment_id": assessment.id,
                "rule_id": rule.id,
                "rule_version_id": version.id,
                "result": "fail" if pending else "pass",
                "risk_level": "high" if pending else "info",
                "title": "Risk center cross-border fact finding",
                "summary": "Controlled cross-border facts for risk center display.",
                "recommendation": "Review controlled cross-border facts.",
                "evidence_required": "Keep reviewed cross-border evidence.",
                "requires_human_review": True,
                "checksum": ("x" * 64),
            }
        )
        assessment._engine_write({"state": "completed"})
        self._fact_snapshot(
            finding,
            "cross_pending",
            key="cn.cross_border.pending_review_count",
            value=pending,
        )
        self._fact_snapshot(
            finding,
            "cross_reviewed",
            key="cn.cross_border.reviewed_transaction_count",
            value=reviewed,
        )
        self._fact_snapshot(
            finding,
            "cross_detail",
            key="cn.cross_border.detail",
            value={
                "pending_review_count": pending,
                "reviewed_transaction_count": reviewed,
                "transaction_count": pending + reviewed,
            },
            value_type="json",
        )
        return assessment, finding

    def _fact_snapshot(
        self,
        finding,
        suffix="base",
        quality_state="complete",
        key=None,
        value=3,
        value_type="integer",
    ):
        key = key or f"cn.risk.center.fact.{finding.id}.{suffix}"
        definition = self.env["sudo.compliance.fact.definition"].search(
            [("key", "=", key)], limit=1
        )
        if not definition:
            definition = self.env["sudo.compliance.fact.definition"].create(
                {
                    "name": f"Risk Center Fact {suffix}",
                    "label": f"Risk center fact {suffix}",
                    "key": key,
                    "version": "TEST-1",
                    "country_id": self.country.id,
                    "value_type": value_type,
                    "provider_key": f"risk_center_fact_{suffix}",
                    "provider_version": "1",
                    "source_model": "account.move",
                    "source_description": "Controlled risk center test fact.",
                    "completeness_method": "full_domain",
                }
            )
        snapshot = self.env["sudo.compliance.fact.snapshot"]._create_engine(
            {
                "name": f"Risk center snapshot {suffix}",
                "assessment_id": finding.assessment_id.id,
                "definition_id": definition.id,
                "value_json": value,
                "captured_at": fields.Datetime.now(),
                "source_model": "account.move",
                "source_domain_json": [("company_id", "=", self.company.id)],
                "record_count": 3,
                "aggregation_method": "controlled_test",
                "is_complete": quality_state == "complete",
                "is_full_dataset": quality_state == "complete",
                "quality_state": quality_state,
                "provider_key": definition.provider_key,
                "provider_version": "1",
                "checksum": suffix[:1].ljust(64, "d"),
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
        amount=120.0,
    ):
        finding.write(
            {
                "review_notes": (
                    "Controlled test review confirms the risk needs tax impact follow-up."
                )
            }
        )
        finding.action_require_correction()
        attachment = self.env["ir.attachment"].create(
            {
                "name": "risk-center-tax-impact.txt",
                "raw": b"risk center tax impact evidence",
            }
        )
        case = self.env["sudo.cn.tax.impact.case"].with_company(
            self.company
        ).create(
            {
                "title": "Risk center tax impact case",
                "profile_id": self.profile.id,
                "period_start": finding.assessment_id.period_start,
                "period_end": finding.assessment_id.period_end,
                "assessment_id": finding.assessment_id.id,
                "finding_ids": [Command.set(finding.ids)],
                "impact_direction": direction,
                "quantification_state": "preliminary",
                "impact_amount": amount,
                "analysis": (
                    "Controlled test analysis explains the tax impact calculation."
                ),
                "assumptions_limitations": (
                    "Controlled assumptions and limitations are documented."
                ),
                "source_reference": "RC-TAX-IMPACT-TEST",
                "evidence_attachment_ids": [Command.set(attachment.ids)],
            }
        )
        case.action_submit()
        case.write(
            {
                "review_notes": (
                    "Independent controlled review confirms the quantified tax impact."
                ),
                "separation_exception_reason": (
                    "Controlled automated test allows same-user review exception."
                ),
            }
        )
        case.action_review()
        finding.invalidate_recordset()
        return case

    def _set_task_verification_state(self, task, state):
        self.env.cr.execute(
            """
            UPDATE sudo_compliance_task
               SET state = %s,
                   verification_state = %s,
                   verification_assessment_id = %s
             WHERE id = %s
            """,
            ("pending_review", state, task.assessment_id.id, task.id),
        )
        task.invalidate_recordset()

    def test_finding_exposes_period_next_action_and_evidence_status(self):
        finding = self._finding()

        self.assertIn("2026-06-01", finding.cn_risk_period_label)
        self.assertIn("2026-06-30", finding.cn_risk_period_label)
        self.assertIn("数据基础", finding.cn_risk_next_action)
        self.assertEqual(finding.cn_risk_evidence_state, "none")
        self.assertEqual(finding.cn_risk_evidence_count, 0)
        self.assertEqual(finding.cn_risk_verified_evidence_count, 0)
        self.assertEqual(finding.cn_closure_state, "blocked")
        self.assertIn("数据基础", finding.cn_closure_summary)
        self.assertEqual(finding.cn_risk_fact_snapshot_count, 0)
        self.assertEqual(finding.cn_risk_fact_issue_count, 0)
        self.assertIn("未附加规则事实快照", finding.cn_risk_fact_summary)
        self.assertEqual(finding.cn_risk_data_basis_state, "missing")
        self.assertGreater(finding.cn_risk_data_basis_missing_type_count, 0)
        self.assertIn(
            "电子发票",
            finding.cn_risk_data_basis_missing_type_summary,
        )
        self.assertIn(
            finding.cn_risk_data_basis_missing_type_summary,
            finding.cn_risk_data_basis_next_action,
        )

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
        self.assertEqual(task.cn_remediation_data_basis_state, "missing")
        self.assertGreater(task.cn_remediation_data_basis_missing_type_count, 0)
        self.assertIn(
            "电子发票",
            task.cn_remediation_data_basis_missing_type_summary,
        )
        self.assertEqual(task.cn_remediation_rescan_stage, "ready_for_rescan")
        self.assertEqual(task.cn_remediation_progress, 0)
        stage_labels = dict(
            task._fields["cn_remediation_rescan_stage"]._description_selection(
                task.env
            )
        )
        self.assertIn(
            stage_labels["ready_for_rescan"], task.cn_remediation_summary
        )

        self._set_task_verification_state(task, "pending_rescan")
        self.assertEqual(task.cn_remediation_rescan_stage, "pending_rescan")
        self.assertIn(stage_labels["pending_rescan"], task.cn_remediation_summary)

        action = task.action_cn_open_remediation_verification_assessment()
        self.assertEqual(action["res_model"], "sudo.compliance.assessment")
        self.assertEqual(action["res_id"], finding.assessment_id.id)

    def test_remediation_rescan_stage_is_searchable(self):
        finding = self._finding()
        task = self.env["sudo.compliance.task"].create_from_finding(finding)
        task._transition_write({"state": "pending_review"})

        tasks = self.env["sudo.compliance.task"].search(
            [("cn_remediation_rescan_stage", "=", "ready_for_rescan")]
        )

        self.assertIn(task, tasks)

    def test_remediation_tracker_search_view_exposes_rescan_filters(self):
        view = self.env.ref(
            "sudo_country_pack_cn.view_cn_remediation_tracker_task_search"
        )
        arch = view.arch_db

        for required in (
            "cn_rescan_ready",
            "cn_rescan_pending",
            "cn_rescan_failed",
            "cn_rescan_evidence_gap",
            "cn_rescan_verified",
            "cn_remediation_rescan_stage",
        ):
            self.assertIn(required, arch)

    def test_country_pack_advertises_remediation_rescan_visibility(self):
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_remediation_rescan_visibility"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_remediation_progress_visibility"
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
        self.assertEqual(finding.cn_closure_state, "blocked")
        self.assertIn("签核前受阻", finding.cn_closure_summary)

        action = finding.action_cn_open_traceability_evidence()
        self.assertEqual(action["res_model"], "sudo.compliance.evidence")
        self.assertIn(("finding_id", "=", finding.id), action["domain"])

    def test_finding_closure_summary_distinguishes_ready_and_action_required(self):
        self.assertEqual(
            _closure_summary_values(
                translate=self.env._,
                data_basis_state="ready",
                rule_basis_state="ready",
                result="fail",
                review_state="confirmed",
                task_state=False,
                task_verification_state=False,
                tax_impact_state="reviewed",
                evidence_state="verified",
            )[1],
            "已可进行报告签核：风险复核、整改、证据、税务影响和复扫控制均已对齐。",
        )

        state, summary = _closure_summary_values(
            translate=self.env._,
            data_basis_state="ready",
            rule_basis_state="ready",
            result="fail",
            review_state="confirmed",
            task_state=False,
            task_verification_state=False,
            tax_impact_state="reviewed",
            evidence_state="partial",
        )
        self.assertEqual(state, "action_required")
        self.assertIn("验证证据", summary)

    def test_finding_exposes_fact_snapshot_summary(self):
        finding = self._finding()
        snapshot = self._fact_snapshot(finding, "complete")

        self.assertEqual(finding.cn_risk_fact_snapshot_count, 1)
        self.assertEqual(finding.cn_risk_fact_issue_count, 0)
        self.assertIn(snapshot.definition_id.label, finding.cn_risk_fact_summary)
        quality_labels = dict(
            snapshot._fields["quality_state"]._description_selection(snapshot.env)
        )
        self.assertIn(quality_labels["complete"], finding.cn_risk_fact_summary)

    def test_finding_flags_incomplete_fact_snapshots(self):
        finding = self._finding()
        self._fact_snapshot(finding, "limited", quality_state="truncated")

        self.assertEqual(finding.cn_risk_fact_snapshot_count, 1)
        self.assertEqual(finding.cn_risk_fact_issue_count, 1)
        snapshot = finding.fact_snapshot_ids[:1]
        quality_labels = dict(
            snapshot._fields["quality_state"]._description_selection(snapshot.env)
        )
        self.assertIn(quality_labels["truncated"], finding.cn_risk_fact_summary)

    def test_finding_exposes_reconciliation_risk_summary(self):
        finding = self._finding()
        self._fact_snapshot(
            finding,
            "vat_recon",
            key="cn.reconciliation.vat.risk_summary",
            value={
                "risk_status": "difference_review_required",
                "next_action": "Review VAT reconciliation differences.",
                "counts": {
                    "difference_count": 2,
                    "blocking_issue_count": 1,
                    "warning_issue_count": 1,
                },
                "material_differences": {"output_tax": "100.00"},
                "top_issues": [{"code": "VAT-DIFF-001"}],
            },
            value_type="json",
        )

        self.assertEqual(
            finding.cn_reconciliation_risk_state,
            "difference_review_required",
        )
        self.assertIn("差异 2", finding.cn_reconciliation_risk_summary)
        self.assertIn("VAT-DIFF-001", finding.cn_reconciliation_risk_summary)
        self.assertEqual(
            finding.cn_reconciliation_risk_next_action,
            "Review VAT reconciliation differences.",
        )

    def test_finding_exposes_reviewed_tax_impact_summary(self):
        finding = self._finding()
        case = self._reviewed_tax_impact_case(finding, amount=120.0)

        self.assertEqual(case.integrity_state, "verified")
        self.assertEqual(finding.cn_tax_impact_state, "reviewed")
        self.assertEqual(finding.cn_tax_impact_pending_review_count, 0)
        self.assertAlmostEqual(
            finding.cn_tax_impact_reviewed_underpayment_amount,
            120.0,
        )
        self.assertIn("少缴 120", finding.cn_tax_impact_summary)

    def test_remediation_task_exposes_tax_impact_summary(self):
        finding = self._finding()
        self._reviewed_tax_impact_case(finding, amount=230.0)
        task = self.env["sudo.compliance.task"].create_from_finding(finding)

        self.assertEqual(task.cn_remediation_tax_impact_state, "reviewed")
        self.assertEqual(task.cn_remediation_tax_impact_pending_review_count, 0)
        self.assertAlmostEqual(
            task.cn_remediation_tax_impact_reviewed_underpayment_amount,
            230.0,
        )
        self.assertIn("少缴 230", task.cn_remediation_tax_impact_summary)

    def test_risk_and_remediation_expose_responsibility_urgency(self):
        finding = self._finding()
        task = self.env["sudo.compliance.task"].create_from_finding(finding)
        due_date = fields.Date.add(fields.Date.context_today(task), days=3)
        task.write(
            {
                "assignee_id": self.env.user.id,
                "due_date": due_date,
            }
        )
        task.invalidate_recordset()
        finding.invalidate_recordset()

        self.assertEqual(task.cn_remediation_urgency, "due_soon")
        self.assertIn(self.env.user.display_name, task.cn_remediation_responsibility_summary)
        self.assertIn(str(due_date), task.cn_remediation_responsibility_summary)
        self.assertEqual(finding.cn_risk_remediation_urgency, "due_soon")
        self.assertIn(
            self.env.user.display_name,
            finding.cn_risk_responsibility_summary,
        )
        self.assertIn("下一步：", finding.cn_risk_action_summary)
        self.assertIn("责任与期限：", finding.cn_risk_action_summary)
        self.assertIn(self.env.user.display_name, finding.cn_risk_action_summary)
        self.assertIn("证据：", finding.cn_risk_action_summary)
        self.assertIn("闭环：", finding.cn_risk_action_summary)

        task.write({"due_date": fields.Date.add(fields.Date.context_today(task), days=-1)})
        task.invalidate_recordset()
        finding.invalidate_recordset()

        self.assertEqual(task.cn_remediation_urgency, "overdue")
        self.assertEqual(finding.cn_risk_remediation_urgency, "overdue")

    def test_cross_border_rule_finding_exposes_fact_review_status(self):
        transaction = self._cross_border_transaction()
        _assessment, finding = self._cross_border_assessment()

        self.assertEqual(finding.result, "fail")
        self.assertEqual(finding.cn_cross_border_fact_state, "pending_review")
        self.assertEqual(finding.cn_cross_border_pending_count, 1)
        self.assertEqual(finding.cn_cross_border_reviewed_count, 0)
        self.assertEqual(finding.cn_cross_border_transaction_count, 1)
        self.assertIn("跨境业务台账", finding.cn_cross_border_next_action)
        self.assertGreater(finding.cn_risk_fact_snapshot_count, 0)
        self.assertGreaterEqual(finding.cn_risk_fact_issue_count, 0)
        self.assertIn("=", finding.cn_risk_fact_summary)

        transaction.action_submit()
        transaction.review_notes = (
            "Manager reviewed withholding consideration, evidence and limitations."
        )
        transaction.action_mark_reviewed()
        _assessment, reviewed_finding = self._cross_border_assessment()

        self.assertEqual(reviewed_finding.result, "pass")
        self.assertEqual(reviewed_finding.cn_cross_border_fact_state, "reviewed")
        self.assertEqual(reviewed_finding.cn_cross_border_pending_count, 0)
        self.assertEqual(reviewed_finding.cn_cross_border_reviewed_count, 1)

    def test_remediation_task_exposes_traceability_gaps(self):
        finding = self._finding()
        task = self.env["sudo.compliance.task"].create_from_finding(finding)

        self.assertEqual(task.cn_remediation_traceability_state, "blocked")
        self.assertGreater(task.cn_remediation_traceability_gap_count, 0)
        self.assertIn("受阻原因：", task.cn_remediation_blocker_summary)
        self.assertIn("数据基础缺失", task.cn_remediation_blocker_summary)
        self.assertIn("没有已验证证据", task.cn_remediation_blocker_summary)
        self.assertIn("下一步：", task.cn_remediation_action_summary)
        self.assertIn("阻断事项：", task.cn_remediation_action_summary)
        self.assertIn("证据：", task.cn_remediation_action_summary)
        self.assertIn("复扫：", task.cn_remediation_action_summary)
        self.assertIn("进度：", task.cn_remediation_action_summary)

        self._set_task_verification_state(task, "pending_rescan")
        self.assertEqual(task.cn_remediation_traceability_state, "blocked")
        self.assertIn(
            "验证复扫待完成",
            task.cn_remediation_blocker_summary,
        )

    def test_remediation_task_blocker_summary_keeps_remaining_gaps_visible(self):
        finding = self._finding()
        task = self.env["sudo.compliance.task"].create_from_finding(finding)
        self._fact_snapshot(finding, "complete")
        self.env["sudo.compliance.evidence"].create(
            {
                "name": "Verified remediation evidence",
                "company_id": self.company.id,
                "task_id": task.id,
                "state": "verified",
                "document_checksum": "e" * 64,
            }
        )
        self.env.cr.execute(
            """
            UPDATE sudo_compliance_task
               SET state = %s,
                   verification_state = %s,
                   verification_assessment_id = %s
             WHERE id = %s
            """,
            ("done", "verified", finding.assessment_id.id, task.id),
        )
        task.invalidate_recordset()

        self.assertEqual(task.cn_remediation_rescan_stage, "verified")
        self.assertIn("受阻原因：", task.cn_remediation_blocker_summary)
        self.assertIn("数据基础缺失", task.cn_remediation_blocker_summary)
        self.assertIn(
            "证据待验证",
            task.cn_remediation_blocker_summary,
        )

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
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_cross_border_risk_visibility"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_risk_card_state_badge_clarity"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_risk_fact_basis_visibility"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_risk_data_basis_visibility"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_reconciliation_risk_visibility"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_risk_tax_impact_visibility"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_risk_closure_status_summary"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_remediation_responsibility_visibility"
            ]
        )

    def test_risk_closure_state_is_searchable(self):
        domain = self.env[
            "sudo.compliance.finding"
        ]._search_cn_closure_state("=", "blocked")

        self.assertEqual(domain[0][0], "id")
        self.assertEqual(domain[0][1], "in")

    def test_risk_center_can_filter_latest_and_historical_scans(self):
        historical = self._finding()
        latest = self._finding()

        historical.invalidate_recordset()
        latest.invalidate_recordset()

        self.assertFalse(historical.cn_is_latest_assessment)
        self.assertTrue(latest.cn_is_latest_assessment)
        latest_results = self.env["sudo.compliance.finding"].search(
            [
                ("id", "in", (historical.id, latest.id)),
                ("cn_is_latest_assessment", "=", True),
            ]
        )
        historical_results = self.env["sudo.compliance.finding"].search(
            [
                ("id", "in", (historical.id, latest.id)),
                ("cn_is_latest_assessment", "=", False),
            ]
        )
        self.assertEqual(latest_results, latest)
        self.assertEqual(historical_results, historical)

    def test_risk_center_search_view_exposes_closure_filters(self):
        view = self.env.ref(
            "sudo_country_pack_cn.view_cn_risk_center_finding_search"
        )
        arch = view.arch_db

        self.assertIn("cn_latest_scan", arch)
        self.assertIn("cn_historical_scan", arch)
        self.assertIn("cn_closure_ready", arch)
        self.assertIn("cn_closure_action_required", arch)
        self.assertIn("cn_closure_blocked", arch)
        self.assertIn("cn_closure_state", arch)
