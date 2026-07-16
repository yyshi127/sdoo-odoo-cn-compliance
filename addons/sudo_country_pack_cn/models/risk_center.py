from odoo import _, fields, models


EVIDENCE_STATES = [
    ("none", "无证据"),
    ("partial", "待验证"),
    ("verified", "已验证"),
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
        string="官方来源",
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

    def _compute_cn_risk_center_display(self):
        Evidence = self.env["sudo.compliance.evidence"].sudo()
        for finding in self:
            assessment = finding.assessment_id
            finding.cn_risk_period_label = _period_label(
                assessment.period_start,
                assessment.period_end,
            )
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
            finding.cn_risk_next_action = finding._cn_risk_next_action()

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

    def _cn_risk_next_action(self):
        self.ensure_one()
        task = self.current_task_id
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
    )

    def _compute_cn_remediation_display(self):
        Evidence = self.env["sudo.compliance.evidence"].sudo()
        for task in self:
            assessment = task.assessment_id
            task.cn_remediation_period_label = _period_label(
                assessment.period_start,
                assessment.period_end,
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
            task.cn_remediation_next_action = task._cn_remediation_next_action()

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

    def _cn_remediation_next_action(self):
        self.ensure_one()
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


def _period_label(period_start, period_end):
    if period_start and period_end:
        return _("%(start)s 至 %(end)s", start=period_start, end=period_end)
    return _("未记录期间")


def _evidence_state(evidence_count, verified_evidence_count):
    if not evidence_count:
        return "none"
    if evidence_count == verified_evidence_count:
        return "verified"
    return "partial"
