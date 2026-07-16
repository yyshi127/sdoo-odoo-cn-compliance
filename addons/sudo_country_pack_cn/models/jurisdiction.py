import hashlib
import json

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


_JURISDICTION_TRANSITION_MARKER = object()
_ASSIGNMENT_TRANSITION_MARKER = object()
_ASSESSMENT_SCOPE_MARKER = object()
_SCOPE_SCHEMA = "sdoo.cn.jurisdiction-assessment-scope.v1"
_MAX_PARENT_DEPTH = 32

CN_JURISDICTION_DOMAIN_SELECTION = [
    ("all", "全部中国财税领域"),
    ("accounting", "会计与凭证"),
    ("vat", "增值税"),
    ("cit", "企业所得税"),
    ("iit", "个人所得税扣缴"),
    ("surcharge", "附加税费"),
    ("stamp_duty", "印花税"),
    ("social_insurance", "社会保险费"),
    ("cross_border", "跨境事项"),
]


def _checksum(payload):
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _date_string(value):
    return fields.Date.to_string(value) if value else None


def _date_covers(record, target_date):
    target = fields.Date.to_date(target_date)
    start = fields.Date.to_date(record.effective_from)
    end = fields.Date.to_date(record.effective_to) if record.effective_to else None
    return bool(start and start <= target and (not end or target <= end))


def _ranges_overlap(left, right):
    left_start = fields.Date.to_date(left.effective_from)
    right_start = fields.Date.to_date(right.effective_from)
    left_end = (
        fields.Date.to_date(left.effective_to)
        if left.effective_to
        else fields.Date.to_date("9999-12-31")
    )
    right_end = (
        fields.Date.to_date(right.effective_to)
        if right.effective_to
        else fields.Date.to_date("9999-12-31")
    )
    return left_start <= right_end and right_start <= left_end


def _attachment_payload(attachments):
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
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
    return payload


def _source_snapshot_matches_hash(source):
    attachment = source.snapshot_attachment_id.sudo()
    raw = attachment.raw if attachment else b""
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    else:
        raw = bytes(raw or b"")
    return bool(
        raw
        and source.content_hash
        and hashlib.sha256(raw).hexdigest() == source.content_hash
    )


class SudoChinaJurisdictionVersion(models.Model):
    _name = "sudo.cn.jurisdiction.version"
    _description = "Governed China Compliance Jurisdiction Version"
    _order = "code, effective_from desc, version desc, id desc"

    name = fields.Char(string="辖区名称", required=True, translate=True)
    code = fields.Char(string="受控辖区编码", required=True, index=True)
    version = fields.Char(string="版本", required=True, default="1")
    level = fields.Selection(
        [
            ("national", "全国"),
            ("province", "省级"),
            ("prefecture", "地市级"),
            ("county", "区县级"),
            ("tax_authority", "税务机关辖区"),
            ("special_zone", "特殊适用区域"),
        ],
        string="辖区层级",
        required=True,
        index=True,
    )
    country_id = fields.Many2one(
        "res.country",
        string="国家/地区",
        required=True,
        default=lambda self: self.env.ref("base.cn"),
        readonly=True,
        index=True,
    )
    parent_id = fields.Many2one(
        "sudo.cn.jurisdiction.version",
        string="上级辖区版本",
        ondelete="restrict",
        index=True,
    )
    child_ids = fields.One2many(
        "sudo.cn.jurisdiction.version",
        "parent_id",
        string="下级辖区版本",
        readonly=True,
    )
    province_id = fields.Many2one(
        "res.country.state",
        string="对应省级行政区",
        domain="[('country_id', '=', country_id)]",
    )
    effective_from = fields.Date(
        string="有效开始日",
        required=True,
        index=True,
    )
    effective_to = fields.Date(string="有效结束日", index=True)
    authority_source_ids = fields.Many2many(
        "sudo.compliance.authority.source",
        "sudo_cn_jurisdiction_source_rel",
        "jurisdiction_id",
        "source_id",
        string="官方依据",
    )
    scope_note = fields.Text(
        string="适用范围与边界",
        help="说明行政或税务辖区含义、适用领域、排除项和仍需人工判断的边界。",
    )
    state = fields.Selection(
        [
            ("draft", "草稿"),
            ("pending_review", "待独立复核"),
            ("approved", "已批准"),
            ("active", "当前有效"),
            ("retired", "已退役"),
        ],
        string="状态",
        required=True,
        default="draft",
        readonly=True,
        index=True,
    )
    author_id = fields.Many2one(
        "res.users",
        string="编制人",
        required=True,
        default=lambda self: self.env.user,
        readonly=True,
    )
    reviewer_id = fields.Many2one(
        "res.users",
        string="独立复核人",
        readonly=True,
        copy=False,
    )
    submitted_at = fields.Datetime(string="提交时间", readonly=True, copy=False)
    approved_at = fields.Datetime(string="批准时间", readonly=True, copy=False)
    activated_at = fields.Datetime(string="生效时间", readonly=True, copy=False)
    retired_at = fields.Datetime(string="退役时间", readonly=True, copy=False)
    review_notes = fields.Text(string="复核意见")
    checksum = fields.Char(
        string="辖区版本 SHA-256",
        readonly=True,
        copy=False,
        index=True,
    )
    integrity_state = fields.Selection(
        [
            ("unapproved", "尚未批准"),
            ("verified", "完整性正常"),
            ("checksum_mismatch", "版本内容已变化"),
            ("source_invalid", "官方来源失效"),
            ("parent_invalid", "上级辖区失效"),
        ],
        string="完整性",
        compute="_compute_integrity_state",
    )

    _code_version_unique = models.Constraint(
        "unique(code, version)",
        "同一辖区编码的版本号必须唯一。",
    )

    _business_fields = {
        "name",
        "code",
        "version",
        "level",
        "parent_id",
        "province_id",
        "effective_from",
        "effective_to",
        "authority_source_ids",
        "scope_note",
    }
    _governance_fields = {
        "state",
        "author_id",
        "reviewer_id",
        "submitted_at",
        "approved_at",
        "activated_at",
        "retired_at",
        "checksum",
    }

    def _can_author(self):
        return self.env.user.has_group(
            "sudo_global_finance.group_compliance_rule_author"
        ) or self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        )

    def _can_approve(self):
        return self.env.user.has_group(
            "sudo_global_finance.group_compliance_rule_approver"
        ) or self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        )

    def _is_trusted_install_write(self):
        return self.env.is_superuser() and bool(self.env.context.get("install_mode"))

    def _transition_write(self, values):
        return self.with_context(
            cn_jurisdiction_transition=_JURISDICTION_TRANSITION_MARKER
        ).write(values)

    @api.model
    def _normalize_values(self, values):
        for field_name in ("name", "code", "version", "scope_note"):
            if field_name in values and isinstance(values[field_name], str):
                values[field_name] = values[field_name].strip() or False
        if values.get("code"):
            values["code"] = values["code"].upper()

    @api.model_create_multi
    def create(self, vals_list):
        trusted = self._is_trusted_install_write()
        for values in vals_list:
            self._normalize_values(values)
            values["country_id"] = self.env.ref("base.cn").id
            if not trusted:
                values.update(
                    {
                        "state": "draft",
                        "author_id": self.env.user.id,
                        "reviewer_id": False,
                        "submitted_at": False,
                        "approved_at": False,
                        "activated_at": False,
                        "retired_at": False,
                        "checksum": False,
                    }
                )
        records = super().create(vals_list)
        self.env["sudo.compliance.audit.event"]._log_records(
            records,
            "cn.jurisdiction.created",
            new_state="draft" if not trusted else False,
        )
        return records

    def write(self, values):
        self._normalize_values(values)
        changed = set(values)
        transition = (
            self.env.context.get("cn_jurisdiction_transition")
            is _JURISDICTION_TRANSITION_MARKER
        )
        trusted = transition or self._is_trusted_install_write()
        if changed & self._governance_fields and not trusted:
            raise AccessError(_("辖区治理状态只能由受控流程更新。"))
        if changed & self._business_fields and not trusted:
            if not self._can_author():
                raise AccessError(_("只有规则维护人员可以修改中国辖区版本。"))
            if any(record.state != "draft" for record in self):
                raise UserError(_("只有草稿辖区版本可以修改。"))
        if "review_notes" in changed and not trusted:
            if not self._can_approve():
                raise AccessError(_("只有独立复核人员可以填写辖区复核意见。"))
            if any(record.state not in {"draft", "pending_review"} for record in self):
                raise UserError(_("当前辖区状态不能修改复核意见。"))
        return super().write(values)

    def unlink(self):
        if any(record.state != "draft" for record in self):
            raise UserError(_("只有草稿辖区版本可以删除。"))
        return super().unlink()

    def copy(self, default=None):
        self.ensure_one()
        values = dict(default or {})
        values.update(
            {
                "version": _("%(version)s-副本", version=self.version),
                "state": "draft",
                "author_id": self.env.user.id,
                "reviewer_id": False,
                "submitted_at": False,
                "approved_at": False,
                "activated_at": False,
                "retired_at": False,
                "checksum": False,
            }
        )
        return super().copy(values)

    @api.constrains("effective_from", "effective_to")
    def _check_dates(self):
        for record in self:
            if record.effective_to and record.effective_to < record.effective_from:
                raise ValidationError(_("辖区有效结束日不能早于开始日。"))

    @api.constrains("parent_id")
    def _check_parent_cycle(self):
        for record in self:
            current = record.parent_id
            visited = {record.id}
            for _index in range(_MAX_PARENT_DEPTH):
                if not current:
                    break
                if current.id in visited:
                    raise ValidationError(_("中国辖区层级不能形成循环。"))
                visited.add(current.id)
                current = current.parent_id
            else:
                raise ValidationError(_("中国辖区层级超过受控最大深度。"))

    @api.constrains("country_id", "parent_id", "province_id", "level")
    def _check_china_scope(self):
        for record in self:
            if record.country_id.code != "CN":
                raise ValidationError(_("中国辖区版本只能属于中国。"))
            if record.parent_id and record.parent_id.country_id != record.country_id:
                raise ValidationError(_("上级辖区必须属于同一国家。"))
            if record.province_id and record.province_id.country_id != record.country_id:
                raise ValidationError(_("省级行政区必须属于中国。"))
            if record.level == "national" and record.parent_id:
                raise ValidationError(_("全国辖区不能设置上级辖区。"))

    def _snapshot_payload(self):
        self.ensure_one()
        canonical = self.with_context(lang="en_US")
        parent = canonical.parent_id
        return {
            "code": canonical.code,
            "version": canonical.version,
            "name": canonical.name,
            "level": canonical.level,
            "parent": (
                {
                    "code": parent.code,
                    "version": parent.version,
                    "checksum": parent.checksum or None,
                }
                if parent
                else None
            ),
            "province_code": canonical.province_id.code or None,
            "effective_from": _date_string(canonical.effective_from),
            "effective_to": _date_string(canonical.effective_to),
            "source_hashes": sorted(
                canonical.authority_source_ids.mapped("content_hash")
            ),
            "scope_note": canonical.scope_note or None,
        }

    def _current_checksum(self):
        self.ensure_one()
        return _checksum(self._snapshot_payload())

    def _source_issues(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        issues = []
        if not self.authority_source_ids:
            issues.append(_("未关联经过治理的中国官方来源。"))
        invalid_country = self.authority_source_ids.filtered(
            lambda source: source.country_id.code != "CN"
        )
        if invalid_country:
            issues.append(_("官方来源包含非中国来源。"))
        invalid = self.authority_source_ids.filtered(
            lambda source: source.status != "valid"
            or not source.content_hash
            or not source.snapshot_attachment_id
            or not source._is_publishable_snapshot()
            or not _source_snapshot_matches_hash(source)
            or (source.next_review_date and source.next_review_date < today)
        )
        if invalid:
            issues.append(
                _(
                    "官方来源尚未通过有效快照、哈希、独立复核或时效检查：%(names)s",
                    names=", ".join(invalid.mapped("display_name")),
                )
            )
        return issues

    def _governance_issues(self):
        self.ensure_one()
        issues = list(self._source_issues())
        if not self.scope_note:
            issues.append(_("未填写适用范围与结论边界。"))
        parent = self.parent_id
        if self.level != "national" and not parent:
            issues.append(_("非全国辖区必须关联一个经过治理的上级辖区版本。"))
        if parent:
            if parent.state != "active" or parent._current_integrity_state() != "verified":
                issues.append(_("上级辖区尚未生效或完整性异常。"))
            if parent.effective_from > self.effective_from:
                issues.append(_("上级辖区未覆盖当前辖区的有效开始日。"))
            if self.effective_to and (
                not parent.effective_to or parent.effective_to >= self.effective_to
            ):
                pass
            elif self.effective_to:
                issues.append(_("上级辖区未覆盖当前辖区的完整有效期间。"))
            elif parent.effective_to:
                issues.append(_("开放结束日的辖区不能依赖已设置结束日的上级版本。"))
        return issues

    def _active_overlaps(self):
        self.ensure_one()
        others = self.search(
            [
                ("id", "!=", self.id),
                ("code", "=", self.code),
                ("state", "=", "active"),
            ]
        )
        return others.filtered(lambda other: _ranges_overlap(self, other))

    def _current_integrity_state(self):
        self.ensure_one()
        if self.state not in {"approved", "active", "retired"} or not self.checksum:
            return "unapproved"
        if self.checksum != self._current_checksum():
            return "checksum_mismatch"
        if self._source_issues():
            return "source_invalid"
        if self.state == "active" and self.parent_id and (
            self.parent_id.state != "active"
            or self.parent_id._current_integrity_state() != "verified"
        ):
            return "parent_invalid"
        return "verified"

    @api.depends(
        "state",
        "checksum",
        "name",
        "code",
        "version",
        "level",
        "parent_id.state",
        "parent_id.checksum",
        "province_id",
        "effective_from",
        "effective_to",
        "authority_source_ids.status",
        "authority_source_ids.content_hash",
        "authority_source_ids.snapshot_attachment_id",
        "authority_source_ids.snapshot_attachment_id.raw",
        "authority_source_ids.snapshot_kind",
        "authority_source_ids.next_review_date",
        "scope_note",
    )
    def _compute_integrity_state(self):
        for record in self:
            record.integrity_state = record._current_integrity_state()

    def action_submit_review(self):
        if not self._can_author():
            raise AccessError(_("只有规则维护人员可以提交辖区复核。"))
        for record in self:
            if record.state != "draft":
                raise UserError(_("只有草稿辖区版本可以提交复核。"))
            issues = record._governance_issues()
            if issues:
                raise UserError(
                    _("辖区版本尚不能提交复核：\n- %(issues)s", issues="\n- ".join(issues))
                )
        now = fields.Datetime.now()
        for record in self:
            record._transition_write(
                {"state": "pending_review", "submitted_at": now}
            )
            self.env["sudo.compliance.audit.event"]._log_records(
                record,
                "cn.jurisdiction.submitted",
                previous_state="draft",
                new_state="pending_review",
            )
        return True

    def action_approve(self):
        if not self._can_approve():
            raise AccessError(_("只有规则审批人员可以批准辖区版本。"))
        for record in self:
            if record.state != "pending_review":
                raise UserError(_("只有待独立复核的辖区版本可以批准。"))
            if record.author_id == self.env.user:
                raise UserError(_("辖区编制人与独立复核人必须为不同用户。"))
            issues = record._governance_issues()
            if issues:
                raise UserError(
                    _("辖区版本尚不能批准：\n- %(issues)s", issues="\n- ".join(issues))
                )
        now = fields.Datetime.now()
        for record in self:
            checksum = record._current_checksum()
            record._transition_write(
                {
                    "state": "approved",
                    "reviewer_id": self.env.user.id,
                    "approved_at": now,
                    "checksum": checksum,
                }
            )
            self.env["sudo.compliance.audit.event"]._log_records(
                record,
                "cn.jurisdiction.approved",
                previous_state="pending_review",
                new_state="approved",
                details={"checksum": checksum},
            )
        return True

    def action_activate(self):
        if not self._can_approve():
            raise AccessError(_("只有规则审批人员可以发布辖区版本。"))
        for record in self:
            if record.state != "approved":
                raise UserError(_("只有已批准的辖区版本可以生效。"))
            if record.checksum != record._current_checksum():
                raise UserError(_("辖区批准后内容发生变化，请重新复核。"))
            issues = record._governance_issues()
            if issues:
                raise UserError(
                    _("辖区版本尚不能生效：\n- %(issues)s", issues="\n- ".join(issues))
                )
            if record._active_overlaps():
                raise UserError(_("同一辖区编码存在有效期重叠的生效版本。"))
        now = fields.Datetime.now()
        for record in self:
            record._transition_write({"state": "active", "activated_at": now})
            self.env["sudo.compliance.audit.event"]._log_records(
                record,
                "cn.jurisdiction.activated",
                previous_state="approved",
                new_state="active",
                details={"checksum": record.checksum},
            )
        return True

    def action_reject(self):
        if not self._can_approve():
            raise AccessError(_("只有规则审批人员可以退回辖区版本。"))
        for record in self:
            if record.state != "pending_review":
                raise UserError(_("只有待独立复核的辖区版本可以退回。"))
            if not (record.review_notes or "").strip():
                raise UserError(_("退回辖区版本前必须填写复核意见。"))
        for record in self:
            record._transition_write(
                {
                    "state": "draft",
                    "reviewer_id": False,
                    "submitted_at": False,
                    "approved_at": False,
                    "checksum": False,
                }
            )
            self.env["sudo.compliance.audit.event"]._log_records(
                record,
                "cn.jurisdiction.rejected",
                previous_state="pending_review",
                new_state="draft",
                details={"review_notes": record.review_notes},
            )
        return True

    def action_retire(self):
        if not self._can_approve():
            raise AccessError(_("只有规则审批人员可以退役辖区版本。"))
        now = fields.Datetime.now()
        for record in self:
            if record.state != "active":
                raise UserError(_("只有当前有效的辖区版本可以退役。"))
            active_children = record.child_ids.filtered(
                lambda child: child.state == "active"
            )
            if active_children:
                raise UserError(_("请先退役当前辖区的全部生效下级辖区。"))
        for record in self:
            record._transition_write({"state": "retired", "retired_at": now})
            self.env["sudo.compliance.audit.event"]._log_records(
                record,
                "cn.jurisdiction.retired",
                previous_state="active",
                new_state="retired",
                details={"checksum": record.checksum},
            )
        return True

    def _is_within(self, ancestor):
        self.ensure_one()
        ancestor.ensure_one()
        current = self
        visited = set()
        for _index in range(_MAX_PARENT_DEPTH):
            if not current or current.id in visited:
                return False
            if current == ancestor:
                return True
            visited.add(current.id)
            current = current.parent_id
        return False


class SudoChinaProfileJurisdiction(models.Model):
    _name = "sudo.cn.profile.jurisdiction"
    _description = "Verified China Profile Jurisdiction Assignment"
    _order = "profile_id, applicability_domain, valid_from desc, id desc"
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
        index=True,
    )
    jurisdiction_id = fields.Many2one(
        "sudo.cn.jurisdiction.version",
        string="受控辖区版本",
        required=True,
        ondelete="restrict",
        index=True,
    )
    applicability_domain = fields.Selection(
        CN_JURISDICTION_DOMAIN_SELECTION,
        string="适用财税领域",
        required=True,
        default="all",
        index=True,
    )
    role = fields.Selection(
        [
            ("tax_registration", "主管税务登记辖区"),
            ("registered_office", "登记住所辖区"),
            ("branch", "分支机构辖区"),
            ("payroll", "工资与社保辖区"),
            ("transaction", "交易或项目辖区"),
            ("other", "其他受控适用关系"),
        ],
        string="适用关系",
        required=True,
        default="tax_registration",
    )
    valid_from = fields.Date(
        string="有效开始日",
        required=True,
        default=fields.Date.context_today,
        index=True,
    )
    valid_to = fields.Date(string="有效结束日", index=True)
    source_type = fields.Selection(
        [
            ("electronic_tax_bureau", "电子税务局受控导出"),
            ("tax_registration_document", "税务登记或认定文书"),
            ("tax_authority_confirmation", "税务机关确认材料"),
            ("professional_workpaper", "专业复核工作底稿"),
            ("other", "其他受控来源"),
        ],
        string="适用性来源类型",
    )
    source_date = fields.Date(string="来源资料日期")
    source_reference = fields.Char(string="来源引用")
    scope_note = fields.Text(string="适用范围与限制")
    evidence_attachment_ids = fields.Many2many(
        "ir.attachment",
        "sudo_cn_profile_jurisdiction_attachment_rel",
        "assignment_id",
        "attachment_id",
        string="适用性依据附件",
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
        "res.users", string="核验人", readonly=True, copy=False
    )
    jurisdiction_checksum = fields.Char(
        string="辖区版本 SHA-256",
        readonly=True,
        copy=False,
    )
    verification_checksum = fields.Char(
        string="适用快照 SHA-256",
        readonly=True,
        copy=False,
        index=True,
    )
    integrity_state = fields.Selection(
        [
            ("unverified", "未核验"),
            ("verified", "完整性正常"),
            ("jurisdiction_invalid", "辖区版本失效"),
            ("checksum_mismatch", "适用资料已变化"),
        ],
        string="完整性",
        compute="_compute_integrity_state",
    )

    _controlled_fields = {
        "profile_id",
        "jurisdiction_id",
        "applicability_domain",
        "role",
        "valid_from",
        "valid_to",
        "source_type",
        "source_date",
        "source_reference",
        "scope_note",
        "evidence_attachment_ids",
        "evidence_attachment_ids.name",
        "evidence_attachment_ids.mimetype",
        "evidence_attachment_ids.file_size",
        "evidence_attachment_ids.raw",
    }
    _protected_fields = {
        "state",
        "verified_at",
        "verified_by_id",
        "jurisdiction_checksum",
        "verification_checksum",
    }

    @api.depends(
        "profile_id", "jurisdiction_id", "applicability_domain", "valid_from"
    )
    def _compute_name(self):
        for assignment in self:
            assignment.name = "%s / %s / %s" % (
                assignment.profile_id.display_name or _("中国合规档案"),
                assignment.jurisdiction_id.display_name or _("适用辖区"),
                dict(CN_JURISDICTION_DOMAIN_SELECTION).get(
                    assignment.applicability_domain, "-"
                ),
            )

    @api.model
    def _normalize_values(self, values):
        for field_name in ("source_reference", "scope_note"):
            if field_name in values and isinstance(values[field_name], str):
                values[field_name] = values[field_name].strip() or False

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            self._normalize_values(values)
            values.update(
                {
                    "state": "draft",
                    "verified_at": False,
                    "verified_by_id": False,
                    "jurisdiction_checksum": False,
                    "verification_checksum": False,
                }
            )
        records = super().create(vals_list)
        self.env["sudo.compliance.audit.event"]._log_records(
            records,
            "cn.profile_jurisdiction.created",
            new_state="draft",
        )
        return records

    def write(self, values):
        self._normalize_values(values)
        changed = set(values)
        transition = (
            self.env.context.get("cn_assignment_transition")
            is _ASSIGNMENT_TRANSITION_MARKER
        )
        if changed & self._protected_fields and not transition:
            raise AccessError(_("请使用适用辖区快照上的核验操作更新状态。"))
        controlled = sorted(changed & self._controlled_fields)
        verified = self.filtered(lambda record: record.state == "verified")
        if controlled and verified and not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以修改已核验的辖区适用快照。"))
        previous = {
            record.id: {
                "state": record.state,
                "checksum": record.verification_checksum,
            }
            for record in self
        }
        if controlled and not transition:
            values.update(
                {
                    "state": "draft",
                    "verified_at": False,
                    "verified_by_id": False,
                    "jurisdiction_checksum": False,
                    "verification_checksum": False,
                }
            )
        result = super().write(values)
        if controlled and not transition:
            for record in self:
                self.env["sudo.compliance.audit.event"]._log_records(
                    record,
                    "cn.profile_jurisdiction.changed",
                    previous_state=previous[record.id]["state"],
                    new_state=record.state,
                    details={
                        "changed_fields": controlled,
                        "previous_checksum": previous[record.id]["checksum"],
                        "verification_reset": True,
                    },
                )
        return result

    def unlink(self):
        if any(record.state == "verified" for record in self):
            raise UserError(_("已核验的辖区适用快照不可删除。"))
        return super().unlink()

    def copy(self, default=None):
        values = dict(default or {})
        values.update(
            {
                "state": "draft",
                "verified_at": False,
                "verified_by_id": False,
                "jurisdiction_checksum": False,
                "verification_checksum": False,
            }
        )
        return super().copy(values)

    @api.constrains("profile_id", "jurisdiction_id")
    def _check_china_profile(self):
        for assignment in self:
            if assignment.country_id.code != "CN":
                raise ValidationError(_("中国辖区适用快照只能关联中国合规档案。"))
            if assignment.jurisdiction_id.country_id.code != "CN":
                raise ValidationError(_("适用辖区版本必须属于中国。"))

    @api.constrains("valid_from", "valid_to")
    def _check_dates(self):
        for assignment in self:
            if assignment.valid_to and assignment.valid_to < assignment.valid_from:
                raise ValidationError(_("适用快照有效结束日不能早于开始日。"))

    def _overlapping_verified(self):
        self.ensure_one()
        domain = [
            ("profile_id", "=", self.profile_id.id),
            ("jurisdiction_id", "=", self.jurisdiction_id.id),
            ("applicability_domain", "=", self.applicability_domain),
            ("role", "=", self.role),
            ("state", "=", "verified"),
            ("id", "!=", self.id),
            "|",
            ("valid_to", "=", False),
            ("valid_to", ">=", self.valid_from),
        ]
        if self.valid_to:
            domain.append(("valid_from", "<=", self.valid_to))
        return self.search(domain)

    def _checksum_payload(self, jurisdiction_checksum=None):
        self.ensure_one()
        return {
            "profile_id": self.profile_id.id,
            "company_id": self.company_id.id,
            "jurisdiction": {
                "code": self.jurisdiction_id.code,
                "version": self.jurisdiction_id.version,
                "checksum": jurisdiction_checksum or self.jurisdiction_checksum,
            },
            "applicability_domain": self.applicability_domain,
            "role": self.role,
            "valid_from": _date_string(self.valid_from),
            "valid_to": _date_string(self.valid_to),
            "source_type": self.source_type,
            "source_date": _date_string(self.source_date),
            "source_reference": self.source_reference or None,
            "scope_note": self.scope_note or None,
            "attachments": _attachment_payload(self.evidence_attachment_ids),
        }

    def _current_checksum(self):
        self.ensure_one()
        return _checksum(self._checksum_payload())

    def _verification_issues(self):
        self.ensure_one()
        issues = []
        jurisdiction = self.jurisdiction_id
        if jurisdiction.state != "active" or jurisdiction._current_integrity_state() != "verified":
            issues.append(_("所选辖区版本尚未生效或完整性异常。"))
        if not _date_covers(jurisdiction, self.valid_from):
            issues.append(_("辖区版本未覆盖适用快照开始日。"))
        if self.valid_to and not _date_covers(jurisdiction, self.valid_to):
            issues.append(_("辖区版本未覆盖适用快照结束日。"))
        if not self.source_type:
            issues.append(_("未选择适用性来源类型。"))
        if not self.source_date:
            issues.append(_("未填写来源资料日期。"))
        elif self.source_date > fields.Date.context_today(self):
            issues.append(_("来源资料日期不能晚于当前日期。"))
        if not self.source_reference:
            issues.append(_("未填写来源引用。"))
        if not self.scope_note:
            issues.append(_("未记录适用范围与限制。"))
        if not self.evidence_attachment_ids:
            issues.append(_("未上传辖区适用性依据附件。"))
        else:
            invalid = self.evidence_attachment_ids.sudo().filtered(
                lambda attachment: attachment.type != "binary" or not attachment.raw
            )
            if invalid:
                issues.append(_("适用性依据必须是系统内保存的非空二进制附件。"))
        return issues

    def _current_integrity_state(self):
        self.ensure_one()
        if self.state != "verified" or not self.verification_checksum:
            return "unverified"
        jurisdiction = self.jurisdiction_id
        if (
            jurisdiction.state != "active"
            or jurisdiction._current_integrity_state() != "verified"
            or jurisdiction.checksum != self.jurisdiction_checksum
        ):
            return "jurisdiction_invalid"
        if self.verification_checksum != self._current_checksum():
            return "checksum_mismatch"
        return "verified"

    @api.depends(
        "state",
        "verification_checksum",
        "jurisdiction_checksum",
        "jurisdiction_id.state",
        "jurisdiction_id.checksum",
        "jurisdiction_id.integrity_state",
        "applicability_domain",
        "role",
        "valid_from",
        "valid_to",
        "source_type",
        "source_date",
        "source_reference",
        "scope_note",
        "evidence_attachment_ids",
    )
    def _compute_integrity_state(self):
        for assignment in self:
            assignment.integrity_state = assignment._current_integrity_state()

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
            order="applicability_domain, role, valid_from desc, id",
        )

    def action_verify(self):
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以核验辖区适用快照。"))
        for assignment in self:
            if assignment.state != "draft":
                raise UserError(_("只有待核验的辖区适用快照可以核验。"))
            issues = assignment._verification_issues()
            if issues:
                raise UserError(
                    _("辖区适用快照尚不能核验：\n- %(issues)s", issues="\n- ".join(issues))
                )
            if assignment._overlapping_verified():
                raise UserError(_("同一辖区、领域、关系和期间已有已核验适用快照。"))
        now = fields.Datetime.now()
        for assignment in self:
            jurisdiction_checksum = assignment.jurisdiction_id.checksum
            payload = assignment._checksum_payload(jurisdiction_checksum)
            verification_checksum = _checksum(payload)
            assignment.with_context(
                cn_assignment_transition=_ASSIGNMENT_TRANSITION_MARKER
            ).write(
                {
                    "state": "verified",
                    "verified_at": now,
                    "verified_by_id": self.env.user.id,
                    "jurisdiction_checksum": jurisdiction_checksum,
                    "verification_checksum": verification_checksum,
                }
            )
            self.env["sudo.compliance.audit.event"]._log_records(
                assignment,
                "cn.profile_jurisdiction.verified",
                previous_state="draft",
                new_state="verified",
                details={
                    "jurisdiction_checksum": jurisdiction_checksum,
                    "verification_checksum": verification_checksum,
                    "verification_payload": payload,
                },
            )
        return True

    def action_reset_to_draft(self):
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以撤销辖区适用核验。"))
        for assignment in self:
            if assignment.state != "verified":
                raise UserError(_("只有已核验的辖区适用快照可以撤销核验。"))
            previous_checksum = assignment.verification_checksum
            assignment.with_context(
                cn_assignment_transition=_ASSIGNMENT_TRANSITION_MARKER
            ).write(
                {
                    "state": "draft",
                    "verified_at": False,
                    "verified_by_id": False,
                    "jurisdiction_checksum": False,
                    "verification_checksum": False,
                }
            )
            self.env["sudo.compliance.audit.event"]._log_records(
                assignment,
                "cn.profile_jurisdiction.verification_reset",
                previous_state="verified",
                new_state="draft",
                details={"previous_checksum": previous_checksum},
            )
        return True


class SudoComplianceProfile(models.Model):
    _inherit = "sudo.compliance.profile"

    cn_jurisdiction_assignment_ids = fields.One2many(
        "sudo.cn.profile.jurisdiction",
        "profile_id",
        string="中国辖区适用快照",
    )


class SudoComplianceRuleVersion(models.Model):
    _inherit = "sudo.compliance.rule.version"

    cn_jurisdiction_ids = fields.Many2many(
        "sudo.cn.jurisdiction.version",
        "sudo_cn_rule_version_jurisdiction_rel",
        "version_id",
        "jurisdiction_id",
        string="中国地方适用辖区",
    )
    cn_jurisdiction_domain = fields.Selection(
        CN_JURISDICTION_DOMAIN_SELECTION,
        string="辖区适用领域",
        required=True,
        default="all",
    )
    cn_jurisdiction_scope_state = fields.Selection(
        [
            ("national", "全国规则"),
            ("ready", "地方范围已治理"),
            ("invalid", "地方范围待治理"),
        ],
        string="地方适用范围",
        compute="_compute_cn_jurisdiction_scope",
        readonly=True,
    )
    cn_jurisdiction_scope_blockers = fields.Text(
        string="地方范围阻断事项",
        compute="_compute_cn_jurisdiction_scope",
        readonly=True,
    )
    cn_release_state = fields.Selection(
        selection_add=[("jurisdiction_governance", "地方适用范围待治理")],
        ondelete={"jurisdiction_governance": "set null"},
    )

    def _cn_jurisdiction_scope_issues(self):
        self.ensure_one()
        issues = []
        if not self.cn_jurisdiction_ids:
            return issues
        if self.rule_id.country_id.code != "CN":
            issues.append(_("只有中国规则可以设置中国地方适用辖区。"))
        for jurisdiction in self.cn_jurisdiction_ids:
            if jurisdiction.state != "active":
                issues.append(_("辖区 %(scope)s 尚未生效。", scope=jurisdiction.display_name))
                continue
            if jurisdiction._current_integrity_state() != "verified":
                issues.append(_("辖区 %(scope)s 完整性异常。", scope=jurisdiction.display_name))
            if jurisdiction.effective_from > self.effective_from:
                issues.append(_("辖区 %(scope)s 未覆盖规则生效日。", scope=jurisdiction.display_name))
            if self.effective_to:
                if jurisdiction.effective_to and jurisdiction.effective_to < self.effective_to:
                    issues.append(_("辖区 %(scope)s 未覆盖规则完整有效期。", scope=jurisdiction.display_name))
            elif jurisdiction.effective_to:
                issues.append(_("开放结束日的规则不能绑定已设置结束日的辖区版本。"))
        return issues

    @api.depends(
        "rule_id.country_id.code",
        "effective_from",
        "effective_to",
        "cn_jurisdiction_ids.state",
        "cn_jurisdiction_ids.checksum",
        "cn_jurisdiction_ids.integrity_state",
        "cn_jurisdiction_ids.effective_from",
        "cn_jurisdiction_ids.effective_to",
        "cn_jurisdiction_ids.authority_source_ids.status",
        "cn_jurisdiction_ids.authority_source_ids.content_hash",
        "cn_jurisdiction_ids.authority_source_ids.snapshot_attachment_id",
        "cn_jurisdiction_ids.authority_source_ids.snapshot_attachment_id.raw",
        "cn_jurisdiction_ids.authority_source_ids.snapshot_kind",
        "cn_jurisdiction_ids.authority_source_ids.next_review_date",
    )
    def _compute_cn_jurisdiction_scope(self):
        for version in self:
            if not version.cn_jurisdiction_ids:
                version.cn_jurisdiction_scope_state = "national"
                version.cn_jurisdiction_scope_blockers = False
                continue
            issues = version._cn_jurisdiction_scope_issues()
            version.cn_jurisdiction_scope_state = "invalid" if issues else "ready"
            version.cn_jurisdiction_scope_blockers = "\n".join(
                "- %s" % issue for issue in issues
            ) or False

    @api.depends(
        "rule_id.country_id.code",
        "rule_id.cn_rule_nature",
        "state",
        "test_state",
        "professional_review_state",
        "requires_human_review",
        "test_case_ids",
        "cn_review_packet_ready",
        "cn_review_packet_blockers",
        "authority_source_ids.status",
        "authority_source_ids.content_hash",
        "authority_source_ids.snapshot_attachment_id",
        "authority_source_ids.snapshot_kind",
        "authority_source_ids.next_review_date",
        "cn_jurisdiction_ids",
        "cn_jurisdiction_ids.state",
        "cn_jurisdiction_ids.checksum",
        "cn_jurisdiction_ids.effective_from",
        "cn_jurisdiction_ids.effective_to",
        "cn_jurisdiction_ids.authority_source_ids.status",
        "cn_jurisdiction_ids.authority_source_ids.content_hash",
        "cn_jurisdiction_ids.authority_source_ids.snapshot_attachment_id",
        "cn_jurisdiction_ids.authority_source_ids.snapshot_attachment_id.raw",
        "cn_jurisdiction_ids.authority_source_ids.snapshot_kind",
        "cn_jurisdiction_ids.authority_source_ids.next_review_date",
        "cn_jurisdiction_ids.parent_id.state",
        "cn_jurisdiction_ids.parent_id.checksum",
        "cn_jurisdiction_domain",
    )
    def _compute_cn_release_governance(self):
        super()._compute_cn_release_governance()
        for version in self.filtered(
            lambda item: item.cn_is_china_rule and item.cn_jurisdiction_ids
        ):
            issues = version._cn_jurisdiction_scope_issues()
            if not issues:
                continue
            details = "\n".join("- %s" % issue for issue in issues)
            existing_release = version.cn_release_blockers or ""
            existing_professional = version.cn_professional_review_blockers or ""
            version.cn_governance_ready = False
            version.cn_professional_review_ready = False
            version.cn_release_blockers = "\n".join(
                item for item in (details, existing_release) if item
            )
            version.cn_professional_review_blockers = "\n".join(
                item for item in (details, existing_professional) if item
            )
            if version.state == "active":
                version.cn_release_state = "active_attention"
            elif version.state != "retired":
                version.cn_release_state = "jurisdiction_governance"

    @api.constrains("rule_id", "cn_jurisdiction_ids")
    def _check_cn_jurisdiction_country(self):
        for version in self.filtered("cn_jurisdiction_ids"):
            if version.rule_id.country_id.code != "CN":
                raise ValidationError(_("中国地方适用辖区只能用于中国规则。"))

    def write(self, values):
        changed = set(values)
        scope_change = bool(
            changed & {"cn_jurisdiction_ids", "cn_jurisdiction_domain"}
        )
        trusted = self._is_lifecycle_write() or self._is_trusted_install_write()
        base_business_change = bool(changed & self._business_fields)
        invalidated = self.filtered(
            lambda version: scope_change
            and not trusted
            and not base_business_change
            and (
                version.professional_review_state != "pending"
                or version.professional_reviewer_id
                or version.professional_rule_checksum
            )
        )
        if scope_change and not trusted:
            if not self._can_author():
                raise AccessError(_("只有规则维护人员可以修改地方适用范围。"))
            if any(version.state != "draft" for version in self):
                raise UserError(_("只有草稿规则版本可以修改地方适用范围。"))
        result = super().write(values)
        if scope_change and not trusted and not base_business_change:
            self._lifecycle_write(
                {
                    "test_state": "untested",
                    "test_run_at": False,
                    "checksum": False,
                    **self._professional_reset_values(),
                }
            )
            if invalidated:
                self.env["sudo.compliance.audit.event"]._log_records(
                    invalidated,
                    "rule_version.professional_signoff_invalidated",
                    details={"reason": "cn_jurisdiction_scope_changed"},
                )
            self._add_payload_preparer(
                self.env.user, reason="cn_jurisdiction_scope_changed"
            )
        return result

    def _check_publish_gate(self):
        for version in self.filtered("cn_jurisdiction_ids"):
            issues = version._cn_jurisdiction_scope_issues()
            if issues:
                raise UserError(
                    _("地方适用范围尚未完成治理：\n- %(issues)s", issues="\n- ".join(issues))
                )
        return super()._check_publish_gate()

    def _checksum_payload(self):
        payload = super()._checksum_payload()
        if self.cn_jurisdiction_ids:
            payload["cn_jurisdiction_domain"] = self.cn_jurisdiction_domain
            payload["cn_jurisdictions"] = sorted(
                (
                    jurisdiction.code,
                    jurisdiction.version,
                    jurisdiction.checksum,
                )
                for jurisdiction in self.cn_jurisdiction_ids
            )
        return payload


class SudoComplianceAssessment(models.Model):
    _inherit = "sudo.compliance.assessment"

    cn_is_china_assessment = fields.Boolean(
        related="profile_id.is_china_profile",
        string="中国合规评估",
        readonly=True,
    )
    cn_jurisdiction_coverage_state = fields.Selection(
        [
            ("not_assessed", "尚未评估"),
            ("not_required", "无地方范围规则"),
            ("complete", "适用范围完整"),
            ("incomplete", "适用资料不足"),
            ("integrity_error", "适用资料完整性异常"),
        ],
        string="地方规则覆盖",
        required=True,
        default="not_assessed",
        readonly=True,
        copy=False,
        index=True,
    )
    cn_jurisdiction_assignment_count = fields.Integer(
        string="有效期内辖区快照", readonly=True, copy=False
    )
    cn_jurisdiction_scoped_rule_count = fields.Integer(
        string="地方范围规则", readonly=True, copy=False
    )
    cn_jurisdiction_selected_rule_count = fields.Integer(
        string="已选地方规则", readonly=True, copy=False
    )
    cn_jurisdiction_excluded_rule_count = fields.Integer(
        string="排除或阻断规则", readonly=True, copy=False
    )
    cn_jurisdiction_blocked_rule_count = fields.Integer(
        string="资料阻断规则", readonly=True, copy=False
    )
    cn_jurisdiction_scope_snapshot_json = fields.Json(
        string="辖区与地方规则范围快照", readonly=True, copy=False
    )
    cn_jurisdiction_scope_checksum = fields.Char(
        string="辖区范围快照 SHA-256", readonly=True, copy=False, index=True
    )
    cn_jurisdiction_scope_integrity_state = fields.Selection(
        [
            ("unavailable", "尚无快照"),
            ("verified", "完整性正常"),
            ("checksum_mismatch", "快照已变化"),
        ],
        string="辖区范围完整性",
        compute="_compute_cn_jurisdiction_scope_integrity",
    )
    cn_jurisdiction_coverage_message = fields.Char(
        string="地方规则覆盖说明",
        compute="_compute_cn_jurisdiction_coverage_message",
    )

    _cn_scope_fields = {
        "cn_jurisdiction_coverage_state",
        "cn_jurisdiction_assignment_count",
        "cn_jurisdiction_scoped_rule_count",
        "cn_jurisdiction_selected_rule_count",
        "cn_jurisdiction_excluded_rule_count",
        "cn_jurisdiction_blocked_rule_count",
        "cn_jurisdiction_scope_snapshot_json",
        "cn_jurisdiction_scope_checksum",
    }

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            for field_name in self._cn_scope_fields:
                values.pop(field_name, None)
        return super().create(vals_list)

    def write(self, values):
        if set(values) & self._cn_scope_fields and (
            self.env.context.get("cn_assessment_scope_write")
            is not _ASSESSMENT_SCOPE_MARKER
        ):
            raise AccessError(_("评估辖区范围快照只能由规则引擎写入。"))
        return super().write(values)

    def _cn_jurisdiction_scope_write(self, values):
        return self.with_context(
            cn_assessment_scope_write=_ASSESSMENT_SCOPE_MARKER
        ).write(values)

    @api.depends(
        "cn_jurisdiction_scope_snapshot_json",
        "cn_jurisdiction_scope_checksum",
    )
    def _compute_cn_jurisdiction_scope_integrity(self):
        for assessment in self:
            if (
                not assessment.cn_jurisdiction_scope_snapshot_json
                or not assessment.cn_jurisdiction_scope_checksum
            ):
                assessment.cn_jurisdiction_scope_integrity_state = "unavailable"
            elif _checksum(assessment.cn_jurisdiction_scope_snapshot_json) == (
                assessment.cn_jurisdiction_scope_checksum
            ):
                assessment.cn_jurisdiction_scope_integrity_state = "verified"
            else:
                assessment.cn_jurisdiction_scope_integrity_state = (
                    "checksum_mismatch"
                )

    @api.depends(
        "cn_jurisdiction_coverage_state",
        "cn_jurisdiction_scoped_rule_count",
        "cn_jurisdiction_selected_rule_count",
        "cn_jurisdiction_excluded_rule_count",
        "cn_jurisdiction_blocked_rule_count",
    )
    def _compute_cn_jurisdiction_coverage_message(self):
        for assessment in self:
            if assessment.cn_jurisdiction_coverage_state == "complete":
                assessment.cn_jurisdiction_coverage_message = _(
                    "%(selected)s 条地方规则已按受控辖区选中，%(excluded)s 条经完整范围判断排除。",
                    selected=assessment.cn_jurisdiction_selected_rule_count,
                    excluded=assessment.cn_jurisdiction_excluded_rule_count,
                )
            elif assessment.cn_jurisdiction_coverage_state == "incomplete":
                assessment.cn_jurisdiction_coverage_message = _(
                    "%(blocked)s 条地方规则因缺少已核验辖区适用资料而未执行，不能解释为无风险。",
                    blocked=assessment.cn_jurisdiction_blocked_rule_count,
                )
            elif assessment.cn_jurisdiction_coverage_state == "integrity_error":
                assessment.cn_jurisdiction_coverage_message = _(
                    "辖区版本或公司适用快照完整性异常，相关地方规则已阻断。"
                )
            elif assessment.cn_jurisdiction_coverage_state == "not_required":
                assessment.cn_jurisdiction_coverage_message = _(
                    "本次候选规则均未限定中国地方辖区。"
                )
            else:
                assessment.cn_jurisdiction_coverage_message = _(
                    "评估执行后显示地方规则适用范围和排除依据。"
                )

    @api.depends(
        "state",
        "data_sufficiency_state",
        "fail_count",
        "unknown_count",
        "error_count",
        "source_warning_count",
        "professional_warning_count",
        "review_pending_count",
        "cn_jurisdiction_coverage_state",
        "cn_jurisdiction_scope_integrity_state",
    )
    def _compute_report_state(self):
        super()._compute_report_state()
        for assessment in self.filtered(lambda record: record.state == "completed"):
            if (
                assessment.cn_jurisdiction_coverage_state
                in {"incomplete", "integrity_error"}
                or assessment.cn_jurisdiction_scope_integrity_state
                == "checksum_mismatch"
            ):
                assessment.report_state = "limited"


class SudoChinaComplianceEngine(models.AbstractModel):
    _inherit = "sudo.compliance.engine"

    @staticmethod
    def _assignment_domain_matches(assignment, required_domain):
        return required_domain == "all" or assignment.applicability_domain in {
            "all",
            required_domain,
        }

    @staticmethod
    def _assignment_snapshot(assignment):
        return {
            "assignment_id": assignment.id,
            "state": assignment.state,
            "integrity_state": assignment._current_integrity_state(),
            "applicability_domain": assignment.applicability_domain,
            "role": assignment.role,
            "valid_from": _date_string(assignment.valid_from),
            "valid_to": _date_string(assignment.valid_to),
            "verification_checksum": assignment.verification_checksum or None,
            "jurisdiction": {
                "code": assignment.jurisdiction_id.code,
                "version": assignment.jurisdiction_id.version,
                "state": assignment.jurisdiction_id.state,
                "integrity_state": (
                    assignment.jurisdiction_id._current_integrity_state()
                ),
                "checksum": assignment.jurisdiction_id.checksum or None,
            },
        }

    def _select_versions(self, assessment):
        explicit = bool(assessment.rule_version_ids)
        versions = super()._select_versions(assessment)
        if assessment.country_id.code != "CN":
            return versions

        target_date = fields.Date.to_date(assessment.evaluation_date)
        assignments = self.env["sudo.cn.profile.jurisdiction"]._for_profile_date(
            assessment.profile_id,
            target_date,
        )
        scoped_versions = versions.filtered("cn_jurisdiction_ids")
        selected_scoped = self.env["sudo.compliance.rule.version"]
        rule_snapshots = []
        blocked_count = 0
        integrity_failure = False
        incomplete = False

        for version in scoped_versions:
            domain_assignments = assignments.filtered(
                lambda assignment: self._assignment_domain_matches(
                    assignment, version.cn_jurisdiction_domain
                )
            )
            valid_assignments = domain_assignments.filtered(
                lambda assignment: assignment.state == "verified"
                and assignment._current_integrity_state() == "verified"
                and _date_covers(assignment.jurisdiction_id, target_date)
            )
            invalid_verified = domain_assignments.filtered(
                lambda assignment: assignment.state == "verified"
                and assignment._current_integrity_state() != "verified"
            )
            scope_invalid = version._cn_jurisdiction_scope_issues()
            matched = valid_assignments.filtered(
                lambda assignment: any(
                    assignment.jurisdiction_id._is_within(target)
                    for target in version.cn_jurisdiction_ids
                )
            )

            if scope_invalid:
                status = "blocked_integrity"
                reason = "rule_scope_invalid"
                integrity_failure = True
                blocked_count += 1
            elif invalid_verified:
                status = "blocked_integrity"
                reason = "assignment_integrity_invalid"
                integrity_failure = True
                blocked_count += 1
            elif matched:
                status = "selected"
                reason = "verified_scope_match"
                selected_scoped |= version
            elif valid_assignments:
                status = "excluded"
                reason = "verified_out_of_scope"
            elif domain_assignments:
                status = "blocked_missing"
                reason = "assignment_not_verified"
                incomplete = True
                blocked_count += 1
            else:
                status = "blocked_missing"
                reason = "assignment_missing"
                incomplete = True
                blocked_count += 1

            rule_snapshots.append(
                {
                    "rule_code": version.rule_id.code,
                    "version": version.version,
                    "domain": version.cn_jurisdiction_domain,
                    "status": status,
                    "reason": reason,
                    "target_scopes": sorted(
                        (
                            jurisdiction.code,
                            jurisdiction.version,
                            jurisdiction.checksum or None,
                        )
                        for jurisdiction in version.cn_jurisdiction_ids
                    ),
                    "matched_assignment_ids": matched.ids,
                }
            )

        if not scoped_versions:
            coverage_state = "not_required"
        elif integrity_failure:
            coverage_state = "integrity_error"
        elif incomplete:
            coverage_state = "incomplete"
        else:
            coverage_state = "complete"

        snapshot = {
            "schema": _SCOPE_SCHEMA,
            "assessment_id": assessment.id,
            "profile_id": assessment.profile_id.id,
            "company_id": assessment.company_id.id,
            "evaluation_date": _date_string(target_date),
            "explicit_rule_scope": explicit,
            "coverage_state": coverage_state,
            "assignments": [
                self._assignment_snapshot(assignment) for assignment in assignments
            ],
            "scoped_rules": rule_snapshots,
        }
        snapshot_checksum = _checksum(snapshot)
        excluded_count = len(scoped_versions) - len(selected_scoped)
        assessment._cn_jurisdiction_scope_write(
            {
                "cn_jurisdiction_coverage_state": coverage_state,
                "cn_jurisdiction_assignment_count": len(assignments),
                "cn_jurisdiction_scoped_rule_count": len(scoped_versions),
                "cn_jurisdiction_selected_rule_count": len(selected_scoped),
                "cn_jurisdiction_excluded_rule_count": excluded_count,
                "cn_jurisdiction_blocked_rule_count": blocked_count,
                "cn_jurisdiction_scope_snapshot_json": snapshot,
                "cn_jurisdiction_scope_checksum": snapshot_checksum,
            }
        )
        self.env["sudo.compliance.audit.event"]._log_records(
            assessment,
            "cn.assessment.jurisdiction_scope_frozen",
            details={
                "coverage_state": coverage_state,
                "snapshot_checksum": snapshot_checksum,
                "scoped_rule_count": len(scoped_versions),
                "selected_rule_count": len(selected_scoped),
                "blocked_rule_count": blocked_count,
            },
        )

        excluded_explicit = [
            item for item in rule_snapshots if item["status"] != "selected"
        ]
        if explicit and excluded_explicit:
            details = ", ".join(
                "%s (%s)" % (item["rule_code"], item["reason"])
                for item in excluded_explicit
            )
            raise UserError(
                _(
                    "显式选择的地方规则与当前公司辖区不匹配或资料不足：%(details)s",
                    details=details,
                )
            )

        national_versions = versions - scoped_versions
        selected = national_versions | selected_scoped
        if not selected and scoped_versions:
            if coverage_state in {"incomplete", "integrity_error"}:
                raise UserError(
                    _("地方规则因辖区适用资料不足或完整性异常而全部阻断。")
                )
            raise UserError(_("当前公司不在任何候选地方规则的已核验适用范围内。"))
        return selected.sorted(
            lambda version: (version.rule_id.code, version.effective_from)
        )
