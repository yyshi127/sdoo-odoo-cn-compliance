import hashlib
from datetime import timedelta
from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


DOWNLOAD_PATCH = (
    "odoo.addons.sudo_global_finance.models.authority_source."
    "SudoComplianceAuthoritySource._download_official_snapshot"
)


@tagged("post_install", "-at_install")
class TestChinaOfficialSourceMonitoring(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.country = cls.env.ref("base.cn")
        cls.author = new_test_user(
            cls.env,
            login="cn_source_monitor_author",
            groups=(
                "base.group_user,"
                "sudo_global_finance.group_compliance_rule_author"
            ),
        )
        cls.approver = new_test_user(
            cls.env,
            login="cn_source_monitor_approver",
            groups=(
                "base.group_user,"
                "sudo_global_finance.group_compliance_rule_approver"
            ),
        )
        cls.reader = new_test_user(
            cls.env,
            login="cn_source_monitor_reader",
            groups=(
                "base.group_user,"
                "sudo_global_finance.group_compliance_user"
            ),
        )
        cls.Source = cls.env["sudo.compliance.authority.source"]
        cls.Run = cls.env["sudo.cn.authority.source.monitor.run"]

    def _valid_source(self, suffix, content=None, monitor_enabled=False):
        content = content or f"approved source {suffix}".encode()
        source = self.Source.with_user(self.author).with_context(
            lang="en_US"
        ).create(
            {
                "name": f"China source monitor {suffix}",
                "country_id": self.country.id,
                "authority": "Test China authority",
                "source_type": "tax_guide",
                "snapshot_kind": "official_web_capture",
                "official_url": f"https://example.com/cn-source/{suffix}",
                "official_version": "TEST-2026.1",
                "published_date": "2026-01-01",
                "next_review_date": "2027-12-31",
                "cn_monitor_enabled": monitor_enabled,
                "cn_monitor_interval_days": 30,
            }
        )
        attachment = self.env["ir.attachment"].with_user(self.author).create(
            {
                "name": f"cn-source-monitor-{suffix}.html",
                "raw": content,
                "mimetype": "text/html",
                "res_model": source._name,
                "res_id": source.id,
            }
        )
        source.write({"snapshot_attachment_id": attachment.id})
        source.action_compute_hash()
        source.action_submit_review()
        source.with_user(self.approver).action_approve()
        return self.Source.browse(source.id)

    def _capture(self, source, content):
        return {
            "content": content,
            "content_type": "text/html",
            "etag": '"test-etag"',
            "final_url": source.official_url,
            "http_status": 200,
            "last_modified": "Wed, 15 Jul 2026 00:00:00 GMT",
        }

    def _queue(self, source, lang="en_US"):
        return self.Run.with_user(self.author).with_context(lang=lang).enqueue(
            source.with_user(self.author).with_context(lang=lang),
            request_kind="manual",
        )

    def _process_with_capture(self, run, capture):
        with patch(DOWNLOAD_PATCH, return_value=capture):
            run.with_user(self.author).with_context(
                lang="en_US"
            ).action_process_now()
        return self.Run.browse(run.id)

    def test_packaged_candidates_remain_draft_and_unmonitored(self):
        model_data = self.env["ir.model.data"].search(
            [
                ("module", "=", "sudo_country_pack_cn"),
                ("model", "=", "sudo.compliance.authority.source"),
                ("name", "like", "source_cn_%_candidate"),
            ]
        )
        sources = self.Source.browse(model_data.mapped("res_id"))

        self.assertEqual(len(sources), 12)
        self.assertEqual(set(sources.mapped("status")), {"draft"})
        self.assertFalse(any(sources.mapped("snapshot_attachment_id")))
        self.assertFalse(any(sources.mapped("content_hash")))
        self.assertFalse(any(sources.mapped("cn_monitor_enabled")))
        self.assertFalse(self.Run.search_count([("source_id", "in", sources.ids)]))

    def test_monitor_runs_are_controlled_immutable_audit_records(self):
        source = self._valid_source("immutable")
        with self.assertRaises(AccessError):
            self.Run.with_user(self.author).create(
                {
                    "source_id": source.id,
                    "request_kind": "manual",
                    "baseline_content_hash": source.content_hash,
                    "source_snapshot_checksum": "0" * 64,
                }
            )

        run = self._queue(source)
        with self.assertRaises(AccessError):
            run.with_user(self.author).write({"state": "failed"})
        with self.assertRaises(AccessError):
            run.with_user(self.author).unlink()
        with self.assertRaises(AccessError):
            run.with_user(self.author).copy()

        run.with_user(self.author).action_cancel()
        run = self.Run.browse(run.id)
        self.assertEqual(run.state, "cancelled")
        self.assertEqual(run.result_integrity_state, "verified")

    def test_configuration_permissions_and_baseline_scope_are_enforced(self):
        source = self._valid_source("configuration")
        with self.assertRaises(AccessError):
            source.with_user(self.reader).write({"cn_monitor_enabled": True})
        with self.assertRaises(ValidationError):
            source.with_user(self.author).write(
                {"cn_monitor_interval_days": 0}
            )

        draft = self.Source.with_user(self.author).create(
            {
                "name": "Unapproved China source",
                "country_id": self.country.id,
                "authority": "Test China authority",
                "source_type": "tax_guide",
                "official_url": "https://example.com/unapproved-cn-source",
                "next_review_date": "2027-12-31",
            }
        )
        with self.assertRaisesRegex(UserError, "当前有效"):
            self.Run.with_user(self.author).enqueue(
                draft,
                request_kind="manual",
            )

        with self.assertRaises(ValidationError):
            self.Source.with_user(self.author).create(
                {
                    "name": "Non-China monitored source",
                    "country_id": self.env.ref("base.us").id,
                    "authority": "Test authority",
                    "source_type": "tax_guide",
                    "official_url": "https://example.com/non-cn-source",
                    "next_review_date": "2027-12-31",
                    "cn_monitor_enabled": True,
                }
            )

    def test_unchanged_remote_content_preserves_approved_source(self):
        content = b"approved unchanged official source"
        source = self._valid_source(
            "unchanged",
            content=content,
            monitor_enabled=True,
        )
        original_attachment = source.snapshot_attachment_id
        original_hash = source.content_hash
        run = self._queue(source, lang="en_US")

        run = self._process_with_capture(
            run,
            self._capture(source, content),
        )
        source = self.Source.browse(source.id)

        self.assertEqual(run.state, "unchanged")
        self.assertEqual(run.result_integrity_state, "verified")
        self.assertEqual(run.remote_content_hash, original_hash)
        self.assertFalse(run.candidate_source_id)
        self.assertEqual(source.status, "valid")
        self.assertEqual(source.snapshot_attachment_id, original_attachment)
        self.assertEqual(source.content_hash, original_hash)
        self.assertEqual(source.cn_last_monitor_state, "unchanged")
        self.assertEqual(source.cn_latest_monitor_run_id, run)
        self.assertEqual(
            source.cn_next_monitor_date,
            fields.Date.context_today(source) + timedelta(days=30),
        )
        self.assertEqual(
            self.env["sudo.compliance.audit.event"].search_count(
                [
                    ("event_key", "=", "cn.authority_source_monitor.unchanged"),
                    ("model_name", "=", run._name),
                    ("record_id", "=", run.id),
                ]
            ),
            1,
        )

    def test_changed_content_creates_draft_and_snapshots_rule_impact(self):
        original = b"approved original source"
        changed = b"changed remote source"
        source = self._valid_source(
            "changed",
            content=original,
            monitor_enabled=True,
        )
        original_attachment = source.snapshot_attachment_id
        original_hash = source.content_hash
        rule = self.env["sudo.compliance.rule"].with_user(self.author).create(
            {
                "name": "Source impact runtime test",
                "code": "CN-TEST-SOURCE-MONITOR-IMPACT",
                "country_id": self.country.id,
                "domain_key": "CN.TEST.SOURCE_MONITOR",
                "cn_rule_nature": "internal_control",
            }
        )
        version = self.env["sudo.compliance.rule.version"].with_user(
            self.author
        ).create(
            {
                "rule_id": rule.id,
                "version": "TEST-2026.1",
                "effective_from": "2026-01-01",
                "next_review_date": "2027-12-31",
                "evaluator_type": "manual",
                "requires_human_review": True,
                "authority_source_ids": [Command.set(source.ids)],
            }
        )
        run = self._queue(source)

        run = self._process_with_capture(
            run,
            self._capture(source, changed),
        )
        source = self.Source.browse(source.id)
        candidate = run.candidate_source_id

        self.assertEqual(run.state, "changed")
        self.assertEqual(run.result_integrity_state, "verified")
        self.assertEqual(run.impacted_rule_version_ids, version)
        self.assertEqual(run.impacted_rule_count, 1)
        self.assertEqual(run.active_impacted_rule_count, 0)
        self.assertEqual(run.review_impacted_rule_count, 0)
        self.assertEqual(
            run.impact_snapshot_json["rule_versions"][0]["version_id"],
            version.id,
        )
        self.assertEqual(source.status, "change_detected")
        self.assertEqual(source.snapshot_attachment_id, original_attachment)
        self.assertEqual(source.content_hash, original_hash)
        self.assertFalse(source.cn_monitor_enabled)
        self.assertFalse(source.cn_next_monitor_date)
        self.assertEqual(source.cn_latest_change_candidate_id, candidate)
        self.assertEqual(candidate.status, "draft")
        self.assertEqual(candidate.cn_monitor_predecessor_id, source)
        self.assertEqual(candidate.snapshot_attachment_id.sudo().raw, changed)
        self.assertEqual(
            candidate.content_hash,
            hashlib.sha256(changed).hexdigest(),
        )
        self.assertFalse(candidate.official_version)
        self.assertFalse(candidate.published_date)
        self.assertEqual(version.state, "draft")
        self.assertEqual(version.professional_review_state, "pending")
        self.assertEqual(version.authority_source_ids, source)
        self.assertEqual(run.candidate_integrity_state, "verified")

        candidate.snapshot_attachment_id.sudo().write({"raw": b"tampered"})
        run.invalidate_recordset()
        self.assertEqual(run.candidate_integrity_state, "changed")

    def test_network_failure_does_not_claim_source_is_unchanged(self):
        source = self._valid_source("network-failure", monitor_enabled=True)
        original_hash = source.content_hash
        run = self._queue(source)

        with patch(DOWNLOAD_PATCH, side_effect=UserError("remote unavailable")):
            run.with_user(self.author).action_process_now()
        run = self.Run.browse(run.id)
        source = self.Source.browse(source.id)

        self.assertEqual(run.state, "failed")
        self.assertEqual(run.error_code, "SOURCE_MONITOR_INPUT_ERROR")
        self.assertIn("remote unavailable", run.error_message)
        self.assertEqual(run.result_integrity_state, "verified")
        self.assertEqual(source.status, "valid")
        self.assertEqual(source.content_hash, original_hash)
        self.assertFalse(run.candidate_source_id)
        self.assertEqual(source.cn_last_monitor_state, "failed")
        self.assertEqual(
            source.cn_next_monitor_date,
            fields.Date.context_today(source) + timedelta(days=7),
        )

    def test_duplicate_open_run_is_rejected(self):
        source = self._valid_source("duplicate")
        run = self._queue(source)

        with self.assertRaisesRegex(UserError, "已有待检查"):
            self._queue(source)

        run.with_user(self.author).action_cancel()

    def test_approved_snapshot_tampering_quarantines_source(self):
        source = self._valid_source(
            "baseline-tamper",
            monitor_enabled=True,
        )
        run = self._queue(source)
        source.snapshot_attachment_id.sudo().write({"raw": b"tampered baseline"})

        with patch(DOWNLOAD_PATCH) as downloader:
            run.with_user(self.author).action_process_now()
        downloader.assert_not_called()
        run = self.Run.browse(run.id)
        source = self.Source.browse(source.id)

        self.assertEqual(run.state, "failed")
        self.assertEqual(run.error_code, "SOURCE_BASELINE_INTEGRITY_ERROR")
        self.assertEqual(run.result_integrity_state, "verified")
        self.assertEqual(source.status, "change_detected")
        self.assertFalse(source.cn_monitor_enabled)
        self.assertFalse(source.cn_next_monitor_date)
        self.assertEqual(source.cn_last_monitor_state, "failed")

    def test_cron_only_queues_due_valid_enabled_sources(self):
        today = fields.Date.context_today(self.Run)
        due = self._valid_source("cron-due", monitor_enabled=True)
        future = self._valid_source("cron-future", monitor_enabled=True)
        future.with_user(self.author).write(
            {"cn_next_monitor_date": today + timedelta(days=30)}
        )
        self.Source.with_user(self.author).create(
            {
                "name": "Draft monitored source",
                "country_id": self.country.id,
                "authority": "Test China authority",
                "source_type": "tax_guide",
                "official_url": "https://example.com/draft-monitored-source",
                "next_review_date": "2027-12-31",
                "cn_monitor_enabled": True,
                "cn_next_monitor_date": today,
            }
        )

        self.assertEqual(self.Run._cron_enqueue_due_sources(limit=20), 1)
        queued = self.Run.search([("state", "=", "queued")])
        self.assertEqual(queued.source_id, due)
        self.assertEqual(queued.request_kind, "scheduled")
        self.assertNotEqual(queued.source_id, future)

    def test_scheduled_request_cannot_be_spoofed(self):
        source = self._valid_source("scheduled-spoof")

        with self.assertRaisesRegex(AccessError, "系统任务"):
            self.Run.with_user(self.author).with_context(
                cn_source_monitor_schedule=True
            ).enqueue(source.with_user(self.author), request_kind="scheduled")
        with self.assertRaisesRegex(AccessError, "系统任务"):
            self.Run.enqueue(source, request_kind="scheduled")

    def test_frozen_snapshot_tampering_breaks_result_integrity(self):
        content = b"source snapshot integrity"
        source = self._valid_source("result-integrity", content=content)
        run = self._process_with_capture(
            self._queue(source),
            self._capture(source, content),
        )
        self.assertEqual(run.result_integrity_state, "verified")

        run._transition_write({"impact_snapshot_json": {"tampered": True}})
        run.invalidate_recordset()
        self.assertEqual(run.result_integrity_state, "checksum_mismatch")
