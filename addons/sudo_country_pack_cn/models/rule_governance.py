from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


CN_RULE_NATURE_SELECTION = [
    ("statutory_requirement", "法定义务"),
    ("tax_calculation", "税额计算"),
    ("filing_deadline", "申报与缴款时限"),
    ("internal_control", "内部控制"),
    ("data_readiness", "数据准备度"),
]

CN_RULE_NATURE_BY_CODE = {
    "CN-BASE-REG-001": "data_readiness",
    "CN-ACC-PERIOD-001": "internal_control",
    "CN-VAT-INV-READY-001": "data_readiness",
    "CN-ACC-EVIDENCE-001": "internal_control",
    "CN-PROFILE-TAX-001": "data_readiness",
    "CN-DATA-EINV-RECON-001": "data_readiness",
    "CN-DATA-VAT-RECON-001": "data_readiness",
}

_CONTROL_NATURES = {"internal_control", "data_readiness"}
_PUBLISHABLE_SNAPSHOT_KINDS = {"official_document", "official_web_capture"}


def backfill_cn_rule_natures(env):
    rule_model = env["sudo.compliance.rule"].with_context(active_test=False)
    for code, nature in CN_RULE_NATURE_BY_CODE.items():
        rule = rule_model.search([("code", "=", code)], limit=1)
        if rule and not rule.cn_rule_nature:
            rule.write({"cn_rule_nature": nature})


class SudoComplianceRule(models.Model):
    _inherit = "sudo.compliance.rule"

    cn_is_china_rule = fields.Boolean(
        string="中国规则",
        compute="_compute_cn_is_china_rule",
        store=True,
    )
    cn_rule_nature = fields.Selection(
        CN_RULE_NATURE_SELECTION,
        string="规则性质",
        index=True,
        help=(
            "区分法定义务、税额计算、申报时限、内部控制和数据准备度。"
            "内部控制或数据准备度结果不等同于违法或税务认定。"
        ),
    )

    @api.depends("country_id.code")
    def _compute_cn_is_china_rule(self):
        for rule in self:
            rule.cn_is_china_rule = rule.country_id.code == "CN"

    @api.constrains("country_id", "cn_rule_nature")
    def _check_cn_rule_nature_country(self):
        for rule in self.filtered("cn_rule_nature"):
            if rule.country_id.code != "CN":
                raise ValidationError(_("中国规则性质只能用于中国规则。"))

    def write(self, values):
        if "cn_rule_nature" in values:
            proposed = values.get("cn_rule_nature") or False
            for rule in self:
                if (
                    rule.cn_rule_nature
                    and proposed != rule.cn_rule_nature
                    and rule.version_ids
                ):
                    raise UserError(
                        _(
                            "规则已有版本，不能改写规则性质；如业务性质发生变化，"
                            "请创建新的规则编码。"
                        )
                    )
        return super().write(values)


class SudoComplianceRuleVersion(models.Model):
    _inherit = "sudo.compliance.rule.version"

    cn_is_china_rule = fields.Boolean(
        related="rule_id.cn_is_china_rule",
        string="中国规则",
        store=True,
        readonly=True,
    )
    cn_rule_nature = fields.Selection(
        related="rule_id.cn_rule_nature",
        string="规则性质",
        store=True,
        readonly=True,
        index=True,
    )
    cn_release_state = fields.Selection(
        [
            ("classification_required", "规则性质待明确"),
            ("review_boundary_required", "复核边界待设置"),
            ("source_governance", "官方来源待治理"),
            ("test_required", "规则测试待通过"),
            ("review_packet_required", "专业复核包待完善"),
            ("professional_signoff", "专业签核待完成"),
            ("ready_for_review", "可提交技术复核"),
            ("technical_review", "技术复核中"),
            ("ready_to_activate", "可发布生效"),
            ("active", "已正式生效"),
            ("active_attention", "生效后需关注"),
            ("retired", "已退役"),
        ],
        string="发布就绪状态",
        compute="_compute_cn_release_governance",
        store=True,
        readonly=True,
        index=True,
    )
    cn_governance_ready = fields.Boolean(
        string="治理门禁已满足",
        compute="_compute_cn_release_governance",
        store=True,
        readonly=True,
    )
    cn_release_blockers = fields.Text(
        string="发布阻断事项",
        compute="_compute_cn_release_governance",
        store=True,
        readonly=True,
    )
    cn_professional_review_ready = fields.Boolean(
        string="可进行专业签核",
        compute="_compute_cn_release_governance",
        store=True,
        readonly=True,
    )
    cn_professional_review_blockers = fields.Text(
        string="专业签核前置缺口",
        compute="_compute_cn_release_governance",
        store=True,
        readonly=True,
    )

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
    )
    def _compute_cn_release_governance(self):
        today = fields.Date.context_today(self)
        for version in self:
            if not version.cn_is_china_rule:
                version.cn_release_state = False
                version.cn_governance_ready = False
                version.cn_release_blockers = False
                version.cn_professional_review_ready = False
                version.cn_professional_review_blockers = False
                continue

            pre_signoff_blockers = []
            invalid_sources = version.authority_source_ids.filtered(
                lambda source: source.status != "valid"
                or not source.content_hash
                or not source.snapshot_attachment_id
                or source.snapshot_kind not in _PUBLISHABLE_SNAPSHOT_KINDS
                or (
                    source.next_review_date
                    and source.next_review_date < today
                )
            )
            if not version.cn_rule_nature:
                pre_signoff_blockers.append(_("未明确规则性质。"))
            if (
                version.cn_rule_nature in _CONTROL_NATURES
                and not version.requires_human_review
            ):
                pre_signoff_blockers.append(
                    _("内部控制和数据准备度规则必须要求人工复核。")
                )
            if not version.authority_source_ids:
                pre_signoff_blockers.append(_("未关联官方来源。"))
            elif invalid_sources:
                pre_signoff_blockers.append(
                    _(
                        "官方来源尚未完成有效快照、哈希、独立复核或时效复核：%(sources)s",
                        sources=", ".join(invalid_sources.mapped("display_name")),
                    )
                )
            if version.test_state != "passed" or not version.test_case_ids:
                pre_signoff_blockers.append(_("规则测试尚未全部通过。"))
            if not version.cn_review_packet_ready:
                pre_signoff_blockers.append(
                    _(
                        "中国专业复核包尚未完整：%(details)s",
                        details=(
                            version.cn_review_packet_blockers
                            or _("未建立适用范围、结论边界和条款定位。")
                        ),
                    )
                )

            blockers = list(pre_signoff_blockers)
            if version.professional_review_state != "approved":
                blockers.append(_("中国财税专业签核尚未完成或已失效。"))

            version.cn_professional_review_ready = not pre_signoff_blockers
            version.cn_professional_review_blockers = "\n".join(
                "- %s" % blocker for blocker in pre_signoff_blockers
            ) or _("专业签核前置材料完整，仍须由独立真人专业人员判断。")

            ready = not blockers and version.state != "retired"
            if version.state == "retired":
                release_state = "retired"
            elif version.state == "active":
                release_state = "active" if ready else "active_attention"
            elif not version.cn_rule_nature:
                release_state = "classification_required"
            elif (
                version.cn_rule_nature in _CONTROL_NATURES
                and not version.requires_human_review
            ):
                release_state = "review_boundary_required"
            elif not version.authority_source_ids or invalid_sources:
                release_state = "source_governance"
            elif version.test_state != "passed" or not version.test_case_ids:
                release_state = "test_required"
            elif not version.cn_review_packet_ready:
                release_state = "review_packet_required"
            elif version.professional_review_state != "approved":
                release_state = "professional_signoff"
            elif version.state == "draft":
                release_state = "ready_for_review"
            elif version.state == "pending_review":
                release_state = "technical_review"
            elif version.state == "approved":
                release_state = "ready_to_activate"
            else:
                release_state = "active_attention"

            version.cn_release_state = release_state
            version.cn_governance_ready = ready
            version.cn_release_blockers = "\n".join(
                "- %s" % blocker for blocker in blockers
            ) or _("无发布阻断事项。")

    def _check_publish_gate(self):
        today = fields.Date.context_today(self)
        for version in self.filtered("cn_is_china_rule"):
            if not version.cn_rule_nature:
                raise UserError(_("中国规则发布前必须明确规则性质。"))
            if (
                version.cn_rule_nature in _CONTROL_NATURES
                and not version.requires_human_review
            ):
                raise UserError(
                    _("内部控制和数据准备度规则发布前必须设置人工复核。")
                )
            if not version.cn_review_packet_ready:
                raise UserError(
                    _(
                        "中国规则发布前必须完善专业复核包：%(details)s",
                        details=(
                            version.cn_review_packet_blockers
                            or _("未建立适用范围、结论边界和条款定位。")
                        ),
                    )
                )
            overdue_sources = version.authority_source_ids.filtered(
                lambda source: source.next_review_date
                and source.next_review_date < today
            )
            if overdue_sources:
                raise UserError(
                    _(
                        "以下官方来源已超过复核日期：%(sources)s",
                        sources=", ".join(overdue_sources.mapped("display_name")),
                    )
                )
        return super()._check_publish_gate()

    def action_professional_signoff(self):
        for version in self.filtered("cn_is_china_rule"):
            if not version.cn_professional_review_ready:
                raise UserError(
                    _(
                        "中国规则尚不能专业签核：%(details)s",
                        details=(
                            version.cn_professional_review_blockers
                            or _("前置材料不完整。")
                        ),
                    )
                )
        return super().action_professional_signoff()

    def _checksum_payload(self):
        payload = super()._checksum_payload()
        if self.cn_is_china_rule:
            payload["cn_rule_nature"] = self.cn_rule_nature
        return payload


class SudoComplianceFinding(models.Model):
    _inherit = "sudo.compliance.finding"

    cn_rule_nature = fields.Selection(
        related="rule_id.cn_rule_nature",
        string="规则性质",
        store=True,
        readonly=True,
        index=True,
    )
