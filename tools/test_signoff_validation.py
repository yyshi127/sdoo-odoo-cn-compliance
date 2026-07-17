from __future__ import annotations

import importlib.util
import unittest
from copy import deepcopy
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def load_tool(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


PACKET = load_tool(
    "cn_signoff_packet",
    REPOSITORY_ROOT / "tools" / "generate_cn_signoff_packet.py",
)
VALIDATION = load_tool(
    "cn_signoff_validation",
    REPOSITORY_ROOT / "tools" / "validate_cn_signoff_evidence.py",
)
SUMMARY = load_tool(
    "cn_delivery_status",
    REPOSITORY_ROOT / "tools" / "summarize_cn_delivery_status.py",
)


def status_payload() -> dict:
    return {
        "version": "19.0.1.130.0",
        "version_consistent": True,
        "acceptance_passed": True,
        "runtime_passed": True,
        "preview_url": "http://127.0.0.1:18070/web/login?db=test",
        "source_control": {
            "inside_worktree": True,
            "branch": "main",
            "commit": "abc123",
            "dirty": False,
        },
        "readiness_gates": {
            "business_uat_ready": True,
            "source_control_clean": True,
            "business_uat_blockers": [],
            "production_signoff_blockers": [
                "business UAT decision must be recorded outside this automated status",
            ],
        },
        "runtime": {"log": {"failed": 0, "errors": 0}},
        "preview_health": {"ok": True, "url": "http://127.0.0.1:18070/web/login?db=test"},
        "preview_module": {"ok": True, "module_installed_version": "19.0.1.130.0"},
        "real_data_closed_loop": {
            "ok": True,
            "readiness": {"closed_loop_evidence_ready": True},
        },
    }


def manifest_payload() -> dict:
    paths = [
        "docs/CHINA_BUSINESS_UAT_CHECKLIST.md",
        "docs/CHINA_DELIVERY_INDEX.md",
        "docs/CHINA_DELIVERY_OBJECTIVE_COVERAGE.md",
        "docs/CHINA_PRODUCTION_SIGNOFF_TEMPLATE.md",
        "tools/check_cn_preview_health.py",
        "tools/check_cn_preview_module.py",
        "tools/check_cn_real_data_closed_loop.py",
        "tools/generate_cn_signoff_packet.py",
    ]
    return {
        "schema": "sdoo.cn.delivery-manifest.v1",
        "version": "19.0.1.130.0",
        "aggregate_sha256": "aggregate",
        "files": [{"path": path} for path in paths],
    }


def bundle_metadata_payload() -> dict:
    return {
        "schema": "sdoo.cn.delivery-bundle.v1",
        "version": "19.0.1.130.0",
        "aggregate_sha256": "aggregate",
        "bundle_sha256": "bundle",
        "source_control": {
            "inside_worktree": True,
            "branch": "main",
            "commit": "abc123",
            "dirty": False,
        },
    }


def summary_payload() -> dict:
    return {
        "schema": "sdoo.cn.delivery-acceptance-summary.v1",
        "version": "19.0.1.130.0",
        "result": "passed",
        "runtime": {
            "database": "test",
            "log": {"failed": 0, "errors": 0},
        },
    }


def preview_health_payload() -> dict:
    return {
        "schema": SUMMARY.PREVIEW_HEALTH_SCHEMA,
        "url": "http://127.0.0.1:18070/web/login?db=test",
        "ok": True,
        "status_code": 200,
    }


def preview_module_payload() -> dict:
    return {
        "schema": SUMMARY.PREVIEW_MODULE_SCHEMA,
        "database": "test",
        "expected_version": "19.0.1.130.0",
        "ok": True,
        "module_installed_version": "19.0.1.130.0",
        "country_pack_version": "19.0.1.130.0",
    }


def real_data_closed_loop_payload() -> dict:
    return {
        "schema": SUMMARY.REAL_DATA_CLOSED_LOOP_SCHEMA,
        "database": "test",
        "expected_version": "19.0.1.130.0",
        "ok": True,
        "readiness": {
            "demo_ready": True,
            "closed_loop_evidence_ready": True,
        },
    }


def delivery_status(signoff_validation: dict | None = None) -> dict:
    return SUMMARY._status(
        bundle_metadata=bundle_metadata_payload(),
        manifest=manifest_payload(),
        summary=summary_payload(),
        preview_health=preview_health_payload(),
        preview_module=preview_module_payload(),
        real_data_closed_loop=real_data_closed_loop_payload(),
        signoff_validation=signoff_validation,
        preview_url="http://127.0.0.1:18070/web/login?db=test",
    )


def complete_evidence(packet: dict, deployment_decision: str = "deploy") -> dict:
    decisions = []
    for action in packet["production_actions"]:
        decisions.append(
            {
                "key": action["key"],
                "decision": (
                    deployment_decision
                    if action["key"] == "production_deployment_decision"
                    else action["acceptable_decisions"][0]
                ),
                "reviewer": "Reviewer",
                "date": "2026-07-17",
                "evidence_reference": "controlled evidence reference",
            }
        )
    return {
        "schema": VALIDATION.EVIDENCE_SCHEMA,
        "version": packet["version"],
        "source_commit": packet["source_commit"],
        "decisions": decisions,
        "limitations": [],
    }


class TestChinaSignoffValidation(unittest.TestCase):
    def test_complete_signoff_evidence_allows_production_gate(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet)

        result = VALIDATION._validate(packet, evidence)

        self.assertTrue(result["ok"])
        self.assertTrue(result["production_signoff_ready"])
        self.assertEqual(result["deployment_decision"], "deploy")
        self.assertEqual(result["blockers"], [])

    def test_missing_human_decision_blocks_production_gate(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet)
        evidence["decisions"] = evidence["decisions"][:-1]

        result = VALIDATION._validate(packet, evidence)

        self.assertFalse(result["ok"])
        self.assertFalse(result["production_signoff_ready"])
        self.assertIn(
            "production_deployment_decision: decision is missing",
            result["blockers"],
        )

    def test_source_commit_mismatch_blocks_production_gate(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet)
        evidence["source_commit"] = "different"

        result = VALIDATION._validate(packet, evidence)

        self.assertFalse(result["ok"])
        self.assertIn(
            "sign-off evidence source commit does not match the packet",
            result["blockers"],
        )

    def test_deploy_with_limitations_requires_recorded_limitations(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet, deployment_decision="deploy_with_limitations")

        result = VALIDATION._validate(packet, evidence)

        self.assertFalse(result["ok"])
        self.assertIn(
            "deploy_with_limitations requires limitations to be recorded",
            result["blockers"],
        )

        evidence_with_limitations = deepcopy(evidence)
        evidence_with_limitations["limitations"] = ["Known limitation approved."]
        result = VALIDATION._validate(packet, evidence_with_limitations)

        self.assertTrue(result["ok"])
        self.assertEqual(
            result["warnings"],
            ["production deployment is approved with documented limitations"],
        )

    def test_blocked_automated_packet_evidence_blocks_production_gate(self):
        payload = status_payload()
        payload["runtime_passed"] = False
        payload["runtime"]["log"]["failed"] = 1
        packet = PACKET._build_packet(payload)
        evidence = complete_evidence(packet)

        result = VALIDATION._validate(packet, evidence)

        self.assertFalse(result["ok"])
        self.assertIn(
            "automated packet evidence is not ready: runtime_passed",
            result["blockers"],
        )

    def test_delivery_status_requires_signoff_validation_for_production_ready(self):
        status = delivery_status()

        readiness = status["readiness_gates"]
        self.assertTrue(readiness["business_uat_ready"])
        self.assertFalse(readiness["production_signoff_ready"])
        self.assertIn(
            "business UAT decision must be recorded outside this automated status",
            readiness["production_signoff_blockers"],
        )

    def test_delivery_status_accepts_valid_signoff_validation(self):
        packet = PACKET._build_packet(status_payload())
        validation = VALIDATION._validate(packet, complete_evidence(packet))

        status = delivery_status(validation)

        readiness = status["readiness_gates"]
        self.assertTrue(readiness["business_uat_ready"])
        self.assertTrue(readiness["production_signoff_ready"])
        self.assertEqual(readiness["production_signoff_blockers"], [])
        self.assertEqual(status["signoff_validation"]["deployment_decision"], "deploy")

    def test_delivery_status_rejects_mismatched_signoff_validation_version(self):
        packet = PACKET._build_packet(status_payload())
        validation = VALIDATION._validate(packet, complete_evidence(packet))
        validation["version"] = "19.0.1.999.0"

        status = delivery_status(validation)

        readiness = status["readiness_gates"]
        self.assertFalse(readiness["production_signoff_ready"])
        self.assertIn(
            "sign-off validation version does not match delivery version",
            readiness["production_signoff_blockers"],
        )


if __name__ == "__main__":
    unittest.main()
