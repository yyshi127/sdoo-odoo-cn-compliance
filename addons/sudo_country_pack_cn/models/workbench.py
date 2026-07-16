from odoo import _, fields, models


OPEN_TASK_STATES = ("open", "in_progress", "waiting", "pending_review", "blocked")
REVIEW_FINDING_STATES = ("pending", "correction_required")
HIGH_RISK_LEVELS = ("high", "critical")


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
    cn_workbench_limitation_count = fields.Integer(
        string="范围/证据限制",
        compute="_compute_cn_workbench",
    )

    def _compute_cn_workbench(self):
        today = fields.Date.context_today(self)
        Assessment = self.env["sudo.compliance.assessment"].sudo()
        Finding = self.env["sudo.compliance.finding"].sudo()
        Task = self.env["sudo.compliance.task"].sudo()
        ImpactCase = self.env["sudo.cn.tax.impact.case"].sudo()
        Report = self.env["sudo.cn.compliance.report"].sudo()

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

            profile.cn_workbench_last_assessment_id = latest_assessment
            profile.cn_workbench_latest_report_id = latest_report
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
            profile.cn_workbench_limitation_count = limitation_count

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
