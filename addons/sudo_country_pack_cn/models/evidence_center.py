from odoo import _, api, fields, models


class SudoChinaEvidenceCenterEvidence(models.Model):
    _inherit = "sudo.compliance.evidence"

    cn_evidence_source_summary = fields.Char(
        string="Evidence Source",
        compute="_compute_cn_evidence_center_display",
    )
    cn_evidence_blocker_summary = fields.Char(
        string="Evidence Blockers",
        compute="_compute_cn_evidence_center_display",
    )

    @api.depends(
        "state",
        "document_checksum",
        "assessment_id",
        "finding_id",
        "task_id",
        "filing_id",
        "verified_by_id",
        "verified_at",
    )
    def _compute_cn_evidence_center_display(self):
        for evidence in self:
            evidence.cn_evidence_source_summary = (
                evidence._cn_evidence_source_summary()
            )
            evidence.cn_evidence_blocker_summary = (
                evidence._cn_evidence_blocker_summary()
            )

    def _cn_evidence_source_summary(self):
        self.ensure_one()
        if self.task_id:
            return _("Task: %(name)s") % {"name": self.task_id.display_name}
        if self.filing_id:
            return _("Filing: %(name)s") % {"name": self.filing_id.display_name}
        if self.finding_id:
            return _("Finding: %(name)s") % {"name": self.finding_id.display_name}
        if self.assessment_id:
            return _("Assessment: %(name)s") % {
                "name": self.assessment_id.display_name
            }
        return _("No source linked")

    def _cn_evidence_blocker_summary(self):
        self.ensure_one()
        blockers = []
        if not (
            self.assessment_id or self.finding_id or self.task_id or self.filing_id
        ):
            blockers.append(_("no linked source"))
        if self.state != "verified":
            if self.state == "submitted":
                blockers.append(_("verification pending"))
            elif self.state == "rejected":
                blockers.append(_("evidence rejected"))
            else:
                blockers.append(_("evidence not submitted"))
        if not self.document_checksum:
            blockers.append(_("checksum not frozen"))
        if self.state == "verified" and (
            not self.verified_by_id or not self.verified_at
        ):
            blockers.append(_("verification metadata incomplete"))
        if not blockers:
            return _("No blocker: evidence is verified and traceable.")
        return _("Blocked by: %(blockers)s") % {
            "blockers": "; ".join(dict.fromkeys(blockers))
        }


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
