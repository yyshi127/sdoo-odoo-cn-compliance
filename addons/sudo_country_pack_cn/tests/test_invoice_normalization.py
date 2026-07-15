from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestChinaInvoiceNormalization(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.country = cls.env.ref("base.cn")
        cls.currency = cls.env.ref("base.CNY")
        cls.company = cls.env["res.company"].create(
            {
                "name": "China Invoice Normalization Test Company",
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
        cls.reviewer = cls.env["res.users"].create(
            {
                "name": "China Invoice Dataset Reviewer",
                "login": "cn_invoice_dataset_reviewer",
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

    def _attachment(self, suffix="1"):
        return self.env["ir.attachment"].create(
            {
                "name": f"einvoice-package-{suffix}.zip",
                "raw": f"controlled XBRL package {suffix}".encode(),
                "mimetype": "application/zip",
            }
        )

    def _dataset(self, suffix="1", profile=None, company=None, seal=True):
        profile = profile or self.profile
        company = company or profile.company_id
        attachment = self._attachment(suffix)
        dataset = self.env["sudo.cn.external.dataset"].with_company(
            company
        ).create(
            {
                "profile_id": profile.id,
                "dataset_type": "electronic_invoice",
                "period_start": "2026-01-01",
                "period_end": "2026-06-30",
                "coverage_scope": "full",
                "scope_note": "测试期间完整受控电子发票包，仅验证解析契约。",
                "source_channel": "official_export",
                "source_system_name": "测试电子发票平台",
                "source_reference": f"EINV-DATASET-{suffix}",
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
        if seal:
            dataset.with_user(self.reviewer).with_company(company).action_seal()
        return dataset

    def _start_run(self, dataset, suffix="1"):
        return self.env["sudo.cn.external.parse.run"].with_company(
            dataset.company_id
        )._start_for_dataset(
            dataset,
            dataset.source_attachment_ids[:1],
            parser_key="mof_einvoice_xbrl",
            parser_version=f"test-{suffix}",
            parser_distribution="arelle-release test contract",
            taxonomy_namespace=(
                "http://xbrl.mof.gov.cn/taxonomy/2023-12-31/einv"
            ),
            taxonomy_version="2023-12-31",
            taxonomy_checksum="a" * 64,
            taxonomy_source_reference="MOF-EINV-STANDARD-2025-TEST",
        )

    def _document_payload(self, suffix="1", **overrides):
        payload = {
            "source_document_key": f"instance-{suffix}.xml",
            "invoice_number": f"2244200000092129{suffix.zfill(4)}",
            "invoice_type_code": "VAT_SPECIAL",
            "request_time": "2026-06-30 08:30:00",
            "seller_name": "测试销售方有限公司",
            "seller_tax_id": "91440101TESTSELLER1",
            "accounting_entity_name": self.company.name,
            "accounting_entity_tax_id": "91440101TESTBUYER01",
            "currency_code": "CNY",
            "untaxed_amount": "9000.00",
            "tax_amount": "1170.00",
            "total_amount": "10170.00",
            "is_red": False,
            "is_booked": True,
            "is_checked": True,
            "is_paid": True,
            "contract_number": "R9988888",
            "bank_receipt_number": "BANK-TEST-001",
            "usage_confirmation": "抵扣税款",
            "source_fact_count": 30,
            "source_fact_digest": "b" * 64,
            "accounting_documents": [
                {
                    "voucher_number": "R0009",
                    "posting_date": "2026-06-30",
                    "accounting_period": "2026-06",
                    "summary": "测试电子发票入账",
                    "entries": [
                        {
                            "direction": "借方",
                            "general_ledger_subject": "原材料",
                            "amount": "9000.00",
                        },
                        {
                            "direction": "借方",
                            "general_ledger_subject": "应交税费",
                            "subsidiary_ledger_subject": "应交增值税-进项税额",
                            "amount": "1170.00",
                        },
                        {
                            "direction": "贷方",
                            "general_ledger_subject": "银行存款",
                            "amount": "10170.00",
                        },
                    ],
                }
            ],
        }
        payload.update(overrides)
        return payload

    def _complete(self, run, documents=None, **overrides):
        values = {
            "observed_input_sha256": run.input_sha256,
            "source_fact_count": 30,
            "warning_count": 0,
            "error_count": 0,
            "parser_log_checksum": "c" * 64,
        }
        values.update(overrides)
        return run._record_success(
            (
                [self._document_payload()]
                if documents is None
                else documents
            ),
            **values,
        )

    def test_direct_creation_of_governed_results_is_blocked(self):
        with self.assertRaises(AccessError):
            self.env["sudo.cn.external.parse.run"].create({})
        with self.assertRaises(AccessError):
            self.env["sudo.cn.einvoice.document"].create({})
        with self.assertRaises(AccessError):
            self.env["sudo.cn.einvoice.accounting.document"].create({})
        with self.assertRaises(AccessError):
            self.env["sudo.cn.einvoice.accounting.entry"].create({})

    def test_parse_requires_sealed_intact_dataset_and_its_attachment(self):
        draft = self._dataset("draft", seal=False)

        with self.assertRaises(UserError):
            self._start_run(draft)

        draft.separation_exception_reason = (
            "隔离测试环境没有第二名复核人，本记录仅用于解析门禁测试。"
        )
        draft.action_seal()
        other_attachment = self._attachment("other")
        with self.assertRaises(UserError):
            self.env["sudo.cn.external.parse.run"]._start_for_dataset(
                draft,
                other_attachment,
                parser_key="mof_einvoice_xbrl",
                parser_version="test",
                parser_distribution="arelle-release test contract",
                taxonomy_namespace="urn:test",
                taxonomy_version="test",
                taxonomy_checksum="a" * 64,
                taxonomy_source_reference="TEST",
            )

        draft.source_attachment_ids.raw = b"tampered after seal"
        with self.assertRaises(UserError):
            self._start_run(draft)

    def test_success_creates_immutable_normalized_invoice_hierarchy(self):
        dataset = self._dataset("success")
        run = self._start_run(dataset)

        result = self._complete(run)

        self.assertTrue(result)
        self.assertEqual(run.state, "succeeded")
        self.assertEqual(run.document_count, 1)
        self.assertEqual(run.valid_document_count, 1)
        self.assertEqual(run.warning_document_count, 0)
        self.assertEqual(run.error_document_count, 0)
        self.assertEqual(len(run.output_checksum), 64)
        document = run.document_ids
        self.assertEqual(document.quality_state, "valid")
        self.assertEqual(document.invoice_number, "22442000000921290001")
        self.assertEqual(document.seller_tax_id, "91440101TESTSELLER1")
        self.assertEqual(document.untaxed_amount, 9000)
        self.assertEqual(document.tax_amount, 1170)
        self.assertEqual(document.total_amount, 10170)
        self.assertEqual(document.is_red, "no")
        self.assertEqual(document.is_booked, "yes")
        self.assertEqual(document.source_coverage_scope, "full")
        self.assertEqual(document.source_authenticity_state, "not_checked")
        self.assertEqual(len(document.document_checksum), 64)
        accounting = document.accounting_document_ids
        self.assertEqual(len(accounting), 1)
        self.assertEqual(accounting.voucher_number, "R0009")
        self.assertEqual(accounting.debit_total, 10170)
        self.assertEqual(accounting.credit_total, 10170)
        self.assertEqual(accounting.balance_difference, 0)
        self.assertEqual(len(accounting.entry_ids), 3)
        self.assertEqual(
            set(accounting.entry_ids.mapped("direction")),
            {"debit", "credit"},
        )
        self.assertTrue(document.is_current_result)
        self.assertEqual(dataset.normalized_document_count, 1)
        self.assertEqual(dataset.current_parse_run_id, run)
        event = self.env["sudo.compliance.audit.event"].search(
            [
                ("record_id", "=", run.id),
                ("event_key", "=", "cn_external_parse.succeeded"),
            ]
        )
        self.assertEqual(event.details_json["document_count"], 1)
        self.assertEqual(event.details_json["output_checksum"], run.output_checksum)

    def test_observed_input_hash_mismatch_records_failure_without_output(self):
        run = self._start_run(self._dataset("hash-mismatch"))

        result = self._complete(run, observed_input_sha256="d" * 64)

        self.assertFalse(result)
        self.assertEqual(run.state, "failed")
        self.assertEqual(run.error_code, "INPUT_HASH_MISMATCH")
        self.assertFalse(run.document_ids)

    def test_parser_errors_record_failure_without_normalized_documents(self):
        run = self._start_run(self._dataset("parser-error"))

        result = self._complete(
            run,
            warning_count=2,
            error_count=1,
        )

        self.assertFalse(result)
        self.assertEqual(run.state, "failed")
        self.assertEqual(run.error_code, "XBRL_VALIDATION_FAILED")
        self.assertEqual(run.parser_warning_count, 2)
        self.assertEqual(run.parser_error_count, 1)
        self.assertFalse(run.document_ids)

    def test_empty_parser_output_records_failure_without_documents(self):
        run = self._start_run(self._dataset("empty-output"))

        result = self._complete(run, [])

        self.assertFalse(result)
        self.assertEqual(run.state, "failed")
        self.assertEqual(run.error_code, "NO_NORMALIZED_DOCUMENTS")
        self.assertFalse(run.document_ids)

    def test_invalid_parser_log_checksum_records_failure(self):
        run = self._start_run(self._dataset("invalid-log-checksum"))

        result = self._complete(run, parser_log_checksum="not-a-sha256")

        self.assertFalse(result)
        self.assertEqual(run.state, "failed")
        self.assertEqual(run.error_code, "INVALID_PARSER_LOG_CHECKSUM")
        self.assertFalse(run.document_ids)

    def test_empty_or_duplicate_source_keys_fail_the_whole_run(self):
        empty_run = self._start_run(self._dataset("empty-key"), "empty")
        empty_payload = self._document_payload(
            "empty",
            source_document_key=" ",
        )

        self.assertFalse(self._complete(empty_run, [empty_payload]))
        self.assertEqual(empty_run.error_code, "INVALID_SOURCE_DOCUMENT_KEYS")

        duplicate_run = self._start_run(
            self._dataset("duplicate-key"),
            "duplicate",
        )
        first = self._document_payload("duplicate")
        second = self._document_payload(
            "duplicate-2",
            source_document_key=first["source_document_key"],
        )

        self.assertFalse(self._complete(duplicate_run, [first, second]))
        self.assertEqual(
            duplicate_run.error_code,
            "INVALID_SOURCE_DOCUMENT_KEYS",
        )

    def test_field_and_balance_errors_are_preserved_as_error_document(self):
        run = self._start_run(self._dataset("quality-error"))
        payload = self._document_payload(
            "quality-error",
            seller_name=False,
            total_amount="10000.00",
            accounting_documents=[
                {
                    "voucher_number": "ERR-001",
                    "posting_date": "2026-06-30",
                    "accounting_period": "2026-06",
                    "entries": [
                        {
                            "direction": "借方",
                            "general_ledger_subject": "原材料",
                            "amount": "9000.00",
                        },
                        {
                            "direction": "贷方",
                            "general_ledger_subject": "银行存款",
                            "amount": "8000.00",
                        },
                    ],
                }
            ],
        )

        self.assertTrue(self._complete(run, [payload]))

        document = run.document_ids
        self.assertEqual(run.state, "succeeded")
        self.assertEqual(run.error_document_count, 1)
        self.assertEqual(document.quality_state, "error")
        issue_codes = {issue["code"] for issue in document.issue_json}
        self.assertIn("MISSING_SELLER_NAME", issue_codes)
        self.assertIn("INVOICE_TOTAL_MISMATCH", issue_codes)
        self.assertIn("UNBALANCED_ACCOUNTING_DOCUMENT", issue_codes)

    def test_missing_accounting_reference_is_explicit_warning(self):
        run = self._start_run(self._dataset("quality-warning"))
        payload = self._document_payload(
            "quality-warning",
            accounting_documents=[],
        )

        self.assertTrue(self._complete(run, [payload]))

        document = run.document_ids
        self.assertEqual(document.quality_state, "warning")
        self.assertEqual(run.warning_document_count, 1)
        self.assertIn(
            "NO_ACCOUNTING_DOCUMENT_REFERENCE",
            {issue["code"] for issue in document.issue_json},
        )

    def test_failed_retry_keeps_previous_success_until_new_success(self):
        dataset = self._dataset("retry")
        first = self._start_run(dataset, "first")
        self.assertTrue(self._complete(first))

        failed = self._start_run(dataset, "failed")
        failed._record_failure("TEST_FAILURE", "测试失败，不替代成功结果。")

        self.assertEqual(first.state, "succeeded")
        self.assertEqual(failed.state, "failed")
        self.assertTrue(first.document_ids.is_current_result)

        replacement = self._start_run(dataset, "replacement")
        self.assertTrue(
            self._complete(
                replacement,
                [self._document_payload("replacement")],
            )
        )

        self.assertEqual(first.state, "superseded")
        self.assertEqual(replacement.state, "succeeded")
        self.assertFalse(first.document_ids.is_current_result)
        self.assertTrue(replacement.document_ids.is_current_result)
        self.assertEqual(dataset.current_parse_run_id, replacement)

    def test_only_one_parse_run_can_be_running_for_a_dataset(self):
        dataset = self._dataset("concurrent")
        running = self._start_run(dataset, "running")

        with self.assertRaises(UserError):
            self._start_run(dataset, "second")

        running._record_failure("TEST_STOP", "结束并发测试运行。")
        second = self._start_run(dataset, "second")
        self.assertEqual(second.state, "running")

    def test_normalized_hierarchy_is_immutable(self):
        run = self._start_run(self._dataset("immutable"))
        self.assertTrue(self._complete(run))
        document = run.document_ids
        accounting = document.accounting_document_ids
        entry = accounting.entry_ids[:1]

        with self.assertRaises(AccessError):
            document.write({"seller_name": "不得改写"})
        with self.assertRaises(AccessError):
            document.unlink()
        with self.assertRaises(AccessError):
            document.copy()
        with self.assertRaises(AccessError):
            accounting.write({"summary": "不得改写"})
        with self.assertRaises(AccessError):
            entry.write({"amount": 1})
        with self.assertRaises(AccessError):
            run.unlink()

    def test_tampering_after_parse_removes_document_from_current_results(self):
        dataset = self._dataset("post-parse-tamper")
        run = self._start_run(dataset, "post-parse-tamper")
        self.assertTrue(self._complete(run))
        document = run.document_ids
        self.assertTrue(document.is_current_result)

        dataset.source_attachment_ids.raw = b"changed after parse"

        document.invalidate_recordset(["is_current_result"])
        self.assertFalse(document.is_current_result)
        current = self.env["sudo.cn.einvoice.document"].search(
            [("is_current_result", "=", True)]
        )
        self.assertNotIn(document, current)
        self.assertFalse(dataset.current_parse_run_id)
        self.assertEqual(dataset.normalized_document_count, 0)

    def test_read_only_user_and_company_rule_isolate_results(self):
        own_run = self._start_run(self._dataset("own-company"))
        self.assertTrue(self._complete(own_run))
        other_company = self.env["res.company"].create(
            {
                "name": "Other Invoice Normalization Company",
                "currency_id": self.currency.id,
                "country_id": self.country.id,
                "account_fiscal_country_id": self.country.id,
            }
        )
        other_profile = self.env["sudo.compliance.profile"].with_company(
            other_company
        ).create(
            {
                "company_id": other_company.id,
                "country_id": self.country.id,
                "country_pack_id": self.env.ref(
                    "sudo_country_pack_cn.compliance_country_pack_cn"
                ).id,
            }
        )
        self.reviewer.write(
            {"company_ids": [Command.link(other_company.id)]}
        )
        other_dataset = self._dataset(
            "other-company",
            profile=other_profile,
            company=other_company,
        )
        other_run = self._start_run(other_dataset, "other")
        self.assertTrue(
            self._complete(
                other_run,
                [self._document_payload("other")],
            )
        )
        user = self.env["res.users"].create(
            {
                "name": "China Invoice Read Only User",
                "login": "cn_invoice_read_only_user",
                "company_id": self.company.id,
                "company_ids": [Command.set(self.company.ids)],
                "group_ids": [
                    Command.link(
                        self.env.ref(
                            "sudo_global_finance.group_compliance_user"
                        ).id
                    )
                ],
            }
        )
        documents = self.env["sudo.cn.einvoice.document"].with_user(
            user
        ).with_company(self.company)

        visible = documents.search([])

        self.assertEqual(visible, own_run.document_ids)
        self.assertEqual(set(visible.mapped("company_id").ids), {self.company.id})
        with self.assertRaises(AccessError):
            visible.write({"seller_name": "普通用户不可修改"})
