from odoo import _, fields, models


OPEN_TASK_STATES = ("open", "in_progress", "waiting", "pending_review", "blocked")


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
            limitation_count = 0
            if assessment.data_sufficiency_state == "insufficient":
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

            issue_count = (
                review_pending
                + source_or_professional_warnings
                + len(open_tasks)
                + limitation_count
            )

            assessment.cn_report_latest_report_id = latest_report
            assessment.cn_report_open_task_count = len(open_tasks)
            assessment.cn_report_limitation_count = limitation_count
            assessment.cn_report_pending_tax_impact_count = pending_tax_impact
            assessment.cn_report_issue_count = issue_count

            if assessment.country_id.code != "CN":
                assessment.cn_report_readiness_state = False
                assessment.cn_report_next_action = False
                assessment.cn_report_can_prepare = False
                continue
            if latest_report and latest_report.state == "issued":
                assessment.cn_report_readiness_state = "issued"
                assessment.cn_report_next_action = _("查看已签发报告和审计指纹")
                assessment.cn_report_can_prepare = False
            elif latest_report and latest_report.state == "submitted":
                assessment.cn_report_readiness_state = "submitted"
                assessment.cn_report_next_action = _("等待独立批准人审批报告")
                assessment.cn_report_can_prepare = False
            elif latest_report and latest_report.state == "draft":
                assessment.cn_report_readiness_state = "draft_report"
                assessment.cn_report_next_action = _("补齐报告内容并提交独立批准")
                assessment.cn_report_can_prepare = False
            elif assessment.state != "completed":
                assessment.cn_report_readiness_state = "needs_scan"
                assessment.cn_report_next_action = _("先完成规则扫描")
                assessment.cn_report_can_prepare = False
            elif review_pending or source_or_professional_warnings:
                assessment.cn_report_readiness_state = "needs_review"
                assessment.cn_report_next_action = _("先完成人工复核和来源/专业签核复核")
                assessment.cn_report_can_prepare = False
            elif open_tasks:
                assessment.cn_report_readiness_state = "needs_remediation"
                assessment.cn_report_next_action = _("先推进未关闭整改或在报告中说明管理层回应")
                assessment.cn_report_can_prepare = True
            elif limitation_count:
                assessment.cn_report_readiness_state = "limited"
                assessment.cn_report_next_action = _("编制报告时必须披露限制和不确定性")
                assessment.cn_report_can_prepare = True
            else:
                assessment.cn_report_readiness_state = "ready"
                assessment.cn_report_next_action = _("可以编制正式合规报告")
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
