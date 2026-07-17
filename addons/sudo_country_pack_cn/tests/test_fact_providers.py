from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestChinaFactProviders(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.country = cls.env.ref("base.cn")
        cls.company = cls.env["res.company"].create(
            {
                "name": "China Fact Provider Test Company",
                "currency_id": cls.env.ref("base.CNY").id,
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
        cls.assessment = cls.env["sudo.compliance.assessment"].create(
            {
                "profile_id": cls.profile.id,
                "evaluation_date": "2099-12-31",
                "period_start": "2099-01-01",
                "period_end": "2099-12-31",
            }
        )
        cls.engine = cls.env["sudo.compliance.engine"]

    def _provider(self, key):
        return self.engine._fact_provider_registry()[key]

    def test_registry_contains_all_china_foundation_providers(self):
        expected = {
            "cn.company.unified_social_credit_code",
            "cn.company.registration_evidence_count",
            "cn.company.fiscal_year_end_confirmed",
            "cn.taxpayer.classification_verified",
            "cn.taxpayer.classification_detail",
            "cn.account.posted_move_count",
            "cn.account.unposted_move_count",
            "cn.account.posted_invoice_count",
            "cn.account.ledger_basis_detail",
            "cn.evidence.invoice_missing_attachment_count",
            "cn.vat_invoice.posted_line_without_tax_count",
            "cn.master.transaction_partner_missing_tax_id_count",
            "cn.reconciliation.einvoice.source_state",
            "cn.reconciliation.einvoice.data_gap_case_count",
            "cn.reconciliation.einvoice.unresolved_case_count",
            "cn.reconciliation.einvoice.decision_integrity_mismatch_count",
            "cn.reconciliation.einvoice.detail",
            "cn.reconciliation.vat.conclusion_state",
            "cn.reconciliation.vat.blocking_issue_count",
            "cn.reconciliation.vat.difference_issue_count",
            "cn.reconciliation.vat.warning_issue_count",
            "cn.reconciliation.vat.detail",
            "cn.reconciliation.vat.risk_summary",
            "cn.reconciliation.cit.conclusion_state",
            "cn.reconciliation.cit.blocking_issue_count",
            "cn.reconciliation.cit.difference_issue_count",
            "cn.reconciliation.cit.warning_issue_count",
            "cn.reconciliation.cit.detail",
            "cn.reconciliation.iit.conclusion_state",
            "cn.reconciliation.iit.blocking_issue_count",
            "cn.reconciliation.iit.difference_issue_count",
            "cn.reconciliation.iit.warning_issue_count",
            "cn.reconciliation.iit.detail",
        }
        self.assertFalse(
            expected - set(self.engine._fact_provider_registry())
        )

    def test_uscc_is_missing_without_controlled_or_company_identifier(self):
        payload = self._provider(
            "cn.company.unified_social_credit_code"
        )(self.assessment, False)

        self.assertIsNone(payload["value"])
        self.assertEqual(payload["quality_state"], "missing")
        self.assertFalse(payload["is_complete"])

    def test_company_identifier_fallback_is_explicitly_truncated(self):
        self.company.partner_id.company_registry = "CN-UNCONTROLLED-001"

        payload = self._provider(
            "cn.company.unified_social_credit_code"
        )(self.assessment, False)

        self.assertEqual(payload["value"], "CN-UNCONTROLLED-001")
        self.assertEqual(payload["quality_state"], "truncated")
        self.assertFalse(payload["is_complete"])

    def test_controlled_uscc_and_attachment_clues_are_separate_facts(self):
        attachment = self.env["ir.attachment"].create(
            {"name": "business-license.txt", "raw": b"test evidence clue"}
        )
        registration = self.env["sudo.compliance.registration"].create(
            {
                "name": "统一社会信用代码登记",
                "profile_id": self.profile.id,
                "registration_type": "unified_social_credit_code",
                "registration_number": "91310000TEST000001",
                "authority": "市场监督管理部门",
                "valid_from": "2099-01-01",
                "state": "active",
                "evidence_attachment_ids": [Command.set(attachment.ids)],
            }
        )

        uscc = self._provider(
            "cn.company.unified_social_credit_code"
        )(self.assessment, False)
        evidence = self._provider(
            "cn.company.registration_evidence_count"
        )(self.assessment, False)

        self.assertEqual(uscc["value"], registration.registration_number)
        self.assertTrue(uscc["is_complete"])
        self.assertEqual(uscc["source_record_ids"], registration.ids)
        self.assertEqual(evidence["value"], 1)
        self.assertEqual(evidence["quality_state"], "complete")

    def test_conflicting_active_uscc_records_raise_configuration_error(self):
        values = {
            "name": "统一社会信用代码登记",
            "profile_id": self.profile.id,
            "registration_type": "uscc",
            "authority": "市场监督管理部门",
            "valid_from": "2099-01-01",
            "state": "active",
        }
        self.env["sudo.compliance.registration"].create(
            {**values, "registration_number": "91310000TEST000002"}
        )
        self.env["sudo.compliance.registration"].create(
            {**values, "registration_number": "91310000TEST000003"}
        )

        with self.assertRaises(UserError):
            self._provider("cn.company.unified_social_credit_code")(
                self.assessment, False
            )

    def test_unposted_move_count_is_company_and_period_isolated(self):
        journal = self.env["account.journal"].create(
            {
                "name": "China Fact Test Journal",
                "code": "ZCN1",
                "type": "general",
                "company_id": self.company.id,
            }
        )
        self.env["account.move"].with_company(self.company).create(
            {
                "date": "2099-06-01",
                "journal_id": journal.id,
                "company_id": self.company.id,
                "move_type": "entry",
            }
        )
        self.env["account.move"].with_company(self.company).create(
            {
                "date": "2098-06-01",
                "journal_id": journal.id,
                "company_id": self.company.id,
                "move_type": "entry",
            }
        )

        payload = self._provider("cn.account.unposted_move_count")(
            self.assessment, False
        )

        self.assertEqual(payload["value"], 1)
        self.assertTrue(payload["is_full_dataset"])
        self.assertIn(("company_id", "=", self.company.id), payload["source_domain"])

    def test_zero_counts_remain_complete_observations(self):
        for key in (
            "cn.account.posted_move_count",
            "cn.account.posted_invoice_count",
            "cn.evidence.invoice_missing_attachment_count",
            "cn.vat_invoice.posted_line_without_tax_count",
            "cn.master.transaction_partner_missing_tax_id_count",
        ):
            payload = self._provider(key)(self.assessment, False)
            self.assertEqual(payload["value"], 0, key)
            self.assertTrue(payload["is_complete"], key)
            self.assertTrue(payload["is_full_dataset"], key)

    def test_ledger_basis_detail_summarizes_period_accounting_moves(self):
        journal = self.env["account.journal"].create(
            {
                "name": "China Fact Ledger Basis Journal",
                "code": "ZCN2",
                "type": "general",
                "company_id": self.company.id,
            }
        )
        sale_journal = self.env["account.journal"].create(
            {
                "name": "China Fact Ledger Basis Sales",
                "code": "ZCN3",
                "type": "sale",
                "company_id": self.company.id,
            }
        )
        posted = self.env["account.move"].with_company(self.company).create(
            {
                "date": "2099-06-01",
                "journal_id": journal.id,
                "company_id": self.company.id,
                "move_type": "entry",
            }
        )
        draft_invoice = self.env["account.move"].with_company(self.company).create(
            {
                "date": "2099-06-05",
                "journal_id": sale_journal.id,
                "company_id": self.company.id,
                "move_type": "out_invoice",
            }
        )
        self.env.cr.execute(
            "UPDATE account_move SET state = 'posted' WHERE id = %s",
            (posted.id,),
        )
        posted.invalidate_recordset(["state"])

        payload = self._provider("cn.account.ledger_basis_detail")(
            self.assessment,
            False,
        )
        value = payload["value"]

        self.assertEqual(value["schema"], "sdoo.cn.accounting-ledger-basis.v1")
        self.assertEqual(value["counts"]["total_moves"], 2)
        self.assertEqual(value["counts"]["posted_moves"], 1)
        self.assertEqual(value["counts"]["draft_moves"], 1)
        self.assertEqual(value["counts"]["posted_invoices"], 0)
        self.assertEqual(value["date_coverage"]["first_move_date"], "2099-06-01")
        self.assertEqual(value["date_coverage"]["last_move_date"], "2099-06-05")
        self.assertEqual(value["move_type_counts"]["entry"], 1)
        self.assertEqual(value["move_type_counts"]["out_invoice"], 1)
        self.assertIn(posted.id, payload["source_record_ids"])
        self.assertIn(draft_invoice.id, payload["source_record_ids"])

    def test_reconciliation_facts_require_an_exact_period_current_result(self):
        for key in (
            "cn.reconciliation.einvoice.source_state",
            "cn.reconciliation.vat.conclusion_state",
        ):
            payload = self._provider(key)(self.assessment, False)
            self.assertIsNone(payload["value"], key)
            self.assertEqual(payload["quality_state"], "missing", key)
            self.assertFalse(payload["is_complete"], key)
            self.assertFalse(payload["is_full_dataset"], key)
