from odoo import _, fields, models
from odoo.osv import expression


EVIDENCE_STATES = [
    ("none", "无证据"),
    ("partial", "待验证"),
    ("verified", "已验证"),
]


TRACEABILITY_STATES = [
    ("blocked", "受阻"),
    ("action_required", "需要处理"),
    ("complete", "完整"),
]


CLOSURE_STATES = [
    ("blocked", "受阻"),
    ("action_required", "需要处理"),
    ("ready", "就绪"),
]


DATA_BASIS_STATES = [
    ("no_period", "未设置期间"),
    ("missing", "缺失"),
    ("blocked", "受阻"),
    ("warning", "需关注"),
    ("ready", "就绪"),
]

RECONCILIATION_RISK_SUMMARY_KEYS = {
    "cn.reconciliation.vat.risk_summary",
    "cn.reconciliation.cit.risk_summary",
    "cn.reconciliation.iit.risk_summary",
}

RECONCILIATION_RISK_STATES = [
    ("unavailable", "不可用"),
    ("blocked", "受阻"),
    ("difference_review_required", "差异待复核"),
    ("aligned_with_disclosure_required", "披露待复核"),
    ("aligned", "已勾稽"),
]

TAX_IMPACT_STATES = [
    ("none", "无"),
    ("pending", "待复核"),
    ("integrity_issue", "完整性异常"),
    ("unquantifiable", "暂无法量化"),
    ("reviewed", "已复核"),
]

REMEDIATION_URGENCY_STATES = [
    ("no_task", "未建任务"),
    ("overdue", "已逾期"),
    ("due_soon", "即将到期"),
    ("pending_review", "待复核"),
    ("waiting_rescan", "等待复扫"),
    ("blocked", "受阻"),
    ("on_track", "正常推进"),
    ("closed", "已关闭"),
]


class SudoChinaRiskCenterFinding(models.Model):
    _inherit = "sudo.compliance.finding"

    cn_risk_period_label = fields.Char(
        string="适用期间",
        compute="_compute_cn_risk_center_display",
    )
    cn_risk_next_action = fields.Char(
        string="下一步动作",
        compute="_compute_cn_risk_center_display",
    )
    cn_risk_action_summary = fields.Char(
        string="Risk Action Summary",
        compute="_compute_cn_risk_center_display",
    )
    cn_risk_remediation_urgency = fields.Selection(
        REMEDIATION_URGENCY_STATES,
        string="Remediation Urgency",
        compute="_compute_cn_risk_center_display",
    )
    cn_risk_responsibility_summary = fields.Char(
        string="Responsibility Summary",
        compute="_compute_cn_risk_center_display",
    )
    cn_risk_evidence_state = fields.Selection(
        EVIDENCE_STATES,
        string="证据状态",
        compute="_compute_cn_risk_center_display",
    )
    cn_risk_evidence_count = fields.Integer(
        string="证据记录",
        compute="_compute_cn_risk_center_display",
    )
    cn_risk_verified_evidence_count = fields.Integer(
        string="已验证证据",
        compute="_compute_cn_risk_center_display",
    )

    cn_risk_fact_snapshot_count = fields.Integer(
        string="Fact Snapshots",
        compute="_compute_cn_risk_center_display",
    )
    cn_risk_fact_issue_count = fields.Integer(
        string="Fact Issues",
        compute="_compute_cn_risk_center_display",
    )
    cn_risk_fact_summary = fields.Char(
        string="Fact Summary",
        compute="_compute_cn_risk_center_display",
    )
    cn_reconciliation_risk_state = fields.Selection(
        RECONCILIATION_RISK_STATES,
        string="Reconciliation Risk",
        compute="_compute_cn_risk_center_display",
    )
    cn_reconciliation_risk_summary = fields.Char(
        string="Reconciliation Summary",
        compute="_compute_cn_risk_center_display",
    )
    cn_reconciliation_risk_next_action = fields.Char(
        string="Reconciliation Next Action",
        compute="_compute_cn_risk_center_display",
    )
    cn_risk_data_basis_state = fields.Selection(
        DATA_BASIS_STATES,
        string="Data Basis",
        compute="_compute_cn_risk_center_display",
    )
    cn_risk_data_basis_required_type_count = fields.Integer(
        string="Required Data Types",
        compute="_compute_cn_risk_center_display",
    )
    cn_risk_data_basis_ready_type_count = fields.Integer(
        string="Ready Data Types",
        compute="_compute_cn_risk_center_display",
    )
    cn_risk_data_basis_missing_type_count = fields.Integer(
        string="Missing Data Types",
        compute="_compute_cn_risk_center_display",
    )
    cn_risk_data_basis_missing_type_summary = fields.Char(
        string="Missing Data Type Summary",
        compute="_compute_cn_risk_center_display",
    )
    cn_risk_data_basis_next_action = fields.Char(
        string="Data Basis Next Action",
        compute="_compute_cn_risk_center_display",
    )

    cn_traceability_state = fields.Selection(
        TRACEABILITY_STATES,
        string="Traceability",
        compute="_compute_cn_risk_center_display",
    )
    cn_traceability_gap_count = fields.Integer(
        string="Traceability Gaps",
        compute="_compute_cn_risk_center_display",
    )
    cn_traceability_next_action = fields.Char(
        string="Traceability Next Action",
        compute="_compute_cn_risk_center_display",
    )
    cn_closure_state = fields.Selection(
        CLOSURE_STATES,
        string="Closure Status",
        compute="_compute_cn_risk_center_display",
        search="_search_cn_closure_state",
    )
    cn_closure_summary = fields.Char(
        string="Closure Summary",
        compute="_compute_cn_risk_center_display",
    )

    cn_cross_border_fact_state = fields.Selection(
        [
            ("unavailable", "Unavailable"),
            ("no_transactions", "No Transactions"),
            ("pending_review", "Pending Review"),
            ("reviewed", "Reviewed"),
            ("limited", "Limited"),
        ],
        string="Cross-Border Facts",
        compute="_compute_cn_risk_center_display",
    )
    cn_cross_border_pending_count = fields.Integer(
        string="Cross-Border Pending",
        compute="_compute_cn_risk_center_display",
    )
    cn_cross_border_reviewed_count = fields.Integer(
        string="Cross-Border Reviewed",
        compute="_compute_cn_risk_center_display",
    )
    cn_cross_border_transaction_count = fields.Integer(
        string="Cross-Border Total",
        compute="_compute_cn_risk_center_display",
    )
    cn_cross_border_next_action = fields.Char(
        string="Cross-Border Next Action",
        compute="_compute_cn_risk_center_display",
    )

    cn_risk_rule_basis_state = fields.Selection(
        [
            ("missing", "缺少依据"),
            ("source_warning", "来源需复核"),
            ("professional_pending", "专业待签核"),
            ("active_attention", "规则需关注"),
            ("ready", "依据可追溯"),
        ],
        string="依据状态",
        compute="_compute_cn_risk_center_display",
    )
    cn_risk_rule_source_count = fields.Integer(
        string="规则官方来源数量",
        compute="_compute_cn_risk_center_display",
    )
    cn_risk_rule_release_state = fields.Selection(
        related="rule_version_id.cn_release_state",
        string="规则发布状态",
        readonly=True,
    )
    cn_risk_rule_professional_state = fields.Selection(
        related="rule_version_id.professional_review_state",
        string="专业签核",
        readonly=True,
    )

    cn_risk_currency_id = fields.Many2one(
        related="company_id.currency_id",
        string="Currency",
        readonly=True,
    )
    cn_tax_impact_state = fields.Selection(
        TAX_IMPACT_STATES,
        string="Tax Impact",
        compute="_compute_cn_risk_center_display",
    )
    cn_tax_impact_pending_review_count = fields.Integer(
        string="Pending Tax Impact",
        compute="_compute_cn_risk_center_display",
    )
    cn_tax_impact_unquantifiable_review_count = fields.Integer(
        string="Unquantifiable Tax Impact",
        compute="_compute_cn_risk_center_display",
    )
    cn_tax_impact_integrity_issue_count = fields.Integer(
        string="Tax Impact Integrity Issues",
        compute="_compute_cn_risk_center_display",
    )
    cn_tax_impact_reviewed_underpayment_amount = fields.Monetary(
        string="Reviewed Underpayment",
        currency_field="cn_risk_currency_id",
        compute="_compute_cn_risk_center_display",
    )
    cn_tax_impact_reviewed_overpayment_amount = fields.Monetary(
        string="Reviewed Overpayment",
        currency_field="cn_risk_currency_id",
        compute="_compute_cn_risk_center_display",
    )
    cn_tax_impact_reviewed_timing_amount = fields.Monetary(
        string="Reviewed Timing Difference",
        currency_field="cn_risk_currency_id",
        compute="_compute_cn_risk_center_display",
    )
    cn_tax_impact_summary = fields.Char(
        string="Tax Impact Summary",
        compute="_compute_cn_risk_center_display",
    )

    def _compute_cn_risk_center_display(self):
        Evidence = self.env["sudo.compliance.evidence"].sudo()
        for finding in self:
            assessment = finding.assessment_id
            finding.cn_risk_period_label = _period_label(
                assessment.period_start,
                assessment.period_end,
                finding.env._,
            )
            evidence_domain = [("finding_id", "=", finding.id)]
            if finding.current_task_id:
                evidence_domain = [
                    "|",
                    ("finding_id", "=", finding.id),
                    ("task_id", "=", finding.current_task_id.id),
                ]
            evidence_count = Evidence.search_count(evidence_domain)
            verified_evidence_count = Evidence.search_count(
                evidence_domain + [("state", "=", "verified")]
            )
            finding.cn_risk_evidence_count = evidence_count
            finding.cn_risk_verified_evidence_count = verified_evidence_count
            finding.cn_risk_evidence_state = _evidence_state(
                evidence_count,
                verified_evidence_count,
            )
            finding.cn_risk_rule_source_count = len(
                finding.rule_version_id.authority_source_ids
            )
            finding.cn_risk_rule_basis_state = (
                finding._cn_risk_rule_basis_state()
            )
            (
                finding.cn_risk_fact_snapshot_count,
                finding.cn_risk_fact_issue_count,
                finding.cn_risk_fact_summary,
            ) = finding._cn_risk_fact_summary()
            (
                finding.cn_reconciliation_risk_state,
                finding.cn_reconciliation_risk_summary,
                finding.cn_reconciliation_risk_next_action,
            ) = finding._cn_reconciliation_risk_summary()
            (
                finding.cn_risk_data_basis_state,
                finding.cn_risk_data_basis_required_type_count,
                finding.cn_risk_data_basis_ready_type_count,
                finding.cn_risk_data_basis_missing_type_count,
                finding.cn_risk_data_basis_missing_type_summary,
                finding.cn_risk_data_basis_next_action,
            ) = _assessment_data_basis_values(assessment)
            finding.cn_risk_next_action = finding._cn_risk_next_action()
            (
                finding.cn_risk_remediation_urgency,
                finding.cn_risk_responsibility_summary,
            ) = _remediation_responsibility_values(
                finding.current_task_id,
                finding.env._,
            )
            (
                finding.cn_traceability_state,
                finding.cn_traceability_gap_count,
                finding.cn_traceability_next_action,
            ) = finding._cn_traceability_summary()
            (
                finding.cn_cross_border_fact_state,
                finding.cn_cross_border_pending_count,
                finding.cn_cross_border_reviewed_count,
                finding.cn_cross_border_transaction_count,
                finding.cn_cross_border_next_action,
            ) = finding._cn_cross_border_fact_summary()
            (
                finding.cn_tax_impact_state,
                finding.cn_tax_impact_pending_review_count,
                finding.cn_tax_impact_unquantifiable_review_count,
                finding.cn_tax_impact_integrity_issue_count,
                finding.cn_tax_impact_reviewed_underpayment_amount,
                finding.cn_tax_impact_reviewed_overpayment_amount,
                finding.cn_tax_impact_reviewed_timing_amount,
                finding.cn_tax_impact_summary,
            ) = finding._cn_tax_impact_summary()
            (
                finding.cn_closure_state,
                finding.cn_closure_summary,
            ) = finding._cn_closure_summary()
            finding.cn_risk_action_summary = finding._cn_risk_action_summary()

    def _cn_risk_rule_basis_state(self):
        self.ensure_one()
        version = self.rule_version_id
        if not version or not version.authority_source_ids:
            return "missing"
        if self.source_warning or not version.cn_governance_ready:
            return "source_warning"
        if version.professional_review_state != "approved":
            return "professional_pending"
        if version.cn_release_state == "active_attention":
            return "active_attention"
        return "ready"

    def _search_cn_closure_state(self, operator, value):
        records = self.with_context(lang=self.env.user.lang or "en_US")
        allowed = {"ready", "action_required", "blocked"}
        if operator in ("=", "!="):
            values = {value}
        elif operator in ("in", "not in"):
            values = set(value or [])
        else:
            return [("id", "=", 0)]
        values &= allowed
        if not values:
            return [] if operator in ("!=", "not in") else [("id", "=", 0)]
        cn_domain = [("assessment_id.profile_id.country_id.code", "=", "CN")]
        matched = records.search(cn_domain).filtered(
            lambda finding: finding._cn_closure_summary()[0] in values
        )
        domain = [("id", "in", matched.ids)]
        if operator in ("!=", "not in"):
            return expression.NOT(domain)
        return domain

    def action_cn_open_risk_rule_version(self):
        self.ensure_one()
        if not self.rule_version_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "name": _("风险规则版本"),
            "res_model": "sudo.compliance.rule.version",
            "view_mode": "form",
            "res_id": self.rule_version_id.id,
            "target": "current",
        }

    def _cn_risk_fact_summary(self):
        self.ensure_one()
        snapshots = self.fact_snapshot_ids
        missing_count = len(self.missing_fact_keys or [])
        if not snapshots:
            if missing_count:
                return (
                    0,
                    missing_count,
                    _("Missing required facts: %s")
                    % ", ".join(self.missing_fact_keys[:3]),
                )
            return (0, 0, _("No rule fact snapshots are attached."))

        issue_count = missing_count
        labels = []
        quality_labels = dict(
            snapshots._fields["quality_state"]._description_selection(self.env)
        )
        for snapshot in snapshots[:4]:
            label = snapshot.definition_id.label or snapshot.definition_id.key
            quality_key = snapshot.quality_state or "unknown"
            quality_label = quality_labels.get(quality_key, _("Unknown"))
            labels.append("%s=%s" % (label, quality_label))
            if quality_key in ("missing", "stale", "truncated", "error"):
                issue_count += 1
            elif not snapshot.is_complete or not snapshot.is_full_dataset:
                issue_count += 1
        if len(snapshots) > 4:
            labels.append(_("+%s more") % (len(snapshots) - 4))
        if missing_count:
            labels.append(_("missing %s") % missing_count)
        return (len(snapshots), issue_count, "; ".join(labels))

    def _cn_risk_next_action(self):
        self.ensure_one()
        task = self.current_task_id
        if self.cn_risk_data_basis_state in ("no_period", "missing", "blocked"):
            return _(
                "Complete the assessment data basis before relying on this risk conclusion."
            )
        if self.cn_risk_data_basis_state == "warning":
            return _("Review incomplete period data before report sign-off.")
        if (
            self.cn_reconciliation_risk_state
            and self.cn_reconciliation_risk_state != "unavailable"
            and self.cn_reconciliation_risk_next_action
        ):
            return self.cn_reconciliation_risk_next_action
        if self.result in ("unknown", "error"):
            return _("先核对数据充分性、规则执行日志和来源限制。")
        if self.review_state == "pending":
            return _("先完成人工复核，确认风险是否成立。")
        if self.review_state == "correction_required" and not task:
            return _("创建整改任务，明确责任人、截止日期和证据要求。")
        if task and task.is_overdue:
            return _("优先处理逾期整改，并补充整改证据。")
        if task and task.state in ("open", "in_progress", "waiting", "blocked"):
            return _("推进整改任务，更新处理进展和正式证据。")
        if task and task.state == "pending_review":
            return _("复核整改结果，确认是否可以发起验证复扫。")
        if task and task.verification_state == "pending_rescan":
            return _("等待验证复扫完成，并查看复扫结论。")
        if task and task.verification_state == "failed":
            return _("复扫未通过，重新分析差异并补充整改。")
        if not self.cn_tax_impact_case_count:
            return _("评估是否需要建立税务影响复核事项。")
        if self.cn_risk_evidence_state != "verified":
            return _("补齐并验证正式证据，确保报告可引用。")
        return _("持续跟踪规则复扫、证据链和报告披露。")


    def _cn_reconciliation_risk_summary(self):
        self.ensure_one()
        snapshot = next(
            (
                item
                for item in self.fact_snapshot_ids
                if item.definition_id.key in RECONCILIATION_RISK_SUMMARY_KEYS
            ),
            None,
        )
        if not snapshot or not isinstance(snapshot.value_json, dict):
            return (
                "unavailable",
                _("No reconciliation risk summary is attached."),
                False,
            )

        value = snapshot.value_json
        state = value.get("risk_status") or value.get("conclusion_state")
        allowed_states = {item[0] for item in RECONCILIATION_RISK_STATES}
        if state not in allowed_states:
            state = "blocked" if state else "unavailable"

        counts = value.get("counts") if isinstance(value.get("counts"), dict) else {}
        material = value.get("material_differences")
        if isinstance(material, dict):
            material_count = len(material)
        elif isinstance(material, list):
            material_count = len(material)
        else:
            material_count = 0
        issues = (
            value.get("top_issues")
            if isinstance(value.get("top_issues"), list)
            else []
        )
        issue_codes = []
        for issue in issues[:3]:
            if isinstance(issue, dict):
                code = issue.get("code") or issue.get("issue_code")
            else:
                code = str(issue)
            if code:
                issue_codes.append(code)

        summary_parts = [
            str(state),
            "differences %s" % counts.get("difference_count", 0),
            "blocking %s" % counts.get("blocking_issue_count", 0),
            "warnings %s" % counts.get("warning_issue_count", 0),
            "material %s" % material_count,
        ]
        if issue_codes:
            summary_parts.append("top issues %s" % ", ".join(issue_codes))
        return (
            state,
            "; ".join(summary_parts),
            value.get("next_action") or False,
        )

    def _cn_tax_impact_summary(self):
        self.ensure_one()
        cases = self.cn_tax_impact_case_ids.filtered(
            lambda record: record.state != "cancelled"
        )
        if not cases:
            return (
                "none",
                0,
                0,
                0,
                0.0,
                0.0,
                0.0,
                _("No tax impact review case is linked."),
            )

        pending_count = len(cases.filtered(lambda record: record.state != "reviewed"))
        reviewed = cases.filtered(lambda record: record.state == "reviewed")
        integrity_issue_count = len(
            reviewed.filtered(lambda record: record.integrity_state != "verified")
        )
        verified = reviewed.filtered(
            lambda record: record.integrity_state == "verified"
        )
        unquantifiable_count = len(
            verified.filtered(
                lambda record: record.quantification_state == "not_quantifiable"
            )
        )
        quantified = verified.filtered(
            lambda record: record.quantification_state == "reviewed"
        )
        underpayment = sum(
            quantified.filtered(
                lambda record: record.impact_direction == "potential_underpayment"
            ).mapped("impact_amount")
        )
        overpayment = sum(
            quantified.filtered(
                lambda record: record.impact_direction == "potential_overpayment"
            ).mapped("impact_amount")
        )
        timing = sum(
            quantified.filtered(
                lambda record: record.impact_direction == "timing_difference"
            ).mapped("impact_amount")
        )
        if pending_count:
            state = "pending"
        elif integrity_issue_count:
            state = "integrity_issue"
        elif unquantifiable_count:
            state = "unquantifiable"
        else:
            state = "reviewed"
        summary = (
            "cases %(cases)s; pending %(pending)s; underpayment %(under)s; "
            "overpayment %(over)s; timing %(timing)s; unquantifiable %(unq)s"
        ) % {
            "cases": len(cases),
            "pending": pending_count,
            "under": underpayment,
            "over": overpayment,
            "timing": timing,
            "unq": unquantifiable_count,
        }
        return (
            state,
            pending_count,
            unquantifiable_count,
            integrity_issue_count,
            underpayment,
            overpayment,
            timing,
            summary,
        )

    def _cn_traceability_summary(self):
        self.ensure_one()
        gaps = []
        if self.cn_risk_data_basis_state in (
            "no_period",
            "missing",
            "blocked",
            "warning",
        ):
            gaps.append("data_basis")
        if self.cn_risk_rule_basis_state != "ready":
            gaps.append("rule_basis")
        if self.result in ("unknown", "error"):
            gaps.append("scan_result")
        if self.review_state == "pending":
            gaps.append("human_review")
        if self.review_state == "correction_required" and not self.current_task_id:
            gaps.append("remediation_task")
        if self.current_task_id and self.current_task_id.state not in (
            "done",
            "cancelled",
        ):
            gaps.append("remediation_closure")
        if self.cn_risk_evidence_state != "verified":
            gaps.append("evidence")
        if not self.cn_tax_impact_case_count and self.result in (
            "fail",
            "unknown",
            "error",
        ):
            gaps.append("tax_impact")
        if not gaps:
            return ("complete", 0, _("Traceability is complete for reporting."))
        if set(gaps) & {"data_basis", "rule_basis", "scan_result", "human_review"}:
            return (
                "blocked",
                len(gaps),
                _("Complete data basis, rule basis, scan result and human review before reporting."),
            )
        return (
            "action_required",
            len(gaps),
            _("Close remediation, tax impact and verified evidence gaps."),
        )

    def _cn_closure_summary(self):
        self.ensure_one()
        task = self.current_task_id
        return _closure_summary_values(
            translate=self.env._,
            data_basis_state=self.cn_risk_data_basis_state,
            rule_basis_state=self.cn_risk_rule_basis_state,
            result=self.result,
            review_state=self.review_state,
            task_state=task.state if task else False,
            task_verification_state=task.verification_state if task else False,
            tax_impact_state=self.cn_tax_impact_state,
            evidence_state=self.cn_risk_evidence_state,
        )

    def _cn_risk_action_summary(self):
        self.ensure_one()
        parts = []
        if self.cn_risk_next_action:
            parts.append(_("Next: %(action)s", action=self.cn_risk_next_action))
        if self.cn_risk_responsibility_summary:
            parts.append(
                _(
                    "Owner/due: %(responsibility)s",
                    responsibility=self.cn_risk_responsibility_summary,
                )
            )
        elif not self.current_task_id and self.review_state == "correction_required":
            parts.append(_("Owner/due: no remediation task"))
        if self.cn_risk_evidence_count:
            parts.append(
                _(
                    "Evidence: %(verified)s/%(total)s verified",
                    verified=self.cn_risk_verified_evidence_count,
                    total=self.cn_risk_evidence_count,
                )
            )
        else:
            parts.append(_("Evidence: none"))
        if self.cn_closure_summary:
            parts.append(_("Closure: %(summary)s", summary=self.cn_closure_summary))
        return " · ".join(parts)

    def _cn_cross_border_fact_summary(self):
        self.ensure_one()
        snapshots = {
            snapshot.definition_id.key: snapshot
            for snapshot in self.fact_snapshot_ids
        }
        if (
            self.rule_id.domain_key != "CN.CROSS_BORDER"
            and "cn.cross_border.detail" not in snapshots
        ):
            return (
                "unavailable",
                0,
                0,
                0,
                _("No cross-border fact snapshot is attached to this finding."),
            )

        detail = snapshots.get("cn.cross_border.detail")
        pending_snapshot = snapshots.get("cn.cross_border.pending_review_count")
        reviewed_snapshot = snapshots.get("cn.cross_border.reviewed_transaction_count")
        detail_value = detail.value_json if detail else {}
        pending = (
            pending_snapshot.value_json
            if pending_snapshot and pending_snapshot.value_json is not None
            else detail_value.get("pending_review_count")
        )
        reviewed = (
            reviewed_snapshot.value_json
            if reviewed_snapshot and reviewed_snapshot.value_json is not None
            else detail_value.get("reviewed_transaction_count")
        )
        total = detail_value.get("transaction_count")
        if not isinstance(pending, int) or not isinstance(reviewed, int):
            return (
                "limited",
                0,
                0,
                0,
                _("Open the rule scan facts and confirm the cross-border snapshot."),
            )
        if total is None:
            total = pending + reviewed
        if pending:
            return (
                "pending_review",
                pending,
                reviewed,
                total,
                _("Open Cross-Border register and finish controlled review before reporting."),
            )
        if reviewed:
            return (
                "reviewed",
                0,
                reviewed,
                total,
                _("Reviewed cross-border facts are available for professional analysis."),
            )
        return (
            "no_transactions",
            0,
            0,
            total,
            _("No cross-border transactions were captured for this period."),
        )

    def action_cn_open_traceability_evidence(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Traceability Evidence"),
            "res_model": "sudo.compliance.evidence",
            "view_mode": "list,form",
            "domain": [
                "|",
                ("finding_id", "=", self.id),
                ("task_id", "=", self.current_task_id.id),
            ],
            "context": {"default_finding_id": self.id},
            "target": "current",
        }


class SudoChinaRiskCenterTask(models.Model):
    _inherit = "sudo.compliance.task"

    cn_remediation_period_label = fields.Char(
        string="适用期间",
        compute="_compute_cn_remediation_display",
    )
    cn_remediation_next_action = fields.Char(
        string="下一步动作",
        compute="_compute_cn_remediation_display",
    )
    cn_remediation_action_summary = fields.Char(
        string="Remediation Action Summary",
        compute="_compute_cn_remediation_display",
    )
    cn_remediation_urgency = fields.Selection(
        REMEDIATION_URGENCY_STATES,
        string="Remediation Urgency",
        compute="_compute_cn_remediation_display",
    )
    cn_remediation_responsibility_summary = fields.Char(
        string="Responsibility Summary",
        compute="_compute_cn_remediation_display",
    )
    cn_remediation_evidence_state = fields.Selection(
        EVIDENCE_STATES,
        string="证据状态",
        compute="_compute_cn_remediation_display",
    )
    cn_remediation_evidence_count = fields.Integer(
        string="证据记录",
        compute="_compute_cn_remediation_display",
    )
    cn_remediation_verified_evidence_count = fields.Integer(
        string="已验证证据",
        compute="_compute_cn_remediation_display",
    )

    cn_remediation_traceability_state = fields.Selection(
        TRACEABILITY_STATES,
        string="Traceability",
        compute="_compute_cn_remediation_display",
    )
    cn_remediation_traceability_gap_count = fields.Integer(
        string="Traceability Gaps",
        compute="_compute_cn_remediation_display",
    )
    cn_remediation_traceability_next_action = fields.Char(
        string="Traceability Next Action",
        compute="_compute_cn_remediation_display",
    )
    cn_remediation_data_basis_state = fields.Selection(
        DATA_BASIS_STATES,
        string="Data Basis",
        compute="_compute_cn_remediation_display",
    )
    cn_remediation_data_basis_missing_type_count = fields.Integer(
        string="Missing Data Types",
        compute="_compute_cn_remediation_display",
    )
    cn_remediation_data_basis_missing_type_summary = fields.Char(
        string="Missing Data Type Summary",
        compute="_compute_cn_remediation_display",
    )
    cn_remediation_data_basis_next_action = fields.Char(
        string="Data Basis Next Action",
        compute="_compute_cn_remediation_display",
    )
    cn_remediation_tax_impact_state = fields.Selection(
        TAX_IMPACT_STATES,
        string="Remediation Tax Impact",
        compute="_compute_cn_remediation_display",
    )
    cn_remediation_tax_impact_pending_review_count = fields.Integer(
        string="Pending Tax Impact",
        compute="_compute_cn_remediation_display",
    )
    cn_remediation_tax_impact_integrity_issue_count = fields.Integer(
        string="Tax Impact Integrity Issues",
        compute="_compute_cn_remediation_display",
    )
    cn_remediation_tax_impact_reviewed_underpayment_amount = fields.Monetary(
        string="Reviewed Underpayment",
        currency_field="cn_remediation_currency_id",
        compute="_compute_cn_remediation_display",
    )
    cn_remediation_tax_impact_reviewed_overpayment_amount = fields.Monetary(
        string="Reviewed Overpayment",
        currency_field="cn_remediation_currency_id",
        compute="_compute_cn_remediation_display",
    )
    cn_remediation_tax_impact_reviewed_timing_amount = fields.Monetary(
        string="Reviewed Timing Difference",
        currency_field="cn_remediation_currency_id",
        compute="_compute_cn_remediation_display",
    )
    cn_remediation_tax_impact_summary = fields.Char(
        string="Tax Impact Summary",
        compute="_compute_cn_remediation_display",
    )
    cn_remediation_currency_id = fields.Many2one(
        related="company_id.currency_id",
        string="Currency",
        readonly=True,
    )

    cn_remediation_rescan_stage = fields.Selection(
        [
            ("in_progress", "整改中"),
            ("overdue", "已逾期"),
            ("blocked", "受阻"),
            ("ready_for_rescan", "可发起复扫"),
            ("pending_rescan", "复扫中"),
            ("failed", "复扫未通过"),
            ("evidence_gap", "证据待核验"),
            ("verified", "已闭环"),
            ("cancelled", "已取消"),
        ],
        string="复扫闭环",
        compute="_compute_cn_remediation_display",
        search="_search_cn_remediation_rescan_stage",
    )

    cn_remediation_progress = fields.Integer(
        string="Remediation Progress",
        compute="_compute_cn_remediation_display",
    )
    cn_remediation_summary = fields.Char(
        string="Remediation Summary",
        compute="_compute_cn_remediation_display",
    )
    cn_remediation_blocker_summary = fields.Char(
        string="Remediation Blockers",
        compute="_compute_cn_remediation_display",
    )

    def _compute_cn_remediation_display(self):
        Evidence = self.env["sudo.compliance.evidence"].sudo()
        for task in self:
            assessment = task.assessment_id
            task.cn_remediation_period_label = _period_label(
                assessment.period_start,
                assessment.period_end,
                task.env._,
            )
            evidence_domain = [("task_id", "=", task.id)]
            evidence_count = Evidence.search_count(evidence_domain)
            verified_evidence_count = Evidence.search_count(
                evidence_domain + [("state", "=", "verified")]
            )
            task.cn_remediation_evidence_count = evidence_count
            task.cn_remediation_verified_evidence_count = verified_evidence_count
            task.cn_remediation_evidence_state = _evidence_state(
                evidence_count,
                verified_evidence_count,
            )
            task.cn_remediation_rescan_stage = (
                task._cn_remediation_rescan_stage()
            )
            (
                task.cn_remediation_data_basis_state,
                _required_type_count,
                _ready_type_count,
                task.cn_remediation_data_basis_missing_type_count,
                task.cn_remediation_data_basis_missing_type_summary,
                task.cn_remediation_data_basis_next_action,
            ) = _assessment_data_basis_values(assessment)
            task.cn_remediation_next_action = task._cn_remediation_next_action()
            finding = task.finding_id
            task.cn_remediation_tax_impact_state = (
                finding.cn_tax_impact_state if finding else "none"
            )
            task.cn_remediation_tax_impact_pending_review_count = (
                finding.cn_tax_impact_pending_review_count if finding else 0
            )
            task.cn_remediation_tax_impact_integrity_issue_count = (
                finding.cn_tax_impact_integrity_issue_count if finding else 0
            )
            task.cn_remediation_tax_impact_reviewed_underpayment_amount = (
                finding.cn_tax_impact_reviewed_underpayment_amount if finding else 0.0
            )
            task.cn_remediation_tax_impact_reviewed_overpayment_amount = (
                finding.cn_tax_impact_reviewed_overpayment_amount if finding else 0.0
            )
            task.cn_remediation_tax_impact_reviewed_timing_amount = (
                finding.cn_tax_impact_reviewed_timing_amount if finding else 0.0
            )
            task.cn_remediation_tax_impact_summary = (
                finding.cn_tax_impact_summary if finding else False
            )
            (
                task.cn_remediation_traceability_state,
                task.cn_remediation_traceability_gap_count,
                task.cn_remediation_traceability_next_action,
            ) = task._cn_remediation_traceability_summary()
            (
                task.cn_remediation_progress,
                task.cn_remediation_summary,
            ) = task._cn_remediation_progress_summary()
            task.cn_remediation_blocker_summary = (
                task._cn_remediation_blocker_summary()
            )
            (
                task.cn_remediation_urgency,
                task.cn_remediation_responsibility_summary,
            ) = _remediation_responsibility_values(task, task.env._)
            task.cn_remediation_action_summary = (
                task._cn_remediation_action_summary()
            )

    def _cn_remediation_rescan_stage(self):
        self.ensure_one()
        if self.state == "cancelled":
            return "cancelled"
        if self.is_overdue and self.state not in ("done", "cancelled"):
            return "overdue"
        if self.state == "blocked":
            return "blocked"
        if self.verification_state == "failed":
            return "failed"
        if self.verification_state == "pending_rescan":
            return "pending_rescan"
        if self.state == "pending_review":
            return "ready_for_rescan"
        if self.state == "done" and self.verification_state == "verified":
            return "verified"
        if self.state == "done" and self.cn_remediation_evidence_state != "verified":
            return "evidence_gap"
        return "in_progress"

    def _search_cn_remediation_rescan_stage(self, operator, value):
        records = self.with_context(lang=self.env.user.lang or "en_US")
        allowed = {
            "in_progress",
            "overdue",
            "blocked",
            "ready_for_rescan",
            "pending_rescan",
            "failed",
            "evidence_gap",
            "verified",
            "cancelled",
        }
        if operator in ("=", "!="):
            values = {value}
        elif operator in ("in", "not in"):
            values = set(value or [])
        else:
            return [("id", "=", 0)]
        values &= allowed
        if not values:
            return [] if operator in ("!=", "not in") else [("id", "=", 0)]
        cn_domain = [
            ("assessment_id.profile_id.country_id.code", "=", "CN"),
            ("task_type", "=", "remediation"),
        ]
        matched = records.search(cn_domain).filtered(
            lambda task: task._cn_remediation_rescan_stage() in values
        )
        domain = [("id", "in", matched.ids)]
        if operator in ("!=", "not in"):
            return expression.NOT(domain)
        return domain

    def _cn_remediation_next_action(self):
        self.ensure_one()
        if self.cn_remediation_data_basis_state in ("no_period", "missing", "blocked"):
            return _("Complete the assessment data basis before closing remediation.")
        if self.cn_remediation_data_basis_state == "warning":
            return _("Review incomplete period data before verification rescan.")
        if self.is_overdue:
            return _("任务已逾期，请优先处理并说明延期原因。")
        if self.state in ("open", "in_progress"):
            return _("推进整改，补充处理记录和证据。")
        if self.state == "waiting":
            return _("跟进等待事项，确认阻塞是否解除。")
        if self.state == "blocked":
            return _("先解除阻塞原因，再继续整改或复扫。")
        if self.state == "pending_review":
            return _("复核整改结果，确认是否具备验证复扫条件。")
        if self.verification_state == "pending_rescan":
            return _("等待验证复扫完成。")
        if self.verification_state == "failed":
            return _("复扫未通过，重新整改并补充证据。")
        if self.state == "done" and self.cn_remediation_evidence_state != "verified":
            return _("整改已完成，但仍需确认正式证据可供报告引用。")
        if self.state == "done":
            return _("整改闭环完成，保留证据和复扫记录。")
        return _("按风险要求推进整改。")

    def action_cn_open_remediation_verification_assessment(self):
        self.ensure_one()
        if not self.verification_assessment_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "name": _("整改验证复扫"),
            "res_model": "sudo.compliance.assessment",
            "view_mode": "form",
            "res_id": self.verification_assessment_id.id,
            "target": "current",
        }

    def _cn_remediation_traceability_summary(self):
        self.ensure_one()
        gaps = []
        if self.cn_remediation_data_basis_state in (
            "no_period",
            "missing",
            "blocked",
            "warning",
        ):
            gaps.append("data_basis")
        if self.state not in ("done", "cancelled"):
            gaps.append("task_closure")
        if self.verification_state in ("pending_rescan", "failed"):
            gaps.append("verification_rescan")
        if self.cn_remediation_evidence_state != "verified":
            gaps.append("evidence")
        if not gaps:
            return ("complete", 0, _("Remediation traceability is complete."))
        if "data_basis" in gaps or "verification_rescan" in gaps:
            return (
                "blocked",
                len(gaps),
                _("Resolve data basis and verification rescan before report sign-off."),
            )
        return (
            "action_required",
            len(gaps),
            _("Close the task and verify remediation evidence."),
        )

    def _cn_remediation_progress_summary(self):
        self.ensure_one()
        checkpoints = 0
        if self.state in ("done", "cancelled"):
            checkpoints += 1
        if self.cn_remediation_evidence_state == "verified":
            checkpoints += 1
        if self.verification_state in ("verified", "not_required"):
            checkpoints += 1
        progress = int(round(checkpoints * 100 / 3.0))
        stage_label = dict(
            self._fields["cn_remediation_rescan_stage"]._description_selection(
                self.env
            )
        ).get(self.cn_remediation_rescan_stage, _("Unknown"))
        task_label = dict(
            self._fields["state"]._description_selection(self.env)
        ).get(self.state, _("Unknown"))
        verification_label = dict(
            self._fields["verification_state"]._description_selection(self.env)
        ).get(self.verification_state, _("Unknown"))
        summary = _(
            "Stage %(stage)s; task %(task)s; verification %(verification)s; "
            "evidence %(verified)s/%(total)s; gaps %(gaps)s",
            stage=stage_label,
            task=task_label,
            verification=verification_label,
            verified=self.cn_remediation_verified_evidence_count,
            total=self.cn_remediation_evidence_count,
            gaps=self.cn_remediation_traceability_gap_count,
        )
        return (progress, summary)

    def _cn_remediation_action_summary(self):
        self.ensure_one()
        parts = []
        if self.cn_remediation_next_action:
            parts.append(
                _("Next: %(action)s", action=self.cn_remediation_next_action)
            )
        if self.cn_remediation_responsibility_summary:
            parts.append(
                _(
                    "Owner/due: %(responsibility)s",
                    responsibility=self.cn_remediation_responsibility_summary,
                )
            )
        if self.cn_remediation_blocker_summary:
            parts.append(
                _(
                    "Blockers: %(summary)s",
                    summary=self.cn_remediation_blocker_summary,
                )
            )
        if self.cn_remediation_evidence_count:
            parts.append(
                _(
                    "Evidence: %(verified)s/%(total)s verified",
                    verified=self.cn_remediation_verified_evidence_count,
                    total=self.cn_remediation_evidence_count,
                )
            )
        else:
            parts.append(_("Evidence: none"))
        rescan_label = dict(
            self._fields["cn_remediation_rescan_stage"]._description_selection(
                self.env
            )
        ).get(self.cn_remediation_rescan_stage, _("Unknown"))
        parts.append(_("Rescan: %(state)s", state=rescan_label))
        parts.append(_("Progress: %(progress)s%%", progress=self.cn_remediation_progress or 0))
        return " · ".join(parts)

    def _cn_remediation_blocker_summary(self):
        self.ensure_one()
        blockers = []
        if self.is_overdue and self.state not in ("done", "cancelled"):
            blockers.append(_("overdue"))
        if self.cn_remediation_data_basis_state in ("no_period", "missing", "blocked"):
            blockers.append(_("missing data basis"))
        elif self.cn_remediation_data_basis_state == "warning":
            blockers.append(_("incomplete data basis"))
        if self.state == "blocked":
            blockers.append(_("task blocked"))
        elif self.state not in ("done", "cancelled"):
            blockers.append(_("task not closed"))
        if self.cn_remediation_evidence_state == "none":
            blockers.append(_("no verified evidence"))
        elif self.cn_remediation_evidence_state == "partial":
            blockers.append(_("evidence pending verification"))
        if self.verification_state == "pending_rescan":
            blockers.append(_("verification rescan pending"))
        elif self.verification_state == "failed":
            blockers.append(_("verification rescan failed"))
        elif self.verification_state not in ("verified", "not_required"):
            blockers.append(_("verification not completed"))
        if not blockers:
            return _("No blocker: remediation is ready for report sign-off.")
        return _("Blocked by: %(blockers)s") % {"blockers": "; ".join(blockers)}


def _period_label(period_start, period_end, translate):
    if period_start and period_end:
        return translate(
            "%(start)s to %(end)s",
            start=period_start,
            end=period_end,
        )
    return translate("No period recorded")


def _evidence_state(evidence_count, verified_evidence_count):
    if not evidence_count:
        return "none"
    if evidence_count == verified_evidence_count:
        return "verified"
    return "partial"


def _remediation_responsibility_values(task, translate):
    if not task:
        return ("no_task", translate("No remediation task has been created."))

    assignee = (
        task.assignee_id.display_name if task.assignee_id else translate("Unassigned")
    )
    due_date = task.due_date
    today = fields.Date.context_today(task)

    if task.state in ("done", "cancelled"):
        return (
            "closed",
            translate(
                "Closed by %(assignee)s; due %(due)s",
                assignee=assignee,
                due=due_date or "-",
            ),
        )
    if task.is_overdue:
        urgency = "overdue"
    elif task.state == "blocked":
        urgency = "blocked"
    elif task.verification_state == "pending_rescan":
        urgency = "waiting_rescan"
    elif task.state == "pending_review":
        urgency = "pending_review"
    elif due_date and 0 <= (due_date - today).days <= 7:
        urgency = "due_soon"
    else:
        urgency = "on_track"

    task_state = dict(task._fields["state"]._description_selection(task.env)).get(
        task.state,
        task.state or "-",
    )
    verification_state = dict(
        task._fields["verification_state"]._description_selection(task.env)
    ).get(task.verification_state, task.verification_state or "-")
    summary = translate(
        "%(assignee)s; due %(due)s; task %(state)s; verification %(verification)s",
        assignee=assignee,
        due=due_date or "-",
        state=task_state,
        verification=verification_state,
    )
    return (urgency, summary)


def _closure_summary_values(
    *,
    translate,
    data_basis_state,
    rule_basis_state,
    result,
    review_state,
    task_state,
    task_verification_state,
    tax_impact_state,
    evidence_state,
):
    blockers = []
    actions = []
    has_task = bool(task_state)
    if data_basis_state in ("no_period", "missing", "blocked"):
        blockers.append(translate("data basis"))
    elif data_basis_state == "warning":
        actions.append(translate("review data basis warning"))
    if rule_basis_state != "ready":
        blockers.append(translate("rule/source basis"))
    if result in ("unknown", "error"):
        blockers.append(translate("scan result"))
    if review_state == "pending":
        blockers.append(translate("human review"))
    elif review_state == "correction_required" and not has_task:
        actions.append(translate("create remediation task"))
    if has_task:
        if task_state not in ("done", "cancelled"):
            actions.append(translate("close remediation task"))
        if task_verification_state in ("pending_rescan", "failed"):
            blockers.append(translate("verification rescan"))
        elif task_verification_state not in ("verified", "not_required"):
            actions.append(translate("verify remediation"))
    if tax_impact_state in ("pending", "integrity_issue"):
        blockers.append(translate("tax impact review"))
    elif tax_impact_state in ("none", "unquantifiable") and result in (
        "fail",
        "unknown",
        "error",
    ):
        actions.append(translate("document tax impact"))
    if evidence_state != "verified":
        actions.append(translate("verify evidence"))
    if blockers:
        return (
            "blocked",
            translate(
                "Blocked before sign-off: %(items)s.",
                items=", ".join(blockers[:4]),
            ),
        )
    if actions:
        return (
            "action_required",
            translate(
                "Next before sign-off: %(items)s.",
                items=", ".join(actions[:4]),
            ),
        )
    return (
        "ready",
        translate(
            "Ready for report sign-off: reviewed risk, remediation, evidence, tax impact and rescan controls are aligned."
        ),
    )


def _assessment_data_basis_values(assessment):
    if not assessment or "cn_data_basis_state" not in assessment._fields:
        return (False, 0, 0, 0, False, False)
    return (
        assessment.cn_data_basis_state,
        assessment.cn_data_basis_required_type_count,
        assessment.cn_data_basis_ready_type_count,
        assessment.cn_data_basis_missing_type_count,
        assessment.cn_data_basis_missing_type_summary,
        assessment.cn_data_basis_next_action,
    )
