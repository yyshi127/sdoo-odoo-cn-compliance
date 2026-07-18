"""Generate a China compliance release sign-off action packet."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PACKET_SCHEMA = "sdoo.cn.signoff-packet.v1"
MARKDOWN_EVIDENCE_LIMIT = 320


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _readiness_item(key: str, label: str, ready: bool, evidence: str) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "ready": ready,
        "evidence": evidence,
    }


def _markdown_evidence(evidence: Any) -> str:
    text = "" if evidence is None else str(evidence)
    if len(text) <= MARKDOWN_EVIDENCE_LIMIT:
        return f"`{text}`"
    return (
        f"`{text[:MARKDOWN_EVIDENCE_LIMIT].rstrip()}...` "
        "(truncated for readability; see the JSON packet for complete evidence)"
    )


def _missing_human_evidence(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "key": action["key"],
            "owner": action["owner"],
            "required_evidence": action["required_evidence"],
            "acceptable_decisions": action["acceptable_decisions"],
            "objective_areas": action["objective_areas"],
            "addresses_blockers": action["addresses_blockers"],
        }
        for action in actions
    ]


def _production_blocker_coverage(
    blockers: list[str],
    actions: list[dict[str, Any]],
) -> dict[str, Any]:
    coverage = []
    covered_blockers: set[str] = set()
    for blocker in blockers:
        action_keys = [
            str(action.get("key"))
            for action in actions
            if blocker in (action.get("addresses_blockers") or [])
        ]
        if action_keys:
            covered_blockers.add(blocker)
        coverage.append(
            {
                "blocker": blocker,
                "covered": bool(action_keys),
                "action_keys": action_keys,
            }
        )
    return {
        "all_covered": len(covered_blockers) == len(blockers),
        "uncovered_blockers": [
            blocker for blocker in blockers if blocker not in covered_blockers
        ],
        "coverage": coverage,
    }


def _build_packet(status: dict[str, Any]) -> dict[str, Any]:
    readiness = status.get("readiness_gates") or {}
    source_control = status.get("source_control") or {}
    preview_health = status.get("preview_health") or {}
    preview_module = status.get("preview_module") or {}
    uat_walkthrough = status.get("uat_walkthrough") or {}
    release_handoff = status.get("release_handoff") or {}
    objective_audit = status.get("objective_audit") or {}
    real_data = status.get("real_data_closed_loop") or {}
    source_governance = status.get("source_governance_summary") or {}
    signoff_evidence_renderer_tool = status.get("signoff_evidence_renderer_tool") or {}
    signoff_evidence_template = status.get("signoff_evidence_template") or {}
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
        _readiness_item(
            "uat_walkthrough_script_in_manifest",
            "Screen-by-screen UAT walkthrough script is included in the delivery manifest",
            uat_walkthrough.get("included_in_manifest") is True,
            str(uat_walkthrough.get("path") or ""),
        ),
        _readiness_item(
            "current_release_handoff_in_manifest",
            "Current release handoff is included in the delivery manifest",
            release_handoff.get("included_in_manifest") is True,
            str(release_handoff.get("path") or ""),
        ),
        _readiness_item(
            "signoff_evidence_template_in_manifest",
            "Machine-readable production sign-off evidence template is included in the delivery manifest",
            signoff_evidence_template.get("included_in_manifest") is True,
            str(signoff_evidence_template.get("path") or ""),
        ),
        _readiness_item(
            "signoff_evidence_renderer_in_manifest",
            "Version-aligned production sign-off evidence draft renderer is included in the delivery manifest",
            signoff_evidence_renderer_tool.get("included_in_manifest") is True,
            str(signoff_evidence_renderer_tool.get("path") or ""),
        ),
        _readiness_item(
            "objective_completion_audit_present",
            "Objective completion audit is attached and exposes evidence-ready versus blocked objective areas",
            objective_audit.get("schema") == "sdoo.cn.objective-completion-audit.v1",
            json.dumps(
                {
                    "achieved": objective_audit.get("achieved"),
                    "state_counts": objective_audit.get("state_counts"),
                    "completion_blockers": objective_audit.get("completion_blockers"),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        ),
        _readiness_item(
            "workbench_summary_evidence",
            "Workbench exposes action, rule-basis, limitation and uncertainty summaries as machine-readable evidence",
            real_data_readiness.get("has_workbench_summary_evidence") is True,
            json.dumps(
                real_data.get("sample_profiles") or [],
                ensure_ascii=False,
                sort_keys=True,
            ),
        ),
        _readiness_item(
            "risk_task_report_summary_evidence",
            "Risk center, remediation tracker and report center expose representative summary evidence for UAT review",
            real_data_readiness.get("has_risk_task_report_summary_evidence") is True
            and real_data_readiness.get("has_risk_finding_visibility_evidence") is True
            and real_data_readiness.get("has_remediation_task_visibility_evidence")
            is True
            and real_data_readiness.get("has_report_visibility_evidence") is True
            and real_data_readiness.get("has_reviewer_view_contract_evidence") is True,
            json.dumps(
                {
                    "visibility": {
                        "risk_finding": real_data_readiness.get(
                            "has_risk_finding_visibility_evidence"
                        ),
                        "remediation_task": real_data_readiness.get(
                            "has_remediation_task_visibility_evidence"
                        ),
                        "report": real_data_readiness.get(
                            "has_report_visibility_evidence"
                        ),
                        "reviewer_view_contract": real_data_readiness.get(
                            "has_reviewer_view_contract_evidence"
                        ),
                    },
                    "reviewer_view_contracts": real_data.get("reviewer_view_contracts")
                    or [],
                    "findings": real_data.get("sample_findings") or [],
                    "remediation_tasks": (
                        real_data.get("sample_remediation_tasks") or []
                    ),
                    "reports": real_data.get("sample_reports") or [],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        ),
        _readiness_item(
            "remediation_verification_rescan_evidence",
            "Remediation closure has verified evidence and a verification rescan result",
            real_data_readiness.get("has_remediation_verification_rescan_evidence")
            is True,
            json.dumps(
                real_data.get("sample_remediation_tasks") or [],
                ensure_ascii=False,
                sort_keys=True,
            ),
        ),
        _readiness_item(
            "evidence_filing_payment_summary_evidence",
            "Evidence center and filing/payment archives expose verified evidence, integrity and next-action summaries",
            real_data_readiness.get("has_evidence_filing_payment_summary_evidence")
            is True,
            json.dumps(
                {
                    "evidence": real_data.get("sample_evidence") or [],
                    "filing_archives": (
                        real_data.get("sample_filing_archives") or []
                    ),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        ),
        _readiness_item(
            "controlled_ai_guidance_evidence",
            "Controlled AI guidance exposes provider, prompt, warning and checksum evidence for representative findings",
            real_data_readiness.get("has_controlled_ai_guidance_evidence") is True,
            json.dumps(
                real_data.get("sample_ai_guidance") or [],
                ensure_ascii=False,
                sort_keys=True,
            ),
        ),
        _readiness_item(
            "rule_source_governance_evidence",
            "Released China rules expose governed official sources, freshness review dates, professional sign-off and rule checksums",
            real_data_readiness.get("has_rule_source_governance_evidence") is True
            and real_data_readiness.get("has_official_source_freshness_evidence")
            is True
            and real_data_readiness.get("has_rule_professional_signoff_evidence")
            is True
            and real_data_readiness.get("has_rule_checksum_traceability_evidence")
            is True,
            json.dumps(
                {
                    "governance": {
                        "official_source_freshness": real_data_readiness.get(
                            "has_official_source_freshness_evidence"
                        ),
                        "rule_professional_signoff": real_data_readiness.get(
                            "has_rule_professional_signoff_evidence"
                        ),
                        "rule_checksum_traceability": real_data_readiness.get(
                            "has_rule_checksum_traceability_evidence"
                        ),
                    },
                    "authority_sources": real_data.get("sample_authority_sources") or [],
                    "rule_versions": real_data.get("sample_rule_versions") or [],
                    "source_monitor_runs": real_data.get("sample_source_monitor_runs") or [],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        ),
        _readiness_item(
            "official_source_governance_summary",
            "Official source governance summary exposes freshness, monitoring and rule sign-off issue counts",
            source_governance.get("ready") is True,
            json.dumps(source_governance, ensure_ascii=False, sort_keys=True),
        ),
        _readiness_item(
            "iit_payroll_withholding_scope_evidence",
            "IIT payroll withholding reconciliation exposes representative payroll, filing, payment, integrity and result evidence",
            real_data_readiness.get("has_iit_payroll_withholding_scope_evidence")
            is True,
            json.dumps(
                real_data.get("sample_iit_reconciliation_runs") or [],
                ensure_ascii=False,
                sort_keys=True,
            ),
        ),
        _readiness_item(
            "cross_border_review_scope_evidence",
            "Cross-border register exposes representative reviewed transaction facts, withholding consideration, evidence and checksum",
            real_data_readiness.get("has_cross_border_review_scope_evidence") is True,
            json.dumps(
                real_data.get("sample_cross_border_transactions") or [],
                ensure_ascii=False,
                sort_keys=True,
            ),
        ),
        _readiness_item(
            "customer_scope_gap_review_evidence",
            "Customer scope review exposes accounting coverage, external data, evidence gaps and open high-risk remediation status",
            real_data_readiness.get("has_customer_scope_gap_review_evidence") is True
            and real_data_readiness.get("has_customer_data_scope_review_evidence")
            is True
            and real_data_readiness.get("has_customer_evidence_gap_review_evidence")
            is True
            and real_data_readiness.get("has_open_high_risk_review_evidence")
            is True,
            json.dumps(
                {
                    "review": {
                        "customer_data_scope": real_data_readiness.get(
                            "has_customer_data_scope_review_evidence"
                        ),
                        "customer_evidence_gap": real_data_readiness.get(
                            "has_customer_evidence_gap_review_evidence"
                        ),
                        "open_high_risk": real_data_readiness.get(
                            "has_open_high_risk_review_evidence"
                        ),
                    },
                    "objects": real_data.get("objects") or {},
                    "accounting": real_data.get("accounting") or {},
                    "profiles": real_data.get("profiles")
                    or real_data.get("sample_profiles")
                    or [],
                    "findings": real_data.get("sample_findings") or [],
                    "remediation_tasks": real_data.get("sample_remediation_tasks") or [],
                    "evidence": real_data.get("sample_evidence") or [],
                    "filing_archives": real_data.get("sample_filing_archives") or [],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
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
            "addresses_blockers": [
                "business UAT decision must be recorded outside this automated status",
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
            "addresses_blockers": [
                "current official sources and released rules require professional sign-off evidence",
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
            "addresses_blockers": [
                "current official sources and released rules require professional sign-off evidence",
            ],
        },
        {
            "key": "customer_scope_and_data_gap_review",
            "owner": "implementation_owner",
            "required_evidence": "Customer-specific accounting periods, external datasets, controlled AI limitations, evidence gaps, open risks and remediation status reviewed.",
            "acceptable_decisions": ["no_blocking_gap", "limitations_documented"],
            "objective_areas": [
                "Odoo accounting and business-data basis",
                "external tax data sufficiency",
            ],
            "addresses_blockers": [
                "customer-specific data gaps, evidence gaps and open critical risks must be reviewed",
            ],
        },
        {
            "key": "representative_ux_walkthrough",
            "owner": "business_reviewer",
            "required_evidence": "Representative walkthrough evidence for workbench, risk center, remediation tracking, controlled AI guidance, filing/payment archive and compliance report pages, including risk level, cause, impact amount, period, owner, due date, status and next action visibility on common desktop and laptop screen sizes, plus AI provider, prompt version, input/output checksum, record checksum and professional warning visibility.",
            "acceptable_decisions": ["passed", "passed_with_limitations"],
            "objective_areas": [
                "risk center and remediation clarity",
                "Odoo-consistent viewing experience",
            ],
            "addresses_blockers": [
                "business UAT decision must be recorded outside this automated status",
            ],
        },
        {
            "key": "blocker_summary_walkthrough",
            "owner": "business_reviewer",
            "required_evidence": "Screenshot, recording or completed UAT reference showing that the workbench action/rule-basis/limitation summaries plus data readiness, evidence, filing/payment archive, remediation, report center and report readiness blocker summaries explain why each non-ready record is blocked, limited or uncertain, including controlled AI guidance disclosures.",
            "acceptable_decisions": ["passed", "passed_with_limitations"],
            "objective_areas": [
                "limitations and uncertainty visibility",
                "data/evidence/report readiness transparency",
            ],
            "addresses_blockers": [
                "business UAT decision must be recorded outside this automated status",
                "customer-specific data gaps, evidence gaps and open critical risks must be reviewed",
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
            "addresses_blockers": [
                "business UAT decision must be recorded outside this automated status",
                "current official sources and released rules require professional sign-off evidence",
                "customer-specific data gaps, evidence gaps and open critical risks must be reviewed",
            ],
        },
    ]
    production_signoff_blockers = readiness.get("production_signoff_blockers") or []
    production_blocker_coverage = _production_blocker_coverage(
        production_signoff_blockers,
        production_actions,
    )
    automated_items.append(
        _readiness_item(
            "production_blocker_coverage_complete",
            "Every production sign-off blocker is mapped to at least one human sign-off action",
            production_blocker_coverage.get("all_covered") is True,
            json.dumps(
                production_blocker_coverage,
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
    )
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
        "production_signoff_blockers": production_signoff_blockers,
        "production_blocker_coverage": production_blocker_coverage,
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
                f"- Evidence: {_markdown_evidence(item['evidence'])}",
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
                f"- Addresses blockers: `{', '.join(item['addresses_blockers'])}`",
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
                f"- Addresses blockers: `{', '.join(action['addresses_blockers'])}`",
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
    lines.extend(["", "## Production Blocker Coverage", ""])
    coverage_summary = packet.get("production_blocker_coverage") or {}
    lines.append(f"- All covered: `{coverage_summary.get('all_covered') is True}`")
    for item in coverage_summary.get("coverage") or []:
        lines.extend(
            [
                f"### {item.get('blocker')}",
                "",
                f"- Covered: `{item.get('covered') is True}`",
                f"- Action keys: `{', '.join(item.get('action_keys') or [])}`",
                "",
            ]
        )
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
