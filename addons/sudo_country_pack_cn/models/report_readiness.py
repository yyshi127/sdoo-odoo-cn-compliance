from datetime import timedelta

from odoo import _, fields, models
from odoo.osv import expression


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

    cn_report_is_latest_assessment = fields.Boolean(
        string="最新扫描",
        compute="_compute_cn_report_is_latest_assessment",
        search="_search_cn_report_is_latest_assessment",
    )
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
        search="_search_cn_report_readiness_state",
    )
    cn_report_next_action = fields.Char(
        string="报告下一步",
        compute="_compute_cn_report_readiness",
    )
    cn_report_action_summary = fields.Char(
        string="报告行动摘要",
        compute="_compute_cn_report_readiness",
    )
    cn_report_readiness_blocker_summary = fields.Char(
        string="报告阻断事项",
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
            ("not_applicable", "无需整改"),
            ("in_progress", "整改进行中"),
            ("pending_rescan", "等待验证复扫"),
            ("failed", "验证复扫未通过"),
            ("verified", "整改已验证"),
            ("evidence_gap", "证据缺口"),
        ],
        string="报告复扫门禁",
        compute="_compute_cn_report_readiness",
        search="_search_cn_report_rescan_state",
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
            ("not_started", "无受控档案"),
            ("ready", "档案已封存"),
            ("attention", "档案待复核"),
            ("blocked", "档案受阻"),
        ],
        string="申报缴款档案门禁",
        compute="_compute_cn_report_readiness",
        search="_search_cn_report_filing_archive_state",
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
    cn_report_ai_guidance_state = fields.Selection(
        [
            ("not_started", "无需 AI 指引"),
            ("ready", "AI 指引有效"),
            ("attention", "AI 指引待补齐"),
            ("blocked", "AI 指引已过期"),
        ],
        string="报告 AI 指引门禁",
        compute="_compute_cn_report_readiness",
    )
    cn_report_ai_guidance_next_action = fields.Char(
        string="AI Guidance Next Action",
        compute="_compute_cn_report_readiness",
    )
    cn_report_ai_guidance_finding_count = fields.Integer(
        string="AI Guidance Findings",
        compute="_compute_cn_report_readiness",
    )
    cn_report_ai_guidance_generated_count = fields.Integer(
        string="AI Guidance Generated",
        compute="_compute_cn_report_readiness",
    )
    cn_report_ai_guidance_current_count = fields.Integer(
        string="AI Guidance Current",
        compute="_compute_cn_report_readiness",
    )
    cn_report_ai_guidance_limited_count = fields.Integer(
        string="AI Guidance Limited",
        compute="_compute_cn_report_readiness",
    )
    cn_report_ai_guidance_stale_count = fields.Integer(
        string="AI Guidance Stale",
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

    def _compute_cn_report_is_latest_assessment(self):
        latest_by_profile = {}
        Assessment = self.env["sudo.compliance.assessment"]
        for profile in self.mapped("profile_id"):
            latest_by_profile[profile.id] = Assessment.search(
                [("profile_id", "=", profile.id)],
                order="period_end desc, create_date desc, id desc",
                limit=1,
            ).id
        for assessment in self:
            assessment.cn_report_is_latest_assessment = (
                assessment.id == latest_by_profile.get(assessment.profile_id.id)
            )

    def _search_cn_report_is_latest_assessment(self, operator, value):
        if operator in ("=", "!="):
            accepted = {bool(value)}
            if operator == "!=":
                accepted = {True, False} - accepted
        elif operator in ("in", "not in"):
            accepted = {bool(item) for item in (value or [])}
            if operator == "not in":
                accepted = {True, False} - accepted
        else:
            return [("id", "=", 0)]
        if accepted == {True, False}:
            return []
        if not accepted:
            return [("id", "=", 0)]

        profiles = self.env["sudo.compliance.profile"].search(
            [("country_id.code", "=", "CN")]
        )
        Assessment = self.env["sudo.compliance.assessment"]
        latest_assessment_ids = [
            assessment.id
            for profile in profiles
            if (
                assessment := Assessment.search(
                    [("profile_id", "=", profile.id)],
                    order="period_end desc, create_date desc, id desc",
                    limit=1,
                )
            )
        ]
        return [
            (
                "id",
                "in" if True in accepted else "not in",
                latest_assessment_ids,
            )
        ]

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
            ai_guidance_findings = assessment.finding_ids.filtered(
                lambda finding: finding.result in ("fail", "unknown", "error")
            )
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
            ai_guidance_stale_count = len(ai_guidance_generated) - len(
                ai_guidance_current
            )
            ai_guidance_missing_count = len(ai_guidance_findings) - len(
                ai_guidance_generated
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
            if ai_guidance_limited:
                limitation_count += len(ai_guidance_limited)
            if ai_guidance_missing_count:
                limitation_count += ai_guidance_missing_count

            issue_count = (
                review_pending
                + source_or_professional_warnings
                + len(open_tasks)
                + pending_rescan_count
                + failed_rescan_count
                + unverified_done_count
                + ai_guidance_stale_count
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
            assessment.cn_report_ai_guidance_finding_count = len(
                ai_guidance_findings
            )
            assessment.cn_report_ai_guidance_generated_count = len(
                ai_guidance_generated
            )
            assessment.cn_report_ai_guidance_current_count = len(
                ai_guidance_current
            )
            assessment.cn_report_ai_guidance_limited_count = len(
                ai_guidance_limited
            )
            assessment.cn_report_ai_guidance_stale_count = ai_guidance_stale_count
            assessment.cn_report_issue_count = issue_count
            if not ai_guidance_findings:
                assessment.cn_report_ai_guidance_state = "not_started"
                assessment.cn_report_ai_guidance_next_action = _(
                    "No unresolved China risk currently requires controlled AI guidance."
                )
            elif ai_guidance_stale_count:
                assessment.cn_report_ai_guidance_state = "blocked"
                assessment.cn_report_ai_guidance_next_action = _(
                    "Regenerate controlled AI guidance for risks whose input facts, tax impact, or remediation state changed before report reliance."
                )
            elif len(ai_guidance_current) == len(ai_guidance_findings):
                assessment.cn_report_ai_guidance_state = "ready"
                assessment.cn_report_ai_guidance_next_action = _(
                    "Controlled AI guidance is current for every unresolved China risk."
                )
            elif ai_guidance_generated:
                assessment.cn_report_ai_guidance_state = "attention"
                assessment.cn_report_ai_guidance_next_action = _(
                    "Generate controlled AI guidance for remaining unresolved risks and disclose limited inputs in the report."
                )
            else:
                assessment.cn_report_ai_guidance_state = "attention"
                assessment.cn_report_ai_guidance_next_action = _(
                    "Generate controlled AI guidance before using the report as a step-by-step remediation playbook."
                )
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
                assessment.cn_report_action_summary = False
                assessment.cn_report_readiness_blocker_summary = False
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
            elif ai_guidance_stale_count:
                assessment.cn_report_readiness_state = "needs_review"
                assessment.cn_report_next_action = _(
                    "Regenerate stale controlled AI guidance before preparing the formal report."
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
            assessment.cn_report_readiness_blocker_summary = (
                assessment._cn_report_readiness_blocker_summary()
            )
            assessment.cn_report_action_summary = (
                assessment._cn_report_action_summary()
            )

    def _search_cn_report_readiness_value(self, operator, value, allowed, field_name):
        records = self.with_context(lang=self.env.user.lang or "en_US")
        if operator in ("=", "!="):
            values = {value}
        elif operator in ("in", "not in"):
            values = set(value or [])
        else:
            return [("id", "=", 0)]
        values &= allowed
        if not values:
            return [] if operator in ("!=", "not in") else [("id", "=", 0)]
        assessments = records.search([("country_id.code", "=", "CN")])
        matched = assessments.filtered(
            lambda assessment: assessment[field_name] in values
        )
        domain = [("id", "in", matched.ids)]
        if operator in ("!=", "not in"):
            return expression.NOT(domain)
        return domain

    def _search_cn_report_readiness_state(self, operator, value):
        return self._search_cn_report_readiness_value(
            operator,
            value,
            {
                "needs_scan",
                "needs_review",
                "needs_remediation",
                "limited",
                "ready",
                "draft_report",
                "submitted",
                "issued",
            },
            "cn_report_readiness_state",
        )

    def _search_cn_report_rescan_state(self, operator, value):
        return self._search_cn_report_readiness_value(
            operator,
            value,
            {
                "not_applicable",
                "in_progress",
                "pending_rescan",
                "failed",
                "verified",
                "evidence_gap",
            },
            "cn_report_rescan_state",
        )

    def _search_cn_report_filing_archive_state(self, operator, value):
        return self._search_cn_report_readiness_value(
            operator,
            value,
            {"not_started", "ready", "attention", "blocked"},
            "cn_report_filing_archive_state",
        )

    def _cn_report_readiness_blocker_summary(self):
        self.ensure_one()
        blockers = []
        if self.state != "completed":
            blockers.append(_("rule scan not completed"))
        if self.cn_report_readiness_state == "needs_review":
            blockers.append(_("manual review or source sign-off pending"))
        if self.cn_report_open_task_count:
            blockers.append(
                _("%(count)s remediation task(s) still open")
                % {"count": self.cn_report_open_task_count}
            )
        if self.cn_report_failed_rescan_count:
            blockers.append(
                _("%(count)s verification rescan(s) failed")
                % {"count": self.cn_report_failed_rescan_count}
            )
        if self.cn_report_pending_rescan_count:
            blockers.append(
                _("%(count)s verification rescan(s) pending")
                % {"count": self.cn_report_pending_rescan_count}
            )
        if self.cn_report_filing_archive_state == "blocked":
            blockers.append(_("filing/payment archive not audit-ready"))
        if self.cn_report_ai_guidance_state == "blocked":
            blockers.append(_("controlled AI guidance is stale"))
        if self.cn_data_basis_state not in (False, "ready"):
            blockers.append(_("required tax data basis is incomplete"))
        if self.cn_accounting_basis_state not in (False, "ready"):
            blockers.append(_("Odoo accounting basis is incomplete"))
        if self.cn_obligation_basis_state not in (False, "ready"):
            blockers.append(_("tax obligation applicability is not confirmed"))
        if self.cn_report_pending_tax_impact_count:
            blockers.append(
                _("%(count)s tax impact case(s) need quantification")
                % {"count": self.cn_report_pending_tax_impact_count}
            )
        if self.cn_report_limitation_count and not blockers:
            return _("Limited: prepare the report with explicit limitations.")
        if not blockers:
            return _("No blocker: assessment is ready for report preparation.")
        return _("Blocked by: %(blockers)s") % {
            "blockers": "; ".join(dict.fromkeys(blockers))
        }

    def _cn_report_action_summary(self):
        self.ensure_one()
        parts = []
        if self.cn_report_next_action:
            parts.append(_("Next: %(action)s", action=self.cn_report_next_action))
        if self.cn_report_readiness_blocker_summary:
            parts.append(
                _(
                    "Blockers: %(blockers)s",
                    blockers=self.cn_report_readiness_blocker_summary,
                )
            )
        parts.append(
            _(
                "Issues: %(issues)s; Open tasks: %(tasks)s; "
                "Limitations: %(limitations)s",
                issues=self.cn_report_issue_count or 0,
                tasks=self.cn_report_open_task_count or 0,
                limitations=self.cn_report_limitation_count or 0,
            )
        )
        rescan_label = dict(
            self._fields["cn_report_rescan_state"]._description_selection(self.env)
        ).get(self.cn_report_rescan_state, _("Unknown"))
        archive_label = dict(
            self._fields["cn_report_filing_archive_state"]._description_selection(
                self.env
            )
        ).get(self.cn_report_filing_archive_state, _("Unknown"))
        ai_label = dict(
            self._fields["cn_report_ai_guidance_state"]._description_selection(
                self.env
            )
        ).get(self.cn_report_ai_guidance_state, _("Unknown"))
        parts.append(
            _(
                "Rescan: %(rescan)s (%(pending)s pending, %(failed)s failed); "
                "Archive: %(archive)s (%(sealed)s/%(archives)s sealed); "
                "AI: %(ai)s (%(current)s/%(findings)s current); "
                "Can prepare: %(can_prepare)s",
                rescan=rescan_label,
                pending=self.cn_report_pending_rescan_count or 0,
                failed=self.cn_report_failed_rescan_count or 0,
                archive=archive_label,
                sealed=self.cn_report_sealed_filing_archive_count or 0,
                archives=self.cn_report_filing_archive_count or 0,
                ai=ai_label,
                current=self.cn_report_ai_guidance_current_count or 0,
                findings=self.cn_report_ai_guidance_finding_count or 0,
                can_prepare=_("Yes") if self.cn_report_can_prepare else _("No"),
            )
        )
        return " · ".join(parts)

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
