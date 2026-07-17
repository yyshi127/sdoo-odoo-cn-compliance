"""Summarize China delivery evidence for handoff review."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


STATUS_SCHEMA = "sdoo.cn.delivery-status.v1"
PREVIEW_HEALTH_SCHEMA = "sdoo.cn.preview-health.v1"
PREVIEW_MODULE_SCHEMA = "sdoo.cn.preview-module.v1"
BUSINESS_UAT_PATH = Path("docs/CHINA_BUSINESS_UAT_CHECKLIST.md")
DELIVERY_INDEX_PATH = Path("docs/CHINA_DELIVERY_INDEX.md")
OBJECTIVE_COVERAGE_PATH = Path("docs/CHINA_DELIVERY_OBJECTIVE_COVERAGE.md")
PRODUCTION_SIGNOFF_PATH = Path("docs/CHINA_PRODUCTION_SIGNOFF_TEMPLATE.md")
PREVIEW_HEALTH_TOOL_PATH = Path("tools/check_cn_preview_health.py")
PREVIEW_MODULE_TOOL_PATH = Path("tools/check_cn_preview_module.py")


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
    production_signoff_blockers = list(business_uat_blockers)
    production_signoff_blockers.extend(
        [
            "business UAT decision must be recorded outside this automated status",
            "current official sources and released rules require professional sign-off evidence",
            "customer-specific data gaps, evidence gaps and open critical risks must be reviewed",
        ]
    )
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
        "preview_health": preview_health_summary,
        "preview_module": preview_module_summary,
        "readiness_gates": {
            "business_uat_ready": not business_uat_blockers,
            "business_uat_blockers": business_uat_blockers,
            "production_signoff_ready": False,
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
        "## Artifacts",
        "",
        f"- Bundle version: `{bundle.get('version', '')}`",
        f"- Bundle SHA-256: `{bundle.get('bundle_sha256', '')}`",
        f"- Manifest files: `{manifest.get('file_count', '')}`",
        f"- Manifest aggregate SHA-256: `{manifest.get('aggregate_sha256', '')}`",
        f"- Acceptance result: `{acceptance.get('result', '')}`",
        "",
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
