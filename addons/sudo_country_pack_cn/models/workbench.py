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
    cn_workbench_open_task_count = fields.Integer(
        string="未完成整改",
        compute="_compute_cn_workbench",
    )
    cn_workbench_overdue_task_count = fields.Integer(
        string="逾期整改",
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
            review_finding_domain = finding_domain + [
                "|",
                ("review_state", "in", REVIEW_FINDING_STATES),
                ("result", "in", ("fail", "unknown", "error")),
            ]
            task_domain = [
                ("assessment_id.profile_id", "=", profile.id),
                ("state", "in", OPEN_TASK_STATES),
            ]
            impact_domain = [
                ("profile_id", "=", profile.id),
                ("state", "!=", "cancelled"),
            ]
            reviewed_impact_domain = impact_domain + [
                ("state", "=", "reviewed"),
                ("integrity_state", "=", "verified"),
                ("quantification_state", "=", "reviewed"),
                ("impact_direction", "=", "potential_underpayment"),
            ]
            cross_border_domain = [("profile_id", "=", profile.id)]
            cross_border_pending_domain = cross_border_domain + [
                ("state", "in", ("draft", "submitted")),
            ]

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
                finding_domain + [("review_state", "in", REVIEW_FINDING_STATES)]
            )
            profile.cn_workbench_open_task_count = Task.search_count(task_domain)
            profile.cn_workbench_overdue_task_count = Task.search_count(
                task_domain + [("due_date", "<", today)]
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
            profile.cn_workbench_underpayment_amount = sum(
                ImpactCase.search(reviewed_impact_domain).mapped("impact_amount")
            )
            profile.cn_workbench_reconciliation_issue_count = reconciliation_issue_count
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
            profile.cn_workbench_cross_border_transaction_count = (
                CrossBorder.search_count(cross_border_domain)
            )
            profile.cn_workbench_cross_border_pending_count = (
                CrossBorder.search_count(cross_border_pending_domain)
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

            if not latest_assessment:
                profile.cn_workbench_scan_state = "not_started"
            elif latest_assessment.state == "completed":
                profile.cn_workbench_scan_state = "ready"
            else:
                profile.cn_workbench_scan_state = "attention"

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

            if profile.country_id.code != "CN":
                profile.cn_workbench_status = False
                profile.cn_workbench_next_action = False
            elif profile.status != "active":
                profile.cn_workbench_status = "setup_required"
                profile.cn_workbench_next_action = _("先完善并启用中国合规档案")
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
                or reconciliation_issue_count
            ):
                profile.cn_workbench_status = "warning"
                profile.cn_workbench_next_action = _("复核风险、量化税务影响并推进整改")
            else:
                profile.cn_workbench_status = "healthy"
                profile.cn_workbench_next_action = _("定期扫描并生成正式合规报告")

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

    def action_cn_open_workbench_findings(self):
        self.ensure_one()
        action = self.env.ref(
            "sudo_country_pack_cn.action_cn_risk_center",
            raise_if_not_found=False,
        )
        if action:
            result = action.sudo().read()[0]
            result["domain"] = [
                ("assessment_id.profile_id", "=", self.id),
                ("result", "in", ("fail", "unknown", "error")),
            ]
            return result
        return self._cn_action(
            _("风险事项"),
            "sudo.compliance.finding",
            [("assessment_id.profile_id", "=", self.id)],
        )

    def action_cn_open_workbench_tasks(self):
        self.ensure_one()
        action = self.env.ref(
            "sudo_country_pack_cn.action_cn_remediation_tracker",
            raise_if_not_found=False,
        )
        if action:
            result = action.sudo().read()[0]
            result["domain"] = [
                ("assessment_id.profile_id", "=", self.id),
                ("task_type", "=", "remediation"),
            ]
            return result
        return self._cn_action(
            _("整改任务"),
            "sudo.compliance.task",
            [("assessment_id.profile_id", "=", self.id)],
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
