import json

from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestChinaCitPeriodReconciliation(AccountTestInvoicingCommon):
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
                "name": "China CIT Scope Author",
                "login": "cn_cit_scope_author",
                "company_id": cls.company.id,
                "company_ids": [Command.set(cls.company.ids)],
                "group_ids": [Command.set(manager_group.ids)],
            }
        )
        cls.reviewer = cls.env["res.users"].create(
            {
                "name": "China CIT Reconciliation Reviewer",
                "login": "cn_cit_reconciliation_reviewer",
                "company_id": cls.company.id,
                "company_ids": [Command.set(cls.company.ids)],
                "group_ids": [Command.set(manager_group.ids)],
            }
        )
        cls.reader = cls.env["res.users"].create(
            {
                "name": "China CIT Reconciliation Reader",
                "login": "cn_cit_reconciliation_reader",
                "company_id": cls.company.id,
                "company_ids": [Command.set(cls.company.ids)],
                "group_ids": [Command.set(user_group.ids)],
            }
        )
        cls.balance_account = cls.env["account.account"].with_company(
            cls.company
        ).create(
            {
                "name": "CIT reconciliation balancing account",
                "code": "19999998",
                "account_type": "asset_current",
                "company_ids": [Command.set(cls.company.ids)],
            }
        )

    def _attachment(self, name, raw, mimetype="application/pdf"):
        return self.env["ir.attachment"].with_user(self.scope_author).create(
            {"name": name, "raw": raw, "mimetype": mimetype}
        )

    def _ledger_profit(self, *, revenue=1000.0, expense=400.0, posted=True):
        move = self.env["account.move"].with_company(self.company).create(
            {
                "move_type": "entry",
                "journal_id": self.company_data["default_journal_misc"].id,
                "date": "2026-06-30",
                "ref": "TEST-CIT-BOOK-PROFIT",
                "line_ids": [
                    Command.create(
                        {
                            "name": "Revenue counterparty",
                            "account_id": self.balance_account.id,
                            "debit": revenue,
                        }
                    ),
                    Command.create(
                        {
                            "name": "Revenue",
                            "account_id": self.company_data[
                                "default_account_revenue"
                            ].id,
                            "credit": revenue,
                        }
                    ),
                    Command.create(
                        {
                            "name": "Expense",
                            "account_id": self.company_data[
                                "default_account_expense"
                            ].id,
                            "debit": expense,
                        }
                    ),
                    Command.create(
                        {
                            "name": "Expense counterparty",
                            "account_id": self.balance_account.id,
                            "credit": expense,
                        }
                    ),
                ],
            }
        )
        if posted:
            move.action_post()
        return move

    def _verified_scope(self, suffix="default"):
        scope = self.env["sudo.cn.cit.accounting.scope"].with_user(
            self.scope_author
        ).with_company(self.company).create(
            {
                "profile_id": self.profile.id,
                "valid_from": "2026-01-01",
                "valid_to": "2026-12-31",
                "source_reference": f"TEST/CIT/SCOPE/{suffix}",
                "scope_note": (
                    "覆盖当前公司科目表全部有效损益科目；按 Odoo 科目类型区分"
                    "利润增加和减少方向，测试期间没有期初或期末损益结转凭证。"
                ),
            }
        )
        evidence = self._attachment(
            f"cit-accounting-scope-{suffix}.pdf",
            f"controlled CIT accounting scope {suffix}".encode(),
        )
        evidence.sudo().write({"res_model": scope._name, "res_id": scope.id})
        scope.with_user(self.scope_author).write(
            {"evidence_attachment_ids": [Command.set(evidence.ids)]}
        )
        scope.with_user(self.scope_author).action_populate_from_chart()
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
                "scope_note": "测试期间完整受控来源，包含零记录声明。",
                "source_channel": "official_export",
                "source_system_name": "测试电子税务数据源",
                "source_reference": f"TEST-CIT-{dataset_type}-{suffix}",
                "source_generated_at": "2026-07-10 09:00:00",
                "data_format": "json",
                "authorization_basis": "测试公司自有账户受控导出。",
                "acquired_at": "2026-07-10 10:00:00",
                "declared_record_count": record_count,
                "currency_id": self.currency.id,
                "source_attachment_ids": [Command.set(attachment.ids)],
                "authenticity_state": "not_applicable",
            }
        )
        attachment.sudo().write(
            {"res_model": dataset._name, "res_id": dataset.id}
        )
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
            f"cit-period-{dataset_type}-{suffix}.json",
            raw,
            "application/json",
        )
        dataset = self._external_dataset(
            dataset_type, suffix, attachment, len(records)
        )
        run = self.env["sudo.cn.tax.data.parse.run"].with_user(
            self.reviewer
        ).with_company(self.company)._start_for_dataset(dataset, attachment)
        self.assertTrue(
            run.with_user(self.reviewer)._process_json_attachment()
        )
        return run

    def _cit_filing(
        self,
        suffix,
        *,
        accounting_profit=600.0,
        adjustment_increase=100.0,
        adjustment_decrease=50.0,
        taxable_income=650.0,
        payable=12.5,
        refundable=0.0,
        omit=(),
    ):
        record = {
            "source_record_key": f"CIT-FILING-{suffix}",
            "taxpayer_name": self.company.name,
            "taxpayer_id": self.company.partner_id.vat,
            "period_start": "2026-06-01",
            "period_end": "2026-06-30",
            "currency_code": "CNY",
            "tax_year": 2026,
            "return_period_type": "quarterly_prepayment",
            "return_type_code": "CIT-QUARTERLY",
            "return_status": "accepted",
            "submitted_at": "2026-07-12T09:00:00+08:00",
            "submission_reference": f"CIT-ACK-{suffix}",
            "revision_number": 0,
            "accounting_profit_amount": f"{accounting_profit:.2f}",
            "adjustment_increase_amount": f"{adjustment_increase:.2f}",
            "adjustment_decrease_amount": f"{adjustment_decrease:.2f}",
            "taxable_income_amount": f"{taxable_income:.2f}",
            "tax_payable_amount": "162.50",
            "tax_relief_amount": "0.00",
            "tax_credit_amount": "0.00",
            "prepaid_tax_amount": "150.00",
            "payable_amount": f"{payable:.2f}",
            "refundable_amount": f"{refundable:.2f}",
            "lines": [],
        }
        for field_name in omit:
            record.pop(field_name, None)
        return record

    def _payment(
        self,
        suffix,
        amount=12.5,
        *,
        status="succeeded",
        include_principal=True,
    ):
        record = {
            "source_record_key": f"CIT-PAYMENT-{suffix}",
            "taxpayer_name": self.company.name,
            "taxpayer_id": self.company.partner_id.vat,
            "tax_type_code": "CIT",
            "period_start": "2026-06-01",
            "period_end": "2026-06-30",
            "payment_date": "2026-07-15",
            "payment_reference": f"CIT-PAY-REF-{suffix}",
            "payment_status": status,
            "currency_code": "CNY",
            "amount": f"{amount:.2f}",
            "interest_amount": "0.00",
            "penalty_amount": "0.00",
            "payer_account_masked": "尾号 1234",
            "receipt_reference": f"CIT-PAY-ACK-{suffix}",
        }
        if include_principal:
            record["principal_amount"] = f"{amount:.2f}"
        return record

    def _queue(self):
        return self.env["sudo.cn.cit.period.reconciliation.run"].with_user(
            self.reviewer
        ).with_company(self.company).enqueue(
            self.profile,
            "2026-06-01",
            "2026-06-30",
            "quarterly_prepayment",
            "CIT",
        )

    def _seed_complete_sources(
        self,
        suffix,
        *,
        filing_values=None,
        payment_values=None,
    ):
        self._ledger_profit()
        scope = self._verified_scope(suffix)
        filing = filing_values or self._cit_filing(suffix)
        payment = payment_values or self._payment(suffix)
        filing_run = self._create_tax_records("cit_filing", suffix, [filing])
        payment_run = self._create_tax_records("tax_payment", suffix, [payment])
        return {"scope": scope, "filing_run": filing_run, "payment_run": payment_run}

    def _assessment(self, start="2026-06-01", end="2026-06-30"):
        return self.env["sudo.compliance.assessment"].create(
            {
                "profile_id": self.profile.id,
                "evaluation_date": "2026-07-16",
                "period_start": start,
                "period_end": end,
            }
        )

    def _fact(self, key, assessment=None):
        assessment = assessment or self._assessment()
        provider = self.env["sudo.compliance.engine"]._fact_provider_registry()[key]
        return provider(assessment, False)

    def test_scope_populates_full_chart_and_is_immutable_after_review(self):
        scope = self._verified_scope("governance")
        expected = scope._expected_accounts(self.company)

        self.assertEqual(scope.state, "verified")
        self.assertEqual(scope.integrity_state, "verified")
        self.assertEqual(set(scope.line_ids.account_id.ids), set(expected.ids))
        self.assertEqual(len(scope.verification_checksum), 64)
        self.assertEqual(
            set(
                scope.line_ids.filtered(
                    lambda line: line.role == "profit_increase"
                ).mapped("account_type")
            ),
            {"income", "income_other"},
        )
        with self.assertRaises(AccessError):
            scope.with_user(self.scope_author).write({"scope_note": "changed"})
        with self.assertRaises(AccessError):
            scope.line_ids[:1].with_user(self.scope_author).write(
                {"role": "profit_decrease"}
            )

    def test_aligned_run_preserves_separate_book_return_payment_facts(self):
        self._seed_complete_sources("aligned")
        run = self._queue()
        self.assertTrue(run.with_user(self.reviewer)._process())
        run.invalidate_recordset()

        self.assertEqual(run.state, "succeeded")
        self.assertEqual(run.conclusion_state, "aligned")
        self.assertEqual(run.blocking_issue_count, 0)
        self.assertEqual(run.difference_issue_count, 0)
        self.assertEqual(run.ledger_accounting_profit_amount, 600.0)
        self.assertEqual(run.filing_accounting_profit_amount, 600.0)
        self.assertEqual(run.expected_taxable_income_amount, 650.0)
        self.assertEqual(run.filing_taxable_income_amount, 650.0)
        self.assertEqual(run.filing_payable_amount, 12.5)
        self.assertEqual(run.effective_paid_principal_amount, 12.5)
        self.assertEqual(run.filing_refundable_amount, 0.0)
        self.assertEqual(run.refunded_principal_amount, 0.0)
        self.assertEqual(len(run.result_checksum), 64)
        self.assertEqual(run.result_integrity_state, "verified")
        self.assertEqual(
            run.accounting_snapshot_json["schema"],
            "sdoo.cn.cit-accounting-ledger.v1",
        )
        with self.assertRaises(AccessError):
            run.write({"result_summary": "changed"})

    def test_missing_external_sources_is_insufficient_not_aligned(self):
        self._ledger_profit()
        self._verified_scope("missing-sources")
        run = self._queue()
        self.assertTrue(run.with_user(self.reviewer)._process())

        self.assertEqual(run.conclusion_state, "insufficient_data")
        self.assertGreaterEqual(run.blocking_issue_count, 2)
        self.assertIn(
            "NO_CURRENT_CIT_FILING",
            run.issue_ids.mapped("code"),
        )
        self.assertIn(
            "NO_CURRENT_CIT_PAYMENT_DATASET",
            run.issue_ids.mapped("code"),
        )
        self.assertFalse(run.has_ledger_filing_profit_difference)
        self.assertFalse(run.has_payable_payment_difference)

    def test_differences_are_review_items_not_blocking_tax_conclusions(self):
        filing = self._cit_filing(
            "differences",
            accounting_profit=610.0,
            taxable_income=660.0,
            payable=20.0,
        )
        self._seed_complete_sources("differences", filing_values=filing)
        run = self._queue()
        self.assertTrue(run.with_user(self.reviewer)._process())

        self.assertEqual(run.conclusion_state, "differences")
        self.assertEqual(run.blocking_issue_count, 0)
        self.assertEqual(run.ledger_filing_profit_difference, -10.0)
        self.assertEqual(run.payable_payment_difference, 7.5)
        self.assertIn(
            "CIT_LEDGER_FILING_PROFIT_DIFFERENCE",
            run.issue_ids.mapped("code"),
        )
        self.assertIn(
            "CIT_PAYABLE_PAYMENT_DIFFERENCE",
            run.issue_ids.mapped("code"),
        )
        self.assertTrue(
            all(
                issue.severity == "review"
                for issue in run.issue_ids.filtered(
                    lambda issue: issue.issue_kind == "difference"
                )
            )
        )

    def test_missing_profit_chain_field_is_not_treated_as_zero(self):
        filing = self._cit_filing(
            "missing-adjustment",
            omit={"adjustment_decrease_amount"},
        )
        self._seed_complete_sources("missing-adjustment", filing_values=filing)
        run = self._queue()
        self.assertTrue(run.with_user(self.reviewer)._process())

        self.assertEqual(run.conclusion_state, "insufficient_data")
        self.assertIn(
            "CIT_FILING_PROFIT_CHAIN_INCOMPLETE",
            run.issue_ids.mapped("code"),
        )
        self.assertFalse(run.has_expected_taxable_income_amount)
        self.assertFalse(run.has_filing_taxable_arithmetic_difference)

    def test_payment_total_without_principal_blocks_payable_comparison(self):
        payment = self._payment(
            "missing-principal", include_principal=False
        )
        self._seed_complete_sources("missing-principal", payment_values=payment)
        run = self._queue()
        self.assertTrue(run.with_user(self.reviewer)._process())

        self.assertEqual(run.conclusion_state, "insufficient_data")
        self.assertIn(
            "CIT_PAYMENT_PRINCIPAL_MISSING",
            run.issue_ids.mapped("code"),
        )
        self.assertFalse(run.has_payable_payment_difference)

    def test_tampered_verified_scope_blocks_accounting_conclusion(self):
        self._ledger_profit()
        scope = self._verified_scope("tampered-scope")
        line = scope.line_ids[:1]
        tampered_role = (
            "profit_decrease"
            if line.role == "profit_increase"
            else "profit_increase"
        )
        self.env.cr.execute(
            """
            UPDATE sudo_cn_cit_accounting_scope_line
               SET role = %s
             WHERE id = %s
            """,
            [tampered_role, line.id],
        )
        scope.invalidate_recordset()
        line.invalidate_recordset()
        self._create_tax_records(
            "cit_filing", "tampered-scope", [self._cit_filing("tampered-scope")]
        )
        self._create_tax_records(
            "tax_payment", "tampered-scope", [self._payment("tampered-scope")]
        )

        run = self._queue()
        self.assertTrue(run.with_user(self.reviewer)._process())

        self.assertEqual(scope.integrity_state, "checksum_mismatch")
        self.assertEqual(run.accounting_source_state, "blocked")
        self.assertEqual(run.conclusion_state, "insufficient_data")
        self.assertIn(
            "CIT_ACCOUNTING_SCOPE_INTEGRITY_FAILED",
            run.issue_ids.mapped("code"),
        )
        self.assertFalse(run.has_ledger_filing_profit_difference)

    def test_fact_provider_exposes_exact_period_auditable_snapshot(self):
        self._seed_complete_sources("facts")
        run = self._queue()
        self.assertTrue(run.with_user(self.reviewer)._process())

        conclusion = self._fact("cn.reconciliation.cit.conclusion_state")
        blocking = self._fact("cn.reconciliation.cit.blocking_issue_count")
        detail = self._fact("cn.reconciliation.cit.detail")

        self.assertEqual(conclusion["value"], "aligned")
        self.assertEqual(conclusion["quality_state"], "complete")
        self.assertEqual(conclusion["source_record_ids"], run.ids)
        self.assertEqual(blocking["value"], 0)
        self.assertEqual(detail["value"]["run_id"], run.id)
        self.assertEqual(
            detail["value"]["checksums"]["result"], run.result_checksum
        )
        self.assertIsNone(
            self._fact(
                "cn.reconciliation.cit.conclusion_state",
                self._assessment("2026-05-01", "2026-05-31"),
            )["value"]
        )
        self.env.cr.execute(
            """
            UPDATE sudo_cn_cit_period_reconciliation_run
               SET ledger_accounting_profit_amount =
                   ledger_accounting_profit_amount + 1
             WHERE id = %s
            """,
            [run.id],
        )
        run.invalidate_recordset(["ledger_accounting_profit_amount"])
        run.invalidate_recordset(["result_integrity_state"])
        self.assertEqual(run.result_integrity_state, "checksum_mismatch")
        with self.assertRaisesRegex(UserError, "结果完整性异常"):
            self._fact("cn.reconciliation.cit.conclusion_state")

    def test_company_rule_hides_other_company_scope(self):
        other_company = self.env["res.company"].create(
            {
                "name": "Other China CIT Company",
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
        other_scope = self.env["sudo.cn.cit.accounting.scope"].sudo().with_company(
            other_company
        ).create(
            {
                "profile_id": other_profile.id,
                "valid_from": "2026-01-01",
                "source_reference": "OTHER/CIT/SCOPE",
                "scope_note": "Other company controlled scope.",
            }
        )

        visible = self.env["sudo.cn.cit.accounting.scope"].with_user(
            self.reader
        ).with_company(self.company).search([("id", "=", other_scope.id)])
        self.assertFalse(visible)

    def test_run_and_issue_cannot_be_created_or_changed_manually(self):
        with self.assertRaises(AccessError):
            self.env["sudo.cn.cit.period.reconciliation.run"].with_user(
                self.reviewer
            ).create(
                {
                    "profile_id": self.profile.id,
                    "period_start": "2026-06-01",
                    "period_end": "2026-06-30",
                    "return_period_type": "quarterly_prepayment",
                    "cit_tax_type_code": "CIT",
                }
            )
        with self.assertRaises(AccessError):
            self.env["sudo.cn.cit.period.reconciliation.issue"].with_user(
                self.reviewer
            ).create(
                {
                    "name": "manual issue",
                    "sequence": 1,
                    "run_id": 1,
                    "code": "MANUAL",
                    "issue_kind": "data_gap",
                    "severity": "blocking",
                    "source_area": "filing",
                }
            )
