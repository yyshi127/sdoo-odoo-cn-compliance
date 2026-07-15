from urllib.parse import urlparse

from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from ..parser.contract import ContractError, inspect_taxonomy_bundle


_TAXONOMY_TRANSITION_MARKER = object()


class SudoChinaXbrlTaxonomyBundle(models.Model):
    _name = "sudo.cn.xbrl.taxonomy.bundle"
    _description = "China Governed XBRL Taxonomy Bundle"
    _order = "version desc, sealed_at desc, id desc"

    name = fields.Char(compute="_compute_name", store=True)
    standard_key = fields.Selection(
        [("mof_einvoice", "财政部电子发票会计数据标准")],
        string="标准类型",
        required=True,
        default="mof_einvoice",
    )
    official_title = fields.Char(string="官方名称", required=True)
    namespace = fields.Char(
        string="分类标准命名空间",
        required=True,
        default="http://xbrl.mof.gov.cn/taxonomy/2023-12-31/einv",
    )
    entry_point_namespace = fields.Char(
        string="入口文件命名空间",
        required=True,
        default=(
            "http://xbrl.mof.gov.cn/taxonomy/2023-12-31/einv/"
            "einv_receiver_entry_point"
        ),
    )
    version = fields.Char(
        string="分类标准版本",
        required=True,
        default="2023-12-31",
        index=True,
    )
    publication_date = fields.Date(string="发布日期", required=True)
    source_url = fields.Char(string="财政部来源地址", required=True)
    source_reference = fields.Char(string="来源引用", required=True)
    entry_point_hint = fields.Char(
        string="入口文件名或路径",
        required=True,
        default="einv_entry_point_2023-12-31.xsd",
    )
    entry_point_path = fields.Char(string="已确认入口路径", readonly=True)
    compatibility_profile = fields.Selection(
        [
            ("strict", "严格使用原始分类标准"),
            (
                "trim_role_uri_whitespace_v1",
                "角色 URI 尾空格兼容处理 v1",
            ),
        ],
        string="技术兼容方案",
        required=True,
        default="strict",
    )
    compatibility_reason = fields.Text(string="技术兼容确认说明")
    compatibility_patch_count = fields.Integer(
        string="兼容修正数",
        readonly=True,
    )
    bundle_attachment_ids = fields.Many2many(
        "ir.attachment",
        "sudo_cn_xbrl_taxonomy_attachment_rel",
        "taxonomy_id",
        "attachment_id",
        string="官方分类标准包",
    )
    bundle_sha256 = fields.Char(string="标准包 SHA-256", readonly=True)
    bundle_file_count = fields.Integer(string="标准包文件数", readonly=True)
    bundle_expanded_size = fields.Integer(string="展开字节数", readonly=True)
    sealed_manifest_json = fields.Json(string="封存清单", readonly=True)
    acquired_at = fields.Datetime(
        string="取得时间",
        required=True,
        default=fields.Datetime.now,
    )
    acquired_by_id = fields.Many2one(
        "res.users",
        string="登记人",
        required=True,
        readonly=True,
    )
    separation_exception_reason = fields.Text(string="单人复核例外理由")
    state = fields.Selection(
        [
            ("draft", "待复核"),
            ("sealed", "已封存"),
            ("superseded", "已被替代"),
        ],
        string="状态",
        required=True,
        default="draft",
        readonly=True,
        index=True,
    )
    sealed_at = fields.Datetime(string="封存时间", readonly=True)
    sealed_by_id = fields.Many2one(
        "res.users",
        string="复核封存人",
        readonly=True,
    )
    supersedes_id = fields.Many2one(
        "sudo.cn.xbrl.taxonomy.bundle",
        string="替代原标准包",
        ondelete="restrict",
        index=True,
    )
    replacement_ids = fields.One2many(
        "sudo.cn.xbrl.taxonomy.bundle",
        "supersedes_id",
        string="替代版本",
        readonly=True,
    )
    integrity_state = fields.Selection(
        [
            ("unsealed", "未封存"),
            ("verified", "完整性正常"),
            ("checksum_mismatch", "封存后文件已变化"),
        ],
        string="文件完整性",
        compute="_compute_integrity_state",
    )

    _controlled_fields = {
        "standard_key",
        "official_title",
        "namespace",
        "entry_point_namespace",
        "version",
        "publication_date",
        "source_url",
        "source_reference",
        "entry_point_hint",
        "compatibility_profile",
        "compatibility_reason",
        "bundle_attachment_ids",
        "acquired_at",
        "acquired_by_id",
        "separation_exception_reason",
        "supersedes_id",
    }
    _protected_fields = {
        "state",
        "entry_point_path",
        "bundle_sha256",
        "bundle_file_count",
        "bundle_expanded_size",
        "compatibility_patch_count",
        "sealed_manifest_json",
        "sealed_at",
        "sealed_by_id",
    }

    @api.depends("official_title", "version")
    def _compute_name(self):
        for bundle in self:
            bundle.name = "%s / %s" % (
                bundle.official_title or _("电子发票分类标准"),
                bundle.version or "-",
            )

    @api.depends(
        "state",
        "bundle_attachment_ids",
        "bundle_attachment_ids.checksum",
        "bundle_attachment_ids.file_size",
        "bundle_attachment_ids.name",
        "sealed_manifest_json",
    )
    def _compute_integrity_state(self):
        for bundle in self:
            bundle.integrity_state = bundle._current_integrity_state()

    def _current_integrity_state(self):
        self.ensure_one()
        if self.state == "draft" or not self.sealed_manifest_json:
            return "unsealed"
        expected = self.sealed_manifest_json or {}
        attachments = self.bundle_attachment_ids.sudo()
        if len(attachments) != 1:
            return "checksum_mismatch"
        attachment = attachments[:1]
        current = {
            "id": attachment.id,
            "name": attachment.name,
            "file_size": attachment.file_size,
            "odoo_checksum": attachment.checksum,
        }
        return "verified" if current == expected.get("attachment") else (
            "checksum_mismatch"
        )

    @api.constrains("publication_date")
    def _check_publication_date(self):
        today = fields.Date.context_today(self)
        for bundle in self:
            if bundle.publication_date and bundle.publication_date > today:
                raise ValidationError(_("分类标准发布日期不能晚于当前日期。"))

    @api.constrains(
        "supersedes_id",
        "standard_key",
        "namespace",
        "entry_point_namespace",
    )
    def _check_supersession(self):
        for bundle in self.filtered("supersedes_id"):
            original = bundle.supersedes_id
            if original == bundle:
                raise ValidationError(_("分类标准包不能替代自身。"))
            if original.standard_key != bundle.standard_key:
                raise ValidationError(_("替代版本必须保持相同标准类型。"))
            if original.namespace != bundle.namespace:
                raise ValidationError(_("替代版本必须保持相同命名空间。"))
            if original.entry_point_namespace != bundle.entry_point_namespace:
                raise ValidationError(_("替代版本必须保持相同入口文件命名空间。"))
            if original.state != "sealed":
                raise ValidationError(_("只能替代当前已封存的分类标准包。"))

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            for field_name in self._controlled_fields & set(values):
                value = values[field_name]
                if isinstance(value, str):
                    values[field_name] = value.strip() or False
            values.update(
                {
                    "acquired_by_id": self.env.user.id,
                    "state": "draft",
                    "entry_point_path": False,
                    "bundle_sha256": False,
                    "bundle_file_count": 0,
                    "bundle_expanded_size": 0,
                    "compatibility_patch_count": 0,
                    "sealed_manifest_json": False,
                    "sealed_at": False,
                    "sealed_by_id": False,
                }
            )
        bundles = super().create(vals_list)
        self.env["sudo.compliance.audit.event"]._log_records(
            bundles,
            "cn_xbrl_taxonomy.created",
            new_state="draft",
        )
        return bundles

    def write(self, values):
        transition = (
            self.env.context.get("cn_taxonomy_transition")
            is _TAXONOMY_TRANSITION_MARKER
        )
        if set(values) & self._protected_fields and not transition:
            raise AccessError(_("请使用分类标准包上的受控操作更新状态。"))
        changed = sorted(set(values) & self._controlled_fields)
        if changed and self.filtered(lambda bundle: bundle.state != "draft"):
            if not transition:
                raise AccessError(_("已封存的分类标准包不可修改，请创建替代版本。"))
        for field_name in self._controlled_fields & set(values):
            value = values[field_name]
            if isinstance(value, str):
                values[field_name] = value.strip() or False
        result = super().write(values)
        if changed and not transition:
            self.env["sudo.compliance.audit.event"]._log_records(
                self,
                "cn_xbrl_taxonomy.changed",
                previous_state="draft",
                new_state="draft",
                details={"changed_fields": changed},
            )
        return result

    def unlink(self):
        if self.filtered(lambda bundle: bundle.state != "draft"):
            raise UserError(_("已封存或已替代的分类标准包不可删除。"))
        self.env["sudo.compliance.audit.event"]._log_records(
            self,
            "cn_xbrl_taxonomy.deleted",
            previous_state="draft",
        )
        return super().unlink()

    def copy(self, default=None):
        values = dict(default or {})
        values.update(
            {
                "bundle_attachment_ids": [Command.clear()],
                "acquired_at": fields.Datetime.now(),
                "state": "draft",
                "entry_point_path": False,
                "bundle_sha256": False,
                "bundle_file_count": 0,
                "bundle_expanded_size": 0,
                "compatibility_patch_count": 0,
                "sealed_manifest_json": False,
                "sealed_at": False,
                "sealed_by_id": False,
                "separation_exception_reason": False,
            }
        )
        values.setdefault("supersedes_id", False)
        return super().copy(values)

    def _sealing_issues(self):
        self.ensure_one()
        issues = []
        required = (
            (self.official_title, _("未填写官方名称")),
            (self.namespace, _("未填写分类标准命名空间")),
            (self.entry_point_namespace, _("未填写入口文件命名空间")),
            (self.version, _("未填写分类标准版本")),
            (self.publication_date, _("未填写发布日期")),
            (self.source_url, _("未填写财政部来源地址")),
            (self.source_reference, _("未填写来源引用")),
            (self.entry_point_hint, _("未填写入口文件名或路径")),
        )
        issues.extend(message for value, message in required if not value)
        parsed = urlparse(self.source_url or "")
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not (
            hostname == "mof.gov.cn" or hostname.endswith(".mof.gov.cn")
        ):
            issues.append(_("分类标准来源必须是财政部 HTTPS 地址"))
        attachments = self.bundle_attachment_ids.sudo()
        if len(attachments) != 1:
            issues.append(_("必须且只能上传一个官方分类标准 ZIP 包"))
        elif attachments.type != "binary" or not attachments.raw:
            issues.append(_("分类标准包必须是系统内保存的非空二进制附件"))
        if self.acquired_by_id == self.env.user:
            reason = self.separation_exception_reason or ""
            if len(reason) < 20:
                issues.append(_("登记人与封存人为同一人时，需填写不少于 20 字的例外理由"))
        if (
            self.compatibility_profile != "strict"
            and len(self.compatibility_reason or "") < 20
        ):
            issues.append(_("启用技术兼容方案时，需填写不少于 20 字的确认说明"))
        return issues

    def action_seal(self):
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以封存分类标准包。"))
        for bundle in self:
            if bundle.state != "draft":
                raise UserError(_("只有待复核的分类标准包可以封存。"))
            issues = bundle._sealing_issues()
            if issues:
                raise UserError(
                    _(
                        "分类标准包尚不能封存：\n- %(issues)s",
                        issues="\n- ".join(issues),
                    )
                )
            attachment = bundle.bundle_attachment_ids.sudo()[:1]
            raw = attachment.raw
            try:
                inspection = inspect_taxonomy_bundle(
                    raw,
                    bundle.entry_point_hint,
                    bundle.namespace,
                    bundle.entry_point_namespace,
                )
            except ContractError as exc:
                raise UserError(
                    _(
                        "分类标准包安全检查失败 [%(code)s]：%(message)s",
                        code=exc.code,
                        message=exc.message,
                    )
                ) from exc
            detected_patches = inspection["role_uri_whitespace_count"]
            if detected_patches and bundle.compatibility_profile == "strict":
                raise UserError(
                    _(
                        "分类标准包检测到 %(count)s 处角色 URI 尾空格。"
                        "请选择受控兼容方案并填写确认说明，或使用修订后的官方包。",
                        count=detected_patches,
                    )
                )
            if (
                not detected_patches
                and bundle.compatibility_profile
                == "trim_role_uri_whitespace_v1"
            ):
                raise UserError(_("分类标准包未检测到所选兼容方案对应的问题。"))
            current = self.search(
                [
                    ("standard_key", "=", bundle.standard_key),
                    ("namespace", "=", bundle.namespace),
                    ("state", "=", "sealed"),
                    ("id", "!=", bundle.id),
                ],
                limit=1,
            )
            if current and bundle.supersedes_id != current:
                raise UserError(_("同一命名空间已有当前标准包，请从其创建替代版本。"))
            manifest = {
                "attachment": {
                    "id": attachment.id,
                    "name": attachment.name,
                    "file_size": attachment.file_size,
                    "odoo_checksum": attachment.checksum,
                },
                "sha256": inspection["sha256"],
                "entry_point_path": inspection["entry_point_path"],
                "compatibility_profile": bundle.compatibility_profile,
                "compatibility_patch_count": detected_patches,
            }
            bundle.with_context(
                cn_taxonomy_transition=_TAXONOMY_TRANSITION_MARKER
            ).write(
                {
                    "state": "sealed",
                    "entry_point_path": inspection["entry_point_path"],
                    "bundle_sha256": inspection["sha256"],
                    "bundle_file_count": inspection["file_count"],
                    "bundle_expanded_size": inspection["expanded_size"],
                    "compatibility_patch_count": detected_patches,
                    "sealed_manifest_json": manifest,
                    "sealed_at": fields.Datetime.now(),
                    "sealed_by_id": self.env.user.id,
                }
            )
            if bundle.supersedes_id:
                original = bundle.supersedes_id
                original.with_context(
                    cn_taxonomy_transition=_TAXONOMY_TRANSITION_MARKER
                ).write({"state": "superseded"})
                self.env["sudo.compliance.audit.event"]._log_records(
                    original,
                    "cn_xbrl_taxonomy.superseded",
                    previous_state="sealed",
                    new_state="superseded",
                    details={"replacement_id": bundle.id},
                )
            self.env["sudo.compliance.audit.event"]._log_records(
                bundle,
                "cn_xbrl_taxonomy.sealed",
                previous_state="draft",
                new_state="sealed",
                details={
                    "sha256": bundle.bundle_sha256,
                    "namespace": bundle.namespace,
                    "version": bundle.version,
                    "entry_point_path": bundle.entry_point_path,
                    "file_count": bundle.bundle_file_count,
                    "compatibility_profile": bundle.compatibility_profile,
                    "compatibility_patch_count": detected_patches,
                    "independent_review": (
                        bundle.acquired_by_id != bundle.sealed_by_id
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
            raise UserError(_("只有当前已封存的分类标准包可以创建替代版本。"))
        if self.replacement_ids:
            raise UserError(_("该分类标准包已经存在替代版本。"))
        replacement = self.copy({"supersedes_id": self.id})
        return {
            "type": "ir.actions.act_window",
            "name": _("分类标准包替代版本"),
            "res_model": self._name,
            "res_id": replacement.id,
            "view_mode": "form",
            "target": "current",
        }
