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
ADDON_VALIDATION = load_tool(
    "cn_addon_validation",
    REPOSITORY_ROOT / "tools" / "validate_addon.py",
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
        "tools/validate_cn_signoff_evidence.py",
    ]
    return {
        "schema": "sdoo.cn.delivery-manifest.v1",
        "version": "19.0.1.130.0",
        "aggregate_sha256": "aggregate",
        "files": [{"path": path} for path in paths],
    }


def manifest_without(path_to_remove: str) -> dict:
    manifest = manifest_payload()
    manifest["files"] = [
        item for item in manifest["files"] if item["path"] != path_to_remove
    ]
    return manifest


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


def delivery_status_with_manifest(manifest: dict) -> dict:
    return SUMMARY._status(
        bundle_metadata=bundle_metadata_payload(),
        manifest=manifest,
        summary=summary_payload(),
        preview_health=preview_health_payload(),
        preview_module=preview_module_payload(),
        real_data_closed_loop=real_data_closed_loop_payload(),
        signoff_validation=None,
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
                "reviewer": "Alice Zhang",
                "date": "2026-07-17",
                "evidence_reference": "SGN-2026-07-17-UAT-001",
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
    def test_objective_coverage_path_guard_accepts_real_paths_and_rejects_missing_paths(self):
        content = (
            "`models/risk_center.py` `views/*.xml` "
            "`tools/generate_cn_signoff_packet.py` `models/not_a_real_file.py`"
        )

        references = ADDON_VALIDATION._coverage_referenced_paths(content)

        self.assertIn("models/risk_center.py", references)
        self.assertIn("views/*.xml", references)
        self.assertIn("tools/generate_cn_signoff_packet.py", references)
        self.assertTrue(ADDON_VALIDATION._coverage_path_exists("models/risk_center.py"))
        self.assertTrue(ADDON_VALIDATION._coverage_path_exists("views/*.xml"))
        self.assertTrue(
            ADDON_VALIDATION._coverage_path_exists(
                "tools/generate_cn_signoff_packet.py"
            )
        )
        self.assertFalse(
            ADDON_VALIDATION._coverage_path_exists("models/not_a_real_file.py")
        )

    def test_complete_signoff_evidence_allows_production_gate(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet)

        result = VALIDATION._validate(packet, evidence)

        self.assertTrue(result["ok"])
        self.assertTrue(result["production_signoff_ready"])
        self.assertEqual(result["deployment_decision"], "deploy")
        self.assertEqual(result["blockers"], [])

    def test_signoff_packet_requires_representative_ux_walkthrough(self):
        packet = PACKET._build_packet(status_payload())

        actions = {
            action["key"]: action for action in packet["production_actions"]
        }

        self.assertIn("representative_ux_walkthrough", actions)
        self.assertEqual(
            actions["representative_ux_walkthrough"]["acceptable_decisions"],
            ["passed", "passed_with_limitations"],
        )
        self.assertIn(
            "risk level, cause, impact amount, period, owner, due date, status and next action visibility",
            actions["representative_ux_walkthrough"]["required_evidence"],
        )

    def test_missing_representative_ux_walkthrough_blocks_production_gate(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet)
        evidence["decisions"] = [
            item
            for item in evidence["decisions"]
            if item["key"] != "representative_ux_walkthrough"
        ]

        result = VALIDATION._validate(packet, evidence)

        self.assertFalse(result["ok"])
        self.assertFalse(result["production_signoff_ready"])
        self.assertIn(
            "representative_ux_walkthrough: decision is missing",
            result["blockers"],
        )

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

    def test_duplicate_decision_key_blocks_production_gate(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet)
        evidence["decisions"].append(deepcopy(evidence["decisions"][0]))

        result = VALIDATION._validate(packet, evidence)

        self.assertFalse(result["ok"])
        self.assertFalse(result["production_signoff_ready"])
        self.assertIn(
            "sign-off evidence decision keys must be unique: business_uat_decision",
            result["blockers"],
        )

    def test_unknown_decision_key_blocks_production_gate(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet)
        evidence["decisions"].append(
            {
                "key": "uncontrolled_extra_approval",
                "decision": "approved",
                "reviewer": "Alice Zhang",
                "date": "2026-07-17",
                "evidence_reference": "SGN-2026-07-17-EXTRA-001",
            }
        )

        result = VALIDATION._validate(packet, evidence)

        self.assertFalse(result["ok"])
        self.assertIn(
            "sign-off evidence contains unknown decision keys: uncontrolled_extra_approval",
            result["blockers"],
        )

    def test_decisions_must_be_a_list(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet)
        evidence["decisions"] = {"business_uat_decision": "accepted"}

        result = VALIDATION._validate(packet, evidence)

        self.assertFalse(result["ok"])
        self.assertIn("sign-off evidence decisions must be a list", result["blockers"])
        self.assertIn(
            "business_uat_decision: decision is missing",
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

    def test_decision_rejects_invalid_date_format(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet)
        evidence["decisions"][0]["date"] = "17/07/2026"

        result = VALIDATION._validate(packet, evidence)

        self.assertFalse(result["ok"])
        self.assertIn(
            "business_uat_decision: date must be YYYY-MM-DD",
            result["blockers"],
        )

    def test_decision_rejects_template_placeholders(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet)
        evidence["decisions"][0]["reviewer"] = "Business reviewer name"
        evidence["decisions"][0]["date"] = "YYYY-MM-DD"
        evidence["decisions"][0]["evidence_reference"] = (
            "Path or document reference for completed CHINA_BUSINESS_UAT_CHECKLIST.md"
        )

        result = VALIDATION._validate(packet, evidence)

        self.assertFalse(result["ok"])
        self.assertIn(
            "business_uat_decision: reviewer is missing or still a template placeholder",
            result["blockers"],
        )
        self.assertIn(
            "business_uat_decision: date must be YYYY-MM-DD",
            result["blockers"],
        )
        self.assertIn(
            "business_uat_decision: evidence_reference is missing or still a template placeholder",
            result["blockers"],
        )

    def test_deploy_with_limitations_requires_recorded_limitations(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet, deployment_decision="deploy_with_limitations")

        result = VALIDATION._validate(packet, evidence)

        self.assertFalse(result["ok"])
        self.assertIn(
            "limitation decisions require at least one substantive limitation "
            "entry of 20 or more characters: production_deployment_decision",
            result["blockers"],
        )

        evidence_with_limitations = deepcopy(evidence)
        evidence_with_limitations["limitations"] = ["Known limitation approved."]
        result = VALIDATION._validate(packet, evidence_with_limitations)

        self.assertTrue(result["ok"])
        self.assertEqual(
            result["warnings"],
            [
                "production sign-off includes documented limitations: production_deployment_decision"
            ],
        )

    def test_limitation_decision_rejects_empty_short_or_malformed_limitations(self):
        packet = PACKET._build_packet(status_payload())
        evidence = complete_evidence(packet, deployment_decision="deploy_with_limitations")

        for malformed_limitations in ([""], ["too short"], "not-a-list", [123]):
            payload = deepcopy(evidence)
            payload["limitations"] = malformed_limitations
            result = VALIDATION._validate(packet, payload)

            self.assertFalse(result["ok"])
            self.assertIn(
                "limitation decisions require at least one substantive limitation "
                "entry of 20 or more characters: production_deployment_decision",
                result["blockers"],
            )

    def test_any_limitation_decision_requires_recorded_limitations(self):
        packet = PACKET._build_packet(status_payload())
        limitation_cases = {
            "business_uat_decision": "accepted_with_limitations",
            "china_tax_professional_rule_signoff": "approved_with_limitations",
            "official_source_freshness_review": "current_with_documented_limitations",
            "customer_scope_and_data_gap_review": "limitations_documented",
            "representative_ux_walkthrough": "passed_with_limitations",
        }
        evidence = complete_evidence(packet)
        for item in evidence["decisions"]:
            if item["key"] in limitation_cases:
                item["decision"] = limitation_cases[item["key"]]

        result = VALIDATION._validate(packet, evidence)

        self.assertFalse(result["ok"])
        self.assertIn(
            "limitation decisions require at least one substantive limitation "
            "entry of 20 or more characters: "
            "business_uat_decision, china_tax_professional_rule_signoff, "
            "official_source_freshness_review, customer_scope_and_data_gap_review, "
            "representative_ux_walkthrough",
            result["blockers"],
        )

        evidence_with_limitations = deepcopy(evidence)
        evidence_with_limitations["limitations"] = [
            "Business, professional, source, data and UX limitations are documented."
        ]
        result = VALIDATION._validate(packet, evidence_with_limitations)

        self.assertTrue(result["ok"])
        self.assertEqual(
            result["warnings"],
            [
                "production sign-off includes documented limitations: "
                "business_uat_decision, china_tax_professional_rule_signoff, "
                "official_source_freshness_review, customer_scope_and_data_gap_review, "
                "representative_ux_walkthrough"
            ],
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

    def test_delivery_status_rejects_mismatched_signoff_validation_source_commit(self):
        packet = PACKET._build_packet(status_payload())
        validation = VALIDATION._validate(packet, complete_evidence(packet))
        validation["source_commit"] = "different-commit"

        status = delivery_status(validation)

        readiness = status["readiness_gates"]
        self.assertFalse(readiness["production_signoff_ready"])
        self.assertIn(
            "sign-off validation source commit does not match delivery source commit",
            readiness["production_signoff_blockers"],
        )

    def test_delivery_status_rejects_mismatched_signoff_validation_preview_url(self):
        packet = PACKET._build_packet(status_payload())
        validation = VALIDATION._validate(packet, complete_evidence(packet))
        validation["preview_url"] = "http://127.0.0.1:18070/web/login?db=other"

        status = delivery_status(validation)

        readiness = status["readiness_gates"]
        self.assertFalse(readiness["production_signoff_ready"])
        self.assertIn(
            "sign-off validation preview URL does not match delivery preview URL",
            readiness["production_signoff_blockers"],
        )

    def test_delivery_status_requires_signoff_validator_in_manifest(self):
        status = delivery_status_with_manifest(
            manifest_without("tools/validate_cn_signoff_evidence.py")
        )

        readiness = status["readiness_gates"]
        self.assertFalse(readiness["business_uat_ready"])
        self.assertFalse(readiness["production_signoff_ready"])
        self.assertIn(
            "production sign-off evidence validator is not included in the manifest",
            readiness["business_uat_blockers"],
        )
        self.assertFalse(
            status["signoff_validation_tool"]["included_in_manifest"],
        )


if __name__ == "__main__":
    unittest.main()
