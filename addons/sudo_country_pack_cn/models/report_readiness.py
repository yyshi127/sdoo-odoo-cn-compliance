from odoo import _, fields, models


OPEN_TASK_STATES = ("open", "in_progress", "waiting", "pending_review", "blocked")


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


class SudoChinaReportReadinessAssessment(models.Model):
    _inherit = "sudo.compliance.assessment"

    cn_report_readiness_state = fields.Selection(
        [
            ("needs_scan", "扫描未完成"),
            ("needs_review", "需要复核"),
            ("needs_remediation", "需要整改"),
            ("limited", "存在限制"),
            ("ready", "可以编制报告"),
            ("draft_report", "报告编制中"),
            ("submitted", "报告待批准"),
            ("issued", "报告已签发"),
        ],
        string="中国报告准备度",
        compute="_compute_cn_report_readiness",
    )
    cn_report_next_action = fields.Char(
        string="报告下一步",
        compute="_compute_cn_report_readiness",
    )
    cn_report_issue_count = fields.Integer(
        string="准备度问题",
        compute="_compute_cn_report_readiness",
    )
    cn_report_open_task_count = fields.Integer(
        string="未关闭整改",
        compute="_compute_cn_report_readiness",
    )
    cn_report_limitation_count = fields.Integer(
        string="限制项",
        compute="_compute_cn_report_readiness",
    )
    cn_report_pending_tax_impact_count = fields.Integer(
        string="待量化税务影响",
        compute="_compute_cn_report_readiness",
    )
    cn_report_rescan_state = fields.Selection(
        [
            ("not_applicable", "No remediation"),
            ("in_progress", "Remediation in progress"),
            ("pending_rescan", "Pending verification rescan"),
            ("failed", "Verification failed"),
            ("verified", "Verified remediation"),
            ("evidence_gap", "Evidence gap"),
        ],
        string="Report Rescan Gate",
        compute="_compute_cn_report_readiness",
    )
    cn_report_rescan_next_action = fields.Char(
        string="Rescan Next Action",
        compute="_compute_cn_report_readiness",
    )
    cn_report_pending_rescan_count = fields.Integer(
        string="Pending Rescans",
        compute="_compute_cn_report_readiness",
    )
    cn_report_failed_rescan_count = fields.Integer(
        string="Failed Rescans",
        compute="_compute_cn_report_readiness",
    )
    cn_report_verified_remediation_count = fields.Integer(
        string="Verified Remediations",
        compute="_compute_cn_report_readiness",
    )
    cn_report_filing_archive_state = fields.Selection(
        [
            ("not_started", "No controlled archive"),
            ("ready", "Archive sealed"),
            ("attention", "Archive needs attention"),
            ("blocked", "Archive blocked"),
        ],
        string="Filing Archive Gate",
        compute="_compute_cn_report_readiness",
    )
    cn_report_filing_archive_next_action = fields.Char(
        string="Filing Archive Next Action",
        compute="_compute_cn_report_readiness",
    )
    cn_report_filing_archive_count = fields.Integer(
        string="Controlled Filing Archives",
        compute="_compute_cn_report_readiness",
    )
    cn_report_filing_archive_issue_count = fields.Integer(
        string="Filing Archive Issues",
        compute="_compute_cn_report_readiness",
    )
    cn_report_sealed_filing_archive_count = fields.Integer(
        string="Sealed Filing Archives",
        compute="_compute_cn_report_readiness",
    )
    cn_report_latest_report_id = fields.Many2one(
        "sudo.cn.compliance.report",
        string="最新正式报告",
        compute="_compute_cn_report_readiness",
    )
    cn_report_can_prepare = fields.Boolean(
        string="可编制报告",
        compute="_compute_cn_report_readiness",
    )

    def _compute_cn_report_readiness(self):
        Report = self.env["sudo.cn.compliance.report"].sudo()
        Filing = self.env["sudo.compliance.filing"].sudo()
        for assessment in self:
            reports = getattr(assessment, "cn_formal_report_ids", Report.browse())
            active_reports = reports.filtered(
                lambda report: report.state not in ("withdrawn", "superseded")
            )
            latest_report = active_reports[:1]
            if not latest_report:
                latest_report = Report.search(
                    [
                        ("assessment_id", "=", assessment.id),
                        ("state", "not in", ("withdrawn", "superseded")),
                    ],
                    order="issued_at desc, create_date desc, id desc",
                    limit=1,
                )

            open_tasks = assessment.finding_ids.mapped("task_ids").filtered(
                lambda task: task.state in OPEN_TASK_STATES
            )
            remediation_tasks = assessment.finding_ids.mapped("task_ids").filtered(
                lambda task: task.state != "cancelled"
            )
            pending_rescan_count = len(
                remediation_tasks.filtered(
                    lambda task: task.verification_state == "pending_rescan"
                )
            )
            failed_rescan_count = len(
                remediation_tasks.filtered(
                    lambda task: task.verification_state == "failed"
                )
            )
            verified_remediation_count = len(
                remediation_tasks.filtered(
                    lambda task: task.state == "done"
                    and task.verification_state == "verified"
                )
            )
            unverified_done_count = len(
                remediation_tasks.filtered(
                    lambda task: task.state == "done"
                    and task.verification_state not in ("verified", "not_required")
                )
            )
            review_pending = len(
                assessment.finding_ids.filtered(
                    lambda finding: finding.review_state == "pending"
                )
            )
            source_or_professional_warnings = int(
                bool(
                    assessment.source_warning_count
                    or assessment.professional_warning_count
                )
            )
            pending_tax_impact = getattr(
                assessment, "cn_tax_impact_pending_count", 0
            ) or 0
            unquantifiable_tax_impact = getattr(
                assessment, "cn_tax_impact_unquantifiable_count", 0
            ) or 0
            integrity_tax_impact = getattr(
                assessment, "cn_tax_impact_integrity_issue_count", 0
            ) or 0
            filing_archives = Filing.search(_controlled_filing_domain(assessment))
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
            limitation_count = 0
            if assessment.data_sufficiency_state == "insufficient":
                limitation_count += 1
            if (
                "cn_data_basis_state" in assessment._fields
                and assessment.cn_data_basis_state
                not in (False, "ready")
            ):
                limitation_count += 1
            if (
                "cn_accounting_basis_state" in assessment._fields
                and assessment.cn_accounting_basis_state
                not in (False, "ready")
            ):
                limitation_count += 1
            limitation_count += assessment.unknown_count or 0
            limitation_count += assessment.error_count or 0
            limitation_count += pending_tax_impact
            limitation_count += unquantifiable_tax_impact
            limitation_count += integrity_tax_impact
            if (
                "cn_jurisdiction_coverage_state" in assessment._fields
                and assessment.cn_jurisdiction_coverage_state
                not in (False, "complete")
            ):
                limitation_count += 1
            if filing_archive_issues:
                limitation_count += 1

            issue_count = (
                review_pending
                + source_or_professional_warnings
                + len(open_tasks)
                + pending_rescan_count
                + failed_rescan_count
                + unverified_done_count
                + limitation_count
            )

            assessment.cn_report_latest_report_id = latest_report
            assessment.cn_report_open_task_count = len(open_tasks)
            assessment.cn_report_limitation_count = limitation_count
            assessment.cn_report_pending_tax_impact_count = pending_tax_impact
            assessment.cn_report_pending_rescan_count = pending_rescan_count
            assessment.cn_report_failed_rescan_count = failed_rescan_count
            assessment.cn_report_verified_remediation_count = (
                verified_remediation_count
            )
            assessment.cn_report_filing_archive_count = len(filing_archives)
            assessment.cn_report_filing_archive_issue_count = len(
                filing_archive_issues
            )
            assessment.cn_report_sealed_filing_archive_count = len(
                sealed_filing_archives
            )
            assessment.cn_report_issue_count = issue_count
            if not filing_archives:
                assessment.cn_report_filing_archive_state = "not_started"
                assessment.cn_report_filing_archive_next_action = _(
                    "No controlled filing/payment archive exists for this assessment period."
                )
            elif filing_archive_issues:
                assessment.cn_report_filing_archive_state = "blocked"
                assessment.cn_report_filing_archive_next_action = _(
                    "Seal filing/payment archives and verify receipt/payment evidence before relying on report conclusions."
                )
            elif len(sealed_filing_archives) == len(filing_archives):
                assessment.cn_report_filing_archive_state = "ready"
                assessment.cn_report_filing_archive_next_action = _(
                    "Controlled filing/payment archives are sealed for the report period."
                )
            else:
                assessment.cn_report_filing_archive_state = "attention"
                assessment.cn_report_filing_archive_next_action = _(
                    "Review filing/payment archive evidence before report sign-off."
                )
            if not remediation_tasks:
                assessment.cn_report_rescan_state = "not_applicable"
                assessment.cn_report_rescan_next_action = _(
                    "No remediation tasks require verification rescan."
                )
            elif failed_rescan_count:
                assessment.cn_report_rescan_state = "failed"
                assessment.cn_report_rescan_next_action = _(
                    "Review failed verification rescans, reopen remediation, and rerun the exact-period scan before report preparation."
                )
            elif pending_rescan_count:
                assessment.cn_report_rescan_state = "pending_rescan"
                assessment.cn_report_rescan_next_action = _(
                    "Wait for verification rescans to finish before preparing the formal report."
                )
            elif open_tasks:
                assessment.cn_report_rescan_state = "in_progress"
                assessment.cn_report_rescan_next_action = _(
                    "Close remediation tasks and submit them for verification rescan."
                )
            elif unverified_done_count:
                assessment.cn_report_rescan_state = "evidence_gap"
                assessment.cn_report_rescan_next_action = _(
                    "Verify completed remediation evidence or document the verification basis before report sign-off."
                )
            elif verified_remediation_count == len(remediation_tasks):
                assessment.cn_report_rescan_state = "verified"
                assessment.cn_report_rescan_next_action = _(
                    "All remediation tasks have verified rescan evidence for report reliance."
                )
            else:
                assessment.cn_report_rescan_state = "evidence_gap"
                assessment.cn_report_rescan_next_action = _(
                    "Review remediation verification status before relying on the report."
                )

            if assessment.country_id.code != "CN":
                assessment.cn_report_readiness_state = False
                assessment.cn_report_next_action = False
                assessment.cn_report_can_prepare = False
                continue
            if latest_report and latest_report.state == "issued":
                assessment.cn_report_readiness_state = "issued"
                assessment.cn_report_next_action = _(
                    "Review the issued report and retained audit trail."
                )
                assessment.cn_report_can_prepare = False
            elif latest_report and latest_report.state == "submitted":
                assessment.cn_report_readiness_state = "submitted"
                assessment.cn_report_next_action = _(
                    "Wait for independent report approval."
                )
                assessment.cn_report_can_prepare = False
            elif latest_report and latest_report.state == "draft":
                assessment.cn_report_readiness_state = "draft_report"
                assessment.cn_report_next_action = _(
                    "Complete the draft report and submit it for approval."
                )
                assessment.cn_report_can_prepare = False
            elif assessment.state != "completed":
                assessment.cn_report_readiness_state = "needs_scan"
                assessment.cn_report_next_action = _(
                    "Complete the rule scan before preparing a formal report."
                )
                assessment.cn_report_can_prepare = False
            elif review_pending or source_or_professional_warnings:
                assessment.cn_report_readiness_state = "needs_review"
                assessment.cn_report_next_action = _(
                    "Complete manual review, source review, and professional sign-off checks first."
                )
                assessment.cn_report_can_prepare = False
            elif failed_rescan_count:
                assessment.cn_report_readiness_state = "needs_remediation"
                assessment.cn_report_next_action = _(
                    "Verification rescan failed; complete remediation again before preparing the formal report."
                )
                assessment.cn_report_can_prepare = False
            elif pending_rescan_count:
                assessment.cn_report_readiness_state = "needs_remediation"
                assessment.cn_report_next_action = _(
                    "Verification rescan is pending; wait for the exact-period rescan result before preparing the report."
                )
                assessment.cn_report_can_prepare = False
            elif unverified_done_count:
                assessment.cn_report_readiness_state = "needs_remediation"
                assessment.cn_report_next_action = _(
                    "Completed remediation still needs verified evidence or a documented verification basis."
                )
                assessment.cn_report_can_prepare = False
            elif open_tasks:
                assessment.cn_report_readiness_state = "needs_remediation"
                assessment.cn_report_next_action = _(
                    "Close all remediation tasks before preparing the formal report."
                )
                assessment.cn_report_can_prepare = False
            elif limitation_count:
                assessment.cn_report_readiness_state = "limited"
                assessment.cn_report_next_action = _(
                    "Prepare the report only with explicit limitations and uncertainty disclosure."
                )
                assessment.cn_report_can_prepare = True
            else:
                assessment.cn_report_readiness_state = "ready"
                assessment.cn_report_next_action = _(
                    "The assessment is ready for formal compliance report preparation."
                )
                assessment.cn_report_can_prepare = True

    def action_cn_open_report_readiness_findings(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("报告相关风险事项"),
            "res_model": "sudo.compliance.finding",
            "view_mode": "list,form",
            "domain": [("assessment_id", "=", self.id)],
            "context": {"search_default_actionable": 1},
            "target": "current",
        }

    def action_cn_open_report_readiness_tasks(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("报告相关整改任务"),
            "res_model": "sudo.compliance.task",
            "view_mode": "list,form",
            "domain": [("assessment_id", "=", self.id)],
            "context": {"search_default_open": 1},
            "target": "current",
        }
