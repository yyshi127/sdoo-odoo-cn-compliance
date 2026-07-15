import hashlib
import json

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


_DATASET_TRANSITION_MARKER = object()

DATASET_TYPES = (
    ("electronic_invoice", "电子发票与电子凭证"),
    ("vat_filing", "增值税申报数据"),
    ("tax_payment", "税款缴纳数据"),
    ("iit_withholding", "个人所得税扣缴数据"),
    ("bank_evidence", "银行与支付证据"),
    ("other_regulatory", "其他监管数据"),
)


class SudoChinaExternalDataset(models.Model):
    _name = "sudo.cn.external.dataset"
    _description = "China Controlled External Dataset"
    _order = "period_end desc, period_start desc, id desc"
    _check_company_auto = True

    name = fields.Char(compute="_compute_name", store=True)
    profile_id = fields.Many2one(
        "sudo.compliance.profile",
        string="合规档案",
        required=True,
        ondelete="restrict",
        index=True,
        check_company=True,
    )
    company_id = fields.Many2one(
        related="profile_id.company_id",
        store=True,
        index=True,
        readonly=True,
    )
    country_id = fields.Many2one(
        related="profile_id.country_id",
        store=True,
        index=True,
        readonly=True,
    )
    dataset_type = fields.Selection(
        DATASET_TYPES,
        string="数据集类型",
        required=True,
        index=True,
    )
    period_start = fields.Date(string="覆盖开始日", required=True, index=True)
    period_end = fields.Date(string="覆盖结束日", required=True, index=True)
    coverage_scope = fields.Selection(
        [
            ("full", "声明为完整数据集"),
            ("partial", "部分数据"),
            ("sample", "抽样数据"),
        ],
        string="覆盖范围",
        required=True,
        default="partial",
    )
    scope_note = fields.Text(
        string="范围与限制",
        help="说明覆盖口径、缺失范围、筛选条件和仍未消除的不确定性。",
    )
    source_channel = fields.Selection(
        [
            ("official_export", "企业自有官方系统导出"),
            ("direct_api", "经授权接口获取"),
            ("signed_electronic_voucher", "结构化电子凭证原件"),
            ("authorized_platform", "经授权第三方平台"),
            ("professional_workpaper", "专业工作底稿"),
            ("other_controlled", "其他受控来源"),
        ],
        string="取得渠道",
    )
    source_system_name = fields.Char(string="来源系统")
    source_reference = fields.Char(
        string="来源批次或引用",
        help="记录导出批次、回执号、接口请求号或其他可追溯引用。",
    )
    source_generated_at = fields.Datetime(string="源文件生成时间")
    data_format = fields.Selection(
        [
            ("xbrl", "XBRL"),
            ("xml", "XML"),
            ("xlsx", "Excel"),
            ("csv", "CSV"),
            ("json", "JSON"),
            ("pdf", "PDF"),
            ("zip", "ZIP"),
            ("other", "其他"),
        ],
        string="数据格式",
    )
    authorization_basis = fields.Text(
        string="取得授权与依据",
        help="说明企业自有、客户授权、接口授权或其他合法取得依据。",
    )
    acquired_at = fields.Datetime(
        string="取得时间",
        required=True,
        default=fields.Datetime.now,
    )
    acquired_by_id = fields.Many2one(
        "res.users",
        string="采集人",
        required=True,
        default=lambda self: self.env.user,
        readonly=True,
        index=True,
    )
    contains_sensitive_data = fields.Boolean(string="包含个人或敏感数据")
    data_control_note = fields.Text(
        string="数据保护说明",
        help="记录访问限制、脱敏、保存期限和授权边界。",
    )
    declared_record_count = fields.Integer(
        string="源文件声明记录数",
        default=0,
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="声明金额币种",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    declared_total_amount = fields.Monetary(
        string="源文件声明价税合计",
        currency_field="currency_id",
    )
    declared_tax_amount = fields.Monetary(
        string="源文件声明税额",
        currency_field="currency_id",
    )
    source_attachment_ids = fields.Many2many(
        "ir.attachment",
        "sudo_cn_external_dataset_source_attachment_rel",
        "dataset_id",
        "attachment_id",
        string="源文件",
    )
    authenticity_state = fields.Selection(
        [
            ("not_checked", "尚未验证"),
            ("official_tool_passed", "已记录受控工具通过结果"),
            ("official_tool_failed", "已记录受控工具失败结果"),
            ("unavailable", "当前无法验证"),
            ("not_applicable", "不适用"),
        ],
        string="真实性验证",
        required=True,
        default="not_checked",
        index=True,
    )
    authenticity_method = fields.Char(string="验证工具或方法")
    authenticity_reference = fields.Char(string="验证结果引用")
    authenticity_evidence_attachment_ids = fields.Many2many(
        "ir.attachment",
        "sudo_cn_external_dataset_auth_attachment_rel",
        "dataset_id",
        "attachment_id",
        string="验证证据",
    )
    separation_exception_reason = fields.Text(
        string="非独立复核例外理由",
        help="仅在测试或确无第二复核人时使用；例外会进入审计轨迹。",
    )
    state = fields.Selection(
        [
            ("draft", "待完善"),
            ("sealed", "已封存"),
            ("superseded", "已替代"),
        ],
        string="状态",
        required=True,
        default="draft",
        readonly=True,
        index=True,
    )
    sealed_at = fields.Datetime(string="封存时间", readonly=True, copy=False)
    sealed_by_id = fields.Many2one(
        "res.users",
        string="复核封存人",
        readonly=True,
        copy=False,
    )
    seal_checksum = fields.Char(
        string="封存校验和",
        readonly=True,
        copy=False,
    )
    sealed_file_manifest_json = fields.Json(
        string="封存文件哈希清单",
        readonly=True,
        copy=False,
    )
    integrity_state = fields.Selection(
        [
            ("unsealed", "未封存"),
            ("verified", "完整性正常"),
            ("checksum_mismatch", "封存后资料已变化"),
        ],
        string="文件完整性",
        compute="_compute_integrity_state",
    )
    review_control_state = fields.Selection(
        [
            ("pending", "待复核"),
            ("independent", "独立复核"),
            ("exception", "单人例外"),
        ],
        string="复核控制",
        compute="_compute_review_control_state",
    )
    supersedes_id = fields.Many2one(
        "sudo.cn.external.dataset",
        string="替代原数据集",
        ondelete="restrict",
        index=True,
        copy=False,
    )
    replacement_ids = fields.One2many(
        "sudo.cn.external.dataset",
        "supersedes_id",
        string="替代版本",
        readonly=True,
        copy=False,
    )

    _record_count_nonnegative = models.Constraint(
        "CHECK(declared_record_count >= 0)",
        "源文件声明记录数不能小于零。",
    )
    _supersedes_unique = models.Constraint(
        "unique(supersedes_id)",
        "同一数据集只能有一个直接替代版本。",
    )

    _controlled_fields = {
        "profile_id",
        "dataset_type",
        "period_start",
        "period_end",
        "coverage_scope",
        "scope_note",
        "source_channel",
        "source_system_name",
        "source_reference",
        "source_generated_at",
        "data_format",
        "authorization_basis",
        "acquired_at",
        "contains_sensitive_data",
        "data_control_note",
        "declared_record_count",
        "currency_id",
        "declared_total_amount",
        "declared_tax_amount",
        "source_attachment_ids",
        "authenticity_state",
        "authenticity_method",
        "authenticity_reference",
        "authenticity_evidence_attachment_ids",
        "separation_exception_reason",
        "supersedes_id",
    }
    _protected_fields = {
        "acquired_by_id",
        "state",
        "sealed_at",
        "sealed_by_id",
        "seal_checksum",
        "sealed_file_manifest_json",
    }
    _normalized_text_fields = {
        "scope_note",
        "source_system_name",
        "source_reference",
        "authorization_basis",
        "data_control_note",
        "authenticity_method",
        "authenticity_reference",
        "separation_exception_reason",
    }

    @api.depends(
        "profile_id",
        "dataset_type",
        "period_start",
        "period_end",
    )
    def _compute_name(self):
        type_labels = dict(DATASET_TYPES)
        for dataset in self:
            profile_name = dataset.profile_id.display_name or _("中国合规档案")
            type_label = type_labels.get(dataset.dataset_type, _("外部数据"))
            start = fields.Date.to_string(dataset.period_start) or "-"
            end = fields.Date.to_string(dataset.period_end) or "-"
            dataset.name = "%s / %s / %s - %s" % (
                profile_name,
                type_label,
                start,
                end,
            )

    @api.depends("state", "acquired_by_id", "sealed_by_id")
    def _compute_review_control_state(self):
        for dataset in self:
            if dataset.state == "draft" or not dataset.sealed_by_id:
                dataset.review_control_state = "pending"
            elif dataset.sealed_by_id == dataset.acquired_by_id:
                dataset.review_control_state = "exception"
            else:
                dataset.review_control_state = "independent"

    @api.model
    def _attachment_payload(self, attachments):
        payload = []
        for attachment in attachments.sudo().sorted("id"):
            raw = attachment.raw or b""
            if isinstance(raw, str):
                raw = raw.encode("utf-8")
            else:
                raw = bytes(raw)
            payload.append(
                {
                    "id": attachment.id,
                    "name": attachment.name,
                    "mimetype": attachment.mimetype,
                    "file_size": attachment.file_size,
                    "odoo_checksum": attachment.checksum,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
            )
        return payload

    def _checksum_payload(self):
        self.ensure_one()
        return {
            "profile_id": self.profile_id.id,
            "company_id": self.company_id.id,
            "dataset_type": self.dataset_type,
            "period_start": fields.Date.to_string(self.period_start),
            "period_end": fields.Date.to_string(self.period_end),
            "coverage_scope": self.coverage_scope,
            "scope_note": self.scope_note or None,
            "source_channel": self.source_channel,
            "source_system_name": self.source_system_name or None,
            "source_reference": self.source_reference or None,
            "source_generated_at": fields.Datetime.to_string(
                self.source_generated_at
            ),
            "data_format": self.data_format,
            "authorization_basis": self.authorization_basis or None,
            "acquired_at": fields.Datetime.to_string(self.acquired_at),
            "acquired_by_id": self.acquired_by_id.id,
            "contains_sensitive_data": self.contains_sensitive_data,
            "data_control_note": self.data_control_note or None,
            "declared_record_count": self.declared_record_count,
            "currency_id": self.currency_id.id,
            "declared_total_amount": self.declared_total_amount,
            "declared_tax_amount": self.declared_tax_amount,
            "authenticity_state": self.authenticity_state,
            "authenticity_method": self.authenticity_method or None,
            "authenticity_reference": self.authenticity_reference or None,
            "separation_exception_reason": (
                self.separation_exception_reason or None
            ),
            "supersedes_id": self.supersedes_id.id or None,
            "source_attachments": self._attachment_payload(
                self.source_attachment_ids
            ),
            "authenticity_evidence": self._attachment_payload(
                self.authenticity_evidence_attachment_ids
            ),
        }

    def _current_checksum(self, payload=None):
        self.ensure_one()
        payload = self._checksum_payload() if payload is None else payload
        return hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    def _current_integrity_state(self):
        self.ensure_one()
        if self.state == "draft" or not self.seal_checksum:
            return "unsealed"
        manifest = self.sealed_file_manifest_json or {}
        expected_source = self._manifest_probe(
            manifest.get("source_attachments", [])
        )
        expected_authenticity = self._manifest_probe(
            manifest.get("authenticity_evidence", [])
        )
        current_source = self._attachment_probe(self.source_attachment_ids)
        current_authenticity = self._attachment_probe(
            self.authenticity_evidence_attachment_ids
        )
        if (
            expected_source == current_source
            and expected_authenticity == current_authenticity
        ):
            return "verified"
        return "checksum_mismatch"

    @api.model
    def _manifest_probe(self, manifest):
        keys = ("id", "name", "mimetype", "file_size", "odoo_checksum")
        return [
            {key: item.get(key) for key in keys}
            for item in sorted(manifest, key=lambda item: item.get("id") or 0)
        ]

    @api.model
    def _attachment_probe(self, attachments):
        return [
            {
                "id": attachment.id,
                "name": attachment.name,
                "mimetype": attachment.mimetype,
                "file_size": attachment.file_size,
                "odoo_checksum": attachment.checksum,
            }
            for attachment in attachments.sudo().sorted("id")
        ]

    @api.depends(
        "state",
        "seal_checksum",
        "source_attachment_ids",
        "source_attachment_ids.checksum",
        "source_attachment_ids.file_size",
        "source_attachment_ids.name",
        "source_attachment_ids.mimetype",
        "authenticity_evidence_attachment_ids",
        "authenticity_evidence_attachment_ids.checksum",
        "authenticity_evidence_attachment_ids.file_size",
        "authenticity_evidence_attachment_ids.name",
        "authenticity_evidence_attachment_ids.mimetype",
        "dataset_type",
        "period_start",
        "period_end",
        "coverage_scope",
        "scope_note",
        "source_channel",
        "source_system_name",
        "source_reference",
        "source_generated_at",
        "data_format",
        "authorization_basis",
        "acquired_at",
        "acquired_by_id",
        "contains_sensitive_data",
        "data_control_note",
        "declared_record_count",
        "currency_id",
        "declared_total_amount",
        "declared_tax_amount",
        "authenticity_state",
        "authenticity_method",
        "authenticity_reference",
        "separation_exception_reason",
        "supersedes_id",
    )
    def _compute_integrity_state(self):
        for dataset in self:
            dataset.integrity_state = dataset._current_integrity_state()

    @api.model
    def _normalize_text_values(self, values):
        for field_name in self._normalized_text_fields & set(values):
            value = values[field_name]
            if isinstance(value, str):
                values[field_name] = value.strip() or False

    @api.model
    def _invalid_binary_attachments(self, attachments):
        return attachments.sudo().filtered(
            lambda attachment: attachment.type != "binary" or not attachment.raw
        )

    def _sealing_issues(self):
        self.ensure_one()
        issues = []
        required_values = (
            (self.source_channel, _("未选择取得渠道")),
            (self.source_system_name, _("未填写来源系统")),
            (self.source_reference, _("未填写来源批次或引用")),
            (self.source_generated_at, _("未填写源文件生成时间")),
            (self.data_format, _("未选择数据格式")),
            (self.authorization_basis, _("未记录取得授权与依据")),
            (self.scope_note, _("未记录范围与限制")),
        )
        issues.extend(message for value, message in required_values if not value)
        if self.declared_record_count <= 0:
            issues.append(_("源文件声明记录数必须大于零"))
        if not self.source_attachment_ids:
            issues.append(_("未上传源文件"))
        elif self._invalid_binary_attachments(self.source_attachment_ids):
            issues.append(_("源文件必须是系统内保存的非空二进制附件"))
        if self.contains_sensitive_data and not self.data_control_note:
            issues.append(_("包含个人或敏感数据时必须记录数据保护说明"))
        if self.authenticity_state in (
            "official_tool_passed",
            "official_tool_failed",
        ):
            if not self.authenticity_method:
                issues.append(_("未记录真实性验证工具或方法"))
            if not self.authenticity_reference:
                issues.append(_("未记录真实性验证结果引用"))
            if not self.authenticity_evidence_attachment_ids:
                issues.append(_("未上传真实性验证证据"))
            elif self._invalid_binary_attachments(
                self.authenticity_evidence_attachment_ids
            ):
                issues.append(_("真实性验证证据必须是非空二进制附件"))
        if (
            self.source_channel == "signed_electronic_voucher"
            and self.authenticity_state != "official_tool_passed"
        ):
            issues.append(_("结构化电子凭证原件必须留存受控工具通过结果"))
        if self.source_generated_at:
            generated_date = fields.Datetime.context_timestamp(
                self,
                self.source_generated_at,
            ).date()
            if self.period_end > generated_date:
                issues.append(_("覆盖结束日不能晚于源文件生成日期"))
        if self.acquired_by_id == self.env.user:
            reason = self.separation_exception_reason or ""
            if len(reason) < 20:
                issues.append(
                    _("采集人与封存人为同一人时，必须填写不少于 20 字的例外理由")
                )
        return issues

    @api.constrains("profile_id")
    def _check_china_profile(self):
        for dataset in self:
            if dataset.country_id.code != "CN":
                raise ValidationError(_("中国外部数据集只能关联中国合规档案。"))

    @api.constrains("period_start", "period_end")
    def _check_period(self):
        for dataset in self:
            if dataset.period_end < dataset.period_start:
                raise ValidationError(_("覆盖结束日不能早于开始日。"))

    @api.constrains("source_generated_at", "acquired_at")
    def _check_source_times(self):
        now = fields.Datetime.now()
        for dataset in self:
            if dataset.source_generated_at and dataset.source_generated_at > now:
                raise ValidationError(_("源文件生成时间不能晚于当前时间。"))
            if dataset.acquired_at and dataset.acquired_at > now:
                raise ValidationError(_("取得时间不能晚于当前时间。"))
            if (
                dataset.source_generated_at
                and dataset.acquired_at
                and dataset.acquired_at < dataset.source_generated_at
            ):
                raise ValidationError(_("取得时间不能早于源文件生成时间。"))

    @api.constrains("supersedes_id", "profile_id", "dataset_type")
    def _check_supersession(self):
        for dataset in self.filtered("supersedes_id"):
            original = dataset.supersedes_id
            if original == dataset:
                raise ValidationError(_("数据集不能替代自身。"))
            if original.profile_id != dataset.profile_id:
                raise ValidationError(_("替代版本必须属于同一合规档案。"))
            if original.dataset_type != dataset.dataset_type:
                raise ValidationError(_("替代版本必须保持相同的数据集类型。"))
            if original.state != "sealed":
                raise ValidationError(_("只能替代当前已封存的数据集。"))

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            self._normalize_text_values(values)
            values.update(
                {
                    "acquired_by_id": self.env.user.id,
                    "state": "draft",
                    "sealed_at": False,
                    "sealed_by_id": False,
                    "seal_checksum": False,
                    "sealed_file_manifest_json": False,
                }
            )
        records = super().create(vals_list)
        self.env["sudo.compliance.audit.event"]._log_records(
            records,
            "cn_external_dataset.created",
            new_state="draft",
        )
        return records

    def write(self, values):
        self._normalize_text_values(values)
        transition = (
            self.env.context.get("cn_dataset_transition")
            is _DATASET_TRANSITION_MARKER
        )
        changed_fields = sorted(set(values) & self._controlled_fields)
        if set(values) & self._protected_fields and not transition:
            raise AccessError(_("请使用外部数据集上的受控操作更新状态。"))
        locked = self.filtered(lambda dataset: dataset.state != "draft")
        if changed_fields and locked and not transition:
            raise AccessError(_("已封存或已替代的数据集不可修改，请创建替代版本。"))
        result = super().write(values)
        if changed_fields and not transition:
            for dataset in self:
                self.env["sudo.compliance.audit.event"]._log_records(
                    dataset,
                    "cn_external_dataset.changed",
                    previous_state="draft",
                    new_state="draft",
                    details={"changed_fields": changed_fields},
                )
        return result

    def unlink(self):
        if self.filtered(lambda dataset: dataset.state != "draft"):
            raise UserError(_("已封存或已替代的数据集不可删除。"))
        self.env["sudo.compliance.audit.event"]._log_records(
            self,
            "cn_external_dataset.deleted",
            previous_state="draft",
        )
        return super().unlink()

    def copy(self, default=None):
        values = dict(default or {})
        values.update(
            {
                "acquired_at": fields.Datetime.now(),
                "acquired_by_id": self.env.user.id,
                "state": "draft",
                "sealed_at": False,
                "sealed_by_id": False,
                "seal_checksum": False,
                "sealed_file_manifest_json": False,
                "separation_exception_reason": False,
            }
        )
        if "supersedes_id" not in values:
            values["supersedes_id"] = False
        return super().copy(values)

    def action_seal(self):
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以复核并封存外部数据集。"))
        for dataset in self:
            if dataset.state != "draft":
                raise UserError(_("只有待完善的数据集可以封存。"))
            issues = dataset._sealing_issues()
            if issues:
                raise UserError(
                    _(
                        "外部数据集尚不能封存：\n- %(issues)s",
                        issues="\n- ".join(issues),
                    )
                )
            payload = dataset._checksum_payload()
            checksum = dataset._current_checksum(payload)
            file_manifest = {
                "source_attachments": payload["source_attachments"],
                "authenticity_evidence": payload[
                    "authenticity_evidence"
                ],
            }
            dataset.with_context(
                cn_dataset_transition=_DATASET_TRANSITION_MARKER
            ).write(
                {
                    "state": "sealed",
                    "sealed_at": fields.Datetime.now(),
                    "sealed_by_id": self.env.user.id,
                    "seal_checksum": checksum,
                    "sealed_file_manifest_json": file_manifest,
                }
            )
            if dataset.supersedes_id:
                original = dataset.supersedes_id
                original.with_context(
                    cn_dataset_transition=_DATASET_TRANSITION_MARKER
                ).write({"state": "superseded"})
                self.env["sudo.compliance.audit.event"]._log_records(
                    original,
                    "cn_external_dataset.superseded",
                    previous_state="sealed",
                    new_state="superseded",
                    details={
                        "replacement_id": dataset.id,
                        "replacement_checksum": checksum,
                    },
                )
            self.env["sudo.compliance.audit.event"]._log_records(
                dataset,
                "cn_external_dataset.sealed",
                previous_state="draft",
                new_state="sealed",
                details={
                    "checksum": checksum,
                    "dataset_type": dataset.dataset_type,
                    "coverage_scope": dataset.coverage_scope,
                    "source_attachment_count": len(
                        dataset.source_attachment_ids
                    ),
                    "authenticity_state": dataset.authenticity_state,
                    "independent_review": (
                        dataset.acquired_by_id != dataset.sealed_by_id
                    ),
                    "separation_exception_used": (
                        dataset.acquired_by_id == dataset.sealed_by_id
                    ),
                },
            )
        return True

    def action_create_replacement(self):
        self.ensure_one()
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以创建替代版本。"))
        if self.state != "sealed":
            raise UserError(_("只有当前已封存的数据集可以创建替代版本。"))
        if self.replacement_ids:
            raise UserError(_("该数据集已经存在替代版本。"))
        replacement = self.copy({"supersedes_id": self.id})
        self.env["sudo.compliance.audit.event"]._log_records(
            self,
            "cn_external_dataset.replacement_draft_created",
            previous_state="sealed",
            new_state="sealed",
            details={"replacement_id": replacement.id},
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("外部数据集替代版本"),
            "res_model": self._name,
            "res_id": replacement.id,
            "view_mode": "form",
            "view_id": self.env.ref(
                "sudo_country_pack_cn.view_cn_external_dataset_form"
            ).id,
            "target": "current",
        }
