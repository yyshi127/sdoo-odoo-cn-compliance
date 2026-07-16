import re

from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError

from .tax_data_normalization import (
    _TAX_NORMALIZED_RECORD_MARKER,
    _safe_text,
    _sha256_json,
)


class SudoChinaIitWithholdingRecord(models.Model):
    _name = "sudo.cn.iit.withholding.record"
    _description = "China Normalized IIT Withholding Return"
    _inherit = "sudo.cn.tax.normalized.record.mixin"
    _order = "tax_year desc, period_end desc, submitted_at desc, id desc"
    _source_dataset_type = "iit_withholding"

    name = fields.Char(compute="_compute_name", store=True)
    jurisdiction_code = fields.Char(string="主管辖区代码", readonly=True)
    jurisdiction_name = fields.Char(string="主管辖区", readonly=True)
    tax_year = fields.Integer(string="纳税年度", readonly=True, index=True)
    filing_frequency = fields.Selection(
        [
            ("monthly", "按月申报"),
            ("per_payment", "按次申报"),
            ("other", "其他频次"),
            ("unknown", "未提供"),
        ],
        string="申报频次",
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

    has_declared_person_count = fields.Boolean(
        string="提供申报人数", readonly=True
    )
    declared_person_count = fields.Integer(string="申报人数", readonly=True)
    has_declared_line_count = fields.Boolean(
        string="提供申报明细行数", readonly=True
    )
    declared_line_count = fields.Integer(string="申报明细行数", readonly=True)

    has_total_income_amount = fields.Boolean(string="提供收入合计", readonly=True)
    total_income_amount = fields.Monetary(
        string="收入合计", currency_field="currency_id", readonly=True
    )
    has_total_tax_exempt_income_amount = fields.Boolean(
        string="提供免税收入合计", readonly=True
    )
    total_tax_exempt_income_amount = fields.Monetary(
        string="免税收入合计", currency_field="currency_id", readonly=True
    )
    has_total_basic_deduction_amount = fields.Boolean(
        string="提供减除费用合计", readonly=True
    )
    total_basic_deduction_amount = fields.Monetary(
        string="减除费用合计", currency_field="currency_id", readonly=True
    )
    has_total_special_deduction_amount = fields.Boolean(
        string="提供专项扣除合计", readonly=True
    )
    total_special_deduction_amount = fields.Monetary(
        string="专项扣除合计", currency_field="currency_id", readonly=True
    )
    has_total_special_additional_deduction_amount = fields.Boolean(
        string="提供专项附加扣除合计", readonly=True
    )
    total_special_additional_deduction_amount = fields.Monetary(
        string="专项附加扣除合计",
        currency_field="currency_id",
        readonly=True,
    )
    has_total_other_deduction_amount = fields.Boolean(
        string="提供其他扣除合计", readonly=True
    )
    total_other_deduction_amount = fields.Monetary(
        string="其他扣除合计", currency_field="currency_id", readonly=True
    )
    has_total_donation_deduction_amount = fields.Boolean(
        string="提供准予扣除捐赠额合计", readonly=True
    )
    total_donation_deduction_amount = fields.Monetary(
        string="准予扣除捐赠额合计",
        currency_field="currency_id",
        readonly=True,
    )
    has_total_taxable_income_amount = fields.Boolean(
        string="提供应纳税所得额合计", readonly=True
    )
    total_taxable_income_amount = fields.Monetary(
        string="应纳税所得额合计", currency_field="currency_id", readonly=True
    )
    has_total_tax_calculated_amount = fields.Boolean(
        string="提供应纳税额合计", readonly=True
    )
    total_tax_calculated_amount = fields.Monetary(
        string="应纳税额合计", currency_field="currency_id", readonly=True
    )
    has_total_tax_relief_amount = fields.Boolean(
        string="提供减免税额合计", readonly=True
    )
    total_tax_relief_amount = fields.Monetary(
        string="减免税额合计", currency_field="currency_id", readonly=True
    )
    has_total_tax_paid_amount = fields.Boolean(
        string="提供已缴税额合计", readonly=True
    )
    total_tax_paid_amount = fields.Monetary(
        string="已缴税额合计", currency_field="currency_id", readonly=True
    )
    has_total_payable_refundable_amount = fields.Boolean(
        string="提供应补退税额合计", readonly=True
    )
    total_payable_refundable_amount = fields.Monetary(
        string="应补退税额合计", currency_field="currency_id", readonly=True
    )
    line_ids = fields.One2many(
        "sudo.cn.iit.withholding.line",
        "withholding_record_id",
        string="个税扣缴申报受限明细",
        readonly=True,
    )

    _source_record_unique = models.Constraint(
        "unique(parse_run_id, source_record_key)",
        "同一导入运行中的个人所得税扣缴申报源记录键必须唯一。",
    )

    @api.depends("return_type_code", "tax_year", "period_start", "period_end")
    def _compute_name(self):
        for record in self:
            record.name = "%s / %s / %s - %s" % (
                record.return_type_code or _("个人所得税扣缴申报"),
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
            self._issue(
                "UNKNOWN_RETURN_STATUS",
                "warning",
                _("个人所得税扣缴申报状态未识别"),
            )
        )
        return "unknown"

    @api.model
    def _filing_frequency(self, payload, issues):
        raw_frequency = (
            _safe_text(payload.get("filing_frequency"), 32) or "unknown"
        )
        frequency_map = {
            "monthly": "monthly",
            "per_payment": "per_payment",
            "other": "other",
            "unknown": "unknown",
            "按月": "monthly",
            "按次": "per_payment",
            "其他": "other",
        }
        frequency = frequency_map.get(
            raw_frequency.lower(), frequency_map.get(raw_frequency)
        )
        if frequency:
            return frequency
        issues.append(
            self._issue(
                "UNKNOWN_IIT_FILING_FREQUENCY",
                "warning",
                _("个人所得税扣缴申报频次未识别"),
            )
        )
        return "unknown"

    @api.model
    def _tax_year(self, payload, issues):
        raw_year = payload.get("tax_year")
        normalized = str(raw_year).strip() if raw_year is not None else ""
        if isinstance(raw_year, bool) or not re.fullmatch(r"\d{4}", normalized):
            issues.append(
                self._issue("INVALID_IIT_TAX_YEAR", "error", _("纳税年度格式无效"))
            )
            return 0
        tax_year = int(normalized)
        if tax_year < 1900 or tax_year > 2200:
            issues.append(
                self._issue(
                    "INVALID_IIT_TAX_YEAR", "error", _("纳税年度超出受控范围")
                )
            )
            return 0
        return tax_year

    @api.model
    def _count_value(self, payload, field_name, label, issues):
        raw_value = payload.get(field_name)
        if raw_value in (None, ""):
            return False, 0
        normalized = str(raw_value).strip()
        if isinstance(raw_value, bool) or not re.fullmatch(r"\d+", normalized):
            issues.append(
                self._issue(
                    "INVALID_IIT_DECLARED_COUNT",
                    "error",
                    _("%(field)s格式无效", field=label),
                )
            )
            return False, 0
        return True, int(normalized)

    @api.model
    def _line_status(self, payload, issues, source_line_key):
        raw_status = _safe_text(payload.get("residency_status"), 32) or "unknown"
        status_map = {
            "resident": "resident",
            "nonresident": "nonresident",
            "unknown": "unknown",
            "居民个人": "resident",
            "非居民个人": "nonresident",
        }
        status = status_map.get(raw_status.lower(), status_map.get(raw_status))
        if status:
            return status
        issues.append(
            self._issue(
                "UNKNOWN_IIT_RESIDENCY_STATUS",
                "warning",
                _("明细 %(line)s 的居民身份状态未识别", line=source_line_key),
            )
        )
        return "unknown"

    @api.model
    def _line_income_type(self, payload, issues, source_line_key):
        raw_type = _safe_text(payload.get("income_type_code"), 64) or "unknown"
        type_map = {
            "wages_salary": "wages_salary",
            "labor_remuneration": "labor_remuneration",
            "author_remuneration": "author_remuneration",
            "royalties": "royalties",
            "interest_dividend": "interest_dividend",
            "property_lease": "property_lease",
            "property_transfer": "property_transfer",
            "incidental": "incidental",
            "other": "other",
            "unknown": "unknown",
            "工资薪金": "wages_salary",
            "劳务报酬": "labor_remuneration",
            "稿酬": "author_remuneration",
            "特许权使用费": "royalties",
            "利息股息红利": "interest_dividend",
            "财产租赁": "property_lease",
            "财产转让": "property_transfer",
            "偶然所得": "incidental",
        }
        income_type = type_map.get(raw_type.lower(), type_map.get(raw_type))
        if income_type:
            return income_type
        issues.append(
            self._issue(
                "UNKNOWN_IIT_INCOME_TYPE",
                "warning",
                _("明细 %(line)s 的所得项目未识别", line=source_line_key),
            )
        )
        return "unknown"

    @api.model
    def _prepare_line_values(self, payloads, issues):
        amount_fields = (
            ("current_income_amount", "本月（次）收入额"),
            ("current_tax_exempt_income_amount", "本月（次）免税收入"),
            ("current_basic_deduction_amount", "本月（次）减除费用"),
            ("current_special_deduction_amount", "本月（次）专项扣除"),
            ("current_other_deduction_amount", "本月（次）其他扣除"),
            ("cumulative_income_amount", "累计收入额"),
            ("cumulative_basic_deduction_amount", "累计减除费用"),
            ("cumulative_special_deduction_amount", "累计专项扣除"),
            (
                "cumulative_special_additional_deduction_amount",
                "累计专项附加扣除",
            ),
            ("cumulative_other_deduction_amount", "累计其他扣除"),
            ("donation_deduction_amount", "准予扣除的捐赠额"),
            ("taxable_income_amount", "应纳税所得额"),
            ("quick_deduction_amount", "速算扣除数"),
            ("tax_calculated_amount", "应纳税额"),
            ("tax_relief_amount", "减免税额"),
            ("tax_paid_amount", "已缴税额"),
            ("payable_refundable_amount", "应补退税额"),
        )
        line_values = []
        canonical_lines = []
        for sequence, payload in enumerate(payloads or [], start=1):
            source_line_key = _safe_text(payload.get("source_line_key"), 512)
            subject_key = _safe_text(payload.get("subject_key"), 160)
            values = {
                "sequence": sequence,
                "source_line_key": source_line_key,
                "subject_key": subject_key,
                "residency_status": self._line_status(
                    payload, issues, source_line_key
                ),
                "income_type_code": self._line_income_type(
                    payload, issues, source_line_key
                ),
            }
            canonical = dict(values)
            for field_name, label in amount_fields:
                present, amount, decimal_amount = self._parse_decimal(
                    payload.get(field_name), _(label), issues
                )
                values[f"has_{field_name}"] = present
                values[field_name] = amount
                canonical[field_name] = decimal_amount
                if (
                    present
                    and field_name != "payable_refundable_amount"
                    and amount < 0
                ):
                    issues.append(
                        self._issue(
                            "NEGATIVE_IIT_LINE_AMOUNT",
                            "warning",
                            _(
                                "明细 %(line)s 的 %(field)s 为负数，请核对源申报口径",
                                line=source_line_key,
                                field=_(label),
                            ),
                        )
                    )
            has_rate, rate, rate_decimal = self._parse_decimal(
                payload.get("tax_rate"), _("来源税率或预扣率"), issues
            )
            values["has_tax_rate"] = has_rate
            values["tax_rate"] = rate
            canonical["tax_rate"] = rate_decimal
            if has_rate and (rate < 0 or rate > 1):
                issues.append(
                    self._issue(
                        "IIT_RATE_OUT_OF_RANGE",
                        "warning",
                        _(
                            "明细 %(line)s 的来源税率或预扣率不在 0 至 1 之间",
                            line=source_line_key,
                        ),
                    )
                )
            if not (
                values["has_current_income_amount"]
                or values["has_cumulative_income_amount"]
            ):
                issues.append(
                    self._issue(
                        "IIT_LINE_WITHOUT_INCOME",
                        "error",
                        _("明细 %(line)s 未提供本期或累计收入", line=source_line_key),
                    )
                )
            if not values["has_payable_refundable_amount"]:
                issues.append(
                    self._issue(
                        "IIT_LINE_WITHOUT_SETTLEMENT_AMOUNT",
                        "error",
                        _("明细 %(line)s 未提供应补退税额", line=source_line_key),
                    )
                )
            values["line_checksum"] = _sha256_json(canonical)
            line_values.append(values)
            canonical_lines.append(canonical)
        return line_values, canonical_lines

    @api.model
    def _prepare_import_values(self, run, payload):
        values, canonical, issues, currency = self._prepare_common(run, payload)
        return_status = self._return_status(payload, issues)
        filing_frequency = self._filing_frequency(payload, issues)
        tax_year = self._tax_year(payload, issues)
        return_type_code = _safe_text(payload.get("return_type_code"), 128)
        if not return_type_code:
            issues.append(
                self._issue(
                    "MISSING_IIT_RETURN_TYPE",
                    "error",
                    _("缺少个人所得税扣缴申报表类型代码"),
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
                    "INVALID_REVISION_NUMBER", "warning", _("修订序号格式无效")
                )
            )

        person_count_present, person_count = self._count_value(
            payload, "declared_person_count", _("申报人数"), issues
        )
        line_count_present, line_count = self._count_value(
            payload, "declared_line_count", _("申报明细行数"), issues
        )
        values.update(
            {
                "has_declared_person_count": person_count_present,
                "declared_person_count": person_count,
                "has_declared_line_count": line_count_present,
                "declared_line_count": line_count,
            }
        )
        if not person_count_present:
            issues.append(
                self._issue(
                    "MISSING_IIT_PERSON_COUNT", "error", _("缺少申报人数")
                )
            )
        if not line_count_present:
            issues.append(
                self._issue(
                    "MISSING_IIT_LINE_COUNT", "error", _("缺少申报明细行数")
                )
            )

        amount_fields = (
            ("total_income_amount", "收入合计"),
            ("total_tax_exempt_income_amount", "免税收入合计"),
            ("total_basic_deduction_amount", "减除费用合计"),
            ("total_special_deduction_amount", "专项扣除合计"),
            (
                "total_special_additional_deduction_amount",
                "专项附加扣除合计",
            ),
            ("total_other_deduction_amount", "其他扣除合计"),
            ("total_donation_deduction_amount", "准予扣除捐赠额合计"),
            ("total_taxable_income_amount", "应纳税所得额合计"),
            ("total_tax_calculated_amount", "应纳税额合计"),
            ("total_tax_relief_amount", "减免税额合计"),
            ("total_tax_paid_amount", "已缴税额合计"),
            ("total_payable_refundable_amount", "应补退税额合计"),
        )
        canonical_amounts = {}
        for field_name, label in amount_fields:
            present, amount, decimal_amount = self._parse_decimal(
                payload.get(field_name), _(label), issues
            )
            values[f"has_{field_name}"] = present
            values[field_name] = amount
            canonical_amounts[field_name] = decimal_amount
            if (
                present
                and field_name != "total_payable_refundable_amount"
                and amount < 0
            ):
                issues.append(
                    self._issue(
                        "NEGATIVE_IIT_SUMMARY_AMOUNT",
                        "warning",
                        _("%(field)s为负数，请核对源申报口径", field=_(label)),
                    )
                )
        if not values["has_total_income_amount"]:
            issues.append(
                self._issue(
                    "MISSING_IIT_TOTAL_INCOME", "error", _("缺少收入合计")
                )
            )
        if not values["has_total_payable_refundable_amount"]:
            issues.append(
                self._issue(
                    "MISSING_IIT_TOTAL_SETTLEMENT",
                    "error",
                    _("缺少应补退税额合计"),
                )
            )

        line_values, canonical_lines = self._prepare_line_values(
            payload.get("lines"), issues
        )
        if not line_values:
            issues.append(
                self._issue(
                    "MISSING_IIT_PERSON_LINES",
                    "error",
                    _("个人所得税扣缴申报未提供受控人员明细"),
                )
            )
        distinct_subjects = {line["subject_key"] for line in line_values}
        if person_count_present and person_count != len(distinct_subjects):
            issues.append(
                self._issue(
                    "IIT_PERSON_COUNT_MISMATCH",
                    "error",
                    _("申报人数与受控假名人员数量不一致"),
                )
            )
        if line_count_present and line_count != len(line_values):
            issues.append(
                self._issue(
                    "IIT_LINE_COUNT_MISMATCH",
                    "error",
                    _("申报明细行数与规范化明细数量不一致"),
                )
            )
        if (
            currency
            and values["has_total_income_amount"]
            and line_values
            and all(line["has_current_income_amount"] for line in line_values)
            and not currency.is_zero(
                values["total_income_amount"]
                - sum(line["current_income_amount"] for line in line_values)
            )
        ):
            issues.append(
                self._issue(
                    "IIT_INCOME_TOTAL_MISMATCH",
                    "warning",
                    _("来源收入合计与明细本月（次）收入汇总不一致"),
                )
            )
        if (
            currency
            and values["has_total_payable_refundable_amount"]
            and line_values
            and all(
                line["has_payable_refundable_amount"] for line in line_values
            )
            and not currency.is_zero(
                values["total_payable_refundable_amount"]
                - sum(line["payable_refundable_amount"] for line in line_values)
            )
        ):
            issues.append(
                self._issue(
                    "IIT_SETTLEMENT_TOTAL_MISMATCH",
                    "warning",
                    _("来源应补退税额合计与明细汇总不一致"),
                )
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
                "filing_frequency": filing_frequency,
                "return_type_code": return_type_code,
                "return_status": return_status,
                "submitted_at": submitted_at,
                "submission_reference": submission_reference,
                "revision_number": revision_number,
                "correction_reference": _safe_text(
                    payload.get("correction_reference"), 256
                ),
                "line_ids": [Command.create(line) for line in line_values],
            }
        )
        canonical.update(
            {
                "jurisdiction_code": values["jurisdiction_code"],
                "jurisdiction_name": values["jurisdiction_name"],
                "tax_year": tax_year or None,
                "filing_frequency": filing_frequency,
                "return_type_code": return_type_code,
                "return_status": return_status,
                "submitted_at": fields.Datetime.to_string(submitted_at),
                "submission_reference": submission_reference,
                "revision_number": revision_number,
                "correction_reference": values["correction_reference"],
                "declared_person_count": (
                    person_count if person_count_present else None
                ),
                "declared_line_count": line_count if line_count_present else None,
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


class SudoChinaIitWithholdingLine(models.Model):
    _name = "sudo.cn.iit.withholding.line"
    _description = "China Normalized IIT Withholding Restricted Detail"
    _order = "withholding_record_id, sequence, id"
    _check_company_auto = True

    withholding_record_id = fields.Many2one(
        "sudo.cn.iit.withholding.record",
        string="个人所得税扣缴申报",
        required=True,
        ondelete="restrict",
        check_company=True,
        readonly=True,
        index=True,
    )
    company_id = fields.Many2one(
        related="withholding_record_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    currency_id = fields.Many2one(
        related="withholding_record_id.currency_id",
        store=True,
        readonly=True,
    )
    sequence = fields.Integer(readonly=True)
    source_line_key = fields.Char(
        string="源明细键",
        required=True,
        readonly=True,
        help="仅允许受控 HMAC 或不透明令牌，不得包含姓名、证件号码或其他人员标识。",
    )
    subject_key = fields.Char(
        string="受控人员假名键",
        required=True,
        readonly=True,
        index=True,
        help="应由来源系统使用独立受控密钥生成 HMAC，或使用不可回推人员身份的不透明令牌。",
    )
    residency_status = fields.Selection(
        [
            ("resident", "居民个人"),
            ("nonresident", "非居民个人"),
            ("unknown", "未提供"),
        ],
        string="居民身份状态",
        required=True,
        readonly=True,
    )
    income_type_code = fields.Selection(
        [
            ("wages_salary", "工资、薪金所得"),
            ("labor_remuneration", "劳务报酬所得"),
            ("author_remuneration", "稿酬所得"),
            ("royalties", "特许权使用费所得"),
            ("interest_dividend", "利息、股息、红利所得"),
            ("property_lease", "财产租赁所得"),
            ("property_transfer", "财产转让所得"),
            ("incidental", "偶然所得"),
            ("other", "其他"),
            ("unknown", "未提供"),
        ],
        string="所得项目",
        required=True,
        readonly=True,
        index=True,
    )
    has_current_income_amount = fields.Boolean(readonly=True)
    current_income_amount = fields.Monetary(
        string="本月（次）收入额", currency_field="currency_id", readonly=True
    )
    has_current_tax_exempt_income_amount = fields.Boolean(readonly=True)
    current_tax_exempt_income_amount = fields.Monetary(
        string="本月（次）免税收入", currency_field="currency_id", readonly=True
    )
    has_current_basic_deduction_amount = fields.Boolean(readonly=True)
    current_basic_deduction_amount = fields.Monetary(
        string="本月（次）减除费用", currency_field="currency_id", readonly=True
    )
    has_current_special_deduction_amount = fields.Boolean(readonly=True)
    current_special_deduction_amount = fields.Monetary(
        string="本月（次）专项扣除", currency_field="currency_id", readonly=True
    )
    has_current_other_deduction_amount = fields.Boolean(readonly=True)
    current_other_deduction_amount = fields.Monetary(
        string="本月（次）其他扣除", currency_field="currency_id", readonly=True
    )
    has_cumulative_income_amount = fields.Boolean(readonly=True)
    cumulative_income_amount = fields.Monetary(
        string="累计收入额", currency_field="currency_id", readonly=True
    )
    has_cumulative_basic_deduction_amount = fields.Boolean(readonly=True)
    cumulative_basic_deduction_amount = fields.Monetary(
        string="累计减除费用", currency_field="currency_id", readonly=True
    )
    has_cumulative_special_deduction_amount = fields.Boolean(readonly=True)
    cumulative_special_deduction_amount = fields.Monetary(
        string="累计专项扣除", currency_field="currency_id", readonly=True
    )
    has_cumulative_special_additional_deduction_amount = fields.Boolean(
        readonly=True
    )
    cumulative_special_additional_deduction_amount = fields.Monetary(
        string="累计专项附加扣除",
        currency_field="currency_id",
        readonly=True,
    )
    has_cumulative_other_deduction_amount = fields.Boolean(readonly=True)
    cumulative_other_deduction_amount = fields.Monetary(
        string="累计其他扣除", currency_field="currency_id", readonly=True
    )
    has_donation_deduction_amount = fields.Boolean(readonly=True)
    donation_deduction_amount = fields.Monetary(
        string="准予扣除的捐赠额", currency_field="currency_id", readonly=True
    )
    has_taxable_income_amount = fields.Boolean(readonly=True)
    taxable_income_amount = fields.Monetary(
        string="应纳税所得额", currency_field="currency_id", readonly=True
    )
    has_tax_rate = fields.Boolean(readonly=True)
    tax_rate = fields.Float(
        string="来源税率或预扣率", digits=(16, 8), readonly=True
    )
    has_quick_deduction_amount = fields.Boolean(readonly=True)
    quick_deduction_amount = fields.Monetary(
        string="速算扣除数", currency_field="currency_id", readonly=True
    )
    has_tax_calculated_amount = fields.Boolean(readonly=True)
    tax_calculated_amount = fields.Monetary(
        string="应纳税额", currency_field="currency_id", readonly=True
    )
    has_tax_relief_amount = fields.Boolean(readonly=True)
    tax_relief_amount = fields.Monetary(
        string="减免税额", currency_field="currency_id", readonly=True
    )
    has_tax_paid_amount = fields.Boolean(readonly=True)
    tax_paid_amount = fields.Monetary(
        string="已缴税额", currency_field="currency_id", readonly=True
    )
    has_payable_refundable_amount = fields.Boolean(readonly=True)
    payable_refundable_amount = fields.Monetary(
        string="应补退税额", currency_field="currency_id", readonly=True
    )
    line_checksum = fields.Char(
        string="明细 SHA-256", required=True, readonly=True, index=True
    )

    _line_unique = models.Constraint(
        "unique(withholding_record_id, source_line_key)",
        "同一份个人所得税扣缴申报中的源明细键必须唯一。",
    )

    @api.model_create_multi
    def create(self, vals_list):
        if (
            self.env.context.get("cn_tax_normalized_record_transition")
            is not _TAX_NORMALIZED_RECORD_MARKER
        ):
            raise AccessError(_("个人所得税扣缴申报明细只能由受控导入流程创建。"))
        return super().create(vals_list)

    def write(self, values):
        raise AccessError(_("个人所得税扣缴申报明细不可修改。"))

    def unlink(self):
        raise AccessError(_("个人所得税扣缴申报明细属于审计结果，不可删除。"))

    def copy(self, default=None):
        raise AccessError(_("个人所得税扣缴申报明细不可复制。"))
