from decimal import Decimal
import hashlib
import json

from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


CIT_PERIOD_ENGINE_VERSION = "19.0.1"
MAX_ACCOUNTING_LINES = 200000
MAX_FILING_RECORDS = 100
MAX_PAYMENT_RECORDS = 10000
_CIT_PERIOD_TRANSITION_MARKER = object()

SOURCE_STATES = [
    ("not_evaluated", "未评估"),
    ("available", "数据可勾稽"),
    ("no_data", "没有当前数据"),
    ("blocked", "数据存在阻断"),
]


def _checksum(payload):
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _safe_text(value, limit=1000):
    if value in (None, False):
        return False
    text = " ".join(str(value).split()).strip()
    return text[:limit] if text else False


def _amount_string(currency, value):
    rounded = currency.round(float(value or 0.0))
    return format(Decimal(str(rounded)), "f")


class SudoChinaCitPeriodReconciliationRun(models.Model):
    _name = "sudo.cn.cit.period.reconciliation.run"
    _description = "China CIT Book Return Payment Reconciliation Run"
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
        string="币种",
        store=True,
        readonly=True,
    )
    period_start = fields.Date(string="期间开始", required=True, readonly=True)
    period_end = fields.Date(string="期间结束", required=True, readonly=True)
    return_period_type = fields.Selection(
        [
            ("quarterly_prepayment", "季度预缴"),
            ("annual_reconciliation", "年度汇算清缴"),
            ("other", "其他申报期间"),
        ],
        string="申报期间类型",
        required=True,
        readonly=True,
        index=True,
    )
    cit_tax_type_code = fields.Char(
        string="缴退税数据所得税代码",
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
            ("insufficient_data", "数据不足，不能形成勾稽结论"),
            ("differences", "存在待复核差异"),
            ("aligned", "受控口径算术一致，不等于合规结论"),
        ],
        string="勾稽结论",
        required=True,
        default="not_evaluated",
        readonly=True,
        index=True,
    )
    engine_version = fields.Char(string="引擎版本", required=True, readonly=True)
    requested_at = fields.Datetime(string="提交时间", required=True, readonly=True)
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
        string="Odoo 会计利润数据",
        required=True,
        default="not_evaluated",
        readonly=True,
    )
    filing_source_state = fields.Selection(
        SOURCE_STATES,
        string="企业所得税申报数据",
        required=True,
        default="not_evaluated",
        readonly=True,
    )
    payment_source_state = fields.Selection(
        SOURCE_STATES,
        string="所得税缴退税数据",
        required=True,
        default="not_evaluated",
        readonly=True,
    )

    accounting_scope_id = fields.Many2one(
        "sudo.cn.cit.accounting.scope",
        string="会计利润口径版本",
        ondelete="restrict",
        check_company=True,
        readonly=True,
    )
    accounting_scope_line_count = fields.Integer(string="口径科目数", readonly=True)
    posted_accounting_line_count = fields.Integer(
        string="已过账损益分录数", readonly=True
    )
    draft_accounting_line_count = fields.Integer(
        string="未过账损益分录数", readonly=True
    )
    filing_record_id = fields.Many2one(
        "sudo.cn.cit.filing.record",
        string="企业所得税来源申报",
        ondelete="restrict",
        check_company=True,
        readonly=True,
    )
    payment_dataset_id = fields.Many2one(
        "sudo.cn.external.dataset",
        string="缴退税来源数据集",
        ondelete="restrict",
        check_company=True,
        readonly=True,
    )
    payment_record_ids = fields.Many2many(
        "sudo.cn.tax.payment.record",
        "sudo_cn_cit_period_run_payment_rel",
        "run_id",
        "payment_id",
        string="所得税缴退税记录",
        readonly=True,
    )
    payment_record_count = fields.Integer(string="缴退税记录数", readonly=True)

    ledger_profit_increase_amount = fields.Monetary(
        string="账簿利润增加项", currency_field="currency_id", readonly=True
    )
    ledger_profit_decrease_amount = fields.Monetary(
        string="账簿利润减少项", currency_field="currency_id", readonly=True
    )
    ledger_accounting_profit_amount = fields.Monetary(
        string="Odoo 账簿会计利润", currency_field="currency_id", readonly=True
    )

    has_filing_accounting_profit_amount = fields.Boolean(readonly=True)
    filing_accounting_profit_amount = fields.Monetary(
        string="申报会计利润", currency_field="currency_id", readonly=True
    )
    has_filing_adjustment_increase_amount = fields.Boolean(readonly=True)
    filing_adjustment_increase_amount = fields.Monetary(
        string="来源纳税调增额", currency_field="currency_id", readonly=True
    )
    has_filing_adjustment_decrease_amount = fields.Boolean(readonly=True)
    filing_adjustment_decrease_amount = fields.Monetary(
        string="来源纳税调减额", currency_field="currency_id", readonly=True
    )
    has_filing_taxable_income_amount = fields.Boolean(readonly=True)
    filing_taxable_income_amount = fields.Monetary(
        string="来源应纳税所得额", currency_field="currency_id", readonly=True
    )
    has_expected_taxable_income_amount = fields.Boolean(readonly=True)
    expected_taxable_income_amount = fields.Monetary(
        string="来源字段算术所得额", currency_field="currency_id", readonly=True
    )
    has_filing_tax_payable_amount = fields.Boolean(readonly=True)
    filing_tax_payable_amount = fields.Monetary(
        string="来源应纳所得税额", currency_field="currency_id", readonly=True
    )
    has_filing_tax_relief_amount = fields.Boolean(readonly=True)
    filing_tax_relief_amount = fields.Monetary(
        string="来源减免所得税额", currency_field="currency_id", readonly=True
    )
    has_filing_tax_credit_amount = fields.Boolean(readonly=True)
    filing_tax_credit_amount = fields.Monetary(
        string="来源抵免所得税额", currency_field="currency_id", readonly=True
    )
    has_filing_prepaid_tax_amount = fields.Boolean(readonly=True)
    filing_prepaid_tax_amount = fields.Monetary(
        string="来源已预缴所得税额", currency_field="currency_id", readonly=True
    )
    has_filing_payable_amount = fields.Boolean(readonly=True)
    filing_payable_amount = fields.Monetary(
        string="来源应补所得税额", currency_field="currency_id", readonly=True
    )
    has_filing_refundable_amount = fields.Boolean(readonly=True)
    filing_refundable_amount = fields.Monetary(
        string="来源应退所得税额", currency_field="currency_id", readonly=True
    )

    has_payment_amount = fields.Boolean(readonly=True)
    paid_principal_amount = fields.Monetary(
        string="缴款成功本金", currency_field="currency_id", readonly=True
    )
    reversed_principal_amount = fields.Monetary(
        string="已冲正本金", currency_field="currency_id", readonly=True
    )
    effective_paid_principal_amount = fields.Monetary(
        string="有效缴款本金", currency_field="currency_id", readonly=True
    )
    has_refund_amount = fields.Boolean(readonly=True)
    refunded_principal_amount = fields.Monetary(
        string="已退库本金", currency_field="currency_id", readonly=True
    )
    interest_amount = fields.Monetary(
        string="来源利息合计", currency_field="currency_id", readonly=True
    )
    penalty_amount = fields.Monetary(
        string="来源滞纳金罚款合计", currency_field="currency_id", readonly=True
    )

    has_ledger_filing_profit_difference = fields.Boolean(readonly=True)
    ledger_filing_profit_difference = fields.Monetary(
        string="账簿与申报会计利润差异",
        currency_field="currency_id",
        readonly=True,
    )
    has_filing_taxable_arithmetic_difference = fields.Boolean(readonly=True)
    filing_taxable_arithmetic_difference = fields.Monetary(
        string="申报所得额字段算术差异",
        currency_field="currency_id",
        readonly=True,
    )
    has_payable_payment_difference = fields.Boolean(readonly=True)
    payable_payment_difference = fields.Monetary(
        string="应补与有效缴款差异",
        currency_field="currency_id",
        readonly=True,
    )
    has_refundable_refund_difference = fields.Boolean(readonly=True)
    refundable_refund_difference = fields.Monetary(
        string="应退与退库差异",
        currency_field="currency_id",
        readonly=True,
    )

    issue_ids = fields.One2many(
        "sudo.cn.cit.period.reconciliation.issue",
        "run_id",
        string="勾稽问题",
        readonly=True,
    )
    issue_count = fields.Integer(string="问题数", readonly=True)
    blocking_issue_count = fields.Integer(string="阻断数", readonly=True)
    difference_issue_count = fields.Integer(string="差异数", readonly=True)
    warning_issue_count = fields.Integer(string="复核提示数", readonly=True)

    accounting_scope_snapshot_json = fields.Json(
        string="会计利润口径快照", readonly=True
    )
    accounting_scope_snapshot_checksum = fields.Char(
        string="会计利润口径快照 SHA-256", readonly=True
    )
    accounting_snapshot_json = fields.Json(string="账簿取数快照", readonly=True)
    accounting_snapshot_checksum = fields.Char(
        string="账簿取数 SHA-256", readonly=True
    )
    filing_snapshot_json = fields.Json(string="申报来源快照", readonly=True)
    filing_snapshot_checksum = fields.Char(string="申报来源 SHA-256", readonly=True)
    payment_snapshot_json = fields.Json(string="缴退税来源快照", readonly=True)
    payment_snapshot_checksum = fields.Char(string="缴退税来源 SHA-256", readonly=True)
    result_checksum = fields.Char(string="结果 SHA-256", readonly=True)
    result_integrity_state = fields.Selection(
        [
            ("not_available", "尚无结果"),
            ("verified", "结果完整性正常"),
            ("checksum_mismatch", "结果完整性异常"),
        ],
        string="结果完整性",
        compute="_compute_result_integrity_state",
    )
    result_summary = fields.Text(string="结果摘要", readonly=True)
    error_code = fields.Char(string="失败代码", readonly=True)

    @api.depends("profile_id", "period_start", "period_end", "return_period_type")
    def _compute_name(self):
        labels = dict(self._fields["return_period_type"].selection)
        for run in self:
            run.name = "%s / %s / %s - %s" % (
                run.profile_id.display_name or _("企业所得税账税勾稽"),
                labels.get(run.return_period_type, run.return_period_type or "-"),
                fields.Date.to_string(run.period_start) or "-",
                fields.Date.to_string(run.period_end) or "-",
            )

    def _compute_result_integrity_state(self):
        for run in self:
            if (
                run.state not in {"succeeded", "superseded"}
                or not run.result_checksum
            ):
                run.result_integrity_state = "not_available"
            elif run._current_result_checksum() == run.result_checksum:
                run.result_integrity_state = "verified"
            else:
                run.result_integrity_state = "checksum_mismatch"

    @api.model_create_multi
    def create(self, vals_list):
        if (
            self.env.context.get("cn_cit_period_transition")
            is not _CIT_PERIOD_TRANSITION_MARKER
        ):
            raise AccessError(_("企业所得税账税勾稽批次只能由受控流程创建。"))
        defaults = {
            "state": "queued",
            "conclusion_state": "not_evaluated",
            "engine_version": CIT_PERIOD_ENGINE_VERSION,
            "requested_at": fields.Datetime.now(),
            "requested_by_id": self.env.user.id,
            "started_at": False,
            "finished_at": False,
            "accounting_source_state": "not_evaluated",
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
            self.env.context.get("cn_cit_period_transition")
            is not _CIT_PERIOD_TRANSITION_MARKER
        ):
            raise AccessError(_("企业所得税账税勾稽批次只能由受控流程更新。"))
        return super().write(values)

    def unlink(self):
        raise AccessError(_("企业所得税账税勾稽批次属于审计记录，不可删除。"))

    @api.model
    def enqueue(
        self,
        profile,
        period_start,
        period_end,
        return_period_type,
        cit_tax_type_code,
    ):
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以提交企业所得税账税勾稽。"))
        profile.ensure_one()
        period_start = fields.Date.to_date(period_start)
        period_end = fields.Date.to_date(period_end)
        tax_type_code = (_safe_text(cit_tax_type_code, 128) or "").upper()
        allowed_period_types = {key for key, _label in self._fields["return_period_type"].selection}
        if not period_start or not period_end or period_start > period_end:
            raise ValidationError(_("请选择有效的勾稽期间。"))
        if return_period_type not in allowed_period_types:
            raise ValidationError(_("请选择有效的企业所得税申报期间类型。"))
        if not tax_type_code:
            raise ValidationError(_("请填写来源缴退税数据中的企业所得税代码。"))
        if profile.country_id != self.env.ref("base.cn"):
            raise UserError(_("只能对中国合规档案执行企业所得税账税勾稽。"))
        active = self.search(
            [
                ("profile_id", "=", profile.id),
                ("period_start", "=", period_start),
                ("period_end", "=", period_end),
                ("return_period_type", "=", return_period_type),
                ("state", "in", ("queued", "processing")),
            ],
            limit=1,
        )
        if active:
            raise UserError(_("相同档案、期间和申报类型已有待处理或处理中的勾稽。"))
        run = self.with_company(profile.company_id).with_context(
            cn_cit_period_transition=_CIT_PERIOD_TRANSITION_MARKER
        ).create(
            {
                "profile_id": profile.id,
                "period_start": period_start,
                "period_end": period_end,
                "return_period_type": return_period_type,
                "cit_tax_type_code": tax_type_code,
            }
        )
        self.env["sudo.compliance.audit.event"]._log_records(
            run,
            "cn_cit_period_reconciliation.queued",
            new_state="queued",
            details={
                "period_start": fields.Date.to_string(period_start),
                "period_end": fields.Date.to_string(period_end),
                "return_period_type": return_period_type,
                "cit_tax_type_code": tax_type_code,
                "engine_version": CIT_PERIOD_ENGINE_VERSION,
            },
        )
        return run.with_context(cn_cit_period_transition=None)

    def _add_issue(
        self,
        issues,
        code,
        severity,
        source_area,
        title,
        description,
        action_hint,
        *,
        issue_kind="data_gap",
        affected_record_count=0,
        left_label=False,
        left_amount=0.0,
        right_label=False,
        right_amount=0.0,
        difference=0.0,
    ):
        issues.append(
            {
                "name": _safe_text(title, 512),
                "sequence": len(issues) + 1,
                "code": _safe_text(code, 128),
                "issue_kind": issue_kind,
                "severity": severity,
                "source_area": source_area,
                "affected_record_count": max(int(affected_record_count or 0), 0),
                "description": _safe_text(description, 4000),
                "action_hint": _safe_text(action_hint, 4000),
                "has_difference": issue_kind == "difference",
                "left_label": _safe_text(left_label, 256),
                "left_amount": left_amount,
                "right_label": _safe_text(right_label, 256),
                "right_amount": right_amount,
                "difference_amount": difference,
            }
        )

    def _add_source_control_issues(self, issues, record, source_area, label):
        blocked = False
        if record.source_coverage_scope != "full":
            blocked = True
            self._add_issue(
                issues,
                f"{source_area.upper()}_SOURCE_NOT_FULL",
                "blocking",
                source_area,
                _("%(label)s未声明完整覆盖", label=label),
                _("部分或抽样来源不能证明当前期间数据完整。"),
                _("取得完整期间受控导出，封存并重新导入。"),
            )
        if record.source_integrity_state != "verified":
            blocked = True
            self._add_issue(
                issues,
                f"{source_area.upper()}_SOURCE_INTEGRITY_FAILED",
                "blocking",
                source_area,
                _("%(label)s封存完整性异常", label=label),
                _("来源文件或封存元数据已经变化。"),
                _("核对原始资料并创建受控替代数据集。"),
            )
        if record.source_authenticity_state == "official_tool_failed":
            blocked = True
            self._add_issue(
                issues,
                f"{source_area.upper()}_AUTHENTICITY_FAILED",
                "blocking",
                source_area,
                _("%(label)s真实性验证失败", label=label),
                _("来源记录明确标记受控真实性验证未通过。"),
                _("取得可验证来源并保留正式验证证据。"),
            )
        elif record.source_authenticity_state in {"not_checked", "unavailable"}:
            self._add_issue(
                issues,
                f"{source_area.upper()}_AUTHENTICITY_NOT_CONFIRMED",
                "review",
                source_area,
                _("%(label)s真实性尚未确认", label=label),
                _("结构和封存校验不能替代税务机关来源真实性确认。"),
                _("结合正式申报回执、完税凭证或受控验证工具复核。"),
            )
        if record.source_review_control_state == "exception":
            self._add_issue(
                issues,
                f"{source_area.upper()}_SINGLE_PERSON_EXCEPTION",
                "review",
                source_area,
                _("%(label)s采用单人复核例外", label=label),
                _("来源采集和封存由同一人员完成。"),
                _("在形成正式结论前安排独立人员复核来源资料。"),
            )
        return blocked

    def _collect_accounting(self, issues):
        self.ensure_one()
        scope_model = self.env["sudo.cn.cit.accounting.scope"].sudo().with_company(
            self.company_id
        )
        scopes = scope_model._for_profile_period(
            self.profile_id, self.period_start, self.period_end
        )
        if not scopes:
            self._add_issue(
                issues,
                "NO_VERIFIED_CIT_ACCOUNTING_SCOPE",
                "blocking",
                "accounting_scope",
                _("缺少覆盖当前期间的已核验会计利润口径"),
                _("系统不能自行猜测哪些 Odoo 科目构成会计利润。"),
                _("建立会计利润口径、同步损益科目、上传工作底稿并完成核验。"),
            )
            empty = {"schema": "sdoo.cn.cit-accounting-profit-scope.v1", "scope": None}
            return {
                "state": "no_data",
                "scope": scope_model.browse(),
                "lines": self.env["account.move.line"],
                "posted_count": 0,
                "draft_count": 0,
                "increase": 0.0,
                "decrease": 0.0,
                "profit": 0.0,
                "scope_snapshot": empty,
                "snapshot": {"schema": "sdoo.cn.cit-accounting-ledger.v1", "accounts": []},
            }
        if len(scopes) > 1:
            self._add_issue(
                issues,
                "MULTIPLE_CIT_ACCOUNTING_SCOPES",
                "blocking",
                "accounting_scope",
                _("当前期间存在多份已核验会计利润口径"),
                _("系统不会自动选择或合并重叠口径。"),
                _("撤销重叠核验并保留一份完整有效口径。"),
                affected_record_count=len(scopes),
            )
            scope = scopes[:1]
            blocked = True
        else:
            scope = scopes[0]
            blocked = False
        if scope._current_integrity_state() != "verified":
            blocked = True
            self._add_issue(
                issues,
                "CIT_ACCOUNTING_SCOPE_INTEGRITY_FAILED",
                "blocking",
                "accounting_scope",
                _("会计利润口径完整性异常"),
                _("口径字段、附件、科目代码、名称、类型或角色在核验后发生变化。"),
                _("核对变化，撤销核验后重新形成工作底稿并核验。"),
            )

        expected_accounts = scope._expected_accounts(self.company_id)
        missing_accounts = expected_accounts - scope.line_ids.account_id
        if missing_accounts:
            blocked = True
            self._add_issue(
                issues,
                "CIT_ACCOUNTING_SCOPE_COVERAGE_GAP",
                "blocking",
                "accounting_scope",
                _("会计利润口径未覆盖当前科目表"),
                _(
                    "核验后新增或恢复了 %(count)s 个有效损益科目，当前快照不能证明覆盖完整。",
                    count=len(missing_accounts),
                ),
                _("撤销口径核验，同步科目表并重新复核。"),
                affected_record_count=len(missing_accounts),
            )

        mappings = {line.account_id.id: line for line in scope.line_ids}
        move_lines = self.env["account.move.line"].sudo().with_company(
            self.company_id
        ).search(
            [
                ("company_id", "=", self.company_id.id),
                ("date", ">=", self.period_start),
                ("date", "<=", self.period_end),
                ("account_id", "in", list(mappings)),
                ("parent_state", "in", ("draft", "posted")),
            ],
            order="account_id, date, id",
            limit=MAX_ACCOUNTING_LINES + 1,
        )
        if len(move_lines) > MAX_ACCOUNTING_LINES:
            raise UserError(_("单次企业所得税勾稽的损益分录超过安全上限。"))
        posted = move_lines.filtered(lambda line: line.parent_state == "posted")
        draft = move_lines - posted
        if not posted:
            blocked = True
            self._add_issue(
                issues,
                "NO_POSTED_CIT_PROFIT_LINES",
                "blocking",
                "accounting",
                _("当前期间没有已过账损益分录"),
                _("系统无法从空的已过账损益范围证明会计利润为零。"),
                _("确认期间、公司和过账状态，必要时完成结账后重新勾稽。"),
            )
        if draft:
            self._add_issue(
                issues,
                "DRAFT_CIT_PROFIT_LINES_EXCLUDED",
                "review",
                "accounting",
                _("存在未过账损益分录"),
                _("未过账分录没有计入当前会计利润快照，后续过账可能改变结果。"),
                _("确认期间结账状态，并在过账完成后重新勾稽。"),
                affected_record_count=len(draft),
            )

        aggregates = {}
        digest = hashlib.sha256()
        for line in posted:
            mapping = mappings[line.account_id.id]
            item = {
                "line_id": line.id,
                "move_id": line.move_id.id,
                "date": fields.Date.to_string(line.date),
                "account_id": line.account_id.id,
                "debit": _amount_string(self.currency_id, line.debit),
                "credit": _amount_string(self.currency_id, line.credit),
                "balance": _amount_string(self.currency_id, line.balance),
            }
            digest.update(
                json.dumps(
                    item,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            digest.update(b"\n")
            bucket = aggregates.setdefault(
                line.account_id.id,
                {
                    "account_id": line.account_id.id,
                    "account_code": line.account_id.code,
                    "account_name": line.account_id.name,
                    "account_type": line.account_id.account_type,
                    "role": mapping.role,
                    "line_count": 0,
                    "debit": 0.0,
                    "credit": 0.0,
                },
            )
            bucket["line_count"] += 1
            bucket["debit"] += line.debit
            bucket["credit"] += line.credit

        increase = 0.0
        decrease = 0.0
        account_snapshots = []
        for account_id in sorted(
            aggregates,
            key=lambda item: (aggregates[item]["account_code"] or "", item),
        ):
            bucket = aggregates[account_id]
            if bucket["role"] == "profit_increase":
                contribution = bucket["credit"] - bucket["debit"]
                increase += contribution
            else:
                contribution = bucket["debit"] - bucket["credit"]
                decrease += contribution
            account_snapshots.append(
                {
                    **bucket,
                    "debit": _amount_string(self.currency_id, bucket["debit"]),
                    "credit": _amount_string(self.currency_id, bucket["credit"]),
                    "role_amount": _amount_string(self.currency_id, contribution),
                }
            )
        increase = self.currency_id.round(increase)
        decrease = self.currency_id.round(decrease)
        profit = self.currency_id.round(increase - decrease)
        scope_snapshot = scope._checksum_payload()
        snapshot = {
            "schema": "sdoo.cn.cit-accounting-ledger.v1",
            "company_id": self.company_id.id,
            "period_start": fields.Date.to_string(self.period_start),
            "period_end": fields.Date.to_string(self.period_end),
            "currency": self.currency_id.name,
            "posted_line_count": len(posted),
            "draft_line_count": len(draft),
            "posted_line_digest": digest.hexdigest(),
            "accounts": account_snapshots,
            "amounts": {
                "profit_increase": _amount_string(self.currency_id, increase),
                "profit_decrease": _amount_string(self.currency_id, decrease),
                "accounting_profit": _amount_string(self.currency_id, profit),
            },
        }
        return {
            "state": "blocked" if blocked else "available",
            "scope": scope,
            "lines": move_lines,
            "posted_count": len(posted),
            "draft_count": len(draft),
            "increase": increase,
            "decrease": decrease,
            "profit": profit,
            "scope_snapshot": scope_snapshot,
            "snapshot": snapshot,
        }

    def _collect_filing(self, issues):
        self.ensure_one()
        model = self.env["sudo.cn.cit.filing.record"].sudo().with_company(
            self.company_id
        )
        records = model.search(
            [
                ("profile_id", "=", self.profile_id.id),
                ("is_current_result", "=", True),
                ("period_start", "=", self.period_start),
                ("period_end", "=", self.period_end),
                ("return_period_type", "=", self.return_period_type),
            ],
            order="revision_number desc, submitted_at desc, id desc",
            limit=MAX_FILING_RECORDS + 1,
        )
        if len(records) > MAX_FILING_RECORDS:
            raise UserError(_("当前期间企业所得税申报记录超过安全上限。"))
        if not records:
            self._add_issue(
                issues,
                "NO_CURRENT_CIT_FILING",
                "blocking",
                "filing",
                _("没有完全匹配期间的当前企业所得税申报"),
                _("系统不会用其他期间、其他申报类型或旧导入结果替代。"),
                _("封存并导入对应期间和申报类型的完整来源申报。"),
            )
            empty = {"schema": "sdoo.cn.cit-filing-source.v1", "records": []}
            return {
                "state": "no_data",
                "record": model.browse(),
                "snapshot": empty,
                "amounts": {},
            }
        blocked = False
        if len(records) > 1:
            blocked = True
            self._add_issue(
                issues,
                "MULTIPLE_CURRENT_CIT_FILINGS",
                "blocking",
                "filing",
                _("同一期间存在多份当前企业所得税申报"),
                _("系统不会自动判断更正链或选择其中一份。"),
                _("核对更正申报关系，并通过受控替代数据集只保留一份当前结果。"),
                affected_record_count=len(records),
            )
        record = records[0]
        blocked = self._add_source_control_issues(
            issues, record, "filing", _("企业所得税申报")
        ) or blocked
        if record.quality_state == "error":
            blocked = True
            self._add_issue(
                issues,
                "CIT_FILING_QUALITY_ERROR",
                "blocking",
                "filing",
                _("企业所得税申报存在字段错误"),
                _("来源申报的主体、期间、币种或必要金额未通过标准化校验。"),
                _("查看申报台账问题，修正来源后重新封存和导入。"),
            )
        elif record.quality_state == "warning":
            self._add_issue(
                issues,
                "CIT_FILING_QUALITY_WARNING",
                "review",
                "filing",
                _("企业所得税申报存在数据警告"),
                _("来源申报可以读取，但仍有必须披露的数据限制。"),
                _("在形成报告前逐项复核申报台账警告。"),
            )
        if record.currency_id != self.currency_id:
            blocked = True
            self._add_issue(
                issues,
                "CIT_FILING_CURRENCY_MISMATCH",
                "blocking",
                "filing",
                _("申报币种与公司本位币不一致"),
                _("本版本不自动执行汇率换算或选择折算日。"),
                _("提供与公司本位币一致的受控申报值，或等待受控汇率模块。"),
            )
        if record.return_status not in {"submitted", "accepted", "amended"}:
            blocked = True
            self._add_issue(
                issues,
                "CIT_FILING_STATUS_NOT_EFFECTIVE",
                "blocking",
                "filing",
                _("申报状态不能作为当前有效来源"),
                _("草稿、作废或未知状态没有被解释为已经完成申报。"),
                _("取得最终申报状态和回执后重新导入。"),
            )

        required_profit_fields = (
            ("has_accounting_profit_amount", "会计利润总额"),
            ("has_adjustment_increase_amount", "纳税调增额"),
            ("has_adjustment_decrease_amount", "纳税调减额"),
            ("has_taxable_income_amount", "应纳税所得额"),
        )
        missing = [label for field_name, label in required_profit_fields if not record[field_name]]
        if missing:
            blocked = True
            self._add_issue(
                issues,
                "CIT_FILING_PROFIT_CHAIN_INCOMPLETE",
                "blocking",
                "filing",
                _("申报账税利润链字段不完整"),
                _("缺少：%(fields)s。系统不会把缺失金额按零处理。", fields="、".join(missing)),
                _("从来源申报中补齐字段并重新受控导入。"),
            )

        amount_fields = (
            "accounting_profit_amount",
            "adjustment_increase_amount",
            "adjustment_decrease_amount",
            "taxable_income_amount",
            "tax_payable_amount",
            "tax_relief_amount",
            "tax_credit_amount",
            "prepaid_tax_amount",
            "payable_amount",
            "refundable_amount",
        )
        amounts = {
            field_name: {
                "provided": bool(record[f"has_{field_name}"]),
                "amount": record[field_name],
            }
            for field_name in amount_fields
        }
        snapshot = {
            "schema": "sdoo.cn.cit-filing-source.v1",
            "record_id": record.id,
            "dataset_id": record.dataset_id.id,
            "parse_run_id": record.parse_run_id.id,
            "source_record_key": record.source_record_key,
            "return_period_type": record.return_period_type,
            "return_type_code": record.return_type_code,
            "return_status": record.return_status,
            "revision_number": record.revision_number,
            "record_checksum": record.record_checksum,
            "parse_run_checksum": record.parse_run_id.output_checksum,
            "dataset_checksum": record.dataset_id.seal_checksum,
            "amounts": {
                key: (
                    _amount_string(self.currency_id, value["amount"])
                    if value["provided"]
                    else None
                )
                for key, value in amounts.items()
            },
        }
        return {
            "state": "blocked" if blocked else "available",
            "record": record,
            "snapshot": snapshot,
            "amounts": amounts,
        }

    def _collect_payments(self, issues):
        self.ensure_one()
        dataset_model = self.env["sudo.cn.external.dataset"].sudo().with_company(
            self.company_id
        )
        candidates = dataset_model.search(
            [
                ("profile_id", "=", self.profile_id.id),
                ("dataset_type", "=", "tax_payment"),
                ("state", "=", "sealed"),
                ("coverage_scope", "=", "full"),
                ("period_start", "<=", self.period_start),
                ("period_end", ">=", self.period_end),
            ],
            order="period_start desc, period_end, id desc",
        )
        candidates = candidates.filtered(
            lambda dataset: dataset._current_integrity_state() == "verified"
            and dataset.current_tax_data_parse_run_id
            and dataset.current_tax_data_parse_run_id.state == "succeeded"
        )
        if not candidates:
            self._add_issue(
                issues,
                "NO_CURRENT_CIT_PAYMENT_DATASET",
                "blocking",
                "payment",
                _("没有覆盖当前税款所属期的完整缴退税数据集"),
                _("没有记录不能被解释为企业所得税无需缴款或退税。"),
                _("封存完整缴退税导出并执行受控导入；零记录数据集也必须保留来源证明。"),
            )
            empty = {"schema": "sdoo.cn.cit-payment-source.v1", "dataset": None, "records": []}
            return {
                "state": "no_data",
                "dataset": dataset_model.browse(),
                "records": self.env["sudo.cn.tax.payment.record"],
                "snapshot": empty,
                "paid": 0.0,
                "reversed": 0.0,
                "refunded": 0.0,
                "interest": 0.0,
                "penalty": 0.0,
            }
        blocked = False
        if len(candidates) > 1:
            blocked = True
            self._add_issue(
                issues,
                "MULTIPLE_CURRENT_CIT_PAYMENT_DATASETS",
                "blocking",
                "payment",
                _("当前期间存在多份完整缴退税数据集"),
                _("系统不会自动合并可能重复的缴款和退库记录。"),
                _("使用受控替代链保留一份完整当前数据集。"),
                affected_record_count=len(candidates),
            )
        dataset = candidates[0]
        pseudo_record = dataset.current_tax_data_parse_run_id.tax_payment_record_ids[:1]
        if pseudo_record:
            blocked = self._add_source_control_issues(
                issues, pseudo_record, "payment", _("所得税缴退税数据")
            ) or blocked
        else:
            if dataset.authenticity_state == "official_tool_failed":
                blocked = True
                self._add_issue(
                    issues,
                    "PAYMENT_AUTHENTICITY_FAILED",
                    "blocking",
                    "payment",
                    _("缴退税来源真实性验证失败"),
                    _("零记录来源仍明确标记受控真实性验证未通过。"),
                    _("取得可验证来源并保留正式验证证据。"),
                )
            elif dataset.authenticity_state in {"not_checked", "unavailable"}:
                self._add_issue(
                    issues,
                    "PAYMENT_AUTHENTICITY_NOT_CONFIRMED",
                    "review",
                    "payment",
                    _("缴退税来源真实性尚未确认"),
                    _("完整覆盖声明和零记录不能替代正式来源确认。"),
                    _("结合完税凭证、电子税务局导出或受控验证证据复核。"),
                )
            if dataset.review_control_state == "exception":
                self._add_issue(
                    issues,
                    "PAYMENT_SINGLE_PERSON_EXCEPTION",
                    "review",
                    "payment",
                    _("缴退税来源采用单人复核例外"),
                    _("来源采集和封存由同一人员完成。"),
                    _("在形成正式结论前安排独立人员复核。"),
                )

        run = dataset.current_tax_data_parse_run_id
        records = run.tax_payment_record_ids.filtered(
            lambda record: record.tax_type_code == self.cit_tax_type_code
            and record.period_start == self.period_start
            and record.period_end == self.period_end
        ).sorted(lambda record: (record.payment_date or fields.Date.today(), record.id))
        if len(records) > MAX_PAYMENT_RECORDS:
            raise UserError(_("当前期间企业所得税缴退税记录超过安全上限。"))

        paid = 0.0
        reversed_amount = 0.0
        refunded = 0.0
        interest = 0.0
        penalty = 0.0
        snapshots = []
        for record in records:
            record_blocked = False
            if record.quality_state == "error":
                record_blocked = True
                self._add_issue(
                    issues,
                    "CIT_PAYMENT_QUALITY_ERROR",
                    "blocking",
                    "payment",
                    _("所得税缴退税记录存在字段错误"),
                    _("至少一条记录的主体、期间、币种、状态或金额不可用。"),
                    _("查看缴税台账问题并重新导入修正来源。"),
                )
            if record.currency_id != self.currency_id:
                record_blocked = True
                self._add_issue(
                    issues,
                    "CIT_PAYMENT_CURRENCY_MISMATCH",
                    "blocking",
                    "payment",
                    _("缴退税币种与公司本位币不一致"),
                    _("本版本不自动执行汇率换算。"),
                    _("提供本位币受控缴退税数据或等待受控汇率模块。"),
                )
            effective_status = record.payment_status in {"succeeded", "reversed", "refunded"}
            if effective_status and not record.has_principal_amount:
                record_blocked = True
                self._add_issue(
                    issues,
                    "CIT_PAYMENT_PRINCIPAL_MISSING",
                    "blocking",
                    "payment",
                    _("有效缴退税记录缺少税款本金"),
                    _("总金额可能包含利息和滞纳金，不能直接与应补或应退所得税比较。"),
                    _("从来源中补齐税款本金并重新导入。"),
                )
            if record.payment_status == "unknown":
                record_blocked = True
                self._add_issue(
                    issues,
                    "CIT_PAYMENT_STATUS_UNKNOWN",
                    "blocking",
                    "payment",
                    _("所得税缴退税状态无法判断"),
                    _("系统不能判断记录应计入缴款、冲正、退库还是排除。"),
                    _("核对最终状态和回执后重新导入。"),
                )
            elif record.payment_status in {"pending", "failed"}:
                self._add_issue(
                    issues,
                    "NON_EFFECTIVE_CIT_PAYMENT_EXCLUDED",
                    "review",
                    "payment",
                    _("存在未生效所得税缴款"),
                    _("处理中或失败记录没有计入有效缴款本金。"),
                    _("取得最终缴款状态后重新导入。"),
                )

            if not record_blocked and record.has_principal_amount:
                if record.payment_status == "succeeded":
                    paid += record.principal_amount
                elif record.payment_status == "reversed":
                    reversed_amount += record.principal_amount
                elif record.payment_status == "refunded":
                    refunded += record.principal_amount
            if record.has_interest_amount:
                interest += record.interest_amount
            if record.has_penalty_amount:
                penalty += record.penalty_amount
            blocked = blocked or record_blocked
            snapshots.append(
                {
                    "record_id": record.id,
                    "source_record_key": record.source_record_key,
                    "payment_status": record.payment_status,
                    "payment_date": fields.Date.to_string(record.payment_date),
                    "principal_amount": (
                        _amount_string(self.currency_id, record.principal_amount)
                        if record.has_principal_amount
                        else None
                    ),
                    "interest_amount": (
                        _amount_string(self.currency_id, record.interest_amount)
                        if record.has_interest_amount
                        else None
                    ),
                    "penalty_amount": (
                        _amount_string(self.currency_id, record.penalty_amount)
                        if record.has_penalty_amount
                        else None
                    ),
                    "included": not record_blocked and effective_status,
                    "record_checksum": record.record_checksum,
                }
            )
        paid = self.currency_id.round(paid)
        reversed_amount = self.currency_id.round(reversed_amount)
        refunded = self.currency_id.round(refunded)
        interest = self.currency_id.round(interest)
        penalty = self.currency_id.round(penalty)
        snapshot = {
            "schema": "sdoo.cn.cit-payment-source.v1",
            "dataset": {
                "dataset_id": dataset.id,
                "parse_run_id": run.id,
                "dataset_checksum": dataset.seal_checksum,
                "parse_run_checksum": run.output_checksum,
                "coverage_scope": dataset.coverage_scope,
            },
            "tax_type_code": self.cit_tax_type_code,
            "records": snapshots,
            "amounts": {
                "paid_principal": _amount_string(self.currency_id, paid),
                "reversed_principal": _amount_string(self.currency_id, reversed_amount),
                "effective_paid_principal": _amount_string(
                    self.currency_id, paid - reversed_amount
                ),
                "refunded_principal": _amount_string(self.currency_id, refunded),
                "interest": _amount_string(self.currency_id, interest),
                "penalty": _amount_string(self.currency_id, penalty),
            },
        }
        return {
            "state": "blocked" if blocked else "available",
            "dataset": dataset,
            "records": records,
            "snapshot": snapshot,
            "paid": paid,
            "reversed": reversed_amount,
            "refunded": refunded,
            "interest": interest,
            "penalty": penalty,
        }

    def _add_comparison(
        self,
        issues,
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
        source_area="cross_source",
    ):
        difference = self.currency_id.round(left_amount - right_amount)
        values[has_field] = True
        values[difference_field] = difference
        if self.currency_id.is_zero(difference):
            return
        self._add_issue(
            issues,
            code,
            "review",
            source_area,
            title,
            _("两个受控金额口径在当前期间存在差异。"),
            action_hint,
            issue_kind="difference",
            left_label=left_label,
            left_amount=left_amount,
            right_label=right_label,
            right_amount=right_amount,
            difference=difference,
        )

    def _result_payload(self, values=None, issues=None):
        self.ensure_one()
        values = values or {}

        def value(field_name):
            return values[field_name] if field_name in values else self[field_name]

        def issue_value(issue, field_name):
            return (
                issue.get(field_name)
                if isinstance(issue, dict)
                else issue[field_name]
            )

        amount_fields = (
            "ledger_profit_increase_amount",
            "ledger_profit_decrease_amount",
            "ledger_accounting_profit_amount",
            "filing_accounting_profit_amount",
            "filing_adjustment_increase_amount",
            "filing_adjustment_decrease_amount",
            "filing_taxable_income_amount",
            "expected_taxable_income_amount",
            "filing_tax_payable_amount",
            "filing_tax_relief_amount",
            "filing_tax_credit_amount",
            "filing_prepaid_tax_amount",
            "filing_payable_amount",
            "filing_refundable_amount",
            "paid_principal_amount",
            "reversed_principal_amount",
            "effective_paid_principal_amount",
            "refunded_principal_amount",
            "interest_amount",
            "penalty_amount",
            "ledger_filing_profit_difference",
            "filing_taxable_arithmetic_difference",
            "payable_payment_difference",
            "refundable_refund_difference",
        )
        provided_fields = (
            "has_filing_accounting_profit_amount",
            "has_filing_adjustment_increase_amount",
            "has_filing_adjustment_decrease_amount",
            "has_filing_taxable_income_amount",
            "has_expected_taxable_income_amount",
            "has_filing_tax_payable_amount",
            "has_filing_tax_relief_amount",
            "has_filing_tax_credit_amount",
            "has_filing_prepaid_tax_amount",
            "has_filing_payable_amount",
            "has_filing_refundable_amount",
            "has_payment_amount",
            "has_refund_amount",
            "has_ledger_filing_profit_difference",
            "has_filing_taxable_arithmetic_difference",
            "has_payable_payment_difference",
            "has_refundable_refund_difference",
        )
        issue_items = issues
        if issue_items is None:
            issue_items = self.issue_ids.sorted(
                lambda issue: (
                    issue.sequence,
                    issue.issue_kind,
                    issue.source_area,
                    issue.code,
                    issue.id,
                )
            )
        issue_payload = []
        for issue in issue_items:
            has_difference = bool(issue_value(issue, "has_difference"))
            issue_payload.append(
                {
                    "sequence": issue_value(issue, "sequence"),
                    "code": issue_value(issue, "code"),
                    "name": issue_value(issue, "name"),
                    "severity": issue_value(issue, "severity"),
                    "issue_kind": issue_value(issue, "issue_kind"),
                    "source_area": issue_value(issue, "source_area"),
                    "affected_record_count": issue_value(
                        issue, "affected_record_count"
                    ),
                    "description": issue_value(issue, "description") or None,
                    "action_hint": issue_value(issue, "action_hint") or None,
                    "has_difference": has_difference,
                    "left_label": issue_value(issue, "left_label") or None,
                    "left_amount": (
                        _amount_string(
                            self.currency_id, issue_value(issue, "left_amount")
                        )
                        if has_difference
                        else None
                    ),
                    "right_label": issue_value(issue, "right_label") or None,
                    "right_amount": (
                        _amount_string(
                            self.currency_id, issue_value(issue, "right_amount")
                        )
                        if has_difference
                        else None
                    ),
                    "difference": (
                        _amount_string(
                            self.currency_id,
                            issue_value(issue, "difference_amount"),
                        )
                        if has_difference
                        else None
                    ),
                }
            )
        return {
            "schema": "sdoo.cn.cit-period-reconciliation-result.v1",
            "engine_version": self.engine_version,
            "profile_id": self.profile_id.id,
            "company_id": self.company_id.id,
            "period_start": fields.Date.to_string(self.period_start),
            "period_end": fields.Date.to_string(self.period_end),
            "return_period_type": self.return_period_type,
            "cit_tax_type_code": self.cit_tax_type_code,
            "conclusion_state": value("conclusion_state"),
            "source_states": {
                "accounting": value("accounting_source_state"),
                "filing": value("filing_source_state"),
                "payment": value("payment_source_state"),
            },
            "counts": {
                "accounting_scope_lines": value("accounting_scope_line_count"),
                "posted_accounting_lines": value("posted_accounting_line_count"),
                "draft_accounting_lines": value("draft_accounting_line_count"),
                "payment_records": value("payment_record_count"),
                "issues": value("issue_count"),
                "blocking": value("blocking_issue_count"),
                "differences": value("difference_issue_count"),
                "warnings": value("warning_issue_count"),
            },
            "amounts": {
                field_name: _amount_string(self.currency_id, value(field_name))
                for field_name in amount_fields
            },
            "provided": {
                field_name: bool(value(field_name))
                for field_name in provided_fields
            },
            "issues": issue_payload,
            "checksums": {
                "accounting_scope": value("accounting_scope_snapshot_checksum"),
                "accounting": value("accounting_snapshot_checksum"),
                "filing": value("filing_snapshot_checksum"),
                "payment": value("payment_snapshot_checksum"),
            },
        }

    def _current_result_checksum(self):
        self.ensure_one()
        return _checksum(self._result_payload())

    def _build_results(self):
        self.ensure_one()
        issues = []
        accounting = self._collect_accounting(issues)
        filing = self._collect_filing(issues)
        payments = self._collect_payments(issues)
        scope_checksum = _checksum(accounting["scope_snapshot"])
        accounting_checksum = _checksum(accounting["snapshot"])
        filing_checksum = _checksum(filing["snapshot"])
        payment_checksum = _checksum(payments["snapshot"])

        filing_amounts = filing["amounts"]

        def filing_value(name):
            return filing_amounts.get(name, {}).get("amount", 0.0)

        def filing_has(name):
            return bool(filing_amounts.get(name, {}).get("provided"))

        effective_paid = self.currency_id.round(
            payments["paid"] - payments["reversed"]
        )
        values = {
            "accounting_source_state": accounting["state"],
            "filing_source_state": filing["state"],
            "payment_source_state": payments["state"],
            "accounting_scope_id": accounting["scope"].id,
            "accounting_scope_line_count": len(accounting["scope"].line_ids),
            "posted_accounting_line_count": accounting["posted_count"],
            "draft_accounting_line_count": accounting["draft_count"],
            "filing_record_id": filing["record"].id,
            "payment_dataset_id": payments["dataset"].id,
            "payment_record_ids": [Command.set(payments["records"].ids)],
            "payment_record_count": len(payments["records"]),
            "ledger_profit_increase_amount": accounting["increase"],
            "ledger_profit_decrease_amount": accounting["decrease"],
            "ledger_accounting_profit_amount": accounting["profit"],
            "has_filing_accounting_profit_amount": filing_has("accounting_profit_amount"),
            "filing_accounting_profit_amount": filing_value("accounting_profit_amount"),
            "has_filing_adjustment_increase_amount": filing_has("adjustment_increase_amount"),
            "filing_adjustment_increase_amount": filing_value("adjustment_increase_amount"),
            "has_filing_adjustment_decrease_amount": filing_has("adjustment_decrease_amount"),
            "filing_adjustment_decrease_amount": filing_value("adjustment_decrease_amount"),
            "has_filing_taxable_income_amount": filing_has("taxable_income_amount"),
            "filing_taxable_income_amount": filing_value("taxable_income_amount"),
            "has_expected_taxable_income_amount": False,
            "expected_taxable_income_amount": 0.0,
            "has_filing_tax_payable_amount": filing_has("tax_payable_amount"),
            "filing_tax_payable_amount": filing_value("tax_payable_amount"),
            "has_filing_tax_relief_amount": filing_has("tax_relief_amount"),
            "filing_tax_relief_amount": filing_value("tax_relief_amount"),
            "has_filing_tax_credit_amount": filing_has("tax_credit_amount"),
            "filing_tax_credit_amount": filing_value("tax_credit_amount"),
            "has_filing_prepaid_tax_amount": filing_has("prepaid_tax_amount"),
            "filing_prepaid_tax_amount": filing_value("prepaid_tax_amount"),
            "has_filing_payable_amount": filing_has("payable_amount"),
            "filing_payable_amount": filing_value("payable_amount"),
            "has_filing_refundable_amount": filing_has("refundable_amount"),
            "filing_refundable_amount": filing_value("refundable_amount"),
            "has_payment_amount": payments["state"] == "available",
            "paid_principal_amount": payments["paid"],
            "reversed_principal_amount": payments["reversed"],
            "effective_paid_principal_amount": effective_paid,
            "has_refund_amount": payments["state"] == "available",
            "refunded_principal_amount": payments["refunded"],
            "interest_amount": payments["interest"],
            "penalty_amount": payments["penalty"],
            "has_ledger_filing_profit_difference": False,
            "ledger_filing_profit_difference": 0.0,
            "has_filing_taxable_arithmetic_difference": False,
            "filing_taxable_arithmetic_difference": 0.0,
            "has_payable_payment_difference": False,
            "payable_payment_difference": 0.0,
            "has_refundable_refund_difference": False,
            "refundable_refund_difference": 0.0,
            "accounting_scope_snapshot_json": accounting["scope_snapshot"],
            "accounting_scope_snapshot_checksum": scope_checksum,
            "accounting_snapshot_json": accounting["snapshot"],
            "accounting_snapshot_checksum": accounting_checksum,
            "filing_snapshot_json": filing["snapshot"],
            "filing_snapshot_checksum": filing_checksum,
            "payment_snapshot_json": payments["snapshot"],
            "payment_snapshot_checksum": payment_checksum,
        }

        if (
            accounting["state"] == "available"
            and filing["state"] == "available"
            and values["has_filing_accounting_profit_amount"]
        ):
            self._add_comparison(
                issues,
                values,
                "has_ledger_filing_profit_difference",
                "ledger_filing_profit_difference",
                "CIT_LEDGER_FILING_PROFIT_DIFFERENCE",
                _("账簿与申报会计利润存在差异"),
                _("Odoo 已过账损益口径"),
                accounting["profit"],
                _("来源申报会计利润"),
                values["filing_accounting_profit_amount"],
                _("逐项核对损益科目、结转凭证、期间调整和申报取数工作底稿。"),
            )

        profit_chain_fields = (
            "accounting_profit_amount",
            "adjustment_increase_amount",
            "adjustment_decrease_amount",
            "taxable_income_amount",
        )
        if filing["state"] == "available" and all(
            filing_has(field_name) for field_name in profit_chain_fields
        ):
            expected_taxable = self.currency_id.round(
                values["filing_accounting_profit_amount"]
                + values["filing_adjustment_increase_amount"]
                - values["filing_adjustment_decrease_amount"]
            )
            values["has_expected_taxable_income_amount"] = True
            values["expected_taxable_income_amount"] = expected_taxable
            self._add_comparison(
                issues,
                values,
                "has_filing_taxable_arithmetic_difference",
                "filing_taxable_arithmetic_difference",
                "CIT_FILING_TAXABLE_ARITHMETIC_DIFFERENCE",
                _("申报账税利润字段算术不一致"),
                _("会计利润 + 调增 - 调减"),
                expected_taxable,
                _("来源应纳税所得额"),
                values["filing_taxable_income_amount"],
                _("核对来源申报表栏次映射和未纳入汇总字段；该比较不判断调整是否合法。"),
                source_area="filing",
            )

        if filing["state"] == "available" and payments["state"] == "available":
            if values["has_filing_payable_amount"]:
                self._add_comparison(
                    issues,
                    values,
                    "has_payable_payment_difference",
                    "payable_payment_difference",
                    "CIT_PAYABLE_PAYMENT_DIFFERENCE",
                    _("应补所得税与有效缴款本金存在差异"),
                    _("来源应补所得税额"),
                    values["filing_payable_amount"],
                    _("缴款成功本金减已冲正本金"),
                    effective_paid,
                    _("核对申报回执、税款所属期、缴款状态、冲正和完税凭证。"),
                )
            if values["has_filing_refundable_amount"]:
                self._add_comparison(
                    issues,
                    values,
                    "has_refundable_refund_difference",
                    "refundable_refund_difference",
                    "CIT_REFUNDABLE_REFUND_DIFFERENCE",
                    _("应退所得税与已退库本金存在差异"),
                    _("来源应退所得税额"),
                    values["filing_refundable_amount"],
                    _("来源已退库本金"),
                    payments["refunded"],
                    _("核对退税申请、核准状态、退库日期和银行回单。"),
                )

        blocking_count = sum(issue["severity"] == "blocking" for issue in issues)
        difference_count = sum(issue["issue_kind"] == "difference" for issue in issues)
        warning_count = sum(
            issue["severity"] == "review" and issue["issue_kind"] != "difference"
            for issue in issues
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
                "issue_ids": [Command.clear()]
                + [Command.create(issue) for issue in issues],
                "issue_count": len(issues),
                "blocking_issue_count": blocking_count,
                "difference_issue_count": difference_count,
                "warning_issue_count": warning_count,
                "conclusion_state": conclusion,
            }
        )
        values["result_checksum"] = _checksum(self._result_payload(values, issues))
        return values

    def _mark_failed(self, code, summary):
        self.ensure_one()
        safe_code = _safe_text(code, 128) or "CIT_PERIOD_RECONCILIATION_FAILED"
        safe_summary = _safe_text(summary, 2000) or _("企业所得税账税勾稽失败。")
        self.with_context(
            cn_cit_period_transition=_CIT_PERIOD_TRANSITION_MARKER
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
            "cn_cit_period_reconciliation.failed",
            previous_state="processing",
            new_state="failed",
            details={"error_code": safe_code},
        )
        return False

    def _process(self):
        self.ensure_one()
        if self.state != "queued":
            raise UserError(_("只有待处理的企业所得税账税勾稽批次可以执行。"))
        self.with_context(
            cn_cit_period_transition=_CIT_PERIOD_TRANSITION_MARKER
        ).write({"state": "processing", "started_at": fields.Datetime.now()})
        self.env["sudo.compliance.audit.event"]._log_records(
            self,
            "cn_cit_period_reconciliation.processing",
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
                        ("return_period_type", "=", self.return_period_type),
                        ("state", "=", "succeeded"),
                        ("id", "!=", self.id),
                    ]
                )
                previous_runs.with_context(
                    cn_cit_period_transition=_CIT_PERIOD_TRANSITION_MARKER
                ).write({"state": "superseded"})
                conclusion = result_values["conclusion_state"]
                if conclusion == "insufficient_data":
                    summary = _(
                        "企业所得税账税勾稽已执行，但存在 %(count)s 项数据阻断，"
                        "不能形成金额一致或不一致结论。",
                        count=result_values["blocking_issue_count"],
                    )
                elif conclusion == "differences":
                    summary = _(
                        "账簿、申报及缴退税受控数据可比较，发现 %(count)s 项待复核差异；"
                        "差异不自动等同于少缴、多缴、违法或税务机关结论。",
                        count=result_values["difference_issue_count"],
                    )
                else:
                    summary = _(
                        "账簿、申报及缴退税金额在当前受控口径下算术一致；"
                        "该结果不证明纳税调整、税率、优惠、扣除或申报处理合法。"
                    )
                self.sudo().with_context(
                    cn_cit_period_transition=_CIT_PERIOD_TRANSITION_MARKER
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
            return self._mark_failed("CIT_PERIOD_INPUT_ERROR", exc)
        except Exception as exc:
            return self._mark_failed(
                "UNEXPECTED_CIT_PERIOD_FAILURE",
                _(
                    "企业所得税账税勾稽发生未预期错误：%(kind)s",
                    kind=type(exc).__name__,
                ),
            )
        for previous in previous_runs:
            self.env["sudo.compliance.audit.event"]._log_records(
                previous,
                "cn_cit_period_reconciliation.superseded",
                previous_state="succeeded",
                new_state="superseded",
                details={"replacement_run_id": self.id},
            )
        self.env["sudo.compliance.audit.event"]._log_records(
            self,
            "cn_cit_period_reconciliation.succeeded",
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
                      FROM sudo_cn_cit_period_reconciliation_run
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
            raise AccessError(_("只有合规管理员可以取消企业所得税账税勾稽。"))
        for run in self:
            if run.state != "queued":
                raise UserError(_("只有待处理的企业所得税账税勾稽可以取消。"))
            run.with_context(
                cn_cit_period_transition=_CIT_PERIOD_TRANSITION_MARKER
            ).write(
                {
                    "state": "cancelled",
                    "finished_at": fields.Datetime.now(),
                    "result_summary": _("批次在执行前取消。"),
                }
            )
            self.env["sudo.compliance.audit.event"]._log_records(
                run,
                "cn_cit_period_reconciliation.cancelled",
                previous_state="queued",
                new_state="cancelled",
            )
        return True

    def action_view_issues(self):
        self.ensure_one()
        action = self.env.ref(
            "sudo_country_pack_cn.action_cn_cit_period_reconciliation_issues"
        ).read()[0]
        action["domain"] = [("run_id", "=", self.id)]
        action["context"] = {}
        return action

    def action_open_accounting_scope(self):
        self.ensure_one()
        if not self.accounting_scope_id:
            raise UserError(_("当前批次没有关联会计利润口径。"))
        return {
            "type": "ir.actions.act_window",
            "name": _("企业所得税会计利润口径"),
            "res_model": "sudo.cn.cit.accounting.scope",
            "res_id": self.accounting_scope_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_open_filing_record(self):
        self.ensure_one()
        if not self.filing_record_id:
            raise UserError(_("当前批次没有关联企业所得税申报记录。"))
        return {
            "type": "ir.actions.act_window",
            "name": _("企业所得税申报台账"),
            "res_model": "sudo.cn.cit.filing.record",
            "res_id": self.filing_record_id.id,
            "view_mode": "form",
            "target": "current",
        }


class SudoChinaCitPeriodReconciliationIssue(models.Model):
    _name = "sudo.cn.cit.period.reconciliation.issue"
    _description = "China CIT Period Reconciliation Issue"
    _order = "sequence, issue_kind, source_area, code, id"
    _check_company_auto = True

    name = fields.Char(string="问题", required=True, readonly=True)
    sequence = fields.Integer(required=True, readonly=True)
    run_id = fields.Many2one(
        "sudo.cn.cit.period.reconciliation.run",
        string="勾稽批次",
        required=True,
        ondelete="restrict",
        check_company=True,
        readonly=True,
        index=True,
    )
    profile_id = fields.Many2one(
        related="run_id.profile_id", store=True, readonly=True, index=True
    )
    company_id = fields.Many2one(
        related="run_id.company_id", store=True, readonly=True, index=True
    )
    currency_id = fields.Many2one(
        related="run_id.currency_id", store=True, readonly=True
    )
    code = fields.Char(string="问题代码", required=True, readonly=True, index=True)
    issue_kind = fields.Selection(
        [("data_gap", "数据或控制问题"), ("difference", "金额差异")],
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
            ("accounting_scope", "会计利润口径"),
            ("accounting", "Odoo 账簿"),
            ("filing", "所得税申报"),
            ("payment", "缴款与退库"),
            ("cross_source", "跨来源比较"),
        ],
        string="问题来源",
        required=True,
        readonly=True,
        index=True,
    )
    affected_record_count = fields.Integer(string="影响记录数", readonly=True)
    description = fields.Text(string="原因与边界", readonly=True)
    action_hint = fields.Text(string="下一步建议", readonly=True)
    has_difference = fields.Boolean(readonly=True)
    left_label = fields.Char(string="左侧口径", readonly=True)
    left_amount = fields.Monetary(
        string="左侧金额", currency_field="currency_id", readonly=True
    )
    right_label = fields.Char(string="右侧口径", readonly=True)
    right_amount = fields.Monetary(
        string="右侧金额", currency_field="currency_id", readonly=True
    )
    difference_amount = fields.Monetary(
        string="差异金额", currency_field="currency_id", readonly=True
    )
    is_current_result = fields.Boolean(
        string="当前成功结果",
        compute="_compute_is_current_result",
        search="_search_is_current_result",
    )

    @api.depends("run_id.state")
    def _compute_is_current_result(self):
        for issue in self:
            issue.is_current_result = issue.run_id.state == "succeeded"

    @api.model
    def _search_is_current_result(self, operator, value):
        if operator not in ("=", "!="):
            raise UserError(_("当前结果仅支持等于或不等于筛选。"))
        positive = (operator == "=" and bool(value)) or (
            operator == "!=" and not bool(value)
        )
        return [("run_id.state", "=" if positive else "!=", "succeeded")]

    @api.model_create_multi
    def create(self, vals_list):
        if (
            self.env.context.get("cn_cit_period_transition")
            is not _CIT_PERIOD_TRANSITION_MARKER
        ):
            raise AccessError(_("企业所得税勾稽问题只能由受控引擎创建。"))
        return super().create(vals_list)

    def write(self, values):
        raise AccessError(_("企业所得税勾稽问题属于执行快照，不可修改。"))

    def unlink(self):
        raise AccessError(_("企业所得税勾稽问题属于执行快照，不可删除。"))

    def copy(self, default=None):
        raise AccessError(_("企业所得税勾稽问题不可复制。"))


class SudoChinaCitPeriodReconciliationWizard(models.TransientModel):
    _name = "sudo.cn.cit.period.reconciliation.wizard"
    _description = "Start China CIT Period Reconciliation"

    profile_id = fields.Many2one(
        "sudo.compliance.profile",
        string="合规档案",
        required=True,
        domain="[('country_id.code', '=', 'CN'), ('company_id', 'in', allowed_company_ids)]",
    )
    company_id = fields.Many2one(
        related="profile_id.company_id", string="公司", readonly=True
    )
    period_start = fields.Date(string="期间开始", required=True)
    period_end = fields.Date(string="期间结束", required=True)
    return_period_type = fields.Selection(
        [
            ("quarterly_prepayment", "季度预缴"),
            ("annual_reconciliation", "年度汇算清缴"),
            ("other", "其他申报期间"),
        ],
        string="申报期间类型",
        required=True,
        default="quarterly_prepayment",
    )
    cit_tax_type_code = fields.Char(
        string="缴退税数据所得税代码",
        required=True,
        help="必须与受控缴退税数据中的 tax_type_code 完全一致。",
    )

    @api.model
    def default_get(self, field_names):
        values = super().default_get(field_names)
        if "profile_id" in field_names and not values.get("profile_id"):
            profile = self.env["sudo.compliance.profile"].search(
                [
                    ("company_id", "=", self.env.company.id),
                    ("country_id", "=", self.env.ref("base.cn").id),
                ],
                limit=1,
            )
            values["profile_id"] = profile.id
        return values

    def action_queue(self):
        self.ensure_one()
        run = self.env["sudo.cn.cit.period.reconciliation.run"].with_company(
            self.company_id
        ).enqueue(
            self.profile_id,
            self.period_start,
            self.period_end,
            self.return_period_type,
            self.cit_tax_type_code,
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("企业所得税账税勾稽"),
            "res_model": "sudo.cn.cit.period.reconciliation.run",
            "res_id": run.id,
            "view_mode": "form",
            "target": "current",
        }
