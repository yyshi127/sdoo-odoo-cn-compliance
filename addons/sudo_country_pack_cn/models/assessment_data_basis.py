from odoo import _, api, fields, models


class SudoChinaAssessmentDataBasis(models.Model):
    _inherit = "sudo.compliance.assessment"

    cn_data_basis_state = fields.Selection(
        [
            ("no_period", "未设期间"),
            ("missing", "未登记数据"),
            ("blocked", "数据受阻"),
            ("warning", "需复核"),
            ("ready", "数据可用"),
        ],
        string="中国数据基础",
        compute="_compute_cn_data_basis",
    )
    cn_data_basis_dataset_count = fields.Integer(
        string="相关数据集",
        compute="_compute_cn_data_basis",
    )
    cn_data_basis_ready_count = fields.Integer(
        string="可用数据集",
        compute="_compute_cn_data_basis",
    )
    cn_data_basis_warning_count = fields.Integer(
        string="需复核数据集",
        compute="_compute_cn_data_basis",
    )
    cn_data_basis_blocked_count = fields.Integer(
        string="受阻数据集",
        compute="_compute_cn_data_basis",
    )
    cn_data_basis_normalized_record_count = fields.Integer(
        string="规范化记录",
        compute="_compute_cn_data_basis",
    )
    cn_data_basis_next_action = fields.Char(
        string="数据基础下一步",
        compute="_compute_cn_data_basis",
    )

    @api.depends("profile_id", "period_start", "period_end", "country_id")
    def _compute_cn_data_basis(self):
        Dataset = self.env["sudo.cn.external.dataset"].sudo()
        for assessment in self:
            defaults = {
                "cn_data_basis_state": False,
                "cn_data_basis_dataset_count": 0,
                "cn_data_basis_ready_count": 0,
                "cn_data_basis_warning_count": 0,
                "cn_data_basis_blocked_count": 0,
                "cn_data_basis_normalized_record_count": 0,
                "cn_data_basis_next_action": False,
            }
            if assessment.country_id.code != "CN":
                assessment.update(defaults)
                continue
            if not assessment.period_start or not assessment.period_end:
                defaults.update(
                    {
                        "cn_data_basis_state": "no_period",
                        "cn_data_basis_next_action": _(
                            "先为规则评估设置明确的起止期间，再核对数据来源。"
                        ),
                    }
                )
                assessment.update(defaults)
                continue

            datasets = Dataset.search(assessment._cn_data_basis_domain())
            stages = datasets.mapped("cn_data_readiness_stage")
            blocked_count = stages.count("blocked")
            warning_count = len(
                [
                    stage
                    for stage in stages
                    if stage in ("draft", "sealed", "warning", "superseded")
                ]
            )
            ready_count = stages.count("ready")
            normalized_count = sum(
                datasets.mapped("cn_data_readiness_record_count")
            )

            state = "ready"
            next_action = _("数据基础已具备可追溯入口，可继续查看风险和报告准备。")
            if not datasets:
                state = "missing"
                next_action = _("先登记并封存本评估期间相关的电子发票、申报、缴款或工资数据。")
            elif blocked_count:
                state = "blocked"
                next_action = _("先处理受阻数据集，避免基于完整性或真实性异常的数据出具结论。")
            elif warning_count:
                state = "warning"
                next_action = _("复核待补齐、待验证或尚未规范化的数据集，再进入正式报告。")

            assessment.cn_data_basis_state = state
            assessment.cn_data_basis_dataset_count = len(datasets)
            assessment.cn_data_basis_ready_count = ready_count
            assessment.cn_data_basis_warning_count = warning_count
            assessment.cn_data_basis_blocked_count = blocked_count
            assessment.cn_data_basis_normalized_record_count = normalized_count
            assessment.cn_data_basis_next_action = next_action

    def _cn_data_basis_domain(self):
        self.ensure_one()
        domain = [("profile_id", "=", self.profile_id.id)]
        if self.period_start:
            domain.append(("period_end", ">=", self.period_start))
        if self.period_end:
            domain.append(("period_start", "<=", self.period_end))
        return domain

    def action_cn_open_assessment_data_basis(self):
        self.ensure_one()
        action = self.env.ref(
            "sudo_country_pack_cn.action_cn_data_readiness_center",
            raise_if_not_found=False,
        )
        domain = self._cn_data_basis_domain()
        context = {
            "default_profile_id": self.profile_id.id,
            "search_default_group_dataset_type": 1,
        }
        if action:
            result = action.sudo().read()[0]
            result["domain"] = domain
            result["context"] = context
            return result
        return {
            "type": "ir.actions.act_window",
            "name": _("评估数据基础"),
            "res_model": "sudo.cn.external.dataset",
            "view_mode": "kanban,list,form",
            "domain": domain,
            "context": context,
            "target": "current",
        }
