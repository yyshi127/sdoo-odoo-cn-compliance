from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SudoComplianceProfile(models.Model):
    _inherit = "sudo.compliance.profile"

    is_china_profile = fields.Boolean(compute="_compute_is_china_profile")

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
