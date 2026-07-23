import hashlib
import json
from unittest.mock import patch

from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.sudo_country_pack_cn.models.reconciliation_source_monitoring import (
    SudoChinaCitPeriodReconciliationSourceMonitor,
)
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import new_test_user, tagged


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
        cls.filing_source_approver = cls.env["res.users"].create(
            {
                "name": "China CIT Filing Source Approver",
                "login": "cn_cit_filing_source_approver",
                "company_id": cls.company.id,
                "company_ids": [Command.set(cls.company.ids)],
                "group_ids": [Command.set(manager_group.ids)],
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

    def _valid_filing_authority_source(self, suffix):
        attachment = self._attachment(
            f"official-cit-filing-deadline-{suffix}.pdf",
            f"official CIT filing deadline source {suffix}".encode(),
        )
        source = self.env["sudo.compliance.authority.source"].with_user(
            self.reviewer
        ).create(
            {
                "name": f"企业所得税申报期限官方依据 {suffix}",
                "country_id": self.country.id,
                "authority": "国家税务总局",
                "source_type": "form_instruction",
                "official_url": "https://www.chinatax.gov.cn/",
                "official_version": f"TEST-{suffix}",
                "published_date": "2026-01-01",
                "next_review_date": "2027-12-31",
                "snapshot_kind": "official_document",
                "snapshot_attachment_id": attachment.id,
            }
        )
        source.with_user(self.reviewer).action_compute_hash()
        source.with_user(self.reviewer).action_submit_review()
        source.with_user(self.filing_source_approver).action_approve()
        return source

    def _controlled_filing_archive(self, run, suffix):
        action = run.with_user(self.reviewer).action_open_cn_filing_archive()
        defaults = {
            key.removeprefix("default_"): value
            for key, value in action["context"].items()
            if key.startswith("default_")
        }
        source = self._valid_filing_authority_source(suffix)
        obligation = self.env["sudo.compliance.obligation"].browse(
            defaults["obligation_id"]
        )
        obligation.write(
            {
                "applicability": "applicable",
                "effective_from": "2026-01-01",
                "authority_source_id": source.id,
                "justification": (
                    "依据已复核官方资料和测试公司所得税申报身份，"
                    "确认当前期间适用企业所得税申报义务。"
                ),
            }
        )
        defaults.update(
            {
                "due_date": "2026-07-15",
                "authority_source_id": source.id,
                "due_date_basis": (
                    "依据已复核官方资料、来源申报类型和测试期间，"
                    "人工确认本期截止日；未由系统自动推断。"
                ),
            }
        )
        return self.env["sudo.compliance.filing"].with_user(
            self.reviewer
        ).with_company(self.company).create(defaults)

    def _verified_filing_evidence(self, filing, suffix, evidence_type):
        evidence = self.env["sudo.compliance.evidence"].with_user(
            self.reader
        ).with_company(self.company).create(
            {
                "name": f"企业所得税受控档案证据 {suffix}",
                "company_id": self.company.id,
                "filing_id": filing.id,
                "evidence_type": evidence_type,
                "external_reference": (
                    f"TEST-CIT-ARCHIVE/{suffix}; 保管人=测试合规管理员; "
                    "访问方式=受控测试索引; 保留期限=测试期间"
                ),
                "evidence_date": "2026-07-15",
                "issuer": "测试主管税务机关",
            }
        )
        evidence.with_user(self.reader).action_submit()
        evidence.with_user(self.reviewer).write(
            {"review_notes": "已与受控企业所得税申报或缴退税来源逐项核对。"}
        )
        evidence.with_user(self.reviewer).action_verify()
        return evidence

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

    def _activate_cit_reconciliation_test_rule(self):
        author = new_test_user(
            self.env,
            login="cn_cit_bridge_rule_author",
            groups=(
                "base.group_user,"
                "sudo_global_finance.group_compliance_rule_author"
            ),
            company_id=self.company.id,
            company_ids=[self.company.id],
        )
        approver = new_test_user(
            self.env,
            login="cn_cit_bridge_rule_approver",
            groups=(
                "base.group_user,"
                "sudo_global_finance.group_compliance_rule_approver"
            ),
            company_id=self.company.id,
            company_ids=[self.company.id],
        )
        professional = new_test_user(
            self.env,
            login="cn_cit_bridge_professional_reviewer",
            groups=(
                "base.group_user,"
                "sudo_global_finance.group_compliance_professional_reviewer"
            ),
            company_id=self.company.id,
            company_ids=[self.company.id],
        )
        source = self.env[
            "sudo.compliance.authority.source"
        ].with_user(author).create(
            {
                "name": "中国企业所得税勾稽闭环测试受控来源",
                "country_id": self.country.id,
                "authority": "测试主管税务机关",
                "source_type": "tax_guide",
                "snapshot_kind": "official_web_capture",
                "official_url": (
                    "https://example.test/cn-cit-reconciliation-control"
                ),
                "official_version": "TEST-2026.1",
                "published_date": "2026-01-01",
                "next_review_date": "2027-07-16",
            }
        )
        attachment = self.env["ir.attachment"].with_user(author).create(
            {
                "name": "cn-cit-reconciliation-test-source.html",
                "raw": b"Controlled China CIT reconciliation test source",
                "mimetype": "text/html",
                "res_model": source._name,
                "res_id": source.id,
            }
        )
        source.with_user(author).write(
            {"snapshot_attachment_id": attachment.id}
        )
        source.with_user(author).action_compute_hash()
        source.with_user(author).action_submit_review()
        source.with_user(approver).action_approve()

        fact_definitions = self.env[
            "sudo.compliance.fact.definition"
        ].browse(
            [
                self.env.ref(
                    "sudo_country_pack_cn."
                    "fact_cn_cit_reconciliation_conclusion_state_v1"
                ).id,
                self.env.ref(
                    "sudo_country_pack_cn."
                    "fact_cn_cit_reconciliation_blocking_count_v1"
                ).id,
                self.env.ref(
                    "sudo_country_pack_cn."
                    "fact_cn_cit_reconciliation_difference_count_v1"
                ).id,
                self.env.ref(
                    "sudo_country_pack_cn."
                    "fact_cn_cit_reconciliation_warning_count_v1"
                ).id,
                self.env.ref(
                    "sudo_country_pack_cn."
                    "fact_cn_cit_reconciliation_detail_v1"
                ).id,
            ]
        )
        rule = self.env["sudo.compliance.rule"].with_user(author).create(
            {
                "name": "中国企业所得税勾稽闭环运行时测试规则",
                "code": "CN-TEST-CIT-RECON-E2E",
                "country_id": self.country.id,
                "domain_key": "CN.CIT.TEST",
                "cn_rule_nature": "internal_control",
                "description": "仅用于运行时验证三态规则扫描与整改复扫闭环。",
            }
        )
        version = self.env[
            "sudo.compliance.rule.version"
        ].with_user(author).create(
            {
                "rule_id": rule.id,
                "version": "TEST-2026.1",
                "effective_from": "2026-01-01",
                "next_review_date": "2027-07-16",
                "evaluator_type": "handler",
                "handler_key": "cn.cit.reconciliation.review.v1",
                "handler_version": "1",
                "risk_level": "high",
                "stale_policy": "block_all",
                "authority_source_ids": [Command.set(source.ids)],
                "required_fact_ids": [Command.set(fact_definitions.ids)],
                "legal_basis_summary": "受控运行时测试来源。",
                "failure_message": "企业所得税勾稽存在待复核差异。",
                "pass_message": "企业所得税勾稽在测试范围内一致。",
                "unknown_message": "数据不可比较或仍有复核提示。",
                "recommended_actions": "补齐来源并重新执行企业所得税勾稽。",
                "evidence_required": "受控来源、差异调节和复核证据。",
                "requires_human_review": True,
            }
        )
        packet = self.env["sudo.cn.rule.review.packet"].with_user(
            author
        ).create(
            {
                "rule_version_id": version.id,
                "scope_summary": "仅验证企业所得税勾稽运行时测试期间。",
                "applicability_assumptions": "测试来源和事实定义完整。",
                "exclusions_limitations": "不构成真实中国税务结论。",
                "conclusion_boundary": "仅验证系统治理闭环。",
                "reviewer_questions": "确认测试载荷和三态结论边界。",
            }
        )
        self.env["sudo.cn.rule.review.citation"].with_user(author).create(
            {
                "packet_id": packet.id,
                "source_id": source.id,
                "citation_type": "internal_control_rationale",
                "locator": "运行时测试来源",
                "claim_summary": "仅用于验证系统运行时控制。",
                "applicability_note": "不得用于真实财税判断。",
            }
        )
        self.env["sudo.compliance.rule.test.case"].with_user(author).create(
            [
                {
                    "name": "企业所得税勾稽一致",
                    "rule_version_id": version.id,
                    "facts_json": {
                        "cn.reconciliation.cit.conclusion_state": "aligned",
                        "cn.reconciliation.cit.blocking_issue_count": 0,
                        "cn.reconciliation.cit.difference_issue_count": 0,
                        "cn.reconciliation.cit.warning_issue_count": 0,
                        "cn.reconciliation.cit.detail": {},
                    },
                    "evaluation_date": "2026-07-16",
                    "expected_result": "pass",
                },
                {
                    "name": "企业所得税勾稽存在差异",
                    "rule_version_id": version.id,
                    "facts_json": {
                        "cn.reconciliation.cit.conclusion_state": "differences",
                        "cn.reconciliation.cit.blocking_issue_count": 0,
                        "cn.reconciliation.cit.difference_issue_count": 1,
                        "cn.reconciliation.cit.warning_issue_count": 0,
                        "cn.reconciliation.cit.detail": {},
                    },
                    "evaluation_date": "2026-07-16",
                    "expected_result": "fail",
                },
                {
                    "name": "企业所得税勾稽数据不足",
                    "rule_version_id": version.id,
                    "facts_json": {
                        "cn.reconciliation.cit.conclusion_state": (
                            "insufficient_data"
                        ),
                        "cn.reconciliation.cit.blocking_issue_count": 1,
                        "cn.reconciliation.cit.difference_issue_count": 0,
                        "cn.reconciliation.cit.warning_issue_count": 0,
                        "cn.reconciliation.cit.detail": {},
                    },
                    "evaluation_date": "2026-07-16",
                    "expected_result": "unknown",
                },
                {
                    "name": "企业所得税勾稽仍有复核提示",
                    "rule_version_id": version.id,
                    "facts_json": {
                        "cn.reconciliation.cit.conclusion_state": "aligned",
                        "cn.reconciliation.cit.blocking_issue_count": 0,
                        "cn.reconciliation.cit.difference_issue_count": 0,
                        "cn.reconciliation.cit.warning_issue_count": 1,
                        "cn.reconciliation.cit.detail": {},
                    },
                    "evaluation_date": "2026-07-16",
                    "expected_result": "unknown",
                },
            ]
        )
        version.with_user(author).action_run_tests()
        evidence = b"China CIT reconciliation professional test workpaper"
        version.with_user(professional).write(
            {
                "professional_qualification": "中国财税专业测试资质",
                "professional_review_notes": (
                    "仅验证三态规则治理、事实快照和整改闭环。"
                ),
                "professional_evidence_reference": (
                    "TEST/CN/CIT-RECON/%s" % version.id
                ),
                "professional_evidence_checksum": hashlib.sha256(
                    evidence
                ).hexdigest(),
            }
        )
        version.with_user(professional).action_professional_signoff()
        version.with_user(author).action_submit_review()
        version.with_user(approver).action_approve()
        version.with_user(approver).action_activate()
        return version

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

    def test_source_change_monitor_queues_one_recalculation(self):
        run = self._queue()
        self.assertTrue(run.with_user(self.reviewer)._process())
        run.invalidate_recordset()
        self.assertEqual(
            run._cn_current_source_checksums(),
            run._cn_stored_source_checksums(),
        )
        model = self.env[run._name].with_user(self.reviewer).with_company(
            self.company
        )

        with patch.object(
            SudoChinaCitPeriodReconciliationSourceMonitor,
            "_cn_current_source_checksums",
            return_value={"changed": "cit-source"},
        ):
            self.assertEqual(model._cn_monitor_current_results(limit=1), 1)
            self.assertEqual(model._cn_monitor_current_results(limit=1), 0)

        run.invalidate_recordset(["source_checked_at"])
        replacement = model.search(
            [
                ("profile_id", "=", self.profile.id),
                ("period_start", "=", run.period_start),
                ("period_end", "=", run.period_end),
                ("state", "=", "queued"),
            ]
        )
        self.assertTrue(run.source_checked_at)
        self.assertEqual(len(replacement), 1)
        self.assertEqual(run.state, "succeeded")

    def test_reconciliation_snapshot_is_independent_of_ui_language(self):
        self.env["res.lang"]._activate_lang("zh_CN")
        sources = self._seed_complete_sources("locale-stable")
        foreign_company = self.env["res.company"].create(
            {"name": "Foreign CIT execution context"}
        )
        (self.scope_author | self.reviewer).write(
            {"company_ids": [Command.link(foreign_company.id)]}
        )
        (self.scope_author | self.reviewer).invalidate_recordset(
            ["company_ids"]
        )
        account = self.company_data["default_account_revenue"]
        canonical_name = account.with_context(lang="en_US").name
        account.with_context(lang="zh_CN").write(
            {"name": "仅用于测试的中文主营业务收入"}
        )

        self.assertEqual(
            sources["scope"]
            .with_company(foreign_company)
            .with_context(lang="zh_CN")
            ._current_integrity_state(),
            "verified",
        )
        run = self._queue()
        self.assertTrue(
            run.with_user(self.reviewer)
            .with_company(foreign_company)
            .with_context(lang="zh_CN")
            ._process()
        )
        run.invalidate_recordset()

        account_snapshot = next(
            item
            for item in run.accounting_snapshot_json["accounts"]
            if item["account_id"] == account.id
        )
        self.assertEqual(account_snapshot["account_name"], canonical_name)
        self.assertEqual(
            account_snapshot["account_code"],
            account.with_company(self.company).code,
        )
        self.assertEqual(
            run.with_company(foreign_company)
            .with_context(lang="zh_CN")
            ._cn_current_source_checksums(),
            run._cn_stored_source_checksums(),
        )
        model = (
            self.env[run._name]
            .with_user(self.reviewer)
            .with_company(foreign_company)
            .with_context(lang="zh_CN")
        )
        self.assertEqual(model._cn_monitor_current_results(limit=1), 0)

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
        summary = self._fact("cn.reconciliation.cit.risk_summary")

        self.assertEqual(conclusion["value"], "aligned")
        self.assertEqual(conclusion["quality_state"], "complete")
        self.assertEqual(conclusion["source_record_ids"], run.ids)
        self.assertEqual(blocking["value"], 0)
        self.assertEqual(detail["value"]["run_id"], run.id)
        self.assertEqual(
            detail["value"]["checksums"]["result"], run.result_checksum
        )
        self.assertEqual(
            summary["value"]["schema"],
            "sdoo.cn.reconciliation.cit-risk-summary.v1",
        )
        self.assertEqual(summary["value"]["risk_status"], "aligned")
        self.assertEqual(
            summary["value"]["next_action"],
            "retain_cit_snapshots_and_continue_monitoring",
        )
        self.assertEqual(
            summary["value"]["checksums"]["result"], run.result_checksum
        )
        self.assertIn(
            "ledger_accounting_profit_amount",
            summary["value"]["amounts"],
        )
        self.assertIn("filing_payable_amount", summary["value"]["amounts"])
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

    def test_cit_reconciliation_drives_remediation_and_exact_period_rescan(self):
        self.profile._write_import({"status": "active"})
        version = self._activate_cit_reconciliation_test_rule()
        initial_run = self._queue()
        self.assertTrue(initial_run.with_user(self.reviewer)._process())
        self.assertEqual(initial_run.conclusion_state, "insufficient_data")

        assessment_action = initial_run.with_user(
            self.reviewer
        ).action_queue_compliance_assessment()
        assessment = self.env["sudo.compliance.assessment"].browse(
            assessment_action["res_id"]
        )
        self.assertEqual(assessment.state, "queued")
        self.assertEqual(assessment.period_start.isoformat(), "2026-06-01")
        self.assertEqual(assessment.period_end.isoformat(), "2026-06-30")
        self.assertEqual(assessment.rule_version_ids, version)

        assessment.with_user(self.reviewer).action_run_now()
        finding = assessment.finding_ids
        self.assertEqual(finding.result, "unknown")
        self.assertEqual(finding.cn_rule_nature, "internal_control")
        self.assertEqual(
            finding.result_details_json["reason"],
            "data_not_comparable",
        )
        self.assertFalse(finding.source_warning)
        self.assertFalse(finding.professional_warning)
        snapshots = {
            snapshot.definition_id.key: snapshot
            for snapshot in finding.fact_snapshot_ids
        }
        self.assertEqual(
            snapshots[
                "cn.reconciliation.cit.conclusion_state"
            ].source_record_ids_json,
            initial_run.ids,
        )
        self.assertEqual(
            snapshots[
                "cn.reconciliation.cit.blocking_issue_count"
            ].value_json,
            initial_run.blocking_issue_count,
        )

        finding.with_user(self.reviewer).write(
            {
                "review_notes": (
                    "已核对企业所得税勾稽数据阻断和三态规则边界，确认需要"
                    "补齐受控来源并建立整改任务。"
                )
            }
        )
        finding.with_user(self.reviewer).action_require_correction()
        impact_action = finding.with_user(
            self.reviewer
        ).action_create_cn_tax_impact_case()
        self.assertEqual(impact_action["view_mode"], "form")
        self.assertEqual(
            impact_action["context"]["default_assessment_id"],
            assessment.id,
        )

        task_action = finding.with_user(self.reviewer).action_create_task()
        task = self.env["sudo.compliance.task"].browse(task_action["res_id"])
        task.with_user(self.reviewer).write(
            {
                "completion_notes": (
                    "已补齐受控损益口径、企业所得税申报和缴税来源并重新勾稽。"
                ),
                "external_evidence_reference": (
                    "TEST/CN/CIT-REMEDIATION/2026-06"
                ),
            }
        )
        task.with_user(self.reviewer).action_done()
        self.assertEqual(task.state, "pending_review")
        self.assertEqual(task.verification_state, "pending_rescan")

        self._seed_complete_sources("compliance-remediated")
        replacement_run = self._queue()
        self.assertTrue(replacement_run.with_user(self.reviewer)._process())
        self.assertEqual(replacement_run.conclusion_state, "aligned")
        initial_run.invalidate_recordset(["state"])
        self.assertEqual(initial_run.state, "superseded")

        verification_action = task.with_user(
            self.reviewer
        ).action_queue_verification_scan()
        verification = self.env["sudo.compliance.assessment"].browse(
            verification_action["res_id"]
        )
        self.assertEqual(verification.period_start, assessment.period_start)
        self.assertEqual(verification.period_end, assessment.period_end)
        self.assertEqual(verification.rule_version_ids, version)
        verification.with_user(self.reviewer).action_run_now()
        self.assertEqual(verification.finding_ids.result, "pass")
        self.assertEqual(
            verification.fact_snapshot_ids.filtered(
                lambda snapshot: snapshot.definition_id.key
                == "cn.reconciliation.cit.conclusion_state"
            ).source_record_ids_json,
            replacement_run.ids,
        )

        evidence = self.env["sudo.compliance.evidence"].with_user(
            self.reviewer
        ).create(
            {
                "name": "企业所得税勾稽整改验证证据",
                "company_id": self.company.id,
                "task_id": task.id,
                "evidence_type": "remediation_proof",
                "external_reference": (
                    "TEST/CN/CIT-REMEDIATION/VERIFIED-2026-06"
                ),
            }
        )
        evidence.with_user(self.reviewer).action_submit()
        evidence.with_user(self.reviewer).review_notes = (
            "已核对替代批次、精确期间、来源范围和结果校验和。"
        )
        evidence.with_user(self.reviewer).action_verify()
        task.with_user(self.reviewer).action_verify_remediation()

        self.assertEqual(task.state, "done")
        self.assertEqual(task.verification_state, "verified")
        self.assertEqual(task.verification_assessment_id, verification)
        self.assertEqual(task.verification_finding_id.result, "pass")
        event = self.env["sudo.compliance.audit.event"].search(
            [
                ("model_name", "=", task._name),
                ("record_id", "=", task.id),
                ("event_key", "=", "task.verification_scan_queued"),
            ],
            order="id desc",
            limit=1,
        )
        self.assertEqual(
            event.details_json["scope"],
            "cn_reconciliation_exact_period",
        )

    def test_filing_archive_action_does_not_infer_legal_deadline(self):
        self._seed_complete_sources("cit-archive-no-inference")
        run = self._queue()
        self.assertTrue(run.with_user(self.reviewer)._process())

        action = run.with_user(self.reviewer).action_open_cn_filing_archive()

        self.assertEqual(action["res_model"], "sudo.compliance.filing")
        self.assertEqual(
            action["context"]["default_cn_cit_reconciliation_run_id"],
            run.id,
        )
        self.assertNotIn("default_due_date", action["context"])
        self.assertNotIn("default_authority_source_id", action["context"])
        self.assertNotIn("default_due_date_basis", action["context"])

    def test_cit_payable_archive_seals_submission_and_payment_chain(self):
        self._seed_complete_sources("cit-archive-payable")
        run = self._queue()
        self.assertTrue(run.with_user(self.reviewer)._process())
        filing = self._controlled_filing_archive(run, "cit-archive-payable")
        receipt = self._verified_filing_evidence(
            filing,
            "cit-archive-payable-receipt",
            "filing_receipt",
        )

        filing.with_user(self.reviewer).action_prepare()
        filing.with_user(self.reviewer).action_ready()
        filing.with_user(self.reviewer).action_submit()
        filing.invalidate_recordset()

        self.assertEqual(filing.state, "submitted")
        self.assertEqual(filing.cn_cit_settlement_kind, "payable")
        self.assertEqual(filing.cn_submission_evidence_ids, receipt)
        self.assertEqual(filing.cn_submission_integrity_state, "verified")
        self.assertEqual(
            filing.cn_submission_snapshot_json["schema"],
            "sdoo.cn.cit-filing-archive.v1",
        )
        self.assertEqual(
            filing.cn_submission_snapshot_json["reconciliation"]["run_id"],
            run.id,
        )

        payment_evidence = self._verified_filing_evidence(
            filing,
            "cit-archive-payable-proof",
            "payment_proof",
        )
        filing.with_user(self.reviewer).action_mark_paid()
        filing.invalidate_recordset()

        self.assertEqual(filing.payment_state, "paid")
        self.assertEqual(filing.cn_payment_evidence_ids, payment_evidence)
        self.assertEqual(filing.cn_payment_integrity_state, "verified")
        self.assertEqual(
            filing.cn_payment_snapshot_json["schema"],
            "sdoo.cn.cit-settlement-archive.v1",
        )
        self.assertEqual(
            filing.cn_payment_snapshot_json["settlement_kind"],
            "payable",
        )
        self.assertEqual(
            filing.cn_cit_effective_paid_principal_amount,
            run.effective_paid_principal_amount,
        )
        reopened = run.with_user(self.reviewer).action_open_cn_filing_archive()
        self.assertEqual(reopened["res_id"], filing.id)
        run.invalidate_recordset(["filing_archive_count"])
        self.assertEqual(run.filing_archive_count, 1)
        event_keys = self.env["sudo.compliance.audit.event"].search(
            [
                ("model_name", "=", filing._name),
                ("record_id", "=", filing.id),
            ]
        ).mapped("event_key")
        self.assertIn("cn.cit_filing_archive.sealed", event_keys)
        self.assertIn("cn.cit_payment_archive.sealed", event_keys)

    def test_cit_refund_archive_keeps_refund_distinct_from_payment(self):
        filing_values = self._cit_filing(
            "cit-archive-refund",
            payable=0.0,
            refundable=18.0,
        )
        refund_values = self._payment(
            "cit-archive-refund",
            amount=18.0,
            status="refunded",
        )
        self._seed_complete_sources(
            "cit-archive-refund",
            filing_values=filing_values,
            payment_values=refund_values,
        )
        run = self._queue()
        self.assertTrue(run.with_user(self.reviewer)._process())
        filing = self._controlled_filing_archive(run, "cit-archive-refund")
        self._verified_filing_evidence(
            filing,
            "cit-archive-refund-receipt",
            "filing_receipt",
        )
        filing.with_user(self.reviewer).action_prepare()
        filing.with_user(self.reviewer).action_ready()
        filing.with_user(self.reviewer).action_submit()
        refund_evidence = self._verified_filing_evidence(
            filing,
            "cit-archive-refund-proof",
            "refund_receipt",
        )

        filing.with_user(self.reviewer).action_seal_cn_cit_refund()
        filing.invalidate_recordset()

        self.assertEqual(filing.cn_cit_settlement_kind, "refund")
        self.assertFalse(filing.payment_required)
        self.assertEqual(filing.payment_state, "not_required")
        self.assertEqual(filing.cn_payment_evidence_ids, refund_evidence)
        self.assertEqual(filing.cn_payment_integrity_state, "verified")
        self.assertEqual(
            filing.cn_payment_snapshot_json["settlement_kind"],
            "refund",
        )
        self.assertEqual(
            filing.cn_cit_refunded_principal_amount,
            run.refunded_principal_amount,
        )
        with self.assertRaisesRegex(AccessError, "封存后不能修改"):
            filing.write({"cn_cit_refund_reference": "CHANGED"})
        event_keys = self.env["sudo.compliance.audit.event"].search(
            [
                ("model_name", "=", filing._name),
                ("record_id", "=", filing.id),
            ]
        ).mapped("event_key")
        self.assertIn("cn.cit_refund_archive.sealed", event_keys)

    def test_cit_filing_archive_requires_verified_formal_receipt(self):
        self._seed_complete_sources("cit-archive-no-receipt")
        run = self._queue()
        self.assertTrue(run.with_user(self.reviewer)._process())
        filing = self._controlled_filing_archive(run, "cit-archive-no-receipt")
        filing.with_user(self.reviewer).action_prepare()
        filing.with_user(self.reviewer).action_ready()

        with self.assertRaisesRegex(UserError, "已验证的正式申报回执"):
            filing.with_user(self.reviewer).action_submit()

    def test_cit_filing_archive_blocks_conflicting_settlement_directions(self):
        filing_values = self._cit_filing(
            "cit-archive-conflict",
            payable=12.5,
            refundable=5.0,
        )
        self._seed_complete_sources(
            "cit-archive-conflict",
            filing_values=filing_values,
        )
        run = self._queue()
        self.assertTrue(run.with_user(self.reviewer)._process())
        filing = self._controlled_filing_archive(run, "cit-archive-conflict")
        filing.with_user(self.reviewer).action_prepare()

        self.assertEqual(filing.cn_cit_settlement_kind, "conflict")
        with self.assertRaisesRegex(UserError, "同时存在正数应补和应退"):
            filing.with_user(self.reviewer).action_ready()

    def test_cit_payable_archive_rejects_unreconciled_payment(self):
        filing_values = self._cit_filing(
            "cit-archive-payable-difference",
            payable=20.0,
        )
        self._seed_complete_sources(
            "cit-archive-payable-difference",
            filing_values=filing_values,
        )
        run = self._queue()
        self.assertTrue(run.with_user(self.reviewer)._process())
        filing = self._controlled_filing_archive(
            run,
            "cit-archive-payable-difference",
        )
        self._verified_filing_evidence(
            filing,
            "cit-archive-payable-difference-receipt",
            "filing_receipt",
        )
        filing.with_user(self.reviewer).action_prepare()
        filing.with_user(self.reviewer).action_ready()
        filing.with_user(self.reviewer).action_submit()
        self._verified_filing_evidence(
            filing,
            "cit-archive-payable-difference-proof",
            "payment_proof",
        )

        with self.assertRaisesRegex(UserError, "尚未勾稽一致"):
            filing.with_user(self.reviewer).action_mark_paid()

    def test_cit_refund_archive_rejects_unreconciled_refund(self):
        filing_values = self._cit_filing(
            "cit-archive-refund-difference",
            payable=0.0,
            refundable=20.0,
        )
        refund_values = self._payment(
            "cit-archive-refund-difference",
            amount=12.5,
            status="refunded",
        )
        self._seed_complete_sources(
            "cit-archive-refund-difference",
            filing_values=filing_values,
            payment_values=refund_values,
        )
        run = self._queue()
        self.assertTrue(run.with_user(self.reviewer)._process())
        filing = self._controlled_filing_archive(
            run,
            "cit-archive-refund-difference",
        )
        self._verified_filing_evidence(
            filing,
            "cit-archive-refund-difference-receipt",
            "filing_receipt",
        )
        filing.with_user(self.reviewer).action_prepare()
        filing.with_user(self.reviewer).action_ready()
        filing.with_user(self.reviewer).action_submit()
        self._verified_filing_evidence(
            filing,
            "cit-archive-refund-difference-proof",
            "refund_receipt",
        )

        with self.assertRaisesRegex(UserError, "尚未勾稽一致"):
            filing.with_user(self.reviewer).action_seal_cn_cit_refund()

    def test_cit_filing_archive_detects_reconciliation_tampering(self):
        self._seed_complete_sources("cit-archive-tampering")
        run = self._queue()
        self.assertTrue(run.with_user(self.reviewer)._process())
        filing = self._controlled_filing_archive(run, "cit-archive-tampering")
        self._verified_filing_evidence(
            filing,
            "cit-archive-tampering-receipt",
            "filing_receipt",
        )
        filing.with_user(self.reviewer).action_prepare()
        filing.with_user(self.reviewer).action_ready()
        filing.with_user(self.reviewer).action_submit()
        self.assertEqual(filing.cn_submission_integrity_state, "verified")

        self.env.cr.execute(
            """
            UPDATE sudo_cn_cit_period_reconciliation_run
               SET result_checksum = %s
             WHERE id = %s
            """,
            ["0" * 64, run.id],
        )
        run.invalidate_recordset(["result_checksum"])
        filing.invalidate_recordset(["cn_submission_integrity_state"])
        self.assertEqual(filing.cn_submission_integrity_state, "changed")

    def test_cit_filing_archive_rejects_cross_company_reconciliation(self):
        other_company = self.env["res.company"].create(
            {
                "name": "Other China CIT Filing Company",
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
        self.reviewer.write(
            {"company_ids": [Command.link(other_company.id)]}
        )
        other_run = self.env[
            "sudo.cn.cit.period.reconciliation.run"
        ].with_user(self.reviewer).with_company(other_company).enqueue(
            other_profile,
            "2026-06-01",
            "2026-06-30",
            "quarterly_prepayment",
            "CIT",
        )
        source = self._valid_filing_authority_source(
            "cit-archive-cross-company"
        )
        obligation = self.profile.obligation_ids.filtered(
            lambda item: item.code == "CN-CIT"
        )[:1]

        with self.assertRaisesRegex(
            ValidationError,
            "当前公司和合规档案",
        ):
            self.env["sudo.compliance.filing"].with_company(self.company).create(
                {
                    "filing_name": "Cross-company CIT filing",
                    "profile_id": self.profile.id,
                    "obligation_id": obligation.id,
                    "filing_code": "CN-CIT",
                    "filing_type": "cn_cit_return",
                    "authority": "主管税务机关",
                    "period_start": "2026-06-01",
                    "period_end": "2026-06-30",
                    "due_date": "2026-07-15",
                    "authority_source_id": source.id,
                    "due_date_basis": "人工确认测试期间截止日。",
                    "assignee_id": self.reviewer.id,
                    "payment_required": True,
                    "cn_cit_reconciliation_run_id": other_run.id,
                }
            )

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
