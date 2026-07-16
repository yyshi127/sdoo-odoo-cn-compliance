from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import re

from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from ..services.tax_data_contract import (
    CONTRACT_SCHEMA,
    TaxDataContractError,
    load_tax_data_contract,
)


_TAX_PARSE_RUN_MARKER = object()
_TAX_NORMALIZED_RECORD_MARKER = object()
TAX_DATA_MAPPING_KEY = "sdoo_cn_controlled_tax_json"
TAX_DATA_MAPPING_VERSION = "1.0"
TAX_DATA_RECORD_MODELS = {
    "vat_filing": "sudo.cn.vat.filing.record",
    "cit_filing": "sudo.cn.cit.filing.record",
    "iit_withholding": "sudo.cn.iit.withholding.record",
    "payroll_summary": "sudo.cn.payroll.summary.record",
    "tax_payment": "sudo.cn.tax.payment.record",
}
TAX_DATA_COUNT_FIELDS = {
    "vat_filing": "vat_filing_count",
    "cit_filing": "cit_filing_count",
    "iit_withholding": "iit_withholding_count",
    "payroll_summary": "payroll_summary_count",
    "tax_payment": "tax_payment_count",
}
TAX_DATA_KIND_LABELS = {
    "vat_filing": "增值税申报",
    "cit_filing": "企业所得税申报",
    "iit_withholding": "个人所得税扣缴申报",
    "payroll_summary": "工资薪酬汇总",
    "tax_payment": "税款缴纳",
}


def _safe_text(value, limit=None):
    if value in (None, False):
        return False
    text = " ".join(str(value).split()).strip()
    if not text:
        return False
    return text[:limit] if limit else text


def _sha256_json(payload):
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _normalized_sha256(value):
    candidate = (_safe_text(value, 64) or "").lower()
    return candidate if re.fullmatch(r"[0-9a-f]{64}", candidate) else False


class SudoChinaTaxDataParseRun(models.Model):
    _name = "sudo.cn.tax.data.parse.run"
    _description = "China Tax Filing and Payment Import Run"
    _order = "started_at desc, id desc"
    _check_company_auto = True

    name = fields.Char(compute="_compute_name", store=True)
    dataset_id = fields.Many2one(
        "sudo.cn.external.dataset",
        string="外部数据集",
        required=True,
        ondelete="restrict",
        check_company=True,
        readonly=True,
        index=True,
    )
    dataset_type = fields.Selection(
        related="dataset_id.dataset_type",
        store=True,
        readonly=True,
        index=True,
    )
    profile_id = fields.Many2one(
        related="dataset_id.profile_id",
        store=True,
        readonly=True,
        index=True,
    )
    company_id = fields.Many2one(
        related="dataset_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    country_id = fields.Many2one(
        related="dataset_id.country_id",
        store=True,
        readonly=True,
    )
    input_attachment_id = fields.Many2one(
        "ir.attachment",
        string="导入源文件",
        required=True,
        ondelete="restrict",
        readonly=True,
    )
    input_sha256 = fields.Char(
        string="导入源文件 SHA-256",
        required=True,
        readonly=True,
    )
    dataset_seal_checksum = fields.Char(
        string="数据集封存校验和",
        required=True,
        readonly=True,
    )
    contract_schema = fields.Char(
        string="标准化契约",
        required=True,
        readonly=True,
    )
    source_schema = fields.Char(string="源数据结构", readonly=True)
    source_schema_version = fields.Char(string="源结构版本", readonly=True)
    mapping_key = fields.Char(
        string="映射键",
        required=True,
        readonly=True,
    )
    mapping_version = fields.Char(
        string="映射版本",
        required=True,
        readonly=True,
    )
    contract_checksum = fields.Char(
        string="标准化输入 SHA-256",
        readonly=True,
    )
    state = fields.Selection(
        [
            ("running", "导入中"),
            ("succeeded", "成功"),
            ("failed", "失败"),
            ("superseded", "已被新结果替代"),
        ],
        string="状态",
        required=True,
        default="running",
        readonly=True,
        index=True,
    )
    started_at = fields.Datetime(
        string="开始时间",
        required=True,
        readonly=True,
    )
    started_by_id = fields.Many2one(
        "res.users",
        string="执行人",
        required=True,
        readonly=True,
    )
    finished_at = fields.Datetime(string="完成时间", readonly=True)
    record_count = fields.Integer(string="规范化记录数", readonly=True)
    valid_record_count = fields.Integer(string="正常记录数", readonly=True)
    warning_record_count = fields.Integer(string="警告记录数", readonly=True)
    error_record_count = fields.Integer(string="异常记录数", readonly=True)
    vat_filing_count = fields.Integer(string="增值税申报数", readonly=True)
    cit_filing_count = fields.Integer(string="企业所得税申报数", readonly=True)
    iit_withholding_count = fields.Integer(
        string="个人所得税扣缴申报数", readonly=True
    )
    payroll_summary_count = fields.Integer(string="工资薪酬汇总数", readonly=True)
    tax_payment_count = fields.Integer(string="税款缴纳数", readonly=True)
    output_checksum = fields.Char(string="规范化输出 SHA-256", readonly=True)
    error_code = fields.Char(string="失败代码", readonly=True)
    result_summary = fields.Text(string="结果摘要", readonly=True)
    vat_filing_record_ids = fields.One2many(
        "sudo.cn.vat.filing.record",
        "parse_run_id",
        string="规范化增值税申报",
        readonly=True,
    )
    cit_filing_record_ids = fields.One2many(
        "sudo.cn.cit.filing.record",
        "parse_run_id",
        string="规范化企业所得税申报",
        readonly=True,
    )
    iit_withholding_record_ids = fields.One2many(
        "sudo.cn.iit.withholding.record",
        "parse_run_id",
        string="规范化个人所得税扣缴申报",
        readonly=True,
    )
    payroll_summary_record_ids = fields.One2many(
        "sudo.cn.payroll.summary.record",
        "parse_run_id",
        string="规范化工资薪酬汇总",
        readonly=True,
    )
    tax_payment_record_ids = fields.One2many(
        "sudo.cn.tax.payment.record",
        "parse_run_id",
        string="规范化税款缴纳",
        readonly=True,
    )

    @api.depends(
        "dataset_id",
        "mapping_key",
        "mapping_version",
        "started_at",
    )
    def _compute_name(self):
        for run in self:
            started = fields.Datetime.to_string(run.started_at) or "-"
            run.name = "%s / %s %s / %s" % (
                run.dataset_id.display_name or _("申报缴税导入"),
                run.mapping_key or "-",
                run.mapping_version or "-",
                started,
            )

    @api.model_create_multi
    def create(self, vals_list):
        if (
            self.env.context.get("cn_tax_parse_run_transition")
            is not _TAX_PARSE_RUN_MARKER
        ):
            raise AccessError(_("申报缴税导入运行只能由受控流程创建。"))
        for values in vals_list:
            values.update(
                {
                    "state": "running",
                    "finished_at": False,
                    "source_schema": False,
                    "source_schema_version": False,
                    "contract_checksum": False,
                    "record_count": 0,
                    "valid_record_count": 0,
                    "warning_record_count": 0,
                    "error_record_count": 0,
                    "vat_filing_count": 0,
                    "cit_filing_count": 0,
                    "iit_withholding_count": 0,
                    "payroll_summary_count": 0,
                    "tax_payment_count": 0,
                    "output_checksum": False,
                    "error_code": False,
                    "result_summary": False,
                }
            )
        return super().create(vals_list)

    def write(self, values):
        if (
            self.env.context.get("cn_tax_parse_run_transition")
            is not _TAX_PARSE_RUN_MARKER
        ):
            raise AccessError(_("申报缴税导入运行只能由受控流程更新。"))
        return super().write(values)

    def unlink(self):
        raise AccessError(_("申报缴税导入运行属于审计记录，不可删除。"))

    @api.model
    def _require_manager(self):
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以导入申报与缴税数据。"))

    @api.model
    def _start_for_dataset(
        self,
        dataset,
        input_attachment,
        *,
        mapping_key=TAX_DATA_MAPPING_KEY,
        mapping_version=TAX_DATA_MAPPING_VERSION,
    ):
        self._require_manager()
        dataset.ensure_one()
        input_attachment.ensure_one()
        if dataset.dataset_type not in TAX_DATA_RECORD_MODELS:
            raise UserError(_("当前导入契约不支持该申报缴税数据集类型。"))
        if dataset.state != "sealed":
            raise UserError(_("只有当前已封存的数据集可以导入。"))
        if dataset._current_integrity_state() != "verified":
            raise UserError(_("数据集文件完整性异常，不能开始导入。"))
        if dataset.data_format != "json":
            raise UserError(_("当前受控导入契约只接受 UTF-8 JSON 文件。"))
        source_attachments = dataset._controlled_source_attachments()
        if len(source_attachments) != 1:
            raise UserError(_("当前受控导入要求数据集只能包含一份标准化 JSON 源文件。"))
        if input_attachment not in source_attachments:
            raise UserError(_("导入源文件必须属于当前数据集。"))
        attachment = input_attachment.sudo()
        if attachment.type != "binary" or attachment.file_size <= 0:
            raise UserError(_("导入源文件必须是非空二进制附件。"))
        mapping_key = _safe_text(mapping_key, 128)
        mapping_version = _safe_text(mapping_version, 64)
        if not mapping_key or not mapping_version:
            raise UserError(_("映射键和映射版本不能为空。"))
        manifest = dataset.sealed_file_manifest_json or {}
        manifest_entry = next(
            (
                item
                for item in manifest.get("source_attachments", [])
                if item.get("id") == input_attachment.id
            ),
            None,
        )
        input_sha256 = manifest_entry and _normalized_sha256(
            manifest_entry.get("sha256")
        )
        if not input_sha256:
            raise UserError(_("封存清单中没有导入源文件的有效 SHA-256。"))
        self.env.cr.execute(
            "SELECT id FROM sudo_cn_external_dataset WHERE id = %s FOR UPDATE",
            [dataset.id],
        )
        running = self.search(
            [("dataset_id", "=", dataset.id), ("state", "=", "running")],
            limit=1,
        )
        if running:
            raise UserError(_("该数据集已有正在执行的申报缴税导入。"))
        run = self.with_context(
            cn_tax_parse_run_transition=_TAX_PARSE_RUN_MARKER
        ).create(
            {
                "dataset_id": dataset.id,
                "input_attachment_id": input_attachment.id,
                "input_sha256": input_sha256,
                "dataset_seal_checksum": dataset.seal_checksum,
                "contract_schema": CONTRACT_SCHEMA,
                "mapping_key": mapping_key,
                "mapping_version": mapping_version,
                "started_at": fields.Datetime.now(),
                "started_by_id": self.env.user.id,
            }
        )
        self.env["sudo.compliance.audit.event"]._log_records(
            run,
            "cn_tax_data_import.started",
            new_state="running",
            details={
                "dataset_id": dataset.id,
                "dataset_type": dataset.dataset_type,
                "input_attachment_id": input_attachment.id,
                "input_sha256": input_sha256,
                "dataset_seal_checksum": dataset.seal_checksum,
                "mapping_key": mapping_key,
                "mapping_version": mapping_version,
            },
        )
        return run.with_context(cn_tax_parse_run_transition=None)

    def _record_failure(self, error_code, summary):
        self.ensure_one()
        if self.state != "running":
            raise UserError(_("只有导入中的运行可以记录失败。"))
        values = {
            "state": "failed",
            "finished_at": fields.Datetime.now(),
            "error_code": _safe_text(error_code, 128) or "IMPORT_FAILED",
            "result_summary": _safe_text(summary, 2000) or _("导入失败。"),
        }
        self.with_context(
            cn_tax_parse_run_transition=_TAX_PARSE_RUN_MARKER
        ).write(values)
        self.env["sudo.compliance.audit.event"]._log_records(
            self,
            "cn_tax_data_import.failed",
            previous_state="running",
            new_state="failed",
            details={"error_code": values["error_code"]},
        )
        return False

    def _process_json_attachment(self):
        self.ensure_one()
        if self.state != "running":
            raise UserError(_("只有导入中的运行可以处理源文件。"))
        raw = self.input_attachment_id.sudo().raw or b""
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        else:
            raw = bytes(raw)
        observed_hash = hashlib.sha256(raw).hexdigest()
        if observed_hash != self.input_sha256:
            return self._record_failure(
                "INPUT_HASH_MISMATCH",
                _("导入进程读取的文件与封存文件哈希不一致。"),
            )
        try:
            contract = load_tax_data_contract(
                raw,
                expected_dataset_type=self.dataset_type,
            )
        except TaxDataContractError as exc:
            return self._record_failure(
                "INVALID_TAX_DATA_CONTRACT",
                _safe_text(exc, 1000),
            )
        if self.dataset_id.declared_record_count != len(contract.records):
            return self._record_failure(
                "DECLARED_RECORD_COUNT_MISMATCH",
                _("数据集声明记录数与标准化契约记录数不一致。"),
            )
        return self._record_success(contract)

    def _record_success(self, contract):
        self.ensure_one()
        if self.state != "running":
            raise UserError(_("只有导入中的运行可以记录成功结果。"))
        if contract.dataset_type != self.dataset_type:
            return self._record_failure(
                "DATASET_TYPE_MISMATCH",
                _("标准化契约类型与数据集类型不一致。"),
            )
        model_name = TAX_DATA_RECORD_MODELS[self.dataset_type]
        record_model = self.env[model_name]
        previous_runs = self.browse()
        try:
            with self.env.cr.savepoint():
                prepared = [
                    record_model._prepare_import_values(self, payload)
                    for payload in contract.records
                ]
                created = record_model.with_context(
                    cn_tax_normalized_record_transition=(
                        _TAX_NORMALIZED_RECORD_MARKER
                    )
                ).create(prepared)
                output_checksum = _sha256_json(
                    sorted(created.mapped("record_checksum"))
                )
                previous_runs = self.search(
                    [
                        ("dataset_id", "=", self.dataset_id.id),
                        ("state", "=", "succeeded"),
                        ("id", "!=", self.id),
                    ]
                )
                previous_runs.with_context(
                    cn_tax_parse_run_transition=_TAX_PARSE_RUN_MARKER
                ).write({"state": "superseded"})
                valid_count = len(
                    created.filtered(lambda item: item.quality_state == "valid")
                )
                warning_count = len(
                    created.filtered(
                        lambda item: item.quality_state == "warning"
                    )
                )
                error_count = len(
                    created.filtered(lambda item: item.quality_state == "error")
                )
                values = {
                    "state": "succeeded",
                    "finished_at": fields.Datetime.now(),
                    "source_schema": contract.source_schema,
                    "source_schema_version": contract.source_schema_version,
                    "contract_checksum": contract.checksum,
                    "record_count": len(created),
                    "valid_record_count": valid_count,
                    "warning_record_count": warning_count,
                    "error_record_count": error_count,
                    "vat_filing_count": 0,
                    "cit_filing_count": 0,
                    "iit_withholding_count": 0,
                    "payroll_summary_count": 0,
                    "tax_payment_count": 0,
                    "output_checksum": output_checksum,
                    "error_code": False,
                    "result_summary": _(
                        "已生成 %(count)s 条规范化%(kind)s记录：正常 "
                        "%(valid)s，警告 %(warning)s，异常 %(error)s。",
                        count=len(created),
                        kind=_(TAX_DATA_KIND_LABELS[self.dataset_type]),
                        valid=valid_count,
                        warning=warning_count,
                        error=error_count,
                    ),
                }
                values[TAX_DATA_COUNT_FIELDS[self.dataset_type]] = len(created)
                self.with_context(
                    cn_tax_parse_run_transition=_TAX_PARSE_RUN_MARKER
                ).write(values)
        except (TypeError, ValueError, ValidationError, UserError) as exc:
            return self._record_failure(
                "NORMALIZATION_FAILED",
                _safe_text(exc, 1000) or _("规范化输出校验失败。"),
            )
        for previous in previous_runs:
            self.env["sudo.compliance.audit.event"]._log_records(
                previous,
                "cn_tax_data_import.superseded",
                previous_state="succeeded",
                new_state="superseded",
                details={"replacement_run_id": self.id},
            )
        self.env["sudo.compliance.audit.event"]._log_records(
            self,
            "cn_tax_data_import.succeeded",
            previous_state="running",
            new_state="succeeded",
            details={
                "input_sha256": self.input_sha256,
                "contract_checksum": self.contract_checksum,
                "output_checksum": self.output_checksum,
                "record_count": self.record_count,
                "valid_record_count": self.valid_record_count,
                "warning_record_count": self.warning_record_count,
                "error_record_count": self.error_record_count,
            },
        )
        return True


class SudoChinaTaxNormalizedRecordMixin(models.AbstractModel):
    _name = "sudo.cn.tax.normalized.record.mixin"
    _description = "China Normalized Tax Record Mixin"
    _check_company_auto = True
    _source_dataset_type = False

    parse_run_id = fields.Many2one(
        "sudo.cn.tax.data.parse.run",
        string="导入运行",
        required=True,
        ondelete="restrict",
        check_company=True,
        readonly=True,
        index=True,
    )
    dataset_id = fields.Many2one(
        related="parse_run_id.dataset_id",
        store=True,
        readonly=True,
        index=True,
    )
    profile_id = fields.Many2one(
        related="parse_run_id.profile_id",
        store=True,
        readonly=True,
        index=True,
    )
    company_id = fields.Many2one(
        related="parse_run_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    country_id = fields.Many2one(
        related="parse_run_id.country_id",
        store=True,
        readonly=True,
    )
    source_coverage_scope = fields.Selection(
        related="dataset_id.coverage_scope",
        string="源数据覆盖范围",
        store=True,
        readonly=True,
    )
    source_authenticity_state = fields.Selection(
        related="dataset_id.authenticity_state",
        string="源数据真实性验证",
        store=True,
        readonly=True,
    )
    source_review_control_state = fields.Selection(
        related="dataset_id.review_control_state",
        string="源数据复核控制",
        readonly=True,
    )
    source_integrity_state = fields.Selection(
        related="dataset_id.integrity_state",
        string="源文件完整性",
        readonly=True,
    )
    source_record_key = fields.Char(
        string="源记录键",
        required=True,
        readonly=True,
        index=True,
    )
    taxpayer_name = fields.Char(string="纳税人名称", readonly=True)
    taxpayer_id = fields.Char(
        string="纳税人统一社会信用代码",
        readonly=True,
        index=True,
    )
    period_start = fields.Date(string="税款所属期开始", readonly=True)
    period_end = fields.Date(string="税款所属期结束", readonly=True)
    currency_id = fields.Many2one(
        "res.currency",
        string="币种",
        readonly=True,
    )
    quality_state = fields.Selection(
        [
            ("valid", "字段校验正常"),
            ("warning", "存在数据警告"),
            ("error", "存在数据错误"),
        ],
        string="数据质量",
        required=True,
        readonly=True,
        index=True,
    )
    issue_json = fields.Json(string="数据质量问题", readonly=True)
    record_checksum = fields.Char(
        string="规范化记录 SHA-256",
        required=True,
        readonly=True,
        index=True,
    )
    is_current_result = fields.Boolean(
        string="当前有效导入结果",
        compute="_compute_is_current_result",
        search="_search_is_current_result",
    )

    @api.depends(
        "parse_run_id.state",
        "dataset_id.state",
        "source_integrity_state",
    )
    def _compute_is_current_result(self):
        for record in self:
            record.is_current_result = (
                record.parse_run_id.state == "succeeded"
                and record.dataset_id.state == "sealed"
                and record.source_integrity_state == "verified"
            )

    @api.model
    def _search_is_current_result(self, operator, value):
        if operator not in ("=", "!="):
            raise UserError(_("当前导入结果仅支持等于或不等于筛选。"))
        datasets = self.env["sudo.cn.external.dataset"].search(
            [
                ("dataset_type", "=", self._source_dataset_type),
                ("state", "=", "sealed"),
            ]
        )
        intact_ids = [
            dataset.id
            for dataset in datasets
            if dataset._current_integrity_state() == "verified"
        ]
        positive = (operator == "=" and bool(value)) or (
            operator == "!=" and not bool(value)
        )
        if positive:
            return [
                ("parse_run_id.state", "=", "succeeded"),
                ("dataset_id", "in", intact_ids),
            ]
        return [
            "|",
            ("parse_run_id.state", "!=", "succeeded"),
            ("dataset_id", "not in", intact_ids),
        ]

    @api.model_create_multi
    def create(self, vals_list):
        if (
            self.env.context.get("cn_tax_normalized_record_transition")
            is not _TAX_NORMALIZED_RECORD_MARKER
        ):
            raise AccessError(_("规范化申报缴税记录只能由受控导入流程创建。"))
        return super().create(vals_list)

    def write(self, values):
        raise AccessError(_("规范化申报缴税记录不可修改，请重新执行受控导入。"))

    def unlink(self):
        raise AccessError(_("规范化申报缴税记录属于导入审计结果，不可删除。"))

    def copy(self, default=None):
        raise AccessError(_("规范化申报缴税记录不可复制。"))

    @api.model
    def _issue(self, code, severity, message):
        return {"code": code, "severity": severity, "message": message}

    @api.model
    def _parse_decimal(self, value, field_label, issues):
        if value in (None, False, ""):
            return False, 0.0, None
        try:
            decimal_value = Decimal(str(value))
            if not decimal_value.is_finite():
                raise InvalidOperation
            float_value = float(decimal_value)
            if not math.isfinite(float_value):
                raise InvalidOperation
        except (InvalidOperation, OverflowError, TypeError, ValueError):
            issues.append(
                self._issue(
                    "INVALID_AMOUNT",
                    "error",
                    _("%(field)s格式无效", field=field_label),
                )
            )
            return False, 0.0, None
        return True, float_value, format(decimal_value, "f")

    @api.model
    def _parse_date(self, value, field_label, issues):
        if not value:
            return False
        try:
            return fields.Date.to_date(value)
        except (TypeError, ValueError):
            issues.append(
                self._issue(
                    "INVALID_DATE",
                    "error",
                    _("%(field)s格式无效", field=field_label),
                )
            )
            return False

    @api.model
    def _parse_datetime(self, value, field_label, issues):
        if not value:
            return False
        try:
            if isinstance(value, str):
                normalized = value.strip().replace("Z", "+00:00")
                try:
                    parsed = datetime.fromisoformat(normalized)
                except ValueError:
                    parsed = fields.Datetime.to_datetime(value)
            else:
                parsed = fields.Datetime.to_datetime(value)
            if parsed.tzinfo:
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed
        except (TypeError, ValueError):
            issues.append(
                self._issue(
                    "INVALID_DATETIME",
                    "error",
                    _("%(field)s格式无效", field=field_label),
                )
            )
            return False

    @api.model
    def _currency(self, code, issues):
        currency_code = (_safe_text(code, 8) or "").upper()
        if not currency_code:
            issues.append(
                self._issue("MISSING_CURRENCY", "error", _("未提供币种"))
            )
            return self.env["res.currency"]
        currency = self.env["res.currency"].with_context(
            active_test=False
        ).search([("name", "=", currency_code)], limit=1)
        if not currency:
            issues.append(
                self._issue("UNKNOWN_CURRENCY", "error", _("币种代码未识别"))
            )
        return currency

    @api.model
    def _prepare_common(self, run, payload):
        issues = []
        source_key = _safe_text(payload.get("source_record_key"), 512)
        taxpayer_name = _safe_text(payload.get("taxpayer_name"), 512)
        taxpayer_id = (_safe_text(payload.get("taxpayer_id"), 64) or "").upper()
        if not taxpayer_id:
            issues.append(
                self._issue(
                    "MISSING_TAXPAYER_ID",
                    "error",
                    _("缺少纳税人统一社会信用代码"),
                )
            )
        company_vat = (_safe_text(run.company_id.partner_id.vat, 64) or "").upper()
        if not company_vat:
            issues.append(
                self._issue(
                    "MISSING_COMPANY_TAX_ID",
                    "warning",
                    _("Odoo 公司未维护统一社会信用代码"),
                )
            )
        elif taxpayer_id and taxpayer_id != company_vat:
            issues.append(
                self._issue(
                    "TAXPAYER_ENTITY_MISMATCH",
                    "error",
                    _("申报缴税记录纳税人与当前 Odoo 公司不一致"),
                )
            )
        period_start = self._parse_date(
            payload.get("period_start"),
            _("税款所属期开始"),
            issues,
        )
        period_end = self._parse_date(
            payload.get("period_end"),
            _("税款所属期结束"),
            issues,
        )
        if not period_start or not period_end:
            issues.append(
                self._issue(
                    "MISSING_TAX_PERIOD",
                    "error",
                    _("缺少有效的税款所属期"),
                )
            )
        elif period_end < period_start:
            issues.append(
                self._issue(
                    "INVALID_TAX_PERIOD",
                    "error",
                    _("税款所属期结束日早于开始日"),
                )
            )
        elif (
            period_start < run.dataset_id.period_start
            or period_end > run.dataset_id.period_end
        ):
            issues.append(
                self._issue(
                    "TAX_PERIOD_OUTSIDE_DATASET",
                    "error",
                    _("税款所属期超出数据集声明覆盖范围"),
                )
            )
        currency = self._currency(payload.get("currency_code"), issues)
        values = {
            "parse_run_id": run.id,
            "source_record_key": source_key,
            "taxpayer_name": taxpayer_name,
            "taxpayer_id": taxpayer_id or False,
            "period_start": period_start,
            "period_end": period_end,
            "currency_id": currency.id,
        }
        canonical = {
            "source_record_key": source_key,
            "taxpayer_name": taxpayer_name or None,
            "taxpayer_id": taxpayer_id or None,
            "period_start": fields.Date.to_string(period_start),
            "period_end": fields.Date.to_string(period_end),
            "currency_code": currency.name if currency else None,
        }
        return values, canonical, issues, currency

    @api.model
    def _quality_state(self, issues):
        severities = {issue["severity"] for issue in issues}
        if "error" in severities:
            return "error"
        if "warning" in severities:
            return "warning"
        return "valid"

    @api.model
    def _canonical_issues(self, issues):
        return [
            {"code": issue["code"], "severity": issue["severity"]}
            for issue in issues
        ]


class SudoChinaVatFilingRecord(models.Model):
    _name = "sudo.cn.vat.filing.record"
    _description = "China Normalized VAT Filing Record"
    _inherit = "sudo.cn.tax.normalized.record.mixin"
    _order = "period_end desc, submitted_at desc, id desc"
    _source_dataset_type = "vat_filing"

    name = fields.Char(compute="_compute_name", store=True)
    jurisdiction_code = fields.Char(string="主管辖区代码", readonly=True)
    jurisdiction_name = fields.Char(string="主管辖区", readonly=True)
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
    has_taxable_sales_amount = fields.Boolean(
        string="提供应税销售额",
        readonly=True,
    )
    taxable_sales_amount = fields.Monetary(
        string="应税销售额",
        currency_field="currency_id",
        readonly=True,
    )
    has_output_tax_amount = fields.Boolean(string="提供销项税额", readonly=True)
    output_tax_amount = fields.Monetary(
        string="销项税额",
        currency_field="currency_id",
        readonly=True,
    )
    has_input_tax_amount = fields.Boolean(string="提供进项税额", readonly=True)
    input_tax_amount = fields.Monetary(
        string="进项税额",
        currency_field="currency_id",
        readonly=True,
    )
    has_input_tax_transfer_out_amount = fields.Boolean(
        string="提供进项税额转出",
        readonly=True,
    )
    input_tax_transfer_out_amount = fields.Monetary(
        string="进项税额转出",
        currency_field="currency_id",
        readonly=True,
    )
    has_prior_credit_amount = fields.Boolean(
        string="提供期初留抵税额",
        readonly=True,
    )
    prior_credit_amount = fields.Monetary(
        string="期初留抵税额",
        currency_field="currency_id",
        readonly=True,
    )
    has_tax_payable_amount = fields.Boolean(
        string="提供应纳税额",
        readonly=True,
    )
    tax_payable_amount = fields.Monetary(
        string="应纳税额",
        currency_field="currency_id",
        readonly=True,
    )
    has_tax_refund_amount = fields.Boolean(
        string="提供退税额",
        readonly=True,
    )
    tax_refund_amount = fields.Monetary(
        string="退税额",
        currency_field="currency_id",
        readonly=True,
    )
    has_closing_credit_amount = fields.Boolean(
        string="提供期末留抵税额",
        readonly=True,
    )
    closing_credit_amount = fields.Monetary(
        string="期末留抵税额",
        currency_field="currency_id",
        readonly=True,
    )
    line_ids = fields.One2many(
        "sudo.cn.vat.filing.line",
        "filing_record_id",
        string="申报表标准化行",
        readonly=True,
    )

    _source_record_unique = models.Constraint(
        "unique(parse_run_id, source_record_key)",
        "同一导入运行中的增值税申报源记录键必须唯一。",
    )

    @api.depends("return_type_code", "period_start", "period_end")
    def _compute_name(self):
        for record in self:
            record.name = "%s / %s - %s" % (
                record.return_type_code or _("增值税申报"),
                fields.Date.to_string(record.period_start) or "-",
                fields.Date.to_string(record.period_end) or "-",
            )

    @api.model
    def _prepare_line_values(self, payloads, issues):
        commands = []
        canonical = []
        allowed_types = {
            "taxable_base",
            "tax",
            "payable",
            "credit",
            "refund",
            "other",
        }
        for sequence, payload in enumerate(payloads or [], start=1):
            line_code = _safe_text(payload.get("line_code"), 128)
            amount_type = (
                _safe_text(payload.get("amount_type"), 32) or "other"
            ).lower()
            if amount_type not in allowed_types:
                issues.append(
                    self._issue(
                        "UNKNOWN_VAT_LINE_TYPE",
                        "warning",
                        _("申报表行 %(line)s 的金额类型未识别", line=line_code),
                    )
                )
                amount_type = "other"
            has_current, current, current_decimal = self._parse_decimal(
                payload.get("current_amount"),
                _("本期金额"),
                issues,
            )
            has_ytd, ytd, ytd_decimal = self._parse_decimal(
                payload.get("ytd_amount"),
                _("本年累计金额"),
                issues,
            )
            has_rate, rate, rate_decimal = self._parse_decimal(
                payload.get("tax_rate"),
                _("税率"),
                issues,
            )
            if not has_current and not has_ytd:
                issues.append(
                    self._issue(
                        "VAT_LINE_WITHOUT_AMOUNT",
                        "warning",
                        _("申报表行 %(line)s 未提供本期或累计金额", line=line_code),
                    )
                )
            if has_rate and (rate < 0 or rate > 1):
                issues.append(
                    self._issue(
                        "VAT_RATE_OUT_OF_RANGE",
                        "warning",
                        _("申报表行 %(line)s 的税率不在 0 至 1 之间", line=line_code),
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
        values, canonical, issues, currency = self._prepare_common(run, payload)
        raw_status = (_safe_text(payload.get("return_status"), 32) or "unknown")
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
        return_status = status_map.get(raw_status.lower(), status_map.get(raw_status))
        if not return_status:
            return_status = "unknown"
            issues.append(
                self._issue(
                    "UNKNOWN_RETURN_STATUS",
                    "warning",
                    _("增值税申报状态未识别"),
                )
            )
        submitted_at = self._parse_datetime(
            payload.get("submitted_at"),
            _("申报时间"),
            issues,
        )
        submission_reference = _safe_text(
            payload.get("submission_reference"),
            256,
        )
        if return_status in ("submitted", "accepted", "amended") and not (
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
            ("taxable_sales_amount", "应税销售额"),
            ("output_tax_amount", "销项税额"),
            ("input_tax_amount", "进项税额"),
            ("input_tax_transfer_out_amount", "进项税额转出"),
            ("prior_credit_amount", "期初留抵税额"),
            ("tax_payable_amount", "应纳税额"),
            ("tax_refund_amount", "退税额"),
            ("closing_credit_amount", "期末留抵税额"),
        )
        canonical_amounts = {}
        for field_name, label in amount_fields:
            present, amount, decimal_amount = self._parse_decimal(
                payload.get(field_name),
                _(label),
                issues,
            )
            values["has_%s" % field_name] = present
            values[field_name] = amount
            canonical_amounts[field_name] = decimal_amount
            if present and field_name in (
                "tax_payable_amount",
                "tax_refund_amount",
                "closing_credit_amount",
            ) and amount < 0:
                issues.append(
                    self._issue(
                        "NEGATIVE_VAT_SUMMARY_AMOUNT",
                        "warning",
                        _("%(field)s为负数，请核对源申报口径", field=_(label)),
                    )
                )
        if not values["has_tax_payable_amount"]:
            issues.append(
                self._issue(
                    "MISSING_TAX_PAYABLE_AMOUNT",
                    "error",
                    _("缺少增值税应纳税额"),
                )
            )
        line_commands, canonical_lines = self._prepare_line_values(
            payload.get("lines"),
            issues,
        )
        values.update(
            {
                "jurisdiction_code": _safe_text(
                    payload.get("jurisdiction_code"),
                    128,
                ),
                "jurisdiction_name": _safe_text(
                    payload.get("jurisdiction_name"),
                    512,
                ),
                "return_type_code": _safe_text(
                    payload.get("return_type_code"),
                    128,
                ),
                "return_status": return_status,
                "submitted_at": submitted_at,
                "submission_reference": submission_reference,
                "revision_number": revision_number,
                "correction_reference": _safe_text(
                    payload.get("correction_reference"),
                    256,
                ),
                "line_ids": line_commands,
            }
        )
        canonical.update(
            {
                "jurisdiction_code": values["jurisdiction_code"],
                "jurisdiction_name": values["jurisdiction_name"],
                "return_type_code": values["return_type_code"],
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


class SudoChinaVatFilingLine(models.Model):
    _name = "sudo.cn.vat.filing.line"
    _description = "China Normalized VAT Filing Line"
    _order = "filing_record_id, sequence, id"
    _check_company_auto = True

    filing_record_id = fields.Many2one(
        "sudo.cn.vat.filing.record",
        string="增值税申报记录",
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
            ("taxable_base", "计税基础"),
            ("tax", "税额"),
            ("payable", "应纳税额"),
            ("credit", "留抵或抵减"),
            ("refund", "退税"),
            ("other", "其他"),
        ],
        string="金额类型",
        required=True,
        readonly=True,
    )
    has_current_amount = fields.Boolean(string="提供本期金额", readonly=True)
    current_amount = fields.Monetary(
        string="本期金额",
        currency_field="currency_id",
        readonly=True,
    )
    has_ytd_amount = fields.Boolean(string="提供本年累计", readonly=True)
    ytd_amount = fields.Monetary(
        string="本年累计",
        currency_field="currency_id",
        readonly=True,
    )
    has_tax_rate = fields.Boolean(string="提供税率", readonly=True)
    tax_rate = fields.Float(string="税率", digits=(16, 8), readonly=True)

    _line_unique = models.Constraint(
        "unique(filing_record_id, line_code)",
        "同一增值税申报记录中的标准化行代码必须唯一。",
    )

    @api.model_create_multi
    def create(self, vals_list):
        if (
            self.env.context.get("cn_tax_normalized_record_transition")
            is not _TAX_NORMALIZED_RECORD_MARKER
        ):
            raise AccessError(_("增值税申报标准化行只能由受控导入流程创建。"))
        return super().create(vals_list)

    def write(self, values):
        raise AccessError(_("增值税申报标准化行不可修改。"))

    def unlink(self):
        raise AccessError(_("增值税申报标准化行属于审计结果，不可删除。"))


class SudoChinaTaxPaymentRecord(models.Model):
    _name = "sudo.cn.tax.payment.record"
    _description = "China Normalized Tax Payment Record"
    _inherit = "sudo.cn.tax.normalized.record.mixin"
    _order = "payment_date desc, id desc"
    _source_dataset_type = "tax_payment"

    name = fields.Char(compute="_compute_name", store=True)
    tax_type_code = fields.Char(string="税种代码", readonly=True, index=True)
    tax_item_code = fields.Char(string="征收品目代码", readonly=True)
    payment_date = fields.Date(string="缴款日期", readonly=True, index=True)
    payment_reference = fields.Char(string="缴款参考号", readonly=True)
    payment_status = fields.Selection(
        [
            ("pending", "处理中"),
            ("succeeded", "缴款成功"),
            ("reversed", "已冲正"),
            ("refunded", "已退库"),
            ("failed", "缴款失败"),
            ("unknown", "未提供"),
        ],
        string="缴款状态",
        required=True,
        readonly=True,
        index=True,
    )
    has_amount = fields.Boolean(string="提供缴款金额", readonly=True)
    amount = fields.Monetary(
        string="缴款金额",
        currency_field="currency_id",
        readonly=True,
    )
    has_principal_amount = fields.Boolean(string="提供税款本金", readonly=True)
    principal_amount = fields.Monetary(
        string="税款本金",
        currency_field="currency_id",
        readonly=True,
    )
    has_interest_amount = fields.Boolean(string="提供利息金额", readonly=True)
    interest_amount = fields.Monetary(
        string="利息金额",
        currency_field="currency_id",
        readonly=True,
    )
    has_penalty_amount = fields.Boolean(string="提供滞纳金罚款", readonly=True)
    penalty_amount = fields.Monetary(
        string="滞纳金及罚款",
        currency_field="currency_id",
        readonly=True,
    )
    authority = fields.Char(string="征收机关", readonly=True)
    payment_channel = fields.Char(string="缴款渠道", readonly=True)
    payer_account_masked = fields.Char(string="付款账户脱敏值", readonly=True)
    receipt_reference = fields.Char(string="缴款回执引用", readonly=True)

    _source_record_unique = models.Constraint(
        "unique(parse_run_id, source_record_key)",
        "同一导入运行中的税款缴纳源记录键必须唯一。",
    )

    @api.depends("payment_reference", "tax_type_code", "payment_date")
    def _compute_name(self):
        for record in self:
            record.name = record.payment_reference or "%s / %s" % (
                record.tax_type_code or _("税款缴纳"),
                fields.Date.to_string(record.payment_date) or "-",
            )

    @api.model
    def _prepare_import_values(self, run, payload):
        values, canonical, issues, _currency = self._prepare_common(run, payload)
        tax_type_code = (
            _safe_text(payload.get("tax_type_code"), 128) or ""
        ).upper()
        if not tax_type_code:
            issues.append(
                self._issue("MISSING_TAX_TYPE", "error", _("缺少税种代码"))
            )
        raw_status = (
            _safe_text(payload.get("payment_status"), 32) or "unknown"
        )
        status_map = {
            "pending": "pending",
            "succeeded": "succeeded",
            "reversed": "reversed",
            "refunded": "refunded",
            "failed": "failed",
            "unknown": "unknown",
            "处理中": "pending",
            "缴款成功": "succeeded",
            "已冲正": "reversed",
            "已退库": "refunded",
            "缴款失败": "failed",
        }
        payment_status = status_map.get(raw_status.lower(), status_map.get(raw_status))
        if not payment_status:
            payment_status = "unknown"
            issues.append(
                self._issue(
                    "UNKNOWN_PAYMENT_STATUS",
                    "warning",
                    _("税款缴纳状态未识别"),
                )
            )
        payment_date = self._parse_date(
            payload.get("payment_date"),
            _("缴款日期"),
            issues,
        )
        payment_reference = _safe_text(
            payload.get("payment_reference"),
            256,
        )
        if payment_status in ("succeeded", "reversed", "refunded"):
            if not payment_date:
                issues.append(
                    self._issue(
                        "MISSING_PAYMENT_DATE",
                        "error",
                        _("已形成结果的缴款记录缺少缴款日期"),
                    )
                )
            if not payment_reference:
                issues.append(
                    self._issue(
                        "MISSING_PAYMENT_REFERENCE",
                        "warning",
                        _("缴款记录未提供缴款参考号"),
                    )
                )
        amount_fields = (
            ("amount", "缴款金额"),
            ("principal_amount", "税款本金"),
            ("interest_amount", "利息金额"),
            ("penalty_amount", "滞纳金及罚款"),
        )
        canonical_amounts = {}
        for field_name, label in amount_fields:
            present, amount, decimal_amount = self._parse_decimal(
                payload.get(field_name),
                _(label),
                issues,
            )
            values["has_%s" % field_name] = present
            values[field_name] = amount
            canonical_amounts[field_name] = decimal_amount
            if present and amount < 0:
                issues.append(
                    self._issue(
                        "NEGATIVE_PAYMENT_AMOUNT",
                        "error",
                        _("%(field)s不能为负数", field=_(label)),
                    )
                )
        if not values["has_amount"]:
            issues.append(
                self._issue(
                    "MISSING_PAYMENT_AMOUNT",
                    "error",
                    _("缺少缴款金额"),
                )
            )
        elif payment_status in ("succeeded", "reversed", "refunded") and not values[
            "amount"
        ]:
            issues.append(
                self._issue(
                    "ZERO_RESULT_PAYMENT_AMOUNT",
                    "warning",
                    _("已形成结果的缴款记录金额为零"),
                )
            )
        provided_components = [
            values["has_principal_amount"],
            values["has_interest_amount"],
            values["has_penalty_amount"],
        ]
        if values["has_amount"] and all(provided_components):
            component_total = (
                values["principal_amount"]
                + values["interest_amount"]
                + values["penalty_amount"]
            )
            if values["currency_id"] and not self.env[
                "res.currency"
            ].browse(values["currency_id"]).is_zero(
                values["amount"] - component_total
            ):
                issues.append(
                    self._issue(
                        "PAYMENT_COMPONENT_TOTAL_MISMATCH",
                        "warning",
                        _("缴款本金、利息和滞纳金合计与缴款金额不一致"),
                    )
                )
        masked_account = _safe_text(payload.get("payer_account_masked"), 128)
        masked_digits = re.findall(r"\d", masked_account or "")
        if masked_account and len(masked_digits) > 4:
            issues.append(
                self._issue(
                    "UNMASKED_PAYER_ACCOUNT",
                    "error",
                    _("付款账户包含超过四位数字，已拒绝保存该值"),
                )
            )
            masked_account = False
        elif masked_account and not masked_digits:
            issues.append(
                self._issue(
                    "INVALID_MASKED_PAYER_ACCOUNT",
                    "warning",
                    _("付款账户脱敏值未包含可识别的尾号，已拒绝保存该值"),
                )
            )
            masked_account = False
        elif masked_digits:
            masked_account = "****%s" % "".join(masked_digits)
        values.update(
            {
                "tax_type_code": tax_type_code or False,
                "tax_item_code": _safe_text(
                    payload.get("tax_item_code"),
                    128,
                ),
                "payment_date": payment_date,
                "payment_reference": payment_reference,
                "payment_status": payment_status,
                "authority": _safe_text(payload.get("authority"), 512),
                "payment_channel": _safe_text(
                    payload.get("payment_channel"),
                    128,
                ),
                "payer_account_masked": masked_account,
                "receipt_reference": _safe_text(
                    payload.get("receipt_reference"),
                    256,
                ),
            }
        )
        canonical.update(
            {
                "tax_type_code": tax_type_code or None,
                "tax_item_code": values["tax_item_code"],
                "payment_date": fields.Date.to_string(payment_date),
                "payment_reference": payment_reference,
                "payment_status": payment_status,
                **canonical_amounts,
                "authority": values["authority"],
                "payment_channel": values["payment_channel"],
                "payer_account_masked": masked_account,
                "receipt_reference": values["receipt_reference"],
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


class SudoChinaExternalDataset(models.Model):
    _inherit = "sudo.cn.external.dataset"

    tax_data_parse_run_ids = fields.One2many(
        "sudo.cn.tax.data.parse.run",
        "dataset_id",
        string="申报缴税导入运行",
        readonly=True,
        copy=False,
    )
    tax_data_parse_run_count = fields.Integer(
        string="申报缴税导入次数",
        compute="_compute_tax_data_result_counts",
    )
    normalized_vat_filing_count = fields.Integer(
        string="规范化增值税申报数",
        compute="_compute_tax_data_result_counts",
    )
    normalized_cit_filing_count = fields.Integer(
        string="规范化企业所得税申报数",
        compute="_compute_tax_data_result_counts",
    )
    normalized_iit_withholding_count = fields.Integer(
        string="规范化个人所得税扣缴申报数",
        compute="_compute_tax_data_result_counts",
    )
    normalized_payroll_summary_count = fields.Integer(
        string="规范化工资薪酬汇总数",
        compute="_compute_tax_data_result_counts",
    )
    normalized_tax_payment_count = fields.Integer(
        string="规范化税款缴纳数",
        compute="_compute_tax_data_result_counts",
    )
    current_tax_data_parse_run_id = fields.Many2one(
        "sudo.cn.tax.data.parse.run",
        string="当前申报缴税导入结果",
        compute="_compute_tax_data_result_counts",
    )

    @api.depends(
        "tax_data_parse_run_ids",
        "tax_data_parse_run_ids.state",
        "tax_data_parse_run_ids.started_at",
        "tax_data_parse_run_ids.vat_filing_count",
        "tax_data_parse_run_ids.cit_filing_count",
        "tax_data_parse_run_ids.iit_withholding_count",
        "tax_data_parse_run_ids.payroll_summary_count",
        "tax_data_parse_run_ids.tax_payment_count",
        "state",
        "integrity_state",
    )
    def _compute_tax_data_result_counts(self):
        for dataset in self:
            dataset.tax_data_parse_run_count = len(dataset.tax_data_parse_run_ids)
            eligible = (
                dataset.state == "sealed"
                and dataset._current_integrity_state() == "verified"
            )
            current_runs = dataset.tax_data_parse_run_ids.filtered(
                lambda run: eligible and run.state == "succeeded"
            ).sorted(key=lambda run: (run.started_at, run.id), reverse=True)
            current = current_runs[:1]
            dataset.current_tax_data_parse_run_id = current
            dataset.normalized_vat_filing_count = (
                current.vat_filing_count if current else 0
            )
            dataset.normalized_cit_filing_count = (
                current.cit_filing_count if current else 0
            )
            dataset.normalized_iit_withholding_count = (
                current.iit_withholding_count if current else 0
            )
            dataset.normalized_payroll_summary_count = (
                current.payroll_summary_count if current else 0
            )
            dataset.normalized_tax_payment_count = (
                current.tax_payment_count if current else 0
            )

    def action_import_tax_data(self):
        self.ensure_one()
        if self.dataset_type not in TAX_DATA_RECORD_MODELS:
            raise UserError(_("当前数据集类型不能使用申报缴税受控导入。"))
        return {
            "type": "ir.actions.act_window",
            "name": _("导入申报与缴税数据"),
            "res_model": "sudo.cn.tax.data.import.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_dataset_id": self.id},
        }

    def action_view_tax_data_parse_runs(self):
        self.ensure_one()
        action = self.env.ref(
            "sudo_country_pack_cn.action_cn_tax_data_parse_runs"
        ).read()[0]
        action["domain"] = [("dataset_id", "=", self.id)]
        action["context"] = {}
        return action

    def action_view_normalized_tax_records(self):
        self.ensure_one()
        action_ref = {
            "vat_filing": "sudo_country_pack_cn.action_cn_vat_filing_records",
            "cit_filing": "sudo_country_pack_cn.action_cn_cit_filing_records",
            "iit_withholding": (
                "sudo_country_pack_cn.action_cn_iit_withholding_records"
            ),
            "payroll_summary": (
                "sudo_country_pack_cn.action_cn_payroll_summary_records"
            ),
            "tax_payment": "sudo_country_pack_cn.action_cn_tax_payment_records",
        }.get(self.dataset_type)
        if not action_ref:
            raise UserError(_("当前数据集没有规范化申报缴税台账。"))
        action = self.env.ref(action_ref).read()[0]
        action["domain"] = [("dataset_id", "=", self.id)]
        action["context"] = {}
        return action


class SudoChinaTaxDataImportWizard(models.TransientModel):
    _name = "sudo.cn.tax.data.import.wizard"
    _description = "Import China Tax Filing and Payment Data"
    _check_company_auto = True

    dataset_id = fields.Many2one(
        "sudo.cn.external.dataset",
        string="外部数据集",
        required=True,
        check_company=True,
        domain="[('dataset_type', 'in', ('vat_filing', 'cit_filing', 'iit_withholding', 'payroll_summary', 'tax_payment')), "
        "('state', '=', 'sealed')]",
    )
    company_id = fields.Many2one(
        related="dataset_id.company_id",
        readonly=True,
    )
    available_attachment_ids = fields.Many2many(
        related="dataset_id.source_attachment_ids",
        string="可选源文件",
        readonly=True,
    )
    input_attachment_id = fields.Many2one(
        "ir.attachment",
        string="导入源文件",
        required=True,
    )
    mapping_key = fields.Char(
        string="映射键",
        required=True,
        default=TAX_DATA_MAPPING_KEY,
    )
    mapping_version = fields.Char(
        string="映射版本",
        required=True,
        default=TAX_DATA_MAPPING_VERSION,
    )

    @api.onchange("dataset_id")
    def _onchange_dataset_id(self):
        if self.input_attachment_id not in self.available_attachment_ids:
            self.input_attachment_id = self.available_attachment_ids[:1]

    def action_import(self):
        self.ensure_one()
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以导入申报与缴税数据。"))
        if self.input_attachment_id not in self.available_attachment_ids:
            raise ValidationError(_("导入源文件必须属于当前外部数据集。"))
        run = self.env["sudo.cn.tax.data.parse.run"].with_company(
            self.company_id
        )._start_for_dataset(
            self.dataset_id,
            self.input_attachment_id,
            mapping_key=self.mapping_key,
            mapping_version=self.mapping_version,
        )
        run._process_json_attachment()
        return {
            "type": "ir.actions.act_window",
            "name": _("申报缴税导入运行"),
            "res_model": "sudo.cn.tax.data.parse.run",
            "res_id": run.id,
            "view_mode": "form",
            "target": "current",
        }
