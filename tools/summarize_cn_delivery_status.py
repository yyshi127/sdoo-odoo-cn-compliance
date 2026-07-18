"""Summarize China delivery evidence for handoff review."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path


STATUS_SCHEMA = "sdoo.cn.delivery-status.v1"
PREVIEW_HEALTH_SCHEMA = "sdoo.cn.preview-health.v1"
PREVIEW_MODULE_SCHEMA = "sdoo.cn.preview-module.v1"
REAL_DATA_CLOSED_LOOP_SCHEMA = "sdoo.cn.real-data-closed-loop.v1"
SIGNOFF_VALIDATION_SCHEMA = "sdoo.cn.signoff-validation.v1"
OBJECTIVE_AUDIT_SCHEMA = "sdoo.cn.objective-completion-audit.v1"
BUSINESS_UAT_PATH = Path("docs/CHINA_BUSINESS_UAT_CHECKLIST.md")
UAT_WALKTHROUGH_PATH = Path("docs/CHINA_UAT_WALKTHROUGH_SCRIPT.md")
RELEASE_HANDOFF_PATH = Path("docs/CHINA_RELEASE_HANDOFF_CURRENT.md")
DELIVERY_INDEX_PATH = Path("docs/CHINA_DELIVERY_INDEX.md")
OBJECTIVE_COVERAGE_PATH = Path("docs/CHINA_DELIVERY_OBJECTIVE_COVERAGE.md")
PRODUCTION_SIGNOFF_PATH = Path("docs/CHINA_PRODUCTION_SIGNOFF_TEMPLATE.md")
PREVIEW_HEALTH_TOOL_PATH = Path("tools/check_cn_preview_health.py")
PREVIEW_MODULE_TOOL_PATH = Path("tools/check_cn_preview_module.py")
REAL_DATA_CLOSED_LOOP_TOOL_PATH = Path("tools/check_cn_real_data_closed_loop.py")
OBJECTIVE_AUDIT_TOOL_PATH = Path("tools/audit_cn_objective_completion.py")
SIGNOFF_PACKET_TOOL_PATH = Path("tools/generate_cn_signoff_packet.py")
SIGNOFF_EVIDENCE_RENDERER_TOOL_PATH = Path("tools/render_cn_signoff_evidence_template.py")
SIGNOFF_VALIDATION_TOOL_PATH = Path("tools/validate_cn_signoff_evidence.py")
SIGNOFF_EVIDENCE_TEMPLATE_PATH = Path("docs/samples/cn_signoff_evidence_template.json")
MOJIBAKE_MARKDOWN_PLACEHOLDER = (
    "[unreadable preview-database text; inspect the JSON evidence by record id]"
)
MOJIBAKE_MARKER_CHARS = frozenset(
    "锟斤拷"
    "涓涔浠佽妗楦塦鑻窞鐟崕浜"
    "鏂板姞鍧唴璐"
    "澶嶆牳椋庨櫓"
    "銆冩弿鎻"
    "鐧昏笉"
)

PRODUCTION_SIGNOFF_BLOCKER_ACTIONS = {
    "business UAT decision must be recorded outside this automated status": [
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
            "key": "representative_ux_walkthrough",
            "owner": "business_reviewer",
            "required_evidence": "Representative walkthrough evidence for workbench, risk center, remediation tracking, controlled AI guidance, filing/payment archive and compliance report pages, including risk level, cause, impact amount, period, owner, due date, status and next action visibility on common desktop and laptop screen sizes, plus AI provider, prompt version, input/output checksum, record checksum and professional warning visibility.",
            "acceptable_decisions": ["passed", "passed_with_limitations"],
            "objective_areas": [
                "risk center and remediation clarity",
                "Odoo-consistent viewing experience",
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
    ],
    "current official sources and released rules require professional sign-off evidence": [
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
            "key": "production_deployment_decision",
            "owner": "release_owner",
            "required_evidence": "Completed docs/CHINA_PRODUCTION_SIGNOFF_TEMPLATE.md with deploy/defer/reject decision and rollback owner.",
            "acceptable_decisions": ["deploy", "deploy_with_limitations", "defer", "reject"],
            "objective_areas": [
                "installable and upgradeable Odoo deployment",
                "auditable release and rollback decision",
            ],
        },
    ],
    "customer-specific data gaps, evidence gaps and open critical risks must be reviewed": [
        {
            "key": "customer_scope_and_data_gap_review",
            "owner": "implementation_owner",
            "required_evidence": "Customer-specific accounting periods, external datasets, controlled AI limitations, evidence gaps, open risks and remediation status reviewed.",
            "acceptable_decisions": ["no_blocking_gap", "limitations_documented"],
            "objective_areas": [
                "Odoo accounting and business-data basis",
                "external tax data sufficiency",
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
    ],
}


def _production_signoff_required_actions(blockers: list[str]) -> list[dict[str, object]]:
    actions_by_key: dict[str, dict[str, object]] = {}
    for blocker in blockers:
        for action in PRODUCTION_SIGNOFF_BLOCKER_ACTIONS.get(blocker, []):
            key = str(action.get("key") or "")
            if not key:
                continue
            entry = actions_by_key.setdefault(
                key,
                {
                    "key": key,
                    "owner": action.get("owner"),
                    "required_evidence": action.get("required_evidence"),
                    "acceptable_decisions": action.get("acceptable_decisions") or [],
                    "objective_areas": action.get("objective_areas") or [],
                    "addresses_blockers": [],
                },
            )
            addresses = entry["addresses_blockers"]
            if isinstance(addresses, list) and blocker not in addresses:
                addresses.append(blocker)
    return list(actions_by_key.values())


def _production_signoff_blocker_action_matrix(
    blockers: list[str],
    actions: list[dict[str, object]],
) -> list[dict[str, object]]:
    matrix: list[dict[str, object]] = []
    for blocker in blockers:
        action_keys = [
            str(action.get("key"))
            for action in actions
            if blocker in (action.get("addresses_blockers") or [])
        ]
        matrix.append(
            {
                "blocker": blocker,
                "covered": bool(action_keys),
                "action_keys": action_keys,
            }
        )
    return matrix


def _manifest_includes(
    manifest: dict[str, object] | None,
    path: Path,
) -> bool:
    return bool(
        manifest
        and any(
            entry.get("path") == path.as_posix()
            for entry in manifest.get("files", [])
            if isinstance(entry, dict)
        )
    )


def _load(path: Path | None) -> dict[str, object] | None:
    if not path:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _cjk_count(text: str) -> int:
    return sum("\u4e00" <= char <= "\u9fff" for char in text)


def _looks_mojibake(text: object) -> bool:
    if not isinstance(text, str):
        return False
    if "\ufffd" in text:
        return True
    if any("\ue000" <= char <= "\uf8ff" for char in text):
        return True
    cjk_count = _cjk_count(text)
    if "?" in text and cjk_count >= 2:
        return True
    if cjk_count < 2:
        return False
    marker_count = sum(char in MOJIBAKE_MARKER_CHARS for char in text)
    if marker_count >= 4 and marker_count / max(cjk_count, 1) >= 0.45:
        return True
    return False


def _markdown_text(value: object, fallback: str = MOJIBAKE_MARKDOWN_PLACEHOLDER) -> str:
    if value is False or value is None:
        return ""
    text = str(value)
    return fallback if _looks_mojibake(text) else text


def _sample_heading(record: dict[str, object], *field_names: str, fallback: str) -> str:
    for field_name in field_names:
        value = record.get(field_name)
        if value:
            text = _markdown_text(value)
            if text != MOJIBAKE_MARKDOWN_PLACEHOLDER:
                return text
    identifier = record.get("id")
    return f"{fallback} #{identifier}" if identifier else fallback


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
        "source_control": payload.get("source_control"),
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


def _tax_domain_coverage(real_data_closed_loop: dict[str, object] | None) -> dict[str, dict[str, object]]:
    real_data = real_data_closed_loop or {}
    objects = real_data.get("objects") if isinstance(real_data.get("objects"), dict) else {}
    readiness = (
        real_data.get("readiness")
        if isinstance(real_data.get("readiness"), dict)
        else {}
    )
    sample_filing_archives = real_data.get("sample_filing_archives") or []
    vat_filing_archives = [
        item
        for item in sample_filing_archives
        if isinstance(item, dict)
        and str(item.get("kind") or "").lower() in ("vat", "cn_vat", "vat_return")
    ]
    return {
        "vat": {
            "label": "VAT invoice / filing / payment",
            "ready": bool(
                (objects.get("vat_reconciliation_runs") or 0) > 0
                and (objects.get("vat_filing_records") or 0) > 0
                and (objects.get("tax_payment_records") or 0) > 0
                and bool(vat_filing_archives)
            ),
            "run_count": objects.get("vat_reconciliation_runs") or 0,
            "record_count": objects.get("vat_filing_records") or 0,
            "payment_record_count": objects.get("tax_payment_records") or 0,
            "evidence": "VAT reconciliation plus filing/payment archive sample",
            "boundary": "Representative UAT scope; production still requires current official rule sign-off and customer data completeness review.",
        },
        "cit": {
            "label": "CIT accounting / filing",
            "ready": bool(
                (objects.get("cit_reconciliation_runs") or 0) > 0
                and (objects.get("cit_filing_records") or 0) > 0
            ),
            "run_count": objects.get("cit_reconciliation_runs") or 0,
            "record_count": objects.get("cit_filing_records") or 0,
            "payment_record_count": None,
            "evidence": "CIT reconciliation and filing records",
            "boundary": "CIT data contract and reconciliation exist; representative remote demo evidence may still be thinner than VAT/IIT.",
        },
        "iit": {
            "label": "IIT payroll / withholding / payment",
            "ready": readiness.get("has_iit_payroll_withholding_scope_evidence")
            is True,
            "run_count": objects.get("active_profile_iit_reconciliation_runs") or 0,
            "record_count": objects.get("iit_withholding_records") or 0,
            "payroll_record_count": objects.get("payroll_summary_records") or 0,
            "payment_record_count": objects.get("tax_payment_records") or 0,
            "evidence": "Aligned IIT reconciliation with payroll, withholding filing, payment and checksum evidence",
            "boundary": "Demo uses controlled aggregate/pseudonymous payroll records; production requires lawful payroll and withholding exports.",
        },
        "cross_border": {
            "label": "Cross-border and withholding review",
            "ready": readiness.get("has_cross_border_review_scope_evidence")
            is True,
            "run_count": None,
            "record_count": objects.get("active_profile_cross_border_transactions") or 0,
            "payment_record_count": None,
            "evidence": "Reviewed cross-border transaction with evidence, withholding consideration and snapshot checksum",
            "boundary": "Fact-specific review remains required for contracts, payments, source rules and treaty analysis.",
        },
    }


def _tax_domain_markdown_lines(
    tax_domain_coverage: object,
) -> list[str]:
    if not isinstance(tax_domain_coverage, dict) or not tax_domain_coverage:
        return ["- No tax domain coverage summary was provided.", ""]
    lines: list[str] = []
    for key, domain in tax_domain_coverage.items():
        if not isinstance(domain, dict):
            continue
        lines.extend(
            [
                f"### {domain.get('label') or key}",
                "",
                f"- Ready: `{domain.get('ready', False)}`",
                f"- Runs: `{domain.get('run_count', '')}`",
                f"- Records: `{domain.get('record_count', '')}`",
            ]
        )
        if "payroll_record_count" in domain:
            lines.append(
                f"- Payroll records: `{domain.get('payroll_record_count', '')}`"
            )
        lines.extend(
            [
                f"- Payment records: `{domain.get('payment_record_count', '')}`",
                f"- Evidence: {domain.get('evidence', '')}",
                f"- Boundary: {domain.get('boundary', '')}",
                "",
            ]
        )
    return lines or ["- No tax domain coverage summary was provided.", ""]


def _coverage_binding_markdown_lines(binding: object) -> list[str]:
    if not isinstance(binding, dict):
        return ["- No sign-off validation coverage binding summary was provided."]
    return [
        (
            f"- Packet all covered: `{binding.get('packet_all_covered', False)}`; "
            f"evidence matches packet: `{binding.get('evidence_matches_packet', False)}`; "
            f"covered blockers: `{binding.get('covered_blocker_count', 0)}` / "
            f"`{binding.get('total_blocker_count', 0)}`"
        )
    ]


def _parse_date(value: object) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _source_governance_summary(
    real_data_closed_loop: dict[str, object] | None,
) -> dict[str, object]:
    real_data = real_data_closed_loop or {}
    readiness = (
        real_data.get("readiness")
        if isinstance(real_data.get("readiness"), dict)
        else {}
    )
    objects = real_data.get("objects") if isinstance(real_data.get("objects"), dict) else {}
    sources = [
        source
        for source in real_data.get("sample_authority_sources") or []
        if isinstance(source, dict)
    ]
    rule_versions = [
        version
        for version in real_data.get("sample_rule_versions") or []
        if isinstance(version, dict)
    ]
    monitor_runs = [
        run
        for run in real_data.get("sample_source_monitor_runs") or []
        if isinstance(run, dict)
    ]
    today = datetime.now(timezone.utc).date()
    overdue_sources = [
        source
        for source in sources
        if (review_date := _parse_date(source.get("next_review_date")))
        and review_date < today
    ]
    changed_monitor_runs = [
        run for run in monitor_runs if run.get("state") == "changed"
    ]
    failed_monitor_runs = [
        run for run in monitor_runs if run.get("state") == "failed"
    ]
    unapproved_rule_versions = [
        version
        for version in rule_versions
        if version.get("professional_review_state") != "approved"
        or version.get("release_state") not in ("active", "ready_to_activate")
        or not version.get("checksum")
        or not version.get("source_count")
    ]
    issue_count = (
        len(overdue_sources)
        + len(changed_monitor_runs)
        + len(failed_monitor_runs)
        + len(unapproved_rule_versions)
    )
    return {
        "ready": bool(
            readiness.get("has_rule_source_governance_evidence") is True
            and sources
            and rule_versions
            and issue_count == 0
        ),
        "source_count": objects.get("cn_authority_sources") or len(sources),
        "sample_source_count": len(sources),
        "valid_source_count": objects.get("cn_valid_authority_sources"),
        "active_rule_version_count": objects.get("cn_active_rule_versions"),
        "sample_rule_version_count": len(rule_versions),
        "monitor_run_count": objects.get("cn_source_monitor_runs") or len(monitor_runs),
        "overdue_source_count": len(overdue_sources),
        "changed_monitor_run_count": len(changed_monitor_runs),
        "failed_monitor_run_count": len(failed_monitor_runs),
        "unapproved_rule_version_count": len(unapproved_rule_versions),
        "latest_sample_source": sources[0].get("name") if sources else "",
        "latest_sample_source_next_review_date": (
            sources[0].get("next_review_date") if sources else ""
        ),
        "latest_monitor_state": (
            monitor_runs[0].get("state")
            if monitor_runs
            else (sources[0].get("last_monitor_state") if sources else "")
        ),
        "boundary": (
            "Automated evidence summarizes packaged source governance only; "
            "production still requires current official-source review and "
            "China tax professional sign-off."
        ),
    }


def _compliance_scope_blockers(
    tax_domain_coverage: object,
    source_governance_summary: object,
) -> list[str]:
    blockers: list[str] = []
    if not isinstance(tax_domain_coverage, dict) or not tax_domain_coverage:
        blockers.append("tax domain coverage summary was not provided")
    else:
        for key, domain in tax_domain_coverage.items():
            if not isinstance(domain, dict) or domain.get("ready") is not True:
                label = (
                    domain.get("label")
                    if isinstance(domain, dict) and domain.get("label")
                    else key
                )
                blockers.append(f"{label} coverage is not ready")
    if (
        not isinstance(source_governance_summary, dict)
        or source_governance_summary.get("ready") is not True
    ):
        blockers.append("official source governance summary is not ready")
    return blockers


def _source_control_blockers(source_control: object) -> list[str]:
    if not isinstance(source_control, dict):
        return ["source control evidence is missing"]
    blockers: list[str] = []
    if source_control.get("inside_worktree") is not True:
        blockers.append("source control evidence was not captured from a Git worktree")
    if not source_control.get("commit"):
        blockers.append("source commit is missing")
    if not source_control.get("branch"):
        blockers.append("source branch is missing")
    if source_control.get("dirty") is not False:
        blockers.append("source worktree is not confirmed clean")
    return blockers


def _status(
    *,
    bundle_metadata: dict[str, object] | None,
    manifest: dict[str, object] | None,
    summary: dict[str, object] | None,
    preview_health: dict[str, object] | None,
    preview_module: dict[str, object] | None,
    real_data_closed_loop: dict[str, object] | None,
    objective_audit: dict[str, object] | None,
    signoff_validation: dict[str, object] | None,
    preview_url: str | None,
) -> dict[str, object]:
    versions = {
        str(item.get("version"))
        for item in (bundle_metadata, manifest, summary)
        if item and item.get("version")
    }
    version = sorted(versions)[0] if len(versions) == 1 else None
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
    source_control = bundle_metadata.get("source_control") if bundle_metadata else None
    delivery_index = {
        "path": DELIVERY_INDEX_PATH.as_posix(),
        "included_in_manifest": _manifest_includes(manifest, DELIVERY_INDEX_PATH),
    }
    business_uat = {
        "path": BUSINESS_UAT_PATH.as_posix(),
        "included_in_manifest": _manifest_includes(manifest, BUSINESS_UAT_PATH),
    }
    uat_walkthrough = {
        "path": UAT_WALKTHROUGH_PATH.as_posix(),
        "included_in_manifest": _manifest_includes(manifest, UAT_WALKTHROUGH_PATH),
    }
    release_handoff = {
        "path": RELEASE_HANDOFF_PATH.as_posix(),
        "included_in_manifest": _manifest_includes(manifest, RELEASE_HANDOFF_PATH),
    }
    objective_coverage = {
        "path": OBJECTIVE_COVERAGE_PATH.as_posix(),
        "included_in_manifest": _manifest_includes(manifest, OBJECTIVE_COVERAGE_PATH),
    }
    production_signoff = {
        "path": PRODUCTION_SIGNOFF_PATH.as_posix(),
        "included_in_manifest": _manifest_includes(manifest, PRODUCTION_SIGNOFF_PATH),
    }
    preview_health_checker = {
        "path": PREVIEW_HEALTH_TOOL_PATH.as_posix(),
        "included_in_manifest": _manifest_includes(manifest, PREVIEW_HEALTH_TOOL_PATH),
    }
    preview_module_checker = {
        "path": PREVIEW_MODULE_TOOL_PATH.as_posix(),
        "included_in_manifest": _manifest_includes(manifest, PREVIEW_MODULE_TOOL_PATH),
    }
    real_data_closed_loop_checker = {
        "path": REAL_DATA_CLOSED_LOOP_TOOL_PATH.as_posix(),
        "included_in_manifest": _manifest_includes(
            manifest, REAL_DATA_CLOSED_LOOP_TOOL_PATH
        ),
    }
    objective_audit_tool = {
        "path": OBJECTIVE_AUDIT_TOOL_PATH.as_posix(),
        "included_in_manifest": _manifest_includes(manifest, OBJECTIVE_AUDIT_TOOL_PATH),
    }
    signoff_packet_tool = {
        "path": SIGNOFF_PACKET_TOOL_PATH.as_posix(),
        "included_in_manifest": _manifest_includes(manifest, SIGNOFF_PACKET_TOOL_PATH),
    }
    signoff_evidence_renderer_tool = {
        "path": SIGNOFF_EVIDENCE_RENDERER_TOOL_PATH.as_posix(),
        "included_in_manifest": _manifest_includes(
            manifest, SIGNOFF_EVIDENCE_RENDERER_TOOL_PATH
        ),
    }
    signoff_validation_tool = {
        "path": SIGNOFF_VALIDATION_TOOL_PATH.as_posix(),
        "included_in_manifest": _manifest_includes(
            manifest, SIGNOFF_VALIDATION_TOOL_PATH
        ),
    }
    signoff_evidence_template = {
        "path": SIGNOFF_EVIDENCE_TEMPLATE_PATH.as_posix(),
        "included_in_manifest": _manifest_includes(
            manifest, SIGNOFF_EVIDENCE_TEMPLATE_PATH
        ),
    }
    preview_health_summary = None
    if preview_health:
        preview_health_summary = {
            "schema": preview_health.get("schema"),
            "url": preview_health.get("url"),
            "ok": preview_health.get("ok") is True,
            "status_code": preview_health.get("status_code"),
            "blocking_marker": preview_health.get("blocking_marker"),
            "error": preview_health.get("error"),
        }
    preview_module_summary = None
    if preview_module:
        preview_module_summary = {
            "schema": preview_module.get("schema"),
            "database": preview_module.get("database"),
            "expected_version": preview_module.get("expected_version"),
            "ok": preview_module.get("ok") is True,
            "module_state": preview_module.get("module_state"),
            "module_installed_version": preview_module.get("module_installed_version"),
            "country_pack_version": preview_module.get("country_pack_version"),
            "required_capabilities": preview_module.get("required_capabilities"),
            "error": preview_module.get("error"),
        }
    real_data_closed_loop_summary = None
    if real_data_closed_loop:
        readiness = real_data_closed_loop.get("readiness")
        real_data_closed_loop_summary = {
            "schema": real_data_closed_loop.get("schema"),
            "database": real_data_closed_loop.get("database"),
            "expected_version": real_data_closed_loop.get("expected_version"),
            "ok": real_data_closed_loop.get("ok") is True,
            "module_installed_version": (
                (real_data_closed_loop.get("module") or {}).get("installed_version")
                if isinstance(real_data_closed_loop.get("module"), dict)
                else None
            ),
            "country_pack_version": (
                (real_data_closed_loop.get("country_pack") or {}).get("version")
                if isinstance(real_data_closed_loop.get("country_pack"), dict)
                else None
            ),
            "accounting": real_data_closed_loop.get("accounting"),
            "objects": real_data_closed_loop.get("objects"),
            "sample_profiles": real_data_closed_loop.get("sample_profiles"),
            "sample_findings": real_data_closed_loop.get("sample_findings"),
            "sample_remediation_tasks": real_data_closed_loop.get(
                "sample_remediation_tasks"
            ),
            "sample_reports": real_data_closed_loop.get("sample_reports"),
            "sample_evidence": real_data_closed_loop.get("sample_evidence"),
            "sample_filing_archives": real_data_closed_loop.get(
                "sample_filing_archives"
            ),
            "sample_ai_guidance": real_data_closed_loop.get("sample_ai_guidance"),
            "sample_authority_sources": real_data_closed_loop.get(
                "sample_authority_sources"
            ),
            "sample_rule_versions": real_data_closed_loop.get("sample_rule_versions"),
            "sample_source_monitor_runs": real_data_closed_loop.get(
                "sample_source_monitor_runs"
            ),
            "sample_iit_reconciliation_runs": real_data_closed_loop.get(
                "sample_iit_reconciliation_runs"
            ),
            "sample_cross_border_transactions": real_data_closed_loop.get(
                "sample_cross_border_transactions"
            ),
            "readiness": readiness if isinstance(readiness, dict) else None,
            "error": real_data_closed_loop.get("error"),
        }
    tax_domain_coverage = _tax_domain_coverage(real_data_closed_loop_summary)
    source_governance_summary = _source_governance_summary(
        real_data_closed_loop_summary
    )
    compliance_scope_blockers = _compliance_scope_blockers(
        tax_domain_coverage,
        source_governance_summary,
    )
    objective_audit_summary = None
    if objective_audit:
        objective_audit_summary = {
            "schema": objective_audit.get("schema"),
            "version": objective_audit.get("version"),
            "source_commit": objective_audit.get("source_commit"),
            "preview_url": objective_audit.get("preview_url"),
            "achieved": objective_audit.get("achieved") is True,
            "state_counts": objective_audit.get("state_counts"),
            "completion_blockers": objective_audit.get("completion_blockers"),
        }
    signoff_validation_summary = None
    if signoff_validation:
        signoff_validation_summary = {
            "schema": signoff_validation.get("schema"),
            "version": signoff_validation.get("version"),
            "source_commit": signoff_validation.get("source_commit"),
            "preview_url": signoff_validation.get("preview_url"),
            "ok": signoff_validation.get("ok") is True,
            "production_signoff_ready": signoff_validation.get("production_signoff_ready") is True,
            "deployment_decision": signoff_validation.get("deployment_decision"),
            "blockers": signoff_validation.get("blockers"),
            "warnings": signoff_validation.get("warnings"),
            "blocked_objective_areas": signoff_validation.get("blocked_objective_areas"),
            "blocked_production_signoff_blockers": signoff_validation.get(
                "blocked_production_signoff_blockers"
            ),
            "uncovered_production_signoff_blockers": signoff_validation.get(
                "uncovered_production_signoff_blockers"
            ),
            "production_blocker_coverage_binding": signoff_validation.get(
                "production_blocker_coverage_binding"
            ),
        }
    business_uat_blockers: list[str] = []
    if len(versions) > 1:
        business_uat_blockers.append("bundle, manifest and summary versions differ")
    if len(aggregate_values) > 1:
        business_uat_blockers.append("bundle and manifest aggregate checksums differ")
    if artifact_result != "passed":
        business_uat_blockers.append("automated acceptance did not pass")
    if isinstance(source_control, dict) and source_control.get("dirty") is True:
        business_uat_blockers.append("source worktree was dirty when delivery was built")
    if not runtime_passed:
        business_uat_blockers.append("Odoo runtime tests did not pass")
    for label, evidence in (
        ("delivery index", delivery_index),
        ("objective coverage", objective_coverage),
        ("current release handoff", release_handoff),
        ("business UAT checklist", business_uat),
        ("business UAT walkthrough script", uat_walkthrough),
        ("production sign-off template", production_signoff),
        ("preview health checker", preview_health_checker),
        ("preview module checker", preview_module_checker),
        ("real-data closed-loop checker", real_data_closed_loop_checker),
        ("objective completion auditor", objective_audit_tool),
        ("production sign-off packet generator", signoff_packet_tool),
        ("production sign-off evidence renderer", signoff_evidence_renderer_tool),
        ("production sign-off evidence validator", signoff_validation_tool),
        ("production sign-off evidence template", signoff_evidence_template),
    ):
        if not evidence["included_in_manifest"]:
            business_uat_blockers.append(f"{label} is not included in the manifest")
    if not preview_url:
        business_uat_blockers.append("preview URL was not recorded")
    if not preview_health_summary:
        business_uat_blockers.append("preview health result was not provided")
    else:
        if preview_health_summary["schema"] != PREVIEW_HEALTH_SCHEMA:
            business_uat_blockers.append("preview health result schema is invalid")
        if preview_health_summary["url"] != preview_url:
            business_uat_blockers.append("preview health URL does not match preview URL")
        if preview_health_summary["ok"] is not True:
            business_uat_blockers.append("preview health check did not pass")
    if not preview_module_summary:
        business_uat_blockers.append("preview module result was not provided")
    else:
        if preview_module_summary["schema"] != PREVIEW_MODULE_SCHEMA:
            business_uat_blockers.append("preview module result schema is invalid")
        if preview_module_summary["expected_version"] != version:
            business_uat_blockers.append("preview module expected version does not match delivery version")
        if preview_module_summary["ok"] is not True:
            business_uat_blockers.append("preview module check did not pass")
    if not real_data_closed_loop_summary:
        business_uat_blockers.append("real-data closed-loop result was not provided")
    else:
        if real_data_closed_loop_summary["schema"] != REAL_DATA_CLOSED_LOOP_SCHEMA:
            business_uat_blockers.append("real-data closed-loop result schema is invalid")
        if real_data_closed_loop_summary["expected_version"] != version:
            business_uat_blockers.append(
                "real-data closed-loop expected version does not match delivery version"
            )
        readiness = real_data_closed_loop_summary.get("readiness") or {}
        if not isinstance(readiness, dict) or readiness.get("demo_ready") is not True:
            business_uat_blockers.append("real-data demo readiness check did not pass")
    preview_readiness_blockers = [
        blocker
        for blocker in business_uat_blockers
        if blocker.startswith("preview ")
        or blocker.startswith("real-data ")
    ]
    production_signoff_blockers = list(business_uat_blockers)
    production_signoff_ready = False
    if not signoff_validation_summary:
        production_signoff_blockers.extend(
            [
                "business UAT decision must be recorded outside this automated status",
                "current official sources and released rules require professional sign-off evidence",
                "customer-specific data gaps, evidence gaps and open critical risks must be reviewed",
            ]
        )
    elif signoff_validation_summary["schema"] != SIGNOFF_VALIDATION_SCHEMA:
        production_signoff_blockers.append("sign-off validation result schema is invalid")
    else:
        signoff_binding_blockers: list[str] = []
        if signoff_validation_summary["version"] != version:
            signoff_binding_blockers.append(
                "sign-off validation version does not match delivery version"
            )
        if signoff_validation_summary["source_commit"] != (
            source_control.get("commit") if isinstance(source_control, dict) else None
        ):
            signoff_binding_blockers.append(
                "sign-off validation source commit does not match delivery source commit"
            )
        if signoff_validation_summary["preview_url"] != preview_url:
            signoff_binding_blockers.append(
                "sign-off validation preview URL does not match delivery preview URL"
            )
        if signoff_binding_blockers:
            production_signoff_blockers.extend(signoff_binding_blockers)
        elif signoff_validation_summary["production_signoff_ready"] is not True:
            blockers = signoff_validation_summary.get("blockers") or []
            production_signoff_blockers.extend(
                blockers if isinstance(blockers, list) else ["sign-off validation did not pass"]
            )
        else:
            production_signoff_ready = not production_signoff_blockers
    production_signoff_required_actions = _production_signoff_required_actions(
        production_signoff_blockers
    )
    return {
        "schema": STATUS_SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "version_consistent": len(versions) <= 1,
        "aggregate_consistent": len(aggregate_values) <= 1,
        "acceptance_passed": artifact_result == "passed",
        "runtime_passed": runtime_passed,
        "version": version,
        "preview_url": preview_url,
        "source_control": source_control,
        "business_uat": business_uat,
        "uat_walkthrough": uat_walkthrough,
        "release_handoff": release_handoff,
        "delivery_index": delivery_index,
        "objective_coverage": objective_coverage,
        "production_signoff": production_signoff,
        "preview_health_checker": preview_health_checker,
        "preview_module_checker": preview_module_checker,
        "real_data_closed_loop_checker": real_data_closed_loop_checker,
        "objective_audit_tool": objective_audit_tool,
        "signoff_packet_tool": signoff_packet_tool,
        "signoff_evidence_renderer_tool": signoff_evidence_renderer_tool,
        "signoff_validation_tool": signoff_validation_tool,
        "signoff_evidence_template": signoff_evidence_template,
        "preview_health": preview_health_summary,
        "preview_module": preview_module_summary,
        "real_data_closed_loop": real_data_closed_loop_summary,
        "tax_domain_coverage": tax_domain_coverage,
        "source_governance_summary": source_governance_summary,
        "objective_audit": objective_audit_summary,
        "signoff_validation": signoff_validation_summary,
        "readiness_gates": {
            "preview_ready": not preview_readiness_blockers,
            "preview_readiness_blockers": preview_readiness_blockers,
            "compliance_scope_ready": not compliance_scope_blockers,
            "compliance_scope_blockers": compliance_scope_blockers,
            "business_uat_ready": not business_uat_blockers,
            "business_uat_blockers": business_uat_blockers,
            "production_signoff_ready": production_signoff_ready,
            "production_signoff_blockers": production_signoff_blockers,
            "production_signoff_required_actions": production_signoff_required_actions,
            "production_signoff_blocker_action_matrix": (
                _production_signoff_blocker_action_matrix(
                    production_signoff_blockers,
                    production_signoff_required_actions,
                )
            ),
            "source_control_clean": not _source_control_blockers(source_control),
            "source_control_blockers": _source_control_blockers(source_control),
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
    source_control = status.get("source_control") or {}
    business_uat = status.get("business_uat") or {}
    uat_walkthrough = status.get("uat_walkthrough") or {}
    release_handoff = status.get("release_handoff") or {}
    delivery_index = status.get("delivery_index") or {}
    objective_coverage = status.get("objective_coverage") or {}
    production_signoff = status.get("production_signoff") or {}
    preview_health_checker = status.get("preview_health_checker") or {}
    preview_health = status.get("preview_health") or {}
    preview_module_checker = status.get("preview_module_checker") or {}
    preview_module = status.get("preview_module") or {}
    real_data_closed_loop_checker = status.get("real_data_closed_loop_checker") or {}
    objective_audit_tool = status.get("objective_audit_tool") or {}
    signoff_packet_tool = status.get("signoff_packet_tool") or {}
    signoff_evidence_renderer_tool = status.get("signoff_evidence_renderer_tool") or {}
    signoff_validation_tool = status.get("signoff_validation_tool") or {}
    signoff_evidence_template = status.get("signoff_evidence_template") or {}
    real_data_closed_loop = status.get("real_data_closed_loop") or {}
    objective_audit = status.get("objective_audit") or {}
    signoff_validation = status.get("signoff_validation") or {}
    real_data_readiness = real_data_closed_loop.get("readiness") or {}
    sample_profiles = real_data_closed_loop.get("sample_profiles") or []
    sample_findings = real_data_closed_loop.get("sample_findings") or []
    sample_tasks = real_data_closed_loop.get("sample_remediation_tasks") or []
    sample_reports = real_data_closed_loop.get("sample_reports") or []
    sample_evidence = real_data_closed_loop.get("sample_evidence") or []
    sample_filing_archives = real_data_closed_loop.get("sample_filing_archives") or []
    sample_ai_guidance = real_data_closed_loop.get("sample_ai_guidance") or []
    sample_sources = real_data_closed_loop.get("sample_authority_sources") or []
    sample_rule_versions = real_data_closed_loop.get("sample_rule_versions") or []
    sample_monitor_runs = real_data_closed_loop.get("sample_source_monitor_runs") or []
    sample_iit_runs = real_data_closed_loop.get("sample_iit_reconciliation_runs") or []
    sample_cross_border_transactions = real_data_closed_loop.get(
        "sample_cross_border_transactions"
    ) or []
    readiness = status.get("readiness_gates") or {}
    tax_domain_coverage = status.get("tax_domain_coverage") or {}
    source_governance = status.get("source_governance_summary") or {}
    lines = [
        "# China Delivery Status",
        "",
        f"- Version consistent: `{status['version_consistent']}`",
        f"- Aggregate consistent: `{status['aggregate_consistent']}`",
        f"- Acceptance passed: `{status['acceptance_passed']}`",
        f"- Runtime passed: `{status['runtime_passed']}`",
        f"- Preview URL: `{status.get('preview_url') or ''}`",
        f"- Source branch: `{source_control.get('branch', '')}`",
        f"- Source commit: `{source_control.get('commit', '')}`",
        f"- Source worktree dirty: `{source_control.get('dirty', '')}`",
        f"- Delivery index: `{delivery_index.get('path', '')}`",
        f"- Delivery index in manifest: `{delivery_index.get('included_in_manifest', False)}`",
        f"- Business UAT checklist: `{business_uat.get('path', '')}`",
        f"- Business UAT checklist in manifest: `{business_uat.get('included_in_manifest', False)}`",
        f"- Business UAT walkthrough script: `{uat_walkthrough.get('path', '')}`",
        f"- Business UAT walkthrough script in manifest: `{uat_walkthrough.get('included_in_manifest', False)}`",
        f"- Current release handoff: `{release_handoff.get('path', '')}`",
        f"- Current release handoff in manifest: `{release_handoff.get('included_in_manifest', False)}`",
        f"- Objective coverage: `{objective_coverage.get('path', '')}`",
        f"- Objective coverage in manifest: `{objective_coverage.get('included_in_manifest', False)}`",
        f"- Production sign-off template: `{production_signoff.get('path', '')}`",
        f"- Production sign-off template in manifest: `{production_signoff.get('included_in_manifest', False)}`",
        f"- Preview health checker: `{preview_health_checker.get('path', '')}`",
        f"- Preview health checker in manifest: `{preview_health_checker.get('included_in_manifest', False)}`",
        f"- Preview health ok: `{preview_health.get('ok', False)}`",
        f"- Preview health status code: `{preview_health.get('status_code', '')}`",
        f"- Preview health blocking marker: `{preview_health.get('blocking_marker', '')}`",
        f"- Preview health error: `{preview_health.get('error', '')}`",
        f"- Preview module checker: `{preview_module_checker.get('path', '')}`",
        f"- Preview module checker in manifest: `{preview_module_checker.get('included_in_manifest', False)}`",
        f"- Preview module ok: `{preview_module.get('ok', False)}`",
        f"- Preview module version: `{preview_module.get('module_installed_version', '')}`",
        f"- Preview country pack version: `{preview_module.get('country_pack_version', '')}`",
        f"- Real-data closed-loop checker: `{real_data_closed_loop_checker.get('path', '')}`",
        f"- Real-data closed-loop checker in manifest: `{real_data_closed_loop_checker.get('included_in_manifest', False)}`",
        f"- Objective completion auditor: `{objective_audit_tool.get('path', '')}`",
        f"- Objective completion auditor in manifest: `{objective_audit_tool.get('included_in_manifest', False)}`",
        f"- Objective completion audit achieved: `{objective_audit.get('achieved', False)}`",
        f"- Objective completion audit state counts: `{objective_audit.get('state_counts', '')}`",
        f"- Objective completion audit blockers: `{len(objective_audit.get('completion_blockers') or [])}`",
        f"- Sign-off packet generator: `{signoff_packet_tool.get('path', '')}`",
        f"- Sign-off packet generator in manifest: `{signoff_packet_tool.get('included_in_manifest', False)}`",
        f"- Sign-off evidence renderer: `{signoff_evidence_renderer_tool.get('path', '')}`",
        f"- Sign-off evidence renderer in manifest: `{signoff_evidence_renderer_tool.get('included_in_manifest', False)}`",
        f"- Sign-off evidence validator: `{signoff_validation_tool.get('path', '')}`",
        f"- Sign-off evidence validator in manifest: `{signoff_validation_tool.get('included_in_manifest', False)}`",
        f"- Sign-off evidence template: `{signoff_evidence_template.get('path', '')}`",
        f"- Sign-off evidence template in manifest: `{signoff_evidence_template.get('included_in_manifest', False)}`",
        f"- Real-data setup demo ready: `{real_data_readiness.get('setup_demo_ready', False)}`",
        f"- Real-data demo ready: `{real_data_readiness.get('demo_ready', False)}`",
        f"- Real-data closed-loop evidence ready: `{real_data_readiness.get('closed_loop_evidence_ready', False)}`",
        f"- Workbench summary evidence ready: `{real_data_readiness.get('has_workbench_summary_evidence', False)}`",
        f"- Risk/task/report summary evidence ready: `{real_data_readiness.get('has_risk_task_report_summary_evidence', False)}`",
        f"- Evidence/filing/payment summary evidence ready: `{real_data_readiness.get('has_evidence_filing_payment_summary_evidence', False)}`",
        f"- Controlled AI guidance evidence ready: `{real_data_readiness.get('has_controlled_ai_guidance_evidence', False)}`",
        f"- Rule/source governance evidence ready: `{real_data_readiness.get('has_rule_source_governance_evidence', False)}`",
        f"- Official source governance summary ready: `{source_governance.get('ready', False)}`",
        f"- Official source governance issues: `{source_governance.get('overdue_source_count', 0)} overdue source(s), {source_governance.get('changed_monitor_run_count', 0)} changed monitor run(s), {source_governance.get('failed_monitor_run_count', 0)} failed monitor run(s), {source_governance.get('unapproved_rule_version_count', 0)} rule governance issue(s)`",
        f"- IIT payroll withholding scope evidence ready: `{real_data_readiness.get('has_iit_payroll_withholding_scope_evidence', False)}`",
        f"- Cross-border review scope evidence ready: `{real_data_readiness.get('has_cross_border_review_scope_evidence', False)}`",
        f"- Sign-off validation ok: `{signoff_validation.get('ok', False)}`",
        f"- Sign-off deployment decision: `{signoff_validation.get('deployment_decision', '')}`",
        f"- Preview ready: `{readiness.get('preview_ready', False)}`",
        f"- Compliance scope ready: `{readiness.get('compliance_scope_ready', False)}`",
        f"- Business UAT ready: `{readiness.get('business_uat_ready', False)}`",
        f"- Production sign-off ready: `{readiness.get('production_signoff_ready', False)}`",
        "",
        "## Readiness Gates",
        "",
        "### Preview Readiness Blockers",
        "",
        *[
            f"- {blocker}"
            for blocker in readiness.get("preview_readiness_blockers", [])
        ],
        "",
        "### Compliance Scope Blockers",
        "",
        *[
            f"- {blocker}"
            for blocker in readiness.get("compliance_scope_blockers", [])
        ],
        "",
        "### Business UAT Blockers",
        "",
        *[
            f"- {blocker}"
            for blocker in readiness.get("business_uat_blockers", [])
        ],
        "",
        "### Production Sign-off Blockers",
        "",
        *[
            f"- {blocker}"
            for blocker in readiness.get("production_signoff_blockers", [])
        ],
        "",
        "### Production Sign-off Blocker Action Matrix",
        "",
        *[
            (
                f"- `{item.get('blocker')}` -> "
                f"`{', '.join(item.get('action_keys') or [])}` "
                f"(covered: `{item.get('covered', False)}`)"
            )
            for item in readiness.get(
                "production_signoff_blocker_action_matrix", []
            )
            if isinstance(item, dict)
        ],
        "",
        "### Production Sign-off Required Human Actions",
        "",
        *[
            (
                f"- `{action.get('key')}` owner=`{action.get('owner')}` "
                f"evidence=`{action.get('required_evidence')}` "
                f"addresses=`{'; '.join(action.get('addresses_blockers') or [])}`"
            )
            for action in readiness.get("production_signoff_required_actions", [])
        ],
        "",
        "### Production Blocked Objective Areas",
        "",
        *[
            f"- {area}"
            for area in signoff_validation.get("blocked_objective_areas", []) or []
        ],
        "",
        "### Production Blocked Sign-off Blockers",
        "",
        *[
            f"- {blocker}"
            for blocker in signoff_validation.get(
                "blocked_production_signoff_blockers", []
            )
            or []
        ],
        "",
        "### Production Blocker Coverage Binding",
        "",
        *_coverage_binding_markdown_lines(
            signoff_validation.get("production_blocker_coverage_binding")
        ),
        "",
        "### Objective Completion Audit Blockers",
        "",
        *[
            f"- {blocker}"
            for blocker in objective_audit.get("completion_blockers", []) or []
        ],
        "",
        "## Tax Domain Coverage Overview",
        "",
        *_tax_domain_markdown_lines(tax_domain_coverage),
        "## Official Source Governance Overview",
        "",
        f"- Ready: `{source_governance.get('ready', False)}`",
        f"- Source records: `{source_governance.get('source_count', '')}`",
        f"- Valid source records: `{source_governance.get('valid_source_count', '')}`",
        f"- Active rule versions: `{source_governance.get('active_rule_version_count', '')}`",
        f"- Monitor runs: `{source_governance.get('monitor_run_count', '')}`",
        f"- Overdue source samples: `{source_governance.get('overdue_source_count', 0)}`",
        f"- Changed monitor run samples: `{source_governance.get('changed_monitor_run_count', 0)}`",
        f"- Failed monitor run samples: `{source_governance.get('failed_monitor_run_count', 0)}`",
        f"- Rule governance issue samples: `{source_governance.get('unapproved_rule_version_count', 0)}`",
        f"- Latest sample source: `{_markdown_text(source_governance.get('latest_sample_source', ''))}`",
        f"- Latest sample source next review date: `{source_governance.get('latest_sample_source_next_review_date', '')}`",
        f"- Latest monitor state: `{source_governance.get('latest_monitor_state', '')}`",
        f"- Boundary: {source_governance.get('boundary', '')}",
        "",
        "## Artifacts",
        "",
        f"- Bundle version: `{bundle.get('version', '')}`",
        f"- Bundle SHA-256: `{bundle.get('bundle_sha256', '')}`",
        f"- Manifest files: `{manifest.get('file_count', '')}`",
        f"- Manifest aggregate SHA-256: `{manifest.get('aggregate_sha256', '')}`",
        f"- Acceptance result: `{acceptance.get('result', '')}`",
        "",
        "## Workbench Summary Evidence",
        "",
        *(
            [
                line
                for profile in sample_profiles[:5]
                if isinstance(profile, dict)
                for line in (
                    f"### {_sample_heading(profile, 'name', 'company', fallback='Compliance Profile')}",
                    "",
                    f"- Company: `{_markdown_text(profile.get('company', ''))}`",
                    f"- Status: `{profile.get('status', '')}`",
                    f"- Period: `{_markdown_text(profile.get('period_label', ''))}`",
                    f"- Next action: `{_markdown_text(profile.get('next_action', ''))}`",
                    f"- Action summary: {_markdown_text(profile.get('action_summary', ''))}",
                    f"- Rule basis: `{profile.get('rule_basis_state', '')}` - {_markdown_text(profile.get('rule_basis_summary', ''))}",
                    f"- Limitations: {_markdown_text(profile.get('limitation_summary', ''))}",
                    f"- Uncertainty: {_markdown_text(profile.get('uncertainty_summary', ''))}",
                    f"- Limitation next action: {_markdown_text(profile.get('limitation_next_action', ''))}",
                    "",
                )
            ]
            if isinstance(sample_profiles, list) and sample_profiles
            else ["- No sample profile workbench summary evidence was provided.", ""]
        ),
        "## Risk, Remediation and Report Summary Evidence",
        "",
        "### Sample Risks",
        "",
        *(
            [
                line
                for finding in sample_findings[:5]
                if isinstance(finding, dict)
                for line in (
                    f"#### {_sample_heading(finding, 'title', 'name', fallback='Risk')}",
                    "",
                    f"- Company: `{_markdown_text(finding.get('company', ''))}`",
                    f"- Period: `{finding.get('period_label', '')}`",
                    f"- Risk level: `{finding.get('risk_level', '')}`",
                    f"- Result/review: `{finding.get('result', '')}` / `{finding.get('review_state', '')}`",
                    f"- Tax impact: {_markdown_text(finding.get('tax_impact', ''))}",
                    f"- Rule basis: `{finding.get('rule_basis_state', '')}` / `{finding.get('professional_state', '')}`",
                    f"- Evidence/closure: `{finding.get('evidence_state', '')}` / `{finding.get('closure_state', '')}`",
                    f"- Next action: {_markdown_text(finding.get('next_action', ''))}",
                    f"- Action summary: {_markdown_text(finding.get('action_summary', ''))}",
                    "",
                )
            ]
            if isinstance(sample_findings, list) and sample_findings
            else ["- No sample risk summary evidence was provided.", ""]
        ),
        "### Sample Remediation Tasks",
        "",
        *(
            [
                line
                for task in sample_tasks[:5]
                if isinstance(task, dict)
                for line in (
                    f"#### {_sample_heading(task, 'name', fallback='Remediation Task')}",
                    "",
                    f"- Company: `{_markdown_text(task.get('company', ''))}`",
                    f"- Risk level: `{task.get('risk_level', '')}`",
                    f"- State/verification: `{task.get('state', '')}` / `{task.get('verification_state', '')}`",
                    f"- Assignee/due date: `{_markdown_text(task.get('assignee', ''))}` / `{task.get('due_date', '')}`",
                    f"- Evidence/traceability: `{task.get('evidence_state', '')}` / `{task.get('traceability_state', '')}`",
                    f"- Next action: {_markdown_text(task.get('next_action', ''))}",
                    f"- Action summary: {_markdown_text(task.get('action_summary', ''))}",
                    "",
                )
            ]
            if isinstance(sample_tasks, list) and sample_tasks
            else ["- No sample remediation summary evidence was provided.", ""]
        ),
        "### Sample Reports",
        "",
        *(
            [
                line
                for report in sample_reports[:5]
                if isinstance(report, dict)
                for line in (
                    f"#### {_sample_heading(report, 'name', fallback='Compliance Report')}",
                    "",
                    f"- Company: `{_markdown_text(report.get('company', ''))}`",
                    f"- Period: `{report.get('period_start', '')}` to `{report.get('period_end', '')}`",
                    f"- State/conclusion: `{report.get('state', '')}` / `{report.get('conclusion_state', '')}`",
                    f"- Traceability/fact basis: `{report.get('traceability_state', '')}` / `{report.get('fact_basis_state', '')}`",
                    f"- Integrity: center `{report.get('center_integrity_state', '')}`, snapshot `{report.get('snapshot_integrity_state', '')}`, approval `{report.get('approval_integrity_state', '')}`, pdf `{report.get('pdf_integrity_state', '')}`",
                    f"- Blockers: {_markdown_text(report.get('blocker_summary', ''))}",
                    f"- Next action: {_markdown_text(report.get('traceability_next_action') or report.get('center_next_action') or '')}",
                    "",
                )
            ]
            if isinstance(sample_reports, list) and sample_reports
            else ["- No sample report summary evidence was provided.", ""]
        ),
        "## Controlled AI Guidance Evidence",
        "",
        *(
            [
                line
                for guidance in sample_ai_guidance[:5]
                if isinstance(guidance, dict)
                for line in (
                    f"### {guidance.get('name') or guidance.get('id') or 'AI Guidance'}",
                    "",
                    f"- Finding: `{guidance.get('finding', '')}`",
                    f"- Provider/state: `{guidance.get('provider_key', '')}` / `{guidance.get('state', '')}`",
                    f"- Jurisdiction/prompt: `{guidance.get('jurisdiction_code', '')}` / `{guidance.get('prompt_version', '')}`",
                    f"- Model: `{guidance.get('model_name', '')}`",
                    f"- Source/professional warnings: `{guidance.get('source_warning', '')}` / `{guidance.get('professional_warning', '')}`",
                    f"- Checksums present: input `{bool(guidance.get('input_checksum'))}`, output `{bool(guidance.get('output_checksum'))}`, record `{bool(guidance.get('record_checksum'))}`",
                    "",
                )
            ]
            if isinstance(sample_ai_guidance, list) and sample_ai_guidance
            else ["- No sample controlled AI guidance evidence was provided.", ""]
        ),
        "## Rule And Source Governance Evidence",
        "",
        "### Official Sources",
        "",
        *(
            [
                line
                for source in sample_sources[:5]
                if isinstance(source, dict)
                for line in (
                    f"#### {source.get('name') or source.get('id') or 'Authority Source'}",
                    "",
                    f"- Status/snapshot: `{source.get('status', '')}` / `{source.get('snapshot_kind', '')}`",
                    f"- Content hash: `{source.get('content_hash', '')}`",
                    f"- Snapshot attachment: `{source.get('snapshot_attachment', '')}`",
                    f"- Next review date: `{source.get('next_review_date', '')}`",
                    f"- Monitor: `{source.get('last_monitor_state', '')}` / next `{source.get('next_monitor_date', '')}`",
                    "",
                )
            ]
            if isinstance(sample_sources, list) and sample_sources
            else ["- No official source governance sample was provided.", ""]
        ),
        "### Released Rule Versions",
        "",
        *(
            [
                line
                for version in sample_rule_versions[:5]
                if isinstance(version, dict)
                for line in (
                    f"#### {version.get('name') or version.get('id') or 'Rule Version'}",
                    "",
                    f"- State/release: `{version.get('state', '')}` / `{version.get('release_state', '')}`",
                    f"- Professional review: `{version.get('professional_review_state', '')}` / ready `{version.get('professional_ready', '')}`",
                    f"- Test/checksum: `{version.get('test_state', '')}` / `{version.get('checksum', '')}`",
                    f"- Sources: `{version.get('source_count', 0)}` - {', '.join(version.get('source_names') or [])}",
                    f"- Next review date: `{version.get('next_review_date', '')}`",
                    "",
                )
            ]
            if isinstance(sample_rule_versions, list) and sample_rule_versions
            else ["- No released rule governance sample was provided.", ""]
        ),
        "### Source Monitor Runs",
        "",
        *(
            [
                line
                for run in sample_monitor_runs[:5]
                if isinstance(run, dict)
                for line in (
                    f"#### {run.get('name') or run.get('id') or 'Monitor Run'}",
                    "",
                    f"- Source/state: `{run.get('source', '')}` / `{run.get('state', '')}`",
                    f"- Integrity/checksum: `{run.get('result_integrity_state', '')}` / `{run.get('result_checksum', '')}`",
                    f"- Source snapshot: `{run.get('source_snapshot_checksum', '')}`",
                    f"- Impact snapshot: `{run.get('impact_snapshot_checksum', '')}`",
                    f"- Summary: {run.get('result_summary', '')}",
                    "",
                )
            ]
            if isinstance(sample_monitor_runs, list) and sample_monitor_runs
            else ["- No source monitor run sample was provided; next review dates remain the freshness control for this handoff.", ""]
        ),
        "## Evidence, Filing and Payment Archive Summary Evidence",
        "",
        "### Sample Evidence",
        "",
        *(
            [
                line
                for evidence in sample_evidence[:5]
                if isinstance(evidence, dict)
                for line in (
                    f"#### {evidence.get('name') or evidence.get('id') or 'Evidence'}",
                    "",
                    f"- Company: `{evidence.get('company', '')}`",
                    f"- State: `{evidence.get('state', '')}`",
                    f"- Source: {evidence.get('source_summary', '')}",
                    f"- Blockers: {evidence.get('blocker_summary', '')}",
                    f"- Verified by/at: `{evidence.get('verified_by', '')}` / `{evidence.get('verified_at', '')}`",
                    f"- Checksum present: `{bool(evidence.get('document_checksum'))}`",
                    "",
                )
            ]
            if isinstance(sample_evidence, list) and sample_evidence
            else ["- No sample evidence summary was provided.", ""]
        ),
        "### Sample Filing and Payment Archives",
        "",
        *(
            [
                line
                for filing in sample_filing_archives[:5]
                if isinstance(filing, dict)
                for line in (
                    f"#### {filing.get('name') or filing.get('id') or 'Filing Archive'}",
                    "",
                    f"- Company: `{filing.get('company', '')}`",
                    f"- Kind/period: `{filing.get('kind', '')}` / `{filing.get('period_label', '')}`",
                    f"- State/payment: `{filing.get('state', '')}` / `{filing.get('payment_state', '')}`",
                    f"- Due date: `{filing.get('due_date', '')}`",
                    f"- Submission/payment integrity: `{filing.get('submission_integrity_state', '')}` / `{filing.get('payment_integrity_state', '')}`",
                    f"- Evidence: `{filing.get('evidence_state', '')}` ({filing.get('verified_evidence_count', 0)}/{filing.get('evidence_count', 0)})",
                    f"- Blockers: {filing.get('blocker_summary', '')}",
                    f"- Next action: {filing.get('next_action', '')}",
                    f"- Checksums present: submission `{bool(filing.get('submission_checksum'))}`, payment `{bool(filing.get('payment_checksum'))}`",
                    "",
                )
            ]
            if isinstance(sample_filing_archives, list) and sample_filing_archives
            else ["- No sample filing/payment archive summary was provided.", ""]
        ),
        "## IIT Payroll Withholding Scope Evidence",
        "",
        *(
            [
                line
                for run in sample_iit_runs[:5]
                if isinstance(run, dict)
                for line in (
                    f"### {run.get('name') or run.get('id') or 'IIT Reconciliation Run'}",
                    "",
                    f"- Company/profile: `{run.get('company', '')}` / `{run.get('profile', '')}`",
                    f"- Period: `{run.get('period_start', '')}` to `{run.get('period_end', '')}`",
                    f"- State/conclusion: `{run.get('state', '')}` / `{run.get('conclusion_state', '')}`",
                    f"- Source states: accounting `{run.get('accounting_source_state', '')}`, payroll `{run.get('payroll_source_state', '')}`, filing `{run.get('filing_source_state', '')}`, payment `{run.get('payment_source_state', '')}`",
                    f"- Counts: payroll `{run.get('payroll_record_count', 0)}`, filing `{run.get('filing_record_count', 0)}`, payment `{run.get('payment_record_count', 0)}`, issues `{run.get('issue_count', 0)}`",
                    f"- Payroll persons/gross/withheld IIT: `{run.get('payroll_person_count', '')}` / `{run.get('payroll_gross_income_amount', '')}` / `{run.get('payroll_withheld_iit_amount', '')}`",
                    f"- Result integrity/checksum: `{run.get('result_integrity_state', '')}` / `{run.get('result_checksum', '')}`",
                    f"- Summary: {run.get('result_summary', '')}",
                    "",
                )
            ]
            if isinstance(sample_iit_runs, list) and sample_iit_runs
            else ["- No representative IIT payroll withholding reconciliation sample was provided; this objective area remains a visible coverage gap for business UAT.", ""]
        ),
        "## Cross-Border Review Scope Evidence",
        "",
        *(
            [
                line
                for transaction in sample_cross_border_transactions[:5]
                if isinstance(transaction, dict)
                for line in (
                    f"### {transaction.get('name') or transaction.get('id') or 'Cross-Border Transaction'}",
                    "",
                    f"- Company/profile: `{transaction.get('company', '')}` / `{transaction.get('profile', '')}`",
                    f"- Period/date: `{transaction.get('period_start', '')}` to `{transaction.get('period_end', '')}` / `{transaction.get('transaction_date', '')}`",
                    f"- Type/counterparty: `{transaction.get('transaction_type', '')}` / `{transaction.get('counterparty', '')}` `{transaction.get('counterparty_country', '')}`",
                    f"- Amount/related party: `{transaction.get('amount', '')}` / `{transaction.get('related_party', '')}`",
                    f"- State/readiness: `{transaction.get('state', '')}` / `{transaction.get('readiness_state', '')}`",
                    f"- Withholding considered: `{transaction.get('withholding_considered', '')}`",
                    f"- Evidence/checksum: `{transaction.get('evidence_count', 0)}` / `{transaction.get('snapshot_checksum', '')}`",
                    f"- Next action: {transaction.get('next_action', '')}",
                    "",
                )
            ]
            if isinstance(sample_cross_border_transactions, list)
            and sample_cross_border_transactions
            else ["- No representative reviewed cross-border transaction sample was provided; this objective area remains a visible coverage gap for business UAT.", ""]
        ),
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
    parser.add_argument("--preview-health", type=Path)
    parser.add_argument("--preview-module", type=Path)
    parser.add_argument("--real-data-closed-loop", type=Path)
    parser.add_argument("--objective-audit", type=Path)
    parser.add_argument("--signoff-validation", type=Path)
    parser.add_argument("--preview-url")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument(
        "--require-business-uat-ready",
        action="store_true",
        help="Exit with status 2 unless the delivery evidence is ready for business UAT.",
    )
    parser.add_argument(
        "--require-production-signoff-ready",
        action="store_true",
        help="Exit with status 3 unless production sign-off readiness is explicitly satisfied.",
    )
    parser.add_argument(
        "--require-source-control-clean",
        action="store_true",
        help="Exit with status 4 unless source-control evidence has a branch, commit and clean worktree.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    status = _status(
        bundle_metadata=_load(args.bundle_metadata),
        manifest=_load(args.manifest),
        summary=_load(args.summary),
        preview_health=_load(args.preview_health),
        preview_module=_load(args.preview_module),
        real_data_closed_loop=_load(args.real_data_closed_loop),
        objective_audit=_load(args.objective_audit),
        signoff_validation=_load(args.signoff_validation),
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
    readiness = status.get("readiness_gates") or {}
    if (
        args.require_business_uat_ready
        and readiness.get("business_uat_ready") is not True
    ):
        blockers = readiness.get("business_uat_blockers") or []
        print(f"business UAT readiness gate failed: {blockers}")
        return 2
    if (
        args.require_production_signoff_ready
        and readiness.get("production_signoff_ready") is not True
    ):
        blockers = readiness.get("production_signoff_blockers") or []
        print(f"production sign-off readiness gate failed: {blockers}")
        return 3
    if (
        args.require_source_control_clean
        and readiness.get("source_control_clean") is not True
    ):
        blockers = readiness.get("source_control_blockers") or []
        print(f"source-control readiness gate failed: {blockers}")
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
