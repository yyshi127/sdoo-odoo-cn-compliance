from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools import select_cn_latest_signoff_candidate as selector


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class TestLatestSignoffCandidate(unittest.TestCase):
    def test_selects_highest_complete_consistent_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            dist = Path(temp)
            _candidate(dist, 7, commit="abc", aggregate="hash7")
            _candidate(dist, 8, commit="def", aggregate="hash8")

            result = selector.select_latest(dist)

            self.assertEqual(result["schema"], selector.SCHEMA)
            self.assertEqual(result["selected"]["candidate"], "m8")
            self.assertTrue(result["selected"]["ok"])
            self.assertEqual(result["selected"]["preview_database"], "test")
            self.assertEqual(
                result["selected"]["production_required_action_keys"],
                ["business_uat_decision"],
            )
            self.assertEqual(
                result["selected"]["production_signoff_blockers"],
                ["business UAT decision must be recorded outside this automated status"],
            )
            self.assertEqual(
                set(result["selected"]["evidence_sha256"]),
                {
                    "bundle",
                    "bundle_metadata",
                    "manifest",
                    "remote_acceptance",
                    "remote_upgrade_acceptance",
                    "preview_health",
                    "preview_module",
                    "real_data_closed_loop",
                    "status",
                    "signoff_packet",
                    "production_signoff_actions",
                    "production_signoff_actions_markdown",
                    "objective_audit",
                },
            )
            self.assertTrue(
                all(
                    len(value) == 64
                    for value in result["selected"]["evidence_sha256"].values()
                )
            )

    def test_markdown_summary_points_reviewers_to_actions_and_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            dist = Path(temp)
            _candidate(dist, 17, commit="abc", aggregate="hash17")
            result = selector.select_latest(dist)
            output = dist / "latest.md"

            selector._write_markdown(result, output)

            content = output.read_text(encoding="utf-8")
            self.assertIn("Production sign-off action checklist:", content)
            self.assertIn("Preview database: `test`", content)
            self.assertIn("cn_delivery_m17_chain_production_signoff_actions.md", content)
            self.assertIn("## Evidence SHA-256", content)
            self.assertIn("`remote_acceptance`", content)
            self.assertIn("`remote_upgrade_acceptance`", content)
            self.assertIn("`production_signoff_actions_markdown`", content)
            self.assertIn("## Required Action Keys", content)
            self.assertIn("`business_uat_decision`", content)
            self.assertIn("## Production Sign-off Blockers", content)
            self.assertIn(
                "business UAT decision must be recorded outside this automated status",
                content,
            )

    def test_skips_incomplete_newer_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            dist = Path(temp)
            _candidate(dist, 7, commit="abc", aggregate="hash7")
            _candidate(dist, 8, commit="def", aggregate="hash8", omit="preview_health")

            result = selector.select_latest(dist)

            self.assertEqual(result["selected"]["candidate"], "m7")
            self.assertFalse(result["checked_candidates"][0]["ok"])
            self.assertIn(
                "candidate evidence set is incomplete",
                result["checked_candidates"][0]["errors"],
            )

    def test_strict_mode_rejects_incomplete_newer_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            dist = Path(temp)
            _candidate(dist, 7, commit="abc", aggregate="hash7")
            _candidate(dist, 8, commit="def", aggregate="hash8", omit="preview_health")

            result = selector.select_latest(dist, require_highest_status_complete=True)

            self.assertIsNone(result["selected"])
            self.assertIn("refusing to select older m7", result["errors"][0])

    def test_rejects_commit_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            dist = Path(temp)
            _candidate(dist, 9, commit="abc", aggregate="hash9", packet_commit="wrong")

            result = selector.select_latest(dist)

            self.assertIsNone(result["selected"])
            self.assertIn("sign-off packet commit mismatch", result["checked_candidates"][0]["errors"][0])

    def test_rejects_preview_database_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            dist = Path(temp)
            _candidate(
                dist,
                18,
                commit="abc",
                aggregate="hash18",
                packet_preview_database="other",
            )

            result = selector.select_latest(dist)

            self.assertIsNone(result["selected"])
            self.assertIn(
                "sign-off packet preview database mismatch: 'other' != 'test'",
                result["checked_candidates"][0]["errors"],
            )

    def test_rejects_objective_audit_without_preview_database(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            dist = Path(temp)
            _candidate(
                dist,
                19,
                commit="abc",
                aggregate="hash19",
                audit_preview_database=None,
            )

            result = selector.select_latest(dist)

            self.assertIsNone(result["selected"])
            self.assertIn(
                "objective audit preview database mismatch: None != 'test'",
                result["checked_candidates"][0]["errors"],
            )

    def test_accepts_remote_summary_without_manifest_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            dist = Path(temp)
            _candidate(dist, 10, commit="abc", aggregate="hash10", omit_summary_manifest=True)

            result = selector.select_latest(dist)

            self.assertEqual(result["selected"]["candidate"], "m10")

    def test_rejects_action_checklist_packet_binding_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            dist = Path(temp)
            _candidate(
                dist,
                11,
                commit="abc",
                aggregate="hash11",
                action_binding_ok=False,
            )

            result = selector.select_latest(dist)

            self.assertIsNone(result["selected"])
            self.assertIn(
                "action checklist packet binding action_keys_match is not true",
                result["checked_candidates"][0]["errors"],
            )

    def test_rejects_signoff_packet_bundle_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            dist = Path(temp)
            _candidate(
                dist,
                20,
                commit="abc",
                aggregate=_sha("manifest20"),
                packet_bundle_sha256=_sha("wrong-bundle"),
            )

            result = selector.select_latest(dist)

            self.assertIsNone(result["selected"])
            self.assertTrue(
                any(
                    error.startswith("sign-off packet bundle SHA-256 mismatch")
                    for error in result["checked_candidates"][0]["errors"]
                )
            )

    def test_rejects_action_checklist_manifest_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            dist = Path(temp)
            _candidate(
                dist,
                21,
                commit="abc",
                aggregate=_sha("manifest21"),
                actions_manifest_aggregate_sha256=_sha("wrong-manifest"),
            )

            result = selector.select_latest(dist)

            self.assertIsNone(result["selected"])
            self.assertTrue(
                any(
                    error.startswith("action checklist manifest aggregate SHA-256 mismatch")
                    for error in result["checked_candidates"][0]["errors"]
                )
            )

    def test_rejects_action_checklist_hash_binding_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            dist = Path(temp)
            _candidate(
                dist,
                22,
                commit="abc",
                aggregate=_sha("manifest22"),
                action_bundle_binding_ok=False,
            )

            result = selector.select_latest(dist)

            self.assertIsNone(result["selected"])
            self.assertIn(
                "action checklist packet binding bundle_sha256_matches_status is not true",
                result["checked_candidates"][0]["errors"],
            )

    def test_rejects_missing_reviewer_action_checklist_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            dist = Path(temp)
            _candidate(
                dist,
                12,
                commit="abc",
                aggregate="hash12",
                omit="production_signoff_actions_markdown",
            )

            result = selector.select_latest(dist)

            self.assertIsNone(result["selected"])
            self.assertIn(
                "candidate evidence set is incomplete",
                result["checked_candidates"][0]["errors"],
            )
            self.assertTrue(
                any(
                    missing.endswith(
                        "cn_delivery_m12_chain_production_signoff_actions.md"
                    )
                    for missing in result["checked_candidates"][0]["missing_files"]
                )
            )

    def test_rejects_reviewer_action_checklist_without_action_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            dist = Path(temp)
            _candidate(
                dist,
                13,
                commit="abc",
                aggregate="hash13",
                action_markdown="# checklist without keys\n",
            )

            result = selector.select_latest(dist)

            self.assertIsNone(result["selected"])
            self.assertIn(
                "reviewer action checklist markdown missing action keys: business_uat_decision",
                result["checked_candidates"][0]["errors"],
            )

    def test_rejects_reviewer_action_checklist_without_signoff_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            dist = Path(temp)
            _candidate(
                dist,
                14,
                commit="abc",
                aggregate="hash14",
                action_markdown=(
                    "# checklist\n\n"
                    "### business_uat_decision\n\n"
                    "- Owner: `business_reviewer`\n"
                    "- Acceptable decisions: `accepted, accepted_with_limitations`\n"
                    "- Required evidence: Completed checklist.\n"
                    "- Reviewer:\n"
                    "- Decision:\n"
                ),
            )

            result = selector.select_latest(dist)

            self.assertIsNone(result["selected"])
            self.assertIn(
                "reviewer action checklist markdown incomplete sections: "
                "business_uat_decision missing - Date:, - Evidence reference:, - Notes:",
                result["checked_candidates"][0]["errors"],
            )

    def test_rejects_reviewer_action_checklist_when_values_do_not_match_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            dist = Path(temp)
            _candidate(
                dist,
                16,
                commit="abc",
                aggregate="hash16",
                action_markdown=(
                    "# checklist\n\n"
                    "### business_uat_decision\n\n"
                    "- Owner: `wrong_owner`\n"
                    "- Acceptable decisions: `accepted, accepted_with_limitations`\n"
                    "- Required evidence: Completed checklist.\n"
                    "- Reviewer:\n"
                    "- Decision:\n"
                    "- Date:\n"
                    "- Evidence reference:\n"
                    "- Notes:\n"
                ),
            )

            result = selector.select_latest(dist)

            self.assertIsNone(result["selected"])
            self.assertIn(
                "reviewer action checklist markdown does not match JSON actions: "
                "business_uat_decision mismatch owner",
                result["checked_candidates"][0]["errors"],
            )

    def test_rejects_reviewer_action_checklist_without_owner_or_evidence_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            dist = Path(temp)
            _candidate(
                dist,
                15,
                commit="abc",
                aggregate="hash15",
                action_markdown=(
                    "# checklist\n\n"
                    "### business_uat_decision\n\n"
                    "- Reviewer:\n"
                    "- Decision:\n"
                    "- Date:\n"
                    "- Evidence reference:\n"
                    "- Notes:\n"
                ),
            )

            result = selector.select_latest(dist)

            self.assertIsNone(result["selected"])
            self.assertIn(
                "reviewer action checklist markdown incomplete sections: "
                "business_uat_decision missing - Owner:, - Acceptable decisions:, - Required evidence:",
                result["checked_candidates"][0]["errors"],
            )


def _candidate(
    dist: Path,
    number: int,
    *,
    commit: str,
    aggregate: str,
    packet_commit: str | None = None,
    packet_preview_database: str | None = "test",
    actions_preview_database: str | None = "test",
    audit_preview_database: str | None = "test",
    omit: str | None = None,
    omit_summary_manifest: bool = False,
    action_binding_ok: bool = True,
    action_bundle_binding_ok: bool = True,
    action_manifest_binding_ok: bool = True,
    packet_bundle_sha256: str | None = None,
    packet_manifest_aggregate_sha256: str | None = None,
    actions_bundle_sha256: str | None = None,
    actions_manifest_aggregate_sha256: str | None = None,
    action_markdown: str = (
        "# checklist\n\n"
        "### business_uat_decision\n\n"
        "- Owner: `business_reviewer`\n"
        "- Acceptable decisions: `accepted, accepted_with_limitations`\n"
        "- Required evidence: Completed checklist.\n"
        "- Reviewer:\n"
        "- Decision:\n"
        "- Date:\n"
        "- Evidence reference:\n"
        "- Notes:\n"
    ),
) -> None:
    paths = selector._candidate_paths(dist, number)
    tag = f"m{number}"
    source_control = {
        "branch": "main",
        "commit": commit,
        "dirty": False,
        "inside_worktree": True,
    }
    manifest = {
        "schema": "sdoo.cn.delivery-manifest.v1",
        "addon": "sudo_country_pack_cn",
        "version": "19.0.1.130.0",
        "git_commit": commit,
        "source_control": source_control,
        "file_count": 1,
        "aggregate_sha256": aggregate,
        "files": [],
    }
    bundle = {
        "schema": "sdoo.cn.delivery-bundle.v1",
        "addon": "sudo_country_pack_cn",
        "version": "19.0.1.130.0",
        "git_commit": commit,
        "source_control": source_control,
        "file_count": 1,
        "aggregate_sha256": aggregate,
        "bundle_sha256": _sha(f"bundle-{tag}"),
        "files": [],
    }
    bundle_sha256 = bundle["bundle_sha256"]
    acceptance = {
        "schema": "sdoo.cn.delivery-acceptance-summary.v1",
        "addon": "sudo_country_pack_cn",
        "version": "19.0.1.130.0",
        "result": "passed",
        "runtime": {"log": {"failed": 0, "errors": 0}},
    }
    if not omit_summary_manifest:
        acceptance["manifest"] = {
            "version": "19.0.1.130.0",
            "file_count": 1,
            "aggregate_sha256": aggregate,
        }
    status = {
        "schema": "sdoo.cn.delivery-status.v1",
        "version": "19.0.1.130.0",
        "source_control": source_control,
        "preview_database": "test",
        "readiness_gates": {
            "preview_ready": True,
            "compliance_scope_ready": True,
            "business_uat_ready": True,
            "production_signoff_ready": False,
            "production_signoff_blockers": [
                "business UAT decision must be recorded outside this automated status"
            ],
            "production_signoff_required_actions": [{"key": "business_uat_decision"}],
        },
    }
    packet = {
        "schema": "sdoo.cn.signoff-packet.v1",
        "version": "19.0.1.130.0",
        "source_commit": packet_commit or commit,
        "preview_database": packet_preview_database,
        "bundle_sha256": packet_bundle_sha256 or bundle_sha256,
        "manifest_aggregate_sha256": packet_manifest_aggregate_sha256 or aggregate,
    }
    actions = {
        "schema": "sdoo.cn.production-signoff-actions.v1",
        "version": "19.0.1.130.0",
        "source_commit": commit,
        "preview_url": None,
        "preview_database": actions_preview_database,
        "bundle_sha256": actions_bundle_sha256 or bundle_sha256,
        "manifest_aggregate_sha256": actions_manifest_aggregate_sha256 or aggregate,
        "production_signoff_ready": False,
        "action_count": 1,
        "actions": [
            {
                "key": "business_uat_decision",
                "owner": "business_reviewer",
                "acceptable_decisions": [
                    "accepted",
                    "accepted_with_limitations",
                ],
                "required_evidence": "Completed checklist.",
            }
        ],
        "packet_binding": {
            "provided": True,
            "schema_ok": True,
            "version_matches_status": True,
            "source_commit_matches_status": True,
            "bundle_sha256_matches_status": action_bundle_binding_ok,
            "manifest_aggregate_sha256_matches_status": action_manifest_binding_ok,
            "preview_url_matches_status": True,
            "preview_database_matches_status": True,
            "action_keys_match": action_binding_ok,
        },
    }
    audit = {
        "schema": "sdoo.cn.objective-audit.v1",
        "version": "19.0.1.130.0",
        "preview_database": audit_preview_database,
    }
    payloads: dict[str, object] = {
        "bundle": b"bundle",
        "bundle_metadata": bundle,
        "manifest": manifest,
        "remote_acceptance": acceptance,
        "remote_upgrade_acceptance": acceptance,
        "preview_health": {"ok": True},
        "preview_module": {"ok": True},
        "real_data_closed_loop": {"ok": True},
        "status": status,
        "signoff_packet": packet,
        "production_signoff_actions": actions,
        "production_signoff_actions_markdown": action_markdown.encode("utf-8"),
        "objective_audit": audit,
    }
    for field, payload in payloads.items():
        if field == omit:
            continue
        path = getattr(paths, field)
        if isinstance(payload, bytes):
            path.write_bytes(payload)
        else:
            _write(path, payload)


def _sha(seed: str) -> str:
    return (seed.encode("utf-8").hex() * 64)[:64]


if __name__ == "__main__":
    unittest.main()
