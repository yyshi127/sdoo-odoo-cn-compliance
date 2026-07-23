import hashlib
import json

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


_CROSS_BORDER_TRANSITION_MARKER = object()


class SudoChinaCrossBorderTransaction(models.Model):
    _name = "sudo.cn.cross.border.transaction"
    _description = "中国受控跨境业务"
    _order = "transaction_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(string="跨境业务编号", compute="_compute_name", store=True)
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
        string="公司",
        store=True,
        readonly=True,
        index=True,
    )
    country_id = fields.Many2one(
        related="profile_id.country_id",
        string="适用国家/地区",
        store=True,
        readonly=True,
    )
    period_start = fields.Date(string="期间开始", required=True, index=True)
    period_end = fields.Date(string="期间结束", required=True, index=True)
    transaction_date = fields.Date(string="业务日期", required=True, index=True)
    transaction_type = fields.Selection(
        [
            ("service_fee", "服务费"),
            ("royalty", "特许权使用费"),
            ("interest", "利息"),
            ("dividend", "股息"),
            ("goods", "货物"),
            ("cost_recharge", "成本分摊"),
            ("other", "其他"),
        ],
        string="业务类型",
        required=True,
        index=True,
    )
    counterparty_name = fields.Char(string="交易对方", required=True)
    counterparty_country_id = fields.Many2one(
        "res.country",
        string="交易对方国家/地区",
        required=True,
        index=True,
    )
    related_party = fields.Boolean(string="关联方")
    contract_reference = fields.Char(string="合同编号")
    payment_reference = fields.Char(string="付款凭据")
    service_or_asset_location = fields.Char(string="服务或资产所在地")
    currency_id = fields.Many2one(
        "res.currency",
        string="币种",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    amount = fields.Monetary(
        string="金额",
        currency_field="currency_id",
        required=True,
    )
    withholding_considered = fields.Boolean(
        string="已考虑代扣代缴",
        help="仅记录是否已考虑代扣代缴事项，不代表税务结论。",
    )
    withholding_note = fields.Text(string="代扣代缴复核说明")
    limitation_note = fields.Text(string="限制说明")
    evidence_attachment_ids = fields.Many2many(
        "ir.attachment",
        "sudo_cn_cross_border_transaction_attachment_rel",
        "transaction_id",
        "attachment_id",
        string="受控证据",
    )
    state = fields.Selection(
        [
            ("draft", "草稿"),
            ("submitted", "已提交"),
            ("reviewed", "已复核"),
            ("cancelled", "已取消"),
        ],
        string="状态",
        default="draft",
        required=True,
        readonly=True,
        index=True,
    )
    reviewer_id = fields.Many2one(
        "res.users",
        string="复核人",
        readonly=True,
        copy=False,
    )
    reviewed_at = fields.Datetime(string="复核时间", readonly=True, copy=False)
    review_notes = fields.Text(string="复核记录", copy=False)
    snapshot_checksum = fields.Char(
        string="快照 SHA-256",
        readonly=True,
        copy=False,
        index=True,
    )
    cn_cross_border_readiness_state = fields.Selection(
        [
            ("draft", "草稿"),
            ("needs_evidence", "待补证据"),
            ("needs_review", "待复核"),
            ("reviewed", "已复核"),
            ("cancelled", "已取消"),
        ],
        compute="_compute_cn_cross_border_readiness",
        string="准备状态",
    )
    cn_cross_border_next_action = fields.Char(
        compute="_compute_cn_cross_border_readiness",
        string="下一步",
    )

    _period_order = models.Constraint(
        "CHECK(period_start <= period_end)",
        "跨境业务期间开始日期不能晚于结束日期。",
    )
    _amount_positive = models.Constraint(
        "CHECK(amount > 0)",
        "跨境业务金额必须大于零。",
    )

    @api.depends(
        "counterparty_name",
        "transaction_type",
        "transaction_date",
        "amount",
        "currency_id",
    )
    def _compute_name(self):
        type_labels = dict(self._fields["transaction_type"].selection)
        for record in self:
            label = type_labels.get(record.transaction_type, "-")
            date = fields.Date.to_string(record.transaction_date) or "-"
            amount = record.amount or 0.0
            currency = record.currency_id.name or "-"
            record.name = "%s / %s / %s %.2f / %s" % (
                date,
                label,
                currency,
                amount,
                record.counterparty_name or "-",
            )

    @api.depends(
        "state",
        "evidence_attachment_ids",
        "withholding_considered",
        "review_notes",
    )
    def _compute_cn_cross_border_readiness(self):
        for record in self:
            if record.state == "cancelled":
                record.cn_cross_border_readiness_state = "cancelled"
                record.cn_cross_border_next_action = _("记录已取消。")
            elif not record.evidence_attachment_ids:
                record.cn_cross_border_readiness_state = "needs_evidence"
                record.cn_cross_border_next_action = _(
                    "请补充合同、付款、发票或申报证据。"
                )
            elif record.state == "draft":
                record.cn_cross_border_readiness_state = "draft"
                record.cn_cross_border_next_action = _(
                    "请提交受控跨境业务复核。"
                )
            elif record.state == "submitted":
                record.cn_cross_border_readiness_state = "needs_review"
                record.cn_cross_border_next_action = _(
                    "请复核代扣代缴、关联交易和证据限制。"
                )
            else:
                record.cn_cross_border_readiness_state = "reviewed"
                record.cn_cross_border_next_action = _(
                    "可将该已复核事实用于规则扫描和报告限制披露。"
                )

    @api.constrains("profile_id")
    def _check_china_profile(self):
        for record in self:
            if record.country_id.code != "CN":
                raise ValidationError(_("跨境业务事实必须关联中国合规档案。"))

    @api.constrains("period_start", "period_end", "transaction_date")
    def _check_transaction_date_period(self):
        for record in self:
            if not (record.period_start <= record.transaction_date <= record.period_end):
                raise ValidationError(
                    _("业务日期必须位于所声明的期间内。")
                )

    @api.constrains("counterparty_country_id")
    def _check_counterparty_country(self):
        china = self.env.ref("base.cn", raise_if_not_found=False)
        for record in self:
            if china and record.counterparty_country_id == china:
                raise ValidationError(
                    _("交易对方国家/地区必须位于中国境外。")
                )

    def _snapshot_payload(self):
        self.ensure_one()
        attachments = []
        for attachment in self.evidence_attachment_ids.sudo().sorted("id"):
            raw = attachment.raw or b""
            if isinstance(raw, str):
                raw = raw.encode("utf-8")
            attachments.append(
                {
                    "id": attachment.id,
                    "name": attachment.name,
                    "checksum": attachment.checksum,
                    "sha256": hashlib.sha256(bytes(raw)).hexdigest(),
                    "file_size": attachment.file_size,
                    "mimetype": attachment.mimetype,
                }
            )
        return {
            "schema": "sdoo.cn.cross-border-transaction.v1",
            "id": self.id,
            "profile_id": self.profile_id.id,
            "company_id": self.company_id.id,
            "period_start": fields.Date.to_string(self.period_start),
            "period_end": fields.Date.to_string(self.period_end),
            "transaction_date": fields.Date.to_string(self.transaction_date),
            "transaction_type": self.transaction_type,
            "counterparty_name": self.counterparty_name,
            "counterparty_country_code": self.counterparty_country_id.code,
            "related_party": bool(self.related_party),
            "contract_reference": self.contract_reference or None,
            "payment_reference": self.payment_reference or None,
            "service_or_asset_location": self.service_or_asset_location or None,
            "currency": self.currency_id.name,
            "amount": "%.2f" % (self.amount or 0.0),
            "withholding_considered": bool(self.withholding_considered),
            "withholding_note": self.withholding_note or None,
            "limitation_note": self.limitation_note or None,
            "attachments": attachments,
            "review_notes": self.review_notes or None,
        }

    def _snapshot_checksum(self):
        self.ensure_one()
        return hashlib.sha256(
            json.dumps(
                self._snapshot_payload(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    def _require_manager(self):
        if not self.env.user.has_group("sudo_global_finance.group_compliance_manager"):
            raise AccessError(_("只有合规经理可以控制此记录。"))

    def _transition_write(self, values):
        return self.with_context(
            cn_cross_border_transition=_CROSS_BORDER_TRANSITION_MARKER
        ).write(values)

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            values.update(
                {
                    "state": "draft",
                    "reviewer_id": False,
                    "reviewed_at": False,
                    "snapshot_checksum": False,
                }
            )
        return super().create(vals_list)

    def write(self, values):
        transition = (
            self.env.context.get("cn_cross_border_transition")
            is _CROSS_BORDER_TRANSITION_MARKER
        )
        protected = {"state", "reviewer_id", "reviewed_at", "snapshot_checksum"}
        if protected & set(values) and not transition:
            raise AccessError(_("请使用受控操作更新复核状态。"))
        if not transition and any(record.state == "reviewed" for record in self):
            raise AccessError(_("已复核的跨境业务事实不可修改。"))
        return super().write(values)

    def unlink(self):
        if any(record.state != "draft" for record in self):
            raise UserError(_("只有草稿状态的跨境业务事实可以删除。"))
        return super().unlink()

    def action_submit(self):
        self._require_manager()
        for record in self:
            if record.state != "draft":
                raise UserError(_("只有草稿记录可以提交复核。"))
            if not record.evidence_attachment_ids:
                raise UserError(_("提交前请附加受控证据。"))
            if not record.withholding_considered:
                raise UserError(_("请记录是否已考虑代扣代缴事项。"))
            record._transition_write({"state": "submitted"})
        return True

    def action_mark_reviewed(self):
        self._require_manager()
        for record in self:
            if record.state != "submitted":
                raise UserError(_("只有已提交记录可以执行复核。"))
            if len((record.review_notes or "").strip()) < 20:
                raise UserError(_("复核记录至少需要 20 个字符。"))
            record._transition_write(
                {
                    "state": "reviewed",
                    "reviewer_id": self.env.user.id,
                    "reviewed_at": fields.Datetime.now(),
                    "snapshot_checksum": record._snapshot_checksum(),
                }
            )
        return True

    def action_cancel(self):
        self._require_manager()
        self.filtered(lambda record: record.state != "reviewed")._transition_write(
            {"state": "cancelled"}
        )
        return True


class SudoChinaCrossBorderWorkbenchProfile(models.Model):
    _inherit = "sudo.compliance.profile"

    def action_cn_open_workbench_cross_border_transactions(self):
        self.ensure_one()
        action = self.env.ref(
            "sudo_country_pack_cn.action_cn_cross_border_transactions",
            raise_if_not_found=False,
        )
        if action:
            result = action.sudo().read()[0]
            result["domain"] = [("profile_id", "=", self.id)]
            result["context"] = {"default_profile_id": self.id}
            return result
        return {
            "type": "ir.actions.act_window",
            "name": _("跨境业务"),
            "res_model": "sudo.cn.cross.border.transaction",
            "view_mode": "list,form",
            "domain": [("profile_id", "=", self.id)],
            "context": {"default_profile_id": self.id},
            "target": "current",
        }
