from collections import Counter, defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal
import hashlib
import json
import re

from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import SQL


RECONCILIATION_ENGINE_VERSION = "19.0.2"
_RECONCILIATION_SNAPSHOT_LANG = "en_US"
MAX_SOURCE_DOCUMENTS = 50000
MAX_LEDGER_MOVES = 100000
_RECONCILIATION_TRANSITION_MARKER = object()
_LEDGER_MOVE_SNAPSHOT_FIELDS = (
    "name",
    "ref",
    "payment_reference",
    "invoice_origin",
    "move_type",
    "state",
    "date",
    "invoice_date",
    "commercial_partner_id",
    "currency_id",
    "company_currency_id",
    "amount_total",
    "amount_tax",
    "write_date",
)


def _checksum(payload):
    content = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _checksum_list_item(digest, payload, item_count):
    if item_count:
        digest.update(b",")
    digest.update(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def _safe_text(value, limit=1000):
    if value in (None, False):
        return False
    return " ".join(str(value).split()).strip()[:limit] or False


def _reference_token(value):
    text = _safe_text(value, 512) or ""
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", text).upper()


def _name_token(value):
    return _reference_token(value).casefold()


def _date_string(value):
    return fields.Date.to_string(value) if value else None


def _datetime_string(value):
    return fields.Datetime.to_string(value) if value else None


def _amount_string(currency, value):
    rounded = currency.round(abs(float(value or 0.0)))
    return format(Decimal(str(rounded)), "f")


def _reason(code, matched, points):
    return {
        "code": code,
        "matched": bool(matched),
        "points": int(points if matched else 0),
    }


REASON_LABELS = {
    "invoice_reference_exact": "发票号码精确",
    "invoice_reference_contains": "发票号码包含",
    "voucher_reference_exact": "凭证编号精确",
    "voucher_reference_contains": "凭证编号包含",
    "partner_tax_id": "往来方识别号",
    "partner_name": "往来方名称",
    "currency": "币种",
    "total_amount": "价税合计",
    "tax_amount": "税额",
    "debit_total": "借方合计",
    "credit_total": "贷方合计",
    "document_date": "日期",
    "document_type": "单据类型",
    "posted": "已过账",
    "summary": "摘要",
    "manual": "人工指定",
}


def _reason_summary(reasons):
    parts = []
    for reason in reasons:
        points = int(reason.get("points") or 0)
        if not points:
            continue
        label = REASON_LABELS.get(reason.get("code"), reason.get("code"))
        parts.append("%s %+d" % (label, points))
    return "；".join(parts) or "未达到自动建议条件"


class SudoChinaEinvoiceReconciliationRun(models.Model):
    _name = "sudo.cn.einvoice.reconciliation.run"
    _description = "China Electronic Invoice Reconciliation Run"
    _order = "requested_at desc, id desc"
    _check_company_auto = True

    name = fields.Char(compute="_compute_name", store=True)
    profile_id = fields.Many2one(
        "sudo.compliance.profile",
        string="合规档案",
        required=True,
        ondelete="restrict",
        check_company=True,
        readonly=True,
        index=True,
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
        readonly=True,
    )
    period_start = fields.Date(string="期间开始", required=True, readonly=True)
    period_end = fields.Date(string="期间结束", required=True, readonly=True)
    state = fields.Selection(
        [
            ("queued", "待处理"),
            ("processing", "处理中"),
            ("succeeded", "当前结果"),
            ("failed", "失败"),
            ("cancelled", "已取消"),
            ("superseded", "已被替代"),
        ],
        string="状态",
        required=True,
        default="queued",
        readonly=True,
        index=True,
    )
    engine_version = fields.Char(
        string="匹配引擎版本",
        required=True,
        readonly=True,
    )
    requested_at = fields.Datetime(
        string="提交时间",
        required=True,
        readonly=True,
    )
    requested_by_id = fields.Many2one(
        "res.users",
        string="提交人",
        required=True,
        readonly=True,
    )
    started_at = fields.Datetime(string="开始时间", readonly=True)
    finished_at = fields.Datetime(string="完成时间", readonly=True)
    source_availability_state = fields.Selection(
        [
            ("not_evaluated", "未形成结果"),
            ("no_data", "无可用源数据"),
            ("available", "源数据可勾稽"),
            ("blocked", "源数据存在阻断"),
        ],
        string="源数据状态",
        required=True,
        default="not_evaluated",
        readonly=True,
        index=True,
    )
    source_document_count = fields.Integer(string="源发票数", readonly=True)
    ledger_move_count = fields.Integer(string="账簿凭证数", readonly=True)
    case_count = fields.Integer(string="勾稽事项数", readonly=True)
    matched_case_count = fields.Integer(string="已匹配", readonly=True)
    suggested_case_count = fields.Integer(string="单一建议", readonly=True)
    ambiguous_case_count = fields.Integer(string="多候选", readonly=True)
    unmatched_case_count = fields.Integer(string="未匹配", readonly=True)
    data_gap_case_count = fields.Integer(string="数据缺口", readonly=True)
    warning_case_count = fields.Integer(string="含警告事项", readonly=True)
    source_snapshot_checksum = fields.Char(
        string="发票台账快照 SHA-256",
        readonly=True,
    )
    ledger_snapshot_checksum = fields.Char(
        string="Odoo 账簿范围 SHA-256",
        readonly=True,
    )
    result_checksum = fields.Char(string="勾稽结果 SHA-256", readonly=True)
    result_summary = fields.Text(string="结果摘要", readonly=True)
    error_code = fields.Char(string="失败代码", readonly=True)
    case_ids = fields.One2many(
        "sudo.cn.einvoice.reconciliation.case",
        "run_id",
        string="账票勾稽事项",
        readonly=True,
    )

    _period_order = models.Constraint(
        "CHECK(period_start <= period_end)",
        "勾稽期间开始日期不能晚于结束日期。",
    )
    _active_period_unique = models.UniqueIndex(
        "(profile_id, period_start, period_end) "
        "WHERE state IN ('queued', 'processing')",
        "同一合规档案和期间只能有一个待处理或处理中的勾稽批次。",
    )

    @api.depends("profile_id", "period_start", "period_end")
    def _compute_name(self):
        for run in self:
            run.name = "%s / %s - %s" % (
                run.profile_id.display_name or _("账票勾稽"),
                fields.Date.to_string(run.period_start) or "-",
                fields.Date.to_string(run.period_end) or "-",
            )

    @api.model_create_multi
    def create(self, vals_list):
        if (
            self.env.context.get("cn_reconciliation_transition")
            is not _RECONCILIATION_TRANSITION_MARKER
        ):
            raise AccessError(_("账票勾稽批次只能由受控流程创建。"))
        for values in vals_list:
            values.update(
                {
                    "state": "queued",
                    "engine_version": RECONCILIATION_ENGINE_VERSION,
                    "requested_at": fields.Datetime.now(),
                    "requested_by_id": self.env.user.id,
                    "started_at": False,
                    "finished_at": False,
                    "source_availability_state": "not_evaluated",
                    "source_document_count": 0,
                    "ledger_move_count": 0,
                    "case_count": 0,
                    "matched_case_count": 0,
                    "suggested_case_count": 0,
                    "ambiguous_case_count": 0,
                    "unmatched_case_count": 0,
                    "data_gap_case_count": 0,
                    "warning_case_count": 0,
                    "source_snapshot_checksum": False,
                    "ledger_snapshot_checksum": False,
                    "result_checksum": False,
                    "result_summary": False,
                    "error_code": False,
                }
            )
        return super().create(vals_list)

    def write(self, values):
        if (
            self.env.context.get("cn_reconciliation_transition")
            is not _RECONCILIATION_TRANSITION_MARKER
        ):
            raise AccessError(_("账票勾稽批次只能由受控流程更新。"))
        return super().write(values)

    def unlink(self):
        raise AccessError(_("账票勾稽批次属于审计记录，不可删除。"))

    @api.model
    def enqueue(self, profile, period_start, period_end):
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以提交账票勾稽。"))
        profile.ensure_one()
        period_start = fields.Date.to_date(period_start)
        period_end = fields.Date.to_date(period_end)
        if not period_start or not period_end or period_start > period_end:
            raise ValidationError(_("请选择有效的勾稽期间。"))
        country = self.env.ref("base.cn")
        if profile.country_id != country:
            raise UserError(_("只能对中国合规档案执行本账票勾稽。"))
        active = self.search(
            [
                ("profile_id", "=", profile.id),
                ("period_start", "=", period_start),
                ("period_end", "=", period_end),
                ("state", "in", ("queued", "processing")),
            ],
            limit=1,
        )
        if active:
            raise UserError(_("相同档案和期间已有待处理或处理中的勾稽批次。"))
        run = self.with_company(profile.company_id).with_context(
            cn_reconciliation_transition=_RECONCILIATION_TRANSITION_MARKER
        ).create(
            {
                "profile_id": profile.id,
                "period_start": period_start,
                "period_end": period_end,
            }
        )
        self.env["sudo.compliance.audit.event"]._log_records(
            run,
            "cn_einvoice_reconciliation.queued",
            new_state="queued",
            details={
                "period_start": fields.Date.to_string(period_start),
                "period_end": fields.Date.to_string(period_end),
                "engine_version": RECONCILIATION_ENGINE_VERSION,
            },
        )
        return run.with_context(cn_reconciliation_transition=None)

    def _source_documents(self):
        self.ensure_one()
        start_datetime = datetime.combine(self.period_start, time.min)
        end_datetime = datetime.combine(self.period_end, time.max)
        domain = [
            ("profile_id", "=", self.profile_id.id),
            ("is_current_result", "=", True),
            "|",
            "&",
            ("request_time", ">=", fields.Datetime.to_string(start_datetime)),
            ("request_time", "<=", fields.Datetime.to_string(end_datetime)),
            "&",
            ("request_time", "=", False),
            "&",
            ("dataset_id.period_start", "<=", self.period_end),
            ("dataset_id.period_end", ">=", self.period_start),
        ]
        documents = self.env["sudo.cn.einvoice.document"].search(
            domain,
            order="request_time, invoice_number, id",
            limit=MAX_SOURCE_DOCUMENTS + 1,
        )
        if len(documents) > MAX_SOURCE_DOCUMENTS:
            raise UserError(_("单次勾稽的规范化电子发票超过安全上限。"))
        return documents

    def _ledger_moves(self):
        self.ensure_one()
        date_from = self.period_start - timedelta(days=62)
        date_to = self.period_end + timedelta(days=62)
        moves = self.env["account.move"].sudo().with_company(
            self.company_id
        ).search(
            [
                ("company_id", "=", self.company_id.id),
                ("state", "in", ("draft", "posted")),
                ("move_type", "in", ("entry", "in_invoice", "in_refund")),
                ("date", ">=", date_from),
                ("date", "<=", date_to),
            ],
            order="date, id",
            limit=MAX_LEDGER_MOVES + 1,
        )
        if len(moves) > MAX_LEDGER_MOVES:
            raise UserError(_("单次勾稽的 Odoo 会计凭证超过安全上限。"))
        return moves

    @api.model
    def _move_references(self, move):
        return [
            value
            for value in (
                move.name,
                move.ref,
                move.payment_reference,
                move.invoice_origin,
            )
            if value
        ]

    @api.model
    def _move_core_snapshot(self, move):
        partner = move.commercial_partner_id
        currency = move.currency_id or move.company_currency_id
        business_date = move.invoice_date or move.date
        payload = {
            "move_id": move.id,
            "name": move.name or None,
            "ref": move.ref or None,
            "payment_reference": move.payment_reference or None,
            "invoice_origin": move.invoice_origin or None,
            "move_type": move.move_type,
            "state": move.state,
            "date": _date_string(move.date),
            "business_date": _date_string(business_date),
            "partner_id": partner.id or None,
            "partner_name": partner.name or None,
            "partner_vat": (partner.vat or "").upper() or None,
            "currency_id": currency.id,
            "currency_code": currency.name,
            "amount_total": _amount_string(currency, move.amount_total),
            "amount_tax": _amount_string(currency, move.amount_tax),
            "write_date": _datetime_string(move.write_date),
        }
        return payload

    @api.model
    def _move_candidate_snapshot(self, move, line_summary=None):
        payload = self._move_core_snapshot(move)
        company_currency = move.company_currency_id
        if line_summary is None:
            lines = move.line_ids
            line_summary = {
                "debit_total": sum(lines.mapped("debit")),
                "credit_total": sum(lines.mapped("credit")),
                "line_count": len(lines),
                "line_write_date": max(
                    (line.write_date for line in lines if line.write_date),
                    default=None,
                ),
            }
        payload.update(
            {
                "company_currency_id": company_currency.id,
                "company_currency_code": company_currency.name,
                "debit_total": _amount_string(
                    company_currency,
                    line_summary["debit_total"],
                ),
                "credit_total": _amount_string(
                    company_currency,
                    line_summary["credit_total"],
                ),
                "line_count": line_summary["line_count"],
                "line_write_date": _datetime_string(
                    line_summary["line_write_date"]
                ),
            }
        )
        return payload

    @api.model
    def _ledger_line_summaries(self, moves):
        if not moves:
            return {}
        line_model = self.env["account.move.line"].sudo()
        line_model.flush_model(["move_id", "debit", "credit", "write_date"])
        rows = self.env.execute_query(
            SQL(
                """
                SELECT move_id,
                       COALESCE(SUM(debit), 0.0),
                       COALESCE(SUM(credit), 0.0),
                       COUNT(*),
                       MAX(write_date)
                  FROM account_move_line
                 WHERE move_id = ANY(%s)
                 GROUP BY move_id
                """,
                moves.ids,
            )
        )
        return {
            move_id: {
                "debit_total": debit_total,
                "credit_total": credit_total,
                "line_count": line_count,
                "line_write_date": line_write_date,
            }
            for (
                move_id,
                debit_total,
                credit_total,
                line_count,
                line_write_date,
            ) in rows
        }

    @api.model
    def _build_move_indexes(self, moves):
        moves = moves.with_context(prefetch_fields=False)
        moves.fetch(_LEDGER_MOVE_SNAPSHOT_FIELDS)
        indexes = {
            "bill_reference": defaultdict(set),
            "voucher_reference": defaultdict(set),
            "partner_vat": defaultdict(set),
            "partner_name": defaultdict(set),
            "bill_amount": defaultdict(set),
            "date": defaultdict(set),
        }
        line_summaries = self._ledger_line_summaries(moves)
        empty_line_summary = {
            "debit_total": 0.0,
            "credit_total": 0.0,
            "line_count": 0,
            "line_write_date": None,
        }
        snapshot_count = 0
        snapshot_digest = hashlib.sha256()
        snapshot_digest.update(b"[")
        for move in moves.sorted("id"):
            snapshot = self._move_candidate_snapshot(
                move,
                line_summaries.get(move.id, empty_line_summary),
            )
            _checksum_list_item(snapshot_digest, snapshot, snapshot_count)
            snapshot_count += 1
            references = {
                _reference_token(value)
                for value in self._move_references(move)
                if _reference_token(value)
            }
            for reference in references:
                indexes["voucher_reference"][reference].add(move.id)
                if move.move_type in ("in_invoice", "in_refund"):
                    indexes["bill_reference"][reference].add(move.id)
            move_date = move.invoice_date or move.date
            if move_date:
                indexes["date"][move_date].add(move.id)
            if move.move_type not in ("in_invoice", "in_refund"):
                continue
            partner = move.commercial_partner_id
            vat = _reference_token(partner.vat)
            name = _name_token(partner.name)
            if vat:
                indexes["partner_vat"][vat].add(move.id)
            if name:
                indexes["partner_name"][name].add(move.id)
            currency = move.currency_id or move.company_currency_id
            amount_key = (
                currency.id,
                _amount_string(currency, move.amount_total),
            )
            indexes["bill_amount"][amount_key].add(move.id)
        snapshot_digest.update(b"]")
        return indexes, snapshot_count, snapshot_digest.hexdigest()

    @api.model
    def _date_candidate_ids(self, indexes, source_date, days=7):
        result = set()
        if not source_date:
            return result
        for offset in range(-days, days + 1):
            result.update(indexes["date"].get(source_date + timedelta(days=offset), ()))
        return result

    @api.model
    def _reference_match(self, source, references):
        source_token = _reference_token(source)
        if not source_token:
            return "none"
        tokens = [_reference_token(value) for value in references if value]
        if source_token in tokens:
            return "exact"
        if len(source_token) >= 8 and any(source_token in token for token in tokens):
            return "contains"
        return "none"

    @api.model
    def _confidence(self, score, move_state):
        if score >= 75 and move_state == "posted":
            return "high"
        if score >= 50:
            return "medium"
        return "low"

    def _score_invoice_candidate(self, document, move):
        snapshot = self._move_candidate_snapshot(move)
        reasons = []
        score = 0
        reference_match = self._reference_match(
            document.invoice_number,
            self._move_references(move),
        )
        if reference_match == "exact":
            score += 45
            reasons.append(_reason("invoice_reference_exact", True, 45))
        elif reference_match == "contains":
            score += 35
            reasons.append(_reason("invoice_reference_contains", True, 35))
        seller_vat = _reference_token(document.seller_tax_id)
        partner_vat = _reference_token(move.commercial_partner_id.vat)
        partner_tax_match = bool(seller_vat and seller_vat == partner_vat)
        if partner_tax_match:
            score += 20
        reasons.append(_reason("partner_tax_id", partner_tax_match, 20))
        seller_name = _name_token(document.seller_name)
        partner_name = _name_token(move.commercial_partner_id.name)
        partner_name_match = bool(seller_name and seller_name == partner_name)
        if partner_name_match:
            score += 10
        reasons.append(_reason("partner_name", partner_name_match, 10))
        source_currency = document.currency_id
        move_currency = move.currency_id or move.company_currency_id
        currency_match = source_currency == move_currency
        if currency_match:
            score += 5
        else:
            score -= 25
        reasons.append(_reason("currency", currency_match, 5))
        total_match = False
        tax_match = False
        total_difference = 0.0
        tax_difference = 0.0
        if currency_match and document.has_total_amount:
            total_difference = move.amount_total - document.total_amount
            total_match = source_currency.is_zero(total_difference)
            if total_match:
                score += 20
            reasons.append(_reason("total_amount", total_match, 20))
        if currency_match and document.has_tax_amount:
            tax_difference = move.amount_tax - document.tax_amount
            tax_match = source_currency.is_zero(tax_difference)
            if tax_match:
                score += 10
            reasons.append(_reason("tax_amount", tax_match, 10))
        source_date = document.request_time.date() if document.request_time else False
        move_date = move.invoice_date or move.date
        date_difference = (
            abs((move_date - source_date).days)
            if move_date and source_date
            else 0
        )
        date_points = 0
        if move_date and source_date:
            if date_difference == 0:
                date_points = 5
            elif date_difference <= 7:
                date_points = 3
            elif date_difference <= 31:
                date_points = 1
        score += date_points
        reasons.append(_reason("document_date", bool(date_points), date_points))
        expected_type = {
            "yes": "in_refund",
            "no": "in_invoice",
        }.get(document.is_red)
        type_match = bool(expected_type and move.move_type == expected_type)
        if expected_type:
            if type_match:
                score += 5
            else:
                score -= 15
            reasons.append(_reason("document_type", type_match, 5))
        if move.state == "posted":
            score += 5
            reasons.append(_reason("posted", True, 5))
        else:
            score -= 10
            reasons.append(_reason("posted", False, 5))
        score = max(0, min(int(score), 100))
        return self._candidate_values(
            document,
            move,
            snapshot,
            source_scope="invoice",
            source_accounting_document=False,
            score=score,
            confidence=self._confidence(score, move.state),
            reasons=reasons,
            invoice_number_match=reference_match != "none",
            partner_match=partner_tax_match or partner_name_match,
            currency_match=currency_match,
            has_total_difference=bool(
                currency_match and document.has_total_amount
            ),
            total_difference=total_difference,
            has_tax_difference=bool(currency_match and document.has_tax_amount),
            tax_difference=tax_difference,
            date_difference=date_difference,
        )

    def _score_voucher_candidate(self, document, accounting_document, move):
        snapshot = self._move_candidate_snapshot(move)
        reasons = []
        score = 0
        reference_match = self._reference_match(
            accounting_document.voucher_number,
            self._move_references(move),
        )
        if reference_match == "exact":
            score += 50
            reasons.append(_reason("voucher_reference_exact", True, 50))
        elif reference_match == "contains":
            score += 35
            reasons.append(_reason("voucher_reference_contains", True, 35))
        source_date = accounting_document.posting_date
        move_date = move.date
        date_difference = (
            abs((move_date - source_date).days)
            if move_date and source_date
            else 0
        )
        date_points = 0
        if move_date and source_date:
            if date_difference == 0:
                date_points = 15
            elif date_difference <= 7:
                date_points = 8
            elif date_difference <= 31:
                date_points = 3
        score += date_points
        reasons.append(_reason("document_date", bool(date_points), date_points))
        currency_match = document.currency_id == move.company_currency_id
        if currency_match:
            score += 5
        else:
            score -= 20
        reasons.append(_reason("currency", currency_match, 5))
        debit_difference = 0.0
        credit_difference = 0.0
        debit_match = False
        credit_match = False
        if currency_match:
            debit_total = float(snapshot["debit_total"])
            credit_total = float(snapshot["credit_total"])
            debit_difference = debit_total - accounting_document.debit_total
            credit_difference = credit_total - accounting_document.credit_total
            debit_match = document.currency_id.is_zero(debit_difference)
            credit_match = document.currency_id.is_zero(credit_difference)
            if debit_match:
                score += 20
            if credit_match:
                score += 10
        reasons.append(_reason("debit_total", debit_match, 20))
        reasons.append(_reason("credit_total", credit_match, 10))
        summary_token = _name_token(accounting_document.summary)
        move_summary_tokens = {
            _name_token(value)
            for value in (move.ref, move.invoice_origin)
            if value
        }
        summary_match = bool(summary_token and summary_token in move_summary_tokens)
        if summary_match:
            score += 5
        reasons.append(_reason("summary", summary_match, 5))
        if move.state == "posted":
            score += 5
            reasons.append(_reason("posted", True, 5))
        else:
            score -= 10
            reasons.append(_reason("posted", False, 5))
        score = max(0, min(int(score), 100))
        return self._candidate_values(
            document,
            move,
            snapshot,
            source_scope="voucher",
            source_accounting_document=accounting_document,
            score=score,
            confidence=self._confidence(score, move.state),
            reasons=reasons,
            invoice_number_match=reference_match != "none",
            partner_match=False,
            currency_match=currency_match,
            has_total_difference=currency_match,
            total_difference=debit_difference,
            has_tax_difference=currency_match,
            tax_difference=credit_difference,
            date_difference=date_difference,
        )

    @api.model
    def _candidate_values(
        self,
        document,
        move,
        snapshot,
        *,
        source_scope,
        source_accounting_document,
        score,
        confidence,
        reasons,
        invoice_number_match,
        partner_match,
        currency_match,
        has_total_difference,
        total_difference,
        has_tax_difference,
        tax_difference,
        date_difference,
    ):
        currency = move.currency_id or move.company_currency_id
        source_key = (
            "invoice"
            if source_scope == "invoice"
            else "voucher:%s" % source_accounting_document.id
        )
        return {
            "source_key": source_key,
            "source_scope": source_scope,
            "source_accounting_document_id": (
                source_accounting_document.id
                if source_accounting_document
                else False
            ),
            "move_id": move.id,
            "origin": "engine",
            "score": score,
            "confidence": confidence,
            "reason_json": reasons,
            "reason_summary": _reason_summary(reasons),
            "invoice_number_match": invoice_number_match,
            "partner_match": partner_match,
            "currency_match": currency_match,
            "has_total_difference": has_total_difference,
            "total_difference": total_difference,
            "has_tax_difference": has_tax_difference,
            "tax_difference": tax_difference,
            "date_difference_days": date_difference,
            "move_snapshot_json": snapshot,
            "move_snapshot_checksum": _checksum(snapshot),
            "move_name_snapshot": snapshot["name"] or "/",
            "move_reference_snapshot": snapshot["ref"],
            "move_type_snapshot": snapshot["move_type"],
            "move_state_snapshot": snapshot["state"],
            "move_date_snapshot": snapshot["business_date"],
            "move_partner_name_snapshot": snapshot["partner_name"],
            "move_partner_vat_snapshot": snapshot["partner_vat"],
            "move_currency_id": currency.id,
            "move_company_currency_id": snapshot["company_currency_id"],
            "difference_currency_id": document.currency_id.id,
            "move_total_snapshot": float(snapshot["amount_total"]),
            "move_tax_snapshot": float(snapshot["amount_tax"]),
            "move_debit_snapshot": float(snapshot["debit_total"]),
            "move_credit_snapshot": float(snapshot["credit_total"]),
        }

    @api.model
    def _source_identity(self, document):
        invoice_number = _reference_token(document.invoice_number)
        seller = _reference_token(document.seller_tax_id) or _name_token(
            document.seller_name
        )
        if not invoice_number or not seller:
            return False
        return (invoice_number, seller, document.is_red or "unknown")

    def _document_gaps(self, document, duplicate_count=1):
        gaps = []
        critical = False

        def add(code, severity, message):
            nonlocal critical
            gaps.append({"code": code, "severity": severity, "message": message})
            critical = critical or severity == "error"

        if document.quality_state == "error":
            add("SOURCE_QUALITY_ERROR", "error", "规范化电子发票存在数据错误")
        if document.source_integrity_state != "verified":
            add(
                "SOURCE_INTEGRITY_NOT_VERIFIED",
                "error",
                "源电子发票数据集完整性不再有效",
            )
        if (
            document.dataset_id.declared_record_count
            != document.parse_run_id.document_count
        ):
            add(
                "SOURCE_RECORD_COUNT_MISMATCH",
                "error",
                "源数据声明记录数与当前规范化文档数不一致",
            )
        if not document.invoice_number:
            add("MISSING_INVOICE_NUMBER", "error", "缺少发票号码")
        if not document.has_total_amount:
            add("MISSING_TOTAL_AMOUNT", "error", "缺少价税合计")
        if duplicate_count > 1:
            add(
                "DUPLICATE_CURRENT_SOURCE_INVOICE",
                "error",
                "当前评估范围存在 %s 份相同销售方、发票号码和红蓝状态的记录"
                % duplicate_count,
            )
        company_vat = _reference_token(self.company_id.partner_id.vat)
        accounting_vat = _reference_token(document.accounting_entity_tax_id)
        if not company_vat:
            add("MISSING_COMPANY_TAX_ID", "warning", "Odoo 公司未维护统一社会信用代码")
        elif accounting_vat and accounting_vat != company_vat:
            add(
                "ACCOUNTING_ENTITY_MISMATCH",
                "error",
                "电子发票会计主体与当前 Odoo 公司不一致",
            )
        if document.source_authenticity_state == "official_tool_failed":
            add(
                "SOURCE_AUTHENTICITY_FAILED",
                "error",
                "源电子发票已记录受控真实性工具失败结果",
            )
        elif document.source_authenticity_state not in (
            "official_tool_passed",
            "not_applicable",
        ):
            add(
                "SOURCE_AUTHENTICITY_NOT_CONFIRMED",
                "warning",
                "源电子发票真实性尚未通过官方工具确认",
            )
        if document.source_coverage_scope != "full":
            add(
                "SOURCE_COVERAGE_NOT_FULL",
                "warning",
                "源电子发票数据集不是完整覆盖范围",
            )
        if document.source_review_control_state == "exception":
            add(
                "SOURCE_REVIEW_CONTROL_EXCEPTION",
                "warning",
                "源电子发票数据集采用单人复核例外",
            )
        return gaps, critical

    def _candidate_rows(self, document, moves_by_id, indexes):
        invoice_ids = set()
        invoice_token = _reference_token(document.invoice_number)
        if invoice_token:
            invoice_ids.update(indexes["bill_reference"].get(invoice_token, ()))
        seller_vat = _reference_token(document.seller_tax_id)
        if seller_vat:
            invoice_ids.update(indexes["partner_vat"].get(seller_vat, ()))
        seller_name = _name_token(document.seller_name)
        if seller_name:
            invoice_ids.update(indexes["partner_name"].get(seller_name, ()))
        if document.currency_id and document.has_total_amount:
            amount_key = (
                document.currency_id.id,
                _amount_string(document.currency_id, document.total_amount),
            )
            invoice_ids.update(indexes["bill_amount"].get(amount_key, ()))
        source_date = document.request_time.date() if document.request_time else False
        invoice_ids.update(self._date_candidate_ids(indexes, source_date))
        invoice_values = [
            self._score_invoice_candidate(document, moves_by_id[move_id])
            for move_id in invoice_ids
            if moves_by_id[move_id].move_type in ("in_invoice", "in_refund")
        ]
        invoice_values = sorted(
            (values for values in invoice_values if values["score"] >= 25),
            key=lambda values: (-values["score"], values["move_id"]),
        )[:20]
        result = list(invoice_values)
        for accounting_document in document.accounting_document_ids:
            voucher_ids = set()
            voucher_token = _reference_token(
                accounting_document.voucher_number
            )
            if voucher_token:
                voucher_ids.update(
                    indexes["voucher_reference"].get(voucher_token, ())
                )
            voucher_ids.update(
                self._date_candidate_ids(
                    indexes,
                    accounting_document.posting_date,
                )
            )
            values = [
                self._score_voucher_candidate(
                    document,
                    accounting_document,
                    moves_by_id[move_id],
                )
                for move_id in voucher_ids
            ]
            result.extend(
                sorted(
                    (
                        candidate
                        for candidate in values
                        if candidate["score"] >= 30
                    ),
                    key=lambda candidate: (
                        -candidate["score"],
                        candidate["move_id"],
                    ),
                )[:10]
            )
        return result

    @api.model
    def _initial_case_state(self, candidate_values, critical_gap):
        if critical_gap:
            return "data_gap"
        if not candidate_values:
            return "unmatched"
        high_count = sum(
            values["confidence"] == "high" for values in candidate_values
        )
        return "suggested" if high_count == 1 else "ambiguous"

    def _build_results(self):
        self.ensure_one()
        documents = self._source_documents()
        moves = (
            self._ledger_moves()
            if documents
            else self.env["account.move"].browse()
        )
        indexes, ledger_move_count, ledger_checksum = self._build_move_indexes(
            moves
        )
        moves_by_id = {move.id: move for move in moves}
        source_checksum = _checksum(
            [
                {
                    "document_id": document.id,
                    "document_checksum": document.document_checksum,
                    "parse_run_checksum": document.parse_run_id.output_checksum,
                }
                for document in documents
            ]
        )
        source_identity_counts = Counter(
            identity
            for document in documents
            if (identity := self._source_identity(document))
        )
        result_rows = []
        cases = self.env["sudo.cn.einvoice.reconciliation.case"]
        for document in documents:
            source_identity = self._source_identity(document)
            gaps, critical_gap = self._document_gaps(
                document,
                duplicate_count=source_identity_counts.get(source_identity, 1),
            )
            candidate_values = (
                []
                if critical_gap
                else self._candidate_rows(document, moves_by_id, indexes)
            )
            initial_state = self._initial_case_state(
                candidate_values,
                critical_gap,
            )
            case = cases.with_context(
                cn_reconciliation_transition=(
                    _RECONCILIATION_TRANSITION_MARKER
                )
            ).create(
                {
                    "run_id": self.id,
                    "einvoice_document_id": document.id,
                    "initial_state": initial_state,
                    "state": initial_state,
                    "data_gap_json": gaps,
                    "data_gap_summary": "；".join(
                        gap["message"] for gap in gaps
                    ),
                    "candidate_ids": [
                        Command.create(values) for values in candidate_values
                    ],
                }
            )
            cases |= case
            result_rows.append(
                {
                    "document_checksum": document.document_checksum,
                    "initial_state": initial_state,
                    "gaps": gaps,
                    "candidates": [
                        {
                            "source_key": values["source_key"],
                            "move_id": values["move_id"],
                            "score": values["score"],
                            "confidence": values["confidence"],
                            "move_snapshot_checksum": values[
                                "move_snapshot_checksum"
                            ],
                        }
                        for values in candidate_values
                    ],
                }
            )
        counts = {
            "source_document_count": len(documents),
            "ledger_move_count": ledger_move_count,
            "case_count": len(cases),
            "matched_case_count": 0,
            "suggested_case_count": len(
                cases.filtered(lambda case: case.state == "suggested")
            ),
            "ambiguous_case_count": len(
                cases.filtered(lambda case: case.state == "ambiguous")
            ),
            "unmatched_case_count": len(
                cases.filtered(lambda case: case.state == "unmatched")
            ),
            "data_gap_case_count": len(
                cases.filtered(lambda case: case.state == "data_gap")
            ),
            "warning_case_count": len(
                cases.filtered(lambda case: case.warning_issue_count > 0)
            ),
            "source_snapshot_checksum": source_checksum,
            "ledger_snapshot_checksum": ledger_checksum,
            "result_checksum": _checksum(result_rows),
        }
        counts["source_availability_state"] = (
            "no_data"
            if not documents
            else "blocked"
            if counts["data_gap_case_count"]
            else "available"
        )
        return counts

    def _mark_failed(self, code, summary):
        self.ensure_one()
        safe_code = _safe_text(code, 128) or "RECONCILIATION_FAILED"
        safe_summary = _safe_text(summary, 2000) or "账票勾稽失败。"
        self.with_context(
            cn_reconciliation_transition=_RECONCILIATION_TRANSITION_MARKER
        ).write(
            {
                "state": "failed",
                "finished_at": fields.Datetime.now(),
                "error_code": safe_code,
                "result_summary": safe_summary,
            }
        )
        self.env["sudo.compliance.audit.event"]._log_records(
            self,
            "cn_einvoice_reconciliation.failed",
            previous_state="processing",
            new_state="failed",
            details={"error_code": safe_code},
        )
        return False

    def _process(self):
        self.ensure_one()
        if self.state != "queued":
            raise UserError(_("只有待处理的账票勾稽批次可以执行。"))
        self.with_context(
            cn_reconciliation_transition=_RECONCILIATION_TRANSITION_MARKER
        ).write({"state": "processing", "started_at": fields.Datetime.now()})
        self.env["sudo.compliance.audit.event"]._log_records(
            self,
            "cn_einvoice_reconciliation.processing",
            previous_state="queued",
            new_state="processing",
        )
        try:
            with self.env.cr.savepoint():
                counts = self.with_context(
                    lang=_RECONCILIATION_SNAPSHOT_LANG
                )._build_results()
        except (UserError, ValidationError) as exc:
            return self._mark_failed("RECONCILIATION_INPUT_ERROR", exc)
        except Exception as exc:
            return self._mark_failed(
                "UNEXPECTED_RECONCILIATION_FAILURE",
                "账票勾稽发生未预期错误：%s" % type(exc).__name__,
            )
        previous_runs = self.search(
            [
                ("profile_id", "=", self.profile_id.id),
                ("period_start", "=", self.period_start),
                ("period_end", "=", self.period_end),
                ("state", "=", "succeeded"),
                ("id", "!=", self.id),
            ]
        )
        previous_runs.with_context(
            cn_reconciliation_transition=_RECONCILIATION_TRANSITION_MARKER
        ).write({"state": "superseded"})
        if counts["source_availability_state"] == "no_data":
            summary = _(
                "技术任务已完成，但期间内没有当前有效的规范化电子发票，"
                "不能形成账票匹配或未匹配结论。"
            )
        else:
            summary = _(
                "完成 %(cases)s 项账票勾稽：单一建议 %(suggested)s，"
                "多候选 %(ambiguous)s，未匹配 %(unmatched)s，"
                "数据缺口 %(gaps)s，含警告事项 %(warnings)s。",
                cases=counts["case_count"],
                suggested=counts["suggested_case_count"],
                ambiguous=counts["ambiguous_case_count"],
                unmatched=counts["unmatched_case_count"],
                gaps=counts["data_gap_case_count"],
                warnings=counts["warning_case_count"],
            )
        self.with_context(
            cn_reconciliation_transition=_RECONCILIATION_TRANSITION_MARKER
        ).write(
            {
                **counts,
                "state": "succeeded",
                "finished_at": fields.Datetime.now(),
                "result_summary": summary,
                "error_code": False,
            }
        )
        for previous in previous_runs:
            self.env["sudo.compliance.audit.event"]._log_records(
                previous,
                "cn_einvoice_reconciliation.superseded",
                previous_state="succeeded",
                new_state="superseded",
                details={"replacement_run_id": self.id},
            )
        self.env["sudo.compliance.audit.event"]._log_records(
            self,
            "cn_einvoice_reconciliation.succeeded",
            previous_state="processing",
            new_state="succeeded",
            details={**counts, "engine_version": self.engine_version},
        )
        return True

    @api.model
    def _cron_process_runs(self, limit=1):
        processed = 0
        for _index in range(max(int(limit or 1), 1)):
            self.env.cr.execute(
                """
                    SELECT id
                      FROM sudo_cn_einvoice_reconciliation_run
                     WHERE state = 'queued'
                     ORDER BY requested_at, id
                     FOR UPDATE SKIP LOCKED
                     LIMIT 1
                """
            )
            row = self.env.cr.fetchone()
            if not row:
                break
            self.browse(row[0])._process()
            processed += 1
        return processed

    def action_cancel(self):
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以取消账票勾稽批次。"))
        for run in self:
            if run.state != "queued":
                raise UserError(_("只有待处理的账票勾稽批次可以取消。"))
            run.with_context(
                cn_reconciliation_transition=_RECONCILIATION_TRANSITION_MARKER
            ).write(
                {
                    "state": "cancelled",
                    "finished_at": fields.Datetime.now(),
                    "result_summary": "批次在执行前取消。",
                }
            )
            self.env["sudo.compliance.audit.event"]._log_records(
                run,
                "cn_einvoice_reconciliation.cancelled",
                previous_state="queued",
                new_state="cancelled",
            )
        return True

    def action_view_cases(self):
        self.ensure_one()
        action = self.env.ref(
            "sudo_country_pack_cn.action_cn_einvoice_reconciliation_cases"
        ).read()[0]
        action["domain"] = [("run_id", "=", self.id)]
        action["context"] = {}
        return action

    def _refresh_decision_counts(self):
        for run in self.filtered(lambda item: item.state == "succeeded"):
            cases = run.case_ids
            values = {
                "matched_case_count": len(
                    cases.filtered(
                        lambda case: case.state in ("matched", "partial")
                    )
                ),
                "suggested_case_count": len(
                    cases.filtered(lambda case: case.state == "suggested")
                ),
                "ambiguous_case_count": len(
                    cases.filtered(lambda case: case.state == "ambiguous")
                ),
                "unmatched_case_count": len(
                    cases.filtered(
                        lambda case: case.state
                        in ("unmatched", "reviewed_unmatched")
                    )
                ),
                "data_gap_case_count": len(
                    cases.filtered(lambda case: case.state == "data_gap")
                ),
            }
            run.with_context(
                cn_reconciliation_transition=_RECONCILIATION_TRANSITION_MARKER
            ).write(values)
        return True


class SudoChinaEinvoiceReconciliationCase(models.Model):
    _name = "sudo.cn.einvoice.reconciliation.case"
    _description = "China Electronic Invoice Reconciliation Case"
    _order = "state, invoice_number, id"
    _check_company_auto = True

    name = fields.Char(compute="_compute_name", store=True)
    run_id = fields.Many2one(
        "sudo.cn.einvoice.reconciliation.run",
        string="勾稽批次",
        required=True,
        ondelete="restrict",
        check_company=True,
        readonly=True,
        index=True,
    )
    profile_id = fields.Many2one(
        related="run_id.profile_id",
        store=True,
        index=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        related="run_id.company_id",
        store=True,
        index=True,
        readonly=True,
    )
    einvoice_document_id = fields.Many2one(
        "sudo.cn.einvoice.document",
        string="电子发票",
        required=True,
        ondelete="restrict",
        check_company=True,
        readonly=True,
        index=True,
    )
    invoice_number = fields.Char(
        related="einvoice_document_id.invoice_number",
        store=True,
        readonly=True,
        index=True,
    )
    seller_name = fields.Char(
        related="einvoice_document_id.seller_name",
        store=True,
        readonly=True,
    )
    seller_tax_id = fields.Char(
        related="einvoice_document_id.seller_tax_id",
        store=True,
        readonly=True,
    )
    request_time = fields.Datetime(
        related="einvoice_document_id.request_time",
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        related="einvoice_document_id.currency_id",
        store=True,
        readonly=True,
    )
    total_amount = fields.Monetary(
        related="einvoice_document_id.total_amount",
        currency_field="currency_id",
        store=True,
        readonly=True,
    )
    tax_amount = fields.Monetary(
        related="einvoice_document_id.tax_amount",
        currency_field="currency_id",
        store=True,
        readonly=True,
    )
    source_quality_state = fields.Selection(
        related="einvoice_document_id.quality_state",
        store=True,
        readonly=True,
    )
    initial_state = fields.Selection(
        [
            ("data_gap", "数据缺口"),
            ("unmatched", "未找到候选"),
            ("suggested", "单一高可信建议"),
            ("ambiguous", "需要人工判断"),
        ],
        string="初始结论",
        required=True,
        readonly=True,
    )
    state = fields.Selection(
        [
            ("data_gap", "数据缺口"),
            ("unmatched", "未找到候选"),
            ("suggested", "待确认建议"),
            ("ambiguous", "多候选待判断"),
            ("partial", "部分匹配"),
            ("matched", "已匹配"),
            ("reviewed_unmatched", "已复核未匹配"),
        ],
        string="当前状态",
        required=True,
        readonly=True,
        index=True,
    )
    match_mode = fields.Selection(
        [
            ("none", "未确认"),
            ("bill", "发票级账单匹配"),
            ("voucher", "凭证级匹配"),
        ],
        string="确认方式",
        required=True,
        default="none",
        readonly=True,
    )
    data_gap_json = fields.Json(string="数据缺口明细", readonly=True)
    data_gap_summary = fields.Text(string="数据缺口摘要", readonly=True)
    blocking_issue_count = fields.Integer(
        string="阻断项",
        compute="_compute_gap_metrics",
    )
    warning_issue_count = fields.Integer(
        string="数据警告",
        compute="_compute_gap_metrics",
    )
    candidate_ids = fields.One2many(
        "sudo.cn.einvoice.reconciliation.candidate",
        "case_id",
        string="匹配候选",
        readonly=True,
    )
    candidate_count = fields.Integer(
        string="候选数",
        compute="_compute_decision_metrics",
    )
    high_confidence_count = fields.Integer(
        string="高可信候选",
        compute="_compute_decision_metrics",
    )
    confirmed_candidate_count = fields.Integer(
        string="已确认候选",
        compute="_compute_decision_metrics",
    )
    confirmed_move_ids = fields.Many2many(
        "account.move",
        string="已确认 Odoo 凭证",
        compute="_compute_decision_metrics",
    )
    reviewed_at = fields.Datetime(string="最近复核时间", readonly=True)
    reviewed_by_id = fields.Many2one(
        "res.users",
        string="最近复核人",
        readonly=True,
    )
    decision_integrity_state = fields.Selection(
        [
            ("not_matched", "尚未确认"),
            ("verified", "确认依据未变化"),
            ("mismatch", "确认后账簿已变化"),
        ],
        string="确认依据完整性",
        compute="_compute_decision_metrics",
    )
    is_current_run = fields.Boolean(
        string="当前勾稽结果",
        compute="_compute_is_current_run",
        search="_search_is_current_run",
    )
    can_manual_match = fields.Boolean(
        string="可以人工指定",
        compute="_compute_can_manual_match",
    )

    _document_per_run = models.Constraint(
        "unique(run_id, einvoice_document_id)",
        "同一批次中的电子发票必须唯一。",
    )

    @api.depends("invoice_number", "seller_name")
    def _compute_name(self):
        for case in self:
            case.name = "%s / %s" % (
                case.invoice_number or _("未编号电子发票"),
                case.seller_name or _("未提供销售方"),
            )

    @api.depends("data_gap_json")
    def _compute_gap_metrics(self):
        for case in self:
            gaps = case.data_gap_json or []
            case.blocking_issue_count = sum(
                gap.get("severity") == "error" for gap in gaps
            )
            case.warning_issue_count = sum(
                gap.get("severity") == "warning" for gap in gaps
            )

    @api.depends(
        "candidate_ids.state",
        "candidate_ids.confidence",
        "candidate_ids.integrity_state",
    )
    def _compute_decision_metrics(self):
        for case in self:
            confirmed = case.candidate_ids.filtered(
                lambda candidate: candidate.state == "confirmed"
            )
            case.candidate_count = len(case.candidate_ids)
            case.high_confidence_count = len(
                case.candidate_ids.filtered(
                    lambda candidate: candidate.confidence == "high"
                )
            )
            case.confirmed_candidate_count = len(confirmed)
            case.confirmed_move_ids = confirmed.mapped("move_id")
            if not confirmed:
                case.decision_integrity_state = "not_matched"
            elif any(
                candidate.integrity_state == "mismatch"
                for candidate in confirmed
            ):
                case.decision_integrity_state = "mismatch"
            else:
                case.decision_integrity_state = "verified"

    @api.depends("run_id.state")
    def _compute_is_current_run(self):
        for case in self:
            case.is_current_run = case.run_id.state == "succeeded"

    @api.model
    def _search_is_current_run(self, operator, value):
        if operator not in ("=", "!="):
            raise UserError(_("当前勾稽结果仅支持等于或不等于筛选。"))
        positive = (operator == "=" and bool(value)) or (
            operator == "!=" and not bool(value)
        )
        return [("run_id.state", "=" if positive else "!=", "succeeded")]

    @api.depends("run_id.state")
    @api.depends_context("uid")
    def _compute_can_manual_match(self):
        allowed = self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ) and self.env.user.has_group("account.group_account_user")
        for case in self:
            case.can_manual_match = allowed and case.run_id.state == "succeeded"

    @api.model_create_multi
    def create(self, vals_list):
        if (
            self.env.context.get("cn_reconciliation_transition")
            is not _RECONCILIATION_TRANSITION_MARKER
        ):
            raise AccessError(_("账票勾稽事项只能由受控流程创建。"))
        for values in vals_list:
            values.setdefault("match_mode", "none")
            values.setdefault("reviewed_at", False)
            values.setdefault("reviewed_by_id", False)
        return super().create(vals_list)

    def write(self, values):
        if (
            self.env.context.get("cn_reconciliation_transition")
            is not _RECONCILIATION_TRANSITION_MARKER
        ):
            raise AccessError(_("账票勾稽事项只能由受控决策更新。"))
        return super().write(values)

    def unlink(self):
        raise AccessError(_("账票勾稽事项属于审计记录，不可删除。"))

    def _refresh_decision_state(self):
        for case in self:
            confirmed = case.candidate_ids.filtered(
                lambda candidate: candidate.state == "confirmed"
            )
            if confirmed.filtered(lambda candidate: candidate.source_scope == "invoice"):
                state = "matched"
                mode = "bill"
            elif confirmed:
                expected = len(
                    case.einvoice_document_id.accounting_document_ids
                )
                confirmed_sources = set(
                    confirmed.mapped("source_accounting_document_id").ids
                )
                state = (
                    "matched"
                    if expected and len(confirmed_sources) >= expected
                    else "partial"
                )
                mode = "voucher"
            elif case.candidate_ids and all(
                candidate.state == "rejected"
                for candidate in case.candidate_ids
            ):
                state = "reviewed_unmatched"
                mode = "none"
            else:
                state = case.initial_state
                mode = "none"
            case.with_context(
                cn_reconciliation_transition=_RECONCILIATION_TRANSITION_MARKER
            ).write(
                {
                    "state": state,
                    "match_mode": mode,
                    "reviewed_at": fields.Datetime.now(),
                    "reviewed_by_id": self.env.user.id,
                }
            )
        self.mapped("run_id")._refresh_decision_counts()
        return True

    def action_open_manual_match(self):
        self.ensure_one()
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ) or not self.env.user.has_group("account.group_account_user"):
            raise AccessError(_("人工指定需要合规管理员和会计权限。"))
        if self.run_id.state != "succeeded":
            raise UserError(_("只能处理当前成功批次中的勾稽事项。"))
        return {
            "type": "ir.actions.act_window",
            "name": _("人工指定 Odoo 凭证"),
            "res_model": "sudo.cn.einvoice.manual.match.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_case_id": self.id},
        }

    def _create_manual_candidate(
        self,
        source_scope,
        source_accounting_document,
        move,
        note,
    ):
        self.ensure_one()
        move.ensure_one()
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ) or not self.env.user.has_group("account.group_account_user"):
            raise AccessError(_("人工指定需要合规管理员和会计权限。"))
        note = _safe_text(note, 1000)
        if len(note or "") < 10:
            raise ValidationError(_("人工匹配说明不得少于 10 个字符。"))
        if source_scope not in ("invoice", "voucher"):
            raise ValidationError(_("请选择有效的账票匹配层级。"))
        if move.company_id != self.company_id:
            raise UserError(_("人工指定凭证必须属于勾稽事项所在公司。"))
        if move.state != "posted":
            raise UserError(_("只能人工确认已过账的 Odoo 凭证。"))
        if source_scope == "voucher":
            if (
                not source_accounting_document
                or source_accounting_document.einvoice_document_id
                != self.einvoice_document_id
            ):
                raise UserError(_("请选择当前电子发票中的源会计凭证。"))
            values = self.run_id._score_voucher_candidate(
                self.einvoice_document_id,
                source_accounting_document,
                move.sudo(),
            )
        else:
            if move.move_type not in ("in_invoice", "in_refund"):
                raise UserError(_("发票级匹配只能选择供应商账单或贷项通知单。"))
            source_accounting_document = False
            values = self.run_id._score_invoice_candidate(
                self.einvoice_document_id,
                move.sudo(),
            )
        existing = self.candidate_ids.filtered(
            lambda candidate: candidate.source_key == values["source_key"]
            and candidate.move_id == move
        )[:1]
        if existing:
            if existing.integrity_state != "verified":
                raise UserError(_("已有候选的账簿快照已变化，请重新运行勾稽。"))
            if existing.state != "proposed":
                existing._reset_decision()
            existing._confirm(note)
            return existing
        values.update(
            {
                "case_id": self.id,
                "origin": "manual",
                "score": 0,
                "confidence": "manual",
                "reason_json": [_reason("manual", True, 0)],
                "reason_summary": "人工指定：%s" % note,
            }
        )
        candidate = self.env[
            "sudo.cn.einvoice.reconciliation.candidate"
        ].with_context(
            cn_reconciliation_transition=_RECONCILIATION_TRANSITION_MARKER
        ).create(values)
        self.env["sudo.compliance.audit.event"]._log_records(
            candidate,
            "cn_einvoice_reconciliation.manual_candidate",
            new_state="proposed",
            details={
                "case_id": self.id,
                "source_scope": source_scope,
                "move_id": move.id,
                "note": note,
            },
        )
        candidate._confirm(note)
        return candidate


class SudoChinaEinvoiceReconciliationCandidate(models.Model):
    _name = "sudo.cn.einvoice.reconciliation.candidate"
    _description = "China Electronic Invoice Match Candidate"
    _order = "source_scope, source_key, score desc, id"
    _check_company_auto = True

    case_id = fields.Many2one(
        "sudo.cn.einvoice.reconciliation.case",
        string="勾稽事项",
        required=True,
        ondelete="restrict",
        check_company=True,
        readonly=True,
        index=True,
    )
    run_id = fields.Many2one(
        related="case_id.run_id",
        store=True,
        index=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        related="case_id.company_id",
        store=True,
        index=True,
        readonly=True,
    )
    einvoice_document_id = fields.Many2one(
        related="case_id.einvoice_document_id",
        store=True,
        readonly=True,
    )
    source_key = fields.Char(string="源匹配键", required=True, readonly=True)
    source_scope = fields.Selection(
        [("invoice", "发票级"), ("voucher", "凭证级")],
        string="匹配层级",
        required=True,
        readonly=True,
        index=True,
    )
    source_accounting_document_id = fields.Many2one(
        "sudo.cn.einvoice.accounting.document",
        string="源会计凭证",
        ondelete="restrict",
        check_company=True,
        readonly=True,
    )
    move_id = fields.Many2one(
        "account.move",
        string="Odoo 会计凭证",
        required=True,
        ondelete="restrict",
        check_company=True,
        readonly=True,
        index=True,
    )
    origin = fields.Selection(
        [("engine", "引擎建议"), ("manual", "人工指定")],
        string="候选来源",
        required=True,
        readonly=True,
    )
    score = fields.Integer(string="匹配分", readonly=True)
    confidence = fields.Selection(
        [
            ("high", "高"),
            ("medium", "中"),
            ("low", "低"),
            ("manual", "人工"),
        ],
        string="可信度",
        required=True,
        readonly=True,
        index=True,
    )
    reason_json = fields.Json(string="评分依据", readonly=True)
    reason_summary = fields.Text(string="评分摘要", readonly=True)
    invoice_number_match = fields.Boolean(string="编号匹配", readonly=True)
    partner_match = fields.Boolean(string="往来方匹配", readonly=True)
    currency_match = fields.Boolean(string="币种匹配", readonly=True)
    has_total_difference = fields.Boolean(string="可比总额", readonly=True)
    difference_currency_id = fields.Many2one(
        "res.currency",
        string="差异币种",
        readonly=True,
    )
    total_difference = fields.Monetary(
        string="总额或借方差异",
        currency_field="difference_currency_id",
        readonly=True,
    )
    has_tax_difference = fields.Boolean(string="可比税额", readonly=True)
    tax_difference = fields.Monetary(
        string="税额或贷方差异",
        currency_field="difference_currency_id",
        readonly=True,
    )
    date_difference_days = fields.Integer(string="日期差天数", readonly=True)
    move_snapshot_json = fields.Json(string="Odoo 凭证快照", readonly=True)
    move_snapshot_checksum = fields.Char(
        string="Odoo 凭证快照 SHA-256",
        required=True,
        readonly=True,
    )
    move_name_snapshot = fields.Char(string="凭证编号", readonly=True)
    move_reference_snapshot = fields.Char(string="参考号", readonly=True)
    move_type_snapshot = fields.Selection(
        [
            ("entry", "日记账分录"),
            ("in_invoice", "供应商账单"),
            ("in_refund", "供应商贷项通知单"),
        ],
        string="凭证类型",
        readonly=True,
    )
    move_state_snapshot = fields.Selection(
        [("draft", "草稿"), ("posted", "已过账")],
        string="扫描时状态",
        readonly=True,
    )
    move_date_snapshot = fields.Date(string="凭证日期", readonly=True)
    move_partner_name_snapshot = fields.Char(string="往来方", readonly=True)
    move_partner_vat_snapshot = fields.Char(
        string="往来方识别号",
        readonly=True,
    )
    move_currency_id = fields.Many2one(
        "res.currency",
        string="凭证币种",
        readonly=True,
    )
    move_company_currency_id = fields.Many2one(
        "res.currency",
        string="凭证本位币",
        readonly=True,
    )
    move_total_snapshot = fields.Monetary(
        string="凭证价税合计",
        currency_field="move_currency_id",
        readonly=True,
    )
    move_tax_snapshot = fields.Monetary(
        string="凭证税额",
        currency_field="move_currency_id",
        readonly=True,
    )
    move_debit_snapshot = fields.Monetary(
        string="凭证借方合计",
        currency_field="move_company_currency_id",
        readonly=True,
    )
    move_credit_snapshot = fields.Monetary(
        string="凭证贷方合计",
        currency_field="move_company_currency_id",
        readonly=True,
    )
    state = fields.Selection(
        [
            ("proposed", "待判断"),
            ("confirmed", "已确认"),
            ("rejected", "已拒绝"),
        ],
        string="决策",
        required=True,
        default="proposed",
        readonly=True,
        index=True,
    )
    reviewed_at = fields.Datetime(string="决策时间", readonly=True)
    reviewed_by_id = fields.Many2one(
        "res.users",
        string="决策人",
        readonly=True,
    )
    review_note = fields.Text(string="决策说明", readonly=True)
    integrity_state = fields.Selection(
        [("verified", "快照未变化"), ("mismatch", "账簿已变化")],
        string="快照完整性",
        compute="_compute_integrity_state",
    )
    can_confirm = fields.Boolean(
        string="可以确认",
        compute="_compute_integrity_state",
    )

    _candidate_unique = models.Constraint(
        "unique(case_id, source_key, move_id)",
        "同一勾稽事项、源匹配键和 Odoo 凭证只能有一个候选。",
    )

    @api.model_create_multi
    def create(self, vals_list):
        if (
            self.env.context.get("cn_reconciliation_transition")
            is not _RECONCILIATION_TRANSITION_MARKER
        ):
            raise AccessError(_("账票匹配候选只能由受控流程创建。"))
        for values in vals_list:
            values.update(
                {
                    "state": "proposed",
                    "reviewed_at": False,
                    "reviewed_by_id": False,
                    "review_note": False,
                }
            )
        return super().create(vals_list)

    def write(self, values):
        if (
            self.env.context.get("cn_reconciliation_transition")
            is not _RECONCILIATION_TRANSITION_MARKER
        ):
            raise AccessError(_("账票匹配候选只能由受控决策更新。"))
        return super().write(values)

    def unlink(self):
        raise AccessError(_("账票匹配候选属于审计记录，不可删除。"))

    @api.depends(
        "state",
        "move_id.write_date",
        "move_id.state",
        "move_id.line_ids.write_date",
        "move_id.line_ids.debit",
        "move_id.line_ids.credit",
    )
    def _compute_integrity_state(self):
        run_model = self.env["sudo.cn.einvoice.reconciliation.run"]
        for candidate in self:
            snapshot = run_model._move_candidate_snapshot(
                candidate.move_id.sudo()
            )
            integrity_state = (
                "verified"
                if _checksum(snapshot) == candidate.move_snapshot_checksum
                else "mismatch"
            )
            candidate.integrity_state = integrity_state
            candidate.can_confirm = (
                candidate.state == "proposed"
                and candidate.move_id.sudo().state == "posted"
                and integrity_state == "verified"
            )

    def _ensure_manager(self):
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以确认账票匹配。"))

    def _confirm(self, note=False):
        self.ensure_one()
        self._ensure_manager()
        case = self.case_id
        if case.run_id.state != "succeeded":
            raise UserError(_("只能确认当前成功勾稽批次中的候选。"))
        if self.state != "proposed":
            raise UserError(_("只有待判断候选可以确认。"))
        if self.integrity_state != "verified":
            raise UserError(_("Odoo 凭证在扫描后已变化，请重新运行勾稽。"))
        if self.move_id.sudo().state != "posted":
            raise UserError(_("只能确认已过账的 Odoo 凭证。"))
        if self.source_scope == "invoice" and self.move_id.sudo().move_type not in (
            "in_invoice",
            "in_refund",
        ):
            raise UserError(_("发票级匹配只能确认供应商账单或贷项通知单。"))
        if self.source_scope == "voucher" and (
            not self.source_accounting_document_id
            or self.source_accounting_document_id.einvoice_document_id
            != case.einvoice_document_id
        ):
            raise UserError(_("凭证级匹配必须关联当前电子发票中的源会计凭证。"))
        confirmed = case.candidate_ids.filtered(
            lambda candidate: candidate.state == "confirmed"
        )
        if self.source_scope == "invoice":
            if confirmed:
                raise UserError(_("发票级匹配只能确认一个 Odoo 供应商账单。"))
        else:
            if confirmed.filtered(
                lambda candidate: candidate.source_scope == "invoice"
            ):
                raise UserError(_("发票级匹配与凭证级匹配不能同时确认。"))
            if confirmed.filtered(
                lambda candidate: candidate.source_accounting_document_id
                == self.source_accounting_document_id
            ):
                raise UserError(_("同一源会计凭证只能确认一个 Odoo 凭证。"))
        self.with_context(
            cn_reconciliation_transition=_RECONCILIATION_TRANSITION_MARKER
        ).write(
            {
                "state": "confirmed",
                "reviewed_at": fields.Datetime.now(),
                "reviewed_by_id": self.env.user.id,
                "review_note": _safe_text(note, 1000),
            }
        )
        case._refresh_decision_state()
        self.env["sudo.compliance.audit.event"]._log_records(
            self,
            "cn_einvoice_reconciliation.confirmed",
            previous_state="proposed",
            new_state="confirmed",
            details={
                "case_id": case.id,
                "move_id": self.move_id.id,
                "source_scope": self.source_scope,
                "move_snapshot_checksum": self.move_snapshot_checksum,
                "note": _safe_text(note, 1000),
            },
        )
        return True

    def action_confirm(self):
        return self._confirm()

    def action_reject(self):
        for candidate in self:
            candidate._ensure_manager()
            if candidate.case_id.run_id.state != "succeeded":
                raise UserError(_("只能处理当前成功批次中的候选。"))
            if candidate.state != "proposed":
                raise UserError(_("只有待判断候选可以拒绝。"))
            candidate.with_context(
                cn_reconciliation_transition=_RECONCILIATION_TRANSITION_MARKER
            ).write(
                {
                    "state": "rejected",
                    "reviewed_at": fields.Datetime.now(),
                    "reviewed_by_id": self.env.user.id,
                    "review_note": "合规管理员拒绝该候选。",
                }
            )
            candidate.case_id._refresh_decision_state()
            self.env["sudo.compliance.audit.event"]._log_records(
                candidate,
                "cn_einvoice_reconciliation.rejected",
                previous_state="proposed",
                new_state="rejected",
                details={"move_id": candidate.move_id.id},
            )
        return True

    def _reset_decision(self):
        self.ensure_one()
        self._ensure_manager()
        if self.case_id.run_id.state != "succeeded":
            raise UserError(_("只能处理当前成功批次中的候选。"))
        previous_state = self.state
        if previous_state == "proposed":
            return True
        self.with_context(
            cn_reconciliation_transition=_RECONCILIATION_TRANSITION_MARKER
        ).write(
            {
                "state": "proposed",
                "reviewed_at": False,
                "reviewed_by_id": False,
                "review_note": False,
            }
        )
        self.case_id._refresh_decision_state()
        self.env["sudo.compliance.audit.event"]._log_records(
            self,
            "cn_einvoice_reconciliation.reset",
            previous_state=previous_state,
            new_state="proposed",
            details={"move_id": self.move_id.id},
        )
        return True

    def action_reset_decision(self):
        for candidate in self:
            candidate._reset_decision()
        return True

    def action_open_move(self):
        self.ensure_one()
        if not self.env.user.has_group("account.group_account_readonly"):
            raise AccessError(_("只有具备会计权限的用户可以打开 Odoo 凭证。"))
        return {
            "type": "ir.actions.act_window",
            "name": _("Odoo 会计凭证"),
            "res_model": "account.move",
            "res_id": self.move_id.id,
            "view_mode": "form",
            "target": "current",
        }


class SudoChinaEinvoiceReconciliationWizard(models.TransientModel):
    _name = "sudo.cn.einvoice.reconciliation.wizard"
    _description = "Submit China Electronic Invoice Reconciliation"
    _check_company_auto = True

    profile_id = fields.Many2one(
        "sudo.compliance.profile",
        string="合规档案",
        required=True,
        check_company=True,
        domain="[('country_id.code', '=', 'CN'), ('active', '=', True)]",
    )
    company_id = fields.Many2one(
        related="profile_id.company_id",
        readonly=True,
    )
    period_start = fields.Date(string="期间开始", required=True)
    period_end = fields.Date(string="期间结束", required=True)

    @api.model
    def default_get(self, field_names):
        values = super().default_get(field_names)
        today = fields.Date.context_today(self)
        start = today.replace(day=1)
        next_month = (start + timedelta(days=32)).replace(day=1)
        values.setdefault("period_start", start)
        values.setdefault("period_end", next_month - timedelta(days=1))
        if "profile_id" in field_names and not values.get("profile_id"):
            country = self.env.ref("base.cn")
            profile = self.env["sudo.compliance.profile"].search(
                [
                    ("company_id", "=", self.env.company.id),
                    ("country_id", "=", country.id),
                    ("active", "=", True),
                ],
                limit=1,
            )
            values["profile_id"] = profile.id
        return values

    def action_queue(self):
        self.ensure_one()
        run = self.env["sudo.cn.einvoice.reconciliation.run"].with_company(
            self.company_id
        ).enqueue(
            self.profile_id,
            self.period_start,
            self.period_end,
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("账票勾稽批次"),
            "res_model": "sudo.cn.einvoice.reconciliation.run",
            "res_id": run.id,
            "view_mode": "form",
            "target": "current",
        }


class SudoChinaEinvoiceManualMatchWizard(models.TransientModel):
    _name = "sudo.cn.einvoice.manual.match.wizard"
    _description = "Manually Match China Electronic Invoice"
    _check_company_auto = True

    case_id = fields.Many2one(
        "sudo.cn.einvoice.reconciliation.case",
        string="勾稽事项",
        required=True,
        check_company=True,
    )
    company_id = fields.Many2one(
        related="case_id.company_id",
        readonly=True,
    )
    available_accounting_document_ids = fields.One2many(
        related="case_id.einvoice_document_id.accounting_document_ids",
        string="可选源会计凭证",
        readonly=True,
    )
    source_scope = fields.Selection(
        [("invoice", "发票级账单匹配"), ("voucher", "凭证级匹配")],
        string="匹配层级",
        required=True,
        default="invoice",
    )
    source_accounting_document_id = fields.Many2one(
        "sudo.cn.einvoice.accounting.document",
        string="源会计凭证",
    )
    move_id = fields.Many2one(
        "account.move",
        string="Odoo 会计凭证",
        required=True,
        check_company=True,
        domain="[('company_id', '=', company_id), ('state', '=', 'posted'), "
        "('move_type', 'in', ('entry', 'in_invoice', 'in_refund'))]",
    )
    note = fields.Text(string="人工匹配说明", required=True)

    @api.onchange("source_scope")
    def _onchange_source_scope(self):
        if self.source_scope == "invoice":
            self.source_accounting_document_id = False

    def action_apply(self):
        self.ensure_one()
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ) or not self.env.user.has_group("account.group_account_user"):
            raise AccessError(_("人工指定需要合规管理员和会计权限。"))
        note = _safe_text(self.note, 1000)
        if len(note or "") < 10:
            raise ValidationError(_("人工匹配说明不得少于 10 个字符。"))
        if self.source_scope == "voucher":
            if self.source_accounting_document_id not in (
                self.available_accounting_document_ids
            ):
                raise ValidationError(_("请选择当前电子发票中的源会计凭证。"))
        self.case_id._create_manual_candidate(
            self.source_scope,
            self.source_accounting_document_id,
            self.move_id,
            note,
        )
        return {"type": "ir.actions.act_window_close"}


class SudoChinaEinvoiceDocument(models.Model):
    _inherit = "sudo.cn.einvoice.document"

    reconciliation_case_ids = fields.One2many(
        "sudo.cn.einvoice.reconciliation.case",
        "einvoice_document_id",
        string="账票勾稽事项",
        readonly=True,
    )
    reconciliation_case_count = fields.Integer(
        string="账票勾稽次数",
        compute="_compute_reconciliation_case_count",
    )

    @api.depends("reconciliation_case_ids")
    def _compute_reconciliation_case_count(self):
        for document in self:
            document.reconciliation_case_count = len(
                document.reconciliation_case_ids
            )

    def action_view_reconciliation_cases(self):
        self.ensure_one()
        action = self.env.ref(
            "sudo_country_pack_cn.action_cn_einvoice_reconciliation_cases"
        ).read()[0]
        action["domain"] = [("einvoice_document_id", "=", self.id)]
        action["context"] = {}
        return action
