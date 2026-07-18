"""Run China country-pack delivery acceptance checks.

The script is intentionally small and dependency-free so it can be copied to an
isolated server together with the addon package.  Local checks always run.  Odoo
runtime checks run only when --odoo-bin, --config and --database are supplied.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import py_compile
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "addons" / "sudo_country_pack_cn"
XBRL_ADDON = ROOT / "addons" / "sudo_country_pack_cn_einvoice_xbrl"
DEFAULT_RUNTIME_TAGS = [
    "/sudo_country_pack_cn:TestChinaComplianceWorkbench",
    "/sudo_country_pack_cn:TestChinaRiskCenterDisplay",
    "/sudo_country_pack_cn:TestChinaReportReadiness",
    "/sudo_country_pack_cn:TestChinaFormalComplianceReport",
]
TAX_RUNTIME_TAGS = [
    "/sudo_country_pack_cn:TestChinaTaxDataNormalization",
    "/sudo_country_pack_cn:TestChinaInvoiceNormalization",
    "/sudo_country_pack_cn:TestChinaInvoiceReconciliation",
    "/sudo_country_pack_cn:TestChinaVatPeriodReconciliation",
    "/sudo_country_pack_cn:TestChinaCitPeriodReconciliation",
    "/sudo_country_pack_cn:TestChinaIitPeriodReconciliation",
    "/sudo_country_pack_cn:TestChinaFilingCenter",
]
GOVERNANCE_RUNTIME_TAGS = [
    "/sudo_country_pack_cn:TestChinaCountryPack",
    "/sudo_country_pack_cn:TestChinaJurisdictionPackagedSafety",
    "/sudo_country_pack_cn:TestChinaJurisdictionGovernance",
    "/sudo_country_pack_cn:TestChinaTaxpayerClassification",
    "/sudo_country_pack_cn:TestChinaExternalDataset",
    "/sudo_country_pack_cn:TestChinaFactProviders",
    "/sudo_country_pack_cn:TestChinaRuleDrafts",
    "/sudo_country_pack_cn:TestChinaRuleReviewPacket",
    "/sudo_country_pack_cn:TestChinaOfficialSourceMonitoring",
    "/sudo_country_pack_cn:TestChinaControlledAiGuidance",
    "/sudo_country_pack_cn:TestChinaAssessmentDataBasis",
    "/sudo_country_pack_cn:TestChinaDataReadinessCenter",
]
RUNTIME_PROFILES = {
    "core": DEFAULT_RUNTIME_TAGS,
    "tax": TAX_RUNTIME_TAGS,
    "governance": GOVERNANCE_RUNTIME_TAGS,
    "full": DEFAULT_RUNTIME_TAGS + TAX_RUNTIME_TAGS + GOVERNANCE_RUNTIME_TAGS,
}
FULL_PROFILE_TOOL_TESTS = [
    "tools.test_tax_data_contract",
    "tools.test_xbrl_contract",
    "tools.test_xbrl_normalizer",
    "tools.test_xbrl_worker_compatibility",
    "tools.test_signoff_validation",
]
MANIFEST_SCHEMA = "sdoo.cn.delivery-manifest.v1"
SUMMARY_SCHEMA = "sdoo.cn.delivery-acceptance-summary.v1"
MANIFEST_EXCLUDED_DIRS = {"__pycache__", ".git", "dist", "build", "artifacts", "tmp"}
MANIFEST_EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


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


def _git_commit() -> str | None:
    if not _inside_git_worktree():
        return None
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _git_branch() -> str | None:
    if not _inside_git_worktree():
        return None
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _git_dirty() -> bool | None:
    if not _inside_git_worktree():
        return None
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        return None
    return bool(result.stdout.strip())


def _source_control_summary() -> dict[str, object]:
    return {
        "inside_worktree": _inside_git_worktree(),
        "commit": _git_commit(),
        "branch": _git_branch(),
        "dirty": _git_dirty(),
    }


def _addon_version() -> str:
    manifest = ast.literal_eval((ADDON / "__manifest__.py").read_text(encoding="utf-8"))
    return str(manifest["version"])


def _manifest_paths() -> list[Path]:
    roots = [
        ADDON,
        XBRL_ADDON,
        ROOT / "docs" / "CHINA_BUSINESS_UAT_CHECKLIST.md",
        ROOT / "docs" / "CHINA_UAT_WALKTHROUGH_SCRIPT.md",
        ROOT / "docs" / "CHINA_DELIVERY_INDEX.md",
        ROOT / "docs" / "CHINA_RELEASE_HANDOFF_CURRENT.md",
        ROOT / "docs" / "CHINA_DELIVERY_M138_STATUS.md",
        ROOT / "docs" / "CHINA_DELIVERY_OBJECTIVE_COVERAGE.md",
        ROOT / "docs" / "CHINA_PRODUCTION_SIGNOFF_TEMPLATE.md",
        ROOT / "docs" / "DEVELOPMENT_PREVIEW_ACCESS_CN.md",
        ROOT / "docs" / "DELIVERY_RUNBOOK_CN.md",
        ROOT / "docs" / "MILESTONE_70_CHINA_BLOCKER_SUMMARY_VISIBILITY.md",
        ROOT / "docs" / "samples",
        ROOT / "tools" / "run_cn_delivery_acceptance.py",
        ROOT / "tools" / "build_cn_delivery_bundle.py",
        ROOT / "tools" / "check_cn_preview_health.py",
        ROOT / "tools" / "check_cn_preview_module.py",
        ROOT / "tools" / "check_cn_real_data_closed_loop.py",
        ROOT / "tools" / "prepare_cn_demo_profile.py",
        ROOT / "tools" / "prepare_cn_demo_closed_loop.py",
        ROOT / "tools" / "summarize_cn_delivery_status.py",
        ROOT / "tools" / "audit_cn_objective_completion.py",
        ROOT / "tools" / "generate_cn_signoff_packet.py",
        ROOT / "tools" / "render_cn_signoff_evidence_template.py",
        ROOT / "tools" / "validate_cn_signoff_evidence.py",
        ROOT / "tools" / "verify_cn_delivery_artifacts.py",
        ROOT / "tools" / "validate_addon.py",
        ROOT / "tools" / "test_tax_data_contract.py",
        ROOT / "tools" / "test_xbrl_contract.py",
        ROOT / "tools" / "test_xbrl_normalizer.py",
        ROOT / "tools" / "test_xbrl_worker_compatibility.py",
        ROOT / "tools" / "test_signoff_validation.py",
    ]
    paths: list[Path] = []
    for root in roots:
        if root.is_file():
            paths.append(root)
            continue
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            relative_parts = path.relative_to(ROOT).parts
            if any(part in MANIFEST_EXCLUDED_DIRS for part in relative_parts):
                continue
            if path.suffix in MANIFEST_EXCLUDED_SUFFIXES:
                continue
            paths.append(path)
    return sorted(paths, key=lambda path: path.relative_to(ROOT).as_posix())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_entry(path: Path) -> dict[str, object]:
    relative = path.relative_to(ROOT).as_posix()
    return {
        "path": relative,
        "size": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _aggregate_sha256(entries: list[dict[str, object]]) -> str:
    digest = hashlib.sha256()
    for entry in entries:
        path = str(entry["path"])
        data = (ROOT / path).read_bytes()
        path_bytes = path.encode("utf-8")
        digest.update(len(path_bytes).to_bytes(8, "big"))
        digest.update(path_bytes)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def _write_manifest(path: Path) -> None:
    entries = [_manifest_entry(file_path) for file_path in _manifest_paths()]
    payload = {
        "schema": MANIFEST_SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "addon": "sudo_country_pack_cn",
        "version": _addon_version(),
        "git_commit": _git_commit(),
        "source_control": _source_control_summary(),
        "root": str(ROOT),
        "file_count": len(entries),
        "aggregate_sha256": _aggregate_sha256(entries),
        "files": entries,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "delivery manifest written: "
        f"{path} ({payload['file_count']} files, {payload['aggregate_sha256']})"
    )


def _load_manifest_summary(path: Path | None) -> dict[str, object] | None:
    if not path or not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "schema": payload.get("schema"),
        "path": str(path),
        "version": payload.get("version"),
        "git_commit": payload.get("git_commit"),
        "source_control": payload.get("source_control"),
        "file_count": payload.get("file_count"),
        "aggregate_sha256": payload.get("aggregate_sha256"),
    }


def _parse_runtime_log(path: Path | None) -> dict[str, object] | None:
    if not path or not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    stats_match = re.search(
        r"odoo\.tests\.stats: (?P<module>\S+): (?P<tests>\d+) tests "
        r"(?P<seconds>[0-9.]+)s (?P<queries>\d+) queries",
        text,
    )
    result_match = re.search(
        r"odoo\.tests\.result: (?P<failed>\d+) failed, "
        r"(?P<errors>\d+) error\(s\) of (?P<loaded>\d+) tests",
        text,
    )
    summary: dict[str, object] = {"path": str(path)}
    if stats_match:
        summary.update(
            {
                "module": stats_match.group("module"),
                "reported_test_count": int(stats_match.group("tests")),
                "seconds": float(stats_match.group("seconds")),
                "queries": int(stats_match.group("queries")),
            }
        )
    if result_match:
        summary.update(
            {
                "failed": int(result_match.group("failed")),
                "errors": int(result_match.group("errors")),
                "loaded_test_count": int(result_match.group("loaded")),
            }
        )
    return summary


def _runtime_log_summary(args: argparse.Namespace) -> dict[str, object] | None:
    parsed = _parse_runtime_log(args.logfile)
    if parsed:
        return parsed
    if all([args.odoo_bin, args.config, args.database]):
        return {
            "failed": 0,
            "errors": 0,
            "source": "process_exit_zero",
            "note": (
                "Odoo runtime command completed with exit code 0; no logfile was "
                "provided for detailed test-count parsing."
            ),
        }
    return None


def _write_summary(args: argparse.Namespace, path: Path) -> None:
    runtime_requested = all([args.odoo_bin, args.config, args.database])
    payload = {
        "schema": SUMMARY_SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "addon": "sudo_country_pack_cn",
        "version": _addon_version(),
        "git_commit": _git_commit(),
        "source_control": _source_control_summary(),
        "root": str(ROOT),
        "profile": args.profile,
        "selected_runtime_tags": args.test_tags or RUNTIME_PROFILES[args.profile],
        "full_profile_tool_tests": FULL_PROFILE_TOOL_TESTS if args.profile == "full" else [],
        "local_checks": {
            "validate_addon": "passed",
            "python_compile": "passed",
            "xml_parse": "passed",
            "git_diff_check": "passed" if _inside_git_worktree() else "skipped",
        },
        "runtime": {
            "requested": runtime_requested,
            "database": args.database,
            "install": bool(args.install),
            "http_port": args.http_port,
            "log": _runtime_log_summary(args),
        },
        "manifest": _load_manifest_summary(args.write_manifest),
        "result": "passed",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"delivery acceptance summary written: {path}")


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


def _run_profile_tool_tests(profile: str) -> None:
    if profile != "full":
        return
    _run([sys.executable, "-m", "unittest", *FULL_PROFILE_TOOL_TESTS])


def _run_local_checks(profile: str) -> None:
    _run([sys.executable, "tools/validate_addon.py"])
    _compile_python()
    _parse_xml()
    _run_profile_tool_tests(profile)
    if _inside_git_worktree():
        _run(["git", "diff", "--check", "--", "addons/sudo_country_pack_cn", "tools"])
    else:
        print("git diff check skipped: not inside a Git worktree")


def _run_odoo_checks(args: argparse.Namespace) -> None:
    tags = ",".join(args.test_tags or RUNTIME_PROFILES[args.profile])
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
        "--profile",
        choices=sorted(RUNTIME_PROFILES),
        default="core",
        help=(
            "Runtime acceptance profile. "
            "core is the fast visible closed loop; full also runs local contract tests."
        ),
    )
    parser.add_argument(
        "--test-tags",
        action="append",
        help="Odoo test tag. Repeat to override the default delivery tag set.",
    )
    parser.add_argument(
        "--write-manifest",
        type=Path,
        help="Write a deterministic delivery manifest with file SHA-256 checksums.",
    )
    parser.add_argument(
        "--write-summary",
        type=Path,
        help="Write a JSON acceptance summary after all selected checks pass.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    _run_local_checks(args.profile)
    runtime_args = [args.odoo_bin, args.config, args.database]
    if any(runtime_args) and not all(runtime_args):
        raise SystemExit("--odoo-bin, --config and --database must be supplied together")
    if all(runtime_args):
        _run_odoo_checks(args)
    else:
        print("runtime skipped: supply --odoo-bin --config --database to run Odoo tests")
    if args.write_manifest:
        _write_manifest(args.write_manifest)
    if args.write_summary:
        _write_summary(args, args.write_summary)
    print("China delivery acceptance checks completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
