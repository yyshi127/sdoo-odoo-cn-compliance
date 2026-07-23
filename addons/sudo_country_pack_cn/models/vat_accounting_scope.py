import hashlib
import json

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


_MAPPING_TRANSITION_MARKER = object()
_ADJUSTMENT_TRANSITION_MARKER = object()
_VAT_ACCOUNTING_CHECKSUM_LANG = "en_US"


def _attachment_manifest(attachments):
    manifest = []
    for attachment in attachments.sudo().sorted("id"):
        raw = attachment.raw or b""
        raw = raw.encode("utf-8") if isinstance(raw, str) else bytes(raw)
        manifest.append(
            {
                "id": attachment.id,
                "name": attachment.name,
                "mimetype": attachment.mimetype,
                "file_size": attachment.file_size,
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    return manifest


def _payload_checksum(payload):
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _invalid_binary_attachments(attachments):
    return attachments.sudo().filtered(
        lambda attachment: attachment.type != "binary" or not attachment.raw
    )


class SudoChinaVatAccountMapping(models.Model):
    _name = "sudo.cn.vat.account.mapping"
    _description = "China VAT Control Account Mapping"
    _order = "profile_id, role, valid_from desc, account_id, id desc"
    _check_company_auto = True

    name = fields.Char(compute="_compute_name", store=True)
    profile_id = fields.Many2one(
        "sudo.compliance.profile",
        string="合规档案",
        required=True,
        ondelete="cascade",
        index=True,
        check_company=True,
    )
    company_id = fields.Many2one(
        related="profile_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    country_id = fields.Many2one(
        related="profile_id.country_id",
        store=True,
        readonly=True,
    )
    account_id = fields.Many2one(
        "account.account",
        string="增值税控制科目",
        required=True,
        ondelete="restrict",
        check_company=True,
        domain="[('company_ids', 'in', [company_id])]",
    )
    role = fields.Selection(
        [
            ("output", "销项税额"),
            ("input", "进项税额"),
        ],
        string="科目角色",
        required=True,
        index=True,
    )
    valid_from = fields.Date(
        string="有效开始日",
        required=True,
        default=fields.Date.context_today,
        index=True,
    )
    valid_to = fields.Date(string="有效结束日", index=True)
    source_reference = fields.Char(string="配置依据引用")
    scope_note = fields.Text(
        string="映射口径与限制",
        help="说明科目余额方向、覆盖业务、排除范围和仍需人工处理的边界。",
    )
    evidence_attachment_ids = fields.Many2many(
        "ir.attachment",
        "sudo_cn_vat_account_mapping_attachment_rel",
        "mapping_id",
        "attachment_id",
        string="配置工作底稿",
    )
    separation_exception_reason = fields.Text(
        string="同人复核例外理由",
        help="配置人与核验人为同一人时，记录受控例外原因。",
    )
    state = fields.Selection(
        [("draft", "待核验"), ("verified", "已核验")],
        string="状态",
        required=True,
        default="draft",
        readonly=True,
        index=True,
    )
    verified_at = fields.Datetime(string="核验时间", readonly=True, copy=False)
    verified_by_id = fields.Many2one(
        "res.users",
        string="核验人",
        readonly=True,
        copy=False,
    )
    verification_checksum = fields.Char(
        string="核验 SHA-256",
        readonly=True,
        copy=False,
    )
    integrity_state = fields.Selection(
        [
            ("unverified", "未核验"),
            ("verified", "完整性正常"),
            ("checksum_mismatch", "配置已变化"),
        ],
        string="配置完整性",
        compute="_compute_integrity_state",
    )

    _controlled_fields = {
        "profile_id",
        "account_id",
        "role",
        "valid_from",
        "valid_to",
        "source_reference",
        "scope_note",
        "evidence_attachment_ids",
        "separation_exception_reason",
    }
    _protected_fields = {
        "state",
        "verified_at",
        "verified_by_id",
        "verification_checksum",
    }
    _normalized_text_fields = {
        "source_reference",
        "scope_note",
        "separation_exception_reason",
    }

    @api.depends("profile_id", "account_id", "role", "valid_from")
    def _compute_name(self):
        role_labels = dict(self._fields["role"].selection)
        for mapping in self:
            code = mapping.account_id.with_company(mapping.company_id).code or "-"
            mapping.name = "%s / %s / %s" % (
                mapping.profile_id.display_name or _("中国增值税科目映射"),
                role_labels.get(mapping.role, mapping.role or "-"),
                code,
            )

    def _checksum_payload(self):
        self.ensure_one()
        account = self.account_id.with_company(self.company_id)
        return {
            "profile_id": self.profile_id.id,
            "company_id": self.company_id.id,
            "account_id": account.id,
            "account_code": account.code or None,
            "account_name": account.name or None,
            "account_type": account.account_type or None,
            "role": self.role,
            "valid_from": fields.Date.to_string(self.valid_from),
            "valid_to": fields.Date.to_string(self.valid_to),
            "source_reference": self.source_reference or None,
            "scope_note": self.scope_note or None,
            "separation_exception_reason": (
                self.separation_exception_reason or None
            ),
            "attachments": _attachment_manifest(self.evidence_attachment_ids),
        }

    def _current_checksum(self):
        self.ensure_one()
        return self._checksum_for_language(_VAT_ACCOUNTING_CHECKSUM_LANG)

    def _checksum_for_language(self, lang):
        self.ensure_one()
        return _payload_checksum(
            self.with_context(lang=lang)._checksum_payload()
        )

    def _current_integrity_state(self):
        self.ensure_one()
        if self.state != "verified" or not self.verification_checksum:
            return "unverified"
        if self.verification_checksum == self._current_checksum():
            return "verified"
        return "checksum_mismatch"

    @api.depends(
        "state",
        "verification_checksum",
        "account_id",
        "account_id.code",
        "account_id.name",
        "account_id.account_type",
        "role",
        "valid_from",
        "valid_to",
        "source_reference",
        "scope_note",
        "separation_exception_reason",
        "evidence_attachment_ids",
    )
    def _compute_integrity_state(self):
        for mapping in self:
            mapping.integrity_state = mapping._current_integrity_state()

    @api.model
    def _for_profile_period(self, profile, period_start, period_end):
        return self.search(
            [
                ("profile_id", "=", profile.id),
                ("state", "=", "verified"),
                ("valid_from", "<=", period_start),
                "|",
                ("valid_to", "=", False),
                ("valid_to", ">=", period_end),
            ],
            order="role, account_id, id",
        )

    @api.model
    def _overlapping_for_profile_period(self, profile, period_start, period_end):
        return self.search(
            [
                ("profile_id", "=", profile.id),
                ("state", "=", "verified"),
                ("valid_from", "<=", period_end),
                "|",
                ("valid_to", "=", False),
                ("valid_to", ">=", period_start),
            ],
            order="role, account_id, id",
        )

    def _overlapping_verified(self):
        self.ensure_one()
        domain = [
            ("profile_id", "=", self.profile_id.id),
            ("account_id", "=", self.account_id.id),
            ("state", "=", "verified"),
            ("id", "!=", self.id),
            "|",
            ("valid_to", "=", False),
            ("valid_to", ">=", self.valid_from),
        ]
        if self.valid_to:
            domain.append(("valid_from", "<=", self.valid_to))
        return self.search(domain)

    def _verification_issues(self):
        self.ensure_one()
        issues = []
        if self.country_id.code != "CN":
            issues.append(_("不是中国合规档案"))
        if self.company_id not in self.account_id.company_ids:
            issues.append(_("控制科目不属于档案公司"))
        if not self.source_reference:
            issues.append(_("未填写配置依据引用"))
        if not self.scope_note:
            issues.append(_("未记录映射口径与限制"))
        if not self.evidence_attachment_ids:
            issues.append(_("未上传配置工作底稿"))
        elif _invalid_binary_attachments(self.evidence_attachment_ids):
            issues.append(_("配置工作底稿必须是系统内非空二进制附件"))
        if self.create_uid == self.env.user:
            reason = self.separation_exception_reason or ""
            if len(reason) < 20:
                issues.append(_("配置人与核验人为同一人时，必须填写不少于 20 字的例外理由"))
        return issues

    @api.model
    def _normalize_text_values(self, values):
        for field_name in self._normalized_text_fields & set(values):
            value = values[field_name]
            if isinstance(value, str):
                values[field_name] = value.strip() or False

    @api.constrains("profile_id")
    def _check_china_profile(self):
        for mapping in self:
            if mapping.country_id.code != "CN":
                raise ValidationError(_("增值税控制科目只能关联中国合规档案。"))

    @api.constrains("account_id", "company_id")
    def _check_account_company(self):
        for mapping in self:
            if mapping.company_id not in mapping.account_id.company_ids:
                raise ValidationError(_("增值税控制科目必须属于档案公司。"))

    @api.constrains("valid_from", "valid_to")
    def _check_validity_dates(self):
        for mapping in self:
            if mapping.valid_to and mapping.valid_to < mapping.valid_from:
                raise ValidationError(_("有效结束日不能早于开始日。"))

    @api.constrains("profile_id", "account_id", "valid_from", "valid_to", "state")
    def _check_verified_overlap(self):
        for mapping in self.filtered(lambda record: record.state == "verified"):
            if mapping._overlapping_verified():
                raise ValidationError(
                    _("同一控制科目在同一期间只能有一份已核验映射。")
                )

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            self._normalize_text_values(values)
            values.update(
                {
                    "state": "draft",
                    "verified_at": False,
                    "verified_by_id": False,
                    "verification_checksum": False,
                }
            )
        records = super().create(vals_list)
        self.env["sudo.compliance.audit.event"]._log_records(
            records,
            "cn_vat_account_mapping.created",
            new_state="draft",
        )
        return records

    def write(self, values):
        self._normalize_text_values(values)
        transition = (
            self.env.context.get("cn_vat_mapping_transition")
            is _MAPPING_TRANSITION_MARKER
        )
        changed_fields = sorted(set(values) & self._controlled_fields)
        if set(values) & self._protected_fields and not transition:
            raise AccessError(_("请使用控制科目映射上的核验操作更新状态。"))
        verified = self.filtered(lambda record: record.state == "verified")
        if changed_fields and verified and not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以修改已核验的控制科目映射。"))
        previous = {
            record.id: {
                "state": record.state,
                "checksum": record.verification_checksum,
            }
            for record in self
        }
        if changed_fields and not transition:
            values.update(
                {
                    "state": "draft",
                    "verified_at": False,
                    "verified_by_id": False,
                    "verification_checksum": False,
                }
            )
        result = super().write(values)
        if changed_fields and not transition:
            for record in self:
                self.env["sudo.compliance.audit.event"]._log_records(
                    record,
                    "cn_vat_account_mapping.changed",
                    previous_state=previous[record.id]["state"],
                    new_state=record.state,
                    details={
                        "changed_fields": changed_fields,
                        "previous_checksum": previous[record.id]["checksum"],
                        "verification_reset": True,
                    },
                )
        return result

    def unlink(self):
        used = self.env[
            "sudo.cn.vat.period.reconciliation.run"
        ].sudo().search_count(
            [("control_account_mapping_ids", "in", self.ids)]
        )
        if used:
            raise UserError(_("已进入期间勾稽快照的控制科目映射不可删除。"))
        if self.filtered(lambda record: record.state == "verified"):
            raise UserError(_("已核验的控制科目映射不可删除。"))
        return super().unlink()

    def copy(self, default=None):
        values = dict(default or {})
        values.update(
            {
                "state": "draft",
                "verified_at": False,
                "verified_by_id": False,
                "verification_checksum": False,
                "separation_exception_reason": False,
            }
        )
        return super().copy(values)

    def action_verify(self):
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以核验增值税控制科目映射。"))
        for mapping in self:
            if mapping.state != "draft":
                raise UserError(_("只有待核验的控制科目映射可以执行核验。"))
            issues = mapping._verification_issues()
            if issues:
                raise UserError(
                    _(
                        "控制科目映射尚不能核验：\n- %(issues)s",
                        issues="\n- ".join(issues),
                    )
                )
            if mapping._overlapping_verified():
                raise UserError(_("同一期间已有该控制科目的已核验映射。"))
            payload = mapping.with_context(
                lang=_VAT_ACCOUNTING_CHECKSUM_LANG
            )._checksum_payload()
            checksum = _payload_checksum(payload)
            mapping.with_context(
                cn_vat_mapping_transition=_MAPPING_TRANSITION_MARKER
            ).write(
                {
                    "state": "verified",
                    "verified_at": fields.Datetime.now(),
                    "verified_by_id": self.env.user.id,
                    "verification_checksum": checksum,
                }
            )
            self.env["sudo.compliance.audit.event"]._log_records(
                mapping,
                "cn_vat_account_mapping.verified",
                previous_state="draft",
                new_state="verified",
                details={
                    "checksum": checksum,
                    "role": mapping.role,
                    "account_id": mapping.account_id.id,
                    "valid_from": fields.Date.to_string(mapping.valid_from),
                    "valid_to": fields.Date.to_string(mapping.valid_to),
                    "independent_review": mapping.create_uid != self.env.user,
                },
            )
        return True

    def action_reset_to_draft(self):
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以撤销控制科目映射核验。"))
        for mapping in self:
            if mapping.state != "verified":
                raise UserError(_("只有已核验的控制科目映射可以撤销核验。"))
            previous_checksum = mapping.verification_checksum
            mapping.with_context(
                cn_vat_mapping_transition=_MAPPING_TRANSITION_MARKER
            ).write(
                {
                    "state": "draft",
                    "verified_at": False,
                    "verified_by_id": False,
                    "verification_checksum": False,
                }
            )
            self.env["sudo.compliance.audit.event"]._log_records(
                mapping,
                "cn_vat_account_mapping.verification_reset",
                previous_state="verified",
                new_state="draft",
                details={"previous_checksum": previous_checksum},
            )
        return True


class SudoChinaVatFilingAdjustment(models.Model):
    _name = "sudo.cn.vat.filing.adjustment"
    _description = "China VAT Filing Reconciliation Adjustment"
    _order = "period_end desc, profile_id, tax_side, id desc"
    _check_company_auto = True

    name = fields.Char(compute="_compute_name", store=True)
    profile_id = fields.Many2one(
        "sudo.compliance.profile",
        string="合规档案",
        required=True,
        ondelete="cascade",
        index=True,
        check_company=True,
    )
    company_id = fields.Many2one(
        related="profile_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    country_id = fields.Many2one(
        related="profile_id.country_id",
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id",
        string="币种",
        store=True,
        readonly=True,
    )
    period_start = fields.Date(string="期间开始", required=True, index=True)
    period_end = fields.Date(string="期间结束", required=True, index=True)
    tax_side = fields.Selection(
        [("output", "销项税额"), ("input", "进项税额")],
        string="调节口径",
        required=True,
        index=True,
    )
    effect = fields.Selection(
        [("increase", "增加申报口径"), ("decrease", "减少申报口径")],
        string="调节方向",
        required=True,
    )
    adjustment_type = fields.Selection(
        [
            ("recognition_timing", "确认或认证时点差异"),
            ("unbilled_revenue", "未开票收入"),
            ("deemed_taxable", "视同应税事项"),
            ("input_transfer_out", "进项税额转出"),
            ("red_letter", "红字或冲销调整"),
            ("tax_policy", "税收政策调整"),
            ("other", "其他受控调整"),
        ],
        string="调整类型",
        required=True,
    )
    amount = fields.Monetary(
        string="调整金额",
        currency_field="currency_id",
        required=True,
    )
    signed_amount = fields.Monetary(
        string="申报口径影响额",
        currency_field="currency_id",
        compute="_compute_signed_amount",
        store=True,
    )
    description = fields.Text(string="调整原因与计算过程", required=True)
    source_reference = fields.Char(string="工作底稿引用", required=True)
    evidence_attachment_ids = fields.Many2many(
        "ir.attachment",
        "sudo_cn_vat_filing_adjustment_attachment_rel",
        "adjustment_id",
        "attachment_id",
        string="调整证据",
    )
    prepared_by_id = fields.Many2one(
        "res.users",
        string="编制人",
        required=True,
        readonly=True,
    )
    separation_exception_reason = fields.Text(
        string="同人审批例外理由",
        help="编制人与审批人为同一人时，记录受控例外原因。",
    )
    state = fields.Selection(
        [
            ("draft", "待审批"),
            ("approved", "已批准"),
            ("cancelled", "已取消"),
        ],
        string="状态",
        required=True,
        default="draft",
        readonly=True,
        index=True,
    )
    approved_at = fields.Datetime(string="批准时间", readonly=True, copy=False)
    approved_by_id = fields.Many2one(
        "res.users",
        string="批准人",
        readonly=True,
        copy=False,
    )
    approval_checksum = fields.Char(
        string="批准 SHA-256",
        readonly=True,
        copy=False,
    )
    integrity_state = fields.Selection(
        [
            ("unapproved", "未批准"),
            ("verified", "完整性正常"),
            ("checksum_mismatch", "资料已变化"),
        ],
        string="审批完整性",
        compute="_compute_integrity_state",
    )

    _controlled_fields = {
        "profile_id",
        "period_start",
        "period_end",
        "tax_side",
        "effect",
        "adjustment_type",
        "amount",
        "description",
        "source_reference",
        "evidence_attachment_ids",
        "separation_exception_reason",
    }
    _protected_fields = {
        "prepared_by_id",
        "state",
        "approved_at",
        "approved_by_id",
        "approval_checksum",
    }
    _normalized_text_fields = {
        "description",
        "source_reference",
        "separation_exception_reason",
    }

    @api.depends("profile_id", "period_start", "period_end", "tax_side")
    def _compute_name(self):
        side_labels = dict(self._fields["tax_side"].selection)
        for adjustment in self:
            adjustment.name = "%s / %s - %s / %s" % (
                adjustment.profile_id.display_name or _("增值税申报调整"),
                fields.Date.to_string(adjustment.period_start) or "-",
                fields.Date.to_string(adjustment.period_end) or "-",
                side_labels.get(adjustment.tax_side, adjustment.tax_side or "-"),
            )

    @api.depends("amount", "effect")
    def _compute_signed_amount(self):
        for adjustment in self:
            amount = abs(float(adjustment.amount or 0.0))
            adjustment.signed_amount = (
                amount if adjustment.effect == "increase" else -amount
            )

    def _checksum_payload(self):
        self.ensure_one()
        return {
            "profile_id": self.profile_id.id,
            "company_id": self.company_id.id,
            "period_start": fields.Date.to_string(self.period_start),
            "period_end": fields.Date.to_string(self.period_end),
            "tax_side": self.tax_side,
            "effect": self.effect,
            "adjustment_type": self.adjustment_type,
            "amount": format(
                self.currency_id.round(float(self.amount or 0.0)),
                "f",
            ),
            "description": self.description or None,
            "source_reference": self.source_reference or None,
            "prepared_by_id": self.prepared_by_id.id,
            "separation_exception_reason": (
                self.separation_exception_reason or None
            ),
            "attachments": _attachment_manifest(self.evidence_attachment_ids),
        }

    def _current_checksum(self):
        self.ensure_one()
        return _payload_checksum(self._checksum_payload())

    def _current_integrity_state(self):
        self.ensure_one()
        if self.state not in ("approved", "cancelled") or not self.approval_checksum:
            return "unapproved"
        if self.approval_checksum == self._current_checksum():
            return "verified"
        return "checksum_mismatch"

    @api.depends(
        "state",
        "approval_checksum",
        "period_start",
        "period_end",
        "tax_side",
        "effect",
        "adjustment_type",
        "amount",
        "description",
        "source_reference",
        "prepared_by_id",
        "separation_exception_reason",
        "evidence_attachment_ids",
    )
    def _compute_integrity_state(self):
        for adjustment in self:
            adjustment.integrity_state = adjustment._current_integrity_state()

    @api.model
    def _for_profile_period(self, profile, period_start, period_end):
        return self.search(
            [
                ("profile_id", "=", profile.id),
                ("period_start", "=", period_start),
                ("period_end", "=", period_end),
                ("state", "=", "approved"),
            ],
            order="tax_side, id",
        )

    def _approval_issues(self):
        self.ensure_one()
        issues = []
        if self.country_id.code != "CN":
            issues.append(_("不是中国合规档案"))
        if not self.description or len(self.description) < 20:
            issues.append(_("调整原因与计算过程必须不少于 20 字"))
        if not self.source_reference:
            issues.append(_("未填写工作底稿引用"))
        if not self.evidence_attachment_ids:
            issues.append(_("未上传调整证据"))
        elif _invalid_binary_attachments(self.evidence_attachment_ids):
            issues.append(_("调整证据必须是系统内非空二进制附件"))
        if self.prepared_by_id == self.env.user:
            reason = self.separation_exception_reason or ""
            if len(reason) < 20:
                issues.append(_("编制人与审批人为同一人时，必须填写不少于 20 字的例外理由"))
        return issues

    @api.model
    def _normalize_text_values(self, values):
        for field_name in self._normalized_text_fields & set(values):
            value = values[field_name]
            if isinstance(value, str):
                values[field_name] = value.strip() or False

    @api.constrains("profile_id")
    def _check_china_profile(self):
        for adjustment in self:
            if adjustment.country_id.code != "CN":
                raise ValidationError(_("增值税申报调整只能关联中国合规档案。"))

    @api.constrains("period_start", "period_end")
    def _check_period(self):
        for adjustment in self:
            if adjustment.period_end < adjustment.period_start:
                raise ValidationError(_("期间结束日不能早于开始日。"))

    @api.constrains("amount")
    def _check_amount(self):
        for adjustment in self:
            if adjustment.amount <= 0:
                raise ValidationError(_("调整金额必须大于零。"))

    @api.constrains("tax_side", "effect", "adjustment_type")
    def _check_adjustment_semantics(self):
        for adjustment in self:
            if adjustment.adjustment_type in (
                "unbilled_revenue",
                "deemed_taxable",
            ) and adjustment.tax_side != "output":
                raise ValidationError(_("未开票收入和视同应税事项只能调整销项税额。"))
            if adjustment.adjustment_type == "input_transfer_out" and (
                adjustment.tax_side != "input"
                or adjustment.effect != "decrease"
            ):
                raise ValidationError(_("进项税额转出只能减少进项税额申报口径。"))

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            self._normalize_text_values(values)
            values.update(
                {
                    "prepared_by_id": self.env.user.id,
                    "state": "draft",
                    "approved_at": False,
                    "approved_by_id": False,
                    "approval_checksum": False,
                }
            )
        records = super().create(vals_list)
        self.env["sudo.compliance.audit.event"]._log_records(
            records,
            "cn_vat_filing_adjustment.created",
            new_state="draft",
        )
        return records

    def write(self, values):
        self._normalize_text_values(values)
        transition = (
            self.env.context.get("cn_vat_adjustment_transition")
            is _ADJUSTMENT_TRANSITION_MARKER
        )
        changed_fields = sorted(set(values) & self._controlled_fields)
        if set(values) & self._protected_fields and not transition:
            raise AccessError(_("请使用申报调整上的受控操作更新状态。"))
        locked = self.filtered(lambda record: record.state != "draft")
        if changed_fields and locked and not transition:
            raise AccessError(_("已批准或已取消的申报调整不可修改。"))
        result = super().write(values)
        if changed_fields and not transition:
            for record in self:
                self.env["sudo.compliance.audit.event"]._log_records(
                    record,
                    "cn_vat_filing_adjustment.changed",
                    previous_state="draft",
                    new_state="draft",
                    details={"changed_fields": changed_fields},
                )
        return result

    def unlink(self):
        if self.filtered(lambda record: record.state != "draft"):
            raise UserError(_("已批准或已取消的申报调整不可删除。"))
        return super().unlink()

    def copy(self, default=None):
        values = dict(default or {})
        values.update(
            {
                "prepared_by_id": self.env.user.id,
                "state": "draft",
                "approved_at": False,
                "approved_by_id": False,
                "approval_checksum": False,
                "separation_exception_reason": False,
            }
        )
        return super().copy(values)

    def action_approve(self):
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以批准增值税申报调整。"))
        for adjustment in self:
            if adjustment.state != "draft":
                raise UserError(_("只有待审批的申报调整可以批准。"))
            issues = adjustment._approval_issues()
            if issues:
                raise UserError(
                    _(
                        "申报调整尚不能批准：\n- %(issues)s",
                        issues="\n- ".join(issues),
                    )
                )
            payload = adjustment._checksum_payload()
            checksum = _payload_checksum(payload)
            adjustment.with_context(
                cn_vat_adjustment_transition=_ADJUSTMENT_TRANSITION_MARKER
            ).write(
                {
                    "state": "approved",
                    "approved_at": fields.Datetime.now(),
                    "approved_by_id": self.env.user.id,
                    "approval_checksum": checksum,
                }
            )
            self.env["sudo.compliance.audit.event"]._log_records(
                adjustment,
                "cn_vat_filing_adjustment.approved",
                previous_state="draft",
                new_state="approved",
                details={
                    "checksum": checksum,
                    "tax_side": adjustment.tax_side,
                    "effect": adjustment.effect,
                    "amount": float(adjustment.amount),
                    "period_start": fields.Date.to_string(
                        adjustment.period_start
                    ),
                    "period_end": fields.Date.to_string(adjustment.period_end),
                    "independent_review": (
                        adjustment.prepared_by_id != self.env.user
                    ),
                },
            )
        return True

    def action_cancel(self):
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以取消增值税申报调整。"))
        for adjustment in self:
            if adjustment.state != "approved":
                raise UserError(_("只有已批准的申报调整可以取消。"))
            adjustment.with_context(
                cn_vat_adjustment_transition=_ADJUSTMENT_TRANSITION_MARKER
            ).write({"state": "cancelled"})
            self.env["sudo.compliance.audit.event"]._log_records(
                adjustment,
                "cn_vat_filing_adjustment.cancelled",
                previous_state="approved",
                new_state="cancelled",
                details={"approval_checksum": adjustment.approval_checksum},
            )
        return True
