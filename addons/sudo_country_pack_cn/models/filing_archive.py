import hashlib
import json
from datetime import timezone
from zoneinfo import ZoneInfo

from odoo import _, api, Command, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


_CN_ARCHIVE_TRANSITION_MARKER = object()
_CN_ARCHIVE_LINK_MARKER = object()
_CN_TIMEZONE = ZoneInfo("Asia/Shanghai")
_CN_ARCHIVE_FIELDS = {
    "cn_submission_snapshot_json",
    "cn_submission_checksum",
    "cn_submission_sealed_at",
    "cn_submission_evidence_ids",
    "cn_payment_snapshot_json",
    "cn_payment_checksum",
    "cn_payment_sealed_at",
    "cn_payment_evidence_ids",
}


def _checksum(payload):
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _date_string(value):
    return fields.Date.to_string(value) if value else None


def _datetime_string(value):
    return fields.Datetime.to_string(value) if value else None


class SudoComplianceFiling(models.Model):
    _inherit = "sudo.compliance.filing"

    cn_vat_reconciliation_run_id = fields.Many2one(
        "sudo.cn.vat.period.reconciliation.run",
        string="中国增值税勾稽来源",
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
    cn_vat_filing_record_ids = fields.Many2many(
        related="cn_vat_reconciliation_run_id.filing_record_ids",
        string="受控增值税申报记录",
        readonly=True,
    )
    cn_tax_payment_record_ids = fields.Many2many(
        related="cn_vat_reconciliation_run_id.payment_record_ids",
        string="受控增值税缴款记录",
        readonly=True,
    )
    cn_currency_id = fields.Many2one(
        related="cn_vat_reconciliation_run_id.currency_id",
        string="中国档案币种",
        readonly=True,
    )
    cn_submission_snapshot_json = fields.Json(
        string="申报封存快照",
        readonly=True,
        copy=False,
    )
    cn_submission_checksum = fields.Char(
        string="申报档案 SHA-256",
        readonly=True,
        copy=False,
        index=True,
    )
    cn_submission_sealed_at = fields.Datetime(
        string="申报封存时间",
        readonly=True,
        copy=False,
    )
    cn_submission_evidence_ids = fields.Many2many(
        "sudo.compliance.evidence",
        "sudo_cn_filing_submission_evidence_rel",
        "filing_id",
        "evidence_id",
        string="已封存申报证据",
        readonly=True,
        copy=False,
        check_company=True,
    )
    cn_payment_snapshot_json = fields.Json(
        string="缴款封存快照",
        readonly=True,
        copy=False,
    )
    cn_payment_checksum = fields.Char(
        string="缴款档案 SHA-256",
        readonly=True,
        copy=False,
        index=True,
    )
    cn_payment_sealed_at = fields.Datetime(
        string="缴款封存时间",
        readonly=True,
        copy=False,
    )
    cn_payment_evidence_ids = fields.Many2many(
        "sudo.compliance.evidence",
        "sudo_cn_filing_payment_evidence_rel",
        "filing_id",
        "evidence_id",
        string="已封存缴款证据",
        readonly=True,
        copy=False,
        check_company=True,
    )
    cn_submission_integrity_state = fields.Selection(
        [
            ("not_applicable", "不适用"),
            ("unsealed", "待封存"),
            ("verified", "完整性正常"),
            ("source_superseded", "来源已被新批次替代"),
            ("changed", "封存内容已变化"),
            ("invalid", "来源完整性异常"),
        ],
        string="申报档案完整性",
        compute="_compute_cn_archive_states",
    )
    cn_payment_integrity_state = fields.Selection(
        [
            ("not_applicable", "不适用"),
            ("not_required", "无需缴款"),
            ("unsealed", "待封存"),
            ("verified", "完整性正常"),
            ("source_superseded", "来源已被新批次替代"),
            ("changed", "封存内容已变化"),
            ("invalid", "来源完整性异常"),
        ],
        string="缴款档案完整性",
        compute="_compute_cn_archive_states",
    )
    cn_succeeded_payment_amount = fields.Monetary(
        string="缴款成功金额",
        currency_field="cn_currency_id",
        compute="_compute_cn_payment_totals",
    )
    cn_reversed_payment_amount = fields.Monetary(
        string="冲正金额",
        currency_field="cn_currency_id",
        compute="_compute_cn_payment_totals",
    )
    cn_refunded_payment_amount = fields.Monetary(
        string="退库金额",
        currency_field="cn_currency_id",
        compute="_compute_cn_payment_totals",
    )
    cn_net_payment_amount = fields.Monetary(
        string="有效缴款净额",
        currency_field="cn_currency_id",
        compute="_compute_cn_payment_totals",
    )

    _cn_vat_run_unique = models.Constraint(
        "unique(cn_vat_reconciliation_run_id)",
        "同一增值税勾稽批次只能关联一份申报缴款档案。",
    )

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            for field_name in _CN_ARCHIVE_FIELDS:
                values.pop(field_name, None)
        return super().create(vals_list)

    def write(self, values):
        changed = set(values)
        transition = (
            self.env.context.get("cn_filing_archive_transition")
            is _CN_ARCHIVE_TRANSITION_MARKER
        )
        if changed & _CN_ARCHIVE_FIELDS and not transition:
            raise AccessError(_("中国申报缴款档案封存字段只能由受控流程写入。"))
        if "cn_vat_reconciliation_run_id" in changed and any(
            filing.state != "draft" for filing in self
        ) and self.env.context.get(
            "cn_filing_archive_link"
        ) is not _CN_ARCHIVE_LINK_MARKER:
            raise UserError(_("进入准备流程后不能更换中国增值税勾稽来源。"))
        return super().write(values)

    @api.constrains(
        "cn_vat_reconciliation_run_id",
        "profile_id",
        "period_start",
        "period_end",
        "filing_code",
        "filing_type",
        "obligation_id",
    )
    def _check_cn_vat_archive_scope(self):
        for filing in self.filtered("cn_vat_reconciliation_run_id"):
            run = filing.cn_vat_reconciliation_run_id
            if filing.country_id.code != "CN":
                raise ValidationError(_("中国增值税档案只能关联中国合规档案。"))
            if run.profile_id != filing.profile_id or run.company_id != filing.company_id:
                raise ValidationError(_("增值税勾稽来源必须属于当前公司和合规档案。"))
            if (
                run.period_start != filing.period_start
                or run.period_end != filing.period_end
            ):
                raise ValidationError(_("增值税勾稽来源与申报档案期间必须完全一致。"))
            if (filing.filing_code or "").strip().upper() != "CN-VAT":
                raise ValidationError(_("受控增值税档案的申报编码必须为 CN-VAT。"))
            if (filing.filing_type or "").strip().lower() != "cn_vat_return":
                raise ValidationError(
                    _("受控增值税档案的申报类型必须为 cn_vat_return。")
                )
            if not filing.obligation_id or filing.obligation_id.code != "CN-VAT":
                raise ValidationError(_("受控增值税档案必须关联 CN-VAT 适用义务。"))

    @api.depends(
        "cn_vat_reconciliation_run_id",
        "cn_vat_reconciliation_run_id.payment_record_ids",
    )
    def _compute_cn_payment_totals(self):
        for filing in self:
            succeeded = reversed_amount = refunded = 0.0
            for record in filing.cn_tax_payment_record_ids:
                amount = abs(float(record.amount or 0.0))
                if record.payment_status == "succeeded":
                    succeeded += amount
                elif record.payment_status == "reversed":
                    reversed_amount += amount
                elif record.payment_status == "refunded":
                    refunded += amount
            currency = filing.cn_currency_id
            filing.cn_succeeded_payment_amount = (
                currency.round(succeeded) if currency else succeeded
            )
            filing.cn_reversed_payment_amount = (
                currency.round(reversed_amount) if currency else reversed_amount
            )
            filing.cn_refunded_payment_amount = (
                currency.round(refunded) if currency else refunded
            )
            net = succeeded - reversed_amount - refunded
            filing.cn_net_payment_amount = currency.round(net) if currency else net

    def _cn_source_record(self, *, require_current):
        self.ensure_one()
        run = self.cn_vat_reconciliation_run_id
        if not run:
            raise UserError(_("请先关联中国增值税期间勾稽结果。"))
        allowed_states = {"succeeded"} if require_current else {"succeeded", "superseded"}
        if run.state not in allowed_states:
            raise UserError(_("只有当前成功的增值税勾稽结果可以形成申报档案。"))
        if not run.result_checksum or not run.filing_snapshot_checksum:
            raise UserError(_("增值税勾稽结果缺少受控申报快照校验和。"))
        if run.filing_source_state != "available":
            raise UserError(_("增值税申报来源存在阻断，不能登记正式申报。"))
        records = run.filing_record_ids
        if len(records) != 1:
            raise UserError(_("正式申报档案必须对应唯一一份受控增值税申报记录。"))
        record = records
        if require_current and not record.is_current_result:
            raise UserError(_("受控增值税申报已被替代，请先重新执行期间勾稽。"))
        if record.dataset_id._current_integrity_state() != "verified":
            raise UserError(_("受控增值税申报源文件完整性校验失败。"))
        if record.quality_state == "error":
            raise UserError(_("受控增值税申报存在数据错误，不能登记正式申报。"))
        if record.return_status not in {"submitted", "accepted", "amended"}:
            raise UserError(_("受控增值税申报状态不是已申报、已受理或更正申报。"))
        if not record.submitted_at or not record.submission_reference:
            raise UserError(_("正式申报档案要求受控申报同时具有申报时间和参考号。"))
        if record.currency_id != run.currency_id:
            raise UserError(_("受控增值税申报币种与档案币种不一致。"))
        return record

    def _cn_validate_obligation(self):
        self.ensure_one()
        obligation = self.obligation_id
        if not obligation or obligation.code != "CN-VAT":
            raise UserError(_("请先关联当前合规档案的 CN-VAT 适用义务。"))
        if obligation.applicability != "applicable":
            raise UserError(_("CN-VAT 义务尚未经过公司级适用性确认。"))
        if not obligation.filing_required or obligation.filing_type != "cn_vat_return":
            raise UserError(_("CN-VAT 义务未配置为增值税申报义务。"))
        if obligation.effective_from > self.period_end or (
            obligation.effective_to
            and obligation.effective_to < self.period_start
        ):
            raise UserError(_("CN-VAT 适用义务在当前申报期间内无效。"))
        source = obligation.authority_source_id
        today = fields.Date.context_today(self)
        if (
            not source
            or source.status != "valid"
            or not source._is_publishable_snapshot()
            or source.next_review_date < today
        ):
            raise UserError(_("CN-VAT 义务的官方依据尚未有效复核或已经过期。"))
        return obligation

    def _cn_verified_evidence(self, evidence_types):
        self.ensure_one()
        evidence = self.evidence_ids.filtered(
            lambda evidence: evidence.state == "verified"
            and evidence.evidence_type in evidence_types
            and bool(evidence.document_checksum)
        )
        if any(
            item._document_fingerprint()["document_checksum"]
            != item.document_checksum
            for item in evidence
        ):
            raise UserError(_("已验证的正式证据内容已经变化，请停止使用并重新复核。"))
        return evidence

    @api.model
    def _cn_evidence_payload(self, evidence_records):
        return [
            {
                "evidence_id": evidence.id,
                "evidence_type": evidence.evidence_type,
                "document_checksum": evidence.document_checksum,
                "current_document_checksum": evidence._document_fingerprint()[
                    "document_checksum"
                ],
                "verified_at": _datetime_string(evidence.verified_at),
                "verified_by_id": evidence.verified_by_id.id or None,
            }
            for evidence in evidence_records.sorted("id")
        ]

    @api.model
    def _cn_submission_date(self, record):
        submitted_at = fields.Datetime.to_datetime(record.submitted_at)
        localized = submitted_at.replace(tzinfo=timezone.utc).astimezone(_CN_TIMEZONE)
        return localized.date()

    def _cn_submission_payload(self, record, evidence_records):
        self.ensure_one()
        run = self.cn_vat_reconciliation_run_id
        obligation = self.obligation_id
        return {
            "schema": "sdoo.cn.vat-filing-archive.v1",
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
                "authority_source_checksum": (
                    obligation.authority_source_id.content_hash
                ),
                "justification_checksum": hashlib.sha256(
                    (obligation.justification or "").strip().encode("utf-8")
                ).hexdigest(),
            },
            "reconciliation": {
                "run_id": run.id,
                "result_checksum": run.result_checksum,
                "filing_snapshot_checksum": run.filing_snapshot_checksum,
            },
            "filing_record": {
                "record_id": record.id,
                "record_checksum": record.record_checksum,
                "parse_run_id": record.parse_run_id.id,
                "parse_run_checksum": record.parse_run_id.output_checksum,
                "dataset_id": record.dataset_id.id,
                "dataset_seal_checksum": record.dataset_id.seal_checksum,
            },
            "submission_date": _date_string(self.submission_date),
            "submission_reference": self.submission_reference or None,
            "verified_evidence": self._cn_evidence_payload(evidence_records),
        }

    def _cn_payment_payload(self, evidence_records):
        self.ensure_one()
        run = self.cn_vat_reconciliation_run_id
        records = run.payment_record_ids.sorted("id")
        return {
            "schema": "sdoo.cn.vat-payment-archive.v1",
            "company_id": self.company_id.id,
            "profile_id": self.profile_id.id,
            "filing_id": self.id,
            "period_start": _date_string(self.period_start),
            "period_end": _date_string(self.period_end),
            "reconciliation": {
                "run_id": run.id,
                "result_checksum": run.result_checksum,
                "payment_snapshot_checksum": run.payment_snapshot_checksum,
                "filing_payment_difference": str(
                    run.currency_id.round(run.filing_payment_difference)
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
                }
                for record in records
            ],
            "payment_totals": {
                "succeeded": str(self.cn_succeeded_payment_amount),
                "reversed": str(self.cn_reversed_payment_amount),
                "refunded": str(self.cn_refunded_payment_amount),
                "net": str(self.cn_net_payment_amount),
            },
            "payment_date": _date_string(self.payment_date),
            "payment_reference": self.payment_reference or None,
            "verified_evidence": self._cn_evidence_payload(evidence_records),
        }

    def _cn_validate_submission(self):
        self.ensure_one()
        self._cn_validate_obligation()
        record = self._cn_source_record(require_current=True)
        expected_date = self._cn_submission_date(record)
        if self.submission_date != expected_date:
            raise UserError(
                _(
                    "实际提交日期必须与受控申报时间对应的中国日期 %(date)s 一致。",
                    date=fields.Date.to_string(expected_date),
                )
            )
        if self.submission_reference != record.submission_reference:
            raise UserError(_("官方提交参考号必须与受控增值税申报记录一致。"))
        evidence = self._cn_verified_evidence(
            {"filing_receipt", "external_reference"}
        )
        if not evidence:
            raise UserError(_("登记中国增值税申报前必须具有已验证的正式申报回执证据。"))
        return record, evidence

    def _cn_validate_payment(self):
        self.ensure_one()
        run = self.cn_vat_reconciliation_run_id
        self._cn_source_record(require_current=False)
        if not run.payment_snapshot_checksum or run.payment_source_state != "available":
            raise UserError(_("增值税缴款来源存在阻断，不能登记已缴款。"))
        records = run.payment_record_ids
        effective = records.filtered(
            lambda record: record.payment_status in {"succeeded", "reversed", "refunded"}
        )
        succeeded = effective.filtered(lambda record: record.payment_status == "succeeded")
        if not succeeded:
            raise UserError(_("没有受控的缴款成功记录，不能登记已缴款。"))
        for record in records:
            if record.dataset_id._current_integrity_state() != "verified":
                raise UserError(_("受控缴款源文件完整性校验失败。"))
            if record.quality_state == "error":
                raise UserError(_("受控缴款记录存在数据错误，不能登记已缴款。"))
            if record.currency_id != run.currency_id:
                raise UserError(_("受控缴款记录币种与档案币种不一致。"))
        if not run.has_filing_payment_difference or not run.currency_id.is_zero(
            run.filing_payment_difference
        ):
            raise UserError(_("申报应纳税额与有效缴款净额尚未勾稽一致，不能标记全部已付款。"))
        effective_dates = effective.mapped("payment_date")
        expected_date = max(effective_dates) if effective_dates else False
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
        evidence = self._cn_verified_evidence(
            {"payment_proof", "external_reference"}
        )
        if not evidence:
            raise UserError(_("登记中国增值税已缴款前必须具有已验证的正式缴款证据。"))
        return evidence

    def action_ready(self):
        for filing in self.filtered("cn_vat_reconciliation_run_id"):
            filing._cn_validate_obligation()
            filing._cn_source_record(require_current=True)
        return super().action_ready()

    def action_submit(self):
        payloads = {}
        for filing in self.filtered("cn_vat_reconciliation_run_id"):
            record, evidence = filing._cn_validate_submission()
            payload = filing._cn_submission_payload(record, evidence)
            payloads[filing.id] = (payload, evidence)
        result = super().action_submit()
        sealed_at = fields.Datetime.now()
        for filing in self.filtered("cn_vat_reconciliation_run_id"):
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
                "cn.vat_filing_archive.sealed",
                previous_state="ready",
                new_state="submitted",
                details={
                    "reconciliation_run_id": filing.cn_vat_reconciliation_run_id.id,
                    "previous_checksum": previous_checksum,
                    "archive_checksum": filing.cn_submission_checksum,
                    "evidence_ids": evidence.ids,
                },
            )
        return result

    def action_mark_paid(self):
        payloads = {}
        for filing in self.filtered("cn_vat_reconciliation_run_id"):
            evidence = filing._cn_validate_payment()
            payload = filing._cn_payment_payload(evidence)
            payloads[filing.id] = (payload, evidence)
        result = super().action_mark_paid()
        sealed_at = fields.Datetime.now()
        for filing in self.filtered("cn_vat_reconciliation_run_id"):
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
                "cn.vat_payment_archive.sealed",
                previous_state="pending",
                new_state="paid",
                details={
                    "reconciliation_run_id": filing.cn_vat_reconciliation_run_id.id,
                    "archive_checksum": filing.cn_payment_checksum,
                    "evidence_ids": evidence.ids,
                },
            )
        return result

    def _cn_submission_integrity(self):
        self.ensure_one()
        if not self.cn_vat_reconciliation_run_id:
            return "not_applicable"
        if not self.cn_submission_checksum:
            return "unsealed"
        try:
            record = self._cn_source_record(require_current=False)
            evidence = self.cn_submission_evidence_ids
            if not evidence or any(item.state != "verified" for item in evidence):
                return "invalid"
            payload = self._cn_submission_payload(record, evidence)
        except (UserError, ValidationError):
            return "invalid"
        if _checksum(payload) != self.cn_submission_checksum:
            return "changed"
        if (
            self.cn_vat_reconciliation_run_id.state == "superseded"
            or not record.is_current_result
        ):
            return "source_superseded"
        return "verified"

    def _cn_payment_integrity(self):
        self.ensure_one()
        if not self.cn_vat_reconciliation_run_id:
            return "not_applicable"
        if not self.payment_required:
            return "not_required"
        if not self.cn_payment_checksum:
            return "unsealed"
        try:
            self._cn_source_record(require_current=False)
            evidence = self.cn_payment_evidence_ids
            if not evidence or any(item.state != "verified" for item in evidence):
                return "invalid"
            for record in self.cn_tax_payment_record_ids:
                if record.dataset_id._current_integrity_state() != "verified":
                    return "invalid"
            payload = self._cn_payment_payload(evidence)
        except (UserError, ValidationError):
            return "invalid"
        if _checksum(payload) != self.cn_payment_checksum:
            return "changed"
        if self.cn_vat_reconciliation_run_id.state == "superseded":
            return "source_superseded"
        return "verified"

    def _compute_cn_archive_states(self):
        for filing in self:
            filing.cn_submission_integrity_state = filing._cn_submission_integrity()
            filing.cn_payment_integrity_state = filing._cn_payment_integrity()

    def action_open_cn_vat_reconciliation(self):
        self.ensure_one()
        if not self.cn_vat_reconciliation_run_id:
            raise UserError(_("当前申报档案没有关联中国增值税勾稽结果。"))
        return {
            "type": "ir.actions.act_window",
            "name": _("增值税期间四方勾稽"),
            "res_model": "sudo.cn.vat.period.reconciliation.run",
            "res_id": self.cn_vat_reconciliation_run_id.id,
            "view_mode": "form",
            "views": [
                (
                    self.env.ref(
                        "sudo_country_pack_cn.view_cn_vat_period_reconciliation_run_form"
                    ).id,
                    "form",
                )
            ],
            "target": "current",
        }


class SudoChinaVatPeriodReconciliationRun(models.Model):
    _inherit = "sudo.cn.vat.period.reconciliation.run"

    filing_archive_count = fields.Integer(
        string="申报缴款档案数",
        compute="_compute_filing_archive_count",
    )

    def _compute_filing_archive_count(self):
        grouped = self.env["sudo.compliance.filing"]._read_group(
            [("cn_vat_reconciliation_run_id", "in", self.ids)],
            ["cn_vat_reconciliation_run_id"],
            ["__count"],
        ) if self else []
        counts = {run.id: count for run, count in grouped}
        for run in self:
            run.filing_archive_count = counts.get(run.id, 0)

    def action_open_cn_filing_archive(self):
        self.ensure_one()
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以建立申报缴款档案。"))
        filing_model = self.env["sudo.compliance.filing"].with_company(
            self.company_id
        )
        filing = filing_model.search(
            [("cn_vat_reconciliation_run_id", "=", self.id)],
            limit=1,
        )
        if not filing:
            filing = filing_model.search(
                [
                    ("profile_id", "=", self.profile_id.id),
                    ("filing_code", "=", "CN-VAT"),
                    ("period_start", "=", self.period_start),
                    ("period_end", "=", self.period_end),
                ],
                limit=1,
            )
        if (
            filing
            and not filing.cn_vat_reconciliation_run_id
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
                cn_filing_archive_link=_CN_ARCHIVE_LINK_MARKER
            ).write({"cn_vat_reconciliation_run_id": self.id})
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
            raise UserError(_("只有当前成功的增值税勾稽结果可以新建申报缴款档案。"))
        filing_record = self.filing_record_ids[:1] if len(self.filing_record_ids) == 1 else self.env["sudo.cn.vat.filing.record"]
        obligation = self.env["sudo.compliance.obligation"].search(
            [
                ("profile_id", "=", self.profile_id.id),
                ("code", "=", "CN-VAT"),
                ("active", "=", True),
            ],
            limit=1,
        )
        defaults = {
            "default_filing_name": _("增值税纳税申报"),
            "default_profile_id": self.profile_id.id,
            "default_obligation_id": obligation.id or False,
            "default_filing_code": "CN-VAT",
            "default_filing_type": "cn_vat_return",
            "default_authority": obligation.authority or False,
            "default_period_start": self.period_start,
            "default_period_end": self.period_end,
            "default_assignee_id": self.env.user.id,
            "default_payment_required": bool(
                filing_record
                and filing_record.has_tax_payable_amount
                and not self.currency_id.is_zero(filing_record.tax_payable_amount)
            ),
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
            "default_cn_vat_reconciliation_run_id": self.id,
        }
        effective_payments = self.payment_record_ids.filtered(
            lambda record: record.payment_status in {"succeeded", "reversed", "refunded"}
        )
        if len(effective_payments) == 1:
            defaults.update(
                {
                    "default_payment_date": effective_payments.payment_date,
                    "default_payment_reference": effective_payments.payment_reference,
                }
            )
        action["context"] = defaults
        return action
