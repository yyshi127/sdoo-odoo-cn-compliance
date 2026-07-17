from odoo import _, api, fields, models


_CN_REQUIRED_DATASET_LABELS = {
    "electronic_invoice": "Electronic invoices",
    "vat_filing": "VAT filings",
    "cit_filing": "CIT filings",
    "iit_withholding": "IIT withholding",
    "payroll_summary": "Payroll summaries",
    "tax_payment": "Tax payments",
}

_CN_BASE_REQUIRED_DATASET_TYPES = {
    "electronic_invoice",
    "vat_filing",
    "tax_payment",
}

_CN_OBLIGATION_REQUIRED_DATASET_TYPES = {
    "CN-VAT": {"electronic_invoice", "vat_filing", "tax_payment"},
    "CN-CIT": {"cit_filing", "tax_payment"},
    "CN-IIT-WHT": {"iit_withholding", "payroll_summary", "tax_payment"},
    "CN-SURCHARGE": {"vat_filing", "tax_payment"},
    "CN-STAMP-DUTY": {"tax_payment"},
    "CN-SOCIAL-INSURANCE": {"payroll_summary", "tax_payment"},
}


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
    cn_data_basis_required_type_count = fields.Integer(
        string="Required Data Types",
        compute="_compute_cn_data_basis",
    )
    cn_data_basis_ready_type_count = fields.Integer(
        string="Ready Data Types",
        compute="_compute_cn_data_basis",
    )
    cn_data_basis_missing_type_count = fields.Integer(
        string="Missing Data Types",
        compute="_compute_cn_data_basis",
    )
    cn_data_basis_missing_type_summary = fields.Char(
        string="Missing Data Type Summary",
        compute="_compute_cn_data_basis",
    )
    cn_data_basis_next_action = fields.Char(
        string="数据基础下一步",
        compute="_compute_cn_data_basis",
    )
    cn_obligation_basis_state = fields.Selection(
        [
            ("missing", "No candidate obligations"),
            ("attention", "Needs obligation review"),
            ("ready", "Obligations reviewed"),
        ],
        string="China Obligation Basis",
        compute="_compute_cn_data_basis",
    )
    cn_obligation_basis_candidate_count = fields.Integer(
        string="Candidate Obligations",
        compute="_compute_cn_data_basis",
    )
    cn_obligation_basis_applicable_count = fields.Integer(
        string="Applicable Obligations",
        compute="_compute_cn_data_basis",
    )
    cn_obligation_basis_pending_count = fields.Integer(
        string="Obligations Needing Review",
        compute="_compute_cn_data_basis",
    )
    cn_obligation_basis_filing_count = fields.Integer(
        string="Applicable Filing Obligations",
        compute="_compute_cn_data_basis",
    )
    cn_obligation_basis_next_action = fields.Char(
        string="Obligation Basis Next Action",
        compute="_compute_cn_data_basis",
    )

    @api.depends(
        "profile_id",
        "period_start",
        "period_end",
        "country_id",
        "profile_id.obligation_ids.applicability",
        "profile_id.obligation_ids.authority_source_id",
        "profile_id.obligation_ids.filing_required",
    )
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
                "cn_data_basis_required_type_count": 0,
                "cn_data_basis_ready_type_count": 0,
                "cn_data_basis_missing_type_count": 0,
                "cn_data_basis_missing_type_summary": False,
                "cn_data_basis_next_action": False,
                "cn_obligation_basis_state": False,
                "cn_obligation_basis_candidate_count": 0,
                "cn_obligation_basis_applicable_count": 0,
                "cn_obligation_basis_pending_count": 0,
                "cn_obligation_basis_filing_count": 0,
                "cn_obligation_basis_next_action": False,
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
                assessment._cn_update_obligation_basis_values()
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
            required_types = assessment._cn_required_dataset_types()
            ready_types = set(
                datasets.filtered(
                    lambda dataset: dataset.cn_data_readiness_stage == "ready"
                ).mapped("dataset_type")
            )
            missing_types = required_types - ready_types
            missing_summary = assessment._cn_required_dataset_type_summary(
                missing_types
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

            if state == "missing":
                next_action = _(
                    "Register and seal ready data for this period: %(types)s.",
                    types=missing_summary,
                )
            elif state == "ready" and missing_types:
                state = "warning"
                next_action = _(
                    "Current data is usable but incomplete. Add ready data for: %(types)s.",
                    types=missing_summary,
                )

            assessment.cn_data_basis_state = state
            assessment.cn_data_basis_dataset_count = len(datasets)
            assessment.cn_data_basis_ready_count = ready_count
            assessment.cn_data_basis_warning_count = warning_count
            assessment.cn_data_basis_blocked_count = blocked_count
            assessment.cn_data_basis_normalized_record_count = normalized_count
            assessment.cn_data_basis_required_type_count = len(required_types)
            assessment.cn_data_basis_ready_type_count = len(
                required_types & ready_types
            )
            assessment.cn_data_basis_missing_type_count = len(missing_types)
            assessment.cn_data_basis_missing_type_summary = missing_summary
            assessment.cn_data_basis_next_action = next_action
            assessment._cn_update_obligation_basis_values()

    def _cn_required_dataset_types(self):
        self.ensure_one()
        required = set(_CN_BASE_REQUIRED_DATASET_TYPES)
        for obligation in self.profile_id.obligation_ids:
            if obligation.applicability == "not_applicable":
                continue
            required |= _CN_OBLIGATION_REQUIRED_DATASET_TYPES.get(
                obligation.code,
                set(),
            )
        return required

    def _cn_required_dataset_type_summary(self, dataset_types):
        self.ensure_one()
        labels = [
            _CN_REQUIRED_DATASET_LABELS.get(dataset_type, dataset_type)
            for dataset_type in sorted(dataset_types)
        ]
        return ", ".join(labels)

    def _cn_update_obligation_basis_values(self):
        for assessment in self:
            obligations = assessment.profile_id.obligation_ids
            applicable = obligations.filtered(
                lambda obligation: obligation.applicability == "applicable"
            )
            pending = obligations.filtered(
                lambda obligation: obligation.applicability == "unknown"
                or (
                    obligation.applicability == "applicable"
                    and not obligation.authority_source_id
                )
            )
            filing = applicable.filtered(lambda obligation: obligation.filing_required)
            if not obligations:
                state = "missing"
                next_action = _(
                    "Seed China candidate obligations before treating the assessment perimeter as complete."
                )
            elif pending:
                state = "attention"
                next_action = _(
                    "Confirm obligation applicability and link official sources before relying on scan results as complete."
                )
            else:
                state = "ready"
                next_action = _(
                    "Obligation applicability is reviewed; keep official sources current and rescan when the profile changes."
                )
            assessment.cn_obligation_basis_state = state
            assessment.cn_obligation_basis_candidate_count = len(obligations)
            assessment.cn_obligation_basis_applicable_count = len(applicable)
            assessment.cn_obligation_basis_pending_count = len(pending)
            assessment.cn_obligation_basis_filing_count = len(filing)
            assessment.cn_obligation_basis_next_action = next_action

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

    def action_cn_open_assessment_obligation_basis(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("China obligation basis"),
            "res_model": "sudo.compliance.obligation",
            "view_mode": "list,form",
            "domain": [("profile_id", "=", self.profile_id.id)],
            "context": {
                "default_profile_id": self.profile_id.id,
            },
            "target": "current",
        }
