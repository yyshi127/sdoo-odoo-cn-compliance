"""Export reviewer-facing China production sign-off actions."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ACTIONS_SCHEMA = "sdoo.cn.production-signoff-actions.v1"
STATUS_SCHEMA = "sdoo.cn.delivery-status.v1"
PACKET_SCHEMA = "sdoo.cn.signoff-packet.v1"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _action_key(action: dict[str, Any]) -> str:
    return str(action.get("key") or "")


def _unique_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for action in actions:
        key = _action_key(action)
        if not key:
            continue
        by_key.setdefault(
            key,
            {
                "key": key,
                "owner": action.get("owner"),
                "required_evidence": action.get("required_evidence"),
                "acceptable_decisions": action.get("acceptable_decisions") or [],
                "objective_areas": action.get("objective_areas") or [],
                "addresses_blockers": action.get("addresses_blockers") or [],
            },
        )
    return list(by_key.values())


def _owner_summary(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_owner: dict[str, dict[str, Any]] = {}
    for action in actions:
        owner = str(action.get("owner") or "unassigned")
        entry = by_owner.setdefault(
            owner,
            {
                "owner": owner,
                "action_count": 0,
                "action_keys": [],
                "addresses_blockers": [],
            },
        )
        entry["action_count"] += 1
        entry["action_keys"].append(action["key"])
        for blocker in action.get("addresses_blockers") or []:
            if blocker not in entry["addresses_blockers"]:
                entry["addresses_blockers"].append(blocker)
    return sorted(by_owner.values(), key=lambda item: item["owner"])


def _packet_binding(
    status: dict[str, Any],
    packet: dict[str, Any] | None,
    actions: list[dict[str, Any]],
) -> dict[str, Any]:
    if packet is None:
        return {
            "provided": False,
            "schema_ok": False,
            "version_matches_status": False,
            "source_commit_matches_status": False,
            "bundle_sha256_matches_status": False,
            "manifest_aggregate_sha256_matches_status": False,
            "preview_url_matches_status": False,
            "preview_database_matches_status": False,
            "action_keys_match": False,
            "missing_packet_action_keys": [],
            "extra_packet_action_keys": [],
        }
    status_commit = (status.get("source_control") or {}).get("commit")
    bundle = status.get("bundle_metadata") or {}
    manifest = status.get("manifest") or {}
    action_keys = {_action_key(action) for action in actions if _action_key(action)}
    packet_keys = {
        _action_key(action)
        for action in packet.get("production_actions") or []
        if isinstance(action, dict) and _action_key(action)
    }
    return {
        "provided": True,
        "schema_ok": packet.get("schema") == PACKET_SCHEMA,
        "version_matches_status": packet.get("version") == status.get("version"),
        "source_commit_matches_status": packet.get("source_commit") == status_commit,
        "bundle_sha256_matches_status": packet.get("bundle_sha256")
        == bundle.get("bundle_sha256"),
        "manifest_aggregate_sha256_matches_status": packet.get(
            "manifest_aggregate_sha256"
        )
        == manifest.get("aggregate_sha256"),
        "preview_url_matches_status": packet.get("preview_url")
        == status.get("preview_url"),
        "preview_database_matches_status": packet.get("preview_database")
        == status.get("preview_database"),
        "action_keys_match": action_keys == packet_keys,
        "missing_packet_action_keys": sorted(action_keys - packet_keys),
        "extra_packet_action_keys": sorted(packet_keys - action_keys),
    }


def export_actions(
    status: dict[str, Any],
    packet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if status.get("schema") != STATUS_SCHEMA:
        raise ValueError("delivery status schema is invalid")
    readiness = status.get("readiness_gates") or {}
    actions = _unique_actions(
        [
            action
            for action in readiness.get("production_signoff_required_actions") or []
            if isinstance(action, dict)
        ]
    )
    source_control = status.get("source_control") or {}
    bundle = status.get("bundle_metadata") or {}
    manifest = status.get("manifest") or {}
    return {
        "schema": ACTIONS_SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "version": status.get("version"),
        "source_commit": source_control.get("commit"),
        "bundle_sha256": bundle.get("bundle_sha256"),
        "manifest_aggregate_sha256": manifest.get("aggregate_sha256"),
        "source_branch": source_control.get("branch"),
        "source_control_clean": readiness.get("source_control_clean") is True,
        "preview_url": status.get("preview_url"),
        "preview_database": status.get("preview_database"),
        "business_uat_ready": readiness.get("business_uat_ready") is True,
        "production_signoff_ready": readiness.get("production_signoff_ready") is True,
        "production_signoff_blockers": readiness.get("production_signoff_blockers")
        or [],
        "action_count": len(actions),
        "owner_summary": _owner_summary(actions),
        "actions": actions,
        "blocker_action_matrix": readiness.get(
            "production_signoff_blocker_action_matrix"
        )
        or [],
        "packet_binding": _packet_binding(status, packet, actions),
    }


def _write_markdown(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# China Production Sign-off Action Checklist",
        "",
        f"- Version: `{payload.get('version') or ''}`",
        f"- Source branch: `{payload.get('source_branch') or ''}`",
        f"- Source commit: `{payload.get('source_commit') or ''}`",
        f"- Bundle SHA-256: `{payload.get('bundle_sha256') or ''}`",
        f"- Manifest aggregate SHA-256: `{payload.get('manifest_aggregate_sha256') or ''}`",
        f"- Source control clean: `{payload.get('source_control_clean')}`",
        f"- Preview URL: `{payload.get('preview_url') or ''}`",
        f"- Preview database: `{payload.get('preview_database') or ''}`",
        f"- Business UAT ready: `{payload.get('business_uat_ready')}`",
        f"- Production sign-off ready: `{payload.get('production_signoff_ready')}`",
        f"- Action count: `{payload.get('action_count')}`",
        "",
        "## Production Blockers",
        "",
    ]
    blockers = payload.get("production_signoff_blockers") or []
    lines.extend([f"- {blocker}" for blocker in blockers] or ["- None"])
    lines.extend(["", "## Owner Summary", ""])
    for item in payload.get("owner_summary") or []:
        lines.extend(
            [
                f"### {item.get('owner')}",
                "",
                f"- Action count: `{item.get('action_count')}`",
                f"- Action keys: `{', '.join(item.get('action_keys') or [])}`",
                f"- Addresses blockers: `{', '.join(item.get('addresses_blockers') or [])}`",
                "",
            ]
        )
    if not payload.get("owner_summary"):
        lines.append("- None")
    lines.extend(["", "## Blocker-To-Action Matrix", ""])
    for item in payload.get("blocker_action_matrix") or []:
        lines.extend(
            [
                f"### {item.get('blocker')}",
                "",
                f"- Covered: `{item.get('covered')}`",
                f"- Action keys: `{', '.join(item.get('action_keys') or [])}`",
                "",
            ]
        )
    if not payload.get("blocker_action_matrix"):
        lines.append("- None")
    lines.extend(["", "## Required Actions", ""])
    for action in payload.get("actions") or []:
        lines.extend(
            [
                f"### {action.get('key')}",
                "",
                f"- Owner: `{action.get('owner') or ''}`",
                f"- Acceptable decisions: `{', '.join(action.get('acceptable_decisions') or [])}`",
                f"- Objective areas: `{', '.join(action.get('objective_areas') or [])}`",
                f"- Addresses blockers: `{', '.join(action.get('addresses_blockers') or [])}`",
                f"- Required evidence: {action.get('required_evidence') or ''}",
                "- Reviewer:",
                "- Decision:",
                "- Date:",
                "- Evidence reference:",
                "- Notes:",
                "",
            ]
        )
    lines.extend(["## Packet Binding", ""])
    binding = payload.get("packet_binding") or {}
    for key in (
        "provided",
        "schema_ok",
        "version_matches_status",
        "source_commit_matches_status",
        "bundle_sha256_matches_status",
        "manifest_aggregate_sha256_matches_status",
        "preview_url_matches_status",
        "action_keys_match",
    ):
        lines.append(f"- {key}: `{binding.get(key)}`")
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This checklist only organizes the remaining human release gates. It is not a China tax opinion and does not replace current official-source review, customer-specific fact review or qualified professional judgment.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export reviewer-facing production sign-off actions from China delivery status evidence."
    )
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--packet", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument(
        "--require-actions",
        action="store_true",
        help="Exit with status 2 unless at least one required human action is present.",
    )
    parser.add_argument(
        "--require-packet-binding",
        action="store_true",
        help="Exit with status 3 unless the optional packet matches status and action keys.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    payload = export_actions(_load(args.status), _load(args.packet) if args.packet else None)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.markdown_output:
        _write_markdown(payload, args.markdown_output)
    if not args.json_output and not args.markdown_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    print(
        "production sign-off actions exported: "
        f"actions={payload['action_count']} "
        f"production_signoff_ready={payload['production_signoff_ready']}"
    )
    if args.require_actions and not payload["actions"]:
        print("production sign-off action export failed: no actions found")
        return 2
    binding = payload["packet_binding"]
    if args.require_packet_binding and not (
        binding.get("provided")
        and binding.get("schema_ok")
        and binding.get("version_matches_status")
        and binding.get("source_commit_matches_status")
        and binding.get("preview_url_matches_status")
        and binding.get("action_keys_match")
    ):
        print(f"production sign-off action packet binding failed: {binding}")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
