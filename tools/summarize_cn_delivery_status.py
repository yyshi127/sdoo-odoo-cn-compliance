"""Summarize China delivery evidence for handoff review."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


STATUS_SCHEMA = "sdoo.cn.delivery-status.v1"
PREVIEW_HEALTH_SCHEMA = "sdoo.cn.preview-health.v1"
PREVIEW_MODULE_SCHEMA = "sdoo.cn.preview-module.v1"
REAL_DATA_CLOSED_LOOP_SCHEMA = "sdoo.cn.real-data-closed-loop.v1"
SIGNOFF_VALIDATION_SCHEMA = "sdoo.cn.signoff-validation.v1"
BUSINESS_UAT_PATH = Path("docs/CHINA_BUSINESS_UAT_CHECKLIST.md")
DELIVERY_INDEX_PATH = Path("docs/CHINA_DELIVERY_INDEX.md")
OBJECTIVE_COVERAGE_PATH = Path("docs/CHINA_DELIVERY_OBJECTIVE_COVERAGE.md")
PRODUCTION_SIGNOFF_PATH = Path("docs/CHINA_PRODUCTION_SIGNOFF_TEMPLATE.md")
PREVIEW_HEALTH_TOOL_PATH = Path("tools/check_cn_preview_health.py")
PREVIEW_MODULE_TOOL_PATH = Path("tools/check_cn_preview_module.py")
REAL_DATA_CLOSED_LOOP_TOOL_PATH = Path("tools/check_cn_real_data_closed_loop.py")
SIGNOFF_PACKET_TOOL_PATH = Path("tools/generate_cn_signoff_packet.py")
SIGNOFF_VALIDATION_TOOL_PATH = Path("tools/validate_cn_signoff_evidence.py")


def _manifest_includes(
    manifest: dict[str, object] | None,
    path: Path,
) -> bool:
    return bool(
        manifest
        and any(
            entry.get("path") == path.as_posix()
            for entry in manifest.get("files", [])
            if isinstance(entry, dict)
        )
    )


def _load(path: Path | None) -> dict[str, object] | None:
    if not path:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact_summary(payload: dict[str, object] | None) -> dict[str, object] | None:
    if payload is None:
        return None
    return {
        "schema": payload.get("schema"),
        "version": payload.get("version"),
        "file_count": payload.get("file_count"),
        "aggregate_sha256": payload.get("aggregate_sha256"),
        "bundle_sha256": payload.get("bundle_sha256"),
        "result": payload.get("result"),
        "source_control": payload.get("source_control"),
    }


def _runtime_summary(summary: dict[str, object] | None) -> dict[str, object] | None:
    if not summary:
        return None
    runtime = summary.get("runtime")
    if not isinstance(runtime, dict):
        return None
    log = runtime.get("log")
    return {
        "requested": runtime.get("requested"),
        "database": runtime.get("database"),
        "http_port": runtime.get("http_port"),
        "log": log if isinstance(log, dict) else None,
    }


def _source_control_blockers(source_control: object) -> list[str]:
    if not isinstance(source_control, dict):
        return ["source control evidence is missing"]
    blockers: list[str] = []
    if source_control.get("inside_worktree") is not True:
        blockers.append("source control evidence was not captured from a Git worktree")
    if not source_control.get("commit"):
        blockers.append("source commit is missing")
    if not source_control.get("branch"):
        blockers.append("source branch is missing")
    if source_control.get("dirty") is not False:
        blockers.append("source worktree is not confirmed clean")
    return blockers


def _status(
    *,
    bundle_metadata: dict[str, object] | None,
    manifest: dict[str, object] | None,
    summary: dict[str, object] | None,
    preview_health: dict[str, object] | None,
    preview_module: dict[str, object] | None,
    real_data_closed_loop: dict[str, object] | None,
    signoff_validation: dict[str, object] | None,
    preview_url: str | None,
) -> dict[str, object]:
    versions = {
        str(item.get("version"))
        for item in (bundle_metadata, manifest, summary)
        if item and item.get("version")
    }
    version = sorted(versions)[0] if len(versions) == 1 else None
    aggregate_values = {
        str(item.get("aggregate_sha256"))
        for item in (bundle_metadata, manifest)
        if item and item.get("aggregate_sha256")
    }
    runtime = _runtime_summary(summary)
    runtime_log = runtime.get("log") if isinstance(runtime, dict) else None
    runtime_passed = (
        isinstance(runtime_log, dict)
        and runtime_log.get("failed") == 0
        and runtime_log.get("errors") == 0
    )
    artifact_result = summary.get("result") if summary else None
    source_control = bundle_metadata.get("source_control") if bundle_metadata else None
    delivery_index = {
        "path": DELIVERY_INDEX_PATH.as_posix(),
        "included_in_manifest": _manifest_includes(manifest, DELIVERY_INDEX_PATH),
    }
    business_uat = {
        "path": BUSINESS_UAT_PATH.as_posix(),
        "included_in_manifest": _manifest_includes(manifest, BUSINESS_UAT_PATH),
    }
    objective_coverage = {
        "path": OBJECTIVE_COVERAGE_PATH.as_posix(),
        "included_in_manifest": _manifest_includes(manifest, OBJECTIVE_COVERAGE_PATH),
    }
    production_signoff = {
        "path": PRODUCTION_SIGNOFF_PATH.as_posix(),
        "included_in_manifest": _manifest_includes(manifest, PRODUCTION_SIGNOFF_PATH),
    }
    preview_health_checker = {
        "path": PREVIEW_HEALTH_TOOL_PATH.as_posix(),
        "included_in_manifest": _manifest_includes(manifest, PREVIEW_HEALTH_TOOL_PATH),
    }
    preview_module_checker = {
        "path": PREVIEW_MODULE_TOOL_PATH.as_posix(),
        "included_in_manifest": _manifest_includes(manifest, PREVIEW_MODULE_TOOL_PATH),
    }
    real_data_closed_loop_checker = {
        "path": REAL_DATA_CLOSED_LOOP_TOOL_PATH.as_posix(),
        "included_in_manifest": _manifest_includes(
            manifest, REAL_DATA_CLOSED_LOOP_TOOL_PATH
        ),
    }
    signoff_packet_tool = {
        "path": SIGNOFF_PACKET_TOOL_PATH.as_posix(),
        "included_in_manifest": _manifest_includes(manifest, SIGNOFF_PACKET_TOOL_PATH),
    }
    signoff_validation_tool = {
        "path": SIGNOFF_VALIDATION_TOOL_PATH.as_posix(),
        "included_in_manifest": _manifest_includes(
            manifest, SIGNOFF_VALIDATION_TOOL_PATH
        ),
    }
    preview_health_summary = None
    if preview_health:
        preview_health_summary = {
            "schema": preview_health.get("schema"),
            "url": preview_health.get("url"),
            "ok": preview_health.get("ok") is True,
            "status_code": preview_health.get("status_code"),
            "blocking_marker": preview_health.get("blocking_marker"),
            "error": preview_health.get("error"),
        }
    preview_module_summary = None
    if preview_module:
        preview_module_summary = {
            "schema": preview_module.get("schema"),
            "database": preview_module.get("database"),
            "expected_version": preview_module.get("expected_version"),
            "ok": preview_module.get("ok") is True,
            "module_state": preview_module.get("module_state"),
            "module_installed_version": preview_module.get("module_installed_version"),
            "country_pack_version": preview_module.get("country_pack_version"),
            "required_capabilities": preview_module.get("required_capabilities"),
            "error": preview_module.get("error"),
        }
    real_data_closed_loop_summary = None
    if real_data_closed_loop:
        readiness = real_data_closed_loop.get("readiness")
        real_data_closed_loop_summary = {
            "schema": real_data_closed_loop.get("schema"),
            "database": real_data_closed_loop.get("database"),
            "expected_version": real_data_closed_loop.get("expected_version"),
            "ok": real_data_closed_loop.get("ok") is True,
            "module_installed_version": (
                (real_data_closed_loop.get("module") or {}).get("installed_version")
                if isinstance(real_data_closed_loop.get("module"), dict)
                else None
            ),
            "country_pack_version": (
                (real_data_closed_loop.get("country_pack") or {}).get("version")
                if isinstance(real_data_closed_loop.get("country_pack"), dict)
                else None
            ),
            "accounting": real_data_closed_loop.get("accounting"),
            "objects": real_data_closed_loop.get("objects"),
            "sample_profiles": real_data_closed_loop.get("sample_profiles"),
            "sample_findings": real_data_closed_loop.get("sample_findings"),
            "sample_remediation_tasks": real_data_closed_loop.get(
                "sample_remediation_tasks"
            ),
            "sample_reports": real_data_closed_loop.get("sample_reports"),
            "sample_evidence": real_data_closed_loop.get("sample_evidence"),
            "sample_filing_archives": real_data_closed_loop.get(
                "sample_filing_archives"
            ),
            "readiness": readiness if isinstance(readiness, dict) else None,
            "error": real_data_closed_loop.get("error"),
        }
    signoff_validation_summary = None
    if signoff_validation:
        signoff_validation_summary = {
            "schema": signoff_validation.get("schema"),
            "version": signoff_validation.get("version"),
            "source_commit": signoff_validation.get("source_commit"),
            "preview_url": signoff_validation.get("preview_url"),
            "ok": signoff_validation.get("ok") is True,
            "production_signoff_ready": signoff_validation.get("production_signoff_ready") is True,
            "deployment_decision": signoff_validation.get("deployment_decision"),
            "blockers": signoff_validation.get("blockers"),
            "warnings": signoff_validation.get("warnings"),
            "blocked_objective_areas": signoff_validation.get("blocked_objective_areas"),
        }
    business_uat_blockers: list[str] = []
    if len(versions) > 1:
        business_uat_blockers.append("bundle, manifest and summary versions differ")
    if len(aggregate_values) > 1:
        business_uat_blockers.append("bundle and manifest aggregate checksums differ")
    if artifact_result != "passed":
        business_uat_blockers.append("automated acceptance did not pass")
    if isinstance(source_control, dict) and source_control.get("dirty") is True:
        business_uat_blockers.append("source worktree was dirty when delivery was built")
    if not runtime_passed:
        business_uat_blockers.append("Odoo runtime tests did not pass")
    for label, evidence in (
        ("delivery index", delivery_index),
        ("objective coverage", objective_coverage),
        ("business UAT checklist", business_uat),
        ("production sign-off template", production_signoff),
        ("preview health checker", preview_health_checker),
        ("preview module checker", preview_module_checker),
        ("real-data closed-loop checker", real_data_closed_loop_checker),
        ("production sign-off packet generator", signoff_packet_tool),
        ("production sign-off evidence validator", signoff_validation_tool),
    ):
        if not evidence["included_in_manifest"]:
            business_uat_blockers.append(f"{label} is not included in the manifest")
    if not preview_url:
        business_uat_blockers.append("preview URL was not recorded")
    if not preview_health_summary:
        business_uat_blockers.append("preview health result was not provided")
    else:
        if preview_health_summary["schema"] != PREVIEW_HEALTH_SCHEMA:
            business_uat_blockers.append("preview health result schema is invalid")
        if preview_health_summary["url"] != preview_url:
            business_uat_blockers.append("preview health URL does not match preview URL")
        if preview_health_summary["ok"] is not True:
            business_uat_blockers.append("preview health check did not pass")
    if not preview_module_summary:
        business_uat_blockers.append("preview module result was not provided")
    else:
        if preview_module_summary["schema"] != PREVIEW_MODULE_SCHEMA:
            business_uat_blockers.append("preview module result schema is invalid")
        if preview_module_summary["expected_version"] != version:
            business_uat_blockers.append("preview module expected version does not match delivery version")
        if preview_module_summary["ok"] is not True:
            business_uat_blockers.append("preview module check did not pass")
    if not real_data_closed_loop_summary:
        business_uat_blockers.append("real-data closed-loop result was not provided")
    else:
        if real_data_closed_loop_summary["schema"] != REAL_DATA_CLOSED_LOOP_SCHEMA:
            business_uat_blockers.append("real-data closed-loop result schema is invalid")
        if real_data_closed_loop_summary["expected_version"] != version:
            business_uat_blockers.append(
                "real-data closed-loop expected version does not match delivery version"
            )
        readiness = real_data_closed_loop_summary.get("readiness") or {}
        if not isinstance(readiness, dict) or readiness.get("demo_ready") is not True:
            business_uat_blockers.append("real-data demo readiness check did not pass")
    production_signoff_blockers = list(business_uat_blockers)
    production_signoff_ready = False
    if not signoff_validation_summary:
        production_signoff_blockers.extend(
            [
                "business UAT decision must be recorded outside this automated status",
                "current official sources and released rules require professional sign-off evidence",
                "customer-specific data gaps, evidence gaps and open critical risks must be reviewed",
            ]
        )
    elif signoff_validation_summary["schema"] != SIGNOFF_VALIDATION_SCHEMA:
        production_signoff_blockers.append("sign-off validation result schema is invalid")
    elif signoff_validation_summary["version"] != version:
        production_signoff_blockers.append("sign-off validation version does not match delivery version")
    elif signoff_validation_summary["source_commit"] != (
        source_control.get("commit") if isinstance(source_control, dict) else None
    ):
        production_signoff_blockers.append(
            "sign-off validation source commit does not match delivery source commit"
        )
    elif signoff_validation_summary["preview_url"] != preview_url:
        production_signoff_blockers.append(
            "sign-off validation preview URL does not match delivery preview URL"
        )
    elif signoff_validation_summary["production_signoff_ready"] is not True:
        blockers = signoff_validation_summary.get("blockers") or []
        production_signoff_blockers.extend(
            blockers if isinstance(blockers, list) else ["sign-off validation did not pass"]
        )
    else:
        production_signoff_ready = not production_signoff_blockers
    return {
        "schema": STATUS_SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "version_consistent": len(versions) <= 1,
        "aggregate_consistent": len(aggregate_values) <= 1,
        "acceptance_passed": artifact_result == "passed",
        "runtime_passed": runtime_passed,
        "version": version,
        "preview_url": preview_url,
        "source_control": source_control,
        "business_uat": business_uat,
        "delivery_index": delivery_index,
        "objective_coverage": objective_coverage,
        "production_signoff": production_signoff,
        "preview_health_checker": preview_health_checker,
        "preview_module_checker": preview_module_checker,
        "real_data_closed_loop_checker": real_data_closed_loop_checker,
        "signoff_packet_tool": signoff_packet_tool,
        "signoff_validation_tool": signoff_validation_tool,
        "preview_health": preview_health_summary,
        "preview_module": preview_module_summary,
        "real_data_closed_loop": real_data_closed_loop_summary,
        "signoff_validation": signoff_validation_summary,
        "readiness_gates": {
            "business_uat_ready": not business_uat_blockers,
            "business_uat_blockers": business_uat_blockers,
            "production_signoff_ready": production_signoff_ready,
            "production_signoff_blockers": production_signoff_blockers,
            "source_control_clean": not _source_control_blockers(source_control),
            "source_control_blockers": _source_control_blockers(source_control),
        },
        "bundle_metadata": _artifact_summary(bundle_metadata),
        "manifest": _artifact_summary(manifest),
        "acceptance_summary": _artifact_summary(summary),
        "runtime": runtime,
    }


def _write_markdown(status: dict[str, object], path: Path) -> None:
    bundle = status.get("bundle_metadata") or {}
    manifest = status.get("manifest") or {}
    acceptance = status.get("acceptance_summary") or {}
    runtime = status.get("runtime") or {}
    runtime_log = runtime.get("log") if isinstance(runtime, dict) else None
    source_control = status.get("source_control") or {}
    business_uat = status.get("business_uat") or {}
    delivery_index = status.get("delivery_index") or {}
    objective_coverage = status.get("objective_coverage") or {}
    production_signoff = status.get("production_signoff") or {}
    preview_health_checker = status.get("preview_health_checker") or {}
    preview_health = status.get("preview_health") or {}
    preview_module_checker = status.get("preview_module_checker") or {}
    preview_module = status.get("preview_module") or {}
    real_data_closed_loop_checker = status.get("real_data_closed_loop_checker") or {}
    signoff_packet_tool = status.get("signoff_packet_tool") or {}
    signoff_validation_tool = status.get("signoff_validation_tool") or {}
    real_data_closed_loop = status.get("real_data_closed_loop") or {}
    signoff_validation = status.get("signoff_validation") or {}
    real_data_readiness = real_data_closed_loop.get("readiness") or {}
    sample_profiles = real_data_closed_loop.get("sample_profiles") or []
    sample_findings = real_data_closed_loop.get("sample_findings") or []
    sample_tasks = real_data_closed_loop.get("sample_remediation_tasks") or []
    sample_reports = real_data_closed_loop.get("sample_reports") or []
    sample_evidence = real_data_closed_loop.get("sample_evidence") or []
    sample_filing_archives = real_data_closed_loop.get("sample_filing_archives") or []
    readiness = status.get("readiness_gates") or {}
    lines = [
        "# China Delivery Status",
        "",
        f"- Version consistent: `{status['version_consistent']}`",
        f"- Aggregate consistent: `{status['aggregate_consistent']}`",
        f"- Acceptance passed: `{status['acceptance_passed']}`",
        f"- Runtime passed: `{status['runtime_passed']}`",
        f"- Preview URL: `{status.get('preview_url') or ''}`",
        f"- Source branch: `{source_control.get('branch', '')}`",
        f"- Source commit: `{source_control.get('commit', '')}`",
        f"- Source worktree dirty: `{source_control.get('dirty', '')}`",
        f"- Delivery index: `{delivery_index.get('path', '')}`",
        f"- Delivery index in manifest: `{delivery_index.get('included_in_manifest', False)}`",
        f"- Business UAT checklist: `{business_uat.get('path', '')}`",
        f"- Business UAT checklist in manifest: `{business_uat.get('included_in_manifest', False)}`",
        f"- Objective coverage: `{objective_coverage.get('path', '')}`",
        f"- Objective coverage in manifest: `{objective_coverage.get('included_in_manifest', False)}`",
        f"- Production sign-off template: `{production_signoff.get('path', '')}`",
        f"- Production sign-off template in manifest: `{production_signoff.get('included_in_manifest', False)}`",
        f"- Preview health checker: `{preview_health_checker.get('path', '')}`",
        f"- Preview health checker in manifest: `{preview_health_checker.get('included_in_manifest', False)}`",
        f"- Preview health ok: `{preview_health.get('ok', False)}`",
        f"- Preview health status code: `{preview_health.get('status_code', '')}`",
        f"- Preview health blocking marker: `{preview_health.get('blocking_marker', '')}`",
        f"- Preview health error: `{preview_health.get('error', '')}`",
        f"- Preview module checker: `{preview_module_checker.get('path', '')}`",
        f"- Preview module checker in manifest: `{preview_module_checker.get('included_in_manifest', False)}`",
        f"- Preview module ok: `{preview_module.get('ok', False)}`",
        f"- Preview module version: `{preview_module.get('module_installed_version', '')}`",
        f"- Preview country pack version: `{preview_module.get('country_pack_version', '')}`",
        f"- Real-data closed-loop checker: `{real_data_closed_loop_checker.get('path', '')}`",
        f"- Real-data closed-loop checker in manifest: `{real_data_closed_loop_checker.get('included_in_manifest', False)}`",
        f"- Sign-off packet generator: `{signoff_packet_tool.get('path', '')}`",
        f"- Sign-off packet generator in manifest: `{signoff_packet_tool.get('included_in_manifest', False)}`",
        f"- Sign-off evidence validator: `{signoff_validation_tool.get('path', '')}`",
        f"- Sign-off evidence validator in manifest: `{signoff_validation_tool.get('included_in_manifest', False)}`",
        f"- Real-data setup demo ready: `{real_data_readiness.get('setup_demo_ready', False)}`",
        f"- Real-data demo ready: `{real_data_readiness.get('demo_ready', False)}`",
        f"- Real-data closed-loop evidence ready: `{real_data_readiness.get('closed_loop_evidence_ready', False)}`",
        f"- Workbench summary evidence ready: `{real_data_readiness.get('has_workbench_summary_evidence', False)}`",
        f"- Risk/task/report summary evidence ready: `{real_data_readiness.get('has_risk_task_report_summary_evidence', False)}`",
        f"- Evidence/filing/payment summary evidence ready: `{real_data_readiness.get('has_evidence_filing_payment_summary_evidence', False)}`",
        f"- Sign-off validation ok: `{signoff_validation.get('ok', False)}`",
        f"- Sign-off deployment decision: `{signoff_validation.get('deployment_decision', '')}`",
        f"- Business UAT ready: `{readiness.get('business_uat_ready', False)}`",
        f"- Production sign-off ready: `{readiness.get('production_signoff_ready', False)}`",
        "",
        "## Readiness Gates",
        "",
        "### Business UAT Blockers",
        "",
        *[
            f"- {blocker}"
            for blocker in readiness.get("business_uat_blockers", [])
        ],
        "",
        "### Production Sign-off Blockers",
        "",
        *[
            f"- {blocker}"
            for blocker in readiness.get("production_signoff_blockers", [])
        ],
        "",
        "### Production Blocked Objective Areas",
        "",
        *[
            f"- {area}"
            for area in signoff_validation.get("blocked_objective_areas", []) or []
        ],
        "",
        "## Artifacts",
        "",
        f"- Bundle version: `{bundle.get('version', '')}`",
        f"- Bundle SHA-256: `{bundle.get('bundle_sha256', '')}`",
        f"- Manifest files: `{manifest.get('file_count', '')}`",
        f"- Manifest aggregate SHA-256: `{manifest.get('aggregate_sha256', '')}`",
        f"- Acceptance result: `{acceptance.get('result', '')}`",
        "",
        "## Workbench Summary Evidence",
        "",
        *(
            [
                line
                for profile in sample_profiles[:5]
                if isinstance(profile, dict)
                for line in (
                    f"### {profile.get('name') or profile.get('company') or profile.get('id') or 'Compliance Profile'}",
                    "",
                    f"- Company: `{profile.get('company', '')}`",
                    f"- Status: `{profile.get('status', '')}`",
                    f"- Period: `{profile.get('period_label', '')}`",
                    f"- Next action: `{profile.get('next_action', '')}`",
                    f"- Action summary: {profile.get('action_summary', '')}",
                    f"- Rule basis: `{profile.get('rule_basis_state', '')}` - {profile.get('rule_basis_summary', '')}",
                    f"- Limitations: {profile.get('limitation_summary', '')}",
                    f"- Uncertainty: {profile.get('uncertainty_summary', '')}",
                    f"- Limitation next action: {profile.get('limitation_next_action', '')}",
                    "",
                )
            ]
            if isinstance(sample_profiles, list) and sample_profiles
            else ["- No sample profile workbench summary evidence was provided.", ""]
        ),
        "## Risk, Remediation and Report Summary Evidence",
        "",
        "### Sample Risks",
        "",
        *(
            [
                line
                for finding in sample_findings[:5]
                if isinstance(finding, dict)
                for line in (
                    f"#### {finding.get('title') or finding.get('name') or finding.get('id') or 'Risk'}",
                    "",
                    f"- Company: `{finding.get('company', '')}`",
                    f"- Period: `{finding.get('period_label', '')}`",
                    f"- Risk level: `{finding.get('risk_level', '')}`",
                    f"- Result/review: `{finding.get('result', '')}` / `{finding.get('review_state', '')}`",
                    f"- Tax impact: {finding.get('tax_impact', '')}",
                    f"- Rule basis: `{finding.get('rule_basis_state', '')}` / `{finding.get('professional_state', '')}`",
                    f"- Evidence/closure: `{finding.get('evidence_state', '')}` / `{finding.get('closure_state', '')}`",
                    f"- Next action: {finding.get('next_action', '')}",
                    f"- Action summary: {finding.get('action_summary', '')}",
                    "",
                )
            ]
            if isinstance(sample_findings, list) and sample_findings
            else ["- No sample risk summary evidence was provided.", ""]
        ),
        "### Sample Remediation Tasks",
        "",
        *(
            [
                line
                for task in sample_tasks[:5]
                if isinstance(task, dict)
                for line in (
                    f"#### {task.get('name') or task.get('id') or 'Remediation Task'}",
                    "",
                    f"- Company: `{task.get('company', '')}`",
                    f"- Risk level: `{task.get('risk_level', '')}`",
                    f"- State/verification: `{task.get('state', '')}` / `{task.get('verification_state', '')}`",
                    f"- Assignee/due date: `{task.get('assignee', '')}` / `{task.get('due_date', '')}`",
                    f"- Evidence/traceability: `{task.get('evidence_state', '')}` / `{task.get('traceability_state', '')}`",
                    f"- Next action: {task.get('next_action', '')}",
                    f"- Action summary: {task.get('action_summary', '')}",
                    "",
                )
            ]
            if isinstance(sample_tasks, list) and sample_tasks
            else ["- No sample remediation summary evidence was provided.", ""]
        ),
        "### Sample Reports",
        "",
        *(
            [
                line
                for report in sample_reports[:5]
                if isinstance(report, dict)
                for line in (
                    f"#### {report.get('name') or report.get('id') or 'Compliance Report'}",
                    "",
                    f"- Company: `{report.get('company', '')}`",
                    f"- Period: `{report.get('period_start', '')}` to `{report.get('period_end', '')}`",
                    f"- State/conclusion: `{report.get('state', '')}` / `{report.get('conclusion_state', '')}`",
                    f"- Traceability/fact basis: `{report.get('traceability_state', '')}` / `{report.get('fact_basis_state', '')}`",
                    f"- Integrity: center `{report.get('center_integrity_state', '')}`, snapshot `{report.get('snapshot_integrity_state', '')}`, approval `{report.get('approval_integrity_state', '')}`, pdf `{report.get('pdf_integrity_state', '')}`",
                    f"- Next action: {report.get('traceability_next_action', '')}",
                    "",
                )
            ]
            if isinstance(sample_reports, list) and sample_reports
            else ["- No sample report summary evidence was provided.", ""]
        ),
        "## Evidence, Filing and Payment Archive Summary Evidence",
        "",
        "### Sample Evidence",
        "",
        *(
            [
                line
                for evidence in sample_evidence[:5]
                if isinstance(evidence, dict)
                for line in (
                    f"#### {evidence.get('name') or evidence.get('id') or 'Evidence'}",
                    "",
                    f"- Company: `{evidence.get('company', '')}`",
                    f"- State: `{evidence.get('state', '')}`",
                    f"- Source: {evidence.get('source_summary', '')}",
                    f"- Blockers: {evidence.get('blocker_summary', '')}",
                    f"- Verified by/at: `{evidence.get('verified_by', '')}` / `{evidence.get('verified_at', '')}`",
                    f"- Checksum present: `{bool(evidence.get('document_checksum'))}`",
                    "",
                )
            ]
            if isinstance(sample_evidence, list) and sample_evidence
            else ["- No sample evidence summary was provided.", ""]
        ),
        "### Sample Filing and Payment Archives",
        "",
        *(
            [
                line
                for filing in sample_filing_archives[:5]
                if isinstance(filing, dict)
                for line in (
                    f"#### {filing.get('name') or filing.get('id') or 'Filing Archive'}",
                    "",
                    f"- Company: `{filing.get('company', '')}`",
                    f"- Kind/period: `{filing.get('kind', '')}` / `{filing.get('period_label', '')}`",
                    f"- State/payment: `{filing.get('state', '')}` / `{filing.get('payment_state', '')}`",
                    f"- Due date: `{filing.get('due_date', '')}`",
                    f"- Submission/payment integrity: `{filing.get('submission_integrity_state', '')}` / `{filing.get('payment_integrity_state', '')}`",
                    f"- Evidence: `{filing.get('evidence_state', '')}` ({filing.get('verified_evidence_count', 0)}/{filing.get('evidence_count', 0)})",
                    f"- Blockers: {filing.get('blocker_summary', '')}",
                    f"- Next action: {filing.get('next_action', '')}",
                    f"- Checksums present: submission `{bool(filing.get('submission_checksum'))}`, payment `{bool(filing.get('payment_checksum'))}`",
                    "",
                )
            ]
            if isinstance(sample_filing_archives, list) and sample_filing_archives
            else ["- No sample filing/payment archive summary was provided.", ""]
        ),
        "## Runtime",
        "",
        f"- Database: `{runtime.get('database', '') if isinstance(runtime, dict) else ''}`",
        f"- Log: `{runtime_log or ''}`",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize China delivery status.")
    parser.add_argument("--bundle-metadata", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--preview-health", type=Path)
    parser.add_argument("--preview-module", type=Path)
    parser.add_argument("--real-data-closed-loop", type=Path)
    parser.add_argument("--signoff-validation", type=Path)
    parser.add_argument("--preview-url")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument(
        "--require-business-uat-ready",
        action="store_true",
        help="Exit with status 2 unless the delivery evidence is ready for business UAT.",
    )
    parser.add_argument(
        "--require-production-signoff-ready",
        action="store_true",
        help="Exit with status 3 unless production sign-off readiness is explicitly satisfied.",
    )
    parser.add_argument(
        "--require-source-control-clean",
        action="store_true",
        help="Exit with status 4 unless source-control evidence has a branch, commit and clean worktree.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    status = _status(
        bundle_metadata=_load(args.bundle_metadata),
        manifest=_load(args.manifest),
        summary=_load(args.summary),
        preview_health=_load(args.preview_health),
        preview_module=_load(args.preview_module),
        real_data_closed_loop=_load(args.real_data_closed_loop),
        signoff_validation=_load(args.signoff_validation),
        preview_url=args.preview_url,
    )
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.markdown_output:
        _write_markdown(status, args.markdown_output)
    if not args.json_output and not args.markdown_output:
        print(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "delivery status summarized: "
            f"version_consistent={status['version_consistent']} "
            f"acceptance_passed={status['acceptance_passed']} "
            f"runtime_passed={status['runtime_passed']}"
        )
    readiness = status.get("readiness_gates") or {}
    if (
        args.require_business_uat_ready
        and readiness.get("business_uat_ready") is not True
    ):
        blockers = readiness.get("business_uat_blockers") or []
        print(f"business UAT readiness gate failed: {blockers}")
        return 2
    if (
        args.require_production_signoff_ready
        and readiness.get("production_signoff_ready") is not True
    ):
        blockers = readiness.get("production_signoff_blockers") or []
        print(f"production sign-off readiness gate failed: {blockers}")
        return 3
    if (
        args.require_source_control_clean
        and readiness.get("source_control_clean") is not True
    ):
        blockers = readiness.get("source_control_blockers") or []
        print(f"source-control readiness gate failed: {blockers}")
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
