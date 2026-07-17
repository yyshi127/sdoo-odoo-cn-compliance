"""Validate completed China production sign-off evidence."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VALIDATION_SCHEMA = "sdoo.cn.signoff-validation.v1"
EVIDENCE_SCHEMA = "sdoo.cn.signoff-evidence.v1"
PACKET_SCHEMA = "sdoo.cn.signoff-packet.v1"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _decision_has_limitations(decision: Any) -> bool:
    return isinstance(decision, str) and "limitation" in decision


def _valid_limitations(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    limitations: list[str] = []
    for item in value:
        if isinstance(item, str) and len(item.strip()) >= 20:
            limitations.append(item.strip())
    return limitations


def _decision_map(evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    decisions = evidence.get("decisions") or []
    if not isinstance(decisions, list):
        return {}
    return {
        str(item.get("key")): item
        for item in decisions
        if isinstance(item, dict) and item.get("key")
    }


def _validate(packet: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    if packet.get("schema") != PACKET_SCHEMA:
        blockers.append("sign-off packet schema is invalid")
    if evidence.get("schema") != EVIDENCE_SCHEMA:
        blockers.append("sign-off evidence schema is invalid")
    if evidence.get("version") != packet.get("version"):
        blockers.append("sign-off evidence version does not match the packet version")
    if evidence.get("source_commit") != packet.get("source_commit"):
        blockers.append("sign-off evidence source commit does not match the packet")

    decisions = _decision_map(evidence)
    limitations = _valid_limitations(evidence.get("limitations"))
    action_results: list[dict[str, Any]] = []
    deployment_decision = None
    limitation_decision_keys: list[str] = []
    for action in packet.get("production_actions") or []:
        key = action.get("key")
        item = decisions.get(str(key))
        acceptable = set(action.get("acceptable_decisions") or [])
        item_blockers: list[str] = []
        if not item:
            item_blockers.append("decision is missing")
        else:
            decision = item.get("decision")
            if decision not in acceptable:
                item_blockers.append(
                    "decision must be one of: %s" % ", ".join(sorted(acceptable))
                )
            if not item.get("reviewer"):
                item_blockers.append("reviewer is missing")
            if not item.get("date"):
                item_blockers.append("date is missing")
            if not item.get("evidence_reference"):
                item_blockers.append("evidence_reference is missing")
            if _decision_has_limitations(decision):
                limitation_decision_keys.append(str(key))
            if key == "production_deployment_decision":
                deployment_decision = decision
        if item_blockers:
            blockers.extend([f"{key}: {blocker}" for blocker in item_blockers])
        action_results.append(
            {
                "key": key,
                "ok": not item_blockers,
                "decision": item.get("decision") if item else None,
                "blockers": item_blockers,
            }
        )

    if deployment_decision in ("defer", "reject"):
        blockers.append(
            "production deployment decision is %s, so production sign-off is not ready"
            % deployment_decision
        )
    if limitation_decision_keys:
        if not limitations:
            blockers.append(
                "limitation decisions require at least one substantive limitation "
                "entry of 20 or more characters: %s"
                % ", ".join(limitation_decision_keys)
            )
        else:
            warnings.append(
                "production sign-off includes documented limitations: %s"
                % ", ".join(limitation_decision_keys)
            )

    automated_items = packet.get("automated_items") or []
    blocked_automated = [
        item.get("key")
        for item in automated_items
        if isinstance(item, dict) and item.get("ready") is not True
    ]
    if blocked_automated:
        blockers.append(
            "automated packet evidence is not ready: %s"
            % ", ".join(str(item) for item in blocked_automated)
        )

    return {
        "schema": VALIDATION_SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "version": packet.get("version"),
        "source_commit": packet.get("source_commit"),
        "ok": not blockers,
        "production_signoff_ready": not blockers,
        "deployment_decision": deployment_decision,
        "blockers": blockers,
        "warnings": warnings,
        "action_results": action_results,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate completed China production sign-off evidence."
    )
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument(
        "--require-production-signoff-ready",
        action="store_true",
        help="Exit with status 2 unless the sign-off evidence approves production deployment.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    result = _validate(_load(args.packet), _load(args.evidence))
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    print(
        "sign-off evidence validated: "
        f"ok={result['ok']} production_signoff_ready={result['production_signoff_ready']}"
    )
    if args.require_production_signoff_ready and result["production_signoff_ready"] is not True:
        print(f"production sign-off blockers: {result['blockers']}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
