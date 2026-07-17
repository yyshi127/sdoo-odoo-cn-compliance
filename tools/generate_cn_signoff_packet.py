"""Generate a China compliance release sign-off action packet."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PACKET_SCHEMA = "sdoo.cn.signoff-packet.v1"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _readiness_item(key: str, label: str, ready: bool, evidence: str) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "ready": ready,
        "evidence": evidence,
    }


def _missing_human_evidence(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "key": action["key"],
            "owner": action["owner"],
            "required_evidence": action["required_evidence"],
            "acceptable_decisions": action["acceptable_decisions"],
            "objective_areas": action["objective_areas"],
        }
        for action in actions
    ]


def _build_packet(status: dict[str, Any]) -> dict[str, Any]:
    readiness = status.get("readiness_gates") or {}
    source_control = status.get("source_control") or {}
    preview_health = status.get("preview_health") or {}
    preview_module = status.get("preview_module") or {}
    real_data = status.get("real_data_closed_loop") or {}
    real_data_readiness = real_data.get("readiness") or {}
    runtime = status.get("runtime") or {}
    runtime_log = runtime.get("log") if isinstance(runtime, dict) else {}

    automated_items = [
        _readiness_item(
            "version_consistent",
            "Delivery version is consistent across bundle, manifest and summary",
            status.get("version_consistent") is True,
            str(status.get("version") or ""),
        ),
        _readiness_item(
            "acceptance_passed",
            "Automated delivery acceptance passed",
            status.get("acceptance_passed") is True,
            "acceptance_summary.result=passed",
        ),
        _readiness_item(
            "runtime_passed",
            "Odoo runtime acceptance passed with zero failures and errors",
            status.get("runtime_passed") is True,
            json.dumps(runtime_log, ensure_ascii=False, sort_keys=True),
        ),
        _readiness_item(
            "source_control_clean",
            "Release artifact was built from a clean Git worktree",
            readiness.get("source_control_clean") is True,
            json.dumps(source_control, ensure_ascii=False, sort_keys=True),
        ),
        _readiness_item(
            "preview_health",
            "Preview URL is reachable and not returning an error page",
            preview_health.get("ok") is True,
            str(preview_health.get("url") or status.get("preview_url") or ""),
        ),
        _readiness_item(
            "preview_module",
            "Preview database has the expected China compliance module version",
            preview_module.get("ok") is True,
            str(preview_module.get("module_installed_version") or ""),
        ),
        _readiness_item(
            "real_data_closed_loop",
            "Representative database has accounting, external data, risk/remediation and verified evidence activity",
            real_data.get("ok") is True
            and real_data_readiness.get("closed_loop_evidence_ready") is True,
            json.dumps(real_data_readiness, ensure_ascii=False, sort_keys=True),
        ),
    ]
    production_actions = [
        {
            "key": "business_uat_decision",
            "owner": "business_reviewer",
            "required_evidence": "Completed docs/CHINA_BUSINESS_UAT_CHECKLIST.md with company, period, reviewer, datasets, screens and decision.",
            "acceptable_decisions": ["accepted", "accepted_with_limitations"],
            "objective_areas": [
                "representative business UAT",
                "closed-loop compliance workflow usability",
            ],
        },
        {
            "key": "china_tax_professional_rule_signoff",
            "owner": "china_tax_professional",
            "required_evidence": "Signed rule/source review packet for all released rules used in formal conclusions.",
            "acceptable_decisions": ["approved", "approved_with_limitations"],
            "objective_areas": [
                "source-governed China rules",
                "professional tax-rule sign-off",
            ],
        },
        {
            "key": "official_source_freshness_review",
            "owner": "rule_governance_owner",
            "required_evidence": "Current official-source monitoring results and any local jurisdiction updates reviewed for the target period.",
            "acceptable_decisions": ["current", "current_with_documented_limitations"],
            "objective_areas": [
                "official-source freshness",
                "national and local rule currency",
            ],
        },
        {
            "key": "customer_scope_and_data_gap_review",
            "owner": "implementation_owner",
            "required_evidence": "Customer-specific accounting periods, external datasets, evidence gaps, open risks and remediation status reviewed.",
            "acceptable_decisions": ["no_blocking_gap", "limitations_documented"],
            "objective_areas": [
                "Odoo accounting and business-data basis",
                "external tax data sufficiency",
            ],
        },
        {
            "key": "representative_ux_walkthrough",
            "owner": "business_reviewer",
            "required_evidence": "Representative walkthrough evidence for workbench, risk center, remediation tracking and compliance report pages, including risk level, cause, impact amount, period, owner, due date, status and next action visibility on common desktop and laptop screen sizes.",
            "acceptable_decisions": ["passed", "passed_with_limitations"],
            "objective_areas": [
                "risk center and remediation clarity",
                "Odoo-consistent viewing experience",
            ],
        },
        {
            "key": "blocker_summary_walkthrough",
            "owner": "business_reviewer",
            "required_evidence": "Screenshot, recording or completed UAT reference showing that data readiness, evidence, filing/payment archive, remediation, report center and report readiness blocker summaries explain why each non-ready record is blocked or limited.",
            "acceptable_decisions": ["passed", "passed_with_limitations"],
            "objective_areas": [
                "limitations and uncertainty visibility",
                "data/evidence/report readiness transparency",
            ],
        },
        {
            "key": "production_deployment_decision",
            "owner": "release_owner",
            "required_evidence": "Completed docs/CHINA_PRODUCTION_SIGNOFF_TEMPLATE.md with deploy/defer/reject decision and rollback owner.",
            "acceptable_decisions": ["deploy", "deploy_with_limitations", "defer", "reject"],
            "objective_areas": [
                "installable and upgradeable Odoo deployment",
                "auditable release and rollback decision",
            ],
        },
    ]
    return {
        "schema": PACKET_SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "version": status.get("version"),
        "preview_url": status.get("preview_url"),
        "source_commit": source_control.get("commit"),
        "business_uat_ready": readiness.get("business_uat_ready") is True,
        "production_signoff_ready": False,
        "automated_items": automated_items,
        "production_actions": production_actions,
        "missing_human_evidence": _missing_human_evidence(production_actions),
        "business_uat_blockers": readiness.get("business_uat_blockers") or [],
        "production_signoff_blockers": readiness.get("production_signoff_blockers") or [],
    }


def _write_markdown(packet: dict[str, Any], path: Path) -> None:
    lines = [
        "# China Production Sign-off Action Packet",
        "",
        f"- Version: `{packet.get('version') or ''}`",
        f"- Source commit: `{packet.get('source_commit') or ''}`",
        f"- Preview URL: `{packet.get('preview_url') or ''}`",
        f"- Business UAT ready: `{packet.get('business_uat_ready')}`",
        f"- Production sign-off ready: `{packet.get('production_signoff_ready')}`",
        "",
        "## Automated Evidence",
        "",
    ]
    for item in packet["automated_items"]:
        status = "READY" if item["ready"] else "BLOCKED"
        lines.extend(
            [
                f"### {item['label']}",
                "",
                f"- Status: `{status}`",
                f"- Evidence: `{item['evidence']}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Missing Human Evidence",
            "",
            "These items must be completed before `production_signoff_ready` can become `true`.",
            "",
        ]
    )
    for item in packet["missing_human_evidence"]:
        lines.extend(
            [
                f"### {item['key']}",
                "",
                f"- Owner: `{item['owner']}`",
                f"- Objective areas: `{', '.join(item['objective_areas'])}`",
                f"- Required evidence: {item['required_evidence']}",
                f"- Acceptable decisions: `{', '.join(item['acceptable_decisions'])}`",
                "",
            ]
        )
    lines.extend(["## Required Human Sign-off Actions", ""])
    for action in packet["production_actions"]:
        lines.extend(
            [
                f"### {action['key']}",
                "",
                f"- Owner: `{action['owner']}`",
                f"- Objective areas: `{', '.join(action['objective_areas'])}`",
                f"- Required evidence: {action['required_evidence']}",
                f"- Acceptable decisions: `{', '.join(action['acceptable_decisions'])}`",
                "- Decision:",
                "- Reviewer:",
                "- Date:",
                "- Notes:",
                "",
            ]
        )
    lines.extend(["## Business UAT Blockers", ""])
    blockers = packet.get("business_uat_blockers") or []
    lines.extend([f"- {blocker}" for blocker in blockers] or ["- None"])
    lines.extend(["", "## Production Sign-off Blockers", ""])
    blockers = packet.get("production_signoff_blockers") or []
    lines.extend([f"- {blocker}" for blocker in blockers] or ["- None"])
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This packet records release readiness evidence and the remaining human sign-off actions. It is not a China tax opinion and does not certify any taxpayer filing position.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a sign-off action packet from a China delivery status JSON."
    )
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument(
        "--require-business-uat-ready",
        action="store_true",
        help="Exit with status 2 unless automated evidence is ready for business UAT.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    packet = _build_packet(_load(args.status))
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.markdown_output:
        _write_markdown(packet, args.markdown_output)
    if not args.json_output and not args.markdown_output:
        print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "sign-off packet generated: "
            f"business_uat_ready={packet['business_uat_ready']} "
            f"production_signoff_ready={packet['production_signoff_ready']}"
        )
    if args.require_business_uat_ready and packet["business_uat_ready"] is not True:
        print(f"business UAT blockers: {packet['business_uat_blockers']}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
