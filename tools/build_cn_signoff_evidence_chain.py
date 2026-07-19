"""Build the China delivery status, objective audit and sign-off evidence chain."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _load_tool(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    if not spec or not spec.loader:
        raise RuntimeError(f"cannot load tool: {path}")
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


SUMMARY = _load_tool(
    "cn_delivery_status",
    REPOSITORY_ROOT / "tools" / "summarize_cn_delivery_status.py",
)
PACKET = _load_tool(
    "cn_signoff_packet",
    REPOSITORY_ROOT / "tools" / "generate_cn_signoff_packet.py",
)
RENDER_EVIDENCE = _load_tool(
    "cn_render_signoff_evidence",
    REPOSITORY_ROOT / "tools" / "render_cn_signoff_evidence_template.py",
)
VALIDATION = _load_tool(
    "cn_signoff_validation",
    REPOSITORY_ROOT / "tools" / "validate_cn_signoff_evidence.py",
)
OBJECTIVE_AUDIT = _load_tool(
    "cn_objective_audit",
    REPOSITORY_ROOT / "tools" / "audit_cn_objective_completion.py",
)
LATEST_CANDIDATE = _load_tool(
    "cn_latest_signoff_candidate",
    REPOSITORY_ROOT / "tools" / "select_cn_latest_signoff_candidate.py",
)


def _load(path: Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _status(
    inputs: dict[str, Any],
    *,
    objective_audit: dict[str, Any] | None = None,
    signoff_validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return SUMMARY._status(
        bundle_metadata=inputs.get("bundle_metadata"),
        manifest=inputs.get("manifest"),
        summary=inputs.get("summary"),
        preview_health=inputs.get("preview_health"),
        preview_module=inputs.get("preview_module"),
        real_data_closed_loop=inputs.get("real_data_closed_loop"),
        upgrade_summary=inputs.get("upgrade_summary"),
        objective_audit=objective_audit,
        signoff_validation=signoff_validation,
        preview_url=inputs.get("preview_url"),
    )


def build_chain(
    inputs: dict[str, Any],
    *,
    completed_evidence: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    initial_status = _status(inputs)
    bootstrap_packet = PACKET._build_packet(initial_status)
    bootstrap_evidence = RENDER_EVIDENCE.render_template(bootstrap_packet)
    bootstrap_validation = VALIDATION._validate(
        bootstrap_packet,
        bootstrap_evidence,
    )

    status_for_audit = _status(
        inputs,
        signoff_validation=bootstrap_validation,
    )
    bootstrap_audit = OBJECTIVE_AUDIT.audit(status_for_audit)
    status_for_final_packet = _status(
        inputs,
        objective_audit=bootstrap_audit,
        signoff_validation=bootstrap_validation,
    )
    final_packet = PACKET._build_packet(status_for_final_packet)
    final_evidence = completed_evidence or RENDER_EVIDENCE.render_template(final_packet)
    final_validation = VALIDATION._validate(final_packet, final_evidence)

    status_for_final_audit = _status(
        inputs,
        objective_audit=bootstrap_audit,
        signoff_validation=final_validation,
    )
    final_audit = OBJECTIVE_AUDIT.audit(status_for_final_audit)
    final_status = _status(
        inputs,
        objective_audit=final_audit,
        signoff_validation=final_validation,
    )

    return {
        "initial_status": initial_status,
        "bootstrap_packet": bootstrap_packet,
        "bootstrap_evidence": bootstrap_evidence,
        "bootstrap_validation": bootstrap_validation,
        "status_for_final_packet": status_for_final_packet,
        "final_packet": final_packet,
        "final_evidence": final_evidence,
        "final_validation": final_validation,
        "objective_audit": final_audit,
        "final_status": final_status,
    }


def _write_outputs(chain: dict[str, dict[str, Any]], prefix: Path) -> dict[str, Path]:
    outputs = {
        "initial_status": prefix.with_name(prefix.name + "_status_initial.json"),
        "bootstrap_packet": prefix.with_name(prefix.name + "_signoff_packet_bootstrap.json"),
        "bootstrap_evidence": prefix.with_name(prefix.name + "_signoff_evidence_bootstrap.json"),
        "bootstrap_validation": prefix.with_name(prefix.name + "_signoff_validation_bootstrap.json"),
        "status_for_final_packet": prefix.with_name(
            prefix.name + "_status_for_final_packet.json"
        ),
        "final_packet": prefix.with_name(prefix.name + "_signoff_packet.json"),
        "final_evidence": prefix.with_name(prefix.name + "_signoff_evidence.json"),
        "final_validation": prefix.with_name(prefix.name + "_signoff_validation.json"),
        "objective_audit": prefix.with_name(prefix.name + "_objective_audit.json"),
        "final_status": prefix.with_name(prefix.name + "_status.json"),
    }
    for key, path in outputs.items():
        _write_json(chain[key], path)

    SUMMARY._write_markdown(
        chain["final_status"],
        prefix.with_name(prefix.name + "_status.md"),
    )
    PACKET._write_markdown(
        chain["final_packet"],
        prefix.with_name(prefix.name + "_signoff_packet.md"),
    )
    OBJECTIVE_AUDIT._write_markdown(
        chain["objective_audit"],
        prefix.with_name(prefix.name + "_objective_audit.md"),
    )
    latest_candidate = LATEST_CANDIDATE.select_latest(
        prefix.parent,
        require_highest_status_complete=True,
    )
    latest_candidate_json = prefix.with_name(prefix.name + "_latest_signoff_candidate.json")
    latest_candidate_md = prefix.with_name(prefix.name + "_latest_signoff_candidate.md")
    _write_json(latest_candidate, latest_candidate_json)
    LATEST_CANDIDATE._write_markdown(latest_candidate, latest_candidate_md)
    outputs["latest_signoff_candidate"] = latest_candidate_json
    outputs["latest_signoff_candidate_markdown"] = latest_candidate_md
    return outputs


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a correctly ordered China sign-off evidence chain. The final "
            "packet includes objective audit evidence, and the final status uses "
            "the validation result from that packet."
        )
    )
    parser.add_argument("--bundle-metadata", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--upgrade-summary", type=Path, required=True)
    parser.add_argument("--preview-health", type=Path, required=True)
    parser.add_argument("--preview-module", type=Path, required=True)
    parser.add_argument("--real-data-closed-loop", type=Path, required=True)
    parser.add_argument("--preview-url", required=True)
    parser.add_argument(
        "--completed-evidence",
        type=Path,
        help=(
            "Optional completed human evidence JSON. If omitted, a placeholder "
            "draft is rendered and validation must remain blocked."
        ),
    )
    parser.add_argument("--output-prefix", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    inputs = {
        "bundle_metadata": _load(args.bundle_metadata),
        "manifest": _load(args.manifest),
        "summary": _load(args.summary),
        "upgrade_summary": _load(args.upgrade_summary),
        "preview_health": _load(args.preview_health),
        "preview_module": _load(args.preview_module),
        "real_data_closed_loop": _load(args.real_data_closed_loop),
        "preview_url": args.preview_url,
    }
    chain = build_chain(
        inputs,
        completed_evidence=_load(args.completed_evidence),
    )
    outputs = _write_outputs(chain, args.output_prefix)
    final_readiness = chain["final_status"].get("readiness_gates") or {}
    print(
        "sign-off evidence chain built: "
        f"production_signoff_ready={final_readiness.get('production_signoff_ready')} "
        f"objective_achieved={chain['objective_audit'].get('achieved')} "
        f"final_validation_ok={chain['final_validation'].get('ok')} "
        f"outputs={len(outputs)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
