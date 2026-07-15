import re

from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError

from .tax_data_normalization import (
    _TAX_NORMALIZED_RECORD_MARKER,
    _safe_text,
    _sha256_json,
)


class SudoChinaCitFilingRecord(models.Model):
    _name = "sudo.cn.cit.filing.record"
    _description = "China Normalized CIT Filing Record"
    _inherit = "sudo.cn.tax.normalized.record.mixin"
    _order = "tax_year desc, period_end desc, submitted_at desc, id desc"
    _source_dataset_type = "cit_filing"

    name = fields.Char(compute="_compute_name", store=True)
    jurisdiction_code = fields.Char(string="主管辖区代码", readonly=True)
    jurisdiction_name = fields.Char(string="主管辖区", readonly=True)
    tax_year = fields.Integer(string="纳税年度", readonly=True, index=True)
    return_period_type = fields.Selection(
        [
            ("quarterly_prepayment", "季度预缴"),
            ("annual_reconciliation", "年度汇算清缴"),
            ("other", "其他申报期间"),
            ("unknown", "未提供"),
        ],
        string="申报期间类型",
        required=True,
        readonly=True,
        index=True,
    )
    return_type_code = fields.Char(string="申报表类型代码", readonly=True)
    return_status = fields.Selection(
        [
            ("draft", "草稿"),
            ("submitted", "已申报"),
            ("accepted", "已受理"),
            ("amended", "更正申报"),
            ("cancelled", "已作废"),
            ("unknown", "未提供"),
        ],
        string="申报状态",
        required=True,
        readonly=True,
        index=True,
    )
    submitted_at = fields.Datetime(string="申报时间", readonly=True)
    submission_reference = fields.Char(string="申报参考号", readonly=True)
    revision_number = fields.Integer(string="修订序号", readonly=True)
    correction_reference = fields.Char(string="更正原申报引用", readonly=True)

    has_accounting_profit_amount = fields.Boolean(
        string="提供会计利润总额", readonly=True
    )
    accounting_profit_amount = fields.Monetary(
        string="会计利润总额", currency_field="currency_id", readonly=True
    )
    has_adjustment_increase_amount = fields.Boolean(
        string="提供纳税调增额", readonly=True
    )
    adjustment_increase_amount = fields.Monetary(
        string="纳税调增额", currency_field="currency_id", readonly=True
    )
    has_adjustment_decrease_amount = fields.Boolean(
        string="提供纳税调减额", readonly=True
    )
    adjustment_decrease_amount = fields.Monetary(
        string="纳税调减额", currency_field="currency_id", readonly=True
    )
    has_taxable_income_amount = fields.Boolean(
        string="提供应纳税所得额", readonly=True
    )
    taxable_income_amount = fields.Monetary(
        string="应纳税所得额", currency_field="currency_id", readonly=True
    )
    has_tax_payable_amount = fields.Boolean(
        string="提供应纳所得税额", readonly=True
    )
    tax_payable_amount = fields.Monetary(
        string="应纳所得税额", currency_field="currency_id", readonly=True
    )
    has_tax_relief_amount = fields.Boolean(
        string="提供减免所得税额", readonly=True
    )
    tax_relief_amount = fields.Monetary(
        string="减免所得税额", currency_field="currency_id", readonly=True
    )
    has_tax_credit_amount = fields.Boolean(
        string="提供抵免所得税额", readonly=True
    )
    tax_credit_amount = fields.Monetary(
        string="抵免所得税额", currency_field="currency_id", readonly=True
    )
    has_prepaid_tax_amount = fields.Boolean(
        string="提供已预缴所得税额", readonly=True
    )
    prepaid_tax_amount = fields.Monetary(
        string="已预缴所得税额", currency_field="currency_id", readonly=True
    )
    has_payable_amount = fields.Boolean(string="提供应补所得税额", readonly=True)
    payable_amount = fields.Monetary(
        string="应补所得税额", currency_field="currency_id", readonly=True
    )
    has_refundable_amount = fields.Boolean(string="提供应退所得税额", readonly=True)
    refundable_amount = fields.Monetary(
        string="应退所得税额", currency_field="currency_id", readonly=True
    )
    line_ids = fields.One2many(
        "sudo.cn.cit.filing.line",
        "filing_record_id",
        string="企业所得税申报标准化行",
        readonly=True,
    )

    _source_record_unique = models.Constraint(
        "unique(parse_run_id, source_record_key)",
        "同一导入运行中的企业所得税申报源记录键必须唯一。",
    )

    @api.depends("return_type_code", "tax_year", "period_start", "period_end")
    def _compute_name(self):
        for record in self:
            record.name = "%s / %s / %s - %s" % (
                record.return_type_code or _("企业所得税申报"),
                record.tax_year or "-",
                fields.Date.to_string(record.period_start) or "-",
                fields.Date.to_string(record.period_end) or "-",
            )

    @api.model
    def _return_status(self, payload, issues):
        raw_status = _safe_text(payload.get("return_status"), 32) or "unknown"
        status_map = {
            "draft": "draft",
            "submitted": "submitted",
            "accepted": "accepted",
            "amended": "amended",
            "cancelled": "cancelled",
            "unknown": "unknown",
            "草稿": "draft",
            "已申报": "submitted",
            "已受理": "accepted",
            "更正申报": "amended",
            "已作废": "cancelled",
        }
        status = status_map.get(raw_status.lower(), status_map.get(raw_status))
        if status:
            return status
        issues.append(
            self._issue("UNKNOWN_RETURN_STATUS", "warning", _("企业所得税申报状态未识别"))
        )
        return "unknown"

    @api.model
    def _period_type(self, payload, issues):
        raw_type = _safe_text(payload.get("return_period_type"), 64) or "unknown"
        type_map = {
            "quarterly_prepayment": "quarterly_prepayment",
            "annual_reconciliation": "annual_reconciliation",
            "other": "other",
            "unknown": "unknown",
            "季度预缴": "quarterly_prepayment",
            "年度汇算清缴": "annual_reconciliation",
            "其他": "other",
        }
        period_type = type_map.get(raw_type.lower(), type_map.get(raw_type))
        if period_type:
            return period_type
        issues.append(
            self._issue(
                "UNKNOWN_CIT_RETURN_PERIOD_TYPE",
                "warning",
                _("企业所得税申报期间类型未识别"),
            )
        )
        return "unknown"

    @api.model
    def _tax_year(self, payload, issues):
        raw_year = payload.get("tax_year")
        normalized = str(raw_year).strip() if raw_year is not None else ""
        if isinstance(raw_year, bool) or not re.fullmatch(r"\d{4}", normalized):
            issues.append(
                self._issue("INVALID_CIT_TAX_YEAR", "error", _("纳税年度格式无效"))
            )
            return 0
        tax_year = int(normalized)
        if tax_year < 1900 or tax_year > 2200:
            issues.append(
                self._issue("INVALID_CIT_TAX_YEAR", "error", _("纳税年度超出受控范围"))
            )
            return 0
        return tax_year

    @api.model
    def _prepare_line_values(self, payloads, issues):
        commands = []
        canonical = []
        allowed_types = {
            "accounting",
            "adjustment_increase",
            "adjustment_decrease",
            "taxable_income",
            "tax",
            "relief",
            "credit",
            "prepayment",
            "payable",
            "refund",
            "other",
        }
        for sequence, payload in enumerate(payloads or [], start=1):
            line_code = _safe_text(payload.get("line_code"), 128)
            amount_type = (
                _safe_text(payload.get("amount_type"), 64) or "other"
            ).lower()
            if amount_type not in allowed_types:
                issues.append(
                    self._issue(
                        "UNKNOWN_CIT_LINE_TYPE",
                        "warning",
                        _("申报表行 %(line)s 的金额类型未识别", line=line_code),
                    )
                )
                amount_type = "other"
            has_current, current, current_decimal = self._parse_decimal(
                payload.get("current_amount"), _("本期金额"), issues
            )
            has_ytd, ytd, ytd_decimal = self._parse_decimal(
                payload.get("ytd_amount"), _("本年累计金额"), issues
            )
            has_rate, rate, rate_decimal = self._parse_decimal(
                payload.get("tax_rate"), _("来源申报税率"), issues
            )
            if not has_current and not has_ytd:
                issues.append(
                    self._issue(
                        "CIT_LINE_WITHOUT_AMOUNT",
                        "warning",
                        _("申报表行 %(line)s 未提供本期或累计金额", line=line_code),
                    )
                )
            if has_rate and (rate < 0 or rate > 1):
                issues.append(
                    self._issue(
                        "CIT_RATE_OUT_OF_RANGE",
                        "warning",
                        _("申报表行 %(line)s 的来源税率不在 0 至 1 之间", line=line_code),
                    )
                )
            values = {
                "sequence": sequence,
                "line_code": line_code,
                "line_name": _safe_text(payload.get("line_name"), 512),
                "amount_type": amount_type,
                "has_current_amount": has_current,
                "current_amount": current,
                "has_ytd_amount": has_ytd,
                "ytd_amount": ytd,
                "has_tax_rate": has_rate,
                "tax_rate": rate,
            }
            commands.append(Command.create(values))
            canonical.append(
                {
                    **values,
                    "current_amount": current_decimal,
                    "ytd_amount": ytd_decimal,
                    "tax_rate": rate_decimal,
                }
            )
        return commands, canonical

    @api.model
    def _prepare_import_values(self, run, payload):
        values, canonical, issues, _currency = self._prepare_common(run, payload)
        return_status = self._return_status(payload, issues)
        period_type = self._period_type(payload, issues)
        tax_year = self._tax_year(payload, issues)
        return_type_code = _safe_text(payload.get("return_type_code"), 128)
        if not return_type_code:
            issues.append(
                self._issue(
                    "MISSING_CIT_RETURN_TYPE",
                    "error",
                    _("缺少企业所得税申报表类型代码"),
                )
            )
        submitted_at = self._parse_datetime(
            payload.get("submitted_at"), _("申报时间"), issues
        )
        submission_reference = _safe_text(
            payload.get("submission_reference"), 256
        )
        if return_status in {"submitted", "accepted", "amended"} and not (
            submitted_at or submission_reference
        ):
            issues.append(
                self._issue(
                    "MISSING_SUBMISSION_EVIDENCE",
                    "warning",
                    _("已申报记录未提供申报时间或参考号"),
                )
            )
        try:
            revision_number = max(int(payload.get("revision_number") or 0), 0)
        except (TypeError, ValueError):
            revision_number = 0
            issues.append(
                self._issue(
                    "INVALID_REVISION_NUMBER",
                    "warning",
                    _("修订序号格式无效"),
                )
            )

        amount_fields = (
            ("accounting_profit_amount", "会计利润总额"),
            ("adjustment_increase_amount", "纳税调增额"),
            ("adjustment_decrease_amount", "纳税调减额"),
            ("taxable_income_amount", "应纳税所得额"),
            ("tax_payable_amount", "应纳所得税额"),
            ("tax_relief_amount", "减免所得税额"),
            ("tax_credit_amount", "抵免所得税额"),
            ("prepaid_tax_amount", "已预缴所得税额"),
            ("payable_amount", "应补所得税额"),
            ("refundable_amount", "应退所得税额"),
        )
        nonnegative_fields = {
            "adjustment_increase_amount",
            "adjustment_decrease_amount",
            "tax_payable_amount",
            "tax_relief_amount",
            "tax_credit_amount",
            "prepaid_tax_amount",
            "payable_amount",
            "refundable_amount",
        }
        canonical_amounts = {}
        for field_name, label in amount_fields:
            present, amount, decimal_amount = self._parse_decimal(
                payload.get(field_name), _(label), issues
            )
            values[f"has_{field_name}"] = present
            values[field_name] = amount
            canonical_amounts[field_name] = decimal_amount
            if present and field_name in nonnegative_fields and amount < 0:
                issues.append(
                    self._issue(
                        "NEGATIVE_CIT_SUMMARY_AMOUNT",
                        "warning",
                        _("%(field)s为负数，请核对源申报口径", field=_(label)),
                    )
                )
        if not values["has_taxable_income_amount"]:
            issues.append(
                self._issue(
                    "MISSING_CIT_TAXABLE_INCOME",
                    "error",
                    _("缺少企业所得税应纳税所得额"),
                )
            )
        if not values["has_payable_amount"] and not values["has_refundable_amount"]:
            issues.append(
                self._issue(
                    "MISSING_CIT_SETTLEMENT_AMOUNT",
                    "error",
                    _("缺少企业所得税应补或应退金额"),
                )
            )
        if values["payable_amount"] > 0 and values["refundable_amount"] > 0:
            issues.append(
                self._issue(
                    "CIT_PAYABLE_AND_REFUNDABLE_PRESENT",
                    "warning",
                    _("同一申报同时存在正数应补和应退金额，请核对源申报口径"),
                )
            )

        line_commands, canonical_lines = self._prepare_line_values(
            payload.get("lines"), issues
        )
        values.update(
            {
                "jurisdiction_code": _safe_text(
                    payload.get("jurisdiction_code"), 128
                ),
                "jurisdiction_name": _safe_text(
                    payload.get("jurisdiction_name"), 512
                ),
                "tax_year": tax_year,
                "return_period_type": period_type,
                "return_type_code": return_type_code,
                "return_status": return_status,
                "submitted_at": submitted_at,
                "submission_reference": submission_reference,
                "revision_number": revision_number,
                "correction_reference": _safe_text(
                    payload.get("correction_reference"), 256
                ),
                "line_ids": line_commands,
            }
        )
        canonical.update(
            {
                "jurisdiction_code": values["jurisdiction_code"],
                "jurisdiction_name": values["jurisdiction_name"],
                "tax_year": tax_year or None,
                "return_period_type": period_type,
                "return_type_code": return_type_code,
                "return_status": return_status,
                "submitted_at": fields.Datetime.to_string(submitted_at),
                "submission_reference": submission_reference,
                "revision_number": revision_number,
                "correction_reference": values["correction_reference"],
                **canonical_amounts,
                "lines": canonical_lines,
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


class SudoChinaCitFilingLine(models.Model):
    _name = "sudo.cn.cit.filing.line"
    _description = "China Normalized CIT Filing Line"
    _order = "filing_record_id, sequence, id"
    _check_company_auto = True

    filing_record_id = fields.Many2one(
        "sudo.cn.cit.filing.record",
        string="企业所得税申报记录",
        required=True,
        ondelete="restrict",
        check_company=True,
        readonly=True,
        index=True,
    )
    company_id = fields.Many2one(
        related="filing_record_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    currency_id = fields.Many2one(
        related="filing_record_id.currency_id",
        store=True,
        readonly=True,
    )
    sequence = fields.Integer(readonly=True)
    line_code = fields.Char(string="行代码", required=True, readonly=True)
    line_name = fields.Char(string="行名称", readonly=True)
    amount_type = fields.Selection(
        [
            ("accounting", "会计口径"),
            ("adjustment_increase", "纳税调增"),
            ("adjustment_decrease", "纳税调减"),
            ("taxable_income", "应纳税所得额"),
            ("tax", "所得税额"),
            ("relief", "减免税额"),
            ("credit", "抵免税额"),
            ("prepayment", "预缴税额"),
            ("payable", "应补税额"),
            ("refund", "应退税额"),
            ("other", "其他"),
        ],
        string="金额类型",
        required=True,
        readonly=True,
    )
    has_current_amount = fields.Boolean(string="提供本期金额", readonly=True)
    current_amount = fields.Monetary(
        string="本期金额", currency_field="currency_id", readonly=True
    )
    has_ytd_amount = fields.Boolean(string="提供本年累计", readonly=True)
    ytd_amount = fields.Monetary(
        string="本年累计", currency_field="currency_id", readonly=True
    )
    has_tax_rate = fields.Boolean(string="提供来源申报税率", readonly=True)
    tax_rate = fields.Float(string="来源申报税率", digits=(16, 8), readonly=True)

    _line_unique = models.Constraint(
        "unique(filing_record_id, line_code)",
        "同一企业所得税申报记录中的标准化行代码必须唯一。",
    )

    @api.model_create_multi
    def create(self, vals_list):
        if (
            self.env.context.get("cn_tax_normalized_record_transition")
            is not _TAX_NORMALIZED_RECORD_MARKER
        ):
            raise AccessError(_("企业所得税申报标准化行只能由受控导入流程创建。"))
        return super().create(vals_list)

    def write(self, values):
        raise AccessError(_("企业所得税申报标准化行不可修改。"))

    def unlink(self):
        raise AccessError(_("企业所得税申报标准化行属于导入审计结果，不可删除。"))
