from odoo import _, api, fields, models


class SudoChinaDataReadinessDataset(models.Model):
    _inherit = "sudo.cn.external.dataset"

    cn_data_readiness_stage = fields.Selection(
        [
            ("draft", "待补齐"),
            ("sealed", "已封存"),
            ("ready", "可用于扫描"),
            ("warning", "需复核"),
            ("blocked", "受阻"),
            ("superseded", "已替代"),
        ],
        string="数据准备状态",
        compute="_compute_cn_data_readiness_display",
    )
    cn_data_readiness_period_label = fields.Char(
        string="覆盖期间",
        compute="_compute_cn_data_readiness_display",
    )
    cn_data_readiness_record_count = fields.Integer(
        string="规范化记录",
        compute="_compute_cn_data_readiness_display",
    )
    cn_data_readiness_next_action = fields.Char(
        string="下一步动作",
        compute="_compute_cn_data_readiness_display",
    )

    @api.depends(
        "period_start",
        "period_end",
        "state",
        "integrity_state",
        "authenticity_state",
        "declared_record_count",
        "parse_run_count",
        "normalized_document_count",
        "tax_data_parse_run_count",
        "normalized_vat_filing_count",
        "normalized_cit_filing_count",
        "normalized_iit_withholding_count",
        "normalized_payroll_summary_count",
        "normalized_tax_payment_count",
    )
    def _compute_cn_data_readiness_display(self):
        for dataset in self:
            dataset.cn_data_readiness_period_label = _period_label(
                dataset.period_start,
                dataset.period_end,
            )
            normalized_count = dataset._cn_data_readiness_normalized_count()
            dataset.cn_data_readiness_record_count = normalized_count
            dataset.cn_data_readiness_stage = dataset._cn_data_readiness_stage(
                normalized_count
            )
            dataset.cn_data_readiness_next_action = (
                dataset._cn_data_readiness_next_action(normalized_count)
            )

    def _cn_data_readiness_normalized_count(self):
        self.ensure_one()
        return sum(
            [
                self.normalized_document_count,
                self.normalized_vat_filing_count,
                self.normalized_cit_filing_count,
                self.normalized_iit_withholding_count,
                self.normalized_payroll_summary_count,
                self.normalized_tax_payment_count,
            ]
        )

    def _cn_data_readiness_stage(self, normalized_count):
        self.ensure_one()
        if self.state == "superseded":
            return "superseded"
        if self.integrity_state == "checksum_mismatch":
            return "blocked"
        if self.authenticity_state == "official_tool_failed":
            return "blocked"
        if self.state != "sealed":
            return "draft"
        if self.authenticity_state in ("not_checked", "unavailable"):
            return "warning"
        if not normalized_count and self.dataset_type in _NORMALIZED_DATASET_TYPES:
            return "warning"
        if self.integrity_state == "verified":
            return "ready"
        return "sealed"

    def _cn_data_readiness_next_action(self, normalized_count):
        self.ensure_one()
        if self.state == "superseded":
            return _("该数据集已被新批次替代，仅保留追溯引用。")
        if self.integrity_state == "checksum_mismatch":
            return _("封存后文件或验证证据发生变化，请停止引用并重新采集/封存。")
        if self.authenticity_state == "official_tool_failed":
            return _("真实性验证失败，请复核来源、验证工具结果和失败证据。")
        if self.state != "sealed":
            return _("补齐来源、期间、记录数、附件和授权说明后，由独立复核人封存。")
        if self.authenticity_state in ("not_checked", "unavailable"):
            return _("补充官方工具或受控方法的真实性验证结果；无法验证时记录限制。")
        if self.dataset_type in _NORMALIZED_DATASET_TYPES and not normalized_count:
            return _("执行解析/规范化，确认记录数和异常记录后再进入规则扫描。")
        if self.integrity_state == "verified":
            return _("数据已形成受控链路，可用于对账、风险扫描和报告引用。")
        return _("复核数据完整性和解析结果，确认后进入规则扫描。")


class SudoChinaDataReadinessProfile(models.Model):
    _inherit = "sudo.compliance.profile"

    def action_cn_open_workbench_data_readiness(self):
        self.ensure_one()
        action = self.env.ref(
            "sudo_country_pack_cn.action_cn_data_readiness_center",
            raise_if_not_found=False,
        )
        domain = [("profile_id", "=", self.id)]
        context = {
            "default_profile_id": self.id,
            "search_default_cn_profile_datasets": 1,
            "search_default_group_dataset_type": 1,
        }
        if action:
            result = action.sudo().read()[0]
            result["domain"] = domain
            result["context"] = context
            return result
        return {
            "type": "ir.actions.act_window",
            "name": _("中国数据准备中心"),
            "res_model": "sudo.cn.external.dataset",
            "view_mode": "kanban,list,form",
            "domain": domain,
            "context": context,
            "target": "current",
        }


_NORMALIZED_DATASET_TYPES = {
    "electronic_invoice",
    "vat_filing",
    "cit_filing",
    "iit_withholding",
    "payroll_summary",
    "tax_payment",
}


def _period_label(period_start, period_end):
    if period_start and period_end:
        return _("%(start)s 至 %(end)s", start=period_start, end=period_end)
    return _("未记录期间")
