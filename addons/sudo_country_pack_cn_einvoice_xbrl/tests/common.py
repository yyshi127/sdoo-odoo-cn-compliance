import io
import zipfile

from odoo import Command
from odoo.tests import TransactionCase


NAMESPACE = "http://xbrl.mof.gov.cn/taxonomy/2023-12-31/einv"
ENTRY_NAMESPACE = NAMESPACE + "/einv_receiver_entry_point"


class ChinaXbrlCommon(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.country = cls.env.ref("base.cn")
        cls.currency = cls.env.ref("base.CNY")
        cls.company = cls.env["res.company"].create(
            {
                "name": "China XBRL Test Company",
                "currency_id": cls.currency.id,
                "country_id": cls.country.id,
                "account_fiscal_country_id": cls.country.id,
            }
        )
        cls.profile = cls.env["sudo.compliance.profile"].with_company(
            cls.company
        ).create(
            {
                "company_id": cls.company.id,
                "country_id": cls.country.id,
                "country_pack_id": cls.env.ref(
                    "sudo_country_pack_cn.compliance_country_pack_cn"
                ).id,
            }
        )
        manager_group = cls.env.ref(
            "sudo_global_finance.group_compliance_manager"
        )
        cls.reviewer = cls.env["res.users"].create(
            {
                "name": "China XBRL Independent Reviewer",
                "login": "cn_xbrl_independent_reviewer",
                "company_id": cls.company.id,
                "company_ids": [Command.set(cls.company.ids)],
                "group_ids": [Command.link(manager_group.id)],
            }
        )

    def _zip_bytes(self, files):
        stream = io.BytesIO()
        with zipfile.ZipFile(
            stream,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            for name, content in files.items():
                archive.writestr(name, content)
        return stream.getvalue()

    def _taxonomy_bytes(self, namespace=NAMESPACE):
        schema = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<xsd:schema xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
            'xmlns:link="http://www.xbrl.org/2003/linkbase" '
            f'targetNamespace="{ENTRY_NAMESPACE}">'
            '<xsd:annotation><xsd:appinfo>'
            '<link:roleType id="testRole" '
            'roleURI="http://example.test/role/100801 "/>'
            '</xsd:appinfo></xsd:annotation>'
            f'<xsd:import namespace="{namespace}" '
            'schemaLocation="einv/einv_cor-20231231.xsd"/>'
            '</xsd:schema>'
        ).encode()
        return self._zip_bytes(
            {
                "official/einv-20231231/"
                "einv_entry_point_2023-12-31.xsd": schema,
                "official/einv-20231231/readme.txt": b"test taxonomy",
            }
        )

    def _attachment(self, name, raw):
        return self.env["ir.attachment"].create(
            {
                "name": name,
                "raw": raw,
                "mimetype": "application/zip",
            }
        )

    def _taxonomy(self, suffix="1", seal=True):
        attachment = self._attachment(
            f"mof-taxonomy-{suffix}.zip",
            self._taxonomy_bytes(),
        )
        bundle = self.env["sudo.cn.xbrl.taxonomy.bundle"].create(
            {
                "standard_key": "mof_einvoice",
                "official_title": "电子凭证会计数据标准-电子发票测试包",
                "namespace": NAMESPACE,
                "entry_point_namespace": ENTRY_NAMESPACE,
                "version": "2023-12-31",
                "publication_date": "2025-05-19",
                "source_url": "https://kjs.mof.gov.cn/test/einvoice.html",
                "source_reference": f"MOF-EINV-TEST-{suffix}",
                "entry_point_hint": "einv_entry_point_2023-12-31.xsd",
                "compatibility_profile": "trim_role_uri_whitespace_v1",
                "compatibility_reason": (
                    "测试包模拟官方角色 URI 尾空格，仅在工作副本受控修剪并保留原包。"
                ),
                "bundle_attachment_ids": [Command.set(attachment.ids)],
            }
        )
        if seal:
            bundle.with_user(self.reviewer).action_seal()
        return bundle

    def _dataset(self, suffix="1"):
        attachment = self._attachment(
            f"einv-source-{suffix}.zip",
            self._zip_bytes({"invoice.xml": b"controlled test instance"}),
        )
        dataset = self.env["sudo.cn.external.dataset"].with_company(
            self.company
        ).create(
            {
                "profile_id": self.profile.id,
                "dataset_type": "electronic_invoice",
                "period_start": "2026-01-01",
                "period_end": "2026-06-30",
                "coverage_scope": "full",
                "scope_note": "测试期间完整电子发票包。",
                "source_channel": "official_export",
                "source_system_name": "测试电子发票平台",
                "source_reference": f"EINV-XBRL-{suffix}",
                "source_generated_at": "2026-06-30 09:00:00",
                "data_format": "zip",
                "authorization_basis": "测试公司自有账户导出。",
                "acquired_at": "2026-06-30 10:00:00",
                "declared_record_count": 1,
                "currency_id": self.currency.id,
                "declared_total_amount": 10170,
                "declared_tax_amount": 1170,
                "source_attachment_ids": [Command.set(attachment.ids)],
                "authenticity_state": "not_checked",
            }
        )
        dataset.with_user(self.reviewer).action_seal()
        return dataset

    def _document_payload(self, suffix="1"):
        return {
            "source_document_key": f"batch/invoice-{suffix}.xml",
            "invoice_number": f"2244200000092129{suffix.zfill(4)}",
            "request_time": "2026-06-30 08:30:00",
            "seller_name": "测试销售方有限公司",
            "seller_tax_id": "91440101TESTSELLER1",
            "accounting_entity_name": self.company.name,
            "accounting_entity_tax_id": "91440101TESTBUYER01",
            "currency_code": "CNY",
            "untaxed_amount": "9000.00",
            "tax_amount": "1170.00",
            "total_amount": "10170.00",
            "source_fact_count": 20,
            "source_fact_digest": "b" * 64,
            "accounting_documents": [],
        }

    def _completed_result(self, run, suffix="1"):
        return {
            "schema_version": 1,
            "status": "completed",
            "observed_input_sha256": run.input_sha256,
            "arelle_version": "2.42.1",
            "source_fact_count": 20,
            "warning_count": 0,
            "error_count": 0,
            "parser_log_checksum": "c" * 64,
            "taxonomy_compatibility_profile": (
                "trim_role_uri_whitespace_v1"
            ),
            "taxonomy_patch_count": 1,
            "working_taxonomy_checksum": "e" * 64,
            "documents": [self._document_payload(suffix)],
            "worker_exit_code": 0,
            "worker_result_checksum": "d" * 64,
        }
