from collections import Counter
from datetime import date
from decimal import Decimal
import hashlib
import json

from odoo import _, fields, models
from odoo.exceptions import UserError


USCC_REGISTRATION_TYPES = {
    "business_registration",
    "cn_uscc",
    "unified_social_credit_code",
    "uscc",
}
INVOICE_MOVE_TYPES = (
    "out_invoice",
    "out_refund",
    "in_invoice",
    "in_refund",
    "out_receipt",
    "in_receipt",
)
CIT_RECONCILIATION_REVIEW_HANDLER = "cn.cit.reconciliation.review.v1"
IIT_RECONCILIATION_REVIEW_HANDLER = "cn.iit.reconciliation.review.v1"


def _json_checksum(payload):
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


class SudoChinaComplianceEngine(models.AbstractModel):
    _inherit = "sudo.compliance.engine"

    def _fact_provider_registry(self):
        providers = super()._fact_provider_registry()
        providers.update(
            {
                "cn.company.unified_social_credit_code": (
                    self._provide_cn_unified_social_credit_code
                ),
                "cn.company.registration_evidence_count": (
                    self._provide_cn_registration_evidence_count
                ),
                "cn.company.fiscal_year_end_confirmed": (
                    self._provide_cn_fiscal_year_end_confirmed
                ),
                "cn.taxpayer.classification_verified": (
                    self._provide_cn_taxpayer_classification_verified
                ),
                "cn.taxpayer.classification_detail": (
                    self._provide_cn_taxpayer_classification_detail
                ),
                "cn.account.posted_move_count": self._provide_cn_posted_move_count,
                "cn.account.unposted_move_count": (
                    self._provide_cn_unposted_move_count
                ),
                "cn.account.posted_invoice_count": (
                    self._provide_cn_posted_invoice_count
                ),
                "cn.account.ledger_basis_detail": (
                    self._provide_cn_ledger_basis_detail
                ),
                "cn.evidence.invoice_missing_attachment_count": (
                    self._provide_cn_invoice_missing_attachment_count
                ),
                "cn.vat_invoice.posted_line_without_tax_count": (
                    self._provide_cn_posted_invoice_line_without_tax_count
                ),
                "cn.master.transaction_partner_missing_tax_id_count": (
                    self._provide_cn_transaction_partner_missing_tax_id_count
                ),
                "cn.reconciliation.einvoice.source_state": (
                    self._provide_cn_einvoice_reconciliation_source_state
                ),
                "cn.reconciliation.einvoice.data_gap_case_count": (
                    self._provide_cn_einvoice_reconciliation_data_gap_count
                ),
                "cn.reconciliation.einvoice.unresolved_case_count": (
                    self._provide_cn_einvoice_reconciliation_unresolved_count
                ),
                "cn.reconciliation.einvoice.decision_integrity_mismatch_count": (
                    self._provide_cn_einvoice_reconciliation_integrity_mismatch_count
                ),
                "cn.reconciliation.einvoice.detail": (
                    self._provide_cn_einvoice_reconciliation_detail
                ),
                "cn.reconciliation.vat.conclusion_state": (
                    self._provide_cn_vat_reconciliation_conclusion_state
                ),
                "cn.reconciliation.vat.blocking_issue_count": (
                    self._provide_cn_vat_reconciliation_blocking_count
                ),
                "cn.reconciliation.vat.difference_issue_count": (
                    self._provide_cn_vat_reconciliation_difference_count
                ),
                "cn.reconciliation.vat.warning_issue_count": (
                    self._provide_cn_vat_reconciliation_warning_count
                ),
                "cn.reconciliation.vat.detail": (
                    self._provide_cn_vat_reconciliation_detail
                ),
                "cn.reconciliation.vat.risk_summary": (
                    self._provide_cn_vat_reconciliation_risk_summary
                ),
                "cn.reconciliation.cit.conclusion_state": (
                    self._provide_cn_cit_reconciliation_conclusion_state
                ),
                "cn.reconciliation.cit.blocking_issue_count": (
                    self._provide_cn_cit_reconciliation_blocking_count
                ),
                "cn.reconciliation.cit.difference_issue_count": (
                    self._provide_cn_cit_reconciliation_difference_count
                ),
                "cn.reconciliation.cit.warning_issue_count": (
                    self._provide_cn_cit_reconciliation_warning_count
                ),
                "cn.reconciliation.cit.detail": (
                    self._provide_cn_cit_reconciliation_detail
                ),
                "cn.reconciliation.cit.risk_summary": (
                    self._provide_cn_cit_reconciliation_risk_summary
                ),
                "cn.reconciliation.iit.conclusion_state": (
                    self._provide_cn_iit_reconciliation_conclusion_state
                ),
                "cn.reconciliation.iit.blocking_issue_count": (
                    self._provide_cn_iit_reconciliation_blocking_count
                ),
                "cn.reconciliation.iit.difference_issue_count": (
                    self._provide_cn_iit_reconciliation_difference_count
                ),
                "cn.reconciliation.iit.warning_issue_count": (
                    self._provide_cn_iit_reconciliation_warning_count
                ),
                "cn.reconciliation.iit.detail": (
                    self._provide_cn_iit_reconciliation_detail
                ),
                "cn.reconciliation.iit.risk_summary": (
                    self._provide_cn_iit_reconciliation_risk_summary
                ),
                "cn.cross_border.pending_review_count": (
                    self._provide_cn_cross_border_pending_review_count
                ),
                "cn.cross_border.reviewed_transaction_count": (
                    self._provide_cn_cross_border_reviewed_transaction_count
                ),
                "cn.cross_border.detail": self._provide_cn_cross_border_detail,
            }
        )
        return providers

    def _rule_handler_registry(self):
        handlers = super()._rule_handler_registry()
        handlers[CIT_RECONCILIATION_REVIEW_HANDLER] = (
            self._evaluate_cn_cit_reconciliation_review
        )
        handlers[IIT_RECONCILIATION_REVIEW_HANDLER] = (
            self._evaluate_cn_iit_reconciliation_review
        )
        return handlers

    @staticmethod
    def _evaluate_cn_cit_reconciliation_review(
        _assessment, _version, facts, _parameters
    ):
        return SudoChinaComplianceEngine._evaluate_cn_reconciliation_review(
            facts, "cn.reconciliation.cit."
        )

    @staticmethod
    def _evaluate_cn_iit_reconciliation_review(
        _assessment, _version, facts, _parameters
    ):
        return SudoChinaComplianceEngine._evaluate_cn_reconciliation_review(
            facts, "cn.reconciliation.iit."
        )

    @staticmethod
    def _evaluate_cn_reconciliation_review(facts, prefix):
        state = facts.get(f"{prefix}conclusion_state")
        counts = {
            "blocking": facts.get(f"{prefix}blocking_issue_count"),
            "differences": facts.get(f"{prefix}difference_issue_count"),
            "warnings": facts.get(f"{prefix}warning_issue_count"),
        }
        details = {
            "conclusion_state": state,
            "issue_counts": counts,
        }

        def valid_count(value):
            return (
                isinstance(value, int)
                and not isinstance(value, bool)
                and value >= 0
            )

        if state not in {"aligned", "differences", "insufficient_data"} or not all(
            valid_count(value) for value in counts.values()
        ):
            details["reason"] = "invalid_fact_payload"
            return {
                "result": "unknown",
                "requires_human_review": True,
                "details": details,
            }

        blocking = counts["blocking"]
        differences = counts["differences"]
        warnings = counts["warnings"]
        state_is_consistent = {
            "aligned": blocking == 0 and differences == 0,
            "differences": blocking == 0 and differences > 0,
            "insufficient_data": blocking > 0,
        }[state]
        if not state_is_consistent:
            details["reason"] = "inconsistent_reconciliation_state"
            return {
                "result": "unknown",
                "requires_human_review": True,
                "details": details,
            }
        if state == "insufficient_data":
            details["reason"] = "data_not_comparable"
            result = "unknown"
        elif state == "differences":
            details["reason"] = "differences_require_review"
            result = "fail"
        elif warnings:
            details["reason"] = "warnings_require_review"
            result = "unknown"
        else:
            details["reason"] = "controlled_amounts_aligned"
            result = "pass"
        return {
            "result": result,
            "requires_human_review": True,
            "details": details,
        }

    @staticmethod
    def _reconciliation_period_domain(assessment):
        period_start = fields.Date.to_date(assessment.period_start)
        period_end = fields.Date.to_date(assessment.period_end)
        domain = [("profile_id", "=", assessment.profile_id.id)]
        if period_start:
            domain.append(("period_start", "=", period_start))
        if period_end:
            domain.append(("period_end", "=", period_end))
        return period_start, period_end, domain

    def _current_reconciliation_run(
        self,
        assessment,
        model_name,
        label,
        checksum_fields,
        aggregation_method,
    ):
        period_start, period_end, period_domain = (
            self._reconciliation_period_domain(assessment)
        )
        model = self.env[model_name].sudo().with_company(
            assessment.company_id
        )
        missing = {
            "value": None,
            "source_model": model_name,
            "source_domain": period_domain + [("state", "=", "succeeded")],
            "record_count": 0,
            "aggregation_method": aggregation_method,
            "quality_state": "missing",
            "is_complete": False,
            "is_full_dataset": False,
            "provider_version": "1",
        }
        if not period_start or not period_end:
            return model.browse(), missing

        active = model.search(
            period_domain + [("state", "in", ("queued", "processing"))],
            order="requested_at desc, id desc",
        )
        current = model.search(
            period_domain + [("state", "=", "succeeded")],
            order="requested_at desc, id desc",
            limit=2,
        )
        if len(current) > 1:
            raise UserError(
                _(
                    "%(label)s存在多份当前成功结果，不能选择或汇总。",
                    label=label,
                )
            )
        if active:
            pending = active | current
            return model.browse(), {
                **missing,
                "source_record_ids": pending.ids,
                "record_count": len(pending),
                "quality_state": "stale",
            }
        if not current:
            return model.browse(), missing

        run = current[0]
        required_fields = (
            "engine_version",
            "finished_at",
            "result_checksum",
            *checksum_fields,
        )
        absent = [field_name for field_name in required_fields if not run[field_name]]
        if absent:
            raise UserError(
                _(
                    "%(label)s当前结果缺少审计字段：%(fields)s。",
                    label=label,
                    fields=", ".join(absent),
                )
            )
        return run, {
            "source_model": model_name,
            "source_record_ids": run.ids,
            "record_count": 1,
            "aggregation_method": aggregation_method,
            "valid_at": run.finished_at,
            "quality_state": "complete",
            "is_complete": True,
            "is_full_dataset": True,
            "provider_version": "1",
        }

    def _cn_einvoice_reconciliation_snapshot(self, assessment):
        run, payload = self._current_reconciliation_run(
            assessment,
            "sudo.cn.einvoice.reconciliation.run",
            _("账票勾稽"),
            ("source_snapshot_checksum", "ledger_snapshot_checksum"),
            "single_exact_period_current_success_snapshot",
        )
        if not run:
            return payload, None

        cases = run.case_ids.sudo()
        states = Counter(cases.mapped("state"))
        expected_counts = {
            "case_count": len(cases),
            "matched_case_count": states["matched"] + states["partial"],
            "suggested_case_count": states["suggested"],
            "ambiguous_case_count": states["ambiguous"],
            "unmatched_case_count": (
                states["unmatched"] + states["reviewed_unmatched"]
            ),
            "data_gap_case_count": states["data_gap"],
            "warning_case_count": len(
                cases.filtered(lambda case: case.warning_issue_count > 0)
            ),
        }
        inconsistent = [
            field_name
            for field_name, expected in expected_counts.items()
            if run[field_name] != expected
        ]
        if run.source_document_count != len(cases):
            inconsistent.append("source_document_count")
        if run.source_availability_state == "not_evaluated":
            inconsistent.append("source_availability_state")
        if inconsistent:
            raise UserError(
                _(
                    "账票勾稽当前结果计数或状态不一致：%(fields)s。",
                    fields=", ".join(sorted(set(inconsistent))),
                )
            )

        unresolved = (
            states["suggested"] + states["ambiguous"] + states["unmatched"]
        )
        integrity_mismatches = len(
            cases.filtered(
                lambda case: case.decision_integrity_state == "mismatch"
            )
        )
        detail = {
            "schema": "sdoo.cn.reconciliation.einvoice.fact.v1",
            "run_id": run.id,
            "engine_version": run.engine_version,
            "period_start": fields.Date.to_string(run.period_start),
            "period_end": fields.Date.to_string(run.period_end),
            "source_state": run.source_availability_state,
            "counts": {
                "source_documents": run.source_document_count,
                "ledger_moves": run.ledger_move_count,
                "cases": run.case_count,
                "matched": run.matched_case_count,
                "suggested": states["suggested"],
                "ambiguous": states["ambiguous"],
                "unmatched": states["unmatched"],
                "reviewed_unmatched": states["reviewed_unmatched"],
                "data_gap": states["data_gap"],
                "warning_cases": run.warning_case_count,
                "unresolved": unresolved,
                "decision_integrity_mismatch": integrity_mismatches,
            },
            "checksums": {
                "source": run.source_snapshot_checksum,
                "ledger": run.ledger_snapshot_checksum,
                "result": run.result_checksum,
            },
        }
        return payload, detail

    def _provide_cn_einvoice_reconciliation_value(
        self, assessment, value_getter
    ):
        payload, detail = self._cn_einvoice_reconciliation_snapshot(assessment)
        payload["value"] = value_getter(detail) if detail else None
        return payload

    def _provide_cn_einvoice_reconciliation_source_state(
        self, assessment, _definition
    ):
        return self._provide_cn_einvoice_reconciliation_value(
            assessment, lambda detail: detail["source_state"]
        )

    def _provide_cn_einvoice_reconciliation_data_gap_count(
        self, assessment, _definition
    ):
        return self._provide_cn_einvoice_reconciliation_value(
            assessment, lambda detail: detail["counts"]["data_gap"]
        )

    def _provide_cn_einvoice_reconciliation_unresolved_count(
        self, assessment, _definition
    ):
        return self._provide_cn_einvoice_reconciliation_value(
            assessment, lambda detail: detail["counts"]["unresolved"]
        )

    def _provide_cn_einvoice_reconciliation_integrity_mismatch_count(
        self, assessment, _definition
    ):
        return self._provide_cn_einvoice_reconciliation_value(
            assessment,
            lambda detail: detail["counts"]["decision_integrity_mismatch"],
        )

    def _provide_cn_einvoice_reconciliation_detail(
        self, assessment, _definition
    ):
        return self._provide_cn_einvoice_reconciliation_value(
            assessment, lambda detail: detail
        )

    @staticmethod
    def _amount_snapshot(currency, value):
        return format(Decimal(str(currency.round(float(value or 0.0)))), "f")

    def _cn_vat_reconciliation_snapshot(self, assessment):
        run, payload = self._current_reconciliation_run(
            assessment,
            "sudo.cn.vat.period.reconciliation.run",
            _("增值税期间四方勾稽"),
            (
                "accounting_snapshot_checksum",
                "einvoice_snapshot_checksum",
                "filing_snapshot_checksum",
                "payment_snapshot_checksum",
            ),
            "single_exact_period_current_success_snapshot",
        )
        if not run:
            return payload, None

        scope_snapshot = run.accounting_scope_snapshot_json
        scope_snapshot_checksum = run.accounting_scope_snapshot_checksum
        scope_snapshot_storage = "legacy_hash_only"
        if run.engine_version != "19.0.1":
            if (
                not isinstance(scope_snapshot, dict)
                or scope_snapshot.get("schema")
                != "sdoo.cn.vat-accounting-scope-config.v1"
                or not scope_snapshot_checksum
                or _json_checksum(scope_snapshot) != scope_snapshot_checksum
            ):
                raise UserError(_("增值税期间四方勾稽账务口径配置快照不完整。"))
            snapshot_mapping_ids = [
                item.get("mapping_id")
                for item in scope_snapshot.get("control_mappings", [])
            ]
            snapshot_adjustment_ids = [
                item.get("adjustment_id")
                for item in scope_snapshot.get("filing_adjustments", [])
            ]
            if (
                Counter(snapshot_mapping_ids)
                != Counter(run.control_account_mapping_ids.ids)
                or Counter(snapshot_adjustment_ids)
                != Counter(run.filing_adjustment_ids.ids)
            ):
                raise UserError(
                    _("增值税期间四方勾稽账务口径配置快照与关联记录不一致。")
                )
            scope_snapshot_storage = "persisted"

        issues = run.issue_ids.sudo()
        blocking_count = len(
            issues.filtered(lambda issue: issue.severity == "blocking")
        )
        difference_count = len(
            issues.filtered(lambda issue: issue.issue_kind == "difference")
        )
        warning_count = len(
            issues.filtered(
                lambda issue: issue.severity == "review"
                and issue.issue_kind != "difference"
            )
        )
        expected_conclusion = (
            "insufficient_data"
            if blocking_count
            else "differences"
            if difference_count
            else "aligned"
        )
        expected = {
            "issue_count": len(issues),
            "blocking_issue_count": blocking_count,
            "difference_issue_count": difference_count,
            "warning_issue_count": warning_count,
            "conclusion_state": expected_conclusion,
            "posted_accounting_move_count": len(
                run.accounting_move_ids.filtered(
                    lambda move: move.state == "posted"
                )
            ),
            "draft_accounting_move_count": len(
                run.accounting_move_ids.filtered(
                    lambda move: move.state == "draft"
                )
            ),
            "control_account_mapping_count": len(
                run.control_account_mapping_ids
            ),
            "control_account_line_count": len(run.control_account_line_ids),
            "filing_adjustment_count": len(run.filing_adjustment_ids),
            "einvoice_document_count": len(run.einvoice_document_ids),
            "filing_record_count": len(run.filing_record_ids),
            "payment_record_count": len(run.payment_record_ids),
        }
        inconsistent = [
            field_name
            for field_name, value in expected.items()
            if run[field_name] != value
        ]
        source_state_fields = (
            "accounting_source_state",
            "einvoice_source_state",
            "filing_source_state",
            "payment_source_state",
        )
        inconsistent.extend(
            field_name
            for field_name in source_state_fields
            if run[field_name] == "not_evaluated"
        )
        if inconsistent:
            raise UserError(
                _(
                    "增值税期间四方勾稽当前结果计数或状态不一致：%(fields)s。",
                    fields=", ".join(sorted(set(inconsistent))),
                )
            )

        amount_fields = (
            "invoice_output_tax_amount",
            "invoice_input_tax_amount",
            "control_output_tax_amount",
            "control_input_tax_amount",
            "filing_output_adjustment_amount",
            "filing_input_adjustment_amount",
            "ledger_output_tax_amount",
            "ledger_input_tax_amount",
            "einvoice_output_tax_amount",
            "einvoice_input_tax_amount",
            "filing_output_tax_amount",
            "filing_input_tax_amount",
            "filing_payable_amount",
            "payment_amount",
        )
        provided_fields = {
            "einvoice_output_tax_amount": "has_einvoice_output_tax_amount",
            "einvoice_input_tax_amount": "has_einvoice_input_tax_amount",
            "filing_output_tax_amount": "has_filing_output_tax_amount",
            "filing_input_tax_amount": "has_filing_input_tax_amount",
            "filing_payable_amount": "has_filing_payable_amount",
            "payment_amount": "has_payment_amount",
        }
        amounts = {}
        for field_name in amount_fields:
            provided_field = provided_fields.get(field_name)
            amounts[field_name] = (
                self._amount_snapshot(run.currency_id, run[field_name])
                if not provided_field or run[provided_field]
                else None
            )
        difference_fields = (
            (
                "ledger_einvoice_output_difference",
                "has_ledger_einvoice_output_difference",
            ),
            (
                "ledger_einvoice_input_difference",
                "has_ledger_einvoice_input_difference",
            ),
            (
                "ledger_filing_output_difference",
                "has_ledger_filing_output_difference",
            ),
            (
                "ledger_filing_input_difference",
                "has_ledger_filing_input_difference",
            ),
            ("filing_payment_difference", "has_filing_payment_difference"),
            (
                "invoice_control_output_difference",
                "has_invoice_control_output_difference",
            ),
            (
                "invoice_control_input_difference",
                "has_invoice_control_input_difference",
            ),
        )
        differences = {
            field_name: (
                self._amount_snapshot(run.currency_id, run[field_name])
                if run[provided_field]
                else None
            )
            for field_name, provided_field in difference_fields
        }
        detail = {
            "schema": "sdoo.cn.reconciliation.vat-period.fact.v2",
            "run_id": run.id,
            "engine_version": run.engine_version,
            "period_start": fields.Date.to_string(run.period_start),
            "period_end": fields.Date.to_string(run.period_end),
            "vat_tax_type_code": run.vat_tax_type_code,
            "currency": run.currency_id.name,
            "conclusion_state": run.conclusion_state,
            "accounting": {
                "basis": run.accounting_basis,
                "scope_snapshot_storage": scope_snapshot_storage,
                "control_account_mapping_count": (
                    run.control_account_mapping_count
                ),
                "control_account_line_count": run.control_account_line_count,
                "filing_adjustment_count": run.filing_adjustment_count,
            },
            "source_states": {
                "accounting": run.accounting_source_state,
                "einvoice": run.einvoice_source_state,
                "filing": run.filing_source_state,
                "payment": run.payment_source_state,
            },
            "counts": {
                "accounting_posted": run.posted_accounting_move_count,
                "accounting_draft": run.draft_accounting_move_count,
                "control_account_mappings": (
                    run.control_account_mapping_count
                ),
                "control_account_lines": run.control_account_line_count,
                "filing_adjustments": run.filing_adjustment_count,
                "einvoice": run.einvoice_document_count,
                "filing": run.filing_record_count,
                "payment": run.payment_record_count,
                "issues": run.issue_count,
                "blocking": run.blocking_issue_count,
                "differences": run.difference_issue_count,
                "warnings": run.warning_issue_count,
            },
            "amounts": amounts,
            "differences": differences,
            "issues": [
                {
                    "id": issue.id,
                    "code": issue.code,
                    "severity": issue.severity,
                    "kind": issue.issue_kind,
                    "source_area": issue.source_area,
                    "affected_record_count": issue.affected_record_count,
                    "difference": (
                        self._amount_snapshot(
                            run.currency_id, issue.difference_amount
                        )
                        if issue.has_difference
                        else None
                    ),
                }
                for issue in issues.sorted(
                    lambda issue: (issue.sequence, issue.code, issue.id)
                )
            ],
            "checksums": {
                "accounting": run.accounting_snapshot_checksum,
                "accounting_scope": scope_snapshot_checksum,
                "einvoice": run.einvoice_snapshot_checksum,
                "filing": run.filing_snapshot_checksum,
                "payment": run.payment_snapshot_checksum,
                "result": run.result_checksum,
            },
        }
        return payload, detail

    def _cn_vat_reconciliation_risk_summary(self, detail):
        if not detail:
            return None

        counts = detail["counts"]
        source_states = detail["source_states"]
        differences = {
            key: value
            for key, value in detail["differences"].items()
            if value not in (None, "0", "0.0", "0.00")
        }
        blocked_sources = [
            key for key, value in source_states.items() if value == "blocked"
        ]
        missing_sources = [
            key for key, value in source_states.items() if value == "no_data"
        ]
        if counts["blocking"]:
            risk_status = "blocked"
            next_action = "resolve_blocking_source_or_control_issues"
        elif counts["differences"]:
            risk_status = "difference_review_required"
            next_action = "review_each_difference_before_report_or_filing"
        elif counts["warnings"]:
            risk_status = "aligned_with_disclosure_required"
            next_action = "review_warnings_and_disclose_scope_limits"
        else:
            risk_status = "aligned"
            next_action = "retain_snapshots_and_continue_monitoring"

        return {
            "schema": "sdoo.cn.reconciliation.vat-risk-summary.v1",
            "run_id": detail["run_id"],
            "period_start": detail["period_start"],
            "period_end": detail["period_end"],
            "currency": detail["currency"],
            "conclusion_state": detail["conclusion_state"],
            "risk_status": risk_status,
            "next_action": next_action,
            "source_states": source_states,
            "blocked_sources": blocked_sources,
            "missing_sources": missing_sources,
            "counts": {
                "blocking": counts["blocking"],
                "differences": counts["differences"],
                "warnings": counts["warnings"],
                "issues": counts["issues"],
            },
            "amounts": {
                "ledger_output_tax_amount": detail["amounts"][
                    "ledger_output_tax_amount"
                ],
                "ledger_input_tax_amount": detail["amounts"][
                    "ledger_input_tax_amount"
                ],
                "filing_payable_amount": detail["amounts"][
                    "filing_payable_amount"
                ],
                "payment_amount": detail["amounts"]["payment_amount"],
            },
            "material_differences": differences,
            "top_issues": [
                {
                    "code": issue["code"],
                    "severity": issue["severity"],
                    "kind": issue["kind"],
                    "source_area": issue["source_area"],
                    "difference": issue["difference"],
                }
                for issue in detail["issues"][:10]
            ],
            "checksums": {
                "result": detail["checksums"]["result"],
                "accounting": detail["checksums"]["accounting"],
                "einvoice": detail["checksums"]["einvoice"],
                "filing": detail["checksums"]["filing"],
                "payment": detail["checksums"]["payment"],
            },
        }

    def _provide_cn_vat_reconciliation_value(
        self, assessment, value_getter
    ):
        payload, detail = self._cn_vat_reconciliation_snapshot(assessment)
        payload["value"] = value_getter(detail) if detail else None
        return payload

    def _provide_cn_vat_reconciliation_conclusion_state(
        self, assessment, _definition
    ):
        return self._provide_cn_vat_reconciliation_value(
            assessment, lambda detail: detail["conclusion_state"]
        )

    def _provide_cn_vat_reconciliation_blocking_count(
        self, assessment, _definition
    ):
        return self._provide_cn_vat_reconciliation_value(
            assessment, lambda detail: detail["counts"]["blocking"]
        )

    def _provide_cn_vat_reconciliation_difference_count(
        self, assessment, _definition
    ):
        return self._provide_cn_vat_reconciliation_value(
            assessment, lambda detail: detail["counts"]["differences"]
        )

    def _provide_cn_vat_reconciliation_warning_count(
        self, assessment, _definition
    ):
        return self._provide_cn_vat_reconciliation_value(
            assessment, lambda detail: detail["counts"]["warnings"]
        )

    def _provide_cn_vat_reconciliation_detail(self, assessment, _definition):
        return self._provide_cn_vat_reconciliation_value(
            assessment, lambda detail: detail
        )

    def _provide_cn_vat_reconciliation_risk_summary(
        self, assessment, _definition
    ):
        return self._provide_cn_vat_reconciliation_value(
            assessment, self._cn_vat_reconciliation_risk_summary
        )

    @staticmethod
    def _cn_reconciliation_risk_summary(
        detail, schema, amount_fields, next_actions
    ):
        if not detail:
            return None

        counts = detail["counts"]
        source_states = detail["source_states"]
        differences = {
            key: value
            for key, value in detail["differences"].items()
            if value not in (None, "0", "0.0", "0.00")
        }
        blocked_sources = [
            key for key, value in source_states.items() if value == "blocked"
        ]
        missing_sources = [
            key for key, value in source_states.items() if value == "no_data"
        ]
        if counts["blocking"]:
            risk_status = "blocked"
        elif counts["differences"]:
            risk_status = "difference_review_required"
        elif counts["warnings"]:
            risk_status = "aligned_with_disclosure_required"
        else:
            risk_status = "aligned"

        return {
            "schema": schema,
            "run_id": detail["run_id"],
            "period_start": detail["period_start"],
            "period_end": detail["period_end"],
            "conclusion_state": detail["conclusion_state"],
            "risk_status": risk_status,
            "next_action": next_actions[risk_status],
            "source_states": source_states,
            "blocked_sources": blocked_sources,
            "missing_sources": missing_sources,
            "counts": {
                "blocking": counts["blocking"],
                "differences": counts["differences"],
                "warnings": counts["warnings"],
                "issues": counts["issues"],
            },
            "amounts": {
                field_name: detail["amounts"].get(field_name)
                for field_name in amount_fields
            },
            "material_differences": differences,
            "top_issues": [
                {
                    "code": issue["code"],
                    "severity": issue["severity"],
                    "kind": issue["kind"],
                    "source_area": issue["source_area"],
                    "difference": issue["difference"],
                    "count_comparison": issue.get("count_comparison"),
                }
                for issue in detail["issues"][:10]
            ],
            "checksums": detail["checksums"],
        }

    def _cn_cit_reconciliation_snapshot(self, assessment):
        run, payload = self._current_reconciliation_run(
            assessment,
            "sudo.cn.cit.period.reconciliation.run",
            _("企业所得税账税勾稽"),
            (
                "accounting_scope_snapshot_checksum",
                "accounting_snapshot_checksum",
                "filing_snapshot_checksum",
                "payment_snapshot_checksum",
            ),
            "single_exact_period_current_success_snapshot",
        )
        if not run:
            return payload, None

        snapshots = (
            (
                "accounting_scope_snapshot_json",
                "accounting_scope_snapshot_checksum",
                "sdoo.cn.cit-accounting-profit-scope.v1",
            ),
            (
                "accounting_snapshot_json",
                "accounting_snapshot_checksum",
                "sdoo.cn.cit-accounting-ledger.v1",
            ),
            (
                "filing_snapshot_json",
                "filing_snapshot_checksum",
                "sdoo.cn.cit-filing-source.v1",
            ),
            (
                "payment_snapshot_json",
                "payment_snapshot_checksum",
                "sdoo.cn.cit-payment-source.v1",
            ),
        )
        invalid_snapshots = []
        for json_field, checksum_field, schema in snapshots:
            snapshot = run[json_field]
            if (
                not isinstance(snapshot, dict)
                or snapshot.get("schema") != schema
                or _json_checksum(snapshot) != run[checksum_field]
            ):
                invalid_snapshots.append(json_field)
        if invalid_snapshots:
            raise UserError(
                _(
                    "企业所得税账税勾稽快照完整性异常：%(fields)s。",
                    fields=", ".join(invalid_snapshots),
                )
            )
        if (
            not run.result_checksum
            or run._current_result_checksum() != run.result_checksum
        ):
            raise UserError(_("企业所得税账税勾稽结果完整性异常。"))

        issues = run.issue_ids.sudo()
        blocking_count = len(
            issues.filtered(lambda issue: issue.severity == "blocking")
        )
        difference_count = len(
            issues.filtered(lambda issue: issue.issue_kind == "difference")
        )
        warning_count = len(
            issues.filtered(
                lambda issue: issue.severity == "review"
                and issue.issue_kind != "difference"
            )
        )
        expected_conclusion = (
            "insufficient_data"
            if blocking_count
            else "differences"
            if difference_count
            else "aligned"
        )
        expected = {
            "issue_count": len(issues),
            "blocking_issue_count": blocking_count,
            "difference_issue_count": difference_count,
            "warning_issue_count": warning_count,
            "conclusion_state": expected_conclusion,
            "accounting_scope_line_count": (
                len(run.accounting_scope_id.line_ids)
                if run.accounting_scope_id
                else 0
            ),
            "payment_record_count": len(run.payment_record_ids),
        }
        inconsistent = [
            field_name
            for field_name, expected_value in expected.items()
            if run[field_name] != expected_value
        ]
        inconsistent.extend(
            field_name
            for field_name in (
                "accounting_source_state",
                "filing_source_state",
                "payment_source_state",
            )
            if run[field_name] == "not_evaluated"
        )
        if inconsistent:
            raise UserError(
                _(
                    "企业所得税账税勾稽当前结果计数或状态不一致：%(fields)s。",
                    fields=", ".join(sorted(set(inconsistent))),
                )
            )

        amount_fields = (
            "ledger_profit_increase_amount",
            "ledger_profit_decrease_amount",
            "ledger_accounting_profit_amount",
            "filing_accounting_profit_amount",
            "filing_adjustment_increase_amount",
            "filing_adjustment_decrease_amount",
            "filing_taxable_income_amount",
            "expected_taxable_income_amount",
            "filing_tax_payable_amount",
            "filing_tax_relief_amount",
            "filing_tax_credit_amount",
            "filing_prepaid_tax_amount",
            "filing_payable_amount",
            "filing_refundable_amount",
            "paid_principal_amount",
            "reversed_principal_amount",
            "effective_paid_principal_amount",
            "refunded_principal_amount",
            "interest_amount",
            "penalty_amount",
        )
        provided_fields = {
            "filing_accounting_profit_amount": "has_filing_accounting_profit_amount",
            "filing_adjustment_increase_amount": "has_filing_adjustment_increase_amount",
            "filing_adjustment_decrease_amount": "has_filing_adjustment_decrease_amount",
            "filing_taxable_income_amount": "has_filing_taxable_income_amount",
            "expected_taxable_income_amount": "has_expected_taxable_income_amount",
            "filing_tax_payable_amount": "has_filing_tax_payable_amount",
            "filing_tax_relief_amount": "has_filing_tax_relief_amount",
            "filing_tax_credit_amount": "has_filing_tax_credit_amount",
            "filing_prepaid_tax_amount": "has_filing_prepaid_tax_amount",
            "filing_payable_amount": "has_filing_payable_amount",
            "filing_refundable_amount": "has_filing_refundable_amount",
        }
        amounts = {
            field_name: (
                self._amount_snapshot(run.currency_id, run[field_name])
                if not provided_fields.get(field_name)
                or run[provided_fields[field_name]]
                else None
            )
            for field_name in amount_fields
        }
        difference_fields = (
            (
                "ledger_filing_profit_difference",
                "has_ledger_filing_profit_difference",
            ),
            (
                "filing_taxable_arithmetic_difference",
                "has_filing_taxable_arithmetic_difference",
            ),
            ("payable_payment_difference", "has_payable_payment_difference"),
            (
                "refundable_refund_difference",
                "has_refundable_refund_difference",
            ),
        )
        detail = {
            "schema": "sdoo.cn.reconciliation.cit-period.fact.v1",
            "run_id": run.id,
            "engine_version": run.engine_version,
            "period_start": fields.Date.to_string(run.period_start),
            "period_end": fields.Date.to_string(run.period_end),
            "return_period_type": run.return_period_type,
            "cit_tax_type_code": run.cit_tax_type_code,
            "conclusion_state": run.conclusion_state,
            "source_states": {
                "accounting": run.accounting_source_state,
                "filing": run.filing_source_state,
                "payment": run.payment_source_state,
            },
            "counts": {
                "accounting_scope_lines": run.accounting_scope_line_count,
                "posted_accounting_lines": run.posted_accounting_line_count,
                "draft_accounting_lines": run.draft_accounting_line_count,
                "payment_records": run.payment_record_count,
                "issues": run.issue_count,
                "blocking": run.blocking_issue_count,
                "differences": run.difference_issue_count,
                "warnings": run.warning_issue_count,
            },
            "amounts": amounts,
            "differences": {
                field_name: (
                    self._amount_snapshot(run.currency_id, run[field_name])
                    if run[provided_field]
                    else None
                )
                for field_name, provided_field in difference_fields
            },
            "issues": [
                {
                    "id": issue.id,
                    "code": issue.code,
                    "severity": issue.severity,
                    "kind": issue.issue_kind,
                    "source_area": issue.source_area,
                    "difference": (
                        self._amount_snapshot(
                            run.currency_id, issue.difference_amount
                        )
                        if issue.has_difference
                        else None
                    ),
                }
                for issue in issues.sorted(
                    lambda issue: (issue.sequence, issue.code, issue.id)
                )
            ],
            "checksums": {
                "accounting_scope": run.accounting_scope_snapshot_checksum,
                "accounting": run.accounting_snapshot_checksum,
                "filing": run.filing_snapshot_checksum,
                "payment": run.payment_snapshot_checksum,
                "result": run.result_checksum,
            },
        }
        return payload, detail

    def _provide_cn_cit_reconciliation_value(self, assessment, value_getter):
        payload, detail = self._cn_cit_reconciliation_snapshot(assessment)
        payload["value"] = value_getter(detail) if detail else None
        return payload

    def _provide_cn_cit_reconciliation_conclusion_state(
        self, assessment, _definition
    ):
        return self._provide_cn_cit_reconciliation_value(
            assessment, lambda detail: detail["conclusion_state"]
        )

    def _provide_cn_cit_reconciliation_blocking_count(
        self, assessment, _definition
    ):
        return self._provide_cn_cit_reconciliation_value(
            assessment, lambda detail: detail["counts"]["blocking"]
        )

    def _provide_cn_cit_reconciliation_difference_count(
        self, assessment, _definition
    ):
        return self._provide_cn_cit_reconciliation_value(
            assessment, lambda detail: detail["counts"]["differences"]
        )

    def _provide_cn_cit_reconciliation_warning_count(
        self, assessment, _definition
    ):
        return self._provide_cn_cit_reconciliation_value(
            assessment, lambda detail: detail["counts"]["warnings"]
        )

    def _provide_cn_cit_reconciliation_detail(self, assessment, _definition):
        return self._provide_cn_cit_reconciliation_value(
            assessment, lambda detail: detail
        )

    def _provide_cn_cit_reconciliation_risk_summary(
        self, assessment, _definition
    ):
        return self._provide_cn_cit_reconciliation_value(
            assessment,
            lambda detail: self._cn_reconciliation_risk_summary(
                detail,
                "sdoo.cn.reconciliation.cit-risk-summary.v1",
                (
                    "ledger_accounting_profit_amount",
                    "filing_accounting_profit_amount",
                    "expected_taxable_income_amount",
                    "filing_taxable_income_amount",
                    "filing_payable_amount",
                    "effective_paid_principal_amount",
                    "filing_refundable_amount",
                    "refunded_principal_amount",
                ),
                {
                    "blocked": "resolve_cit_source_or_scope_blockers",
                    "difference_review_required": (
                        "review_cit_ledger_filing_payment_differences"
                    ),
                    "aligned_with_disclosure_required": (
                        "review_cit_warnings_and_disclose_scope_limits"
                    ),
                    "aligned": "retain_cit_snapshots_and_continue_monitoring",
                },
            ),
        )

    def _cn_iit_reconciliation_snapshot(self, assessment):
        run, payload = self._current_reconciliation_run(
            assessment,
            "sudo.cn.iit.period.reconciliation.run",
            _("个人所得税工资账表款勾稽"),
            (
                "accounting_scope_snapshot_checksum",
                "accounting_snapshot_checksum",
                "payroll_snapshot_checksum",
                "filing_snapshot_checksum",
                "payment_snapshot_checksum",
            ),
            "single_exact_period_current_success_snapshot",
        )
        if not run:
            return payload, None

        snapshots = (
            (
                "accounting_scope_snapshot_json",
                "accounting_scope_snapshot_checksum",
                "sdoo.cn.iit-accounting-scope.v1",
            ),
            (
                "accounting_snapshot_json",
                "accounting_snapshot_checksum",
                "sdoo.cn.iit-accounting-ledger.v1",
            ),
            (
                "payroll_snapshot_json",
                "payroll_snapshot_checksum",
                "sdoo.cn.payroll-summary-source.v1",
            ),
            (
                "filing_snapshot_json",
                "filing_snapshot_checksum",
                "sdoo.cn.iit-withholding-source.v1",
            ),
            (
                "payment_snapshot_json",
                "payment_snapshot_checksum",
                "sdoo.cn.iit-payment-source.v1",
            ),
        )
        invalid_snapshots = []
        for json_field, checksum_field, schema in snapshots:
            snapshot = run[json_field]
            if (
                not isinstance(snapshot, dict)
                or snapshot.get("schema") != schema
                or _json_checksum(snapshot) != run[checksum_field]
            ):
                invalid_snapshots.append(json_field)
        if invalid_snapshots:
            raise UserError(
                _(
                    "个人所得税工资账表款勾稽快照完整性异常：%(fields)s。",
                    fields=", ".join(invalid_snapshots),
                )
            )
        if (
            not run.result_checksum
            or run._current_result_checksum() != run.result_checksum
        ):
            raise UserError(_("个人所得税工资账表款勾稽结果完整性异常。"))

        issues = run.issue_ids.sudo()
        blocking_count = len(
            issues.filtered(lambda issue: issue.severity == "blocking")
        )
        difference_count = len(
            issues.filtered(lambda issue: issue.issue_kind == "difference")
        )
        warning_count = len(
            issues.filtered(
                lambda issue: issue.severity == "review"
                and issue.issue_kind != "difference"
            )
        )
        expected_conclusion = (
            "insufficient_data"
            if blocking_count
            else "differences"
            if difference_count
            else "aligned"
        )
        expected = {
            "issue_count": len(issues),
            "blocking_issue_count": blocking_count,
            "difference_issue_count": difference_count,
            "warning_issue_count": warning_count,
            "conclusion_state": expected_conclusion,
            "payment_record_count": len(run.payment_record_ids),
        }
        inconsistent = [
            field_name
            for field_name, expected_value in expected.items()
            if run[field_name] != expected_value
        ]
        inconsistent.extend(
            field_name
            for field_name in (
                "accounting_scope_state",
                "accounting_source_state",
                "payroll_source_state",
                "filing_source_state",
                "payment_source_state",
            )
            if run[field_name] == "not_evaluated"
        )
        for state_field, count_field in (
            ("payroll_source_state", "payroll_record_count"),
            ("filing_source_state", "filing_record_count"),
            ("payment_source_state", "payment_record_count"),
        ):
            if run[count_field] < 0:
                inconsistent.append(count_field)
            if run[state_field] == "available" and run[count_field] < 1:
                inconsistent.append(count_field)
            if run[state_field] == "no_data" and run[count_field] != 0:
                inconsistent.append(count_field)
        if inconsistent:
            raise UserError(
                _(
                    "个人所得税工资账表款勾稽当前结果计数或状态不一致：%(fields)s。",
                    fields=", ".join(sorted(set(inconsistent))),
                )
            )

        amount_fields = (
            "ledger_payroll_expense_amount",
            "ledger_employee_payable_accrual_amount",
            "ledger_employee_payable_settlement_amount",
            "ledger_iit_accrual_amount",
            "ledger_iit_settlement_amount",
            "payroll_gross_income_amount",
            "payroll_withheld_iit_amount",
            "filing_income_amount",
            "filing_tax_calculated_amount",
            "filing_payable_refundable_amount",
            "filing_payable_amount",
            "filing_refundable_amount",
            "paid_principal_amount",
            "reversed_principal_amount",
            "effective_paid_principal_amount",
            "refunded_principal_amount",
            "interest_amount",
            "penalty_amount",
        )
        provided_fields = {
            field_name.removeprefix("has_"): field_name
            for field_name in (
                "has_ledger_payroll_expense_amount",
                "has_ledger_employee_payable_accrual_amount",
                "has_ledger_employee_payable_settlement_amount",
                "has_ledger_iit_accrual_amount",
                "has_ledger_iit_settlement_amount",
                "has_payroll_gross_income_amount",
                "has_payroll_withheld_iit_amount",
                "has_filing_income_amount",
                "has_filing_tax_calculated_amount",
                "has_filing_payable_refundable_amount",
                "has_filing_payable_amount",
                "has_filing_refundable_amount",
                "has_payment_amount",
                "has_refund_amount",
            )
        }
        payment_fields = {
            "paid_principal_amount",
            "reversed_principal_amount",
            "effective_paid_principal_amount",
            "interest_amount",
            "penalty_amount",
        }
        for field_name in payment_fields:
            provided_fields[field_name] = "has_payment_amount"
        provided_fields["refunded_principal_amount"] = "has_refund_amount"
        amounts = {
            field_name: (
                self._amount_snapshot(run.currency_id, run[field_name])
                if run[provided_fields[field_name]]
                else None
            )
            for field_name in amount_fields
        }
        difference_fields = (
            "ledger_payroll_difference",
            "employee_payable_payroll_difference",
            "filing_payroll_income_difference",
            "filing_payroll_iit_difference",
            "ledger_payroll_iit_difference",
            "ledger_payment_difference",
            "payable_payment_difference",
            "refundable_refund_difference",
        )
        detail = {
            "schema": "sdoo.cn.reconciliation.iit-period.fact.v1",
            "run_id": run.id,
            "engine_version": run.engine_version,
            "period_start": fields.Date.to_string(run.period_start),
            "period_end": fields.Date.to_string(run.period_end),
            "iit_tax_type_code": run.iit_tax_type_code,
            "conclusion_state": run.conclusion_state,
            "source_states": {
                "accounting_scope": run.accounting_scope_state,
                "accounting": run.accounting_source_state,
                "payroll": run.payroll_source_state,
                "filing": run.filing_source_state,
                "payment": run.payment_source_state,
            },
            "counts": {
                "accounting_scope_lines": len(
                    run.accounting_scope_snapshot_json.get("lines", [])
                ),
                "posted_accounting_lines": run.posted_accounting_line_count,
                "draft_accounting_lines": run.draft_accounting_line_count,
                "payroll_records": run.payroll_record_count,
                "filing_records": run.filing_record_count,
                "payment_records": run.payment_record_count,
                "payroll_persons": (
                    run.payroll_person_count
                    if run.has_payroll_person_count
                    else None
                ),
                "filing_persons": (
                    run.filing_person_count
                    if run.has_filing_person_count
                    else None
                ),
                "issues": run.issue_count,
                "blocking": run.blocking_issue_count,
                "differences": run.difference_issue_count,
                "warnings": run.warning_issue_count,
            },
            "amounts": amounts,
            "differences": {
                field_name: (
                    self._amount_snapshot(run.currency_id, run[field_name])
                    if run[f"has_{field_name}"]
                    else None
                )
                for field_name in difference_fields
            },
            "issues": [
                {
                    "id": issue.id,
                    "code": issue.code,
                    "severity": issue.severity,
                    "kind": issue.issue_kind,
                    "source_area": issue.source_area,
                    "affected_record_count": issue.affected_record_count,
                    "difference": (
                        self._amount_snapshot(
                            run.currency_id, issue.difference_amount
                        )
                        if issue.has_difference
                        else None
                    ),
                    "count_comparison": (
                        {
                            "left": issue.left_count,
                            "right": issue.right_count,
                            "difference": issue.count_difference,
                        }
                        if issue.has_count_comparison
                        else None
                    ),
                }
                for issue in issues.sorted(
                    lambda issue: (issue.sequence, issue.code, issue.id)
                )
            ],
            "checksums": {
                "accounting_scope": run.accounting_scope_snapshot_checksum,
                "accounting": run.accounting_snapshot_checksum,
                "payroll": run.payroll_snapshot_checksum,
                "filing": run.filing_snapshot_checksum,
                "payment": run.payment_snapshot_checksum,
                "result": run.result_checksum,
            },
        }
        return payload, detail

    def _provide_cn_iit_reconciliation_value(self, assessment, value_getter):
        payload, detail = self._cn_iit_reconciliation_snapshot(assessment)
        payload["value"] = value_getter(detail) if detail else None
        return payload

    def _provide_cn_iit_reconciliation_conclusion_state(
        self, assessment, _definition
    ):
        return self._provide_cn_iit_reconciliation_value(
            assessment, lambda detail: detail["conclusion_state"]
        )

    def _provide_cn_iit_reconciliation_blocking_count(
        self, assessment, _definition
    ):
        return self._provide_cn_iit_reconciliation_value(
            assessment, lambda detail: detail["counts"]["blocking"]
        )

    def _provide_cn_iit_reconciliation_difference_count(
        self, assessment, _definition
    ):
        return self._provide_cn_iit_reconciliation_value(
            assessment, lambda detail: detail["counts"]["differences"]
        )

    def _provide_cn_iit_reconciliation_warning_count(
        self, assessment, _definition
    ):
        return self._provide_cn_iit_reconciliation_value(
            assessment, lambda detail: detail["counts"]["warnings"]
        )

    def _provide_cn_iit_reconciliation_detail(self, assessment, _definition):
        return self._provide_cn_iit_reconciliation_value(
            assessment, lambda detail: detail
        )

    def _provide_cn_iit_reconciliation_risk_summary(
        self, assessment, _definition
    ):
        return self._provide_cn_iit_reconciliation_value(
            assessment,
            lambda detail: self._cn_reconciliation_risk_summary(
                detail,
                "sdoo.cn.reconciliation.iit-risk-summary.v1",
                (
                    "ledger_payroll_expense_amount",
                    "payroll_gross_income_amount",
                    "filing_income_amount",
                    "filing_tax_calculated_amount",
                    "filing_payable_amount",
                    "effective_paid_principal_amount",
                    "filing_refundable_amount",
                    "refunded_principal_amount",
                ),
                {
                    "blocked": "resolve_iit_source_scope_or_person_count_blockers",
                    "difference_review_required": (
                        "review_iit_payroll_filing_payment_differences"
                    ),
                    "aligned_with_disclosure_required": (
                        "review_iit_warnings_and_disclose_scope_limits"
                    ),
                    "aligned": "retain_iit_snapshots_and_continue_monitoring",
                },
            ),
        )

    @staticmethod
    def _cross_border_transaction_domain(assessment):
        domain = [("profile_id", "=", assessment.profile_id.id)]
        if assessment.period_start:
            domain.append(("transaction_date", ">=", assessment.period_start))
        if assessment.period_end:
            domain.append(("transaction_date", "<=", assessment.period_end))
        return domain

    def _cn_cross_border_transactions(self, assessment):
        domain = self._cross_border_transaction_domain(assessment)
        return (
            self.env["sudo.cn.cross.border.transaction"]
            .sudo()
            .with_company(assessment.company_id)
            .search(domain, order="transaction_date, id")
        ), domain

    def _cn_cross_border_fact_payload(self, assessment):
        transactions, domain = self._cn_cross_border_transactions(assessment)
        state_counts = Counter(transactions.mapped("state"))
        type_counts = Counter(transactions.mapped("transaction_type"))
        pending = transactions.filtered(
            lambda transaction: transaction.state in ("draft", "submitted")
        )
        reviewed = transactions.filtered(
            lambda transaction: transaction.state == "reviewed"
        )
        detail = {
            "schema": "sdoo.cn.cross-border-facts.v1",
            "profile_id": assessment.profile_id.id,
            "company_id": assessment.company_id.id,
            "period_start": fields.Date.to_string(assessment.period_start),
            "period_end": fields.Date.to_string(assessment.period_end),
            "transaction_count": len(transactions),
            "pending_review_count": len(pending),
            "reviewed_transaction_count": len(reviewed),
            "state_counts": dict(sorted(state_counts.items())),
            "transaction_type_counts": dict(sorted(type_counts.items())),
            "pending_transaction_ids": pending.ids,
            "reviewed_snapshot_checksums": sorted(
                reviewed.mapped("snapshot_checksum")
            ),
            "related_party_count": len(
                transactions.filtered(lambda transaction: transaction.related_party)
            ),
            "withholding_not_considered_count": len(
                transactions.filtered(
                    lambda transaction: not transaction.withholding_considered
                )
            ),
        }
        return transactions, domain, detail

    def _provide_cn_cross_border_pending_review_count(
        self, assessment, _definition
    ):
        transactions, domain, detail = self._cn_cross_border_fact_payload(
            assessment
        )
        return {
            "value": detail["pending_review_count"],
            "source_model": "sudo.cn.cross.border.transaction",
            "source_record_ids": transactions.ids,
            "source_domain": domain,
            "record_count": len(transactions),
            "aggregation_method": "controlled_cross_border_period_register",
            "is_complete": bool(assessment.period_start and assessment.period_end),
            "is_full_dataset": True,
            "provider_version": "1",
        }

    def _provide_cn_cross_border_reviewed_transaction_count(
        self, assessment, _definition
    ):
        transactions, domain, detail = self._cn_cross_border_fact_payload(
            assessment
        )
        return {
            "value": detail["reviewed_transaction_count"],
            "source_model": "sudo.cn.cross.border.transaction",
            "source_record_ids": transactions.ids,
            "source_domain": domain,
            "record_count": len(transactions),
            "aggregation_method": "controlled_cross_border_period_register",
            "is_complete": bool(assessment.period_start and assessment.period_end),
            "is_full_dataset": True,
            "provider_version": "1",
        }

    def _provide_cn_cross_border_detail(self, assessment, _definition):
        transactions, domain, detail = self._cn_cross_border_fact_payload(
            assessment
        )
        return {
            "value": detail,
            "source_model": "sudo.cn.cross.border.transaction",
            "source_record_ids": transactions.ids,
            "source_domain": domain,
            "record_count": len(transactions),
            "aggregation_method": "controlled_cross_border_period_register",
            "checksum": _json_checksum(detail),
            "is_complete": bool(assessment.period_start and assessment.period_end),
            "is_full_dataset": True,
            "provider_version": "1",
        }

    def _taxpayer_classifications(self, assessment):
        classifications = self.env[
            "sudo.cn.taxpayer.classification"
        ]._for_profile_date(
            assessment.profile_id,
            fields.Date.to_date(assessment.evaluation_date),
        )
        if len(classifications) > 1:
            raise UserError(
                _("评估日存在多份中国纳税人身份快照，无法确定唯一身份。")
            )
        return classifications

    @staticmethod
    def _classification_control_state(classification):
        if classification.state != "verified":
            return "draft"
        return classification._current_integrity_state()

    def _provide_cn_taxpayer_classification_verified(
        self, assessment, _definition
    ):
        classifications = self._taxpayer_classifications(assessment)
        if not classifications:
            return {
                "value": None,
                "source_model": "sudo.cn.taxpayer.classification",
                "source_domain": [
                    ("profile_id", "=", assessment.profile_id.id)
                ],
                "record_count": 0,
                "aggregation_method": "single_effective_verified_snapshot",
                "quality_state": "missing",
                "is_complete": False,
                "is_full_dataset": True,
                "provider_version": "1",
            }
        control_state = self._classification_control_state(classifications)
        return {
            "value": control_state == "verified",
            "source_model": classifications._name,
            "source_record_ids": classifications.ids,
            "record_count": 1,
            "aggregation_method": "single_effective_verified_snapshot",
            "is_complete": True,
            "is_full_dataset": True,
            "provider_version": "1",
        }

    def _provide_cn_taxpayer_classification_detail(
        self, assessment, _definition
    ):
        classifications = self._taxpayer_classifications(assessment)
        if not classifications:
            return {
                "value": {"control_state": "missing"},
                "source_model": "sudo.cn.taxpayer.classification",
                "source_domain": [
                    ("profile_id", "=", assessment.profile_id.id)
                ],
                "record_count": 0,
                "aggregation_method": "single_effective_snapshot_detail",
                "quality_state": "missing",
                "is_complete": False,
                "is_full_dataset": True,
                "provider_version": "1",
            }
        control_state = self._classification_control_state(classifications)
        return {
            "value": {
                "control_state": control_state,
                "valid_from": fields.Date.to_string(
                    classifications.valid_from
                ),
                "valid_to": fields.Date.to_string(classifications.valid_to),
                "province_code": classifications.province_id.code or None,
                "local_jurisdiction_code": (
                    classifications.local_jurisdiction_code
                ),
                "vat_taxpayer_status": (
                    classifications.vat_taxpayer_status
                ),
                "vat_filing_frequency": (
                    classifications.vat_filing_frequency
                ),
                "cit_taxpayer_status": (
                    classifications.cit_taxpayer_status
                ),
                "cit_collection_method": (
                    classifications.cit_collection_method
                ),
                "pit_withholding_status": (
                    classifications.pit_withholding_status
                ),
                "accounting_regime": classifications.accounting_regime,
                "source_type": classifications.source_type,
                "evidence_count": len(
                    classifications.evidence_attachment_ids
                ),
            },
            "source_model": classifications._name,
            "source_record_ids": classifications.ids,
            "record_count": 1,
            "aggregation_method": "single_effective_snapshot_detail",
            "is_complete": True,
            "is_full_dataset": True,
            "provider_version": "1",
        }

    @staticmethod
    def _registration_type(registration):
        return (registration.registration_type or "").strip().lower()

    def _uscc_registrations(self, assessment):
        target = fields.Date.to_date(assessment.evaluation_date)
        return assessment.profile_id.registration_ids.filtered(
            lambda registration: (
                self._registration_type(registration)
                in USCC_REGISTRATION_TYPES
                and registration.state == "active"
                and (
                    not registration.valid_from
                    or registration.valid_from <= target
                )
                and (
                    not registration.valid_to
                    or registration.valid_to >= target
                )
            )
        )

    @staticmethod
    def _company_registration_fallback(company):
        for record in (company, company.partner_id):
            for field_name in ("company_registry", "vat"):
                if field_name not in record._fields:
                    continue
                value = record[field_name]
                if value and str(value).strip():
                    return record, str(value).strip()
        return company.env["res.company"], False

    def _provide_cn_unified_social_credit_code(self, assessment, _definition):
        registrations = self._uscc_registrations(assessment)
        numbered = registrations.filtered(
            lambda registration: bool(
                registration.registration_number
                and registration.registration_number.strip()
            )
        )
        if len(numbered) > 1:
            raise UserError(_("存在多个同时有效的统一社会信用代码登记记录。"))
        if numbered:
            return {
                "value": numbered.registration_number.strip(),
                "source_model": numbered._name,
                "source_record_ids": numbered.ids,
                "record_count": 1,
                "aggregation_method": "single_active_controlled_registration",
                "is_complete": True,
                "is_full_dataset": True,
                "provider_version": "1",
            }

        source, fallback = self._company_registration_fallback(
            assessment.company_id
        )
        if fallback:
            return {
                "value": fallback,
                "source_model": source._name,
                "source_record_ids": source.ids,
                "record_count": 1,
                "aggregation_method": "uncontrolled_company_identifier_fallback",
                "quality_state": "truncated",
                "is_complete": False,
                "is_full_dataset": True,
                "provider_version": "1",
            }
        return {
            "value": None,
            "source_model": "sudo.compliance.registration",
            "source_domain": [("profile_id", "=", assessment.profile_id.id)],
            "record_count": len(registrations),
            "aggregation_method": "active_controlled_registration",
            "quality_state": "missing",
            "is_complete": False,
            "is_full_dataset": True,
            "provider_version": "1",
        }

    def _provide_cn_registration_evidence_count(self, assessment, _definition):
        registrations = self._uscc_registrations(assessment)
        if len(registrations) > 1:
            raise UserError(_("存在多个同时有效的统一社会信用代码登记记录。"))
        if not registrations:
            return {
                "value": None,
                "source_model": "sudo.compliance.registration",
                "source_domain": [
                    ("profile_id", "=", assessment.profile_id.id)
                ],
                "record_count": 0,
                "aggregation_method": "registration_attachment_clue_count",
                "quality_state": "missing",
                "is_complete": False,
                "is_full_dataset": True,
                "provider_version": "1",
            }
        count = len(registrations.evidence_attachment_ids)
        return {
            "value": count,
            "source_model": registrations._name,
            "source_record_ids": registrations.ids,
            "record_count": len(registrations),
            "aggregation_method": "registration_attachment_clue_count",
            "quality_state": "complete" if count else "missing",
            "is_complete": bool(count),
            "is_full_dataset": True,
            "provider_version": "1",
        }

    def _provide_cn_fiscal_year_end_confirmed(self, assessment, _definition):
        profile = assessment.profile_id
        try:
            date(2024, profile.fiscal_year_end_month, profile.fiscal_year_end_day)
        except (TypeError, ValueError):
            return {
                "value": None,
                "source_model": profile._name,
                "source_record_ids": profile.ids,
                "record_count": 1,
                "aggregation_method": "validated_confirmed_profile_fields",
                "quality_state": "error",
                "is_complete": False,
                "is_full_dataset": True,
                "provider_version": "1",
            }
        return {
            "value": bool(profile.fiscal_year_end_confirmed),
            "source_model": profile._name,
            "source_record_ids": profile.ids,
            "record_count": 1,
            "aggregation_method": "validated_confirmed_profile_fields",
            "is_complete": True,
            "is_full_dataset": True,
            "provider_version": "1",
        }

    @staticmethod
    def _move_domain(assessment, states=None, move_types=None):
        domain = [("company_id", "=", assessment.company_id.id)]
        if states:
            domain.append(("state", "in", states))
        if move_types:
            domain.append(("move_type", "in", move_types))
        if assessment.period_start:
            domain.append(("date", ">=", assessment.period_start))
        if assessment.period_end:
            domain.append(("date", "<=", assessment.period_end))
        return domain

    def _move_count_payload(self, assessment, states=None, move_types=None):
        domain = self._move_domain(assessment, states, move_types)
        count = (
            self.env["account.move"]
            .with_company(assessment.company_id)
            .search_count(domain)
        )
        return {
            "value": count,
            "source_model": "account.move",
            "source_domain": domain,
            "record_count": count,
            "aggregation_method": "search_count_full_domain",
            "is_complete": True,
            "is_full_dataset": True,
            "provider_version": "1",
        }

    def _provide_cn_posted_move_count(self, assessment, _definition):
        return self._move_count_payload(assessment, states=["posted"])

    def _provide_cn_unposted_move_count(self, assessment, _definition):
        return self._move_count_payload(assessment, states=["draft"])

    def _provide_cn_posted_invoice_count(self, assessment, _definition):
        return self._move_count_payload(
            assessment,
            states=["posted"],
            move_types=INVOICE_MOVE_TYPES,
        )

    def _provide_cn_ledger_basis_detail(self, assessment, _definition):
        domain = self._move_domain(assessment)
        moves = (
            self.env["account.move"]
            .with_company(assessment.company_id)
            .search(domain, order="date, id")
        )
        posted = moves.filtered(lambda move: move.state == "posted")
        draft = moves.filtered(lambda move: move.state == "draft")
        posted_invoices = posted.filtered(
            lambda move: move.move_type in INVOICE_MOVE_TYPES
        )
        move_types = Counter(moves.mapped("move_type"))
        dates = [move.date for move in moves if move.date]
        detail = {
            "schema": "sdoo.cn.accounting-ledger-basis.v1",
            "company_id": assessment.company_id.id,
            "period_start": fields.Date.to_string(assessment.period_start)
            if assessment.period_start
            else None,
            "period_end": fields.Date.to_string(assessment.period_end)
            if assessment.period_end
            else None,
            "counts": {
                "total_moves": len(moves),
                "posted_moves": len(posted),
                "draft_moves": len(draft),
                "posted_invoices": len(posted_invoices),
            },
            "date_coverage": {
                "first_move_date": fields.Date.to_string(min(dates))
                if dates
                else None,
                "last_move_date": fields.Date.to_string(max(dates))
                if dates
                else None,
            },
            "move_type_counts": dict(sorted(move_types.items())),
        }
        return {
            "value": detail,
            "source_model": "account.move",
            "source_domain": domain,
            "source_record_ids": moves.ids[:2000],
            "record_count": len(moves),
            "aggregation_method": "full_period_ledger_basis_summary",
            "is_complete": True,
            "is_full_dataset": len(moves) <= 2000,
            "quality_state": "complete" if len(moves) <= 2000 else "truncated",
            "provider_version": "1",
        }

    def _provide_cn_invoice_missing_attachment_count(
        self, assessment, _definition
    ):
        domain = self._move_domain(
            assessment,
            states=["posted"],
            move_types=INVOICE_MOVE_TYPES,
        )
        moves = (
            self.env["account.move"]
            .with_company(assessment.company_id)
            .search(domain)
        )
        attached_move_ids = set(
            self.env["ir.attachment"]
            .sudo()
            .search(
                [
                    ("res_model", "=", "account.move"),
                    ("res_id", "in", moves.ids),
                    ("res_field", "=", False),
                    ("type", "=", "binary"),
                ]
            )
            .mapped("res_id")
        )
        missing_count = len(moves) - len(attached_move_ids)
        return {
            "value": missing_count,
            "source_model": "account.move",
            "source_domain": domain,
            "record_count": missing_count,
            "aggregation_method": "full_domain_attachment_antijoin",
            "is_complete": True,
            "is_full_dataset": True,
            "provider_version": "1",
        }

    @staticmethod
    def _line_period_domain(assessment):
        domain = [("company_id", "=", assessment.company_id.id)]
        if assessment.period_start:
            domain.append(("date", ">=", assessment.period_start))
        if assessment.period_end:
            domain.append(("date", "<=", assessment.period_end))
        return domain

    def _provide_cn_posted_invoice_line_without_tax_count(
        self, assessment, _definition
    ):
        domain = self._line_period_domain(assessment) + [
            ("parent_state", "=", "posted"),
            ("move_id.move_type", "in", INVOICE_MOVE_TYPES),
            ("tax_ids", "=", False),
            (
                "account_id.account_type",
                "in",
                (
                    "income",
                    "income_other",
                    "expense",
                    "expense_depreciation",
                    "expense_direct_cost",
                ),
            ),
        ]
        count = (
            self.env["account.move.line"]
            .with_company(assessment.company_id)
            .search_count(domain)
        )
        return {
            "value": count,
            "source_model": "account.move.line",
            "source_domain": domain,
            "record_count": count,
            "aggregation_method": "full_period_posted_invoice_tax_antijoin",
            "is_complete": True,
            "is_full_dataset": True,
            "provider_version": "1",
        }

    def _provide_cn_transaction_partner_missing_tax_id_count(
        self, assessment, _definition
    ):
        domain = self._move_domain(
            assessment,
            states=["posted"],
            move_types=INVOICE_MOVE_TYPES,
        )
        moves = (
            self.env["account.move"]
            .with_company(assessment.company_id)
            .search(domain)
        )
        partners = moves.mapped("commercial_partner_id")
        missing = partners.filtered(lambda partner: not partner.vat)
        return {
            "value": len(missing),
            "source_model": "res.partner",
            "source_record_ids": missing.ids,
            "source_domain": [("id", "in", partners.ids)],
            "record_count": len(missing),
            "aggregation_method": "transaction_partner_tax_id_presence_signal",
            "is_complete": True,
            "is_full_dataset": True,
            "provider_version": "1",
        }
