"""Render a version-aligned China production sign-off evidence draft."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EVIDENCE_SCHEMA = "sdoo.cn.signoff-evidence.v1"
PACKET_SCHEMA = "sdoo.cn.signoff-packet.v1"
DATE_PLACEHOLDER = "YYYY-MM-DD"
REVIEWER_PLACEHOLDERS = {
    "business_reviewer": "Business reviewer name",
    "china_tax_professional": "China tax professional name",
    "rule_governance_owner": "Rule governance owner name",
    "implementation_owner": "Implementation owner name",
    "release_owner": "Release owner name",
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _reviewer_placeholder(owner: object) -> str:
    return REVIEWER_PLACEHOLDERS.get(str(owner or ""), "Reviewer")


def _draft_decision(action: dict[str, Any]) -> dict[str, Any]:
    acceptable = action.get("acceptable_decisions") or []
    objective_areas = action.get("objective_areas") or []
    addresses_blockers = action.get("addresses_blockers") or []
    return {
        "key": action.get("key"),
        "decision": acceptable[0] if acceptable else "",
        "reviewer": _reviewer_placeholder(action.get("owner")),
        "date": DATE_PLACEHOLDER,
        "evidence_reference": action.get("required_evidence") or "Evidence reference",
        "notes": (
            "Replace this draft note with the reviewer conclusion. "
            "The final evidence must mention the required evidence, objective "
            "areas and production blockers. Objective areas: %s. "
            "Production blockers addressed: %s."
            % (
                "; ".join(str(item) for item in objective_areas) or "None",
                "; ".join(str(item) for item in addresses_blockers) or "None",
            )
        ),
        "objective_areas": objective_areas,
        "addresses_blockers": addresses_blockers,
    }


def render_template(packet: dict[str, Any]) -> dict[str, Any]:
    if packet.get("schema") != PACKET_SCHEMA:
        raise ValueError("sign-off packet schema is invalid")
    actions = [
        action
        for action in packet.get("production_actions") or []
        if isinstance(action, dict)
    ]
    return {
        "schema": EVIDENCE_SCHEMA,
        "version": packet.get("version"),
        "source_commit": packet.get("source_commit"),
        "preview_url": packet.get("preview_url"),
        "generated_from_packet_at_utc": (
            datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        ),
        "placeholder_notice": (
            "This file is a draft generated from the current sign-off packet. "
            "Replace every reviewer, date, evidence_reference and notes placeholder "
            "with real evidence before running validate_cn_signoff_evidence.py."
        ),
        "limitations": [
            (
                "Replace or remove this limitation entry. If any decision uses a "
                "with-limitations outcome, keep at least one substantive limitation "
                "of 20 or more characters."
            )
        ],
        "production_blocker_coverage": packet.get("production_blocker_coverage") or {},
        "production_blocker_coverage_note": (
            "Use this packet-derived matrix to confirm every production blocker "
            "has at least one completed human decision. It is not a substitute for "
            "the decision evidence below."
        ),
        "decisions": [_draft_decision(action) for action in actions],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render a China production sign-off evidence draft from a sign-off packet."
    )
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--json-output", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    payload = render_template(_load(args.packet))
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(text, encoding="utf-8")
        print(f"sign-off evidence draft written: {args.json_output}")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
