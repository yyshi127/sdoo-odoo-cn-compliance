from collections import Counter
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import re

from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


VAT_PERIOD_ENGINE_VERSION = "19.0.1"
MAX_ACCOUNTING_MOVES = 100000
MAX_EINVOICE_DOCUMENTS = 50000
MAX_FILING_RECORDS = 100
MAX_PAYMENT_RECORDS = 10000
_VAT_PERIOD_TRANSITION_MARKER = object()
_CN_TIMEZONE = timezone(timedelta(hours=8))

SOURCE_STATES = [
    ("not_evaluated", "未评估"),
    ("available", "数据可勾稽"),
    ("no_data", "没有当前数据"),
    ("blocked", "数据存在阻断"),
]


def _checksum(payload):
    content = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _safe_text(value, limit=1000):
    if value in (None, False):
        return False
    text = " ".join(str(value).split()).strip()
    return text[:limit] if text else False


def _identity_token(value):
    text = _safe_text(value, 128) or ""
    return re.sub(r"[^0-9A-Za-z]", "", text).upper()


def _date_string(value):
    return fields.Date.to_string(value) if value else None


def _datetime_string(value):
    return fields.Datetime.to_string(value) if value else None


def _amount_string(currency, value):
    rounded = currency.round(float(value or 0.0))
    return format(Decimal(str(rounded)), "f")


def _local_period_utc_bounds(period_start, period_end):
    local_start = datetime.combine(period_start, time.min, tzinfo=_CN_TIMEZONE)
    local_end = datetime.combine(
        period_end + timedelta(days=1),
        time.min,
        tzinfo=_CN_TIMEZONE,
    )
    start_utc = local_start.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = local_end.astimezone(timezone.utc).replace(tzinfo=None)
    return start_utc, end_utc


class SudoChinaVatPeriodReconciliationRun(models.Model):
    _name = "sudo.cn.vat.period.reconciliation.run"
    _description = "China VAT Four-Way Period Reconciliation Run"
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
        store=True,
        readonly=True,
    )
    period_start = fields.Date(string="期间开始", required=True, readonly=True)
    period_end = fields.Date(string="期间结束", required=True, readonly=True)
    vat_tax_type_code = fields.Char(
        string="缴税数据增值税代码",
        required=True,
        readonly=True,
    )
    state = fields.Selection(
        [
            ("queued", "待处理"),
            ("processing", "处理中"),
            ("succeeded", "最新成功结果"),
            ("failed", "失败"),
            ("cancelled", "已取消"),
            ("superseded", "已被替代"),
        ],
        string="运行状态",
        required=True,
        default="queued",
        readonly=True,
        index=True,
    )
    conclusion_state = fields.Selection(
        [
            ("not_evaluated", "未评估"),
            ("insufficient_data", "数据不足，不能形成四方结论"),
            ("differences", "存在待复核差异"),
            ("aligned", "四方勾稽一致，不等于合规结论"),
        ],
        string="勾稽结论",
        required=True,
        default="not_evaluated",
        readonly=True,
        index=True,
    )
    engine_version = fields.Char(
        string="引擎版本",
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
    accounting_source_state = fields.Selection(
        SOURCE_STATES,
        string="账务数据",
        required=True,
        default="not_evaluated",
        readonly=True,
    )
    einvoice_source_state = fields.Selection(
        SOURCE_STATES,
        string="电子发票数据",
        required=True,
        default="not_evaluated",
        readonly=True,
    )
    filing_source_state = fields.Selection(
        SOURCE_STATES,
        string="增值税申报数据",
        required=True,
        default="not_evaluated",
        readonly=True,
    )
    payment_source_state = fields.Selection(
        SOURCE_STATES,
        string="税款缴纳数据",
        required=True,
        default="not_evaluated",
        readonly=True,
    )
    posted_accounting_move_count = fields.Integer(
        string="已过账发票凭证数",
        readonly=True,
    )
    draft_accounting_move_count = fields.Integer(
        string="草稿发票凭证数",
        readonly=True,
    )
    einvoice_document_count = fields.Integer(
        string="电子发票数",
        readonly=True,
    )
    filing_record_count = fields.Integer(string="申报记录数", readonly=True)
    payment_record_count = fields.Integer(string="缴税记录数", readonly=True)
    ledger_output_tax_amount = fields.Monetary(
        string="Odoo 客户发票税额合计",
        currency_field="currency_id",
        readonly=True,
    )
    ledger_input_tax_amount = fields.Monetary(
        string="Odoo 供应商账单税额合计",
        currency_field="currency_id",
        readonly=True,
    )
    has_einvoice_output_tax_amount = fields.Boolean(
        string="电子发票销项税额可比较",
        readonly=True,
    )
    einvoice_output_tax_amount = fields.Monetary(
        string="电子发票销项税额",
        currency_field="currency_id",
        readonly=True,
    )
    has_einvoice_input_tax_amount = fields.Boolean(
        string="电子发票进项税额可比较",
        readonly=True,
    )
    einvoice_input_tax_amount = fields.Monetary(
        string="电子发票进项税额",
        currency_field="currency_id",
        readonly=True,
    )
    has_filing_output_tax_amount = fields.Boolean(
        string="申报销项税额已提供",
        readonly=True,
    )
    filing_output_tax_amount = fields.Monetary(
        string="申报销项税额",
        currency_field="currency_id",
        readonly=True,
    )
    has_filing_input_tax_amount = fields.Boolean(
        string="申报进项税额已提供",
        readonly=True,
    )
    filing_input_tax_amount = fields.Monetary(
        string="申报进项税额",
        currency_field="currency_id",
        readonly=True,
    )
    has_filing_payable_amount = fields.Boolean(
        string="申报应纳税额已提供",
        readonly=True,
    )
    filing_payable_amount = fields.Monetary(
        string="申报应纳税额",
        currency_field="currency_id",
        readonly=True,
    )
    has_payment_amount = fields.Boolean(
        string="缴税净额可比较",
        readonly=True,
    )
    payment_amount = fields.Monetary(
        string="缴税净额",
        currency_field="currency_id",
        readonly=True,
    )
    has_ledger_einvoice_output_difference = fields.Boolean(readonly=True)
    ledger_einvoice_output_difference = fields.Monetary(
        string="账务与发票销项差异",
        currency_field="currency_id",
        readonly=True,
    )
    has_ledger_einvoice_input_difference = fields.Boolean(readonly=True)
    ledger_einvoice_input_difference = fields.Monetary(
        string="账务与发票进项差异",
        currency_field="currency_id",
        readonly=True,
    )
    has_ledger_filing_output_difference = fields.Boolean(readonly=True)
    ledger_filing_output_difference = fields.Monetary(
        string="账务与申报销项差异",
        currency_field="currency_id",
        readonly=True,
    )
    has_ledger_filing_input_difference = fields.Boolean(readonly=True)
    ledger_filing_input_difference = fields.Monetary(
        string="账务与申报进项差异",
        currency_field="currency_id",
        readonly=True,
    )
    has_filing_payment_difference = fields.Boolean(readonly=True)
    filing_payment_difference = fields.Monetary(
        string="申报应纳与缴税差异",
        currency_field="currency_id",
        readonly=True,
    )
    issue_count = fields.Integer(string="问题数", readonly=True)
    blocking_issue_count = fields.Integer(string="阻断问题数", readonly=True)
    difference_issue_count = fields.Integer(string="差异问题数", readonly=True)
    warning_issue_count = fields.Integer(string="警告数", readonly=True)
    accounting_snapshot_checksum = fields.Char(
        string="账务快照 SHA-256",
        readonly=True,
    )
    einvoice_snapshot_checksum = fields.Char(
        string="电子发票快照 SHA-256",
        readonly=True,
    )
    filing_snapshot_checksum = fields.Char(
        string="申报快照 SHA-256",
        readonly=True,
    )
    payment_snapshot_checksum = fields.Char(
        string="缴税快照 SHA-256",
        readonly=True,
    )
    result_checksum = fields.Char(string="结果 SHA-256", readonly=True)
    result_summary = fields.Text(string="结果摘要", readonly=True)
    error_code = fields.Char(string="失败代码", readonly=True)
    issue_ids = fields.One2many(
        "sudo.cn.vat.period.reconciliation.issue",
        "run_id",
        string="勾稽问题",
        readonly=True,
    )
    accounting_move_ids = fields.Many2many(
        "account.move",
        "sudo_cn_vat_period_move_rel",
        "run_id",
        "move_id",
        string="账务范围",
        groups="account.group_account_readonly",
        check_company=True,
        readonly=True,
    )
    einvoice_document_ids = fields.Many2many(
        "sudo.cn.einvoice.document",
        "sudo_cn_vat_period_einvoice_rel",
        "run_id",
        "document_id",
        string="电子发票范围",
        check_company=True,
        readonly=True,
    )
    filing_record_ids = fields.Many2many(
        "sudo.cn.vat.filing.record",
        "sudo_cn_vat_period_filing_rel",
        "run_id",
        "filing_id",
        string="申报范围",
        check_company=True,
        readonly=True,
    )
    payment_record_ids = fields.Many2many(
        "sudo.cn.tax.payment.record",
        "sudo_cn_vat_period_payment_rel",
        "run_id",
        "payment_id",
        string="缴税范围",
        check_company=True,
        readonly=True,
    )

    _period_order = models.Constraint(
        "CHECK(period_start <= period_end)",
        "增值税期间勾稽开始日期不能晚于结束日期。",
    )
    _active_period_unique = models.UniqueIndex(
        "(profile_id, period_start, period_end) "
        "WHERE state IN ('queued', 'processing')",
        "同一合规档案和期间只能有一个待处理或处理中的四方勾稽批次。",
    )

    @api.depends("profile_id", "period_start", "period_end")
    def _compute_name(self):
        for run in self:
            run.name = "%s / %s - %s" % (
                run.profile_id.display_name or _("增值税期间勾稽"),
                fields.Date.to_string(run.period_start) or "-",
                fields.Date.to_string(run.period_end) or "-",
            )

    @api.model_create_multi
    def create(self, vals_list):
        if (
            self.env.context.get("cn_vat_period_transition")
            is not _VAT_PERIOD_TRANSITION_MARKER
        ):
            raise AccessError(_("增值税期间勾稽批次只能由受控流程创建。"))
        defaults = {
            "state": "queued",
            "conclusion_state": "not_evaluated",
            "engine_version": VAT_PERIOD_ENGINE_VERSION,
            "requested_at": fields.Datetime.now(),
            "requested_by_id": self.env.user.id,
            "started_at": False,
            "finished_at": False,
            "accounting_source_state": "not_evaluated",
            "einvoice_source_state": "not_evaluated",
            "filing_source_state": "not_evaluated",
            "payment_source_state": "not_evaluated",
            "result_summary": False,
            "error_code": False,
        }
        for values in vals_list:
            values.update(defaults)
        return super().create(vals_list)

    def write(self, values):
        if (
            self.env.context.get("cn_vat_period_transition")
            is not _VAT_PERIOD_TRANSITION_MARKER
        ):
            raise AccessError(_("增值税期间勾稽批次只能由受控流程更新。"))
        return super().write(values)

    def unlink(self):
        raise AccessError(_("增值税期间勾稽批次属于审计记录，不可删除。"))

    @api.model
    def enqueue(
        self,
        profile,
        period_start,
        period_end,
        vat_tax_type_code="VAT",
    ):
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以提交增值税期间勾稽。"))
        profile.ensure_one()
        period_start = fields.Date.to_date(period_start)
        period_end = fields.Date.to_date(period_end)
        tax_type_code = (_safe_text(vat_tax_type_code, 128) or "").upper()
        if not period_start or not period_end or period_start > period_end:
            raise ValidationError(_("请选择有效的勾稽期间。"))
        if not tax_type_code:
            raise ValidationError(_("请提供缴税数据中的增值税代码。"))
        if profile.country_id != self.env.ref("base.cn"):
            raise UserError(_("只能对中国合规档案执行增值税期间勾稽。"))
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
            raise UserError(_("相同档案和期间已有待处理或处理中的四方勾稽。"))
        run = self.with_company(profile.company_id).with_context(
            cn_vat_period_transition=_VAT_PERIOD_TRANSITION_MARKER
        ).create(
            {
                "profile_id": profile.id,
                "period_start": period_start,
                "period_end": period_end,
                "vat_tax_type_code": tax_type_code,
            }
        )
        self.env["sudo.compliance.audit.event"]._log_records(
            run,
            "cn_vat_period_reconciliation.queued",
            new_state="queued",
            details={
                "period_start": fields.Date.to_string(period_start),
                "period_end": fields.Date.to_string(period_end),
                "vat_tax_type_code": tax_type_code,
                "engine_version": VAT_PERIOD_ENGINE_VERSION,
            },
        )
        return run.with_context(cn_vat_period_transition=None)

    def _accounting_moves(self):
        self.ensure_one()
        moves = self.env["account.move"].sudo().with_company(
            self.company_id
        ).search(
            [
                ("company_id", "=", self.company_id.id),
                ("state", "in", ("draft", "posted")),
                (
                    "move_type",
                    "in",
                    ("out_invoice", "out_refund", "in_invoice", "in_refund"),
                ),
                ("date", ">=", self.period_start),
                ("date", "<=", self.period_end),
            ],
            order="date, id",
            limit=MAX_ACCOUNTING_MOVES + 1,
        )
        if len(moves) > MAX_ACCOUNTING_MOVES:
            raise UserError(_("单次勾稽的 Odoo 发票凭证超过安全上限。"))
        return moves

    def _einvoice_documents(self):
        self.ensure_one()
        start_utc, end_utc = _local_period_utc_bounds(
            self.period_start,
            self.period_end,
        )
        documents = self.env["sudo.cn.einvoice.document"].sudo().search(
            [
                ("profile_id", "=", self.profile_id.id),
                ("is_current_result", "=", True),
                "|",
                "&",
                ("request_time", ">=", fields.Datetime.to_string(start_utc)),
                ("request_time", "<", fields.Datetime.to_string(end_utc)),
                "&",
                ("request_time", "=", False),
                "&",
                ("dataset_id.period_start", "<=", self.period_end),
                ("dataset_id.period_end", ">=", self.period_start),
            ],
            order="request_time, invoice_number, id",
            limit=MAX_EINVOICE_DOCUMENTS + 1,
        )
        if len(documents) > MAX_EINVOICE_DOCUMENTS:
            raise UserError(_("单次勾稽的规范化电子发票超过安全上限。"))
        return documents

    def _filing_records(self):
        self.ensure_one()
        records = self.env["sudo.cn.vat.filing.record"].sudo().search(
            [
                ("profile_id", "=", self.profile_id.id),
                ("is_current_result", "=", True),
                ("period_start", "=", self.period_start),
                ("period_end", "=", self.period_end),
            ],
            order="revision_number desc, submitted_at desc, id desc",
            limit=MAX_FILING_RECORDS + 1,
        )
        if len(records) > MAX_FILING_RECORDS:
            raise UserError(_("单次勾稽的规范化增值税申报超过安全上限。"))
        return records

    def _payment_records(self):
        self.ensure_one()
        records = self.env["sudo.cn.tax.payment.record"].sudo().search(
            [
                ("profile_id", "=", self.profile_id.id),
                ("is_current_result", "=", True),
                ("period_start", "=", self.period_start),
                ("period_end", "=", self.period_end),
                ("tax_type_code", "=ilike", self.vat_tax_type_code),
            ],
            order="payment_date, id",
            limit=MAX_PAYMENT_RECORDS + 1,
        )
        if len(records) > MAX_PAYMENT_RECORDS:
            raise UserError(_("单次勾稽的规范化税款缴纳记录超过安全上限。"))
        return records

    @api.model
    def _add_issue(
        self,
        bucket,
        code,
        severity,
        source_area,
        title,
        description,
        action_hint,
        *,
        issue_kind="data_gap",
        affected_count=1,
        left_label=False,
        left_amount=None,
        right_label=False,
        right_amount=None,
        difference=None,
    ):
        key = code
        if key in bucket:
            existing = bucket[key]
            definition = (
                existing["severity"],
                existing["source_area"],
                existing["issue_kind"],
            )
            if definition != (severity, source_area, issue_kind):
                raise ValidationError(
                    _("勾稽问题代码 %(code)s 存在冲突定义。", code=code)
                )
            existing["affected_record_count"] += int(affected_count or 1)
            return existing
        values = {
            "sequence": {"blocking": 10, "review": 20, "info": 30}[severity],
            "code": code,
            "severity": severity,
            "source_area": source_area,
            "issue_kind": issue_kind,
            "name": title,
            "description": description,
            "action_hint": action_hint,
            "affected_record_count": int(affected_count or 1),
            "has_left_amount": left_amount is not None,
            "left_label": left_label,
            "left_amount": float(left_amount or 0.0),
            "has_right_amount": right_amount is not None,
            "right_label": right_label,
            "right_amount": float(right_amount or 0.0),
            "has_difference": difference is not None,
            "difference_amount": float(difference or 0.0),
        }
        bucket[key] = values
        return values

    def _add_source_control_issues(self, record, bucket, source_area, label):
        blocked = False
        if record.source_integrity_state != "verified":
            blocked = True
            self._add_issue(
                bucket,
                "%s_SOURCE_INTEGRITY_NOT_VERIFIED" % source_area.upper(),
                "blocking",
                source_area,
                _("%(source)s完整性失效", source=label),
                _("当前规范化记录对应的封存文件完整性不再有效。"),
                _("重新核对原始附件与封存哈希，必要时创建替代数据集。"),
            )
        if record.source_coverage_scope != "full":
            blocked = True
            self._add_issue(
                bucket,
                "%s_SOURCE_COVERAGE_NOT_FULL" % source_area.upper(),
                "blocking",
                source_area,
                _("%(source)s不是完整覆盖", source=label),
                _("部分、抽样或未知覆盖范围不能用于期间总额勾稽。"),
                _("取得覆盖整个勾稽期间的完整受控数据并重新导入。"),
            )
        if record.source_authenticity_state == "official_tool_failed":
            blocked = True
            self._add_issue(
                bucket,
                "%s_SOURCE_AUTHENTICITY_FAILED" % source_area.upper(),
                "blocking",
                source_area,
                _("%(source)s真实性验证失败", source=label),
                _("来源记录已明确保存受控真实性工具失败结果。"),
                _("核对原始来源并在真实性问题解决后重新取得数据。"),
            )
        elif record.source_authenticity_state not in (
            "official_tool_passed",
            "not_applicable",
        ):
            self._add_issue(
                bucket,
                "%s_SOURCE_AUTHENTICITY_NOT_CONFIRMED" % source_area.upper(),
                "review",
                source_area,
                _("%(source)s真实性尚未确认", source=label),
                _("标准化和封存不等于税务机关或银行真实性确认。"),
                _("结合申报回执、缴款回执或受控验证工具完成人工复核。"),
            )
        if record.source_review_control_state == "exception":
            self._add_issue(
                bucket,
                "%s_SOURCE_REVIEW_EXCEPTION" % source_area.upper(),
                "review",
                source_area,
                _("%(source)s采用单人复核例外", source=label),
                _("来源数据没有完成独立双人复核。"),
                _("由另一名授权人员复核来源、范围和封存清单。"),
            )
        return blocked

    def _collect_accounting(self, bucket):
        moves = self._accounting_moves()
        posted = moves.filtered(lambda move: move.state == "posted")
        drafts = moves - posted
        output_tax = 0.0
        input_tax = 0.0
        helper = self.env["sudo.cn.einvoice.reconciliation.run"]
        line_summaries = helper._ledger_line_summaries(moves)
        empty_summary = {
            "debit_total": 0.0,
            "credit_total": 0.0,
            "line_count": 0,
            "line_write_date": None,
        }
        snapshots = []
        for move in moves:
            amount = abs(float(move.amount_tax_signed or 0.0))
            if move.state == "posted":
                if move.move_type == "out_invoice":
                    output_tax += amount
                elif move.move_type == "out_refund":
                    output_tax -= amount
                elif move.move_type == "in_invoice":
                    input_tax += amount
                elif move.move_type == "in_refund":
                    input_tax -= amount
            snapshot = helper._move_candidate_snapshot(
                move,
                line_summaries.get(move.id, empty_summary),
            )
            snapshot["period_tax_amount_company_currency"] = _amount_string(
                self.currency_id,
                amount,
            )
            snapshots.append(snapshot)
        self._add_issue(
            bucket,
            "ACCOUNTING_SCOPE_INVOICE_TAX_TOTALS_ONLY",
            "review",
            "accounting",
            _("账务口径仅为 Odoo 发票税额合计"),
            _(
                "当前版本使用客户和供应商发票的全部税额合计，尚未按"
                "中国增值税税种、税目或控制科目建立专用映射。"
            ),
            _(
                "复核 Odoo 税配置及增值税控制科目，并结合未开票、"
                "视同销售、进项转出和其他申报调整解释差异。"
            ),
        )
        if drafts:
            self._add_issue(
                bucket,
                "DRAFT_ACCOUNTING_INVOICES_EXCLUDED",
                "review",
                "accounting",
                _("存在未过账发票凭证"),
                _("%(count)s 张草稿客户或供应商发票未计入账务税额。", count=len(drafts)),
                _("核对草稿单据是否应在当前期间过账、取消或移至其他期间。"),
                affected_count=len(drafts),
            )
        return {
            "state": "available",
            "moves": moves,
            "posted_count": len(posted),
            "draft_count": len(drafts),
            "output_tax": self.currency_id.round(output_tax),
            "input_tax": self.currency_id.round(input_tax),
            "snapshot": sorted(snapshots, key=lambda item: item["move_id"]),
        }

    def _invoice_identity(self, document):
        number = _identity_token(document.invoice_number)
        seller = _identity_token(document.seller_tax_id)
        if not number or not seller:
            return False
        return (number, seller, document.is_red or "unknown")

    def _collect_einvoices(self, bucket):
        documents = self._einvoice_documents()
        if not documents:
            self._add_issue(
                bucket,
                "NO_CURRENT_EINVOICE_DATA",
                "blocking",
                "einvoice",
                _("期间没有当前有效电子发票数据"),
                _("缺少完整票据口径，不能完成账务、票据、申报、缴税四方勾稽。"),
                _("登记并封存覆盖当前期间的完整电子发票数据后执行受控解析。"),
            )
            return {
                "state": "no_data",
                "documents": documents,
                "output_tax": 0.0,
                "input_tax": 0.0,
                "snapshot": [],
            }
        company_tax_id = _identity_token(self.company_id.partner_id.vat)
        if not company_tax_id:
            self._add_issue(
                bucket,
                "MISSING_COMPANY_TAX_ID",
                "blocking",
                "einvoice",
                _("Odoo 公司缺少统一社会信用代码"),
                _("无法判断电子发票属于销项还是进项。"),
                _("在公司登记信息中维护并核实统一社会信用代码。"),
            )
        identities = Counter(
            identity
            for document in documents
            if (identity := self._invoice_identity(document))
        )
        output_tax = 0.0
        input_tax = 0.0
        blocked = not company_tax_id
        snapshots = []
        for document in documents:
            document_blocked = not company_tax_id
            if document.quality_state == "error":
                document_blocked = True
                self._add_issue(
                    bucket,
                    "EINVOICE_QUALITY_ERROR",
                    "blocking",
                    "einvoice",
                    _("电子发票存在标准化数据错误"),
                    _("至少一张电子发票缺少关键字段或金额关系无效。"),
                    _("打开电子发票台账修复来源映射后重新解析。"),
                )
            elif document.quality_state == "warning":
                self._add_issue(
                    bucket,
                    "EINVOICE_QUALITY_WARNING",
                    "review",
                    "einvoice",
                    _("电子发票存在数据警告"),
                    _("至少一张电子发票包含需要披露的数据质量限制。"),
                    _("在确认期间差异前逐项复核电子发票质量提示。"),
                )
            document_blocked = (
                self._add_source_control_issues(
                    document,
                    bucket,
                    "einvoice",
                    _("电子发票"),
                )
                or document_blocked
            )
            if (
                document.dataset_id.declared_record_count
                != document.parse_run_id.document_count
            ):
                document_blocked = True
                self._add_issue(
                    bucket,
                    "EINVOICE_RECORD_COUNT_MISMATCH",
                    "blocking",
                    "einvoice",
                    _("电子发票声明数量不一致"),
                    _("数据集声明数量与当前规范化发票数量不一致。"),
                    _("核对完整导出范围、附件和解析结果后重新导入。"),
                )
            identity = self._invoice_identity(document)
            if identity and identities[identity] > 1:
                document_blocked = True
                self._add_issue(
                    bucket,
                    "DUPLICATE_CURRENT_EINVOICE",
                    "blocking",
                    "einvoice",
                    _("存在重复当前电子发票"),
                    _("同一销售方、发票号码和红蓝状态存在多份当前记录。"),
                    _("确认替代版本关系并只保留一份当前有效来源。"),
                )
            if not document.request_time:
                document_blocked = True
                self._add_issue(
                    bucket,
                    "EINVOICE_DATE_MISSING",
                    "blocking",
                    "einvoice",
                    _("电子发票缺少开具时间"),
                    _("无法确认电子发票是否属于当前勾稽期间。"),
                    _("补齐受控来源中的开具时间并重新解析。"),
                )
            if not document.has_tax_amount:
                document_blocked = True
                self._add_issue(
                    bucket,
                    "EINVOICE_TAX_AMOUNT_MISSING",
                    "blocking",
                    "einvoice",
                    _("电子发票缺少税额"),
                    _("缺少可与账务和申报比较的电子发票税额。"),
                    _("核对源文件字段映射并重新解析。"),
                )
            if document.currency_id != self.currency_id:
                document_blocked = True
                self._add_issue(
                    bucket,
                    "EINVOICE_CURRENCY_MISMATCH",
                    "blocking",
                    "einvoice",
                    _("电子发票币种与公司本位币不一致"),
                    _("当前版本不在缺少受控汇率快照时换算票据税额。"),
                    _("补充受控汇率与换算规则后再执行跨币种勾稽。"),
                )
            if document.is_red not in ("yes", "no"):
                document_blocked = True
                self._add_issue(
                    bucket,
                    "EINVOICE_RED_STATUS_UNKNOWN",
                    "blocking",
                    "einvoice",
                    _("电子发票红蓝状态不明确"),
                    _("无法确定税额在期间汇总中应加计还是冲减。"),
                    _("核对红字标识后重新解析。"),
                )
            seller_tax_id = _identity_token(document.seller_tax_id)
            accounting_tax_id = _identity_token(
                document.accounting_entity_tax_id
            )
            direction = False
            if company_tax_id and seller_tax_id == company_tax_id:
                direction = "output"
            elif company_tax_id and accounting_tax_id == company_tax_id:
                direction = "input"
            else:
                document_blocked = True
                self._add_issue(
                    bucket,
                    "EINVOICE_ENTITY_UNCLASSIFIED",
                    "blocking",
                    "einvoice",
                    _("电子发票主体无法归类"),
                    _("销售方和会计主体均不能可靠映射到当前 Odoo 公司。"),
                    _("核对销售方、购买方或会计主体统一社会信用代码。"),
                )
            signed_tax = 0.0
            if not document_blocked:
                signed_tax = abs(float(document.tax_amount or 0.0))
                if document.is_red == "yes":
                    signed_tax *= -1
                if direction == "output":
                    output_tax += signed_tax
                else:
                    input_tax += signed_tax
            blocked = blocked or document_blocked
            snapshots.append(
                {
                    "document_id": document.id,
                    "document_checksum": document.document_checksum,
                    "parse_run_checksum": document.parse_run_id.output_checksum,
                    "direction": direction,
                    "included": not document_blocked,
                    "signed_tax_amount": _amount_string(
                        self.currency_id,
                        signed_tax,
                    ),
                }
            )
        return {
            "state": "blocked" if blocked else "available",
            "documents": documents,
            "output_tax": self.currency_id.round(output_tax),
            "input_tax": self.currency_id.round(input_tax),
            "snapshot": sorted(
                snapshots,
                key=lambda item: item["document_id"],
            ),
        }

    def _filing_snapshot(self, record):
        return {
            "record_id": record.id,
            "record_checksum": record.record_checksum,
            "parse_run_checksum": record.parse_run_id.output_checksum,
            "return_status": record.return_status,
            "revision_number": record.revision_number,
            "submitted_at": _datetime_string(record.submitted_at),
            "has_output_tax_amount": record.has_output_tax_amount,
            "output_tax_amount": (
                _amount_string(self.currency_id, record.output_tax_amount)
                if record.has_output_tax_amount
                else None
            ),
            "has_input_tax_amount": record.has_input_tax_amount,
            "input_tax_amount": (
                _amount_string(self.currency_id, record.input_tax_amount)
                if record.has_input_tax_amount
                else None
            ),
            "has_tax_payable_amount": record.has_tax_payable_amount,
            "tax_payable_amount": (
                _amount_string(self.currency_id, record.tax_payable_amount)
                if record.has_tax_payable_amount
                else None
            ),
        }

    def _collect_filing(self, bucket):
        records = self._filing_records()
        snapshots = [self._filing_snapshot(record) for record in records]
        if not records:
            self._add_issue(
                bucket,
                "NO_CURRENT_VAT_FILING",
                "blocking",
                "filing",
                _("期间没有当前有效增值税申报"),
                _("缺少申报口径，不能完成账务、票据、申报、缴税四方勾稽。"),
                _("登记、封存并导入当前税款所属期的受控增值税申报数据。"),
            )
            return {
                "state": "no_data",
                "records": records,
                "has_output": False,
                "output_tax": 0.0,
                "has_input": False,
                "input_tax": 0.0,
                "has_payable": False,
                "payable": 0.0,
                "snapshot": snapshots,
            }
        if len(records) != 1:
            self._add_issue(
                bucket,
                "AMBIGUOUS_CURRENT_VAT_FILING",
                "blocking",
                "filing",
                _("期间存在多份当前增值税申报"),
                _("系统不会自动猜测哪一份申报或更正申报应作为最终口径。"),
                _("核实申报、更正和替代关系，只保留一份当前有效申报结果。"),
                affected_count=len(records),
            )
            return {
                "state": "blocked",
                "records": records,
                "has_output": False,
                "output_tax": 0.0,
                "has_input": False,
                "input_tax": 0.0,
                "has_payable": False,
                "payable": 0.0,
                "snapshot": snapshots,
            }
        record = records
        blocked = self._add_source_control_issues(
            record,
            bucket,
            "filing",
            _("增值税申报"),
        )
        if record.dataset_id.declared_record_count != record.parse_run_id.record_count:
            blocked = True
            self._add_issue(
                bucket,
                "FILING_RECORD_COUNT_MISMATCH",
                "blocking",
                "filing",
                _("增值税申报声明数量不一致"),
                _("数据集声明数量与当前规范化申报数量不一致。"),
                _("核对完整导出范围、附件和导入结果后重新导入。"),
            )
        if record.quality_state == "error":
            blocked = True
            self._add_issue(
                bucket,
                "FILING_QUALITY_ERROR",
                "blocking",
                "filing",
                _("增值税申报存在标准化数据错误"),
                _("申报主体、期间、币种或必要金额存在错误。"),
                _("打开增值税申报台账处理质量问题后重新导入。"),
            )
        elif record.quality_state == "warning":
            self._add_issue(
                bucket,
                "FILING_QUALITY_WARNING",
                "review",
                "filing",
                _("增值税申报存在数据警告"),
                _("申报数据包含需要在结论中披露的质量限制。"),
                _("核对申报原件和回执后再确认期间差异。"),
            )
        if record.return_status not in ("submitted", "accepted", "amended"):
            blocked = True
            self._add_issue(
                bucket,
                "FILING_STATUS_NOT_EFFECTIVE",
                "blocking",
                "filing",
                _("增值税申报状态不能作为期间口径"),
                _("草稿、作废或未知状态不能代表已提交的期间申报。"),
                _("取得有效申报结果与回执后更新受控数据。"),
            )
        if record.currency_id != self.currency_id:
            blocked = True
            self._add_issue(
                bucket,
                "FILING_CURRENCY_MISMATCH",
                "blocking",
                "filing",
                _("增值税申报币种与公司本位币不一致"),
                _("当前版本不在缺少受控汇率快照时换算申报金额。"),
                _("核实申报币种或补充受控汇率与换算规则。"),
            )
        required_amounts = (
            (
                record.has_output_tax_amount,
                "FILING_OUTPUT_TAX_MISSING",
                _("申报未提供销项税额"),
            ),
            (
                record.has_input_tax_amount,
                "FILING_INPUT_TAX_MISSING",
                _("申报未提供进项税额"),
            ),
            (
                record.has_tax_payable_amount,
                "FILING_PAYABLE_MISSING",
                _("申报未提供应纳税额"),
            ),
        )
        for present, code, title in required_amounts:
            if present:
                continue
            blocked = True
            self._add_issue(
                bucket,
                code,
                "blocking",
                "filing",
                title,
                _("缺少完成四方勾稽所需的申报汇总金额。"),
                _("核对申报表映射并重新导入完整字段。"),
            )
        return {
            "state": "blocked" if blocked else "available",
            "records": records,
            "has_output": bool(record.has_output_tax_amount and not blocked),
            "output_tax": self.currency_id.round(record.output_tax_amount),
            "has_input": bool(record.has_input_tax_amount and not blocked),
            "input_tax": self.currency_id.round(record.input_tax_amount),
            "has_payable": bool(record.has_tax_payable_amount and not blocked),
            "payable": self.currency_id.round(record.tax_payable_amount),
            "snapshot": snapshots,
        }

    def _payment_snapshot(self, record, included, signed_amount):
        return {
            "record_id": record.id,
            "record_checksum": record.record_checksum,
            "parse_run_checksum": record.parse_run_id.output_checksum,
            "payment_status": record.payment_status,
            "payment_date": _date_string(record.payment_date),
            "included": included,
            "signed_amount": _amount_string(self.currency_id, signed_amount),
        }

    def _collect_payments(self, bucket):
        records = self._payment_records()
        if not records:
            self._add_issue(
                bucket,
                "NO_CURRENT_VAT_PAYMENT_DATA",
                "blocking",
                "payment",
                _("期间没有当前有效增值税缴款数据"),
                _("缺少缴税口径，不能完成申报应纳与实际缴税勾稽。"),
                _("登记、封存并导入当前税款所属期的受控缴税记录。"),
            )
            return {
                "state": "no_data",
                "records": records,
                "has_amount": False,
                "amount": 0.0,
                "snapshot": [],
            }
        blocked = False
        effective_count = 0
        net_amount = 0.0
        snapshots = []
        identities = Counter(
            (
                record.tax_type_code,
                record.payment_reference or record.source_record_key,
                record.payment_status,
                _amount_string(
                    record.currency_id or self.currency_id,
                    record.amount,
                ),
            )
            for record in records
        )
        for record in records:
            record_blocked = self._add_source_control_issues(
                record,
                bucket,
                "payment",
                _("税款缴纳"),
            )
            identity = (
                record.tax_type_code,
                record.payment_reference or record.source_record_key,
                record.payment_status,
                _amount_string(
                    record.currency_id or self.currency_id,
                    record.amount,
                ),
            )
            if identities[identity] > 1:
                record_blocked = True
                self._add_issue(
                    bucket,
                    "DUPLICATE_CURRENT_VAT_PAYMENT",
                    "blocking",
                    "payment",
                    _("存在重复当前增值税缴款记录"),
                    _("相同缴款引用、状态和金额存在多份当前记录。"),
                    _("核实数据集替代关系并只保留一份当前有效记录。"),
                )
            if (
                record.dataset_id.declared_record_count
                != record.parse_run_id.record_count
            ):
                record_blocked = True
                self._add_issue(
                    bucket,
                    "PAYMENT_RECORD_COUNT_MISMATCH",
                    "blocking",
                    "payment",
                    _("税款缴纳声明数量不一致"),
                    _("数据集声明数量与当前规范化缴款数量不一致。"),
                    _("核对完整导出范围、附件和导入结果后重新导入。"),
                )
            if record.quality_state == "error":
                record_blocked = True
                self._add_issue(
                    bucket,
                    "PAYMENT_QUALITY_ERROR",
                    "blocking",
                    "payment",
                    _("税款缴纳记录存在标准化数据错误"),
                    _("缴税主体、期间、币种、金额或敏感字段存在错误。"),
                    _("打开税款缴纳台账处理质量问题后重新导入。"),
                )
            elif record.quality_state == "warning":
                self._add_issue(
                    bucket,
                    "PAYMENT_QUALITY_WARNING",
                    "review",
                    "payment",
                    _("税款缴纳记录存在数据警告"),
                    _("缴税数据包含需要在结论中披露的质量限制。"),
                    _("核对缴款回执后再确认申报与缴税差异。"),
                )
            if record.currency_id != self.currency_id:
                record_blocked = True
                self._add_issue(
                    bucket,
                    "PAYMENT_CURRENCY_MISMATCH",
                    "blocking",
                    "payment",
                    _("税款缴纳币种与公司本位币不一致"),
                    _("当前版本不在缺少受控汇率快照时换算缴税金额。"),
                    _("核实缴税币种或补充受控汇率与换算规则。"),
                )
            if not record.has_amount:
                record_blocked = True
                self._add_issue(
                    bucket,
                    "PAYMENT_AMOUNT_MISSING",
                    "blocking",
                    "payment",
                    _("税款缴纳记录缺少金额"),
                    _("缺少可与申报应纳税额比较的缴税金额。"),
                    _("核对缴款数据映射并重新导入。"),
                )
            signed_amount = 0.0
            included = False
            if record.payment_status == "succeeded":
                signed_amount = abs(float(record.amount or 0.0))
                included = not record_blocked
            elif record.payment_status in ("reversed", "refunded"):
                signed_amount = -abs(float(record.amount or 0.0))
                included = not record_blocked
            elif record.payment_status in ("pending", "failed"):
                self._add_issue(
                    bucket,
                    "NON_EFFECTIVE_PAYMENT_EXCLUDED",
                    "review",
                    "payment",
                    _("存在未生效缴税记录"),
                    _("处理中或失败的缴款没有计入期间缴税净额。"),
                    _("核对最终缴款状态和回执，必要时重新导入。"),
                )
            else:
                record_blocked = True
                self._add_issue(
                    bucket,
                    "PAYMENT_STATUS_UNKNOWN",
                    "blocking",
                    "payment",
                    _("税款缴纳状态无法判断"),
                    _("无法确认该记录应计入、冲减还是排除期间缴税净额。"),
                    _("核对缴款状态并重新导入。"),
                )
            if included:
                effective_count += 1
                net_amount += signed_amount
            blocked = blocked or record_blocked
            snapshots.append(
                self._payment_snapshot(record, included, signed_amount)
            )
        if not effective_count:
            blocked = True
            self._add_issue(
                bucket,
                "NO_EFFECTIVE_VAT_PAYMENT",
                "blocking",
                "payment",
                _("期间没有可计入的有效增值税缴款"),
                _("当前记录均为处理中、失败、未知或数据阻断状态。"),
                _("取得最终缴款结果和回执后重新导入。"),
            )
        return {
            "state": "blocked" if blocked else "available",
            "records": records,
            "has_amount": bool(effective_count and not blocked),
            "amount": self.currency_id.round(net_amount),
            "snapshot": sorted(
                snapshots,
                key=lambda item: item["record_id"],
            ),
        }

    def _add_comparison(
        self,
        bucket,
        values,
        has_field,
        difference_field,
        code,
        title,
        left_label,
        left_amount,
        right_label,
        right_amount,
        action_hint,
    ):
        difference = self.currency_id.round(left_amount - right_amount)
        values[has_field] = True
        values[difference_field] = difference
        if self.currency_id.is_zero(difference):
            return
        self._add_issue(
            bucket,
            code,
            "review",
            "cross_source",
            title,
            _("两个受控口径在当前期间存在金额差异。"),
            action_hint,
            issue_kind="difference",
            left_label=left_label,
            left_amount=left_amount,
            right_label=right_label,
            right_amount=right_amount,
            difference=difference,
        )

    def _build_results(self):
        self.ensure_one()
        bucket = {}
        accounting = self._collect_accounting(bucket)
        einvoices = self._collect_einvoices(bucket)
        filing = self._collect_filing(bucket)
        payments = self._collect_payments(bucket)
        accounting_checksum = _checksum(accounting["snapshot"])
        einvoice_checksum = _checksum(einvoices["snapshot"])
        filing_checksum = _checksum(filing["snapshot"])
        payment_checksum = _checksum(payments["snapshot"])
        values = {
            "accounting_source_state": accounting["state"],
            "einvoice_source_state": einvoices["state"],
            "filing_source_state": filing["state"],
            "payment_source_state": payments["state"],
            "posted_accounting_move_count": accounting["posted_count"],
            "draft_accounting_move_count": accounting["draft_count"],
            "einvoice_document_count": len(einvoices["documents"]),
            "filing_record_count": len(filing["records"]),
            "payment_record_count": len(payments["records"]),
            "ledger_output_tax_amount": accounting["output_tax"],
            "ledger_input_tax_amount": accounting["input_tax"],
            "has_einvoice_output_tax_amount": (
                einvoices["state"] == "available"
            ),
            "einvoice_output_tax_amount": einvoices["output_tax"],
            "has_einvoice_input_tax_amount": (
                einvoices["state"] == "available"
            ),
            "einvoice_input_tax_amount": einvoices["input_tax"],
            "has_filing_output_tax_amount": filing["has_output"],
            "filing_output_tax_amount": filing["output_tax"],
            "has_filing_input_tax_amount": filing["has_input"],
            "filing_input_tax_amount": filing["input_tax"],
            "has_filing_payable_amount": filing["has_payable"],
            "filing_payable_amount": filing["payable"],
            "has_payment_amount": payments["has_amount"],
            "payment_amount": payments["amount"],
            "has_ledger_einvoice_output_difference": False,
            "ledger_einvoice_output_difference": 0.0,
            "has_ledger_einvoice_input_difference": False,
            "ledger_einvoice_input_difference": 0.0,
            "has_ledger_filing_output_difference": False,
            "ledger_filing_output_difference": 0.0,
            "has_ledger_filing_input_difference": False,
            "ledger_filing_input_difference": 0.0,
            "has_filing_payment_difference": False,
            "filing_payment_difference": 0.0,
            "accounting_snapshot_checksum": accounting_checksum,
            "einvoice_snapshot_checksum": einvoice_checksum,
            "filing_snapshot_checksum": filing_checksum,
            "payment_snapshot_checksum": payment_checksum,
            "accounting_move_ids": [Command.set(accounting["moves"].ids)],
            "einvoice_document_ids": [
                Command.set(einvoices["documents"].ids)
            ],
            "filing_record_ids": [Command.set(filing["records"].ids)],
            "payment_record_ids": [Command.set(payments["records"].ids)],
        }
        if einvoices["state"] == "available":
            self._add_comparison(
                bucket,
                values,
                "has_ledger_einvoice_output_difference",
                "ledger_einvoice_output_difference",
                "LEDGER_EINVOICE_OUTPUT_DIFFERENCE",
                _("账务与电子发票销项税额不一致"),
                _("Odoo 已过账客户发票税额合计"),
                accounting["output_tax"],
                _("受控电子发票销项税额"),
                einvoices["output_tax"],
                _("按单据、红字状态、入账期间和票据覆盖范围逐项核对。"),
            )
            self._add_comparison(
                bucket,
                values,
                "has_ledger_einvoice_input_difference",
                "ledger_einvoice_input_difference",
                "LEDGER_EINVOICE_INPUT_DIFFERENCE",
                _("账务与电子发票进项税额不一致"),
                _("Odoo 已过账供应商账单税额合计"),
                accounting["input_tax"],
                _("受控电子发票进项税额"),
                einvoices["input_tax"],
                _("按单据、红字状态、入账期间和票据覆盖范围逐项核对。"),
            )
        if filing["has_output"]:
            self._add_comparison(
                bucket,
                values,
                "has_ledger_filing_output_difference",
                "ledger_filing_output_difference",
                "LEDGER_FILING_OUTPUT_DIFFERENCE",
                _("账务销项税额与申报销项税额不一致"),
                _("Odoo 已过账客户发票税额合计"),
                accounting["output_tax"],
                _("增值税申报销项税额"),
                filing["output_tax"],
                _("核对未开票收入、视同销售、红字、调整及跨期入账。"),
            )
        if filing["has_input"]:
            self._add_comparison(
                bucket,
                values,
                "has_ledger_filing_input_difference",
                "ledger_filing_input_difference",
                "LEDGER_FILING_INPUT_DIFFERENCE",
                _("账务进项税额与申报进项税额不一致"),
                _("Odoo 已过账供应商账单税额合计"),
                accounting["input_tax"],
                _("增值税申报进项税额"),
                filing["input_tax"],
                _("核对用途确认、不可抵扣转出、红字、调整及跨期认证。"),
            )
        if filing["has_payable"] and payments["has_amount"]:
            self._add_comparison(
                bucket,
                values,
                "has_filing_payment_difference",
                "filing_payment_difference",
                "FILING_PAYMENT_DIFFERENCE",
                _("申报应纳税额与缴税净额不一致"),
                _("增值税申报应纳税额"),
                filing["payable"],
                _("有效缴税、冲正及退库净额"),
                payments["amount"],
                _("核对缴款回执、欠税、抵缴、分次缴纳、冲正和退库记录。"),
            )
        issue_values = list(bucket.values())
        blocking_count = sum(
            issue["severity"] == "blocking" for issue in issue_values
        )
        difference_count = sum(
            issue["issue_kind"] == "difference" for issue in issue_values
        )
        warning_count = sum(
            issue["severity"] == "review"
            and issue["issue_kind"] != "difference"
            for issue in issue_values
        )
        conclusion = (
            "insufficient_data"
            if blocking_count
            else "differences"
            if difference_count
            else "aligned"
        )
        values.update(
            {
                "conclusion_state": conclusion,
                "issue_count": len(issue_values),
                "blocking_issue_count": blocking_count,
                "difference_issue_count": difference_count,
                "warning_issue_count": warning_count,
                "issue_ids": [Command.create(issue) for issue in issue_values],
            }
        )
        result_payload = {
            "engine_version": self.engine_version,
            "period_start": _date_string(self.period_start),
            "period_end": _date_string(self.period_end),
            "vat_tax_type_code": self.vat_tax_type_code,
            "source_states": {
                "accounting": accounting["state"],
                "einvoice": einvoices["state"],
                "filing": filing["state"],
                "payment": payments["state"],
            },
            "source_counts": {
                "accounting_posted": accounting["posted_count"],
                "accounting_draft": accounting["draft_count"],
                "einvoice": len(einvoices["documents"]),
                "filing": len(filing["records"]),
                "payment": len(payments["records"]),
            },
            "source_checksums": {
                "accounting": accounting_checksum,
                "einvoice": einvoice_checksum,
                "filing": filing_checksum,
                "payment": payment_checksum,
            },
            "conclusion_state": conclusion,
            "amounts": {
                key: _amount_string(self.currency_id, values[key])
                for key in (
                    "ledger_output_tax_amount",
                    "ledger_input_tax_amount",
                    "einvoice_output_tax_amount",
                    "einvoice_input_tax_amount",
                    "filing_output_tax_amount",
                    "filing_input_tax_amount",
                    "filing_payable_amount",
                    "payment_amount",
                    "ledger_einvoice_output_difference",
                    "ledger_einvoice_input_difference",
                    "ledger_filing_output_difference",
                    "ledger_filing_input_difference",
                    "filing_payment_difference",
                )
            },
            "provided": {
                key: bool(values[key])
                for key in (
                    "has_einvoice_output_tax_amount",
                    "has_einvoice_input_tax_amount",
                    "has_filing_output_tax_amount",
                    "has_filing_input_tax_amount",
                    "has_filing_payable_amount",
                    "has_payment_amount",
                    "has_ledger_einvoice_output_difference",
                    "has_ledger_einvoice_input_difference",
                    "has_ledger_filing_output_difference",
                    "has_ledger_filing_input_difference",
                    "has_filing_payment_difference",
                )
            },
            "issues": [
                {
                    "code": issue["code"],
                    "severity": issue["severity"],
                    "issue_kind": issue["issue_kind"],
                    "affected_record_count": issue["affected_record_count"],
                    "difference": (
                        _amount_string(
                            self.currency_id,
                            issue["difference_amount"],
                        )
                        if issue["has_difference"]
                        else None
                    ),
                }
                for issue in sorted(
                    issue_values,
                    key=lambda item: (
                        item["code"],
                        item["severity"],
                        item["issue_kind"],
                    ),
                )
            ],
        }
        values["result_checksum"] = _checksum(result_payload)
        return values

    def _mark_failed(self, code, summary):
        self.ensure_one()
        safe_code = _safe_text(code, 128) or "VAT_PERIOD_RECONCILIATION_FAILED"
        safe_summary = _safe_text(summary, 2000) or _("增值税期间勾稽失败。")
        self.with_context(
            cn_vat_period_transition=_VAT_PERIOD_TRANSITION_MARKER
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
            "cn_vat_period_reconciliation.failed",
            previous_state="processing",
            new_state="failed",
            details={"error_code": safe_code},
        )
        return False

    def _process(self):
        self.ensure_one()
        if self.state != "queued":
            raise UserError(_("只有待处理的增值税期间勾稽批次可以执行。"))
        self.with_context(
            cn_vat_period_transition=_VAT_PERIOD_TRANSITION_MARKER
        ).write(
            {
                "state": "processing",
                "started_at": fields.Datetime.now(),
            }
        )
        self.env["sudo.compliance.audit.event"]._log_records(
            self,
            "cn_vat_period_reconciliation.processing",
            previous_state="queued",
            new_state="processing",
        )
        try:
            with self.env.cr.savepoint():
                result_values = self._build_results()
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
                    cn_vat_period_transition=_VAT_PERIOD_TRANSITION_MARKER
                ).write({"state": "superseded"})
                conclusion = result_values["conclusion_state"]
                if conclusion == "insufficient_data":
                    summary = _(
                        "期间四方勾稽已执行，但存在 %(count)s 项数据阻断，"
                        "不能形成金额一致或不一致结论。",
                        count=result_values["blocking_issue_count"],
                    )
                elif conclusion == "differences":
                    summary = _(
                        "期间四方数据可比较，发现 %(count)s 项待复核金额差异；"
                        "差异不自动等同于税务风险或违法结论。",
                        count=result_values["difference_issue_count"],
                    )
                else:
                    summary = _(
                        "期间四方金额在当前受控口径下勾稽一致；"
                        "该结果不替代税法规则评估、人工复核或专业签核。"
                    )
                self.sudo().with_context(
                    cn_vat_period_transition=_VAT_PERIOD_TRANSITION_MARKER
                ).write(
                    {
                        **result_values,
                        "state": "succeeded",
                        "finished_at": fields.Datetime.now(),
                        "result_summary": summary,
                        "error_code": False,
                    }
                )
        except (UserError, ValidationError) as exc:
            return self._mark_failed("VAT_PERIOD_INPUT_ERROR", exc)
        except Exception as exc:
            return self._mark_failed(
                "UNEXPECTED_VAT_PERIOD_FAILURE",
                _(
                    "增值税期间勾稽发生未预期错误：%(kind)s",
                    kind=type(exc).__name__,
                ),
            )
        for previous in previous_runs:
            self.env["sudo.compliance.audit.event"]._log_records(
                previous,
                "cn_vat_period_reconciliation.superseded",
                previous_state="succeeded",
                new_state="superseded",
                details={"replacement_run_id": self.id},
            )
        self.env["sudo.compliance.audit.event"]._log_records(
            self,
            "cn_vat_period_reconciliation.succeeded",
            previous_state="processing",
            new_state="succeeded",
            details={
                "engine_version": self.engine_version,
                "conclusion_state": self.conclusion_state,
                "issue_count": self.issue_count,
                "blocking_issue_count": self.blocking_issue_count,
                "difference_issue_count": self.difference_issue_count,
                "result_checksum": self.result_checksum,
            },
        )
        return True

    @api.model
    def _cron_process_runs(self, limit=1):
        processed = 0
        for _index in range(max(int(limit or 1), 1)):
            self.env.cr.execute(
                """
                    SELECT id
                      FROM sudo_cn_vat_period_reconciliation_run
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
            raise AccessError(_("只有合规管理员可以取消增值税期间勾稽。"))
        for run in self:
            if run.state != "queued":
                raise UserError(_("只有待处理的增值税期间勾稽可以取消。"))
            run.with_context(
                cn_vat_period_transition=_VAT_PERIOD_TRANSITION_MARKER
            ).write(
                {
                    "state": "cancelled",
                    "finished_at": fields.Datetime.now(),
                    "result_summary": _("批次在执行前取消。"),
                }
            )
            self.env["sudo.compliance.audit.event"]._log_records(
                run,
                "cn_vat_period_reconciliation.cancelled",
                previous_state="queued",
                new_state="cancelled",
            )
        return True

    def action_view_issues(self):
        self.ensure_one()
        action = self.env.ref(
            "sudo_country_pack_cn.action_cn_vat_period_reconciliation_issues"
        ).read()[0]
        action["domain"] = [("run_id", "=", self.id)]
        action["context"] = {}
        return action


class SudoChinaVatPeriodReconciliationIssue(models.Model):
    _name = "sudo.cn.vat.period.reconciliation.issue"
    _description = "China VAT Period Reconciliation Issue"
    _order = "sequence, issue_kind, source_area, code, id"
    _check_company_auto = True

    name = fields.Char(string="问题", required=True, readonly=True)
    sequence = fields.Integer(required=True, readonly=True)
    run_id = fields.Many2one(
        "sudo.cn.vat.period.reconciliation.run",
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
        readonly=True,
        index=True,
    )
    company_id = fields.Many2one(
        related="run_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    currency_id = fields.Many2one(
        related="run_id.currency_id",
        store=True,
        readonly=True,
    )
    code = fields.Char(string="问题代码", required=True, readonly=True, index=True)
    issue_kind = fields.Selection(
        [
            ("data_gap", "数据或控制问题"),
            ("difference", "金额差异"),
        ],
        string="问题类型",
        required=True,
        readonly=True,
        index=True,
    )
    severity = fields.Selection(
        [
            ("blocking", "阻断勾稽"),
            ("review", "需要复核"),
            ("info", "提示"),
        ],
        string="严重级别",
        required=True,
        readonly=True,
        index=True,
    )
    source_area = fields.Selection(
        [
            ("accounting", "账务"),
            ("einvoice", "电子发票"),
            ("filing", "增值税申报"),
            ("payment", "税款缴纳"),
            ("cross_source", "跨来源差异"),
        ],
        string="来源区域",
        required=True,
        readonly=True,
        index=True,
    )
    description = fields.Text(string="问题说明", required=True, readonly=True)
    action_hint = fields.Text(string="建议下一步", required=True, readonly=True)
    affected_record_count = fields.Integer(
        string="影响记录数",
        required=True,
        readonly=True,
    )
    has_left_amount = fields.Boolean(readonly=True)
    left_label = fields.Char(string="左侧口径", readonly=True)
    left_amount = fields.Monetary(
        string="左侧金额",
        currency_field="currency_id",
        readonly=True,
    )
    has_right_amount = fields.Boolean(readonly=True)
    right_label = fields.Char(string="右侧口径", readonly=True)
    right_amount = fields.Monetary(
        string="右侧金额",
        currency_field="currency_id",
        readonly=True,
    )
    has_difference = fields.Boolean(readonly=True)
    difference_amount = fields.Monetary(
        string="差异金额",
        currency_field="currency_id",
        readonly=True,
    )
    is_current_result = fields.Boolean(
        string="当前勾稽结果",
        compute="_compute_is_current_result",
        search="_search_is_current_result",
    )

    _issue_unique = models.Constraint(
        "unique(run_id, code)",
        "同一增值税期间勾稽批次中的问题代码必须唯一。",
    )

    @api.depends("run_id.state")
    def _compute_is_current_result(self):
        for issue in self:
            issue.is_current_result = issue.run_id.state == "succeeded"

    @api.model
    def _search_is_current_result(self, operator, value):
        if operator not in ("=", "!="):
            raise UserError(_("当前勾稽结果仅支持等于或不等于筛选。"))
        positive = (operator == "=" and bool(value)) or (
            operator == "!=" and not bool(value)
        )
        return [
            ("run_id.state", "=" if positive else "!=", "succeeded")
        ]

    @api.model_create_multi
    def create(self, vals_list):
        if (
            self.env.context.get("cn_vat_period_transition")
            is not _VAT_PERIOD_TRANSITION_MARKER
        ):
            raise AccessError(_("增值税期间勾稽问题只能由受控引擎创建。"))
        return super().create(vals_list)

    def write(self, values):
        raise AccessError(_("增值税期间勾稽问题不可修改，请重新执行勾稽。"))

    def unlink(self):
        raise AccessError(_("增值税期间勾稽问题属于审计记录，不可删除。"))

    def copy(self, default=None):
        raise AccessError(_("增值税期间勾稽问题不可复制。"))


class SudoChinaVatPeriodReconciliationWizard(models.TransientModel):
    _name = "sudo.cn.vat.period.reconciliation.wizard"
    _description = "Submit China VAT Four-Way Period Reconciliation"
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
    vat_tax_type_code = fields.Char(
        string="缴税数据增值税代码",
        required=True,
        default="VAT",
    )

    @api.model
    def default_get(self, field_names):
        values = super().default_get(field_names)
        today = fields.Date.context_today(self)
        start = today.replace(day=1)
        next_month = (start + timedelta(days=32)).replace(day=1)
        values.setdefault("period_start", start)
        values.setdefault("period_end", next_month - timedelta(days=1))
        if "profile_id" in field_names and not values.get("profile_id"):
            profile = self.env["sudo.compliance.profile"].search(
                [
                    ("company_id", "=", self.env.company.id),
                    ("country_id", "=", self.env.ref("base.cn").id),
                    ("active", "=", True),
                ],
                limit=1,
            )
            values["profile_id"] = profile.id
        return values

    def action_queue(self):
        self.ensure_one()
        run = self.env[
            "sudo.cn.vat.period.reconciliation.run"
        ].with_company(self.company_id).enqueue(
            self.profile_id,
            self.period_start,
            self.period_end,
            self.vat_tax_type_code,
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("增值税期间勾稽批次"),
            "res_model": "sudo.cn.vat.period.reconciliation.run",
            "res_id": run.id,
            "view_mode": "form",
            "target": "current",
        }
