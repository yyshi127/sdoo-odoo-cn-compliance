from odoo import _, models


class SudoChinaEvidenceCenterProfile(models.Model):
    _inherit = "sudo.compliance.profile"

    def action_cn_open_workbench_evidence_center(self):
        self.ensure_one()
        action = self.env.ref(
            "sudo_country_pack_cn.action_cn_evidence_center",
            raise_if_not_found=False,
        )
        domain = [
            ("company_id", "=", self.company_id.id),
            "|",
            ("assessment_id.profile_id", "=", self.id),
            "|",
            ("finding_id.assessment_id.profile_id", "=", self.id),
            "|",
            ("task_id.assessment_id.profile_id", "=", self.id),
            ("filing_id.profile_id", "=", self.id),
        ]
        if action:
            result = action.sudo().read()[0]
            result["domain"] = domain
            result["context"] = {
                "search_default_cn_related": 1,
                "search_default_group_state": 1,
            }
            return result
        return {
            "type": "ir.actions.act_window",
            "name": _("中国证据中心"),
            "res_model": "sudo.compliance.evidence",
            "view_mode": "list,form",
            "domain": domain,
            "context": {"search_default_group_state": 1},
            "target": "current",
        }
