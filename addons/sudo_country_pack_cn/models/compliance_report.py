import base64
import binascii
import hashlib
import json

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


_REPORT_TRANSITION_MARKER = object()

_RISK_LABELS = {
    "info": "信息",
    "low": "低",
    "medium": "中",
    "high": "高",
    "critical": "严重",
}
_RESULT_LABELS = {
    "pass": "通过",
    "fail": "失败",
    "unknown": "待确认",
    "not_applicable": "不适用",
    "error": "执行错误",
}
_REVIEW_LABELS = {
    "not_required": "无需复核",
    "pending": "待复核",
    "confirmed": "已确认",
    "correction_required": "需整改",
}
_TASK_LABELS = {
    "open": "待处理",
    "in_progress": "处理中",
    "waiting": "等待资料",
    "pending_review": "待复核",
    "blocked": "验证未通过",
    "done": "已完成",
    "cancelled": "已取消",
}
_EVIDENCE_LABELS = {
    "draft": "草稿",
    "submitted": "待验证",
    "verified": "已验证",
    "rejected": "已退回",
}
_IMPACT_LABELS = {
    "undetermined": "尚未判断税务影响",
    "no_tax_impact": "复核后无税额影响",
    "timing_difference": "期间错配影响",
    "potential_underpayment": "潜在少缴税影响",
    "potential_overpayment": "潜在多缴税影响",
}
_CONCLUSION_LABELS = {
    "clear": "范围内未发现未解决高风险",
    "action_required": "发现需要整改的事项",
    "limited": "存在范围或数据限制",
    "limited_action_required": "存在限制且需要整改",
}


def _canonical_checksum(payload):
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _date_value(value):
    return fields.Date.to_string(value) if value else None


def _datetime_value(value):
    return fields.Datetime.to_string(value) if value else None


def _amount_value(value, currency):
    decimals = currency.decimal_places if currency else 2
    return f"{float(value or 0.0):.{decimals}f}"


def _text_is_complete(value, minimum=20):
    return len((value or "").strip()) >= minimum


def _controlled_filing_domain(assessment):
    if (
        not assessment.profile_id
        or not assessment.period_start
        or not assessment.period_end
    ):
        return [("id", "=", 0)]
    return [
        ("profile_id", "=", assessment.profile_id.id),
        ("period_start", "<=", assessment.period_end),
        ("period_end", ">=", assessment.period_start),
        "|",
        "|",
        ("cn_vat_reconciliation_run_id", "!=", False),
        ("cn_cit_reconciliation_run_id", "!=", False),
        ("cn_iit_reconciliation_run_id", "!=", False),
    ]


class SudoChinaComplianceReport(models.Model):
    _name = "sudo.cn.compliance.report"
    _description = "China Governed Compliance Report"
    _order = "issued_at desc, create_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(
        string="报告编号",
        required=True,
        readonly=True,
        copy=False,
        index=True,
    )
    title = fields.Char(string="报告名称", required=True)
    assessment_id = fields.Many2one(
        "sudo.compliance.assessment",
        string="来源评估",
        required=True,
        ondelete="restrict",
        index=True,
        check_company=True,
        domain="[('country_id.code', '=', 'CN'), ('state', '=', 'completed')]",
    )
    profile_id = fields.Many2one(
        related="assessment_id.profile_id",
        string="合规档案",
        store=True,
        readonly=True,
        index=True,
    )
    company_id = fields.Many2one(
        related="assessment_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    country_id = fields.Many2one(
        related="assessment_id.country_id",
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id",
        store=True,
        readonly=True,
    )
    period_start = fields.Date(
        related="assessment_id.period_start",
        store=True,
        readonly=True,
    )
    period_end = fields.Date(
        related="assessment_id.period_end",
        store=True,
        readonly=True,
    )
    revision = fields.Integer(string="报告版本", required=True, readonly=True)
    supersedes_id = fields.Many2one(
        "sudo.cn.compliance.report",
        string="替代原报告",
        readonly=True,
        ondelete="restrict",
        index=True,
        check_company=True,
    )
    replacement_ids = fields.One2many(
        "sudo.cn.compliance.report",
        "supersedes_id",
        string="后续报告",
        readonly=True,
    )
    state = fields.Selection(
        [
            ("draft", "编制中"),
            ("submitted", "待独立批准"),
            ("issued", "已签发"),
            ("superseded", "已被替代"),
            ("withdrawn", "已撤回"),
        ],
        string="状态",
        required=True,
        default="draft",
        readonly=True,
        copy=False,
        index=True,
    )
    conclusion_state = fields.Selection(
        [
            ("clear", "范围内未发现未解决高风险"),
            ("action_required", "发现需要整改的事项"),
            ("limited", "存在范围或数据限制"),
            ("limited_action_required", "存在限制且需要整改"),
        ],
        string="报告结论",
        readonly=True,
        copy=False,
        index=True,
    )
    executive_summary = fields.Text(string="管理层摘要", required=True)
    scope_statement = fields.Text(string="范围说明", required=True)
    limitation_statement = fields.Text(string="限制与不确定性")
    management_response = fields.Text(string="管理层整改回应")
    prepared_by_id = fields.Many2one(
        "res.users",
        string="编制人",
        required=True,
        readonly=True,
        copy=False,
    )
    reviewer_id = fields.Many2one(
        "res.users",
        string="报告批准人",
        required=True,
        domain="[('company_ids', 'in', [company_id])]",
    )
    independence_exception_reason = fields.Text(
        string="同人批准例外理由",
        help="编制、提交与批准职责未分离时，记录经授权的例外原因。",
    )
    review_notes = fields.Text(string="独立批准意见", copy=False)
    submitted_by_id = fields.Many2one(
        "res.users", string="提交人", readonly=True, copy=False
    )
    submitted_at = fields.Datetime(string="提交时间", readonly=True, copy=False)
    issued_by_id = fields.Many2one(
        "res.users", string="签发人", readonly=True, copy=False
    )
    issued_at = fields.Datetime(string="签发时间", readonly=True, copy=False)
    withdrawal_reason = fields.Text(string="撤回理由", copy=False)
    withdrawn_by_id = fields.Many2one(
        "res.users", string="撤回人", readonly=True, copy=False
    )
    withdrawn_at = fields.Datetime(string="撤回时间", readonly=True, copy=False)
    snapshot_json = fields.Json(
        string="报告内容快照", readonly=True, copy=False, default=dict
    )
    snapshot_checksum = fields.Char(
        string="内容快照 SHA-256", readonly=True, copy=False, index=True
    )
    approval_checksum = fields.Char(
        string="批准 SHA-256", readonly=True, copy=False, index=True
    )
    issued_pdf = fields.Binary(
        string="已签发 PDF", attachment=True, readonly=True, copy=False
    )
    issued_pdf_filename = fields.Char(
        string="PDF 文件名", readonly=True, copy=False
    )
    issued_pdf_sha256 = fields.Char(
        string="PDF SHA-256", readonly=True, copy=False, index=True
    )
    snapshot_integrity_state = fields.Selection(
        [
            ("unsealed", "尚未冻结"),
            ("verified", "源资料未变化"),
            ("source_changed", "源资料已变化"),
        ],
        string="快照来源完整性",
        compute="_compute_snapshot_integrity_state",
    )
    approval_integrity_state = fields.Selection(
        [
            ("not_issued", "尚未签发"),
            ("verified", "批准记录完整性正常"),
            ("missing", "批准记录缺失"),
            ("checksum_mismatch", "批准记录已变化"),
        ],
        string="批准记录完整性",
        compute="_compute_approval_integrity_state",
    )
    pdf_integrity_state = fields.Selection(
        [
            ("not_issued", "尚未生成"),
            ("verified", "PDF 完整性正常"),
            ("missing", "PDF 缺失"),
            ("checksum_mismatch", "PDF 已变化"),
        ],
        string="PDF 完整性",
        compute="_compute_pdf_integrity_state",
    )
    has_material_limitations = fields.Boolean(
        string="存在重大限制", readonly=True, copy=False
    )
    finding_count = fields.Integer(string="风险结果", readonly=True, copy=False)
    critical_count = fields.Integer(string="严重风险", readonly=True, copy=False)
    high_count = fields.Integer(string="高风险", readonly=True, copy=False)
    open_task_count = fields.Integer(string="未关闭整改", readonly=True, copy=False)
    overdue_task_count = fields.Integer(string="逾期整改", readonly=True, copy=False)
    remediation_task_count = fields.Integer(
        string="Remediation Tasks", readonly=True, copy=False
    )
    remediation_verified_count = fields.Integer(
        string="Verified Remediation", readonly=True, copy=False
    )
    remediation_pending_verification_count = fields.Integer(
        string="Remediation Pending Verification", readonly=True, copy=False
    )
    evidence_count = fields.Integer(string="证据记录", readonly=True, copy=False)
    verified_evidence_count = fields.Integer(
        string="已验证证据", readonly=True, copy=False
    )
    tax_impact_pending_count = fields.Integer(
        string="待复核税务影响", readonly=True, copy=False
    )
    reviewed_underpayment_amount = fields.Monetary(
        string="已复核潜在少缴税影响",
        currency_field="currency_id",
        readonly=True,
        copy=False,
    )
    reviewed_overpayment_amount = fields.Monetary(
        string="已复核潜在多缴税影响",
        currency_field="currency_id",
        readonly=True,
        copy=False,
    )
    reviewed_timing_amount = fields.Monetary(
        string="已复核期间错配影响",
        currency_field="currency_id",
        readonly=True,
        copy=False,
    )

    cn_report_center_stage = fields.Selection(
        [
            ("draft", "编制中"),
            ("approval", "待批准"),
            ("issued", "已签发"),
            ("source_changed", "来源已变化"),
            ("integrity_issue", "完整性异常"),
            ("closed", "历史版本"),
        ],
        string="报告中心状态",
        compute="_compute_cn_report_center_display",
    )
    cn_report_center_integrity_state = fields.Selection(
        [
            ("unsealed", "未封存"),
            ("verified", "已校验"),
            ("warning", "需要复核"),
            ("blocked", "禁止分发"),
        ],
        string="报告完整性",
        compute="_compute_cn_report_center_display",
    )
    cn_report_center_next_action = fields.Char(
        string="下一步动作",
        compute="_compute_cn_report_center_display",
    )
    cn_report_center_period_label = fields.Char(
        string="报告期间",
        compute="_compute_cn_report_center_display",
    )

    cn_report_traceability_state = fields.Selection(
        [
            ("blocked", "Blocked"),
            ("action_required", "Action Required"),
            ("complete", "Complete"),
        ],
        string="Traceability",
        compute="_compute_cn_report_traceability",
    )
    cn_report_traceability_gap_count = fields.Integer(
        string="Traceability Gaps",
        compute="_compute_cn_report_traceability",
    )
    cn_report_traceability_next_action = fields.Char(
        string="Traceability Next Action",
        compute="_compute_cn_report_traceability",
    )

    _assessment_revision_unique = models.Constraint(
        "unique(assessment_id, revision)",
        "同一评估的正式报告版本不能重复。",
    )

    _draft_fields = {
        "title",
        "executive_summary",
        "scope_statement",
        "limitation_statement",
        "management_response",
        "reviewer_id",
        "independence_exception_reason",
    }
    _transition_fields = {
        "state",
        "conclusion_state",
        "submitted_by_id",
        "submitted_at",
        "issued_by_id",
        "issued_at",
        "withdrawn_by_id",
        "withdrawn_at",
        "snapshot_json",
        "snapshot_checksum",
        "approval_checksum",
        "issued_pdf",
        "issued_pdf_filename",
        "issued_pdf_sha256",
        "has_material_limitations",
        "finding_count",
        "critical_count",
        "high_count",
        "open_task_count",
        "overdue_task_count",
        "evidence_count",
        "verified_evidence_count",
        "tax_impact_pending_count",
        "reviewed_underpayment_amount",
        "reviewed_overpayment_amount",
        "reviewed_timing_amount",
    }
    _identity_fields = {
        "name",
        "assessment_id",
        "prepared_by_id",
        "revision",
        "supersedes_id",
    }

    @api.model
    def _require_preparer(self):
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以编制正式报告。"))

    @api.model
    def _require_approver(self):
        if not self.env.user.has_group(
            "sudo_country_pack_cn.group_cn_report_approver"
        ):
            raise AccessError(_("只有中国合规报告批准人可以执行独立批准。"))

    @api.model_create_multi
    def create(self, vals_list):
        self._require_preparer()
        prepared = self.env.user
        normalized_list = []
        for incoming in vals_list:
            values = dict(incoming)
            assessment = self.env["sudo.compliance.assessment"].browse(
                values.get("assessment_id")
            ).exists()
            assessment.ensure_one()
            if assessment.country_id != self.env.ref("base.cn"):
                raise ValidationError(_("只能为中国合规评估编制正式报告。"))
            if assessment.state != "completed":
                raise ValidationError(_("只有已完成评估可以编制正式报告。"))
            latest = self.search(
                [("assessment_id", "=", assessment.id)],
                order="revision desc, id desc",
                limit=1,
            )
            current = self.search(
                [
                    ("assessment_id", "=", assessment.id),
                    ("state", "=", "issued"),
                ],
                order="issued_at desc, id desc",
                limit=1,
            )
            sequence = self.env["ir.sequence"].next_by_code(
                "sudo.cn.compliance.report"
            ) or _("新报告")
            values.update(
                {
                    "name": sequence,
                    "revision": (latest.revision or 0) + 1,
                    "prepared_by_id": prepared.id,
                    "state": "draft",
                    "supersedes_id": current.id or False,
                    "snapshot_json": {},
                    "snapshot_checksum": False,
                    "approval_checksum": False,
                    "issued_pdf": False,
                    "issued_pdf_filename": False,
                    "issued_pdf_sha256": False,
                    "conclusion_state": False,
                    "submitted_by_id": False,
                    "submitted_at": False,
                    "issued_by_id": False,
                    "issued_at": False,
                    "withdrawn_by_id": False,
                    "withdrawn_at": False,
                    "review_notes": False,
                    "withdrawal_reason": False,
                    "has_material_limitations": False,
                    "finding_count": 0,
                    "critical_count": 0,
                    "high_count": 0,
                    "open_task_count": 0,
                    "overdue_task_count": 0,
                    "remediation_task_count": 0,
                    "remediation_verified_count": 0,
                    "remediation_pending_verification_count": 0,
                    "evidence_count": 0,
                    "verified_evidence_count": 0,
                    "tax_impact_pending_count": 0,
                    "reviewed_underpayment_amount": 0.0,
                    "reviewed_overpayment_amount": 0.0,
                    "reviewed_timing_amount": 0.0,
                }
            )
            normalized_list.append(values)
        reports = super().create(normalized_list)
        self.env["sudo.compliance.audit.event"]._log_records(
            reports,
            "cn_compliance_report.created",
            new_state="draft",
            details={"report_ids": reports.ids},
        )
        return reports

    def write(self, values):
        changed = set(values)
        transition = (
            self.env.context.get("cn_compliance_report_transition")
            is _REPORT_TRANSITION_MARKER
        )
        if changed & (self._transition_fields | self._identity_fields) and not transition:
            raise AccessError(_("正式报告受控字段只能通过状态操作更新。"))
        if changed & self._draft_fields:
            self._require_preparer()
            if any(report.state != "draft" for report in self):
                raise UserError(_("只有编制中的报告可以修改报告内容。"))
        if "review_notes" in changed and not transition:
            self._require_approver()
            if any(
                report.state != "submitted"
                or report.reviewer_id != self.env.user
                for report in self
            ):
                raise AccessError(_("只有指定批准人可以填写独立批准意见。"))
        if "withdrawal_reason" in changed and not transition:
            self._require_preparer()
            if any(report.state != "issued" for report in self):
                raise UserError(_("只有当前已签发报告可以填写撤回理由。"))
        result = super().write(values)
        if "review_notes" in changed and not transition:
            self.env["sudo.compliance.audit.event"]._log_records(
                self,
                "cn_compliance_report.review_notes_updated",
                details={
                    "review_notes_checksum": hashlib.sha256(
                        (values.get("review_notes") or "").encode("utf-8")
                    ).hexdigest()
                },
            )
        if "withdrawal_reason" in changed and not transition:
            self.env["sudo.compliance.audit.event"]._log_records(
                self,
                "cn_compliance_report.withdrawal_reason_updated",
                details={
                    "reason_checksum": hashlib.sha256(
                        (values.get("withdrawal_reason") or "").encode("utf-8")
                    ).hexdigest()
                },
            )
        return result

    def _transition_write(self, values):
        return self.with_context(
            cn_compliance_report_transition=_REPORT_TRANSITION_MARKER
        ).write(values)

    def _lock_for_transition(self):
        if not self.ids:
            return self
        self.env.cr.execute(
            "SELECT id FROM sudo_cn_compliance_report "
            "WHERE id IN %s ORDER BY id FOR UPDATE",
            (tuple(self.ids),),
        )
        self.invalidate_recordset()
        return self

    def unlink(self):
        self._require_preparer()
        if any(report.state != "draft" for report in self):
            raise UserError(_("已提交或已签发报告属于审计记录，不允许删除。"))
        return super().unlink()

    def copy(self, default=None):
        raise UserError(_("正式报告不能复制，请从来源评估建立新版本。"))

    @api.constrains("assessment_id", "supersedes_id", "reviewer_id")
    def _check_report_links(self):
        approver_group = self.env.ref(
            "sudo_country_pack_cn.group_cn_report_approver"
        )
        for report in self:
            if report.supersedes_id:
                if report.supersedes_id == report:
                    raise ValidationError(_("报告不能替代自身。"))
                if report.supersedes_id.assessment_id != report.assessment_id:
                    raise ValidationError(_("替代关系必须属于同一来源评估。"))
            if report.reviewer_id:
                if approver_group not in report.reviewer_id.group_ids:
                    raise ValidationError(_("所选用户不是中国合规报告批准人。"))
                if report.company_id not in report.reviewer_id.company_ids:
                    raise ValidationError(_("报告批准人必须具有当前公司访问权限。"))

    def _evidence_payload(self):
        self.ensure_one()
        rows = []
        for evidence in self.assessment_id.report_evidence_ids.sorted("id"):
            current_checksum = None
            if evidence.document_file or evidence.external_reference:
                current_checksum = evidence._document_fingerprint()[
                    "document_checksum"
                ]
            integrity_state = "not_verified"
            if evidence.state == "verified":
                integrity_state = (
                    "verified"
                    if current_checksum == evidence.document_checksum
                    else "checksum_mismatch"
                )
            rows.append(
                {
                    "id": evidence.id,
                    "name": evidence.name,
                    "evidence_type": evidence.evidence_type,
                    "state": evidence.state,
                    "evidence_date": _date_value(evidence.evidence_date),
                    "issuer": evidence.issuer or None,
                    "description": evidence.description or None,
                    "stored_checksum": evidence.document_checksum or None,
                    "current_checksum": current_checksum,
                    "integrity_state": integrity_state,
                    "verified_by_id": evidence.verified_by_id.id or None,
                    "verified_at": _datetime_value(evidence.verified_at),
                }
            )
        return rows

    def _obligation_readiness_payload(self):
        self.ensure_one()
        profile = self.assessment_id.profile_id
        obligation_rows = []
        for obligation in profile.obligation_ids.sorted("code"):
            obligation_rows.append(
                {
                    "id": obligation.id,
                    "code": obligation.code,
                    "name": obligation.name,
                    "domain_key": obligation.domain_key,
                    "applicability": obligation.applicability,
                    "authority": obligation.authority,
                    "authority_source_id": obligation.authority_source_id.id
                    or None,
                    "authority_source_name": obligation.authority_source_id.name
                    or None,
                    "filing_required": bool(obligation.filing_required),
                    "filing_frequency": obligation.filing_frequency,
                    "filing_type": obligation.filing_type or None,
                    "effective_from": _date_value(obligation.effective_from),
                }
            )
        return {
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
            "obligations": obligation_rows,
        }

    def _filing_archive_payload(self):
        self.ensure_one()
        assessment = self.assessment_id
        filings = self.env["sudo.compliance.filing"].sudo().search(
            _controlled_filing_domain(assessment),
            order="period_start, period_end, filing_code, id",
        )
        rows = []
        sealed_count = 0
        issue_count = 0
        for filing in filings:
            submission_state = filing.cn_submission_integrity_state
            payment_state = filing.cn_payment_integrity_state
            evidence_state = filing.cn_filing_center_evidence_state
            sealed = (
                submission_state in ("verified", "source_superseded")
                and payment_state
                in ("verified", "not_required", "source_superseded")
                and evidence_state == "verified"
            )
            issue = (
                submission_state in ("changed", "invalid", "unsealed")
                or payment_state in ("changed", "invalid", "unsealed")
                or evidence_state != "verified"
            )
            if sealed:
                sealed_count += 1
            if issue:
                issue_count += 1
            rows.append(
                {
                    "id": filing.id,
                    "name": filing.display_name,
                    "filing_code": filing.filing_code,
                    "filing_type": filing.filing_type,
                    "state": filing.state,
                    "period_start": _date_value(filing.period_start),
                    "period_end": _date_value(filing.period_end),
                    "due_date": _date_value(filing.due_date),
                    "authority_source_id": filing.authority_source_id.id
                    or None,
                    "authority_source_name": filing.authority_source_id.name
                    or None,
                    "submission_integrity_state": submission_state,
                    "payment_integrity_state": payment_state,
                    "evidence_state": evidence_state,
                    "submission_checksum": filing.cn_submission_checksum
                    or None,
                    "payment_checksum": filing.cn_payment_checksum or None,
                    "sealed": sealed,
                    "issue": issue,
                }
            )
        if not filings:
            state = "not_started"
            next_action = (
                "No controlled filing/payment archive exists for this report period."
            )
        elif issue_count:
            state = "blocked"
            next_action = (
                "Seal filing/payment archives and verify receipt/payment evidence before relying on the report."
            )
        elif sealed_count == len(filings):
            state = "ready"
            next_action = "Controlled filing/payment archives are sealed."
        else:
            state = "attention"
            next_action = "Review filing/payment archive evidence before sign-off."
        return {
            "state": state,
            "next_action": next_action,
            "archive_count": len(filings),
            "sealed_count": sealed_count,
            "issue_count": issue_count,
            "archives": rows,
        }

    def _snapshot_payload(self):
        self.ensure_one()
        assessment = self.assessment_id
        currency = self.currency_id
        findings = []
        for finding in assessment.finding_ids.sorted("id"):
            findings.append(
                {
                    "id": finding.id,
                    "rule_code": finding.rule_id.code,
                    "rule_version": finding.rule_version_id.version,
                    "result": finding.result,
                    "risk_level": finding.risk_level,
                    "title": finding.title,
                    "summary": finding.summary or None,
                    "legal_basis": finding.legal_basis or None,
                    "recommendation": finding.recommendation or None,
                    "evidence_required": finding.evidence_required or None,
                    "review_state": finding.review_state,
                    "reviewer_id": finding.reviewer_id.id or None,
                    "reviewed_at": _datetime_value(finding.reviewed_at),
                    "review_notes": finding.review_notes or None,
                    "source_warning": bool(finding.source_warning),
                    "professional_warning": bool(
                        finding.professional_warning
                    ),
                    "checksum": finding.checksum,
                    "fact_snapshot_checksums": sorted(
                        finding.fact_snapshot_ids.mapped("checksum")
                    ),
                    "result_details": finding.result_details_json or {},
                    "source_snapshot": finding.source_snapshot_json or [],
                    "professional_snapshot": (
                        finding.professional_snapshot_json or {}
                    ),
                }
            )

        facts = [
            {
                "id": snapshot.id,
                "key": snapshot.definition_id.key,
                "label": snapshot.definition_id.label,
                "quality_state": snapshot.quality_state,
                "record_count": snapshot.record_count,
                "is_complete": bool(snapshot.is_complete),
                "is_full_dataset": bool(snapshot.is_full_dataset),
                "captured_at": _datetime_value(snapshot.captured_at),
                "valid_at": _datetime_value(snapshot.valid_at),
                "provider_key": snapshot.provider_key,
                "provider_version": snapshot.provider_version,
                "aggregation_method": snapshot.aggregation_method,
                "value": snapshot.value_json,
                "checksum": snapshot.checksum,
            }
            for snapshot in assessment.fact_snapshot_ids.sorted("id")
        ]

        rules = [
            {
                "id": version.id,
                "code": version.rule_id.code,
                "version": version.version,
                "state": version.state,
                "checksum": version.checksum,
                "professional_review_state": version.professional_review_state,
                "professional_rule_checksum": (
                    version.professional_rule_checksum or None
                ),
            }
            for version in assessment.rule_version_ids.sorted("id")
        ]

        tasks = assessment.finding_ids.mapped("task_ids")
        tasks |= assessment.verification_task_ids
        task_rows = [
            {
                "id": task.id,
                "name": task.name,
                "finding_id": task.finding_id.id or None,
                "risk_level": task.risk_level,
                "state": task.state,
                "assignee_id": task.assignee_id.id or None,
                "assignee_name": task.assignee_id.name or None,
                "due_date": _date_value(task.due_date),
                "is_overdue": bool(task.is_overdue),
                "verification_state": task.verification_state,
                "verification_assessment_id": (
                    task.verification_assessment_id.id or None
                ),
                "verification_assessment_name": (
                    task.verification_assessment_id.display_name or None
                ),
                "verification_assessment_state": (
                    task.verification_assessment_id.state or None
                ),
                "verified_at": _datetime_value(task.verified_at),
                "verified_by_id": task.verified_by_id.id or None,
                "completion_notes": task.completion_notes or None,
                "verification_notes": task.verification_notes or None,
            }
            for task in tasks.sorted("id")
        ]

        impact_cases = []
        for case in assessment.cn_tax_impact_case_ids.sorted("id"):
            if case.state == "cancelled":
                continue
            impact_cases.append(
                {
                    "id": case.id,
                    "title": case.title,
                    "impact_direction": case.impact_direction,
                    "quantification_state": case.quantification_state,
                    "impact_amount": _amount_value(
                        case.impact_amount, currency
                    ),
                    "state": case.state,
                    "integrity_state": case.integrity_state,
                    "source_reference": case.source_reference,
                    "source_count": case.source_count,
                    "analysis": case.analysis,
                    "assumptions_limitations": (
                        case.assumptions_limitations
                    ),
                    "reviewer_id": case.reviewer_id.id or None,
                    "reviewed_at": _datetime_value(case.reviewed_at),
                    "review_checksum": case.review_checksum or None,
                }
            )

        ai_rows = [
            {
                "id": analysis.id,
                "finding_id": analysis.finding_id.id,
                "revision": analysis.revision,
                "state": analysis.state,
                "provider_key": analysis.provider_key,
                "model_name": analysis.model_name,
                "generated_at": _datetime_value(analysis.generated_at),
                "record_checksum": analysis.record_checksum,
                "source_warning": bool(analysis.source_warning),
                "professional_warning": bool(
                    analysis.professional_warning
                ),
            }
            for analysis in assessment.report_ai_analysis_ids.sorted("id")
        ]

        return {
            "schema": "sdoo.cn.compliance-report.v1",
            "report": {
                "id": self.id,
                "number": self.name,
                "revision": self.revision,
                "title": self.title,
                "executive_summary": self.executive_summary,
                "scope_statement": self.scope_statement,
                "limitation_statement": self.limitation_statement or None,
                "management_response": self.management_response or None,
                "prepared_by_id": self.prepared_by_id.id,
                "prepared_by_name": self.prepared_by_id.name,
                "reviewer_id": self.reviewer_id.id,
                "reviewer_name": self.reviewer_id.name,
                "independence_exception_reason": (
                    self.independence_exception_reason or None
                ),
                "supersedes_id": self.supersedes_id.id or None,
            },
            "assessment": {
                "id": assessment.id,
                "name": assessment.name,
                "company_id": assessment.company_id.id,
                "company_name": assessment.company_id.name,
                "profile_id": assessment.profile_id.id,
                "profile_name": assessment.profile_id.display_name,
                "country_code": assessment.country_id.code,
                "currency": currency.name,
                "evaluation_date": _date_value(assessment.evaluation_date),
                "period_start": _date_value(assessment.period_start),
                "period_end": _date_value(assessment.period_end),
                "completed_at": _datetime_value(assessment.completed_at),
                "report_state": assessment.report_state,
                "data_sufficiency_state": (
                    assessment.data_sufficiency_state
                ),
                "data_sufficiency_message": (
                    assessment.data_sufficiency_message
                ),
                "required_fact_count": assessment.required_fact_count,
                "complete_fact_count": assessment.complete_fact_count,
                "problem_fact_count": assessment.problem_fact_count,
                "finding_count": assessment.finding_count,
                "pass_count": assessment.pass_count,
                "fail_count": assessment.fail_count,
                "unknown_count": assessment.unknown_count,
                "error_count": assessment.error_count,
                "critical_count": assessment.critical_count,
                "high_count": assessment.high_count,
                "medium_count": assessment.medium_count,
                "low_count": assessment.low_count,
                "source_warning_count": assessment.source_warning_count,
                "professional_warning_count": (
                    assessment.professional_warning_count
                ),
                "review_pending_count": assessment.review_pending_count,
                "note": assessment.note or None,
            },
            "rules": rules,
            "obligation_readiness": self._obligation_readiness_payload(),
            "filing_archive": self._filing_archive_payload(),
            "facts": facts,
            "findings": findings,
            "tasks": task_rows,
            "evidence": self._evidence_payload(),
            "tax_impact": {
                "cases": impact_cases,
                "pending_count": assessment.cn_tax_impact_pending_count,
                "reviewed_count": assessment.cn_tax_impact_reviewed_count,
                "unquantifiable_count": (
                    assessment.cn_tax_impact_unquantifiable_count
                ),
                "integrity_issue_count": (
                    assessment.cn_tax_impact_integrity_issue_count
                ),
                "reviewed_underpayment_amount": _amount_value(
                    assessment.cn_reviewed_underpayment_amount, currency
                ),
                "reviewed_overpayment_amount": _amount_value(
                    assessment.cn_reviewed_overpayment_amount, currency
                ),
                "reviewed_timing_amount": _amount_value(
                    assessment.cn_reviewed_timing_amount, currency
                ),
            },
            "ai_analysis_metadata": ai_rows,
        }

    @api.model
    def _derive_conclusion(self, payload):
        assessment = payload["assessment"]
        tax_impact = payload["tax_impact"]
        has_actions = bool(
            assessment["fail_count"]
            or any(
                finding["review_state"] == "correction_required"
                for finding in payload["findings"]
            )
            or any(
                task["state"] not in ("done", "cancelled")
                or (
                    task["state"] != "cancelled"
                    and task["verification_state"]
                    not in ("verified", "not_required")
                )
                for task in payload["tasks"]
            )
        )
        has_limits = bool(
            assessment["data_sufficiency_state"] == "insufficient"
            or assessment["unknown_count"]
            or assessment["error_count"]
            or tax_impact["pending_count"]
            or tax_impact["unquantifiable_count"]
            or payload["obligation_readiness"]["state"]
            in ("not_started", "attention")
        )
        if has_actions and has_limits:
            return "limited_action_required", True
        if has_actions:
            return "action_required", False
        if has_limits:
            return "limited", True
        return "clear", False

    def _submission_issues(self):
        self.ensure_one()
        assessment = self.assessment_id
        issues = []
        if assessment.state != "completed":
            issues.append(_("来源评估尚未完成。"))
        if not assessment.period_start or not assessment.period_end:
            issues.append(_("来源评估没有完整期间。"))
        if not assessment.rule_version_ids or not assessment.finding_ids:
            issues.append(_("来源评估没有可冻结的规则与结果。"))
        if not _text_is_complete(self.executive_summary):
            issues.append(_("管理层摘要至少需要 20 个字符。"))
        if not _text_is_complete(self.scope_statement):
            issues.append(_("范围说明至少需要 20 个字符。"))
        if assessment.source_warning_count:
            issues.append(_("仍有规则结果使用待复核官方来源。"))
        if assessment.professional_warning_count:
            issues.append(_("仍有规则结果未完成真人专业签核。"))
        if assessment.finding_ids.filtered(
            lambda finding: finding.review_state == "pending"
        ):
            issues.append(_("仍有规则结果未完成人工复核。"))
        if assessment.cn_tax_impact_integrity_issue_count:
            issues.append(_("税务影响复核资料存在完整性异常。"))
        if any(
            row["integrity_state"] == "checksum_mismatch"
            for row in self._evidence_payload()
        ):
            issues.append(_("已验证证据内容与封存校验和不一致。"))
        if not self.reviewer_id:
            issues.append(_("尚未指定独立报告批准人。"))
        elif self.company_id not in self.reviewer_id.company_ids:
            issues.append(_("报告批准人没有当前公司访问权限。"))
        same_person = self.reviewer_id in (
            self.prepared_by_id | self.env.user
        )
        if same_person and not _text_is_complete(
            self.independence_exception_reason
        ):
            issues.append(_("职责未分离时必须填写至少 20 个字符的例外理由。"))
        payload = self._snapshot_payload()
        conclusion, has_limits = self._derive_conclusion(payload)
        if has_limits and not _text_is_complete(self.limitation_statement):
            obligation_state = payload["obligation_readiness"]["state"]
            if obligation_state in ("not_started", "attention"):
                issues.append(
                    _(
                        "Tax obligation applicability is not fully confirmed; disclose this limitation before submitting the report."
                    )
                )
            else:
                issues.append(_("存在报告限制时必须填写至少 20 个字符的限制说明。"))
        if conclusion in ("action_required", "limited_action_required") and not _text_is_complete(
            self.management_response
        ):
            issues.append(_("存在整改事项时必须填写至少 20 个字符的管理层回应。"))
        return issues

    def _snapshot_summary_values(self, payload):
        assessment = payload["assessment"]
        tasks = payload["tasks"]
        evidence = payload["evidence"]
        tax_impact = payload["tax_impact"]
        conclusion, has_limits = self._derive_conclusion(payload)
        open_tasks = [
            task
            for task in tasks
            if task["state"] not in ("done", "cancelled")
        ]
        remediation_tasks = [
            task for task in tasks if task["state"] != "cancelled"
        ]
        verified_remediation_tasks = [
            task
            for task in remediation_tasks
            if task["verification_state"] == "verified"
        ]
        pending_verification_tasks = [
            task
            for task in remediation_tasks
            if task["verification_state"] not in ("verified", "not_required")
        ]
        return {
            "conclusion_state": conclusion,
            "has_material_limitations": has_limits,
            "finding_count": assessment["finding_count"],
            "critical_count": assessment["critical_count"],
            "high_count": assessment["high_count"],
            "open_task_count": len(open_tasks),
            "overdue_task_count": len(
                [task for task in open_tasks if task["is_overdue"]]
            ),
            "remediation_task_count": len(remediation_tasks),
            "remediation_verified_count": len(verified_remediation_tasks),
            "remediation_pending_verification_count": len(
                pending_verification_tasks
            ),
            "evidence_count": len(evidence),
            "verified_evidence_count": len(
                [
                    row
                    for row in evidence
                    if row["integrity_state"] == "verified"
                ]
            ),
            "tax_impact_pending_count": tax_impact["pending_count"],
            "reviewed_underpayment_amount": float(
                tax_impact["reviewed_underpayment_amount"]
            ),
            "reviewed_overpayment_amount": float(
                tax_impact["reviewed_overpayment_amount"]
            ),
            "reviewed_timing_amount": float(
                tax_impact["reviewed_timing_amount"]
            ),
        }

    @api.depends(
        "state",
        "period_start",
        "period_end",
        "snapshot_integrity_state",
        "approval_integrity_state",
        "pdf_integrity_state",
        "conclusion_state",
        "has_material_limitations",
        "open_task_count",
        "overdue_task_count",
        "remediation_pending_verification_count",
    )
    def _compute_cn_report_center_display(self):
        for report in self:
            start = fields.Date.to_string(report.period_start) or "-"
            end = fields.Date.to_string(report.period_end) or "-"
            report.cn_report_center_period_label = f"{start} ~ {end}"

            issued_like = report.state in ("issued", "superseded", "withdrawn")
            approval_bad = report.approval_integrity_state in (
                "missing",
                "checksum_mismatch",
            )
            pdf_bad = report.pdf_integrity_state in (
                "missing",
                "checksum_mismatch",
            )
            if issued_like and (approval_bad or pdf_bad):
                integrity = "blocked"
            elif report.state == "draft":
                integrity = "unsealed"
            elif report.snapshot_integrity_state == "source_changed":
                integrity = "warning"
            elif issued_like and (
                report.approval_integrity_state != "verified"
                or report.pdf_integrity_state != "verified"
            ):
                integrity = "warning"
            else:
                integrity = "verified"
            report.cn_report_center_integrity_state = integrity

            if integrity == "blocked":
                stage = "integrity_issue"
                next_action = "停止分发，检查审批记录和已签发 PDF 完整性。"
            elif (
                report.state != "draft"
                and report.snapshot_integrity_state == "source_changed"
            ):
                stage = "source_changed"
                next_action = "来源评估、整改或证据已变化，退回后重新提交。"
            elif report.state == "draft":
                stage = "draft"
                next_action = "补全报告内容和批准人，提交独立批准。"
            elif report.state == "submitted":
                stage = "approval"
                next_action = "由指定批准人复核范围、证据、整改和结论后签发。"
            elif report.state == "issued":
                stage = "issued"
                if report.open_task_count:
                    next_action = "跟踪未关闭整改，并在整改后重新评估或出具后续版本。"
                elif report.remediation_pending_verification_count:
                    next_action = "整改已关闭但仍需验证复扫或确认无需复扫。"
                elif report.has_material_limitations:
                    next_action = "报告已签发，但使用时必须保留范围和数据限制说明。"
                else:
                    next_action = "报告已签发并可下载归档。"
            else:
                stage = "closed"
                next_action = "历史版本，仅用于审计追溯。"
            report.cn_report_center_stage = stage
            report.cn_report_center_next_action = next_action

    @api.depends(
        "snapshot_checksum",
        "snapshot_integrity_state",
        "approval_integrity_state",
        "pdf_integrity_state",
        "finding_count",
        "open_task_count",
        "overdue_task_count",
        "remediation_pending_verification_count",
        "evidence_count",
        "verified_evidence_count",
        "tax_impact_pending_count",
        "assessment_id.profile_id.obligation_ids.write_date",
        "assessment_id.profile_id.obligation_ids.authority_source_id.write_date",
        "assessment_id.finding_ids.cn_traceability_gap_count",
        "assessment_id.finding_ids.task_ids.cn_remediation_traceability_gap_count",
    )
    def _compute_cn_report_traceability(self):
        for report in self:
            gaps = []
            if not report.snapshot_checksum:
                gaps.append("snapshot")
            if report.snapshot_integrity_state == "source_changed":
                gaps.append("source_changed")
            if report.approval_integrity_state in ("missing", "checksum_mismatch"):
                gaps.append("approval_integrity")
            if report.pdf_integrity_state in ("missing", "checksum_mismatch"):
                gaps.append("pdf_integrity")
            if report.open_task_count:
                gaps.append("open_tasks")
            if report.overdue_task_count:
                gaps.append("overdue_tasks")
            if report.remediation_pending_verification_count:
                gaps.append("remediation_verification")
            if report.evidence_count != report.verified_evidence_count:
                gaps.append("evidence")
            if report.tax_impact_pending_count:
                gaps.append("tax_impact")
            if report.assessment_id.profile_id.cn_workbench_obligation_state in (
                "not_started",
                "attention",
            ):
                gaps.append("obligation_readiness")
            if any(report.assessment_id.finding_ids.mapped("cn_traceability_gap_count")):
                gaps.append("finding_traceability")
            if any(
                report.assessment_id.finding_ids.mapped(
                    "task_ids.cn_remediation_traceability_gap_count"
                )
            ):
                gaps.append("remediation_traceability")

            unique_gap_count = len(set(gaps))
            report.cn_report_traceability_gap_count = unique_gap_count
            if not unique_gap_count:
                report.cn_report_traceability_state = "complete"
                report.cn_report_traceability_next_action = _(
                    "Report traceability is complete."
                )
            elif set(gaps) & {
                "snapshot",
                "source_changed",
                "approval_integrity",
                "pdf_integrity",
                "finding_traceability",
            }:
                report.cn_report_traceability_state = "blocked"
                report.cn_report_traceability_next_action = _(
                    "Refresh the report snapshot and close source or finding traceability gaps."
                )
            elif "obligation_readiness" in gaps:
                report.cn_report_traceability_state = "action_required"
                report.cn_report_traceability_next_action = _(
                    "Confirm tax obligation applicability or keep the report limitation visible before relying on distribution."
                )
            elif "remediation_verification" in gaps:
                report.cn_report_traceability_state = "action_required"
                report.cn_report_traceability_next_action = _(
                    "Complete remediation verification rescans or document why verification is not required."
                )
            else:
                report.cn_report_traceability_state = "action_required"
                report.cn_report_traceability_next_action = _(
                    "Close remediation, evidence and tax impact gaps before distribution."
                )

    @api.depends(
        "state",
        "snapshot_checksum",
        "title",
        "executive_summary",
        "scope_statement",
        "limitation_statement",
        "management_response",
        "reviewer_id",
        "independence_exception_reason",
        "assessment_id.write_date",
        "assessment_id.rule_version_ids.write_date",
        "assessment_id.finding_ids.write_date",
        "assessment_id.fact_snapshot_ids.write_date",
        "assessment_id.finding_ids.task_ids.write_date",
        "assessment_id.evidence_ids.write_date",
        "assessment_id.finding_ids.evidence_ids.write_date",
        "assessment_id.finding_ids.task_ids.evidence_ids.write_date",
        "assessment_id.verification_task_ids.evidence_ids.write_date",
        "assessment_id.finding_ids.ai_analysis_ids.write_date",
        "assessment_id.cn_tax_impact_case_ids.write_date",
        "assessment_id.profile_id.obligation_ids.write_date",
        "assessment_id.profile_id.obligation_ids.authority_source_id.write_date",
    )
    def _compute_snapshot_integrity_state(self):
        for report in self:
            if not report.snapshot_checksum or report.state == "draft":
                report.snapshot_integrity_state = "unsealed"
                continue
            try:
                current = _canonical_checksum(report._snapshot_payload())
            except (AccessError, UserError, ValidationError):
                current = False
            report.snapshot_integrity_state = (
                "verified"
                if current == report.snapshot_checksum
                else "source_changed"
            )

    @api.depends(
        "state",
        "approval_checksum",
        "snapshot_checksum",
        "submitted_by_id",
        "submitted_at",
        "reviewer_id",
        "issued_at",
        "review_notes",
        "independence_exception_reason",
    )
    def _compute_approval_integrity_state(self):
        for report in self:
            if report.state in ("draft", "submitted"):
                report.approval_integrity_state = "not_issued"
                continue
            if not report.approval_checksum or not report.issued_at:
                report.approval_integrity_state = "missing"
                continue
            current = _canonical_checksum(
                report._approval_payload(report.issued_at)
            )
            report.approval_integrity_state = (
                "verified"
                if current == report.approval_checksum
                else "checksum_mismatch"
            )

    def _issued_pdf_bytes(self):
        self.ensure_one()
        attachment = self.env["ir.attachment"].sudo().search(
            [
                ("res_model", "=", self._name),
                ("res_id", "=", self.id),
                ("res_field", "=", "issued_pdf"),
            ],
            order="id desc",
            limit=1,
        )
        if attachment:
            return attachment.raw or b""
        encoded = self.issued_pdf or b""
        if isinstance(encoded, str):
            encoded = encoded.encode("ascii")
        try:
            return base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            return encoded

    @api.depends("issued_pdf", "issued_pdf_sha256", "state")
    def _compute_pdf_integrity_state(self):
        for report in self:
            if report.state in ("draft", "submitted"):
                report.pdf_integrity_state = "not_issued"
                continue
            raw = report._issued_pdf_bytes()
            if not raw or not report.issued_pdf_sha256:
                report.pdf_integrity_state = "missing"
                continue
            report.pdf_integrity_state = (
                "verified"
                if hashlib.sha256(raw).hexdigest()
                == report.issued_pdf_sha256
                else "checksum_mismatch"
            )

    def action_submit(self):
        self._require_preparer()
        self._lock_for_transition()
        for report in self:
            if report.state != "draft":
                raise UserError(_("只有编制中的报告可以提交独立批准。"))
            issues = report._submission_issues()
            if issues:
                raise UserError(
                    _("正式报告尚不能提交：\n- %(issues)s", issues="\n- ".join(issues))
                )
            payload = report._snapshot_payload()
            checksum = _canonical_checksum(payload)
            values = report._snapshot_summary_values(payload)
            values.update(
                {
                    "state": "submitted",
                    "submitted_by_id": self.env.user.id,
                    "submitted_at": fields.Datetime.now(),
                    "review_notes": False,
                    "snapshot_json": payload,
                    "snapshot_checksum": checksum,
                    "approval_checksum": False,
                    "issued_pdf": False,
                    "issued_pdf_filename": False,
                    "issued_pdf_sha256": False,
                }
            )
            report._transition_write(values)
            self.env["sudo.compliance.audit.event"]._log_records(
                report,
                "cn_compliance_report.submitted",
                previous_state="draft",
                new_state="submitted",
                details={
                    "snapshot_checksum": checksum,
                    "conclusion_state": report.conclusion_state,
                    "reviewer_id": report.reviewer_id.id,
                },
            )
        return True

    def action_return_to_draft(self):
        self._require_approver()
        self._lock_for_transition()
        for report in self:
            if report.state != "submitted" or report.reviewer_id != self.env.user:
                raise AccessError(_("只有指定批准人可以退回待批准报告。"))
            if not _text_is_complete(report.review_notes):
                raise UserError(_("退回前请填写至少 20 个字符的批准意见。"))
            previous_checksum = report.snapshot_checksum
            report._transition_write(
                {
                    "state": "draft",
                    "submitted_by_id": False,
                    "submitted_at": False,
                    "snapshot_json": {},
                    "snapshot_checksum": False,
                    "approval_checksum": False,
                    "conclusion_state": False,
                    "has_material_limitations": False,
                    "finding_count": 0,
                    "critical_count": 0,
                    "high_count": 0,
                    "open_task_count": 0,
                    "overdue_task_count": 0,
                    "remediation_task_count": 0,
                    "remediation_verified_count": 0,
                    "remediation_pending_verification_count": 0,
                    "evidence_count": 0,
                    "verified_evidence_count": 0,
                    "tax_impact_pending_count": 0,
                    "reviewed_underpayment_amount": 0.0,
                    "reviewed_overpayment_amount": 0.0,
                    "reviewed_timing_amount": 0.0,
                }
            )
            self.env["sudo.compliance.audit.event"]._log_records(
                report,
                "cn_compliance_report.returned",
                previous_state="submitted",
                new_state="draft",
                details={
                    "previous_snapshot_checksum": previous_checksum,
                    "review_notes_checksum": hashlib.sha256(
                        (report.review_notes or "").encode("utf-8")
                    ).hexdigest(),
                },
            )
        return True

    def _approval_payload(self, issued_at):
        self.ensure_one()
        return {
            "schema": "sdoo.cn.compliance-report-approval.v1",
            "report_id": self.id,
            "report_number": self.name,
            "revision": self.revision,
            "snapshot_checksum": self.snapshot_checksum,
            "submitted_by_id": self.submitted_by_id.id,
            "submitted_at": _datetime_value(self.submitted_at),
            "reviewer_id": self.reviewer_id.id,
            "issued_at": _datetime_value(issued_at),
            "review_notes": self.review_notes,
            "independence_exception_reason": (
                self.independence_exception_reason or None
            ),
        }

    def _render_issued_pdf(self):
        self.ensure_one()
        action = self.env.ref(
            "sudo_country_pack_cn.action_report_cn_formal_compliance"
        )
        pdf, _report_type = action._render_qweb_pdf(
            action.report_name,
            self.ids,
        )
        return pdf

    def action_issue(self):
        self._require_approver()
        self._lock_for_transition()
        for report in self:
            if report.state != "submitted" or report.reviewer_id != self.env.user:
                raise AccessError(_("只有指定批准人可以签发待批准报告。"))
            if not _text_is_complete(report.review_notes):
                raise UserError(_("签发前请填写至少 20 个字符的独立批准意见。"))
            same_person = report.reviewer_id in (
                report.prepared_by_id | report.submitted_by_id
            )
            if same_person and not _text_is_complete(
                report.independence_exception_reason
            ):
                raise UserError(_("职责未分离时必须记录完整例外理由。"))
            current_checksum = _canonical_checksum(report._snapshot_payload())
            if current_checksum != report.snapshot_checksum:
                raise UserError(_("报告源资料在提交后发生变化，请退回并重新提交。"))

            self.env.cr.execute(
                "SELECT id FROM sudo_compliance_assessment WHERE id = %s FOR UPDATE",
                (report.assessment_id.id,),
            )
            current = self.search(
                [
                    ("assessment_id", "=", report.assessment_id.id),
                    ("state", "=", "issued"),
                    ("id", "!=", report.id),
                ],
                order="issued_at desc, id desc",
                limit=1,
            )
            if current and report.supersedes_id != current:
                raise UserError(_("已有其他当前签发报告，请建立新的替代版本。"))

            issued_at = fields.Datetime.now()
            approval_checksum = _canonical_checksum(
                report._approval_payload(issued_at)
            )
            report._transition_write(
                {
                    "state": "issued",
                    "issued_by_id": self.env.user.id,
                    "issued_at": issued_at,
                    "approval_checksum": approval_checksum,
                }
            )
            pdf = report._render_issued_pdf()
            if not pdf or not pdf.startswith(b"%PDF"):
                raise UserError(_("报告 PDF 生成失败，未执行签发。"))
            pdf_checksum = hashlib.sha256(pdf).hexdigest()
            filename = "%s-R%s.pdf" % (report.name.replace("/", "-"), report.revision)
            report._transition_write(
                {
                    "issued_pdf": base64.b64encode(pdf),
                    "issued_pdf_filename": filename,
                    "issued_pdf_sha256": pdf_checksum,
                }
            )
            if current:
                current._transition_write({"state": "superseded"})
                self.env["sudo.compliance.audit.event"]._log_records(
                    current,
                    "cn_compliance_report.superseded",
                    previous_state="issued",
                    new_state="superseded",
                    details={"replacement_report_id": report.id},
                )
            self.env["sudo.compliance.audit.event"]._log_records(
                report,
                "cn_compliance_report.issued",
                previous_state="submitted",
                new_state="issued",
                details={
                    "snapshot_checksum": report.snapshot_checksum,
                    "approval_checksum": approval_checksum,
                    "pdf_sha256": pdf_checksum,
                    "independent_approval": not same_person,
                },
            )
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_withdraw(self):
        self._require_preparer()
        self._lock_for_transition()
        for report in self:
            if report.state != "issued":
                raise UserError(_("只有当前已签发报告可以撤回。"))
            if not _text_is_complete(report.withdrawal_reason):
                raise UserError(_("撤回前请填写至少 20 个字符的撤回理由。"))
            report._transition_write(
                {
                    "state": "withdrawn",
                    "withdrawn_by_id": self.env.user.id,
                    "withdrawn_at": fields.Datetime.now(),
                }
            )
            self.env["sudo.compliance.audit.event"]._log_records(
                report,
                "cn_compliance_report.withdrawn",
                previous_state="issued",
                new_state="withdrawn",
                details={
                    "reason_checksum": hashlib.sha256(
                        report.withdrawal_reason.encode("utf-8")
                    ).hexdigest(),
                    "pdf_sha256": report.issued_pdf_sha256,
                },
            )
        return True

    def action_preview(self):
        self.ensure_one()
        if self.state in ("issued", "superseded", "withdrawn"):
            raise UserError(_("报告已签发，请下载经过校验的封存 PDF。"))
        return self.env.ref(
            "sudo_country_pack_cn.action_report_cn_formal_compliance"
        ).report_action(self)

    def action_download_issued_pdf(self):
        self.ensure_one()
        if self.state not in ("issued", "superseded", "withdrawn"):
            raise UserError(_("报告尚未签发，没有可下载的正式 PDF。"))
        if self.approval_integrity_state != "verified":
            raise UserError(_("批准记录缺失或完整性异常，禁止下载正式报告。"))
        if self.pdf_integrity_state != "verified":
            raise UserError(_("已签发 PDF 缺失或完整性异常，禁止下载。"))
        filename = self.issued_pdf_filename or "%s.pdf" % self.name
        return {
            "type": "ir.actions.act_url",
            "target": "self",
            "url": (
                "/web/content/%s/%s/issued_pdf/%s?download=true"
                % (self._name, self.id, filename)
            ),
        }

    def action_open_assessment(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("来源合规评估"),
            "res_model": "sudo.compliance.assessment",
            "view_mode": "form",
            "res_id": self.assessment_id.id,
            "target": "current",
        }

    def action_cn_open_report_findings(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("报告相关风险事项"),
            "res_model": "sudo.compliance.finding",
            "view_mode": "list,form",
            "domain": [("assessment_id", "=", self.assessment_id.id)],
            "context": {"search_default_actionable": 1},
            "target": "current",
        }

    def action_cn_open_report_tasks(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("报告相关整改任务"),
            "res_model": "sudo.compliance.task",
            "view_mode": "list,form",
            "domain": [("assessment_id", "=", self.assessment_id.id)],
            "context": {"search_default_open": 1},
            "target": "current",
        }

    def action_cn_open_report_evidence(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Report Evidence"),
            "res_model": "sudo.compliance.evidence",
            "view_mode": "list,form",
            "domain": [("id", "in", self.assessment_id.report_evidence_ids.ids)],
            "context": {"search_default_group_state": 1},
            "target": "current",
        }

    def report_payload(self):
        self.ensure_one()
        return self.snapshot_json or self._snapshot_payload()

    @api.model
    def report_label(self, category, value):
        mappings = {
            "risk": _RISK_LABELS,
            "result": _RESULT_LABELS,
            "review": _REVIEW_LABELS,
            "task": _TASK_LABELS,
            "evidence": _EVIDENCE_LABELS,
            "impact": _IMPACT_LABELS,
            "conclusion": _CONCLUSION_LABELS,
        }
        return mappings.get(category, {}).get(value, value or "-")


class SudoComplianceAssessment(models.Model):
    _inherit = "sudo.compliance.assessment"

    cn_formal_report_ids = fields.One2many(
        "sudo.cn.compliance.report",
        "assessment_id",
        string="中国正式合规报告",
        readonly=True,
    )
    cn_formal_report_count = fields.Integer(
        string="正式报告",
        compute="_compute_cn_formal_report_count",
    )

    @api.depends("cn_formal_report_ids.state")
    def _compute_cn_formal_report_count(self):
        for assessment in self:
            assessment.cn_formal_report_count = len(
                assessment.cn_formal_report_ids
            )

    def action_open_cn_formal_reports(self):
        self.ensure_one()
        action = self.env.ref(
            "sudo_country_pack_cn.action_cn_formal_compliance_reports"
        ).read()[0]
        action["domain"] = [("assessment_id", "=", self.id)]
        action["context"] = {
            "default_assessment_id": self.id,
            "default_title": _("中国财税合规管理报告 - %(name)s", name=self.name),
        }
        if self.cn_formal_report_count == 1:
            action.update(
                {
                    "view_mode": "form",
                    "views": [(False, "form")],
                    "res_id": self.cn_formal_report_ids.id,
                }
            )
        return action

    def action_prepare_cn_formal_report(self):
        self.ensure_one()
        if self.state != "completed":
            raise UserError(_("只有已完成评估可以编制正式报告。"))
        open_report = self.cn_formal_report_ids.filtered(
            lambda report: report.state in ("draft", "submitted")
        ).sorted("id", reverse=True)[:1]
        if open_report:
            return {
                "type": "ir.actions.act_window",
                "name": _("中国正式合规报告"),
                "res_model": "sudo.cn.compliance.report",
                "view_mode": "form",
                "res_id": open_report.id,
                "target": "current",
            }
        return {
            "type": "ir.actions.act_window",
            "name": _("编制中国正式合规报告"),
            "res_model": "sudo.cn.compliance.report",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_assessment_id": self.id,
                "default_title": _(
                    "中国财税合规管理报告 - %(name)s", name=self.name
                ),
            },
        }
