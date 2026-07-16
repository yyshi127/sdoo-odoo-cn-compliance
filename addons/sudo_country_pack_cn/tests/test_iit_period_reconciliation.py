import json

from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestChinaIitPeriodReconciliation(AccountTestInvoicingCommon):
    chart_template = "cn"
    country_code = "CN"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(su=True)
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
        manager_group = cls.env.ref(
            "sudo_global_finance.group_compliance_manager"
        )
        user_group = cls.env.ref("sudo_global_finance.group_compliance_user")
        cls.scope_author = cls.env["res.users"].create(
            {
                "name": "China IIT Scope Author",
                "login": "cn_iit_scope_author",
                "company_id": cls.company.id,
                "company_ids": [Command.set(cls.company.ids)],
                "group_ids": [Command.set(manager_group.ids)],
            }
        )
        cls.reviewer = cls.env["res.users"].create(
            {
                "name": "China IIT Reconciliation Reviewer",
                "login": "cn_iit_reconciliation_reviewer",
                "company_id": cls.company.id,
                "company_ids": [Command.set(cls.company.ids)],
                "group_ids": [Command.set(manager_group.ids)],
            }
        )
        cls.reader = cls.env["res.users"].create(
            {
                "name": "China IIT Reconciliation Reader",
                "login": "cn_iit_reconciliation_reader",
                "company_id": cls.company.id,
                "company_ids": [Command.set(cls.company.ids)],
                "group_ids": [Command.set(user_group.ids)],
            }
        )
        cls.balance_account = cls.env["account.account"].with_company(
            cls.company
        ).create(
            {
                "name": "IIT reconciliation balancing account",
                "code": "19999997",
                "account_type": "asset_current",
                "company_ids": [Command.set(cls.company.ids)],
            }
        )
        cls.employee_payable_account = cls.env["account.account"].with_company(
            cls.company
        ).create(
            {
                "name": "Controlled employee compensation payable",
                "code": "22119901",
                "account_type": "liability_current",
                "company_ids": [Command.set(cls.company.ids)],
            }
        )
        cls.iit_payable_account = cls.env["account.account"].with_company(
            cls.company
        ).create(
            {
                "name": "Controlled individual income tax payable",
                "code": "22219901",
                "account_type": "liability_current",
                "company_ids": [Command.set(cls.company.ids)],
            }
        )

    def _attachment(self, name, raw, mimetype="application/pdf"):
        return self.env["ir.attachment"].with_user(self.scope_author).create(
            {"name": name, "raw": raw, "mimetype": mimetype}
        )

    def _verified_scope(self, suffix="default", **overrides):
        values = {
            "profile_id": self.profile.id,
            "valid_from": "2026-01-01",
            "valid_to": "2026-12-31",
            "source_reference": f"TEST/IIT/SCOPE/{suffix}",
            "payroll_source_schema": "controlled-test-payroll_summary",
            "payroll_source_schema_version": "2026.1",
            "iit_source_schema": "controlled-test-iit_withholding",
            "iit_source_schema_version": "2026.1",
            "payable_refundable_sign_convention": (
                "positive_payable_negative_refundable"
            ),
            "scope_note": (
                "测试口径分别配置工资薪酬成本、应付职工薪酬和应交个人所得税；"
                "工资在所属期计提，税款在受控缴款记录日期结算，不包含其他人员费用。"
            ),
            "line_ids": [
                Command.create(
                    {
                        "account_id": self.company_data[
                            "default_account_expense"
                        ].id,
                        "role": "payroll_expense",
                    }
                ),
                Command.create(
                    {
                        "account_id": self.employee_payable_account.id,
                        "role": "employee_payable",
                    }
                ),
                Command.create(
                    {
                        "account_id": self.iit_payable_account.id,
                        "role": "iit_payable",
                    }
                ),
            ],
        }
        values.update(overrides)
        scope = self.env["sudo.cn.iit.accounting.scope"].with_user(
            self.scope_author
        ).with_company(self.company).create(values)
        evidence = self._attachment(
            f"iit-accounting-scope-{suffix}.pdf",
            f"controlled IIT accounting scope {suffix}".encode(),
        )
        evidence.sudo().write({"res_model": scope._name, "res_id": scope.id})
        scope.with_user(self.scope_author).write(
            {"evidence_attachment_ids": [Command.set(evidence.ids)]}
        )
        scope.with_user(self.reviewer).action_verify()
        return scope

    def _external_dataset(self, dataset_type, suffix, attachment, record_count):
        dataset = self.env["sudo.cn.external.dataset"].with_user(
            self.scope_author
        ).with_company(self.company).create(
            {
                "profile_id": self.profile.id,
                "dataset_type": dataset_type,
                "period_start": "2026-06-01",
                "period_end": "2026-06-30",
                "coverage_scope": "full",
                "scope_note": "测试期间完整受控来源。",
                "source_channel": "official_export",
                "source_system_name": "测试工资或电子税务数据源",
                "source_reference": f"TEST-IIT-{dataset_type}-{suffix}",
                "source_generated_at": "2026-07-10 09:00:00",
                "data_format": "json",
                "authorization_basis": "测试公司自有账户受控导出。",
                "acquired_at": "2026-07-10 10:00:00",
                "contains_sensitive_data": dataset_type in (
                    "payroll_summary",
                    "iit_withholding",
                ),
                "data_control_note": (
                    "仅授权合规管理员访问；标准化工资汇总不含姓名证件。"
                    if dataset_type in ("payroll_summary", "iit_withholding")
                    else False
                ),
                "declared_record_count": record_count,
                "currency_id": self.currency.id,
                "source_attachment_ids": [Command.set(attachment.ids)],
                "authenticity_state": "not_applicable",
            }
        )
        attachment.sudo().write({"res_model": dataset._name, "res_id": dataset.id})
        dataset.with_user(self.reviewer).with_company(self.company).action_seal()
        return dataset

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
            f"iit-period-{dataset_type}-{suffix}.json",
            raw,
            "application/json",
        )
        dataset = self._external_dataset(
            dataset_type, suffix, attachment, len(records)
        )
        run = self.env["sudo.cn.tax.data.parse.run"].with_user(
            self.reviewer
        ).with_company(self.company)._start_for_dataset(dataset, attachment)
        self.assertTrue(run.with_user(self.reviewer)._process_json_attachment())
        return run

    def _payroll_summary(
        self, suffix, *, gross=10000.0, withheld=90.0, persons=1, **overrides
    ):
        record = {
            "source_record_key": f"PAYROLL-2026-06-{suffix}",
            "taxpayer_name": self.company.name,
            "taxpayer_id": self.company.partner_id.vat,
            "period_start": "2026-06-01",
            "period_end": "2026-06-30",
            "currency_code": "CNY",
            "payroll_frequency": "monthly",
            "payroll_status": "confirmed",
            "payroll_run_reference": f"PAYROLL-RUN-{suffix}",
            "approved_at": "2026-06-30T18:00:00+08:00",
            "declared_person_count": persons,
            "gross_income_amount": f"{gross:.2f}",
            "tax_exempt_income_amount": "0.00",
            "employee_social_insurance_amount": "0.00",
            "employee_housing_fund_amount": "0.00",
            "other_pre_tax_deduction_amount": "0.00",
            "net_pay_amount": f"{gross - withheld:.2f}",
            "withheld_iit_amount": f"{withheld:.2f}",
        }
        record.update(overrides)
        return record

    def _iit_filing(
        self,
        suffix,
        *,
        income=10000.0,
        tax=90.0,
        settlement=90.0,
        persons=1,
        **overrides,
    ):
        record = {
            "source_record_key": f"IIT-2026-06-{suffix}",
            "taxpayer_name": self.company.name,
            "taxpayer_id": self.company.partner_id.vat,
            "jurisdiction_code": "440100",
            "jurisdiction_name": "测试主管税务机关",
            "tax_year": 2026,
            "filing_frequency": "monthly",
            "return_type_code": "IIT-WITHHOLDING",
            "return_status": "accepted",
            "period_start": "2026-06-01",
            "period_end": "2026-06-30",
            "submitted_at": "2026-07-10T09:00:00+08:00",
            "submission_reference": f"IIT-ACK-{suffix}",
            "revision_number": 0,
            "currency_code": "CNY",
            "declared_person_count": persons,
            "declared_line_count": 1,
            "total_income_amount": f"{income:.2f}",
            "total_tax_exempt_income_amount": "0.00",
            "total_basic_deduction_amount": "5000.00",
            "total_special_deduction_amount": "1000.00",
            "total_special_additional_deduction_amount": "1000.00",
            "total_other_deduction_amount": "0.00",
            "total_donation_deduction_amount": "0.00",
            "total_taxable_income_amount": "3000.00",
            "total_tax_calculated_amount": f"{tax:.2f}",
            "total_tax_relief_amount": "0.00",
            "total_tax_paid_amount": "0.00",
            "total_payable_refundable_amount": f"{settlement:.2f}",
            "lines": [
                {
                    "source_line_key": "opaque:" + "b" * 32,
                    "subject_key": "hmac-sha256:" + "a" * 64,
                    "residency_status": "resident",
                    "income_type_code": "wages_salary",
                    "current_income_amount": f"{income:.2f}",
                    "current_tax_exempt_income_amount": "0.00",
                    "current_basic_deduction_amount": "5000.00",
                    "current_special_deduction_amount": "1000.00",
                    "current_other_deduction_amount": "0.00",
                    "taxable_income_amount": "3000.00",
                    "tax_calculated_amount": f"{tax:.2f}",
                    "tax_relief_amount": "0.00",
                    "tax_paid_amount": "0.00",
                    "payable_refundable_amount": f"{settlement:.2f}",
                }
            ],
        }
        record.update(overrides)
        return record

    def _payment(self, suffix, *, amount=90.0, status="succeeded", **overrides):
        record = {
            "source_record_key": f"IIT-PAYMENT-{suffix}",
            "taxpayer_name": self.company.name,
            "taxpayer_id": self.company.partner_id.vat,
            "tax_type_code": "IIT",
            "period_start": "2026-06-01",
            "period_end": "2026-06-30",
            "payment_date": "2026-07-15",
            "payment_reference": f"IIT-PAY-REF-{suffix}",
            "payment_status": status,
            "currency_code": "CNY",
            "amount": f"{amount:.2f}",
            "principal_amount": f"{amount:.2f}",
            "interest_amount": "0.00",
            "penalty_amount": "0.00",
            "receipt_reference": f"IIT-PAY-ACK-{suffix}",
        }
        record.update(overrides)
        return record

    def _ledger(self, *, gross=10000.0, withheld=90.0, payment=90.0):
        expense = self.company_data["default_account_expense"]
        journal = self.company_data["default_journal_misc"]
        accrual = self.env["account.move"].with_company(self.company).create(
            {
                "move_type": "entry",
                "journal_id": journal.id,
                "date": "2026-06-30",
                "ref": "TEST-IIT-PAYROLL-ACCRUAL",
                "line_ids": [
                    Command.create(
                        {
                            "name": "Payroll expense",
                            "account_id": expense.id,
                            "debit": gross,
                        }
                    ),
                    Command.create(
                        {
                            "name": "Employee compensation payable",
                            "account_id": self.employee_payable_account.id,
                            "credit": gross,
                        }
                    ),
                ],
            }
        )
        accrual.action_post()
        withholding = self.env["account.move"].with_company(self.company).create(
            {
                "move_type": "entry",
                "journal_id": journal.id,
                "date": "2026-06-30",
                "ref": "TEST-IIT-WITHHOLDING-ACCRUAL",
                "line_ids": [
                    Command.create(
                        {
                            "name": "Employee payable deduction",
                            "account_id": self.employee_payable_account.id,
                            "debit": withheld,
                        }
                    ),
                    Command.create(
                        {
                            "name": "IIT payable accrual",
                            "account_id": self.iit_payable_account.id,
                            "credit": withheld,
                        }
                    ),
                ],
            }
        )
        withholding.action_post()
        settlement = self.env["account.move"].with_company(self.company).create(
            {
                "move_type": "entry",
                "journal_id": journal.id,
                "date": "2026-07-15",
                "ref": "TEST-IIT-PAYMENT-SETTLEMENT",
                "line_ids": [
                    Command.create(
                        {
                            "name": "IIT payable settlement",
                            "account_id": self.iit_payable_account.id,
                            "debit": payment,
                        }
                    ),
                    Command.create(
                        {
                            "name": "Bank payment counterparty",
                            "account_id": self.balance_account.id,
                            "credit": payment,
                        }
                    ),
                ],
            }
        )
        settlement.action_post()
        return accrual | withholding | settlement

    def _seed_complete_sources(
        self,
        suffix,
        *,
        payroll=None,
        filing=None,
        payment=None,
        ledger=True,
        scope=True,
    ):
        if ledger:
            self._ledger()
        scope_record = self._verified_scope(suffix) if scope else False
        payroll_run = self._create_tax_records(
            "payroll_summary",
            suffix,
            [payroll or self._payroll_summary(suffix)],
        )
        filing_run = self._create_tax_records(
            "iit_withholding",
            suffix,
            [filing or self._iit_filing(suffix)],
        )
        payment_run = self._create_tax_records(
            "tax_payment",
            suffix,
            [payment or self._payment(suffix)],
        )
        return {
            "scope": scope_record,
            "payroll_run": payroll_run,
            "filing_run": filing_run,
            "payment_run": payment_run,
        }

    def _queue(self):
        return self.env["sudo.cn.iit.period.reconciliation.run"].with_user(
            self.reviewer
        ).with_company(self.company).enqueue(
            self.profile,
            "2026-06-01",
            "2026-06-30",
            "IIT",
        )

    def test_aligned_run_uses_payment_date_outside_tax_period(self):
        sources = self._seed_complete_sources("aligned")
        run = self._queue()

        self.assertTrue(run.with_user(self.reviewer)._process())
        run.invalidate_recordset()

        self.assertEqual(run.state, "succeeded")
        self.assertEqual(run.conclusion_state, "aligned")
        self.assertEqual(run.blocking_issue_count, 0)
        self.assertEqual(run.difference_issue_count, 0)
        self.assertEqual(run.ledger_payroll_expense_amount, 10000.0)
        self.assertEqual(run.ledger_employee_payable_accrual_amount, 10000.0)
        self.assertEqual(run.ledger_iit_accrual_amount, 90.0)
        self.assertEqual(run.ledger_iit_settlement_amount, 90.0)
        self.assertEqual(run.effective_paid_principal_amount, 90.0)
        self.assertEqual(run.payroll_summary_id, sources["payroll_run"].payroll_summary_record_ids)
        self.assertEqual(run.withholding_record_id, sources["filing_run"].iit_withholding_record_ids)
        self.assertEqual(run.result_integrity_state, "verified")

    def test_missing_sources_is_insufficient_not_aligned(self):
        run = self._queue()

        self.assertTrue(run.with_user(self.reviewer)._process())
        run.invalidate_recordset()

        self.assertEqual(run.conclusion_state, "insufficient_data")
        self.assertGreaterEqual(run.blocking_issue_count, 4)
        codes = set(run.issue_ids.mapped("code"))
        self.assertIn("NO_VERIFIED_IIT_ACCOUNTING_SCOPE", codes)
        self.assertIn("NO_CURRENT_PAYROLL_SUMMARY", codes)
        self.assertIn("NO_CURRENT_IIT_WITHHOLDING_RETURN", codes)
        self.assertIn("NO_CURRENT_IIT_PAYMENT_DATA", codes)

    def test_amount_differences_are_visible_review_items(self):
        self._seed_complete_sources(
            "differences",
            payroll=self._payroll_summary("differences", gross=11000.0, withheld=100.0),
            filing=self._iit_filing("differences", income=12000.0, tax=110.0, settlement=110.0),
            payment=self._payment("differences", amount=80.0),
        )
        run = self._queue()

        self.assertTrue(run.with_user(self.reviewer)._process())
        run.invalidate_recordset()

        self.assertEqual(run.conclusion_state, "differences")
        self.assertEqual(run.blocking_issue_count, 0)
        self.assertGreaterEqual(run.difference_issue_count, 5)
        self.assertTrue(run.has_filing_payroll_income_difference)
        self.assertEqual(run.filing_payroll_income_difference, 1000.0)
        self.assertTrue(run.has_payable_payment_difference)
        self.assertEqual(run.payable_payment_difference, 30.0)

    def test_person_count_difference_is_not_rendered_as_money(self):
        self._seed_complete_sources(
            "persons",
            payroll=self._payroll_summary("persons", persons=2),
            filing=self._iit_filing("persons", persons=1),
        )
        run = self._queue()
        self.assertTrue(run.with_user(self.reviewer)._process())

        issue = run.issue_ids.filtered(
            lambda item: item.code == "IIT_PAYROLL_FILING_PERSON_COUNT_DIFFERENCE"
        )
        self.assertTrue(issue.has_count_comparison)
        self.assertFalse(issue.has_difference)
        self.assertEqual(issue.left_count, 2)
        self.assertEqual(issue.right_count, 1)
        self.assertEqual(issue.count_difference, 1)

    def test_source_schema_mismatch_blocks_comparison(self):
        self._ledger()
        self._verified_scope(
            "schema-mismatch",
            payroll_source_schema_version="different-version",
        )
        self._create_tax_records(
            "payroll_summary",
            "schema-mismatch",
            [self._payroll_summary("schema-mismatch")],
        )
        self._create_tax_records(
            "iit_withholding",
            "schema-mismatch",
            [self._iit_filing("schema-mismatch")],
        )
        self._create_tax_records(
            "tax_payment",
            "schema-mismatch",
            [self._payment("schema-mismatch")],
        )
        run = self._queue()

        self.assertTrue(run.with_user(self.reviewer)._process())
        self.assertEqual(run.conclusion_state, "insufficient_data")
        self.assertIn(
            "PAYROLL_SOURCE_SCHEMA_MISMATCH", set(run.issue_ids.mapped("code"))
        )
        self.assertFalse(run.has_ledger_payroll_difference)

    def test_verified_scope_and_results_are_immutable(self):
        sources = self._seed_complete_sources("immutable")
        scope = sources["scope"]
        run = self._queue()
        self.assertTrue(run.with_user(self.reviewer)._process())

        with self.assertRaises(AccessError):
            scope.with_user(self.scope_author).write({"scope_note": "changed"})
        with self.assertRaises(AccessError):
            run.with_user(self.reviewer).write({"result_summary": "changed"})
        with self.assertRaises(AccessError):
            run.issue_ids.with_user(self.reviewer).write({"description": "changed"})
        with self.assertRaises(UserError):
            scope.with_user(self.reviewer).action_reset_to_draft()
        with self.assertRaises(AccessError):
            run.unlink()

    def test_sensitive_sources_are_manager_only_but_run_is_readable(self):
        sources = self._seed_complete_sources("access")
        run = self._queue()
        self.assertTrue(run.with_user(self.reviewer)._process())

        with self.assertRaises(AccessError):
            sources["payroll_run"].payroll_summary_record_ids.with_user(
                self.reader
            ).read(["gross_income_amount"])
        with self.assertRaises(AccessError):
            sources["filing_run"].iit_withholding_record_ids.with_user(
                self.reader
            ).read(["total_income_amount"])
        with self.assertRaises(AccessError):
            run.with_user(self.reader).read(["payroll_summary_id"])
        with self.assertRaises(AccessError):
            run.with_user(self.reader).read(["withholding_record_id"])
        with self.assertRaises(AccessError):
            run.with_user(self.reader).action_open_payroll_summary()
        with self.assertRaises(AccessError):
            run.with_user(self.reader).action_open_withholding_record()
        values = run.with_user(self.reader).read(
            ["conclusion_state", "payroll_gross_income_amount"]
        )[0]
        self.assertEqual(values["conclusion_state"], "aligned")
        self.assertEqual(values["payroll_gross_income_amount"], 10000.0)

    def test_company_rule_hides_other_company_scope(self):
        other_company = self.env["res.company"].create(
            {
                "name": "Other China IIT Company",
                "country_id": self.country.id,
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
        other_scope = self.env["sudo.cn.iit.accounting.scope"].sudo().with_company(
            other_company
        ).create(
            {
                "profile_id": other_profile.id,
                "valid_from": "2026-01-01",
                "source_reference": "OTHER/IIT/SCOPE",
                "scope_note": "Other company controlled IIT accounting scope.",
            }
        )

        visible = self.env["sudo.cn.iit.accounting.scope"].with_user(
            self.reader
        ).with_company(self.company).search([("id", "=", other_scope.id)])
        self.assertFalse(visible)

    def test_direct_creation_and_manual_changes_are_blocked(self):
        for model_name in (
            "sudo.cn.payroll.summary.record",
            "sudo.cn.iit.period.reconciliation.run",
            "sudo.cn.iit.period.reconciliation.issue",
        ):
            with self.assertRaises(AccessError):
                self.env[model_name].create({})
        with self.assertRaises(UserError):
            self._verified_scope("duplicate-role", line_ids=[])
