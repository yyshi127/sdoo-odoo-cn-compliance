from copy import deepcopy

from odoo import models


_CAPABILITY_WRITE_MARKER = object()


class SudoComplianceCountryPack(models.Model):
    _inherit = "sudo.compliance.country.pack"

    def write(self, values):
        if (
            "capability_json" not in values
            or self.env.context.get("cn_xbrl_capability_transition")
            is _CAPABILITY_WRITE_MARKER
        ):
            return super().write(values)
        china_pack = self.env.ref(
            "sudo_country_pack_cn.compliance_country_pack_cn",
            raise_if_not_found=False,
        )
        if not china_pack or china_pack not in self:
            return super().write(values)
        result = True
        for country_pack in self:
            record_values = dict(values)
            if country_pack == china_pack:
                capabilities = deepcopy(values.get("capability_json") or {})
                features = capabilities.setdefault("features", {})
                features["einvoice_xbrl_parser"] = True
                record_values["capability_json"] = capabilities
            result = (
                super(SudoComplianceCountryPack, country_pack).write(
                    record_values
                )
                and result
            )
        return result
