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


def has_text(value):
    return bool(value and str(value).strip())


def sample_records(model_name, domain, order="id asc", limit=5):
    if not has_model(model_name):
        return []
    return env[model_name].sudo().search(domain or [], order=order, limit=limit)


def view_field_contract(xml_id, required_fields):
    view = env.ref("sudo_country_pack_cn." + xml_id, raise_if_not_found=False)
    arch = str(view.arch_db or "") if view else ""
    missing = [
        field
        for field in required_fields
        if ('name="' + field + '"') not in arch and ("name='" + field + "'") not in arch
    ]
    return {{
        "xml_id": xml_id,
        "ready": bool(view and not missing),
        "missing": missing,
        "required_fields": required_fields,
    }}


def view_ux_contract(xml_id, required_fields, required_snippets):
    view = env.ref("sudo_country_pack_cn." + xml_id, raise_if_not_found=False)
    arch = str(view.arch_db or "") if view else ""
    missing_fields = [
        field
        for field in required_fields
        if ('name="' + field + '"') not in arch and ("name='" + field + "'") not in arch
    ]
    missing_snippets = [
        snippet
        for snippet in required_snippets
        if snippet not in arch
    ]
    return {{
        "xml_id": xml_id,
        "ready": bool(view and not missing_fields and not missing_snippets),
        "missing_fields": missing_fields,
        "missing_snippets": missing_snippets,
        "required_fields": required_fields,
        "required_snippets": required_snippets,
    }}


def menu_action_contract(menu_xml_id, action_xml_id, res_model, required_groups):
    menu = env.ref("sudo_country_pack_cn." + menu_xml_id, raise_if_not_found=False)
    action = env.ref("sudo_country_pack_cn." + action_xml_id, raise_if_not_found=False)
    menu_action = menu.action if menu else None
    menu_groups = menu.group_ids if menu else env["res.groups"]
    group_external_ids = menu_groups.get_external_id() if menu else {{}}
    groups = [
        group_external_ids.get(group.id) or group.display_name
        for group in menu_groups
    ]
    missing_groups = [
        group
        for group in required_groups
        if group not in groups
    ]
    action_matches = bool(
        action
        and getattr(action, "res_model", None) == res_model
        and menu_action
        and getattr(menu_action, "_name", "") == "ir.actions.act_window"
        and menu_action.id == action.id
    )
    return {{
        "menu_xml_id": menu_xml_id,
        "action_xml_id": action_xml_id,
        "res_model": res_model,
        "ready": bool(menu and action_matches and not missing_groups),
        "action_matches": action_matches,
        "missing_groups": missing_groups,
        "groups": groups,
    }}


def _domain_terms(domain):
    terms = []
    if isinstance(domain, (list, tuple)):
        if (
            len(domain) >= 3
            and isinstance(domain[0], str)
            and domain[0] not in ("|", "&", "!")
        ):
            terms.append(tuple(domain[:3]))
        else:
            for item in domain:
                terms.extend(_domain_terms(item))
    return terms


def _domain_has(domain, field_name, operator, value):
    return any(
        len(term) >= 3
        and term[0] == field_name
        and term[1] == operator
        and term[2] == value
        for term in _domain_terms(domain)
    )


def _domain_has_any(domain, expected_terms):
    return any(
        _domain_has(domain, field_name, operator, value)
        for field_name, operator, value in expected_terms
    )


def workbench_action_contract(method_name, res_model, expected_terms=None):
    profile = active_profiles[:1] if active_profiles else env["sudo.compliance.profile"]
    if not profile:
        return {{
            "method": method_name,
            "res_model": res_model,
            "ready": False,
            "error": "no active China compliance profile",
            "action_type": None,
            "scope_matches": False,
            "expected_terms": expected_terms or [],
        }}
    if not hasattr(profile, method_name):
        return {{
            "method": method_name,
            "res_model": res_model,
            "ready": False,
            "error": "method missing",
            "action_type": None,
            "scope_matches": False,
            "expected_terms": expected_terms or [],
        }}
    try:
        action = getattr(profile, method_name)()
    except Exception as exc:
        return {{
            "method": method_name,
            "res_model": res_model,
            "ready": False,
            "error": str(exc),
            "action_type": None,
            "scope_matches": False,
            "expected_terms": expected_terms or [],
        }}
    domain = action.get("domain") or []
    action_type = action.get("type")
    expected_terms = expected_terms or [("profile_id", "=", profile.id)]
    scope_matches = _domain_has_any(domain, expected_terms)
    return {{
        "method": method_name,
        "res_model": res_model,
        "ready": bool(
            action_type == "ir.actions.act_window"
            and action.get("res_model") == res_model
            and scope_matches
        ),
        "action_type": action_type,
        "action_res_model": action.get("res_model"),
        "view_mode": action.get("view_mode"),
        "scope_matches": scope_matches,
        "expected_terms": expected_terms,
        "domain": domain,
        "context": action.get("context") or {{}},
    }}


def company_rule_contract(model_name):
    model_record = env["ir.model"].sudo().search([("model", "=", model_name)], limit=1)
    rules = env["ir.rule"].sudo().search([("model_id", "=", model_record.id), ("active", "=", True)])
    matches = []
    for rule in rules:
        domain = str(rule.domain_force or "")
        group_external_ids = rule.groups.get_external_id()
        groups = [
            group_external_ids.get(group.id) or group.display_name
            for group in rule.groups
        ]
        if "company_id" in domain and "company_ids" in domain:
            matches.append(
                {{
                    "name": rule.name,
                    "domain": domain,
                    "groups": groups,
                }}
            )
    return {{
        "model": model_name,
        "ready": bool(model_record and matches),
        "rule_count": len(matches),
        "rules": matches,
    }}


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
active_profile_iit_reconciliation_domain = (
    [("profile_id", "in", active_profile_ids)]
    if active_profile_ids
    else [("id", "=", 0)]
)
active_profile_cross_border_domain = (
    [("profile_id", "in", active_profile_ids)]
    if active_profile_ids
    else [("id", "=", 0)]
)
cn_source_domain = (
    [("country_id.code", "=", "CN")]
    if has_model("sudo.compliance.authority.source")
    and "country_id" in env["sudo.compliance.authority.source"]._fields
    else [("id", "=", 0)]
)
cn_valid_source_domain = cn_source_domain + [("status", "=", "valid")]
cn_active_rule_domain = (
    [("rule_id.country_id.code", "=", "CN"), ("state", "=", "active")]
    if has_model("sudo.compliance.rule.version")
    and "rule_id" in env["sudo.compliance.rule.version"]._fields
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
            "reason": (
                safe_field(finding, "message")
                or safe_field(finding, "summary")
                or safe_field(finding, "recommendation")
                or safe_field(finding, "title")
            ),
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
            "evidence_count": safe_field(task, "cn_remediation_evidence_count"),
            "verified_evidence_count": safe_field(task, "cn_remediation_verified_evidence_count"),
            "rescan_stage": safe_field(task, "cn_remediation_rescan_stage"),
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
            "center_next_action": safe_field(report, "cn_report_center_next_action"),
            "blocker_summary": safe_field(report, "cn_report_blocker_summary"),
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

sample_authority_sources = []
for source in sample_records(
    "sudo.compliance.authority.source",
    cn_valid_source_domain,
    order="next_review_date desc, id desc",
    limit=8,
):
    sample_authority_sources.append(
        {{
            "id": source.id,
            "name": safe_field(source, "display_name"),
            "country": safe_field(source, "country_id"),
            "status": safe_field(source, "status"),
            "snapshot_kind": safe_field(source, "snapshot_kind"),
            "content_hash": safe_field(source, "content_hash"),
            "snapshot_attachment": safe_field(source, "snapshot_attachment_id"),
            "next_review_date": str(safe_field(source, "next_review_date") or ""),
            "monitor_enabled": safe_field(source, "cn_monitor_enabled"),
            "next_monitor_date": str(safe_field(source, "cn_next_monitor_date") or ""),
            "last_monitor_state": safe_field(source, "cn_last_monitor_state"),
            "latest_monitor_run": safe_field(source, "cn_latest_monitor_run_id"),
        }}
    )

sample_rule_versions = []
for version in sample_records(
    "sudo.compliance.rule.version",
    cn_active_rule_domain,
    order="next_review_date desc, id desc",
    limit=8,
):
    sample_rule_versions.append(
        {{
            "id": version.id,
            "name": safe_field(version, "display_name"),
            "rule": safe_field(version, "rule_id"),
            "version": safe_field(version, "version"),
            "state": safe_field(version, "state"),
            "release_state": safe_field(version, "cn_release_state"),
            "professional_review_state": safe_field(version, "professional_review_state"),
            "professional_ready": safe_field(version, "cn_professional_review_ready"),
            "professional_blockers": safe_field(version, "cn_professional_review_blockers"),
            "test_state": safe_field(version, "test_state"),
            "checksum": safe_field(version, "checksum"),
            "next_review_date": str(safe_field(version, "next_review_date") or ""),
            "source_count": len(version.authority_source_ids)
            if "authority_source_ids" in version._fields
            else 0,
            "source_names": version.authority_source_ids.mapped("display_name")
            if "authority_source_ids" in version._fields
            else [],
        }}
    )

sample_source_monitor_runs = []
for run in sample_records(
    "sudo.cn.authority.source.monitor.run",
    [],
    order="requested_at desc, id desc",
    limit=8,
):
    sample_source_monitor_runs.append(
        {{
            "id": run.id,
            "name": safe_field(run, "display_name"),
            "source": safe_field(run, "source_id"),
            "state": safe_field(run, "state"),
            "request_kind": safe_field(run, "request_kind"),
            "completed_at": str(safe_field(run, "completed_at") or ""),
            "result_integrity_state": safe_field(run, "result_integrity_state"),
            "source_snapshot_checksum": safe_field(run, "source_snapshot_checksum"),
            "impact_snapshot_checksum": safe_field(run, "impact_snapshot_checksum"),
            "result_checksum": safe_field(run, "result_checksum"),
            "result_summary": safe_field(run, "result_summary"),
        }}
    )

sample_iit_reconciliation_runs = []
for run in sample_records(
    "sudo.cn.iit.period.reconciliation.run",
    active_profile_iit_reconciliation_domain,
    order="period_end desc, id desc",
    limit=8,
):
    sample_iit_reconciliation_runs.append(
        {{
            "id": run.id,
            "name": safe_field(run, "display_name"),
            "company": safe_field(run, "company_id"),
            "profile": safe_field(run, "profile_id"),
            "period_start": str(safe_field(run, "period_start") or ""),
            "period_end": str(safe_field(run, "period_end") or ""),
            "state": safe_field(run, "state"),
            "conclusion_state": safe_field(run, "conclusion_state"),
            "result_summary": safe_field(run, "result_summary"),
            "accounting_source_state": safe_field(run, "accounting_source_state"),
            "payroll_source_state": safe_field(run, "payroll_source_state"),
            "filing_source_state": safe_field(run, "filing_source_state"),
            "payment_source_state": safe_field(run, "payment_source_state"),
            "payroll_record_count": safe_field(run, "payroll_record_count"),
            "filing_record_count": safe_field(run, "filing_record_count"),
            "payment_record_count": safe_field(run, "payment_record_count"),
            "payroll_person_count": safe_field(run, "payroll_person_count"),
            "payroll_gross_income_amount": safe_field(run, "payroll_gross_income_amount"),
            "payroll_withheld_iit_amount": safe_field(run, "payroll_withheld_iit_amount"),
            "issue_count": safe_field(run, "issue_count"),
            "blocking_issue_count": safe_field(run, "blocking_issue_count"),
            "difference_issue_count": safe_field(run, "difference_issue_count"),
            "result_integrity_state": safe_field(run, "result_integrity_state"),
            "result_checksum": safe_field(run, "result_checksum"),
            "payroll_snapshot_checksum": safe_field(run, "payroll_snapshot_checksum"),
            "filing_snapshot_checksum": safe_field(run, "filing_snapshot_checksum"),
            "payment_snapshot_checksum": safe_field(run, "payment_snapshot_checksum"),
        }}
    )

sample_cross_border_transactions = []
for transaction in sample_records(
    "sudo.cn.cross.border.transaction",
    active_profile_cross_border_domain,
    order="transaction_date desc, id desc",
    limit=8,
):
    sample_cross_border_transactions.append(
        {{
            "id": transaction.id,
            "name": safe_field(transaction, "display_name"),
            "company": safe_field(transaction, "company_id"),
            "profile": safe_field(transaction, "profile_id"),
            "period_start": str(safe_field(transaction, "period_start") or ""),
            "period_end": str(safe_field(transaction, "period_end") or ""),
            "transaction_date": str(safe_field(transaction, "transaction_date") or ""),
            "transaction_type": safe_field(transaction, "transaction_type"),
            "counterparty": safe_field(transaction, "counterparty_name"),
            "counterparty_country": safe_field(transaction, "counterparty_country_id"),
            "amount": safe_field(transaction, "amount"),
            "related_party": safe_field(transaction, "related_party"),
            "withholding_considered": safe_field(transaction, "withholding_considered"),
            "state": safe_field(transaction, "state"),
            "readiness_state": safe_field(transaction, "cn_cross_border_readiness_state"),
            "next_action": safe_field(transaction, "cn_cross_border_next_action"),
            "snapshot_checksum": safe_field(transaction, "snapshot_checksum"),
            "evidence_count": len(transaction.evidence_attachment_ids)
            if "evidence_attachment_ids" in transaction._fields
            else 0,
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
    "payroll_summary_records": count("sudo.cn.payroll.summary.record"),
    "tax_payment_records": count("sudo.cn.tax.payment.record"),
    "vat_reconciliation_runs": count("sudo.cn.vat.period.reconciliation.run"),
    "cit_reconciliation_runs": count("sudo.cn.cit.period.reconciliation.run"),
    "iit_reconciliation_runs": count("sudo.cn.iit.period.reconciliation.run"),
    "einvoice_reconciliation_runs": count("sudo.cn.einvoice.reconciliation.run"),
    "vat_reconciliation_issues": count("sudo.cn.vat.period.reconciliation.issue"),
    "cit_reconciliation_issues": count("sudo.cn.cit.period.reconciliation.issue"),
    "iit_reconciliation_issues": count("sudo.cn.iit.period.reconciliation.issue"),
    "active_profile_ai_guidance": count("sudo.compliance.ai.analysis", active_profile_ai_domain),
    "cn_authority_sources": count("sudo.compliance.authority.source", cn_source_domain),
    "cn_valid_authority_sources": count("sudo.compliance.authority.source", cn_valid_source_domain),
    "cn_active_rule_versions": count("sudo.compliance.rule.version", cn_active_rule_domain),
    "cn_source_monitor_runs": count("sudo.cn.authority.source.monitor.run"),
    "active_profile_iit_reconciliation_runs": count(
        "sudo.cn.iit.period.reconciliation.run",
        active_profile_iit_reconciliation_domain,
    ),
    "active_profile_cross_border_transactions": count(
        "sudo.cn.cross.border.transaction",
        active_profile_cross_border_domain,
    ),
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

reviewer_view_contracts = [
    view_field_contract(
        "view_cn_compliance_workbench_kanban",
        [
            "cn_workbench_next_action",
            "cn_workbench_action_summary",
            "cn_workbench_rule_basis_summary",
            "cn_workbench_limitation_summary",
            "cn_workbench_uncertainty_summary",
        ],
    ),
    view_field_contract(
        "view_cn_risk_center_finding_list",
        [
            "risk_level",
            "review_state",
            "cn_risk_period_label",
            "cn_risk_next_action",
            "cn_risk_action_summary",
            "cn_tax_impact_summary",
            "task_assignee_id",
            "task_due_date",
        ],
    ),
    view_field_contract(
        "view_cn_remediation_tracker_task_list",
        [
            "risk_level",
            "assignee_id",
            "due_date",
            "cn_remediation_next_action",
            "cn_remediation_action_summary",
            "state",
            "verification_state",
            "cn_remediation_evidence_state",
            "cn_remediation_rescan_stage",
        ],
    ),
    view_field_contract(
        "view_cn_report_readiness_kanban",
        [
            "cn_report_next_action",
            "cn_report_readiness_state",
            "cn_report_readiness_blocker_summary",
            "cn_report_limitation_count",
        ],
    ),
    view_field_contract(
        "view_cn_evidence_center_list",
        [
            "state",
            "cn_evidence_source_summary",
            "cn_evidence_blocker_summary",
            "document_checksum",
        ],
    ),
    view_field_contract(
        "view_cn_filing_center_kanban",
        [
            "state",
            "payment_state",
            "due_date",
            "cn_filing_center_next_action",
            "cn_filing_center_blocker_summary",
            "cn_filing_center_evidence_state",
        ],
    ),
]

ux_view_clarity_contracts = [
    view_ux_contract(
        "view_cn_compliance_workbench_kanban",
        [
            "cn_workbench_status",
            "cn_workbench_period_label",
            "cn_workbench_next_action",
            "cn_workbench_action_summary",
            "cn_workbench_high_risk_count",
            "cn_workbench_open_task_count",
            "cn_workbench_overdue_task_count",
            "cn_workbench_underpayment_amount",
            "cn_workbench_limitation_summary",
            "cn_workbench_uncertainty_summary",
        ],
        [
            'widget="badge"',
            "border-start border-4",
            "action_cn_open_workbench_next_best_action",
            "action_cn_open_workbench_findings",
            "action_cn_open_workbench_tasks",
            "action_cn_open_workbench_tax_impacts",
            "btn btn-primary",
        ],
    ),
    view_ux_contract(
        "view_cn_risk_center_finding_kanban",
        [
            "risk_level",
            "cn_risk_period_label",
            "cn_risk_next_action",
            "cn_risk_action_summary",
            "cn_tax_impact_reviewed_underpayment_amount",
            "task_assignee_id",
            "task_due_date",
            "cn_risk_evidence_state",
            "cn_traceability_state",
        ],
        [
            'widget="badge"',
            "border-start border-4",
            'decoration-danger="risk_level',
            "Tax impact",
            "cn_risk_responsibility_summary",
        ],
    ),
    view_ux_contract(
        "view_cn_remediation_tracker_task_kanban",
        [
            "risk_level",
            "assignee_id",
            "due_date",
            "cn_remediation_next_action",
            "cn_remediation_action_summary",
            "cn_remediation_blocker_summary",
            "cn_remediation_progress",
            "cn_remediation_evidence_state",
            "cn_remediation_rescan_stage",
            "cn_remediation_tax_impact_summary",
        ],
        [
            'widget="badge"',
            "border-start border-4",
            "Action summary",
            "Blockers",
            "Tax impact",
        ],
    ),
    view_ux_contract(
        "view_cn_report_readiness_kanban",
        [
            "cn_report_readiness_state",
            "cn_report_next_action",
            "cn_report_action_summary",
            "cn_report_readiness_blocker_summary",
            "cn_report_rescan_state",
            "cn_report_filing_archive_state",
            "cn_report_ai_guidance_state",
            "cn_data_basis_state",
            "cn_accounting_basis_state",
        ],
        [
            'widget="badge"',
            "border-start border-4",
            "Report Blockers",
            "Verification rescan gate",
            "Filing/payment archive gate",
            "Controlled AI guidance gate",
        ],
    ),
    view_ux_contract(
        "view_cn_formal_compliance_report_kanban",
        [
            "cn_report_center_stage",
            "cn_report_center_next_action",
            "cn_report_blocker_summary",
            "conclusion_state",
            "cn_report_traceability_state",
            "cn_report_fact_basis_state",
            "critical_count",
            "high_count",
            "open_task_count",
            "verified_evidence_count",
        ],
        [
            'widget="badge"',
            "border-start border-4",
            "Blockers",
            "Traceability",
            "Fact basis",
            "action_cn_open_report_findings",
        ],
    ),
]

menu_action_contracts = [
    menu_action_contract(
        "menu_cn_compliance_workbench",
        "action_cn_compliance_workbench",
        "sudo.compliance.profile",
        ["sudo_global_finance.group_compliance_user"],
    ),
    menu_action_contract(
        "menu_cn_risk_center",
        "action_cn_risk_center",
        "sudo.compliance.finding",
        ["sudo_global_finance.group_compliance_user"],
    ),
    menu_action_contract(
        "menu_cn_remediation_tracker",
        "action_cn_remediation_tracker",
        "sudo.compliance.task",
        ["sudo_global_finance.group_compliance_user"],
    ),
    menu_action_contract(
        "menu_cn_data_readiness_center",
        "action_cn_data_readiness_center",
        "sudo.cn.external.dataset",
        ["sudo_global_finance.group_compliance_user"],
    ),
    menu_action_contract(
        "menu_cn_evidence_center",
        "action_cn_evidence_center",
        "sudo.compliance.evidence",
        ["sudo_global_finance.group_compliance_user"],
    ),
    menu_action_contract(
        "menu_cn_filing_center",
        "action_cn_filing_center",
        "sudo.compliance.filing",
        ["sudo_global_finance.group_compliance_user"],
    ),
    menu_action_contract(
        "menu_cn_report_readiness",
        "action_cn_report_readiness",
        "sudo.compliance.assessment",
        ["sudo_global_finance.group_compliance_user"],
    ),
    menu_action_contract(
        "menu_cn_formal_compliance_reports",
        "action_cn_formal_compliance_reports",
        "sudo.cn.compliance.report",
        ["sudo_global_finance.group_compliance_user"],
    ),
]

active_profile = active_profiles[:1] if active_profiles else False
profile_scope = ("profile_id", "=", active_profile.id) if active_profile else ("profile_id", "=", False)
assessment_profile_scope = (
    "assessment_id.profile_id",
    "=",
    active_profile.id if active_profile else False,
)
company_scope = (
    "company_id",
    "=",
    active_profile.company_id.id if active_profile else False,
)

workbench_action_contracts = [
    workbench_action_contract(
        "action_cn_open_workbench_assessments",
        "sudo.compliance.assessment",
        [profile_scope],
    ),
    workbench_action_contract(
        "action_cn_open_workbench_data_readiness",
        "sudo.cn.external.dataset",
        [profile_scope],
    ),
    workbench_action_contract(
        "action_cn_open_workbench_obligations",
        "sudo.compliance.obligation",
        [profile_scope],
    ),
    workbench_action_contract(
        "action_cn_open_workbench_findings",
        "sudo.compliance.finding",
        [assessment_profile_scope],
    ),
    workbench_action_contract(
        "action_cn_open_workbench_tasks",
        "sudo.compliance.task",
        [assessment_profile_scope],
    ),
    workbench_action_contract(
        "action_cn_open_workbench_tax_impacts",
        "sudo.cn.tax.impact.case",
        [profile_scope],
    ),
    workbench_action_contract(
        "action_cn_open_workbench_evidence_center",
        "sudo.compliance.evidence",
        [
            company_scope,
            ("assessment_id.profile_id", "=", active_profile.id if active_profile else False),
            ("finding_id.assessment_id.profile_id", "=", active_profile.id if active_profile else False),
            ("task_id.assessment_id.profile_id", "=", active_profile.id if active_profile else False),
            ("filing_id.profile_id", "=", active_profile.id if active_profile else False),
        ],
    ),
    workbench_action_contract(
        "action_cn_open_workbench_filing_center",
        "sudo.compliance.filing",
        [profile_scope],
    ),
    workbench_action_contract(
        "action_cn_open_workbench_report_readiness",
        "sudo.compliance.assessment",
        [profile_scope],
    ),
    workbench_action_contract(
        "action_cn_open_workbench_reports",
        "sudo.cn.compliance.report",
        [profile_scope],
    ),
    workbench_action_contract(
        "action_cn_open_workbench_ai_guidance_findings",
        "sudo.compliance.finding",
        [assessment_profile_scope],
    ),
    workbench_action_contract(
        "action_cn_open_workbench_cross_border_transactions",
        "sudo.cn.cross.border.transaction",
        [profile_scope],
    ),
    workbench_action_contract(
        "action_cn_open_workbench_rule_basis",
        "sudo.compliance.rule.version",
        [("rule_id.country_id.code", "=", "CN")],
    ),
]

multi_company_security_contracts = [
    company_rule_contract(model_name)
    for model_name in (
        "sudo.cn.external.dataset",
        "sudo.cn.einvoice.document",
        "sudo.cn.tax.payment.record",
        "sudo.cn.vat.period.reconciliation.run",
        "sudo.cn.cit.period.reconciliation.run",
        "sudo.cn.iit.period.reconciliation.run",
        "sudo.cn.tax.impact.case",
        "sudo.cn.compliance.report",
        "sudo.cn.cross.border.transaction",
    )
]

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

risk_finding_visibility_evidence = bool(
    any(
        has_text(finding.get("period_label"))
        and has_text(finding.get("risk_level"))
        and has_text(finding.get("reason"))
        and has_text(finding.get("tax_impact"))
        and has_text(finding.get("evidence_state"))
        and has_text(finding.get("closure_state"))
        and has_text(finding.get("closure_summary"))
        and has_text(finding.get("next_action"))
        and has_text(finding.get("action_summary"))
        for finding in sample_findings
    )
)
remediation_task_visibility_evidence = bool(
    any(
        has_text(task.get("risk_level"))
        and has_text(task.get("state"))
        and has_text(task.get("assignee"))
        and has_text(task.get("due_date"))
        and has_text(task.get("verification_state"))
        and has_text(task.get("evidence_state"))
        and has_text(task.get("traceability_state"))
        and has_text(task.get("next_action"))
        and has_text(task.get("action_summary"))
        for task in sample_tasks
    )
)
remediation_verification_rescan_evidence = bool(
    any(
        task.get("state") == "done"
        and task.get("verification_state") in ("verified", "not_required")
        and has_text(task.get("verification_assessment"))
        and task.get("evidence_state") == "verified"
        and (task.get("verified_evidence_count") or 0) > 0
        and task.get("rescan_stage") in ("verified", "not_required")
        for task in sample_tasks
    )
)
official_source_freshness_evidence = bool(
    any(
        source.get("status") == "valid"
        and has_text(source.get("content_hash"))
        and has_text(source.get("snapshot_attachment"))
        and source.get("snapshot_kind") in ("official_document", "official_web_capture")
        and has_text(source.get("next_review_date"))
        for source in sample_authority_sources
    )
)
rule_professional_signoff_evidence = bool(
    any(
        version.get("state") == "active"
        and version.get("release_state") == "active"
        and version.get("professional_review_state") == "approved"
        and version.get("professional_ready") in (True, "True", "true", 1)
        and version.get("test_state") == "passed"
        and (version.get("source_count") or 0) > 0
        for version in sample_rule_versions
    )
)
rule_checksum_traceability_evidence = bool(
    any(
        has_text(version.get("checksum"))
        and has_text(version.get("next_review_date"))
        and (version.get("source_count") or 0) > 0
        for version in sample_rule_versions
    )
)
customer_data_scope_review_evidence = bool(
    (accounting.get("active_profile_posted_moves") or 0) > 0
    and (accounting.get("active_profile_posted_move_lines") or 0) > 0
    and any(
        profile.get("status") == "active"
        and has_text(profile.get("period_label"))
        and has_text(profile.get("data_state"))
        and has_text(profile.get("limitation_summary"))
        and has_text(profile.get("uncertainty_summary"))
        and has_text(profile.get("limitation_next_action"))
        for profile in profiles
    )
    and (objects.get("external_datasets") or 0) > 0
    and (objects.get("total_reconciliation_runs") or 0) > 0
)
customer_evidence_gap_review_evidence = bool(
    any(
        has_text(evidence.get("source_summary"))
        and has_text(evidence.get("blocker_summary"))
        and has_text(evidence.get("document_checksum"))
        and has_text(evidence.get("state"))
        for evidence in sample_evidence
    )
    and any(
        has_text(filing.get("blocker_summary"))
        and has_text(filing.get("next_action"))
        and has_text(filing.get("submission_integrity_state"))
        and has_text(filing.get("payment_integrity_state"))
        and has_text(filing.get("evidence_state"))
        for filing in sample_filing_archives
    )
)
open_high_risk_review_evidence = bool(
    any(
        finding.get("risk_level") in ("high", "critical")
        and has_text(finding.get("review_state"))
        and has_text(finding.get("closure_state"))
        and has_text(finding.get("closure_summary"))
        and has_text(finding.get("next_action"))
        and has_text(finding.get("action_summary"))
        for finding in sample_findings
    )
    and any(
        task.get("risk_level") in ("high", "critical")
        and has_text(task.get("state"))
        and has_text(task.get("verification_state"))
        and has_text(task.get("evidence_state"))
        and has_text(task.get("rescan_stage"))
        and has_text(task.get("action_summary"))
        for task in sample_tasks
    )
)
report_visibility_evidence = bool(
    any(
        has_text(report.get("period_start"))
        and has_text(report.get("period_end"))
        and has_text(report.get("state"))
        and has_text(report.get("traceability_state"))
        and has_text(report.get("fact_basis_state"))
        and (
            has_text(report.get("conclusion_state"))
            or (
                has_text(report.get("blocker_summary"))
                and (
                    has_text(report.get("traceability_next_action"))
                    or has_text(report.get("center_next_action"))
                )
            )
        )
        for report in sample_reports
    )
)

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
    "has_risk_finding_visibility_evidence": risk_finding_visibility_evidence,
    "has_remediation_task_visibility_evidence": remediation_task_visibility_evidence,
    "has_remediation_verification_rescan_evidence": remediation_verification_rescan_evidence,
    "has_report_visibility_evidence": report_visibility_evidence,
    "has_risk_task_report_summary_evidence": bool(
        risk_finding_visibility_evidence
        and remediation_task_visibility_evidence
        and report_visibility_evidence
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
    "has_official_source_freshness_evidence": official_source_freshness_evidence,
    "has_rule_professional_signoff_evidence": rule_professional_signoff_evidence,
    "has_rule_checksum_traceability_evidence": rule_checksum_traceability_evidence,
    "has_rule_source_governance_evidence": bool(
        official_source_freshness_evidence
        and rule_professional_signoff_evidence
        and rule_checksum_traceability_evidence
    ),
    "has_customer_data_scope_review_evidence": customer_data_scope_review_evidence,
    "has_customer_evidence_gap_review_evidence": customer_evidence_gap_review_evidence,
    "has_open_high_risk_review_evidence": open_high_risk_review_evidence,
    "has_customer_scope_gap_review_evidence": bool(
        customer_data_scope_review_evidence
        and customer_evidence_gap_review_evidence
        and open_high_risk_review_evidence
    ),
    "has_reviewer_view_contract_evidence": bool(
        reviewer_view_contracts
        and all(contract.get("ready") for contract in reviewer_view_contracts)
    ),
    "has_ux_view_clarity_contract_evidence": bool(
        ux_view_clarity_contracts
        and all(contract.get("ready") for contract in ux_view_clarity_contracts)
    ),
    "has_menu_action_contract_evidence": bool(
        menu_action_contracts
        and all(contract.get("ready") for contract in menu_action_contracts)
    ),
    "has_workbench_action_contract_evidence": bool(
        workbench_action_contracts
        and all(contract.get("ready") for contract in workbench_action_contracts)
    ),
    "has_multi_company_security_contract_evidence": bool(
        multi_company_security_contracts
        and all(contract.get("ready") for contract in multi_company_security_contracts)
    ),
    "has_iit_payroll_withholding_scope_evidence": bool(
        any(
            run.get("state") == "succeeded"
            and has_text(run.get("period_start"))
            and has_text(run.get("period_end"))
            and run.get("accounting_source_state") == "available"
            and run.get("payroll_source_state") == "available"
            and run.get("filing_source_state") == "available"
            and run.get("payment_source_state") == "available"
            and has_text(run.get("result_summary"))
            and has_text(run.get("result_checksum"))
            and run.get("result_integrity_state") == "verified"
            and (run.get("payroll_record_count") or 0) > 0
            and (run.get("filing_record_count") or 0) > 0
            and has_text(run.get("payroll_snapshot_checksum"))
            and has_text(run.get("filing_snapshot_checksum"))
            for run in sample_iit_reconciliation_runs
        )
    ),
    "has_cross_border_review_scope_evidence": bool(
        any(
            has_text(transaction.get("period_start"))
            and has_text(transaction.get("period_end"))
            and has_text(transaction.get("transaction_type"))
            and has_text(transaction.get("counterparty_country"))
            and transaction.get("withholding_considered") in (True, "True", "true", 1)
            and transaction.get("readiness_state") == "reviewed"
            and has_text(transaction.get("snapshot_checksum"))
            and (transaction.get("evidence_count") or 0) > 0
            for transaction in sample_cross_border_transactions
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
        "has_remediation_verification_rescan_evidence",
        "has_evidence_filing_payment_summary_evidence",
        "has_controlled_ai_guidance_evidence",
        "has_rule_source_governance_evidence",
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
    "sample_authority_sources": sample_authority_sources,
    "sample_rule_versions": sample_rule_versions,
    "sample_source_monitor_runs": sample_source_monitor_runs,
    "sample_iit_reconciliation_runs": sample_iit_reconciliation_runs,
    "sample_cross_border_transactions": sample_cross_border_transactions,
    "reviewer_view_contracts": reviewer_view_contracts,
    "ux_view_clarity_contracts": ux_view_clarity_contracts,
    "menu_action_contracts": menu_action_contracts,
    "workbench_action_contracts": workbench_action_contracts,
    "multi_company_security_contracts": multi_company_security_contracts,
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
