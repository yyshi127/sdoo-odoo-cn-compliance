"""Run China country-pack delivery acceptance checks.

The script is intentionally small and dependency-free so it can be copied to an
isolated server together with the addon package.  Local checks always run.  Odoo
runtime checks run only when --odoo-bin, --config and --database are supplied.
"""

from __future__ import annotations

import argparse
import py_compile
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "addons" / "sudo_country_pack_cn"
DEFAULT_RUNTIME_TAGS = [
    "/sudo_country_pack_cn:TestChinaComplianceWorkbench",
    "/sudo_country_pack_cn:TestChinaRiskCenterDisplay",
    "/sudo_country_pack_cn:TestChinaReportReadiness",
    "/sudo_country_pack_cn:TestChinaFormalComplianceReport",
]


def _run(command: list[str], *, cwd: Path = ROOT) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def _inside_git_worktree() -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def _compile_python() -> None:
    targets = [
        ADDON / "__manifest__.py",
        ADDON / "hooks.py",
        ADDON / "models" / "workbench.py",
        ADDON / "models" / "risk_center.py",
        ADDON / "models" / "report_readiness.py",
        ADDON / "models" / "compliance_report.py",
        ADDON / "tests" / "test_workbench.py",
        ADDON / "tests" / "test_risk_center.py",
        ADDON / "tests" / "test_report_readiness.py",
        ADDON / "tests" / "test_compliance_report.py",
    ]
    for target in targets:
        py_compile.compile(str(target), doraise=True)
    print(f"compiled {len(targets)} Python files")


def _parse_xml() -> None:
    targets = [
        ADDON / "data" / "country_pack_data.xml",
        ADDON / "views" / "workbench_views.xml",
        ADDON / "views" / "risk_center_views.xml",
        ADDON / "views" / "report_readiness_views.xml",
        ADDON / "views" / "compliance_report_views.xml",
    ]
    for target in targets:
        ET.parse(target)
    print(f"parsed {len(targets)} XML files")


def _run_local_checks() -> None:
    _run([sys.executable, "tools/validate_addon.py"])
    _compile_python()
    _parse_xml()
    if _inside_git_worktree():
        _run(["git", "diff", "--check", "--", "addons/sudo_country_pack_cn", "tools"])
    else:
        print("git diff check skipped: not inside a Git worktree")


def _run_odoo_checks(args: argparse.Namespace) -> None:
    tags = ",".join(args.test_tags or DEFAULT_RUNTIME_TAGS)
    command = [
        str(args.python_bin) if args.python_bin else str(args.odoo_bin),
    ]
    if args.python_bin:
        command.append(str(args.odoo_bin))
    command.extend(
        [
        "-c",
        str(args.config),
        "-d",
        args.database,
        "--db-filter=.*",
        "-i" if args.install else "-u",
        "sudo_country_pack_cn",
        "--without-demo=True",
        "--test-enable",
        "--test-tags",
        tags,
        "--stop-after-init",
        "--log-level=test",
        ]
    )
    if args.http_port:
        command.extend(["--http-port", str(args.http_port)])
    if args.logfile:
        command.extend(["--logfile", str(args.logfile)])
    _run(command)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run local and optional Odoo runtime delivery acceptance checks."
    )
    parser.add_argument("--odoo-bin", type=Path)
    parser.add_argument(
        "--python-bin",
        type=Path,
        help="Optional Python interpreter for running odoo-bin inside a venv.",
    )
    parser.add_argument("--config", type=Path)
    parser.add_argument("--database")
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--http-port", type=int)
    parser.add_argument("--logfile", type=Path)
    parser.add_argument(
        "--test-tags",
        action="append",
        help="Odoo test tag. Repeat to override the default delivery tag set.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    _run_local_checks()
    runtime_args = [args.odoo_bin, args.config, args.database]
    if any(runtime_args) and not all(runtime_args):
        raise SystemExit("--odoo-bin, --config and --database must be supplied together")
    if all(runtime_args):
        _run_odoo_checks(args)
    else:
        print("runtime skipped: supply --odoo-bin --config --database to run Odoo tests")
    print("China delivery acceptance checks completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
