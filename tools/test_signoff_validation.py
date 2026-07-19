from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def load_tool(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


PACKET = load_tool(
    "cn_signoff_packet",
    REPOSITORY_ROOT / "tools" / "generate_cn_signoff_packet.py",
)
VALIDATION = load_tool(
    "cn_signoff_validation",
    REPOSITORY_ROOT / "tools" / "validate_cn_signoff_evidence.py",
)
SUMMARY = load_tool(
    "cn_delivery_status",
    REPOSITORY_ROOT / "tools" / "summarize_cn_delivery_status.py",
)
OBJECTIVE_AUDIT = load_tool(
    "cn_objective_audit",
    REPOSITORY_ROOT / "tools" / "audit_cn_objective_completion.py",
)
RENDER_EVIDENCE = load_tool(
    "cn_render_signoff_evidence",
    REPOSITORY_ROOT / "tools" / "render_cn_signoff_evidence_template.py",
)
SIGNOFF_CHAIN = load_tool(
    "cn_signoff_chain",
    REPOSITORY_ROOT / "tools" / "build_cn_signoff_evidence_chain.py",
)
SIGNOFF_ACTIONS = load_tool(
    "cn_production_signoff_actions",
    REPOSITORY_ROOT / "tools" / "export_cn_production_signoff_actions.py",
)
ADDON_VALIDATION = load_tool(
    "cn_addon_validation",
    REPOSITORY_ROOT / "tools" / "validate_addon.py",
)


def status_payload() -> dict:
    return {
        "version": "19.0.1.130.0",
        "version_consistent": True,
        "acceptance_passed": True,
        "runtime_passed": True,
        "upgrade_runtime_passed": True,
        "preview_url": "http://127.0.0.1:18070/web/login?db=test",
        "source_control": {
            "inside_worktree": True,
            "branch": "main",
            "commit": "abc123",
            "dirty": False,
        },
        "readiness_gates": {
            "business_uat_ready": True,
            "source_control_clean": True,
            "business_uat_blockers": [],
            "production_signoff_blockers": [
                "business UAT decision must be recorded outside this automated status",
            ],
        },
        "runtime": {"log": {"failed": 0, "errors": 0}},
        "upgrade_runtime": {
            "requested": True,
            "database": "test",
            "install": False,
            "http_port": 18071,
            "log": {"failed": 0, "errors": 0},
        },
        "preview_health": {"ok": True, "url": "http://127.0.0.1:18070/web/login?db=test"},
        "preview_module": {"ok": True, "module_installed_version": "19.0.1.130.0"},
        "upgrade_migration_chain": {
            "ready": True,
            "module_manifest": "addons/sudo_country_pack_cn/__manifest__.py",
            "module_manifest_included": True,
            "validator": "tools/validate_addon.py",
            "validator_included": True,
            "current_version": "19.0.1.130.0",
            "current_migration": (
                "addons/sudo_country_pack_cn/migrations/"
                "19.0.1.130.0/post-migration.py"
            ),
            "current_migration_included": True,
            "migration_script_count": 120,
            "packaged_migration_versions": ["19.0.1.129.0", "19.0.1.130.0"],
        },
        "uat_walkthrough": {
            "path": "docs/CHINA_UAT_WALKTHROUGH_SCRIPT.md",
            "included_in_manifest": True,
        },
        "release_handoff": {
            "path": "docs/CHINA_RELEASE_HANDOFF_CURRENT.md",
            "included_in_manifest": True,
        },
        "production_release_control": {
            "path": "docs/CHINA_PRODUCTION_RELEASE_CONTROL.md",
            "included_in_manifest": True,
        },
        "signoff_evidence_template": {
            "path": "docs/samples/cn_signoff_evidence_template.json",
            "included_in_manifest": True,
        },
        "signoff_evidence_renderer_tool": {
            "path": "tools/render_cn_signoff_evidence_template.py",
            "included_in_manifest": True,
        },
        "objective_audit_tool": {
            "path": "tools/audit_cn_objective_completion.py",
            "included_in_manifest": True,
        },
        "objective_audit": {
            "schema": "sdoo.cn.objective-completion-audit.v1",
            "version": "19.0.1.130.0",
            "source_commit": "abc123",
            "preview_url": "http://127.0.0.1:18070/web/login?db=test",
            "achieved": False,
            "state_counts": {"evidence_ready": 12, "blocked": 1, "not_ready": 0},
            "completion_blockers": [
                "business UAT decision must be recorded outside this automated status"
            ],
        },
        "source_governance_summary": {
            "ready": True,
            "source_count": 1,
            "sample_source_count": 1,
            "valid_source_count": 1,
            "active_rule_version_count": 1,
            "sample_rule_version_count": 1,
            "monitor_run_count": 0,
            "overdue_source_count": 0,
            "changed_monitor_run_count": 0,
            "failed_monitor_run_count": 0,
            "unapproved_rule_version_count": 0,
            "latest_sample_source": "CODEX-DEMO China VAT source",
            "latest_sample_source_next_review_date": "2027-07-15",
            "latest_monitor_state": "never",
            "boundary": (
                "Automated evidence summarizes packaged source governance only; "
                "production still requires current official-source review and "
                "China tax professional sign-off."
            ),
        },
        "real_data_closed_loop": {
            "ok": True,
            "objects": {
                "vat_reconciliation_runs": 1,
                "vat_filing_records": 1,
                "tax_payment_records": 2,
                "cit_reconciliation_runs": 1,
                "cit_filing_records": 1,
                "active_profile_iit_reconciliation_runs": 1,
                "iit_withholding_records": 1,
                "payroll_summary_records": 1,
                "active_profile_cross_border_transactions": 1,
            },
            "readiness": {
                "closed_loop_evidence_ready": True,
                "has_workbench_summary_evidence": True,
                "has_risk_task_report_summary_evidence": True,
                "has_risk_finding_visibility_evidence": True,
                "has_remediation_task_visibility_evidence": True,
                "has_remediation_verification_rescan_evidence": True,
                "has_report_visibility_evidence": True,
                "has_reviewer_view_contract_evidence": True,
                "has_evidence_filing_payment_summary_evidence": True,
                "has_controlled_ai_guidance_evidence": True,
                "has_rule_source_governance_evidence": True,
                "has_official_source_freshness_evidence": True,
                "has_rule_professional_signoff_evidence": True,
                "has_rule_checksum_traceability_evidence": True,
                "has_customer_scope_gap_review_evidence": True,
                "has_customer_data_scope_review_evidence": True,
                "has_customer_evidence_gap_review_evidence": True,
                "has_open_high_risk_review_evidence": True,
                "has_iit_payroll_withholding_scope_evidence": True,
                "has_cross_border_review_scope_evidence": True,
                "has_multi_company_security_contract_evidence": True,
                "has_menu_action_contract_evidence": True,
                "has_workbench_action_contract_evidence": True,
                "has_ux_view_clarity_contract_evidence": True,
            },
            "sample_profiles": [
                {
                    "name": "CN Demo",
                    "action_summary": "Next: Review the ready compliance report package",
                    "rule_basis_summary": "Rules are current.",
                    "limitation_summary": "No explicit conclusion limitation is currently recorded.",
                    "uncertainty_summary": "No open uncertainty driver is currently recorded.",
                }
            ],
            "sample_findings": [
                {
                    "title": "VAT filing mismatch",
                    "company": "CN Company",
                    "period_label": "2026-06",
                    "risk_level": "high",
                    "result": "fail",
                    "review_state": "correction_required",
                    "tax_impact": "Reviewed underpayment 100.00",
                    "rule_basis_state": "ready",
                    "professional_state": "approved",
                    "evidence_state": "verified",
                    "closure_state": "action_required",
                    "closure_summary": "Blocked before sign-off: human review.",
                    "next_action": "Review remediation and rescan.",
                    "action_summary": "High risk; owner must verify remediation.",
                }
            ],
            "sample_remediation_tasks": [
                {
                    "name": "Correct VAT filing mismatch",
                    "company": "CN Company",
                    "risk_level": "high",
                    "state": "done",
                    "verification_state": "verified",
                    "assignee": "Reviewer",
                    "due_date": "2026-07-31",
                    "evidence_state": "verified",
                    "evidence_count": 1,
                    "verified_evidence_count": 1,
                    "rescan_stage": "verified",
                    "traceability_state": "complete",
                    "next_action": "Keep evidence sealed.",
                    "action_summary": "Verified remediation task with evidence.",
                }
            ],
            "sample_reports": [
                {
                    "name": "CN Compliance Report",
                    "company": "CN Company",
                    "period_start": "2026-06-01",
                    "period_end": "2026-06-30",
                    "state": "issued",
                    "conclusion_state": "action_required",
                    "traceability_state": "complete",
                    "fact_basis_state": "ready",
                    "center_integrity_state": "complete",
                    "snapshot_integrity_state": "verified",
                    "approval_integrity_state": "verified",
                    "pdf_integrity_state": "verified",
                    "traceability_next_action": "Archive issued report evidence.",
                }
            ],
            "reviewer_view_contracts": [
                {
                    "xml_id": "view_cn_risk_center_finding_list",
                    "ready": True,
                    "missing": [],
                    "required_fields": [
                        "risk_level",
                        "cn_risk_period_label",
                        "cn_risk_next_action",
                    ],
                }
            ],
            "ux_view_clarity_contracts": [
                {
                    "xml_id": "view_cn_risk_center_finding_kanban",
                    "ready": True,
                    "missing_fields": [],
                    "missing_snippets": [],
                    "required_fields": [
                        "risk_level",
                        "cn_risk_next_action",
                        "cn_tax_impact_reviewed_underpayment_amount",
                        "task_assignee_id",
                        "task_due_date",
                    ],
                    "required_snippets": [
                        'widget="badge"',
                        "border-start border-4",
                        "Tax impact",
                    ],
                }
            ],
            "multi_company_security_contracts": [
                {
                    "model": "sudo.cn.external.dataset",
                    "ready": True,
                    "rule_count": 1,
                    "rules": [
                        {
                            "name": "China external datasets: allowed companies",
                            "domain": "[('company_id', 'in', company_ids)]",
                            "groups": [
                                "sudo_global_finance.group_compliance_user"
                            ],
                        }
                    ],
                }
            ],
            "menu_action_contracts": [
                {
                    "menu_xml_id": "menu_cn_risk_center",
                    "action_xml_id": "action_cn_risk_center",
                    "res_model": "sudo.compliance.finding",
                    "ready": True,
                    "action_matches": True,
                    "missing_groups": [],
                    "groups": ["sudo_global_finance.group_compliance_user"],
                }
            ],
            "workbench_action_contracts": [
                {
                    "method": "action_cn_open_workbench_findings",
                    "res_model": "sudo.compliance.finding",
                    "ready": True,
                    "action_type": "ir.actions.act_window",
                    "action_res_model": "sudo.compliance.finding",
                    "view_mode": "kanban,list,form",
                    "scope_matches": True,
                    "expected_terms": [
                        ["assessment_id.profile_id", "=", 1],
                    ],
                    "domain": [
                        ["assessment_id.profile_id", "=", 1],
                        ["result", "in", ["fail", "unknown", "error"]],
                    ],
                    "context": {},
                }
            ],
            "sample_evidence": [
                {
                    "name": "VAT payment receipt",
                    "company": "CN Company",
                    "state": "verified",
                    "source_summary": "Filing: VAT June archive",
                    "blocker_summary": "No blocker: evidence is verified and traceable.",
                    "verified_by": "Reviewer",
                    "verified_at": "2026-07-18 10:00:00",
                    "document_checksum": "abc123",
                }
            ],
            "sample_filing_archives": [
                {
                    "name": "VAT June archive",
                    "company": "CN Company",
                    "kind": "vat",
                    "period_label": "2026-06-01 to 2026-06-30",
                    "state": "accepted",
                    "payment_state": "paid",
                    "due_date": "2026-07-15",
                    "submission_integrity_state": "verified",
                    "payment_integrity_state": "verified",
                    "evidence_state": "verified",
                    "evidence_count": 2,
                    "verified_evidence_count": 2,
                    "blocker_summary": "No blocker: filing, payment and evidence archive are traceable.",
                    "next_action": "Keep sealed filing and payment archive.",
                    "submission_checksum": "sub123",
                    "payment_checksum": "pay123",
                }
            ],
            "sample_ai_guidance": [
                {
                    "name": "Controlled China AI guidance",
                    "finding": "VAT filing mismatch",
                    "provider_key": "sdoo_cn_controlled_guidance",
                    "jurisdiction_code": "CN",
                    "state": "fallback",
                    "prompt_version": "cn-compliance-guidance-v1",
                    "model_name": "sdoo-cn-guidance-fallback-v1",
                    "source_warning": False,
                    "professional_warning": False,
                    "input_checksum": "input123",
                    "output_checksum": "output123",
                    "record_checksum": "record123",
                }
            ],
            "sample_authority_sources": [
                {
                    "name": "CODEX-DEMO China VAT source",
                    "status": "valid",
                    "snapshot_kind": "official_web_capture",
                    "content_hash": "sourcehash123",
                    "snapshot_attachment": "source.html",
                    "next_review_date": "2027-07-15",
                    "last_monitor_state": "never",
                    "next_monitor_date": "2026-08-01",
                }
            ],
            "sample_rule_versions": [
                {
                    "name": "CN VAT Demo Rule / 2026.1",
                    "state": "active",
                    "release_state": "active",
                    "professional_review_state": "approved",
                    "professional_ready": True,
                    "test_state": "passed",
                    "checksum": "rulehash123",
                    "source_count": 1,
                    "source_names": ["CODEX-DEMO China VAT source"],
                    "next_review_date": "2027-07-15",
                }
            ],
            "sample_source_monitor_runs": [],
            "sample_iit_reconciliation_runs": [
                {
                    "name": "CN IIT payroll withholding June run",
                    "company": "CN Company",
                    "profile": "CN Demo",
                    "period_start": "2026-06-01",
                    "period_end": "2026-06-30",
                    "state": "succeeded",
                    "conclusion_state": "aligned",
                    "result_summary": "Payroll, withholding filing and payment are aligned.",
                    "accounting_source_state": "available",
                    "payroll_source_state": "available",
                    "filing_source_state": "available",
                    "payment_source_state": "available",
                    "payroll_record_count": 1,
                    "filing_record_count": 1,
                    "payment_record_count": 1,
                    "payroll_person_count": 12,
                    "payroll_gross_income_amount": 120000.0,
                    "payroll_withheld_iit_amount": 8600.0,
                    "issue_count": 0,
                    "result_integrity_state": "verified",
                    "result_checksum": "iitresult123",
                    "payroll_snapshot_checksum": "payrollsnap123",
                    "filing_snapshot_checksum": "iitfilingsnap123",
                    "payment_snapshot_checksum": "iitpaysnap123",
                }
            ],
            "sample_cross_border_transactions": [
                {
                    "name": "2026-06 service fee cross-border review",
                    "company": "CN Company",
                    "profile": "CN Demo",
                    "period_start": "2026-06-01",
                    "period_end": "2026-06-30",
                    "transaction_date": "2026-06-18",
                    "transaction_type": "service_fee",
                    "counterparty": "US Service Provider",
                    "counterparty_country": "United States",
                    "amount": 12000.0,
                    "related_party": True,
                    "withholding_considered": True,
                    "state": "reviewed",
                    "readiness_state": "reviewed",
                    "next_action": "Use this reviewed fact in scans and report limitations.",
                    "snapshot_checksum": "crossbordersnap123",
                    "evidence_count": 1,
                }
            ],
        },
    }


def manifest_payload() -> dict:
    paths = [
        "docs/CHINA_BUSINESS_UAT_CHECKLIST.md",
        "docs/CHINA_UAT_WALKTHROUGH_SCRIPT.md",
        "docs/CHINA_RELEASE_HANDOFF_CURRENT.md",
        "docs/CHINA_CURRENT_PRODUCTION_SIGNOFF_RUNBOOK.md",
        "docs/CHINA_DELIVERY_INDEX.md",
        "docs/CHINA_DELIVERY_M138_STATUS.md",
        "docs/CHINA_DELIVERY_OBJECTIVE_COVERAGE.md",
        "docs/CHINA_PRODUCTION_SIGNOFF_TEMPLATE.md",
        "docs/CHINA_PRODUCTION_RELEASE_CONTROL.md",
        "docs/samples/cn_signoff_evidence_template.json",
        "addons/sudo_country_pack_cn/__manifest__.py",
        "addons/sudo_country_pack_cn/migrations/19.0.1.130.0/post-migration.py",
        "tools/validate_addon.py",
        "tools/check_cn_preview_health.py",
        "tools/check_cn_preview_module.py",
        "tools/check_cn_real_data_closed_loop.py",
        "tools/audit_cn_objective_completion.py",
        "tools/build_cn_signoff_evidence_chain.py",
        "tools/select_cn_latest_signoff_candidate.py",
        "tools/export_cn_production_signoff_actions.py",
        "tools/generate_cn_signoff_packet.py",
        "tools/render_cn_signoff_evidence_template.py",
        "tools/validate_cn_signoff_evidence.py",
    ]
    return {
        "schema": "sdoo.cn.delivery-manifest.v1",
        "version": "19.0.1.130.0",
        "aggregate_sha256": "aggregate",
        "files": [{"path": path} for path in paths],
    }


def manifest_without(path_to_remove: str) -> dict:
    manifest = manifest_payload()
    manifest["files"] = [
        item for item in manifest["files"] if item["path"] != path_to_remove
    ]
    return manifest


def bundle_metadata_payload() -> dict:
    return {
        "schema": "sdoo.cn.delivery-bundle.v1",
        "version": "19.0.1.130.0",
        "aggregate_sha256": "aggregate",
        "bundle_sha256": "bundle",
        "source_control": {
            "inside_worktree": True,
            "branch": "main",
            "commit": "abc123",
            "dirty": False,
        },
    }


def summary_payload() -> dict:
    return {
        "schema": "sdoo.cn.delivery-acceptance-summary.v1",
        "version": "19.0.1.130.0",
        "result": "passed",
        "runtime": {
            "database": "test",
            "log": {"failed": 0, "errors": 0},
        },
    }


def upgrade_summary_payload() -> dict:
    return {
        "schema": "sdoo.cn.delivery-acceptance-summary.v1",
        "version": "19.0.1.130.0",
        "result": "passed",
        "runtime": {
            "requested": True,
            "database": "test",
            "install": False,
            "http_port": 18071,
            "log": {"failed": 0, "errors": 0},
        },
    }


def preview_health_payload() -> dict:
    return {
        "schema": SUMMARY.PREVIEW_HEALTH_SCHEMA,
        "url": "http://127.0.0.1:18070/web/login?db=test",
        "ok": True,
        "status_code": 200,
    }


def preview_module_payload() -> dict:
    return {
        "schema": SUMMARY.PREVIEW_MODULE_SCHEMA,
        "database": "test",
        "expected_version": "19.0.1.130.0",
        "ok": True,
        "module_installed_version": "19.0.1.130.0",
        "country_pack_version": "19.0.1.130.0",
    }


def real_data_closed_loop_payload() -> dict:
    return {
        "schema": SUMMARY.REAL_DATA_CLOSED_LOOP_SCHEMA,
        "database": "test",
        "expected_version": "19.0.1.130.0",
        "ok": True,
        "objects": {
            "vat_reconciliation_runs": 1,
            "vat_filing_records": 1,
            "tax_payment_records": 2,
            "cit_reconciliation_runs": 1,
            "cit_filing_records": 1,
            "active_profile_iit_reconciliation_runs": 1,
            "iit_withholding_records": 1,
            "payroll_summary_records": 1,
            "active_profile_cross_border_transactions": 1,
        },
        "readiness": {
            "demo_ready": True,
            "closed_loop_evidence_ready": True,
            "has_workbench_summary_evidence": True,
            "has_risk_task_report_summary_evidence": True,
            "has_risk_finding_visibility_evidence": True,
            "has_remediation_task_visibility_evidence": True,
            "has_remediation_verification_rescan_evidence": True,
            "has_report_visibility_evidence": True,
            "has_reviewer_view_contract_evidence": True,
            "has_evidence_filing_payment_summary_evidence": True,
            "has_controlled_ai_guidance_evidence": True,
            "has_rule_source_governance_evidence": True,
            "has_official_source_freshness_evidence": True,
            "has_rule_professional_signoff_evidence": True,
            "has_rule_checksum_traceability_evidence": True,
            "has_customer_scope_gap_review_evidence": True,
            "has_customer_data_scope_review_evidence": True,
            "has_customer_evidence_gap_review_evidence": True,
            "has_open_high_risk_review_evidence": True,
            "has_iit_payroll_withholding_scope_evidence": True,
            "has_cross_border_review_scope_evidence": True,
            "has_multi_company_security_contract_evidence": True,
            "has_menu_action_contract_evidence": True,
            "has_workbench_action_contract_evidence": True,
            "has_ux_view_clarity_contract_evidence": True,
        },
        "sample_profiles": [
            {
                "name": "CN Demo",
                "action_summary": "Next: Review the ready compliance report package",
                "rule_basis_summary": "Rules are current.",
                "limitation_summary": "No explicit conclusion limitation is currently recorded.",
                "uncertainty_summary": "No open uncertainty driver is currently recorded.",
            }
        ],
        "sample_findings": [
            {
                "title": "VAT filing mismatch",
                "company": "CN Company",
                "period_label": "2026-06",
                "risk_level": "high",
                "result": "fail",
                "review_state": "correction_required",
                "tax_impact": "Reviewed underpayment 100.00",
                "rule_basis_state": "ready",
                "professional_state": "approved",
                "evidence_state": "verified",
                "closure_state": "action_required",
                "closure_summary": "Blocked before sign-off: human review.",
                "next_action": "Review remediation and rescan.",
                "action_summary": "High risk; owner must verify remediation.",
            }
        ],
        "sample_remediation_tasks": [
            {
                "name": "Correct VAT filing mismatch",
                "company": "CN Company",
                "risk_level": "high",
                "state": "done",
                "verification_state": "verified",
                "assignee": "Reviewer",
                "due_date": "2026-07-31",
                "evidence_state": "verified",
                "evidence_count": 1,
                "verified_evidence_count": 1,
                "rescan_stage": "verified",
                "traceability_state": "complete",
                "next_action": "Keep evidence sealed.",
                "action_summary": "Verified remediation task with evidence.",
            }
        ],
        "sample_reports": [
            {
                "name": "CN Compliance Report",
                "company": "CN Company",
                "period_start": "2026-06-01",
                "period_end": "2026-06-30",
                "state": "issued",
                "conclusion_state": "action_required",
                "traceability_state": "complete",
                "fact_basis_state": "ready",
                "center_integrity_state": "complete",
                "snapshot_integrity_state": "verified",
                "approval_integrity_state": "verified",
                "pdf_integrity_state": "verified",
                "traceability_next_action": "Archive issued report evidence.",
            }
        ],
        "reviewer_view_contracts": [
            {
                "xml_id": "view_cn_risk_center_finding_list",
                "ready": True,
                "missing": [],
                "required_fields": [
                    "risk_level",
                    "cn_risk_period_label",
                    "cn_risk_next_action",
                ],
            }
        ],
        "ux_view_clarity_contracts": [
            {
                "xml_id": "view_cn_risk_center_finding_kanban",
                "ready": True,
                "missing_fields": [],
                "missing_snippets": [],
                "required_fields": [
                    "risk_level",
                    "cn_risk_next_action",
                    "cn_tax_impact_reviewed_underpayment_amount",
                    "task_assignee_id",
                    "task_due_date",
                ],
                "required_snippets": [
                    'widget="badge"',
                    "border-start border-4",
                    "Tax impact",
                ],
            }
        ],
        "multi_company_security_contracts": [
            {
                "model": "sudo.cn.external.dataset",
                "ready": True,
                "rule_count": 1,
                "rules": [
                    {
                        "name": "China external datasets: allowed companies",
                        "domain": "[('company_id', 'in', company_ids)]",
                        "groups": [
                            "sudo_global_finance.group_compliance_user"
                        ],
                    }
                ],
            }
        ],
        "menu_action_contracts": [
            {
                "menu_xml_id": "menu_cn_risk_center",
                "action_xml_id": "action_cn_risk_center",
                "res_model": "sudo.compliance.finding",
                "ready": True,
                "action_matches": True,
                "missing_groups": [],
                "groups": ["sudo_global_finance.group_compliance_user"],
            }
        ],
        "workbench_action_contracts": [
            {
                "method": "action_cn_open_workbench_findings",
                "res_model": "sudo.compliance.finding",
                "ready": True,
                "action_type": "ir.actions.act_window",
                "action_res_model": "sudo.compliance.finding",
                "view_mode": "kanban,list,form",
                "scope_matches": True,
                "expected_terms": [
                    ["assessment_id.profile_id", "=", 1],
                ],
                "domain": [
                    ["assessment_id.profile_id", "=", 1],
                    ["result", "in", ["fail", "unknown", "error"]],
                ],
                "context": {},
            }
        ],
        "sample_evidence": [
            {
                "name": "VAT payment receipt",
                "company": "CN Company",
                "state": "verified",
                "source_summary": "Filing: VAT June archive",
                "blocker_summary": "No blocker: evidence is verified and traceable.",
                "verified_by": "Reviewer",
                "verified_at": "2026-07-18 10:00:00",
                "document_checksum": "abc123",
            }
        ],
        "sample_filing_archives": [
            {
                "name": "VAT June archive",
                "company": "CN Company",
                "kind": "vat",
                "period_label": "2026-06-01 to 2026-06-30",
                "state": "accepted",
                "payment_state": "paid",
                "due_date": "2026-07-15",
                "submission_integrity_state": "verified",
                "payment_integrity_state": "verified",
                "evidence_state": "verified",
                "evidence_count": 2,
                "verified_evidence_count": 2,
                "blocker_summary": "No blocker: filing, payment and evidence archive are traceable.",
                "next_action": "Keep sealed filing and payment archive.",
                "submission_checksum": "sub123",
                "payment_checksum": "pay123",
            }
        ],
        "sample_ai_guidance": [
            {
                "name": "Controlled China AI guidance",
                "finding": "VAT filing mismatch",
                "provider_key": "sdoo_cn_controlled_guidance",
                "jurisdiction_code": "CN",
                "state": "fallback",
                "prompt_version": "cn-compliance-guidance-v1",
                "model_name": "sdoo-cn-guidance-fallback-v1",
                "source_warning": False,
                "professional_warning": False,
                "input_checksum": "input123",
                "output_checksum": "output123",
                "record_checksum": "record123",
            }
        ],
        "sample_authority_sources": [
            {
                "name": "CODEX-DEMO China VAT source",
                "status": "valid",
                "snapshot_kind": "official_web_capture",
                "content_hash": "sourcehash123",
                "snapshot_attachment": "source.html",
                "next_review_date": "2027-07-15",
                "last_monitor_state": "never",
                "next_monitor_date": "2026-08-01",
            }
        ],
        "sample_rule_versions": [
            {
                "name": "CN VAT Demo Rule / 2026.1",
                "state": "active",
                "release_state": "active",
                "professional_review_state": "approved",
                "professional_ready": True,
                "test_state": "passed",
                "checksum": "rulehash123",
                "source_count": 1,
                "source_names": ["CODEX-DEMO China VAT source"],
                "next_review_date": "2027-07-15",
            }
        ],
        "sample_source_monitor_runs": [],
        "sample_iit_reconciliation_runs": [
            {
                "name": "CN IIT payroll withholding June run",
                "company": "CN Company",
                "profile": "CN Demo",
                "period_start": "2026-06-01",
                "period_end": "2026-06-30",
                "state": "succeeded",
                "conclusion_state": "aligned",
                "result_summary": "Payroll, withholding filing and payment are aligned.",
                "accounting_source_state": "available",
                "payroll_source_state": "available",
                "filing_source_state": "available",
                "payment_source_state": "available",
                "payroll_record_count": 1,
                "filing_record_count": 1,
                "payment_record_count": 1,
                "payroll_person_count": 12,
                "payroll_gross_income_amount": 120000.0,
                "payroll_withheld_iit_amount": 8600.0,
                "issue_count": 0,
                "result_integrity_state": "verified",
                "result_checksum": "iitresult123",
                "payroll_snapshot_checksum": "payrollsnap123",
                "filing_snapshot_checksum": "iitfilingsnap123",
                "payment_snapshot_checksum": "iitpaysnap123",
            }
        ],
        "sample_cross_border_transactions": [
            {
                "name": "2026-06 service fee cross-border review",
                "company": "CN Company",
                "profile": "CN Demo",
                "period_start": "2026-06-01",
                "period_end": "2026-06-30",
                "transaction_date": "2026-06-18",
                "transaction_type": "service_fee",
                "counterparty": "US Service Provider",
                "counterparty_country": "United States",
                "amount": 12000.0,
                "related_party": True,
                "withholding_considered": True,
                "state": "reviewed",
                "readiness_state": "reviewed",
                "next_action": "Use this reviewed fact in scans and report limitations.",
                "snapshot_checksum": "crossbordersnap123",
                "evidence_count": 1,
            }
        ],
    }


def delivery_status(signoff_validation: dict | None = None) -> dict:
    objective_audit = status_payload()["objective_audit"]
    return SUMMARY._status(
        bundle_metadata=bundle_metadata_payload(),
        manifest=manifest_payload(),
        summary=summary_payload(),
        preview_health=preview_health_payload(),
        preview_module=preview_module_payload(),
        real_data_closed_loop=real_data_closed_loop_payload(),
        upgrade_summary=upgrade_summary_payload(),
        objective_audit=objective_audit,
        signoff_validation=signoff_validation,
        preview_url="http://127.0.0.1:18070/web/login?db=test",
    )


def delivery_inputs() -> dict:
    return {
        "bundle_metadata": bundle_metadata_payload(),
        "manifest": manifest_payload(),
        "summary": summary_payload(),
        "upgrade_summary": upgrade_summary_payload(),
        "preview_health": preview_health_payload(),
        "preview_module": preview_module_payload(),
        "real_data_closed_loop": real_data_closed_loop_payload(),
        "preview_url": "http://127.0.0.1:18070/web/login?db=test",
    }


def write_delivery_input_files(directory: Path) -> dict[str, Path]:
    inputs = delivery_inputs()
    paths = {
        "bundle_metadata": directory / "bundle.json",
        "manifest": directory / "manifest.json",
        "summary": directory / "summary.json",
        "upgrade_summary": directory / "upgrade.json",
        "preview_health": directory / "preview_health.json",
        "preview_module": directory / "preview_module.json",
        "real_data_closed_loop": directory / "real_data.json",
    }
    for key, path in paths.items():
        path.write_text(
            json.dumps(inputs[key], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return paths


def delivery_status_with_manifest(manifest: dict) -> dict:
    return SUMMARY._status(
        bundle_metadata=bundle_metadata_payload(),
        manifest=manifest,
        summary=summary_payload(),
        preview_health=preview_health_payload(),
        preview_module=preview_module_payload(),
        real_data_closed_loop=real_data_closed_loop_payload(),
        upgrade_summary=upgrade_summary_payload(),
        objective_audit=status_payload()["objective_audit"],
        signoff_validation=None,
        preview_url="http://127.0.0.1:18070/web/login?db=test",
    )


def complete_evidence(packet: dict, deployment_decision: str = "deploy") -> dict:
    evidence_notes = {
        "business_uat_decision": (
            "Completed UAT evidence for company CN Company and period 2026-06; "
            "screen-by-screen walkthrough script and controlled AI guidance "
            "evidence reviewed."
        ),
        "china_tax_professional_rule_signoff": (
            "Released rule official source packet reviewed by China tax professional."
        ),
        "official_source_freshness_review": (
            "Official source freshness, source governance summary, monitoring "
            "results and local jurisdiction updates reviewed."
        ),
        "customer_scope_and_data_gap_review": (
            "External dataset coverage, evidence gap register, open risk list and "
            "controlled AI limitation register reviewed."
        ),
        "representative_ux_walkthrough": (
            "Screen-by-screen walkthrough script completed for workbench, risk "
            "center, controlled AI guidance, filing/payment archive and report "
            "screens; input/output checksum and record checksum were visible."
        ),
        "blocker_summary_walkthrough": (
            "Data readiness, filing/payment archive, report readiness and controlled "
            "AI guidance disclosure blocker summaries reviewed."
        ),
        "production_deployment_decision": (
            "Production sign-off template completed with deployment decision and "
            "rollback owner."
        ),
    }
    decisions = []
    for action in packet["production_actions"]:
        decisions.append(
            {
                "key": action["key"],
                "decision": (
                    deployment_decision
                    if action["key"] == "production_deployment_decision"
                    else action["acceptable_decisions"][0]
                ),
                "reviewer": "Alice Zhang",
                "date": "2026-07-17",
                "evidence_reference": "SGN-2026-07-17-UAT-001",
                "notes": evidence_notes[action["key"]],
            }
        )
    return {
        "schema": VALIDATION.EVIDENCE_SCHEMA,
        "version": packet["version"],
        "source_commit": packet["source_commit"],
        "production_blocker_coverage": packet["production_blocker_coverage"],
        "decisions": decisions,
        "limitations": [],
    }


class TestChinaSignoffValidation(unittest.TestCase):
    def test_production_signoff_actions_export_lists_required_actions(self):
        export = SIGNOFF_ACTIONS.export_actions(delivery_status())

        self.assertEqual(export["schema"], "sdoo.cn.production-signoff-actions.v1")
        self.assertFalse(export["production_signoff_ready"])
        self.assertEqual(export["action_count"], 7)
        self.assertEqual(
            {action["key"] for action in export["actions"]},
            {
                "business_uat_decision",
                "representative_ux_walkthrough",
                "blocker_summary_walkthrough",
                "production_deployment_decision",
                "china_tax_professional_rule_signoff",
                "official_source_freshness_review",
                "customer_scope_and_data_gap_review",
            },
        )
        self.assertIn(
            "business UAT decision must be recorded outside this automated status",
            export["production_signoff_blockers"],
        )

    def test_production_signoff_actions_export_binds_to_packet(self):
        status = delivery_status()
        packet = PACKET._build_packet(status)

        export = SIGNOFF_ACTIONS.export_actions(status, packet)

        binding = export["packet_binding"]
        self.assertTrue(binding["provided"])
        self.assertTrue(binding["schema_ok"])
        self.assertTrue(binding["version_matches_status"])
        self.assertTrue(binding["source_commit_matches_status"])
        self.assertTrue(binding["preview_url_matches_status"])
        self.assertTrue(binding["action_keys_match"])

    def test_production_signoff_actions_markdown_is_reviewer_checklist(self):
        status = delivery_status()
        packet = PACKET._build_packet(status)
        export = SIGNOFF_ACTIONS.export_actions(status, packet)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "actions.md"

            SIGNOFF_ACTIONS._write_markdown(export, output)

            content = output.read_text(encoding="utf-8")
        self.assertIn("# China Production Sign-off Action Checklist", content)
        self.assertIn("## Required Actions", content)
        self.assertIn("### business_uat_decision", content)
        self.assertIn("- Evidence reference:", content)
        self.assertIn("## Packet Binding", content)

    def test_objective_coverage_path_guard_accepts_real_paths_and_rejects_missing_paths(self):
        content = (
            "`models/risk_center.py` `views/*.xml` "
            "`tools/generate_cn_signoff_packet.py` `models/not_a_real_file.py`"
        )

        references = ADDON_VALIDATION._coverage_referenced_paths(content)

        self.assertIn("models/risk_center.py", references)
        self.assertIn("views/*.xml", references)
        self.assertIn("tools/generate_cn_signoff_packet.py", references)
        self.assertTrue(ADDON_VALIDATION._coverage_path_exists("models/risk_center.py"))
        self.assertTrue(ADDON_VALIDATION._coverage_path_exists("views/*.xml"))
        self.assertTrue(
            ADDON_VALIDATION._coverage_path_exists(
                "tools/generate_cn_signoff_packet.py"
            )
        )
        self.assertFalse(
            ADDON_VALIDATION._coverage_path_exists("models/not_a_real_file.py")
        )

    def test_complete_signoff_evidence_allows_production_gate(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet)

        result = VALIDATION._validate(packet, evidence)

        self.assertTrue(result["ok"])
        self.assertTrue(result["production_signoff_ready"])
        self.assertEqual(result["deployment_decision"], "deploy")
        self.assertEqual(result["blockers"], [])
        self.assertEqual(result["blocked_objective_areas"], [])
        coverage_items = packet["production_blocker_coverage"]["coverage"]
        self.assertEqual(
            result["production_blocker_coverage_binding"],
            {
                "packet_all_covered": True,
                "evidence_matches_packet": True,
                "covered_blocker_count": len(coverage_items),
                "total_blocker_count": len(coverage_items),
                "uncovered_blockers": [],
            },
        )
        for item in result["action_results"]:
            self.assertGreaterEqual(len(item["objective_areas"]), 1)

    def test_rendered_signoff_evidence_draft_tracks_packet_actions_and_commit(self):
        packet = PACKET._build_packet(status_payload())

        draft = RENDER_EVIDENCE.render_template(packet)

        self.assertEqual(draft["schema"], VALIDATION.EVIDENCE_SCHEMA)
        self.assertEqual(draft["version"], packet["version"])
        self.assertEqual(draft["source_commit"], packet["source_commit"])
        self.assertEqual(
            [item["key"] for item in draft["decisions"]],
            [item["key"] for item in packet["production_actions"]],
        )
        self.assertEqual(
            draft["production_blocker_coverage"],
            packet["production_blocker_coverage"],
        )
        self.assertTrue(draft["production_blocker_coverage"]["all_covered"])
        self.assertIn("matrix", draft["production_blocker_coverage_note"])
        self.assertIn("placeholder", draft["placeholder_notice"].lower())
        self.assertIn("objective_areas", draft["decisions"][0])
        self.assertIn("addresses_blockers", draft["decisions"][0])
        self.assertIn("Objective areas:", draft["decisions"][0]["notes"])
        self.assertIn(
            "Production blockers addressed:",
            draft["decisions"][0]["notes"],
        )
        self.assertIn(
            "business UAT decision must be recorded outside this automated status",
            draft["decisions"][0]["notes"],
        )

    def test_rendered_signoff_evidence_draft_cannot_pass_with_placeholders(self):
        packet = PACKET._build_packet(status_payload())
        draft = RENDER_EVIDENCE.render_template(packet)

        result = VALIDATION._validate(packet, draft)

        self.assertFalse(result["production_signoff_ready"])
        self.assertIn(
            "business_uat_decision: reviewer is missing or still a template placeholder",
            result["blockers"],
        )
        self.assertIn(
            "representative business UAT",
            result["blocked_objective_areas"],
        )

    def test_signoff_evidence_requires_packet_blocker_coverage_match(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet)
        evidence["production_blocker_coverage"] = {
            "all_covered": True,
            "coverage": [],
            "uncovered_blockers": [],
        }

        result = VALIDATION._validate(packet, evidence)

        self.assertFalse(result["production_signoff_ready"])
        self.assertFalse(
            result["production_blocker_coverage_binding"]["evidence_matches_packet"]
        )
        self.assertIn(
            "sign-off evidence production_blocker_coverage does not match the packet",
            result["blockers"],
        )

    def test_objective_audit_marks_production_signoff_blocker(self):
        status = delivery_status()

        audit = OBJECTIVE_AUDIT.audit(status)

        self.assertEqual(audit["schema"], OBJECTIVE_AUDIT.AUDIT_SCHEMA)
        self.assertFalse(audit["achieved"])
        items = {item["key"]: item for item in audit["items"]}
        self.assertEqual(
            items["production_signoff_gate"]["state"],
            "blocked",
        )
        self.assertIn(
            "business UAT decision must be recorded outside this automated status",
            items["production_signoff_gate"]["blockers"],
        )
        self.assertGreaterEqual(audit["state_counts"]["evidence_ready"], 1)
        self.assertGreaterEqual(audit["state_counts"]["blocked"], 1)

    def test_objective_audit_blocks_when_risk_visibility_evidence_is_missing(self):
        status = delivery_status()
        status["real_data_closed_loop"]["readiness"][
            "has_remediation_task_visibility_evidence"
        ] = False

        audit = OBJECTIVE_AUDIT.audit(status)

        items = {item["key"]: item for item in audit["items"]}
        self.assertEqual(
            items["risk_remediation_report_visibility"]["state"],
            "not_ready",
        )
        self.assertIn(
            "remediation_task_visibility=False",
            items["risk_remediation_report_visibility"]["evidence"],
        )

    def test_objective_audit_blocks_when_remediation_rescan_evidence_is_missing(self):
        status = delivery_status()
        status["real_data_closed_loop"]["readiness"][
            "closed_loop_evidence_ready"
        ] = False
        status["real_data_closed_loop"]["readiness"][
            "has_remediation_verification_rescan_evidence"
        ] = False

        audit = OBJECTIVE_AUDIT.audit(status)

        items = {item["key"]: item for item in audit["items"]}
        self.assertEqual(
            items["real_odoo_accounting_business_data_basis"]["state"],
            "not_ready",
        )
        self.assertIn(
            "remediation_verification_rescan=False",
            items["real_odoo_accounting_business_data_basis"]["evidence"],
        )

    def test_objective_audit_blocks_when_rule_governance_detail_is_missing(self):
        status = delivery_status()
        status["real_data_closed_loop"]["readiness"][
            "has_rule_professional_signoff_evidence"
        ] = False

        audit = OBJECTIVE_AUDIT.audit(status)

        items = {item["key"]: item for item in audit["items"]}
        self.assertEqual(
            items["source_governed_versioned_rules"]["state"],
            "not_ready",
        )
        self.assertIn(
            "rule_professional_signoff=False",
            items["source_governed_versioned_rules"]["evidence"],
        )

    def test_objective_audit_blocks_when_customer_scope_gap_review_is_missing(self):
        status = delivery_status()
        status["real_data_closed_loop"]["readiness"][
            "has_open_high_risk_review_evidence"
        ] = False

        audit = OBJECTIVE_AUDIT.audit(status)

        items = {item["key"]: item for item in audit["items"]}
        self.assertEqual(
            items["customer_scope_gap_review_evidence"]["state"],
            "not_ready",
        )
        self.assertIn(
            "open_high_risk_review=False",
            items["customer_scope_gap_review_evidence"]["evidence"],
        )

    def test_objective_audit_blocks_when_reviewer_view_contract_is_missing(self):
        status = delivery_status()
        status["real_data_closed_loop"]["readiness"][
            "has_reviewer_view_contract_evidence"
        ] = False

        audit = OBJECTIVE_AUDIT.audit(status)

        items = {item["key"]: item for item in audit["items"]}
        self.assertEqual(
            items["risk_remediation_report_visibility"]["state"],
            "not_ready",
        )
        self.assertIn(
            "reviewer_view_contract=False",
            items["risk_remediation_report_visibility"]["evidence"],
        )

    def test_objective_audit_blocks_when_ux_view_clarity_contract_is_missing(self):
        status = delivery_status()
        status["real_data_closed_loop"]["readiness"][
            "has_ux_view_clarity_contract_evidence"
        ] = False

        audit = OBJECTIVE_AUDIT.audit(status)

        items = {item["key"]: item for item in audit["items"]}
        self.assertEqual(
            items["risk_remediation_report_visibility"]["state"],
            "not_ready",
        )
        self.assertIn(
            "ux_view_clarity_contract=False",
            items["risk_remediation_report_visibility"]["evidence"],
        )

    def test_objective_audit_blocks_when_multi_company_security_contract_is_missing(self):
        status = delivery_status()
        status["real_data_closed_loop"]["readiness"][
            "has_multi_company_security_contract_evidence"
        ] = False

        audit = OBJECTIVE_AUDIT.audit(status)

        items = {item["key"]: item for item in audit["items"]}
        self.assertEqual(
            items["native_odoo_multi_company_security"]["state"],
            "not_ready",
        )
        self.assertIn(
            "multi_company_security=False",
            items["native_odoo_multi_company_security"]["evidence"],
        )

    def test_objective_audit_blocks_when_menu_action_contract_is_missing(self):
        status = delivery_status()
        status["real_data_closed_loop"]["readiness"][
            "has_menu_action_contract_evidence"
        ] = False

        audit = OBJECTIVE_AUDIT.audit(status)

        items = {item["key"]: item for item in audit["items"]}
        self.assertEqual(
            items["native_odoo_multi_company_security"]["state"],
            "not_ready",
        )
        self.assertIn(
            "menu_action_contract=False",
            items["native_odoo_multi_company_security"]["evidence"],
        )

    def test_objective_audit_blocks_when_workbench_action_contract_is_missing(self):
        status = delivery_status()
        status["real_data_closed_loop"]["readiness"][
            "has_workbench_action_contract_evidence"
        ] = False

        audit = OBJECTIVE_AUDIT.audit(status)

        items = {item["key"]: item for item in audit["items"]}
        self.assertEqual(
            items["native_odoo_multi_company_security"]["state"],
            "not_ready",
        )
        self.assertIn(
            "workbench_action_contract=False",
            items["native_odoo_multi_company_security"]["evidence"],
        )

    def test_objective_audit_blocks_when_upgrade_migration_chain_is_missing(self):
        status = delivery_status()
        status["upgrade_migration_chain"]["ready"] = False

        audit = OBJECTIVE_AUDIT.audit(status)

        items = {item["key"]: item for item in audit["items"]}
        self.assertEqual(
            items["installable_upgradeable_odoo19"]["state"],
            "not_ready",
        )
        self.assertIn(
            "upgrade_migration_chain=False",
            items["installable_upgradeable_odoo19"]["evidence"],
        )

    def test_objective_audit_blocks_when_upgrade_runtime_is_missing(self):
        status = delivery_status()
        status["upgrade_runtime_passed"] = False

        audit = OBJECTIVE_AUDIT.audit(status)

        items = {item["key"]: item for item in audit["items"]}
        self.assertEqual(
            items["installable_upgradeable_odoo19"]["state"],
            "not_ready",
        )
        self.assertIn(
            "upgrade_runtime_passed=False",
            items["installable_upgradeable_odoo19"]["evidence"],
        )

    def test_objective_audit_is_achieved_after_valid_production_signoff(self):
        packet = PACKET._build_packet(status_payload())
        validation = VALIDATION._validate(packet, complete_evidence(packet))
        status = delivery_status(validation)

        audit = OBJECTIVE_AUDIT.audit(status)

        self.assertTrue(audit["achieved"])
        self.assertEqual(
            audit["state_counts"],
            {"evidence_ready": 15, "blocked": 0, "not_ready": 0},
        )
        items = {item["key"]: item for item in audit["items"]}
        self.assertEqual(
            items["production_signoff_gate"]["state"],
            "evidence_ready",
        )
        self.assertIn(
            "coverage_packet_all_covered=True",
            items["production_signoff_gate"]["evidence"],
        )
        self.assertIn(
            "coverage_evidence_matches_packet=True",
            items["production_signoff_gate"]["evidence"],
        )
        self.assertEqual(audit["completion_blockers"], [])

    def test_generic_signoff_evidence_reference_blocks_production_gate(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet)
        for item in evidence["decisions"]:
            item["evidence_reference"] = "SGN-2026-07-17-GENERIC"
            item["notes"] = "Generic approval record without required evidence scope."

        result = VALIDATION._validate(packet, evidence)

        self.assertFalse(result["ok"])
        self.assertIn(
            "business_uat_decision: evidence_reference or notes must mention: "
            "walkthrough script, uat, company, period, controlled ai",
            result["blockers"],
        )

    def test_missing_ai_checksum_scope_blocks_ux_walkthrough(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet)
        for item in evidence["decisions"]:
            if item["key"] == "representative_ux_walkthrough":
                item["notes"] = (
                    "Screen-by-screen walkthrough script completed for workbench, "
                    "risk center, controlled AI guidance, "
                    "filing/payment archive and report screens reviewed."
                )

        result = VALIDATION._validate(packet, evidence)

        self.assertFalse(result["ok"])
        self.assertIn(
            "representative_ux_walkthrough: evidence_reference or notes must "
            "mention: input/output checksum, record checksum",
            result["blockers"],
        )

    def test_signoff_evidence_requires_uat_walkthrough_script_reference(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet)
        for item in evidence["decisions"]:
            if item["key"] in (
                "business_uat_decision",
                "representative_ux_walkthrough",
            ):
                item["notes"] = item["notes"].replace(
                    "screen-by-screen walkthrough script",
                    "screen evidence",
                ).replace(
                    "Screen-by-screen walkthrough script",
                    "Screen evidence",
                )

        result = VALIDATION._validate(packet, evidence)

        self.assertFalse(result["ok"])
        self.assertIn(
            "business_uat_decision: evidence_reference or notes must mention: "
            "walkthrough script",
            result["blockers"],
        )
        self.assertIn(
            "representative_ux_walkthrough: evidence_reference or notes must "
            "mention: walkthrough script",
            result["blockers"],
        )

    def test_signoff_evidence_requires_source_governance_summary_reference(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet)
        for item in evidence["decisions"]:
            if item["key"] == "official_source_freshness_review":
                item["notes"] = "Official source freshness and local jurisdiction updates reviewed."

        result = VALIDATION._validate(packet, evidence)

        self.assertFalse(result["ok"])
        self.assertIn(
            "official_source_freshness_review: evidence_reference or notes must "
            "mention: governance summary, monitoring",
            result["blockers"],
        )

    def test_signoff_packet_requires_representative_ux_walkthrough(self):
        packet = PACKET._build_packet(status_payload())

        actions = {
            action["key"]: action for action in packet["production_actions"]
        }

        self.assertIn("representative_ux_walkthrough", actions)
        self.assertEqual(
            actions["representative_ux_walkthrough"]["acceptable_decisions"],
            ["passed", "passed_with_limitations"],
        )
        self.assertIn(
            "risk level, cause, impact amount, period, owner, due date, status and next action visibility",
            actions["representative_ux_walkthrough"]["required_evidence"],
        )

    def test_signoff_packet_requires_blocker_summary_walkthrough(self):
        packet = PACKET._build_packet(status_payload())

        actions = {
            action["key"]: action for action in packet["production_actions"]
        }

        self.assertIn("blocker_summary_walkthrough", actions)
        self.assertEqual(
            actions["blocker_summary_walkthrough"]["acceptable_decisions"],
            ["passed", "passed_with_limitations"],
        )
        self.assertIn(
            "data readiness, evidence, filing/payment archive, remediation, report center and report readiness blocker summaries",
            actions["blocker_summary_walkthrough"]["required_evidence"],
        )
        self.assertIn(
            "workbench action/rule-basis/limitation summaries",
            actions["blocker_summary_walkthrough"]["required_evidence"],
        )

    def test_signoff_packet_surfaces_workbench_summary_automated_evidence(self):
        packet = PACKET._build_packet(status_payload())

        automated = {item["key"]: item for item in packet["automated_items"]}

        self.assertIn("workbench_summary_evidence", automated)
        self.assertTrue(automated["workbench_summary_evidence"]["ready"])
        self.assertIn(
            "limitation_summary",
            automated["workbench_summary_evidence"]["evidence"],
        )

    def test_signoff_packet_surfaces_uat_walkthrough_script_manifest_evidence(self):
        packet = PACKET._build_packet(status_payload())

        automated = {item["key"]: item for item in packet["automated_items"]}

        self.assertIn("uat_walkthrough_script_in_manifest", automated)
        self.assertTrue(automated["uat_walkthrough_script_in_manifest"]["ready"])
        self.assertIn(
            "docs/CHINA_UAT_WALKTHROUGH_SCRIPT.md",
            automated["uat_walkthrough_script_in_manifest"]["evidence"],
        )

    def test_signoff_packet_surfaces_current_release_handoff_manifest_evidence(self):
        packet = PACKET._build_packet(status_payload())

        automated = {item["key"]: item for item in packet["automated_items"]}

        self.assertIn("current_release_handoff_in_manifest", automated)
        self.assertTrue(automated["current_release_handoff_in_manifest"]["ready"])
        self.assertIn(
            "docs/CHINA_RELEASE_HANDOFF_CURRENT.md",
            automated["current_release_handoff_in_manifest"]["evidence"],
        )

    def test_signoff_packet_surfaces_signoff_evidence_template_manifest_evidence(self):
        packet = PACKET._build_packet(status_payload())

        automated = {item["key"]: item for item in packet["automated_items"]}

        self.assertIn("signoff_evidence_template_in_manifest", automated)
        self.assertTrue(automated["signoff_evidence_template_in_manifest"]["ready"])
        self.assertIn(
            "docs/samples/cn_signoff_evidence_template.json",
            automated["signoff_evidence_template_in_manifest"]["evidence"],
        )

    def test_signoff_packet_surfaces_signoff_evidence_renderer_manifest_evidence(self):
        packet = PACKET._build_packet(status_payload())

        automated = {item["key"]: item for item in packet["automated_items"]}

        self.assertIn("signoff_evidence_renderer_in_manifest", automated)
        self.assertTrue(automated["signoff_evidence_renderer_in_manifest"]["ready"])
        self.assertIn(
            "tools/render_cn_signoff_evidence_template.py",
            automated["signoff_evidence_renderer_in_manifest"]["evidence"],
        )

    def test_signoff_packet_surfaces_objective_completion_audit_evidence(self):
        packet = PACKET._build_packet(status_payload())

        automated = {item["key"]: item for item in packet["automated_items"]}

        self.assertIn("objective_completion_audit_present", automated)
        self.assertTrue(automated["objective_completion_audit_present"]["ready"])
        self.assertIn(
            "business UAT decision must be recorded",
            automated["objective_completion_audit_present"]["evidence"],
        )

    def test_signoff_packet_surfaces_multi_company_security_contract_evidence(self):
        packet = PACKET._build_packet(status_payload())

        automated = {item["key"]: item for item in packet["automated_items"]}

        self.assertIn("multi_company_security_contract_evidence", automated)
        self.assertTrue(automated["multi_company_security_contract_evidence"]["ready"])
        self.assertIn(
            "sudo.cn.external.dataset",
            automated["multi_company_security_contract_evidence"]["evidence"],
        )
        self.assertIn(
            "company_ids",
            automated["multi_company_security_contract_evidence"]["evidence"],
        )

    def test_signoff_packet_surfaces_native_menu_action_contract_evidence(self):
        packet = PACKET._build_packet(status_payload())

        automated = {item["key"]: item for item in packet["automated_items"]}

        self.assertIn("native_menu_action_contract_evidence", automated)
        self.assertTrue(automated["native_menu_action_contract_evidence"]["ready"])
        self.assertIn(
            "menu_cn_risk_center",
            automated["native_menu_action_contract_evidence"]["evidence"],
        )
        self.assertIn(
            "action_cn_risk_center",
            automated["native_menu_action_contract_evidence"]["evidence"],
        )

    def test_signoff_packet_surfaces_workbench_action_contract_evidence(self):
        packet = PACKET._build_packet(status_payload())

        automated = {item["key"]: item for item in packet["automated_items"]}

        self.assertIn("workbench_action_contract_evidence", automated)
        self.assertTrue(automated["workbench_action_contract_evidence"]["ready"])
        self.assertIn(
            "action_cn_open_workbench_findings",
            automated["workbench_action_contract_evidence"]["evidence"],
        )
        self.assertIn(
            "assessment_id.profile_id",
            automated["workbench_action_contract_evidence"]["evidence"],
        )

    def test_signoff_packet_surfaces_upgrade_migration_chain_evidence(self):
        packet = PACKET._build_packet(status_payload())

        automated = {item["key"]: item for item in packet["automated_items"]}

        self.assertIn("upgrade_migration_chain_evidence", automated)
        self.assertTrue(automated["upgrade_migration_chain_evidence"]["ready"])
        self.assertIn(
            "addons/sudo_country_pack_cn/migrations/19.0.1.130.0/post-migration.py",
            automated["upgrade_migration_chain_evidence"]["evidence"],
        )
        self.assertIn(
            "tools/validate_addon.py",
            automated["upgrade_migration_chain_evidence"]["evidence"],
        )

    def test_signoff_packet_surfaces_production_release_control_manifest_evidence(self):
        packet = PACKET._build_packet(status_payload())

        automated = {item["key"]: item for item in packet["automated_items"]}

        self.assertIn("production_release_control_in_manifest", automated)
        self.assertTrue(automated["production_release_control_in_manifest"]["ready"])
        self.assertIn(
            "docs/CHINA_PRODUCTION_RELEASE_CONTROL.md",
            automated["production_release_control_in_manifest"]["evidence"],
        )

    def test_signoff_packet_surfaces_upgrade_runtime_evidence(self):
        packet = PACKET._build_packet(status_payload())

        automated = {item["key"]: item for item in packet["automated_items"]}

        self.assertIn("upgrade_runtime_evidence", automated)
        self.assertTrue(automated["upgrade_runtime_evidence"]["ready"])
        self.assertIn('"install": false', automated["upgrade_runtime_evidence"]["evidence"])
        self.assertIn('"failed": 0', automated["upgrade_runtime_evidence"]["evidence"])

    def test_signoff_packet_blocks_when_multi_company_security_contract_is_missing(self):
        payload = status_payload()
        payload["real_data_closed_loop"]["readiness"][
            "has_multi_company_security_contract_evidence"
        ] = False
        payload["real_data_closed_loop"]["multi_company_security_contracts"] = [
            {
                "model": "sudo.cn.external.dataset",
                "ready": False,
                "rule_count": 0,
                "rules": [],
            }
        ]

        packet = PACKET._build_packet(payload)

        automated = {item["key"]: item for item in packet["automated_items"]}
        self.assertFalse(automated["multi_company_security_contract_evidence"]["ready"])
        self.assertIn(
            '"ready": false',
            automated["multi_company_security_contract_evidence"]["evidence"],
        )

    def test_signoff_packet_blocks_when_menu_action_contract_is_missing(self):
        payload = status_payload()
        payload["real_data_closed_loop"]["readiness"][
            "has_menu_action_contract_evidence"
        ] = False
        payload["real_data_closed_loop"]["menu_action_contracts"] = [
            {
                "menu_xml_id": "menu_cn_risk_center",
                "action_xml_id": "action_cn_risk_center",
                "res_model": "sudo.compliance.finding",
                "ready": False,
                "action_matches": False,
                "missing_groups": ["sudo_global_finance.group_compliance_user"],
                "groups": [],
            }
        ]

        packet = PACKET._build_packet(payload)

        automated = {item["key"]: item for item in packet["automated_items"]}
        self.assertFalse(automated["native_menu_action_contract_evidence"]["ready"])
        self.assertIn(
            '"ready": false',
            automated["native_menu_action_contract_evidence"]["evidence"],
        )
        self.assertIn(
            "missing_groups",
            automated["native_menu_action_contract_evidence"]["evidence"],
        )

    def test_signoff_packet_blocks_when_workbench_action_contract_is_missing(self):
        payload = status_payload()
        payload["real_data_closed_loop"]["readiness"][
            "has_workbench_action_contract_evidence"
        ] = False
        payload["real_data_closed_loop"]["workbench_action_contracts"] = [
            {
                "method": "action_cn_open_workbench_findings",
                "res_model": "sudo.compliance.finding",
                "ready": False,
                "action_type": "ir.actions.act_window",
                "action_res_model": "sudo.compliance.finding",
                "scope_matches": False,
                "expected_terms": [["assessment_id.profile_id", "=", 1]],
                "domain": [],
                "context": {},
            }
        ]

        packet = PACKET._build_packet(payload)

        automated = {item["key"]: item for item in packet["automated_items"]}
        self.assertFalse(automated["workbench_action_contract_evidence"]["ready"])
        self.assertIn(
            '"scope_matches": false',
            automated["workbench_action_contract_evidence"]["evidence"],
        )

    def test_signoff_packet_surfaces_risk_task_report_summary_evidence(self):
        packet = PACKET._build_packet(status_payload())

        automated = {item["key"]: item for item in packet["automated_items"]}

        self.assertIn("risk_task_report_summary_evidence", automated)
        self.assertTrue(automated["risk_task_report_summary_evidence"]["ready"])
        self.assertIn(
            "VAT filing mismatch",
            automated["risk_task_report_summary_evidence"]["evidence"],
        )
        self.assertIn(
            "Correct VAT filing mismatch",
            automated["risk_task_report_summary_evidence"]["evidence"],
        )
        self.assertIn(
            "CN Compliance Report",
            automated["risk_task_report_summary_evidence"]["evidence"],
        )
        self.assertIn(
            '"risk_finding": true',
            automated["risk_task_report_summary_evidence"]["evidence"],
        )
        self.assertIn(
            '"remediation_task": true',
            automated["risk_task_report_summary_evidence"]["evidence"],
        )
        self.assertIn(
            '"report": true',
            automated["risk_task_report_summary_evidence"]["evidence"],
        )
        self.assertIn(
            '"reviewer_view_contract": true',
            automated["risk_task_report_summary_evidence"]["evidence"],
        )
        self.assertIn(
            '"ux_view_clarity_contract": true',
            automated["risk_task_report_summary_evidence"]["evidence"],
        )
        self.assertIn(
            "view_cn_risk_center_finding_list",
            automated["risk_task_report_summary_evidence"]["evidence"],
        )
        self.assertIn(
            "view_cn_risk_center_finding_kanban",
            automated["risk_task_report_summary_evidence"]["evidence"],
        )

    def test_signoff_packet_surfaces_ux_view_clarity_contract_evidence(self):
        packet = PACKET._build_packet(status_payload())

        automated = {item["key"]: item for item in packet["automated_items"]}

        self.assertIn("ux_view_clarity_contract_evidence", automated)
        self.assertTrue(automated["ux_view_clarity_contract_evidence"]["ready"])
        self.assertIn(
            "view_cn_risk_center_finding_kanban",
            automated["ux_view_clarity_contract_evidence"]["evidence"],
        )
        self.assertIn(
            "border-start border-4",
            automated["ux_view_clarity_contract_evidence"]["evidence"],
        )

    def test_signoff_packet_blocks_when_risk_visibility_evidence_is_incomplete(self):
        payload = status_payload()
        payload["real_data_closed_loop"]["readiness"][
            "has_remediation_task_visibility_evidence"
        ] = False

        packet = PACKET._build_packet(payload)

        automated = {item["key"]: item for item in packet["automated_items"]}
        self.assertFalse(automated["risk_task_report_summary_evidence"]["ready"])
        self.assertIn(
            '"remediation_task": false',
            automated["risk_task_report_summary_evidence"]["evidence"],
        )

    def test_signoff_packet_blocks_when_ux_view_clarity_contract_is_missing(self):
        payload = status_payload()
        payload["real_data_closed_loop"]["readiness"][
            "has_ux_view_clarity_contract_evidence"
        ] = False
        payload["real_data_closed_loop"]["ux_view_clarity_contracts"] = [
            {
                "xml_id": "view_cn_risk_center_finding_kanban",
                "ready": False,
                "missing_fields": ["cn_risk_next_action"],
                "missing_snippets": ["border-start border-4"],
                "required_fields": ["risk_level", "cn_risk_next_action"],
                "required_snippets": ['widget="badge"', "border-start border-4"],
            }
        ]

        packet = PACKET._build_packet(payload)

        automated = {item["key"]: item for item in packet["automated_items"]}
        self.assertFalse(automated["ux_view_clarity_contract_evidence"]["ready"])
        self.assertFalse(automated["risk_task_report_summary_evidence"]["ready"])
        self.assertIn(
            '"ux_view_clarity_contract": false',
            automated["risk_task_report_summary_evidence"]["evidence"],
        )
        self.assertIn(
            "missing_snippets",
            automated["ux_view_clarity_contract_evidence"]["evidence"],
        )

    def test_signoff_packet_blocks_when_reviewer_view_contract_is_missing(self):
        payload = status_payload()
        payload["real_data_closed_loop"]["readiness"][
            "has_reviewer_view_contract_evidence"
        ] = False
        payload["real_data_closed_loop"]["reviewer_view_contracts"] = [
            {
                "xml_id": "view_cn_risk_center_finding_list",
                "ready": False,
                "missing": ["cn_risk_next_action"],
                "required_fields": ["risk_level", "cn_risk_next_action"],
            }
        ]

        packet = PACKET._build_packet(payload)

        automated = {item["key"]: item for item in packet["automated_items"]}
        self.assertFalse(automated["risk_task_report_summary_evidence"]["ready"])
        self.assertIn(
            '"reviewer_view_contract": false',
            automated["risk_task_report_summary_evidence"]["evidence"],
        )
        self.assertIn(
            '"missing": ["cn_risk_next_action"]',
            automated["risk_task_report_summary_evidence"]["evidence"],
        )

    def test_signoff_packet_surfaces_remediation_verification_rescan_evidence(self):
        packet = PACKET._build_packet(status_payload())

        automated = {item["key"]: item for item in packet["automated_items"]}

        self.assertIn("remediation_verification_rescan_evidence", automated)
        self.assertTrue(automated["remediation_verification_rescan_evidence"]["ready"])
        self.assertIn(
            '"rescan_stage": "verified"',
            automated["remediation_verification_rescan_evidence"]["evidence"],
        )
        self.assertIn(
            '"verified_evidence_count": 1',
            automated["remediation_verification_rescan_evidence"]["evidence"],
        )

    def test_signoff_packet_blocks_when_remediation_rescan_evidence_is_missing(self):
        payload = status_payload()
        payload["real_data_closed_loop"]["readiness"][
            "has_remediation_verification_rescan_evidence"
        ] = False

        packet = PACKET._build_packet(payload)

        automated = {item["key"]: item for item in packet["automated_items"]}
        self.assertFalse(
            automated["remediation_verification_rescan_evidence"]["ready"]
        )

    def test_signoff_packet_surfaces_rule_governance_detail_evidence(self):
        packet = PACKET._build_packet(status_payload())

        automated = {item["key"]: item for item in packet["automated_items"]}

        self.assertTrue(automated["rule_source_governance_evidence"]["ready"])
        self.assertIn(
            '"official_source_freshness": true',
            automated["rule_source_governance_evidence"]["evidence"],
        )
        self.assertIn(
            '"rule_professional_signoff": true',
            automated["rule_source_governance_evidence"]["evidence"],
        )
        self.assertIn(
            '"rule_checksum_traceability": true',
            automated["rule_source_governance_evidence"]["evidence"],
        )

    def test_signoff_packet_blocks_when_rule_governance_detail_is_missing(self):
        payload = status_payload()
        payload["real_data_closed_loop"]["readiness"][
            "has_rule_professional_signoff_evidence"
        ] = False

        packet = PACKET._build_packet(payload)

        automated = {item["key"]: item for item in packet["automated_items"]}
        self.assertFalse(automated["rule_source_governance_evidence"]["ready"])
        self.assertIn(
            '"rule_professional_signoff": false',
            automated["rule_source_governance_evidence"]["evidence"],
        )

    def test_signoff_packet_surfaces_customer_scope_gap_review_evidence(self):
        packet = PACKET._build_packet(status_payload())

        automated = {item["key"]: item for item in packet["automated_items"]}

        self.assertTrue(automated["customer_scope_gap_review_evidence"]["ready"])
        self.assertIn(
            '"customer_data_scope": true',
            automated["customer_scope_gap_review_evidence"]["evidence"],
        )
        self.assertIn(
            '"customer_evidence_gap": true',
            automated["customer_scope_gap_review_evidence"]["evidence"],
        )
        self.assertIn(
            '"open_high_risk": true',
            automated["customer_scope_gap_review_evidence"]["evidence"],
        )

    def test_signoff_packet_blocks_when_customer_scope_gap_review_is_missing(self):
        payload = status_payload()
        payload["real_data_closed_loop"]["readiness"][
            "has_customer_evidence_gap_review_evidence"
        ] = False

        packet = PACKET._build_packet(payload)

        automated = {item["key"]: item for item in packet["automated_items"]}
        self.assertFalse(automated["customer_scope_gap_review_evidence"]["ready"])
        self.assertIn(
            '"customer_evidence_gap": false',
            automated["customer_scope_gap_review_evidence"]["evidence"],
        )

    def test_signoff_packet_surfaces_evidence_filing_payment_summary_evidence(self):
        packet = PACKET._build_packet(status_payload())

        automated = {item["key"]: item for item in packet["automated_items"]}

        self.assertIn("evidence_filing_payment_summary_evidence", automated)
        self.assertTrue(automated["evidence_filing_payment_summary_evidence"]["ready"])
        self.assertIn(
            "VAT payment receipt",
            automated["evidence_filing_payment_summary_evidence"]["evidence"],
        )
        self.assertIn(
            "VAT June archive",
            automated["evidence_filing_payment_summary_evidence"]["evidence"],
        )

    def test_signoff_packet_surfaces_iit_and_cross_border_scope_evidence(self):
        packet = PACKET._build_packet(status_payload())

        automated = {item["key"]: item for item in packet["automated_items"]}

        self.assertIn("iit_payroll_withholding_scope_evidence", automated)
        self.assertTrue(automated["iit_payroll_withholding_scope_evidence"]["ready"])
        self.assertIn(
            "CN IIT payroll withholding June run",
            automated["iit_payroll_withholding_scope_evidence"]["evidence"],
        )
        self.assertIn("cross_border_review_scope_evidence", automated)
        self.assertTrue(automated["cross_border_review_scope_evidence"]["ready"])
        self.assertIn(
            "2026-06 service fee cross-border review",
            automated["cross_border_review_scope_evidence"]["evidence"],
        )

    def test_signoff_packet_surfaces_official_source_governance_summary(self):
        packet = PACKET._build_packet(status_payload())

        automated = {item["key"]: item for item in packet["automated_items"]}

        self.assertIn("official_source_governance_summary", automated)
        self.assertTrue(automated["official_source_governance_summary"]["ready"])
        self.assertIn(
            "CODEX-DEMO China VAT source",
            automated["official_source_governance_summary"]["evidence"],
        )
        self.assertIn(
            "overdue_source_count",
            automated["official_source_governance_summary"]["evidence"],
        )

    def test_signoff_packet_lists_missing_human_evidence(self):
        packet = PACKET._build_packet(status_payload())

        action_keys = {action["key"] for action in packet["production_actions"]}
        missing = {item["key"]: item for item in packet["missing_human_evidence"]}

        self.assertEqual(set(missing), action_keys)
        for item in missing.values():
            self.assertGreaterEqual(len(item["objective_areas"]), 1)
            self.assertGreaterEqual(len(item["addresses_blockers"]), 1)
        self.assertIn("blocker_summary_walkthrough", missing)
        self.assertIn(
            "required_evidence",
            missing["blocker_summary_walkthrough"],
        )
        self.assertIn(
            "limitations and uncertainty visibility",
            missing["blocker_summary_walkthrough"]["objective_areas"],
        )
        self.assertIn(
            "customer-specific data gaps, evidence gaps and open critical risks must be reviewed",
            missing["blocker_summary_walkthrough"]["addresses_blockers"],
        )
        coverage = packet["production_blocker_coverage"]
        self.assertTrue(coverage["all_covered"])
        self.assertEqual(coverage["uncovered_blockers"], [])
        covered = {item["blocker"]: item for item in coverage["coverage"]}
        self.assertIn(
            "business UAT decision must be recorded outside this automated status",
            covered,
        )
        self.assertIn(
            "business_uat_decision",
            covered[
                "business UAT decision must be recorded outside this automated status"
            ]["action_keys"],
        )
        automated = {item["key"]: item for item in packet["automated_items"]}
        self.assertIn("production_blocker_coverage_complete", automated)
        self.assertTrue(automated["production_blocker_coverage_complete"]["ready"])
        self.assertIn(
            "business UAT decision must be recorded outside this automated status",
            automated["production_blocker_coverage_complete"]["evidence"],
        )

    def test_signoff_packet_markdown_lists_missing_human_evidence(self):
        packet = PACKET._build_packet(status_payload())
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "packet.md"

            PACKET._write_markdown(packet, output)

            content = output.read_text(encoding="utf-8")
        self.assertIn("## Missing Human Evidence", content)
        self.assertIn(
            "These items must be completed before `production_signoff_ready` can become `true`.",
            content,
        )
        self.assertIn("Objective areas:", content)
        self.assertIn("Addresses blockers:", content)
        self.assertIn("blocker_summary_walkthrough", content)
        self.assertIn(
            "Every production sign-off blocker is mapped to at least one human sign-off action",
            content,
        )
        self.assertIn("## Production Blocker Coverage", content)
        self.assertIn("All covered: `True`", content)

    def test_signoff_validation_blocks_unmapped_production_blockers(self):
        packet = PACKET._build_packet(status_payload())
        packet["production_signoff_blockers"].append(
            "new production blocker without assigned owner"
        )
        packet["production_blocker_coverage"] = PACKET._production_blocker_coverage(
            packet["production_signoff_blockers"],
            packet["production_actions"],
        )
        evidence = complete_evidence(packet)

        result = VALIDATION._validate(packet, evidence)

        self.assertFalse(result["ok"])
        self.assertIn(
            "new production blocker without assigned owner",
            result["uncovered_production_signoff_blockers"],
        )
        self.assertIn(
            "production sign-off blockers are not fully mapped to human actions: "
            "new production blocker without assigned owner",
            result["blockers"],
        )

    def test_signoff_packet_markdown_truncates_long_automated_evidence_only(self):
        packet = PACKET._build_packet(status_payload())
        automated = {
            item["key"]: item for item in packet["automated_items"]
        }
        self.assertIn(
            "VAT filing mismatch",
            automated["risk_task_report_summary_evidence"]["evidence"],
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "packet.md"

            PACKET._write_markdown(packet, output)

            content = output.read_text(encoding="utf-8")
        self.assertIn("truncated for readability", content)
        self.assertIn("see the JSON packet for complete evidence", content)
        self.assertIn(
            "Remediation closure has verified evidence and a verification rescan result",
            content,
        )

    def test_missing_representative_ux_walkthrough_blocks_production_gate(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet)
        evidence["decisions"] = [
            item
            for item in evidence["decisions"]
            if item["key"] != "representative_ux_walkthrough"
        ]

        result = VALIDATION._validate(packet, evidence)

        self.assertFalse(result["ok"])
        self.assertFalse(result["production_signoff_ready"])
        self.assertIn(
            "representative_ux_walkthrough: decision is missing",
            result["blockers"],
        )

    def test_missing_blocker_summary_walkthrough_blocks_production_gate(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet)
        evidence["decisions"] = [
            item
            for item in evidence["decisions"]
            if item["key"] != "blocker_summary_walkthrough"
        ]

        result = VALIDATION._validate(packet, evidence)

        self.assertFalse(result["ok"])
        self.assertFalse(result["production_signoff_ready"])
        self.assertIn(
            "blocker_summary_walkthrough: decision is missing",
            result["blockers"],
        )
        self.assertIn(
            "limitations and uncertainty visibility",
            result["blocked_objective_areas"],
        )
        self.assertIn(
            "data/evidence/report readiness transparency",
            result["blocked_objective_areas"],
        )
        self.assertIn(
            "customer-specific data gaps, evidence gaps and open critical risks must be reviewed",
            result["blocked_production_signoff_blockers"],
        )

    def test_signoff_validation_blocks_actions_without_objective_areas(self):
        packet = PACKET._build_packet(status_payload())
        packet["production_actions"][0].pop("objective_areas")
        evidence = complete_evidence(packet)

        result = VALIDATION._validate(packet, evidence)

        self.assertFalse(result["ok"])
        self.assertIn(
            "business_uat_decision: objective_areas are missing from the sign-off packet",
            result["blockers"],
        )

    def test_missing_human_decision_blocks_production_gate(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet)
        evidence["decisions"] = evidence["decisions"][:-1]

        result = VALIDATION._validate(packet, evidence)

        self.assertFalse(result["ok"])
        self.assertFalse(result["production_signoff_ready"])
        self.assertIn(
            "production_deployment_decision: decision is missing",
            result["blockers"],
        )

    def test_duplicate_decision_key_blocks_production_gate(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet)
        evidence["decisions"].append(deepcopy(evidence["decisions"][0]))

        result = VALIDATION._validate(packet, evidence)

        self.assertFalse(result["ok"])
        self.assertFalse(result["production_signoff_ready"])
        self.assertIn(
            "sign-off evidence decision keys must be unique: business_uat_decision",
            result["blockers"],
        )

    def test_unknown_decision_key_blocks_production_gate(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet)
        evidence["decisions"].append(
            {
                "key": "uncontrolled_extra_approval",
                "decision": "approved",
                "reviewer": "Alice Zhang",
                "date": "2026-07-17",
                "evidence_reference": "SGN-2026-07-17-EXTRA-001",
            }
        )

        result = VALIDATION._validate(packet, evidence)

        self.assertFalse(result["ok"])
        self.assertIn(
            "sign-off evidence contains unknown decision keys: uncontrolled_extra_approval",
            result["blockers"],
        )

    def test_decisions_must_be_a_list(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet)
        evidence["decisions"] = {"business_uat_decision": "accepted"}

        result = VALIDATION._validate(packet, evidence)

        self.assertFalse(result["ok"])
        self.assertIn("sign-off evidence decisions must be a list", result["blockers"])
        self.assertIn(
            "business_uat_decision: decision is missing",
            result["blockers"],
        )

    def test_source_commit_mismatch_blocks_production_gate(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet)
        evidence["source_commit"] = "different"

        result = VALIDATION._validate(packet, evidence)

        self.assertFalse(result["ok"])
        self.assertIn(
            "sign-off evidence source commit does not match the packet",
            result["blockers"],
        )

    def test_decision_rejects_invalid_date_format(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet)
        evidence["decisions"][0]["date"] = "17/07/2026"

        result = VALIDATION._validate(packet, evidence)

        self.assertFalse(result["ok"])
        self.assertIn(
            "business_uat_decision: date must be YYYY-MM-DD",
            result["blockers"],
        )

    def test_decision_rejects_template_placeholders(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet)
        evidence["decisions"][0]["reviewer"] = "Business reviewer name"
        evidence["decisions"][0]["date"] = "YYYY-MM-DD"
        evidence["decisions"][0]["evidence_reference"] = (
            "Path or document reference for completed CHINA_BUSINESS_UAT_CHECKLIST.md"
        )

        result = VALIDATION._validate(packet, evidence)

        self.assertFalse(result["ok"])
        self.assertIn(
            "business_uat_decision: reviewer is missing or still a template placeholder",
            result["blockers"],
        )
        self.assertIn(
            "business_uat_decision: date must be YYYY-MM-DD",
            result["blockers"],
        )
        self.assertIn(
            "business_uat_decision: evidence_reference is missing or still a template placeholder",
            result["blockers"],
        )

    def test_deploy_with_limitations_requires_recorded_limitations(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet, deployment_decision="deploy_with_limitations")

        result = VALIDATION._validate(packet, evidence)

        self.assertFalse(result["ok"])
        self.assertIn(
            "limitation decisions require at least one substantive limitation "
            "entry of 20 or more characters: production_deployment_decision",
            result["blockers"],
        )

        evidence_with_limitations = deepcopy(evidence)
        evidence_with_limitations["limitations"] = ["Known limitation approved."]
        result = VALIDATION._validate(packet, evidence_with_limitations)

        self.assertTrue(result["ok"])
        self.assertEqual(
            result["warnings"],
            [
                "production sign-off includes documented limitations: production_deployment_decision"
            ],
        )

    def test_limitation_decision_rejects_empty_short_or_malformed_limitations(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet, deployment_decision="deploy_with_limitations")

        for malformed_limitations in ([""], ["too short"], "not-a-list", [123]):
            payload = deepcopy(evidence)
            payload["limitations"] = malformed_limitations
            result = VALIDATION._validate(packet, payload)

            self.assertFalse(result["ok"])
            self.assertIn(
                "limitation decisions require at least one substantive limitation "
                "entry of 20 or more characters: production_deployment_decision",
                result["blockers"],
            )

    def test_any_limitation_decision_requires_recorded_limitations(self):
        packet = PACKET._build_packet(status_payload())
        limitation_cases = {
            "business_uat_decision": "accepted_with_limitations",
            "china_tax_professional_rule_signoff": "approved_with_limitations",
            "official_source_freshness_review": "current_with_documented_limitations",
            "customer_scope_and_data_gap_review": "limitations_documented",
            "representative_ux_walkthrough": "passed_with_limitations",
            "blocker_summary_walkthrough": "passed_with_limitations",
        }
        evidence = complete_evidence(packet)
        for item in evidence["decisions"]:
            if item["key"] in limitation_cases:
                item["decision"] = limitation_cases[item["key"]]

        result = VALIDATION._validate(packet, evidence)

        self.assertFalse(result["ok"])
        self.assertIn(
            "limitation decisions require at least one substantive limitation "
            "entry of 20 or more characters: "
            "business_uat_decision, china_tax_professional_rule_signoff, "
            "official_source_freshness_review, customer_scope_and_data_gap_review, "
            "representative_ux_walkthrough, blocker_summary_walkthrough",
            result["blockers"],
        )

        evidence_with_limitations = deepcopy(evidence)
        evidence_with_limitations["limitations"] = [
            "Business, professional, source, data and UX limitations are documented."
        ]
        result = VALIDATION._validate(packet, evidence_with_limitations)

        self.assertTrue(result["ok"])
        self.assertEqual(
            result["warnings"],
            [
                "production sign-off includes documented limitations: "
                "business_uat_decision, china_tax_professional_rule_signoff, "
                "official_source_freshness_review, customer_scope_and_data_gap_review, "
                "representative_ux_walkthrough, blocker_summary_walkthrough"
            ],
        )

    def test_blocked_automated_packet_evidence_blocks_production_gate(self):
        payload = status_payload()
        payload["runtime_passed"] = False
        payload["runtime"]["log"]["failed"] = 1
        packet = PACKET._build_packet(payload)
        evidence = complete_evidence(packet)

        result = VALIDATION._validate(packet, evidence)

        self.assertFalse(result["ok"])
        self.assertTrue(
            any(
                blocker.startswith("automated packet evidence is not ready:")
                and "runtime_passed" in blocker
                for blocker in result["blockers"]
            )
        )

    def test_delivery_status_requires_signoff_validation_for_production_ready(self):
        status = delivery_status()

        readiness = status["readiness_gates"]
        self.assertTrue(readiness["preview_ready"])
        self.assertEqual(readiness["preview_readiness_blockers"], [])
        self.assertTrue(readiness["business_uat_ready"])
        self.assertFalse(readiness["production_signoff_ready"])
        self.assertIn(
            "business UAT decision must be recorded outside this automated status",
            readiness["production_signoff_blockers"],
        )
        required_actions = {
            action["key"]: action
            for action in readiness["production_signoff_required_actions"]
        }
        self.assertIn("business_uat_decision", required_actions)
        self.assertIn("china_tax_professional_rule_signoff", required_actions)
        self.assertIn("customer_scope_and_data_gap_review", required_actions)
        self.assertIn("production_deployment_decision", required_actions)
        self.assertIn(
            "business UAT decision must be recorded outside this automated status",
            required_actions["business_uat_decision"]["addresses_blockers"],
        )
        self.assertEqual(
            set(required_actions["production_deployment_decision"]["addresses_blockers"]),
            set(readiness["production_signoff_blockers"]),
        )
        matrix = {
            item["blocker"]: item
            for item in readiness["production_signoff_blocker_action_matrix"]
        }
        self.assertEqual(set(matrix), set(readiness["production_signoff_blockers"]))
        self.assertTrue(all(item["covered"] for item in matrix.values()))
        self.assertIn(
            "business_uat_decision",
            matrix[
                "business UAT decision must be recorded outside this automated status"
            ]["action_keys"],
        )
        self.assertIn(
            "china_tax_professional_rule_signoff",
            matrix[
                "current official sources and released rules require professional sign-off evidence"
            ]["action_keys"],
        )
        self.assertIn(
            "customer_scope_and_data_gap_review",
            matrix[
                "customer-specific data gaps, evidence gaps and open critical risks must be reviewed"
            ]["action_keys"],
        )

    def test_delivery_status_surfaces_preview_readiness_blockers(self):
        preview_health = preview_health_payload()
        preview_health["ok"] = False
        preview_health["status_code"] = 500

        status = SUMMARY._status(
            bundle_metadata=bundle_metadata_payload(),
            manifest=manifest_payload(),
            summary=summary_payload(),
            preview_health=preview_health,
            preview_module=preview_module_payload(),
            real_data_closed_loop=real_data_closed_loop_payload(),
            upgrade_summary=upgrade_summary_payload(),
            objective_audit=status_payload()["objective_audit"],
            signoff_validation=None,
            preview_url="http://127.0.0.1:18070/web/login?db=test",
        )

        readiness = status["readiness_gates"]
        self.assertFalse(readiness["preview_ready"])
        self.assertEqual(
            readiness["preview_readiness_blockers"],
            ["preview health check did not pass"],
        )
        self.assertIn(
            "preview health check did not pass",
            readiness["business_uat_blockers"],
        )

    def test_delivery_status_required_actions_match_signoff_packet_evidence(self):
        status = delivery_status()
        packet = PACKET._build_packet(status)

        status_actions = {
            action["key"]: action
            for action in status["readiness_gates"][
                "production_signoff_required_actions"
            ]
        }
        packet_actions = {
            action["key"]: action
            for action in packet["missing_human_evidence"]
        }

        self.assertEqual(set(status_actions), set(packet_actions))
        for key, status_action in status_actions.items():
            packet_action = packet_actions[key]
            self.assertEqual(status_action["owner"], packet_action["owner"])
            self.assertEqual(
                status_action["required_evidence"],
                packet_action["required_evidence"],
            )
            self.assertEqual(
                status_action["acceptable_decisions"],
                packet_action["acceptable_decisions"],
            )
            self.assertEqual(
                status_action["objective_areas"],
                packet_action["objective_areas"],
            )
            self.assertEqual(
                set(status_action["addresses_blockers"]),
                set(packet_action["addresses_blockers"]),
            )

    def test_delivery_status_markdown_lists_production_blocker_action_matrix(self):
        status = delivery_status()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "status.md"

            SUMMARY._write_markdown(status, output)

            content = output.read_text(encoding="utf-8")
        self.assertIn("### Production Sign-off Blocker Action Matrix", content)
        self.assertIn("business_uat_decision", content)
        self.assertIn("china_tax_professional_rule_signoff", content)
        self.assertIn("customer_scope_and_data_gap_review", content)

    def test_delivery_status_accepts_valid_signoff_validation(self):
        packet = PACKET._build_packet(status_payload())
        validation = VALIDATION._validate(packet, complete_evidence(packet))

        status = delivery_status(validation)

        readiness = status["readiness_gates"]
        self.assertTrue(readiness["business_uat_ready"])
        self.assertTrue(readiness["production_signoff_ready"])
        self.assertEqual(readiness["production_signoff_blockers"], [])
        self.assertEqual(status["signoff_validation"]["deployment_decision"], "deploy")
        self.assertTrue(
            status["signoff_validation"]["production_blocker_coverage_binding"][
                "evidence_matches_packet"
            ]
        )

    def test_signoff_chain_final_packet_includes_objective_audit(self):
        chain = SIGNOFF_CHAIN.build_chain(delivery_inputs())

        final_packet_items = {
            item["key"]: item
            for item in chain["final_packet"]["automated_items"]
        }
        final_validation = chain["final_validation"]
        final_readiness = chain["final_status"]["readiness_gates"]
        action_checklist = chain["production_signoff_actions"]

        self.assertTrue(
            final_packet_items["objective_completion_audit_present"]["ready"]
        )
        self.assertFalse(final_validation["ok"])
        self.assertNotIn(
            "automated packet evidence is not ready: objective_completion_audit_present",
            final_validation["blockers"],
        )
        self.assertFalse(final_readiness["production_signoff_ready"])
        self.assertEqual(
            len(final_readiness["production_signoff_required_actions"]),
            7,
        )
        self.assertEqual(action_checklist["action_count"], 7)
        self.assertTrue(action_checklist["packet_binding"]["action_keys_match"])
        self.assertEqual(
            chain["objective_audit"]["state_counts"],
            {"evidence_ready": 14, "blocked": 1, "not_ready": 0},
        )

    def test_signoff_chain_accepts_completed_human_evidence(self):
        initial_chain = SIGNOFF_CHAIN.build_chain(delivery_inputs())
        completed_evidence = complete_evidence(initial_chain["final_packet"])

        chain = SIGNOFF_CHAIN.build_chain(
            delivery_inputs(),
            completed_evidence=completed_evidence,
        )

        self.assertTrue(chain["final_validation"]["ok"])
        self.assertTrue(
            chain["final_status"]["readiness_gates"]["production_signoff_ready"]
        )
        self.assertTrue(chain["objective_audit"]["achieved"])

    def test_signoff_chain_require_ready_flag_rejects_placeholder_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = write_delivery_input_files(root)
            argv = [
                "build_cn_signoff_evidence_chain.py",
                "--bundle-metadata",
                str(inputs["bundle_metadata"]),
                "--manifest",
                str(inputs["manifest"]),
                "--summary",
                str(inputs["summary"]),
                "--upgrade-summary",
                str(inputs["upgrade_summary"]),
                "--preview-health",
                str(inputs["preview_health"]),
                "--preview-module",
                str(inputs["preview_module"]),
                "--real-data-closed-loop",
                str(inputs["real_data_closed_loop"]),
                "--preview-url",
                "http://127.0.0.1:18070/web/login?db=test",
                "--output-prefix",
                str(root / "cn_delivery_m1_chain"),
                "--require-production-signoff-ready",
            ]

            with patch.object(sys, "argv", argv):
                result = SIGNOFF_CHAIN.main()

            self.assertEqual(result, 2)

    def test_signoff_chain_require_ready_flag_accepts_completed_evidence(self):
        initial_chain = SIGNOFF_CHAIN.build_chain(delivery_inputs())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = write_delivery_input_files(root)
            completed_evidence = root / "completed_evidence.json"
            completed_evidence.write_text(
                json.dumps(
                    complete_evidence(initial_chain["final_packet"]),
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            argv = [
                "build_cn_signoff_evidence_chain.py",
                "--bundle-metadata",
                str(inputs["bundle_metadata"]),
                "--manifest",
                str(inputs["manifest"]),
                "--summary",
                str(inputs["summary"]),
                "--upgrade-summary",
                str(inputs["upgrade_summary"]),
                "--preview-health",
                str(inputs["preview_health"]),
                "--preview-module",
                str(inputs["preview_module"]),
                "--real-data-closed-loop",
                str(inputs["real_data_closed_loop"]),
                "--preview-url",
                "http://127.0.0.1:18070/web/login?db=test",
                "--completed-evidence",
                str(completed_evidence),
                "--output-prefix",
                str(root / "cn_delivery_m1_signed_chain"),
                "--require-production-signoff-ready",
            ]

            with patch.object(sys, "argv", argv):
                result = SIGNOFF_CHAIN.main()

            self.assertEqual(result, 0)

    def test_signoff_chain_writes_latest_candidate_outputs(self):
        chain = SIGNOFF_CHAIN.build_chain(delivery_inputs())

        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory) / "cn_delivery_m1_chain"
            outputs = SIGNOFF_CHAIN._write_outputs(chain, prefix)

            self.assertIn("latest_signoff_candidate", outputs)
            self.assertIn("latest_signoff_candidate_markdown", outputs)
            self.assertIn("production_signoff_actions", outputs)
            self.assertIn("production_signoff_actions_markdown", outputs)
            self.assertTrue(outputs["latest_signoff_candidate"].is_file())
            self.assertTrue(outputs["latest_signoff_candidate_markdown"].is_file())
            self.assertTrue(outputs["production_signoff_actions"].is_file())
            self.assertTrue(outputs["production_signoff_actions_markdown"].is_file())
            actions = json.loads(
                outputs["production_signoff_actions"].read_text(encoding="utf-8")
            )
            self.assertEqual(actions["action_count"], 7)
            self.assertTrue(actions["packet_binding"]["action_keys_match"])

    def test_signoff_chain_latest_candidate_output_uses_strict_mode(self):
        chain = SIGNOFF_CHAIN.build_chain(delivery_inputs())

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_minimal_selector_candidate(root, 1)
            (root / "cn_delivery_m2_chain_status.json").write_text(
                "{}",
                encoding="utf-8",
            )
            current_prefix = root / "cn_delivery_m2_chain"
            outputs = SIGNOFF_CHAIN._write_outputs(chain, current_prefix)
            latest = json.loads(
                outputs["latest_signoff_candidate"].read_text(encoding="utf-8")
            )

            self.assertIsNone(latest["selected"])
            self.assertIn("refusing to select older", latest["errors"][0])

    def _write_minimal_selector_candidate(self, root: Path, number: int) -> None:
        tag = f"m{number}"
        commit = "abc123"
        aggregate = f"hash-{tag}"
        source_control = {
            "branch": "main",
            "commit": commit,
            "dirty": False,
            "inside_worktree": True,
        }
        manifest = {
            "version": "19.0.1.130.0",
            "git_commit": commit,
            "source_control": source_control,
            "file_count": 1,
            "aggregate_sha256": aggregate,
        }
        bundle = {
            "version": "19.0.1.130.0",
            "git_commit": commit,
            "source_control": source_control,
            "file_count": 1,
            "aggregate_sha256": aggregate,
            "bundle_sha256": "bundle",
        }
        acceptance = {
            "version": "19.0.1.130.0",
            "result": "passed",
            "runtime": {"log": {"failed": 0, "errors": 0}},
        }
        status = {
            "version": "19.0.1.130.0",
            "source_control": source_control,
            "readiness_gates": {
                "preview_ready": True,
                "compliance_scope_ready": True,
                "business_uat_ready": True,
                "production_signoff_ready": False,
                "production_signoff_required_actions": [{"key": "business_uat_decision"}],
            },
        }
        actions = {
            "version": "19.0.1.130.0",
            "source_commit": commit,
            "production_signoff_ready": False,
            "action_count": 1,
            "packet_binding": {
                "provided": True,
                "schema_ok": True,
                "version_matches_status": True,
                "source_commit_matches_status": True,
                "preview_url_matches_status": True,
                "action_keys_match": True,
            },
        }
        files = {
            f"sdoo-cn-compliance-delivery-{tag}.tgz": b"bundle",
            f"sdoo-cn-compliance-delivery-{tag}.bundle.json": bundle,
            f"cn_delivery_manifest_{tag}_full.json": manifest,
            f"cn_delivery_acceptance_{tag}_remote.json": acceptance,
            f"cn_delivery_acceptance_{tag}_upgrade_remote.json": acceptance,
            f"cn_preview_health_{tag}.json": {"ok": True},
            f"cn_preview_module_{tag}.json": {"ok": True},
            f"cn_real_data_closed_loop_{tag}.json": {"ok": True},
            f"cn_delivery_{tag}_chain_status.json": status,
            f"cn_delivery_{tag}_chain_signoff_packet.json": {
                "version": "19.0.1.130.0",
                "source_commit": commit,
            },
            f"cn_delivery_{tag}_chain_production_signoff_actions.json": actions,
            f"cn_delivery_{tag}_chain_production_signoff_actions.md": (
                b"# checklist\n\n"
                b"### business_uat_decision\n\n"
                b"- Owner: `business_reviewer`\n"
                b"- Acceptable decisions: `accepted`\n"
                b"- Required evidence: Completed checklist.\n"
                b"- Reviewer:\n"
                b"- Decision:\n"
                b"- Date:\n"
                b"- Evidence reference:\n"
                b"- Notes:\n"
            ),
            f"cn_delivery_{tag}_chain_objective_audit.json": {
                "version": "19.0.1.130.0",
            },
        }
        for name, payload in files.items():
            path = root / name
            if isinstance(payload, bytes):
                path.write_bytes(payload)
            else:
                path.write_text(json.dumps(payload), encoding="utf-8")

    def test_delivery_status_keeps_required_actions_for_incomplete_signoff_validation(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet)
        evidence["decisions"] = [
            item
            for item in evidence["decisions"]
            if item["key"] != "china_tax_professional_rule_signoff"
        ]
        validation = VALIDATION._validate(packet, evidence)

        status = delivery_status(validation)

        readiness = status["readiness_gates"]
        required_actions = {
            action["key"]: action
            for action in readiness["production_signoff_required_actions"]
        }
        self.assertFalse(readiness["production_signoff_ready"])
        self.assertIn(
            "current official sources and released rules require professional sign-off evidence",
            readiness["production_signoff_blockers"],
        )
        self.assertIn("china_tax_professional_rule_signoff", required_actions)
        self.assertIn("production_deployment_decision", required_actions)

    def test_delivery_status_surfaces_blocked_objective_areas(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet)
        evidence["decisions"] = [
            item
            for item in evidence["decisions"]
            if item["key"] != "blocker_summary_walkthrough"
        ]
        validation = VALIDATION._validate(packet, evidence)

        status = delivery_status(validation)

        self.assertFalse(status["readiness_gates"]["production_signoff_ready"])
        self.assertIn(
            "limitations and uncertainty visibility",
            status["signoff_validation"]["blocked_objective_areas"],
        )
        self.assertIn(
            "data/evidence/report readiness transparency",
            status["signoff_validation"]["blocked_objective_areas"],
        )
        self.assertIn(
            "customer-specific data gaps, evidence gaps and open critical risks must be reviewed",
            status["signoff_validation"]["blocked_production_signoff_blockers"],
        )

    def test_delivery_status_markdown_surfaces_blocked_objective_areas(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet)
        evidence["decisions"] = [
            item
            for item in evidence["decisions"]
            if item["key"] != "blocker_summary_walkthrough"
        ]
        status = delivery_status(VALIDATION._validate(packet, evidence))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "status.md"

            SUMMARY._write_markdown(status, output)

            content = output.read_text(encoding="utf-8")
        self.assertIn("### Production Blocked Objective Areas", content)
        self.assertIn("limitations and uncertainty visibility", content)
        self.assertIn("### Production Blocked Sign-off Blockers", content)
        self.assertIn("### Production Blocker Coverage Binding", content)
        self.assertIn("evidence matches packet: `True`", content)
        self.assertIn("### Production Sign-off Required Human Actions", content)
        self.assertIn(
            "customer-specific data gaps, evidence gaps and open critical risks must be reviewed",
            content,
        )

    def test_delivery_status_markdown_lists_workbench_summary_evidence(self):
        status = delivery_status()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "status.md"

            SUMMARY._write_markdown(status, output)

            content = output.read_text(encoding="utf-8")
        self.assertIn("## Workbench Summary Evidence", content)
        self.assertIn("Workbench summary evidence ready: `True`", content)
        self.assertIn("### CN Demo", content)
        self.assertIn("Action summary", content)
        self.assertIn("Rule basis", content)
        self.assertIn("Limitations", content)
        self.assertIn("Uncertainty", content)

    def test_delivery_status_markdown_lists_uat_walkthrough_script(self):
        status = delivery_status()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "status.md"

            SUMMARY._write_markdown(status, output)

            content = output.read_text(encoding="utf-8")
        self.assertIn(
            "Business UAT walkthrough script: `docs/CHINA_UAT_WALKTHROUGH_SCRIPT.md`",
            content,
        )
        self.assertIn("Business UAT walkthrough script in manifest: `True`", content)
        self.assertIn(
            "Current release handoff: `docs/CHINA_RELEASE_HANDOFF_CURRENT.md`",
            content,
        )
        self.assertIn("Current release handoff in manifest: `True`", content)
        self.assertIn(
            "Sign-off evidence template: `docs/samples/cn_signoff_evidence_template.json`",
            content,
        )
        self.assertIn("Sign-off evidence template in manifest: `True`", content)
        self.assertIn(
            "Sign-off evidence renderer: `tools/render_cn_signoff_evidence_template.py`",
            content,
        )
        self.assertIn("Sign-off evidence renderer in manifest: `True`", content)
        self.assertIn("Objective completion audit achieved: `False`", content)
        self.assertIn("Objective completion audit blockers: `1`", content)
        self.assertIn("### Objective Completion Audit Blockers", content)
        self.assertIn("### Production Sign-off Required Human Actions", content)
        self.assertIn("business_uat_decision", content)
        self.assertIn("china_tax_professional_rule_signoff", content)
        self.assertIn("customer_scope_and_data_gap_review", content)
        self.assertIn("production_deployment_decision", content)

    def test_delivery_status_markdown_preserves_valid_chinese_and_masks_bad_text(self):
        self.assertFalse(SUMMARY._looks_mojibake("中国合规档案"))
        self.assertTrue(SUMMARY._looks_mojibake("涓浗鍚堣妗ｆ"))
        self.assertTrue(SUMMARY._looks_mojibake("中国合规" + "\ufffd" + "档案"))
        self.assertTrue(SUMMARY._looks_mojibake("中国合规?档案"))
        status = delivery_status()
        status["real_data_closed_loop"]["sample_profiles"] = [
            {
                "id": 42,
                "name": "中国合规档案",
                "company": "中国公司",
                "status": "active",
                "period_label": "2026-06",
                "next_action": "澶嶆牳椋庨櫓",
                "action_summary": "涓浗鍚堣?妗ｆ",
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "status.md"

            SUMMARY._write_markdown(status, output)

            content = output.read_text(encoding="utf-8")
        self.assertIn("### 中国合规档案", content)
        self.assertIn("Company: `中国公司`", content)
        self.assertIn(SUMMARY.MOJIBAKE_MARKDOWN_PLACEHOLDER, content)

    def test_delivery_status_markdown_lists_risk_task_report_summary_evidence(self):
        status = delivery_status()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "status.md"

            SUMMARY._write_markdown(status, output)

            content = output.read_text(encoding="utf-8")
        self.assertIn("## Risk, Remediation and Report Summary Evidence", content)
        self.assertIn("Risk/task/report summary evidence ready: `True`", content)
        self.assertIn("Risk finding visibility evidence ready: `True`", content)
        self.assertIn("Remediation task visibility evidence ready: `True`", content)
        self.assertIn(
            "Remediation verification rescan evidence ready: `True`",
            content,
        )
        self.assertIn("Report visibility evidence ready: `True`", content)
        self.assertIn("Reviewer view contract evidence ready: `True`", content)
        self.assertIn("VAT filing mismatch", content)
        self.assertIn("Correct VAT filing mismatch", content)
        self.assertIn("CN Compliance Report", content)
        self.assertIn("Risk level", content)
        self.assertIn("State/verification", content)
        self.assertIn("State/conclusion", content)

    def test_delivery_status_preserves_reviewer_view_contract_details(self):
        status = delivery_status()

        contracts = status["real_data_closed_loop"]["reviewer_view_contracts"]

        self.assertEqual(
            contracts[0]["xml_id"],
            "view_cn_risk_center_finding_list",
        )
        self.assertEqual(contracts[0]["missing"], [])
        self.assertIn("cn_risk_next_action", contracts[0]["required_fields"])

    def test_delivery_status_preserves_ux_view_clarity_contract_details(self):
        status = delivery_status()

        contracts = status["real_data_closed_loop"]["ux_view_clarity_contracts"]

        self.assertEqual(contracts[0]["xml_id"], "view_cn_risk_center_finding_kanban")
        self.assertTrue(contracts[0]["ready"])
        self.assertEqual(contracts[0]["missing_fields"], [])
        self.assertIn("task_due_date", contracts[0]["required_fields"])
        self.assertIn("border-start border-4", contracts[0]["required_snippets"])

    def test_delivery_status_markdown_lists_ux_view_clarity_contract_evidence(self):
        status = delivery_status()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "status.md"

            SUMMARY._write_markdown(status, output)

            content = output.read_text(encoding="utf-8")
        self.assertIn("UX view clarity contract evidence ready: `True`", content)

    def test_delivery_status_preserves_multi_company_security_contract_details(self):
        status = delivery_status()

        contracts = status["real_data_closed_loop"][
            "multi_company_security_contracts"
        ]

        self.assertEqual(contracts[0]["model"], "sudo.cn.external.dataset")
        self.assertTrue(contracts[0]["ready"])
        self.assertEqual(contracts[0]["rule_count"], 1)
        self.assertIn("company_ids", contracts[0]["rules"][0]["domain"])

    def test_delivery_status_preserves_menu_action_contract_details(self):
        status = delivery_status()

        contracts = status["real_data_closed_loop"]["menu_action_contracts"]

        self.assertEqual(contracts[0]["menu_xml_id"], "menu_cn_risk_center")
        self.assertTrue(contracts[0]["ready"])
        self.assertTrue(contracts[0]["action_matches"])
        self.assertIn(
            "sudo_global_finance.group_compliance_user",
            contracts[0]["groups"],
        )

    def test_delivery_status_preserves_workbench_action_contract_details(self):
        status = delivery_status()

        contracts = status["real_data_closed_loop"]["workbench_action_contracts"]

        self.assertEqual(
            contracts[0]["method"],
            "action_cn_open_workbench_findings",
        )
        self.assertTrue(contracts[0]["ready"])
        self.assertTrue(contracts[0]["scope_matches"])
        self.assertEqual(contracts[0]["action_type"], "ir.actions.act_window")

    def test_delivery_status_markdown_lists_workbench_action_contract_evidence(self):
        status = delivery_status()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "status.md"

            SUMMARY._write_markdown(status, output)

            content = output.read_text(encoding="utf-8")
        self.assertIn("Workbench action contract evidence ready: `True`", content)

    def test_delivery_status_markdown_lists_menu_action_contract_evidence(self):
        status = delivery_status()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "status.md"

            SUMMARY._write_markdown(status, output)

            content = output.read_text(encoding="utf-8")
        self.assertIn("Menu/action contract evidence ready: `True`", content)

    def test_delivery_status_preserves_upgrade_migration_chain_details(self):
        status = delivery_status()

        chain = status["upgrade_migration_chain"]

        self.assertTrue(chain["ready"])
        self.assertTrue(chain["module_manifest_included"])
        self.assertTrue(chain["validator_included"])
        self.assertTrue(chain["current_migration_included"])
        self.assertEqual(chain["current_version"], "19.0.1.130.0")
        self.assertGreaterEqual(chain["migration_script_count"], 1)

    def test_delivery_status_markdown_lists_upgrade_migration_chain_evidence(self):
        status = delivery_status()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "status.md"

            SUMMARY._write_markdown(status, output)

            content = output.read_text(encoding="utf-8")
        self.assertIn("Upgrade migration chain evidence ready: `True`", content)
        self.assertIn("## Upgrade Migration Chain Evidence", content)
        self.assertIn(
            "addons/sudo_country_pack_cn/migrations/19.0.1.130.0/post-migration.py",
            content,
        )
        self.assertIn("tools/validate_addon.py", content)

    def test_delivery_status_markdown_lists_upgrade_runtime_evidence(self):
        status = delivery_status()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "status.md"

            SUMMARY._write_markdown(status, output)

            content = output.read_text(encoding="utf-8")
        self.assertIn("Upgrade runtime passed: `True`", content)
        self.assertIn("## Upgrade Runtime", content)
        self.assertIn("Install mode: `False`", content)

    def test_delivery_status_markdown_lists_production_release_control(self):
        status = delivery_status()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "status.md"

            SUMMARY._write_markdown(status, output)

            content = output.read_text(encoding="utf-8")
        self.assertIn(
            "Production release-control checklist in manifest: `True`",
            content,
        )
        self.assertIn("docs/CHINA_PRODUCTION_RELEASE_CONTROL.md", content)

    def test_delivery_status_markdown_lists_evidence_filing_payment_summary_evidence(self):
        status = delivery_status()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "status.md"

            SUMMARY._write_markdown(status, output)

            content = output.read_text(encoding="utf-8")
        self.assertIn("## Evidence, Filing and Payment Archive Summary Evidence", content)
        self.assertIn(
            "Evidence/filing/payment summary evidence ready: `True`",
            content,
        )
        self.assertIn("VAT payment receipt", content)
        self.assertIn("VAT June archive", content)
        self.assertIn("Submission/payment integrity", content)
        self.assertIn("Checksums present", content)

    def test_delivery_status_markdown_lists_rule_source_governance_evidence(self):
        status = delivery_status()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "status.md"

            SUMMARY._write_markdown(status, output)

            content = output.read_text(encoding="utf-8")
        self.assertIn("## Rule And Source Governance Evidence", content)
        self.assertIn("Rule/source governance evidence ready: `True`", content)
        self.assertIn("Official source freshness evidence ready: `True`", content)
        self.assertIn("Rule professional sign-off evidence ready: `True`", content)
        self.assertIn("Rule checksum traceability evidence ready: `True`", content)
        self.assertIn("Customer scope/gap review evidence ready: `True`", content)
        self.assertIn("Customer data-scope evidence ready: `True`", content)
        self.assertIn("Customer evidence-gap evidence ready: `True`", content)
        self.assertIn("Open high-risk review evidence ready: `True`", content)
        self.assertIn("CODEX-DEMO China VAT source", content)
        self.assertIn("CN VAT Demo Rule / 2026.1", content)
        self.assertIn("Professional review", content)
        self.assertIn("Multi-company security contract evidence ready: `True`", content)
        self.assertIn("No source monitor run sample was provided", content)

    def test_delivery_status_markdown_lists_official_source_governance_overview(self):
        status = delivery_status()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "status.md"

            SUMMARY._write_markdown(status, output)

            content = output.read_text(encoding="utf-8")
        self.assertIn("## Official Source Governance Overview", content)
        self.assertIn("Official source governance summary ready: `True`", content)
        self.assertIn("Overdue source samples: `0`", content)
        self.assertIn("Changed monitor run samples: `0`", content)
        self.assertIn("Rule governance issue samples: `0`", content)
        self.assertIn("CODEX-DEMO China VAT source", content)

    def test_delivery_status_markdown_lists_iit_and_cross_border_scope_evidence(self):
        status = delivery_status()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "status.md"

            SUMMARY._write_markdown(status, output)

            content = output.read_text(encoding="utf-8")
        self.assertIn("IIT payroll withholding scope evidence ready: `True`", content)
        self.assertIn("Cross-border review scope evidence ready: `True`", content)
        self.assertIn("## IIT Payroll Withholding Scope Evidence", content)
        self.assertIn("CN IIT payroll withholding June run", content)
        self.assertIn("Source states", content)
        self.assertIn("## Cross-Border Review Scope Evidence", content)
        self.assertIn("2026-06 service fee cross-border review", content)
        self.assertIn("Withholding considered", content)

    def test_delivery_status_lists_tax_domain_coverage_overview(self):
        status = delivery_status()

        coverage = status["tax_domain_coverage"]
        readiness = status["readiness_gates"]

        self.assertTrue(coverage["vat"]["ready"])
        self.assertTrue(coverage["cit"]["ready"])
        self.assertTrue(coverage["iit"]["ready"])
        self.assertTrue(coverage["cross_border"]["ready"])
        self.assertTrue(status["source_governance_summary"]["ready"])
        self.assertTrue(readiness["compliance_scope_ready"])
        self.assertEqual(readiness["compliance_scope_blockers"], [])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "status.md"

            SUMMARY._write_markdown(status, output)

            content = output.read_text(encoding="utf-8")
        self.assertIn("Compliance scope ready: `True`", content)
        self.assertIn("### Compliance Scope Blockers", content)
        self.assertIn("## Tax Domain Coverage Overview", content)
        self.assertIn("VAT invoice / filing / payment", content)
        self.assertIn("CIT accounting / filing", content)
        self.assertIn("IIT payroll / withholding / payment", content)
        self.assertIn("Cross-border and withholding review", content)
        self.assertIn("Representative UAT scope", content)
        self.assertIn("Fact-specific review remains required", content)

    def test_delivery_status_surfaces_compliance_scope_blockers(self):
        real_data = real_data_closed_loop_payload()
        real_data["readiness"]["has_iit_payroll_withholding_scope_evidence"] = False

        status = SUMMARY._status(
            bundle_metadata=bundle_metadata_payload(),
            manifest=manifest_payload(),
            summary=summary_payload(),
            preview_health=preview_health_payload(),
            preview_module=preview_module_payload(),
            real_data_closed_loop=real_data,
            upgrade_summary=upgrade_summary_payload(),
            objective_audit=status_payload()["objective_audit"],
            signoff_validation=None,
            preview_url="http://127.0.0.1:18070/web/login?db=test",
        )

        readiness = status["readiness_gates"]
        self.assertFalse(readiness["compliance_scope_ready"])
        self.assertIn(
            "IIT payroll / withholding / payment coverage is not ready",
            readiness["compliance_scope_blockers"],
        )

    def test_delivery_status_rejects_mismatched_signoff_validation_version(self):
        packet = PACKET._build_packet(status_payload())
        validation = VALIDATION._validate(packet, complete_evidence(packet))
        validation["version"] = "19.0.1.999.0"

        status = delivery_status(validation)

        readiness = status["readiness_gates"]
        self.assertFalse(readiness["production_signoff_ready"])
        self.assertIn(
            "sign-off validation version does not match delivery version",
            readiness["production_signoff_blockers"],
        )

    def test_delivery_status_rejects_mismatched_signoff_validation_source_commit(self):
        packet = PACKET._build_packet(status_payload())
        validation = VALIDATION._validate(packet, complete_evidence(packet))
        validation["source_commit"] = "different-commit"

        status = delivery_status(validation)

        readiness = status["readiness_gates"]
        self.assertFalse(readiness["production_signoff_ready"])
        self.assertIn(
            "sign-off validation source commit does not match delivery source commit",
            readiness["production_signoff_blockers"],
        )

    def test_delivery_status_rejects_mismatched_signoff_validation_preview_url(self):
        packet = PACKET._build_packet(status_payload())
        validation = VALIDATION._validate(packet, complete_evidence(packet))
        validation["preview_url"] = "http://127.0.0.1:18070/web/login?db=other"

        status = delivery_status(validation)

        readiness = status["readiness_gates"]
        self.assertFalse(readiness["production_signoff_ready"])
        self.assertIn(
            "sign-off validation preview URL does not match delivery preview URL",
            readiness["production_signoff_blockers"],
        )

    def test_objective_audit_rejects_mismatched_signoff_validation_binding(self):
        packet = PACKET._build_packet(status_payload())
        validation = VALIDATION._validate(packet, complete_evidence(packet))
        validation["version"] = "19.0.1.999.0"
        validation["source_commit"] = "different-commit"
        validation["preview_url"] = "http://127.0.0.1:18070/web/login?db=other"

        status = delivery_status(validation)
        audit = OBJECTIVE_AUDIT.audit(status)

        self.assertFalse(audit["achieved"])
        items = {item["key"]: item for item in audit["items"]}
        self.assertEqual(items["production_signoff_gate"]["state"], "blocked")
        self.assertIn(
            "sign-off validation version does not match delivery version",
            audit["completion_blockers"],
        )
        self.assertIn(
            "sign-off validation source commit does not match delivery source commit",
            audit["completion_blockers"],
        )
        self.assertIn(
            "sign-off validation preview URL does not match delivery preview URL",
            audit["completion_blockers"],
        )

    def test_delivery_status_requires_signoff_validator_in_manifest(self):
        status = delivery_status_with_manifest(
            manifest_without("tools/validate_cn_signoff_evidence.py")
        )

        readiness = status["readiness_gates"]
        self.assertFalse(readiness["business_uat_ready"])
        self.assertFalse(readiness["production_signoff_ready"])
        self.assertIn(
            "production sign-off evidence validator is not included in the manifest",
            readiness["business_uat_blockers"],
        )
        self.assertFalse(
            status["signoff_validation_tool"]["included_in_manifest"],
        )

    def test_delivery_status_requires_signoff_evidence_template_in_manifest(self):
        status = delivery_status_with_manifest(
            manifest_without("docs/samples/cn_signoff_evidence_template.json")
        )

        readiness = status["readiness_gates"]
        self.assertFalse(readiness["business_uat_ready"])
        self.assertFalse(readiness["production_signoff_ready"])
        self.assertIn(
            "production sign-off evidence template is not included in the manifest",
            readiness["business_uat_blockers"],
        )
        self.assertFalse(
            status["signoff_evidence_template"]["included_in_manifest"],
        )

    def test_delivery_status_requires_signoff_evidence_renderer_in_manifest(self):
        status = delivery_status_with_manifest(
            manifest_without("tools/render_cn_signoff_evidence_template.py")
        )

        readiness = status["readiness_gates"]
        self.assertFalse(readiness["business_uat_ready"])
        self.assertFalse(readiness["production_signoff_ready"])
        self.assertIn(
            "production sign-off evidence renderer is not included in the manifest",
            readiness["business_uat_blockers"],
        )
        self.assertFalse(
            status["signoff_evidence_renderer_tool"]["included_in_manifest"],
        )

    def test_delivery_status_requires_objective_auditor_in_manifest(self):
        status = delivery_status_with_manifest(
            manifest_without("tools/audit_cn_objective_completion.py")
        )

        readiness = status["readiness_gates"]
        self.assertFalse(readiness["business_uat_ready"])
        self.assertFalse(readiness["production_signoff_ready"])
        self.assertIn(
            "objective completion auditor is not included in the manifest",
            readiness["business_uat_blockers"],
        )
        self.assertFalse(status["objective_audit_tool"]["included_in_manifest"])

    def test_delivery_status_requires_signoff_chain_builder_in_manifest(self):
        status = delivery_status_with_manifest(
            manifest_without("tools/build_cn_signoff_evidence_chain.py")
        )

        readiness = status["readiness_gates"]
        self.assertFalse(readiness["business_uat_ready"])
        self.assertFalse(readiness["production_signoff_ready"])
        self.assertIn(
            "production sign-off evidence chain builder is not included in the manifest",
            readiness["business_uat_blockers"],
        )
        self.assertFalse(status["signoff_chain_tool"]["included_in_manifest"])

    def test_delivery_status_requires_signoff_candidate_selector_in_manifest(self):
        status = delivery_status_with_manifest(
            manifest_without("tools/select_cn_latest_signoff_candidate.py")
        )

        readiness = status["readiness_gates"]
        self.assertFalse(readiness["business_uat_ready"])
        self.assertFalse(readiness["production_signoff_ready"])
        self.assertIn(
            "production sign-off candidate selector is not included in the manifest",
            readiness["business_uat_blockers"],
        )
        self.assertFalse(
            status["signoff_candidate_selector_tool"]["included_in_manifest"]
        )

    def test_delivery_status_requires_production_signoff_actions_exporter_in_manifest(self):
        status = delivery_status_with_manifest(
            manifest_without("tools/export_cn_production_signoff_actions.py")
        )

        readiness = status["readiness_gates"]
        self.assertFalse(readiness["business_uat_ready"])
        self.assertFalse(readiness["production_signoff_ready"])
        self.assertIn(
            "production sign-off action checklist exporter is not included in the manifest",
            readiness["business_uat_blockers"],
        )
        self.assertFalse(
            status["production_signoff_actions_tool"]["included_in_manifest"]
        )

    def test_delivery_status_requires_uat_walkthrough_script_in_manifest(self):
        status = delivery_status_with_manifest(
            manifest_without("docs/CHINA_UAT_WALKTHROUGH_SCRIPT.md")
        )

        readiness = status["readiness_gates"]
        self.assertFalse(readiness["business_uat_ready"])
        self.assertFalse(readiness["production_signoff_ready"])
        self.assertIn(
            "business UAT walkthrough script is not included in the manifest",
            readiness["business_uat_blockers"],
        )
        self.assertFalse(status["uat_walkthrough"]["included_in_manifest"])

    def test_delivery_status_requires_current_release_handoff_in_manifest(self):
        status = delivery_status_with_manifest(
            manifest_without("docs/CHINA_RELEASE_HANDOFF_CURRENT.md")
        )

        readiness = status["readiness_gates"]
        self.assertFalse(readiness["business_uat_ready"])
        self.assertFalse(readiness["production_signoff_ready"])
        self.assertIn(
            "current release handoff is not included in the manifest",
            readiness["business_uat_blockers"],
        )
        self.assertFalse(status["release_handoff"]["included_in_manifest"])

    def test_delivery_status_requires_production_release_control_in_manifest(self):
        status = delivery_status_with_manifest(
            manifest_without("docs/CHINA_PRODUCTION_RELEASE_CONTROL.md")
        )

        readiness = status["readiness_gates"]
        self.assertFalse(readiness["business_uat_ready"])
        self.assertFalse(readiness["production_signoff_ready"])
        self.assertIn(
            "production release-control checklist is not included in the manifest",
            readiness["business_uat_blockers"],
        )
        self.assertFalse(
            status["production_release_control"]["included_in_manifest"],
        )

    def test_delivery_status_requires_current_migration_in_manifest(self):
        status = delivery_status_with_manifest(
            manifest_without(
                "addons/sudo_country_pack_cn/migrations/"
                "19.0.1.130.0/post-migration.py"
            )
        )

        readiness = status["readiness_gates"]
        self.assertFalse(readiness["business_uat_ready"])
        self.assertFalse(readiness["production_signoff_ready"])
        self.assertIn(
            "upgrade migration chain evidence is not included in the manifest",
            readiness["business_uat_blockers"],
        )
        self.assertFalse(
            status["upgrade_migration_chain"]["current_migration_included"],
        )

    def test_delivery_status_requires_upgrade_runtime_summary(self):
        status = SUMMARY._status(
            bundle_metadata=bundle_metadata_payload(),
            manifest=manifest_payload(),
            summary=summary_payload(),
            preview_health=preview_health_payload(),
            preview_module=preview_module_payload(),
            real_data_closed_loop=real_data_closed_loop_payload(),
            upgrade_summary=None,
            objective_audit=status_payload()["objective_audit"],
            signoff_validation=None,
            preview_url="http://127.0.0.1:18070/web/login?db=test",
        )

        readiness = status["readiness_gates"]
        self.assertFalse(status["upgrade_runtime_passed"])
        self.assertFalse(readiness["business_uat_ready"])
        self.assertIn(
            "Odoo upgrade runtime tests did not pass",
            readiness["business_uat_blockers"],
        )


if __name__ == "__main__":
    unittest.main()
