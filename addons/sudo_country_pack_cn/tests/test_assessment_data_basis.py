from odoo import Command
from odoo.addons.sudo_country_pack_cn.models.invoice_normalization import (
    _PARSE_RUN_MARKER,
)
from odoo.addons.sudo_country_pack_cn.models.tax_data_normalization import (
    _TAX_PARSE_RUN_MARKER,
)
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestChinaAssessmentDataBasis(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.country = cls.env.ref("base.cn")
        cls.currency = cls.env.ref("base.CNY")
        cls.country_pack = cls.env.ref(
            "sudo_country_pack_cn.compliance_country_pack_cn"
        )
        cls.company = cls.env["res.company"].create(
            {
                "name": "China Assessment Data Basis Test Company",
                "country_id": cls.country.id,
                "account_fiscal_country_id": cls.country.id,
                "currency_id": cls.currency.id,
            }
        )
        cls.profile = cls.env["sudo.compliance.profile"].with_company(
            cls.company
        ).create(
            {
                "company_id": cls.company.id,
                "country_id": cls.country.id,
                "country_pack_id": cls.country_pack.id,
            }
        )
        cls.reviewer = cls.env["res.users"].create(
            {
                "name": "China Assessment Data Basis Reviewer",
                "login": "cn_assessment_data_basis_reviewer",
                "company_id": cls.company.id,
                "company_ids": [Command.set(cls.company.ids)],
                "group_ids": [
                    Command.link(
                        cls.env.ref(
                            "sudo_global_finance.group_compliance_manager"
                        ).id
                    )
                ],
            }
        )

    def _assessment(self):
        return self.env["sudo.compliance.assessment"].with_company(
            self.company
        ).create(
            {
                "profile_id": self.profile.id,
                "evaluation_date": "2026-07-01",
                "period_start": "2026-06-01",
                "period_end": "2026-06-30",
            }
        )

    def _attachment(self, dataset_type):
        return self.env["ir.attachment"].create(
            {
                "name": f"cn-assessment-data-basis-{dataset_type}.json",
                "raw": f'{{"dataset_type": "{dataset_type}"}}'.encode(),
                "mimetype": "application/json",
            }
        )

    def _dataset(self, dataset_type):
        attachment = self._attachment(dataset_type)
        dataset = self.env["sudo.cn.external.dataset"].create(
            {
                "profile_id": self.profile.id,
                "dataset_type": dataset_type,
                "period_start": "2026-06-01",
                "period_end": "2026-06-30",
                "coverage_scope": "full",
                "scope_note": "Controlled test dataset for required type coverage.",
                "source_channel": "official_export",
                "source_system_name": "Controlled test source",
                "source_reference": f"CN-ASSESSMENT-{dataset_type}",
                "source_generated_at": "2026-06-30 09:00:00",
                "data_format": "json",
                "authorization_basis": "Controlled automated test export.",
                "acquired_at": "2026-06-30 10:00:00",
                "declared_record_count": 1,
                "currency_id": self.currency.id,
                "source_attachment_ids": [Command.set(attachment.ids)],
                "authenticity_state": "not_applicable",
            }
        )
        dataset.with_user(self.reviewer).with_company(self.company).action_seal()
        return dataset

    def _make_ready_dataset(self, dataset_type):
        dataset = self._dataset(dataset_type)
        attachment = dataset.source_attachment_ids[:1]
        if dataset_type == "electronic_invoice":
            run = self.env["sudo.cn.external.parse.run"].with_user(
                self.reviewer
            ).with_company(self.company)._start_for_dataset(
                dataset,
                attachment,
                parser_key="test-cn-einvoice",
                parser_version="1",
                parser_distribution="test",
                taxonomy_namespace="test-cn",
                taxonomy_version="1",
                taxonomy_checksum="b" * 64,
                taxonomy_source_reference="TEST",
            )
            run.with_context(cn_parse_run_transition=_PARSE_RUN_MARKER).write(
                {
                    "state": "succeeded",
                    "finished_at": "2026-06-30 11:01:00",
                    "document_count": 1,
                    "valid_document_count": 1,
                    "output_checksum": "c" * 64,
                }
            )
        else:
            count_field = {
                "vat_filing": "vat_filing_count",
                "cit_filing": "cit_filing_count",
                "iit_withholding": "iit_withholding_count",
                "payroll_summary": "payroll_summary_count",
                "tax_payment": "tax_payment_count",
            }[dataset_type]
            values = {
                "state": "succeeded",
                "finished_at": "2026-06-30 11:01:00",
                "record_count": 1,
                "valid_record_count": 1,
                "output_checksum": "f" * 64,
            }
            values[count_field] = 1
            run = self.env["sudo.cn.tax.data.parse.run"].with_user(
                self.reviewer
            ).with_company(self.company)._start_for_dataset(
                dataset,
                attachment,
                mapping_key=f"test-{dataset_type}",
                mapping_version="1",
            )
            run.with_context(
                cn_tax_parse_run_transition=_TAX_PARSE_RUN_MARKER
            ).write(values)
        dataset.invalidate_recordset()
        return dataset

    def test_country_pack_advertises_assessment_data_basis(self):
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_assessment_data_basis"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_assessment_obligation_basis"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_assessment_required_dataset_type_coverage"
            ]
        )

    def test_assessment_without_datasets_shows_missing_data_basis(self):
        assessment = self._assessment()
        assessment.invalidate_recordset()

        self.assertEqual(assessment.cn_data_basis_state, "missing")
        self.assertEqual(assessment.cn_data_basis_dataset_count, 0)
        self.assertEqual(assessment.cn_data_basis_ready_type_count, 0)
        self.assertGreater(assessment.cn_data_basis_missing_type_count, 0)
        self.assertIn(
            "Electronic invoices",
            assessment.cn_data_basis_missing_type_summary,
        )
        self.assertIn(
            assessment.cn_data_basis_missing_type_summary,
            assessment.cn_data_basis_next_action,
        )
        self.assertEqual(assessment.cn_obligation_basis_state, "attention")
        self.assertEqual(
            assessment.cn_obligation_basis_candidate_count,
            len(self.profile.obligation_ids),
        )
        self.assertEqual(
            assessment.cn_obligation_basis_pending_count,
            len(self.profile.obligation_ids),
        )

    def test_assessment_opens_period_scoped_data_basis(self):
        assessment = self._assessment()
        action = assessment.action_cn_open_assessment_data_basis()

        self.assertEqual(action["res_model"], "sudo.cn.external.dataset")
        self.assertIn(("profile_id", "=", self.profile.id), action["domain"])
        self.assertIn(("period_end", ">=", assessment.period_start), action["domain"])
        self.assertIn(("period_start", "<=", assessment.period_end), action["domain"])
        self.assertEqual(
            action["context"]["search_default_group_dataset_type"],
            1,
        )

    def test_assessment_opens_profile_scoped_obligation_basis(self):
        assessment = self._assessment()
        action = assessment.action_cn_open_assessment_obligation_basis()

        self.assertEqual(action["res_model"], "sudo.compliance.obligation")
        self.assertIn(("profile_id", "=", self.profile.id), action["domain"])
        self.assertEqual(action["context"]["default_profile_id"], self.profile.id)

    def test_draft_dataset_makes_data_basis_warning(self):
        self.env["sudo.cn.external.dataset"].create(
            {
                "profile_id": self.profile.id,
                "dataset_type": "electronic_invoice",
                "period_start": "2026-06-01",
                "period_end": "2026-06-30",
                "coverage_scope": "partial",
                "declared_record_count": 1,
                "currency_id": self.currency.id,
            }
        )
        assessment = self._assessment()
        assessment.invalidate_recordset()

        self.assertEqual(assessment.cn_data_basis_state, "warning")
        self.assertEqual(assessment.cn_data_basis_dataset_count, 1)
        self.assertEqual(assessment.cn_data_basis_warning_count, 1)

    def test_partial_ready_dataset_keeps_data_basis_warning(self):
        self._make_ready_dataset("electronic_invoice")
        assessment = self._assessment()
        assessment.invalidate_recordset()

        self.assertEqual(assessment.cn_data_basis_state, "warning")
        self.assertEqual(assessment.cn_data_basis_ready_type_count, 1)
        self.assertGreater(assessment.cn_data_basis_missing_type_count, 0)
        self.assertIn("VAT filings", assessment.cn_data_basis_missing_type_summary)

    def test_all_required_dataset_types_make_data_basis_ready(self):
        for dataset_type in (
            "electronic_invoice",
            "vat_filing",
            "cit_filing",
            "iit_withholding",
            "payroll_summary",
            "tax_payment",
        ):
            self._make_ready_dataset(dataset_type)
        assessment = self._assessment()
        assessment.invalidate_recordset()

        self.assertEqual(assessment.cn_data_basis_state, "ready")
        self.assertEqual(assessment.cn_data_basis_missing_type_count, 0)
        self.assertFalse(assessment.cn_data_basis_missing_type_summary)
        self.assertEqual(
            assessment.cn_data_basis_ready_type_count,
            assessment.cn_data_basis_required_type_count,
        )

    def test_reviewed_obligations_make_assessment_obligation_basis_ready(self):
        source = self.env["sudo.compliance.authority.source"].search(
            [("country_id", "=", self.country.id)],
            limit=1,
        )
        self.assertTrue(source)
        self.profile.obligation_ids.write(
            {
                "applicability": "not_applicable",
                "authority_source_id": source.id,
                "justification": "All candidate obligations are reviewed as not applicable for this automated test.",
            }
        )
        assessment = self._assessment()
        assessment.invalidate_recordset()

        self.assertEqual(assessment.cn_obligation_basis_state, "ready")
        self.assertEqual(assessment.cn_obligation_basis_pending_count, 0)
        self.assertEqual(assessment.cn_obligation_basis_applicable_count, 0)
        self.assertTrue(assessment.cn_obligation_basis_next_action)
