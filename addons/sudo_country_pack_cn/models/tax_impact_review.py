import hashlib

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .vat_accounting_scope import (
    _attachment_manifest,
    _invalid_binary_attachments,
    _payload_checksum,
)


_TAX_IMPACT_TRANSITION_MARKER = object()


def _impact_summary(cases):
    active = cases.filtered(lambda record: record.state != "cancelled")
    reviewed = active.filtered(lambda record: record.state == "reviewed")
    verified_reviewed = reviewed.filtered(
        lambda record: record.integrity_state == "verified"
    )
    quantified = verified_reviewed.filtered(
        lambda record: record.quantification_state == "reviewed"
    )
    return {
        "count": len(active),
        "pending_count": len(
            active.filtered(lambda record: record.state != "reviewed")
        ),
        "reviewed_count": len(reviewed),
        "integrity_issue_count": len(reviewed - verified_reviewed),
        "unquantifiable_count": len(
            verified_reviewed.filtered(
                lambda record: record.quantification_state == "not_quantifiable"
            )
        ),
        "underpayment": sum(
            quantified.filtered(
                lambda record: record.impact_direction
                == "potential_underpayment"
            ).mapped("impact_amount")
        ),
        "overpayment": sum(
            quantified.filtered(
                lambda record: record.impact_direction
                == "potential_overpayment"
            ).mapped("impact_amount")
        ),
        "timing": sum(
            quantified.filtered(
                lambda record: record.impact_direction == "timing_difference"
            ).mapped("impact_amount")
        ),
    }


def _impact_case_action(env, domain=None, context=None, res_id=None):
    action = env.ref(
        "sudo_country_pack_cn.action_cn_tax_impact_cases"
    ).sudo().read()[0]
    if res_id:
        action.update({"view_mode": "form", "views": [(False, "form")]})
        action["res_id"] = res_id
    elif domain is None:
        action.update({"view_mode": "form", "views": [(False, "form")]})
    else:
        action["domain"] = domain
    action["context"] = context or {}
    return action


class SudoChinaTaxImpactCase(models.Model):
    _name = "sudo.cn.tax.impact.case"
    _description = "China Controlled Tax Impact Review Case"
    _order = "period_end desc, impact_direction, id desc"
    _check_company_auto = True

    name = fields.Char(compute="_compute_name", store=True)
    title = fields.Char(string="复核事项", required=True, index=True)
    profile_id = fields.Many2one(
        "sudo.compliance.profile",
        string="合规档案",
        required=True,
        ondelete="restrict",
        index=True,
        check_company=True,
        domain="[('country_id.code', '=', 'CN')]",
    )
    company_id = fields.Many2one(
        related="profile_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    country_id = fields.Many2one(
        related="profile_id.country_id",
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id",
        string="币种",
        store=True,
        readonly=True,
    )
    period_start = fields.Date(string="期间开始", required=True, index=True)
    period_end = fields.Date(string="期间结束", required=True, index=True)
    assessment_id = fields.Many2one(
        "sudo.compliance.assessment",
        string="规则评估",
        ondelete="restrict",
        check_company=True,
        index=True,
        domain="[('profile_id', '=', profile_id)]",
    )
    vat_run_id = fields.Many2one(
        "sudo.cn.vat.period.reconciliation.run",
        string="增值税勾稽批次",
        ondelete="restrict",
        check_company=True,
        index=True,
        domain=(
            "[('profile_id', '=', profile_id), "
            "('state', 'in', ('succeeded', 'superseded'))]"
        ),
    )
    finding_ids = fields.Many2many(
        "sudo.compliance.finding",
        "sudo_cn_tax_impact_case_finding_rel",
        "case_id",
        "finding_id",
        string="规则风险来源",
        check_company=True,
        domain=(
            "[('assessment_id', '=', assessment_id), "
            "('result', 'in', ('fail', 'unknown', 'error'))]"
        ),
    )
    reconciliation_issue_ids = fields.Many2many(
        "sudo.cn.vat.period.reconciliation.issue",
        "sudo_cn_tax_impact_case_issue_rel",
        "case_id",
        "issue_id",
        string="勾稽问题来源",
        check_company=True,
        domain="[('run_id', '=', vat_run_id)]",
    )
    source_count = fields.Integer(
        string="来源事项数",
        compute="_compute_source_count",
    )
    impact_direction = fields.Selection(
        [
            ("undetermined", "尚未判断税务影响"),
            ("no_tax_impact", "复核后无税额影响"),
            ("timing_difference", "期间错配影响"),
            ("potential_underpayment", "潜在少缴税影响"),
            ("potential_overpayment", "潜在多缴税影响"),
        ],
        string="影响方向",
        required=True,
        default="undetermined",
        index=True,
    )
    quantification_state = fields.Selection(
        [
            ("not_assessed", "尚未评估"),
            ("not_quantifiable", "现有证据无法量化"),
            ("preliminary", "待复核初步金额"),
            ("reviewed", "已复核金额"),
        ],
        string="量化状态",
        required=True,
        default="not_assessed",
        index=True,
    )
    impact_amount = fields.Monetary(
        string="税务影响金额",
        currency_field="currency_id",
        required=True,
        default=0.0,
    )
    analysis = fields.Text(
        string="事实分析与计算过程",
        required=True,
    )
    assumptions_limitations = fields.Text(
        string="假设、限制与不确定性",
        required=True,
    )
    source_reference = fields.Char(
        string="工作底稿引用",
        required=True,
        index=True,
    )
    evidence_attachment_ids = fields.Many2many(
        "ir.attachment",
        "sudo_cn_tax_impact_case_attachment_rel",
        "case_id",
        "attachment_id",
        string="量化与复核证据",
    )
    prepared_by_id = fields.Many2one(
        "res.users",
        string="编制人",
        required=True,
        readonly=True,
    )
    state = fields.Selection(
        [
            ("draft", "分析中"),
            ("submitted", "待独立复核"),
            ("reviewed", "已复核"),
            ("cancelled", "已取消"),
        ],
        string="状态",
        required=True,
        default="draft",
        readonly=True,
        index=True,
    )
    review_notes = fields.Text(string="独立复核意见")
    separation_exception_reason = fields.Text(
        string="同人复核例外理由",
        help="编制人与复核人为同一人时，记录受控例外原因。",
    )
    submitted_at = fields.Datetime(string="提交复核时间", readonly=True)
    submitted_by_id = fields.Many2one(
        "res.users",
        string="提交人",
        readonly=True,
    )
    reviewed_at = fields.Datetime(string="复核时间", readonly=True)
    reviewer_id = fields.Many2one(
        "res.users",
        string="复核人",
        readonly=True,
    )
    submission_checksum = fields.Char(
        string="提交 SHA-256",
        readonly=True,
        copy=False,
    )
    review_checksum = fields.Char(
        string="复核 SHA-256",
        readonly=True,
        copy=False,
    )
    integrity_state = fields.Selection(
        [
            ("unsealed", "尚未封存"),
            ("verified", "完整性正常"),
            ("checksum_mismatch", "资料已变化"),
        ],
        string="资料完整性",
        compute="_compute_integrity_state",
    )

    _body_fields = {
        "title",
        "profile_id",
        "period_start",
        "period_end",
        "assessment_id",
        "vat_run_id",
        "finding_ids",
        "reconciliation_issue_ids",
        "impact_direction",
        "quantification_state",
        "impact_amount",
        "analysis",
        "assumptions_limitations",
        "source_reference",
        "evidence_attachment_ids",
    }
    _review_fields = {"review_notes", "separation_exception_reason"}
    _protected_fields = {
        "prepared_by_id",
        "state",
        "submitted_at",
        "submitted_by_id",
        "reviewed_at",
        "reviewer_id",
        "submission_checksum",
        "review_checksum",
    }
    _normalized_text_fields = {
        "title",
        "analysis",
        "assumptions_limitations",
        "source_reference",
        "review_notes",
        "separation_exception_reason",
    }

    @api.depends("title", "period_start", "period_end")
    def _compute_name(self):
        for case in self:
            period = "%s - %s" % (
                fields.Date.to_string(case.period_start) or "-",
                fields.Date.to_string(case.period_end) or "-",
            )
            case.name = "%s / %s" % (
                case.title or _("税务影响复核事项"),
                period,
            )

    @api.depends("finding_ids", "reconciliation_issue_ids")
    def _compute_source_count(self):
        for case in self:
            case.source_count = len(case.finding_ids) + len(
                case.reconciliation_issue_ids
            )

    @api.model
    def _normalize_text_values(self, values):
        for field_name in self._normalized_text_fields & set(values):
            value = values[field_name]
            if isinstance(value, str):
                values[field_name] = value.strip() or False

    def _body_payload(self):
        self.ensure_one()
        findings = []
        for finding in self.finding_ids.sudo().sorted("id"):
            review_note = finding.review_notes or ""
            findings.append(
                {
                    "id": finding.id,
                    "assessment_id": finding.assessment_id.id,
                    "checksum": finding.checksum,
                    "result": finding.result,
                    "review_state": finding.review_state,
                    "reviewer_id": finding.reviewer_id.id or None,
                    "reviewed_at": fields.Datetime.to_string(
                        finding.reviewed_at
                    ),
                    "review_notes_sha256": hashlib.sha256(
                        review_note.encode("utf-8")
                    ).hexdigest(),
                }
            )
        issues = []
        for issue in self.reconciliation_issue_ids.sudo().sorted("id"):
            issues.append(
                {
                    "id": issue.id,
                    "run_id": issue.run_id.id,
                    "run_result_checksum": issue.run_id.result_checksum,
                    "code": issue.code,
                    "issue_kind": issue.issue_kind,
                    "has_difference": issue.has_difference,
                    "difference_amount": (
                        format(
                            self.currency_id.round(
                                float(issue.difference_amount or 0.0)
                            ),
                            "f",
                        )
                        if issue.has_difference
                        else None
                    ),
                }
            )
        return {
            "schema": "sdoo.cn.tax-impact-review.v1",
            "case_id": self.id,
            "title": self.title,
            "profile_id": self.profile_id.id,
            "company_id": self.company_id.id,
            "currency_id": self.currency_id.id,
            "period_start": fields.Date.to_string(self.period_start),
            "period_end": fields.Date.to_string(self.period_end),
            "assessment_id": self.assessment_id.id or None,
            "vat_run_id": self.vat_run_id.id or None,
            "impact_direction": self.impact_direction,
            "quantification_state": self.quantification_state,
            "impact_amount": format(
                self.currency_id.round(float(self.impact_amount or 0.0)),
                "f",
            ),
            "analysis": self.analysis,
            "assumptions_limitations": self.assumptions_limitations,
            "source_reference": self.source_reference,
            "prepared_by_id": self.prepared_by_id.id,
            "findings": findings,
            "reconciliation_issues": issues,
            "attachments": _attachment_manifest(
                self.sudo().evidence_attachment_ids
            ),
        }

    def _body_checksum(self):
        self.ensure_one()
        return _payload_checksum(self._body_payload())

    def _review_payload(self):
        self.ensure_one()
        payload = self._body_payload()
        payload["review"] = {
            "reviewer_id": self.reviewer_id.id or None,
            "reviewed_at": fields.Datetime.to_string(self.reviewed_at),
            "review_notes": self.review_notes or None,
            "separation_exception_reason": (
                self.separation_exception_reason or None
            ),
        }
        return payload

    def _review_payload_checksum(self):
        self.ensure_one()
        return _payload_checksum(self._review_payload())

    def _current_integrity_state(self):
        self.ensure_one()
        if self.state == "submitted" and self.submission_checksum:
            return (
                "verified"
                if self.submission_checksum == self._body_checksum()
                else "checksum_mismatch"
            )
        if self.state in ("reviewed", "cancelled") and self.review_checksum:
            return (
                "verified"
                if self.review_checksum == self._review_payload_checksum()
                else "checksum_mismatch"
            )
        return "unsealed"

    @api.depends(
        "state",
        "submission_checksum",
        "review_checksum",
        "title",
        "profile_id",
        "period_start",
        "period_end",
        "assessment_id",
        "vat_run_id",
        "impact_direction",
        "quantification_state",
        "impact_amount",
        "analysis",
        "assumptions_limitations",
        "source_reference",
        "prepared_by_id",
        "review_notes",
        "separation_exception_reason",
        "reviewed_at",
        "reviewer_id",
        "finding_ids",
        "finding_ids.checksum",
        "finding_ids.review_state",
        "finding_ids.reviewer_id",
        "finding_ids.reviewed_at",
        "finding_ids.review_notes",
        "reconciliation_issue_ids",
        "reconciliation_issue_ids.run_id.result_checksum",
        "evidence_attachment_ids",
        "evidence_attachment_ids.checksum",
        "evidence_attachment_ids.file_size",
    )
    def _compute_integrity_state(self):
        for case in self:
            case.integrity_state = case._current_integrity_state()

    @api.constrains("profile_id")
    def _check_china_profile(self):
        for case in self:
            if case.country_id.code != "CN":
                raise ValidationError(_("税务影响复核事项只能关联中国合规档案。"))

    @api.constrains("period_start", "period_end")
    def _check_period(self):
        for case in self:
            if case.period_end < case.period_start:
                raise ValidationError(_("期间结束日不能早于开始日。"))

    @api.constrains(
        "impact_direction",
        "quantification_state",
        "impact_amount",
        "state",
    )
    def _check_quantification_semantics(self):
        for case in self:
            amount = float(case.impact_amount or 0.0)
            if amount < 0:
                raise ValidationError(_("税务影响金额不得为负数，请使用影响方向表达性质。"))
            if case.quantification_state in (
                "not_assessed",
                "not_quantifiable",
            ) and not case.currency_id.is_zero(amount):
                raise ValidationError(_("尚未量化或无法量化的事项金额必须为零。"))
            if case.quantification_state in ("preliminary", "reviewed"):
                if case.impact_direction in (
                    "undetermined",
                    "no_tax_impact",
                ):
                    raise ValidationError(_("存在量化金额时必须明确少缴、多缴或期间错配方向。"))
                if amount <= 0:
                    raise ValidationError(_("初步或已复核的税务影响金额必须大于零。"))
            if case.impact_direction == "no_tax_impact" and (
                case.quantification_state != "not_quantifiable"
            ):
                raise ValidationError(_("无税额影响结论不得填写税务影响金额。"))
            if case.quantification_state == "reviewed" and (
                case.state not in ("reviewed", "cancelled")
            ):
                raise ValidationError(_("已复核金额只能由受控复核操作形成。"))
            if case.state == "reviewed" and (
                case.quantification_state == "preliminary"
            ):
                raise ValidationError(_("已复核事项不能保留初步金额状态。"))

    @api.constrains(
        "profile_id",
        "period_start",
        "period_end",
        "assessment_id",
        "vat_run_id",
        "finding_ids",
        "reconciliation_issue_ids",
    )
    def _check_source_consistency(self):
        for case in self:
            if case.assessment_id:
                if case.assessment_id.profile_id != case.profile_id:
                    raise ValidationError(_("规则评估与合规档案不一致。"))
                if (
                    case.assessment_id.period_start != case.period_start
                    or case.assessment_id.period_end != case.period_end
                ):
                    raise ValidationError(_("规则评估期间必须与复核事项期间完全一致。"))
            if case.finding_ids:
                if not case.assessment_id:
                    raise ValidationError(_("关联规则风险时必须选择对应规则评估。"))
                if any(
                    finding.assessment_id != case.assessment_id
                    for finding in case.finding_ids
                ):
                    raise ValidationError(_("所有规则风险必须来自所选规则评估。"))
            if case.vat_run_id:
                if case.vat_run_id.profile_id != case.profile_id:
                    raise ValidationError(_("增值税勾稽批次与合规档案不一致。"))
                if (
                    case.vat_run_id.period_start != case.period_start
                    or case.vat_run_id.period_end != case.period_end
                ):
                    raise ValidationError(_("增值税勾稽期间必须与复核事项期间完全一致。"))
            if case.reconciliation_issue_ids:
                if not case.vat_run_id:
                    raise ValidationError(_("关联勾稽问题时必须选择对应勾稽批次。"))
                if any(
                    issue.run_id != case.vat_run_id
                    for issue in case.reconciliation_issue_ids
                ):
                    raise ValidationError(_("所有勾稽问题必须来自所选增值税勾稽批次。"))

    def _lock_source_rows(self):
        finding_ids = tuple(self.finding_ids.ids)
        issue_ids = tuple(self.reconciliation_issue_ids.ids)
        if finding_ids:
            self.env.cr.execute(
                "SELECT id FROM sudo_compliance_finding "
                "WHERE id IN %s ORDER BY id FOR UPDATE",
                [finding_ids],
            )
        if issue_ids:
            self.env.cr.execute(
                "SELECT id FROM sudo_cn_vat_period_reconciliation_issue "
                "WHERE id IN %s ORDER BY id FOR UPDATE",
                [issue_ids],
            )

    @api.constrains("finding_ids", "reconciliation_issue_ids", "state")
    def _check_unique_source_ownership(self):
        for case in self:
            if case.state == "cancelled":
                continue
            case._lock_source_rows()
            domain = [
                ("id", "!=", case.id),
                ("state", "!=", "cancelled"),
            ]
            if case.finding_ids and self.sudo().search_count(
                domain + [("finding_ids", "in", case.finding_ids.ids)],
                limit=1,
            ):
                raise ValidationError(_("同一规则风险只能归入一份未取消的税务影响复核事项。"))
            if case.reconciliation_issue_ids and self.sudo().search_count(
                domain
                + [
                    (
                        "reconciliation_issue_ids",
                        "in",
                        case.reconciliation_issue_ids.ids,
                    )
                ],
                limit=1,
            ):
                raise ValidationError(_("同一勾稽问题只能归入一份未取消的税务影响复核事项。"))

    def _submission_issues(self):
        self.ensure_one()
        issues = []
        if not self.finding_ids and not self.reconciliation_issue_ids:
            issues.append(_("至少关联一项规则风险或勾稽问题"))
        if self.assessment_id and self.assessment_id.state != "completed":
            issues.append(_("关联的规则评估尚未完成"))
        pending_findings = self.finding_ids.filtered(
            lambda finding: finding.review_state
            not in ("confirmed", "correction_required")
        )
        if pending_findings:
            issues.append(_("关联规则风险尚未完成人工复核"))
        if self.vat_run_id:
            if self.vat_run_id.state not in ("succeeded", "superseded"):
                issues.append(_("关联增值税勾稽批次不是成功审计快照"))
            if not self.vat_run_id.result_checksum:
                issues.append(_("关联增值税勾稽批次缺少结果校验和"))
        if self.quantification_state not in (
            "preliminary",
            "not_quantifiable",
        ):
            issues.append(_("必须选择待复核初步金额或现有证据无法量化"))
        if not self.analysis or len(self.analysis) < 20:
            issues.append(_("事实分析与计算过程必须不少于 20 字"))
        if not self.assumptions_limitations or len(
            self.assumptions_limitations
        ) < 10:
            issues.append(_("假设、限制与不确定性必须不少于 10 字"))
        if not self.source_reference:
            issues.append(_("未填写工作底稿引用"))
        attachments = self.sudo().evidence_attachment_ids
        if not attachments:
            issues.append(_("未上传量化与复核证据"))
        elif _invalid_binary_attachments(attachments):
            issues.append(_("复核证据必须是系统内非空二进制附件"))
        return issues

    def _review_issues(self):
        self.ensure_one()
        issues = []
        if self._current_integrity_state() != "verified":
            issues.append(_("提交后资料或来源发生变化，请退回并重新提交"))
        if not self.review_notes or len(self.review_notes) < 20:
            issues.append(_("独立复核意见必须不少于 20 字"))
        if self.prepared_by_id == self.env.user and len(
            self.separation_exception_reason or ""
        ) < 20:
            issues.append(_("编制人与复核人为同一人时，必须填写不少于 20 字的例外理由"))
        return issues

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            self._normalize_text_values(values)
            values.update(
                {
                    "prepared_by_id": self.env.user.id,
                    "state": "draft",
                    "submitted_at": False,
                    "submitted_by_id": False,
                    "reviewed_at": False,
                    "reviewer_id": False,
                    "review_notes": False,
                    "separation_exception_reason": False,
                    "submission_checksum": False,
                    "review_checksum": False,
                }
            )
        records = super().create(vals_list)
        self.env["sudo.compliance.audit.event"]._log_records(
            records,
            "cn_tax_impact_case.created",
            new_state="draft",
        )
        return records

    def write(self, values):
        self._normalize_text_values(values)
        transition = (
            self.env.context.get("cn_tax_impact_transition")
            is _TAX_IMPACT_TRANSITION_MARKER
        )
        if set(values) & self._protected_fields and not transition:
            raise AccessError(_("请使用税务影响复核事项上的受控操作更新状态。"))
        body_changes = sorted(set(values) & self._body_fields)
        review_changes = sorted(set(values) & self._review_fields)
        if body_changes and any(case.state != "draft" for case in self) and not transition:
            raise AccessError(_("已提交、已复核或已取消的复核事项不可修改分析载荷。"))
        if review_changes and any(
            case.state != "submitted" for case in self
        ) and not transition:
            raise AccessError(_("独立复核意见只能在事项提交后由复核人员填写。"))
        result = super().write(values)
        if (body_changes or review_changes) and not transition:
            self.env["sudo.compliance.audit.event"]._log_records(
                self,
                "cn_tax_impact_case.changed",
                details={
                    "body_fields": body_changes,
                    "review_fields": review_changes,
                },
            )
        return result

    def unlink(self):
        if self.filtered(lambda case: case.state != "draft"):
            raise UserError(_("已提交、已复核或已取消的复核事项不可删除。"))
        return super().unlink()

    def copy(self, default=None):
        values = dict(default or {})
        values.update(
            {
                "prepared_by_id": self.env.user.id,
                "state": "draft",
                "review_notes": False,
                "separation_exception_reason": False,
                "submitted_at": False,
                "submitted_by_id": False,
                "reviewed_at": False,
                "reviewer_id": False,
                "submission_checksum": False,
                "review_checksum": False,
                "quantification_state": (
                    "preliminary"
                    if self.quantification_state == "reviewed"
                    else self.quantification_state
                ),
            }
        )
        return super().copy(values)

    def _require_manager(self):
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以执行税务影响复核操作。"))

    def action_submit(self):
        self._require_manager()
        for case in self:
            if case.state != "draft":
                raise UserError(_("只有分析中的事项可以提交复核。"))
            issues = case._submission_issues()
            if issues:
                raise UserError(
                    _(
                        "税务影响事项尚不能提交：\n- %(issues)s",
                        issues="\n- ".join(issues),
                    )
                )
            checksum = case._body_checksum()
            case.with_context(
                cn_tax_impact_transition=_TAX_IMPACT_TRANSITION_MARKER
            ).write(
                {
                    "state": "submitted",
                    "submitted_at": fields.Datetime.now(),
                    "submitted_by_id": self.env.user.id,
                    "submission_checksum": checksum,
                }
            )
            self.env["sudo.compliance.audit.event"]._log_records(
                case,
                "cn_tax_impact_case.submitted",
                previous_state="draft",
                new_state="submitted",
                details={
                    "checksum": checksum,
                    "finding_ids": case.finding_ids.ids,
                    "reconciliation_issue_ids": (
                        case.reconciliation_issue_ids.ids
                    ),
                    "quantification_state": case.quantification_state,
                },
            )
        return True

    def action_review(self):
        self._require_manager()
        for case in self:
            if case.state != "submitted":
                raise UserError(_("只有待独立复核的事项可以确认复核。"))
            issues = case._review_issues()
            if issues:
                raise UserError(
                    _(
                        "税务影响事项尚不能确认复核：\n- %(issues)s",
                        issues="\n- ".join(issues),
                    )
                )
            reviewed_at = fields.Datetime.now()
            quantification_state = (
                "reviewed"
                if case.quantification_state == "preliminary"
                else case.quantification_state
            )
            case.with_context(
                cn_tax_impact_transition=_TAX_IMPACT_TRANSITION_MARKER
            ).write(
                {
                    "state": "reviewed",
                    "quantification_state": quantification_state,
                    "reviewed_at": reviewed_at,
                    "reviewer_id": self.env.user.id,
                }
            )
            checksum = case._review_payload_checksum()
            case.with_context(
                cn_tax_impact_transition=_TAX_IMPACT_TRANSITION_MARKER
            ).write({"review_checksum": checksum})
            self.env["sudo.compliance.audit.event"]._log_records(
                case,
                "cn_tax_impact_case.reviewed",
                previous_state="submitted",
                new_state="reviewed",
                details={
                    "checksum": checksum,
                    "impact_direction": case.impact_direction,
                    "quantification_state": case.quantification_state,
                    "impact_amount": float(case.impact_amount),
                    "independent_review": case.prepared_by_id != self.env.user,
                },
            )
        return True

    def action_reject(self):
        self._require_manager()
        for case in self:
            if case.state != "submitted":
                raise UserError(_("只有待独立复核的事项可以退回。"))
            if not case.review_notes or len(case.review_notes) < 20:
                raise UserError(_("退回前必须填写不少于 20 字的复核意见。"))
            previous_checksum = case.submission_checksum
            case.with_context(
                cn_tax_impact_transition=_TAX_IMPACT_TRANSITION_MARKER
            ).write(
                {
                    "state": "draft",
                    "submitted_at": False,
                    "submitted_by_id": False,
                    "submission_checksum": False,
                }
            )
            self.env["sudo.compliance.audit.event"]._log_records(
                case,
                "cn_tax_impact_case.rejected",
                previous_state="submitted",
                new_state="draft",
                details={"previous_checksum": previous_checksum},
            )
        return True

    def action_cancel(self):
        self._require_manager()
        for case in self:
            if case.state != "reviewed":
                raise UserError(_("只有已复核事项可以取消。"))
            case.with_context(
                cn_tax_impact_transition=_TAX_IMPACT_TRANSITION_MARKER
            ).write({"state": "cancelled"})
            self.env["sudo.compliance.audit.event"]._log_records(
                case,
                "cn_tax_impact_case.cancelled",
                previous_state="reviewed",
                new_state="cancelled",
                details={"review_checksum": case.review_checksum},
            )
        return True


class SudoComplianceAssessment(models.Model):
    _inherit = "sudo.compliance.assessment"

    cn_tax_impact_case_ids = fields.One2many(
        "sudo.cn.tax.impact.case",
        "assessment_id",
        string="税务影响复核事项",
        readonly=True,
    )
    cn_tax_impact_case_count = fields.Integer(
        string="税务影响事项",
        compute="_compute_cn_tax_impact_summary",
    )
    cn_tax_impact_pending_count = fields.Integer(
        string="待完成影响复核",
        compute="_compute_cn_tax_impact_summary",
    )
    cn_tax_impact_reviewed_count = fields.Integer(
        string="已复核影响事项",
        compute="_compute_cn_tax_impact_summary",
    )
    cn_tax_impact_unquantifiable_count = fields.Integer(
        string="已复核但无法量化",
        compute="_compute_cn_tax_impact_summary",
    )
    cn_tax_impact_integrity_issue_count = fields.Integer(
        string="复核完整性异常",
        compute="_compute_cn_tax_impact_summary",
    )
    cn_reviewed_underpayment_amount = fields.Monetary(
        string="已复核潜在少缴税影响",
        currency_field="company_currency_id",
        compute="_compute_cn_tax_impact_summary",
    )
    cn_reviewed_overpayment_amount = fields.Monetary(
        string="已复核潜在多缴税影响",
        currency_field="company_currency_id",
        compute="_compute_cn_tax_impact_summary",
    )
    cn_reviewed_timing_amount = fields.Monetary(
        string="已复核期间错配影响",
        currency_field="company_currency_id",
        compute="_compute_cn_tax_impact_summary",
    )
    company_currency_id = fields.Many2one(
        related="company_id.currency_id",
        readonly=True,
    )
    cn_tax_impact_applicable = fields.Boolean(
        string="适用中国税务影响复核",
        compute="_compute_cn_tax_impact_applicable",
    )

    @api.depends("country_id")
    def _compute_cn_tax_impact_applicable(self):
        china = self.env.ref("base.cn")
        for assessment in self:
            assessment.cn_tax_impact_applicable = (
                assessment.country_id == china
            )

    @api.depends(
        "cn_tax_impact_case_ids.state",
        "cn_tax_impact_case_ids.quantification_state",
        "cn_tax_impact_case_ids.impact_direction",
        "cn_tax_impact_case_ids.impact_amount",
        "cn_tax_impact_case_ids.integrity_state",
    )
    def _compute_cn_tax_impact_summary(self):
        for assessment in self:
            summary = _impact_summary(assessment.cn_tax_impact_case_ids)
            assessment.cn_tax_impact_case_count = summary["count"]
            assessment.cn_tax_impact_pending_count = summary["pending_count"]
            assessment.cn_tax_impact_reviewed_count = summary["reviewed_count"]
            assessment.cn_tax_impact_unquantifiable_count = summary[
                "unquantifiable_count"
            ]
            assessment.cn_tax_impact_integrity_issue_count = summary[
                "integrity_issue_count"
            ]
            assessment.cn_reviewed_underpayment_amount = summary[
                "underpayment"
            ]
            assessment.cn_reviewed_overpayment_amount = summary[
                "overpayment"
            ]
            assessment.cn_reviewed_timing_amount = summary["timing"]

    def action_open_cn_tax_impact_cases(self):
        self.ensure_one()
        return _impact_case_action(
            self.env,
            domain=[("assessment_id", "=", self.id)],
            context={"default_assessment_id": self.id},
        )

    def action_create_cn_tax_impact_case(self):
        self.ensure_one()
        if not self.period_start or not self.period_end:
            raise UserError(_("规则评估没有完整期间，不能建立税务影响复核事项。"))
        return _impact_case_action(
            self.env,
            context={
                "default_profile_id": self.profile_id.id,
                "default_assessment_id": self.id,
                "default_period_start": self.period_start,
                "default_period_end": self.period_end,
            },
        )


class SudoComplianceFinding(models.Model):
    _inherit = "sudo.compliance.finding"

    cn_tax_impact_case_ids = fields.Many2many(
        "sudo.cn.tax.impact.case",
        "sudo_cn_tax_impact_case_finding_rel",
        "finding_id",
        "case_id",
        string="税务影响复核事项",
        readonly=True,
    )
    cn_tax_impact_case_count = fields.Integer(
        string="税务影响事项",
        compute="_compute_cn_tax_impact_case_count",
    )

    @api.depends("cn_tax_impact_case_ids.state")
    def _compute_cn_tax_impact_case_count(self):
        for finding in self:
            finding.cn_tax_impact_case_count = len(
                finding.cn_tax_impact_case_ids.filtered(
                    lambda case: case.state != "cancelled"
                )
            )

    def action_open_cn_tax_impact_cases(self):
        self.ensure_one()
        active = self.cn_tax_impact_case_ids.filtered(
            lambda case: case.state != "cancelled"
        )
        return _impact_case_action(
            self.env,
            domain=[("finding_ids", "in", [self.id])],
            res_id=active.id if len(active) == 1 else None,
        )

    def action_create_cn_tax_impact_case(self):
        self.ensure_one()
        if self.result not in ("fail", "unknown", "error"):
            raise UserError(_("只有失败、待确认或执行错误的规则结果可以建立税务影响事项。"))
        active = self.cn_tax_impact_case_ids.filtered(
            lambda case: case.state != "cancelled"
        )[:1]
        if active:
            return _impact_case_action(self.env, res_id=active.id)
        assessment = self.assessment_id
        if not assessment.period_start or not assessment.period_end:
            raise UserError(_("规则评估没有完整期间，不能建立税务影响复核事项。"))
        return _impact_case_action(
            self.env,
            context={
                "default_profile_id": assessment.profile_id.id,
                "default_assessment_id": assessment.id,
                "default_period_start": assessment.period_start,
                "default_period_end": assessment.period_end,
                "default_finding_ids": [(6, 0, self.ids)],
                "default_title": self.title,
            },
        )


class SudoChinaVatPeriodReconciliationRun(models.Model):
    _inherit = "sudo.cn.vat.period.reconciliation.run"

    tax_impact_case_ids = fields.One2many(
        "sudo.cn.tax.impact.case",
        "vat_run_id",
        string="税务影响复核事项",
        readonly=True,
    )
    tax_impact_case_count = fields.Integer(
        string="税务影响事项",
        compute="_compute_tax_impact_summary",
    )
    tax_impact_pending_count = fields.Integer(
        string="待完成影响复核",
        compute="_compute_tax_impact_summary",
    )
    tax_impact_reviewed_count = fields.Integer(
        string="已复核影响事项",
        compute="_compute_tax_impact_summary",
    )
    tax_impact_unquantifiable_count = fields.Integer(
        string="已复核但无法量化",
        compute="_compute_tax_impact_summary",
    )
    tax_impact_integrity_issue_count = fields.Integer(
        string="复核完整性异常",
        compute="_compute_tax_impact_summary",
    )
    reviewed_underpayment_amount = fields.Monetary(
        string="已复核潜在少缴税影响",
        currency_field="currency_id",
        compute="_compute_tax_impact_summary",
    )
    reviewed_overpayment_amount = fields.Monetary(
        string="已复核潜在多缴税影响",
        currency_field="currency_id",
        compute="_compute_tax_impact_summary",
    )
    reviewed_timing_amount = fields.Monetary(
        string="已复核期间错配影响",
        currency_field="currency_id",
        compute="_compute_tax_impact_summary",
    )

    @api.depends(
        "tax_impact_case_ids.state",
        "tax_impact_case_ids.quantification_state",
        "tax_impact_case_ids.impact_direction",
        "tax_impact_case_ids.impact_amount",
        "tax_impact_case_ids.integrity_state",
    )
    def _compute_tax_impact_summary(self):
        for run in self:
            summary = _impact_summary(run.tax_impact_case_ids)
            run.tax_impact_case_count = summary["count"]
            run.tax_impact_pending_count = summary["pending_count"]
            run.tax_impact_reviewed_count = summary["reviewed_count"]
            run.tax_impact_unquantifiable_count = summary[
                "unquantifiable_count"
            ]
            run.tax_impact_integrity_issue_count = summary[
                "integrity_issue_count"
            ]
            run.reviewed_underpayment_amount = summary["underpayment"]
            run.reviewed_overpayment_amount = summary["overpayment"]
            run.reviewed_timing_amount = summary["timing"]

    def action_open_tax_impact_cases(self):
        self.ensure_one()
        return _impact_case_action(
            self.env,
            domain=[("vat_run_id", "=", self.id)],
            context={"default_vat_run_id": self.id},
        )

    def action_create_tax_impact_case(self):
        self.ensure_one()
        if self.state not in ("succeeded", "superseded"):
            raise UserError(_("只有成功的增值税勾稽审计快照可以建立税务影响事项。"))
        return _impact_case_action(
            self.env,
            context={
                "default_profile_id": self.profile_id.id,
                "default_vat_run_id": self.id,
                "default_period_start": self.period_start,
                "default_period_end": self.period_end,
            },
        )

    def action_print_vat_adjustment_report(self):
        self.ensure_one()
        if self.state not in ("succeeded", "superseded"):
            raise UserError(_("只有成功的增值税勾稽审计快照可以生成调节报告。"))
        return self.env.ref(
            "sudo_country_pack_cn.action_report_cn_vat_adjustment"
        ).report_action(self)


class SudoChinaVatPeriodReconciliationIssue(models.Model):
    _inherit = "sudo.cn.vat.period.reconciliation.issue"

    tax_impact_case_ids = fields.Many2many(
        "sudo.cn.tax.impact.case",
        "sudo_cn_tax_impact_case_issue_rel",
        "issue_id",
        "case_id",
        string="税务影响复核事项",
        readonly=True,
    )
    tax_impact_case_count = fields.Integer(
        string="税务影响事项",
        compute="_compute_tax_impact_case_count",
    )

    @api.depends("tax_impact_case_ids.state")
    def _compute_tax_impact_case_count(self):
        for issue in self:
            issue.tax_impact_case_count = len(
                issue.tax_impact_case_ids.filtered(
                    lambda case: case.state != "cancelled"
                )
            )

    def action_open_tax_impact_cases(self):
        self.ensure_one()
        active = self.tax_impact_case_ids.filtered(
            lambda case: case.state != "cancelled"
        )
        return _impact_case_action(
            self.env,
            domain=[("reconciliation_issue_ids", "in", [self.id])],
            res_id=active.id if len(active) == 1 else None,
        )

    def action_create_tax_impact_case(self):
        self.ensure_one()
        active = self.tax_impact_case_ids.filtered(
            lambda case: case.state != "cancelled"
        )[:1]
        if active:
            return _impact_case_action(self.env, res_id=active.id)
        run = self.run_id
        return _impact_case_action(
            self.env,
            context={
                "default_profile_id": run.profile_id.id,
                "default_vat_run_id": run.id,
                "default_period_start": run.period_start,
                "default_period_end": run.period_end,
                "default_reconciliation_issue_ids": [(6, 0, self.ids)],
                "default_title": self.name,
            },
        )
