import hashlib
import json
from unittest.mock import patch

from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.sudo_country_pack_cn.models.reconciliation_source_monitoring import (
    SudoChinaVatPeriodReconciliationSourceMonitor,
)
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import new_test_user, tagged


@tagged("post_install", "-at_install")
class TestChinaVatPeriodReconciliation(AccountTestInvoicingCommon):
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
        cls.filing_source_approver = cls.env["res.users"].create(
            {
                "name": "China VAT Filing Source Approver",
                "login": "cn_vat_filing_source_approver",
                "company_id": cls.company.id,
                "company_ids": [Command.set(cls.company.ids)],
                "group_ids": [Command.set(compliance_manager.ids)],
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

    def _control_account_scope(self, sale, purchase, suffix):
        output_tax, input_tax = self._ledger_tax_amounts(sale, purchase)
        code_suffix = str(
            int(hashlib.sha256(suffix.encode()).hexdigest()[:8], 16)
            % 100000
        ).zfill(5)
        account_model = self.env["account.account"].with_company(self.company)
        output_account = account_model.create(
            {
                "name": f"测试销项税额控制科目 {suffix}",
                "code": f"2221{code_suffix}",
                "account_type": "liability_current",
                "company_ids": [Command.set(self.company.ids)],
            }
        )
        input_account = account_model.create(
            {
                "name": f"测试进项税额控制科目 {suffix}",
                "code": f"1122{code_suffix}",
                "account_type": "asset_current",
                "company_ids": [Command.set(self.company.ids)],
            }
        )
        control_move = self.env["account.move"].with_company(
            self.company
        ).create(
            {
                "move_type": "entry",
                "journal_id": self.company_data["default_journal_misc"].id,
                "date": "2026-06-30",
                "ref": f"TEST-VAT-CONTROL-{suffix}",
                "line_ids": [
                    Command.create(
                        {
                            "name": "销项税额对方科目",
                            "account_id": self.company_data[
                                "default_account_expense"
                            ].id,
                            "debit": output_tax,
                        }
                    ),
                    Command.create(
                        {
                            "name": "销项税额控制科目",
                            "account_id": output_account.id,
                            "credit": output_tax,
                        }
                    ),
                    Command.create(
                        {
                            "name": "进项税额控制科目",
                            "account_id": input_account.id,
                            "debit": input_tax,
                        }
                    ),
                    Command.create(
                        {
                            "name": "进项税额对方科目",
                            "account_id": self.company_data[
                                "default_account_revenue"
                            ].id,
                            "credit": input_tax,
                        }
                    ),
                ],
            }
        )
        control_move.action_post()
        mapping_model = self.env["sudo.cn.vat.account.mapping"].with_company(
            self.company
        )
        mappings = {}
        for role, account in (
            ("output", output_account),
            ("input", input_account),
        ):
            evidence = self._attachment(
                f"vat-control-{role}-{suffix}.pdf",
                f"controlled VAT account mapping {role} {suffix}".encode(),
                "application/pdf",
            )
            mapping = mapping_model.create(
                {
                    "profile_id": self.profile.id,
                    "account_id": account.id,
                    "role": role,
                    "valid_from": "2026-06-01",
                    "valid_to": "2026-06-30",
                    "source_reference": f"VAT-CONTROL/{suffix}/{role}",
                    "scope_note": (
                        "测试增值税控制科目映射，覆盖当前完整期间并按固定余额方向取数。"
                    ),
                    "evidence_attachment_ids": [Command.set(evidence.ids)],
                }
            )
            mapping.with_user(self.reviewer).action_verify()
            mappings[role] = mapping
        return {
            "move": control_move,
            "mappings": mappings,
            "output_tax": output_tax,
            "input_tax": input_tax,
        }

    def _approved_adjustment(
        self,
        suffix,
        amount,
        *,
        tax_side="output",
        effect="increase",
    ):
        evidence = self._attachment(
            f"vat-adjustment-{suffix}.pdf",
            f"controlled VAT filing adjustment {suffix}".encode(),
            "application/pdf",
        )
        adjustment = self.env[
            "sudo.cn.vat.filing.adjustment"
        ].with_company(self.company).create(
            {
                "profile_id": self.profile.id,
                "period_start": "2026-06-01",
                "period_end": "2026-06-30",
                "tax_side": tax_side,
                "effect": effect,
                "adjustment_type": "recognition_timing",
                "amount": amount,
                "description": (
                    "测试申报调节项目，记录控制科目与申报栏次之间的受控期间差异和计算过程。"
                ),
                "source_reference": f"VAT-ADJUSTMENT/{suffix}",
                "evidence_attachment_ids": [Command.set(evidence.ids)],
            }
        )
        adjustment.with_user(self.reviewer).action_approve()
        return adjustment

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

    def _valid_filing_authority_source(self, suffix):
        attachment = self._attachment(
            f"official-vat-filing-deadline-{suffix}.pdf",
            f"official VAT filing deadline source {suffix}".encode(),
            "application/pdf",
        )
        source = self.env["sudo.compliance.authority.source"].with_user(
            self.reviewer
        ).create(
            {
                "name": f"增值税申报期限官方依据 {suffix}",
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
                    "依据已复核官方资料和测试公司纳税人身份，"
                    "确认当前期间适用增值税申报与缴纳义务。"
                ),
            }
        )
        defaults.update(
            {
                "due_date": "2026-07-15",
                "authority_source_id": source.id,
                "due_date_basis": (
                    "依据已复核官方资料和当前测试纳税人按月申报身份，"
                    "人工确认本期申报截止日；未由系统自动推断。"
                ),
            }
        )
        return self.env["sudo.compliance.filing"].with_user(
            self.reviewer
        ).with_company(self.company).create(defaults)

    def _verified_filing_evidence(self, filing, suffix, evidence_type):
        evidence = self.env["sudo.compliance.evidence"].with_user(
            self.read_only_user
        ).with_company(self.company).create(
            {
                "name": f"受控档案证据 {suffix}",
                "company_id": self.company.id,
                "filing_id": filing.id,
                "evidence_type": evidence_type,
                "external_reference": (
                    f"TEST-CONTROLLED-ARCHIVE/{suffix}; 保管人=测试合规管理员; "
                    "访问方式=受控测试索引; 保留期限=测试期间"
                ),
                "evidence_date": "2026-07-12",
                "issuer": "测试主管税务机关",
            }
        )
        evidence.with_user(self.read_only_user).action_submit()
        evidence.with_user(self.reviewer).write(
            {"review_notes": "已与受控申报或缴款来源逐项核对，测试验证通过。"}
        )
        evidence.with_user(self.reviewer).action_verify()
        return evidence

    def _assessment(
        self,
        period_start="2026-06-01",
        period_end="2026-06-30",
    ):
        return self.env["sudo.compliance.assessment"].create(
            {
                "profile_id": self.profile.id,
                "evaluation_date": "2026-07-15",
                "period_start": period_start,
                "period_end": period_end,
            }
        )

    def _tax_impact_case(
        self,
        run,
        issue,
        suffix,
        *,
        impact_direction="potential_underpayment",
        impact_amount=10.0,
        quantification_state="preliminary",
        assessment=None,
        creator=None,
        include_evidence=True,
    ):
        values = {
            "title": f"税务影响复核测试事项 {suffix}",
            "profile_id": self.profile.id,
            "period_start": "2026-06-01",
            "period_end": "2026-06-30",
            "vat_run_id": run.id,
            "reconciliation_issue_ids": [Command.set(issue.ids)],
            "impact_direction": impact_direction,
            "quantification_state": quantification_state,
            "impact_amount": impact_amount,
            "analysis": (
                "根据受控勾稽来源、账务记录和工作底稿逐项分析差异，"
                "并按同一经济事项归并后形成当前初步金额。"
            ),
            "assumptions_limitations": (
                "仅基于当前测试证据，尚不替代正式申报和税务机关认定。"
            ),
            "source_reference": f"TEST/CN/TAX-IMPACT/{suffix}",
        }
        if assessment:
            values["assessment_id"] = assessment.id
        case_model = self.env["sudo.cn.tax.impact.case"].with_company(
            self.company
        )
        if creator:
            case_model = case_model.with_user(creator)
        else:
            case_model = case_model.sudo()
        case = case_model.create(values)
        attachment_model = self.env["ir.attachment"].with_company(
            self.company
        )
        if creator:
            attachment_model = attachment_model.with_user(creator)
        else:
            attachment_model = attachment_model.sudo()
        evidence = attachment_model.create(
            {
                "name": f"tax-impact-{suffix}.pdf",
                "raw": f"controlled tax impact evidence {suffix}".encode(),
                "mimetype": "application/pdf",
                "res_model": case._name,
                "res_id": case.id,
            }
        )
        if include_evidence:
            case.write(
                {"evidence_attachment_ids": [Command.set(evidence.ids)]}
            )
        return case, evidence

    def _review_tax_impact_case(self, case, reviewer=None):
        reviewer = reviewer or self.reviewer
        case.invalidate_recordset()
        if case.state == "draft":
            case.with_user(reviewer).with_company(
                self.company
            ).action_submit()
        case.with_user(reviewer).with_company(self.company).write(
            {
                "review_notes": (
                    "已逐项核对来源、影响方向、计算过程、证据和结论边界，"
                    "同意按当前受控金额列入复核报告。"
                )
            }
        )
        case.with_user(reviewer).with_company(self.company).action_review()
        case.invalidate_recordset()
        return case

    def _fact(self, key, assessment=None):
        assessment = assessment or self._assessment()
        provider = self.env[
            "sudo.compliance.engine"
        ]._fact_provider_registry()[key]
        return provider(assessment, False)

    def _activate_vat_reconciliation_test_rule(self):
        author = new_test_user(
            self.env,
            login="cn_vat_bridge_rule_author",
            groups=(
                "base.group_user,"
                "sudo_global_finance.group_compliance_rule_author"
            ),
            company_id=self.company.id,
            company_ids=[self.company.id],
        )
        approver = new_test_user(
            self.env,
            login="cn_vat_bridge_rule_approver",
            groups=(
                "base.group_user,"
                "sudo_global_finance.group_compliance_rule_approver"
            ),
            company_id=self.company.id,
            company_ids=[self.company.id],
        )
        professional = new_test_user(
            self.env,
            login="cn_vat_bridge_professional_reviewer",
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
                "name": "中国增值税勾稽闭环测试受控来源",
                "country_id": self.country.id,
                "authority": "测试主管税务机关",
                "source_type": "tax_guide",
                "snapshot_kind": "official_web_capture",
                "official_url": (
                    "https://example.test/cn-vat-reconciliation-control"
                ),
                "official_version": "TEST-2026.1",
                "published_date": "2026-01-01",
                "next_review_date": "2027-07-15",
            }
        )
        attachment = self.env["ir.attachment"].with_user(author).create(
            {
                "name": "cn-vat-reconciliation-test-source.html",
                "raw": b"Controlled China VAT reconciliation test source",
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
                    "fact_cn_vat_reconciliation_conclusion_state_v1"
                ).id,
                self.env.ref(
                    "sudo_country_pack_cn."
                    "fact_cn_vat_reconciliation_blocking_count_v1"
                ).id,
                self.env.ref(
                    "sudo_country_pack_cn."
                    "fact_cn_vat_reconciliation_difference_count_v1"
                ).id,
                self.env.ref(
                    "sudo_country_pack_cn."
                    "fact_cn_vat_reconciliation_detail_v1"
                ).id,
            ]
        )
        rule = self.env["sudo.compliance.rule"].with_user(author).create(
            {
                "name": "中国增值税四方勾稽闭环运行时测试规则",
                "code": "CN-TEST-VAT-RECON-E2E",
                "country_id": self.country.id,
                "domain_key": "CN.FILING_PAYMENT.TEST",
                "cn_rule_nature": "data_readiness",
                "description": "仅用于运行时验证规则扫描与整改复扫闭环。",
            }
        )
        version = self.env[
            "sudo.compliance.rule.version"
        ].with_user(author).create(
            {
                "rule_id": rule.id,
                "version": "TEST-2026.1",
                "effective_from": "2026-01-01",
                "next_review_date": "2027-07-15",
                "evaluator_type": "declarative",
                "condition_json": {
                    "all": [
                        {
                            "fact": "cn.reconciliation.vat.conclusion_state",
                            "operator": "eq",
                            "value": "aligned",
                        },
                        {
                            "fact": (
                                "cn.reconciliation.vat."
                                "blocking_issue_count"
                            ),
                            "operator": "eq",
                            "value": 0,
                        },
                        {
                            "fact": (
                                "cn.reconciliation.vat."
                                "difference_issue_count"
                            ),
                            "operator": "eq",
                            "value": 0,
                        },
                    ]
                },
                "match_result": "pass",
                "no_match_result": "fail",
                "risk_level": "high",
                "stale_policy": "block_all",
                "authority_source_ids": [Command.set(source.ids)],
                "required_fact_ids": [Command.set(fact_definitions.ids)],
                "legal_basis_summary": "受控运行时测试来源。",
                "failure_message": "四方勾稽存在阻断或差异。",
                "pass_message": "四方勾稽在测试范围内一致。",
                "unknown_message": "没有完整的四方勾稽事实。",
                "recommended_actions": "补齐来源并重新执行四方勾稽。",
                "evidence_required": "受控来源、差异调节和复核证据。",
                "requires_human_review": True,
            }
        )
        packet = self.env["sudo.cn.rule.review.packet"].with_user(
            author
        ).create(
            {
                "rule_version_id": version.id,
                "scope_summary": "仅验证四方勾稽运行时测试期间。",
                "applicability_assumptions": "测试来源和事实定义完整。",
                "exclusions_limitations": "不构成真实中国税务结论。",
                "conclusion_boundary": "仅验证系统治理闭环。",
                "reviewer_questions": "确认测试载荷和结论边界。",
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
                    "name": "四方勾稽一致",
                    "rule_version_id": version.id,
                    "facts_json": {
                        "cn.reconciliation.vat.conclusion_state": "aligned",
                        "cn.reconciliation.vat.blocking_issue_count": 0,
                        "cn.reconciliation.vat.difference_issue_count": 0,
                    },
                    "evaluation_date": "2026-07-15",
                    "expected_result": "pass",
                },
                {
                    "name": "四方勾稽数据不足",
                    "rule_version_id": version.id,
                    "facts_json": {
                        "cn.reconciliation.vat.conclusion_state": (
                            "insufficient_data"
                        ),
                        "cn.reconciliation.vat.blocking_issue_count": 1,
                        "cn.reconciliation.vat.difference_issue_count": 0,
                    },
                    "evaluation_date": "2026-07-15",
                    "expected_result": "fail",
                },
            ]
        )
        version.with_user(author).action_run_tests()
        evidence = b"China VAT reconciliation professional test workpaper"
        version.with_user(professional).write(
            {
                "professional_qualification": "中国财税专业测试资质",
                "professional_review_notes": (
                    "仅验证规则治理、事实快照和整改闭环。"
                ),
                "professional_evidence_reference": (
                    "TEST/CN/VAT-RECON/%s" % version.id
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

    def test_vat_reconciliation_facts_expose_auditable_aligned_snapshot(self):
        self._seed_complete_sources("fact-aligned")
        run = self._queue()
        self.assertTrue(self._process(run))
        assessment = self._assessment()

        conclusion = self._fact(
            "cn.reconciliation.vat.conclusion_state", assessment
        )
        blocking = self._fact(
            "cn.reconciliation.vat.blocking_issue_count", assessment
        )
        differences = self._fact(
            "cn.reconciliation.vat.difference_issue_count", assessment
        )
        warnings = self._fact(
            "cn.reconciliation.vat.warning_issue_count", assessment
        )
        detail = self._fact("cn.reconciliation.vat.detail", assessment)
        summary = self._fact(
            "cn.reconciliation.vat.risk_summary", assessment
        )

        self.assertEqual(conclusion["value"], "aligned")
        self.assertEqual(conclusion["quality_state"], "complete")
        self.assertEqual(conclusion["source_record_ids"], run.ids)
        self.assertEqual(blocking["value"], 0)
        self.assertEqual(differences["value"], 0)
        self.assertGreater(warnings["value"], 0)
        self.assertEqual(detail["value"]["run_id"], run.id)
        self.assertEqual(
            detail["value"]["checksums"]["result"],
            run.result_checksum,
        )
        self.assertIn(
            "ACCOUNTING_SCOPE_INVOICE_TAX_TOTALS_ONLY",
            {issue["code"] for issue in detail["value"]["issues"]},
        )
        self.assertIsNotNone(
            detail["value"]["amounts"]["filing_payable_amount"]
        )
        self.assertEqual(
            summary["value"]["schema"],
            "sdoo.cn.reconciliation.vat-risk-summary.v1",
        )
        self.assertEqual(
            summary["value"]["risk_status"],
            "aligned_with_disclosure_required",
        )
        self.assertEqual(
            summary["value"]["next_action"],
            "review_warnings_and_disclose_scope_limits",
        )
        self.assertEqual(
            summary["value"]["checksums"]["result"],
            run.result_checksum,
        )
        self.assertIn(
            "ACCOUNTING_SCOPE_INVOICE_TAX_TOTALS_ONLY",
            {issue["code"] for issue in summary["value"]["top_issues"]},
        )

        wrong_period = self._fact(
            "cn.reconciliation.vat.conclusion_state",
            self._assessment("2026-05-01", "2026-05-31"),
        )
        self.assertIsNone(wrong_period["value"])
        self.assertEqual(wrong_period["quality_state"], "missing")

    def test_verified_control_accounts_drive_layered_accounting_scope(self):
        sources = self._seed_complete_sources("control-scope")
        scope = self._control_account_scope(
            sources["sale"],
            sources["purchase"],
            "control-scope",
        )
        run = self._queue()

        self.assertTrue(self._process(run))

        self.assertEqual(run.conclusion_state, "aligned")
        self.assertEqual(run.accounting_basis, "control_accounts")
        self.assertEqual(run.accounting_source_state, "available")
        self.assertEqual(run.control_account_mapping_count, 2)
        self.assertEqual(run.control_account_line_count, 2)
        self.assertEqual(run.filing_adjustment_count, 0)
        self.assertEqual(
            set(run.control_account_mapping_ids.ids),
            {mapping.id for mapping in scope["mappings"].values()},
        )
        self.assertAlmostEqual(
            run.invoice_output_tax_amount,
            sources["output_tax"],
        )
        self.assertAlmostEqual(
            run.control_output_tax_amount,
            sources["output_tax"],
        )
        self.assertAlmostEqual(
            run.ledger_output_tax_amount,
            sources["output_tax"],
        )
        self.assertTrue(run.has_invoice_control_output_difference)
        self.assertAlmostEqual(run.invoice_control_output_difference, 0.0)
        self.assertNotIn(
            "ACCOUNTING_SCOPE_INVOICE_TAX_TOTALS_ONLY",
            set(run.issue_ids.mapped("code")),
        )
        detail = self._fact(
            "cn.reconciliation.vat.detail",
            self._assessment(),
        )["value"]
        self.assertEqual(
            detail["schema"],
            "sdoo.cn.reconciliation.vat-period.fact.v2",
        )
        self.assertEqual(detail["accounting"]["basis"], "control_accounts")
        self.assertEqual(
            detail["accounting"]["scope_snapshot_storage"],
            "persisted",
        )
        self.assertEqual(
            detail["accounting"]["control_account_line_count"],
            2,
        )
        used_mapping = scope["mappings"]["output"]
        audit_run = run.sudo()
        historical_scope = audit_run.accounting_scope_snapshot_json
        historical_scope_checksum = (
            audit_run.accounting_scope_snapshot_checksum
        )
        used_mapping.with_user(self.reviewer).action_reset_to_draft()
        used_mapping.with_user(self.reviewer).write(
            {"scope_note": "未来期间重新配置，不得改写历史批次中的原始映射快照。"}
        )
        self.assertEqual(
            audit_run.accounting_scope_snapshot_json,
            historical_scope,
        )
        self.assertEqual(
            audit_run.accounting_scope_snapshot_checksum,
            historical_scope_checksum,
        )
        self.assertEqual(
            self._fact(
                "cn.reconciliation.vat.detail",
                self._assessment(),
            )["quality_state"],
            "complete",
        )
        with self.assertRaises(UserError):
            used_mapping.unlink()

    def test_vat_fact_rejects_corrupted_accounting_scope_snapshot(self):
        sources = self._seed_complete_sources("scope-snapshot-corruption")
        self._control_account_scope(
            sources["sale"],
            sources["purchase"],
            "scope-snapshot-corruption",
        )
        run = self._queue()
        self.assertTrue(self._process(run))
        self.env.cr.execute(
            """
                UPDATE sudo_cn_vat_period_reconciliation_run
                   SET accounting_scope_snapshot_checksum = NULL
                 WHERE id = %s
            """,
            [run.id],
        )
        run.invalidate_recordset(["accounting_scope_snapshot_checksum"])

        with self.assertRaises(UserError):
            self._fact("cn.reconciliation.vat.conclusion_state")

    def test_partial_control_account_mapping_blocks_filing_comparison(self):
        sources = self._seed_complete_sources("partial-control")
        scope = self._control_account_scope(
            sources["sale"],
            sources["purchase"],
            "partial-control",
        )
        scope["mappings"]["input"].with_user(
            self.reviewer
        ).action_reset_to_draft()
        run = self._queue()

        self.assertTrue(self._process(run))

        self.assertEqual(run.conclusion_state, "insufficient_data")
        self.assertEqual(run.accounting_source_state, "blocked")
        self.assertEqual(run.accounting_basis, "control_accounts")
        self.assertEqual(run.control_account_mapping_count, 1)
        self.assertIn(
            "VAT_CONTROL_ACCOUNT_MAPPING_INCOMPLETE",
            set(run.issue_ids.mapped("code")),
        )
        self.assertFalse(run.has_ledger_filing_output_difference)
        self.assertFalse(run.has_ledger_filing_input_difference)

    def test_partial_period_mapping_is_not_silently_ignored(self):
        sources = self._seed_complete_sources("partial-period-control")
        scope = self._control_account_scope(
            sources["sale"],
            sources["purchase"],
            "partial-period-control",
        )
        output_mapping = scope["mappings"]["output"]
        output_mapping.with_user(self.reviewer).action_reset_to_draft()
        output_mapping.with_user(self.reviewer).write(
            {"valid_to": "2026-06-15"}
        )
        output_mapping.with_user(self.reviewer).action_verify()
        run = self._queue()

        self.assertTrue(self._process(run))

        self.assertEqual(run.conclusion_state, "insufficient_data")
        self.assertEqual(run.accounting_source_state, "blocked")
        self.assertEqual(run.accounting_basis, "control_accounts")
        self.assertIn(
            "VAT_CONTROL_ACCOUNT_MAPPING_PERIOD_NOT_COVERED",
            set(run.issue_ids.mapped("code")),
        )
        self.assertIn(output_mapping, run.control_account_mapping_ids)
        self.assertEqual(run.control_account_line_count, 1)
        self.assertFalse(run.has_ledger_filing_output_difference)

    def test_adjustment_type_must_match_tax_side_and_effect(self):
        values = {
            "profile_id": self.profile.id,
            "period_start": "2026-06-01",
            "period_end": "2026-06-30",
            "tax_side": "input",
            "effect": "increase",
            "adjustment_type": "unbilled_revenue",
            "amount": 1.0,
            "description": "测试调整类型与进销项口径的一致性校验记录。",
            "source_reference": "VAT-ADJUSTMENT/SEMANTICS",
        }
        model = self.env["sudo.cn.vat.filing.adjustment"]
        with self.assertRaises(ValidationError):
            model.create(values)

        values.update(
            {
                "tax_side": "input",
                "effect": "increase",
                "adjustment_type": "input_transfer_out",
            }
        )
        with self.assertRaises(ValidationError):
            model.create(values)

        values["effect"] = "decrease"
        adjustment = model.create(values)
        self.assertEqual(adjustment.tax_side, "input")
        self.assertEqual(adjustment.signed_amount, -1.0)

    def test_approved_adjustment_is_snapshotted_and_cancelled_for_future_runs(self):
        sources = self._seed_complete_sources("approved-adjustment")
        self._control_account_scope(
            sources["sale"],
            sources["purchase"],
            "approved-adjustment",
        )
        adjustment = self._approved_adjustment(
            "approved-adjustment",
            10.0,
        )
        run = self._queue()

        self.assertTrue(self._process(run))

        self.assertEqual(run.conclusion_state, "differences")
        self.assertEqual(run.filing_adjustment_count, 1)
        self.assertEqual(run.filing_adjustment_ids, adjustment)
        self.assertAlmostEqual(run.filing_output_adjustment_amount, 10.0)
        self.assertAlmostEqual(
            run.ledger_output_tax_amount,
            run.control_output_tax_amount + 10.0,
        )
        self.assertTrue(run.has_ledger_filing_output_difference)
        self.assertAlmostEqual(run.ledger_filing_output_difference, 10.0)
        with self.assertRaises(AccessError):
            adjustment.write({"amount": 11.0})

        adjustment.with_user(self.reviewer).action_cancel()
        replacement = self._queue()
        self.assertTrue(self._process(replacement))

        self.assertEqual(replacement.conclusion_state, "aligned")
        self.assertEqual(replacement.filing_adjustment_count, 0)
        self.assertEqual(run.state, "superseded")
        self.assertEqual(run.filing_adjustment_ids, adjustment)
        self.assertAlmostEqual(run.filing_output_adjustment_amount, 10.0)

    def test_mapping_same_person_review_requires_controlled_exception(self):
        account = self.env["account.account"].with_company(
            self.company
        ).create(
            {
                "name": "测试同人复核控制科目",
                "code": "222199998",
                "account_type": "liability_current",
                "company_ids": [Command.set(self.company.ids)],
            }
        )
        evidence = self.env["ir.attachment"].with_user(self.reviewer).create(
            {
                "name": "same-person-control.pdf",
                "raw": b"same person controlled exception workpaper",
                "mimetype": "application/pdf",
            }
        )
        mapping = self.env["sudo.cn.vat.account.mapping"].with_user(
            self.reviewer
        ).with_company(self.company).create(
            {
                "profile_id": self.profile.id,
                "account_id": account.id,
                "role": "output",
                "valid_from": "2026-06-01",
                "valid_to": "2026-06-30",
                "source_reference": "VAT-CONTROL/SAME-PERSON",
                "scope_note": "测试同人复核例外，明确余额方向、期间边界和受控配置依据。",
                "evidence_attachment_ids": [Command.set(evidence.ids)],
            }
        )

        with self.assertRaises(UserError):
            mapping.with_user(self.reviewer).action_verify()

        mapping.with_user(self.reviewer).write(
            {
                "separation_exception_reason": (
                    "当前测试环境仅配置一名合规管理员，已记录同人复核例外并保留完整工作底稿。"
                )
            }
        )
        mapping.with_user(self.reviewer).action_verify()

        self.assertEqual(mapping.state, "verified")
        self.assertEqual(mapping.integrity_state, "verified")
        with self.assertRaises(AccessError):
            mapping.with_user(self.read_only_user).write(
                {"scope_note": "只读用户不得修改映射。"}
            )

    def test_scope_configuration_is_company_isolated_and_read_only(self):
        own_account = self.env["account.account"].with_company(
            self.company
        ).create(
            {
                "name": "测试本公司控制科目",
                "code": "222199997",
                "account_type": "liability_current",
                "company_ids": [Command.set(self.company.ids)],
            }
        )
        own_mapping = self.env["sudo.cn.vat.account.mapping"].create(
            {
                "profile_id": self.profile.id,
                "account_id": own_account.id,
                "role": "output",
                "valid_from": "2026-06-01",
                "source_reference": "VAT-CONTROL/OWN",
                "scope_note": "本公司控制科目映射访问权限测试。",
            }
        )
        own_adjustment = self.env["sudo.cn.vat.filing.adjustment"].create(
            {
                "profile_id": self.profile.id,
                "period_start": "2026-06-01",
                "period_end": "2026-06-30",
                "tax_side": "output",
                "effect": "increase",
                "adjustment_type": "other",
                "amount": 1.0,
                "description": "本公司增值税申报调整访问权限测试记录。",
                "source_reference": "VAT-ADJUSTMENT/OWN",
            }
        )
        self.assertEqual(
            self.env["sudo.cn.vat.account.mapping"].with_user(
                self.read_only_user
            ).search([("id", "=", own_mapping.id)]),
            own_mapping,
        )
        self.assertEqual(
            self.env["sudo.cn.vat.filing.adjustment"].with_user(
                self.read_only_user
            ).search([("id", "=", own_adjustment.id)]),
            own_adjustment,
        )
        with self.assertRaises(AccessError):
            self.env["sudo.cn.vat.account.mapping"].with_user(
                self.read_only_user
            ).create({})
        with self.assertRaises(AccessError):
            self.env["sudo.cn.vat.filing.adjustment"].with_user(
                self.read_only_user
            ).create({})

        other_company = self.env["res.company"].create(
            {
                "name": "Other China VAT Scope Company",
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
        other_account = self.env["account.account"].with_company(
            other_company
        ).create(
            {
                "name": "其他公司增值税控制科目",
                "code": "222199996",
                "account_type": "liability_current",
                "company_ids": [Command.set(other_company.ids)],
            }
        )
        other_mapping = self.env["sudo.cn.vat.account.mapping"].with_company(
            other_company
        ).create(
            {
                "profile_id": other_profile.id,
                "account_id": other_account.id,
                "role": "output",
                "valid_from": "2026-06-01",
                "source_reference": "VAT-CONTROL/OTHER",
                "scope_note": "其他公司控制科目映射访问隔离测试。",
            }
        )
        other_adjustment = self.env[
            "sudo.cn.vat.filing.adjustment"
        ].with_company(other_company).create(
            {
                "profile_id": other_profile.id,
                "period_start": "2026-06-01",
                "period_end": "2026-06-30",
                "tax_side": "output",
                "effect": "increase",
                "adjustment_type": "other",
                "amount": 1.0,
                "description": "其他公司增值税申报调整访问隔离测试记录。",
                "source_reference": "VAT-ADJUSTMENT/OTHER",
            }
        )
        self.assertFalse(
            self.env["sudo.cn.vat.account.mapping"].with_user(
                self.read_only_user
            ).search([("id", "=", other_mapping.id)])
        )
        self.assertFalse(
            self.env["sudo.cn.vat.filing.adjustment"].with_user(
                self.read_only_user
            ).search([("id", "=", other_adjustment.id)])
        )

    def test_vat_reconciliation_drives_remediation_and_exact_period_rescan(self):
        self.profile._write_import({"status": "active"})
        version = self._activate_vat_reconciliation_test_rule()
        initial_run = self._queue()
        self.assertTrue(self._process(initial_run))
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
        self.assertEqual(finding.result, "fail")
        self.assertEqual(finding.cn_rule_nature, "data_readiness")
        self.assertFalse(finding.source_warning)
        self.assertFalse(finding.professional_warning)
        snapshots = {
            snapshot.definition_id.key: snapshot
            for snapshot in finding.fact_snapshot_ids
        }
        self.assertEqual(
            snapshots[
                "cn.reconciliation.vat.conclusion_state"
            ].source_record_ids_json,
            initial_run.ids,
        )
        self.assertEqual(
            snapshots[
                "cn.reconciliation.vat.blocking_issue_count"
            ].value_json,
            initial_run.blocking_issue_count,
        )

        finding.with_user(self.reviewer).write(
            {
                "review_notes": (
                    "已核对四方勾稽阻断事实和规则结论，确认需要补齐受控来源"
                    "并建立整改任务。"
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
        self.assertEqual(
            impact_action["context"]["default_finding_ids"],
            [(6, 0, finding.ids)],
        )

        task_action = finding.with_user(self.reviewer).action_create_task()
        task = self.env["sudo.compliance.task"].browse(task_action["res_id"])
        task.with_user(self.reviewer).write(
            {
                "completion_notes": (
                    "已补齐受控电子发票、增值税申报和缴税来源并重新勾稽。"
                ),
                "external_evidence_reference": (
                    "TEST/CN/VAT-REMEDIATION/2026-06"
                ),
            }
        )
        task.with_user(self.reviewer).action_done()
        self.assertEqual(task.state, "pending_review")
        self.assertEqual(task.verification_state, "pending_rescan")

        self._seed_complete_sources("compliance-remediated")
        replacement_run = self._queue()
        self.assertTrue(self._process(replacement_run))
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
                == "cn.reconciliation.vat.conclusion_state"
            ).source_record_ids_json,
            replacement_run.ids,
        )

        evidence = self.env["sudo.compliance.evidence"].with_user(
            self.reviewer
        ).create(
            {
                "name": "增值税四方勾稽整改验证证据",
                "company_id": self.company.id,
                "task_id": task.id,
                "evidence_type": "remediation_proof",
                "external_reference": (
                    "TEST/CN/VAT-REMEDIATION/VERIFIED-2026-06"
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
        assessment = self._assessment()
        conclusion = self._fact(
            "cn.reconciliation.vat.conclusion_state", assessment
        )
        blocking = self._fact(
            "cn.reconciliation.vat.blocking_issue_count", assessment
        )
        self.assertEqual(conclusion["value"], "insufficient_data")
        self.assertEqual(conclusion["quality_state"], "complete")
        self.assertEqual(blocking["value"], run.blocking_issue_count)

    def test_vat_reconciliation_fact_rejects_missing_audit_checksum(self):
        self._seed_complete_sources("fact-corruption")
        run = self._queue()
        self.assertTrue(self._process(run))
        self.env.cr.execute(
            """
                UPDATE sudo_cn_vat_period_reconciliation_run
                   SET result_checksum = NULL
                 WHERE id = %s
            """,
            [run.id],
        )
        run.invalidate_recordset(["result_checksum"])

        with self.assertRaises(UserError):
            self._fact("cn.reconciliation.vat.conclusion_state")

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
        self.assertFalse(any(first.issue_ids.mapped("is_current_result")))
        self.assertTrue(all(second.issue_ids.mapped("is_current_result")))

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

    def test_source_change_monitor_queues_one_recalculation(self):
        run = self._queue()
        self.assertTrue(self._process(run))
        self.assertEqual(
            run._cn_current_source_checksums(),
            run._cn_stored_source_checksums(),
        )
        model = self.env[run._name].with_user(self.reviewer).with_company(
            self.company
        )

        with patch.object(
            SudoChinaVatPeriodReconciliationSourceMonitor,
            "_cn_current_source_checksums",
            return_value={"changed": "vat-source"},
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
            {"name": "Foreign VAT execution context"}
        )
        self.reviewer.write(
            {"company_ids": [Command.link(foreign_company.id)]}
        )
        scope = self._control_account_scope(
            sources["sale"],
            sources["purchase"],
            "locale-stable",
        )
        mapping = scope["mappings"]["output"]
        account = mapping.account_id
        canonical_name = account.with_context(lang="en_US").name
        account.with_context(lang="zh_CN").write(
            {"name": "仅用于测试的中文销项税额科目"}
        )

        self.assertEqual(
            mapping.with_company(foreign_company)
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

        audit_run = run.sudo()
        output_snapshot = next(
            item
            for item in audit_run.accounting_scope_snapshot_json[
                "control_mappings"
            ]
            if item["mapping_id"] == mapping.id
        )
        self.assertEqual(output_snapshot["account_name"], canonical_name)
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
        other_case = self.env["sudo.cn.tax.impact.case"].with_user(
            other_manager
        ).with_company(other_company).create(
            {
                "title": "其他公司税务影响隔离测试",
                "profile_id": other_profile.id,
                "period_start": "2026-06-01",
                "period_end": "2026-06-30",
                "vat_run_id": other_run.id,
                "impact_direction": "undetermined",
                "quantification_state": "not_assessed",
                "impact_amount": 0.0,
                "analysis": "验证普通合规用户不能读取未获授权公司的税务影响复核事项。",
                "assumptions_limitations": "仅用于多公司记录规则隔离测试。",
                "source_reference": "TEST/CN/TAX-IMPACT/OTHER-COMPANY",
            }
        )
        hidden_case = self.env["sudo.cn.tax.impact.case"].with_user(
            self.read_only_user
        ).search([("id", "=", other_case.id)])
        self.assertFalse(hidden_case)

    def test_tax_impact_case_requires_sources_evidence_and_review(self):
        self._seed_complete_sources(
            "tax-impact-controlled",
            einvoice_output_delta=10.0,
        )
        run = self._queue()
        self.assertTrue(self._process(run))
        issue = run.issue_ids.filtered(
            lambda item: item.code == "LEDGER_EINVOICE_OUTPUT_DIFFERENCE"
        )
        assessment = self._assessment()
        assessment._engine_write({"state": "completed"})
        action = issue.action_create_tax_impact_case()
        self.assertEqual(action["view_mode"], "form")
        self.assertEqual(action["context"]["default_vat_run_id"], run.id)
        self.assertEqual(
            action["context"]["default_reconciliation_issue_ids"],
            [(6, 0, issue.ids)],
        )

        case, evidence = self._tax_impact_case(
            run,
            issue,
            "controlled",
            assessment=assessment,
            include_evidence=False,
        )
        with self.assertRaisesRegex(UserError, "复核证据"):
            case.with_user(self.reviewer).action_submit()

        case.write(
            {"evidence_attachment_ids": [Command.set(evidence.ids)]}
        )
        case.with_user(self.reviewer).action_submit()
        case.invalidate_recordset()
        self.assertEqual(case.state, "submitted")
        self.assertEqual(case.integrity_state, "verified")
        self.assertRegex(case.submission_checksum, r"^[0-9a-f]{64}$")
        with self.assertRaises(AccessError):
            case.write({"impact_amount": 11.0})

        case.with_user(self.reviewer).write(
            {
                "review_notes": (
                    "已核对来源、计算过程、影响方向和证据，确认当前金额"
                    "可以作为受控专业复核工作底稿。"
                )
            }
        )
        case.with_user(self.reviewer).action_review()
        case.invalidate_recordset()
        self.assertEqual(case.state, "reviewed")
        self.assertEqual(case.quantification_state, "reviewed")
        self.assertEqual(case.integrity_state, "verified")
        self.assertRegex(case.review_checksum, r"^[0-9a-f]{64}$")
        self.assertAlmostEqual(run.reviewed_underpayment_amount, 10.0)
        self.assertAlmostEqual(
            assessment.cn_reviewed_underpayment_amount,
            10.0,
        )
        self.assertEqual(assessment.cn_tax_impact_reviewed_count, 1)
        self.assertEqual(
            self.env["sudo.compliance.audit.event"].search_count(
                [
                    ("model_name", "=", case._name),
                    ("record_id", "=", case.id),
                    ("event_key", "=", "cn_tax_impact_case.reviewed"),
                ]
            ),
            1,
        )

        evidence.write({"raw": b"tampered after final professional review"})
        case.invalidate_recordset(["integrity_state"])
        run.invalidate_recordset()
        assessment.invalidate_recordset()
        self.assertEqual(case.integrity_state, "checksum_mismatch")
        self.assertEqual(run.tax_impact_integrity_issue_count, 1)
        self.assertEqual(run.reviewed_underpayment_amount, 0.0)
        self.assertEqual(
            assessment.cn_tax_impact_integrity_issue_count,
            1,
        )
        self.assertEqual(
            assessment.cn_reviewed_underpayment_amount,
            0.0,
        )

    def test_tax_impact_totals_are_reviewed_and_separate_not_net(self):
        run = self._queue()
        self.assertTrue(self._process(run))
        self.assertGreaterEqual(len(run.issue_ids), 3)
        self.assertEqual(run.reviewed_underpayment_amount, 0.0)
        self.assertEqual(run.reviewed_overpayment_amount, 0.0)
        self.assertEqual(run.reviewed_timing_amount, 0.0)

        underpayment, _evidence = self._tax_impact_case(
            run,
            run.issue_ids[0],
            "underpayment",
            impact_direction="potential_underpayment",
            impact_amount=120.0,
        )
        underpayment.with_user(self.reviewer).action_submit()
        self.assertEqual(run.tax_impact_pending_count, 1)
        self.assertEqual(run.reviewed_underpayment_amount, 0.0)
        self._review_tax_impact_case(underpayment)

        overpayment, _evidence = self._tax_impact_case(
            run,
            run.issue_ids[1],
            "overpayment",
            impact_direction="potential_overpayment",
            impact_amount=35.0,
        )
        self._review_tax_impact_case(overpayment)
        timing, _evidence = self._tax_impact_case(
            run,
            run.issue_ids[2],
            "timing",
            impact_direction="timing_difference",
            impact_amount=48.0,
        )
        self._review_tax_impact_case(timing)

        self.assertEqual(run.tax_impact_pending_count, 0)
        self.assertEqual(run.tax_impact_reviewed_count, 3)
        self.assertAlmostEqual(run.reviewed_underpayment_amount, 120.0)
        self.assertAlmostEqual(run.reviewed_overpayment_amount, 35.0)
        self.assertAlmostEqual(run.reviewed_timing_amount, 48.0)
        self.assertNotIn("net_tax_impact_amount", run._fields)

    def test_unquantifiable_case_is_counted_without_amount(self):
        run = self._queue()
        self.assertTrue(self._process(run))
        case, _evidence = self._tax_impact_case(
            run,
            run.issue_ids[0],
            "unquantifiable",
            impact_direction="undetermined",
            impact_amount=0.0,
            quantification_state="not_quantifiable",
        )
        self._review_tax_impact_case(case)

        self.assertEqual(case.quantification_state, "not_quantifiable")
        self.assertEqual(run.tax_impact_unquantifiable_count, 1)
        self.assertEqual(run.reviewed_underpayment_amount, 0.0)
        self.assertEqual(run.reviewed_overpayment_amount, 0.0)
        self.assertEqual(run.reviewed_timing_amount, 0.0)

    def test_tax_impact_source_cannot_be_double_counted(self):
        run = self._queue()
        self.assertTrue(self._process(run))
        issue = run.issue_ids[0]
        first, _evidence = self._tax_impact_case(
            run,
            issue,
            "first-owner",
        )
        with self.assertRaisesRegex(
            ValidationError,
            "只能归入一份",
        ), self.env.cr.savepoint():
            self._tax_impact_case(
                run,
                issue,
                "duplicate-owner",
            )

        self._review_tax_impact_case(first)
        first.with_user(self.reviewer).action_cancel()
        replacement, _evidence = self._tax_impact_case(
            run,
            issue,
            "replacement-owner",
        )
        self.assertEqual(replacement.state, "draft")
        self.assertEqual(first.state, "cancelled")

    def test_tax_impact_same_person_review_requires_exception(self):
        run = self._queue()
        self.assertTrue(self._process(run))
        case, _evidence = self._tax_impact_case(
            run,
            run.issue_ids[0],
            "same-person",
            creator=self.reviewer,
        )
        case.with_user(self.reviewer).action_submit()
        case.with_user(self.reviewer).write(
            {
                "review_notes": (
                    "已核对来源、计算过程、影响方向和测试证据，"
                    "拟在受控例外下确认当前复核结论。"
                )
            }
        )
        with self.assertRaisesRegex(UserError, "例外理由"):
            case.with_user(self.reviewer).action_review()

        case.with_user(self.reviewer).write(
            {
                "separation_exception_reason": (
                    "当前隔离测试环境仅配置一名复核管理员，已记录同人复核"
                    "例外并保留完整工作底稿。"
                )
            }
        )
        case.with_user(self.reviewer).action_review()
        self.assertEqual(case.state, "reviewed")
        self.assertEqual(case.reviewer_id, self.reviewer)

    def test_tax_impact_submission_detects_evidence_tampering(self):
        run = self._queue()
        self.assertTrue(self._process(run))
        case, evidence = self._tax_impact_case(
            run,
            run.issue_ids[0],
            "tampering",
        )
        case.with_user(self.reviewer).action_submit()
        evidence.write({"raw": b"changed after controlled submission"})
        case.invalidate_recordset(["integrity_state"])
        self.assertEqual(case.integrity_state, "checksum_mismatch")
        case.with_user(self.reviewer).write(
            {
                "review_notes": (
                    "已发现提交后的证据内容变化，当前资料不得直接确认复核。"
                    "应退回重新形成受控载荷。"
                )
            }
        )
        with self.assertRaisesRegex(UserError, "重新提交"):
            case.with_user(self.reviewer).action_review()

    def test_tax_impact_period_and_company_sources_are_controlled(self):
        run = self._queue()
        self.assertTrue(self._process(run))
        issue = run.issue_ids[0]
        values = {
            "title": "错误期间测试事项",
            "profile_id": self.profile.id,
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
            "vat_run_id": run.id,
            "reconciliation_issue_ids": [Command.set(issue.ids)],
            "impact_direction": "undetermined",
            "quantification_state": "not_assessed",
            "impact_amount": 0.0,
            "analysis": "用于验证税务影响事项和来源期间必须完全一致的受控测试记录。",
            "assumptions_limitations": "仅用于受控期间一致性测试。",
            "source_reference": "TEST/CN/TAX-IMPACT/PERIOD",
        }
        with self.assertRaisesRegex(ValidationError, "期间必须"):
            self.env["sudo.cn.tax.impact.case"].create(values)

        own_case, _evidence = self._tax_impact_case(
            run,
            run.issue_ids[1],
            "access-own",
        )
        visible = self.env["sudo.cn.tax.impact.case"].with_user(
            self.read_only_user
        ).search([("id", "=", own_case.id)])
        self.assertEqual(visible, own_case)
        with self.assertRaises(AccessError):
            visible.write({"review_notes": "普通用户不得写入"})
        with self.assertRaises(AccessError):
            self.env["sudo.cn.tax.impact.case"].with_user(
                self.read_only_user
            ).create(values)

    def test_vat_adjustment_report_preserves_conclusion_boundary(self):
        self._seed_complete_sources(
            "tax-impact-report",
            einvoice_output_delta=10.0,
        )
        run = self._queue()
        self.assertTrue(self._process(run))
        issue = run.issue_ids.filtered(
            lambda item: item.code == "LEDGER_EINVOICE_OUTPUT_DIFFERENCE"
        )
        case, _evidence = self._tax_impact_case(
            run,
            issue,
            "report",
            impact_amount=10.0,
        )
        self._review_tax_impact_case(case)
        report = self.env.ref(
            "sudo_country_pack_cn.action_report_cn_vat_adjustment"
        )
        action = run.action_print_vat_adjustment_report()
        html, _report_type = report._render_qweb_html(
            report.report_name,
            run.ids,
        )

        self.assertFalse(report.binding_model_id)
        self.assertEqual(action["type"], "ir.actions.report")
        self.assertIn("原始勾稽差异可能相互重叠".encode(), html)
        self.assertIn("不计算净额".encode(), html)
        self.assertIn("已复核潜在少缴税影响".encode(), html)
        self.assertIn(run.result_checksum.encode(), html)
        self.assertIn(case.review_checksum.encode(), html)

    def test_filing_archive_action_does_not_infer_legal_deadline(self):
        self._seed_complete_sources("archive-no-inference")
        run = self._queue()
        self.assertTrue(self._process(run))

        action = run.with_user(self.reviewer).action_open_cn_filing_archive()

        self.assertEqual(action["res_model"], "sudo.compliance.filing")
        self.assertEqual(
            action["context"]["default_cn_vat_reconciliation_run_id"],
            run.id,
        )
        self.assertNotIn("default_due_date", action["context"])
        self.assertNotIn("default_authority_source_id", action["context"])
        self.assertNotIn("default_due_date_basis", action["context"])

    def test_filing_and_payment_archive_seal_full_controlled_chain(self):
        self._seed_complete_sources("archive-full")
        run = self._queue()
        self.assertTrue(self._process(run))
        filing = self._controlled_filing_archive(run, "archive-full")
        receipt = self._verified_filing_evidence(
            filing,
            "archive-full-receipt",
            "filing_receipt",
        )

        filing.with_user(self.reviewer).action_prepare()
        filing.with_user(self.reviewer).action_ready()
        filing.with_user(self.reviewer).action_submit()
        filing.invalidate_recordset()

        self.assertEqual(filing.state, "submitted")
        self.assertTrue(filing.cn_submission_checksum)
        self.assertEqual(filing.cn_submission_evidence_ids, receipt)
        self.assertEqual(filing.cn_submission_integrity_state, "verified")
        self.assertEqual(
            filing.cn_submission_snapshot_json["reconciliation"]["run_id"],
            run.id,
        )

        payment = run.payment_record_ids
        filing.write(
            {
                "payment_date": payment.payment_date,
                "payment_reference": payment.payment_reference,
            }
        )
        payment_evidence = self._verified_filing_evidence(
            filing,
            "archive-full-payment",
            "payment_proof",
        )
        filing.with_user(self.reviewer).action_mark_paid()
        filing.invalidate_recordset()

        self.assertEqual(filing.payment_state, "paid")
        self.assertTrue(filing.cn_payment_checksum)
        self.assertEqual(filing.cn_payment_evidence_ids, payment_evidence)
        self.assertEqual(filing.cn_payment_integrity_state, "verified")
        self.assertEqual(
            filing.cn_net_payment_amount,
            run.payment_amount,
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
        self.assertIn("cn.vat_filing_archive.sealed", event_keys)
        self.assertIn("cn.vat_payment_archive.sealed", event_keys)

    def test_filing_archive_requires_verified_formal_receipt(self):
        self._seed_complete_sources("archive-no-receipt")
        run = self._queue()
        self.assertTrue(self._process(run))
        filing = self._controlled_filing_archive(run, "archive-no-receipt")
        filing.with_user(self.reviewer).action_prepare()
        filing.with_user(self.reviewer).action_ready()

        with self.assertRaisesRegex(UserError, "已验证的正式申报回执"):
            filing.with_user(self.reviewer).action_submit()

    def test_filing_archive_requires_applicable_vat_obligation(self):
        self._seed_complete_sources("archive-obligation")
        run = self._queue()
        self.assertTrue(self._process(run))
        action = run.with_user(self.reviewer).action_open_cn_filing_archive()
        defaults = {
            key.removeprefix("default_"): value
            for key, value in action["context"].items()
            if key.startswith("default_")
        }
        source = self._valid_filing_authority_source("archive-obligation")
        defaults.update(
            {
                "due_date": "2026-07-15",
                "authority_source_id": source.id,
                "due_date_basis": "人工确认测试期间截止日。",
            }
        )
        filing = self.env["sudo.compliance.filing"].with_user(
            self.reviewer
        ).with_company(self.company).create(defaults)
        filing.with_user(self.reviewer).action_prepare()

        with self.assertRaisesRegex(UserError, "义务尚未经过公司级适用性确认"):
            filing.with_user(self.reviewer).action_ready()

    def test_filing_archive_rejects_payment_difference(self):
        seeded = self._seed_complete_sources(
            "archive-payment-difference",
            include_payment=False,
        )
        self._create_tax_records(
            "tax_payment",
            "archive-payment-difference",
            [
                self._payment_record(
                    "archive-payment-difference",
                    seeded["payable"] + 1.0,
                )
            ],
        )
        run = self._queue()
        self.assertTrue(self._process(run))
        filing = self._controlled_filing_archive(
            run,
            "archive-payment-difference",
        )
        self._verified_filing_evidence(
            filing,
            "archive-payment-difference-receipt",
            "filing_receipt",
        )
        filing.with_user(self.reviewer).action_prepare()
        filing.with_user(self.reviewer).action_ready()
        filing.with_user(self.reviewer).action_submit()
        payment = run.payment_record_ids
        filing.write(
            {
                "payment_date": payment.payment_date,
                "payment_reference": payment.payment_reference,
            }
        )
        self._verified_filing_evidence(
            filing,
            "archive-payment-difference-proof",
            "payment_proof",
        )

        with self.assertRaisesRegex(UserError, "尚未勾稽一致"):
            filing.with_user(self.reviewer).action_mark_paid()

    def test_filing_archive_detects_checksum_tampering(self):
        self._seed_complete_sources("archive-tampering")
        run = self._queue()
        self.assertTrue(self._process(run))
        filing = self._controlled_filing_archive(run, "archive-tampering")
        self._verified_filing_evidence(
            filing,
            "archive-tampering-receipt",
            "filing_receipt",
        )
        filing.with_user(self.reviewer).action_prepare()
        filing.with_user(self.reviewer).action_ready()
        filing.with_user(self.reviewer).action_submit()
        self.assertEqual(filing.cn_submission_integrity_state, "verified")

        self.env.cr.execute(
            """
            UPDATE sudo_cn_vat_period_reconciliation_run
               SET result_checksum = %s
             WHERE id = %s
            """,
            ["0" * 64, run.id],
        )
        run.invalidate_recordset(["result_checksum"])
        filing.invalidate_recordset(["cn_submission_integrity_state"])
        self.assertEqual(filing.cn_submission_integrity_state, "changed")

    def test_filing_archive_preserves_superseded_historical_snapshot(self):
        self._seed_complete_sources("archive-superseded")
        first = self._queue()
        self.assertTrue(self._process(first))
        filing = self._controlled_filing_archive(first, "archive-superseded")
        self._verified_filing_evidence(
            filing,
            "archive-superseded-receipt",
            "filing_receipt",
        )
        filing.with_user(self.reviewer).action_prepare()
        filing.with_user(self.reviewer).action_ready()
        filing.with_user(self.reviewer).action_submit()
        sealed_checksum = filing.cn_submission_checksum

        replacement = self._queue()
        self.assertTrue(self._process(replacement))
        first.invalidate_recordset()
        filing.invalidate_recordset(["cn_submission_integrity_state"])

        self.assertEqual(first.state, "superseded")
        self.assertEqual(filing.cn_submission_checksum, sealed_checksum)
        self.assertEqual(
            filing.cn_submission_integrity_state,
            "source_superseded",
        )

    def test_filing_archive_rejects_cross_company_reconciliation(self):
        other_company = self.env["res.company"].create(
            {
                "name": "Other China Filing Archive Company",
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
            "sudo.cn.vat.period.reconciliation.run"
        ].with_user(self.reviewer).with_company(other_company).enqueue(
            other_profile,
            "2026-06-01",
            "2026-06-30",
            "VAT",
        )
        source = self._valid_filing_authority_source("archive-cross-company")
        obligation = self.profile.obligation_ids.filtered(
            lambda item: item.code == "CN-VAT"
        )[:1]
        obligation.write(
            {
                "applicability": "applicable",
                "effective_from": "2026-01-01",
                "authority_source_id": source.id,
                "justification": "测试当前公司适用增值税申报义务。",
            }
        )
        with self.assertRaisesRegex(ValidationError, "当前公司和合规档案"):
            self.env["sudo.compliance.filing"].with_company(self.company).create(
                {
                    "filing_name": "跨公司错误增值税档案",
                    "profile_id": self.profile.id,
                    "filing_code": "CN-VAT",
                    "filing_type": "cn_vat_return",
                    "authority": "主管税务机关",
                    "period_start": "2026-06-01",
                    "period_end": "2026-06-30",
                    "due_date": "2026-07-15",
                    "authority_source_id": source.id,
                    "obligation_id": obligation.id,
                    "due_date_basis": "测试跨公司来源必须被拒绝。",
                    "assignee_id": self.reviewer.id,
                    "cn_vat_reconciliation_run_id": other_run.id,
                }
            )
