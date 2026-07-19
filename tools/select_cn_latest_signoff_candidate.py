"""Select and validate the latest China sign-off evidence candidate."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DIST = REPOSITORY_ROOT / "dist"
SCHEMA = "sdoo.cn.latest-signoff-candidate.v1"
STATUS_PATTERN = re.compile(r"^cn_delivery_m(?P<number>\d+)_chain_status\.json$")


@dataclass(frozen=True)
class CandidatePaths:
    number: int
    bundle: Path
    bundle_metadata: Path
    manifest: Path
    remote_acceptance: Path
    remote_upgrade_acceptance: Path
    preview_health: Path
    preview_module: Path
    real_data_closed_loop: Path
    status: Path
    signoff_packet: Path
    production_signoff_actions: Path
    objective_audit: Path


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _candidate_paths(dist_dir: Path, number: int) -> CandidatePaths:
    tag = f"m{number}"
    return CandidatePaths(
        number=number,
        bundle=dist_dir / f"sdoo-cn-compliance-delivery-{tag}.tgz",
        bundle_metadata=dist_dir / f"sdoo-cn-compliance-delivery-{tag}.bundle.json",
        manifest=dist_dir / f"cn_delivery_manifest_{tag}_full.json",
        remote_acceptance=dist_dir / f"cn_delivery_acceptance_{tag}_remote.json",
        remote_upgrade_acceptance=dist_dir
        / f"cn_delivery_acceptance_{tag}_upgrade_remote.json",
        preview_health=dist_dir / f"cn_preview_health_{tag}.json",
        preview_module=dist_dir / f"cn_preview_module_{tag}.json",
        real_data_closed_loop=dist_dir / f"cn_real_data_closed_loop_{tag}.json",
        status=dist_dir / f"cn_delivery_{tag}_chain_status.json",
        signoff_packet=dist_dir / f"cn_delivery_{tag}_chain_signoff_packet.json",
        production_signoff_actions=dist_dir
        / f"cn_delivery_{tag}_chain_production_signoff_actions.json",
        objective_audit=dist_dir / f"cn_delivery_{tag}_chain_objective_audit.json",
    )


def _discover_numbers(dist_dir: Path) -> list[int]:
    if not dist_dir.is_dir():
        return []
    numbers: list[int] = []
    for path in dist_dir.iterdir():
        match = STATUS_PATTERN.match(path.name)
        if match:
            numbers.append(int(match.group("number")))
    return sorted(set(numbers))


def _missing(paths: CandidatePaths) -> list[str]:
    missing: list[str] = []
    for field in paths.__dataclass_fields__:
        if field == "number":
            continue
        path = getattr(paths, field)
        if not path.is_file():
            missing.append(path.as_posix())
    return missing


def _source_commit(payload: dict[str, Any]) -> str | None:
    source_control = payload.get("source_control")
    if isinstance(source_control, dict):
        commit = source_control.get("commit")
        if isinstance(commit, str):
            return commit
    commit = payload.get("git_commit") or payload.get("source_commit")
    return commit if isinstance(commit, str) else None


def _manifest_summary(payload: dict[str, Any]) -> dict[str, Any]:
    manifest = payload.get("manifest")
    return manifest if isinstance(manifest, dict) else payload


def _runtime_ok(payload: dict[str, Any]) -> bool:
    if payload.get("result") != "passed":
        return False
    runtime = payload.get("runtime")
    if not isinstance(runtime, dict):
        return False
    log = runtime.get("log")
    if not isinstance(log, dict):
        return False
    return log.get("failed") == 0 and log.get("errors") == 0


def _validate_candidate(paths: CandidatePaths) -> dict[str, Any]:
    missing = _missing(paths)
    if missing:
        return {
            "candidate": f"m{paths.number}",
            "ok": False,
            "missing_files": missing,
            "errors": ["candidate evidence set is incomplete"],
        }

    bundle_metadata = _load(paths.bundle_metadata)
    manifest = _load(paths.manifest)
    remote_acceptance = _load(paths.remote_acceptance)
    remote_upgrade = _load(paths.remote_upgrade_acceptance)
    status = _load(paths.status)
    packet = _load(paths.signoff_packet)
    actions = _load(paths.production_signoff_actions)
    audit = _load(paths.objective_audit)
    preview_health = _load(paths.preview_health)
    preview_module = _load(paths.preview_module)
    real_data = _load(paths.real_data_closed_loop)

    errors: list[str] = []
    version = manifest.get("version")
    aggregate = manifest.get("aggregate_sha256")
    commit = _source_commit(manifest)

    for label, payload in (
        ("bundle metadata", bundle_metadata),
        ("status", status),
        ("sign-off packet", packet),
        ("production sign-off actions", actions),
        ("objective audit", audit),
    ):
        payload_version = payload.get("version")
        if payload_version != version:
            errors.append(f"{label} version mismatch: {payload_version!r} != {version!r}")

    for label, payload in (
        ("bundle metadata", bundle_metadata),
        ("status", status),
        ("sign-off packet", packet),
        ("production sign-off actions", actions),
    ):
        payload_commit = _source_commit(payload)
        if payload_commit != commit:
            errors.append(f"{label} commit mismatch: {payload_commit!r} != {commit!r}")

    bundle_aggregate = bundle_metadata.get("aggregate_sha256")
    if bundle_aggregate != aggregate:
        errors.append(
            f"bundle metadata aggregate mismatch: {bundle_aggregate!r} != {aggregate!r}"
        )

    for label, payload in (
        ("remote acceptance", remote_acceptance),
        ("remote upgrade acceptance", remote_upgrade),
    ):
        summary_manifest = _manifest_summary(payload)
        summary_aggregate = summary_manifest.get("aggregate_sha256")
        if summary_aggregate is not None and summary_aggregate != aggregate:
            errors.append(f"{label} manifest aggregate mismatch")
        summary_version = payload.get("version")
        if summary_version != version:
            errors.append(f"{label} version mismatch: {summary_version!r} != {version!r}")
        if not _runtime_ok(payload):
            errors.append(f"{label} runtime acceptance did not pass")

    source_control = manifest.get("source_control")
    if not isinstance(source_control, dict) or source_control.get("dirty") is not False:
        errors.append("manifest source-control state is not clean")

    readiness = status.get("readiness_gates")
    if not isinstance(readiness, dict):
        errors.append("status does not include readiness gates")
        readiness = {}
    for key in ("preview_ready", "compliance_scope_ready", "business_uat_ready"):
        if readiness.get(key) is not True:
            errors.append(f"status readiness gate {key} is not true")
    if readiness.get("production_signoff_ready") is not False:
        errors.append("unsigned candidate should remain production_signoff_ready=false")
    if actions.get("production_signoff_ready") is not False:
        errors.append("action checklist should remain production_signoff_ready=false")
    if actions.get("action_count") != len(
        readiness.get("production_signoff_required_actions") or []
    ):
        errors.append("action checklist count does not match status required actions")
    action_binding = actions.get("packet_binding")
    if not isinstance(action_binding, dict):
        errors.append("action checklist does not include packet binding")
    else:
        for key in (
            "provided",
            "schema_ok",
            "version_matches_status",
            "source_commit_matches_status",
            "preview_url_matches_status",
            "action_keys_match",
        ):
            if action_binding.get(key) is not True:
                errors.append(f"action checklist packet binding {key} is not true")

    if preview_health.get("ok") is not True:
        errors.append("preview health is not ok")
    if preview_module.get("ok") is not True:
        errors.append("preview module check is not ok")
    if real_data.get("ok") is not True:
        errors.append("real-data closed-loop check is not ok")

    return {
        "candidate": f"m{paths.number}",
        "ok": not errors,
        "version": version,
        "source_commit": commit,
        "source_branch": source_control.get("branch") if isinstance(source_control, dict) else None,
        "source_clean": source_control.get("dirty") is False if isinstance(source_control, dict) else False,
        "manifest_aggregate_sha256": aggregate,
        "bundle_sha256": bundle_metadata.get("bundle_sha256"),
        "file_count": manifest.get("file_count"),
        "business_uat_ready": readiness.get("business_uat_ready"),
        "production_signoff_ready": readiness.get("production_signoff_ready"),
        "production_required_action_count": len(
            readiness.get("production_signoff_required_actions") or []
        ),
        "paths": {
            field: getattr(paths, field).as_posix()
            for field in paths.__dataclass_fields__
            if field != "number"
        },
        "errors": errors,
    }


def select_latest(
    dist_dir: Path = DIST,
    *,
    require_highest_status_complete: bool = False,
) -> dict[str, Any]:
    checked: list[dict[str, Any]] = []
    numbers = _discover_numbers(dist_dir)
    highest_number = numbers[-1] if numbers else None
    for number in reversed(numbers):
        candidate = _validate_candidate(_candidate_paths(dist_dir, number))
        checked.append(candidate)
        if candidate["ok"]:
            if require_highest_status_complete and number != highest_number:
                return {
                    "schema": SCHEMA,
                    "selected": None,
                    "checked_candidates": checked,
                    "errors": [
                        (
                            "latest discovered status candidate is incomplete; "
                            f"refusing to select older {candidate['candidate']}"
                        )
                    ],
                }
            return {
                "schema": SCHEMA,
                "selected": candidate,
                "checked_candidates": checked,
                "errors": [],
            }
    return {
        "schema": SCHEMA,
        "selected": None,
        "checked_candidates": checked,
        "errors": ["no complete candidate evidence set was found"] if checked else [],
    }


def _write_markdown(payload: dict[str, Any], path: Path) -> None:
    selected = payload.get("selected")
    lines = ["# China Latest Sign-off Candidate", ""]
    if not isinstance(selected, dict):
        lines.append("No complete sign-off candidate evidence set was found.")
    else:
        lines.extend(
            [
                f"- Candidate: `{selected['candidate']}`",
                f"- Version: `{selected.get('version')}`",
                f"- Source commit: `{selected.get('source_commit')}`",
                f"- Manifest aggregate SHA-256: `{selected.get('manifest_aggregate_sha256')}`",
                f"- Business UAT ready: `{selected.get('business_uat_ready')}`",
                f"- Production sign-off ready: `{selected.get('production_signoff_ready')}`",
                f"- Required human actions: `{selected.get('production_required_action_count')}`",
                "",
                "Use this exact candidate number for the production sign-off runbook.",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Select the latest complete China production sign-off candidate."
    )
    parser.add_argument("--dist-dir", type=Path, default=DIST)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument(
        "--require-found",
        action="store_true",
        help="Exit with an error when no complete candidate can be selected.",
    )
    parser.add_argument(
        "--require-highest-status-complete",
        action="store_true",
        help=(
            "Exit with an error instead of selecting an older complete candidate "
            "when a newer mNNN status file exists but is incomplete or invalid."
        ),
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    payload = select_latest(
        args.dist_dir,
        require_highest_status_complete=args.require_highest_status_complete,
    )
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.markdown_output:
        _write_markdown(payload, args.markdown_output)
    selected = payload.get("selected")
    if not isinstance(selected, dict):
        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            message = "; ".join(str(error) for error in errors)
        else:
            message = "no complete China sign-off candidate found"
        if args.require_found:
            raise SystemExit(message)
        print(message)
        return 0
    print(
        "selected China sign-off candidate: "
        f"{selected['candidate']} / {selected.get('version')} / "
        f"{selected.get('source_commit')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
