import hashlib
import json

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


_CROSS_BORDER_TRANSITION_MARKER = object()


class SudoChinaCrossBorderTransaction(models.Model):
    _name = "sudo.cn.cross.border.transaction"
    _description = "China Controlled Cross-Border Transaction"
    _order = "transaction_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(compute="_compute_name", store=True)
    profile_id = fields.Many2one(
        "sudo.compliance.profile",
        string="Compliance Profile",
        required=True,
        ondelete="restrict",
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
    period_start = fields.Date(required=True, index=True)
    period_end = fields.Date(required=True, index=True)
    transaction_date = fields.Date(required=True, index=True)
    transaction_type = fields.Selection(
        [
            ("service_fee", "Service Fee"),
            ("royalty", "Royalty"),
            ("interest", "Interest"),
            ("dividend", "Dividend"),
            ("goods", "Goods"),
            ("cost_recharge", "Cost Recharge"),
            ("other", "Other"),
        ],
        required=True,
        index=True,
    )
    counterparty_name = fields.Char(required=True)
    counterparty_country_id = fields.Many2one(
        "res.country",
        string="Counterparty Country/Region",
        required=True,
        index=True,
    )
    related_party = fields.Boolean(string="Related Party")
    contract_reference = fields.Char()
    payment_reference = fields.Char()
    service_or_asset_location = fields.Char()
    currency_id = fields.Many2one(
        "res.currency",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    amount = fields.Monetary(currency_field="currency_id", required=True)
    withholding_considered = fields.Boolean(
        string="Withholding Considered",
        help="Only records whether the matter was considered. It is not a tax conclusion.",
    )
    withholding_note = fields.Text()
    limitation_note = fields.Text()
    evidence_attachment_ids = fields.Many2many(
        "ir.attachment",
        "sudo_cn_cross_border_transaction_attachment_rel",
        "transaction_id",
        "attachment_id",
        string="Controlled Evidence",
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("reviewed", "Reviewed"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
        readonly=True,
        index=True,
    )
    reviewer_id = fields.Many2one("res.users", readonly=True, copy=False)
    reviewed_at = fields.Datetime(readonly=True, copy=False)
    review_notes = fields.Text(copy=False)
    snapshot_checksum = fields.Char(readonly=True, copy=False, index=True)
    cn_cross_border_readiness_state = fields.Selection(
        [
            ("draft", "Draft"),
            ("needs_evidence", "Needs Evidence"),
            ("needs_review", "Needs Review"),
            ("reviewed", "Reviewed"),
            ("cancelled", "Cancelled"),
        ],
        compute="_compute_cn_cross_border_readiness",
        string="Readiness",
    )
    cn_cross_border_next_action = fields.Char(
        compute="_compute_cn_cross_border_readiness",
        string="Next Action",
    )

    _period_order = models.Constraint(
        "CHECK(period_start <= period_end)",
        "Cross-border transaction period start cannot be after period end.",
    )
    _amount_positive = models.Constraint(
        "CHECK(amount > 0)",
        "Cross-border transaction amount must be greater than zero.",
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
                record.cn_cross_border_next_action = _("Record is cancelled.")
            elif not record.evidence_attachment_ids:
                record.cn_cross_border_readiness_state = "needs_evidence"
                record.cn_cross_border_next_action = _(
                    "Attach contract, payment, invoice or filing evidence."
                )
            elif record.state == "draft":
                record.cn_cross_border_readiness_state = "draft"
                record.cn_cross_border_next_action = _(
                    "Submit for controlled cross-border review."
                )
            elif record.state == "submitted":
                record.cn_cross_border_readiness_state = "needs_review"
                record.cn_cross_border_next_action = _(
                    "Review withholding, related-party and evidence limitations."
                )
            else:
                record.cn_cross_border_readiness_state = "reviewed"
                record.cn_cross_border_next_action = _(
                    "Use this reviewed fact in scans and report limitations."
                )

    @api.constrains("profile_id")
    def _check_china_profile(self):
        for record in self:
            if record.country_id.code != "CN":
                raise ValidationError(_("Cross-border facts must use a China profile."))

    @api.constrains("period_start", "period_end", "transaction_date")
    def _check_transaction_date_period(self):
        for record in self:
            if not (record.period_start <= record.transaction_date <= record.period_end):
                raise ValidationError(
                    _("Transaction date must be inside the declared period.")
                )

    @api.constrains("counterparty_country_id")
    def _check_counterparty_country(self):
        china = self.env.ref("base.cn", raise_if_not_found=False)
        for record in self:
            if china and record.counterparty_country_id == china:
                raise ValidationError(
                    _("Counterparty country/region must be outside China.")
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
            raise AccessError(_("Only compliance managers can control this record."))

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
            raise AccessError(_("Use controlled actions to update review state."))
        if not transition and any(record.state == "reviewed" for record in self):
            raise AccessError(_("Reviewed cross-border facts cannot be changed."))
        return super().write(values)

    def unlink(self):
        if any(record.state != "draft" for record in self):
            raise UserError(_("Only draft cross-border facts can be deleted."))
        return super().unlink()

    def action_submit(self):
        self._require_manager()
        for record in self:
            if record.state != "draft":
                raise UserError(_("Only draft records can be submitted."))
            if not record.evidence_attachment_ids:
                raise UserError(_("Attach controlled evidence before submitting."))
            if not record.withholding_considered:
                raise UserError(_("Record whether withholding was considered."))
            record._transition_write({"state": "submitted"})
        return True

    def action_mark_reviewed(self):
        self._require_manager()
        for record in self:
            if record.state != "submitted":
                raise UserError(_("Only submitted records can be reviewed."))
            if len((record.review_notes or "").strip()) < 20:
                raise UserError(_("Review notes must contain at least 20 characters."))
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
            "name": _("Cross-Border Transactions"),
            "res_model": "sudo.cn.cross.border.transaction",
            "view_mode": "list,form",
            "domain": [("profile_id", "=", self.id)],
            "context": {"default_profile_id": self.id},
            "target": "current",
        }
