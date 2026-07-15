import json

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestChinaTaxDataNormalization(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.country = cls.env.ref("base.cn")
        cls.currency = cls.env.ref("base.CNY")
        cls.company = cls.env["res.company"].create(
            {
                "name": "China Tax Data Test Company",
                "currency_id": cls.currency.id,
                "country_id": cls.country.id,
                "account_fiscal_country_id": cls.country.id,
            }
        )
        cls.company.partner_id.vat = "91440101MA5D123451"
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
        user_group = cls.env.ref("sudo_global_finance.group_compliance_user")
        cls.reviewer = cls.env["res.users"].create(
            {
                "name": "China Tax Data Reviewer",
                "login": "cn_tax_data_reviewer",
                "company_id": cls.company.id,
                "company_ids": [Command.set(cls.company.ids)],
                "group_ids": [Command.set(manager_group.ids)],
            }
        )
        cls.read_only_user = cls.env["res.users"].create(
            {
                "name": "China Tax Data Reader",
                "login": "cn_tax_data_reader",
                "company_id": cls.company.id,
                "company_ids": [Command.set(cls.company.ids)],
                "group_ids": [Command.set(user_group.ids)],
            }
        )

    def _filing_record(self, suffix="1", **overrides):
        record = {
            "source_record_key": f"VAT-2026-06-{suffix}",
            "taxpayer_name": self.company.name,
            "taxpayer_id": self.company.partner_id.vat,
            "jurisdiction_code": "440100",
            "jurisdiction_name": "测试主管税务机关",
            "return_type_code": "VAT-GENERAL",
            "return_status": "accepted",
            "period_start": "2026-06-01",
            "period_end": "2026-06-30",
            "submitted_at": "2026-07-10T09:00:00+08:00",
            "submission_reference": f"VAT-ACK-{suffix}",
            "revision_number": 0,
            "currency_code": "CNY",
            "taxable_sales_amount": "10000.00",
            "output_tax_amount": "1300.00",
            "input_tax_amount": "1300.00",
            "input_tax_transfer_out_amount": "0.00",
            "prior_credit_amount": "0.00",
            "tax_payable_amount": "0.00",
            "tax_refund_amount": "0.00",
            "closing_credit_amount": "0.00",
            "lines": [
                {
                    "line_code": "L01",
                    "line_name": "测试应税销售额",
                    "amount_type": "taxable_base",
                    "current_amount": "10000.00",
                    "ytd_amount": "60000.00",
                    "tax_rate": "0.13",
                },
                {
                    "line_code": "L32",
                    "line_name": "本期应补退税额",
                    "amount_type": "payable",
                    "current_amount": "0.00",
                },
            ],
        }
        record.update(overrides)
        return record

    def _payment_record(self, suffix="1", **overrides):
        record = {
            "source_record_key": f"PAY-2026-06-{suffix}",
            "taxpayer_name": self.company.name,
            "taxpayer_id": self.company.partner_id.vat,
            "tax_type_code": "VAT",
            "tax_item_code": "VAT-GENERAL",
            "period_start": "2026-06-01",
            "period_end": "2026-06-30",
            "payment_date": "2026-07-12",
            "payment_reference": f"PAY-REF-{suffix}",
            "payment_status": "succeeded",
            "currency_code": "CNY",
            "amount": "100.00",
            "principal_amount": "100.00",
            "interest_amount": "0.00",
            "penalty_amount": "0.00",
            "authority": "测试主管税务机关",
            "payment_channel": "受控测试渠道",
            "payer_account_masked": "尾号 1234",
            "receipt_reference": f"PAY-ACK-{suffix}",
        }
        record.update(overrides)
        return record

    def _contract(self, dataset_type, records):
        return {
            "schema": "sdoo.cn.tax-data.v1",
            "dataset_type": dataset_type,
            "source_schema": f"controlled-test-{dataset_type}",
            "source_schema_version": "2026.1",
            "record_count": len(records),
            "records": records,
        }

    def _dataset(
        self,
        dataset_type,
        records,
        *,
        suffix="1",
        declared_record_count=None,
        data_format="json",
        profile=None,
        company=None,
        reviewer=None,
        seal=True,
    ):
        profile = profile or self.profile
        company = company or profile.company_id
        reviewer = reviewer or self.reviewer
        raw = json.dumps(
            self._contract(dataset_type, records),
            ensure_ascii=False,
        ).encode("utf-8")
        attachment = self.env["ir.attachment"].create(
            {
                "name": f"cn-tax-data-{dataset_type}-{suffix}.json",
                "raw": raw,
                "mimetype": "application/json",
            }
        )
        dataset = self.env["sudo.cn.external.dataset"].with_company(
            company
        ).create(
            {
                "profile_id": profile.id,
                "dataset_type": dataset_type,
                "period_start": "2026-06-01",
                "period_end": "2026-06-30",
                "coverage_scope": "full",
                "scope_note": "覆盖测试税款所属期的受控标准化数据。",
                "source_channel": "official_export",
                "source_system_name": "测试电子税务数据源",
                "source_reference": f"CN-TAX-DATA-{suffix}",
                "source_generated_at": "2026-07-01 09:00:00",
                "data_format": data_format,
                "authorization_basis": "测试公司自有账户受控导出。",
                "acquired_at": "2026-07-01 10:00:00",
                "declared_record_count": (
                    len(records)
                    if declared_record_count is None
                    else declared_record_count
                ),
                "currency_id": self.currency.id,
                "source_attachment_ids": [Command.set(attachment.ids)],
                "authenticity_state": "not_checked",
            }
        )
        if seal:
            dataset.with_user(reviewer).with_company(company).action_seal()
        return dataset

    def _start(self, dataset, reviewer=None):
        reviewer = reviewer or self.reviewer
        return self.env["sudo.cn.tax.data.parse.run"].with_user(
            reviewer
        ).with_company(dataset.company_id)._start_for_dataset(
            dataset,
            dataset.source_attachment_ids[:1],
        )

    def _process(self, run, reviewer=None):
        reviewer = reviewer or self.reviewer
        result = run.with_user(reviewer).with_company(
            run.company_id
        )._process_json_attachment()
        run.invalidate_recordset()
        return result

    def test_direct_creation_of_governed_results_is_blocked(self):
        for model_name in (
            "sudo.cn.tax.data.parse.run",
            "sudo.cn.vat.filing.record",
            "sudo.cn.vat.filing.line",
            "sudo.cn.tax.payment.record",
        ):
            with self.assertRaises(AccessError):
                self.env[model_name].create({})

    def test_unsealed_or_non_json_dataset_cannot_start(self):
        draft = self._dataset(
            "vat_filing",
            [self._filing_record("draft")],
            suffix="draft",
            seal=False,
        )
        with self.assertRaises(UserError):
            self._start(draft)

        non_json = self._dataset(
            "vat_filing",
            [self._filing_record("format")],
            suffix="format",
            data_format="csv",
        )
        with self.assertRaises(UserError):
            self._start(non_json)

    def test_valid_vat_filing_preserves_zero_and_flexible_lines(self):
        dataset = self._dataset(
            "vat_filing",
            [self._filing_record("valid")],
            suffix="filing-valid",
        )
        run = self._start(dataset)

        self.assertTrue(self._process(run))

        record = run.vat_filing_record_ids
        self.assertEqual(run.state, "succeeded")
        self.assertEqual(run.valid_record_count, 1)
        self.assertEqual(record.quality_state, "valid")
        self.assertEqual(
            fields.Datetime.to_string(record.submitted_at),
            "2026-07-10 01:00:00",
        )
        self.assertTrue(record.has_tax_payable_amount)
        self.assertEqual(record.tax_payable_amount, 0.0)
        zero_line = record.line_ids.filtered(
            lambda line: line.line_code == "L32"
        )
        self.assertTrue(zero_line.has_current_amount)
        self.assertEqual(zero_line.current_amount, 0.0)
        self.assertEqual(len(record.record_checksum), 64)
        self.assertEqual(len(run.output_checksum), 64)

    def test_taxpayer_mismatch_is_visible_data_error(self):
        dataset = self._dataset(
            "vat_filing",
            [
                self._filing_record(
                    "entity-mismatch",
                    taxpayer_id="91310000MA1BAD9995",
                )
            ],
            suffix="entity-mismatch",
        )
        run = self._start(dataset)

        self.assertTrue(self._process(run))

        record = run.vat_filing_record_ids
        self.assertEqual(record.quality_state, "error")
        self.assertIn(
            "TAXPAYER_ENTITY_MISMATCH",
            {issue["code"] for issue in record.issue_json},
        )

    def test_out_of_scope_period_and_missing_payable_are_errors(self):
        record = self._filing_record(
            "scope-error",
            period_start="2026-05-01",
            period_end="2026-05-31",
        )
        record.pop("tax_payable_amount")
        dataset = self._dataset(
            "vat_filing",
            [record],
            suffix="scope-error",
        )
        run = self._start(dataset)

        self.assertTrue(self._process(run))

        codes = {issue["code"] for issue in run.vat_filing_record_ids.issue_json}
        self.assertIn("TAX_PERIOD_OUTSIDE_DATASET", codes)
        self.assertIn("MISSING_TAX_PAYABLE_AMOUNT", codes)

    def test_valid_tax_payment_retains_only_masked_account(self):
        dataset = self._dataset(
            "tax_payment",
            [self._payment_record("valid")],
            suffix="payment-valid",
        )
        run = self._start(dataset)

        self.assertTrue(self._process(run))

        record = run.tax_payment_record_ids
        self.assertEqual(record.quality_state, "valid")
        self.assertEqual(record.payer_account_masked, "****1234")
        self.assertEqual(record.amount, 100.0)
        self.assertEqual(record.principal_amount, 100.0)

    def test_unmasked_account_is_not_persisted(self):
        dataset = self._dataset(
            "tax_payment",
            [
                self._payment_record(
                    "unmasked",
                    payer_account_masked="6222021234567890",
                )
            ],
            suffix="payment-unmasked",
        )
        run = self._start(dataset)

        self.assertTrue(self._process(run))

        record = run.tax_payment_record_ids
        self.assertEqual(record.quality_state, "error")
        self.assertFalse(record.payer_account_masked)
        self.assertIn(
            "UNMASKED_PAYER_ACCOUNT",
            {issue["code"] for issue in record.issue_json},
        )

    def test_unbounded_amount_becomes_visible_error(self):
        dataset = self._dataset(
            "tax_payment",
            [self._payment_record("unbounded", amount="1e10000")],
            suffix="payment-unbounded",
        )
        run = self._start(dataset)

        self.assertTrue(self._process(run))

        record = run.tax_payment_record_ids
        self.assertEqual(record.quality_state, "error")
        self.assertFalse(record.has_amount)
        self.assertIn(
            "INVALID_AMOUNT",
            {issue["code"] for issue in record.issue_json},
        )

    def test_declared_record_count_mismatch_fails_without_records(self):
        dataset = self._dataset(
            "vat_filing",
            [self._filing_record("count")],
            suffix="count-mismatch",
            declared_record_count=2,
        )
        run = self._start(dataset)

        self.assertFalse(self._process(run))

        self.assertEqual(run.state, "failed")
        self.assertEqual(run.error_code, "DECLARED_RECORD_COUNT_MISMATCH")
        self.assertFalse(run.vat_filing_record_ids)

    def test_failed_retry_does_not_supersede_previous_success(self):
        dataset = self._dataset(
            "vat_filing",
            [self._filing_record("retry")],
            suffix="failed-retry",
        )
        first = self._start(dataset)
        self.assertTrue(self._process(first))
        failed = self._start(dataset)

        failed.with_user(self.reviewer)._record_failure(
            "CONTROLLED_TEST_FAILURE",
            "受控测试失败。",
        )

        first.invalidate_recordset()
        self.assertEqual(first.state, "succeeded")
        self.assertEqual(failed.state, "failed")
        self.assertTrue(first.vat_filing_record_ids.is_current_result)

    def test_successful_retry_supersedes_previous_result(self):
        dataset = self._dataset(
            "tax_payment",
            [self._payment_record("supersede")],
            suffix="successful-retry",
        )
        first = self._start(dataset)
        self.assertTrue(self._process(first))
        second = self._start(dataset)

        self.assertTrue(self._process(second))

        first.invalidate_recordset()
        self.assertEqual(first.state, "superseded")
        self.assertEqual(second.state, "succeeded")
        self.assertFalse(first.tax_payment_record_ids.is_current_result)
        self.assertTrue(second.tax_payment_record_ids.is_current_result)

    def test_normalized_records_are_immutable(self):
        dataset = self._dataset(
            "vat_filing",
            [self._filing_record("immutable")],
            suffix="immutable",
        )
        run = self._start(dataset)
        self.assertTrue(self._process(run))
        record = run.vat_filing_record_ids

        with self.assertRaises(AccessError):
            record.write({"submission_reference": "CHANGED"})
        with self.assertRaises(AccessError):
            record.unlink()
        with self.assertRaises(AccessError):
            record.line_ids.write({"line_name": "CHANGED"})

    def test_read_only_access_is_company_isolated(self):
        own_dataset = self._dataset(
            "vat_filing",
            [self._filing_record("own")],
            suffix="own-company",
        )
        own_run = self._start(own_dataset)
        self.assertTrue(self._process(own_run))
        visible = self.env["sudo.cn.vat.filing.record"].with_user(
            self.read_only_user
        ).search([("id", "=", own_run.vat_filing_record_ids.id)])
        self.assertTrue(visible)
        with self.assertRaises(AccessError):
            self.env["sudo.cn.tax.data.parse.run"].with_user(
                self.read_only_user
            )._start_for_dataset(
                own_dataset,
                own_dataset.source_attachment_ids[:1],
            )

        other_company = self.env["res.company"].create(
            {
                "name": "Other China Tax Data Company",
                "currency_id": self.currency.id,
                "country_id": self.country.id,
                "account_fiscal_country_id": self.country.id,
            }
        )
        other_company.partner_id.vat = "91310000MA5E67890G"
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
        other_manager = self.env["res.users"].create(
            {
                "name": "Other China Tax Data Manager",
                "login": "other_cn_tax_data_manager",
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
        other_record = self._filing_record(
            "other",
            taxpayer_name=other_company.name,
            taxpayer_id=other_company.partner_id.vat,
        )
        other_dataset = self._dataset(
            "vat_filing",
            [other_record],
            suffix="other-company",
            profile=other_profile,
            company=other_company,
            reviewer=other_manager,
        )
        other_run = self._start(other_dataset, reviewer=other_manager)
        self.assertTrue(self._process(other_run, reviewer=other_manager))

        hidden = self.env["sudo.cn.vat.filing.record"].with_user(
            self.read_only_user
        ).search([("id", "=", other_run.vat_filing_record_ids.id)])
        self.assertFalse(hidden)
