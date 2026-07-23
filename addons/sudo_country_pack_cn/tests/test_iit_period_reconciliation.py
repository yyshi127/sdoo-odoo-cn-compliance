import hashlib
import json
from unittest.mock import patch

from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.sudo_country_pack_cn.models.reconciliation_source_monitoring import (
    SudoChinaIitPeriodReconciliationSourceMonitor,
)
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import new_test_user, tagged


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
        cls.filing_source_approver = cls.env["res.users"].create(
            {
                "name": "China IIT Filing Source Approver",
                "login": "cn_iit_filing_source_approver",
                "company_id": cls.company.id,
                "company_ids": [Command.set(cls.company.ids)],
                "group_ids": [Command.set(manager_group.ids)],
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
        provider = self.env[
            "sudo.compliance.engine"
        ]._fact_provider_registry()[key]
        return provider(assessment, False)

    def _valid_filing_authority_source(self, suffix):
        attachment = self._attachment(
            f"official-iit-filing-deadline-{suffix}.pdf",
            f"official IIT filing deadline source {suffix}".encode(),
        )
        source = self.env["sudo.compliance.authority.source"].with_user(
            self.reviewer
        ).create(
            {
                "name": f"个人所得税扣缴申报期限官方依据 {suffix}",
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
                    "依据已复核官方资料和测试公司扣缴义务，"
                    "确认当前期间适用个人所得税扣缴申报义务。"
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
                "name": f"个人所得税受控档案证据 {suffix}",
                "company_id": self.company.id,
                "filing_id": filing.id,
                "evidence_type": evidence_type,
                "external_reference": (
                    f"TEST-IIT-ARCHIVE/{suffix}; 保管人=测试合规管理员; "
                    "访问方式=受控测试索引; 保留期限=测试期间"
                ),
                "evidence_date": "2026-07-15",
                "issuer": "测试主管税务机关",
            }
        )
        evidence.with_user(self.reader).action_submit()
        evidence.with_user(self.reviewer).write(
            {"review_notes": "已与受控个人所得税申报或缴退税来源逐项核对。"}
        )
        evidence.with_user(self.reviewer).action_verify()
        return evidence

    def _activate_iit_reconciliation_test_rule(self):
        author = new_test_user(
            self.env,
            login="cn_iit_bridge_rule_author",
            groups=(
                "base.group_user,"
                "sudo_global_finance.group_compliance_rule_author"
            ),
            company_id=self.company.id,
            company_ids=[self.company.id],
        )
        approver = new_test_user(
            self.env,
            login="cn_iit_bridge_rule_approver",
            groups=(
                "base.group_user,"
                "sudo_global_finance.group_compliance_rule_approver"
            ),
            company_id=self.company.id,
            company_ids=[self.company.id],
        )
        professional = new_test_user(
            self.env,
            login="cn_iit_bridge_professional_reviewer",
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
                "name": "中国个人所得税勾稽闭环测试受控来源",
                "country_id": self.country.id,
                "authority": "测试主管税务机关",
                "source_type": "tax_guide",
                "snapshot_kind": "official_web_capture",
                "official_url": (
                    "https://example.test/cn-iit-reconciliation-control"
                ),
                "official_version": "TEST-2026.1",
                "published_date": "2026-01-01",
                "next_review_date": "2027-07-16",
            }
        )
        attachment = self.env["ir.attachment"].with_user(author).create(
            {
                "name": "cn-iit-reconciliation-test-source.html",
                "raw": b"Controlled China IIT reconciliation test source",
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
                    "fact_cn_iit_reconciliation_conclusion_state_v1"
                ).id,
                self.env.ref(
                    "sudo_country_pack_cn."
                    "fact_cn_iit_reconciliation_blocking_count_v1"
                ).id,
                self.env.ref(
                    "sudo_country_pack_cn."
                    "fact_cn_iit_reconciliation_difference_count_v1"
                ).id,
                self.env.ref(
                    "sudo_country_pack_cn."
                    "fact_cn_iit_reconciliation_warning_count_v1"
                ).id,
                self.env.ref(
                    "sudo_country_pack_cn."
                    "fact_cn_iit_reconciliation_detail_v1"
                ).id,
            ]
        )
        rule = self.env["sudo.compliance.rule"].with_user(author).create(
            {
                "name": "中国个人所得税勾稽闭环运行时测试规则",
                "code": "CN-TEST-IIT-RECON-E2E",
                "country_id": self.country.id,
                "domain_key": "CN.PAYROLL_IIT.TEST",
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
                "handler_key": "cn.iit.reconciliation.review.v1",
                "handler_version": "1",
                "risk_level": "high",
                "stale_policy": "block_all",
                "authority_source_ids": [Command.set(source.ids)],
                "required_fact_ids": [Command.set(fact_definitions.ids)],
                "legal_basis_summary": "受控运行时测试来源。",
                "failure_message": "个人所得税勾稽存在待复核差异。",
                "pass_message": "个人所得税勾稽在测试范围内一致。",
                "unknown_message": "数据不可比较或仍有复核提示。",
                "recommended_actions": "补齐来源并重新执行个税勾稽。",
                "evidence_required": "受控来源、差异调节和复核证据。",
                "requires_human_review": True,
            }
        )
        packet = self.env["sudo.cn.rule.review.packet"].with_user(
            author
        ).create(
            {
                "rule_version_id": version.id,
                "scope_summary": "仅验证个人所得税勾稽运行时测试期间。",
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
                    "name": "个人所得税勾稽一致",
                    "rule_version_id": version.id,
                    "facts_json": {
                        "cn.reconciliation.iit.conclusion_state": "aligned",
                        "cn.reconciliation.iit.blocking_issue_count": 0,
                        "cn.reconciliation.iit.difference_issue_count": 0,
                        "cn.reconciliation.iit.warning_issue_count": 0,
                        "cn.reconciliation.iit.detail": {},
                    },
                    "evaluation_date": "2026-07-16",
                    "expected_result": "pass",
                },
                {
                    "name": "个人所得税勾稽存在差异",
                    "rule_version_id": version.id,
                    "facts_json": {
                        "cn.reconciliation.iit.conclusion_state": "differences",
                        "cn.reconciliation.iit.blocking_issue_count": 0,
                        "cn.reconciliation.iit.difference_issue_count": 1,
                        "cn.reconciliation.iit.warning_issue_count": 0,
                        "cn.reconciliation.iit.detail": {},
                    },
                    "evaluation_date": "2026-07-16",
                    "expected_result": "fail",
                },
                {
                    "name": "个人所得税勾稽数据不足",
                    "rule_version_id": version.id,
                    "facts_json": {
                        "cn.reconciliation.iit.conclusion_state": (
                            "insufficient_data"
                        ),
                        "cn.reconciliation.iit.blocking_issue_count": 1,
                        "cn.reconciliation.iit.difference_issue_count": 0,
                        "cn.reconciliation.iit.warning_issue_count": 0,
                        "cn.reconciliation.iit.detail": {},
                    },
                    "evaluation_date": "2026-07-16",
                    "expected_result": "unknown",
                },
                {
                    "name": "个人所得税勾稽仍有复核提示",
                    "rule_version_id": version.id,
                    "facts_json": {
                        "cn.reconciliation.iit.conclusion_state": "aligned",
                        "cn.reconciliation.iit.blocking_issue_count": 0,
                        "cn.reconciliation.iit.difference_issue_count": 0,
                        "cn.reconciliation.iit.warning_issue_count": 1,
                        "cn.reconciliation.iit.detail": {},
                    },
                    "evaluation_date": "2026-07-16",
                    "expected_result": "unknown",
                },
            ]
        )
        version.with_user(author).action_run_tests()
        evidence = b"China IIT reconciliation professional test workpaper"
        version.with_user(professional).write(
            {
                "professional_qualification": "中国财税专业测试资质",
                "professional_review_notes": (
                    "仅验证三态规则治理、事实快照和整改闭环。"
                ),
                "professional_evidence_reference": (
                    "TEST/CN/IIT-RECON/%s" % version.id
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
            SudoChinaIitPeriodReconciliationSourceMonitor,
            "_cn_current_source_checksums",
            return_value={"changed": "iit-source"},
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
            {"name": "Foreign IIT execution context"}
        )
        self.reviewer.write(
            {"company_ids": [Command.link(foreign_company.id)]}
        )
        account = self.company_data["default_account_expense"]
        canonical_name = account.with_context(lang="en_US").name
        account.with_context(lang="zh_CN").write(
            {"name": "仅用于测试的中文工资费用科目"}
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
        self.assertEqual(run.result_integrity_state, "verified")
        self.assertEqual(
            self._fact("cn.reconciliation.iit.conclusion_state")["value"],
            "insufficient_data",
        )

    def test_fact_provider_exposes_aggregate_exact_period_snapshot(self):
        self._seed_complete_sources("facts")
        run = self._queue()
        self.assertTrue(run.with_user(self.reviewer)._process())

        conclusion = self._fact("cn.reconciliation.iit.conclusion_state")
        blocking = self._fact("cn.reconciliation.iit.blocking_issue_count")
        detail = self._fact("cn.reconciliation.iit.detail")
        summary = self._fact("cn.reconciliation.iit.risk_summary")

        self.assertEqual(conclusion["value"], "aligned")
        self.assertEqual(conclusion["quality_state"], "complete")
        self.assertEqual(conclusion["source_record_ids"], run.ids)
        self.assertEqual(blocking["value"], 0)
        self.assertEqual(detail["value"]["run_id"], run.id)
        self.assertEqual(detail["value"]["counts"]["payroll_persons"], 1)
        self.assertEqual(detail["value"]["counts"]["filing_persons"], 1)
        self.assertEqual(
            detail["value"]["checksums"]["result"], run.result_checksum
        )
        self.assertEqual(
            summary["value"]["schema"],
            "sdoo.cn.reconciliation.iit-risk-summary.v1",
        )
        self.assertEqual(summary["value"]["risk_status"], "aligned")
        self.assertEqual(
            summary["value"]["next_action"],
            "retain_iit_snapshots_and_continue_monitoring",
        )
        self.assertEqual(
            summary["value"]["checksums"]["result"], run.result_checksum
        )
        self.assertIn(
            "payroll_gross_income_amount",
            summary["value"]["amounts"],
        )
        self.assertIn("filing_payable_amount", summary["value"]["amounts"])
        serialized = json.dumps(detail["value"], ensure_ascii=False)
        serialized_summary = json.dumps(summary["value"], ensure_ascii=False)
        for sensitive_key in (
            "subject_key",
            "source_line_key",
            "taxpayer_name",
            "taxpayer_id",
        ):
            self.assertNotIn(sensitive_key, serialized)
            self.assertNotIn(sensitive_key, serialized_summary)
        self.assertIsNone(
            self._fact(
                "cn.reconciliation.iit.conclusion_state",
                self._assessment("2026-05-01", "2026-05-31"),
            )["value"]
        )

        self.env.cr.execute(
            """
            UPDATE sudo_cn_iit_period_reconciliation_run
               SET payroll_gross_income_amount =
                   payroll_gross_income_amount + 1
             WHERE id = %s
            """,
            [run.id],
        )
        run.invalidate_recordset(["payroll_gross_income_amount"])
        with self.assertRaises(UserError):
            self._fact("cn.reconciliation.iit.conclusion_state")

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

    def test_iit_reconciliation_drives_remediation_and_exact_period_rescan(self):
        self.profile._write_import({"status": "active"})
        version = self._activate_iit_reconciliation_test_rule()
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
        snapshot_diagnostics = {
            snapshot.definition_id.key: {
                "quality": snapshot.quality_state,
                "error": snapshot.error_message,
            }
            for snapshot in finding.fact_snapshot_ids
        }
        self.assertEqual(
            finding.result_details_json.get("reason"),
            "data_not_comparable",
            (finding.result_details_json, snapshot_diagnostics),
        )
        self.assertFalse(finding.source_warning)
        self.assertFalse(finding.professional_warning)
        snapshots = {
            snapshot.definition_id.key: snapshot
            for snapshot in finding.fact_snapshot_ids
        }
        self.assertEqual(
            snapshots[
                "cn.reconciliation.iit.conclusion_state"
            ].source_record_ids_json,
            initial_run.ids,
        )
        self.assertEqual(
            snapshots[
                "cn.reconciliation.iit.blocking_issue_count"
            ].value_json,
            initial_run.blocking_issue_count,
        )

        finding.with_user(self.reviewer).write(
            {
                "review_notes": (
                    "已核对个人所得税勾稽数据阻断和三态规则边界，确认需要"
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
                    "已补齐受控工资汇总、个人所得税申报、缴退税和账务口径，"
                    "并重新执行精确期间勾稽。"
                ),
                "external_evidence_reference": (
                    "TEST/CN/IIT-REMEDIATION/2026-06"
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
                == "cn.reconciliation.iit.conclusion_state"
            ).source_record_ids_json,
            replacement_run.ids,
        )

        evidence = self.env["sudo.compliance.evidence"].with_user(
            self.reviewer
        ).create(
            {
                "name": "个人所得税勾稽整改验证证据",
                "company_id": self.company.id,
                "task_id": task.id,
                "evidence_type": "remediation_proof",
                "external_reference": (
                    "TEST/CN/IIT-REMEDIATION/VERIFIED-2026-06"
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
        self._seed_complete_sources("iit-archive-no-inference")
        run = self._queue()
        self.assertTrue(run.with_user(self.reviewer)._process())

        action = run.with_user(self.reviewer).action_open_cn_filing_archive()

        self.assertEqual(action["res_model"], "sudo.compliance.filing")
        self.assertEqual(
            action["context"]["default_cn_iit_reconciliation_run_id"],
            run.id,
        )
        self.assertNotIn("default_due_date", action["context"])
        self.assertNotIn("default_authority_source_id", action["context"])
        self.assertNotIn("default_due_date_basis", action["context"])

    def test_iit_payable_archive_seals_private_submission_and_payment_chain(self):
        self._seed_complete_sources("iit-archive-payable")
        run = self._queue()
        self.assertTrue(run.with_user(self.reviewer)._process())
        filing = self._controlled_filing_archive(run, "iit-archive-payable")
        receipt = self._verified_filing_evidence(
            filing,
            "iit-archive-payable-receipt",
            "filing_receipt",
        )

        filing.with_user(self.reviewer).action_prepare()
        filing.with_user(self.reviewer).action_ready()
        filing.with_user(self.reviewer).action_submit()
        filing.invalidate_recordset()

        self.assertEqual(filing.state, "submitted")
        self.assertEqual(filing.cn_iit_settlement_kind, "payable")
        self.assertEqual(filing.cn_submission_evidence_ids, receipt)
        self.assertEqual(filing.cn_submission_integrity_state, "verified")
        snapshot = filing.cn_submission_snapshot_json
        self.assertEqual(
            snapshot["schema"],
            "sdoo.cn.iit-withholding-filing-archive.v1",
        )
        self.assertEqual(snapshot["reconciliation"]["run_id"], run.id)
        self.assertNotIn("lines", snapshot["filing_record"])
        serialized = json.dumps(snapshot, ensure_ascii=False)
        for sensitive_key in (
            "subject_key",
            "source_line_key",
            "taxpayer_name",
            "taxpayer_id",
        ):
            self.assertNotIn(sensitive_key, serialized)

        payment_evidence = self._verified_filing_evidence(
            filing,
            "iit-archive-payable-proof",
            "payment_proof",
        )
        filing.with_user(self.reviewer).action_mark_paid()
        filing.invalidate_recordset()

        self.assertEqual(filing.payment_state, "paid")
        self.assertEqual(filing.cn_payment_evidence_ids, payment_evidence)
        self.assertEqual(filing.cn_payment_integrity_state, "verified")
        self.assertEqual(
            filing.cn_payment_snapshot_json["schema"],
            "sdoo.cn.iit-withholding-settlement-archive.v1",
        )
        self.assertEqual(
            filing.cn_payment_snapshot_json["settlement_kind"],
            "payable",
        )
        self.assertEqual(
            filing.cn_iit_effective_paid_principal_amount,
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
        self.assertIn("cn.iit_filing_archive.sealed", event_keys)
        self.assertIn("cn.iit_payment_archive.sealed", event_keys)

    def test_iit_refund_archive_keeps_refund_distinct_from_payment(self):
        self._seed_complete_sources(
            "iit-archive-refund",
            filing=self._iit_filing("iit-archive-refund", settlement=-18.0),
            payment=self._payment(
                "iit-archive-refund",
                amount=18.0,
                status="refunded",
            ),
        )
        run = self._queue()
        self.assertTrue(run.with_user(self.reviewer)._process())
        filing = self._controlled_filing_archive(run, "iit-archive-refund")
        self._verified_filing_evidence(
            filing,
            "iit-archive-refund-receipt",
            "filing_receipt",
        )
        filing.with_user(self.reviewer).action_prepare()
        filing.with_user(self.reviewer).action_ready()
        filing.with_user(self.reviewer).action_submit()
        refund_evidence = self._verified_filing_evidence(
            filing,
            "iit-archive-refund-proof",
            "refund_receipt",
        )

        filing.with_user(self.reviewer).action_seal_cn_iit_refund()
        filing.invalidate_recordset()

        self.assertEqual(filing.cn_iit_settlement_kind, "refund")
        self.assertFalse(filing.payment_required)
        self.assertEqual(filing.payment_state, "not_required")
        self.assertEqual(filing.cn_payment_evidence_ids, refund_evidence)
        self.assertEqual(filing.cn_payment_integrity_state, "verified")
        self.assertEqual(
            filing.cn_payment_snapshot_json["settlement_kind"],
            "refund",
        )
        self.assertEqual(
            filing.cn_iit_refunded_principal_amount,
            run.refunded_principal_amount,
        )
        with self.assertRaisesRegex(AccessError, "封存后不能修改"):
            filing.write({"cn_iit_refund_reference": "CHANGED"})
        event_keys = self.env["sudo.compliance.audit.event"].search(
            [
                ("model_name", "=", filing._name),
                ("record_id", "=", filing.id),
            ]
        ).mapped("event_key")
        self.assertIn("cn.iit_refund_archive.sealed", event_keys)

    def test_iit_filing_archive_requires_verified_formal_receipt(self):
        self._seed_complete_sources("iit-archive-no-receipt")
        run = self._queue()
        self.assertTrue(run.with_user(self.reviewer)._process())
        filing = self._controlled_filing_archive(run, "iit-archive-no-receipt")
        filing.with_user(self.reviewer).action_prepare()
        filing.with_user(self.reviewer).action_ready()

        with self.assertRaisesRegex(UserError, "已验证的正式申报回执"):
            filing.with_user(self.reviewer).action_submit()

    def test_iit_filing_archive_blocks_unknown_settlement_direction(self):
        source = self._iit_filing("iit-archive-unknown")
        source.pop("total_payable_refundable_amount")
        self._seed_complete_sources(
            "iit-archive-unknown",
            filing=source,
        )
        run = self._queue()
        self.assertTrue(run.with_user(self.reviewer)._process())
        filing = self._controlled_filing_archive(run, "iit-archive-unknown")
        filing.with_user(self.reviewer).action_prepare()

        self.assertEqual(filing.cn_iit_settlement_kind, "unknown")
        with self.assertRaisesRegex(UserError, "结算方向不能确认"):
            filing.with_user(self.reviewer).action_ready()

    def test_iit_payable_archive_rejects_unreconciled_payment(self):
        self._seed_complete_sources(
            "iit-archive-payable-difference",
            payment=self._payment(
                "iit-archive-payable-difference",
                amount=80.0,
            ),
        )
        run = self._queue()
        self.assertTrue(run.with_user(self.reviewer)._process())
        filing = self._controlled_filing_archive(
            run,
            "iit-archive-payable-difference",
        )
        self._verified_filing_evidence(
            filing,
            "iit-archive-payable-difference-receipt",
            "filing_receipt",
        )
        filing.with_user(self.reviewer).action_prepare()
        filing.with_user(self.reviewer).action_ready()
        filing.with_user(self.reviewer).action_submit()
        self._verified_filing_evidence(
            filing,
            "iit-archive-payable-difference-proof",
            "payment_proof",
        )

        with self.assertRaisesRegex(UserError, "尚未勾稽一致"):
            filing.with_user(self.reviewer).action_mark_paid()

    def test_iit_refund_archive_rejects_unreconciled_refund(self):
        self._seed_complete_sources(
            "iit-archive-refund-difference",
            filing=self._iit_filing(
                "iit-archive-refund-difference",
                settlement=-20.0,
            ),
            payment=self._payment(
                "iit-archive-refund-difference",
                amount=12.5,
                status="refunded",
            ),
        )
        run = self._queue()
        self.assertTrue(run.with_user(self.reviewer)._process())
        filing = self._controlled_filing_archive(
            run,
            "iit-archive-refund-difference",
        )
        self._verified_filing_evidence(
            filing,
            "iit-archive-refund-difference-receipt",
            "filing_receipt",
        )
        filing.with_user(self.reviewer).action_prepare()
        filing.with_user(self.reviewer).action_ready()
        filing.with_user(self.reviewer).action_submit()
        self._verified_filing_evidence(
            filing,
            "iit-archive-refund-difference-proof",
            "refund_receipt",
        )

        with self.assertRaisesRegex(UserError, "尚未勾稽一致"):
            filing.with_user(self.reviewer).action_seal_cn_iit_refund()

    def test_iit_filing_archive_detects_reconciliation_tampering(self):
        self._seed_complete_sources("iit-archive-tampering")
        run = self._queue()
        self.assertTrue(run.with_user(self.reviewer)._process())
        filing = self._controlled_filing_archive(run, "iit-archive-tampering")
        self._verified_filing_evidence(
            filing,
            "iit-archive-tampering-receipt",
            "filing_receipt",
        )
        filing.with_user(self.reviewer).action_prepare()
        filing.with_user(self.reviewer).action_ready()
        filing.with_user(self.reviewer).action_submit()
        self.assertEqual(filing.cn_submission_integrity_state, "verified")

        self.env.cr.execute(
            """
            UPDATE sudo_cn_iit_period_reconciliation_run
               SET result_checksum = %s
             WHERE id = %s
            """,
            ["0" * 64, run.id],
        )
        run.invalidate_recordset(["result_checksum"])
        filing.invalidate_recordset(["cn_submission_integrity_state"])
        self.assertEqual(filing.cn_submission_integrity_state, "changed")

    def test_iit_filing_archive_rejects_cross_company_reconciliation(self):
        other_company = self.env["res.company"].create(
            {
                "name": "Other China IIT Filing Company",
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
            "sudo.cn.iit.period.reconciliation.run"
        ].with_user(self.reviewer).with_company(other_company).enqueue(
            other_profile,
            "2026-06-01",
            "2026-06-30",
            "IIT",
        )
        source = self._valid_filing_authority_source(
            "iit-archive-cross-company"
        )
        obligation = self.profile.obligation_ids.filtered(
            lambda item: item.code == "CN-IIT-WHT"
        )[:1]

        with self.assertRaisesRegex(
            ValidationError,
            "当前公司和合规档案",
        ):
            self.env["sudo.compliance.filing"].with_company(self.company).create(
                {
                    "filing_name": "Cross-company IIT filing",
                    "profile_id": self.profile.id,
                    "obligation_id": obligation.id,
                    "filing_code": "CN-IIT-WHT",
                    "filing_type": "cn_iit_withholding_return",
                    "authority": "主管税务机关",
                    "period_start": "2026-06-01",
                    "period_end": "2026-06-30",
                    "due_date": "2026-07-15",
                    "authority_source_id": source.id,
                    "due_date_basis": "人工确认测试期间截止日。",
                    "assignee_id": self.reviewer.id,
                    "payment_required": True,
                    "cn_iit_reconciliation_run_id": other_run.id,
                }
            )

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
