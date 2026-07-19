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


def _candidate(
    dist: Path,
    number: int,
    *,
    commit: str,
    aggregate: str,
    packet_commit: str | None = None,
    omit: str | None = None,
    omit_summary_manifest: bool = False,
    action_binding_ok: bool = True,
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
        "bundle_sha256": f"bundle-{tag}",
        "files": [],
    }
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
        "readiness_gates": {
            "preview_ready": True,
            "compliance_scope_ready": True,
            "business_uat_ready": True,
            "production_signoff_ready": False,
            "production_signoff_required_actions": [{"key": "business_uat_decision"}],
        },
    }
    packet = {
        "schema": "sdoo.cn.signoff-packet.v1",
        "version": "19.0.1.130.0",
        "source_commit": packet_commit or commit,
    }
    actions = {
        "schema": "sdoo.cn.production-signoff-actions.v1",
        "version": "19.0.1.130.0",
        "source_commit": commit,
        "preview_url": None,
        "production_signoff_ready": False,
        "action_count": 1,
        "actions": [{"key": "business_uat_decision"}],
        "packet_binding": {
            "provided": True,
            "schema_ok": True,
            "version_matches_status": True,
            "source_commit_matches_status": True,
            "preview_url_matches_status": True,
            "action_keys_match": action_binding_ok,
        },
    }
    audit = {
        "schema": "sdoo.cn.objective-audit.v1",
        "version": "19.0.1.130.0",
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


if __name__ == "__main__":
    unittest.main()
