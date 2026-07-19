"""Prepare a controlled China compliance closed-loop walkthrough.

This tool is for development and UAT databases only.  It creates a clearly
marked CODEX-DEMO governed VAT reconciliation rule, runs the existing
reconciliation-to-assessment bridge, opens a remediation task, and prepares a
draft formal report so delivery checks can verify the visible closed-loop path.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = "sdoo.cn.demo-closed-loop-preparation.v1"
MARKER = "SDOO_CN_DEMO_CLOSED_LOOP_PREPARATION_JSON="


def _shell_code(company_name: str | None, allow_demo_data: bool) -> str:
    return f"""
import hashlib
import json
from datetime import date
from unittest.mock import patch

allow_demo_data = {allow_demo_data!r}
company_name = {company_name!r}


def command_set(ids):
    return [(6, 0, ids)]


def has_model(model_name):
    return model_name in env.registry


def pick_profile():
    Profile = env["sudo.compliance.profile"].sudo()
    cn = env["res.country"].sudo().search([("code", "=", "CN")], limit=1)
    domain = [("country_id", "=", cn.id), ("status", "=", "active")] if cn else [("status", "=", "active")]
    if company_name:
        exact = Profile.search(domain + [("company_id.name", "=", company_name)], limit=1)
        if exact:
            return exact
        partial = Profile.search(domain + [("company_id.name", "ilike", company_name)], limit=1)
        if partial:
            return partial
    Move = env["account.move"].sudo()
    profiles = Profile.search(domain, order="id asc")
    with_ledger = profiles.filtered(
        lambda profile: Move.search_count([
            ("company_id", "=", profile.company_id.id),
            ("state", "=", "posted"),
        ])
    )
    return (with_ledger or profiles)[:1]


def latest_or_create_vat_run(profile):
    Run = env["sudo.cn.vat.period.reconciliation.run"].with_company(profile.company_id)
    run = Run.sudo().search([
        ("profile_id", "=", profile.id),
        ("state", "=", "succeeded"),
    ], order="id desc", limit=20)
    if run:
        return run, False
    start = date(2026, 6, 1)
    end = date(2026, 6, 30)
    run = Run.enqueue(profile, start, end, "VAT")
    run._process()
    run.invalidate_recordset()
    return run, True


def attachment(name, raw):
    existing = env["ir.attachment"].sudo().search([("name", "=", name)], limit=1)
    if existing:
        return existing
    return env["ir.attachment"].sudo().create({{"name": name, "raw": raw}})


def demo_user(login, name, group_xmlids, company):
    User = env["res.users"].sudo()
    user = User.search([("login", "=", login)], limit=1)
    groups = env["res.groups"].sudo()
    for xmlid in group_xmlids:
        group = env.ref(xmlid, raise_if_not_found=False)
        if group:
            groups |= group
    values = {{
        "name": name,
        "login": login,
        "company_id": company.id,
        "company_ids": command_set(company.ids),
        "group_ids": command_set(groups.ids),
    }}
    if user:
        user.write({{
            "company_id": company.id,
            "company_ids": command_set(company.ids),
            "group_ids": [(4, group.id) for group in groups],
        }})
        return user
    return User.create(values)


def ensure_demo_rule(profile):
    author = demo_user(
        "codex_cn_demo_rule_author",
        "CODEX-DEMO China Rule Author",
        ["base.group_user", "sudo_global_finance.group_compliance_rule_author"],
        profile.company_id,
    )
    approver = demo_user(
        "codex_cn_demo_rule_approver",
        "CODEX-DEMO China Rule Approver",
        ["base.group_user", "sudo_global_finance.group_compliance_rule_approver"],
        profile.company_id,
    )
    professional = demo_user(
        "codex_cn_demo_professional_reviewer",
        "CODEX-DEMO China Professional Reviewer",
        ["base.group_user", "sudo_global_finance.group_compliance_professional_reviewer"],
        profile.company_id,
    )
    code = "CN-CODEX-DEMO-VAT-RECON-CLOSED-LOOP"
    Rule = env["sudo.compliance.rule"].with_user(author).with_company(profile.company_id)
    Version = env["sudo.compliance.rule.version"].with_user(author).with_company(profile.company_id)
    rule = Rule.search([("code", "=", code), ("country_id", "=", profile.country_id.id)], limit=1)
    if not rule:
        rule = Rule.create({{
            "name": "CODEX-DEMO 中国增值税四方勾稽闭环规则",
            "code": code,
            "country_id": profile.country_id.id,
            "domain_key": "CN.VAT.RECONCILIATION.DEMO",
            "cn_rule_nature": "data_readiness",
            "description": (
                "CODEX-DEMO ONLY: controlled development rule used to prove "
                "assessment, risk, remediation and report workflow wiring. "
                "It is not a production tax conclusion."
            ),
        }})
    version = Version.sudo().search([
        ("rule_id", "=", rule.id),
        ("version", "=", "CODEX-DEMO-2026.1"),
    ], limit=1)
    if version and version.state == "active":
        return rule, version, False

    fact_refs = [
        "fact_cn_vat_reconciliation_conclusion_state_v1",
        "fact_cn_vat_reconciliation_blocking_count_v1",
        "fact_cn_vat_reconciliation_difference_count_v1",
        "fact_cn_vat_reconciliation_detail_v1",
    ]
    facts = env["sudo.compliance.fact.definition"].sudo()
    for ref in fact_refs:
        record = env.ref("sudo_country_pack_cn." + ref, raise_if_not_found=False)
        if record:
            facts |= record
    demo_source_url = "https://example.invalid/codex-demo-cn-vat-recon"
    source = env["sudo.compliance.authority.source"].sudo().search([
        ("country_id", "=", profile.country_id.id),
        ("official_url", "=", demo_source_url),
    ], limit=1)
    if not source:
        source = env["sudo.compliance.authority.source"].with_user(author).create({{
            "name": "CODEX-DEMO 中国增值税闭环演示来源",
            "country_id": profile.country_id.id,
            "authority": "CODEX-DEMO 税务机关",
            "source_type": "tax_guide",
            "snapshot_kind": "official_web_capture",
            "official_url": demo_source_url,
            "next_review_date": "2027-07-15",
        }})
    if not getattr(source, "snapshot_attachment_id", False):
        source_attachment = attachment(
            "CODEX-DEMO-cn-vat-reconciliation-source.html",
            b"<html><body>CODEX DEMO ONLY - governed VAT reconciliation workflow source</body></html>",
        )
        source.with_user(author).write({{"snapshot_attachment_id": source_attachment.id}})
    if hasattr(source, "action_compute_hash") and not getattr(source, "content_hash", False):
        source.with_user(author).action_compute_hash()
    if getattr(source, "status", False) == "draft" and hasattr(source, "action_submit_review"):
        source.with_user(author).action_submit_review()
    if getattr(source, "status", False) == "pending_review" and hasattr(source, "action_approve"):
        source.with_user(approver).write({{
            "review_notes": (
                "CODEX-DEMO ONLY: source snapshot reviewed for controlled "
                "development workflow validation."
            )
        }})
        source.with_user(approver).action_approve()
    if not version:
        version = Version.create({{
            "rule_id": rule.id,
            "version": "CODEX-DEMO-2026.1",
            "effective_from": "2026-01-01",
            "next_review_date": "2027-07-15",
            "evaluator_type": "declarative",
            "condition_json": {{
                "all": [
                    {{
                        "fact": "cn.reconciliation.vat.conclusion_state",
                        "operator": "eq",
                        "value": "aligned",
                    }},
                    {{
                        "fact": "cn.reconciliation.vat.blocking_issue_count",
                        "operator": "eq",
                        "value": 0,
                    }},
                    {{
                        "fact": "cn.reconciliation.vat.difference_issue_count",
                        "operator": "eq",
                        "value": 0,
                    }},
                ]
            }},
            "match_result": "pass",
            "no_match_result": "fail",
            "risk_level": "high",
            "stale_policy": "block_all",
            "authority_source_ids": command_set(source.ids),
            "required_fact_ids": command_set(facts.ids),
            "legal_basis_summary": (
                "CODEX-DEMO ONLY: validates workflow wiring against controlled "
                "VAT reconciliation facts; replace with signed Chinese tax rule "
                "source before production."
            ),
            "failure_message": "VAT reconciliation is not aligned or has blocking data gaps.",
            "pass_message": "VAT reconciliation is aligned within the controlled scope.",
            "unknown_message": "VAT reconciliation facts are missing or stale.",
            "recommended_actions": (
                "Review missing tax invoice, filing and payment evidence; assign "
                "remediation and rescan the exact period."
            ),
            "evidence_required": (
                "VAT reconciliation run, issue list, source data snapshots, reviewer "
                "workpaper and remediation evidence."
            ),
            "requires_human_review": True,
        }})
    else:
        version.with_user(author).write({{
            "authority_source_ids": command_set(source.ids),
            "required_fact_ids": command_set(facts.ids),
        }})
    test_cases = env["sudo.compliance.rule.test.case"].sudo().search([
        ("rule_version_id", "=", version.id),
    ])
    if not test_cases:
        env["sudo.compliance.rule.test.case"].with_user(author).create([
            {{
                "name": "CODEX-DEMO VAT reconciliation aligned",
                "rule_version_id": version.id,
                "facts_json": {{
                    "cn.reconciliation.vat.conclusion_state": "aligned",
                    "cn.reconciliation.vat.blocking_issue_count": 0,
                    "cn.reconciliation.vat.difference_issue_count": 0,
                }},
                "evaluation_date": "2026-07-15",
                "expected_result": "pass",
            }},
            {{
                "name": "CODEX-DEMO VAT reconciliation blocked",
                "rule_version_id": version.id,
                "facts_json": {{
                    "cn.reconciliation.vat.conclusion_state": "insufficient_data",
                    "cn.reconciliation.vat.blocking_issue_count": 1,
                    "cn.reconciliation.vat.difference_issue_count": 0,
                }},
                "evaluation_date": "2026-07-15",
                "expected_result": "fail",
            }},
        ])
    packet = env["sudo.cn.rule.review.packet"].sudo().search([
        ("rule_version_id", "=", version.id),
    ], limit=1)
    if not packet:
        packet = env["sudo.cn.rule.review.packet"].with_user(author).create({{
            "rule_version_id": version.id,
            "scope_summary": (
                "CODEX-DEMO ONLY: validates the VAT reconciliation closed-loop "
                "workflow for a development database."
            ),
            "applicability_assumptions": (
                "The selected active China profile and its VAT reconciliation run "
                "are used solely as controlled UAT evidence."
            ),
            "exclusions_limitations": (
                "This is not a real Chinese tax rule, filing conclusion, legal "
                "opinion or professional advice."
            ),
            "conclusion_boundary": (
                "Failure only means the controlled VAT reconciliation facts are "
                "not aligned or complete enough for report reliance."
            ),
            "reviewer_questions": (
                "Confirm source snapshot, fact definitions, data limitations and "
                "remediation workflow visibility."
            ),
        }})
    citation = env["sudo.cn.rule.review.citation"].sudo().search([
        ("packet_id", "=", packet.id),
        ("source_id", "=", source.id),
    ], limit=1)
    if not citation:
        env["sudo.cn.rule.review.citation"].with_user(author).create({{
            "packet_id": packet.id,
            "source_id": source.id,
            "citation_type": "internal_control_rationale",
            "locator": "CODEX-DEMO workflow source snapshot",
            "claim_summary": (
                "The source supports controlled validation of the VAT "
                "reconciliation workflow in development only."
            ),
            "applicability_note": "Do not use as a production tax source.",
        }})
    if hasattr(version, "action_run_tests"):
        version.with_user(author).action_run_tests()
    evidence = b"CODEX DEMO ONLY - China VAT reconciliation closed-loop professional workpaper"
    version.with_user(professional).write({{
        "professional_qualification": "CODEX-DEMO 中国财税专业复核人",
        "professional_review_notes": (
            "CODEX-DEMO ONLY: confirms this rule is limited to development "
            "workflow validation and is not a real tax opinion."
        ),
        "professional_evidence_reference": "CODEX-DEMO/CN/VAT-CLOSED-LOOP",
        "professional_evidence_checksum": hashlib.sha256(evidence).hexdigest(),
    }})
    if hasattr(version, "action_professional_signoff") and version.state != "active":
        version.with_user(professional).action_professional_signoff()
    if hasattr(version, "action_submit_review") and version.state != "active":
        version.with_user(author).action_submit_review()
    if hasattr(version, "action_approve") and version.state != "active":
        version.with_user(approver).action_approve()
    if hasattr(version, "action_activate") and version.state != "active":
        version.with_user(approver).action_activate()
    version.invalidate_recordset()
    return rule, version, True


def ensure_source_monitor_run(version):
    source = version.authority_source_ids[:1]
    if not source:
        return None, False
    author = env["res.users"].sudo().search([
        ("login", "=", "codex_cn_demo_rule_author"),
    ], limit=1) or env.user
    changed = False
    if (
        not getattr(source, "cn_monitor_enabled", False)
        or not getattr(source, "cn_next_monitor_date", False)
        or getattr(source, "cn_monitor_interval_days", 0) != 30
    ):
        source.with_user(author).write({{
            "cn_monitor_enabled": True,
            "cn_monitor_interval_days": 30,
            "cn_next_monitor_date": "2026-07-15",
        }})
        changed = True
    Run = env["sudo.cn.authority.source.monitor.run"].sudo()
    existing = Run.search([
        ("source_id", "=", source.id),
        ("state", "in", ("unchanged", "changed", "failed")),
        ("result_checksum", "!=", False),
    ], order="requested_at desc, id desc", limit=8).filtered(
        lambda item: item.result_integrity_state == "verified"
    )[:1]
    if existing:
        return existing, changed
    run = Run.search([
        ("source_id", "=", source.id),
        ("state", "=", "queued"),
    ], order="requested_at desc, id desc", limit=1)
    if not run:
        run = env["sudo.cn.authority.source.monitor.run"].with_user(author).enqueue(
            source.with_user(author),
            request_kind="manual",
        )
        changed = True
    raw = source.snapshot_attachment_id.sudo().raw or b""
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    capture = {{
        "content": raw,
        "content_type": source.snapshot_attachment_id.mimetype or "text/html",
        "etag": '"codex-demo-source-monitor"',
        "final_url": source.official_url,
        "http_status": 200,
        "last_modified": "Wed, 15 Jul 2026 00:00:00 GMT",
    }}
    patch_target = (
        "odoo.addons.sudo_global_finance.models.authority_source."
        "SudoComplianceAuthoritySource._download_official_snapshot"
    )
    with patch(patch_target, return_value=capture):
        run.with_user(author).action_process_now()
    run.invalidate_recordset()
    return run, True


def ensure_assessment(run):
    candidates = env["sudo.compliance.assessment"].sudo().search([
        ("profile_id", "=", run.profile_id.id),
        ("period_start", "=", run.period_start),
        ("period_end", "=", run.period_end),
        ("finding_ids.rule_id.code", "=", "CN-CODEX-DEMO-VAT-RECON-CLOSED-LOOP"),
    ], order="id desc", limit=1)
    verification_ids = env["sudo.compliance.task"].sudo().search([
        ("assessment_id.profile_id", "=", run.profile_id.id),
        ("verification_assessment_id", "!=", False),
    ]).mapped("verification_assessment_id").ids
    existing = candidates.filtered(lambda item: item.id not in verification_ids)[:1]
    if existing:
        return existing, False
    action = run.action_queue_compliance_assessment()
    assessment = env["sudo.compliance.assessment"].sudo().browse(action["res_id"])
    assessment.action_run_now()
    assessment.invalidate_recordset()
    return assessment, True


def ensure_finding_task(assessment):
    finding = assessment.finding_ids.filtered(
        lambda item: item.rule_id.code == "CN-CODEX-DEMO-VAT-RECON-CLOSED-LOOP"
    )[:1]
    if not finding:
        finding = assessment.finding_ids[:1]
    def ensure_task_due_date(task):
        if not task or task.due_date:
            return False
        due = date(2026, 7, 31)
        try:
            task.write({{"due_date": due}})
        except Exception:
            env.cr.execute(
                "UPDATE sudo_compliance_task SET due_date = %s WHERE id = %s",
                (due, task.id),
            )
            task.invalidate_recordset(["due_date"])
        return True
    if finding and finding.result == "pass":
        verified_task = env["sudo.compliance.task"].sudo().search([
            ("assessment_id.profile_id", "=", assessment.profile_id.id),
            ("task_type", "=", "remediation"),
            ("state", "=", "done"),
            ("verification_state", "=", "verified"),
        ], order="id desc", limit=1)
        changed = ensure_task_due_date(verified_task)
        return finding, verified_task, changed
    task = env["sudo.compliance.task"].sudo().search([
        ("finding_id", "=", finding.id),
        ("task_type", "=", "remediation"),
    ], order="id desc", limit=1)
    changed = False
    if finding and finding.result == "fail":
        if not finding.review_notes:
            finding.write({{
                "review_notes": (
                    "CODEX-DEMO ONLY: reviewed the VAT reconciliation fact "
                    "snapshots and confirmed that missing external tax evidence "
                    "must be remediated before relying on the conclusion."
                )
            }})
        if finding.review_state not in ("correction_required", "confirmed"):
            finding.action_require_correction()
            changed = True
        if not task:
            action = finding.action_create_task()
            task = env["sudo.compliance.task"].sudo().browse(action["res_id"])
            changed = True
        changed = ensure_task_due_date(task) or changed
    return finding, task, changed


def dataset_attachment(name, payload, mimetype="application/json"):
    raw = payload if isinstance(payload, bytes) else json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    existing = env["ir.attachment"].sudo().search([("name", "=", name)], limit=1)
    if existing:
        return existing
    return env["ir.attachment"].sudo().create({{
        "name": name,
        "raw": raw,
        "mimetype": mimetype,
    }})


def create_external_dataset(profile, dataset_type, suffix, attachment_record, record_count, data_format="json"):
    Dataset = env["sudo.cn.external.dataset"].with_company(profile.company_id)
    dataset = Dataset.sudo().search([
        ("profile_id", "=", profile.id),
        ("dataset_type", "=", dataset_type),
        ("source_reference", "=", "CODEX-DEMO/" + suffix),
    ], order="id desc", limit=1)
    if dataset:
        if dataset.replacement_ids:
            dataset = dataset.replacement_ids.sorted("id", reverse=True)[:1]
        elif dataset.state == "sealed" and not dataset.supersedes_id:
            action = dataset.action_create_replacement()
            dataset = Dataset.browse(action["res_id"])
        else:
            return dataset
    values = {{
        "profile_id": profile.id,
        "dataset_type": dataset_type,
        "period_start": "2026-06-01",
        "period_end": "2026-06-30",
        "coverage_scope": "full",
        "scope_note": (
            "CODEX-DEMO ONLY: controlled external tax data used to validate "
            "the remediation and verification-rescan workflow."
        ),
        "source_channel": "official_export",
        "source_system_name": "CODEX-DEMO controlled tax data source",
        "source_reference": "CODEX-DEMO/" + suffix,
        "source_generated_at": "2026-07-01 09:00:00",
        "data_format": data_format,
        "authorization_basis": (
            "CODEX-DEMO ONLY: simulated lawful acquisition basis for development UAT."
        ),
        "separation_exception_reason": (
            "CODEX-DEMO ONLY: one controlled automation user both acquires and "
            "seals this development dataset so the UAT workflow can be repeated."
        ),
        "acquired_at": "2026-07-01 10:00:00",
        "declared_record_count": record_count,
        "currency_id": profile.company_id.currency_id.id,
        "source_attachment_ids": command_set(attachment_record.ids),
        "authenticity_state": "not_applicable",
    }}
    if dataset:
        if dataset.state != "draft":
            return dataset
        dataset.write(values)
    else:
        dataset = Dataset.create(values)
    dataset.action_seal()
    return dataset


def accounting_document(suffix, amount):
    formatted = "%.2f" % float(amount or 0.0)
    return {{
        "voucher_number": "CODEX-DEMO-VOUCHER-" + suffix,
        "posting_date": "2026-06-30",
        "accounting_period": "2026-06",
        "summary": "CODEX-DEMO VAT reconciliation remediation entry",
        "entries": [
            {{
                "direction": "借方",
                "general_ledger_subject": "CODEX-DEMO debit subject",
                "amount": formatted,
            }},
            {{
                "direction": "贷方",
                "general_ledger_subject": "CODEX-DEMO credit subject",
                "amount": formatted,
            }},
        ],
    }}


def einvoice_payload(profile, suffix, tax_amount, direction):
    untaxed = 1000.0
    tax_amount = float(tax_amount or 0.0)
    total = untaxed + tax_amount
    company = profile.company_id
    taxpayer_id = company.partner_id.vat or "91310000CODEXDEMO01"
    if direction == "output":
        seller_name = company.name
        seller_tax_id = taxpayer_id
        entity_name = "CODEX-DEMO Customer"
        entity_tax_id = "91310000CODEXOUT01"
    else:
        seller_name = "CODEX-DEMO Supplier"
        seller_tax_id = "91310000CODEXIN01"
        entity_name = company.name
        entity_tax_id = taxpayer_id
    return {{
        "source_document_key": "CODEX-DEMO-vat-period-" + suffix + ".xml",
        "invoice_number": "CODEX-DEMO-VAT-INVOICE-" + suffix,
        "invoice_type_code": "VAT_CODEX_DEMO",
        "request_time": "2026-06-30 08:30:00",
        "seller_name": seller_name,
        "seller_tax_id": seller_tax_id,
        "accounting_entity_name": entity_name,
        "accounting_entity_tax_id": entity_tax_id,
        "currency_code": company.currency_id.name or "CNY",
        "untaxed_amount": "%.2f" % untaxed,
        "tax_amount": "%.2f" % tax_amount,
        "total_amount": "%.2f" % total,
        "is_red": False,
        "is_booked": True,
        "is_checked": True,
        "is_paid": False,
        "source_fact_count": 20,
        "source_fact_digest": "b" * 64,
        "accounting_documents": [accounting_document(suffix, total)],
    }}


def ensure_einvoice_documents(profile, source_run):
    suffix = "VAT-REMEDIATION-EINVOICE-%s" % source_run.id
    existing = env["sudo.cn.einvoice.document"].sudo().search_count([
        ("profile_id", "=", profile.id),
        ("source_document_key", "ilike", "CODEX-DEMO-vat-period-" + suffix),
    ])
    if existing:
        return False
    attachment_record = dataset_attachment(
        "CODEX-DEMO-vat-period-einvoice-%s.zip" % source_run.id,
        b"CODEX DEMO ONLY - controlled einvoice remediation input",
        "application/zip",
    )
    dataset = create_external_dataset(
        profile,
        "electronic_invoice",
        suffix,
        attachment_record,
        2,
        data_format="zip",
    )
    parse_run = env["sudo.cn.external.parse.run"].with_company(
        profile.company_id
    )._start_for_dataset(
        dataset,
        attachment_record,
        parser_key="mof_einvoice_xbrl",
        parser_version="CODEX-DEMO-2026.1",
        parser_distribution="CODEX-DEMO controlled parser contract",
        taxonomy_namespace="http://xbrl.mof.gov.cn/taxonomy/2023-12-31/einv",
        taxonomy_version="2023-12-31",
        taxonomy_checksum="a" * 64,
        taxonomy_source_reference="CODEX-DEMO-MOF-VAT",
    )
    payloads = [
        einvoice_payload(
            profile,
            "output-%s" % source_run.id,
            source_run.invoice_output_tax_amount,
            "output",
        ),
        einvoice_payload(
            profile,
            "input-%s" % source_run.id,
            source_run.invoice_input_tax_amount,
            "input",
        ),
    ]
    parse_run._record_success(
        payloads,
        observed_input_sha256=parse_run.input_sha256,
        source_fact_count=20 * len(payloads),
        warning_count=0,
        error_count=0,
        parser_log_checksum="c" * 64,
    )
    return True


def ensure_tax_records(profile, source_run, dataset_type):
    output_tax = float(source_run.invoice_output_tax_amount or 0.0)
    input_tax = float(source_run.invoice_input_tax_amount or 0.0)
    payable = max(output_tax - input_tax, 0.0)
    currency_code = profile.company_id.currency_id.name or "CNY"
    suffix = "%s-%s" % (dataset_type.upper(), source_run.id)
    record_key = "CODEX-DEMO-" + suffix
    model_name = (
        "sudo.cn.vat.filing.record"
        if dataset_type == "vat_filing"
        else "sudo.cn.tax.payment.record"
    )
    key_field = "source_record_key" if dataset_type == "vat_filing" else "source_record_key"
    if env[model_name].sudo().search_count([(key_field, "=", record_key)]):
        return False
    if dataset_type == "vat_filing":
        record = {{
            "source_record_key": record_key,
            "taxpayer_name": profile.company_id.name,
            "taxpayer_id": profile.company_id.partner_id.vat or "91310000CODEXDEMO01",
            "return_type_code": "VAT-GENERAL",
            "return_status": "accepted",
            "period_start": "2026-06-01",
            "period_end": "2026-06-30",
            "submitted_at": "2026-07-10T09:00:00+08:00",
            "submission_reference": "CODEX-DEMO-VAT-ACK-%s" % source_run.id,
            "revision_number": 0,
            "currency_code": currency_code,
            "output_tax_amount": "%.2f" % output_tax,
            "input_tax_amount": "%.2f" % input_tax,
            "tax_payable_amount": "%.2f" % payable,
            "lines": [
                {{
                    "line_code": "L01",
                    "line_name": "CODEX-DEMO output VAT",
                    "amount_type": "tax",
                    "current_amount": "%.2f" % output_tax,
                }}
            ],
        }}
    else:
        record = {{
            "source_record_key": record_key,
            "taxpayer_name": profile.company_id.name,
            "taxpayer_id": profile.company_id.partner_id.vat or "91310000CODEXDEMO01",
            "tax_type_code": "VAT",
            "period_start": "2026-06-01",
            "period_end": "2026-06-30",
            "payment_date": "2026-07-12",
            "payment_reference": "CODEX-DEMO-VAT-PAY-REF-%s" % source_run.id,
            "payment_status": "succeeded",
            "currency_code": currency_code,
            "amount": "%.2f" % payable,
            "principal_amount": "%.2f" % payable,
            "interest_amount": "0.00",
            "penalty_amount": "0.00",
            "payer_account_masked": "CODEX-DEMO ****1234",
            "receipt_reference": "CODEX-DEMO-VAT-PAY-ACK-%s" % source_run.id,
        }}
    contract = {{
        "schema": "sdoo.cn.tax-data.v1",
        "dataset_type": dataset_type,
        "source_schema": "CODEX-DEMO-" + dataset_type,
        "source_schema_version": "2026.1",
        "record_count": 1,
        "records": [record],
    }}
    attachment_record = dataset_attachment(
        "CODEX-DEMO-vat-period-%s-%s.json" % (dataset_type, source_run.id),
        contract,
    )
    dataset = create_external_dataset(
        profile,
        dataset_type,
        suffix,
        attachment_record,
        1,
    )
    parse_run = env["sudo.cn.tax.data.parse.run"].with_company(
        profile.company_id
    )._start_for_dataset(dataset, attachment_record)
    parse_run._process_json_attachment()
    return True


def ensure_aligned_replacement_run(profile, source_run):
    existing = env["sudo.cn.vat.period.reconciliation.run"].sudo().search([
        ("profile_id", "=", profile.id),
        ("period_start", "=", source_run.period_start),
        ("period_end", "=", source_run.period_end),
        ("state", "=", "succeeded"),
        ("conclusion_state", "=", "aligned"),
    ], order="id desc", limit=1)
    if existing:
        return existing, False
    changed = False
    changed = ensure_einvoice_documents(profile, source_run) or changed
    changed = ensure_tax_records(profile, source_run, "vat_filing") or changed
    changed = ensure_tax_records(profile, source_run, "tax_payment") or changed
    changed = retire_stale_demo_datasets(
        profile,
        set((
            "CODEX-DEMO/VAT-REMEDIATION-EINVOICE-%s" % source_run.id,
            "CODEX-DEMO/VAT_FILING-%s" % source_run.id,
            "CODEX-DEMO/TAX_PAYMENT-%s" % source_run.id,
        )),
    ) or changed
    replacement = env["sudo.cn.vat.period.reconciliation.run"].with_company(
        profile.company_id
    ).enqueue(
        profile,
        source_run.period_start,
        source_run.period_end,
        source_run.vat_tax_type_code,
    )
    replacement._process()
    replacement.invalidate_recordset()
    return replacement, True or changed


def retire_stale_demo_datasets(profile, keep_references):
    Dataset = env["sudo.cn.external.dataset"].sudo()
    stale = Dataset.search([
        ("profile_id", "=", profile.id),
        ("source_reference", "like", "CODEX-DEMO/%"),
        ("period_start", "=", "2026-06-01"),
        ("period_end", "=", "2026-06-30"),
        ("state", "=", "sealed"),
    ])
    changed = False
    for dataset in stale:
        if dataset.source_reference in keep_references:
            continue
        if dataset.replacement_ids:
            continue
        action = dataset.action_create_replacement()
        replacement = Dataset.browse(action["res_id"])
        attachment_record = dataset_attachment(
            "CODEX-DEMO-retired-dataset-%s.txt" % dataset.id,
            b"CODEX DEMO ONLY - retired supersession placeholder",
            "text/plain",
        )
        replacement.write({{
            "period_start": "2000-01-01",
            "period_end": "2000-01-31",
            "source_reference": dataset.source_reference + "/RETIRED",
            "source_generated_at": "2000-02-01 09:00:00",
            "acquired_at": "2000-02-01 10:00:00",
            "declared_record_count": 1,
            "source_attachment_ids": command_set(attachment_record.ids),
            "scope_note": (
                "CODEX-DEMO ONLY: supersession placeholder that retires an "
                "earlier malformed demo dataset from the current 2026-06 VAT "
                "reconciliation period."
            ),
            "separation_exception_reason": (
                "CODEX-DEMO ONLY: one automation user retires malformed demo "
                "data so the UAT verification path remains repeatable."
            ),
        }})
        replacement.action_seal()
        changed = True
    return changed


def ensure_remediation_verification(profile, source_run, task):
    if not task:
        return {{
            "changed": False,
            "replacement_run": None,
            "verification_assessment": None,
            "evidence": None,
        }}
    changed = False
    if task.state in ("open", "in_progress", "waiting"):
        task.write({{
            "completion_notes": (
                "CODEX-DEMO ONLY: controlled external invoice, VAT filing and "
                "payment data were added; exact-period reconciliation will be "
                "rerun for verification."
            ),
            "external_evidence_reference": "CODEX-DEMO/CN/VAT-REMEDIATION/2026-06",
        }})
        task.action_done()
        task.invalidate_recordset()
        changed = True
    if not profile.company_id.partner_id.vat:
        profile.company_id.partner_id.write({{
            "vat": "91310000CODEXDEMO01",
        }})
        changed = True
    replacement_run, replacement_changed = ensure_aligned_replacement_run(
        profile,
        source_run,
    )
    changed = changed or replacement_changed
    if task.state == "blocked" and task.verification_state == "failed":
        task._transition_write({{
            "state": "pending_review",
            "verification_state": "pending_rescan",
            "verification_assessment_id": False,
        }})
        task.invalidate_recordset()
        changed = True
    verification = task.verification_assessment_id
    if not verification:
        action = task.action_queue_verification_scan()
        verification = env["sudo.compliance.assessment"].sudo().browse(action["res_id"])
        changed = True
    if verification.state != "completed":
        verification.action_run_now()
        verification.invalidate_recordset()
        changed = True
    evidence = env["sudo.compliance.evidence"].sudo().search([
        ("task_id", "=", task.id),
        ("external_reference", "=", "CODEX-DEMO/CN/VAT-REMEDIATION/VERIFIED-2026-06"),
    ], limit=1)
    if not evidence:
        evidence = env["sudo.compliance.evidence"].with_company(
            profile.company_id
        ).create({{
            "name": "CODEX-DEMO VAT remediation verification evidence",
            "company_id": profile.company_id.id,
            "task_id": task.id,
            "evidence_type": "remediation_proof",
            "external_reference": "CODEX-DEMO/CN/VAT-REMEDIATION/VERIFIED-2026-06",
            "evidence_date": "2026-07-12",
            "issuer": "CODEX-DEMO controlled evidence issuer",
        }})
        changed = True
    if getattr(evidence, "state", False) == "draft":
        evidence.action_submit()
        changed = True
    if getattr(evidence, "state", False) == "submitted":
        evidence.write({{
            "review_notes": (
                "CODEX-DEMO ONLY: replacement reconciliation, exact period, "
                "source scope and pass finding were checked for UAT."
            )
        }})
        evidence.action_verify()
        changed = True
    task.invalidate_recordset()
    if task.state == "pending_review" and task.verification_state != "verified":
        task.action_verify_remediation()
        task.invalidate_recordset()
        changed = True
    return {{
        "changed": changed,
        "replacement_run": replacement_run,
        "verification_assessment": task.verification_assessment_id,
        "evidence": evidence,
    }}


def verified_filing_evidence(profile, filing, suffix, evidence_type):
    evidence = env["sudo.compliance.evidence"].sudo().search([
        ("filing_id", "=", filing.id),
        ("evidence_type", "=", evidence_type),
        ("external_reference", "=", "CODEX-DEMO/CN/VAT-FILING-ARCHIVE/" + suffix),
    ], limit=1)
    changed = False
    if not evidence:
        evidence = env["sudo.compliance.evidence"].with_company(
            profile.company_id
        ).sudo().create({{
            "name": "CODEX-DEMO VAT filing/payment archive evidence " + suffix,
            "company_id": profile.company_id.id,
            "filing_id": filing.id,
            "evidence_type": evidence_type,
            "external_reference": "CODEX-DEMO/CN/VAT-FILING-ARCHIVE/" + suffix,
            "evidence_date": "2026-07-12",
            "issuer": "CODEX-DEMO controlled tax authority evidence issuer",
        }})
        changed = True
    if getattr(evidence, "state", False) == "draft":
        evidence.action_submit()
        changed = True
    if getattr(evidence, "state", False) == "submitted":
        evidence.write({{
            "review_notes": (
                "CODEX-DEMO ONLY: verified against the controlled VAT filing "
                "or payment source record before sealing the archive."
            )
        }})
        evidence.action_verify()
        changed = True
    return evidence, changed


def ensure_filing_archive(profile, run, source):
    if not run:
        return {{"filing": None, "changed": False, "error": "no VAT run"}}
    run.invalidate_recordset()
    filing = env["sudo.compliance.filing"].sudo().search([
        ("cn_vat_reconciliation_run_id", "=", run.id),
    ], limit=1)
    changed = False
    obligation = profile.obligation_ids.filtered(lambda item: item.code == "CN-VAT")[:1]
    if obligation and source:
        effective_from = obligation.effective_from
        if not effective_from or effective_from > run.period_start:
            effective_from = "2026-01-01"
        effective_to = obligation.effective_to
        if effective_to and effective_to < run.period_end:
            effective_to = False
        obligation.write({{
            "applicability": "applicable",
            "effective_from": effective_from,
            "effective_to": effective_to,
            "authority_source_id": source.id,
            "justification": (
                "CODEX-DEMO ONLY: VAT obligation confirmed for the controlled "
                "filing/payment archive walkthrough; not a production taxpayer conclusion."
            ),
        }})
    action = run.action_open_cn_filing_archive()
    defaults = {{
        key.removeprefix("default_"): value
        for key, value in action["context"].items()
        if key.startswith("default_")
    }}
    defaults.update({{
        "due_date": "2026-07-15",
        "authority_source_id": source.id if source else False,
        "due_date_basis": (
            "CODEX-DEMO ONLY: due date manually confirmed for the controlled "
            "VAT filing/payment archive walkthrough; do not use as production law."
        ),
    }})
    if not filing:
        filing = env["sudo.compliance.filing"].with_company(
            profile.company_id
        ).sudo().create(defaults)
        changed = True
    else:
        backfill_values = {{}}
        for field_name in (
            "due_date",
            "due_date_basis",
            "authority_source_id",
            "submission_date",
            "submission_reference",
            "payment_date",
            "payment_reference",
        ):
            if field_name in filing._fields and not filing[field_name] and defaults.get(field_name):
                backfill_values[field_name] = defaults[field_name]
        if backfill_values:
            filing.write(backfill_values)
            changed = True
            filing.invalidate_recordset()
    receipt, receipt_changed = verified_filing_evidence(
        profile,
        filing,
        "RECEIPT-%s" % run.id,
        "filing_receipt",
    )
    changed = changed or receipt_changed
    if filing.state == "draft":
        filing.action_prepare()
        changed = True
        filing.invalidate_recordset()
    if filing.state == "preparing":
        filing.action_ready()
        changed = True
        filing.invalidate_recordset()
    if filing.state == "ready":
        filing.action_submit()
        changed = True
    filing.invalidate_recordset()
    payment_evidence = None
    payment_needed = (
        filing.payment_required
        or filing.payment_state in ("pending", "not_paid", "partial")
        or filing.cn_payment_integrity_state == "unsealed"
    )
    if payment_needed:
        payment_evidence, payment_changed = verified_filing_evidence(
            profile,
            filing,
            "PAYMENT-%s" % run.id,
            "payment_proof",
        )
        changed = changed or payment_changed
        filing.invalidate_recordset()
        if filing.payment_state in ("pending", "not_paid", "partial"):
            filing.action_mark_paid()
            changed = True
    filing.invalidate_recordset()
    return {{
        "filing": filing,
        "changed": changed,
        "receipt_evidence": receipt,
        "payment_evidence": payment_evidence,
    }}


def ensure_account(company, code, name, account_type):
    Account = env["account.account"].sudo().with_company(company)
    account = Account.search([
        ("code", "=", code),
        ("company_ids", "in", company.ids),
    ], limit=1)
    if account:
        return account, False
    account = Account.create({{
        "name": name,
        "code": code,
        "account_type": account_type,
        "company_ids": command_set(company.ids),
    }})
    return account, True


def misc_journal(company):
    Journal = env["account.journal"].sudo().with_company(company)
    journal = Journal.search([
        ("company_id", "=", company.id),
        ("type", "=", "general"),
    ], limit=1)
    if journal:
        return journal, False
    journal = Journal.create({{
        "name": "CODEX-DEMO China Compliance Journal",
        "code": "CDCN",
        "type": "general",
        "company_id": company.id,
    }})
    return journal, True


def ensure_iit_accounting_scope(profile, accounts):
    Scope = env["sudo.cn.iit.accounting.scope"].sudo().with_company(profile.company_id)
    scope = Scope.search([
        ("profile_id", "=", profile.id),
        ("source_reference", "=", "CODEX-DEMO/CN/IIT-SCOPE/2026-06"),
    ], order="id desc", limit=1)
    changed = False
    if not scope:
        scope = Scope.create({{
            "profile_id": profile.id,
            "valid_from": "2026-01-01",
            "valid_to": "2026-12-31",
            "source_reference": "CODEX-DEMO/CN/IIT-SCOPE/2026-06",
            "payroll_source_schema": "CODEX-DEMO-payroll_summary",
            "payroll_source_schema_version": "2026.1",
            "iit_source_schema": "CODEX-DEMO-iit_withholding",
            "iit_source_schema_version": "2026.1",
            "payable_refundable_sign_convention": "positive_payable_negative_refundable",
            "scope_note": (
                "CODEX-DEMO ONLY: maps payroll expense, employee compensation "
                "payable and individual income tax payable accounts for the "
                "2026-06 controlled IIT walkthrough."
            ),
            "separation_exception_reason": (
                "CODEX-DEMO ONLY: development UAT automation creates and verifies "
                "this controlled IIT scope in one repeatable script; production "
                "must use independent preparer and reviewer users."
            ),
            "line_ids": [
                (0, 0, {{"account_id": accounts["payroll_expense"].id, "role": "payroll_expense"}}),
                (0, 0, {{"account_id": accounts["employee_payable"].id, "role": "employee_payable"}}),
                (0, 0, {{"account_id": accounts["iit_payable"].id, "role": "iit_payable"}}),
            ],
        }})
        changed = True
    elif not scope.separation_exception_reason:
        scope.write({{
            "separation_exception_reason": (
                "CODEX-DEMO ONLY: development UAT automation creates and verifies "
                "this controlled IIT scope in one repeatable script; production "
                "must use independent preparer and reviewer users."
            )
        }})
        changed = True
    if not scope.evidence_attachment_ids:
        evidence = attachment(
            "CODEX-DEMO-cn-iit-accounting-scope-2026-06.pdf",
            b"CODEX DEMO ONLY - China IIT accounting scope evidence",
        )
        evidence.sudo().write({{"res_model": scope._name, "res_id": scope.id}})
        scope.write({{"evidence_attachment_ids": command_set(evidence.ids)}})
        changed = True
    if hasattr(scope, "action_verify") and getattr(scope, "state", False) != "verified":
        scope.action_verify()
        changed = True
    return scope, changed


def ensure_iit_ledger(profile, accounts):
    company = profile.company_id
    journal, journal_changed = misc_journal(company)
    Move = env["account.move"].sudo().with_company(company)
    changed = journal_changed
    if not Move.search_count([
        ("company_id", "=", company.id),
        ("ref", "=", "CODEX-DEMO-CN-IIT-PAYROLL-ACCRUAL-2026-06"),
        ("state", "=", "posted"),
    ]):
        move = Move.create({{
            "move_type": "entry",
            "journal_id": journal.id,
            "date": "2026-06-30",
            "ref": "CODEX-DEMO-CN-IIT-PAYROLL-ACCRUAL-2026-06",
            "line_ids": [
                (0, 0, {{"name": "CODEX-DEMO payroll expense", "account_id": accounts["payroll_expense"].id, "debit": 10000.0}}),
                (0, 0, {{"name": "CODEX-DEMO employee compensation payable", "account_id": accounts["employee_payable"].id, "credit": 10000.0}}),
            ],
        }})
        move.action_post()
        changed = True
    if not Move.search_count([
        ("company_id", "=", company.id),
        ("ref", "=", "CODEX-DEMO-CN-IIT-WITHHOLDING-ACCRUAL-2026-06"),
        ("state", "=", "posted"),
    ]):
        move = Move.create({{
            "move_type": "entry",
            "journal_id": journal.id,
            "date": "2026-06-30",
            "ref": "CODEX-DEMO-CN-IIT-WITHHOLDING-ACCRUAL-2026-06",
            "line_ids": [
                (0, 0, {{"name": "CODEX-DEMO employee payable deduction", "account_id": accounts["employee_payable"].id, "debit": 90.0}}),
                (0, 0, {{"name": "CODEX-DEMO IIT payable accrual", "account_id": accounts["iit_payable"].id, "credit": 90.0}}),
            ],
        }})
        move.action_post()
        changed = True
    if not Move.search_count([
        ("company_id", "=", company.id),
        ("ref", "=", "CODEX-DEMO-CN-IIT-PAYMENT-SETTLEMENT-2026-06"),
        ("state", "=", "posted"),
    ]):
        move = Move.create({{
            "move_type": "entry",
            "journal_id": journal.id,
            "date": "2026-07-15",
            "ref": "CODEX-DEMO-CN-IIT-PAYMENT-SETTLEMENT-2026-06",
            "line_ids": [
                (0, 0, {{"name": "CODEX-DEMO IIT payable settlement", "account_id": accounts["iit_payable"].id, "debit": 90.0}}),
                (0, 0, {{"name": "CODEX-DEMO bank payment clearing", "account_id": accounts["clearing"].id, "credit": 90.0}}),
            ],
        }})
        move.action_post()
        changed = True
    return changed


def iit_payroll_record(profile):
    taxpayer_id = profile.company_id.partner_id.vat or "91310000CODEXDEMO01"
    return {{
        "source_record_key": "CODEX-DEMO-IIT-PAYROLL-2026-06",
        "taxpayer_name": profile.company_id.name,
        "taxpayer_id": taxpayer_id,
        "period_start": "2026-06-01",
        "period_end": "2026-06-30",
        "currency_code": profile.company_id.currency_id.name or "CNY",
        "payroll_frequency": "monthly",
        "payroll_status": "confirmed",
        "payroll_run_reference": "CODEX-DEMO-PAYROLL-RUN-2026-06",
        "approved_at": "2026-06-30T18:00:00+08:00",
        "declared_person_count": 1,
        "gross_income_amount": "10000.00",
        "tax_exempt_income_amount": "0.00",
        "employee_social_insurance_amount": "0.00",
        "employee_housing_fund_amount": "0.00",
        "other_pre_tax_deduction_amount": "0.00",
        "net_pay_amount": "9910.00",
        "withheld_iit_amount": "90.00",
    }}


def iit_withholding_record(profile):
    taxpayer_id = profile.company_id.partner_id.vat or "91310000CODEXDEMO01"
    return {{
        "source_record_key": "CODEX-DEMO-IIT-WITHHOLDING-2026-06",
        "taxpayer_name": profile.company_id.name,
        "taxpayer_id": taxpayer_id,
        "jurisdiction_code": "310000",
        "jurisdiction_name": "CODEX-DEMO China tax authority",
        "tax_year": 2026,
        "filing_frequency": "monthly",
        "return_type_code": "IIT-WITHHOLDING",
        "return_status": "accepted",
        "period_start": "2026-06-01",
        "period_end": "2026-06-30",
        "submitted_at": "2026-07-10T09:00:00+08:00",
        "submission_reference": "CODEX-DEMO-IIT-ACK-2026-06",
        "revision_number": 0,
        "currency_code": profile.company_id.currency_id.name or "CNY",
        "declared_person_count": 1,
        "declared_line_count": 1,
        "total_income_amount": "10000.00",
        "total_tax_exempt_income_amount": "0.00",
        "total_basic_deduction_amount": "5000.00",
        "total_special_deduction_amount": "1000.00",
        "total_special_additional_deduction_amount": "1000.00",
        "total_other_deduction_amount": "0.00",
        "total_donation_deduction_amount": "0.00",
        "total_taxable_income_amount": "3000.00",
        "total_tax_calculated_amount": "90.00",
        "total_tax_relief_amount": "0.00",
        "total_tax_paid_amount": "0.00",
        "total_payable_refundable_amount": "90.00",
        "lines": [
            {{
                "source_line_key": "opaque:" + "b" * 32,
                "subject_key": "hmac-sha256:" + "a" * 64,
                "residency_status": "resident",
                "income_type_code": "wages_salary",
                "current_income_amount": "10000.00",
                "current_tax_exempt_income_amount": "0.00",
                "current_basic_deduction_amount": "5000.00",
                "current_special_deduction_amount": "1000.00",
                "current_other_deduction_amount": "0.00",
                "taxable_income_amount": "3000.00",
                "tax_calculated_amount": "90.00",
                "tax_relief_amount": "0.00",
                "tax_paid_amount": "0.00",
                "payable_refundable_amount": "90.00",
            }}
        ],
    }}


def iit_payment_record(profile):
    taxpayer_id = profile.company_id.partner_id.vat or "91310000CODEXDEMO01"
    return {{
        "source_record_key": "CODEX-DEMO-IIT-PAYMENT-2026-06",
        "taxpayer_name": profile.company_id.name,
        "taxpayer_id": taxpayer_id,
        "tax_type_code": "IIT",
        "period_start": "2026-06-01",
        "period_end": "2026-06-30",
        "payment_date": "2026-07-15",
        "payment_reference": "CODEX-DEMO-IIT-PAY-REF-2026-06",
        "payment_status": "succeeded",
        "currency_code": profile.company_id.currency_id.name or "CNY",
        "amount": "90.00",
        "principal_amount": "90.00",
        "interest_amount": "0.00",
        "penalty_amount": "0.00",
        "receipt_reference": "CODEX-DEMO-IIT-PAY-ACK-2026-06",
    }}


def ensure_iit_tax_record(profile, dataset_type, record):
    model_by_type = {{
        "payroll_summary": "sudo.cn.payroll.summary.record",
        "iit_withholding": "sudo.cn.iit.withholding.record",
        "tax_payment": "sudo.cn.tax.payment.record",
    }}
    if env[model_by_type[dataset_type]].sudo().search_count([
        ("source_record_key", "=", record["source_record_key"]),
    ]):
        return False
    contract = {{
        "schema": "sdoo.cn.tax-data.v1",
        "dataset_type": dataset_type,
        "source_schema": "CODEX-DEMO-" + dataset_type,
        "source_schema_version": "2026.1",
        "record_count": 1,
        "records": [record],
    }}
    attachment_record = dataset_attachment(
        "CODEX-DEMO-iit-%s-2026-06.json" % dataset_type,
        contract,
    )
    dataset = create_external_dataset(
        profile,
        dataset_type,
        "IIT-" + dataset_type.upper() + "-2026-06",
        attachment_record,
        1,
    )
    parse_run = env["sudo.cn.tax.data.parse.run"].sudo().with_company(
        profile.company_id
    )._start_for_dataset(dataset, attachment_record)
    parse_run._process_json_attachment()
    return True


def ensure_iit_demo_scope(profile):
    payroll_expense, changed_expense = ensure_account(
        profile.company_id,
        "66029991",
        "CODEX-DEMO payroll expense",
        "expense",
    )
    employee_payable, changed_employee = ensure_account(
        profile.company_id,
        "22119991",
        "CODEX-DEMO employee compensation payable",
        "liability_current",
    )
    iit_payable, changed_iit = ensure_account(
        profile.company_id,
        "22219991",
        "CODEX-DEMO individual income tax payable",
        "liability_current",
    )
    clearing, changed_clearing = ensure_account(
        profile.company_id,
        "19999991",
        "CODEX-DEMO IIT payment clearing",
        "asset_current",
    )
    accounts = {{
        "payroll_expense": payroll_expense,
        "employee_payable": employee_payable,
        "iit_payable": iit_payable,
        "clearing": clearing,
    }}
    scope, changed_scope = ensure_iit_accounting_scope(profile, accounts)
    changed_ledger = ensure_iit_ledger(profile, accounts)
    changed_records = False
    changed_records = ensure_iit_tax_record(profile, "payroll_summary", iit_payroll_record(profile)) or changed_records
    changed_records = ensure_iit_tax_record(profile, "iit_withholding", iit_withholding_record(profile)) or changed_records
    changed_records = ensure_iit_tax_record(profile, "tax_payment", iit_payment_record(profile)) or changed_records
    existing = env["sudo.cn.iit.period.reconciliation.run"].sudo().search([
        ("profile_id", "=", profile.id),
        ("period_start", "=", "2026-06-01"),
        ("period_end", "=", "2026-06-30"),
        ("state", "=", "succeeded"),
        ("conclusion_state", "=", "aligned"),
    ], order="id desc", limit=1)
    if existing:
        return {{
            "run": existing,
            "scope": scope,
            "changed": bool(
                changed_expense or changed_employee or changed_iit or changed_clearing
                or changed_scope or changed_ledger or changed_records
            ),
        }}
    run = env["sudo.cn.iit.period.reconciliation.run"].sudo().with_company(
        profile.company_id
    ).enqueue(profile, "2026-06-01", "2026-06-30", "IIT")
    run._process()
    run.invalidate_recordset()
    return {{
        "run": run,
        "scope": scope,
        "changed": True,
    }}


def ensure_cross_border_demo_scope(profile):
    Transaction = env["sudo.cn.cross.border.transaction"].sudo().with_company(
        profile.company_id
    )
    transaction = Transaction.search([
        ("profile_id", "=", profile.id),
        ("contract_reference", "=", "CODEX-DEMO-CB-2026-06"),
    ], order="id desc", limit=1)
    changed = False
    us = env.ref("base.us", raise_if_not_found=False)
    if not us:
        us = env["res.country"].sudo().search([("code", "=", "US")], limit=1)
    if not transaction:
        evidence = attachment(
            "CODEX-DEMO-cn-cross-border-service-fee-2026-06.txt",
            b"CODEX DEMO ONLY - reviewed cross-border service fee contract, invoice and payment evidence",
        )
        transaction = Transaction.create({{
            "profile_id": profile.id,
            "period_start": "2026-06-01",
            "period_end": "2026-06-30",
            "transaction_date": "2026-06-18",
            "transaction_type": "service_fee",
            "counterparty_name": "CODEX-DEMO US Service Provider",
            "counterparty_country_id": us.id,
            "related_party": True,
            "contract_reference": "CODEX-DEMO-CB-2026-06",
            "payment_reference": "CODEX-DEMO-CB-PAY-2026-06",
            "service_or_asset_location": "United States",
            "currency_id": profile.company_id.currency_id.id,
            "amount": 12000.0,
            "withholding_considered": True,
            "withholding_note": (
                "CODEX-DEMO ONLY: withholding and treaty/source questions were "
                "considered for workflow visibility; this is not a production conclusion."
            ),
            "limitation_note": (
                "CODEX-DEMO ONLY: real contracts, invoices, payment bank slips "
                "and treaty analysis are required before production reliance."
            ),
            "evidence_attachment_ids": command_set(evidence.ids),
        }})
        changed = True
    if not transaction.evidence_attachment_ids:
        evidence = attachment(
            "CODEX-DEMO-cn-cross-border-service-fee-2026-06.txt",
            b"CODEX DEMO ONLY - reviewed cross-border service fee contract, invoice and payment evidence",
        )
        transaction.write({{"evidence_attachment_ids": command_set(evidence.ids)}})
        changed = True
    if transaction.state == "draft":
        transaction.action_submit()
        changed = True
    if transaction.state == "submitted":
        transaction.review_notes = (
            "CODEX-DEMO ONLY: manager reviewed withholding consideration, "
            "controlled evidence and limitation notes for UAT."
        )
        transaction.action_mark_reviewed()
        changed = True
    transaction.invalidate_recordset()
    return {{"transaction": transaction, "changed": changed}}


def ensure_cit_accounting_scope(profile):
    Scope = env["sudo.cn.cit.accounting.scope"].sudo().with_company(profile.company_id)
    scope = Scope.search([
        ("profile_id", "=", profile.id),
        ("source_reference", "=", "CODEX-DEMO/CN/CIT-SCOPE/2026-06"),
    ], order="id desc", limit=1)
    changed = False
    if not scope:
        scope = Scope.create({{
            "profile_id": profile.id,
            "valid_from": "2026-01-01",
            "valid_to": "2026-12-31",
            "source_reference": "CODEX-DEMO/CN/CIT-SCOPE/2026-06",
            "scope_note": (
                "CODEX-DEMO ONLY: controlled accounting profit scope for the "
                "2026-06 CIT walkthrough. It includes all current Odoo P&L "
                "accounts and therefore reflects the demo ledger state."
            ),
            "separation_exception_reason": (
                "CODEX-DEMO ONLY: development UAT automation creates and verifies "
                "this controlled CIT scope in one repeatable script; production "
                "must use independent preparer and reviewer users."
            ),
        }})
        changed = True
    elif not scope.separation_exception_reason:
        scope.write({{
            "separation_exception_reason": (
                "CODEX-DEMO ONLY: development UAT automation creates and verifies "
                "this controlled CIT scope in one repeatable script; production "
                "must use independent preparer and reviewer users."
            )
        }})
        changed = True
    if not scope.evidence_attachment_ids:
        evidence = attachment(
            "CODEX-DEMO-cn-cit-accounting-scope-2026-06.pdf",
            b"CODEX DEMO ONLY - China CIT accounting profit scope evidence",
        )
        evidence.sudo().write({{"res_model": scope._name, "res_id": scope.id}})
        scope.write({{"evidence_attachment_ids": command_set(evidence.ids)}})
        changed = True
    if scope.state == "draft":
        before = len(scope.line_ids)
        scope.action_populate_from_chart()
        scope.invalidate_recordset()
        changed = changed or len(scope.line_ids) != before
        scope.action_verify()
        changed = True
    return scope, changed


def ensure_cit_ledger(profile):
    company = profile.company_id
    revenue, changed_revenue = ensure_account(
        company,
        "60019991",
        "CODEX-DEMO CIT revenue",
        "income",
    )
    expense, changed_expense = ensure_account(
        company,
        "66029992",
        "CODEX-DEMO CIT expense",
        "expense",
    )
    clearing, changed_clearing = ensure_account(
        company,
        "19999992",
        "CODEX-DEMO CIT clearing",
        "asset_current",
    )
    journal, changed_journal = misc_journal(company)
    Move = env["account.move"].sudo().with_company(company)
    changed = changed_revenue or changed_expense or changed_clearing or changed_journal
    if not Move.search_count([
        ("company_id", "=", company.id),
        ("ref", "=", "CODEX-DEMO-CN-CIT-BOOK-PROFIT-2026-06"),
        ("state", "=", "posted"),
    ]):
        move = Move.create({{
            "move_type": "entry",
            "journal_id": journal.id,
            "date": "2026-06-30",
            "ref": "CODEX-DEMO-CN-CIT-BOOK-PROFIT-2026-06",
            "line_ids": [
                (0, 0, {{"name": "CODEX-DEMO CIT revenue counterparty", "account_id": clearing.id, "debit": 1000.0}}),
                (0, 0, {{"name": "CODEX-DEMO CIT revenue", "account_id": revenue.id, "credit": 1000.0}}),
                (0, 0, {{"name": "CODEX-DEMO CIT expense", "account_id": expense.id, "debit": 400.0}}),
                (0, 0, {{"name": "CODEX-DEMO CIT expense counterparty", "account_id": clearing.id, "credit": 400.0}}),
            ],
        }})
        move.action_post()
        changed = True
    return changed


def cit_accounting_profit_from_scope(profile, scope):
    company = profile.company_id
    MoveLine = env["account.move.line"].sudo().with_company(company)
    increase = 0.0
    decrease = 0.0
    for line in scope.line_ids:
        account = line.account_id
        totals = MoveLine.read_group(
            [
                ("company_id", "=", company.id),
                ("date", ">=", "2026-06-01"),
                ("date", "<=", "2026-06-30"),
                ("account_id", "=", account.id),
                ("parent_state", "=", "posted"),
            ],
            ["debit:sum", "credit:sum"],
            [],
        )
        debit = totals[0].get("debit") or 0.0 if totals else 0.0
        credit = totals[0].get("credit") or 0.0 if totals else 0.0
        if line.role == "profit_increase":
            increase += credit - debit
        else:
            decrease += debit - credit
    profit = company.currency_id.round(increase - decrease)
    return profit


def cit_filing_record(profile, accounting_profit):
    taxpayer_id = profile.company_id.partner_id.vat or "91310000CODEXDEMO01"
    adjustment_decrease = 50.0
    taxable_income = 650.0
    adjustment_increase = profile.company_id.currency_id.round(
        taxable_income - accounting_profit + adjustment_decrease
    )
    tax_payable = profile.company_id.currency_id.round(taxable_income * 0.25)
    prepaid = profile.company_id.currency_id.round(max(tax_payable - 12.5, 0.0))
    payable = profile.company_id.currency_id.round(tax_payable - prepaid)
    return {{
        "source_record_key": "CODEX-DEMO-CIT-FILING-2026-06",
        "taxpayer_name": profile.company_id.name,
        "taxpayer_id": taxpayer_id,
        "period_start": "2026-06-01",
        "period_end": "2026-06-30",
        "currency_code": profile.company_id.currency_id.name or "CNY",
        "tax_year": 2026,
        "return_period_type": "quarterly_prepayment",
        "return_type_code": "CIT-QUARTERLY",
        "return_status": "accepted",
        "submitted_at": "2026-07-12T09:00:00+08:00",
        "submission_reference": "CODEX-DEMO-CIT-ACK-2026-06",
        "revision_number": 0,
        "accounting_profit_amount": "%.2f" % accounting_profit,
        "adjustment_increase_amount": "%.2f" % adjustment_increase,
        "adjustment_decrease_amount": "%.2f" % adjustment_decrease,
        "taxable_income_amount": "%.2f" % taxable_income,
        "tax_payable_amount": "%.2f" % tax_payable,
        "tax_relief_amount": "0.00",
        "tax_credit_amount": "0.00",
        "prepaid_tax_amount": "%.2f" % prepaid,
        "payable_amount": "%.2f" % payable,
        "refundable_amount": "0.00",
        "lines": [],
    }}


def cit_payment_record(profile, amount=12.5):
    taxpayer_id = profile.company_id.partner_id.vat or "91310000CODEXDEMO01"
    return {{
        "source_record_key": "CODEX-DEMO-CIT-PAYMENT-2026-06",
        "taxpayer_name": profile.company_id.name,
        "taxpayer_id": taxpayer_id,
        "tax_type_code": "CIT",
        "period_start": "2026-06-01",
        "period_end": "2026-06-30",
        "payment_date": "2026-07-15",
        "payment_reference": "CODEX-DEMO-CIT-PAY-REF-2026-06",
        "payment_status": "succeeded",
        "currency_code": profile.company_id.currency_id.name or "CNY",
        "amount": "%.2f" % amount,
        "principal_amount": "%.2f" % amount,
        "interest_amount": "0.00",
        "penalty_amount": "0.00",
        "payer_account_masked": "CODEX-DEMO ****5678",
        "receipt_reference": "CODEX-DEMO-CIT-PAY-ACK-2026-06",
    }}


def ensure_cit_tax_record(profile, dataset_type, record):
    model_by_type = {{
        "cit_filing": "sudo.cn.cit.filing.record",
        "tax_payment": "sudo.cn.tax.payment.record",
    }}
    if env[model_by_type[dataset_type]].sudo().search_count([
        ("source_record_key", "=", record["source_record_key"]),
    ]):
        return False
    contract = {{
        "schema": "sdoo.cn.tax-data.v1",
        "dataset_type": dataset_type,
        "source_schema": "CODEX-DEMO-" + dataset_type,
        "source_schema_version": "2026.1",
        "record_count": 1,
        "records": [record],
    }}
    attachment_record = dataset_attachment(
        "CODEX-DEMO-cit-%s-2026-06.json" % dataset_type,
        contract,
    )
    dataset = create_external_dataset(
        profile,
        dataset_type,
        "CIT-" + dataset_type.upper() + "-2026-06",
        attachment_record,
        1,
    )
    parse_run = env["sudo.cn.tax.data.parse.run"].sudo().with_company(
        profile.company_id
    )._start_for_dataset(dataset, attachment_record)
    parse_run._process_json_attachment()
    return True


def ensure_cit_demo_scope(profile):
    changed_ledger = ensure_cit_ledger(profile)
    scope, changed_scope = ensure_cit_accounting_scope(profile)
    accounting_profit = cit_accounting_profit_from_scope(profile, scope)
    changed_records = False
    changed_records = ensure_cit_tax_record(
        profile,
        "cit_filing",
        cit_filing_record(profile, accounting_profit),
    ) or changed_records
    changed_records = ensure_cit_tax_record(
        profile,
        "tax_payment",
        cit_payment_record(profile),
    ) or changed_records
    existing = env["sudo.cn.cit.period.reconciliation.run"].sudo().search([
        ("profile_id", "=", profile.id),
        ("period_start", "=", "2026-06-01"),
        ("period_end", "=", "2026-06-30"),
        ("state", "=", "succeeded"),
        ("conclusion_state", "=", "aligned"),
    ], order="id desc", limit=1)
    if existing:
        return {{
            "run": existing,
            "scope": scope,
            "changed": bool(changed_ledger or changed_scope or changed_records),
        }}
    run = env["sudo.cn.cit.period.reconciliation.run"].sudo().with_company(
        profile.company_id
    ).enqueue(
        profile,
        "2026-06-01",
        "2026-06-30",
        "quarterly_prepayment",
        "CIT",
    )
    run._process()
    run.invalidate_recordset()
    return {{
        "run": run,
        "scope": scope,
        "changed": True,
    }}


def ensure_report(assessment):
    report = env["sudo.cn.compliance.report"].sudo().search([
        ("assessment_id", "=", assessment.id),
    ], order="id desc", limit=1)
    if report:
        return report, False
    report = env["sudo.cn.compliance.report"].with_company(assessment.company_id).sudo().create({{
        "title": "CODEX-DEMO 中国财税合规闭环报告",
        "assessment_id": assessment.id,
        "executive_summary": (
            "CODEX-DEMO ONLY: this draft report packages the controlled scan, "
            "risk finding, remediation task and evidence requirements for UAT."
        ),
        "scope_statement": (
            "Scope is limited to the selected China compliance profile, the VAT "
            "reconciliation period, Odoo ledger data and available controlled "
            "demo evidence."
        ),
        "limitation_statement": (
            "External invoice, filing and payment data are not fully connected in "
            "this development database. The report is a limited workflow artifact, "
            "not a production tax report."
        ),
        "management_response": (
            "Management should complete missing external evidence, review impact, "
            "execute remediation, and rescan the exact period before sign-off."
        ),
        "reviewer_id": env.user.id,
    }})
    return report, True


def ensure_ai_guidance(finding):
    if not finding:
        return {{"analysis": None, "changed": False}}
    if finding.result not in ("fail", "unknown", "error"):
        finding = env["sudo.compliance.finding"].sudo().search([
            ("assessment_id.profile_id", "=", finding.assessment_id.profile_id.id),
            ("result", "in", ("fail", "unknown", "error")),
        ], order="id desc", limit=1)
    if not finding:
        return {{"analysis": None, "changed": False}}
    analysis = env["sudo.compliance.ai.analysis"].sudo().search([
        ("finding_id", "=", finding.id),
        ("provider_key", "=", "sdoo_cn_controlled_guidance"),
    ], order="id desc", limit=1)
    if analysis:
        return {{"analysis": analysis, "changed": False}}
    action = finding.action_generate_cn_ai_guidance()
    analysis = env["sudo.compliance.ai.analysis"].sudo().browse(action.get("res_id"))
    return {{"analysis": analysis, "changed": True}}


payload = {{
    "schema": "{SCHEMA}",
    "ok": False,
    "changed": False,
    "allow_demo_data": allow_demo_data,
}}
if not allow_demo_data:
    payload["error"] = "pass --allow-demo-data to create controlled demo closed-loop records"
else:
    profile = pick_profile()
    if not profile:
        payload["error"] = "no active China compliance profile was found"
    elif profile.status != "active" or profile._activation_issues():
        payload["error"] = "selected profile is not active or has activation issues"
        payload["activation_issues"] = profile._activation_issues()
    else:
        run, created_run = latest_or_create_vat_run(profile)
        rule, version, changed_rule = ensure_demo_rule(profile)
        source_monitor_run, changed_source_monitor = ensure_source_monitor_run(version)
        assessment, created_assessment = ensure_assessment(run)
        finding, task, changed_task = ensure_finding_task(assessment)
        verification = ensure_remediation_verification(profile, run, task)
        archive_run = verification.get("replacement_run") or run
        archive = ensure_filing_archive(
            profile,
            archive_run,
            version.authority_source_ids[:1],
        )
        iit_scope = ensure_iit_demo_scope(profile)
        cross_border = ensure_cross_border_demo_scope(profile)
        cit_scope = ensure_cit_demo_scope(profile)
        report, created_report = ensure_report(assessment)
        ai_guidance = ensure_ai_guidance(finding)
        profile.invalidate_recordset()
        payload.update({{
            "ok": bool(
                assessment
                and finding
                and report
                and ai_guidance.get("analysis")
                and ai_guidance["analysis"].input_checksum
                and ai_guidance["analysis"].record_checksum
                and archive.get("filing")
                and archive["filing"].cn_submission_integrity_state == "verified"
                and archive["filing"].cn_filing_center_evidence_state == "verified"
                and (
                    not archive["filing"].payment_required
                    or archive["filing"].cn_payment_integrity_state == "verified"
                )
                and (
                    finding.result == "pass"
                    or (
                        task
                        and task.state == "done"
                        and task.verification_state == "verified"
                    )
                )
                and iit_scope.get("run")
                and iit_scope["run"].state == "succeeded"
                and iit_scope["run"].conclusion_state == "aligned"
                and iit_scope["run"].result_integrity_state == "verified"
                and cross_border.get("transaction")
                and cross_border["transaction"].state == "reviewed"
                and cross_border["transaction"].cn_cross_border_readiness_state == "reviewed"
                and cross_border["transaction"].snapshot_checksum
                and cit_scope.get("run")
                and cit_scope["run"].state == "succeeded"
                and cit_scope["run"].conclusion_state == "aligned"
                and cit_scope["run"].result_integrity_state == "verified"
                and source_monitor_run
                and source_monitor_run.state == "unchanged"
                and source_monitor_run.result_integrity_state == "verified"
            ),
            "changed": bool(
                created_run
                or changed_rule
                or changed_source_monitor
                or created_assessment
                or changed_task
                or verification.get("changed")
                or archive.get("changed")
                or iit_scope.get("changed")
                or cross_border.get("changed")
                or cit_scope.get("changed")
                or created_report
                or ai_guidance.get("changed")
            ),
            "profile": {{
                "id": profile.id,
                "name": profile.display_name,
                "company": profile.company_id.display_name,
                "status": profile.status,
            }},
            "vat_run": {{
                "id": run.id,
                "name": run.display_name,
                "state": run.state,
                "conclusion_state": run.conclusion_state,
                "issue_count": len(run.issue_ids),
                "blocking_issue_count": run.blocking_issue_count,
                "difference_issue_count": run.difference_issue_count,
            }},
            "rule_version": {{
                "id": version.id,
                "name": version.display_name,
                "state": version.state,
            }},
            "source_monitor_run": {{
                "id": source_monitor_run.id if source_monitor_run else False,
                "name": source_monitor_run.display_name if source_monitor_run else False,
                "state": source_monitor_run.state if source_monitor_run else False,
                "result_integrity_state": source_monitor_run.result_integrity_state if source_monitor_run else False,
                "source_snapshot_checksum": source_monitor_run.source_snapshot_checksum if source_monitor_run else False,
                "impact_snapshot_checksum": source_monitor_run.impact_snapshot_checksum if source_monitor_run else False,
                "result_checksum": source_monitor_run.result_checksum if source_monitor_run else False,
            }},
            "assessment": {{
                "id": assessment.id,
                "name": assessment.display_name,
                "state": assessment.state,
                "finding_count": len(assessment.finding_ids),
            }},
            "finding": {{
                "id": finding.id,
                "title": finding.display_name,
                "result": finding.result,
                "risk_level": finding.risk_level,
                "review_state": finding.review_state,
            }} if finding else None,
            "task": {{
                "id": task.id,
                "name": task.display_name,
                "state": task.state,
                "task_type": task.task_type,
                "verification_state": task.verification_state,
                "verification_assessment_id": (
                    task.verification_assessment_id.id or None
                ),
            }} if task else None,
            "verification": {{
                "replacement_run_id": (
                    verification["replacement_run"].id
                    if verification.get("replacement_run")
                    else None
                ),
                "replacement_run_conclusion": (
                    verification["replacement_run"].conclusion_state
                    if verification.get("replacement_run")
                    else None
                ),
                "assessment_id": (
                    verification["verification_assessment"].id
                    if verification.get("verification_assessment")
                    else None
                ),
                "assessment_state": (
                    verification["verification_assessment"].state
                    if verification.get("verification_assessment")
                    else None
                ),
                "finding_results": (
                    verification["verification_assessment"].finding_ids.mapped("result")
                    if verification.get("verification_assessment")
                    else []
                ),
                "evidence_id": (
                    verification["evidence"].id
                    if verification.get("evidence")
                    else None
                ),
                "evidence_state": (
                    verification["evidence"].state
                    if verification.get("evidence") and "state" in verification["evidence"]._fields
                    else None
                ),
            }},
            "report": {{
                "id": report.id,
                "name": report.display_name,
                "state": report.state,
                "conclusion_state": report.conclusion_state,
            }} if report else None,
            "ai_guidance": {{
                "id": ai_guidance["analysis"].id,
                "provider_key": ai_guidance["analysis"].provider_key,
                "state": ai_guidance["analysis"].state,
                "prompt_version": ai_guidance["analysis"].prompt_version,
                "model_name": ai_guidance["analysis"].model_name,
                "input_checksum": ai_guidance["analysis"].input_checksum,
                "output_checksum": ai_guidance["analysis"].output_checksum,
                "record_checksum": ai_guidance["analysis"].record_checksum,
            }} if ai_guidance.get("analysis") else None,
            "filing_archive": {{
                "id": archive["filing"].id,
                "name": archive["filing"].display_name,
                "state": archive["filing"].state,
                "payment_state": archive["filing"].payment_state,
                "submission_integrity_state": archive["filing"].cn_submission_integrity_state,
                "payment_integrity_state": archive["filing"].cn_payment_integrity_state,
                "evidence_state": archive["filing"].cn_filing_center_evidence_state,
            }} if archive.get("filing") else None,
            "iit_scope": {{
                "run_id": iit_scope["run"].id,
                "run_name": iit_scope["run"].display_name,
                "state": iit_scope["run"].state,
                "conclusion_state": iit_scope["run"].conclusion_state,
                "result_integrity_state": iit_scope["run"].result_integrity_state,
                "payroll_record_count": iit_scope["run"].payroll_record_count,
                "filing_record_count": iit_scope["run"].filing_record_count,
                "payment_record_count": iit_scope["run"].payment_record_count,
                "issue_count": iit_scope["run"].issue_count,
                "result_checksum": iit_scope["run"].result_checksum,
            }} if iit_scope.get("run") else None,
            "cross_border_scope": {{
                "transaction_id": cross_border["transaction"].id,
                "name": cross_border["transaction"].display_name,
                "state": cross_border["transaction"].state,
                "readiness_state": cross_border["transaction"].cn_cross_border_readiness_state,
                "withholding_considered": cross_border["transaction"].withholding_considered,
                "evidence_count": len(cross_border["transaction"].evidence_attachment_ids),
                "snapshot_checksum": cross_border["transaction"].snapshot_checksum,
            }} if cross_border.get("transaction") else None,
            "cit_scope": {{
                "run_id": cit_scope["run"].id,
                "run_name": cit_scope["run"].display_name,
                "state": cit_scope["run"].state,
                "conclusion_state": cit_scope["run"].conclusion_state,
                "result_integrity_state": cit_scope["run"].result_integrity_state,
                "filing_record_id": cit_scope["run"].filing_record_id.id or None,
                "payment_record_count": cit_scope["run"].payment_record_count,
                "issue_count": cit_scope["run"].issue_count,
                "blocking_issue_count": cit_scope["run"].blocking_issue_count,
                "difference_issue_count": cit_scope["run"].difference_issue_count,
                "warning_issue_count": cit_scope["run"].warning_issue_count,
                "issues": [
                    {{
                        "sequence": issue.sequence,
                        "code": issue.code,
                        "severity": issue.severity,
                        "issue_kind": issue.issue_kind,
                        "source_area": issue.source_area,
                        "description": issue.description,
                        "action_hint": issue.action_hint,
                        "affected_record_count": issue.affected_record_count,
                        "left_label": issue.left_label,
                        "left_amount": issue.left_amount,
                        "right_label": issue.right_label,
                        "right_amount": issue.right_amount,
                        "difference_amount": issue.difference_amount,
                    }}
                    for issue in cit_scope["run"].issue_ids.sorted("sequence")
                ],
                "result_checksum": cit_scope["run"].result_checksum,
            }} if cit_scope.get("run") else None,
            "counts": {{
                "assessments": env["sudo.compliance.assessment"].sudo().search_count([("profile_id", "=", profile.id)]),
                "findings": env["sudo.compliance.finding"].sudo().search_count([("assessment_id.profile_id", "=", profile.id)]),
                "tasks": env["sudo.compliance.task"].sudo().search_count([("assessment_id.profile_id", "=", profile.id)]),
                "reports": env["sudo.cn.compliance.report"].sudo().search_count([("assessment_id.profile_id", "=", profile.id)]),
                "evidence": env["sudo.compliance.evidence"].sudo().search_count([("task_id.assessment_id.profile_id", "=", profile.id)]),
                "filing_archives": env["sudo.compliance.filing"].sudo().search_count([("profile_id", "=", profile.id)]),
                "iit_reconciliation_runs": env["sudo.cn.iit.period.reconciliation.run"].sudo().search_count([("profile_id", "=", profile.id)]),
                "cross_border_transactions": env["sudo.cn.cross.border.transaction"].sudo().search_count([("profile_id", "=", profile.id)]),
                "cit_reconciliation_runs": env["sudo.cn.cit.period.reconciliation.run"].sudo().search_count([("profile_id", "=", profile.id)]),
            }},
        }})
        if payload["ok"]:
            env.cr.commit()
print("{MARKER}" + json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))
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
        input=_shell_code(args.company, args.allow_demo_data),
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
        "ok": False,
        "shell_returncode": result.returncode,
        "error": "demo closed-loop preparation marker was not found in Odoo shell output",
        "output_tail": result.stdout[-4000:],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a controlled China compliance closed-loop walkthrough in a "
            "development database."
        )
    )
    parser.add_argument("--python-bin", type=Path, required=True)
    parser.add_argument("--odoo-bin", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--company")
    parser.add_argument("--allow-demo-data", action="store_true")
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--json-output", type=Path)
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
    if payload.get("ok") is True:
        print(f"China demo closed loop ready: {args.database}")
        return 0
    print(f"China demo closed loop is not ready: {args.database}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
