from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SudoChinaEinvoiceParseWizard(models.TransientModel):
    _name = "sudo.cn.einvoice.parse.wizard"
    _description = "Submit China Electronic Invoice XBRL Parse"
    _check_company_auto = True

    dataset_id = fields.Many2one(
        "sudo.cn.external.dataset",
        string="电子发票数据集",
        required=True,
        check_company=True,
        domain="[('dataset_type', '=', 'electronic_invoice'), "
        "('state', '=', 'sealed')]",
    )
    company_id = fields.Many2one(
        related="dataset_id.company_id",
        readonly=True,
    )
    available_source_attachment_ids = fields.Many2many(
        related="dataset_id.source_attachment_ids",
        string="可选源文件",
        readonly=True,
    )
    source_attachment_id = fields.Many2one(
        "ir.attachment",
        string="解析源文件",
        required=True,
    )
    taxonomy_bundle_id = fields.Many2one(
        "sudo.cn.xbrl.taxonomy.bundle",
        string="分类标准包",
        required=True,
        domain="[('state', '=', 'sealed'), "
        "('standard_key', '=', 'mof_einvoice')]",
    )
    timeout_seconds = fields.Integer(
        string="超时秒数",
        required=True,
        default=300,
    )

    @api.onchange("dataset_id")
    def _onchange_dataset_id(self):
        attachments = self.dataset_id.source_attachment_ids
        self.source_attachment_id = attachments if len(attachments) == 1 else False

    @api.model
    def default_get(self, field_names):
        values = super().default_get(field_names)
        if "taxonomy_bundle_id" in field_names:
            bundle = self.env["sudo.cn.xbrl.taxonomy.bundle"].search(
                [
                    ("standard_key", "=", "mof_einvoice"),
                    ("state", "=", "sealed"),
                ],
                order="sealed_at desc, id desc",
                limit=1,
            )
            values["taxonomy_bundle_id"] = bundle.id
        return values

    def action_queue(self):
        self.ensure_one()
        if self.source_attachment_id not in self.dataset_id.source_attachment_ids:
            raise UserError(_("解析源文件必须属于所选电子发票数据集。"))
        job = self.env["sudo.cn.einvoice.xbrl.job"].with_company(
            self.company_id
        ).enqueue(
            self.dataset_id,
            self.source_attachment_id,
            self.taxonomy_bundle_id,
            timeout=self.timeout_seconds,
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("电子发票 XBRL 解析任务"),
            "res_model": "sudo.cn.einvoice.xbrl.job",
            "res_id": job.id,
            "view_mode": "form",
            "target": "current",
        }
