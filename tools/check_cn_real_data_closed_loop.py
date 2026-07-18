"""Inspect whether a China compliance database has real-data loop evidence."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = "sdoo.cn.real-data-closed-loop.v1"
MARKER = "SDOO_CN_REAL_DATA_CLOSED_LOOP_JSON="


def _shell_code(expected_version: str | None) -> str:
    return f"""
import json
from collections import Counter


def has_model(model_name):
    return model_name in env.registry


def count(model_name, domain=None):
    if not has_model(model_name):
        return None
    return env[model_name].sudo().search_count(domain or [])


def selection_count(model_name, field_name, domain=None):
    if not has_model(model_name):
        return {{}}
    model = env[model_name].sudo()
    if field_name not in model._fields:
        return {{}}
    values = model.search(domain or []).mapped(field_name)
    return dict(sorted(Counter(value or False for value in values).items()))


def first_last_dates(model_name, date_field, domain=None):
    if not has_model(model_name):
        return {{"first": None, "last": None}}
    model = env[model_name].sudo()
    if date_field not in model._fields:
        return {{"first": None, "last": None}}
    first = model.search(domain or [], order=date_field + " asc, id asc", limit=1)
    last = model.search(domain or [], order=date_field + " desc, id desc", limit=1)
    return {{
        "first": str(first[date_field]) if first and first[date_field] else None,
        "last": str(last[date_field]) if last and last[date_field] else None,
    }}


def country_id(code):
    country = env["res.country"].sudo().search([("code", "=", code)], limit=1)
    return country.id if country else False


def profile_domain():
    domain = []
    if has_model("sudo.compliance.profile"):
        Profile = env["sudo.compliance.profile"].sudo()
        if "country_id" in Profile._fields:
            cn_id = country_id("CN")
            if cn_id:
                domain.append(("country_id", "=", cn_id))
    return domain


def safe_field(record, field_name):
    if not record or field_name not in record._fields:
        return None
    value = record[field_name]
    if hasattr(value, "display_name"):
        return value.display_name
    return value


def sample_records(model_name, domain, order="id asc", limit=5):
    if not has_model(model_name):
        return []
    return env[model_name].sudo().search(domain or [], order=order, limit=limit)


module = env["ir.module.module"].sudo().search(
    [("name", "=", "sudo_country_pack_cn")], limit=1
)
pack = env.ref("sudo_country_pack_cn.compliance_country_pack_cn", raise_if_not_found=False)
profile_dom = profile_domain()
profile_ids = (
    env["sudo.compliance.profile"].sudo().search(profile_dom).ids
    if has_model("sudo.compliance.profile")
    else []
)
profile_status_domain = profile_dom
if has_model("sudo.compliance.profile") and "status" in env["sudo.compliance.profile"]._fields:
    profile_status_domain = profile_dom + [("status", "=", "active")]
active_profiles = (
    env["sudo.compliance.profile"].sudo().search(profile_status_domain)
    if has_model("sudo.compliance.profile")
    else env["res.company"].sudo().browse()
)
active_profile_ids = active_profiles.ids if has_model("sudo.compliance.profile") else []
active_profile_company_ids = active_profiles.mapped("company_id").ids if active_profiles else []
active_profiles_with_ledger = (
    active_profiles.filtered(
        lambda profile: count(
            "account.move",
            [
                ("company_id", "=", profile.company_id.id),
                ("state", "=", "posted"),
            ],
        )
        and count(
            "account.move.line",
            [
                ("company_id", "=", profile.company_id.id),
                ("move_id.state", "=", "posted"),
            ],
        )
    )
    if active_profiles
    else active_profiles
)
assessment_domain = [("profile_id", "in", profile_ids)] if profile_ids else []
finding_domain = [("assessment_id.profile_id", "in", profile_ids)] if profile_ids else []
posted_move_domain = [("state", "=", "posted")]
invoice_domain = posted_move_domain + [("move_type", "!=", "entry")]
active_profile_posted_move_domain = (
    posted_move_domain + [("company_id", "in", active_profile_company_ids)]
    if active_profile_company_ids
    else posted_move_domain + [("id", "=", 0)]
)
active_profile_assessment_domain = (
    [("profile_id", "in", active_profile_ids)] if active_profile_ids else [("id", "=", 0)]
)
active_profile_finding_domain = (
    [("assessment_id.profile_id", "in", active_profile_ids)]
    if active_profile_ids
    else [("id", "=", 0)]
)
active_profile_task_domain = (
    [("assessment_id.profile_id", "in", active_profile_ids)]
    if active_profile_ids
    else [("id", "=", 0)]
)
active_profile_report_domain = (
    [("assessment_id.profile_id", "in", active_profile_ids)]
    if active_profile_ids
    else [("id", "=", 0)]
)
active_profile_filing_domain = (
    [("profile_id", "in", active_profile_ids)]
    if active_profile_ids
    else [("id", "=", 0)]
)
active_profile_evidence_domain = (
    [("task_id.assessment_id.profile_id", "in", active_profile_ids)]
    if active_profile_ids
    else [("id", "=", 0)]
)
active_profile_evidence_sample_domain = (
    [
        "|",
        "|",
        "|",
        ("assessment_id.profile_id", "in", active_profile_ids),
        ("finding_id.assessment_id.profile_id", "in", active_profile_ids),
        ("task_id.assessment_id.profile_id", "in", active_profile_ids),
        ("filing_id.profile_id", "in", active_profile_ids),
    ]
    if active_profile_ids
    else [("id", "=", 0)]
)
active_profile_ai_domain = (
    [("finding_id.assessment_id.profile_id", "in", active_profile_ids)]
    if active_profile_ids
    else [("id", "=", 0)]
)

profiles = []
if has_model("sudo.compliance.profile"):
    for profile in env["sudo.compliance.profile"].sudo().search(
        profile_dom, order="id asc", limit=8
    ):
        profiles.append(
            {{
                "id": profile.id,
                "name": profile.display_name,
                "company": safe_field(profile, "company_id"),
                "status": safe_field(profile, "status"),
                "period_label": safe_field(profile, "cn_workbench_period_label"),
                "data_state": safe_field(profile, "cn_workbench_data_state"),
                "scan_state": safe_field(profile, "cn_workbench_scan_state"),
                "risk_state": safe_field(profile, "cn_workbench_risk_state"),
                "remediation_state": safe_field(profile, "cn_workbench_remediation_state"),
                "report_state": safe_field(profile, "cn_workbench_report_state"),
                "closed_loop_state": safe_field(profile, "cn_workbench_closed_loop_state"),
                "next_action_key": safe_field(profile, "cn_workbench_next_best_action_key"),
                "next_action": safe_field(profile, "cn_workbench_next_action"),
                "action_summary": safe_field(profile, "cn_workbench_action_summary"),
                "rule_basis_state": safe_field(profile, "cn_workbench_rule_basis_state"),
                "rule_basis_summary": safe_field(profile, "cn_workbench_rule_basis_summary"),
                "limitation_summary": safe_field(profile, "cn_workbench_limitation_summary"),
                "uncertainty_summary": safe_field(profile, "cn_workbench_uncertainty_summary"),
                "limitation_next_action": safe_field(profile, "cn_workbench_limitation_next_action"),
            }}
        )

sample_findings = []
for finding in sample_records(
    "sudo.compliance.finding",
    active_profile_finding_domain,
    order="risk_level desc, id asc",
    limit=8,
):
    task = safe_field(finding, "current_task_id")
    sample_findings.append(
        {{
            "id": finding.id,
            "name": safe_field(finding, "display_name"),
            "company": safe_field(finding, "company_id"),
            "assessment": safe_field(finding, "assessment_id"),
            "period_label": safe_field(finding, "cn_risk_period_label"),
            "risk_level": safe_field(finding, "risk_level"),
            "result": safe_field(finding, "result"),
            "review_state": safe_field(finding, "review_state"),
            "title": safe_field(finding, "title"),
            "reason": safe_field(finding, "message"),
            "action_summary": safe_field(finding, "cn_risk_action_summary"),
            "next_action": safe_field(finding, "cn_risk_next_action"),
            "tax_impact": safe_field(finding, "cn_tax_impact_summary"),
            "rule_basis_state": safe_field(finding, "cn_risk_rule_basis_state"),
            "rule_release_state": safe_field(finding, "cn_risk_rule_release_state"),
            "professional_state": safe_field(finding, "cn_risk_rule_professional_state"),
            "data_basis_state": safe_field(finding, "cn_risk_data_basis_state"),
            "evidence_state": safe_field(finding, "cn_risk_evidence_state"),
            "closure_state": safe_field(finding, "cn_closure_state"),
            "closure_summary": safe_field(finding, "cn_closure_summary"),
            "current_task": task.display_name if hasattr(task, "display_name") else None,
        }}
    )

sample_tasks = []
for task in sample_records(
    "sudo.compliance.task",
    active_profile_task_domain + [("task_type", "=", "remediation")],
    order="due_date asc, id asc",
    limit=8,
):
    sample_tasks.append(
        {{
            "id": task.id,
            "name": safe_field(task, "name"),
            "company": safe_field(task, "company_id"),
            "assessment": safe_field(task, "assessment_id"),
            "finding": safe_field(task, "finding_id"),
            "risk_level": safe_field(task, "risk_level"),
            "state": safe_field(task, "state"),
            "assignee": safe_field(task, "assignee_id"),
            "due_date": str(safe_field(task, "due_date") or ""),
            "verification_state": safe_field(task, "verification_state"),
            "verification_assessment": safe_field(task, "verification_assessment_id"),
            "action_summary": safe_field(task, "cn_remediation_action_summary"),
            "next_action": safe_field(task, "cn_remediation_next_action"),
            "responsibility_summary": safe_field(task, "cn_remediation_responsibility_summary"),
            "evidence_state": safe_field(task, "cn_remediation_evidence_state"),
            "traceability_state": safe_field(task, "cn_remediation_traceability_state"),
        }}
    )

sample_reports = []
for report in sample_records(
    "sudo.cn.compliance.report",
    active_profile_report_domain,
    order="id desc",
    limit=8,
):
    sample_reports.append(
        {{
            "id": report.id,
            "name": safe_field(report, "display_name"),
            "company": safe_field(report, "company_id"),
            "assessment": safe_field(report, "assessment_id"),
            "period_start": str(safe_field(report, "period_start") or ""),
            "period_end": str(safe_field(report, "period_end") or ""),
            "state": safe_field(report, "state"),
            "conclusion_state": safe_field(report, "conclusion_state"),
            "traceability_state": safe_field(report, "cn_report_traceability_state"),
            "traceability_next_action": safe_field(report, "cn_report_traceability_next_action"),
            "fact_basis_state": safe_field(report, "cn_report_fact_basis_state"),
            "center_integrity_state": safe_field(report, "cn_report_center_integrity_state"),
            "snapshot_integrity_state": safe_field(report, "snapshot_integrity_state"),
            "approval_integrity_state": safe_field(report, "approval_integrity_state"),
            "pdf_integrity_state": safe_field(report, "pdf_integrity_state"),
        }}
    )

sample_evidence = []
for evidence in sample_records(
    "sudo.compliance.evidence",
    active_profile_evidence_sample_domain,
    order="state desc, id asc",
    limit=8,
):
    sample_evidence.append(
        {{
            "id": evidence.id,
            "name": safe_field(evidence, "display_name"),
            "company": safe_field(evidence, "company_id"),
            "state": safe_field(evidence, "state"),
            "source_summary": safe_field(evidence, "cn_evidence_source_summary"),
            "blocker_summary": safe_field(evidence, "cn_evidence_blocker_summary"),
            "assessment": safe_field(evidence, "assessment_id"),
            "finding": safe_field(evidence, "finding_id"),
            "task": safe_field(evidence, "task_id"),
            "filing": safe_field(evidence, "filing_id"),
            "document_checksum": safe_field(evidence, "document_checksum"),
            "verified_by": safe_field(evidence, "verified_by_id"),
            "verified_at": str(safe_field(evidence, "verified_at") or ""),
        }}
    )

sample_filing_archives = []
for filing in sample_records(
    "sudo.compliance.filing",
    active_profile_filing_domain,
    order="period_end desc, id desc",
    limit=8,
):
    sample_filing_archives.append(
        {{
            "id": filing.id,
            "name": safe_field(filing, "display_name"),
            "company": safe_field(filing, "company_id"),
            "profile": safe_field(filing, "profile_id"),
            "kind": safe_field(filing, "cn_filing_center_kind"),
            "period_label": safe_field(filing, "cn_filing_center_period_label"),
            "period_start": str(safe_field(filing, "period_start") or ""),
            "period_end": str(safe_field(filing, "period_end") or ""),
            "state": safe_field(filing, "state"),
            "payment_state": safe_field(filing, "payment_state"),
            "due_date": str(safe_field(filing, "due_date") or ""),
            "submission_integrity_state": safe_field(filing, "cn_submission_integrity_state"),
            "payment_integrity_state": safe_field(filing, "cn_payment_integrity_state"),
            "evidence_state": safe_field(filing, "cn_filing_center_evidence_state"),
            "evidence_count": safe_field(filing, "cn_filing_center_evidence_count"),
            "verified_evidence_count": safe_field(filing, "cn_filing_center_verified_evidence_count"),
            "next_action": safe_field(filing, "cn_filing_center_next_action"),
            "blocker_summary": safe_field(filing, "cn_filing_center_blocker_summary"),
            "submission_checksum": safe_field(filing, "cn_submission_checksum"),
            "payment_checksum": safe_field(filing, "cn_payment_checksum"),
        }}
    )

sample_ai_guidance = []
for analysis in sample_records(
    "sudo.compliance.ai.analysis",
    active_profile_ai_domain,
    order="id desc",
    limit=8,
):
    sample_ai_guidance.append(
        {{
            "id": analysis.id,
            "name": safe_field(analysis, "display_name"),
            "finding": safe_field(analysis, "finding_id"),
            "provider_key": safe_field(analysis, "provider_key"),
            "jurisdiction_code": safe_field(analysis, "jurisdiction_code"),
            "state": safe_field(analysis, "state"),
            "prompt_version": safe_field(analysis, "prompt_version"),
            "model_name": safe_field(analysis, "model_name"),
            "input_checksum": safe_field(analysis, "input_checksum"),
            "output_checksum": safe_field(analysis, "output_checksum"),
            "record_checksum": safe_field(analysis, "record_checksum"),
            "source_warning": safe_field(analysis, "source_warning"),
            "professional_warning": safe_field(analysis, "professional_warning"),
        }}
    )

objects = {{
    "cn_profiles": count("sudo.compliance.profile", profile_dom),
    "active_cn_profiles": count("sudo.compliance.profile", profile_status_domain),
    "active_cn_profiles_with_ledger": len(active_profiles_with_ledger),
    "assessments": count("sudo.compliance.assessment", assessment_domain),
    "findings": count("sudo.compliance.finding", finding_domain),
    "remediation_tasks": count("sudo.compliance.task", [("task_type", "=", "remediation")]) if has_model("sudo.compliance.task") else None,
    "formal_reports": count("sudo.cn.compliance.report"),
    "active_profile_assessments": count("sudo.compliance.assessment", active_profile_assessment_domain),
    "active_profile_findings": count("sudo.compliance.finding", active_profile_finding_domain),
    "active_profile_remediation_tasks": count(
        "sudo.compliance.task",
        active_profile_task_domain + [("task_type", "=", "remediation")],
    ) if has_model("sudo.compliance.task") else None,
    "active_profile_verified_remediation_tasks": count(
        "sudo.compliance.task",
        active_profile_task_domain
        + [
            ("task_type", "=", "remediation"),
            ("state", "=", "done"),
            ("verification_state", "=", "verified"),
        ],
    ) if has_model("sudo.compliance.task") else None,
    "active_profile_formal_reports": count("sudo.cn.compliance.report", active_profile_report_domain),
    "active_profile_filing_archives": count("sudo.compliance.filing", active_profile_filing_domain),
    "evidence": count("sudo.compliance.evidence"),
    "active_profile_evidence": count("sudo.compliance.evidence", active_profile_evidence_domain),
    "active_profile_verified_evidence": count(
        "sudo.compliance.evidence",
        active_profile_evidence_domain + [("state", "=", "verified")],
    ) if has_model("sudo.compliance.evidence") and "state" in env["sudo.compliance.evidence"]._fields else None,
    "filing_archives": count("sudo.compliance.filing"),
    "external_datasets": count("sudo.cn.external.dataset"),
    "einvoice_documents": count("sudo.cn.einvoice.document"),
    "vat_filing_records": count("sudo.cn.vat.filing.record"),
    "cit_filing_records": count("sudo.cn.cit.filing.record"),
    "iit_withholding_records": count("sudo.cn.iit.withholding.record"),
    "tax_payment_records": count("sudo.cn.tax.payment.record"),
    "vat_reconciliation_runs": count("sudo.cn.vat.period.reconciliation.run"),
    "cit_reconciliation_runs": count("sudo.cn.cit.period.reconciliation.run"),
    "iit_reconciliation_runs": count("sudo.cn.iit.period.reconciliation.run"),
    "einvoice_reconciliation_runs": count("sudo.cn.einvoice.reconciliation.run"),
    "vat_reconciliation_issues": count("sudo.cn.vat.period.reconciliation.issue"),
    "cit_reconciliation_issues": count("sudo.cn.cit.period.reconciliation.issue"),
    "iit_reconciliation_issues": count("sudo.cn.iit.period.reconciliation.issue"),
    "active_profile_ai_guidance": count("sudo.compliance.ai.analysis", active_profile_ai_domain),
}}
objects["total_reconciliation_runs"] = sum(
    value or 0
    for key, value in objects.items()
    if key.endswith("_reconciliation_runs")
)
objects["total_reconciliation_issues"] = sum(
    value or 0
    for key, value in objects.items()
    if key.endswith("_reconciliation_issues")
)

accounting = {{
    "companies": count("res.company"),
    "partners": count("res.partner"),
    "posted_moves": count("account.move", posted_move_domain),
    "posted_invoices": count("account.move", invoice_domain),
    "posted_move_lines": count("account.move.line", [("move_id.state", "=", "posted")]),
    "posted_move_date_range": first_last_dates("account.move", "date", posted_move_domain),
    "active_profile_posted_moves": count("account.move", active_profile_posted_move_domain),
    "active_profile_posted_move_lines": count(
        "account.move.line",
        [("company_id", "in", active_profile_company_ids), ("move_id.state", "=", "posted")]
        if active_profile_company_ids
        else [("id", "=", 0)],
    ),
}}

readiness = {{
    "module_installed": bool(module and module.state == "installed"),
    "module_version_matches": bool(
        not {expected_version!r}
        or (module and module.installed_version == {expected_version!r})
    ),
    "country_pack_version_matches": bool(
        not {expected_version!r}
        or (pack and pack.version == {expected_version!r})
    ),
    "has_real_accounting_ledger": bool(
        (accounting.get("posted_moves") or 0) > 0
        and (accounting.get("posted_move_lines") or 0) > 0
    ),
    "has_china_profile": bool((objects.get("cn_profiles") or 0) > 0),
    "has_active_china_profile": bool((objects.get("active_cn_profiles") or 0) > 0),
    "has_active_china_profile_with_ledger": bool(
        (objects.get("active_cn_profiles_with_ledger") or 0) > 0
        and (accounting.get("active_profile_posted_moves") or 0) > 0
        and (accounting.get("active_profile_posted_move_lines") or 0) > 0
    ),
    "has_external_tax_or_invoice_data": bool(
        sum(
            objects.get(key) or 0
            for key in (
                "external_datasets",
                "einvoice_documents",
                "vat_filing_records",
                "cit_filing_records",
                "iit_withholding_records",
                "tax_payment_records",
            )
        )
        > 0
    ),
    "has_reconciliation_activity": bool((objects.get("total_reconciliation_runs") or 0) > 0),
    "has_risk_or_remediation_activity": bool(
        (objects.get("findings") or 0) > 0 or (objects.get("remediation_tasks") or 0) > 0
    ),
    "has_report_activity": bool((objects.get("formal_reports") or 0) > 0),
    "has_active_profile_risk_or_remediation_activity": bool(
        (objects.get("active_profile_findings") or 0) > 0
        or (objects.get("active_profile_remediation_tasks") or 0) > 0
    ),
    "has_active_profile_report_activity": bool(
        (objects.get("active_profile_formal_reports") or 0) > 0
    ),
    "has_active_profile_verified_remediation": bool(
        (objects.get("active_profile_verified_remediation_tasks") or 0) > 0
    ),
    "has_active_profile_verified_evidence": bool(
        (objects.get("active_profile_verified_evidence") or 0) > 0
    ),
    "has_workbench_summary_evidence": bool(
        any(
            profile.get("action_summary")
            and profile.get("rule_basis_summary")
            and profile.get("limitation_summary")
            and profile.get("uncertainty_summary")
            for profile in profiles
            if profile.get("status") == "active"
        )
    ),
    "has_risk_task_report_summary_evidence": bool(
        any(
            finding.get("risk_level") and finding.get("action_summary")
            for finding in sample_findings
        )
        and any(
            task.get("state")
            and task.get("verification_state")
            and task.get("action_summary")
            for task in sample_tasks
        )
        and any(
            report.get("state")
            and (
                report.get("conclusion_state")
                or report.get("traceability_next_action")
            )
            for report in sample_reports
        )
    ),
    "has_evidence_filing_payment_summary_evidence": bool(
        any(
            evidence.get("state") == "verified"
            and evidence.get("source_summary")
            and evidence.get("blocker_summary")
            and evidence.get("document_checksum")
            for evidence in sample_evidence
        )
        and any(
            filing.get("state")
            and filing.get("payment_state")
            and filing.get("submission_integrity_state")
            and filing.get("payment_integrity_state")
            and filing.get("evidence_state") == "verified"
            and filing.get("next_action")
            for filing in sample_filing_archives
        )
    ),
    "has_controlled_ai_guidance_evidence": bool(
        any(
            guidance.get("provider_key") == "sdoo_cn_controlled_guidance"
            and guidance.get("jurisdiction_code") == "CN"
            and guidance.get("prompt_version") == "cn-compliance-guidance-v1"
            and guidance.get("state")
            and guidance.get("input_checksum")
            and guidance.get("output_checksum")
            and guidance.get("record_checksum")
            for guidance in sample_ai_guidance
        )
    ),
}}
readiness["setup_demo_ready"] = all(
    readiness[key]
    for key in (
        "module_installed",
        "module_version_matches",
        "country_pack_version_matches",
        "has_real_accounting_ledger",
        "has_china_profile",
    )
)
readiness["demo_ready"] = all(
    readiness[key]
    for key in (
        "setup_demo_ready",
        "has_active_china_profile",
        "has_active_china_profile_with_ledger",
    )
)
readiness["closed_loop_evidence_ready"] = all(
    readiness[key]
    for key in (
        "demo_ready",
        "has_external_tax_or_invoice_data",
        "has_reconciliation_activity",
        "has_active_profile_risk_or_remediation_activity",
        "has_active_profile_verified_remediation",
        "has_active_profile_verified_evidence",
        "has_active_profile_report_activity",
        "has_workbench_summary_evidence",
        "has_risk_task_report_summary_evidence",
        "has_evidence_filing_payment_summary_evidence",
        "has_controlled_ai_guidance_evidence",
    )
)

payload = {{
    "schema": "{SCHEMA}",
    "expected_version": {expected_version!r},
    "module": {{
        "found": bool(module),
        "state": module.state if module else None,
        "installed_version": module.installed_version if module else None,
    }},
    "country_pack": {{
        "found": bool(pack),
        "code": pack.code if pack else None,
        "version": pack.version if pack else None,
    }},
    "accounting": accounting,
    "objects": objects,
    "states": {{
        "profile_status": selection_count("sudo.compliance.profile", "status", profile_dom),
        "assessment_state": selection_count("sudo.compliance.assessment", "state", assessment_domain),
        "finding_result": selection_count("sudo.compliance.finding", "result", finding_domain),
        "task_state": selection_count("sudo.compliance.task", "state"),
        "report_state": selection_count("sudo.cn.compliance.report", "state"),
        "external_dataset_state": selection_count("sudo.cn.external.dataset", "state"),
    }},
    "sample_profiles": profiles,
    "sample_findings": sample_findings,
    "sample_remediation_tasks": sample_tasks,
    "sample_reports": sample_reports,
    "sample_evidence": sample_evidence,
    "sample_filing_archives": sample_filing_archives,
    "sample_ai_guidance": sample_ai_guidance,
    "readiness": readiness,
    "ok": readiness["demo_ready"],
}}
print("{MARKER}" + json.dumps(payload, ensure_ascii=False, sort_keys=True))
"""


def _run_shell(args: argparse.Namespace) -> dict[str, object]:
    command = [
        str(args.python_bin),
        str(args.odoo_bin),
        "shell",
        "-c",
        str(args.config),
        "-d",
        args.database,
        "--no-http",
    ]
    result = subprocess.run(
        command,
        input=_shell_code(args.expected_version),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=args.timeout,
    )
    for line in result.stdout.splitlines():
        if line.startswith(MARKER):
            payload = json.loads(line.removeprefix(MARKER))
            payload["checked_at_utc"] = (
                datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            )
            payload["database"] = args.database
            payload["shell_returncode"] = result.returncode
            return payload
    return {
        "schema": SCHEMA,
        "checked_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "database": args.database,
        "expected_version": args.expected_version,
        "ok": False,
        "shell_returncode": result.returncode,
        "error": "real-data closed-loop marker was not found in Odoo shell output",
        "output_tail": result.stdout[-4000:],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check China compliance real-data closed-loop evidence in an Odoo database."
    )
    parser.add_argument("--python-bin", type=Path, required=True)
    parser.add_argument("--odoo-bin", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--expected-version")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--require-demo-ready", action="store_true")
    parser.add_argument("--require-closed-loop-evidence", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    payload = _run_shell(args)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")

    readiness = payload.get("readiness") or {}
    if args.require_closed_loop_evidence and readiness.get("closed_loop_evidence_ready") is not True:
        print(
            "real-data closed-loop evidence check failed: "
            f"{args.database} lacks full closed-loop evidence"
        )
        return 1
    if args.require_demo_ready and readiness.get("demo_ready") is not True:
        print(
            "real-data demo readiness check failed: "
            f"{args.database} lacks minimum demo evidence"
        )
        return 1
    if payload.get("ok") is True:
        print(f"real-data demo readiness check passed: {args.database}")
        return 0
    print(f"real-data demo readiness check completed with gaps: {args.database}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
