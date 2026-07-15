import hashlib
import json
import re
from decimal import Decimal, InvalidOperation

from odoo import _, api, Command, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


_PARSE_RUN_MARKER = object()
_NORMALIZED_RECORD_MARKER = object()

TRI_STATE = (
    ("unknown", "未提供"),
    ("yes", "是"),
    ("no", "否"),
)


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


def _nonnegative_int(value, default=0):
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return default


def _normalized_sha256(value):
    candidate = (_safe_text(value, 64) or "").lower()
    return candidate if re.fullmatch(r"[0-9a-f]{64}", candidate) else False


class SudoChinaExternalParseRun(models.Model):
    _name = "sudo.cn.external.parse.run"
    _description = "China External Dataset Parse Run"
    _order = "started_at desc, id desc"
    _check_company_auto = True

    name = fields.Char(compute="_compute_name", store=True)
    dataset_id = fields.Many2one(
        "sudo.cn.external.dataset",
        string="外部数据集",
        required=True,
        ondelete="restrict",
        index=True,
        check_company=True,
    )
    profile_id = fields.Many2one(
        related="dataset_id.profile_id",
        store=True,
        index=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        related="dataset_id.company_id",
        store=True,
        index=True,
        readonly=True,
    )
    country_id = fields.Many2one(
        related="dataset_id.country_id",
        store=True,
        index=True,
        readonly=True,
    )
    input_attachment_id = fields.Many2one(
        "ir.attachment",
        string="解析源文件",
        required=True,
        ondelete="restrict",
        readonly=True,
    )
    input_sha256 = fields.Char(
        string="解析源文件 SHA-256",
        required=True,
        readonly=True,
    )
    dataset_seal_checksum = fields.Char(
        string="数据集封存校验和",
        required=True,
        readonly=True,
    )
    parser_key = fields.Char(string="解析器键", required=True, readonly=True)
    parser_version = fields.Char(
        string="解析器版本",
        required=True,
        readonly=True,
    )
    parser_distribution = fields.Char(
        string="解析器发行包",
        required=True,
        readonly=True,
    )
    taxonomy_namespace = fields.Char(
        string="分类标准命名空间",
        required=True,
        readonly=True,
    )
    taxonomy_version = fields.Char(
        string="分类标准版本",
        required=True,
        readonly=True,
    )
    taxonomy_checksum = fields.Char(
        string="分类标准包 SHA-256",
        required=True,
        readonly=True,
    )
    taxonomy_source_reference = fields.Char(
        string="分类标准来源引用",
        required=True,
        readonly=True,
    )
    state = fields.Selection(
        [
            ("running", "解析中"),
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
    source_fact_count = fields.Integer(string="源事实数", readonly=True)
    document_count = fields.Integer(string="规范化文档数", readonly=True)
    valid_document_count = fields.Integer(string="正常文档数", readonly=True)
    warning_document_count = fields.Integer(
        string="警告文档数",
        readonly=True,
    )
    error_document_count = fields.Integer(string="异常文档数", readonly=True)
    parser_warning_count = fields.Integer(string="解析警告数", readonly=True)
    parser_error_count = fields.Integer(string="解析错误数", readonly=True)
    parser_log_checksum = fields.Char(string="解析日志摘要哈希", readonly=True)
    output_checksum = fields.Char(string="规范化输出校验和", readonly=True)
    error_code = fields.Char(string="失败代码", readonly=True)
    result_summary = fields.Text(string="结果摘要", readonly=True)
    document_ids = fields.One2many(
        "sudo.cn.einvoice.document",
        "parse_run_id",
        string="规范化电子发票",
        readonly=True,
    )

    @api.depends("dataset_id", "parser_key", "parser_version", "started_at")
    def _compute_name(self):
        for run in self:
            started = fields.Datetime.to_string(run.started_at) or "-"
            run.name = "%s / %s %s / %s" % (
                run.dataset_id.display_name or _("电子发票解析"),
                run.parser_key or "-",
                run.parser_version or "-",
                started,
            )

    @api.model_create_multi
    def create(self, vals_list):
        if (
            self.env.context.get("cn_parse_run_transition")
            is not _PARSE_RUN_MARKER
        ):
            raise AccessError(_("解析运行只能由受控解析流程创建。"))
        for values in vals_list:
            values.update(
                {
                    "state": "running",
                    "finished_at": False,
                    "source_fact_count": 0,
                    "document_count": 0,
                    "valid_document_count": 0,
                    "warning_document_count": 0,
                    "error_document_count": 0,
                    "parser_warning_count": 0,
                    "parser_error_count": 0,
                    "parser_log_checksum": False,
                    "output_checksum": False,
                    "error_code": False,
                    "result_summary": False,
                }
            )
        return super().create(vals_list)

    def write(self, values):
        if (
            self.env.context.get("cn_parse_run_transition")
            is not _PARSE_RUN_MARKER
        ):
            raise AccessError(_("解析运行只能由受控解析流程更新。"))
        return super().write(values)

    def unlink(self):
        raise AccessError(_("解析运行属于审计记录，不可删除。"))

    @api.model
    def _require_manager(self):
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以执行外部数据解析。"))

    @api.model
    def _start_for_dataset(
        self,
        dataset,
        input_attachment,
        *,
        parser_key,
        parser_version,
        parser_distribution,
        taxonomy_namespace,
        taxonomy_version,
        taxonomy_checksum,
        taxonomy_source_reference,
    ):
        self._require_manager()
        dataset.ensure_one()
        input_attachment.ensure_one()
        if dataset.dataset_type != "electronic_invoice":
            raise UserError(_("当前解析契约仅适用于电子发票与电子凭证数据集。"))
        if dataset.state != "sealed":
            raise UserError(_("只有当前已封存的数据集可以解析。"))
        if dataset._current_integrity_state() != "verified":
            raise UserError(_("数据集文件完整性异常，不能开始解析。"))
        if input_attachment not in dataset._controlled_source_attachments():
            raise UserError(_("解析源文件必须属于当前数据集。"))
        source_attachment = input_attachment.sudo()
        if source_attachment.type != "binary" or source_attachment.file_size <= 0:
            raise UserError(_("解析源文件必须是非空二进制附件。"))

        parser_values = {
            "parser_key": _safe_text(parser_key, 128),
            "parser_version": _safe_text(parser_version, 64),
            "parser_distribution": _safe_text(parser_distribution, 128),
            "taxonomy_namespace": _safe_text(taxonomy_namespace, 512),
            "taxonomy_version": _safe_text(taxonomy_version, 64),
            "taxonomy_checksum": _safe_text(taxonomy_checksum, 64),
            "taxonomy_source_reference": _safe_text(
                taxonomy_source_reference,
                512,
            ),
        }
        missing = [key for key, value in parser_values.items() if not value]
        if missing:
            raise UserError(
                _(
                    "解析器或分类标准信息不完整：%(fields)s",
                    fields=", ".join(sorted(missing)),
                )
            )
        parser_values["taxonomy_checksum"] = _normalized_sha256(
            parser_values["taxonomy_checksum"]
        )
        if not parser_values["taxonomy_checksum"]:
            raise UserError(_("分类标准包 SHA-256 格式无效。"))

        manifest = dataset.sealed_file_manifest_json or {}
        manifest_entry = next(
            (
                item
                for item in manifest.get("source_attachments", [])
                if item.get("id") == input_attachment.id
            ),
            None,
        )
        input_sha256 = manifest_entry and manifest_entry.get("sha256")
        if not input_sha256:
            raise UserError(_("封存清单中没有解析源文件的 SHA-256。"))

        self.env.cr.execute(
            "SELECT id FROM sudo_cn_external_dataset WHERE id = %s FOR UPDATE",
            [dataset.id],
        )
        running = self.search(
            [("dataset_id", "=", dataset.id), ("state", "=", "running")],
            limit=1,
        )
        if running:
            raise UserError(_("该数据集已有正在执行的解析运行。"))

        run = self.with_context(
            cn_parse_run_transition=_PARSE_RUN_MARKER
        ).create(
            {
                "dataset_id": dataset.id,
                "input_attachment_id": input_attachment.id,
                "input_sha256": input_sha256,
                "dataset_seal_checksum": dataset.seal_checksum,
                "started_at": fields.Datetime.now(),
                "started_by_id": self.env.user.id,
                **parser_values,
            }
        )
        self.env["sudo.compliance.audit.event"]._log_records(
            run,
            "cn_external_parse.started",
            new_state="running",
            details={
                "dataset_id": dataset.id,
                "input_attachment_id": input_attachment.id,
                "input_sha256": input_sha256,
                "dataset_seal_checksum": dataset.seal_checksum,
                "parser_key": run.parser_key,
                "parser_version": run.parser_version,
                "taxonomy_checksum": run.taxonomy_checksum,
            },
        )
        return run.with_context(cn_parse_run_transition=None)

    def _record_failure(
        self,
        error_code,
        summary,
        *,
        warning_count=0,
        error_count=1,
        parser_log_checksum=False,
    ):
        self.ensure_one()
        if self.state != "running":
            raise UserError(_("只有解析中的运行可以记录失败。"))
        values = {
            "state": "failed",
            "finished_at": fields.Datetime.now(),
            "error_code": _safe_text(error_code, 128) or "PARSER_FAILED",
            "result_summary": _safe_text(summary, 2000),
            "parser_warning_count": _nonnegative_int(warning_count),
            "parser_error_count": max(_nonnegative_int(error_count, 1), 1),
            "parser_log_checksum": _normalized_sha256(parser_log_checksum),
        }
        self.with_context(
            cn_parse_run_transition=_PARSE_RUN_MARKER
        ).write(values)
        self.env["sudo.compliance.audit.event"]._log_records(
            self,
            "cn_external_parse.failed",
            previous_state="running",
            new_state="failed",
            details={
                "error_code": values["error_code"],
                "warning_count": values["parser_warning_count"],
                "error_count": values["parser_error_count"],
                "parser_log_checksum": values["parser_log_checksum"],
            },
        )
        return False

    def _record_success(
        self,
        documents,
        *,
        observed_input_sha256,
        source_fact_count,
        warning_count=0,
        error_count=0,
        parser_log_checksum=False,
    ):
        self.ensure_one()
        if self.state != "running":
            raise UserError(_("只有解析中的运行可以记录成功结果。"))
        observed_hash = _normalized_sha256(observed_input_sha256)
        if observed_hash != self.input_sha256:
            return self._record_failure(
                "INPUT_HASH_MISMATCH",
                "解析进程读取的源文件与封存文件哈希不一致。",
            )
        normalized_error_count = _nonnegative_int(error_count)
        normalized_warning_count = _nonnegative_int(warning_count)
        normalized_log_checksum = _normalized_sha256(parser_log_checksum)
        if parser_log_checksum and not normalized_log_checksum:
            return self._record_failure(
                "INVALID_PARSER_LOG_CHECKSUM",
                "解析器日志摘要哈希格式无效。",
            )
        if normalized_error_count > 0:
            return self._record_failure(
                "XBRL_VALIDATION_FAILED",
                "解析器报告错误，未生成规范化结果。",
                warning_count=normalized_warning_count,
                error_count=normalized_error_count,
                parser_log_checksum=normalized_log_checksum,
            )
        if not isinstance(documents, (list, tuple)) or not documents:
            return self._record_failure(
                "NO_NORMALIZED_DOCUMENTS",
                "解析器没有生成规范化电子发票记录。",
                warning_count=normalized_warning_count,
                parser_log_checksum=normalized_log_checksum,
            )
        source_keys = [
            _safe_text(document.get("source_document_key"), 512)
            if isinstance(document, dict)
            else False
            for document in documents
        ]
        if not all(source_keys) or len(source_keys) != len(set(source_keys)):
            return self._record_failure(
                "INVALID_SOURCE_DOCUMENT_KEYS",
                "解析输出包含空白或重复的源文档键。",
                warning_count=normalized_warning_count,
                parser_log_checksum=normalized_log_checksum,
            )

        document_model = self.env["sudo.cn.einvoice.document"]
        previous_runs = self.browse()
        try:
            with self.env.cr.savepoint():
                prepared_values = [
                    document_model._prepare_parser_values(self, payload)
                    for payload in documents
                ]
                created = document_model.with_context(
                    cn_normalized_record_transition=(
                        _NORMALIZED_RECORD_MARKER
                    )
                ).create(prepared_values)
                output_checksum = _sha256_json(
                    sorted(created.mapped("document_checksum"))
                )
                previous_runs = self.search(
                    [
                        ("dataset_id", "=", self.dataset_id.id),
                        ("state", "=", "succeeded"),
                        ("id", "!=", self.id),
                    ]
                )
                previous_runs.with_context(
                    cn_parse_run_transition=_PARSE_RUN_MARKER
                ).write({"state": "superseded"})
                self.with_context(
                    cn_parse_run_transition=_PARSE_RUN_MARKER
                ).write(
                    {
                        "state": "succeeded",
                        "finished_at": fields.Datetime.now(),
                        "source_fact_count": _nonnegative_int(
                            source_fact_count
                        ),
                        "document_count": len(created),
                        "valid_document_count": len(
                            created.filtered(
                                lambda item: item.quality_state == "valid"
                            )
                        ),
                        "warning_document_count": len(
                            created.filtered(
                                lambda item: item.quality_state == "warning"
                            )
                        ),
                        "error_document_count": len(
                            created.filtered(
                                lambda item: item.quality_state == "error"
                            )
                        ),
                        "parser_warning_count": normalized_warning_count,
                        "parser_error_count": 0,
                        "parser_log_checksum": normalized_log_checksum,
                        "output_checksum": output_checksum,
                        "result_summary": _(
                            "已生成 %(count)s 份规范化电子发票。",
                            count=len(created),
                        ),
                    }
                )
        except (TypeError, ValueError, ValidationError, UserError) as exc:
            return self._record_failure(
                "NORMALIZATION_FAILED",
                _safe_text(exc, 1000) or "规范化输出校验失败。",
                warning_count=normalized_warning_count,
                parser_log_checksum=normalized_log_checksum,
            )
        for previous in previous_runs:
            self.env["sudo.compliance.audit.event"]._log_records(
                previous,
                "cn_external_parse.superseded",
                previous_state="succeeded",
                new_state="superseded",
                details={"replacement_run_id": self.id},
            )
        self.env["sudo.compliance.audit.event"]._log_records(
            self,
            "cn_external_parse.succeeded",
            previous_state="running",
            new_state="succeeded",
            details={
                "input_sha256": self.input_sha256,
                "output_checksum": output_checksum,
                "source_fact_count": self.source_fact_count,
                "document_count": self.document_count,
                "valid_document_count": self.valid_document_count,
                "warning_document_count": self.warning_document_count,
                "error_document_count": self.error_document_count,
                "parser_warning_count": self.parser_warning_count,
                "parser_log_checksum": self.parser_log_checksum,
            },
        )
        return True


class SudoChinaEinvoiceDocument(models.Model):
    _name = "sudo.cn.einvoice.document"
    _description = "China Normalized Electronic Invoice"
    _order = "request_time desc, invoice_number, id"
    _check_company_auto = True

    name = fields.Char(compute="_compute_name", store=True)
    parse_run_id = fields.Many2one(
        "sudo.cn.external.parse.run",
        string="解析运行",
        required=True,
        ondelete="restrict",
        index=True,
        check_company=True,
    )
    dataset_id = fields.Many2one(
        related="parse_run_id.dataset_id",
        store=True,
        index=True,
        readonly=True,
    )
    profile_id = fields.Many2one(
        related="parse_run_id.profile_id",
        store=True,
        index=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        related="parse_run_id.company_id",
        store=True,
        index=True,
        readonly=True,
    )
    country_id = fields.Many2one(
        related="parse_run_id.country_id",
        store=True,
        index=True,
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
    source_document_key = fields.Char(
        string="源文档键",
        required=True,
        readonly=True,
        index=True,
    )
    invoice_number = fields.Char(string="发票号码", readonly=True, index=True)
    invoice_type_code = fields.Char(string="发票类型代码", readonly=True)
    request_time = fields.Datetime(string="开具或申请时间", readonly=True)
    seller_name = fields.Char(string="销售方名称", readonly=True)
    seller_tax_id = fields.Char(string="销售方识别号", readonly=True, index=True)
    accounting_entity_name = fields.Char(string="会计主体名称", readonly=True)
    accounting_entity_tax_id = fields.Char(
        string="会计主体统一社会信用代码",
        readonly=True,
        index=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="币种",
        readonly=True,
    )
    has_untaxed_amount = fields.Boolean(string="提供不含税金额", readonly=True)
    untaxed_amount = fields.Monetary(
        string="不含税金额",
        currency_field="currency_id",
        readonly=True,
    )
    has_tax_amount = fields.Boolean(string="提供税额", readonly=True)
    tax_amount = fields.Monetary(
        string="税额",
        currency_field="currency_id",
        readonly=True,
    )
    has_total_amount = fields.Boolean(string="提供价税合计", readonly=True)
    total_amount = fields.Monetary(
        string="价税合计",
        currency_field="currency_id",
        readonly=True,
    )
    is_red = fields.Selection(TRI_STATE, string="红字发票", readonly=True)
    is_booked = fields.Selection(TRI_STATE, string="已入账", readonly=True)
    is_checked = fields.Selection(TRI_STATE, string="已查验", readonly=True)
    is_paid = fields.Selection(TRI_STATE, string="已支付", readonly=True)
    contract_number = fields.Char(string="合同编号", readonly=True)
    bank_receipt_number = fields.Char(string="银行电子回单编号", readonly=True)
    usage_confirmation = fields.Char(string="用途确认", readonly=True)
    source_fact_count = fields.Integer(string="源事实数", readonly=True)
    source_fact_digest = fields.Char(string="源事实摘要哈希", readonly=True)
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
    document_checksum = fields.Char(
        string="规范化文档校验和",
        required=True,
        readonly=True,
        index=True,
    )
    accounting_document_ids = fields.One2many(
        "sudo.cn.einvoice.accounting.document",
        "einvoice_document_id",
        string="会计凭证信息",
        readonly=True,
    )
    is_current_result = fields.Boolean(
        string="当前有效解析结果",
        compute="_compute_is_current_result",
        search="_search_is_current_result",
    )

    _source_document_unique = models.Constraint(
        "unique(parse_run_id, source_document_key)",
        "同一解析运行中的源文档键必须唯一。",
    )

    @api.depends("invoice_number", "source_document_key")
    def _compute_name(self):
        for document in self:
            document.name = document.invoice_number or document.source_document_key

    @api.depends(
        "parse_run_id.state",
        "dataset_id.state",
        "source_integrity_state",
    )
    def _compute_is_current_result(self):
        for document in self:
            document.is_current_result = (
                document.parse_run_id.state == "succeeded"
                and document.dataset_id.state == "sealed"
                and document.source_integrity_state == "verified"
            )

    @api.model
    def _search_is_current_result(self, operator, value):
        if operator not in ("=", "!="):
            raise UserError(_("当前解析结果仅支持等于或不等于筛选。"))
        datasets = self.env["sudo.cn.external.dataset"].search(
            [
                ("dataset_type", "=", "electronic_invoice"),
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
            self.env.context.get("cn_normalized_record_transition")
            is not _NORMALIZED_RECORD_MARKER
        ):
            raise AccessError(_("规范化电子发票只能由受控解析流程创建。"))
        return super().create(vals_list)

    def write(self, values):
        raise AccessError(_("规范化电子发票不可修改，请重新执行受控解析。"))

    def unlink(self):
        raise AccessError(_("规范化电子发票属于解析审计结果，不可删除。"))

    def copy(self, default=None):
        raise AccessError(_("规范化电子发票不可复制。"))

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
        except (InvalidOperation, TypeError, ValueError):
            issues.append(
                self._issue(
                    "INVALID_AMOUNT",
                    "error",
                    _("%(field)s格式无效", field=field_label),
                )
            )
            return False, 0.0, None
        return True, float(decimal_value), format(decimal_value, "f")

    @api.model
    def _parse_datetime(self, value, field_label, issues):
        if not value:
            return False
        try:
            if isinstance(value, str):
                value = value.replace("T", " ")
            return fields.Datetime.to_datetime(value)
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
    def _tri_state(self, value):
        if value is True:
            return "yes"
        if value is False:
            return "no"
        normalized = (_safe_text(value, 16) or "").lower()
        if normalized in {"true", "yes", "1"}:
            return "yes"
        if normalized in {"false", "no", "0"}:
            return "no"
        return "unknown"

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
    def _prepare_accounting_documents(
        self,
        payloads,
        currency,
        issues,
    ):
        commands = []
        canonical = []
        for document_index, payload in enumerate(payloads or [], start=1):
            if not isinstance(payload, dict):
                raise ValueError("会计凭证信息必须是对象列表。")
            entry_commands = []
            canonical_entries = []
            debit_total = Decimal("0")
            credit_total = Decimal("0")
            for entry_index, entry in enumerate(
                payload.get("entries") or [],
                start=1,
            ):
                if not isinstance(entry, dict):
                    raise ValueError("借贷分录必须是对象列表。")
                raw_direction = (_safe_text(entry.get("direction"), 32) or "")
                direction_map = {
                    "debit": "debit",
                    "借方": "debit",
                    "credit": "credit",
                    "贷方": "credit",
                }
                direction = direction_map.get(raw_direction, "unknown")
                present, amount, decimal_amount = self._parse_decimal(
                    entry.get("amount"),
                    _("入账金额"),
                    issues,
                )
                if not present:
                    issues.append(
                        self._issue(
                            "MISSING_ENTRY_AMOUNT",
                            "error",
                            _("会计分录缺少有效金额"),
                        )
                    )
                elif amount < 0:
                    issues.append(
                        self._issue(
                            "NEGATIVE_ENTRY_AMOUNT",
                            "error",
                            _("会计分录金额不能为负数"),
                        )
                    )
                if direction == "unknown":
                    issues.append(
                        self._issue(
                            "UNKNOWN_DEBIT_CREDIT",
                            "error",
                            _("会计分录借贷方向无法识别"),
                        )
                    )
                if present and amount >= 0:
                    if direction == "debit":
                        debit_total += Decimal(decimal_amount)
                    elif direction == "credit":
                        credit_total += Decimal(decimal_amount)
                general_subject = _safe_text(
                    entry.get("general_ledger_subject"),
                    256,
                )
                subsidiary_subject = _safe_text(
                    entry.get("subsidiary_ledger_subject"),
                    256,
                )
                if not general_subject:
                    issues.append(
                        self._issue(
                            "MISSING_LEDGER_SUBJECT",
                            "warning",
                            _("会计分录未提供总账科目名称"),
                        )
                    )
                entry_values = {
                    "sequence": entry_index,
                    "direction": direction,
                    "general_ledger_subject": general_subject,
                    "subsidiary_ledger_subject": subsidiary_subject,
                    "amount": amount,
                }
                entry_commands.append(Command.create(entry_values))
                canonical_entries.append(
                    {
                        **entry_values,
                        "amount": decimal_amount,
                    }
                )
            if not canonical_entries:
                issues.append(
                    self._issue(
                        "NO_ACCOUNTING_ENTRIES",
                        "warning",
                        _("电子发票携带的会计凭证没有借贷分录"),
                    )
                )
            difference = debit_total - credit_total
            if currency:
                balanced = currency.is_zero(float(difference))
            else:
                balanced = abs(difference) <= Decimal("0.01")
            if canonical_entries and not balanced:
                issues.append(
                    self._issue(
                        "UNBALANCED_ACCOUNTING_DOCUMENT",
                        "error",
                        _("电子发票携带的会计凭证借贷不平衡"),
                    )
                )
            voucher_number = _safe_text(payload.get("voucher_number"), 128)
            posting_date = self._parse_date(
                payload.get("posting_date"),
                _("入账日期"),
                issues,
            )
            accounting_period = _safe_text(
                payload.get("accounting_period"),
                32,
            )
            summary = _safe_text(payload.get("summary"), 1000)
            if not voucher_number:
                issues.append(
                    self._issue(
                        "MISSING_VOUCHER_NUMBER",
                        "warning",
                        _("会计凭证关联未提供凭证编号"),
                    )
                )
            if not posting_date:
                issues.append(
                    self._issue(
                        "MISSING_POSTING_DATE",
                        "warning",
                        _("会计凭证关联未提供入账日期"),
                    )
                )
            if accounting_period and not re.fullmatch(
                r"\d{4}-(0[1-9]|1[0-2])",
                accounting_period,
            ):
                issues.append(
                    self._issue(
                        "INVALID_ACCOUNTING_PERIOD",
                        "warning",
                        _("会计期间不是 YYYY-MM 格式"),
                    )
                )
            document_values = {
                "sequence": document_index,
                "voucher_number": voucher_number,
                "posting_date": posting_date,
                "accounting_period": accounting_period,
                "summary": summary,
                "debit_total": float(debit_total),
                "credit_total": float(credit_total),
                "balance_difference": float(difference),
                "entry_ids": entry_commands,
            }
            commands.append(Command.create(document_values))
            canonical.append(
                {
                    "sequence": document_index,
                    "voucher_number": voucher_number,
                    "posting_date": fields.Date.to_string(posting_date),
                    "accounting_period": accounting_period,
                    "summary": summary,
                    "debit_total": format(debit_total, "f"),
                    "credit_total": format(credit_total, "f"),
                    "balance_difference": format(difference, "f"),
                    "entries": canonical_entries,
                }
            )
        return commands, canonical

    @api.model
    def _prepare_parser_values(self, run, payload):
        if not isinstance(payload, dict):
            raise ValueError("规范化电子发票必须是对象。")
        issues = []
        source_key = _safe_text(payload.get("source_document_key"), 512)
        invoice_number = _safe_text(payload.get("invoice_number"), 128)
        seller_name = _safe_text(payload.get("seller_name"), 512)
        seller_tax_id = (_safe_text(payload.get("seller_tax_id"), 64) or "").upper()
        accounting_entity_name = _safe_text(
            payload.get("accounting_entity_name"),
            512,
        )
        accounting_entity_tax_id = (
            _safe_text(payload.get("accounting_entity_tax_id"), 64) or ""
        ).upper()
        if not invoice_number:
            issues.append(
                self._issue("MISSING_INVOICE_NUMBER", "error", _("缺少发票号码"))
            )
        if not seller_name:
            issues.append(
                self._issue("MISSING_SELLER_NAME", "error", _("缺少销售方名称"))
            )
        if not seller_tax_id:
            issues.append(
                self._issue("MISSING_SELLER_ID", "error", _("缺少销售方识别号"))
            )
        if not accounting_entity_tax_id:
            issues.append(
                self._issue(
                    "MISSING_ACCOUNTING_ENTITY_ID",
                    "warning",
                    _("未提供会计主体统一社会信用代码"),
                )
            )
        if not accounting_entity_name:
            issues.append(
                self._issue(
                    "MISSING_ACCOUNTING_ENTITY_NAME",
                    "warning",
                    _("未提供会计主体名称"),
                )
            )

        currency = self._currency(payload.get("currency_code"), issues)
        has_untaxed, untaxed, untaxed_decimal = self._parse_decimal(
            payload.get("untaxed_amount"),
            _("不含税金额"),
            issues,
        )
        has_tax, tax, tax_decimal = self._parse_decimal(
            payload.get("tax_amount"),
            _("税额"),
            issues,
        )
        has_total, total, total_decimal = self._parse_decimal(
            payload.get("total_amount"),
            _("价税合计"),
            issues,
        )
        if not has_total:
            issues.append(
                self._issue("MISSING_TOTAL_AMOUNT", "error", _("缺少价税合计"))
            )
        if has_untaxed and has_tax and has_total:
            difference = untaxed + tax - total
            consistent = (
                currency.is_zero(difference)
                if currency
                else abs(difference) <= 0.01
            )
            if not consistent:
                issues.append(
                    self._issue(
                        "INVOICE_TOTAL_MISMATCH",
                        "error",
                        _("不含税金额、税额与价税合计不一致"),
                    )
                )

        accounting_commands, canonical_accounting = (
            self._prepare_accounting_documents(
                payload.get("accounting_documents"),
                currency,
                issues,
            )
        )
        if not accounting_commands:
            issues.append(
                self._issue(
                    "NO_ACCOUNTING_DOCUMENT_REFERENCE",
                    "warning",
                    _("电子发票未提供会计凭证关联信息"),
                )
            )

        source_fact_digest = (
            _safe_text(payload.get("source_fact_digest"), 64) or ""
        ).lower()
        if source_fact_digest and not re.fullmatch(
            r"[0-9a-f]{64}",
            source_fact_digest,
        ):
            issues.append(
                self._issue(
                    "INVALID_FACT_DIGEST",
                    "warning",
                    _("源事实摘要哈希格式无效"),
                )
            )
            source_fact_digest = False

        request_time = self._parse_datetime(
            payload.get("request_time"),
            _("开具或申请时间"),
            issues,
        )
        if not request_time:
            issues.append(
                self._issue(
                    "MISSING_REQUEST_TIME",
                    "warning",
                    _("未提供有效的开具或申请时间"),
                )
            )
        severities = {issue["severity"] for issue in issues}
        quality_state = (
            "error"
            if "error" in severities
            else "warning"
            if "warning" in severities
            else "valid"
        )
        canonical = {
            "source_document_key": source_key,
            "invoice_number": invoice_number or None,
            "invoice_type_code": _safe_text(
                payload.get("invoice_type_code"),
                128,
            ),
            "request_time": fields.Datetime.to_string(request_time),
            "seller_name": seller_name or None,
            "seller_tax_id": seller_tax_id or None,
            "accounting_entity_name": accounting_entity_name or None,
            "accounting_entity_tax_id": accounting_entity_tax_id or None,
            "currency_code": currency.name if currency else None,
            "untaxed_amount": untaxed_decimal,
            "tax_amount": tax_decimal,
            "total_amount": total_decimal,
            "is_red": self._tri_state(payload.get("is_red")),
            "is_booked": self._tri_state(payload.get("is_booked")),
            "is_checked": self._tri_state(payload.get("is_checked")),
            "is_paid": self._tri_state(payload.get("is_paid")),
            "contract_number": _safe_text(payload.get("contract_number"), 256),
            "bank_receipt_number": _safe_text(
                payload.get("bank_receipt_number"),
                256,
            ),
            "usage_confirmation": _safe_text(
                payload.get("usage_confirmation"),
                256,
            ),
            "source_fact_count": max(int(payload.get("source_fact_count") or 0), 0),
            "source_fact_digest": source_fact_digest or None,
            "quality_state": quality_state,
            "issues": issues,
            "accounting_documents": canonical_accounting,
        }
        return {
            "parse_run_id": run.id,
            "source_document_key": source_key,
            "invoice_number": invoice_number,
            "invoice_type_code": canonical["invoice_type_code"],
            "request_time": request_time,
            "seller_name": seller_name,
            "seller_tax_id": seller_tax_id or False,
            "accounting_entity_name": accounting_entity_name,
            "accounting_entity_tax_id": accounting_entity_tax_id or False,
            "currency_id": currency.id,
            "has_untaxed_amount": has_untaxed,
            "untaxed_amount": untaxed,
            "has_tax_amount": has_tax,
            "tax_amount": tax,
            "has_total_amount": has_total,
            "total_amount": total,
            "is_red": canonical["is_red"],
            "is_booked": canonical["is_booked"],
            "is_checked": canonical["is_checked"],
            "is_paid": canonical["is_paid"],
            "contract_number": canonical["contract_number"],
            "bank_receipt_number": canonical["bank_receipt_number"],
            "usage_confirmation": canonical["usage_confirmation"],
            "source_fact_count": canonical["source_fact_count"],
            "source_fact_digest": source_fact_digest,
            "quality_state": quality_state,
            "issue_json": issues,
            "document_checksum": _sha256_json(canonical),
            "accounting_document_ids": accounting_commands,
        }


class SudoChinaEinvoiceAccountingDocument(models.Model):
    _name = "sudo.cn.einvoice.accounting.document"
    _description = "China Electronic Invoice Accounting Document Reference"
    _order = "einvoice_document_id, sequence, id"
    _check_company_auto = True

    einvoice_document_id = fields.Many2one(
        "sudo.cn.einvoice.document",
        string="电子发票",
        required=True,
        ondelete="restrict",
        index=True,
        check_company=True,
    )
    company_id = fields.Many2one(
        related="einvoice_document_id.company_id",
        store=True,
        index=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        related="einvoice_document_id.currency_id",
        store=True,
        readonly=True,
    )
    sequence = fields.Integer(string="顺序", required=True, readonly=True)
    voucher_number = fields.Char(string="会计凭证编号", readonly=True)
    posting_date = fields.Date(string="入账日期", readonly=True)
    accounting_period = fields.Char(string="会计期间", readonly=True)
    summary = fields.Text(string="会计凭证摘要", readonly=True)
    debit_total = fields.Monetary(
        string="借方合计",
        currency_field="currency_id",
        readonly=True,
    )
    credit_total = fields.Monetary(
        string="贷方合计",
        currency_field="currency_id",
        readonly=True,
    )
    balance_difference = fields.Monetary(
        string="借贷差额",
        currency_field="currency_id",
        readonly=True,
    )
    entry_ids = fields.One2many(
        "sudo.cn.einvoice.accounting.entry",
        "accounting_document_id",
        string="借贷分录",
        readonly=True,
    )

    _sequence_unique = models.Constraint(
        "unique(einvoice_document_id, sequence)",
        "同一电子发票中的会计凭证顺序必须唯一。",
    )

    @api.model_create_multi
    def create(self, vals_list):
        if (
            self.env.context.get("cn_normalized_record_transition")
            is not _NORMALIZED_RECORD_MARKER
        ):
            raise AccessError(_("会计凭证引用只能由受控解析流程创建。"))
        return super().create(vals_list)

    def write(self, values):
        raise AccessError(_("会计凭证引用不可修改。"))

    def unlink(self):
        raise AccessError(_("会计凭证引用不可删除。"))


class SudoChinaEinvoiceAccountingEntry(models.Model):
    _name = "sudo.cn.einvoice.accounting.entry"
    _description = "China Electronic Invoice Accounting Entry"
    _order = "accounting_document_id, sequence, id"
    _check_company_auto = True

    accounting_document_id = fields.Many2one(
        "sudo.cn.einvoice.accounting.document",
        string="会计凭证引用",
        required=True,
        ondelete="restrict",
        index=True,
        check_company=True,
    )
    company_id = fields.Many2one(
        related="accounting_document_id.company_id",
        store=True,
        index=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        related="accounting_document_id.currency_id",
        store=True,
        readonly=True,
    )
    sequence = fields.Integer(string="顺序", required=True, readonly=True)
    direction = fields.Selection(
        [("debit", "借方"), ("credit", "贷方"), ("unknown", "无法识别")],
        string="借贷方向",
        required=True,
        readonly=True,
    )
    general_ledger_subject = fields.Char(string="总账科目名称", readonly=True)
    subsidiary_ledger_subject = fields.Char(string="明细科目名称", readonly=True)
    amount = fields.Monetary(
        string="入账金额",
        currency_field="currency_id",
        readonly=True,
    )

    _sequence_unique = models.Constraint(
        "unique(accounting_document_id, sequence)",
        "同一会计凭证引用中的分录顺序必须唯一。",
    )
    @api.model_create_multi
    def create(self, vals_list):
        if (
            self.env.context.get("cn_normalized_record_transition")
            is not _NORMALIZED_RECORD_MARKER
        ):
            raise AccessError(_("借贷分录只能由受控解析流程创建。"))
        return super().create(vals_list)

    def write(self, values):
        raise AccessError(_("规范化借贷分录不可修改。"))

    def unlink(self):
        raise AccessError(_("规范化借贷分录不可删除。"))
