"""Check that a China compliance preview database has the expected module state."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = "sdoo.cn.preview-module.v1"
MARKER = "SDOO_CN_PREVIEW_MODULE_JSON="


def _shell_code(expected_version: str) -> str:
    return f"""
import json

module = env["ir.module.module"].search([("name", "=", "sudo_country_pack_cn")], limit=1)
pack = env.ref("sudo_country_pack_cn.compliance_country_pack_cn", raise_if_not_found=False)
features = {{}}
if pack and isinstance(pack.capability_json, dict):
    features = pack.capability_json.get("features") or {{}}
payload = {{
    "schema": "{SCHEMA}",
    "expected_version": {expected_version!r},
    "module_found": bool(module),
    "module_state": module.state if module else None,
    "module_installed_version": module.installed_version if module else None,
    "country_pack_found": bool(pack),
    "country_pack_code": pack.code if pack else None,
    "country_pack_module_name": pack.module_name if pack else None,
    "country_pack_version": pack.version if pack else None,
    "required_capabilities": {{
        "china_workbench": bool(features.get("china_workbench")),
        "china_delivery_preview_health_gate": bool(features.get("china_delivery_preview_health_gate")),
        "china_delivery_preview_module_gate": bool(features.get("china_delivery_preview_module_gate")),
        "china_delivery_source_control_traceability": bool(features.get("china_delivery_source_control_traceability")),
    }},
}}
payload["ok"] = (
    payload["module_found"]
    and payload["module_state"] == "installed"
    and payload["module_installed_version"] == payload["expected_version"]
    and payload["country_pack_found"]
    and payload["country_pack_code"] == "CN"
    and payload["country_pack_module_name"] == "sudo_country_pack_cn"
    and payload["country_pack_version"] == payload["expected_version"]
    and all(payload["required_capabilities"].values())
)
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
        "error": "preview module marker was not found in Odoo shell output",
        "output_tail": result.stdout[-4000:],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check a China compliance preview database module installation."
    )
    parser.add_argument("--python-bin", type=Path, required=True)
    parser.add_argument("--odoo-bin", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--timeout", type=int, default=120)
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
        print(
            "preview module check passed: "
            f"{args.database} / sudo_country_pack_cn {args.expected_version}"
        )
        return 0
    print(
        "preview module check failed: "
        f"{args.database} / sudo_country_pack_cn {args.expected_version}"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
