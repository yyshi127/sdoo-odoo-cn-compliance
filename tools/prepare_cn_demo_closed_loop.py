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
    ], order="id desc", limit=1)
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


def ensure_assessment(run):
    existing = env["sudo.compliance.assessment"].sudo().search([
        ("profile_id", "=", run.profile_id.id),
        ("period_start", "=", run.period_start),
        ("period_end", "=", run.period_end),
        ("finding_ids.rule_id.code", "=", "CN-CODEX-DEMO-VAT-RECON-CLOSED-LOOP"),
    ], order="id desc", limit=1)
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
    return finding, task, changed


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
        assessment, created_assessment = ensure_assessment(run)
        finding, task, changed_task = ensure_finding_task(assessment)
        report, created_report = ensure_report(assessment)
        profile.invalidate_recordset()
        payload.update({{
            "ok": bool(assessment and finding and task and report),
            "changed": bool(created_run or changed_rule or created_assessment or changed_task or created_report),
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
            }} if task else None,
            "report": {{
                "id": report.id,
                "name": report.display_name,
                "state": report.state,
                "conclusion_state": report.conclusion_state,
            }} if report else None,
            "counts": {{
                "assessments": env["sudo.compliance.assessment"].sudo().search_count([("profile_id", "=", profile.id)]),
                "findings": env["sudo.compliance.finding"].sudo().search_count([("assessment_id.profile_id", "=", profile.id)]),
                "tasks": env["sudo.compliance.task"].sudo().search_count([("assessment_id.profile_id", "=", profile.id)]),
                "reports": env["sudo.cn.compliance.report"].sudo().search_count([("assessment_id.profile_id", "=", profile.id)]),
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
