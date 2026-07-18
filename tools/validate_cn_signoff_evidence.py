"""Validate completed China production sign-off evidence."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


VALIDATION_SCHEMA = "sdoo.cn.signoff-validation.v1"
EVIDENCE_SCHEMA = "sdoo.cn.signoff-evidence.v1"
PACKET_SCHEMA = "sdoo.cn.signoff-packet.v1"
PLACEHOLDER_TEXTS = {
    "YYYY-MM-DD",
    "Reviewer",
    "Business reviewer name",
    "China tax professional name",
    "Rule governance owner name",
    "Implementation owner name",
    "Release owner name",
    "Path or document reference for completed CHINA_BUSINESS_UAT_CHECKLIST.md",
    "Path or document reference for completed CHINA_UAT_WALKTHROUGH_SCRIPT.md",
    "Rule/source review packet reference",
    "Official-source freshness monitoring result reference",
    "Official-source freshness monitoring result and governance summary reference",
    "Customer data, evidence gap and open risk review reference",
    "Screenshots or recording reference for workbench, risk center, remediation tracking and compliance report walkthrough",
    "Completed CHINA_PRODUCTION_SIGNOFF_TEMPLATE.md reference",
    "replace-with-signoff-packet-source-commit",
    "controlled evidence reference",
    "uncontrolled evidence reference",
}

ACTION_EVIDENCE_REQUIREMENTS = {
    "business_uat_decision": (
        ("walkthrough script", ("walkthrough script", "walkthrough", "screen-by-screen")),
        ("uat", ("uat", "user acceptance", "用户验收", "业务验收")),
        ("company", ("company", "公司")),
        ("period", ("period", "期间")),
        ("controlled ai", ("controlled ai", "受控 ai", "受控AI")),
    ),
    "china_tax_professional_rule_signoff": (
        ("released rule", ("released rule", "已发布规则", "正式规则")),
        ("official source", ("official source", "官方来源", "官方依据")),
        ("professional", ("professional", "专业人员", "税务专业")),
    ),
    "official_source_freshness_review": (
        ("governance summary", ("governance summary", "source governance")),
        ("monitoring", ("monitoring", "monitor")),
        ("official source", ("official source", "官方来源", "官方依据")),
        ("freshness", ("freshness", "时效", "更新")),
        ("local jurisdiction", ("local jurisdiction", "地方", "属地")),
    ),
    "customer_scope_and_data_gap_review": (
        ("external dataset", ("external dataset", "外部数据", "监管数据")),
        ("evidence gap", ("evidence gap", "证据缺口")),
        ("open risk", ("open risk", "未关闭风险", "开放风险")),
        ("controlled ai limitation", ("controlled ai limitation", "受控 ai 限制", "受控AI限制")),
    ),
    "representative_ux_walkthrough": (
        ("walkthrough script", ("walkthrough script", "walkthrough", "screen-by-screen")),
        ("workbench", ("workbench", "工作台", "总览")),
        ("risk center", ("risk center", "风险中心")),
        ("controlled ai guidance", ("controlled ai guidance", "受控 ai 引导", "受控AI引导")),
        ("filing/payment archive", ("filing/payment archive", "申报缴款档案", "申报/缴款档案")),
        ("input/output checksum", ("input/output checksum", "输入输出校验", "输入/输出校验")),
        ("record checksum", ("record checksum", "记录校验")),
    ),
    "blocker_summary_walkthrough": (
        ("data readiness", ("data readiness", "数据就绪")),
        ("filing/payment archive", ("filing/payment archive", "申报缴款档案", "申报/缴款档案")),
        ("report readiness", ("report readiness", "报告就绪")),
        ("controlled ai guidance disclosure", ("controlled ai guidance disclosure", "受控 ai 披露", "受控AI披露")),
    ),
    "production_deployment_decision": (
        ("production sign-off", ("production sign-off", "生产签核", "上线签核")),
        ("deployment decision", ("deployment decision", "部署决策", "上线决策")),
        ("rollback", ("rollback", "回滚")),
    ),
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _decision_has_limitations(decision: Any) -> bool:
    return isinstance(decision, str) and "limitation" in decision


def _is_substantive_text(value: Any, *, min_length: int = 3) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    return len(text) >= min_length and text not in PLACEHOLDER_TEXTS


def _valid_iso_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return False
    return parsed.isoformat() == value


def _valid_limitations(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    limitations: list[str] = []
    for item in value:
        if isinstance(item, str) and len(item.strip()) >= 20:
            limitations.append(item.strip())
    return limitations


def _evidence_text(item: dict[str, Any]) -> str:
    return " ".join(
        str(item.get(field) or "")
        for field in ("evidence_reference", "notes")
    ).lower()


def _missing_action_keywords(key: Any, item: dict[str, Any]) -> list[str]:
    requirements = ACTION_EVIDENCE_REQUIREMENTS.get(str(key), ())
    evidence_text = _evidence_text(item)
    return [
        label
        for label, aliases in requirements
        if not any(alias.lower() in evidence_text for alias in aliases)
    ]


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

    raw_decisions = evidence.get("decisions")
    if not isinstance(raw_decisions, list):
        blockers.append("sign-off evidence decisions must be a list")
        raw_decisions = []
    allowed_keys = {
        str(action.get("key"))
        for action in packet.get("production_actions") or []
        if isinstance(action, dict) and action.get("key")
    }
    seen_keys: set[str] = set()
    duplicate_keys: list[str] = []
    unknown_keys: list[str] = []
    for item in raw_decisions:
        if not isinstance(item, dict) or not item.get("key"):
            blockers.append("sign-off evidence decision item is missing key")
            continue
        key = str(item.get("key"))
        if key in seen_keys and key not in duplicate_keys:
            duplicate_keys.append(key)
        seen_keys.add(key)
        if key not in allowed_keys:
            unknown_keys.append(key)
    if duplicate_keys:
        blockers.append(
            "sign-off evidence decision keys must be unique: %s"
            % ", ".join(duplicate_keys)
        )
    if unknown_keys:
        blockers.append(
            "sign-off evidence contains unknown decision keys: %s"
            % ", ".join(unknown_keys)
        )

    decisions = _decision_map(evidence)
    limitations = _valid_limitations(evidence.get("limitations"))
    action_results: list[dict[str, Any]] = []
    blocked_objective_areas: list[str] = []
    deployment_decision = None
    limitation_decision_keys: list[str] = []
    for action in packet.get("production_actions") or []:
        key = action.get("key")
        objective_areas = [
            str(area)
            for area in action.get("objective_areas") or []
            if isinstance(area, str) and area.strip()
        ]
        item = decisions.get(str(key))
        acceptable = set(action.get("acceptable_decisions") or [])
        item_blockers: list[str] = []
        if not objective_areas:
            item_blockers.append("objective_areas are missing from the sign-off packet")
        if not item:
            item_blockers.append("decision is missing")
        else:
            decision = item.get("decision")
            if decision not in acceptable:
                item_blockers.append(
                    "decision must be one of: %s" % ", ".join(sorted(acceptable))
                )
            if not _is_substantive_text(item.get("reviewer")):
                item_blockers.append(
                    "reviewer is missing or still a template placeholder"
                )
            if not _valid_iso_date(item.get("date")):
                item_blockers.append("date must be YYYY-MM-DD")
            if not _is_substantive_text(
                item.get("evidence_reference"),
                min_length=10,
            ):
                item_blockers.append(
                    "evidence_reference is missing or still a template placeholder"
                )
            missing_keywords = _missing_action_keywords(key, item)
            if missing_keywords:
                item_blockers.append(
                    "evidence_reference or notes must mention: %s"
                    % ", ".join(missing_keywords)
                )
            if _decision_has_limitations(decision):
                limitation_decision_keys.append(str(key))
            if key == "production_deployment_decision":
                deployment_decision = decision
        if item_blockers:
            blockers.extend([f"{key}: {blocker}" for blocker in item_blockers])
            for area in objective_areas:
                if area not in blocked_objective_areas:
                    blocked_objective_areas.append(area)
        action_results.append(
            {
                "key": key,
                "ok": not item_blockers,
                "decision": item.get("decision") if item else None,
                "objective_areas": objective_areas,
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
        "preview_url": packet.get("preview_url"),
        "ok": not blockers,
        "production_signoff_ready": not blockers,
        "deployment_decision": deployment_decision,
        "blockers": blockers,
        "warnings": warnings,
        "blocked_objective_areas": blocked_objective_areas,
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
