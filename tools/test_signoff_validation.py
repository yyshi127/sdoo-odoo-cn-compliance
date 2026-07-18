from __future__ import annotations

import importlib.util
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


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
        "preview_health": {"ok": True, "url": "http://127.0.0.1:18070/web/login?db=test"},
        "preview_module": {"ok": True, "module_installed_version": "19.0.1.130.0"},
        "real_data_closed_loop": {
            "ok": True,
            "objects": {
                "vat_reconciliation_runs": 1,
                "vat_filing_records": 1,
                "tax_payment_records": 2,
                "cit_reconciliation_runs": 0,
                "cit_filing_records": 0,
                "active_profile_iit_reconciliation_runs": 1,
                "iit_withholding_records": 1,
                "payroll_summary_records": 1,
                "active_profile_cross_border_transactions": 1,
            },
            "readiness": {
                "closed_loop_evidence_ready": True,
                "has_workbench_summary_evidence": True,
                "has_risk_task_report_summary_evidence": True,
                "has_evidence_filing_payment_summary_evidence": True,
                "has_controlled_ai_guidance_evidence": True,
                "has_rule_source_governance_evidence": True,
                "has_iit_payroll_withholding_scope_evidence": True,
                "has_cross_border_review_scope_evidence": True,
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
        "docs/CHINA_DELIVERY_INDEX.md",
        "docs/CHINA_DELIVERY_M138_STATUS.md",
        "docs/CHINA_DELIVERY_OBJECTIVE_COVERAGE.md",
        "docs/CHINA_PRODUCTION_SIGNOFF_TEMPLATE.md",
        "tools/check_cn_preview_health.py",
        "tools/check_cn_preview_module.py",
        "tools/check_cn_real_data_closed_loop.py",
        "tools/generate_cn_signoff_packet.py",
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
            "cit_reconciliation_runs": 0,
            "cit_filing_records": 0,
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
            "has_evidence_filing_payment_summary_evidence": True,
            "has_controlled_ai_guidance_evidence": True,
            "has_rule_source_governance_evidence": True,
            "has_iit_payroll_withholding_scope_evidence": True,
            "has_cross_border_review_scope_evidence": True,
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
    return SUMMARY._status(
        bundle_metadata=bundle_metadata_payload(),
        manifest=manifest_payload(),
        summary=summary_payload(),
        preview_health=preview_health_payload(),
        preview_module=preview_module_payload(),
        real_data_closed_loop=real_data_closed_loop_payload(),
        signoff_validation=signoff_validation,
        preview_url="http://127.0.0.1:18070/web/login?db=test",
    )


def delivery_status_with_manifest(manifest: dict) -> dict:
    return SUMMARY._status(
        bundle_metadata=bundle_metadata_payload(),
        manifest=manifest,
        summary=summary_payload(),
        preview_health=preview_health_payload(),
        preview_module=preview_module_payload(),
        real_data_closed_loop=real_data_closed_loop_payload(),
        signoff_validation=None,
        preview_url="http://127.0.0.1:18070/web/login?db=test",
    )


def complete_evidence(packet: dict, deployment_decision: str = "deploy") -> dict:
    evidence_notes = {
        "business_uat_decision": (
            "Completed UAT evidence for company CN Company and period 2026-06; "
            "controlled AI guidance evidence reviewed."
        ),
        "china_tax_professional_rule_signoff": (
            "Released rule official source packet reviewed by China tax professional."
        ),
        "official_source_freshness_review": (
            "Official source freshness and local jurisdiction updates reviewed."
        ),
        "customer_scope_and_data_gap_review": (
            "External dataset coverage, evidence gap register, open risk list and "
            "controlled AI limitation register reviewed."
        ),
        "representative_ux_walkthrough": (
            "Workbench, risk center, controlled AI guidance, filing/payment archive "
            "and report screens reviewed; input/output checksum and record checksum "
            "were visible."
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
        "decisions": decisions,
        "limitations": [],
    }


class TestChinaSignoffValidation(unittest.TestCase):
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
        for item in result["action_results"]:
            self.assertGreaterEqual(len(item["objective_areas"]), 1)

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
            "uat, company, period, controlled ai",
            result["blockers"],
        )

    def test_missing_ai_checksum_scope_blocks_ux_walkthrough(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet)
        for item in evidence["decisions"]:
            if item["key"] == "representative_ux_walkthrough":
                item["notes"] = (
                    "Workbench, risk center, controlled AI guidance, "
                    "filing/payment archive and report screens reviewed."
                )

        result = VALIDATION._validate(packet, evidence)

        self.assertFalse(result["ok"])
        self.assertIn(
            "representative_ux_walkthrough: evidence_reference or notes must "
            "mention: input/output checksum, record checksum",
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

    def test_signoff_packet_lists_missing_human_evidence(self):
        packet = PACKET._build_packet(status_payload())

        action_keys = {action["key"] for action in packet["production_actions"]}
        missing = {item["key"]: item for item in packet["missing_human_evidence"]}

        self.assertEqual(set(missing), action_keys)
        for item in missing.values():
            self.assertGreaterEqual(len(item["objective_areas"]), 1)
        self.assertIn("blocker_summary_walkthrough", missing)
        self.assertIn(
            "required_evidence",
            missing["blocker_summary_walkthrough"],
        )
        self.assertIn(
            "limitations and uncertainty visibility",
            missing["blocker_summary_walkthrough"]["objective_areas"],
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
        self.assertIn("blocker_summary_walkthrough", content)

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
        self.assertNotIn("Correct VAT filing mismatch", content)

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
        self.assertTrue(readiness["business_uat_ready"])
        self.assertFalse(readiness["production_signoff_ready"])
        self.assertIn(
            "business UAT decision must be recorded outside this automated status",
            readiness["production_signoff_blockers"],
        )

    def test_delivery_status_accepts_valid_signoff_validation(self):
        packet = PACKET._build_packet(status_payload())
        validation = VALIDATION._validate(packet, complete_evidence(packet))

        status = delivery_status(validation)

        readiness = status["readiness_gates"]
        self.assertTrue(readiness["business_uat_ready"])
        self.assertTrue(readiness["production_signoff_ready"])
        self.assertEqual(readiness["production_signoff_blockers"], [])
        self.assertEqual(status["signoff_validation"]["deployment_decision"], "deploy")

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

    def test_delivery_status_markdown_preserves_valid_chinese_and_masks_bad_text(self):
        self.assertFalse(SUMMARY._looks_mojibake("中国合规档案"))
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
                "next_action": "复核风险",
                "action_summary": "中国合规?档案",
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
        self.assertIn("VAT filing mismatch", content)
        self.assertIn("Correct VAT filing mismatch", content)
        self.assertIn("CN Compliance Report", content)
        self.assertIn("Risk level", content)
        self.assertIn("State/verification", content)
        self.assertIn("State/conclusion", content)

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
        self.assertIn("CODEX-DEMO China VAT source", content)
        self.assertIn("CN VAT Demo Rule / 2026.1", content)
        self.assertIn("Professional review", content)
        self.assertIn("No source monitor run sample was provided", content)

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

        self.assertTrue(coverage["vat"]["ready"])
        self.assertFalse(coverage["cit"]["ready"])
        self.assertTrue(coverage["iit"]["ready"])
        self.assertTrue(coverage["cross_border"]["ready"])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "status.md"

            SUMMARY._write_markdown(status, output)

            content = output.read_text(encoding="utf-8")
        self.assertIn("## Tax Domain Coverage Overview", content)
        self.assertIn("VAT invoice / filing / payment", content)
        self.assertIn("CIT accounting / filing", content)
        self.assertIn("IIT payroll / withholding / payment", content)
        self.assertIn("Cross-border and withholding review", content)
        self.assertIn("Representative UAT scope", content)
        self.assertIn("Fact-specific review remains required", content)

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


if __name__ == "__main__":
    unittest.main()
