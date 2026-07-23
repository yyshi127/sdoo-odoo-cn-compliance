from decimal import Decimal
import hashlib
import json

from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


IIT_PERIOD_ENGINE_VERSION = "19.0.2"
_IIT_PERIOD_SNAPSHOT_LANG = "en_US"
MAX_ACCOUNTING_LINES = 200000
MAX_SOURCE_RECORDS = 100
MAX_PAYMENT_RECORDS = 10000
_IIT_PERIOD_TRANSITION_MARKER = object()

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


class SudoChinaIitPeriodReconciliationRun(models.Model):
    _name = "sudo.cn.iit.period.reconciliation.run"
    _description = "China IIT Payroll Book Return Payment Reconciliation Run"
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
        related="profile_id.country_id", store=True, readonly=True
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id",
        string="币种",
        store=True,
        readonly=True,
    )
    period_start = fields.Date(string="期间开始", required=True, readonly=True)
    period_end = fields.Date(string="期间结束", required=True, readonly=True)
    iit_tax_type_code = fields.Char(
        string="缴税数据个税代码", required=True, readonly=True
    )
    state = fields.Selection(
        [
            ("queued", "待处理"),
            ("processing", "处理中"),
            ("succeeded", "已完成"),
            ("superseded", "已被替代"),
            ("failed", "失败"),
            ("cancelled", "已取消"),
        ],
        string="执行状态",
        required=True,
        default="queued",
        readonly=True,
        index=True,
    )
    conclusion_state = fields.Selection(
        [
            ("not_evaluated", "未评估"),
            ("insufficient_data", "数据不足"),
            ("differences", "存在待复核差异"),
            ("aligned", "当前口径算术一致"),
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
        default=IIT_PERIOD_ENGINE_VERSION,
        readonly=True,
    )
    requested_at = fields.Datetime(
        string="提交时间", required=True, default=fields.Datetime.now, readonly=True
    )
    requested_by_id = fields.Many2one(
        "res.users",
        string="提交人",
        required=True,
        default=lambda self: self.env.user,
        readonly=True,
    )
    started_at = fields.Datetime(string="开始时间", readonly=True)
    finished_at = fields.Datetime(string="完成时间", readonly=True)
    error_code = fields.Char(string="失败代码", readonly=True)
    result_summary = fields.Text(string="结果摘要", readonly=True)

    accounting_scope_state = fields.Selection(
        SOURCE_STATES, string="账务口径状态", default="not_evaluated", readonly=True
    )
    accounting_source_state = fields.Selection(
        SOURCE_STATES, string="Odoo 账簿状态", default="not_evaluated", readonly=True
    )
    payroll_source_state = fields.Selection(
        SOURCE_STATES, string="工资汇总状态", default="not_evaluated", readonly=True
    )
    filing_source_state = fields.Selection(
        SOURCE_STATES, string="个税申报状态", default="not_evaluated", readonly=True
    )
    payment_source_state = fields.Selection(
        SOURCE_STATES, string="缴退税状态", default="not_evaluated", readonly=True
    )

    accounting_scope_id = fields.Many2one(
        "sudo.cn.iit.accounting.scope",
        string="个税账务口径",
        ondelete="restrict",
        check_company=True,
        readonly=True,
    )
    payroll_summary_id = fields.Many2one(
        "sudo.cn.payroll.summary.record",
        string="工资薪酬汇总",
        ondelete="restrict",
        check_company=True,
        readonly=True,
        groups="sudo_global_finance.group_compliance_manager",
    )
    withholding_record_id = fields.Many2one(
        "sudo.cn.iit.withholding.record",
        string="个人所得税扣缴申报",
        ondelete="restrict",
        check_company=True,
        readonly=True,
        groups="sudo_global_finance.group_compliance_manager",
    )
    payment_dataset_id = fields.Many2one(
        "sudo.cn.external.dataset",
        string="缴退税数据集",
        ondelete="restrict",
        check_company=True,
        readonly=True,
    )
    payment_record_ids = fields.Many2many(
        "sudo.cn.tax.payment.record",
        "sudo_cn_iit_period_run_payment_rel",
        "run_id",
        "payment_id",
        string="缴退税记录",
        readonly=True,
        check_company=True,
    )
    posted_accounting_line_count = fields.Integer(
        string="已过账分录数", readonly=True
    )
    draft_accounting_line_count = fields.Integer(
        string="未过账分录数", readonly=True
    )
    payroll_record_count = fields.Integer(string="工资汇总记录数", readonly=True)
    filing_record_count = fields.Integer(string="个税申报记录数", readonly=True)
    payment_record_count = fields.Integer(string="缴退税记录数", readonly=True)

    has_ledger_payroll_expense_amount = fields.Boolean(readonly=True)
    ledger_payroll_expense_amount = fields.Monetary(
        string="账簿工资薪酬成本",
        currency_field="currency_id",
        readonly=True,
    )
    has_ledger_employee_payable_accrual_amount = fields.Boolean(readonly=True)
    ledger_employee_payable_accrual_amount = fields.Monetary(
        string="账簿应付职工薪酬贷方发生",
        currency_field="currency_id",
        readonly=True,
    )
    has_ledger_employee_payable_settlement_amount = fields.Boolean(readonly=True)
    ledger_employee_payable_settlement_amount = fields.Monetary(
        string="账簿应付职工薪酬借方发生",
        currency_field="currency_id",
        readonly=True,
    )
    has_ledger_iit_accrual_amount = fields.Boolean(readonly=True)
    ledger_iit_accrual_amount = fields.Monetary(
        string="账簿应交个人所得税贷方发生",
        currency_field="currency_id",
        readonly=True,
    )
    has_ledger_iit_settlement_amount = fields.Boolean(readonly=True)
    ledger_iit_settlement_amount = fields.Monetary(
        string="缴款日期应交个人所得税借方发生",
        currency_field="currency_id",
        readonly=True,
    )

    has_payroll_person_count = fields.Boolean(readonly=True)
    payroll_person_count = fields.Integer(string="工资汇总人数", readonly=True)
    has_payroll_gross_income_amount = fields.Boolean(readonly=True)
    payroll_gross_income_amount = fields.Monetary(
        string="工资汇总收入总额", currency_field="currency_id", readonly=True
    )
    has_payroll_withheld_iit_amount = fields.Boolean(readonly=True)
    payroll_withheld_iit_amount = fields.Monetary(
        string="工资汇总代扣个税", currency_field="currency_id", readonly=True
    )

    has_filing_person_count = fields.Boolean(readonly=True)
    filing_person_count = fields.Integer(string="个税申报人数", readonly=True)
    has_filing_income_amount = fields.Boolean(readonly=True)
    filing_income_amount = fields.Monetary(
        string="个税申报收入合计", currency_field="currency_id", readonly=True
    )
    has_filing_tax_calculated_amount = fields.Boolean(readonly=True)
    filing_tax_calculated_amount = fields.Monetary(
        string="个税申报应纳税额合计",
        currency_field="currency_id",
        readonly=True,
    )
    has_filing_payable_refundable_amount = fields.Boolean(readonly=True)
    filing_payable_refundable_amount = fields.Monetary(
        string="来源应补退税额合计",
        currency_field="currency_id",
        readonly=True,
    )
    has_filing_payable_amount = fields.Boolean(readonly=True)
    filing_payable_amount = fields.Monetary(
        string="按受控符号约定解释的应补税额",
        currency_field="currency_id",
        readonly=True,
    )
    has_filing_refundable_amount = fields.Boolean(readonly=True)
    filing_refundable_amount = fields.Monetary(
        string="按受控符号约定解释的应退税额",
        currency_field="currency_id",
        readonly=True,
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
        string="利息金额", currency_field="currency_id", readonly=True
    )
    penalty_amount = fields.Monetary(
        string="滞纳金及罚款", currency_field="currency_id", readonly=True
    )

    has_ledger_payroll_difference = fields.Boolean(readonly=True)
    ledger_payroll_difference = fields.Monetary(
        string="账簿成本与工资汇总差异",
        currency_field="currency_id",
        readonly=True,
    )
    has_employee_payable_payroll_difference = fields.Boolean(readonly=True)
    employee_payable_payroll_difference = fields.Monetary(
        string="应付薪酬计提与工资汇总差异",
        currency_field="currency_id",
        readonly=True,
    )
    has_filing_payroll_income_difference = fields.Boolean(readonly=True)
    filing_payroll_income_difference = fields.Monetary(
        string="个税申报与工资收入差异",
        currency_field="currency_id",
        readonly=True,
    )
    has_filing_payroll_iit_difference = fields.Boolean(readonly=True)
    filing_payroll_iit_difference = fields.Monetary(
        string="申报税额与工资代扣税差异",
        currency_field="currency_id",
        readonly=True,
    )
    has_ledger_payroll_iit_difference = fields.Boolean(readonly=True)
    ledger_payroll_iit_difference = fields.Monetary(
        string="账簿计提与工资代扣税差异",
        currency_field="currency_id",
        readonly=True,
    )
    has_ledger_payment_difference = fields.Boolean(readonly=True)
    ledger_payment_difference = fields.Monetary(
        string="账簿个税结算与缴款差异",
        currency_field="currency_id",
        readonly=True,
    )
    has_payable_payment_difference = fields.Boolean(readonly=True)
    payable_payment_difference = fields.Monetary(
        string="申报应补与有效缴款差异",
        currency_field="currency_id",
        readonly=True,
    )
    has_refundable_refund_difference = fields.Boolean(readonly=True)
    refundable_refund_difference = fields.Monetary(
        string="申报应退与已退库差异",
        currency_field="currency_id",
        readonly=True,
    )

    issue_ids = fields.One2many(
        "sudo.cn.iit.period.reconciliation.issue",
        "run_id",
        string="勾稽问题",
        readonly=True,
        copy=False,
    )
    issue_count = fields.Integer(string="问题数", readonly=True)
    blocking_issue_count = fields.Integer(string="阻断数", readonly=True)
    difference_issue_count = fields.Integer(string="差异数", readonly=True)
    warning_issue_count = fields.Integer(string="复核提示数", readonly=True)

    accounting_scope_snapshot_json = fields.Json(
        string="账务口径快照", readonly=True
    )
    accounting_scope_snapshot_checksum = fields.Char(
        string="账务口径 SHA-256", readonly=True
    )
    accounting_snapshot_json = fields.Json(string="账簿快照", readonly=True)
    accounting_snapshot_checksum = fields.Char(
        string="账簿 SHA-256", readonly=True
    )
    payroll_snapshot_json = fields.Json(string="工资汇总快照", readonly=True)
    payroll_snapshot_checksum = fields.Char(
        string="工资汇总 SHA-256", readonly=True
    )
    filing_snapshot_json = fields.Json(string="个税申报快照", readonly=True)
    filing_snapshot_checksum = fields.Char(
        string="个税申报 SHA-256", readonly=True
    )
    payment_snapshot_json = fields.Json(string="缴退税快照", readonly=True)
    payment_snapshot_checksum = fields.Char(
        string="缴退税 SHA-256", readonly=True
    )
    result_checksum = fields.Char(string="结果 SHA-256", readonly=True)
    result_integrity_state = fields.Selection(
        [
            ("unavailable", "尚无结果"),
            ("verified", "完整性正常"),
            ("checksum_mismatch", "结果已变化"),
        ],
        string="结果完整性",
        compute="_compute_result_integrity_state",
    )

    _period_valid = models.Constraint(
        "CHECK(period_start <= period_end)", "勾稽期间开始日不能晚于结束日。"
    )
    _active_period_unique = models.UniqueIndex(
        "(profile_id, period_start, period_end) "
        "WHERE state IN ('queued', 'processing')",
        "同一合规档案和期间只能有一个待处理或处理中的个税勾稽批次。",
    )

    @api.depends("profile_id", "period_start", "period_end")
    def _compute_name(self):
        for run in self:
            run.name = "%s / %s - %s" % (
                run.profile_id.display_name or _("个人所得税勾稽"),
                fields.Date.to_string(run.period_start) or "-",
                fields.Date.to_string(run.period_end) or "-",
            )

    @api.depends("state", "result_checksum")
    def _compute_result_integrity_state(self):
        for run in self:
            if run.state not in ("succeeded", "superseded") or not run.result_checksum:
                run.result_integrity_state = "unavailable"
            elif run._current_result_checksum() == run.result_checksum:
                run.result_integrity_state = "verified"
            else:
                run.result_integrity_state = "checksum_mismatch"

    @api.model_create_multi
    def create(self, vals_list):
        if (
            self.env.context.get("cn_iit_period_transition")
            is not _IIT_PERIOD_TRANSITION_MARKER
        ):
            raise AccessError(_("个人所得税勾稽批次只能由受控流程创建。"))
        for values in vals_list:
            values.update(
                {
                    "state": "queued",
                    "conclusion_state": "not_evaluated",
                    "engine_version": IIT_PERIOD_ENGINE_VERSION,
                    "requested_at": fields.Datetime.now(),
                    "requested_by_id": self.env.user.id,
                    "started_at": False,
                    "finished_at": False,
                    "error_code": False,
                    "result_summary": False,
                    "accounting_scope_state": "not_evaluated",
                    "accounting_source_state": "not_evaluated",
                    "payroll_source_state": "not_evaluated",
                    "filing_source_state": "not_evaluated",
                    "payment_source_state": "not_evaluated",
                    "issue_count": 0,
                    "blocking_issue_count": 0,
                    "difference_issue_count": 0,
                    "warning_issue_count": 0,
                    "result_checksum": False,
                }
            )
        return super().create(vals_list)

    def write(self, values):
        if (
            self.env.context.get("cn_iit_period_transition")
            is not _IIT_PERIOD_TRANSITION_MARKER
        ):
            raise AccessError(_("个人所得税勾稽批次只能由受控流程更新。"))
        return super().write(values)

    def unlink(self):
        raise AccessError(_("个人所得税勾稽批次属于审计记录，不可删除。"))

    def copy(self, default=None):
        raise AccessError(_("个人所得税勾稽批次不可复制。"))

    @api.model
    def enqueue(self, profile, period_start, period_end, iit_tax_type_code):
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以提交个人所得税勾稽。"))
        profile.ensure_one()
        period_start = fields.Date.to_date(period_start)
        period_end = fields.Date.to_date(period_end)
        tax_type_code = (_safe_text(iit_tax_type_code, 128) or "").upper()
        if not period_start or not period_end or period_start > period_end:
            raise ValidationError(_("请选择有效的勾稽期间。"))
        if not tax_type_code:
            raise ValidationError(_("请填写来源缴税数据中的个人所得税代码。"))
        if profile.country_id != self.env.ref("base.cn"):
            raise UserError(_("只能对中国合规档案执行个人所得税勾稽。"))
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
            raise UserError(_("相同档案和期间已有待处理或处理中的个税勾稽。"))
        run = self.with_company(profile.company_id).with_context(
            cn_iit_period_transition=_IIT_PERIOD_TRANSITION_MARKER
        ).create(
            {
                "profile_id": profile.id,
                "period_start": period_start,
                "period_end": period_end,
                "iit_tax_type_code": tax_type_code,
            }
        )
        self.env["sudo.compliance.audit.event"]._log_records(
            run,
            "cn_iit_period_reconciliation.queued",
            new_state="queued",
            details={
                "period_start": fields.Date.to_string(period_start),
                "period_end": fields.Date.to_string(period_end),
                "iit_tax_type_code": tax_type_code,
                "engine_version": IIT_PERIOD_ENGINE_VERSION,
            },
        )
        return run.with_context(cn_iit_period_transition=None)

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
        has_count_comparison=False,
        left_count=0,
        right_count=0,
        count_difference=0,
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
                "has_difference": (
                    issue_kind == "difference" and not has_count_comparison
                ),
                "left_label": _safe_text(left_label, 256),
                "left_amount": left_amount,
                "right_label": _safe_text(right_label, 256),
                "right_amount": right_amount,
                "difference_amount": difference,
                "has_count_comparison": has_count_comparison,
                "left_count": left_count,
                "right_count": right_count,
                "count_difference": count_difference,
            }
        )

    def _add_source_control_issues(self, issues, record, source_area, label):
        blocked = False
        if record.source_coverage_scope != "full":
            blocked = True
            self._add_issue(
                issues,
                "%s_SOURCE_NOT_FULL" % source_area.upper(),
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
                "%s_SOURCE_INTEGRITY_FAILED" % source_area.upper(),
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
                "%s_AUTHENTICITY_FAILED" % source_area.upper(),
                "blocking",
                source_area,
                _("%(label)s真实性验证失败", label=label),
                _("来源记录明确标记受控真实性验证未通过。"),
                _("取得可验证来源并保留正式验证证据。"),
            )
        elif record.source_authenticity_state in {"not_checked", "unavailable"}:
            self._add_issue(
                issues,
                "%s_AUTHENTICITY_NOT_CONFIRMED" % source_area.upper(),
                "review",
                source_area,
                _("%(label)s真实性尚未确认", label=label),
                _("结构和封存校验不能替代工资系统、税务机关或银行来源真实性确认。"),
                _("结合正式审批记录、申报回执或完税凭证复核。"),
            )
        if record.source_review_control_state == "exception":
            self._add_issue(
                issues,
                "%s_SINGLE_PERSON_EXCEPTION" % source_area.upper(),
                "review",
                source_area,
                _("%(label)s采用单人复核例外", label=label),
                _("来源采集和封存由同一人员完成。"),
                _("形成正式结论前安排独立人员复核来源资料。"),
            )
        return blocked

    def _empty_scope(self):
        return {
            "schema": "sdoo.cn.iit-accounting-scope.v1",
            "scope": None,
        }

    def _collect_scope(self, issues):
        scope_model = self.env["sudo.cn.iit.accounting.scope"].sudo().with_company(
            self.company_id
        )
        scopes = scope_model._for_profile_period(
            self.profile_id, self.period_start, self.period_end
        )
        if not scopes:
            self._add_issue(
                issues,
                "NO_VERIFIED_IIT_ACCOUNTING_SCOPE",
                "blocking",
                "accounting_scope",
                _("缺少覆盖当前期间的已核验个税账务口径"),
                _("系统不能根据科目名称或凭证摘要猜测工资和个人所得税金额。"),
                _("配置三个账务角色、来源结构和符号约定，上传工作底稿并完成核验。"),
            )
            return {
                "state": "no_data",
                "scope": scope_model.browse(),
                "snapshot": self._empty_scope(),
            }
        blocked = len(scopes) != 1
        scope = scopes[:1]
        if blocked:
            self._add_issue(
                issues,
                "MULTIPLE_IIT_ACCOUNTING_SCOPES",
                "blocking",
                "accounting_scope",
                _("当前期间存在多份已核验个税账务口径"),
                _("系统不会自动选择或合并重叠口径。"),
                _("撤销重叠核验并保留一份完整有效口径。"),
                affected_record_count=len(scopes),
            )
        if scope._current_integrity_state() != "verified":
            blocked = True
            self._add_issue(
                issues,
                "IIT_ACCOUNTING_SCOPE_INTEGRITY_FAILED",
                "blocking",
                "accounting_scope",
                _("个税账务口径完整性异常"),
                _("口径字段、附件、科目代码、名称、类型或角色在核验后发生变化。"),
                _("核对变化，撤销核验后重新形成工作底稿并核验。"),
            )
        return {
            "state": "blocked" if blocked else "available",
            "scope": scope,
            "snapshot": scope._checksum_payload(),
        }

    def _collect_payroll(self, issues, scope_data):
        model = self.env["sudo.cn.payroll.summary.record"].sudo().with_company(
            self.company_id
        )
        records = model.search(
            [
                ("profile_id", "=", self.profile_id.id),
                ("is_current_result", "=", True),
                ("period_start", "=", self.period_start),
                ("period_end", "=", self.period_end),
            ],
            order="approved_at desc, id desc",
            limit=MAX_SOURCE_RECORDS + 1,
        )
        if len(records) > MAX_SOURCE_RECORDS:
            raise UserError(_("当前期间工资薪酬汇总记录超过安全上限。"))
        if not records:
            self._add_issue(
                issues,
                "NO_CURRENT_PAYROLL_SUMMARY",
                "blocking",
                "payroll",
                _("没有完全匹配期间的当前工资薪酬汇总"),
                _("系统不会从员工档案、科目名称或凭证摘要制造工资汇总。"),
                _("从可靠工资系统取得不含人员身份信息的完整汇总，封存并导入。"),
            )
            return {
                "state": "no_data",
                "record": model.browse(),
                "records": records,
                "amounts": {},
                "snapshot": {"schema": "sdoo.cn.payroll-summary-source.v1", "records": []},
            }
        blocked = len(records) != 1
        if blocked:
            self._add_issue(
                issues,
                "MULTIPLE_CURRENT_PAYROLL_SUMMARIES",
                "blocking",
                "payroll",
                _("同一期间存在多份当前工资薪酬汇总"),
                _("系统不会自动选择或合并工资批次。"),
                _("通过受控替代数据集保留一份覆盖完整期间的当前汇总。"),
                affected_record_count=len(records),
            )
        record = records[0]
        blocked = self._add_source_control_issues(
            issues, record, "payroll", _("工资薪酬汇总")
        ) or blocked
        if record.quality_state == "error":
            blocked = True
            self._add_issue(
                issues,
                "PAYROLL_SUMMARY_QUALITY_ERROR",
                "blocking",
                "payroll",
                _("工资薪酬汇总存在字段错误"),
                _("来源主体、期间、人数、收入或代扣税额未通过标准化校验。"),
                _("查看工资汇总台账问题，修正来源后重新封存和导入。"),
            )
        elif record.quality_state == "warning":
            self._add_issue(
                issues,
                "PAYROLL_SUMMARY_QUALITY_WARNING",
                "review",
                "payroll",
                _("工资薪酬汇总存在数据警告"),
                _("来源可读取，但仍有必须在后续复核和报告中披露的限制。"),
                _("在形成报告前逐项复核工资汇总台账警告。"),
            )
        if record.payroll_status not in ("confirmed", "paid"):
            blocked = True
            self._add_issue(
                issues,
                "PAYROLL_SUMMARY_NOT_FINAL",
                "blocking",
                "payroll",
                _("工资薪酬汇总尚未确认或发放"),
                _("草稿、取消或未知状态不能作为最终期间汇总。"),
                _("取得已审批确认的工资汇总并保留审批引用。"),
            )
        if record.currency_id != self.currency_id:
            blocked = True
            self._add_issue(
                issues,
                "PAYROLL_CURRENCY_MISMATCH",
                "blocking",
                "payroll",
                _("工资汇总币种与公司本位币不一致"),
                _("本版本不自动执行工资数据汇率换算。"),
                _("提供本位币受控汇总或另行核验换算工作底稿。"),
            )
        scope = scope_data["scope"]
        if scope:
            source_schema = record.parse_run_id.source_schema or ""
            source_version = record.parse_run_id.source_schema_version or ""
            if (
                source_schema != scope.payroll_source_schema
                or source_version != scope.payroll_source_schema_version
            ):
                blocked = True
                self._add_issue(
                    issues,
                    "PAYROLL_SOURCE_SCHEMA_MISMATCH",
                    "blocking",
                    "payroll",
                    _("工资汇总来源结构与已核验口径不一致"),
                    _("字段语义或版本变化后不能沿用旧取数口径。"),
                    _("核对来源映射，形成并核验适配该结构版本的新账务口径。"),
                )
        amounts = {
            "has_person_count": record.has_declared_person_count,
            "person_count": record.declared_person_count,
            "has_gross_income": record.has_gross_income_amount,
            "gross_income": record.gross_income_amount,
            "has_withheld_iit": record.has_withheld_iit_amount,
            "withheld_iit": record.withheld_iit_amount,
        }
        snapshot = {
            "schema": "sdoo.cn.payroll-summary-source.v1",
            "record": {
                "record_id": record.id,
                "dataset_id": record.dataset_id.id,
                "parse_run_id": record.parse_run_id.id,
                "source_schema": record.parse_run_id.source_schema,
                "source_schema_version": record.parse_run_id.source_schema_version,
                "dataset_seal_checksum": record.parse_run_id.dataset_seal_checksum,
                "contract_checksum": record.parse_run_id.contract_checksum,
                "record_checksum": record.record_checksum,
                "payroll_status": record.payroll_status,
                "payroll_frequency": record.payroll_frequency,
                "payroll_run_reference": record.payroll_run_reference,
                "person_count": (
                    record.declared_person_count
                    if record.has_declared_person_count
                    else None
                ),
                "gross_income_amount": (
                    _amount_string(self.currency_id, record.gross_income_amount)
                    if record.has_gross_income_amount
                    else None
                ),
                "withheld_iit_amount": (
                    _amount_string(self.currency_id, record.withheld_iit_amount)
                    if record.has_withheld_iit_amount
                    else None
                ),
            },
        }
        return {
            "state": "blocked" if blocked else "available",
            "record": record,
            "records": records,
            "amounts": amounts,
            "snapshot": snapshot,
        }

    def _collect_filing(self, issues, scope_data):
        model = self.env["sudo.cn.iit.withholding.record"].sudo().with_company(
            self.company_id
        )
        records = model.search(
            [
                ("profile_id", "=", self.profile_id.id),
                ("is_current_result", "=", True),
                ("period_start", "=", self.period_start),
                ("period_end", "=", self.period_end),
            ],
            order="revision_number desc, submitted_at desc, id desc",
            limit=MAX_SOURCE_RECORDS + 1,
        )
        if len(records) > MAX_SOURCE_RECORDS:
            raise UserError(_("当前期间个人所得税扣缴申报记录超过安全上限。"))
        if not records:
            self._add_issue(
                issues,
                "NO_CURRENT_IIT_WITHHOLDING_RETURN",
                "blocking",
                "filing",
                _("没有完全匹配期间的当前个税扣缴申报"),
                _("系统不会用其他期间、旧导入结果或工资汇总替代来源申报。"),
                _("封存并导入对应期间的完整个人所得税扣缴申报。"),
            )
            return {
                "state": "no_data",
                "record": model.browse(),
                "records": records,
                "amounts": {},
                "snapshot": {"schema": "sdoo.cn.iit-withholding-source.v1", "records": []},
            }
        blocked = len(records) != 1
        if blocked:
            self._add_issue(
                issues,
                "MULTIPLE_CURRENT_IIT_WITHHOLDING_RETURNS",
                "blocking",
                "filing",
                _("同一期间存在多份当前个税扣缴申报"),
                _("系统不会自动判断更正链或选择其中一份。"),
                _("核对更正关系，通过受控替代数据集只保留一份当前结果。"),
                affected_record_count=len(records),
            )
        record = records[0]
        blocked = self._add_source_control_issues(
            issues, record, "filing", _("个人所得税扣缴申报")
        ) or blocked
        if record.quality_state == "error":
            blocked = True
            self._add_issue(
                issues,
                "IIT_FILING_QUALITY_ERROR",
                "blocking",
                "filing",
                _("个税扣缴申报存在字段错误"),
                _("来源主体、期间、人数、明细或必要金额未通过标准化校验。"),
                _("查看个税扣缴申报台账问题，修正来源后重新封存和导入。"),
            )
        elif record.quality_state == "warning":
            self._add_issue(
                issues,
                "IIT_FILING_QUALITY_WARNING",
                "review",
                "filing",
                _("个税扣缴申报存在数据警告"),
                _("来源可读取，但汇总、明细或状态仍有必须披露的限制。"),
                _("在形成报告前逐项复核个税扣缴申报台账警告。"),
            )
        if record.return_status not in ("submitted", "accepted", "amended"):
            blocked = True
            self._add_issue(
                issues,
                "IIT_FILING_NOT_SUBMITTED",
                "blocking",
                "filing",
                _("个税扣缴申报尚未形成有效提交状态"),
                _("草稿、取消或未知状态不能作为已申报来源。"),
                _("取得申报回执并重新导入受控当前结果。"),
            )
        if record.currency_id != self.currency_id:
            blocked = True
            self._add_issue(
                issues,
                "IIT_FILING_CURRENCY_MISMATCH",
                "blocking",
                "filing",
                _("个税申报币种与公司本位币不一致"),
                _("本版本不自动执行个税申报汇率换算。"),
                _("提供本位币申报来源或单独核验换算工作底稿。"),
            )
        scope = scope_data["scope"]
        if scope:
            source_schema = record.parse_run_id.source_schema or ""
            source_version = record.parse_run_id.source_schema_version or ""
            if (
                source_schema != scope.iit_source_schema
                or source_version != scope.iit_source_schema_version
            ):
                blocked = True
                self._add_issue(
                    issues,
                    "IIT_SOURCE_SCHEMA_MISMATCH",
                    "blocking",
                    "filing",
                    _("个税申报来源结构与已核验口径不一致"),
                    _("字段语义或应补退税额符号可能已经变化。"),
                    _("核对来源映射，形成并核验适配该结构版本的新账务口径。"),
                )
        if not record.has_total_tax_calculated_amount:
            blocked = True
            self._add_issue(
                issues,
                "MISSING_IIT_CALCULATED_TAX_TOTAL",
                "blocking",
                "filing",
                _("个税申报未提供应纳税额合计"),
                _("缺少该字段时不能与工资代扣和账簿计提金额比较。"),
                _("补充来源字段映射并重新执行受控导入。"),
            )

        payable = refundable = 0.0
        has_settlement = bool(record.has_total_payable_refundable_amount and scope)
        if has_settlement:
            signed = record.total_payable_refundable_amount
            if (
                scope.payable_refundable_sign_convention
                == "positive_payable_negative_refundable"
            ):
                payable = max(signed, 0.0)
                refundable = max(-signed, 0.0)
            else:
                payable = max(-signed, 0.0)
                refundable = max(signed, 0.0)
            payable = self.currency_id.round(payable)
            refundable = self.currency_id.round(refundable)

        amounts = {
            "has_person_count": record.has_declared_person_count,
            "person_count": record.declared_person_count,
            "has_income": record.has_total_income_amount,
            "income": record.total_income_amount,
            "has_tax_calculated": record.has_total_tax_calculated_amount,
            "tax_calculated": record.total_tax_calculated_amount,
            "has_payable_refundable": record.has_total_payable_refundable_amount,
            "payable_refundable": record.total_payable_refundable_amount,
            "has_settlement": has_settlement,
            "payable": payable,
            "refundable": refundable,
        }
        snapshot = {
            "schema": "sdoo.cn.iit-withholding-source.v1",
            "record": {
                "record_id": record.id,
                "dataset_id": record.dataset_id.id,
                "parse_run_id": record.parse_run_id.id,
                "source_schema": record.parse_run_id.source_schema,
                "source_schema_version": record.parse_run_id.source_schema_version,
                "dataset_seal_checksum": record.parse_run_id.dataset_seal_checksum,
                "contract_checksum": record.parse_run_id.contract_checksum,
                "record_checksum": record.record_checksum,
                "return_status": record.return_status,
                "submission_reference": record.submission_reference,
                "revision_number": record.revision_number,
                "person_count": (
                    record.declared_person_count
                    if record.has_declared_person_count
                    else None
                ),
                "income_amount": (
                    _amount_string(self.currency_id, record.total_income_amount)
                    if record.has_total_income_amount
                    else None
                ),
                "tax_calculated_amount": (
                    _amount_string(
                        self.currency_id, record.total_tax_calculated_amount
                    )
                    if record.has_total_tax_calculated_amount
                    else None
                ),
                "payable_refundable_amount": (
                    _amount_string(
                        self.currency_id, record.total_payable_refundable_amount
                    )
                    if record.has_total_payable_refundable_amount
                    else None
                ),
                "sign_convention": (
                    scope.payable_refundable_sign_convention if scope else None
                ),
                "interpreted_payable_amount": (
                    _amount_string(self.currency_id, payable)
                    if has_settlement
                    else None
                ),
                "interpreted_refundable_amount": (
                    _amount_string(self.currency_id, refundable)
                    if has_settlement
                    else None
                ),
            },
        }
        return {
            "state": "blocked" if blocked else "available",
            "record": record,
            "records": records,
            "amounts": amounts,
            "snapshot": snapshot,
        }

    def _collect_payments(self, issues):
        model = self.env["sudo.cn.tax.payment.record"].sudo().with_company(
            self.company_id
        )
        records = model.search(
            [
                ("profile_id", "=", self.profile_id.id),
                ("is_current_result", "=", True),
                ("period_start", "=", self.period_start),
                ("period_end", "=", self.period_end),
                ("tax_type_code", "=ilike", self.iit_tax_type_code),
            ],
            order="payment_date, id",
            limit=MAX_PAYMENT_RECORDS + 1,
        )
        if len(records) > MAX_PAYMENT_RECORDS:
            raise UserError(_("当前期间个人所得税缴退税记录超过安全上限。"))
        if not records:
            self._add_issue(
                issues,
                "NO_CURRENT_IIT_PAYMENT_DATA",
                "blocking",
                "payment",
                _("没有完全匹配期间和税种代码的当前缴退税数据"),
                _("没有记录不能证明未缴、无需缴款或尚未退库。"),
                _("取得覆盖当前税款所属期的完整缴退税导出并重新导入。"),
            )
            return {
                "state": "no_data",
                "records": records,
                "dataset": self.env["sudo.cn.external.dataset"],
                "paid": 0.0,
                "reversed": 0.0,
                "effective_paid": 0.0,
                "refunded": 0.0,
                "interest": 0.0,
                "penalty": 0.0,
                "payment_dates": [],
                "snapshot": {"schema": "sdoo.cn.iit-payment-source.v1", "records": []},
            }
        blocked = False
        datasets = records.mapped("dataset_id")
        if len(datasets) != 1:
            blocked = True
            self._add_issue(
                issues,
                "MULTIPLE_CURRENT_IIT_PAYMENT_DATASETS",
                "blocking",
                "payment",
                _("同一期间缴退税记录来自多份当前数据集"),
                _("重叠完整数据集可能造成重复汇总，系统不会自动去重。"),
                _("形成覆盖完整期间的单一受控替代数据集。"),
                affected_record_count=len(datasets),
            )
        for dataset in datasets:
            representative = records.filtered(
                lambda record: record.dataset_id == dataset
            )[:1]
            blocked = self._add_source_control_issues(
                issues, representative, "payment", _("个人所得税缴退税数据")
            ) or blocked

        paid = reversed_amount = refunded = interest = penalty = 0.0
        payment_dates = set()
        snapshots = []
        for record in records:
            if record.quality_state == "error":
                blocked = True
                self._add_issue(
                    issues,
                    "IIT_PAYMENT_QUALITY_ERROR",
                    "blocking",
                    "payment",
                    _("个人所得税缴退税记录存在字段错误"),
                    _("来源主体、期间、金额或必要引用未通过标准化校验。"),
                    _("查看税款缴纳台账问题，修正来源后重新封存和导入。"),
                    affected_record_count=1,
                )
            elif record.quality_state == "warning":
                self._add_issue(
                    issues,
                    "IIT_PAYMENT_QUALITY_WARNING",
                    "review",
                    "payment",
                    _("个人所得税缴退税记录存在数据警告"),
                    _("来源可读取，但仍有必须披露的状态或金额限制。"),
                    _("在形成报告前逐项复核税款缴纳台账警告。"),
                    affected_record_count=1,
                )
            if record.currency_id != self.currency_id:
                blocked = True
                self._add_issue(
                    issues,
                    "IIT_PAYMENT_CURRENCY_MISMATCH",
                    "blocking",
                    "payment",
                    _("缴退税币种与公司本位币不一致"),
                    _("本版本不自动执行缴退税汇率换算。"),
                    _("提供本位币缴退税来源或单独核验换算工作底稿。"),
                    affected_record_count=1,
                )
            principal = abs(float(record.principal_amount or 0.0))
            if record.payment_status in ("succeeded", "reversed", "refunded"):
                if not record.has_principal_amount:
                    blocked = True
                    self._add_issue(
                        issues,
                        "IIT_PAYMENT_PRINCIPAL_MISSING",
                        "blocking",
                        "payment",
                        _("已形成结果的缴退税记录缺少税款本金"),
                        _("总金额可能包含利息和滞纳金，不能替代税款本金。"),
                        _("补充税款本金字段并重新执行受控导入。"),
                        affected_record_count=1,
                    )
                if record.payment_date:
                    payment_dates.add(record.payment_date)
            if record.payment_status == "succeeded":
                paid += principal
            elif record.payment_status == "reversed":
                reversed_amount += principal
            elif record.payment_status == "refunded":
                refunded += principal
            elif record.payment_status in ("pending", "failed", "unknown"):
                self._add_issue(
                    issues,
                    "IIT_PAYMENT_NONFINAL_STATUS",
                    "review",
                    "payment",
                    _("存在未形成最终结果的个人所得税缴款记录"),
                    _("处理中、失败或未知状态记录没有计入有效缴款本金。"),
                    _("核对电子税务局、银行回单和后续状态。"),
                    affected_record_count=1,
                )
            if record.has_interest_amount:
                interest += record.interest_amount
            if record.has_penalty_amount:
                penalty += record.penalty_amount
            snapshots.append(
                {
                    "record_id": record.id,
                    "dataset_id": record.dataset_id.id,
                    "parse_run_id": record.parse_run_id.id,
                    "record_checksum": record.record_checksum,
                    "payment_status": record.payment_status,
                    "payment_date": fields.Date.to_string(record.payment_date),
                    "payment_reference": record.payment_reference,
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
                }
            )

        paid = self.currency_id.round(paid)
        reversed_amount = self.currency_id.round(reversed_amount)
        effective_paid = self.currency_id.round(paid - reversed_amount)
        refunded = self.currency_id.round(refunded)
        interest = self.currency_id.round(interest)
        penalty = self.currency_id.round(penalty)
        if effective_paid < 0:
            self._add_issue(
                issues,
                "IIT_PAYMENT_REVERSAL_EXCEEDS_SUCCESS",
                "review",
                "payment",
                _("个人所得税冲正本金大于当前来源缴款成功本金"),
                _("冲正可能引用更早数据集中的缴款，当前期间来源链需要人工复核。"),
                _("核对完整缴款与冲正链，必要时形成受控替代数据集。"),
            )
        snapshot = {
            "schema": "sdoo.cn.iit-payment-source.v1",
            "datasets": [
                {
                    "dataset_id": dataset.id,
                    "seal_checksum": dataset.seal_checksum,
                    "coverage_scope": dataset.coverage_scope,
                }
                for dataset in datasets.sorted("id")
            ],
            "records": snapshots,
            "amounts": {
                "paid_principal": _amount_string(self.currency_id, paid),
                "reversed_principal": _amount_string(
                    self.currency_id, reversed_amount
                ),
                "effective_paid_principal": _amount_string(
                    self.currency_id, effective_paid
                ),
                "refunded_principal": _amount_string(self.currency_id, refunded),
                "interest": _amount_string(self.currency_id, interest),
                "penalty": _amount_string(self.currency_id, penalty),
            },
        }
        return {
            "state": "blocked" if blocked else "available",
            "records": records,
            "dataset": datasets[:1] if len(datasets) == 1 else self.env["sudo.cn.external.dataset"],
            "paid": paid,
            "reversed": reversed_amount,
            "effective_paid": effective_paid,
            "refunded": refunded,
            "interest": interest,
            "penalty": penalty,
            "payment_dates": sorted(payment_dates),
            "snapshot": snapshot,
        }

    def _collect_accounting(self, issues, scope_data, payments):
        scope = scope_data["scope"]
        empty_snapshot = {
            "schema": "sdoo.cn.iit-accounting-ledger.v1",
            "accounts": [],
            "payment_dates": [],
        }
        if not scope:
            return {
                "state": "no_data",
                "posted_count": 0,
                "draft_count": 0,
                "payroll_expense": 0.0,
                "employee_accrual": 0.0,
                "employee_settlement": 0.0,
                "iit_accrual": 0.0,
                "iit_settlement": 0.0,
                "snapshot": empty_snapshot,
            }

        mappings = {line.account_id.id: line for line in scope.line_ids}
        account_ids = list(mappings)
        period_lines = self.env["account.move.line"].sudo().with_company(
            self.company_id
        ).search(
            [
                ("company_id", "=", self.company_id.id),
                ("date", ">=", self.period_start),
                ("date", "<=", self.period_end),
                ("account_id", "in", account_ids),
                ("parent_state", "in", ("draft", "posted")),
            ],
            order="account_id, date, id",
            limit=MAX_ACCOUNTING_LINES + 1,
        )
        if len(period_lines) > MAX_ACCOUNTING_LINES:
            raise UserError(_("单次个税勾稽的所属期会计分录超过安全上限。"))

        iit_account_ids = scope.line_ids.filtered(
            lambda line: line.role == "iit_payable"
        ).account_id.ids
        payment_dates = payments["payment_dates"]
        settlement_lines = self.env["account.move.line"]
        if payment_dates and iit_account_ids:
            settlement_lines = self.env["account.move.line"].sudo().with_company(
                self.company_id
            ).search(
                [
                    ("company_id", "=", self.company_id.id),
                    ("date", "in", payment_dates),
                    ("account_id", "in", iit_account_ids),
                    ("parent_state", "in", ("draft", "posted")),
                ],
                order="account_id, date, id",
                limit=MAX_ACCOUNTING_LINES + 1,
            )
            if len(settlement_lines) > MAX_ACCOUNTING_LINES:
                raise UserError(_("单次个税勾稽的缴款日期会计分录超过安全上限。"))

        posted_period = period_lines.filtered(
            lambda line: line.parent_state == "posted"
        )
        posted_settlement = settlement_lines.filtered(
            lambda line: line.parent_state == "posted"
        )
        all_lines = period_lines | settlement_lines
        draft_lines = all_lines.filtered(lambda line: line.parent_state == "draft")
        if not posted_period:
            self._add_issue(
                issues,
                "NO_POSTED_IIT_PERIOD_ACCOUNTING_LINES",
                "review",
                "accounting",
                _("当前期间没有已过账的个税口径会计分录"),
                _("零笔分录可能是真实零业务，也可能是尚未记账或期间未结账。"),
                _("结合工资汇总、结账状态和总账工作底稿确认后再形成正式结论。"),
            )
        if draft_lines:
            self._add_issue(
                issues,
                "DRAFT_IIT_ACCOUNTING_LINES_EXCLUDED",
                "review",
                "accounting",
                _("存在未过账的个税口径会计分录"),
                _("未过账分录没有计入快照，后续过账可能改变勾稽结果。"),
                _("确认期间结账状态，并在过账完成后重新勾稽。"),
                affected_record_count=len(draft_lines),
            )

        aggregates = {}
        period_digest = hashlib.sha256()
        settlement_digest = hashlib.sha256()
        payroll_expense = employee_accrual = employee_settlement = 0.0
        iit_accrual = iit_settlement = 0.0

        for line in posted_period:
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
            period_digest.update(
                json.dumps(
                    item,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            period_digest.update(b"\n")
            bucket = aggregates.setdefault(
                line.account_id.id,
                {
                    "account_id": line.account_id.id,
                    "account_code": line.account_id.code,
                    "account_name": line.account_id.name,
                    "account_type": line.account_id.account_type,
                    "role": mapping.role,
                    "period_line_count": 0,
                    "period_debit": 0.0,
                    "period_credit": 0.0,
                    "payment_date_line_count": 0,
                    "payment_date_debit": 0.0,
                    "payment_date_credit": 0.0,
                },
            )
            bucket["period_line_count"] += 1
            bucket["period_debit"] += line.debit
            bucket["period_credit"] += line.credit
            if mapping.role == "payroll_expense":
                payroll_expense += line.debit - line.credit
            elif mapping.role == "employee_payable":
                employee_accrual += line.credit
                employee_settlement += line.debit
            elif mapping.role == "iit_payable":
                iit_accrual += line.credit

        for line in posted_settlement:
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
            settlement_digest.update(
                json.dumps(
                    item,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            settlement_digest.update(b"\n")
            bucket = aggregates.setdefault(
                line.account_id.id,
                {
                    "account_id": line.account_id.id,
                    "account_code": line.account_id.code,
                    "account_name": line.account_id.name,
                    "account_type": line.account_id.account_type,
                    "role": mapping.role,
                    "period_line_count": 0,
                    "period_debit": 0.0,
                    "period_credit": 0.0,
                    "payment_date_line_count": 0,
                    "payment_date_debit": 0.0,
                    "payment_date_credit": 0.0,
                },
            )
            bucket["payment_date_line_count"] += 1
            bucket["payment_date_debit"] += line.debit
            bucket["payment_date_credit"] += line.credit
            iit_settlement += line.debit

        payroll_expense = self.currency_id.round(payroll_expense)
        employee_accrual = self.currency_id.round(employee_accrual)
        employee_settlement = self.currency_id.round(employee_settlement)
        iit_accrual = self.currency_id.round(iit_accrual)
        iit_settlement = self.currency_id.round(iit_settlement)
        account_snapshots = []
        for account_id in sorted(
            aggregates,
            key=lambda item: (aggregates[item]["role"], aggregates[item]["account_code"] or "", item),
        ):
            bucket = aggregates[account_id]
            account_snapshots.append(
                {
                    **bucket,
                    "period_debit": _amount_string(
                        self.currency_id, bucket["period_debit"]
                    ),
                    "period_credit": _amount_string(
                        self.currency_id, bucket["period_credit"]
                    ),
                    "payment_date_debit": _amount_string(
                        self.currency_id, bucket["payment_date_debit"]
                    ),
                    "payment_date_credit": _amount_string(
                        self.currency_id, bucket["payment_date_credit"]
                    ),
                }
            )
        snapshot = {
            "schema": "sdoo.cn.iit-accounting-ledger.v1",
            "company_id": self.company_id.id,
            "period_start": fields.Date.to_string(self.period_start),
            "period_end": fields.Date.to_string(self.period_end),
            "payment_dates": [fields.Date.to_string(date) for date in payment_dates],
            "currency": self.currency_id.name,
            "posted_period_line_count": len(posted_period),
            "posted_payment_date_line_count": len(posted_settlement),
            "draft_line_count": len(draft_lines),
            "period_line_digest": period_digest.hexdigest(),
            "payment_date_line_digest": settlement_digest.hexdigest(),
            "accounts": account_snapshots,
            "amounts": {
                "payroll_expense": _amount_string(
                    self.currency_id, payroll_expense
                ),
                "employee_payable_credit": _amount_string(
                    self.currency_id, employee_accrual
                ),
                "employee_payable_debit": _amount_string(
                    self.currency_id, employee_settlement
                ),
                "iit_payable_credit": _amount_string(
                    self.currency_id, iit_accrual
                ),
                "iit_payable_payment_date_debit": _amount_string(
                    self.currency_id, iit_settlement
                ),
            },
        }
        return {
            "state": (
                "blocked" if scope_data["state"] != "available" else "available"
            ),
            "posted_count": len(posted_period | posted_settlement),
            "draft_count": len(draft_lines),
            "payroll_expense": payroll_expense,
            "employee_accrual": employee_accrual,
            "employee_settlement": employee_settlement,
            "iit_accrual": iit_accrual,
            "iit_settlement": iit_settlement,
            "snapshot": snapshot,
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
        *,
        source_area="cross_source",
    ):
        difference = self.currency_id.round(left_amount - right_amount)
        values[has_field] = True
        values[difference_field] = difference
        if not self.currency_id.is_zero(difference):
            self._add_issue(
                issues,
                code,
                "review",
                source_area,
                title,
                _(
                    "%(left)s与%(right)s在当前受控口径下不一致；差异不自动等同于少缴、"
                    "多缴、违法或税务机关结论。",
                    left=left_label,
                    right=right_label,
                ),
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

        def record_id(field_name):
            item = value(field_name)
            if hasattr(item, "id"):
                item = item.id
            return item or None

        monetary_fields = (
            "ledger_payroll_expense_amount",
            "ledger_employee_payable_accrual_amount",
            "ledger_employee_payable_settlement_amount",
            "ledger_iit_accrual_amount",
            "ledger_iit_settlement_amount",
            "payroll_gross_income_amount",
            "payroll_withheld_iit_amount",
            "filing_income_amount",
            "filing_tax_calculated_amount",
            "filing_payable_refundable_amount",
            "filing_payable_amount",
            "filing_refundable_amount",
            "paid_principal_amount",
            "reversed_principal_amount",
            "effective_paid_principal_amount",
            "refunded_principal_amount",
            "interest_amount",
            "penalty_amount",
            "ledger_payroll_difference",
            "employee_payable_payroll_difference",
            "filing_payroll_income_difference",
            "filing_payroll_iit_difference",
            "ledger_payroll_iit_difference",
            "ledger_payment_difference",
            "payable_payment_difference",
            "refundable_refund_difference",
        )
        boolean_fields = (
            "has_ledger_payroll_expense_amount",
            "has_ledger_employee_payable_accrual_amount",
            "has_ledger_employee_payable_settlement_amount",
            "has_ledger_iit_accrual_amount",
            "has_ledger_iit_settlement_amount",
            "has_payroll_person_count",
            "has_payroll_gross_income_amount",
            "has_payroll_withheld_iit_amount",
            "has_filing_person_count",
            "has_filing_income_amount",
            "has_filing_tax_calculated_amount",
            "has_filing_payable_refundable_amount",
            "has_filing_payable_amount",
            "has_filing_refundable_amount",
            "has_payment_amount",
            "has_refund_amount",
            "has_ledger_payroll_difference",
            "has_employee_payable_payroll_difference",
            "has_filing_payroll_income_difference",
            "has_filing_payroll_iit_difference",
            "has_ledger_payroll_iit_difference",
            "has_ledger_payment_difference",
            "has_payable_payment_difference",
            "has_refundable_refund_difference",
        )
        if issues is None:
            issue_payload = [
                {
                    "sequence": issue.sequence,
                    "code": issue.code,
                    "issue_kind": issue.issue_kind,
                    "severity": issue.severity,
                    "source_area": issue.source_area,
                    "affected_record_count": issue.affected_record_count,
                    "description": issue.description or None,
                    "action_hint": issue.action_hint or None,
                    "has_difference": issue.has_difference,
                    "left_label": issue.left_label or None,
                    "left_amount": _amount_string(
                        self.currency_id, issue.left_amount
                    ),
                    "right_label": issue.right_label or None,
                    "right_amount": _amount_string(
                        self.currency_id, issue.right_amount
                    ),
                    "difference_amount": _amount_string(
                        self.currency_id, issue.difference_amount
                    ),
                    "has_count_comparison": issue.has_count_comparison,
                    "left_count": issue.left_count,
                    "right_count": issue.right_count,
                    "count_difference": issue.count_difference,
                }
                for issue in self.issue_ids.sorted("sequence")
            ]
        else:
            issue_payload = [
                {
                    "sequence": issue["sequence"],
                    "code": issue["code"],
                    "issue_kind": issue["issue_kind"],
                    "severity": issue["severity"],
                    "source_area": issue["source_area"],
                    "affected_record_count": issue["affected_record_count"],
                    "description": issue["description"] or None,
                    "action_hint": issue["action_hint"] or None,
                    "has_difference": issue["has_difference"],
                    "left_label": issue["left_label"] or None,
                    "left_amount": _amount_string(
                        self.currency_id, issue["left_amount"]
                    ),
                    "right_label": issue["right_label"] or None,
                    "right_amount": _amount_string(
                        self.currency_id, issue["right_amount"]
                    ),
                    "difference_amount": _amount_string(
                        self.currency_id, issue["difference_amount"]
                    ),
                    "has_count_comparison": issue["has_count_comparison"],
                    "left_count": issue["left_count"],
                    "right_count": issue["right_count"],
                    "count_difference": issue["count_difference"],
                }
                for issue in issues
            ]
        return {
            "schema": "sdoo.cn.iit-period-reconciliation-result.v1",
            "engine_version": self.engine_version,
            "profile_id": self.profile_id.id,
            "company_id": self.company_id.id,
            "period_start": fields.Date.to_string(self.period_start),
            "period_end": fields.Date.to_string(self.period_end),
            "iit_tax_type_code": self.iit_tax_type_code,
            "source_states": {
                "accounting_scope": value("accounting_scope_state"),
                "accounting": value("accounting_source_state"),
                "payroll": value("payroll_source_state"),
                "filing": value("filing_source_state"),
                "payment": value("payment_source_state"),
            },
            "source_record_ids": {
                "accounting_scope_id": record_id("accounting_scope_id"),
                "payroll_summary_id": record_id("payroll_summary_id"),
                "withholding_record_id": record_id("withholding_record_id"),
                "payment_dataset_id": record_id("payment_dataset_id"),
            },
            "counts": {
                "posted_accounting_lines": value("posted_accounting_line_count"),
                "draft_accounting_lines": value("draft_accounting_line_count"),
                "payroll_records": value("payroll_record_count"),
                "filing_records": value("filing_record_count"),
                "payment_records": value("payment_record_count"),
                "payroll_persons": value("payroll_person_count"),
                "filing_persons": value("filing_person_count"),
                "issues": value("issue_count"),
                "blocking": value("blocking_issue_count"),
                "differences": value("difference_issue_count"),
                "warnings": value("warning_issue_count"),
            },
            "provided": {field_name: bool(value(field_name)) for field_name in boolean_fields},
            "amounts": {
                field_name: _amount_string(self.currency_id, value(field_name))
                for field_name in monetary_fields
            },
            "conclusion_state": value("conclusion_state"),
            "snapshots": {
                "accounting_scope": value("accounting_scope_snapshot_json"),
                "accounting": value("accounting_snapshot_json"),
                "payroll": value("payroll_snapshot_json"),
                "filing": value("filing_snapshot_json"),
                "payment": value("payment_snapshot_json"),
            },
            "issues": issue_payload,
        }

    def _current_result_checksum(self):
        self.ensure_one()
        return _checksum(self._result_payload())

    def _build_results(self):
        self.ensure_one()
        issues = []
        scope_data = self._collect_scope(issues)
        payroll = self._collect_payroll(issues, scope_data)
        filing = self._collect_filing(issues, scope_data)
        payments = self._collect_payments(issues)
        accounting = self._collect_accounting(issues, scope_data, payments)

        payroll_amounts = payroll["amounts"]
        filing_amounts = filing["amounts"]
        scope_checksum = _checksum(scope_data["snapshot"])
        accounting_checksum = _checksum(accounting["snapshot"])
        payroll_checksum = _checksum(payroll["snapshot"])
        filing_checksum = _checksum(filing["snapshot"])
        payment_checksum = _checksum(payments["snapshot"])

        values = {
            "accounting_scope_state": scope_data["state"],
            "accounting_source_state": accounting["state"],
            "payroll_source_state": payroll["state"],
            "filing_source_state": filing["state"],
            "payment_source_state": payments["state"],
            "accounting_scope_id": scope_data["scope"].id or False,
            "payroll_summary_id": payroll["record"].id or False,
            "withholding_record_id": filing["record"].id or False,
            "payment_dataset_id": payments["dataset"].id or False,
            "payment_record_ids": [Command.set(payments["records"].ids)],
            "posted_accounting_line_count": accounting["posted_count"],
            "draft_accounting_line_count": accounting["draft_count"],
            "payroll_record_count": len(payroll["records"]),
            "filing_record_count": len(filing["records"]),
            "payment_record_count": len(payments["records"]),
            "has_ledger_payroll_expense_amount": accounting["state"] == "available",
            "ledger_payroll_expense_amount": accounting["payroll_expense"],
            "has_ledger_employee_payable_accrual_amount": accounting["state"] == "available",
            "ledger_employee_payable_accrual_amount": accounting["employee_accrual"],
            "has_ledger_employee_payable_settlement_amount": accounting["state"] == "available",
            "ledger_employee_payable_settlement_amount": accounting["employee_settlement"],
            "has_ledger_iit_accrual_amount": accounting["state"] == "available",
            "ledger_iit_accrual_amount": accounting["iit_accrual"],
            "has_ledger_iit_settlement_amount": accounting["state"] == "available",
            "ledger_iit_settlement_amount": accounting["iit_settlement"],
            "has_payroll_person_count": payroll_amounts.get("has_person_count", False),
            "payroll_person_count": payroll_amounts.get("person_count", 0),
            "has_payroll_gross_income_amount": payroll_amounts.get("has_gross_income", False),
            "payroll_gross_income_amount": payroll_amounts.get("gross_income", 0.0),
            "has_payroll_withheld_iit_amount": payroll_amounts.get("has_withheld_iit", False),
            "payroll_withheld_iit_amount": payroll_amounts.get("withheld_iit", 0.0),
            "has_filing_person_count": filing_amounts.get("has_person_count", False),
            "filing_person_count": filing_amounts.get("person_count", 0),
            "has_filing_income_amount": filing_amounts.get("has_income", False),
            "filing_income_amount": filing_amounts.get("income", 0.0),
            "has_filing_tax_calculated_amount": filing_amounts.get("has_tax_calculated", False),
            "filing_tax_calculated_amount": filing_amounts.get("tax_calculated", 0.0),
            "has_filing_payable_refundable_amount": filing_amounts.get("has_payable_refundable", False),
            "filing_payable_refundable_amount": filing_amounts.get("payable_refundable", 0.0),
            "has_filing_payable_amount": filing_amounts.get("has_settlement", False),
            "filing_payable_amount": filing_amounts.get("payable", 0.0),
            "has_filing_refundable_amount": filing_amounts.get("has_settlement", False),
            "filing_refundable_amount": filing_amounts.get("refundable", 0.0),
            "has_payment_amount": payments["state"] == "available",
            "paid_principal_amount": payments["paid"],
            "reversed_principal_amount": payments["reversed"],
            "effective_paid_principal_amount": payments["effective_paid"],
            "has_refund_amount": payments["state"] == "available",
            "refunded_principal_amount": payments["refunded"],
            "interest_amount": payments["interest"],
            "penalty_amount": payments["penalty"],
            "has_ledger_payroll_difference": False,
            "ledger_payroll_difference": 0.0,
            "has_employee_payable_payroll_difference": False,
            "employee_payable_payroll_difference": 0.0,
            "has_filing_payroll_income_difference": False,
            "filing_payroll_income_difference": 0.0,
            "has_filing_payroll_iit_difference": False,
            "filing_payroll_iit_difference": 0.0,
            "has_ledger_payroll_iit_difference": False,
            "ledger_payroll_iit_difference": 0.0,
            "has_ledger_payment_difference": False,
            "ledger_payment_difference": 0.0,
            "has_payable_payment_difference": False,
            "payable_payment_difference": 0.0,
            "has_refundable_refund_difference": False,
            "refundable_refund_difference": 0.0,
            "accounting_scope_snapshot_json": scope_data["snapshot"],
            "accounting_scope_snapshot_checksum": scope_checksum,
            "accounting_snapshot_json": accounting["snapshot"],
            "accounting_snapshot_checksum": accounting_checksum,
            "payroll_snapshot_json": payroll["snapshot"],
            "payroll_snapshot_checksum": payroll_checksum,
            "filing_snapshot_json": filing["snapshot"],
            "filing_snapshot_checksum": filing_checksum,
            "payment_snapshot_json": payments["snapshot"],
            "payment_snapshot_checksum": payment_checksum,
        }

        if (
            payroll["state"] == "available"
            and filing["state"] == "available"
            and values["has_payroll_person_count"]
            and values["has_filing_person_count"]
            and values["payroll_person_count"] != values["filing_person_count"]
        ):
            self._add_issue(
                issues,
                "IIT_PAYROLL_FILING_PERSON_COUNT_DIFFERENCE",
                "review",
                "cross_source",
                _("工资汇总人数与个税申报人数不一致"),
                _("人数差异可能来自所得项目、离职补发、零申报或来源范围差异。"),
                _("按受控假名明细和工资批次工作底稿复核范围，不得在普通问题记录中写入姓名证件。"),
                issue_kind="difference",
                has_count_comparison=True,
                left_label=_("工资汇总人数"),
                right_label=_("个税申报人数"),
                left_count=values["payroll_person_count"],
                right_count=values["filing_person_count"],
                count_difference=(
                    values["payroll_person_count"] - values["filing_person_count"]
                ),
            )

        if accounting["state"] == "available" and payroll["state"] == "available":
            self._add_comparison(
                issues,
                values,
                "has_ledger_payroll_difference",
                "ledger_payroll_difference",
                "IIT_LEDGER_PAYROLL_EXPENSE_DIFFERENCE",
                _("账簿工资成本与工资汇总收入存在差异"),
                _("Odoo 工资薪酬成本净额"),
                accounting["payroll_expense"],
                _("受控工资汇总收入总额"),
                payroll_amounts["gross_income"],
                _("核对工资成本口径、非应税福利、跨期计提、冲销和工资批次范围。"),
            )
            self._add_comparison(
                issues,
                values,
                "has_employee_payable_payroll_difference",
                "employee_payable_payroll_difference",
                "IIT_EMPLOYEE_PAYABLE_PAYROLL_DIFFERENCE",
                _("应付职工薪酬计提与工资汇总存在差异"),
                _("应付职工薪酬贷方发生"),
                accounting["employee_accrual"],
                _("受控工资汇总收入总额"),
                payroll_amounts["gross_income"],
                _("核对计提凭证、单位承担项目、非工资项目、重分类和跨期差异。"),
            )
            self._add_comparison(
                issues,
                values,
                "has_ledger_payroll_iit_difference",
                "ledger_payroll_iit_difference",
                "IIT_LEDGER_PAYROLL_WITHHOLDING_DIFFERENCE",
                _("账簿个税计提与工资汇总代扣税存在差异"),
                _("应交个人所得税贷方发生"),
                accounting["iit_accrual"],
                _("受控工资汇总代扣个人所得税"),
                payroll_amounts["withheld_iit"],
                _("核对代扣税计提、以前期间调整、冲销和非工资所得代扣。"),
            )

        if payroll["state"] == "available" and filing["state"] == "available":
            self._add_comparison(
                issues,
                values,
                "has_filing_payroll_income_difference",
                "filing_payroll_income_difference",
                "IIT_FILING_PAYROLL_INCOME_DIFFERENCE",
                _("个税申报收入与工资汇总收入存在差异"),
                _("个税申报收入合计"),
                filing_amounts["income"],
                _("受控工资汇总收入总额"),
                payroll_amounts["gross_income"],
                _("核对所得项目、免税项目、离职补发、跨期工资和来源字段映射。"),
            )
            self._add_comparison(
                issues,
                values,
                "has_filing_payroll_iit_difference",
                "filing_payroll_iit_difference",
                "IIT_FILING_PAYROLL_TAX_DIFFERENCE",
                _("个税申报税额与工资汇总代扣税存在差异"),
                _("个税申报应纳税额合计"),
                filing_amounts["tax_calculated"],
                _("受控工资汇总代扣个人所得税"),
                payroll_amounts["withheld_iit"],
                _("核对累计预扣、减免税、以前期间已缴税额、补退税和工资批次范围。"),
            )

        if accounting["state"] == "available" and payments["state"] == "available":
            self._add_comparison(
                issues,
                values,
                "has_ledger_payment_difference",
                "ledger_payment_difference",
                "IIT_LEDGER_PAYMENT_DIFFERENCE",
                _("账簿个税结算与受控缴款本金存在差异"),
                _("缴款日期应交个人所得税借方发生"),
                accounting["iit_settlement"],
                _("缴款成功本金减已冲正本金"),
                payments["effective_paid"],
                _("核对缴款日期凭证、银行回单、冲正、合并缴款和税款所属期。"),
            )

        if filing["state"] == "available" and payments["state"] == "available":
            self._add_comparison(
                issues,
                values,
                "has_payable_payment_difference",
                "payable_payment_difference",
                "IIT_PAYABLE_PAYMENT_DIFFERENCE",
                _("个税申报应补税额与有效缴款本金存在差异"),
                _("按受控符号约定解释的应补税额"),
                filing_amounts["payable"],
                _("缴款成功本金减已冲正本金"),
                payments["effective_paid"],
                _("核对申报回执、符号约定、税款所属期、缴款状态和完税凭证。"),
            )
            self._add_comparison(
                issues,
                values,
                "has_refundable_refund_difference",
                "refundable_refund_difference",
                "IIT_REFUNDABLE_REFUND_DIFFERENCE",
                _("个税申报应退税额与已退库本金存在差异"),
                _("按受控符号约定解释的应退税额"),
                filing_amounts["refundable"],
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
        safe_code = _safe_text(code, 128) or "IIT_PERIOD_RECONCILIATION_FAILED"
        safe_summary = _safe_text(summary, 2000) or _("个人所得税勾稽失败。")
        self.with_context(
            cn_iit_period_transition=_IIT_PERIOD_TRANSITION_MARKER
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
            "cn_iit_period_reconciliation.failed",
            previous_state="processing",
            new_state="failed",
            details={"error_code": safe_code},
        )
        return False

    def _process(self):
        self.ensure_one()
        if self.state != "queued":
            raise UserError(_("只有待处理的个人所得税勾稽批次可以执行。"))
        self.with_context(
            cn_iit_period_transition=_IIT_PERIOD_TRANSITION_MARKER
        ).write({"state": "processing", "started_at": fields.Datetime.now()})
        self.env["sudo.compliance.audit.event"]._log_records(
            self,
            "cn_iit_period_reconciliation.processing",
            previous_state="queued",
            new_state="processing",
        )
        previous_runs = self.browse()
        try:
            with self.env.cr.savepoint():
                result_values = self.with_context(
                    lang=_IIT_PERIOD_SNAPSHOT_LANG
                )._build_results()
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
                    cn_iit_period_transition=_IIT_PERIOD_TRANSITION_MARKER
                ).write({"state": "superseded"})
                conclusion = result_values["conclusion_state"]
                if conclusion == "insufficient_data":
                    summary = _(
                        "个人所得税勾稽已执行，但存在 %(count)s 项数据阻断，"
                        "不能形成金额一致或不一致结论。",
                        count=result_values["blocking_issue_count"],
                    )
                elif conclusion == "differences":
                    summary = _(
                        "账簿、工资汇总、个税申报及缴退税数据可比较，发现 %(count)s 项"
                        "待复核差异；差异不自动等同于少缴、多缴或违法。",
                        count=result_values["difference_issue_count"],
                    )
                else:
                    summary = _(
                        "账簿、工资汇总、个税申报及缴退税金额在当前受控口径下算术一致；"
                        "该结果不证明人员身份、所得项目、扣除、税率、优惠或申报处理合法。"
                    )
                self.sudo().with_context(
                    cn_iit_period_transition=_IIT_PERIOD_TRANSITION_MARKER
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
            return self._mark_failed("IIT_PERIOD_INPUT_ERROR", exc)
        except Exception as exc:
            return self._mark_failed(
                "UNEXPECTED_IIT_PERIOD_FAILURE",
                _(
                    "个人所得税勾稽发生未预期错误：%(kind)s",
                    kind=type(exc).__name__,
                ),
            )
        for previous in previous_runs:
            self.env["sudo.compliance.audit.event"]._log_records(
                previous,
                "cn_iit_period_reconciliation.superseded",
                previous_state="succeeded",
                new_state="superseded",
                details={"replacement_run_id": self.id},
            )
        self.env["sudo.compliance.audit.event"]._log_records(
            self,
            "cn_iit_period_reconciliation.succeeded",
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
                      FROM sudo_cn_iit_period_reconciliation_run
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
            raise AccessError(_("只有合规管理员可以取消个人所得税勾稽。"))
        for run in self:
            if run.state != "queued":
                raise UserError(_("只有待处理的个人所得税勾稽可以取消。"))
            run.with_context(
                cn_iit_period_transition=_IIT_PERIOD_TRANSITION_MARKER
            ).write(
                {
                    "state": "cancelled",
                    "finished_at": fields.Datetime.now(),
                    "result_summary": _("批次在执行前取消。"),
                }
            )
            self.env["sudo.compliance.audit.event"]._log_records(
                run,
                "cn_iit_period_reconciliation.cancelled",
                previous_state="queued",
                new_state="cancelled",
            )
        return True

    def action_view_issues(self):
        self.ensure_one()
        action = self.env.ref(
            "sudo_country_pack_cn.action_cn_iit_period_reconciliation_issues"
        ).read()[0]
        action["domain"] = [("run_id", "=", self.id)]
        action["context"] = {}
        return action

    def action_open_accounting_scope(self):
        self.ensure_one()
        if not self.accounting_scope_id:
            raise UserError(_("当前批次没有关联个税账务口径。"))
        return {
            "type": "ir.actions.act_window",
            "name": _("个人所得税账务口径"),
            "res_model": "sudo.cn.iit.accounting.scope",
            "res_id": self.accounting_scope_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_open_payroll_summary(self):
        self.ensure_one()
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以查看工资薪酬汇总来源。"))
        if not self.payroll_summary_id:
            raise UserError(_("当前批次没有关联工资薪酬汇总。"))
        return {
            "type": "ir.actions.act_window",
            "name": _("工资薪酬汇总台账"),
            "res_model": "sudo.cn.payroll.summary.record",
            "res_id": self.payroll_summary_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_open_withholding_record(self):
        self.ensure_one()
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以查看个人所得税扣缴申报来源。"))
        if not self.withholding_record_id:
            raise UserError(_("当前批次没有关联个人所得税扣缴申报。"))
        return {
            "type": "ir.actions.act_window",
            "name": _("个人所得税扣缴申报台账"),
            "res_model": "sudo.cn.iit.withholding.record",
            "res_id": self.withholding_record_id.id,
            "view_mode": "form",
            "target": "current",
        }


class SudoChinaIitPeriodReconciliationIssue(models.Model):
    _name = "sudo.cn.iit.period.reconciliation.issue"
    _description = "China IIT Period Reconciliation Issue"
    _order = "sequence, issue_kind, source_area, code, id"
    _check_company_auto = True

    name = fields.Char(string="问题", required=True, readonly=True)
    sequence = fields.Integer(required=True, readonly=True)
    run_id = fields.Many2one(
        "sudo.cn.iit.period.reconciliation.run",
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
        [("data_gap", "数据或控制问题"), ("difference", "差异")],
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
            ("accounting_scope", "账务口径"),
            ("accounting", "Odoo 账簿"),
            ("payroll", "工资薪酬汇总"),
            ("filing", "个人所得税申报"),
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
    has_count_comparison = fields.Boolean(readonly=True)
    left_count = fields.Integer(string="左侧数量", readonly=True)
    right_count = fields.Integer(string="右侧数量", readonly=True)
    count_difference = fields.Integer(string="数量差异", readonly=True)
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
            self.env.context.get("cn_iit_period_transition")
            is not _IIT_PERIOD_TRANSITION_MARKER
        ):
            raise AccessError(_("个人所得税勾稽问题只能由受控引擎创建。"))
        return super().create(vals_list)

    def write(self, values):
        raise AccessError(_("个人所得税勾稽问题属于执行快照，不可修改。"))

    def unlink(self):
        raise AccessError(_("个人所得税勾稽问题属于执行快照，不可删除。"))

    def copy(self, default=None):
        raise AccessError(_("个人所得税勾稽问题不可复制。"))


class SudoChinaIitPeriodReconciliationWizard(models.TransientModel):
    _name = "sudo.cn.iit.period.reconciliation.wizard"
    _description = "Start China IIT Period Reconciliation"

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
    iit_tax_type_code = fields.Char(
        string="缴税数据个税代码",
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
        if "iit_tax_type_code" in field_names and not values.get(
            "iit_tax_type_code"
        ):
            values["iit_tax_type_code"] = "IIT"
        return values

    def action_queue(self):
        self.ensure_one()
        run = self.env["sudo.cn.iit.period.reconciliation.run"].with_company(
            self.company_id
        ).enqueue(
            self.profile_id,
            self.period_start,
            self.period_end,
            self.iit_tax_type_code,
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("个人所得税工资账表款勾稽"),
            "res_model": "sudo.cn.iit.period.reconciliation.run",
            "res_id": run.id,
            "view_mode": "form",
            "target": "current",
        }
