"""Prepare one China compliance profile for controlled development walkthroughs."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = "sdoo.cn.demo-profile-preparation.v1"
MARKER = "SDOO_CN_DEMO_PROFILE_PREPARATION_JSON="


def _shell_code(company_name: str | None, allow_demo_data: bool) -> str:
    return f"""
import json
from datetime import date

allow_demo_data = {allow_demo_data!r}
company_name = {company_name!r}


def has_model(model_name):
    return model_name in env.registry


def attachment(name, raw):
    existing = env["ir.attachment"].sudo().search([("name", "=", name)], limit=1)
    if existing:
        return existing
    return env["ir.attachment"].sudo().create({{"name": name, "raw": raw}})


def command_set(ids):
    return [(6, 0, ids)]


def count(model_name, domain=None):
    if not has_model(model_name):
        return None
    return env[model_name].sudo().search_count(domain or [])


def pick_profile():
    Profile = env["sudo.compliance.profile"].sudo()
    cn = env["res.country"].sudo().search([("code", "=", "CN")], limit=1)
    domain = [("country_id", "=", cn.id)] if cn else []
    if company_name:
        exact = Profile.search(domain + [("company_id.name", "=", company_name)], limit=1)
        if exact:
            return exact
        partial = Profile.search(domain + [("company_id.name", "ilike", company_name)], limit=1)
        if partial:
            return partial
    profiles = Profile.search(domain, order="id asc")
    if not profiles:
        return Profile.browse()
    Move = env["account.move"].sudo()
    with_ledger = profiles.filtered(
        lambda profile: Move.search_count([
            ("company_id", "=", profile.company_id.id),
            ("state", "=", "posted"),
        ])
    )
    return (with_ledger or profiles)[:1]


def activate(profile):
    before = profile.status
    issues_before = profile._activation_issues()
    if issues_before:
        return {{"changed": False, "before": before, "after": profile.status, "issues": issues_before}}
    if profile.status == "active":
        return {{"changed": False, "before": before, "after": profile.status, "issues": []}}
    if hasattr(profile, "action_activate"):
        profile.action_activate()
    elif hasattr(profile, "_write_import"):
        profile._write_import({{"status": "active"}})
    else:
        profile.write({{"status": "active"}})
    profile.invalidate_recordset()
    return {{"changed": before != profile.status, "before": before, "after": profile.status, "issues": profile._activation_issues()}}


def confirm_fiscal_year(profile):
    if getattr(profile, "fiscal_year_end_confirmed", False):
        return False
    values = {{}}
    if "fiscal_year_end_basis" in profile._fields and not profile.fiscal_year_end_basis:
        values["fiscal_year_end_basis"] = (
            "CODEX-DEMO ONLY: fiscal year end confirmed for controlled development walkthrough; "
            "replace with board resolution, articles or tax filing evidence for production."
        )
    if values:
        profile.write(values)
    if hasattr(profile, "action_confirm_fiscal_year_end"):
        profile.action_confirm_fiscal_year_end()
    else:
        profile.write({{"fiscal_year_end_confirmed": True}})
    return True


def review_obligations(profile):
    obligations = profile.obligation_ids
    if not obligations:
        return {{"reviewed": 0, "applicable": []}}
    source = env.ref(
        "sudo_country_pack_cn.source_cn_tax_collection_law_2015_candidate",
        raise_if_not_found=False,
    )
    if not source:
        source = env["sudo.compliance.authority.source"].sudo().search(
            [("country_id.code", "=", "CN")], limit=1
        )
    base_values = {{
        "applicability": "not_applicable",
        "justification": (
            "CODEX-DEMO ONLY: candidate obligation reviewed as not applicable "
            "for controlled development walkthrough; replace with professional "
            "source-backed applicability review before production use."
        ),
    }}
    if source:
        base_values["authority_source_id"] = source.id
    obligations.write(base_values)
    applicable = []
    vat = obligations.filtered(lambda obligation: obligation.code == "CN-VAT")
    if vat:
        vat.write({{
            "applicability": "applicable",
            "justification": (
                "CODEX-DEMO ONLY: VAT obligation marked applicable to exercise "
                "the China compliance walkthrough; not a real taxpayer conclusion."
            ),
        }})
        applicable.append("CN-VAT")
    return {{"reviewed": len(obligations), "applicable": applicable}}


profile = pick_profile()
created = {{
    "registration": False,
    "classification": False,
    "attachments": [],
    "fiscal_year_confirmed": False,
    "obligations": {{"reviewed": 0, "applicable": []}},
}}
if not profile:
    payload = {{
        "schema": "{SCHEMA}",
        "ok": False,
        "changed": False,
        "error": "no China compliance profile was found",
    }}
else:
    today = date.today().isoformat()
    registration_number = "91310000CODEXDEMO01"
    registration_name = "CODEX-DEMO 中国合规演示统一社会信用代码登记"
    identity_name = "CODEX-DEMO 中国合规演示纳税人身份快照"
    if allow_demo_data:
        registration_attachment = attachment(
            "CODEX-DEMO-cn-registration-evidence.txt",
            b"CODEX DEMO ONLY - controlled registration evidence for development walkthrough",
        )
        identity_attachment = attachment(
            "CODEX-DEMO-cn-taxpayer-identity-evidence.txt",
            b"CODEX DEMO ONLY - controlled taxpayer identity evidence for development walkthrough",
        )
        created["attachments"] = [registration_attachment.id, identity_attachment.id]

        Registration = env["sudo.compliance.registration"].sudo()
        registration = Registration.search([
            ("profile_id", "=", profile.id),
            ("registration_type", "=", "unified_social_credit_code"),
            ("registration_number", "=", registration_number),
        ], limit=1)
        if not registration:
            registration = Registration.create({{
                "name": registration_name,
                "profile_id": profile.id,
                "registration_type": "unified_social_credit_code",
                "registration_number": registration_number,
                "authority": "CODEX-DEMO 市场监督管理部门",
                "valid_from": "2000-01-01",
                "state": "active",
                "evidence_attachment_ids": command_set([registration_attachment.id]),
            }})
            created["registration"] = True
        else:
            registration.write({{
                "state": "active",
                "valid_from": registration.valid_from or "2000-01-01",
                "evidence_attachment_ids": command_set([registration_attachment.id]),
            }})

        province = env["res.country.state"].sudo().search([
            ("country_id.code", "=", "CN")
        ], limit=1)
        if not province:
            province = env["res.country.state"].sudo().create({{
                "name": "CODEX-DEMO 中国合规演示辖区",
                "code": "CDX",
                "country_id": env["res.country"].sudo().search([("code", "=", "CN")], limit=1).id,
            }})

        Classification = env["sudo.cn.taxpayer.classification"].sudo()
        classification = Classification.search([
            ("profile_id", "=", profile.id),
            ("source_reference", "=", "CODEX-DEMO-TAXPAYER-PROFILE"),
        ], limit=1)
        values = {{
            "profile_id": profile.id,
            "valid_from": "2000-01-01",
            "province_id": province.id,
            "local_jurisdiction_name": "CODEX-DEMO 税务辖区",
            "local_jurisdiction_code": "CN-CODEX-DEMO",
            "tax_authority_name": "CODEX-DEMO 主管税务机关",
            "vat_taxpayer_status": "general",
            "vat_filing_frequency": "monthly",
            "cit_taxpayer_status": "resident",
            "cit_collection_method": "accounts_based",
            "pit_withholding_status": "yes",
            "accounting_regime": "asbe",
            "source_type": "professional_workpaper",
            "source_date": today,
            "source_reference": "CODEX-DEMO-TAXPAYER-PROFILE",
            "scope_note": "CODEX-DEMO ONLY: controlled development walkthrough identity snapshot; not real taxpayer evidence.",
            "evidence_attachment_ids": command_set([identity_attachment.id]),
        }}
        if classification:
            if classification.state == "verified":
                pass
            else:
                classification.write(values)
        else:
            classification = Classification.create(values)
            created["classification"] = True
        if classification.state == "draft":
            classification.action_verify()
        created["fiscal_year_confirmed"] = confirm_fiscal_year(profile)
        created["obligations"] = review_obligations(profile)
        activation = activate(profile)
    else:
        activation = {{"changed": False, "before": profile.status, "after": profile.status, "issues": profile._activation_issues()}}

    profile.invalidate_recordset()
    payload = {{
        "schema": "{SCHEMA}",
        "ok": bool(profile.status == "active" and not profile._activation_issues()),
        "changed": bool(created["registration"] or created["classification"] or activation.get("changed")),
        "allow_demo_data": allow_demo_data,
        "profile": {{
            "id": profile.id,
            "name": profile.display_name,
            "company": profile.company_id.display_name,
            "status": profile.status,
            "activation_issues": profile._activation_issues(),
            "workbench_status": profile.cn_workbench_status if "cn_workbench_status" in profile._fields else None,
            "next_action": profile.cn_workbench_next_action if "cn_workbench_next_action" in profile._fields else None,
        }},
        "created": created,
        "activation": activation,
        "counts": {{
            "cn_profiles": count("sudo.compliance.profile", [("country_id.code", "=", "CN")]),
            "active_cn_profiles": count("sudo.compliance.profile", [("country_id.code", "=", "CN"), ("status", "=", "active")]),
        }},
    }}
    if allow_demo_data and payload["ok"]:
        env.cr.commit()
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
        "error": "demo profile preparation marker was not found in Odoo shell output",
        "output_tail": result.stdout[-4000:],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare a controlled China compliance demo profile in a development database."
    )
    parser.add_argument("--python-bin", type=Path, required=True)
    parser.add_argument("--odoo-bin", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--company")
    parser.add_argument("--allow-demo-data", action="store_true")
    parser.add_argument("--timeout", type=int, default=180)
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
        print(f"China demo profile ready: {args.database}")
        return 0
    print(f"China demo profile is not ready: {args.database}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
