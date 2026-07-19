"""Audit China delivery status against the stated fiscal-compliance objective."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


AUDIT_SCHEMA = "sdoo.cn.objective-completion-audit.v1"
STATUS_SCHEMA = "sdoo.cn.delivery-status.v1"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _item(
    key: str,
    label: str,
    state: str,
    evidence: list[str],
    blockers: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "state": state,
        "evidence": evidence,
        "blockers": blockers or [],
    }


def _ready(value: object) -> bool:
    return value is True


def _state(ready: bool, blockers: list[str] | None = None) -> str:
    if ready:
        return "evidence_ready"
    if blockers:
        return "blocked"
    return "not_ready"


def _domain_item(key: str, domain: dict[str, Any]) -> dict[str, Any]:
    return _item(
        key,
        str(domain.get("label") or key),
        _state(_ready(domain.get("ready"))),
        [
            f"runs={domain.get('run_count')}",
            f"records={domain.get('record_count')}",
            f"evidence={domain.get('evidence')}",
        ],
        [] if _ready(domain.get("ready")) else [str(domain.get("boundary") or "")],
    )


def audit(status: dict[str, Any]) -> dict[str, Any]:
    if status.get("schema") != STATUS_SCHEMA:
        raise ValueError("delivery status schema is invalid")
    readiness = status.get("readiness_gates") or {}
    real_data = status.get("real_data_closed_loop") or {}
    real_data_readiness = real_data.get("readiness") or {}
    source_governance = status.get("source_governance_summary") or {}
    tax_domains = status.get("tax_domain_coverage") or {}
    preview_module = status.get("preview_module") or {}
    preview_health = status.get("preview_health") or {}
    upgrade_migration_chain = status.get("upgrade_migration_chain") or {}
    production_release_control = status.get("production_release_control") or {}
    signoff_validation = status.get("signoff_validation") or {}
    coverage_binding = (
        signoff_validation.get("production_blocker_coverage_binding")
        if isinstance(signoff_validation, dict)
        else {}
    )
    if not isinstance(coverage_binding, dict):
        coverage_binding = {}
    production_blockers = [
        str(blocker)
        for blocker in readiness.get("production_signoff_blockers") or []
    ]
    business_blockers = [
        str(blocker)
        for blocker in readiness.get("business_uat_blockers") or []
    ]
    items = [
        _item(
            "installable_upgradeable_odoo19",
            "Installable and upgradeable Odoo 19 plugin",
            _state(
                _ready(status.get("acceptance_passed"))
                and _ready(status.get("runtime_passed"))
                and _ready(status.get("upgrade_runtime_passed"))
                and _ready(preview_module.get("ok"))
                and _ready(upgrade_migration_chain.get("ready"))
            ),
            [
                f"acceptance_passed={status.get('acceptance_passed')}",
                f"runtime_passed={status.get('runtime_passed')}",
                f"upgrade_runtime_passed={status.get('upgrade_runtime_passed')}",
                f"preview_module_ok={preview_module.get('ok')}",
                f"upgrade_migration_chain={upgrade_migration_chain.get('ready')}",
                f"current_migration={upgrade_migration_chain.get('current_migration')}",
                f"migration_scripts={upgrade_migration_chain.get('migration_script_count')}",
            ],
        ),
        _item(
            "auditable_delivery_package",
            "Auditable delivery package and deterministic evidence",
            _state(
                _ready(status.get("aggregate_consistent"))
                and _ready(readiness.get("source_control_clean"))
                and _ready(status.get("acceptance_passed"))
                and _ready(production_release_control.get("included_in_manifest"))
            ),
            [
                f"aggregate_consistent={status.get('aggregate_consistent')}",
                f"source_control_clean={readiness.get('source_control_clean')}",
                f"manifest_files={(status.get('manifest') or {}).get('file_count')}",
                f"production_release_control={production_release_control.get('included_in_manifest')}",
            ],
        ),
        _item(
            "native_odoo_multi_company_security",
            "Native Odoo menu, action, multi-company and record-rule security contract",
            _state(
                _ready(real_data_readiness.get("has_multi_company_security_contract_evidence"))
                and _ready(real_data_readiness.get("has_menu_action_contract_evidence"))
                and _ready(real_data_readiness.get("has_workbench_action_contract_evidence"))
            ),
            [
                f"multi_company_security={real_data_readiness.get('has_multi_company_security_contract_evidence')}",
                f"security_contracts={len(real_data.get('multi_company_security_contracts') or [])}",
                f"menu_action_contracts={len(real_data.get('menu_action_contracts') or [])}",
                f"menu_action_contract={real_data_readiness.get('has_menu_action_contract_evidence')}",
                f"workbench_action_contracts={len(real_data.get('workbench_action_contracts') or [])}",
                f"workbench_action_contract={real_data_readiness.get('has_workbench_action_contract_evidence')}",
            ],
        ),
        _item(
            "real_odoo_accounting_business_data_basis",
            "Real Odoo accounting and business-data basis",
            _state(_ready(real_data_readiness.get("closed_loop_evidence_ready"))),
            [
                f"closed_loop_evidence_ready={real_data_readiness.get('closed_loop_evidence_ready')}",
                f"remediation_verification_rescan={real_data_readiness.get('has_remediation_verification_rescan_evidence')}",
                f"database={real_data.get('database')}",
            ],
        ),
        _item(
            "external_tax_data_sufficiency",
            "External invoice, filing, payment and payroll/tax data sufficiency",
            _state(
                _ready(real_data_readiness.get("has_evidence_filing_payment_summary_evidence"))
                and _ready(real_data_readiness.get("has_iit_payroll_withholding_scope_evidence"))
            ),
            [
                f"evidence_filing_payment={real_data_readiness.get('has_evidence_filing_payment_summary_evidence')}",
                f"iit_payroll_scope={real_data_readiness.get('has_iit_payroll_withholding_scope_evidence')}",
            ],
        ),
        _item(
            "customer_scope_gap_review_evidence",
            "Customer-specific data, evidence-gap and open high-risk review evidence",
            _state(
                _ready(real_data_readiness.get("has_customer_scope_gap_review_evidence"))
                and _ready(real_data_readiness.get("has_customer_data_scope_review_evidence"))
                and _ready(real_data_readiness.get("has_customer_evidence_gap_review_evidence"))
                and _ready(real_data_readiness.get("has_open_high_risk_review_evidence"))
            ),
            [
                f"customer_data_scope={real_data_readiness.get('has_customer_data_scope_review_evidence')}",
                f"customer_evidence_gap={real_data_readiness.get('has_customer_evidence_gap_review_evidence')}",
                f"open_high_risk_review={real_data_readiness.get('has_open_high_risk_review_evidence')}",
            ],
        ),
        _item(
            "source_governed_versioned_rules",
            "Source-governed, versioned and professionally signable China rules",
            _state(
                _ready(source_governance.get("ready"))
                and _ready(real_data_readiness.get("has_official_source_freshness_evidence"))
                and _ready(real_data_readiness.get("has_rule_professional_signoff_evidence"))
                and _ready(real_data_readiness.get("has_rule_checksum_traceability_evidence"))
            ),
            [
                f"source_governance_ready={source_governance.get('ready')}",
                f"source_records={source_governance.get('source_count')}",
                f"active_rule_versions={source_governance.get('active_rule_version_count')}",
                f"official_source_freshness={real_data_readiness.get('has_official_source_freshness_evidence')}",
                f"rule_professional_signoff={real_data_readiness.get('has_rule_professional_signoff_evidence')}",
                f"rule_checksum_traceability={real_data_readiness.get('has_rule_checksum_traceability_evidence')}",
            ],
        ),
        _item(
            "risk_remediation_report_visibility",
            "Risk center, remediation tracker and report clarity",
            _state(
                _ready(real_data_readiness.get("has_workbench_summary_evidence"))
                and _ready(real_data_readiness.get("has_risk_task_report_summary_evidence"))
                and _ready(real_data_readiness.get("has_risk_finding_visibility_evidence"))
                and _ready(real_data_readiness.get("has_remediation_task_visibility_evidence"))
                and _ready(real_data_readiness.get("has_report_visibility_evidence"))
                and _ready(real_data_readiness.get("has_reviewer_view_contract_evidence"))
                and _ready(real_data_readiness.get("has_ux_view_clarity_contract_evidence"))
            ),
            [
                f"workbench_summary={real_data_readiness.get('has_workbench_summary_evidence')}",
                f"risk_task_report_summary={real_data_readiness.get('has_risk_task_report_summary_evidence')}",
                f"risk_finding_visibility={real_data_readiness.get('has_risk_finding_visibility_evidence')}",
                f"remediation_task_visibility={real_data_readiness.get('has_remediation_task_visibility_evidence')}",
                f"report_visibility={real_data_readiness.get('has_report_visibility_evidence')}",
                f"reviewer_view_contract={real_data_readiness.get('has_reviewer_view_contract_evidence')}",
                f"ux_view_clarity_contract={real_data_readiness.get('has_ux_view_clarity_contract_evidence')}",
                f"ux_view_clarity_contracts={len(real_data.get('ux_view_clarity_contracts') or [])}",
            ],
        ),
        _item(
            "controlled_ai_guidance",
            "Controlled AI explanation and step-by-step guidance",
            _state(_ready(real_data_readiness.get("has_controlled_ai_guidance_evidence"))),
            [
                f"controlled_ai_guidance={real_data_readiness.get('has_controlled_ai_guidance_evidence')}",
            ],
        ),
        _item(
            "business_uat_gate",
            "Business UAT gate",
            _state(_ready(readiness.get("business_uat_ready")), business_blockers),
            [f"business_uat_ready={readiness.get('business_uat_ready')}"],
            business_blockers,
        ),
        _item(
            "production_signoff_gate",
            "Production sign-off gate",
            _state(_ready(readiness.get("production_signoff_ready")), production_blockers),
            [
                f"production_signoff_ready={readiness.get('production_signoff_ready')}",
                f"coverage_packet_all_covered={coverage_binding.get('packet_all_covered')}",
                f"coverage_evidence_matches_packet={coverage_binding.get('evidence_matches_packet')}",
            ],
            production_blockers,
        ),
    ]
    for key, domain in tax_domains.items():
        if isinstance(domain, dict):
            items.append(_domain_item(f"tax_domain_{key}", domain))
    achieved = all(item["state"] == "evidence_ready" for item in items)
    return {
        "schema": AUDIT_SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "version": status.get("version"),
        "source_commit": (status.get("source_control") or {}).get("commit"),
        "preview_url": status.get("preview_url"),
        "achieved": achieved,
        "state_counts": {
            state: sum(1 for item in items if item["state"] == state)
            for state in ("evidence_ready", "blocked", "not_ready")
        },
        "items": items,
        "completion_blockers": [
            blocker
            for item in items
            for blocker in item["blockers"]
            if blocker
        ],
    }


def _write_markdown(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# China Objective Completion Audit",
        "",
        f"- Version: `{payload.get('version')}`",
        f"- Source commit: `{payload.get('source_commit')}`",
        f"- Preview URL: `{payload.get('preview_url')}`",
        f"- Achieved: `{payload.get('achieved')}`",
        f"- State counts: `{payload.get('state_counts')}`",
        "",
        "## Objective Items",
        "",
    ]
    for item in payload.get("items") or []:
        lines.extend(
            [
                f"### {item.get('label')}",
                "",
                f"- Key: `{item.get('key')}`",
                f"- State: `{item.get('state')}`",
                f"- Evidence: {'; '.join(item.get('evidence') or [])}",
            ]
        )
        blockers = item.get("blockers") or []
        if blockers:
            lines.append("- Blockers:")
            lines.extend(f"  - {blocker}" for blocker in blockers)
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit the China delivery status against the delivery objective."
    )
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument(
        "--require-achieved",
        action="store_true",
        help="Exit with status 2 unless every objective item is evidence_ready.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    payload = audit(_load(args.status))
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
        "objective completion audited: "
        f"achieved={payload['achieved']} state_counts={payload['state_counts']}"
    )
    if args.require_achieved and payload["achieved"] is not True:
        print(f"completion blockers: {payload['completion_blockers']}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
