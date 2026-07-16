from odoo import _, api, fields, models

from .tax_data_normalization import _safe_text, _sha256_json


class SudoChinaPayrollSummaryRecord(models.Model):
    _name = "sudo.cn.payroll.summary.record"
    _description = "China Controlled Aggregate Payroll Summary"
    _inherit = "sudo.cn.tax.normalized.record.mixin"
    _order = "period_end desc, approved_at desc, id desc"
    _source_dataset_type = "payroll_summary"

    name = fields.Char(compute="_compute_name", store=True)
    payroll_frequency = fields.Selection(
        [
            ("monthly", "按月"),
            ("per_cycle", "按薪资批次"),
            ("other", "其他"),
            ("unknown", "未提供"),
        ],
        string="薪资频次",
        required=True,
        readonly=True,
        index=True,
    )
    payroll_status = fields.Selection(
        [
            ("draft", "草稿"),
            ("confirmed", "已确认"),
            ("paid", "已发放"),
            ("cancelled", "已取消"),
            ("unknown", "未提供"),
        ],
        string="薪资状态",
        required=True,
        readonly=True,
        index=True,
    )
    payroll_run_reference = fields.Char(string="薪资批次引用", readonly=True)
    approved_at = fields.Datetime(string="确认时间", readonly=True)

    has_declared_person_count = fields.Boolean(
        string="提供人员数量", readonly=True
    )
    declared_person_count = fields.Integer(string="人员数量", readonly=True)
    has_gross_income_amount = fields.Boolean(
        string="提供收入总额", readonly=True
    )
    gross_income_amount = fields.Monetary(
        string="收入总额",
        currency_field="currency_id",
        readonly=True,
    )
    has_tax_exempt_income_amount = fields.Boolean(
        string="提供免税收入", readonly=True
    )
    tax_exempt_income_amount = fields.Monetary(
        string="免税收入",
        currency_field="currency_id",
        readonly=True,
    )
    has_employee_social_insurance_amount = fields.Boolean(
        string="提供个人社保", readonly=True
    )
    employee_social_insurance_amount = fields.Monetary(
        string="个人承担社会保险费",
        currency_field="currency_id",
        readonly=True,
    )
    has_employee_housing_fund_amount = fields.Boolean(
        string="提供个人公积金", readonly=True
    )
    employee_housing_fund_amount = fields.Monetary(
        string="个人承担住房公积金",
        currency_field="currency_id",
        readonly=True,
    )
    has_other_pre_tax_deduction_amount = fields.Boolean(
        string="提供其他税前扣除", readonly=True
    )
    other_pre_tax_deduction_amount = fields.Monetary(
        string="其他税前扣除",
        currency_field="currency_id",
        readonly=True,
    )
    has_net_pay_amount = fields.Boolean(string="提供实发金额", readonly=True)
    net_pay_amount = fields.Monetary(
        string="实发金额",
        currency_field="currency_id",
        readonly=True,
    )
    has_withheld_iit_amount = fields.Boolean(
        string="提供代扣个人所得税", readonly=True
    )
    withheld_iit_amount = fields.Monetary(
        string="代扣个人所得税",
        currency_field="currency_id",
        readonly=True,
    )

    _source_record_unique = models.Constraint(
        "unique(parse_run_id, source_record_key)",
        "同一导入运行中的工资薪酬汇总源记录键必须唯一。",
    )

    @api.depends("payroll_run_reference", "period_start", "period_end")
    def _compute_name(self):
        for record in self:
            record.name = record.payroll_run_reference or "%s / %s - %s" % (
                _("工资薪酬汇总"),
                fields.Date.to_string(record.period_start) or "-",
                fields.Date.to_string(record.period_end) or "-",
            )

    @api.model
    def _selection_value(self, payload, field_name, mapping, issues, label):
        raw = (_safe_text(payload.get(field_name), 64) or "unknown").lower()
        value = mapping.get(raw)
        if value:
            return value
        issues.append(
            self._issue(
                "UNKNOWN_%s" % field_name.upper(),
                "warning",
                _("%(label)s未识别", label=label),
            )
        )
        return "unknown"

    @api.model
    def _person_count(self, payload, issues):
        value = payload.get("declared_person_count")
        if value in (None, False, ""):
            issues.append(
                self._issue(
                    "MISSING_PAYROLL_PERSON_COUNT",
                    "error",
                    _("缺少工资薪酬人员数量"),
                )
            )
            return False, 0
        if isinstance(value, bool):
            valid = False
        else:
            try:
                integer = int(value)
                valid = str(value).strip() == str(integer) and integer >= 0
            except (TypeError, ValueError):
                valid = False
        if not valid:
            issues.append(
                self._issue(
                    "INVALID_PAYROLL_PERSON_COUNT",
                    "error",
                    _("工资薪酬人员数量必须是非负整数"),
                )
            )
            return False, 0
        return True, integer

    @api.model
    def _prepare_import_values(self, run, payload):
        values, canonical, issues, _currency = self._prepare_common(run, payload)
        frequency = self._selection_value(
            payload,
            "payroll_frequency",
            {
                "monthly": "monthly",
                "per_cycle": "per_cycle",
                "other": "other",
                "unknown": "unknown",
                "按月": "monthly",
                "按薪资批次": "per_cycle",
                "其他": "other",
            },
            issues,
            _("薪资频次"),
        )
        status = self._selection_value(
            payload,
            "payroll_status",
            {
                "draft": "draft",
                "confirmed": "confirmed",
                "paid": "paid",
                "cancelled": "cancelled",
                "unknown": "unknown",
                "草稿": "draft",
                "已确认": "confirmed",
                "已发放": "paid",
                "已取消": "cancelled",
            },
            issues,
            _("薪资状态"),
        )
        payroll_run_reference = _safe_text(
            payload.get("payroll_run_reference"), 256
        )
        approved_at = self._parse_datetime(
            payload.get("approved_at"), _("薪资确认时间"), issues
        )
        has_person_count, person_count = self._person_count(payload, issues)

        amount_fields = (
            ("gross_income_amount", "收入总额", True),
            ("tax_exempt_income_amount", "免税收入", False),
            (
                "employee_social_insurance_amount",
                "个人承担社会保险费",
                False,
            ),
            ("employee_housing_fund_amount", "个人承担住房公积金", False),
            ("other_pre_tax_deduction_amount", "其他税前扣除", False),
            ("net_pay_amount", "实发金额", False),
            ("withheld_iit_amount", "代扣个人所得税", True),
        )
        canonical_amounts = {}
        for field_name, label, required in amount_fields:
            present, amount, decimal_amount = self._parse_decimal(
                payload.get(field_name), _(label), issues
            )
            values["has_%s" % field_name] = present
            values[field_name] = amount
            canonical_amounts[field_name] = decimal_amount
            if required and not present:
                issues.append(
                    self._issue(
                        "MISSING_%s" % field_name.upper(),
                        "error",
                        _("缺少%(label)s", label=_(label)),
                    )
                )
            if present and amount < 0:
                issues.append(
                    self._issue(
                        "NEGATIVE_PAYROLL_AMOUNT",
                        "error",
                        _("%(label)s不能为负数", label=_(label)),
                    )
                )

        if status in ("confirmed", "paid") and not payroll_run_reference:
            issues.append(
                self._issue(
                    "MISSING_PAYROLL_RUN_REFERENCE",
                    "warning",
                    _("已确认或已发放工资汇总缺少薪资批次引用"),
                )
            )
        if status in ("confirmed", "paid") and not approved_at:
            issues.append(
                self._issue(
                    "MISSING_PAYROLL_APPROVAL_TIME",
                    "warning",
                    _("已确认或已发放工资汇总缺少确认时间"),
                )
            )
        if status in ("draft", "cancelled", "unknown"):
            issues.append(
                self._issue(
                    "PAYROLL_STATUS_NOT_FINAL",
                    "warning",
                    _("工资薪酬汇总尚不是可勾稽的最终状态"),
                )
            )
        if (
            has_person_count
            and person_count == 0
            and (
                values["gross_income_amount"]
                or values["withheld_iit_amount"]
            )
        ):
            issues.append(
                self._issue(
                    "ZERO_PERSON_WITH_PAYROLL_AMOUNT",
                    "error",
                    _("人员数量为零但工资或代扣税额不为零"),
                )
            )
        if (
            values["has_gross_income_amount"]
            and values["has_withheld_iit_amount"]
            and values["withheld_iit_amount"] > values["gross_income_amount"]
        ):
            issues.append(
                self._issue(
                    "WITHHELD_IIT_EXCEEDS_GROSS_INCOME",
                    "warning",
                    _("代扣个人所得税大于工资薪酬收入总额"),
                )
            )

        values.update(
            {
                "payroll_frequency": frequency,
                "payroll_status": status,
                "payroll_run_reference": payroll_run_reference,
                "approved_at": approved_at,
                "has_declared_person_count": has_person_count,
                "declared_person_count": person_count,
            }
        )
        canonical.update(
            {
                "payroll_frequency": frequency,
                "payroll_status": status,
                "payroll_run_reference": payroll_run_reference,
                "approved_at": fields.Datetime.to_string(approved_at),
                "declared_person_count": (
                    person_count if has_person_count else None
                ),
                **canonical_amounts,
            }
        )
        quality_state = self._quality_state(issues)
        values.update(
            {
                "quality_state": quality_state,
                "issue_json": issues,
                "record_checksum": _sha256_json(
                    {
                        **canonical,
                        "quality_state": quality_state,
                        "issues": self._canonical_issues(issues),
                    }
                ),
            }
        )
        return values
