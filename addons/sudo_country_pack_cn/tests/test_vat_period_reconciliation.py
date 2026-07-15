import json
from unittest.mock import patch

from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestChinaVatPeriodReconciliation(AccountTestInvoicingCommon):
    chart_template = "cn"
    country_code = "CN"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.country = cls.env.ref("base.cn")
        cls.currency = cls.env.ref("base.CNY")
        cls.company.write(
            {
                "country_id": cls.country.id,
                "account_fiscal_country_id": cls.country.id,
                "currency_id": cls.currency.id,
            }
        )
        cls.company.partner_id.vat = "91440101MA5D123451"
        cls.country_pack = cls.env.ref(
            "sudo_country_pack_cn.compliance_country_pack_cn"
        )
        cls.profile = cls.env["sudo.compliance.profile"].search(
            [
                ("company_id", "=", cls.company.id),
                ("country_id", "=", cls.country.id),
            ],
            limit=1,
        )
        if cls.profile:
            cls.profile.country_pack_id = cls.country_pack
        else:
            cls.profile = cls.env["sudo.compliance.profile"].create(
                {
                    "company_id": cls.company.id,
                    "country_id": cls.country.id,
                    "country_pack_id": cls.country_pack.id,
                }
            )
        compliance_manager = cls.env.ref(
            "sudo_global_finance.group_compliance_manager"
        )
        compliance_user = cls.env.ref(
            "sudo_global_finance.group_compliance_user"
        )
        cls.reviewer = cls.env["res.users"].create(
            {
                "name": "China VAT Period Reviewer",
                "login": "cn_vat_period_reviewer",
                "company_id": cls.company.id,
                "company_ids": [Command.set(cls.company.ids)],
                "group_ids": [Command.set(compliance_manager.ids)],
            }
        )
        cls.read_only_user = cls.env["res.users"].create(
            {
                "name": "China VAT Period Reader",
                "login": "cn_vat_period_reader",
                "company_id": cls.company.id,
                "company_ids": [Command.set(cls.company.ids)],
                "group_ids": [Command.set(compliance_user.ids)],
            }
        )
        partner_values = {
            "property_account_receivable_id": cls.company_data[
                "default_account_receivable"
            ].id,
            "property_account_payable_id": cls.company_data[
                "default_account_payable"
            ].id,
        }
        cls.customer = cls.env["res.partner"].with_company(cls.company).create(
            {
                **partner_values,
                "name": "测试客户有限公司",
                "vat": "91440101MA5C11111A",
            }
        )
        cls.supplier = cls.env["res.partner"].with_company(cls.company).create(
            {
                **partner_values,
                "name": "测试供应商有限公司",
                "vat": "91440101MA5C22222B",
            }
        )

    def _attachment(self, name, raw, mimetype):
        return self.env["ir.attachment"].create(
            {"name": name, "raw": raw, "mimetype": mimetype}
        )

    def _external_dataset(
        self,
        dataset_type,
        suffix,
        attachment,
        record_count,
        *,
        data_format,
        coverage_scope="full",
        profile=None,
        company=None,
        reviewer=None,
    ):
        profile = profile or self.profile
        company = company or profile.company_id
        reviewer = reviewer or self.reviewer
        dataset = self.env["sudo.cn.external.dataset"].with_company(
            company
        ).create(
            {
                "profile_id": profile.id,
                "dataset_type": dataset_type,
                "period_start": "2026-06-01",
                "period_end": "2026-06-30",
                "coverage_scope": coverage_scope,
                "scope_note": "测试期间受控数据。",
                "source_channel": "official_export",
                "source_system_name": "测试受控数据源",
                "source_reference": f"VAT-PERIOD-{suffix}",
                "source_generated_at": "2026-07-01 09:00:00",
                "data_format": data_format,
                "authorization_basis": "测试公司自有账户受控导出。",
                "acquired_at": "2026-07-01 10:00:00",
                "declared_record_count": record_count,
                "currency_id": self.currency.id,
                "source_attachment_ids": [Command.set(attachment.ids)],
                "authenticity_state": "not_applicable",
            }
        )
        dataset.with_user(reviewer).with_company(company).action_seal()
        return dataset

    def _accounting_document(self, suffix, amount):
        formatted = f"{amount:.2f}"
        return {
            "voucher_number": f"TEST-VOUCHER-{suffix}",
            "posting_date": "2026-06-30",
            "accounting_period": "2026-06",
            "summary": "测试增值税期间勾稽入账",
            "entries": [
                {
                    "direction": "借方",
                    "general_ledger_subject": "测试借方科目",
                    "amount": formatted,
                },
                {
                    "direction": "贷方",
                    "general_ledger_subject": "测试贷方科目",
                    "amount": formatted,
                },
            ],
        }

    def _einvoice_payload(
        self,
        suffix,
        tax_amount,
        *,
        direction,
        request_time="2026-06-30 08:30:00",
    ):
        untaxed = 1000.0
        total = untaxed + tax_amount
        if direction == "output":
            seller_name = self.company.name
            seller_tax_id = self.company.partner_id.vat
            entity_name = self.customer.name
            entity_tax_id = self.customer.vat
        else:
            seller_name = self.supplier.name
            seller_tax_id = self.supplier.vat
            entity_name = self.company.name
            entity_tax_id = self.company.partner_id.vat
        return {
            "source_document_key": f"vat-period-{suffix}.xml",
            "invoice_number": f"TEST-VAT-INVOICE-{suffix}",
            "invoice_type_code": "VAT_TEST",
            "request_time": request_time,
            "seller_name": seller_name,
            "seller_tax_id": seller_tax_id,
            "accounting_entity_name": entity_name,
            "accounting_entity_tax_id": entity_tax_id,
            "currency_code": "CNY",
            "untaxed_amount": f"{untaxed:.2f}",
            "tax_amount": f"{tax_amount:.2f}",
            "total_amount": f"{total:.2f}",
            "is_red": False,
            "is_booked": True,
            "is_checked": True,
            "is_paid": False,
            "source_fact_count": 20,
            "source_fact_digest": "b" * 64,
            "accounting_documents": [
                self._accounting_document(suffix, total)
            ],
        }

    def _create_einvoices(
        self,
        suffix,
        payloads,
        *,
        coverage_scope="full",
    ):
        attachment = self._attachment(
            f"vat-period-einvoice-{suffix}.zip",
            f"controlled einvoice input {suffix}".encode(),
            "application/zip",
        )
        dataset = self._external_dataset(
            "electronic_invoice",
            f"einvoice-{suffix}",
            attachment,
            len(payloads),
            data_format="zip",
            coverage_scope=coverage_scope,
        )
        run = self.env["sudo.cn.external.parse.run"].with_user(
            self.reviewer
        ).with_company(self.company)._start_for_dataset(
            dataset,
            attachment,
            parser_key="mof_einvoice_xbrl",
            parser_version=f"vat-period-test-{suffix}",
            parser_distribution="arelle-release test contract",
            taxonomy_namespace=(
                "http://xbrl.mof.gov.cn/taxonomy/2023-12-31/einv"
            ),
            taxonomy_version="2023-12-31",
            taxonomy_checksum="a" * 64,
            taxonomy_source_reference="MOF-VAT-PERIOD-TEST",
        )
        result = run.with_user(self.reviewer)._record_success(
            payloads,
            observed_input_sha256=run.input_sha256,
            source_fact_count=20 * len(payloads),
            warning_count=0,
            error_count=0,
            parser_log_checksum="c" * 64,
        )
        self.assertTrue(result)
        return run.document_ids

    def _filing_record(self, suffix, output_tax, input_tax, payable):
        return {
            "source_record_key": f"VAT-FILING-{suffix}",
            "taxpayer_name": self.company.name,
            "taxpayer_id": self.company.partner_id.vat,
            "return_type_code": "VAT-GENERAL",
            "return_status": "accepted",
            "period_start": "2026-06-01",
            "period_end": "2026-06-30",
            "submitted_at": "2026-07-10T09:00:00+08:00",
            "submission_reference": f"VAT-ACK-{suffix}",
            "revision_number": 0,
            "currency_code": "CNY",
            "output_tax_amount": f"{output_tax:.2f}",
            "input_tax_amount": f"{input_tax:.2f}",
            "tax_payable_amount": f"{payable:.2f}",
            "lines": [
                {
                    "line_code": "L01",
                    "line_name": "测试销项税额",
                    "amount_type": "tax",
                    "current_amount": f"{output_tax:.2f}",
                }
            ],
        }

    def _payment_record(
        self,
        suffix,
        amount,
        *,
        status="succeeded",
        reference=None,
    ):
        return {
            "source_record_key": f"VAT-PAYMENT-{suffix}",
            "taxpayer_name": self.company.name,
            "taxpayer_id": self.company.partner_id.vat,
            "tax_type_code": "VAT",
            "period_start": "2026-06-01",
            "period_end": "2026-06-30",
            "payment_date": "2026-07-12",
            "payment_reference": reference or f"VAT-PAY-REF-{suffix}",
            "payment_status": status,
            "currency_code": "CNY",
            "amount": f"{amount:.2f}",
            "principal_amount": f"{amount:.2f}",
            "interest_amount": "0.00",
            "penalty_amount": "0.00",
            "payer_account_masked": "尾号 1234",
            "receipt_reference": f"VAT-PAY-ACK-{suffix}",
        }

    def _create_tax_records(self, dataset_type, suffix, records):
        contract = {
            "schema": "sdoo.cn.tax-data.v1",
            "dataset_type": dataset_type,
            "source_schema": f"controlled-test-{dataset_type}",
            "source_schema_version": "2026.1",
            "record_count": len(records),
            "records": records,
        }
        raw = json.dumps(contract, ensure_ascii=False).encode("utf-8")
        attachment = self._attachment(
            f"vat-period-{dataset_type}-{suffix}.json",
            raw,
            "application/json",
        )
        dataset = self._external_dataset(
            dataset_type,
            f"{dataset_type}-{suffix}",
            attachment,
            len(records),
            data_format="json",
        )
        run = self.env["sudo.cn.tax.data.parse.run"].with_user(
            self.reviewer
        ).with_company(self.company)._start_for_dataset(
            dataset,
            attachment,
        )
        self.assertTrue(
            run.with_user(self.reviewer)._process_json_attachment()
        )
        return (
            run.vat_filing_record_ids
            if dataset_type == "vat_filing"
            else run.tax_payment_record_ids
        )

    def _invoice(self, move_type, suffix, base_amount, posted=True):
        is_sale = move_type in ("out_invoice", "out_refund")
        line_values = {
            "name": f"测试税务单据 {suffix}",
            "quantity": 1.0,
            "price_unit": base_amount,
            "account_id": self.company_data[
                "default_account_revenue" if is_sale else "default_account_expense"
            ].id,
        }
        tax = self.tax_sale_a if is_sale else self.tax_purchase_a
        if tax:
            line_values["tax_ids"] = [Command.set(tax.ids)]
        move = self.env["account.move"].with_company(self.company).create(
            {
                "move_type": move_type,
                "journal_id": self.company_data[
                    "default_journal_sale" if is_sale else "default_journal_purchase"
                ].id,
                "partner_id": (
                    self.customer.id if is_sale else self.supplier.id
                ),
                "invoice_date": "2026-06-30",
                "date": "2026-06-30",
                "ref": f"TEST-VAT-MOVE-{suffix}",
                "invoice_line_ids": [Command.create(line_values)],
            }
        )
        if posted:
            move.action_post()
        return move

    def _ledger_tax_amounts(self, sale, purchase):
        return (
            abs(float(sale.amount_tax_signed or 0.0)),
            abs(float(purchase.amount_tax_signed or 0.0)),
        )

    def _seed_complete_sources(
        self,
        suffix,
        *,
        einvoice_output_delta=0.0,
        coverage_scope="full",
        include_payment=True,
    ):
        sale = self._invoice("out_invoice", f"sale-{suffix}", 2000.0)
        purchase = self._invoice(
            "in_invoice",
            f"purchase-{suffix}",
            500.0,
        )
        output_tax, input_tax = self._ledger_tax_amounts(sale, purchase)
        payable = max(output_tax - input_tax, 0.0)
        self._create_einvoices(
            suffix,
            [
                self._einvoice_payload(
                    f"output-{suffix}",
                    output_tax + einvoice_output_delta,
                    direction="output",
                ),
                self._einvoice_payload(
                    f"input-{suffix}",
                    input_tax,
                    direction="input",
                ),
            ],
            coverage_scope=coverage_scope,
        )
        self._create_tax_records(
            "vat_filing",
            suffix,
            [self._filing_record(suffix, output_tax, input_tax, payable)],
        )
        if include_payment:
            self._create_tax_records(
                "tax_payment",
                suffix,
                [self._payment_record(suffix, payable)],
            )
        return {
            "sale": sale,
            "purchase": purchase,
            "output_tax": output_tax,
            "input_tax": input_tax,
            "payable": payable,
        }

    def _queue(self):
        return self.env[
            "sudo.cn.vat.period.reconciliation.run"
        ].with_user(self.reviewer).with_company(self.company).enqueue(
            self.profile,
            "2026-06-01",
            "2026-06-30",
            "VAT",
        )

    def _process(self, run):
        result = run.with_user(self.reviewer).with_company(
            self.company
        )._process()
        run.invalidate_recordset()
        return result

    def test_direct_creation_of_governed_results_is_blocked(self):
        for model_name in (
            "sudo.cn.vat.period.reconciliation.run",
            "sudo.cn.vat.period.reconciliation.issue",
        ):
            with self.assertRaises(AccessError):
                self.env[model_name].create({})

    def test_duplicate_active_period_and_cancel_control(self):
        first = self._queue()
        with self.assertRaises(UserError):
            self._queue()

        first.with_user(self.reviewer).action_cancel()

        replacement = self._queue()
        self.assertEqual(replacement.state, "queued")

    def test_complete_sources_produce_aligned_non_legal_conclusion(self):
        self._seed_complete_sources("aligned")
        run = self._queue()

        self.assertTrue(self._process(run))

        self.assertEqual(run.state, "succeeded")
        self.assertEqual(run.conclusion_state, "aligned")
        self.assertEqual(run.blocking_issue_count, 0)
        self.assertEqual(run.difference_issue_count, 0)
        self.assertGreater(run.warning_issue_count, 0)
        self.assertIn(
            "ACCOUNTING_SCOPE_INVOICE_TAX_TOTALS_ONLY",
            set(run.issue_ids.mapped("code")),
        )
        self.assertTrue(run.has_ledger_einvoice_output_difference)
        self.assertTrue(run.has_filing_payment_difference)
        self.assertEqual(len(run.result_checksum), 64)
        self.assertEqual(len(run.accounting_snapshot_checksum), 64)

    def test_explainable_output_difference_is_created(self):
        self._seed_complete_sources(
            "difference",
            einvoice_output_delta=10.0,
        )
        run = self._queue()

        self.assertTrue(self._process(run))

        self.assertEqual(run.conclusion_state, "differences")
        issue = run.issue_ids.filtered(
            lambda item: item.code == "LEDGER_EINVOICE_OUTPUT_DIFFERENCE"
        )
        self.assertEqual(len(issue), 1)
        self.assertTrue(issue.has_difference)
        self.assertEqual(issue.difference_amount, -10.0)
        self.assertTrue(issue.action_hint)

    def test_missing_all_external_sources_is_insufficient_data(self):
        run = self._queue()

        self.assertTrue(self._process(run))

        self.assertEqual(run.conclusion_state, "insufficient_data")
        self.assertEqual(run.einvoice_source_state, "no_data")
        self.assertEqual(run.filing_source_state, "no_data")
        self.assertEqual(run.payment_source_state, "no_data")
        self.assertGreaterEqual(run.blocking_issue_count, 3)

    def test_partial_invoice_coverage_blocks_total_comparison(self):
        self._seed_complete_sources(
            "partial",
            coverage_scope="partial",
        )
        run = self._queue()

        self.assertTrue(self._process(run))

        self.assertEqual(run.conclusion_state, "insufficient_data")
        self.assertEqual(run.einvoice_source_state, "blocked")
        self.assertFalse(run.has_ledger_einvoice_output_difference)
        self.assertIn(
            "EINVOICE_SOURCE_COVERAGE_NOT_FULL",
            set(run.issue_ids.mapped("code")),
        )

    def test_multiple_current_filings_are_not_silently_summed(self):
        seeded = self._seed_complete_sources("filing-one")
        self._create_tax_records(
            "vat_filing",
            "filing-two",
            [
                self._filing_record(
                    "filing-two",
                    seeded["output_tax"],
                    seeded["input_tax"],
                    seeded["payable"],
                )
            ],
        )
        run = self._queue()

        self.assertTrue(self._process(run))

        self.assertEqual(run.filing_source_state, "blocked")
        self.assertIn(
            "AMBIGUOUS_CURRENT_VAT_FILING",
            set(run.issue_ids.mapped("code")),
        )

    def test_missing_payment_blocks_only_payment_comparison(self):
        self._seed_complete_sources("no-payment", include_payment=False)
        run = self._queue()

        self.assertTrue(self._process(run))

        self.assertEqual(run.payment_source_state, "no_data")
        self.assertFalse(run.has_filing_payment_difference)
        self.assertTrue(run.has_ledger_einvoice_output_difference)
        self.assertEqual(run.conclusion_state, "insufficient_data")

    def test_reversal_reduces_effective_payment_net_amount(self):
        seeded = self._seed_complete_sources(
            "payment-net-base",
            include_payment=False,
        )
        gross = seeded["payable"] + 20.0
        self._create_tax_records(
            "tax_payment",
            "payment-net",
            [
                self._payment_record("payment-net-success", gross),
                self._payment_record(
                    "payment-net-reversal",
                    20.0,
                    status="reversed",
                ),
            ],
        )
        run = self._queue()

        self.assertTrue(self._process(run))

        self.assertEqual(run.payment_amount, seeded["payable"])
        self.assertTrue(run.has_filing_payment_difference)
        self.assertEqual(run.filing_payment_difference, 0.0)

    def test_duplicate_current_payment_is_blocking(self):
        seeded = self._seed_complete_sources(
            "duplicate-payment-base",
            include_payment=False,
        )
        reference = "DUPLICATE-VAT-PAYMENT"
        self._create_tax_records(
            "tax_payment",
            "duplicate-payment",
            [
                self._payment_record(
                    "duplicate-payment-1",
                    seeded["payable"],
                    reference=reference,
                ),
                self._payment_record(
                    "duplicate-payment-2",
                    seeded["payable"],
                    reference=reference,
                ),
            ],
        )
        run = self._queue()

        self.assertTrue(self._process(run))

        self.assertEqual(run.payment_source_state, "blocked")
        self.assertIn(
            "DUPLICATE_CURRENT_VAT_PAYMENT",
            set(run.issue_ids.mapped("code")),
        )

    def test_draft_accounting_invoice_is_visible_but_excluded(self):
        self._seed_complete_sources("draft-accounting")
        self._invoice(
            "out_invoice",
            "draft-accounting-extra",
            100.0,
            posted=False,
        )
        run = self._queue()

        self.assertTrue(self._process(run))

        self.assertEqual(run.draft_accounting_move_count, 1)
        self.assertIn(
            "DRAFT_ACCOUNTING_INVOICES_EXCLUDED",
            set(run.issue_ids.mapped("code")),
        )
        self.assertNotEqual(run.conclusion_state, "insufficient_data")

    def test_failed_retry_does_not_supersede_previous_success(self):
        self._seed_complete_sources("failed-retry")
        first = self._queue()
        self.assertTrue(self._process(first))
        failed = self._queue()

        with patch.object(
            type(failed),
            "_build_results",
            side_effect=UserError("controlled failure"),
        ):
            self.assertFalse(self._process(failed))

        first.invalidate_recordset()
        self.assertEqual(first.state, "succeeded")
        self.assertEqual(failed.state, "failed")

    def test_successful_retry_supersedes_previous_result(self):
        self._seed_complete_sources(
            "successful-retry",
            einvoice_output_delta=10.0,
        )
        first = self._queue()
        self.assertTrue(self._process(first))
        second = self._queue()

        self.assertTrue(self._process(second))

        first.invalidate_recordset()
        self.assertEqual(first.state, "superseded")
        self.assertEqual(second.state, "succeeded")
        self.assertFalse(first.issue_ids.is_current_result)
        self.assertTrue(second.issue_ids.is_current_result)

    def test_run_and_issues_are_immutable(self):
        run = self._queue()
        self.assertTrue(self._process(run))

        with self.assertRaises(AccessError):
            run.write({"result_summary": "changed"})
        with self.assertRaises(AccessError):
            run.unlink()
        with self.assertRaises(AccessError):
            run.issue_ids.write({"description": "changed"})

    def test_native_queue_processes_one_run(self):
        run = self._queue()

        processed = self.env[
            "sudo.cn.vat.period.reconciliation.run"
        ]._cron_process_runs(limit=1)

        run.invalidate_recordset()
        self.assertEqual(processed, 1)
        self.assertEqual(run.state, "succeeded")

    def test_read_only_access_is_company_isolated(self):
        own_run = self._queue()
        visible = self.env[
            "sudo.cn.vat.period.reconciliation.run"
        ].with_user(self.read_only_user).search([("id", "=", own_run.id)])
        self.assertEqual(visible, own_run)
        with self.assertRaises(AccessError):
            visible.read(["accounting_move_ids"])
        with self.assertRaises(AccessError):
            self.env[
                "sudo.cn.vat.period.reconciliation.run"
            ].with_user(self.read_only_user).enqueue(
                self.profile,
                "2026-07-01",
                "2026-07-31",
            )

        other_company = self.env["res.company"].create(
            {
                "name": "Other China VAT Period Company",
                "country_id": self.country.id,
                "account_fiscal_country_id": self.country.id,
                "currency_id": self.currency.id,
            }
        )
        other_profile = self.env["sudo.compliance.profile"].with_company(
            other_company
        ).create(
            {
                "company_id": other_company.id,
                "country_id": self.country.id,
                "country_pack_id": self.country_pack.id,
            }
        )
        other_manager = self.env["res.users"].create(
            {
                "name": "Other China VAT Period Manager",
                "login": "other_cn_vat_period_manager",
                "company_id": other_company.id,
                "company_ids": [Command.set(other_company.ids)],
                "group_ids": [
                    Command.set(
                        self.env.ref(
                            "sudo_global_finance.group_compliance_manager"
                        ).ids
                    )
                ],
            }
        )
        other_run = self.env[
            "sudo.cn.vat.period.reconciliation.run"
        ].with_user(other_manager).with_company(other_company).enqueue(
            other_profile,
            "2026-06-01",
            "2026-06-30",
        )

        hidden = self.env[
            "sudo.cn.vat.period.reconciliation.run"
        ].with_user(self.read_only_user).search([("id", "=", other_run.id)])
        self.assertFalse(hidden)
