from unittest.mock import patch

from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestChinaInvoiceReconciliation(AccountTestInvoicingCommon):
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

        compliance_manager = cls.env.ref(
            "sudo_global_finance.group_compliance_manager"
        )
        compliance_user = cls.env.ref(
            "sudo_global_finance.group_compliance_user"
        )
        account_user = cls.env.ref("account.group_account_user")
        cls.reviewer = cls.env["res.users"].create(
            {
                "name": "China Reconciliation Reviewer",
                "login": "cn_reconciliation_reviewer",
                "company_id": cls.company.id,
                "company_ids": [Command.set(cls.company.ids)],
                "group_ids": [
                    Command.set((compliance_manager + account_user).ids)
                ],
            }
        )
        cls.manager_without_account = cls.env["res.users"].create(
            {
                "name": "China Reconciliation Compliance Manager",
                "login": "cn_reconciliation_compliance_manager",
                "company_id": cls.company.id,
                "company_ids": [Command.set(cls.company.ids)],
                "group_ids": [Command.set(compliance_manager.ids)],
            }
        )
        cls.read_only_user = cls.env["res.users"].create(
            {
                "name": "China Reconciliation Reader",
                "login": "cn_reconciliation_reader",
                "company_id": cls.company.id,
                "company_ids": [Command.set(cls.company.ids)],
                "group_ids": [Command.set(compliance_user.ids)],
            }
        )
        cls.seller = cls.env["res.partner"].with_company(cls.company).create(
            {
                "name": "测试销售方有限公司",
                "vat": "91440101MA5E67890G",
                "property_account_receivable_id": cls.company_data[
                    "default_account_receivable"
                ].id,
                "property_account_payable_id": cls.company_data[
                    "default_account_payable"
                ].id,
            }
        )

    def _attachment(self, suffix):
        return self.env["ir.attachment"].create(
            {
                "name": f"reconciliation-{suffix}.zip",
                "raw": f"controlled reconciliation input {suffix}".encode(),
                "mimetype": "application/zip",
            }
        )

    def _dataset(
        self,
        suffix,
        authenticity_state="not_checked",
        coverage_scope="full",
    ):
        attachment = self._attachment(suffix)
        values = {
            "profile_id": self.profile.id,
            "dataset_type": "electronic_invoice",
            "period_start": "2026-01-01",
            "period_end": "2026-06-30",
            "coverage_scope": coverage_scope,
            "scope_note": (
                "测试期间完整受控电子发票包。"
                if coverage_scope == "full"
                else "测试期间部分受控电子发票包。"
            ),
            "source_channel": "official_export",
            "source_system_name": "测试电子发票平台",
            "source_reference": f"EINV-RECON-{suffix}",
            "source_generated_at": "2026-06-30 09:00:00",
            "data_format": "zip",
            "authorization_basis": "测试公司自有账户导出。",
            "acquired_at": "2026-06-30 10:00:00",
            "declared_record_count": 1,
            "currency_id": self.currency.id,
            "declared_total_amount": 10170,
            "declared_tax_amount": 1170,
            "source_attachment_ids": [Command.set(attachment.ids)],
            "authenticity_state": authenticity_state,
        }
        if authenticity_state in (
            "official_tool_passed",
            "official_tool_failed",
        ):
            values.update(
                {
                    "authenticity_method": "受控真实性测试工具",
                    "authenticity_reference": f"AUTH-{suffix}",
                    "authenticity_evidence_attachment_ids": [
                        Command.set(attachment.ids)
                    ],
                }
            )
        dataset = self.env["sudo.cn.external.dataset"].with_company(
            self.company
        ).create(values)
        dataset.with_user(self.reviewer).action_seal()
        return dataset

    def _start_parse_run(self, dataset, suffix):
        return self.env["sudo.cn.external.parse.run"].with_user(
            self.reviewer
        ).with_company(self.company)._start_for_dataset(
            dataset,
            dataset.source_attachment_ids[:1],
            parser_key="mof_einvoice_xbrl",
            parser_version=f"reconciliation-test-{suffix}",
            parser_distribution="arelle-release test contract",
            taxonomy_namespace=(
                "http://xbrl.mof.gov.cn/taxonomy/2023-12-31/einv"
            ),
            taxonomy_version="2023-12-31",
            taxonomy_checksum="a" * 64,
            taxonomy_source_reference="MOF-EINV-RECONCILIATION-TEST",
        )

    def _accounting_document(
        self,
        voucher_number="R0009",
        amount=10170.0,
        posting_date="2026-06-30",
        summary="测试电子发票入账",
    ):
        formatted = f"{amount:.2f}"
        return {
            "voucher_number": voucher_number,
            "posting_date": posting_date,
            "accounting_period": posting_date[:7],
            "summary": summary,
            "entries": [
                {
                    "direction": "借方",
                    "general_ledger_subject": "原材料",
                    "amount": formatted,
                },
                {
                    "direction": "贷方",
                    "general_ledger_subject": "应付账款",
                    "amount": formatted,
                },
            ],
        }

    def _document_payload(self, suffix, **overrides):
        payload = {
            "source_document_key": f"reconciliation-{suffix}.xml",
            "invoice_number": f"TEST-EINV-{suffix}",
            "invoice_type_code": "VAT_SPECIAL",
            "request_time": "2026-06-30 08:30:00",
            "seller_name": self.seller.name,
            "seller_tax_id": self.seller.vat,
            "accounting_entity_name": self.company.name,
            "accounting_entity_tax_id": self.company.partner_id.vat,
            "currency_code": "CNY",
            "untaxed_amount": "9000.00",
            "tax_amount": "1170.00",
            "total_amount": "10170.00",
            "is_red": False,
            "is_booked": True,
            "is_checked": True,
            "is_paid": False,
            "source_fact_count": 30,
            "source_fact_digest": "b" * 64,
            "accounting_documents": [self._accounting_document()],
        }
        payload.update(overrides)
        return payload

    def _normalized_document(
        self,
        suffix,
        payload=None,
        authenticity_state="not_checked",
        coverage_scope="full",
    ):
        dataset = self._dataset(
            suffix,
            authenticity_state,
            coverage_scope,
        )
        parse_run = self._start_parse_run(dataset, suffix)
        if payload is None:
            documents = [self._document_payload(suffix)]
        elif isinstance(payload, list):
            documents = payload
        else:
            documents = [payload]
        result = parse_run._record_success(
            documents,
            observed_input_sha256=parse_run.input_sha256,
            source_fact_count=30,
            warning_count=0,
            error_count=0,
            parser_log_checksum="c" * 64,
        )
        self.assertTrue(result)
        return parse_run.document_ids

    def _bill(
        self,
        reference,
        invoice_date="2026-06-30",
        posted=True,
    ):
        line_values = {
            "name": "测试采购服务",
            "quantity": 1.0,
            "price_unit": 9000.0,
            "account_id": self.company_data["default_account_expense"].id,
        }
        if self.tax_purchase_a:
            line_values["tax_ids"] = [Command.set(self.tax_purchase_a.ids)]
        bill = self.env["account.move"].with_company(self.company).create(
            {
                "move_type": "in_invoice",
                "journal_id": self.company_data[
                    "default_journal_purchase"
                ].id,
                "partner_id": self.seller.id,
                "invoice_date": invoice_date,
                "date": invoice_date,
                "ref": reference,
                "invoice_line_ids": [Command.create(line_values)],
            }
        )
        if posted:
            bill.action_post()
        return bill

    def _entry(
        self,
        reference,
        amount=10170.0,
        entry_date="2026-06-30",
        posted=True,
    ):
        move = self.env["account.move"].with_company(self.company).create(
            {
                "move_type": "entry",
                "journal_id": self.company_data["default_journal_misc"].id,
                "date": entry_date,
                "ref": reference,
                "line_ids": [
                    Command.create(
                        {
                            "name": reference,
                            "account_id": self.company_data[
                                "default_account_expense"
                            ].id,
                            "debit": amount,
                        }
                    ),
                    Command.create(
                        {
                            "name": reference,
                            "account_id": self.company_data[
                                "default_account_revenue"
                            ].id,
                            "credit": amount,
                        }
                    ),
                ],
            }
        )
        if posted:
            move.action_post()
        return move

    def _queue(self, period_start="2026-06-01", period_end="2026-06-30"):
        return self.env[
            "sudo.cn.einvoice.reconciliation.run"
        ].with_user(self.reviewer).with_company(self.company).enqueue(
            self.profile,
            period_start,
            period_end,
        )

    def _process(self, run):
        result = run.with_user(self.reviewer).with_company(
            self.company
        )._process()
        run.invalidate_recordset()
        return result

    def _bill_payload(self, suffix, bill, accounting_documents=None):
        tax = bill.amount_tax
        total = bill.amount_total
        untaxed = bill.amount_untaxed
        return self._document_payload(
            suffix,
            invoice_number=bill.ref,
            untaxed_amount=f"{untaxed:.2f}",
            tax_amount=f"{tax:.2f}",
            total_amount=f"{total:.2f}",
            accounting_documents=(
                [self._accounting_document(amount=total)]
                if accounting_documents is None
                else accounting_documents
            ),
        )

    def test_direct_creation_of_governed_results_is_blocked(self):
        for model_name in (
            "sudo.cn.einvoice.reconciliation.run",
            "sudo.cn.einvoice.reconciliation.case",
            "sudo.cn.einvoice.reconciliation.candidate",
        ):
            with self.assertRaises(AccessError):
                self.env[model_name].create({})

        run = self._queue()
        with self.assertRaises(AccessError):
            run.write({"result_summary": "changed outside controlled flow"})

    def test_duplicate_active_period_is_blocked_and_cancel_releases_it(self):
        first = self._queue()

        with self.assertRaises(UserError):
            self._queue()

        first.with_user(self.reviewer).action_cancel()
        replacement = self._queue()
        self.assertEqual(replacement.state, "queued")

    def test_run_creates_explainable_high_confidence_bill_candidate(self):
        bill = self._bill("EINV-BILL-001")
        self._normalized_document(
            "bill-candidate",
            self._bill_payload("bill-candidate", bill),
        )

        run = self._queue()
        self.assertTrue(self._process(run))

        self.assertEqual(run.state, "succeeded")
        self.assertEqual(run.source_document_count, 1)
        self.assertEqual(run.case_count, 1)
        self.assertEqual(len(run.source_snapshot_checksum), 64)
        self.assertEqual(len(run.ledger_snapshot_checksum), 64)
        self.assertEqual(len(run.result_checksum), 64)
        case = run.case_ids
        self.assertEqual(case.state, "suggested")
        candidate = case.candidate_ids.filtered(
            lambda item: item.source_scope == "invoice"
        )
        self.assertEqual(len(candidate), 1)
        self.assertEqual(candidate.move_id, bill)
        self.assertEqual(candidate.confidence, "high")
        self.assertGreaterEqual(candidate.score, 75)
        self.assertIn(
            "invoice_reference_exact",
            {reason["code"] for reason in candidate.reason_json},
        )
        self.assertEqual(len(candidate.move_snapshot_checksum), 64)
        self.assertIn(
            "SOURCE_AUTHENTICITY_NOT_CONFIRMED",
            {gap["code"] for gap in case.data_gap_json},
        )

    def test_partial_source_coverage_is_visible_but_does_not_fake_failure(self):
        bill = self._bill("EINV-PARTIAL-COVERAGE")
        self._normalized_document(
            "partial-coverage",
            self._bill_payload("partial-coverage", bill),
            coverage_scope="partial",
        )
        run = self._queue()

        self.assertTrue(self._process(run))

        case = run.case_ids
        self.assertEqual(case.state, "suggested")
        self.assertTrue(case.candidate_ids)
        self.assertEqual(case.blocking_issue_count, 0)
        self.assertGreaterEqual(case.warning_issue_count, 1)
        self.assertIn(
            "SOURCE_COVERAGE_NOT_FULL",
            {gap["code"] for gap in case.data_gap_json},
        )

    def test_confirmed_bill_is_audited_and_detects_later_change(self):
        bill = self._bill("EINV-BILL-002")
        self._normalized_document(
            "bill-confirm",
            self._bill_payload(
                "bill-confirm",
                bill,
                accounting_documents=[],
            ),
        )
        run = self._queue()
        self.assertTrue(self._process(run))
        case = run.case_ids
        candidate = case.candidate_ids.filtered(
            lambda item: item.source_scope == "invoice"
        )

        candidate.with_user(self.reviewer).action_confirm()

        self.assertEqual(case.state, "matched")
        self.assertEqual(case.match_mode, "bill")
        self.assertEqual(case.confirmed_move_ids, bill)
        event = self.env["sudo.compliance.audit.event"].search(
            [
                ("model_name", "=", candidate._name),
                ("record_id", "=", candidate.id),
                (
                    "event_key",
                    "=",
                    "cn_einvoice_reconciliation.confirmed",
                ),
            ]
        )
        self.assertEqual(event.details_json["move_id"], bill.id)

        bill.ref = "EINV-BILL-002-CHANGED"
        candidate.invalidate_recordset(["integrity_state"])
        case.invalidate_recordset(["decision_integrity_state"])
        self.assertEqual(candidate.integrity_state, "mismatch")
        self.assertEqual(case.decision_integrity_state, "mismatch")

    def test_voucher_mode_supports_multiple_source_vouchers(self):
        first_move = self._entry("VOUCHER-001", amount=100.0)
        second_move = self._entry("VOUCHER-002", amount=200.0)
        accounting_documents = [
            self._accounting_document("VOUCHER-001", 100.0),
            self._accounting_document("VOUCHER-002", 200.0),
        ]
        payload = self._document_payload(
            "multiple-vouchers",
            untaxed_amount="300.00",
            tax_amount="0.00",
            total_amount="300.00",
            accounting_documents=accounting_documents,
        )
        self._normalized_document("multiple-vouchers", payload)
        run = self._queue()
        self.assertTrue(self._process(run))
        case = run.case_ids
        self.assertEqual(case.initial_state, "ambiguous")

        first_candidate = case.candidate_ids.filtered(
            lambda item: item.source_scope == "voucher"
            and item.move_id == first_move
            and item.source_accounting_document_id.voucher_number
            == "VOUCHER-001"
        )
        second_candidate = case.candidate_ids.filtered(
            lambda item: item.source_scope == "voucher"
            and item.move_id == second_move
            and item.source_accounting_document_id.voucher_number
            == "VOUCHER-002"
        )
        self.assertEqual(len(first_candidate), 1)
        self.assertEqual(len(second_candidate), 1)

        first_candidate.with_user(self.reviewer).action_confirm()
        self.assertEqual(case.state, "partial")
        second_candidate.with_user(self.reviewer).action_confirm()
        self.assertEqual(case.state, "matched")
        self.assertEqual(case.match_mode, "voucher")
        self.assertEqual(case.confirmed_candidate_count, 2)

    def test_entity_mismatch_is_a_data_gap_without_candidates(self):
        payload = self._document_payload(
            "entity-mismatch",
            accounting_entity_tax_id="91310000MA1BAD9995",
        )
        self._normalized_document("entity-mismatch", payload)
        run = self._queue()

        self.assertTrue(self._process(run))

        case = run.case_ids
        self.assertEqual(case.state, "data_gap")
        self.assertFalse(case.candidate_ids)
        self.assertGreaterEqual(case.blocking_issue_count, 1)
        self.assertIn(
            "ACCOUNTING_ENTITY_MISMATCH",
            {gap["code"] for gap in case.data_gap_json},
        )

    def test_failed_authenticity_is_a_data_gap_without_candidates(self):
        bill = self._bill("EINV-AUTH-FAILED")
        self._normalized_document(
            "authenticity-failed",
            self._bill_payload("authenticity-failed", bill),
            authenticity_state="official_tool_failed",
        )
        run = self._queue()

        self.assertTrue(self._process(run))

        case = run.case_ids
        self.assertEqual(case.state, "data_gap")
        self.assertFalse(case.candidate_ids)
        self.assertIn(
            "SOURCE_AUTHENTICITY_FAILED",
            {gap["code"] for gap in case.data_gap_json},
        )

    def test_duplicate_current_source_invoices_are_blocked(self):
        first = self._document_payload(
            "duplicate-one",
            invoice_number="EINV-DUPLICATE-001",
        )
        second = self._document_payload(
            "duplicate-two",
            invoice_number="EINV-DUPLICATE-001",
        )
        self._normalized_document("duplicate-source", [first, second])
        run = self._queue()

        self.assertTrue(self._process(run))

        self.assertEqual(run.source_document_count, 2)
        self.assertEqual(set(run.case_ids.mapped("state")), {"data_gap"})
        self.assertFalse(run.case_ids.mapped("candidate_ids"))
        for case in run.case_ids:
            self.assertIn(
                "DUPLICATE_CURRENT_SOURCE_INVOICE",
                {gap["code"] for gap in case.data_gap_json},
            )
            self.assertIn(
                "SOURCE_RECORD_COUNT_MISMATCH",
                {gap["code"] for gap in case.data_gap_json},
            )

    def test_no_candidate_is_reported_as_unmatched(self):
        self._normalized_document("unmatched")
        run = self._queue()

        self.assertTrue(self._process(run))

        self.assertEqual(run.case_ids.state, "unmatched")
        self.assertEqual(run.unmatched_case_count, 1)
        self.assertFalse(run.case_ids.candidate_ids)

    def test_no_source_data_is_explicit_and_not_a_silent_pass(self):
        run = self._queue()

        self.assertTrue(self._process(run))

        self.assertEqual(run.state, "succeeded")
        self.assertEqual(run.source_availability_state, "no_data")
        self.assertEqual(run.source_document_count, 0)
        self.assertEqual(run.ledger_move_count, 0)
        self.assertFalse(run.case_ids)
        self.assertIn("不能形成账票匹配", run.result_summary)

    def test_equal_voucher_candidates_are_reported_as_ambiguous(self):
        self._entry("VOUCHER-AMBIGUOUS", amount=500.0)
        self._entry("VOUCHER-AMBIGUOUS", amount=500.0)
        payload = self._document_payload(
            "ambiguous",
            untaxed_amount="500.00",
            tax_amount="0.00",
            total_amount="500.00",
            accounting_documents=[
                self._accounting_document("VOUCHER-AMBIGUOUS", 500.0)
            ],
        )
        self._normalized_document("ambiguous", payload)
        run = self._queue()

        self.assertTrue(self._process(run))

        case = run.case_ids
        self.assertEqual(case.state, "ambiguous")
        self.assertEqual(case.high_confidence_count, 2)

    def test_draft_candidate_cannot_be_confirmed(self):
        bill = self._bill("EINV-DRAFT-001", posted=False)
        self._normalized_document(
            "draft-candidate",
            self._bill_payload(
                "draft-candidate",
                bill,
                accounting_documents=[],
            ),
        )
        run = self._queue()
        self.assertTrue(self._process(run))
        candidate = run.case_ids.candidate_ids.filtered(
            lambda item: item.source_scope == "invoice"
        )
        self.assertEqual(candidate.move_state_snapshot, "draft")

        with self.assertRaises(UserError):
            candidate.with_user(self.reviewer).action_confirm()

    def test_manual_match_requires_roles_note_and_valid_scope(self):
        self._normalized_document("manual-match")
        run = self._queue()
        self.assertTrue(self._process(run))
        case = run.case_ids
        source_voucher = case.einvoice_document_id.accounting_document_ids
        move = self._entry("MANUAL-VOUCHER-001")

        with self.assertRaises(AccessError):
            case.with_user(self.manager_without_account)._create_manual_candidate(
                "voucher",
                source_voucher,
                move,
                "该说明长度足够但用户没有会计权限。",
            )
        with self.assertRaises(ValidationError):
            case.with_user(self.reviewer)._create_manual_candidate(
                "voucher",
                source_voucher,
                move,
                "太短",
            )
        with self.assertRaises(UserError):
            case.with_user(self.reviewer)._create_manual_candidate(
                "invoice",
                False,
                move,
                "普通日记账不得作为发票级供应商账单确认。",
            )

        candidate = case.with_user(self.reviewer)._create_manual_candidate(
            "voucher",
            source_voucher,
            move,
            "已核对原始电子发票与该已过账会计凭证。",
        )
        self.assertEqual(candidate.origin, "manual")
        self.assertEqual(candidate.state, "confirmed")
        self.assertEqual(case.state, "matched")

    def test_reject_and_reset_restore_initial_case_state(self):
        bill = self._bill("EINV-REJECT-001")
        self._normalized_document(
            "reject-reset",
            self._bill_payload(
                "reject-reset",
                bill,
                accounting_documents=[],
            ),
        )
        run = self._queue()
        self.assertTrue(self._process(run))
        case = run.case_ids
        candidate = case.candidate_ids

        candidate.with_user(self.reviewer).action_reject()
        self.assertEqual(case.state, "reviewed_unmatched")
        candidate.with_user(self.reviewer).action_reset_decision()
        self.assertEqual(candidate.state, "proposed")
        self.assertEqual(case.state, "suggested")

    def test_failed_retry_does_not_replace_previous_success(self):
        self._normalized_document("failed-retry")
        first = self._queue()
        self.assertTrue(self._process(first))
        failed = self._queue()

        def fail_build(_run):
            raise ValidationError("受控测试失败")

        with patch.object(type(failed), "_build_results", fail_build):
            self.assertFalse(self._process(failed))

        first.invalidate_recordset()
        self.assertEqual(first.state, "succeeded")
        self.assertEqual(failed.state, "failed")
        self.assertTrue(first.case_ids.is_current_run)

        replacement = self._queue()
        self.assertTrue(self._process(replacement))
        first.invalidate_recordset()
        self.assertEqual(first.state, "superseded")
        self.assertEqual(replacement.state, "succeeded")

    def test_invoice_and_voucher_confirmation_modes_cannot_mix(self):
        reference = "EINV-MODE-001"
        bill = self._bill(reference)
        payload = self._bill_payload(
            "mode-mix",
            bill,
            accounting_documents=[
                self._accounting_document(reference, bill.amount_total)
            ],
        )
        self._normalized_document("mode-mix", payload)
        run = self._queue()
        self.assertTrue(self._process(run))
        case = run.case_ids
        invoice_candidate = case.candidate_ids.filtered(
            lambda item: item.source_scope == "invoice"
        )
        voucher_candidate = case.candidate_ids.filtered(
            lambda item: item.source_scope == "voucher"
            and item.move_id == bill
        )
        self.assertEqual(len(invoice_candidate), 1)
        self.assertEqual(len(voucher_candidate), 1)

        invoice_candidate.with_user(self.reviewer).action_confirm()
        with self.assertRaises(UserError):
            voucher_candidate.with_user(self.reviewer).action_confirm()

    def test_read_only_access_is_company_isolated(self):
        own_run = self._queue()
        own_visible = self.env[
            "sudo.cn.einvoice.reconciliation.run"
        ].with_user(self.read_only_user).search([("id", "=", own_run.id)])
        self.assertEqual(own_visible, own_run)
        with self.assertRaises(AccessError):
            self.env[
                "sudo.cn.einvoice.reconciliation.run"
            ].with_user(self.read_only_user).enqueue(
                self.profile,
                "2026-07-01",
                "2026-07-31",
            )

        other_company = self.env["res.company"].create(
            {
                "name": "Other China Reconciliation Company",
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
                "name": "Other China Reconciliation Manager",
                "login": "other_cn_reconciliation_manager",
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
            "sudo.cn.einvoice.reconciliation.run"
        ].with_user(other_manager).with_company(other_company).enqueue(
            other_profile,
            "2026-06-01",
            "2026-06-30",
        )
        hidden = self.env[
            "sudo.cn.einvoice.reconciliation.run"
        ].with_user(self.read_only_user).search([("id", "=", other_run.id)])
        self.assertFalse(hidden)
