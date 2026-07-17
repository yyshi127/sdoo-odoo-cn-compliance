"""Summarize China delivery evidence for handoff review."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


STATUS_SCHEMA = "sdoo.cn.delivery-status.v1"
BUSINESS_UAT_PATH = Path("docs/CHINA_BUSINESS_UAT_CHECKLIST.md")
OBJECTIVE_COVERAGE_PATH = Path("docs/CHINA_DELIVERY_OBJECTIVE_COVERAGE.md")
PRODUCTION_SIGNOFF_PATH = Path("docs/CHINA_PRODUCTION_SIGNOFF_TEMPLATE.md")


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


def _status(
    *,
    bundle_metadata: dict[str, object] | None,
    manifest: dict[str, object] | None,
    summary: dict[str, object] | None,
    preview_url: str | None,
) -> dict[str, object]:
    versions = {
        str(item.get("version"))
        for item in (bundle_metadata, manifest, summary)
        if item and item.get("version")
    }
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
    return {
        "schema": STATUS_SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "version_consistent": len(versions) <= 1,
        "aggregate_consistent": len(aggregate_values) <= 1,
        "acceptance_passed": artifact_result == "passed",
        "runtime_passed": runtime_passed,
        "preview_url": preview_url,
        "business_uat": {
            "path": BUSINESS_UAT_PATH.as_posix(),
            "included_in_manifest": bool(
                manifest
                and any(
                    entry.get("path") == BUSINESS_UAT_PATH.as_posix()
                    for entry in manifest.get("files", [])
                    if isinstance(entry, dict)
                )
            ),
        },
        "objective_coverage": {
            "path": OBJECTIVE_COVERAGE_PATH.as_posix(),
            "included_in_manifest": bool(
                manifest
                and any(
                    entry.get("path") == OBJECTIVE_COVERAGE_PATH.as_posix()
                    for entry in manifest.get("files", [])
                    if isinstance(entry, dict)
                )
            ),
        },
        "production_signoff": {
            "path": PRODUCTION_SIGNOFF_PATH.as_posix(),
            "included_in_manifest": bool(
                manifest
                and any(
                    entry.get("path") == PRODUCTION_SIGNOFF_PATH.as_posix()
                    for entry in manifest.get("files", [])
                    if isinstance(entry, dict)
                )
            ),
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
    business_uat = status.get("business_uat") or {}
    objective_coverage = status.get("objective_coverage") or {}
    production_signoff = status.get("production_signoff") or {}
    lines = [
        "# China Delivery Status",
        "",
        f"- Version consistent: `{status['version_consistent']}`",
        f"- Aggregate consistent: `{status['aggregate_consistent']}`",
        f"- Acceptance passed: `{status['acceptance_passed']}`",
        f"- Runtime passed: `{status['runtime_passed']}`",
        f"- Preview URL: `{status.get('preview_url') or ''}`",
        f"- Business UAT checklist: `{business_uat.get('path', '')}`",
        f"- Business UAT checklist in manifest: `{business_uat.get('included_in_manifest', False)}`",
        f"- Objective coverage: `{objective_coverage.get('path', '')}`",
        f"- Objective coverage in manifest: `{objective_coverage.get('included_in_manifest', False)}`",
        f"- Production sign-off template: `{production_signoff.get('path', '')}`",
        f"- Production sign-off template in manifest: `{production_signoff.get('included_in_manifest', False)}`",
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
    parser.add_argument("--preview-url")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    status = _status(
        bundle_metadata=_load(args.bundle_metadata),
        manifest=_load(args.manifest),
        summary=_load(args.summary),
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
