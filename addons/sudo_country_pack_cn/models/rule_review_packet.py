from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from odoo.addons.sudo_global_finance.models.rule_engine import stable_checksum


CN_CITATION_TYPE_SELECTION = [
    ("direct_requirement", "法条直接要求"),
    ("supporting_context", "法定背景"),
    ("internal_control_rationale", "内控推导"),
    ("technical_guidance", "技术规范"),
]


class SudoCnRuleReviewPacket(models.Model):
    _name = "sudo.cn.rule.review.packet"
    _description = "China Rule Professional Review Packet"
    _inherit = "sudo.compliance.governance.mixin"
    _order = "rule_version_id"

    name = fields.Char(compute="_compute_name", store=True)
    rule_version_id = fields.Many2one(
        "sudo.compliance.rule.version",
        string="规则版本",
        required=True,
        ondelete="cascade",
        index=True,
    )
    rule_version_state = fields.Selection(
        related="rule_version_id.state",
        string="规则状态",
        readonly=True,
    )
    professional_review_state = fields.Selection(
        related="rule_version_id.professional_review_state",
        string="专业签核状态",
        readonly=True,
    )
    test_state = fields.Selection(
        related="rule_version_id.test_state",
        string="规则测试",
        readonly=True,
    )
    cn_rule_nature = fields.Selection(
        related="rule_version_id.cn_rule_nature",
        string="规则性质",
        readonly=True,
    )
    scope_summary = fields.Text(
        string="适用范围",
        required=True,
        translate=True,
    )
    applicability_assumptions = fields.Text(
        string="适用前提",
        required=True,
        translate=True,
    )
    exclusions_limitations = fields.Text(
        string="明确排除与限制",
        required=True,
        translate=True,
    )
    conclusion_boundary = fields.Text(
        string="结论边界",
        required=True,
        translate=True,
    )
    reviewer_questions = fields.Text(
        string="待专业人员回答",
        required=True,
        translate=True,
    )
    citation_ids = fields.One2many(
        "sudo.cn.rule.review.citation",
        "packet_id",
        string="条款定位",
        copy=True,
    )
    readiness_state = fields.Selection(
        [("incomplete", "材料不完整"), ("ready", "候选材料完整")],
        string="复核包状态",
        compute="_compute_readiness",
        store=True,
        readonly=True,
        index=True,
    )
    readiness_blockers = fields.Text(
        string="材料缺口",
        compute="_compute_readiness",
        store=True,
        readonly=True,
    )
    candidate_checksum = fields.Char(
        string="候选包 SHA-256",
        compute="_compute_readiness",
        store=True,
        readonly=True,
        index=True,
    )

    _rule_version_unique = models.Constraint(
        "unique(rule_version_id)",
        "同一规则版本只能有一份中国专业复核包。",
    )

    @api.depends("rule_version_id.name")
    def _compute_name(self):
        for packet in self:
            packet.name = _("中国专业复核包：%(version)s", version=packet.rule_version_id.name)

    def governance_payload(self):
        self.ensure_one()
        packet = self.with_context(lang="en_US")
        citations = sorted(
            (
                citation.governance_payload()
                for citation in packet.citation_ids
            ),
            key=lambda item: (
                item["sequence"],
                item["source_url"],
                item["locator"],
                item["citation_type"],
            ),
        )
        return {
            "scope_summary": packet.scope_summary or "",
            "applicability_assumptions": packet.applicability_assumptions or "",
            "exclusions_limitations": packet.exclusions_limitations or "",
            "conclusion_boundary": packet.conclusion_boundary or "",
            "reviewer_questions": packet.reviewer_questions or "",
            "citations": citations,
        }

    @api.depends(
        "scope_summary",
        "applicability_assumptions",
        "exclusions_limitations",
        "conclusion_boundary",
        "reviewer_questions",
        "rule_version_id.authority_source_ids",
        "citation_ids.sequence",
        "citation_ids.citation_type",
        "citation_ids.source_id",
        "citation_ids.source_id.official_url",
        "citation_ids.source_id.official_version",
        "citation_ids.source_id.content_hash",
        "citation_ids.locator",
        "citation_ids.claim_summary",
        "citation_ids.applicability_note",
    )
    def _compute_readiness(self):
        labels = {
            "scope_summary": _("未说明适用范围。"),
            "applicability_assumptions": _("未说明适用前提。"),
            "exclusions_limitations": _("未说明明确排除与限制。"),
            "conclusion_boundary": _("未说明结论边界。"),
            "reviewer_questions": _("未列出待专业人员回答的问题。"),
        }
        for packet in self:
            blockers = [
                message
                for field_name, message in labels.items()
                if not (packet[field_name] or "").strip()
            ]
            if not packet.citation_ids:
                blockers.append(_("未建立条款定位。"))
            linked_sources = packet.rule_version_id.authority_source_ids
            cited_sources = packet.citation_ids.mapped("source_id")
            uncovered_sources = linked_sources - cited_sources
            if uncovered_sources:
                blockers.append(
                    _(
                        "以下已关联来源没有条款定位：%(sources)s",
                        sources=", ".join(uncovered_sources.mapped("display_name")),
                    )
                )
            unrelated_sources = cited_sources - linked_sources
            if unrelated_sources:
                blockers.append(
                    _(
                        "以下条款来源未关联到规则版本：%(sources)s",
                        sources=", ".join(unrelated_sources.mapped("display_name")),
                    )
                )
            packet.readiness_state = "incomplete" if blockers else "ready"
            packet.readiness_blockers = "\n".join(
                "- %s" % blocker for blocker in blockers
            ) or _("候选材料字段和来源覆盖完整，仍须真人专业复核。")
            packet.candidate_checksum = stable_checksum(
                packet.governance_payload()
            )

    def _ensure_author_can_edit(self):
        if self._is_trusted_install_write():
            return True
        if not self._can_author():
            raise AccessError(_("只有规则维护人员可以维护中国专业复核包。"))
        invalid = self.filtered(
            lambda packet: packet.rule_version_id.state != "draft"
        )
        if invalid:
            raise UserError(_("只有草稿规则版本的专业复核包可以修改。"))
        return True

    def _touch_versions(self, versions, reason):
        if self._is_trusted_install_write() or not versions:
            return
        signed = versions.filtered(
            lambda version: version.professional_review_state != "pending"
        )
        if signed:
            signed._invalidate_professional_signoff(reason, reset_tests=False)
        pending = versions - signed
        if pending:
            pending._lifecycle_write({"checksum": False})
        versions._add_payload_preparer(self.env.user, reason=reason)

    @api.model_create_multi
    def create(self, vals_list):
        versions = self.env["sudo.compliance.rule.version"].browse(
            [values.get("rule_version_id") for values in vals_list]
        ).exists()
        if not self._is_trusted_install_write():
            if len(versions) != len(vals_list):
                raise ValidationError(_("专业复核包必须关联有效规则版本。"))
            packets = self.browse()
            for version in versions:
                packets |= self.new({"rule_version_id": version.id})
            packets._ensure_author_can_edit()
            if any(not version.cn_is_china_rule for version in versions):
                raise ValidationError(_("中国专业复核包只能关联中国规则。"))
        records = super().create(vals_list)
        if not self._is_trusted_install_write():
            records._touch_versions(
                records.mapped("rule_version_id"),
                "cn_review_packet_created",
            )
            self.env["sudo.compliance.audit.event"]._log_records(
                records,
                "cn_rule_review_packet.created",
                details={"candidate_checksums": records.mapped("candidate_checksum")},
            )
        return records

    def write(self, values):
        self._ensure_author_can_edit()
        result = super().write(values)
        if not self._is_trusted_install_write():
            self._touch_versions(
                self.mapped("rule_version_id"),
                "cn_review_packet_updated",
            )
            self.env["sudo.compliance.audit.event"]._log_records(
                self,
                "cn_rule_review_packet.updated",
                details={"changed_fields": sorted(values)},
            )
        return result

    def unlink(self):
        self._ensure_author_can_edit()
        versions = self.mapped("rule_version_id")
        if not self._is_trusted_install_write():
            self.env["sudo.compliance.audit.event"]._log_records(
                self,
                "cn_rule_review_packet.deleted",
                details={"candidate_checksums": self.mapped("candidate_checksum")},
            )
        result = super().unlink()
        self._touch_versions(versions, "cn_review_packet_deleted")
        return result

    def action_print_review_packet(self):
        self.ensure_one()
        return self.env.ref(
            "sudo_country_pack_cn.action_report_cn_rule_review_packet"
        ).report_action(self)


class SudoCnRuleReviewCitation(models.Model):
    _name = "sudo.cn.rule.review.citation"
    _description = "China Rule Review Citation"
    _inherit = "sudo.compliance.governance.mixin"
    _order = "packet_id, sequence, id"

    name = fields.Char(compute="_compute_name", store=True)
    packet_id = fields.Many2one(
        "sudo.cn.rule.review.packet",
        string="专业复核包",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    source_id = fields.Many2one(
        "sudo.compliance.authority.source",
        string="官方来源",
        required=True,
        ondelete="restrict",
        index=True,
    )
    citation_type = fields.Selection(
        CN_CITATION_TYPE_SELECTION,
        string="引用性质",
        required=True,
        default="supporting_context",
        index=True,
    )
    locator = fields.Char(
        string="条款定位",
        required=True,
        translate=True,
    )
    claim_summary = fields.Text(
        string="规则主张与来源关系",
        required=True,
        translate=True,
    )
    applicability_note = fields.Text(
        string="适用说明与待核事项",
        required=True,
        translate=True,
    )

    _citation_unique = models.Constraint(
        "unique(packet_id, source_id, citation_type, locator)",
        "同一复核包中不能重复登记相同来源、性质和条款定位。",
    )

    @api.depends("source_id.name", "locator")
    def _compute_name(self):
        for citation in self:
            citation.name = "%s · %s" % (
                citation.source_id.name or _("官方来源"),
                citation.locator or _("待定位"),
            )

    def governance_payload(self):
        self.ensure_one()
        citation = self.with_context(lang="en_US")
        return {
            "sequence": citation.sequence,
            "source_url": citation.source_id.official_url or "",
            "source_version": citation.source_id.official_version or "",
            "source_content_hash": citation.source_id.content_hash or "",
            "citation_type": citation.citation_type,
            "locator": citation.locator or "",
            "claim_summary": citation.claim_summary or "",
            "applicability_note": citation.applicability_note or "",
        }

    @api.constrains("packet_id", "source_id")
    def _check_source_is_linked(self):
        for citation in self:
            if (
                citation.source_id
                not in citation.packet_id.rule_version_id.authority_source_ids
            ):
                raise ValidationError(
                    _("条款定位只能选择规则版本已经关联的官方来源。")
                )

    def _ensure_author_can_edit(self):
        self.mapped("packet_id")._ensure_author_can_edit()

    def _touch_packets(self, packets, reason):
        if self._is_trusted_install_write() or not packets:
            return
        packets._touch_versions(packets.mapped("rule_version_id"), reason)

    @api.model_create_multi
    def create(self, vals_list):
        packets = self.env["sudo.cn.rule.review.packet"].browse(
            [values.get("packet_id") for values in vals_list]
        ).exists()
        if not self._is_trusted_install_write():
            if len(packets) != len(vals_list):
                raise ValidationError(_("条款定位必须关联有效专业复核包。"))
            packets._ensure_author_can_edit()
        records = super().create(vals_list)
        if not self._is_trusted_install_write():
            records._touch_packets(
                records.mapped("packet_id"),
                "cn_review_citation_created",
            )
            self.env["sudo.compliance.audit.event"]._log_records(
                records,
                "cn_rule_review_citation.created",
                details={"packet_ids": records.mapped("packet_id").ids},
            )
        return records

    def write(self, values):
        packets = self.mapped("packet_id")
        self._ensure_author_can_edit()
        result = super().write(values)
        packets |= self.mapped("packet_id")
        if not self._is_trusted_install_write():
            self._touch_packets(packets, "cn_review_citation_updated")
            self.env["sudo.compliance.audit.event"]._log_records(
                self,
                "cn_rule_review_citation.updated",
                details={"changed_fields": sorted(values)},
            )
        return result

    def unlink(self):
        self._ensure_author_can_edit()
        packets = self.mapped("packet_id")
        if not self._is_trusted_install_write():
            self.env["sudo.compliance.audit.event"]._log_records(
                self,
                "cn_rule_review_citation.deleted",
                details={"packet_ids": packets.ids},
            )
        result = super().unlink()
        self._touch_packets(packets, "cn_review_citation_deleted")
        return result


class SudoComplianceRuleVersion(models.Model):
    _inherit = "sudo.compliance.rule.version"

    cn_review_packet_ids = fields.One2many(
        "sudo.cn.rule.review.packet",
        "rule_version_id",
        string="中国专业复核包记录",
    )
    cn_review_packet_id = fields.Many2one(
        "sudo.cn.rule.review.packet",
        string="当前中国专业复核包",
        compute="_compute_cn_review_packet_record",
        readonly=True,
    )
    cn_review_packet_state = fields.Selection(
        [
            ("missing", "尚未建立"),
            ("incomplete", "材料不完整"),
            ("ready", "候选材料完整"),
        ],
        string="专业复核包",
        compute="_compute_cn_review_packet_status",
        store=True,
        readonly=True,
        index=True,
    )
    cn_review_packet_ready = fields.Boolean(
        string="专业复核包完整",
        compute="_compute_cn_review_packet_status",
        store=True,
        readonly=True,
    )
    cn_review_packet_blockers = fields.Text(
        string="专业复核包缺口",
        compute="_compute_cn_review_packet_status",
        store=True,
        readonly=True,
    )

    @api.depends("cn_review_packet_ids")
    def _compute_cn_review_packet_record(self):
        for version in self:
            version.cn_review_packet_id = version.cn_review_packet_ids[:1]

    @api.depends(
        "rule_id.country_id.code",
        "cn_review_packet_ids",
        "cn_review_packet_ids.readiness_state",
        "cn_review_packet_ids.readiness_blockers",
    )
    def _compute_cn_review_packet_status(self):
        for version in self:
            packets = version.cn_review_packet_ids
            if not version.cn_is_china_rule:
                version.cn_review_packet_state = False
                version.cn_review_packet_ready = False
                version.cn_review_packet_blockers = False
            elif not packets:
                version.cn_review_packet_state = "missing"
                version.cn_review_packet_ready = False
                version.cn_review_packet_blockers = _(
                    "- 尚未建立中国专业复核包。"
                )
            elif len(packets) != 1:
                version.cn_review_packet_state = "incomplete"
                version.cn_review_packet_ready = False
                version.cn_review_packet_blockers = _(
                    "- 同一规则版本存在多份专业复核包。"
                )
            else:
                packet = packets[0]
                version.cn_review_packet_state = packet.readiness_state
                version.cn_review_packet_ready = packet.readiness_state == "ready"
                version.cn_review_packet_blockers = packet.readiness_blockers

    def _checksum_payload(self):
        payload = super()._checksum_payload()
        if self.cn_is_china_rule:
            packet = self.cn_review_packet_id
            payload["cn_review_packet"] = (
                packet.governance_payload() if packet else None
            )
        return payload

    def action_open_cn_review_packet(self):
        self.ensure_one()
        if not self.cn_review_packet_id:
            raise UserError(_("该规则版本尚未建立中国专业复核包。"))
        return {
            "type": "ir.actions.act_window",
            "name": _("中国专业复核包"),
            "res_model": "sudo.cn.rule.review.packet",
            "view_mode": "form",
            "res_id": self.cn_review_packet_id.id,
            "target": "current",
        }

    def action_print_cn_review_packet(self):
        self.ensure_one()
        if not self.cn_review_packet_id:
            raise UserError(_("该规则版本尚未建立中国专业复核包。"))
        return self.cn_review_packet_id.action_print_review_packet()
