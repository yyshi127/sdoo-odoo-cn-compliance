from datetime import timedelta

from odoo import _, fields, models


OPEN_TASK_STATES = ("open", "in_progress", "waiting", "pending_review", "blocked")
REVIEW_FINDING_STATES = ("pending", "correction_required")
HIGH_RISK_LEVELS = ("high", "critical")
FLOW_STATES = [
    ("not_started", "未开始"),
    ("ready", "已就绪"),
    ("attention", "需处理"),
    ("blocked", "受限"),
]
NEXT_STEP_KEYS = [
    ("profile", "Profile Setup"),
    ("rule_basis", "Rule Basis"),
    ("data_readiness", "Data Readiness"),
    ("obligations", "Tax Obligations"),
    ("scan", "Rule Scan"),
    ("risks", "Risk Review"),
    ("remediation", "Remediation"),
    ("report_readiness", "Report Readiness"),
    ("evidence", "Evidence"),
    ("filing", "Filing Archive"),
    ("ai_guidance", "AI Guidance"),
]


def _tax_domain_state(latest_assessment, issue_count, limitation_count):
    if limitation_count:
        return "blocked"
    if issue_count:
        return "attention"
    if latest_assessment:
        return "ready"
    return "not_started"


def _cross_border_state(classification, limitation_count):
    if limitation_count:
        return "blocked"
    if not classification:
        return "not_started"
    if classification._current_integrity_state() != "verified":
        return "blocked"
    if (
        classification.cit_taxpayer_status
        in ("nonresident_establishment", "nonresident_no_establishment")
        or classification.cit_collection_method == "withholding"
        or classification.pit_withholding_status == "yes"
    ):
        return "attention"
    return "ready"


def _controlled_filing_domain(profile):
    return [
        ("profile_id", "=", profile.id),
        "|",
        "|",
        ("cn_vat_reconciliation_run_id", "!=", False),
        ("cn_cit_reconciliation_run_id", "!=", False),
        ("cn_iit_reconciliation_run_id", "!=", False),
    ]


def _closed_loop_values(profile):
    if profile.country_id.code != "CN":
        return (False, 0, False)
    if profile.status != "active":
        return (
            "not_started",
            1,
            "Activate the China compliance profile before evaluating the closed loop.",
        )

    stages = [
        ("rule basis", profile.cn_workbench_rule_basis_state),
        ("obligations", profile.cn_workbench_obligation_state),
        ("data", profile.cn_workbench_data_state),
        ("scan", profile.cn_workbench_scan_state),
        ("risk review", profile.cn_workbench_risk_state),
        ("remediation", profile.cn_workbench_remediation_state),
        ("verification rescan", profile.cn_workbench_rescan_state),
        ("report", profile.cn_workbench_report_state),
        ("evidence", profile.cn_workbench_evidence_state),
    ]
    if (
        profile.cn_workbench_filing_obligation_count
        or profile.cn_workbench_filing_archive_count
    ):
        stages.append(("filing archive", profile.cn_workbench_filing_archive_state))
    if profile.cn_workbench_ai_guidance_finding_count:
        stages.append(("AI guidance", profile.cn_workbench_ai_guidance_state))

    blocked = [label for label, state in stages if state == "blocked"]
    gaps = [
        label
        for label, state in stages
        if state in ("not_started", "attention", "blocked")
    ]
    if blocked:
        return (
            "blocked",
            len(gaps),
            "Closed loop blocked: %s." % ", ".join(gaps[:6]),
        )
    if gaps:
        return (
            "attention",
            len(gaps),
            "Closed loop gaps: %s." % ", ".join(gaps[:6]),
        )
    return (
        "ready",
        0,
        "Closed loop is ready: data, scan, risk review, remediation, evidence and report controls are aligned.",
    )


def _conclusion_boundary_values(profile):
    if profile.country_id.code != "CN":
        return (False, False, False)
    if profile.status != "active":
        return (
            "blocked",
            "Not usable as a compliance conclusion until the China profile is active.",
            "Complete and activate the China compliance profile first.",
        )
    if profile.cn_workbench_data_state in ("blocked", "not_started"):
        return (
            "blocked",
            "Not usable as a compliance conclusion because controlled accounting/tax data is not ready.",
            profile.cn_workbench_data_next_action,
        )
    if profile.cn_workbench_rule_basis_state == "blocked":
        return (
            "blocked",
            "Not usable as a compliance conclusion because China rule sources or rule governance require attention.",
            profile.cn_workbench_rule_basis_next_action,
        )
    if profile.cn_workbench_rule_basis_state == "attention":
        return (
            "attention",
            "Conclusion is limited until China rule source freshness and professional sign-off gaps are reviewed.",
            profile.cn_workbench_rule_basis_next_action,
        )
    if profile.cn_workbench_limitation_count:
        return (
            "blocked",
            "Only a limited conclusion is possible because scope, evidence or report limitations exist.",
            "Resolve or explicitly document all limitations before final sign-off.",
        )
    if profile.cn_workbench_obligation_state != "ready":
        return (
            "attention",
            "Conclusion is incomplete until China tax obligation applicability has been reviewed.",
            profile.cn_workbench_obligation_next_action,
        )
    if profile.cn_workbench_scan_state != "ready":
        return (
            "attention",
            "Conclusion is not current because no completed rule scan is available for this profile.",
            "Run and complete a rule scan for the target period.",
        )
    if profile.cn_workbench_risk_state in ("blocked", "attention"):
        return (
            "attention",
            "Conclusion requires review because unresolved or high-risk findings remain.",
            "Review risks, quantify tax impact, and create remediation tasks where needed.",
        )
    if profile.cn_workbench_remediation_state in ("blocked", "attention"):
        return (
            "attention",
            "Conclusion requires remediation follow-through before it can support management sign-off.",
            "Complete open remediation tasks and verify them with evidence.",
        )
    if profile.cn_workbench_rescan_state in ("blocked", "attention"):
        return (
            "attention",
            "Conclusion is waiting for remediation verification rescans.",
            profile.cn_workbench_rescan_next_action,
        )
    if profile.cn_workbench_report_state != "ready":
        return (
            "attention",
            "Conclusion is not yet packaged as an issued formal compliance report.",
            "Generate and issue the formal China compliance report after review gates pass.",
        )
    if profile.cn_workbench_evidence_state != "ready":
        return (
            "attention",
            "Conclusion is not fully supportable until evidence is attached and verified.",
            "Verify supporting evidence for the report, risks, remediation and filing archives.",
        )
    if profile.cn_workbench_ai_guidance_limited_count:
        return (
            "attention",
            "AI guidance is available only as controlled assistance and still has limited inputs to disclose.",
            "Review AI guidance disclosures before using them in remediation instructions.",
        )
    if profile.cn_workbench_closed_loop_state != "ready":
        return (
            "attention",
            "Conclusion is close but the closed-loop control summary still has open gaps.",
            profile.cn_workbench_closed_loop_summary,
        )
    return (
        "ready",
        "Ready for management review: data, scan, risk review, remediation, evidence and issued report are aligned.",
        "Keep rules, source references and period data current before the next scan.",
    )


def _next_best_action_values(profile):
    if profile.country_id.code != "CN":
        return (False, False)
    if profile.status != "active":
        return ("profile", "Complete and activate the China profile")
    if profile.cn_workbench_rule_basis_state == "blocked":
        return ("rule_basis", "Review China rule source and sign-off basis")
    if profile.cn_workbench_data_state in ("blocked", "not_started"):
        return ("data_readiness", "Prepare controlled accounting and tax data")
    if profile.cn_workbench_obligation_state != "ready":
        return ("obligations", "Review China tax obligations")
    if profile.cn_workbench_scan_state != "ready":
        return ("scan", "Run or review the rule scan")
    if profile.cn_workbench_risk_state in ("blocked", "attention"):
        return ("risks", "Review unresolved compliance risks")
    if profile.cn_workbench_remediation_state in ("blocked", "attention"):
        return ("remediation", "Work remediation tasks")
    if profile.cn_workbench_rescan_state in ("blocked", "attention"):
        return ("remediation", "Verify remediation with rescans")
    if profile.cn_workbench_report_state != "ready":
        return ("report_readiness", "Prepare the formal compliance report")
    if profile.cn_workbench_evidence_state != "ready":
        return ("evidence", "Verify supporting evidence")
    if profile.cn_workbench_filing_archive_state in ("blocked", "attention"):
        return ("filing", "Seal filing and payment archives")
    if profile.cn_workbench_ai_guidance_state in ("blocked", "attention"):
        return ("ai_guidance", "Review controlled AI guidance")
    return ("report_readiness", "Review the ready compliance report package")


class SudoChinaComplianceWorkbenchProfile(models.Model):
    _inherit = "sudo.compliance.profile"

    cn_workbench_status = fields.Selection(
        [
            ("setup_required", "档案待完善"),
            ("healthy", "范围内正常"),
            ("warning", "需要关注"),
            ("action_required", "需要整改"),
            ("limited", "范围受限"),
        ],
        string="中国合规状态",
        compute="_compute_cn_workbench",
    )
    cn_workbench_next_action = fields.Char(
        string="下一步动作",
        compute="_compute_cn_workbench",
    )
    cn_workbench_action_summary = fields.Char(
        string="Workbench Action Summary",
        compute="_compute_cn_workbench",
    )
    cn_workbench_period_label = fields.Char(
        string="最新扫描期间",
        compute="_compute_cn_workbench",
    )
    cn_workbench_last_assessment_id = fields.Many2one(
        "sudo.compliance.assessment",
        string="最新规则扫描",
        compute="_compute_cn_workbench",
    )
    cn_workbench_latest_report_id = fields.Many2one(
        "sudo.cn.compliance.report",
        string="最新正式报告",
        compute="_compute_cn_workbench",
    )
    cn_workbench_package_label = fields.Char(
        string="中国包",
        compute="_compute_cn_workbench",
    )
    cn_workbench_scope_label = fields.Char(
        string="覆盖范围",
        compute="_compute_cn_workbench",
    )
    cn_workbench_data_state = fields.Selection(
        FLOW_STATES,
        string="数据准备状态",
        compute="_compute_cn_workbench",
    )
    cn_workbench_data_next_action = fields.Char(
        string="数据准备下一步",
        compute="_compute_cn_workbench",
    )
    cn_workbench_dataset_count = fields.Integer(
        string="受控数据集",
        compute="_compute_cn_workbench",
    )
    cn_workbench_ready_dataset_count = fields.Integer(
        string="可扫描数据集",
        compute="_compute_cn_workbench",
    )
    cn_workbench_posted_move_count = fields.Integer(
        string="Posted Accounting Entries",
        compute="_compute_cn_workbench",
    )
    cn_workbench_draft_move_count = fields.Integer(
        string="Draft Accounting Entries",
        compute="_compute_cn_workbench",
    )
    cn_workbench_posted_invoice_count = fields.Integer(
        string="Posted Accounting Invoices",
        compute="_compute_cn_workbench",
    )
    cn_workbench_currency_id = fields.Many2one(
        related="company_id.currency_id",
        string="工作台币种",
        readonly=True,
    )
    cn_workbench_finding_count = fields.Integer(
        string="风险事项",
        compute="_compute_cn_workbench",
    )
    cn_workbench_high_risk_count = fields.Integer(
        string="高风险事项",
        compute="_compute_cn_workbench",
    )
    cn_workbench_pending_review_count = fields.Integer(
        string="待复核事项",
        compute="_compute_cn_workbench",
    )
    cn_workbench_historical_unresolved_finding_count = fields.Integer(
        string="Historical Unresolved Findings",
        compute="_compute_cn_workbench",
    )
    cn_workbench_open_task_count = fields.Integer(
        string="未完成整改",
        compute="_compute_cn_workbench",
    )
    cn_workbench_overdue_task_count = fields.Integer(
        string="逾期整改",
        compute="_compute_cn_workbench",
    )
    cn_workbench_historical_blocked_task_count = fields.Integer(
        string="Historical Blocked Tasks",
        compute="_compute_cn_workbench",
    )
    cn_workbench_tax_impact_case_count = fields.Integer(
        string="税务影响事项",
        compute="_compute_cn_workbench",
    )
    cn_workbench_pending_tax_impact_count = fields.Integer(
        string="待量化影响",
        compute="_compute_cn_workbench",
    )
    cn_workbench_underpayment_amount = fields.Monetary(
        string="已复核潜在少缴",
        currency_field="cn_workbench_currency_id",
        compute="_compute_cn_workbench",
    )
    cn_workbench_reconciliation_issue_count = fields.Integer(
        string="账税勾稽问题",
        compute="_compute_cn_workbench",
    )
    cn_workbench_vat_issue_count = fields.Integer(
        string="增值税勾稽问题",
        compute="_compute_cn_workbench",
    )
    cn_workbench_cit_issue_count = fields.Integer(
        string="企业所得税勾稽问题",
        compute="_compute_cn_workbench",
    )
    cn_workbench_iit_issue_count = fields.Integer(
        string="个税勾稽问题",
        compute="_compute_cn_workbench",
    )
    cn_workbench_vat_domain_state = fields.Selection(
        FLOW_STATES,
        string="增值税域",
        compute="_compute_cn_workbench",
    )
    cn_workbench_cit_domain_state = fields.Selection(
        FLOW_STATES,
        string="企业所得税域",
        compute="_compute_cn_workbench",
    )
    cn_workbench_iit_domain_state = fields.Selection(
        FLOW_STATES,
        string="个人所得税域",
        compute="_compute_cn_workbench",
    )
    cn_workbench_vat_next_action = fields.Char(
        string="增值税下一步",
        compute="_compute_cn_workbench",
    )
    cn_workbench_cit_next_action = fields.Char(
        string="企业所得税下一步",
        compute="_compute_cn_workbench",
    )
    cn_workbench_iit_next_action = fields.Char(
        string="个人所得税下一步",
        compute="_compute_cn_workbench",
    )
    cn_workbench_obligation_state = fields.Selection(
        FLOW_STATES,
        string="Tax Obligation Readiness",
        compute="_compute_cn_workbench",
    )
    cn_workbench_obligation_next_action = fields.Char(
        string="Tax Obligation Next Action",
        compute="_compute_cn_workbench",
    )
    cn_workbench_obligation_count = fields.Integer(
        string="Candidate Obligations",
        compute="_compute_cn_workbench",
    )
    cn_workbench_applicable_obligation_count = fields.Integer(
        string="Applicable Obligations",
        compute="_compute_cn_workbench",
    )
    cn_workbench_pending_obligation_count = fields.Integer(
        string="Obligations Needing Review",
        compute="_compute_cn_workbench",
    )
    cn_workbench_filing_obligation_count = fields.Integer(
        string="Applicable Filing Obligations",
        compute="_compute_cn_workbench",
    )
    cn_workbench_cross_border_state = fields.Selection(
        FLOW_STATES,
        string="跨境与源泉扣缴域",
        compute="_compute_cn_workbench",
    )
    cn_workbench_cross_border_basis = fields.Char(
        string="跨境判断依据",
        compute="_compute_cn_workbench",
    )
    cn_workbench_cross_border_next_action = fields.Char(
        string="跨境下一步",
        compute="_compute_cn_workbench",
    )
    cn_workbench_cross_border_transaction_count = fields.Integer(
        string="Cross-Border Transactions",
        compute="_compute_cn_workbench",
    )
    cn_workbench_cross_border_pending_count = fields.Integer(
        string="Cross-Border Pending Review",
        compute="_compute_cn_workbench",
    )
    cn_workbench_rule_basis_state = fields.Selection(
        FLOW_STATES,
        string="Rule Basis Readiness",
        compute="_compute_cn_workbench",
    )
    cn_workbench_rule_basis_summary = fields.Char(
        string="Rule Basis Summary",
        compute="_compute_cn_workbench",
    )
    cn_workbench_rule_basis_next_action = fields.Char(
        string="Rule Basis Next Action",
        compute="_compute_cn_workbench",
    )
    cn_workbench_rule_version_count = fields.Integer(
        string="China Rule Versions",
        compute="_compute_cn_workbench",
    )
    cn_workbench_active_rule_version_count = fields.Integer(
        string="Active China Rule Versions",
        compute="_compute_cn_workbench",
    )
    cn_workbench_rule_governance_issue_count = fields.Integer(
        string="Rule Governance Issues",
        compute="_compute_cn_workbench",
    )
    cn_workbench_rule_pending_professional_count = fields.Integer(
        string="Rules Pending Professional Sign-off",
        compute="_compute_cn_workbench",
    )
    cn_workbench_source_review_overdue_count = fields.Integer(
        string="Official Sources Review Overdue",
        compute="_compute_cn_workbench",
    )
    cn_workbench_source_monitor_issue_count = fields.Integer(
        string="Official Source Monitor Issues",
        compute="_compute_cn_workbench",
    )
    cn_workbench_limitation_count = fields.Integer(
        string="范围/证据限制",
        compute="_compute_cn_workbench",
    )
    cn_workbench_scan_state = fields.Selection(
        FLOW_STATES,
        string="扫描状态",
        compute="_compute_cn_workbench",
    )
    cn_workbench_risk_state = fields.Selection(
        FLOW_STATES,
        string="风险状态",
        compute="_compute_cn_workbench",
    )
    cn_workbench_remediation_state = fields.Selection(
        FLOW_STATES,
        string="整改状态",
        compute="_compute_cn_workbench",
    )
    cn_workbench_rescan_state = fields.Selection(
        FLOW_STATES,
        string="Verification Rescan State",
        compute="_compute_cn_workbench",
    )
    cn_workbench_pending_rescan_count = fields.Integer(
        string="Pending Verification Rescans",
        compute="_compute_cn_workbench",
    )
    cn_workbench_failed_rescan_count = fields.Integer(
        string="Failed Verification Rescans",
        compute="_compute_cn_workbench",
    )
    cn_workbench_verified_remediation_count = fields.Integer(
        string="Verified Remediations",
        compute="_compute_cn_workbench",
    )
    cn_workbench_rescan_next_action = fields.Char(
        string="Verification Rescan Next Action",
        compute="_compute_cn_workbench",
    )
    cn_workbench_report_state = fields.Selection(
        FLOW_STATES,
        string="报告状态",
        compute="_compute_cn_workbench",
    )
    cn_workbench_evidence_state = fields.Selection(
        FLOW_STATES,
        string="证据状态",
        compute="_compute_cn_workbench",
    )
    cn_workbench_evidence_count = fields.Integer(
        string="证据记录",
        compute="_compute_cn_workbench",
    )
    cn_workbench_verified_evidence_count = fields.Integer(
        string="已验证证据",
        compute="_compute_cn_workbench",
    )

    cn_workbench_filing_archive_state = fields.Selection(
        FLOW_STATES,
        string="Filing Archive State",
        compute="_compute_cn_workbench",
    )
    cn_workbench_filing_archive_next_action = fields.Char(
        string="Filing Archive Next Action",
        compute="_compute_cn_workbench",
    )
    cn_workbench_filing_archive_count = fields.Integer(
        string="Controlled Filing Archives",
        compute="_compute_cn_workbench",
    )
    cn_workbench_sealed_filing_archive_count = fields.Integer(
        string="Sealed Filing Archives",
        compute="_compute_cn_workbench",
    )
    cn_workbench_filing_archive_issue_count = fields.Integer(
        string="Filing Archive Issues",
        compute="_compute_cn_workbench",
    )
    cn_workbench_ai_guidance_state = fields.Selection(
        FLOW_STATES,
        string="AI Guidance State",
        compute="_compute_cn_workbench",
    )
    cn_workbench_ai_guidance_next_action = fields.Char(
        string="AI Guidance Next Action",
        compute="_compute_cn_workbench",
    )
    cn_workbench_ai_guidance_finding_count = fields.Integer(
        string="AI Guidance Findings",
        compute="_compute_cn_workbench",
    )
    cn_workbench_ai_guidance_generated_count = fields.Integer(
        string="Generated AI Guidance",
        compute="_compute_cn_workbench",
    )
    cn_workbench_ai_guidance_current_count = fields.Integer(
        string="Current AI Guidance",
        compute="_compute_cn_workbench",
    )
    cn_workbench_ai_guidance_limited_count = fields.Integer(
        string="Limited AI Guidance Inputs",
        compute="_compute_cn_workbench",
    )
    cn_workbench_ai_guidance_stale_count = fields.Integer(
        string="Stale AI Guidance Inputs",
        compute="_compute_cn_workbench",
    )
    cn_workbench_closed_loop_state = fields.Selection(
        FLOW_STATES,
        string="Closed Loop Readiness",
        compute="_compute_cn_workbench",
    )
    cn_workbench_closed_loop_gap_count = fields.Integer(
        string="Closed Loop Gaps",
        compute="_compute_cn_workbench",
    )
    cn_workbench_closed_loop_summary = fields.Char(
        string="Closed Loop Summary",
        compute="_compute_cn_workbench",
    )
    cn_workbench_conclusion_boundary_state = fields.Selection(
        FLOW_STATES,
        string="Conclusion Boundary",
        compute="_compute_cn_workbench",
    )
    cn_workbench_conclusion_boundary_summary = fields.Char(
        string="Conclusion Boundary Summary",
        compute="_compute_cn_workbench",
    )
    cn_workbench_conclusion_boundary_next_action = fields.Char(
        string="Conclusion Boundary Next Action",
        compute="_compute_cn_workbench",
    )
    cn_workbench_next_best_action_key = fields.Selection(
        NEXT_STEP_KEYS,
        string="Next Best Action Target",
        compute="_compute_cn_workbench",
    )
    cn_workbench_next_best_action_label = fields.Char(
        string="Next Best Action",
        compute="_compute_cn_workbench",
    )

    def _cn_workbench_action_summary(self):
        self.ensure_one()
        parts = []
        next_action = (
            self.cn_workbench_next_best_action_label or self.cn_workbench_next_action
        )
        if next_action:
            parts.append("Next: %s" % next_action)
        if self.cn_workbench_conclusion_boundary_summary:
            parts.append(
                "Conclusion: %s" % self.cn_workbench_conclusion_boundary_summary
            )
        if self.cn_workbench_closed_loop_summary:
            parts.append(
                "Closed loop: %s (%s gaps) - %s"
                % (
                    self.cn_workbench_closed_loop_state or "unknown",
                    self.cn_workbench_closed_loop_gap_count or 0,
                    self.cn_workbench_closed_loop_summary,
                )
            )
        parts.extend(
            [
                "Risks: %s high / %s total; %s pending review"
                % (
                    self.cn_workbench_high_risk_count or 0,
                    self.cn_workbench_finding_count or 0,
                    self.cn_workbench_pending_review_count or 0,
                ),
                "Tasks: %s open / %s overdue"
                % (
                    self.cn_workbench_open_task_count or 0,
                    self.cn_workbench_overdue_task_count or 0,
                ),
                "Data: %s/%s controlled datasets ready"
                % (
                    self.cn_workbench_ready_dataset_count or 0,
                    self.cn_workbench_dataset_count or 0,
                ),
                "Report: %s; Evidence: %s; Filing: %s; AI: %s"
                % (
                    self.cn_workbench_report_state or "unknown",
                    self.cn_workbench_evidence_state or "unknown",
                    self.cn_workbench_filing_archive_state or "unknown",
                    self.cn_workbench_ai_guidance_state or "unknown",
                ),
                "Rule basis: %s - %s"
                % (
                    self.cn_workbench_rule_basis_state or "unknown",
                    self.cn_workbench_rule_basis_summary or "no summary",
                ),
            ]
        )
        return " | ".join(parts)

    def _compute_cn_workbench(self):
        today = fields.Date.context_today(self)
        Assessment = self.env["sudo.compliance.assessment"].sudo()
        Finding = self.env["sudo.compliance.finding"].sudo()
        Task = self.env["sudo.compliance.task"].sudo()
        ImpactCase = self.env["sudo.cn.tax.impact.case"].sudo()
        Report = self.env["sudo.cn.compliance.report"].sudo()
        Evidence = self.env["sudo.compliance.evidence"].sudo()
        Classification = self.env["sudo.cn.taxpayer.classification"].sudo()
        CrossBorder = self.env["sudo.cn.cross.border.transaction"].sudo()
        Obligation = self.env["sudo.compliance.obligation"].sudo()
        Filing = self.env["sudo.compliance.filing"].sudo()
        Dataset = self.env["sudo.cn.external.dataset"].sudo()
        Move = self.env["account.move"].sudo()
        RuleVersion = self.env["sudo.compliance.rule.version"].sudo()
        Source = self.env["sudo.compliance.authority.source"].sudo()

        issue_models = (
            "sudo.cn.vat.period.reconciliation.issue",
            "sudo.cn.cit.period.reconciliation.issue",
            "sudo.cn.iit.period.reconciliation.issue",
        )

        for profile in self:
            latest_assessment = Assessment.search(
                [("profile_id", "=", profile.id)],
                order="period_end desc, create_date desc, id desc",
                limit=1,
            )
            latest_report = Report.search(
                [("profile_id", "=", profile.id), ("state", "!=", "withdrawn")],
                order="issued_at desc, create_date desc, id desc",
                limit=1,
            )
            current_classification = Classification._for_profile_date(
                profile, today
            )[:1]
            finding_domain = [("assessment_id.profile_id", "=", profile.id)]
            current_finding_domain = list(finding_domain)
            historical_finding_domain = list(finding_domain)
            if latest_assessment:
                current_finding_domain.append(("assessment_id", "=", latest_assessment.id))
                historical_finding_domain.append(("assessment_id", "!=", latest_assessment.id))
            review_finding_domain = current_finding_domain + [
                "|",
                ("review_state", "in", REVIEW_FINDING_STATES),
                ("result", "in", ("fail", "unknown", "error")),
            ]
            historical_review_finding_domain = historical_finding_domain + [
                "|",
                ("review_state", "in", REVIEW_FINDING_STATES),
                ("result", "in", ("fail", "unknown", "error")),
            ]
            ai_guidance_domain = current_finding_domain + [
                ("result", "in", ("fail", "unknown", "error")),
            ]
            task_domain = [
                ("assessment_id.profile_id", "=", profile.id),
                ("state", "in", OPEN_TASK_STATES),
            ]
            historical_task_domain = [
                ("assessment_id.profile_id", "=", profile.id),
                ("state", "in", OPEN_TASK_STATES),
            ]
            if latest_assessment:
                task_domain.append(("assessment_id", "=", latest_assessment.id))
                historical_task_domain.append(("assessment_id", "!=", latest_assessment.id))
            impact_domain = [
                ("profile_id", "=", profile.id),
                ("state", "!=", "cancelled"),
            ]
            reviewed_impact_domain = impact_domain + [
                ("state", "=", "reviewed"),
                ("quantification_state", "=", "reviewed"),
                ("impact_direction", "=", "potential_underpayment"),
            ]
            cross_border_domain = [("profile_id", "=", profile.id)]
            cross_border_pending_domain = cross_border_domain + [
                ("state", "in", ("draft", "submitted")),
            ]
            obligations = Obligation.search([("profile_id", "=", profile.id)])
            applicable_obligations = obligations.filtered(
                lambda obligation: obligation.applicability == "applicable"
            )
            pending_obligations = obligations.filtered(
                lambda obligation: obligation.applicability == "unknown"
                or (
                    obligation.applicability == "applicable"
                    and not obligation.authority_source_id
                )
            )
            filing_obligations = applicable_obligations.filtered(
                lambda obligation: obligation.filing_required
            )

            issue_counts = {}
            for model_name in issue_models:
                if model_name in self.env.registry.models:
                    issue_counts[model_name] = self.env[model_name].sudo().search_count(
                        [("profile_id", "=", profile.id)]
                    )
                else:
                    issue_counts[model_name] = 0
            reconciliation_issue_count = sum(issue_counts.values())

            limitation_count = 0
            if latest_assessment and "cn_jurisdiction_coverage_state" in latest_assessment._fields:
                if latest_assessment.cn_jurisdiction_coverage_state in (
                    "missing_assignment",
                    "integrity_error",
                    "limited",
                ):
                    limitation_count += 1
            if latest_report and latest_report.conclusion_state in (
                "limited",
                "limited_action_required",
            ):
                limitation_count += 1
            evidence_domain = [
                ("company_id", "=", profile.company_id.id),
                "|",
                "|",
                "|",
                ("assessment_id.profile_id", "=", profile.id),
                ("finding_id.assessment_id.profile_id", "=", profile.id),
                ("task_id.assessment_id.profile_id", "=", profile.id),
                ("filing_id.profile_id", "=", profile.id),
            ]
            evidence_count = Evidence.search_count(evidence_domain)
            verified_evidence_count = Evidence.search_count(
                evidence_domain + [("state", "=", "verified")]
            )
            filing_archives = Filing.search(_controlled_filing_domain(profile))
            sealed_filing_archives = filing_archives.filtered(
                lambda filing: filing.cn_submission_integrity_state
                in ("verified", "source_superseded")
                and filing.cn_payment_integrity_state
                in ("verified", "not_required", "source_superseded")
                and filing.cn_filing_center_evidence_state == "verified"
            )
            filing_archive_issues = filing_archives.filtered(
                lambda filing: filing.cn_submission_integrity_state
                in ("changed", "invalid", "unsealed")
                or filing.cn_payment_integrity_state
                in ("changed", "invalid", "unsealed")
                or filing.cn_filing_center_evidence_state != "verified"
            )
            datasets = Dataset.search([("profile_id", "=", profile.id)])
            current_datasets = datasets.filtered(
                lambda dataset: dataset.state != "superseded"
            )
            ready_datasets = current_datasets.filtered(
                lambda dataset: dataset.cn_data_readiness_stage == "ready"
            )
            blocked_datasets = current_datasets.filtered(
                lambda dataset: dataset.cn_data_readiness_stage == "blocked"
            )
            move_domain = [("company_id", "=", profile.company_id.id)]
            invoice_domain = move_domain + [
                (
                    "move_type",
                    "in",
                    (
                        "out_invoice",
                        "out_refund",
                        "in_invoice",
                        "in_refund",
                        "out_receipt",
                        "in_receipt",
                    ),
                )
            ]
            if latest_assessment and latest_assessment.period_start:
                move_domain.append(("date", ">=", latest_assessment.period_start))
                invoice_domain.append(("date", ">=", latest_assessment.period_start))
            if latest_assessment and latest_assessment.period_end:
                move_domain.append(("date", "<=", latest_assessment.period_end))
                invoice_domain.append(("date", "<=", latest_assessment.period_end))
            posted_move_count = Move.with_company(profile.company_id).search_count(
                move_domain + [("state", "=", "posted")]
            )
            draft_move_count = Move.with_company(profile.company_id).search_count(
                move_domain + [("state", "=", "draft")]
            )
            posted_invoice_count = Move.with_company(profile.company_id).search_count(
                invoice_domain + [("state", "=", "posted")]
            )

            profile.cn_workbench_last_assessment_id = latest_assessment
            profile.cn_workbench_latest_report_id = latest_report
            profile.cn_workbench_package_label = _("中国财税合规包")
            profile.cn_workbench_scope_label = _(
                "增值税、企业所得税、个人所得税、电子发票、申报缴款、证据与正式报告"
            )
            if latest_assessment and latest_assessment.period_start and latest_assessment.period_end:
                profile.cn_workbench_period_label = _(
                    "%(start)s 至 %(end)s",
                    start=latest_assessment.period_start,
                    end=latest_assessment.period_end,
                )
            else:
                profile.cn_workbench_period_label = _("尚未扫描")

            profile.cn_workbench_finding_count = Finding.search_count(
                review_finding_domain
            )
            profile.cn_workbench_high_risk_count = Finding.search_count(
                review_finding_domain + [("risk_level", "in", HIGH_RISK_LEVELS)]
            )
            profile.cn_workbench_pending_review_count = Finding.search_count(
                current_finding_domain + [("review_state", "in", REVIEW_FINDING_STATES)]
            )
            profile.cn_workbench_historical_unresolved_finding_count = Finding.search_count(
                historical_review_finding_domain
            )
            ai_guidance_findings = Finding.search(ai_guidance_domain)
            ai_guidance_generated = self.env["sudo.compliance.finding"]
            ai_guidance_current = self.env["sudo.compliance.finding"]
            for finding in ai_guidance_findings:
                analyses = finding.ai_analysis_ids.filtered(
                    lambda analysis: analysis.provider_key
                    == "sdoo_cn_controlled_guidance"
                ).sorted("id")
                if not analyses:
                    continue
                ai_guidance_generated |= finding
                latest = analyses[-1:]
                if latest.generated_at and (
                    not finding.write_date
                    or latest.generated_at + timedelta(seconds=5) >= finding.write_date
                ):
                    ai_guidance_current |= finding
            ai_guidance_limited = ai_guidance_findings.filtered(
                lambda finding: finding.source_warning
                or finding.professional_warning
                or bool(finding.missing_fact_keys)
                or bool(finding.missing_parameter_keys)
                or not finding.fact_snapshot_ids
            )
            profile.cn_workbench_ai_guidance_finding_count = len(
                ai_guidance_findings
            )
            profile.cn_workbench_ai_guidance_generated_count = len(
                ai_guidance_generated
            )
            profile.cn_workbench_ai_guidance_current_count = len(
                ai_guidance_current
            )
            profile.cn_workbench_ai_guidance_limited_count = len(
                ai_guidance_limited
            )
            profile.cn_workbench_ai_guidance_stale_count = (
                len(ai_guidance_generated) - len(ai_guidance_current)
            )
            profile.cn_workbench_open_task_count = Task.search_count(task_domain)
            profile.cn_workbench_overdue_task_count = Task.search_count(
                task_domain + [("due_date", "<", today)]
            )
            profile.cn_workbench_historical_blocked_task_count = Task.search_count(
                historical_task_domain + [("state", "=", "blocked")]
            )
            profile.cn_workbench_pending_rescan_count = Task.search_count(
                task_domain + [("verification_state", "=", "pending_rescan")]
            )
            profile.cn_workbench_failed_rescan_count = Task.search_count(
                task_domain + [("verification_state", "=", "failed")]
            )
            profile.cn_workbench_verified_remediation_count = Task.search_count(
                [
                    ("assessment_id.profile_id", "=", profile.id),
                    ("task_type", "=", "remediation"),
                    ("state", "=", "done"),
                    ("verification_state", "=", "verified"),
                ]
            )
            profile.cn_workbench_tax_impact_case_count = ImpactCase.search_count(
                impact_domain
            )
            profile.cn_workbench_pending_tax_impact_count = ImpactCase.search_count(
                impact_domain
                + [
                    "|",
                    ("state", "!=", "reviewed"),
                    ("quantification_state", "in", ("not_assessed", "preliminary")),
                ]
            )
            reviewed_underpayment_cases = ImpactCase.search(
                reviewed_impact_domain
            ).filtered(lambda case: case.integrity_state == "verified")
            profile.cn_workbench_underpayment_amount = sum(
                reviewed_underpayment_cases.mapped("impact_amount")
            )
            profile.cn_workbench_reconciliation_issue_count = reconciliation_issue_count
            profile.cn_workbench_dataset_count = len(current_datasets)
            profile.cn_workbench_ready_dataset_count = len(ready_datasets)
            profile.cn_workbench_posted_move_count = posted_move_count
            profile.cn_workbench_draft_move_count = draft_move_count
            profile.cn_workbench_posted_invoice_count = posted_invoice_count
            if latest_assessment and not posted_move_count:
                profile.cn_workbench_data_state = "blocked"
                profile.cn_workbench_data_next_action = _(
                    "Post Odoo accounting entries for the scanned period before relying on compliance risk results."
                )
            elif not current_datasets:
                profile.cn_workbench_data_state = "not_started"
                profile.cn_workbench_data_next_action = _(
                    "登记电子发票、纳税申报、缴款、工资和银行等受控数据来源后再扫描。"
                )
            elif blocked_datasets:
                profile.cn_workbench_data_state = "blocked"
                profile.cn_workbench_data_next_action = _(
                    "先修复数据集完整性或真实性失败，再运行规则扫描。"
                )
            elif len(ready_datasets) == len(current_datasets):
                profile.cn_workbench_data_state = "ready"
                profile.cn_workbench_data_next_action = _(
                    "受控数据来源已封存并可用于规则扫描；按期间持续更新。"
                )
            else:
                profile.cn_workbench_data_state = "attention"
                profile.cn_workbench_data_next_action = _(
                    "补齐封存、真实性验证和解析/规范化记录后再扫描。"
                )
            profile.cn_workbench_vat_issue_count = issue_counts[
                "sudo.cn.vat.period.reconciliation.issue"
            ]
            profile.cn_workbench_cit_issue_count = issue_counts[
                "sudo.cn.cit.period.reconciliation.issue"
            ]
            profile.cn_workbench_iit_issue_count = issue_counts[
                "sudo.cn.iit.period.reconciliation.issue"
            ]
            profile.cn_workbench_vat_domain_state = _tax_domain_state(
                latest_assessment,
                profile.cn_workbench_vat_issue_count,
                limitation_count,
            )
            profile.cn_workbench_cit_domain_state = _tax_domain_state(
                latest_assessment,
                profile.cn_workbench_cit_issue_count,
                limitation_count,
            )
            profile.cn_workbench_iit_domain_state = _tax_domain_state(
                latest_assessment,
                profile.cn_workbench_iit_issue_count,
                limitation_count,
            )
            profile.cn_workbench_obligation_count = len(obligations)
            profile.cn_workbench_applicable_obligation_count = len(
                applicable_obligations
            )
            profile.cn_workbench_pending_obligation_count = len(pending_obligations)
            profile.cn_workbench_filing_obligation_count = len(filing_obligations)
            if not obligations:
                profile.cn_workbench_obligation_state = "not_started"
                profile.cn_workbench_obligation_next_action = _(
                    "Seed the China candidate obligation list from the compliance profile."
                )
            elif pending_obligations:
                profile.cn_workbench_obligation_state = "attention"
                profile.cn_workbench_obligation_next_action = _(
                    "Review candidate tax obligations, confirm applicability, and link official sources before relying on filing controls."
                )
            else:
                profile.cn_workbench_obligation_state = "ready"
                profile.cn_workbench_obligation_next_action = _(
                    "Obligation applicability has been reviewed; keep sources current and rescan periodically."
                )
            profile.cn_workbench_cross_border_transaction_count = (
                CrossBorder.search_count(cross_border_domain)
            )
            profile.cn_workbench_cross_border_pending_count = (
                CrossBorder.search_count(cross_border_pending_domain)
            )
            rule_versions = RuleVersion.search(
                [
                    ("rule_id.country_id.code", "=", "CN"),
                    ("state", "!=", "retired"),
                ]
            )
            active_rule_versions = rule_versions.filtered(
                lambda version: version.state == "active"
            )
            governance_issue_versions = rule_versions.filtered(
                lambda version: not version.cn_governance_ready
            )
            pending_professional_versions = rule_versions.filtered(
                lambda version: version.professional_review_state != "approved"
                and version.cn_professional_review_ready
            )
            source_review_overdue_count = Source.search_count(
                [
                    ("country_id.code", "=", "CN"),
                    ("status", "=", "valid"),
                    ("next_review_date", "!=", False),
                    ("next_review_date", "<", today),
                ]
            )
            source_monitor_issue_count = Source.search_count(
                [
                    ("country_id.code", "=", "CN"),
                    ("cn_last_monitor_state", "in", ("changed", "failed")),
                ]
            )
            profile.cn_workbench_rule_version_count = len(rule_versions)
            profile.cn_workbench_active_rule_version_count = len(
                active_rule_versions
            )
            profile.cn_workbench_rule_governance_issue_count = len(
                governance_issue_versions
            )
            profile.cn_workbench_rule_pending_professional_count = len(
                pending_professional_versions
            )
            profile.cn_workbench_source_review_overdue_count = (
                source_review_overdue_count
            )
            profile.cn_workbench_source_monitor_issue_count = (
                source_monitor_issue_count
            )
            if not rule_versions:
                profile.cn_workbench_rule_basis_state = "not_started"
                profile.cn_workbench_rule_basis_summary = (
                    "No China rule versions are installed or governed yet."
                )
                profile.cn_workbench_rule_basis_next_action = (
                    "Install or seed China rule versions before relying on rule scans."
                )
            elif source_monitor_issue_count or source_review_overdue_count:
                profile.cn_workbench_rule_basis_state = "blocked"
                profile.cn_workbench_rule_basis_summary = (
                    "%s China rule versions, %s active; %s official sources overdue; %s source monitor issues."
                    % (
                        len(rule_versions),
                        len(active_rule_versions),
                        source_review_overdue_count,
                        source_monitor_issue_count,
                    )
                )
                profile.cn_workbench_rule_basis_next_action = (
                    "Review overdue or changed official sources, update affected rule versions, and rerun scans."
                )
            elif governance_issue_versions or pending_professional_versions:
                profile.cn_workbench_rule_basis_state = "attention"
                profile.cn_workbench_rule_basis_summary = (
                    "%s China rule versions, %s active; %s governance gaps; %s pending professional sign-off."
                    % (
                        len(rule_versions),
                        len(active_rule_versions),
                        len(governance_issue_versions),
                        len(pending_professional_versions),
                    )
                )
                profile.cn_workbench_rule_basis_next_action = (
                    "Complete source governance, review packets, tests and China tax professional sign-off for rule gaps."
                )
            else:
                profile.cn_workbench_rule_basis_state = "ready"
                profile.cn_workbench_rule_basis_summary = (
                    "%s China rule versions, %s active; sources and professional sign-off gates are current."
                    % (len(rule_versions), len(active_rule_versions))
                )
                profile.cn_workbench_rule_basis_next_action = (
                    "Keep official source monitoring current and rescan when rules or data change."
                )
            cross_border_state = _cross_border_state(
                current_classification,
                limitation_count,
            )
            if profile.cn_workbench_cross_border_pending_count:
                cross_border_state = "attention"
            profile.cn_workbench_cross_border_state = cross_border_state
            if not current_classification:
                profile.cn_workbench_cross_border_basis = _("尚无当前有效纳税人身份快照")
            elif current_classification._current_integrity_state() != "verified":
                profile.cn_workbench_cross_border_basis = _("当前身份快照未核验或完整性异常")
            else:
                profile.cn_workbench_cross_border_basis = _(
                    "企业所得税身份：%(cit)s；征收方式：%(method)s；个税扣缴：%(pit)s",
                    cit=current_classification.cit_taxpayer_status,
                    method=current_classification.cit_collection_method,
                    pit=current_classification.pit_withholding_status,
                )
            if profile.status != "active":
                profile.cn_workbench_vat_next_action = _("先启用中国合规档案。")
                profile.cn_workbench_cit_next_action = _("先启用中国合规档案。")
                profile.cn_workbench_iit_next_action = _("先启用中国合规档案。")
            elif not latest_assessment:
                profile.cn_workbench_vat_next_action = _("运行规则扫描，形成增值税账票申报勾稽结论。")
                profile.cn_workbench_cit_next_action = _("运行规则扫描，形成企业所得税账税申报勾稽结论。")
                profile.cn_workbench_iit_next_action = _("运行规则扫描，形成个人所得税工资账表款勾稽结论。")
            elif limitation_count:
                profile.cn_workbench_vat_next_action = _("先解除适用地区、证据或报告范围限制。")
                profile.cn_workbench_cit_next_action = _("先解除适用地区、证据或报告范围限制。")
                profile.cn_workbench_iit_next_action = _("先解除适用地区、证据或报告范围限制。")
            else:
                profile.cn_workbench_vat_next_action = (
                    _("复核增值税勾稽问题并补齐申报缴款证据。")
                    if profile.cn_workbench_vat_issue_count
                    else _("保持增值税账票申报勾稽定期扫描。")
                )
                profile.cn_workbench_cit_next_action = (
                    _("复核企业所得税账税差异并完成影响量化。")
                    if profile.cn_workbench_cit_issue_count
                    else _("保持企业所得税账税申报勾稽定期扫描。")
                )
                profile.cn_workbench_iit_next_action = (
                    _("复核个人所得税工资账表款差异并推进整改。")
                    if profile.cn_workbench_iit_issue_count
                    else _("保持个人所得税扣缴数据定期扫描。")
                )
            if profile.status != "active":
                profile.cn_workbench_cross_border_next_action = _(
                    "先启用中国合规档案，再维护纳税人身份和跨境交易资料。"
                )
            elif not latest_assessment:
                profile.cn_workbench_cross_border_next_action = _(
                    "先完成身份快照核验；如存在非居民、源泉扣缴或跨境交易，补充受控资料。"
                )
            elif limitation_count:
                profile.cn_workbench_cross_border_next_action = _(
                    "先解除适用地区、证据或报告范围限制，再判断跨境事项。"
                )
            elif profile.cn_workbench_cross_border_state == "attention":
                profile.cn_workbench_cross_border_next_action = _(
                    "复核非居民、源泉扣缴、个税扣缴和跨境交易合同/付款/备案资料。"
                )
            elif profile.cn_workbench_cross_border_state == "blocked":
                profile.cn_workbench_cross_border_next_action = _(
                    "先修复纳税人身份快照或证据完整性。"
                )
            else:
                profile.cn_workbench_cross_border_next_action = _(
                    "当前身份快照未提示非居民或源泉扣缴特征；跨境交易仍需按实际发生单独留痕。"
                )
            profile.cn_workbench_limitation_count = limitation_count
            profile.cn_workbench_evidence_count = evidence_count
            profile.cn_workbench_verified_evidence_count = verified_evidence_count
            profile.cn_workbench_filing_archive_count = len(filing_archives)
            profile.cn_workbench_sealed_filing_archive_count = len(
                sealed_filing_archives
            )
            profile.cn_workbench_filing_archive_issue_count = len(
                filing_archive_issues
            )

            if not latest_assessment:
                profile.cn_workbench_scan_state = "not_started"
            elif latest_assessment.state == "completed":
                profile.cn_workbench_scan_state = "ready"
            else:
                profile.cn_workbench_scan_state = "attention"

            if not ai_guidance_findings:
                profile.cn_workbench_ai_guidance_state = "not_started"
                profile.cn_workbench_ai_guidance_next_action = _(
                    "No unresolved China risk currently requires controlled AI guidance."
                )
            elif profile.cn_workbench_ai_guidance_stale_count:
                profile.cn_workbench_ai_guidance_state = "blocked"
                profile.cn_workbench_ai_guidance_next_action = _(
                    "Regenerate controlled AI guidance for risks whose input facts or remediation state changed."
                )
            elif len(ai_guidance_current) == len(ai_guidance_findings):
                profile.cn_workbench_ai_guidance_state = "ready"
                profile.cn_workbench_ai_guidance_next_action = _(
                    "Controlled AI guidance is current for all unresolved China risks."
                )
            elif ai_guidance_generated:
                profile.cn_workbench_ai_guidance_state = "attention"
                profile.cn_workbench_ai_guidance_next_action = _(
                    "Generate controlled AI guidance for remaining unresolved risks and disclose limited inputs."
                )
            else:
                profile.cn_workbench_ai_guidance_state = "attention"
                profile.cn_workbench_ai_guidance_next_action = _(
                    "Generate controlled AI guidance before using the report as a step-by-step remediation playbook."
                )

            if limitation_count:
                profile.cn_workbench_risk_state = "blocked"
            elif profile.cn_workbench_high_risk_count or profile.cn_workbench_finding_count:
                profile.cn_workbench_risk_state = "attention"
            elif latest_assessment:
                profile.cn_workbench_risk_state = "ready"
            else:
                profile.cn_workbench_risk_state = "not_started"

            if limitation_count:
                profile.cn_workbench_remediation_state = "blocked"
            elif profile.cn_workbench_open_task_count or profile.cn_workbench_overdue_task_count:
                profile.cn_workbench_remediation_state = "attention"
            elif latest_assessment:
                profile.cn_workbench_remediation_state = "ready"
            else:
                profile.cn_workbench_remediation_state = "not_started"

            if limitation_count:
                profile.cn_workbench_rescan_state = "blocked"
                profile.cn_workbench_rescan_next_action = _(
                    "Resolve scope, data or evidence limitations before treating remediation rescans as conclusive."
                )
            elif profile.cn_workbench_failed_rescan_count:
                profile.cn_workbench_rescan_state = "blocked"
                profile.cn_workbench_rescan_next_action = _(
                    "Review failed verification rescans, reopen remediation where needed, and rerun the exact-period scan."
                )
            elif profile.cn_workbench_pending_rescan_count:
                profile.cn_workbench_rescan_state = "attention"
                profile.cn_workbench_rescan_next_action = _(
                    "Monitor pending verification rescans and attach the resulting assessment to the remediation evidence trail."
                )
            elif profile.cn_workbench_verified_remediation_count:
                profile.cn_workbench_rescan_state = "ready"
                profile.cn_workbench_rescan_next_action = _(
                    "Verified remediation is available for report sign-off; keep evidence and rescan records sealed."
                )
            elif profile.cn_workbench_open_task_count:
                profile.cn_workbench_rescan_state = "attention"
                profile.cn_workbench_rescan_next_action = _(
                    "Complete remediation tasks, request review, then queue verification rescans."
                )
            else:
                profile.cn_workbench_rescan_state = "not_started"
                profile.cn_workbench_rescan_next_action = _(
                    "No remediation rescan has been required yet; run scans and close any confirmed risks through the remediation workflow."
                )

            if latest_report and latest_report.state == "issued":
                profile.cn_workbench_report_state = "ready"
            elif latest_report or latest_assessment:
                profile.cn_workbench_report_state = "attention"
            else:
                profile.cn_workbench_report_state = "not_started"

            if evidence_count and evidence_count == verified_evidence_count:
                profile.cn_workbench_evidence_state = "ready"
            elif evidence_count:
                profile.cn_workbench_evidence_state = "attention"
            else:
                profile.cn_workbench_evidence_state = "not_started"

            if not filing_archives:
                profile.cn_workbench_filing_archive_state = "not_started"
                profile.cn_workbench_filing_archive_next_action = _(
                    "Create controlled filing/payment archives from VAT, CIT and IIT reconciliation runs."
                )
            elif filing_archive_issues:
                profile.cn_workbench_filing_archive_state = "attention"
                profile.cn_workbench_filing_archive_next_action = _(
                    "Review filing/payment archive integrity and verified evidence before relying on filings."
                )
            elif len(sealed_filing_archives) == len(filing_archives):
                profile.cn_workbench_filing_archive_state = "ready"
                profile.cn_workbench_filing_archive_next_action = _(
                    "Controlled filing/payment archive chain is sealed; keep receipts and payment evidence current."
                )
            else:
                profile.cn_workbench_filing_archive_state = "attention"
                profile.cn_workbench_filing_archive_next_action = _(
                    "Seal submission and payment evidence for all controlled filing archives."
                )

            if profile.country_id.code != "CN":
                profile.cn_workbench_status = False
                profile.cn_workbench_next_action = False
                profile.cn_workbench_action_summary = False
                profile.cn_workbench_rule_basis_state = False
                profile.cn_workbench_rule_basis_summary = False
                profile.cn_workbench_rule_basis_next_action = False
                profile.cn_workbench_rule_version_count = 0
                profile.cn_workbench_active_rule_version_count = 0
                profile.cn_workbench_rule_governance_issue_count = 0
                profile.cn_workbench_rule_pending_professional_count = 0
                profile.cn_workbench_source_review_overdue_count = 0
                profile.cn_workbench_source_monitor_issue_count = 0
            elif profile.status != "active":
                profile.cn_workbench_status = "setup_required"
                profile.cn_workbench_next_action = _("先完善并启用中国合规档案")
            elif profile.cn_workbench_rule_basis_state == "blocked":
                profile.cn_workbench_status = "limited"
                profile.cn_workbench_next_action = _(
                    "Review official source freshness and rule governance before relying on China compliance conclusions."
                )
            elif profile.cn_workbench_obligation_state == "attention":
                profile.cn_workbench_status = "warning"
                profile.cn_workbench_next_action = _(
                    "Confirm China tax obligation applicability before treating scan results as complete."
                )
            elif limitation_count:
                profile.cn_workbench_status = "limited"
                profile.cn_workbench_next_action = _("补齐适用地区、证据和报告限制说明")
            elif profile.cn_workbench_high_risk_count or profile.cn_workbench_overdue_task_count:
                profile.cn_workbench_status = "action_required"
                profile.cn_workbench_next_action = _("优先处理高风险和逾期整改")
            elif (
                profile.cn_workbench_finding_count
                or profile.cn_workbench_open_task_count
                or profile.cn_workbench_pending_tax_impact_count
                or profile.cn_workbench_filing_archive_issue_count
                or reconciliation_issue_count
            ):
                profile.cn_workbench_status = "warning"
                profile.cn_workbench_next_action = _("复核风险、量化税务影响并推进整改")
            else:
                profile.cn_workbench_status = "healthy"
                profile.cn_workbench_next_action = _("定期扫描并生成正式合规报告")

            (
                profile.cn_workbench_closed_loop_state,
                profile.cn_workbench_closed_loop_gap_count,
                profile.cn_workbench_closed_loop_summary,
            ) = _closed_loop_values(profile)
            if (
                profile.cn_workbench_closed_loop_state == "ready"
                and (
                    profile.cn_workbench_historical_unresolved_finding_count
                    or profile.cn_workbench_historical_blocked_task_count
                )
            ):
                profile.cn_workbench_closed_loop_summary = _(
                    "Current closed loop is ready. Historical unresolved findings: %(findings)s; historical blocked tasks: %(tasks)s.",
                    findings=profile.cn_workbench_historical_unresolved_finding_count,
                    tasks=profile.cn_workbench_historical_blocked_task_count,
                )
            (
                profile.cn_workbench_conclusion_boundary_state,
                profile.cn_workbench_conclusion_boundary_summary,
                profile.cn_workbench_conclusion_boundary_next_action,
            ) = _conclusion_boundary_values(profile)
            (
                profile.cn_workbench_next_best_action_key,
                profile.cn_workbench_next_best_action_label,
            ) = _next_best_action_values(profile)
            if profile.country_id.code == "CN":
                profile.cn_workbench_action_summary = (
                    profile._cn_workbench_action_summary()
                )

    def _cn_action(self, name, res_model, domain, context=None):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": res_model,
            "view_mode": "list,form",
            "domain": domain,
            "context": context or {},
            "target": "current",
        }

    def action_cn_open_workbench_assessments(self):
        self.ensure_one()
        return self._cn_action(
            _("规则扫描"),
            "sudo.compliance.assessment",
            [("profile_id", "=", self.id)],
            {"default_profile_id": self.id},
        )

    def action_cn_open_workbench_taxpayer_classifications(self):
        self.ensure_one()
        return self._cn_action(
            _("中国纳税人身份快照"),
            "sudo.cn.taxpayer.classification",
            [("profile_id", "=", self.id)],
            {"default_profile_id": self.id},
        )

    def action_cn_open_workbench_obligations(self):
        self.ensure_one()
        return self._cn_action(
            _("China Tax Obligations"),
            "sudo.compliance.obligation",
            [("profile_id", "=", self.id)],
            {"default_profile_id": self.id},
        )

    def action_cn_open_workbench_findings(self):
        self.ensure_one()
        domain = [
            ("assessment_id.profile_id", "=", self.id),
            ("result", "in", ("fail", "unknown", "error")),
        ]
        if self.cn_workbench_last_assessment_id:
            domain.append(
                ("assessment_id", "=", self.cn_workbench_last_assessment_id.id)
            )
        action = self.env.ref(
            "sudo_country_pack_cn.action_cn_risk_center",
            raise_if_not_found=False,
        )
        if action:
            result = action.sudo().read()[0]
            result["domain"] = domain
            return result
        return self._cn_action(
            _("风险事项"),
            "sudo.compliance.finding",
            domain,
        )

    def action_cn_open_workbench_ai_guidance_findings(self):
        self.ensure_one()
        action = self.action_cn_open_workbench_findings()
        action["name"] = _("Controlled AI Guidance")
        action["domain"] = [
            ("assessment_id.profile_id", "=", self.id),
            ("result", "in", ("fail", "unknown", "error")),
        ]
        if self.cn_workbench_last_assessment_id:
            action["domain"].append(
                ("assessment_id", "=", self.cn_workbench_last_assessment_id.id)
            )
        return action

    def action_cn_open_workbench_tasks(self):
        self.ensure_one()
        domain = [
            ("assessment_id.profile_id", "=", self.id),
            ("task_type", "=", "remediation"),
        ]
        if self.cn_workbench_last_assessment_id:
            domain.append(
                ("assessment_id", "=", self.cn_workbench_last_assessment_id.id)
            )
        action = self.env.ref(
            "sudo_country_pack_cn.action_cn_remediation_tracker",
            raise_if_not_found=False,
        )
        if action:
            result = action.sudo().read()[0]
            result["domain"] = domain
            return result
        return self._cn_action(
            _("整改任务"),
            "sudo.compliance.task",
            domain,
        )

    def action_cn_open_workbench_tax_impacts(self):
        self.ensure_one()
        action = self.env.ref(
            "sudo_country_pack_cn.action_cn_tax_impact_cases",
            raise_if_not_found=False,
        )
        if action:
            result = action.sudo().read()[0]
            result["domain"] = [("profile_id", "=", self.id)]
            result["context"] = {"default_profile_id": self.id}
            return result
        return self._cn_action(
            _("税务影响事项"),
            "sudo.cn.tax.impact.case",
            [("profile_id", "=", self.id)],
            {"default_profile_id": self.id},
        )

    def action_cn_open_workbench_reports(self):
        self.ensure_one()
        action = self.env.ref(
            "sudo_country_pack_cn.action_cn_formal_compliance_reports",
            raise_if_not_found=False,
        )
        if action:
            result = action.sudo().read()[0]
            result["domain"] = [("profile_id", "=", self.id)]
            result["context"] = {}
            return result
        return self._cn_action(
            _("正式报告"),
            "sudo.cn.compliance.report",
            [("profile_id", "=", self.id)],
        )

    def action_cn_open_workbench_report_readiness(self):
        self.ensure_one()
        action = self.env.ref(
            "sudo_country_pack_cn.action_cn_report_readiness",
            raise_if_not_found=False,
        )
        if action:
            result = action.sudo().read()[0]
            result["domain"] = [("profile_id", "=", self.id)]
            result["context"] = {
                "search_default_cn_assessments": 1,
                "search_default_completed": 1,
            }
            return result
        return self._cn_action(
            _("报告准备度"),
            "sudo.compliance.assessment",
            [("profile_id", "=", self.id)],
            {"search_default_completed": 1},
        )

    def action_cn_open_workbench_vat_issues(self):
        self.ensure_one()
        action = self.env.ref(
            "sudo_country_pack_cn.action_cn_vat_period_reconciliation_issues",
            raise_if_not_found=False,
        )
        if action:
            result = action.sudo().read()[0]
            result["domain"] = [("profile_id", "=", self.id)]
            return result
        return self._cn_action(
            _("增值税勾稽问题"),
            "sudo.cn.vat.period.reconciliation.issue",
            [("profile_id", "=", self.id)],
        )

    def action_cn_open_workbench_cit_issues(self):
        self.ensure_one()
        action = self.env.ref(
            "sudo_country_pack_cn.action_cn_cit_period_reconciliation_issues",
            raise_if_not_found=False,
        )
        if action:
            result = action.sudo().read()[0]
            result["domain"] = [("profile_id", "=", self.id)]
            return result
        return self._cn_action(
            _("企业所得税勾稽问题"),
            "sudo.cn.cit.period.reconciliation.issue",
            [("profile_id", "=", self.id)],
        )

    def action_cn_open_workbench_iit_issues(self):
        self.ensure_one()
        action = self.env.ref(
            "sudo_country_pack_cn.action_cn_iit_period_reconciliation_issues",
            raise_if_not_found=False,
        )
        if action:
            result = action.sudo().read()[0]
            result["domain"] = [("profile_id", "=", self.id)]
            return result
        return self._cn_action(
            _("个税勾稽问题"),
            "sudo.cn.iit.period.reconciliation.issue",
            [("profile_id", "=", self.id)],
        )

    def action_cn_open_workbench_rule_basis(self):
        self.ensure_one()
        return self._cn_action(
            _("China Rule Basis"),
            "sudo.compliance.rule.version",
            [
                ("rule_id.country_id.code", "=", "CN"),
                ("state", "!=", "retired"),
            ],
            {"group_by": "cn_release_state"},
        )

    def action_cn_open_workbench_next_best_action(self):
        self.ensure_one()
        target = self.cn_workbench_next_best_action_key
        if target == "profile":
            return {
                "type": "ir.actions.act_window",
                "name": _("China Compliance Profile"),
                "res_model": self._name,
                "res_id": self.id,
                "view_mode": "form",
                "target": "current",
            }
        if target == "rule_basis":
            return self.action_cn_open_workbench_rule_basis()
        if target == "data_readiness":
            return self.action_cn_open_workbench_data_readiness()
        if target == "obligations":
            return self.action_cn_open_workbench_obligations()
        if target == "scan":
            return self.action_cn_open_workbench_assessments()
        if target == "risks":
            return self.action_cn_open_workbench_findings()
        if target == "remediation":
            return self.action_cn_open_workbench_tasks()
        if target == "evidence":
            return self.action_cn_open_workbench_evidence_center()
        if target == "filing":
            return self.action_cn_open_workbench_filing_center()
        if target == "ai_guidance":
            return self.action_cn_open_workbench_ai_guidance_findings()
        return self.action_cn_open_workbench_report_readiness()
