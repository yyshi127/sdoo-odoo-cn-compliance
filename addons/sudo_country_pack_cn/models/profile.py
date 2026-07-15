from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .compliance_engine import USCC_REGISTRATION_TYPES


class SudoComplianceProfile(models.Model):
    _inherit = "sudo.compliance.profile"

    is_china_profile = fields.Boolean(compute="_compute_is_china_profile")
    cn_taxpayer_classification_ids = fields.One2many(
        "sudo.cn.taxpayer.classification",
        "profile_id",
        string="中国纳税人身份快照",
    )
    cn_external_dataset_ids = fields.One2many(
        "sudo.cn.external.dataset",
        "profile_id",
        string="中国外部监管数据集",
    )

    @api.depends("country_id.code")
    def _compute_is_china_profile(self):
        for profile in self:
            profile.is_china_profile = profile.country_id.code == "CN"

    @api.model_create_multi
    def create(self, vals_list):
        profiles = super().create(vals_list)
        profiles._ensure_cn_obligation_templates()
        return profiles

    def write(self, values):
        result = super().write(values)
        if {"country_id", "country_pack_id"} & set(values):
            self._ensure_cn_obligation_templates()
        return result

    def _ensure_cn_obligation_templates(self):
        china_profiles = self.filtered("is_china_profile")
        if not china_profiles:
            return self.env["sudo.compliance.obligation"]
        from odoo.addons.sudo_country_pack_cn.hooks import seed_cn_obligations

        return seed_cn_obligations(self.env, china_profiles)

    def _cn_activation_issues(self):
        self.ensure_one()
        if not self.is_china_profile:
            return []
        today = fields.Date.context_today(self)
        registrations = self.registration_ids.filtered(
            lambda registration: (
                (registration.registration_type or "").strip().lower()
                in USCC_REGISTRATION_TYPES
                and registration.state == "active"
                and (
                    not registration.valid_from
                    or registration.valid_from <= today
                )
                and (
                    not registration.valid_to
                    or registration.valid_to >= today
                )
                and bool(
                    registration.registration_number
                    and registration.registration_number.strip()
                )
            )
        )
        issues = []
        if not registrations:
            issues.append(_("未建立有效的统一社会信用代码受控登记记录"))
        elif len(registrations) > 1:
            issues.append(_("存在多个同时有效的统一社会信用代码登记记录"))
        elif not registrations.evidence_attachment_ids:
            issues.append(_("统一社会信用代码登记尚未上传证明附件线索"))
        classifications = self.env[
            "sudo.cn.taxpayer.classification"
        ]._for_profile_date(self, today)
        if not classifications:
            issues.append(_("未建立当前有效的中国纳税人身份快照"))
        elif len(classifications) > 1:
            issues.append(_("当前期间存在多份中国纳税人身份快照"))
        elif classifications.state != "verified":
            issues.append(_("当前中国纳税人身份快照尚未核验"))
        elif classifications._current_integrity_state() != "verified":
            issues.append(_("中国纳税人身份快照证据完整性校验失败"))
        return issues

    def _activation_issues(self):
        self.ensure_one()
        return super()._activation_issues() + self._cn_activation_issues()

    def action_seed_cn_obligations(self):
        china_profiles = self.filtered("is_china_profile")
        if len(china_profiles) != len(self):
            raise UserError(_("该操作仅适用于中国合规档案。"))
        before = self.env["sudo.compliance.obligation"].search_count(
            [("profile_id", "in", self.ids)]
        )
        self._ensure_cn_obligation_templates()
        after = self.env["sudo.compliance.obligation"].search_count(
            [("profile_id", "in", self.ids)]
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("中国候选义务已检查"),
                "message": _("已补充 %(count)s 项缺失候选义务。", count=after - before),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.client", "tag": "reload"},
            },
        }
