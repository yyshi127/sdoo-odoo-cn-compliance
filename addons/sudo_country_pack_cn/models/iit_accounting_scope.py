import hashlib
import json

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


_IIT_SCOPE_TRANSITION_MARKER = object()
_IIT_ACCOUNTING_CHECKSUM_LANG = "en_US"
_EXPENSE_ACCOUNT_TYPES = {
    "expense",
    "expense_depreciation",
    "expense_direct_cost",
}
_LIABILITY_ACCOUNT_TYPES = {"liability_current", "liability_payable"}
_ROLE_ACCOUNT_TYPES = {
    "payroll_expense": _EXPENSE_ACCOUNT_TYPES,
    "employee_payable": _LIABILITY_ACCOUNT_TYPES,
    "iit_payable": _LIABILITY_ACCOUNT_TYPES,
}
_REQUIRED_ROLES = frozenset(_ROLE_ACCOUNT_TYPES)


def _checksum(payload):
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


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


class SudoChinaIitAccountingScope(models.Model):
    _name = "sudo.cn.iit.accounting.scope"
    _description = "China IIT Withholding Accounting Scope"
    _order = "profile_id, valid_from desc, id desc"
    _check_company_auto = True

    name = fields.Char(compute="_compute_name", store=True)
    profile_id = fields.Many2one(
        "sudo.compliance.profile",
        string="合规档案",
        required=True,
        ondelete="restrict",
        check_company=True,
        index=True,
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
    valid_from = fields.Date(
        string="有效开始日",
        required=True,
        default=fields.Date.context_today,
        index=True,
    )
    valid_to = fields.Date(string="有效结束日", index=True)
    source_reference = fields.Char(string="账务口径依据引用")
    iit_source_schema = fields.Char(
        string="个税申报来源结构",
        help="必须与受控个税申报导入运行的 source_schema 完全一致。",
    )
    iit_source_schema_version = fields.Char(
        string="个税申报来源结构版本",
        help="必须与受控个税申报导入运行的 source_schema_version 完全一致。",
    )
    payroll_source_schema = fields.Char(
        string="工资汇总来源结构",
        help="必须与受控工资汇总导入运行的 source_schema 完全一致。",
    )
    payroll_source_schema_version = fields.Char(
        string="工资汇总来源结构版本",
        help="必须与受控工资汇总导入运行的 source_schema_version 完全一致。",
    )
    payable_refundable_sign_convention = fields.Selection(
        [
            (
                "positive_payable_negative_refundable",
                "正数应补、负数应退",
            ),
            (
                "negative_payable_positive_refundable",
                "负数应补、正数应退",
            ),
        ],
        string="应补退税额符号约定",
        help="只解释指定来源结构的符号，不计算税款或判断退税资格。",
    )
    scope_note = fields.Text(
        string="取数口径、排除与限制",
        help=(
            "说明工资成本、应付职工薪酬、应交个人所得税科目的覆盖范围，"
            "计提与结算时点、冲销重分类、非工资项目和其他限制。"
        ),
    )
    evidence_attachment_ids = fields.Many2many(
        "ir.attachment",
        "sudo_cn_iit_accounting_scope_attachment_rel",
        "scope_id",
        "attachment_id",
        string="账务口径工作底稿",
    )
    separation_exception_reason = fields.Text(
        string="同人复核例外理由",
        help="编制人与核验人为同一人时，记录受控例外原因。",
    )
    line_ids = fields.One2many(
        "sudo.cn.iit.accounting.scope.line",
        "scope_id",
        string="取数科目",
        copy=False,
    )
    line_count = fields.Integer(string="科目数", compute="_compute_line_count")
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
        "res.users", string="核验人", readonly=True, copy=False
    )
    verification_checksum = fields.Char(
        string="核验 SHA-256", readonly=True, copy=False
    )
    integrity_state = fields.Selection(
        [
            ("unverified", "未核验"),
            ("verified", "完整性正常"),
            ("checksum_mismatch", "口径或科目已变化"),
        ],
        string="口径完整性",
        compute="_compute_integrity_state",
    )

    _controlled_fields = {
        "profile_id",
        "valid_from",
        "valid_to",
        "source_reference",
        "iit_source_schema",
        "iit_source_schema_version",
        "payroll_source_schema",
        "payroll_source_schema_version",
        "payable_refundable_sign_convention",
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
        "iit_source_schema",
        "iit_source_schema_version",
        "payroll_source_schema",
        "payroll_source_schema_version",
        "scope_note",
        "separation_exception_reason",
    }

    @api.depends("profile_id", "valid_from", "valid_to")
    def _compute_name(self):
        for scope in self:
            scope.name = "%s / %s - %s" % (
                scope.profile_id.display_name or _("个人所得税账务口径"),
                fields.Date.to_string(scope.valid_from) or "-",
                fields.Date.to_string(scope.valid_to) or _("持续有效"),
            )

    @api.depends("line_ids")
    def _compute_line_count(self):
        for scope in self:
            scope.line_count = len(scope.line_ids)

    def _checksum_payload(self):
        self.ensure_one()
        lines = []
        for line in self.line_ids.sorted(
            key=lambda item: (item.role, item.account_id.code or "", item.id)
        ):
            account = line.account_id.with_company(self.company_id)
            lines.append(
                {
                    "line_id": line.id,
                    "account_id": account.id,
                    "account_code": account.code or None,
                    "account_name": account.name or None,
                    "account_type": account.account_type or None,
                    "role": line.role,
                    "exception_reason": line.exception_reason or None,
                }
            )
        return {
            "schema": "sdoo.cn.iit-accounting-scope.v1",
            "profile_id": self.profile_id.id,
            "company_id": self.company_id.id,
            "valid_from": fields.Date.to_string(self.valid_from),
            "valid_to": fields.Date.to_string(self.valid_to),
            "source_reference": self.source_reference or None,
            "iit_source_schema": self.iit_source_schema or None,
            "iit_source_schema_version": self.iit_source_schema_version or None,
            "payroll_source_schema": self.payroll_source_schema or None,
            "payroll_source_schema_version": (
                self.payroll_source_schema_version or None
            ),
            "payable_refundable_sign_convention": (
                self.payable_refundable_sign_convention or None
            ),
            "scope_note": self.scope_note or None,
            "separation_exception_reason": (
                self.separation_exception_reason or None
            ),
            "lines": lines,
            "attachments": _attachment_manifest(self.evidence_attachment_ids),
        }

    def _current_checksum(self):
        self.ensure_one()
        return self._checksum_for_language(_IIT_ACCOUNTING_CHECKSUM_LANG)

    def _checksum_for_language(self, lang):
        self.ensure_one()
        return _checksum(self.with_context(lang=lang)._checksum_payload())

    def _current_integrity_state(self):
        self.ensure_one()
        if self.state != "verified" or not self.verification_checksum:
            return "unverified"
        return (
            "verified"
            if self.verification_checksum == self._current_checksum()
            else "checksum_mismatch"
        )

    @api.depends(
        "state",
        "verification_checksum",
        "valid_from",
        "valid_to",
        "source_reference",
        "iit_source_schema",
        "iit_source_schema_version",
        "payroll_source_schema",
        "payroll_source_schema_version",
        "payable_refundable_sign_convention",
        "scope_note",
        "separation_exception_reason",
        "evidence_attachment_ids",
        "line_ids.account_id",
        "line_ids.account_id.code",
        "line_ids.account_id.name",
        "line_ids.account_id.account_type",
        "line_ids.role",
        "line_ids.exception_reason",
    )
    def _compute_integrity_state(self):
        for scope in self:
            scope.integrity_state = scope._current_integrity_state()

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
        if self.country_id.code != "CN":
            issues.append(_("不是中国合规档案"))
        if self.valid_to and self.valid_to < self.valid_from:
            issues.append(_("有效结束日早于开始日"))
        if not self.source_reference:
            issues.append(_("未填写账务口径依据引用"))
        if not self.iit_source_schema or not self.iit_source_schema_version:
            issues.append(_("未锁定个税申报来源结构及版本"))
        if not self.payroll_source_schema or not self.payroll_source_schema_version:
            issues.append(_("未锁定工资汇总来源结构及版本"))
        if not self.payable_refundable_sign_convention:
            issues.append(_("未确认来源应补退税额符号约定"))
        if not self.scope_note:
            issues.append(_("未记录取数口径、排除与限制"))
        if not self.evidence_attachment_ids:
            issues.append(_("未上传账务口径工作底稿"))
        elif self.evidence_attachment_ids.sudo().filtered(
            lambda attachment: attachment.type != "binary" or not attachment.raw
        ):
            issues.append(_("账务口径工作底稿必须是系统内非空二进制附件"))

        roles = set(self.line_ids.mapped("role"))
        for role in sorted(_REQUIRED_ROLES - roles):
            labels = dict(self.env["sudo.cn.iit.accounting.scope.line"]._fields["role"].selection)
            issues.append(_("缺少%(role)s科目", role=labels[role]))

        for line in self.line_ids:
            account = line.account_id.with_company(self.company_id)
            if self.company_id not in account.company_ids:
                issues.append(_("科目 %(code)s 不属于档案公司", code=account.code))
                continue
            expected_types = _ROLE_ACCOUNT_TYPES[line.role]
            if (
                account.account_type not in expected_types
                and len(line.exception_reason or "") < 20
            ):
                issues.append(
                    _(
                        "科目 %(code)s 的类型与角色不一致时，必须填写不少于 20 字的例外理由",
                        code=account.code or account.display_name,
                    )
                )

        if self.create_uid == self.env.user and len(
            self.separation_exception_reason or ""
        ) < 20:
            issues.append(_("编制人与核验人为同一人时，必须填写不少于 20 字的例外理由"))
        if self._overlapping_verified():
            issues.append(_("当前有效期与另一份已核验个税账务口径重叠"))
        return issues

    @api.model
    def _normalize_text_values(self, values):
        for field_name in self._normalized_text_fields & set(values):
            value = values[field_name]
            if isinstance(value, str):
                values[field_name] = value.strip() or False

    @api.constrains("profile_id")
    def _check_china_profile(self):
        for scope in self:
            if scope.country_id.code != "CN":
                raise ValidationError(_("个人所得税账务口径只能关联中国合规档案。"))

    @api.constrains("valid_from", "valid_to")
    def _check_validity_dates(self):
        for scope in self:
            if scope.valid_to and scope.valid_to < scope.valid_from:
                raise ValidationError(_("有效结束日不能早于开始日。"))

    @api.constrains("profile_id", "valid_from", "valid_to", "state")
    def _check_verified_overlap(self):
        for scope in self.filtered(lambda record: record.state == "verified"):
            if scope._overlapping_verified():
                raise ValidationError(_("同一档案同一期间只能有一份已核验个税账务口径。"))

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
        scopes = super().create(vals_list)
        self.env["sudo.compliance.audit.event"]._log_records(
            scopes, "cn_iit_accounting_scope.created", new_state="draft"
        )
        return scopes

    def write(self, values):
        self._normalize_text_values(values)
        transition = (
            self.env.context.get("cn_iit_scope_transition")
            is _IIT_SCOPE_TRANSITION_MARKER
        )
        if set(values) & self._protected_fields and not transition:
            raise AccessError(_("请使用个税账务口径上的核验操作更新状态。"))
        if set(values) & self._controlled_fields and self.filtered(
            lambda record: record.state == "verified"
        ):
            raise AccessError(_("已核验个税账务口径不可修改，请先撤销核验。"))
        return super().write(values)

    def unlink(self):
        if self.filtered(lambda record: record.state == "verified"):
            raise UserError(_("已核验个税账务口径不可删除。"))
        used = self.env["sudo.cn.iit.period.reconciliation.run"].sudo().search_count(
            [("accounting_scope_id", "in", self.ids)]
        )
        if used:
            raise UserError(_("已进入个税勾稽快照的账务口径不可删除。"))
        return super().unlink()

    def copy(self, default=None):
        self.ensure_one()
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
        duplicate = super().copy(values)
        for line in self.line_ids:
            line.copy({"scope_id": duplicate.id})
        return duplicate

    def action_verify(self):
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以核验个人所得税账务口径。"))
        for scope in self:
            if scope.state != "draft":
                raise UserError(_("只有待核验个税账务口径可以执行核验。"))
            issues = scope._verification_issues()
            if issues:
                raise UserError(
                    _(
                        "个税账务口径尚不能核验：\n- %(issues)s",
                        issues="\n- ".join(issues),
                    )
                )
            checksum = scope._current_checksum()
            scope.with_context(
                cn_iit_scope_transition=_IIT_SCOPE_TRANSITION_MARKER
            ).write(
                {
                    "state": "verified",
                    "verified_at": fields.Datetime.now(),
                    "verified_by_id": self.env.user.id,
                    "verification_checksum": checksum,
                }
            )
            self.env["sudo.compliance.audit.event"]._log_records(
                scope,
                "cn_iit_accounting_scope.verified",
                previous_state="draft",
                new_state="verified",
                details={
                    "checksum": checksum,
                    "line_count": len(scope.line_ids),
                    "independent_review": scope.create_uid != self.env.user,
                },
            )
        return True

    def action_reset_to_draft(self):
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以撤销个税账务口径核验。"))
        for scope in self:
            if scope.state != "verified":
                raise UserError(_("只有已核验个税账务口径可以撤销核验。"))
            if self.env["sudo.cn.iit.period.reconciliation.run"].sudo().search_count(
                [("accounting_scope_id", "=", scope.id)]
            ):
                raise UserError(
                    _("已进入个税勾稽快照的账务口径不可撤销核验，请新建后续口径。")
                )
            previous_checksum = scope.verification_checksum
            scope.with_context(
                cn_iit_scope_transition=_IIT_SCOPE_TRANSITION_MARKER
            ).write(
                {
                    "state": "draft",
                    "verified_at": False,
                    "verified_by_id": False,
                    "verification_checksum": False,
                }
            )
            self.env["sudo.compliance.audit.event"]._log_records(
                scope,
                "cn_iit_accounting_scope.verification_reset",
                previous_state="verified",
                new_state="draft",
                details={"previous_checksum": previous_checksum},
            )
        return True


class SudoChinaIitAccountingScopeLine(models.Model):
    _name = "sudo.cn.iit.accounting.scope.line"
    _description = "China IIT Accounting Scope Line"
    _order = "scope_id, role, account_id, id"
    _check_company_auto = True

    scope_id = fields.Many2one(
        "sudo.cn.iit.accounting.scope",
        string="个税账务口径",
        required=True,
        ondelete="cascade",
        check_company=True,
        index=True,
    )
    company_id = fields.Many2one(
        related="scope_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    account_id = fields.Many2one(
        "account.account",
        string="会计科目",
        required=True,
        ondelete="restrict",
        check_company=True,
        domain="[('company_ids', 'in', [company_id])]",
    )
    account_code = fields.Char(
        related="account_id.code", string="科目代码", readonly=True, store=True
    )
    account_type = fields.Selection(
        related="account_id.account_type", string="Odoo 科目类型", readonly=True
    )
    role = fields.Selection(
        [
            ("payroll_expense", "工资薪酬成本"),
            ("employee_payable", "应付职工薪酬"),
            ("iit_payable", "应交个人所得税"),
        ],
        string="取数角色",
        required=True,
        index=True,
    )
    exception_reason = fields.Text(
        string="非标准科目类型例外理由",
        help="科目类型与角色不一致时必须填写。",
    )

    _scope_account_unique = models.Constraint(
        "unique(scope_id, account_id)",
        "同一个税账务口径中的会计科目不能重复。",
    )

    @api.constrains("account_id", "company_id")
    def _check_account_company(self):
        for line in self:
            if line.company_id not in line.account_id.company_ids:
                raise ValidationError(_("会计科目必须属于个税账务口径所在公司。"))

    @api.model_create_multi
    def create(self, vals_list):
        scope_ids = {values.get("scope_id") for values in vals_list}
        scopes = self.env["sudo.cn.iit.accounting.scope"].browse(
            [scope_id for scope_id in scope_ids if scope_id]
        )
        if scopes.filtered(lambda scope: scope.state != "draft"):
            raise AccessError(_("已核验个税账务口径不可新增科目。"))
        for values in vals_list:
            if isinstance(values.get("exception_reason"), str):
                values["exception_reason"] = (
                    values["exception_reason"].strip() or False
                )
        return super().create(vals_list)

    def write(self, values):
        if self.mapped("scope_id").filtered(lambda scope: scope.state != "draft"):
            raise AccessError(_("已核验个税账务口径中的科目不可修改。"))
        if isinstance(values.get("exception_reason"), str):
            values["exception_reason"] = values["exception_reason"].strip() or False
        return super().write(values)

    def unlink(self):
        if self.mapped("scope_id").filtered(lambda scope: scope.state != "draft"):
            raise AccessError(_("已核验个税账务口径中的科目不可删除。"))
        return super().unlink()
