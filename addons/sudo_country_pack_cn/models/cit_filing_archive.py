import hashlib

from odoo import _, api, Command, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .filing_archive import (
    _CN_ARCHIVE_TRANSITION_MARKER,
    _checksum,
    _date_string,
)


_CN_CIT_ARCHIVE_LINK_MARKER = object()


class SudoComplianceEvidence(models.Model):
    _inherit = "sudo.compliance.evidence"

    evidence_type = fields.Selection(
        selection_add=[("refund_receipt", "退库回执")],
        ondelete={"refund_receipt": "set default"},
    )


class SudoComplianceFiling(models.Model):
    _inherit = "sudo.compliance.filing"

    cn_cit_reconciliation_run_id = fields.Many2one(
        "sudo.cn.cit.period.reconciliation.run",
        string="中国企业所得税勾稽来源",
        ondelete="restrict",
        check_company=True,
        index=True,
        copy=False,
        domain=(
            "[('profile_id', '=', profile_id), "
            "('period_start', '=', period_start), "
            "('period_end', '=', period_end), "
            "('state', '=', 'succeeded')]"
        ),
    )
    cn_cit_filing_record_id = fields.Many2one(
        related="cn_cit_reconciliation_run_id.filing_record_id",
        string="受控企业所得税申报记录",
        readonly=True,
    )
    cn_cit_payment_record_ids = fields.Many2many(
        related="cn_cit_reconciliation_run_id.payment_record_ids",
        string="受控企业所得税缴退税记录",
        readonly=True,
    )
    cn_cit_currency_id = fields.Many2one(
        related="cn_cit_reconciliation_run_id.currency_id",
        string="企业所得税档案币种",
        readonly=True,
    )
    cn_cit_settlement_kind = fields.Selection(
        [
            ("none", "无应补应退"),
            ("payable", "应补缴税"),
            ("refund", "应退税款"),
            ("unknown", "方向待确认"),
            ("conflict", "应补应退冲突"),
        ],
        string="所得税结算方向",
        compute="_compute_cn_cit_settlement_kind",
    )
    cn_cit_refund_date = fields.Date(string="实际退库日期", tracking=True)
    cn_cit_refund_reference = fields.Char(string="退库参考号", tracking=True)
    cn_cit_filing_payable_amount = fields.Monetary(
        related="cn_cit_reconciliation_run_id.filing_payable_amount",
        string="来源应补所得税额",
        currency_field="cn_cit_currency_id",
        readonly=True,
    )
    cn_cit_filing_refundable_amount = fields.Monetary(
        related="cn_cit_reconciliation_run_id.filing_refundable_amount",
        string="来源应退所得税额",
        currency_field="cn_cit_currency_id",
        readonly=True,
    )
    cn_cit_paid_principal_amount = fields.Monetary(
        related="cn_cit_reconciliation_run_id.paid_principal_amount",
        string="缴款成功本金",
        currency_field="cn_cit_currency_id",
        readonly=True,
    )
    cn_cit_reversed_principal_amount = fields.Monetary(
        related="cn_cit_reconciliation_run_id.reversed_principal_amount",
        string="已冲正本金",
        currency_field="cn_cit_currency_id",
        readonly=True,
    )
    cn_cit_effective_paid_principal_amount = fields.Monetary(
        related="cn_cit_reconciliation_run_id.effective_paid_principal_amount",
        string="有效缴款本金",
        currency_field="cn_cit_currency_id",
        readonly=True,
    )
    cn_cit_refunded_principal_amount = fields.Monetary(
        related="cn_cit_reconciliation_run_id.refunded_principal_amount",
        string="已退库本金",
        currency_field="cn_cit_currency_id",
        readonly=True,
    )
    cn_cit_interest_amount = fields.Monetary(
        related="cn_cit_reconciliation_run_id.interest_amount",
        string="来源利息合计",
        currency_field="cn_cit_currency_id",
        readonly=True,
    )
    cn_cit_penalty_amount = fields.Monetary(
        related="cn_cit_reconciliation_run_id.penalty_amount",
        string="来源滞纳金罚款合计",
        currency_field="cn_cit_currency_id",
        readonly=True,
    )

    _cn_cit_run_unique = models.Constraint(
        "unique(cn_cit_reconciliation_run_id)",
        "同一企业所得税勾稽批次只能关联一份申报缴退税档案。",
    )

    def write(self, values):
        changed = set(values)
        if "cn_cit_reconciliation_run_id" in changed and any(
            filing.state != "draft" for filing in self
        ) and self.env.context.get(
            "cn_cit_filing_archive_link"
        ) is not _CN_CIT_ARCHIVE_LINK_MARKER:
            raise UserError(_("进入准备流程后不能更换中国企业所得税勾稽来源。"))
        if changed & {"cn_cit_refund_date", "cn_cit_refund_reference"} and any(
            filing.cn_payment_checksum for filing in self
        ):
            raise AccessError(_("退库档案封存后不能修改退库日期或参考号。"))
        return super().write(values)

    @api.constrains(
        "cn_vat_reconciliation_run_id",
        "cn_cit_reconciliation_run_id",
        "profile_id",
        "period_start",
        "period_end",
        "filing_code",
        "filing_type",
        "obligation_id",
    )
    def _check_cn_cit_archive_scope(self):
        for filing in self:
            if (
                filing.cn_vat_reconciliation_run_id
                and filing.cn_cit_reconciliation_run_id
            ):
                raise ValidationError(_("同一申报档案不能同时关联增值税和企业所得税勾稽。"))
            run = filing.cn_cit_reconciliation_run_id
            if not run:
                continue
            if filing.country_id.code != "CN":
                raise ValidationError(_("中国企业所得税档案只能关联中国合规档案。"))
            if run.profile_id != filing.profile_id or run.company_id != filing.company_id:
                raise ValidationError(_("企业所得税勾稽来源必须属于当前公司和合规档案。"))
            if (
                run.period_start != filing.period_start
                or run.period_end != filing.period_end
            ):
                raise ValidationError(_("企业所得税勾稽来源与申报档案期间必须完全一致。"))
            if (filing.filing_code or "").strip().upper() != "CN-CIT":
                raise ValidationError(_("受控企业所得税档案的申报编码必须为 CN-CIT。"))
            if (filing.filing_type or "").strip().lower() != "cn_cit_return":
                raise ValidationError(
                    _("受控企业所得税档案的申报类型必须为 cn_cit_return。")
                )
            if not filing.obligation_id or filing.obligation_id.code != "CN-CIT":
                raise ValidationError(_("受控企业所得税档案必须关联 CN-CIT 适用义务。"))

    @api.depends(
        "cn_cit_reconciliation_run_id",
        "cn_cit_reconciliation_run_id.has_filing_payable_amount",
        "cn_cit_reconciliation_run_id.filing_payable_amount",
        "cn_cit_reconciliation_run_id.has_filing_refundable_amount",
        "cn_cit_reconciliation_run_id.filing_refundable_amount",
    )
    def _compute_cn_cit_settlement_kind(self):
        for filing in self:
            run = filing.cn_cit_reconciliation_run_id
            if not run:
                filing.cn_cit_settlement_kind = "none"
                continue
            if not (
                run.has_filing_payable_amount
                and run.has_filing_refundable_amount
            ):
                filing.cn_cit_settlement_kind = "unknown"
                continue
            payable = not run.currency_id.is_zero(run.filing_payable_amount)
            refundable = not run.currency_id.is_zero(run.filing_refundable_amount)
            if payable and refundable:
                filing.cn_cit_settlement_kind = "conflict"
            elif payable:
                filing.cn_cit_settlement_kind = "payable"
            elif refundable:
                filing.cn_cit_settlement_kind = "refund"
            else:
                filing.cn_cit_settlement_kind = "none"

    def _cn_cit_source_record(self, *, require_current):
        self.ensure_one()
        run = self.cn_cit_reconciliation_run_id
        if not run:
            raise UserError(_("请先关联中国企业所得税账税与缴退税勾稽结果。"))
        allowed_states = {"succeeded"} if require_current else {"succeeded", "superseded"}
        if run.state not in allowed_states:
            raise UserError(_("只有当前成功的企业所得税勾稽结果可以形成申报档案。"))
        if not run.result_checksum or not run.filing_snapshot_checksum:
            raise UserError(_("企业所得税勾稽结果缺少受控申报快照校验和。"))
        if require_current and run.result_integrity_state != "verified":
            raise UserError(_("企业所得税勾稽结果完整性校验失败。"))
        if run.filing_source_state != "available":
            raise UserError(_("企业所得税申报来源存在阻断，不能登记正式申报。"))
        record = run.filing_record_id
        if not record:
            raise UserError(_("正式申报档案必须对应唯一一份受控企业所得税申报记录。"))
        if require_current and not record.is_current_result:
            raise UserError(_("受控企业所得税申报已被替代，请先重新执行期间勾稽。"))
        if record.dataset_id._current_integrity_state() != "verified":
            raise UserError(_("受控企业所得税申报源文件完整性校验失败。"))
        if record.quality_state == "error":
            raise UserError(_("受控企业所得税申报存在数据错误，不能登记正式申报。"))
        if record.return_status not in {"submitted", "accepted", "amended"}:
            raise UserError(_("受控企业所得税申报状态不是已申报、已受理或更正申报。"))
        if not record.submitted_at or not record.submission_reference:
            raise UserError(_("正式申报档案要求受控申报同时具有申报时间和参考号。"))
        if record.currency_id != run.currency_id:
            raise UserError(_("受控企业所得税申报币种与档案币种不一致。"))
        return record

    def _cn_cit_validate_obligation(self):
        self.ensure_one()
        obligation = self.obligation_id
        if not obligation or obligation.code != "CN-CIT":
            raise UserError(_("请先关联当前合规档案的 CN-CIT 适用义务。"))
        if obligation.applicability != "applicable":
            raise UserError(_("CN-CIT 义务尚未经过公司级适用性确认。"))
        if not obligation.filing_required or obligation.filing_type != "cn_cit_return":
            raise UserError(_("CN-CIT 义务未配置为企业所得税申报义务。"))
        if obligation.effective_from > self.period_end or (
            obligation.effective_to and obligation.effective_to < self.period_start
        ):
            raise UserError(_("CN-CIT 适用义务在当前申报期间内无效。"))
        source = obligation.authority_source_id
        today = fields.Date.context_today(self)
        if (
            not source
            or source.status != "valid"
            or not source._is_publishable_snapshot()
            or source.next_review_date < today
        ):
            raise UserError(_("CN-CIT 义务的官方依据尚未有效复核或已经过期。"))
        return obligation

    def _cn_cit_validate_settlement_configuration(self):
        self.ensure_one()
        kind = self.cn_cit_settlement_kind
        if kind == "unknown":
            raise UserError(_("企业所得税来源没有完整提供应补和应退字段，结算方向不能确认。"))
        if kind == "conflict":
            raise UserError(_("企业所得税来源同时存在正数应补和应退金额，请先复核来源。"))
        if kind == "payable" and not self.payment_required:
            raise UserError(_("当前来源存在应补所得税，请将申报档案标记为需要付款。"))
        if kind in {"none", "refund"} and self.payment_required:
            raise UserError(_("当前来源不存在应补所得税，不应将申报档案标记为需要付款。"))
        return kind

    @api.model
    def _cn_cit_amount_payload(self, currency, provided, amount):
        return {
            "provided": bool(provided),
            "amount": str(currency.round(amount)) if provided else None,
        }

    def _cn_submission_payload(self, record, evidence_records):
        self.ensure_one()
        if not self.cn_cit_reconciliation_run_id:
            return super()._cn_submission_payload(record, evidence_records)
        run = self.cn_cit_reconciliation_run_id
        obligation = self.obligation_id
        amount_fields = (
            "accounting_profit_amount",
            "adjustment_increase_amount",
            "adjustment_decrease_amount",
            "taxable_income_amount",
            "tax_payable_amount",
            "tax_relief_amount",
            "tax_credit_amount",
            "prepaid_tax_amount",
            "payable_amount",
            "refundable_amount",
        )
        return {
            "schema": "sdoo.cn.cit-filing-archive.v1",
            "company_id": self.company_id.id,
            "profile_id": self.profile_id.id,
            "filing_code": self.filing_code,
            "filing_type": self.filing_type,
            "period_start": _date_string(self.period_start),
            "period_end": _date_string(self.period_end),
            "due_date": _date_string(self.due_date),
            "authority_source_id": self.authority_source_id.id,
            "authority_source_checksum": self.authority_source_id.content_hash,
            "due_date_basis_checksum": hashlib.sha256(
                (self.due_date_basis or "").strip().encode("utf-8")
            ).hexdigest(),
            "obligation": {
                "obligation_id": obligation.id,
                "code": obligation.code,
                "applicability": obligation.applicability,
                "effective_from": _date_string(obligation.effective_from),
                "effective_to": _date_string(obligation.effective_to),
                "authority_source_id": obligation.authority_source_id.id,
                "authority_source_checksum": obligation.authority_source_id.content_hash,
                "justification_checksum": hashlib.sha256(
                    (obligation.justification or "").strip().encode("utf-8")
                ).hexdigest(),
            },
            "reconciliation": {
                "run_id": run.id,
                "result_checksum": run.result_checksum,
                "filing_snapshot_checksum": run.filing_snapshot_checksum,
                "return_period_type": run.return_period_type,
                "tax_type_code": run.cit_tax_type_code,
            },
            "filing_record": {
                "record_id": record.id,
                "record_checksum": record.record_checksum,
                "parse_run_id": record.parse_run_id.id,
                "parse_run_checksum": record.parse_run_id.output_checksum,
                "dataset_id": record.dataset_id.id,
                "dataset_seal_checksum": record.dataset_id.seal_checksum,
                "return_type_code": record.return_type_code,
                "return_status": record.return_status,
                "revision_number": record.revision_number,
                "amounts": {
                    field_name: self._cn_cit_amount_payload(
                        record.currency_id,
                        record[f"has_{field_name}"],
                        record[field_name],
                    )
                    for field_name in amount_fields
                },
            },
            "settlement_kind": self.cn_cit_settlement_kind,
            "submission_date": _date_string(self.submission_date),
            "submission_reference": self.submission_reference or None,
            "verified_evidence": self._cn_evidence_payload(evidence_records),
        }

    def _cn_payment_payload(self, evidence_records):
        self.ensure_one()
        if not self.cn_cit_reconciliation_run_id:
            return super()._cn_payment_payload(evidence_records)
        run = self.cn_cit_reconciliation_run_id
        records = run.payment_record_ids.sorted("id")
        kind = self.cn_cit_settlement_kind
        settlement_date = self.payment_date if kind == "payable" else self.cn_cit_refund_date
        settlement_reference = (
            self.payment_reference if kind == "payable" else self.cn_cit_refund_reference
        )
        return {
            "schema": "sdoo.cn.cit-settlement-archive.v1",
            "company_id": self.company_id.id,
            "profile_id": self.profile_id.id,
            "filing_id": self.id,
            "period_start": _date_string(self.period_start),
            "period_end": _date_string(self.period_end),
            "settlement_kind": kind,
            "reconciliation": {
                "run_id": run.id,
                "result_checksum": run.result_checksum,
                "payment_snapshot_checksum": run.payment_snapshot_checksum,
                "has_payable_payment_difference": run.has_payable_payment_difference,
                "payable_payment_difference": (
                    str(run.currency_id.round(run.payable_payment_difference))
                    if run.has_payable_payment_difference
                    else None
                ),
                "has_refundable_refund_difference": run.has_refundable_refund_difference,
                "refundable_refund_difference": (
                    str(run.currency_id.round(run.refundable_refund_difference))
                    if run.has_refundable_refund_difference
                    else None
                ),
            },
            "filing_settlement": {
                "payable": self._cn_cit_amount_payload(
                    run.currency_id,
                    run.has_filing_payable_amount,
                    run.filing_payable_amount,
                ),
                "refundable": self._cn_cit_amount_payload(
                    run.currency_id,
                    run.has_filing_refundable_amount,
                    run.filing_refundable_amount,
                ),
            },
            "payment_records": [
                {
                    "record_id": record.id,
                    "record_checksum": record.record_checksum,
                    "parse_run_id": record.parse_run_id.id,
                    "parse_run_checksum": record.parse_run_id.output_checksum,
                    "dataset_id": record.dataset_id.id,
                    "dataset_seal_checksum": record.dataset_id.seal_checksum,
                    "payment_status": record.payment_status,
                    "payment_date": _date_string(record.payment_date),
                    "payment_reference": record.payment_reference or None,
                    "principal": self._cn_cit_amount_payload(
                        record.currency_id,
                        record.has_principal_amount,
                        record.principal_amount,
                    ),
                }
                for record in records
            ],
            "settlement_totals": {
                "paid_principal": str(run.currency_id.round(run.paid_principal_amount)),
                "reversed_principal": str(
                    run.currency_id.round(run.reversed_principal_amount)
                ),
                "effective_paid_principal": str(
                    run.currency_id.round(run.effective_paid_principal_amount)
                ),
                "refunded_principal": str(
                    run.currency_id.round(run.refunded_principal_amount)
                ),
                "interest": str(run.currency_id.round(run.interest_amount)),
                "penalty": str(run.currency_id.round(run.penalty_amount)),
            },
            "settlement_date": _date_string(settlement_date),
            "settlement_reference": settlement_reference or None,
            "verified_evidence": self._cn_evidence_payload(evidence_records),
        }

    def _cn_cit_validate_submission(self):
        self.ensure_one()
        self._cn_cit_validate_obligation()
        self._cn_cit_validate_settlement_configuration()
        record = self._cn_cit_source_record(require_current=True)
        expected_date = self._cn_submission_date(record)
        if self.submission_date != expected_date:
            raise UserError(
                _(
                    "实际提交日期必须与受控申报时间对应的中国日期 %(date)s 一致。",
                    date=fields.Date.to_string(expected_date),
                )
            )
        if self.submission_reference != record.submission_reference:
            raise UserError(_("官方提交参考号必须与受控企业所得税申报记录一致。"))
        evidence = self._cn_verified_evidence({"filing_receipt", "external_reference"})
        if not evidence:
            raise UserError(_("登记中国企业所得税申报前必须具有已验证的正式申报回执证据。"))
        return record, evidence

    def _cn_cit_validate_payment_records(self):
        self.ensure_one()
        run = self.cn_cit_reconciliation_run_id
        self._cn_cit_source_record(require_current=False)
        if run.result_integrity_state != "verified":
            raise UserError(_("企业所得税勾稽结果完整性校验失败。"))
        if not run.payment_snapshot_checksum or run.payment_source_state != "available":
            raise UserError(_("企业所得税缴退税来源存在阻断，不能封存结算结果。"))
        records = run.payment_record_ids
        if not records:
            raise UserError(_("没有受控的企业所得税缴退税记录。"))
        for record in records:
            if record.dataset_id._current_integrity_state() != "verified":
                raise UserError(_("受控缴退税源文件完整性校验失败。"))
            if record.quality_state == "error":
                raise UserError(_("受控缴退税记录存在数据错误，不能封存。"))
            if record.currency_id != run.currency_id:
                raise UserError(_("受控缴退税记录币种与档案币种不一致。"))
        return records

    def _cn_cit_validate_payable(self):
        self.ensure_one()
        if self._cn_cit_validate_settlement_configuration() != "payable":
            raise UserError(_("当前企业所得税档案不是应补缴税方向。"))
        run = self.cn_cit_reconciliation_run_id
        records = self._cn_cit_validate_payment_records()
        effective = records.filtered(
            lambda record: record.payment_status in {"succeeded", "reversed"}
        )
        if not effective.filtered(lambda record: record.payment_status == "succeeded"):
            raise UserError(_("没有受控的企业所得税缴款成功记录，不能登记已付款。"))
        if not run.has_payable_payment_difference or not run.currency_id.is_zero(
            run.payable_payment_difference
        ):
            raise UserError(_("应补所得税与有效缴款本金尚未勾稽一致，不能标记全部已付款。"))
        expected_date = max(effective.mapped("payment_date"))
        if self.payment_date != expected_date:
            raise UserError(
                _(
                    "实际付款日期必须等于受控有效缴款记录的最后日期 %(date)s。",
                    date=fields.Date.to_string(expected_date),
                )
            )
        if len(effective) == 1:
            record = effective
            if not record.payment_reference:
                raise UserError(_("唯一有效缴款记录缺少缴款参考号。"))
            if self.payment_reference != record.payment_reference:
                raise UserError(_("付款参考号必须与唯一有效缴款记录一致。"))
        elif not self.payment_reference:
            raise UserError(_("多笔有效缴款记录需要填写受控汇总参考号。"))
        evidence = self._cn_verified_evidence({"payment_proof", "external_reference"})
        if not evidence:
            raise UserError(_("登记中国企业所得税已缴款前必须具有已验证的正式缴款证据。"))
        return evidence

    def _cn_cit_validate_refund(self):
        self.ensure_one()
        self._require_manager()
        if self.state not in {"submitted", "accepted"}:
            raise UserError(_("只有已提交或已受理的企业所得税档案可以封存退库结果。"))
        if self.cn_payment_checksum:
            raise UserError(_("当前企业所得税退库结果已经封存，不能重复登记。"))
        if self._cn_cit_validate_settlement_configuration() != "refund":
            raise UserError(_("当前企业所得税档案不是应退税款方向。"))
        if not self.cn_submission_checksum or self.cn_submission_integrity_state not in {
            "verified",
            "source_superseded",
        }:
            raise UserError(_("请先完成并校验企业所得税正式申报封存。"))
        run = self.cn_cit_reconciliation_run_id
        records = self._cn_cit_validate_payment_records()
        refunded = records.filtered(lambda record: record.payment_status == "refunded")
        if not refunded:
            raise UserError(_("没有受控的企业所得税已退库记录，不能封存退库结果。"))
        if not run.has_refundable_refund_difference or not run.currency_id.is_zero(
            run.refundable_refund_difference
        ):
            raise UserError(_("应退所得税与已退库本金尚未勾稽一致，不能封存退库结果。"))
        expected_date = max(refunded.mapped("payment_date"))
        if self.cn_cit_refund_date != expected_date:
            raise UserError(
                _(
                    "实际退库日期必须等于受控退库记录的最后日期 %(date)s。",
                    date=fields.Date.to_string(expected_date),
                )
            )
        if len(refunded) == 1:
            record = refunded
            if not record.payment_reference:
                raise UserError(_("唯一退库记录缺少退库参考号。"))
            if self.cn_cit_refund_reference != record.payment_reference:
                raise UserError(_("退库参考号必须与唯一受控退库记录一致。"))
        elif not self.cn_cit_refund_reference:
            raise UserError(_("多笔退库记录需要填写受控汇总参考号。"))
        evidence = self._cn_verified_evidence({"refund_receipt", "external_reference"})
        if not evidence:
            raise UserError(_("封存中国企业所得税退库前必须具有已验证的正式退库回执证据。"))
        return evidence

    def action_ready(self):
        for filing in self.filtered("cn_cit_reconciliation_run_id"):
            filing._cn_cit_validate_obligation()
            filing._cn_cit_validate_settlement_configuration()
            filing._cn_cit_source_record(require_current=True)
        return super().action_ready()

    def action_submit(self):
        payloads = {}
        for filing in self.filtered("cn_cit_reconciliation_run_id"):
            record, evidence = filing._cn_cit_validate_submission()
            payloads[filing.id] = (
                filing._cn_submission_payload(record, evidence),
                evidence,
            )
        result = super().action_submit()
        sealed_at = fields.Datetime.now()
        for filing in self.filtered("cn_cit_reconciliation_run_id"):
            payload, evidence = payloads[filing.id]
            previous_checksum = filing.cn_submission_checksum
            filing.with_context(
                cn_filing_archive_transition=_CN_ARCHIVE_TRANSITION_MARKER
            ).write(
                {
                    "cn_submission_snapshot_json": payload,
                    "cn_submission_checksum": _checksum(payload),
                    "cn_submission_sealed_at": sealed_at,
                    "cn_submission_evidence_ids": [Command.set(evidence.ids)],
                }
            )
            self.env["sudo.compliance.audit.event"]._log_records(
                filing,
                "cn.cit_filing_archive.sealed",
                previous_state="ready",
                new_state="submitted",
                details={
                    "reconciliation_run_id": filing.cn_cit_reconciliation_run_id.id,
                    "previous_checksum": previous_checksum,
                    "archive_checksum": filing.cn_submission_checksum,
                    "evidence_ids": evidence.ids,
                },
            )
        return result

    def action_mark_paid(self):
        payloads = {}
        for filing in self.filtered("cn_cit_reconciliation_run_id"):
            evidence = filing._cn_cit_validate_payable()
            payloads[filing.id] = (filing._cn_payment_payload(evidence), evidence)
        result = super().action_mark_paid()
        sealed_at = fields.Datetime.now()
        for filing in self.filtered("cn_cit_reconciliation_run_id"):
            payload, evidence = payloads[filing.id]
            filing.with_context(
                cn_filing_archive_transition=_CN_ARCHIVE_TRANSITION_MARKER
            ).write(
                {
                    "cn_payment_snapshot_json": payload,
                    "cn_payment_checksum": _checksum(payload),
                    "cn_payment_sealed_at": sealed_at,
                    "cn_payment_evidence_ids": [Command.set(evidence.ids)],
                }
            )
            self.env["sudo.compliance.audit.event"]._log_records(
                filing,
                "cn.cit_payment_archive.sealed",
                previous_state="pending",
                new_state="paid",
                details={
                    "reconciliation_run_id": filing.cn_cit_reconciliation_run_id.id,
                    "archive_checksum": filing.cn_payment_checksum,
                    "evidence_ids": evidence.ids,
                },
            )
        return result

    def action_seal_cn_cit_refund(self):
        payloads = {}
        for filing in self:
            evidence = filing._cn_cit_validate_refund()
            payloads[filing.id] = (filing._cn_payment_payload(evidence), evidence)
        sealed_at = fields.Datetime.now()
        for filing in self:
            payload, evidence = payloads[filing.id]
            filing.with_context(
                cn_filing_archive_transition=_CN_ARCHIVE_TRANSITION_MARKER
            ).write(
                {
                    "cn_payment_snapshot_json": payload,
                    "cn_payment_checksum": _checksum(payload),
                    "cn_payment_sealed_at": sealed_at,
                    "cn_payment_evidence_ids": [Command.set(evidence.ids)],
                }
            )
            self.env["sudo.compliance.audit.event"]._log_records(
                filing,
                "cn.cit_refund_archive.sealed",
                previous_state="unsealed",
                new_state="sealed",
                details={
                    "reconciliation_run_id": filing.cn_cit_reconciliation_run_id.id,
                    "archive_checksum": filing.cn_payment_checksum,
                    "evidence_ids": evidence.ids,
                },
            )
        return True

    def _cn_submission_integrity(self):
        self.ensure_one()
        if not self.cn_cit_reconciliation_run_id:
            return super()._cn_submission_integrity()
        if not self.cn_submission_checksum:
            return "unsealed"
        try:
            record = self._cn_cit_source_record(require_current=False)
            evidence = self.cn_submission_evidence_ids
            if not evidence or any(item.state != "verified" for item in evidence):
                return "invalid"
            payload = self._cn_submission_payload(record, evidence)
        except (UserError, ValidationError):
            return "invalid"
        if _checksum(payload) != self.cn_submission_checksum:
            return "changed"
        if (
            self.cn_cit_reconciliation_run_id.state == "superseded"
            or not record.is_current_result
        ):
            return "source_superseded"
        return "verified"

    def _cn_payment_integrity(self):
        self.ensure_one()
        if not self.cn_cit_reconciliation_run_id:
            return super()._cn_payment_integrity()
        kind = self.cn_cit_settlement_kind
        if kind == "none":
            return "not_required"
        if kind in {"unknown", "conflict"}:
            return "invalid"
        if kind == "payable" and not self.payment_required:
            return "invalid"
        if kind == "refund" and self.payment_required:
            return "invalid"
        if not self.cn_payment_checksum:
            return "unsealed"
        try:
            record = self._cn_cit_source_record(require_current=False)
            evidence = self.cn_payment_evidence_ids
            if not evidence or any(item.state != "verified" for item in evidence):
                return "invalid"
            for item in self.cn_cit_payment_record_ids:
                if item.dataset_id._current_integrity_state() != "verified":
                    return "invalid"
            payload = self._cn_payment_payload(evidence)
        except (UserError, ValidationError):
            return "invalid"
        if _checksum(payload) != self.cn_payment_checksum:
            return "changed"
        if kind == "payable" and self.payment_state != "paid":
            return "changed"
        if kind == "refund" and self.payment_state != "not_required":
            return "changed"
        if (
            self.cn_cit_reconciliation_run_id.state == "superseded"
            or not record.is_current_result
        ):
            return "source_superseded"
        return "verified"

    def action_open_cn_cit_reconciliation(self):
        self.ensure_one()
        if not self.cn_cit_reconciliation_run_id:
            raise UserError(_("当前申报档案没有关联中国企业所得税勾稽结果。"))
        return {
            "type": "ir.actions.act_window",
            "name": _("企业所得税账税与缴退税勾稽"),
            "res_model": "sudo.cn.cit.period.reconciliation.run",
            "res_id": self.cn_cit_reconciliation_run_id.id,
            "view_mode": "form",
            "views": [
                (
                    self.env.ref(
                        "sudo_country_pack_cn.view_cn_cit_period_reconciliation_run_form"
                    ).id,
                    "form",
                )
            ],
            "target": "current",
        }


class SudoChinaCitPeriodReconciliationRun(models.Model):
    _inherit = "sudo.cn.cit.period.reconciliation.run"

    filing_archive_count = fields.Integer(
        string="申报缴退税档案数",
        compute="_compute_filing_archive_count",
    )

    def _compute_filing_archive_count(self):
        grouped = (
            self.env["sudo.compliance.filing"]._read_group(
                [("cn_cit_reconciliation_run_id", "in", self.ids)],
                ["cn_cit_reconciliation_run_id"],
                ["__count"],
            )
            if self
            else []
        )
        counts = {run.id: count for run, count in grouped}
        for run in self:
            run.filing_archive_count = counts.get(run.id, 0)

    def action_open_cn_filing_archive(self):
        self.ensure_one()
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以建立申报缴退税档案。"))
        filing_model = self.env["sudo.compliance.filing"].with_company(
            self.company_id
        )
        filing = filing_model.search(
            [("cn_cit_reconciliation_run_id", "=", self.id)],
            limit=1,
        )
        if not filing:
            filing = filing_model.search(
                [
                    ("profile_id", "=", self.profile_id.id),
                    ("filing_code", "=", "CN-CIT"),
                    ("period_start", "=", self.period_start),
                    ("period_end", "=", self.period_end),
                ],
                limit=1,
            )
        if (
            filing
            and not filing.cn_cit_reconciliation_run_id
            and self.state == "succeeded"
        ):
            if filing.state not in {"draft", "preparing", "rejected"}:
                raise UserError(
                    _(
                        "同期间已有未关联勾稽来源的申报档案。请先将其重新打开为准备中，"
                        "再从当前勾稽批次建立受控关联。"
                    )
                )
            filing.with_context(
                cn_cit_filing_archive_link=_CN_CIT_ARCHIVE_LINK_MARKER
            ).write({"cn_cit_reconciliation_run_id": self.id})
        action = self.env.ref(
            "sudo_global_finance.action_compliance_filings"
        ).sudo().read()[0]
        form_view = self.env.ref("sudo_global_finance.view_compliance_filing_form")
        action.update(
            {
                "view_mode": "form",
                "views": [(form_view.id, "form")],
                "target": "current",
            }
        )
        if filing:
            action["res_id"] = filing.id
            action["context"] = {}
            return action
        if self.state != "succeeded":
            raise UserError(_("只有当前成功的企业所得税勾稽结果可以新建申报缴退税档案。"))
        filing_record = self.filing_record_id
        obligation = self.env["sudo.compliance.obligation"].search(
            [
                ("profile_id", "=", self.profile_id.id),
                ("code", "=", "CN-CIT"),
                ("active", "=", True),
            ],
            limit=1,
        )
        payable = bool(
            filing_record
            and filing_record.has_payable_amount
            and not self.currency_id.is_zero(filing_record.payable_amount)
        )
        refundable = bool(
            filing_record
            and filing_record.has_refundable_amount
            and not self.currency_id.is_zero(filing_record.refundable_amount)
        )
        defaults = {
            "default_filing_name": _("企业所得税纳税申报"),
            "default_profile_id": self.profile_id.id,
            "default_obligation_id": obligation.id or False,
            "default_filing_code": "CN-CIT",
            "default_filing_type": "cn_cit_return",
            "default_authority": obligation.authority or False,
            "default_period_start": self.period_start,
            "default_period_end": self.period_end,
            "default_assignee_id": self.env.user.id,
            "default_payment_required": payable and not refundable,
            "default_submission_date": (
                fields.Date.to_string(
                    filing_model._cn_submission_date(filing_record)
                )
                if filing_record and filing_record.submitted_at
                else False
            ),
            "default_submission_reference": (
                filing_record.submission_reference if filing_record else False
            ),
            "default_cn_cit_reconciliation_run_id": self.id,
        }
        if payable and not refundable:
            effective = self.payment_record_ids.filtered(
                lambda record: record.payment_status in {"succeeded", "reversed"}
            )
            if len(effective) == 1:
                defaults.update(
                    {
                        "default_payment_date": effective.payment_date,
                        "default_payment_reference": effective.payment_reference,
                    }
                )
        elif refundable and not payable:
            refunded = self.payment_record_ids.filtered(
                lambda record: record.payment_status == "refunded"
            )
            if len(refunded) == 1:
                defaults.update(
                    {
                        "default_cn_cit_refund_date": refunded.payment_date,
                        "default_cn_cit_refund_reference": refunded.payment_reference,
                    }
                )
        action["context"] = defaults
        return action
