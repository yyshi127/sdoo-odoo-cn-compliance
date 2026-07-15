from odoo import _, api, models

from odoo.addons.sudo_country_pack_cn.hooks import SETUP_DEFAULTS


class SudoComplianceSetupWizard(models.TransientModel):
    _inherit = "sudo.compliance.setup.wizard"

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        country = self.env["res.country"].browse(values.get("country_id"))
        if country.code == "CN":
            for field_name, default_value in SETUP_DEFAULTS.items():
                if field_name in fields_list:
                    values[field_name] = default_value
        return values

    def _apply_cn_setup_defaults(self):
        for wizard in self:
            if wizard.country_id.code == "CN":
                for field_name, default_value in SETUP_DEFAULTS.items():
                    wizard[field_name] = default_value
            elif wizard.registration_name == SETUP_DEFAULTS["registration_name"]:
                wizard.registration_name = _("主要公司登记")

    @api.onchange("country_id")
    def _onchange_country_id(self):
        result = super()._onchange_country_id()
        self._apply_cn_setup_defaults()
        return result

    @api.onchange("country_pack_id")
    def _onchange_country_pack_id_cn_defaults(self):
        self._apply_cn_setup_defaults()
