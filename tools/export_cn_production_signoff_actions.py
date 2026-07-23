"""Export reviewer-facing China production sign-off actions."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ACTIONS_SCHEMA = "sdoo.cn.production-signoff-actions.v1"
STATUS_SCHEMA = "sdoo.cn.delivery-status.v1"
PACKET_SCHEMA = "sdoo.cn.signoff-packet.v1"
PACKET_BINDING_REQUIRED_KEYS = (
    "provided",
    "schema_ok",
    "version_matches_status",
    "source_commit_matches_status",
    "bundle_sha256_matches_status",
    "manifest_aggregate_sha256_matches_status",
    "preview_url_matches_status",
    "preview_database_matches_status",
    "action_keys_match",
)


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


def _packet_evidence(
    packet: dict[str, Any] | None,
    key: str,
    default: Any,
) -> Any:
    if packet is None:
        return default
    item = next(
        (
            item
            for item in packet.get("automated_items") or []
            if isinstance(item, dict) and item.get("key") == key
        ),
        None,
    )
    if not item:
        return default
    evidence = item.get("evidence")
    if not isinstance(evidence, str):
        return evidence if evidence is not None else default
    try:
        return json.loads(evidence)
    except json.JSONDecodeError:
        return evidence


def _count_by(items: list[dict[str, Any]], field: str) -> dict[str, int]:
    return dict(
        sorted(
            Counter(
                str(item.get(field) or "not_recorded")
                for item in items
                if isinstance(item, dict)
            ).items()
        )
    )


def _checksum_complete(item: dict[str, Any], fields: tuple[str, ...]) -> bool:
    return all(
        isinstance(item.get(field), str)
        and re.fullmatch(r"[0-9a-f]{64}", item[field]) is not None
        for field in fields
    )


def _review_prefill(packet: dict[str, Any] | None) -> dict[str, Any]:
    if packet is None:
        return {
            "available": False,
            "boundary": (
                "No sign-off packet was supplied; reviewer decisions and evidence "
                "must remain blank."
            ),
        }

    runtime = _packet_evidence(packet, "runtime_passed", {})
    upgrade = _packet_evidence(packet, "upgrade_runtime_evidence", {})
    profiles = _packet_evidence(packet, "workbench_summary_evidence", [])
    risk_scope = _packet_evidence(packet, "risk_task_report_summary_evidence", {})
    ai_records = _packet_evidence(packet, "controlled_ai_guidance_evidence", [])
    rule_scope = _packet_evidence(packet, "rule_source_governance_evidence", {})
    source_summary = _packet_evidence(
        packet, "official_source_governance_summary", {}
    )
    customer_scope = _packet_evidence(
        packet, "customer_scope_gap_review_evidence", {}
    )

    if not isinstance(profiles, list):
        profiles = []
    if not isinstance(risk_scope, dict):
        risk_scope = {}
    if not isinstance(ai_records, list):
        ai_records = []
    if not isinstance(rule_scope, dict):
        rule_scope = {}
    if not isinstance(source_summary, dict):
        source_summary = {}
    if not isinstance(customer_scope, dict):
        customer_scope = {}

    active_profile = next(
        (
            profile
            for profile in profiles
            if isinstance(profile, dict) and profile.get("status") == "active"
        ),
        profiles[0] if profiles else {},
    )
    findings = [
        item
        for item in risk_scope.get("findings") or []
        if isinstance(item, dict)
    ]
    remediation_tasks = [
        item
        for item in risk_scope.get("remediation_tasks") or []
        if isinstance(item, dict)
    ]
    reports = [
        item
        for item in risk_scope.get("reports") or []
        if isinstance(item, dict)
    ]
    rule_versions = [
        item
        for item in rule_scope.get("rule_versions") or []
        if isinstance(item, dict)
    ]
    source_monitor_runs = [
        item
        for item in rule_scope.get("source_monitor_runs") or []
        if isinstance(item, dict)
    ]
    authority_sources = [
        item
        for item in rule_scope.get("authority_sources") or []
        if isinstance(item, dict)
    ]
    customer_objects = customer_scope.get("objects") or {}
    accounting = customer_scope.get("accounting") or {}
    customer_evidence = [
        item
        for item in customer_scope.get("evidence") or []
        if isinstance(item, dict)
    ]
    filing_archives = [
        item
        for item in customer_scope.get("filing_archives") or []
        if isinstance(item, dict)
    ]
    customer_findings = [
        item
        for item in customer_scope.get("findings") or []
        if isinstance(item, dict)
    ]
    customer_tasks = [
        item
        for item in customer_scope.get("remediation_tasks") or []
        if isinstance(item, dict)
    ]

    runtime_log = runtime if isinstance(runtime, dict) else {}
    upgrade_log = (
        upgrade.get("log")
        if isinstance(upgrade, dict) and isinstance(upgrade.get("log"), dict)
        else {}
    )
    return {
        "available": True,
        "boundary": (
            "This section is generated from automated evidence. It pre-fills "
            "review facts only and never records a reviewer, decision, date or "
            "approval."
        ),
        "candidate_acceptance": {
            "clean_install": {
                "failed": runtime_log.get("failed"),
                "errors": runtime_log.get("errors"),
                "loaded_test_count": runtime_log.get("loaded_test_count"),
                "reported_test_count": runtime_log.get("reported_test_count"),
            },
            "upgrade": {
                "failed": upgrade_log.get("failed"),
                "errors": upgrade_log.get("errors"),
                "loaded_test_count": upgrade_log.get("loaded_test_count"),
                "reported_test_count": upgrade_log.get("reported_test_count"),
            },
        },
        "representative_business_scope": {
            "profile": active_profile.get("name"),
            "company": active_profile.get("company"),
            "period": active_profile.get("period_label"),
            "workbench_status": active_profile.get("closed_loop_state"),
            "workbench_action_summary": active_profile.get("action_summary"),
            "next_action": active_profile.get("next_action"),
            "limitation_summary": active_profile.get("limitation_summary"),
            "uncertainty_summary": active_profile.get("uncertainty_summary"),
            "evidence_sample_finding_count": len(findings),
            "evidence_sample_finding_risk_levels": _count_by(
                findings, "risk_level"
            ),
            "evidence_sample_finding_results": _count_by(findings, "result"),
            "evidence_sample_finding_review_states": _count_by(
                findings, "review_state"
            ),
            "evidence_sample_remediation_task_count": len(remediation_tasks),
            "remediation_states": _count_by(remediation_tasks, "state"),
            "verification_states": _count_by(
                remediation_tasks, "verification_state"
            ),
            "evidence_sample_formal_report_count": len(reports),
            "formal_report_states": _count_by(reports, "state"),
        },
        "controlled_ai": {
            "record_count": len(ai_records),
            "provider_keys": sorted(
                {
                    str(item.get("provider_key"))
                    for item in ai_records
                    if item.get("provider_key")
                }
            ),
            "model_names": sorted(
                {
                    str(item.get("model_name"))
                    for item in ai_records
                    if item.get("model_name")
                }
            ),
            "prompt_versions": sorted(
                {
                    str(item.get("prompt_version"))
                    for item in ai_records
                    if item.get("prompt_version")
                }
            ),
            "checksum_complete_count": sum(
                _checksum_complete(
                    item,
                    ("input_checksum", "output_checksum", "record_checksum"),
                )
                for item in ai_records
                if isinstance(item, dict)
            ),
            "professional_warning_count": sum(
                bool(item.get("professional_warning"))
                for item in ai_records
                if isinstance(item, dict)
            ),
        },
        "rule_and_source_governance": {
            "source_count": source_summary.get("source_count"),
            "valid_source_count": (
                source_summary.get("valid_source_count")
                if source_summary.get("valid_source_count") is not None
                else sum(item.get("state") == "valid" for item in authority_sources)
            ),
            "active_rule_version_count": (
                source_summary.get("active_rule_version_count")
                if source_summary.get("active_rule_version_count") is not None
                else sum(
                    item.get("release_state") == "active"
                    for item in rule_versions
                )
            ),
            "overdue_source_count": source_summary.get("overdue_source_count"),
            "changed_monitor_run_count": source_summary.get(
                "changed_monitor_run_count"
            ),
            "failed_monitor_run_count": source_summary.get(
                "failed_monitor_run_count"
            ),
            "latest_monitor_state": source_summary.get("latest_monitor_state"),
            "rule_versions": [
                {
                    "rule": item.get("rule"),
                    "version": item.get("version"),
                    "release_state": item.get("release_state"),
                    "professional_review_state": item.get(
                        "professional_review_state"
                    ),
                    "released_rule_checksum": item.get("released_rule_checksum"),
                    "source_names": item.get("source_names") or [],
                    "next_review_date": item.get("next_review_date"),
                }
                for item in rule_versions
            ],
            "source_monitor_runs": [
                {
                    "source": item.get("source"),
                    "state": item.get("state"),
                    "completed_at": item.get("completed_at"),
                    "result_integrity_state": item.get(
                        "result_integrity_state"
                    ),
                    "result_checksum": item.get("result_checksum"),
                }
                for item in source_monitor_runs
            ],
        },
        "customer_scope_and_gaps": {
            "accounting": accounting,
            "object_counts": customer_objects,
            "verified_evidence_count": sum(
                item.get("state") == "verified" for item in customer_evidence
            ),
            "filing_archive_count": len(filing_archives),
            "filing_archive_states": _count_by(filing_archives, "state"),
            "finding_count": len(customer_findings),
            "high_or_critical_finding_count": sum(
                item.get("risk_level") in {"high", "critical"}
                for item in customer_findings
            ),
            "finding_review_states": _count_by(
                customer_findings, "review_state"
            ),
            "remediation_task_count": len(customer_tasks),
            "remediation_states": _count_by(customer_tasks, "state"),
            "review_flags": customer_scope.get("review") or {},
        },
        "human_fields": {
            "reviewer": None,
            "decision": None,
            "date": None,
            "evidence_reference": None,
            "notes": None,
        },
    }


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


def _packet_binding_ready(binding: dict[str, Any]) -> bool:
    return all(binding.get(key) is True for key in PACKET_BINDING_REQUIRED_KEYS)


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
        "review_prefill": _review_prefill(packet),
    }


def _json_inline(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


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
    prefill = payload.get("review_prefill") or {}
    lines.extend(["", "## Automated Review Prefill", ""])
    lines.extend(
        [
            f"> {prefill.get('boundary') or ''}",
            "",
        ]
    )
    if prefill.get("available"):
        acceptance = prefill.get("candidate_acceptance") or {}
        scope = prefill.get("representative_business_scope") or {}
        ai = prefill.get("controlled_ai") or {}
        governance = prefill.get("rule_and_source_governance") or {}
        customer = prefill.get("customer_scope_and_gaps") or {}
        lines.extend(
            [
                "### Candidate Acceptance",
                "",
                f"- Clean install: `{_json_inline(acceptance.get('clean_install') or {})}`",
                f"- Upgrade: `{_json_inline(acceptance.get('upgrade') or {})}`",
                "",
                "### Representative Business Scope",
                "",
                f"- Company: `{scope.get('company') or ''}`",
                f"- Profile: `{scope.get('profile') or ''}`",
                f"- Period: `{scope.get('period') or ''}`",
                f"- Workbench state: `{scope.get('workbench_status') or ''}`",
                f"- Current workbench summary: {scope.get('workbench_action_summary') or ''}",
                f"- Next action: {scope.get('next_action') or ''}",
                f"- Limitation summary: {scope.get('limitation_summary') or ''}",
                f"- Uncertainty summary: {scope.get('uncertainty_summary') or ''}",
                f"- Representative finding records included in this evidence packet (not the latest-scan count): `{scope.get('evidence_sample_finding_count')}`; risk levels `{_json_inline(scope.get('evidence_sample_finding_risk_levels') or {})}`; results `{_json_inline(scope.get('evidence_sample_finding_results') or {})}`; review states `{_json_inline(scope.get('evidence_sample_finding_review_states') or {})}`",
                f"- Representative remediation tasks included in this evidence packet: `{scope.get('evidence_sample_remediation_task_count')}`; states `{_json_inline(scope.get('remediation_states') or {})}`; verification `{_json_inline(scope.get('verification_states') or {})}`",
                f"- Representative formal reports included in this evidence packet: `{scope.get('evidence_sample_formal_report_count')}`; states `{_json_inline(scope.get('formal_report_states') or {})}`",
                "",
                "### Controlled AI Evidence",
                "",
                f"- Records: `{ai.get('record_count')}`",
                f"- Providers: `{_json_inline(ai.get('provider_keys') or [])}`",
                f"- Models: `{_json_inline(ai.get('model_names') or [])}`",
                f"- Prompt versions: `{_json_inline(ai.get('prompt_versions') or [])}`",
                f"- Complete input/output/record checksum sets: `{ai.get('checksum_complete_count')}`",
                f"- Professional warnings present: `{ai.get('professional_warning_count')}`",
                "",
                "### Rule And Source Governance",
                "",
                f"- Sources: `{governance.get('source_count')}` total / `{governance.get('valid_source_count')}` valid",
                f"- Active rule versions: `{governance.get('active_rule_version_count')}`",
                f"- Source review state: overdue `{governance.get('overdue_source_count')}`, changed runs `{governance.get('changed_monitor_run_count')}`, failed runs `{governance.get('failed_monitor_run_count')}`, latest `{governance.get('latest_monitor_state') or ''}`",
                f"- Released rule versions: `{_json_inline(governance.get('rule_versions') or [])}`",
                f"- Source monitor runs: `{_json_inline(governance.get('source_monitor_runs') or [])}`",
                "",
                "### Customer Scope And Gaps",
                "",
                f"- Accounting coverage: `{_json_inline(customer.get('accounting') or {})}`",
                f"- Controlled object counts: `{_json_inline(customer.get('object_counts') or {})}`",
                f"- Verified evidence: `{customer.get('verified_evidence_count')}`",
                f"- Filing archives: `{customer.get('filing_archive_count')}`; states `{_json_inline(customer.get('filing_archive_states') or {})}`",
                f"- Findings: `{customer.get('finding_count')}`; high/critical `{customer.get('high_or_critical_finding_count')}`; review states `{_json_inline(customer.get('finding_review_states') or {})}`",
                f"- Remediation tasks: `{customer.get('remediation_task_count')}`; states `{_json_inline(customer.get('remediation_states') or {})}`",
                f"- Review flags: `{_json_inline(customer.get('review_flags') or {})}`",
                "",
                "### Human Completion Fields",
                "",
                "- Reviewer:",
                "- Decision:",
                "- Date:",
                "- Evidence reference:",
                "- Notes:",
                "",
            ]
        )
    else:
        lines.extend(["- Automated prefill is unavailable.", ""])
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
    for key in PACKET_BINDING_REQUIRED_KEYS:
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
    if args.require_packet_binding and not _packet_binding_ready(binding):
        print(f"production sign-off action packet binding failed: {binding}")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
