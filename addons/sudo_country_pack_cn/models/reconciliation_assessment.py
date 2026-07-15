from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


EINVOICE_FACT_PREFIX = "cn.reconciliation.einvoice."
VAT_FACT_PREFIX = "cn.reconciliation.vat."


class SudoChinaReconciliationAssessmentService(models.AbstractModel):
    _inherit = "sudo.compliance.engine"

    @api.model
    def _cn_reconciliation_rule_versions(
        self,
        profile,
        evaluation_date,
        fact_prefixes,
        rule=None,
    ):
        versions = self.env[
            "sudo.compliance.workspace"
        ]._active_rule_versions(profile, evaluation_date)
        if rule:
            versions = versions.filtered(lambda version: version.rule_id == rule)
        prefixes = tuple(fact_prefixes)
        return versions.filtered(
            lambda version: any(
                definition.key.startswith(prefixes)
                for definition in version.required_fact_ids
            )
        )

    @api.model
    def _queue_cn_reconciliation_assessment(
        self,
        profile,
        period_start,
        period_end,
        fact_prefixes,
        note,
        rule=None,
    ):
        profile.ensure_one()
        period_start = fields.Date.to_date(period_start)
        period_end = fields.Date.to_date(period_end)
        if not period_start or not period_end or period_start > period_end:
            raise ValidationError(_("勾稽规则扫描必须具有完整且有效的期间。"))
        if profile.country_id != self.env.ref("base.cn"):
            raise UserError(_("勾稽规则扫描只适用于中国合规档案。"))
        if profile.status != "active":
            raise UserError(_("请先完成并启用中国合规档案。"))

        evaluation_date = fields.Date.context_today(self)
        versions = self._cn_reconciliation_rule_versions(
            profile,
            evaluation_date,
            fact_prefixes,
            rule=rule,
        )
        if not versions:
            raise UserError(
                _(
                    "当前日期没有已经治理、审批、专业签核并生效的勾稽规则；"
                    "草稿规则不会进入正式扫描。"
                )
            )

        running = self.env["sudo.compliance.assessment"].search(
            [
                ("profile_id", "=", profile.id),
                ("state", "in", ("queued", "running")),
            ],
            order="create_date desc, id desc",
            limit=1,
        )
        if running:
            same_scope = (
                running.period_start == period_start
                and running.period_end == period_end
                and set(versions.ids).issubset(running.rule_version_ids.ids)
            )
            if same_scope:
                return running
            raise UserError(_("该合规档案已有其他规则扫描正在排队或执行。"))

        assessment = self.env["sudo.compliance.assessment"].with_company(
            profile.company_id
        ).create(
            {
                "profile_id": profile.id,
                "evaluation_date": evaluation_date,
                "period_start": period_start,
                "period_end": period_end,
                "rule_version_ids": [(6, 0, versions.ids)],
                "note": note,
            }
        )
        assessment.action_queue()
        return assessment

    @api.model
    def _cn_reconciliation_assessment_action(self, assessment):
        assessment.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("合规规则扫描"),
            "res_model": "sudo.compliance.assessment",
            "res_id": assessment.id,
            "view_mode": "form",
            "target": "current",
        }


class SudoChinaEinvoiceReconciliationRun(models.Model):
    _inherit = "sudo.cn.einvoice.reconciliation.run"

    def action_queue_compliance_assessment(self):
        self.ensure_one()
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以发起规则扫描。"))
        if self.state != "succeeded":
            raise UserError(_("只能从当前成功账票勾稽结果发起规则扫描。"))
        engine = self.env["sudo.compliance.engine"].with_company(
            self.company_id
        )
        assessment = engine._queue_cn_reconciliation_assessment(
            self.profile_id,
            self.period_start,
            self.period_end,
            (EINVOICE_FACT_PREFIX,),
            _("从账票勾稽批次 %(run)s 发起的精确期间规则扫描。", run=self.name),
        )
        return engine._cn_reconciliation_assessment_action(assessment)


class SudoChinaVatPeriodReconciliationRun(models.Model):
    _inherit = "sudo.cn.vat.period.reconciliation.run"

    def action_queue_compliance_assessment(self):
        self.ensure_one()
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以发起规则扫描。"))
        if self.state != "succeeded":
            raise UserError(_("只能从当前成功四方勾稽结果发起规则扫描。"))
        engine = self.env["sudo.compliance.engine"].with_company(
            self.company_id
        )
        assessment = engine._queue_cn_reconciliation_assessment(
            self.profile_id,
            self.period_start,
            self.period_end,
            (VAT_FACT_PREFIX,),
            _("从四方勾稽批次 %(run)s 发起的精确期间规则扫描。", run=self.name),
        )
        return engine._cn_reconciliation_assessment_action(assessment)


class SudoComplianceTask(models.Model):
    _inherit = "sudo.compliance.task"

    def _cn_reconciliation_fact_prefixes(self):
        self.ensure_one()
        if not self.finding_id or self.assessment_id.country_id != self.env.ref(
            "base.cn"
        ):
            return ()
        keys = self.finding_id.rule_version_id.required_fact_ids.mapped("key")
        return tuple(
            prefix
            for prefix in (EINVOICE_FACT_PREFIX, VAT_FACT_PREFIX)
            if any(key.startswith(prefix) for key in keys)
        )

    def action_queue_verification_scan(self):
        self.ensure_one()
        fact_prefixes = self._cn_reconciliation_fact_prefixes()
        if not fact_prefixes:
            return super().action_queue_verification_scan()

        self._ensure_action_states({"pending_review"})
        if self.task_type != "remediation" or not self.assessment_id.profile_id:
            raise UserError(_("当前任务不能发起规则复扫。"))
        running = self.env["sudo.compliance.assessment"].search(
            [
                ("profile_id", "=", self.assessment_id.profile_id.id),
                ("state", "in", ("queued", "running")),
            ],
            order="create_date desc, id desc",
            limit=1,
        )
        if running and (
            running.id <= self.assessment_id.id
            or running.create_date < self.review_requested_at
        ):
            raise UserError(
                _("已有早于本次整改提交的扫描正在执行，请等待或取消后重试。")
            )
        engine = self.env["sudo.compliance.engine"].with_company(
            self.company_id
        )
        assessment = engine._queue_cn_reconciliation_assessment(
            self.assessment_id.profile_id,
            self.assessment_id.period_start,
            self.assessment_id.period_end,
            fact_prefixes,
            _(
                "验证整改任务 %(task)s 的精确期间勾稽规则复扫。",
                task=self.name,
            ),
            rule=self.rule_id,
        )
        self._transition_write({"verification_assessment_id": assessment.id})
        self.env["sudo.compliance.audit.event"]._log_records(
            self,
            "task.verification_scan_queued",
            previous_state=self.state,
            new_state=self.state,
            details={
                "assessment_id": assessment.id,
                "period_start": fields.Date.to_string(
                    assessment.period_start
                ),
                "period_end": fields.Date.to_string(assessment.period_end),
                "scope": "cn_reconciliation_exact_period",
            },
        )
        return engine._cn_reconciliation_assessment_action(assessment)
