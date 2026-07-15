import hashlib
import json

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


_CLASSIFICATION_TRANSITION_MARKER = object()


class SudoChinaTaxpayerClassification(models.Model):
    _name = "sudo.cn.taxpayer.classification"
    _description = "China Taxpayer Classification Snapshot"
    _order = "profile_id, valid_from desc, id desc"
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
        index=True,
        readonly=True,
    )
    country_id = fields.Many2one(
        related="profile_id.country_id",
        store=True,
        index=True,
        readonly=True,
    )
    valid_from = fields.Date(
        string="有效开始日",
        required=True,
        default=fields.Date.context_today,
        index=True,
    )
    valid_to = fields.Date(string="有效结束日", index=True)
    province_id = fields.Many2one(
        "res.country.state",
        string="主管税务省级辖区",
        domain="[('country_id', '=', country_id)]",
    )
    local_jurisdiction_name = fields.Char(
        string="地方税务辖区",
        help="记录受控资料中的市、区县或税务适用辖区名称，不根据地址自动猜测。",
    )
    local_jurisdiction_code = fields.Char(
        string="地方税务辖区编码",
        help="记录受控行政区划或税务辖区编码，供后续地方规则选择使用。",
    )
    tax_authority_name = fields.Char(string="主管税务机关")
    tax_authority_code = fields.Char(string="主管税务机关代码")
    vat_taxpayer_status = fields.Selection(
        [
            ("unknown", "待确认"),
            ("general", "增值税一般纳税人"),
            ("small_scale", "增值税小规模纳税人"),
            ("other", "其他受控分类"),
        ],
        string="增值税纳税人身份",
        required=True,
        default="unknown",
    )
    vat_filing_frequency = fields.Selection(
        [
            ("unknown", "待确认"),
            ("monthly", "按月"),
            ("quarterly", "按季"),
            ("not_applicable", "不适用"),
            ("other", "其他"),
        ],
        string="增值税申报频率",
        required=True,
        default="unknown",
    )
    cit_taxpayer_status = fields.Selection(
        [
            ("unknown", "待确认"),
            ("resident", "居民企业"),
            ("nonresident_establishment", "非居民企业（设有机构场所）"),
            ("nonresident_no_establishment", "非居民企业（未设机构场所）"),
            ("not_applicable", "不适用"),
            ("other", "其他受控分类"),
        ],
        string="企业所得税身份",
        required=True,
        default="unknown",
    )
    cit_collection_method = fields.Selection(
        [
            ("unknown", "待确认"),
            ("accounts_based", "查账征收"),
            ("deemed", "核定征收"),
            ("withholding", "源泉扣缴"),
            ("not_applicable", "不适用"),
            ("other", "其他受控方式"),
        ],
        string="企业所得税征收方式",
        required=True,
        default="unknown",
    )
    pit_withholding_status = fields.Selection(
        [
            ("unknown", "待确认"),
            ("yes", "承担扣缴义务"),
            ("no", "当前不承担扣缴义务"),
        ],
        string="个人所得税扣缴身份",
        required=True,
        default="unknown",
    )
    accounting_regime = fields.Selection(
        [
            ("unknown", "待确认"),
            ("asbe", "企业会计准则"),
            ("small_asbe", "小企业会计准则"),
            ("business_accounting_system", "企业会计制度"),
            ("private_nonprofit", "民间非营利组织会计制度"),
            ("other", "其他受控制度"),
        ],
        string="适用会计制度",
        required=True,
        default="unknown",
    )
    source_type = fields.Selection(
        [
            ("electronic_tax_bureau", "电子税务局受控导出"),
            ("tax_registration_document", "税务登记或认定文书"),
            ("tax_authority_confirmation", "税务机关确认材料"),
            ("professional_workpaper", "专业复核工作底稿"),
            ("other", "其他受控来源"),
        ],
        string="身份来源类型",
    )
    source_date = fields.Date(string="来源资料日期")
    source_reference = fields.Char(string="来源引用")
    scope_note = fields.Text(
        string="核验范围与限制",
        help="说明本快照覆盖的税种、期间、资料边界和仍未消除的不确定性。",
    )
    evidence_attachment_ids = fields.Many2many(
        "ir.attachment",
        "sudo_cn_taxpayer_classification_attachment_rel",
        "classification_id",
        "attachment_id",
        string="身份依据附件",
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
        string="核验校验和",
        readonly=True,
        copy=False,
    )
    integrity_state = fields.Selection(
        [
            ("unverified", "未核验"),
            ("verified", "完整性正常"),
            ("checksum_mismatch", "资料已变化"),
        ],
        string="证据完整性",
        compute="_compute_integrity_state",
    )

    _controlled_fields = {
        "profile_id",
        "valid_from",
        "valid_to",
        "province_id",
        "local_jurisdiction_name",
        "local_jurisdiction_code",
        "tax_authority_name",
        "tax_authority_code",
        "vat_taxpayer_status",
        "vat_filing_frequency",
        "cit_taxpayer_status",
        "cit_collection_method",
        "pit_withholding_status",
        "accounting_regime",
        "source_type",
        "source_date",
        "source_reference",
        "scope_note",
        "evidence_attachment_ids",
    }
    _protected_fields = {
        "state",
        "verified_at",
        "verified_by_id",
        "verification_checksum",
    }
    _normalized_text_fields = {
        "local_jurisdiction_name",
        "local_jurisdiction_code",
        "tax_authority_name",
        "tax_authority_code",
        "source_reference",
        "scope_note",
    }
    _required_classification_fields = {
        "vat_taxpayer_status": "增值税纳税人身份",
        "vat_filing_frequency": "增值税申报频率",
        "cit_taxpayer_status": "企业所得税身份",
        "cit_collection_method": "企业所得税征收方式",
        "pit_withholding_status": "个人所得税扣缴身份",
        "accounting_regime": "适用会计制度",
    }

    @api.depends("profile_id", "valid_from", "state")
    def _compute_name(self):
        for classification in self:
            date_label = fields.Date.to_string(classification.valid_from) or "-"
            classification.name = "%s / %s" % (
                classification.profile_id.display_name or _("中国纳税人身份"),
                date_label,
            )

    def _attachment_payload(self):
        self.ensure_one()
        payload = []
        for attachment in self.evidence_attachment_ids.sudo().sorted("id"):
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
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
            )
        return payload

    def _checksum_payload(self):
        self.ensure_one()
        return {
            "profile_id": self.profile_id.id,
            "company_id": self.company_id.id,
            "valid_from": fields.Date.to_string(self.valid_from),
            "valid_to": fields.Date.to_string(self.valid_to),
            "province_id": self.province_id.id,
            "local_jurisdiction_name": self.local_jurisdiction_name or None,
            "local_jurisdiction_code": self.local_jurisdiction_code or None,
            "tax_authority_name": self.tax_authority_name or None,
            "tax_authority_code": self.tax_authority_code or None,
            "vat_taxpayer_status": self.vat_taxpayer_status,
            "vat_filing_frequency": self.vat_filing_frequency,
            "cit_taxpayer_status": self.cit_taxpayer_status,
            "cit_collection_method": self.cit_collection_method,
            "pit_withholding_status": self.pit_withholding_status,
            "accounting_regime": self.accounting_regime,
            "source_type": self.source_type,
            "source_date": fields.Date.to_string(self.source_date),
            "source_reference": self.source_reference or None,
            "scope_note": self.scope_note or None,
            "attachments": self._attachment_payload(),
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
        if self.state != "verified" or not self.verification_checksum:
            return "unverified"
        if self.verification_checksum == self._current_checksum():
            return "verified"
        return "checksum_mismatch"

    @api.depends(
        "state",
        "verification_checksum",
        "evidence_attachment_ids",
        "valid_from",
        "valid_to",
        "province_id",
        "local_jurisdiction_name",
        "local_jurisdiction_code",
        "tax_authority_name",
        "tax_authority_code",
        "vat_taxpayer_status",
        "vat_filing_frequency",
        "cit_taxpayer_status",
        "cit_collection_method",
        "pit_withholding_status",
        "accounting_regime",
        "source_type",
        "source_date",
        "source_reference",
        "scope_note",
    )
    def _compute_integrity_state(self):
        for classification in self:
            classification.integrity_state = (
                classification._current_integrity_state()
            )

    @api.model
    def _for_profile_date(self, profile, target_date):
        return self.search(
            [
                ("profile_id", "=", profile.id),
                ("valid_from", "<=", target_date),
                "|",
                ("valid_to", "=", False),
                ("valid_to", ">=", target_date),
            ],
            order="valid_from desc, id desc",
        )

    def _overlapping_verified(self):
        self.ensure_one()
        domain = [
            ("profile_id", "=", self.profile_id.id),
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
        for field_name, label in self._required_classification_fields.items():
            if self[field_name] == "unknown":
                issues.append(_("%(label)s待确认", label=label))
        if not self.province_id:
            issues.append(_("未选择主管税务省级辖区"))
        if not self.local_jurisdiction_name:
            issues.append(_("未填写地方税务辖区"))
        if not self.local_jurisdiction_code:
            issues.append(_("未填写地方税务辖区编码"))
        if not self.tax_authority_name:
            issues.append(_("未填写主管税务机关"))
        if not self.source_type:
            issues.append(_("未选择身份来源类型"))
        if not self.source_date:
            issues.append(_("未填写来源资料日期"))
        elif self.source_date > fields.Date.context_today(self):
            issues.append(_("来源资料日期不能晚于当前日期"))
        if not self.source_reference:
            issues.append(_("未填写来源引用"))
        if not self.scope_note:
            issues.append(_("未记录核验范围与限制"))
        if not self.evidence_attachment_ids:
            issues.append(_("未上传身份依据附件"))
        else:
            invalid_evidence = self.evidence_attachment_ids.sudo().filtered(
                lambda attachment: (
                    attachment.type != "binary" or not attachment.raw
                )
            )
            if invalid_evidence:
                issues.append(_("身份依据必须是系统内保存的非空二进制附件"))
        return issues

    @api.model
    def _normalize_text_values(self, values):
        for field_name in self._normalized_text_fields & set(values):
            value = values[field_name]
            if isinstance(value, str):
                values[field_name] = value.strip() or False

    @api.constrains("profile_id")
    def _check_china_profile(self):
        for classification in self:
            if classification.country_id.code != "CN":
                raise ValidationError(_("中国纳税人身份只能关联中国合规档案。"))

    @api.constrains("valid_from", "valid_to")
    def _check_validity_dates(self):
        for classification in self:
            if (
                classification.valid_to
                and classification.valid_to < classification.valid_from
            ):
                raise ValidationError(_("有效结束日不能早于开始日。"))

    @api.constrains("profile_id", "valid_from", "valid_to", "state")
    def _check_verified_overlap(self):
        for classification in self.filtered(
            lambda item: item.state == "verified"
        ):
            if classification._overlapping_verified():
                raise ValidationError(
                    _("同一期间只能有一份已核验的中国纳税人身份快照。")
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
            "cn_taxpayer_classification.created",
            new_state="draft",
        )
        return records

    def write(self, values):
        self._normalize_text_values(values)
        transition = (
            self.env.context.get("cn_classification_transition")
            is _CLASSIFICATION_TRANSITION_MARKER
        )
        changed_fields = sorted(set(values) & self._controlled_fields)
        if set(values) & self._protected_fields and not transition:
            raise AccessError(_("请使用身份快照上的核验操作更新状态。"))
        verified = self.filtered(lambda item: item.state == "verified")
        if changed_fields and verified and not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以修改已核验的身份快照。"))
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
                    "cn_taxpayer_classification.changed",
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
        if self.filtered(lambda item: item.state == "verified"):
            raise UserError(_("已核验的身份快照不可删除。"))
        return super().unlink()

    def copy(self, default=None):
        values = dict(default or {})
        values.update(
            {
                "state": "draft",
                "verified_at": False,
                "verified_by_id": False,
                "verification_checksum": False,
            }
        )
        return super().copy(values)

    def action_verify(self):
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以核验中国纳税人身份。"))
        for classification in self:
            if classification.state != "draft":
                raise UserError(_("只有待核验的身份快照可以执行核验。"))
            issues = classification._verification_issues()
            if issues:
                raise UserError(
                    _(
                        "身份快照尚不能核验：\n- %(issues)s",
                        issues="\n- ".join(issues),
                    )
                )
            if classification._overlapping_verified():
                raise UserError(
                    _("同一期间已有另一份已核验的中国纳税人身份快照。")
                )
            verification_payload = classification._checksum_payload()
            checksum = classification._current_checksum(
                verification_payload
            )
            classification.with_context(
                cn_classification_transition=_CLASSIFICATION_TRANSITION_MARKER
            ).write(
                {
                    "state": "verified",
                    "verified_at": fields.Datetime.now(),
                    "verified_by_id": self.env.user.id,
                    "verification_checksum": checksum,
                }
            )
            self.env["sudo.compliance.audit.event"]._log_records(
                classification,
                "cn_taxpayer_classification.verified",
                previous_state="draft",
                new_state="verified",
                details={
                    "checksum": checksum,
                    "verification_payload": verification_payload,
                    "evidence_count": len(
                        classification.evidence_attachment_ids
                    ),
                    "source_type": classification.source_type,
                    "valid_from": fields.Date.to_string(
                        classification.valid_from
                    ),
                    "valid_to": fields.Date.to_string(
                        classification.valid_to
                    ),
                },
            )
        return True

    def action_reset_to_draft(self):
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以撤销身份核验。"))
        for classification in self:
            if classification.state != "verified":
                raise UserError(_("只有已核验的身份快照可以撤销核验。"))
            previous_checksum = classification.verification_checksum
            classification.with_context(
                cn_classification_transition=_CLASSIFICATION_TRANSITION_MARKER
            ).write(
                {
                    "state": "draft",
                    "verified_at": False,
                    "verified_by_id": False,
                    "verification_checksum": False,
                }
            )
            self.env["sudo.compliance.audit.event"]._log_records(
                classification,
                "cn_taxpayer_classification.verification_reset",
                previous_state="verified",
                new_state="draft",
                details={"previous_checksum": previous_checksum},
            )
        return True
