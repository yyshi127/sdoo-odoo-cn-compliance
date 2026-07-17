import hashlib
import json

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


AI_GUIDANCE_PROVIDER = "sdoo_cn_controlled_guidance"
AI_GUIDANCE_MODEL = "sdoo-cn-guidance-fallback-v1"
AI_GUIDANCE_PROMPT_VERSION = "cn-compliance-guidance-v1"


def _checksum(payload):
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


class SudoChinaAiGuidanceFinding(models.Model):
    _inherit = "sudo.compliance.finding"

    cn_ai_guidance_state = fields.Selection(
        [
            ("unavailable", "不适用"),
            ("ready", "可生成"),
            ("limited", "带限制"),
            ("generated", "已生成"),
        ],
        string="AI 引导状态",
        compute="_compute_cn_ai_guidance_display",
    )
    cn_ai_guidance_next_action = fields.Char(
        string="AI 引导下一步",
        compute="_compute_cn_ai_guidance_display",
    )
    cn_ai_guidance_input_checksum = fields.Char(
        string="AI 引导输入指纹",
        compute="_compute_cn_ai_guidance_display",
    )

    @api.depends(
        "assessment_id.country_id",
        "result",
        "source_warning",
        "professional_warning",
        "missing_fact_keys",
        "missing_parameter_keys",
        "ai_analysis_count",
        "write_date",
        "current_task_id.write_date",
    )
    def _compute_cn_ai_guidance_display(self):
        for finding in self:
            if (
                finding.assessment_id.country_id.code != "CN"
                or finding.result not in ("fail", "unknown", "error")
            ):
                finding.cn_ai_guidance_state = "unavailable"
                finding.cn_ai_guidance_next_action = _(
                    "当前事项无需生成中国受控 AI 引导。"
                )
                finding.cn_ai_guidance_input_checksum = False
                continue

            payload = finding._cn_ai_guidance_input()
            finding.cn_ai_guidance_input_checksum = _checksum(payload)
            obligation_state = payload.get("obligation_readiness", {}).get("state")
            data_basis_state = payload.get("data_basis", {}).get("state")
            filing_archive_state = payload.get("filing_archive", {}).get("state")
            fact_basis_state = payload.get("fact_basis", {}).get("state")
            evidence_state = payload.get("remediation_evidence", {}).get("state")
            tax_impact_state = payload.get("tax_impact", {}).get("state")
            remediation_progress = payload.get("remediation_progress", {}).get(
                "progress"
            )
            has_limit = (
                finding.source_warning
                or finding.professional_warning
                or bool(finding.missing_fact_keys)
                or bool(finding.missing_parameter_keys)
                or obligation_state in ("not_started", "attention")
                or data_basis_state in ("no_period", "missing", "warning", "blocked")
                or filing_archive_state in ("not_started", "attention", "blocked")
                or fact_basis_state in ("not_started", "blocked")
                or evidence_state in ("none", "partial")
                or tax_impact_state in ("pending", "integrity_issue", "unquantifiable")
                or (remediation_progress is not None and remediation_progress < 100)
            )
            if finding.ai_analysis_count:
                finding.cn_ai_guidance_state = "generated"
                finding.cn_ai_guidance_next_action = _(
                    "打开已有 AI 引导，按步骤核对事实、证据、整改和报告限制。"
                )
            elif has_limit:
                finding.cn_ai_guidance_state = "limited"
                finding.cn_ai_guidance_next_action = _(
                    "可生成受控 AI 引导，但必须先标明来源、专业签核或数据限制。"
                )
            else:
                finding.cn_ai_guidance_state = "ready"
                finding.cn_ai_guidance_next_action = _(
                    "生成受控 AI 引导，获取分步骤处理建议和证据清单。"
                )

    def _cn_ai_guidance_input(self):
        self.ensure_one()
        task = self.current_task_id
        profile = self.assessment_id.profile_id
        snapshots = self.fact_snapshot_ids
        missing_fact_keys = (
            self.missing_fact_keys
            if isinstance(self.missing_fact_keys, list)
            else []
        )
        fact_issue_count = len(
            snapshots.filtered(
                lambda snapshot: snapshot.quality_state
                in ("missing", "stale", "truncated", "error")
                or not snapshot.is_complete
                or not snapshot.is_full_dataset
            )
        )
        missing_fact_count = len(missing_fact_keys)
        verified_evidence_count = 0
        evidence_count = 0
        if task:
            evidence_count = len(task.evidence_ids)
            verified_evidence_count = len(
                task.evidence_ids.filtered(lambda evidence: evidence.state == "verified")
            )
        if evidence_count and evidence_count == verified_evidence_count:
            evidence_state = "verified"
        elif evidence_count:
            evidence_state = "partial"
        else:
            evidence_state = "none"
        return {
            "schema": "sdoo.cn.ai-guidance.input.v1",
            "finding_id": self.id,
            "assessment_id": self.assessment_id.id,
            "company_id": self.company_id.id,
            "period_start": fields.Date.to_string(
                self.assessment_id.period_start
            )
            if self.assessment_id.period_start
            else None,
            "period_end": fields.Date.to_string(self.assessment_id.period_end)
            if self.assessment_id.period_end
            else None,
            "rule_code": self.rule_id.code,
            "rule_version": self.rule_version_id.version,
            "result": self.result,
            "risk_level": self.risk_level,
            "title": self.title,
            "summary": self.summary,
            "legal_basis": self.legal_basis,
            "recommendation": self.recommendation,
            "evidence_required": self.evidence_required,
            "review_state": self.review_state,
            "review_notes": self.review_notes,
            "source_warning": bool(self.source_warning),
            "professional_warning": bool(self.professional_warning),
            "missing_fact_keys": missing_fact_keys,
            "missing_parameter_keys": self.missing_parameter_keys,
            "fact_snapshot_checksums": sorted(
                self.fact_snapshot_ids.mapped("checksum")
            ),
            "fact_basis": {
                "snapshot_count": len(snapshots),
                "issue_count": fact_issue_count,
                "missing_fact_count": missing_fact_count,
                "state": (
                    "blocked"
                    if fact_issue_count or missing_fact_count
                    else "ready"
                    if snapshots
                    else "not_started"
                ),
            },
            "obligation_readiness": {
                "state": profile.cn_workbench_obligation_state,
                "next_action": profile.cn_workbench_obligation_next_action,
                "candidate_count": profile.cn_workbench_obligation_count,
                "applicable_count": (
                    profile.cn_workbench_applicable_obligation_count
                ),
                "pending_review_count": (
                    profile.cn_workbench_pending_obligation_count
                ),
                "filing_obligation_count": (
                    profile.cn_workbench_filing_obligation_count
                ),
            },
            "data_basis": {
                "state": self.assessment_id.cn_data_basis_state,
                "next_action": self.assessment_id.cn_data_basis_next_action,
                "dataset_count": self.assessment_id.cn_data_basis_dataset_count,
                "ready_dataset_count": self.assessment_id.cn_data_basis_ready_count,
                "warning_dataset_count": self.assessment_id.cn_data_basis_warning_count,
                "blocked_dataset_count": self.assessment_id.cn_data_basis_blocked_count,
                "normalized_record_count": (
                    self.assessment_id.cn_data_basis_normalized_record_count
                ),
                "required_type_count": (
                    self.assessment_id.cn_data_basis_required_type_count
                ),
                "ready_type_count": self.assessment_id.cn_data_basis_ready_type_count,
                "missing_type_count": (
                    self.assessment_id.cn_data_basis_missing_type_count
                ),
                "missing_type_summary": (
                    self.assessment_id.cn_data_basis_missing_type_summary
                    or None
                ),
            },
            "filing_archive": {
                "state": profile.cn_workbench_filing_archive_state,
                "next_action": profile.cn_workbench_filing_archive_next_action,
                "archive_count": profile.cn_workbench_filing_archive_count,
                "sealed_count": (
                    profile.cn_workbench_sealed_filing_archive_count
                ),
                "issue_count": profile.cn_workbench_filing_archive_issue_count,
            },
            "task": {
                "id": task.id or None,
                "state": task.state if task else None,
                "assignee_id": task.assignee_id.id if task else None,
                "due_date": fields.Date.to_string(task.due_date)
                if task and task.due_date
                else None,
                "is_overdue": bool(task.is_overdue) if task else False,
                "verification_state": task.verification_state if task else None,
            },
            "remediation_evidence": {
                "state": evidence_state,
                "evidence_count": evidence_count,
                "verified_evidence_count": verified_evidence_count,
            },
            "reconciliation_risk": {
                "state": self.cn_reconciliation_risk_state
                if "cn_reconciliation_risk_state" in self._fields
                else None,
                "summary": self.cn_reconciliation_risk_summary
                if "cn_reconciliation_risk_summary" in self._fields
                else None,
                "next_action": self.cn_reconciliation_risk_next_action
                if "cn_reconciliation_risk_next_action" in self._fields
                else None,
            },
            "tax_impact": {
                "state": self.cn_tax_impact_state
                if "cn_tax_impact_state" in self._fields
                else None,
                "case_count": self.cn_tax_impact_case_count
                if "cn_tax_impact_case_count" in self._fields
                else 0,
                "pending_count": self.cn_tax_impact_pending_review_count
                if "cn_tax_impact_pending_review_count" in self._fields
                else 0,
                "unquantifiable_count": (
                    self.cn_tax_impact_unquantifiable_review_count
                    if "cn_tax_impact_unquantifiable_review_count" in self._fields
                    else 0
                ),
                "integrity_issue_count": self.cn_tax_impact_integrity_issue_count
                if "cn_tax_impact_integrity_issue_count" in self._fields
                else 0,
                "reviewed_underpayment_amount": (
                    self.cn_tax_impact_reviewed_underpayment_amount
                    if "cn_tax_impact_reviewed_underpayment_amount" in self._fields
                    else 0.0
                ),
                "reviewed_overpayment_amount": (
                    self.cn_tax_impact_reviewed_overpayment_amount
                    if "cn_tax_impact_reviewed_overpayment_amount" in self._fields
                    else 0.0
                ),
                "reviewed_timing_amount": (
                    self.cn_tax_impact_reviewed_timing_amount
                    if "cn_tax_impact_reviewed_timing_amount" in self._fields
                    else 0.0
                ),
                "summary": self.cn_tax_impact_summary
                if "cn_tax_impact_summary" in self._fields
                else None,
            },
            "remediation_progress": {
                "progress": task.cn_remediation_progress
                if task and "cn_remediation_progress" in task._fields
                else None,
                "summary": task.cn_remediation_summary
                if task and "cn_remediation_summary" in task._fields
                else None,
                "rescan_stage": task.cn_remediation_rescan_stage
                if task and "cn_remediation_rescan_stage" in task._fields
                else None,
                "traceability_state": task.cn_remediation_traceability_state
                if task and "cn_remediation_traceability_state" in task._fields
                else None,
                "traceability_gap_count": task.cn_remediation_traceability_gap_count
                if task and "cn_remediation_traceability_gap_count" in task._fields
                else 0,
            },
        }

    def _cn_ai_guidance_text(self, payload):
        self.ensure_one()
        warning_lines = []
        if payload["source_warning"]:
            warning_lines.append(
                "- 官方来源仍有待复核项，不能把当前输出作为最终合规结论。"
            )
        if payload["professional_warning"]:
            warning_lines.append(
                "- 规则专业签核仍有待完善项，需要专业人员复核后再进入正式结论。"
            )
        if payload["missing_fact_keys"]:
            warning_lines.append(
                "- 存在缺失事实，需要先补齐数据或在报告中披露范围限制。"
            )
        if payload["missing_parameter_keys"]:
            warning_lines.append(
                "- 存在缺失参数，需要确认适用参数来源和期间。"
            )
        obligation_readiness = payload.get("obligation_readiness", {})
        if obligation_readiness.get("state") in ("not_started", "attention"):
            warning_lines.append(
                "- 纳税义务适用性尚未完全确认；AI 引导只能作为处理线索，不能替代义务适用判断或申报结论。"
            )
        data_basis = payload.get("data_basis", {})
        if data_basis.get("state") in ("no_period", "missing", "warning", "blocked"):
            warning_lines.append(
                "- Assessment data basis is incomplete; disclose missing data types and keep report limitations visible."
            )
        if not warning_lines:
            warning_lines.append("- 当前未发现来源、签核或事实缺口警示。")

        task = payload["task"]
        obligation_line = _(
            "状态 %(state)s；候选 %(candidate)s；已适用 %(applicable)s；待确认 %(pending)s；申报类 %(filing)s；下一步：%(next_action)s",
            state=obligation_readiness.get("state") or "-",
            candidate=obligation_readiness.get("candidate_count") or 0,
            applicable=obligation_readiness.get("applicable_count") or 0,
            pending=obligation_readiness.get("pending_review_count") or 0,
            filing=obligation_readiness.get("filing_obligation_count") or 0,
            next_action=obligation_readiness.get("next_action") or "-",
        )
        filing_archive = payload.get("filing_archive", {})
        filing_archive_line = (
            "Filing/payment archive: state=%s; archives=%s; sealed=%s; "
            "issues=%s; next=%s"
            % (
                filing_archive.get("state") or "-",
                filing_archive.get("archive_count") or 0,
                filing_archive.get("sealed_count") or 0,
                filing_archive.get("issue_count") or 0,
                filing_archive.get("next_action") or "-",
            )
        )
        due_line = task["due_date"] or "尚未设置"
        data_basis_line = (
            "Data basis: state=%s; datasets=%s; ready_types=%s/%s; missing=%s; missing_types=%s; next=%s"
            % (
                data_basis.get("state") or "-",
                data_basis.get("dataset_count") or 0,
                data_basis.get("ready_type_count") or 0,
                data_basis.get("required_type_count") or 0,
                data_basis.get("missing_type_count") or 0,
                data_basis.get("missing_type_summary") or "-",
                data_basis.get("next_action") or "-",
            )
        )
        fact_basis = payload.get("fact_basis", {})
        fact_basis_line = (
            "Fact basis: state=%s; snapshots=%s; issues=%s; missing=%s"
            % (
                fact_basis.get("state") or "-",
                fact_basis.get("snapshot_count") or 0,
                fact_basis.get("issue_count") or 0,
                fact_basis.get("missing_fact_count") or 0,
            )
        )
        remediation_evidence = payload.get("remediation_evidence", {})
        remediation_evidence_line = (
            "Remediation evidence: state=%s; verified=%s/%s"
            % (
                remediation_evidence.get("state") or "-",
                remediation_evidence.get("verified_evidence_count") or 0,
                remediation_evidence.get("evidence_count") or 0,
            )
        )
        reconciliation_risk = payload.get("reconciliation_risk", {})
        reconciliation_risk_line = (
            "Reconciliation risk: state=%s; summary=%s; next=%s"
            % (
                reconciliation_risk.get("state") or "-",
                reconciliation_risk.get("summary") or "-",
                reconciliation_risk.get("next_action") or "-",
            )
        )
        tax_impact = payload.get("tax_impact", {})
        tax_impact_line = (
            "Tax impact: state=%s; cases=%s; pending=%s; underpayment=%s; "
            "overpayment=%s; timing=%s"
            % (
                tax_impact.get("state") or "-",
                tax_impact.get("case_count") or 0,
                tax_impact.get("pending_count") or 0,
                tax_impact.get("reviewed_underpayment_amount") or 0.0,
                tax_impact.get("reviewed_overpayment_amount") or 0.0,
                tax_impact.get("reviewed_timing_amount") or 0.0,
            )
        )
        remediation_progress = payload.get("remediation_progress", {})
        remediation_progress_line = (
            "Remediation progress: progress=%s%%; stage=%s; traceability=%s; summary=%s"
            % (
                remediation_progress.get("progress")
                if remediation_progress.get("progress") is not None
                else "-",
                remediation_progress.get("rescan_stage") or "-",
                remediation_progress.get("traceability_state") or "-",
                remediation_progress.get("summary") or "-",
            )
        )
        assignee_line = (
            self.current_task_id.assignee_id.display_name
            if self.current_task_id
            else "尚未指定"
        )
        return _(
            "AI 分析仅为辅助材料，不构成税务、法律、审计或监管结论。\n\n"
            "一、风险概览\n"
            "- 风险等级：%(risk)s\n"
            "- 判断结果：%(result)s\n"
            "- 事项：%(title)s\n"
            "- 适用期间：%(period_start)s 至 %(period_end)s\n\n"
            "二、原因与依据\n"
            "%(summary)s\n\n"
            "官方依据摘要：\n%(basis)s\n\n"
            "三、纳税义务适用性边界\n"
            "%(obligation_line)s\n\n"
            "%(filing_archive_line)s\n\n"
            "%(data_basis_line)s\n\n"
            "%(fact_basis_line)s\n\n"
            "%(reconciliation_risk_line)s\n\n"
            "%(tax_impact_line)s\n\n"
            "%(remediation_evidence_line)s\n\n"
            "%(remediation_progress_line)s\n\n"
            "四、处理建议\n"
            "%(recommendation)s\n\n"
            "五、证据要求\n"
            "%(evidence)s\n\n"
            "六、当前限制与注意事项\n"
            "%(warnings)s\n\n"
            "七、下一步操作\n"
            "1. 由责任人核对命中事实、期间和适用规则。\n"
            "2. 先确认纳税义务适用性和官方来源，再把扫描结果用于申报或报告结论。\n"
            "3. 按证据要求补齐或封存正式证据。\n"
            "4. 对可能影响税额的事项建立税务影响复核。\n"
            "5. 若需要整改，按整改任务推进并在完成后发起验证复扫。\n"
            "6. 编制正式报告前，确认所有限制、不确定性和管理层回应已记录。\n\n"
            "整改跟踪：负责人 %(assignee)s；截止日期 %(due)s；当前状态 %(task_state)s；验证状态 %(verification)s。",
            risk=payload["risk_level"],
            result=payload["result"],
            title=payload["title"],
            period_start=payload["period_start"] or "-",
            period_end=payload["period_end"] or "-",
            summary=payload["summary"] or "暂无规则结论摘要。",
            basis=payload["legal_basis"] or "暂无可展示依据摘要。",
            obligation_line=obligation_line,
            filing_archive_line=filing_archive_line,
            data_basis_line=data_basis_line,
            fact_basis_line=fact_basis_line,
            reconciliation_risk_line=reconciliation_risk_line,
            tax_impact_line=tax_impact_line,
            remediation_evidence_line=remediation_evidence_line,
            remediation_progress_line=remediation_progress_line,
            recommendation=payload["recommendation"] or "暂无整改建议。",
            evidence=payload["evidence_required"] or "暂无证据要求。",
            warnings="\n".join(warning_lines),
            assignee=assignee_line,
            due=due_line,
            task_state=task["state"] or "尚未创建整改任务",
            verification=task["verification_state"] or "尚未提交验证",
        )

    def action_generate_cn_ai_guidance(self):
        self.ensure_one()
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_user"
        ):
            raise AccessError(_("只有合规用户可以生成受控 AI 引导。"))
        if self.assessment_id.country_id.code != "CN":
            raise UserError(_("中国受控 AI 引导仅适用于中国合规风险事项。"))
        if self.result not in ("fail", "unknown", "error"):
            raise UserError(_("只有失败、待确认或执行错误的事项需要生成引导。"))

        payload = self._cn_ai_guidance_input()
        analysis = self.env["sudo.compliance.ai.analysis"]._create_generation(
            {
                "finding_id": self.id,
                "provider_key": AI_GUIDANCE_PROVIDER,
                "jurisdiction_code": "CN",
                "state": "fallback",
                "analysis": self._cn_ai_guidance_text(payload),
                "generation_note": _(
                    "由中国合规包根据已冻结规则结果、事实快照、整改建议和证据要求生成；未调用外部模型。"
                ),
                "prompt_version": AI_GUIDANCE_PROMPT_VERSION,
                "model_name": AI_GUIDANCE_MODEL,
                "input_checksum": _checksum(payload),
                "input_snapshot_json": payload,
                "source_warning": bool(self.source_warning),
                "professional_warning": bool(self.professional_warning),
            }
        )
        action = self.sudo().action_open_ai_analyses()
        action["res_id"] = analysis.id
        action["view_mode"] = "form"
        action["views"] = [(False, "form")]
        return action
