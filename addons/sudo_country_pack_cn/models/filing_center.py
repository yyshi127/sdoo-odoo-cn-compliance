from odoo import _, fields, models
from odoo.osv import expression


EVIDENCE_STATES = [
    ("none", "无证据"),
    ("partial", "待验证"),
    ("verified", "已验证"),
]


ARCHIVE_READINESS_STATES = [
    ("ready", "可用于报告"),
    ("attention", "需补充"),
    ("blocked", "不可引用"),
]


class SudoChinaFilingCenterFiling(models.Model):
    _inherit = "sudo.compliance.filing"

    cn_filing_center_kind = fields.Selection(
        [
            ("vat", "增值税"),
            ("cit", "企业所得税"),
            ("iit", "个人所得税"),
            ("other", "其他"),
        ],
        string="中国档案类型",
        compute="_compute_cn_filing_center_display",
    )
    cn_filing_center_period_label = fields.Char(
        string="所属期间",
        compute="_compute_cn_filing_center_display",
    )
    cn_filing_center_next_action = fields.Char(
        string="下一步动作",
        compute="_compute_cn_filing_center_display",
    )
    cn_filing_center_evidence_state = fields.Selection(
        EVIDENCE_STATES,
        string="证据状态",
        compute="_compute_cn_filing_center_display",
    )
    cn_filing_center_archive_state = fields.Selection(
        ARCHIVE_READINESS_STATES,
        string="归档就绪",
        compute="_compute_cn_filing_center_display",
        search="_search_cn_filing_center_archive_state",
    )
    cn_filing_center_evidence_count = fields.Integer(
        string="证据记录",
        compute="_compute_cn_filing_center_display",
    )
    cn_filing_center_blocker_summary = fields.Char(
        string="Filing Blockers",
        compute="_compute_cn_filing_center_display",
    )
    cn_filing_center_verified_evidence_count = fields.Integer(
        string="已验证证据",
        compute="_compute_cn_filing_center_display",
    )

    def _compute_cn_filing_center_display(self):
        for filing in self:
            filing.cn_filing_center_kind = filing._cn_filing_center_kind()
            filing.cn_filing_center_period_label = _period_label(
                filing.period_start,
                filing.period_end,
                filing.env._,
            )
            evidence = (
                filing.cn_submission_evidence_ids | filing.cn_payment_evidence_ids
            )
            verified = evidence.filtered(lambda record: record.state == "verified")
            filing.cn_filing_center_evidence_count = len(evidence)
            filing.cn_filing_center_verified_evidence_count = len(verified)
            filing.cn_filing_center_evidence_state = _evidence_state(
                len(evidence),
                len(verified),
            )
            filing.cn_filing_center_archive_state = (
                filing._cn_filing_center_archive_state()
            )
            filing.cn_filing_center_next_action = (
                filing._cn_filing_center_next_action()
            )
            filing.cn_filing_center_blocker_summary = (
                filing._cn_filing_center_blocker_summary()
            )

    def _cn_filing_center_kind(self):
        self.ensure_one()
        if self.cn_vat_reconciliation_run_id:
            return "vat"
        if self.cn_cit_reconciliation_run_id:
            return "cit"
        if self.cn_iit_reconciliation_run_id:
            return "iit"
        return "other"

    def _cn_filing_center_next_action(self):
        self.ensure_one()
        if self.cn_submission_integrity_state in ("changed", "invalid"):
            return _("申报档案完整性异常，请停止引用并复核封存来源。")
        if self.cn_payment_integrity_state in ("changed", "invalid"):
            return _("缴款或退库档案完整性异常，请停止引用并复核封存来源。")
        if self.cn_submission_integrity_state == "unsealed":
            return _("补齐已验证申报回执证据，并封存申报档案。")
        if self.state in ("draft", "ready"):
            return _("确认截止日依据、适用义务和申报回执后提交。")
        if self.state in ("submitted", "accepted"):
            if self.payment_state in ("not_paid", "partial"):
                return _("补齐已验证缴款证明或退库回执，并封存缴退税档案。")
            if self.cn_payment_integrity_state == "unsealed":
                return _("封存缴款或退库档案，形成可审计证据链。")
        if self.cn_filing_center_evidence_state != "verified":
            return _("核验正式证据，确保报告和后续复核可以引用。")
        if self.cn_submission_integrity_state == "source_superseded":
            return _("来源已被新批次替代，历史档案仅作追溯引用。")
        if self.cn_payment_integrity_state == "source_superseded":
            return _("缴退税来源已被新批次替代，历史档案仅作追溯引用。")
        return _("档案已形成受控链路，持续保留回执、缴退税证据和校验指纹。")


    def _cn_filing_center_archive_state(self):
        self.ensure_one()
        if (
            self.cn_submission_integrity_state in ("changed", "invalid")
            or self.cn_payment_integrity_state in ("changed", "invalid")
            or self.state in ("rejected", "cancelled")
            or self.payment_state in ("failed", "cancelled")
        ):
            return "blocked"
        if (
            self.cn_submission_integrity_state in ("unsealed", "source_superseded")
            or self.cn_payment_integrity_state in ("unsealed", "source_superseded")
            or self.state in ("draft", "ready")
            or self.payment_state in ("not_paid", "partial")
            or self.cn_filing_center_evidence_state != "verified"
        ):
            return "attention"
        return "ready"

    def _search_cn_filing_center_archive_state(self, operator, value):
        records = self.with_context(lang=self.env.user.lang or "en_US")
        allowed = {"ready", "attention", "blocked"}
        if operator in ("=", "!="):
            values = {value}
        elif operator in ("in", "not in"):
            values = set(value or [])
        else:
            return [("id", "=", 0)]
        values &= allowed
        if not values:
            return [] if operator in ("!=", "not in") else [("id", "=", 0)]
        controlled_domain = [
            "|",
            "|",
            ("cn_vat_reconciliation_run_id", "!=", False),
            ("cn_cit_reconciliation_run_id", "!=", False),
            ("cn_iit_reconciliation_run_id", "!=", False),
        ]
        matched = records.search(controlled_domain).filtered(
            lambda filing: filing._cn_filing_center_archive_state() in values
        )
        domain = [("id", "in", matched.ids)]
        if operator in ("!=", "not in"):
            return expression.NOT(domain)
        return domain

    def _cn_filing_center_blocker_summary(self):
        self.ensure_one()
        blockers = []
        if self.cn_submission_integrity_state in ("changed", "invalid"):
            blockers.append(_("申报封存完整性异常"))
        elif self.cn_submission_integrity_state == "unsealed":
            blockers.append(_("申报回执尚未封存"))
        elif self.cn_submission_integrity_state == "source_superseded":
            blockers.append(_("申报来源已被新批次替代"))
        if self.cn_payment_integrity_state in ("changed", "invalid"):
            blockers.append(_("缴退税封存完整性异常"))
        elif self.cn_payment_integrity_state == "unsealed":
            blockers.append(_("缴退税证明尚未封存"))
        elif self.cn_payment_integrity_state == "source_superseded":
            blockers.append(_("缴退税来源已被新批次替代"))
        if self.state in ("draft", "ready"):
            blockers.append(_("申报尚未提交或确认受理"))
        elif self.state in ("rejected", "cancelled"):
            blockers.append(_("申报未被受理"))
        if self.payment_state in ("not_paid", "partial"):
            blockers.append(_("缴退税证明不完整"))
        elif self.payment_state in ("failed", "cancelled"):
            blockers.append(_("缴退税未成功"))
        if self.cn_filing_center_evidence_state == "none":
            blockers.append(_("未关联正式证据"))
        elif self.cn_filing_center_evidence_state == "partial":
            blockers.append(_("部分正式证据未验证"))
        if not blockers:
            return _("无阻断：申报、缴退税和正式证据均可追溯。")
        return _("待处理：%(blockers)s") % {
            "blockers": "; ".join(dict.fromkeys(blockers))
        }


class SudoChinaFilingCenterProfile(models.Model):
    _inherit = "sudo.compliance.profile"

    def action_cn_open_workbench_filing_center(self):
        self.ensure_one()
        action = self.env.ref(
            "sudo_country_pack_cn.action_cn_filing_center",
            raise_if_not_found=False,
        )
        domain = [
            ("profile_id", "=", self.id),
            "|",
            "|",
            ("cn_vat_reconciliation_run_id", "!=", False),
            ("cn_cit_reconciliation_run_id", "!=", False),
            ("cn_iit_reconciliation_run_id", "!=", False),
        ]
        if action:
            result = action.sudo().read()[0]
            result["domain"] = domain
            result["context"] = {
                "search_default_cn_controlled": 1,
                "search_default_group_kind": 1,
            }
            return result
        return {
            "type": "ir.actions.act_window",
            "name": _("中国申报缴款档案"),
            "res_model": "sudo.compliance.filing",
            "view_mode": "list,form",
            "domain": domain,
            "target": "current",
        }


def _period_label(period_start, period_end, translate):
    if period_start and period_end:
        return translate(
            "%(start)s 至 %(end)s",
            start=period_start,
            end=period_end,
        )
    return translate("未记录期间")


def _evidence_state(evidence_count, verified_evidence_count):
    if not evidence_count:
        return "none"
    if evidence_count == verified_evidence_count:
        return "verified"
    return "partial"
