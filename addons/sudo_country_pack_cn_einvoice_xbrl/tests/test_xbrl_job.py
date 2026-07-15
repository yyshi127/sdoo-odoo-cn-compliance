from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import ChinaXbrlCommon


@tagged("post_install", "-at_install")
class TestChinaEinvoiceXbrlJob(ChinaXbrlCommon):
    def _enqueue(self, suffix="1"):
        dataset = self._dataset(suffix)
        taxonomy = self._taxonomy(suffix)
        job = self.env["sudo.cn.einvoice.xbrl.job"].with_company(
            self.company
        ).enqueue(
            dataset,
            dataset.source_attachment_ids[:1],
            taxonomy,
            timeout=300,
        )
        return job

    def test_installed_parser_capability_survives_base_metadata_write(self):
        country_pack = self.env.ref(
            "sudo_country_pack_cn.compliance_country_pack_cn"
        )
        capabilities = deepcopy(country_pack.capability_json)
        capabilities["features"]["einvoice_xbrl_parser"] = False

        country_pack.write({"capability_json": capabilities})

        self.assertTrue(
            country_pack.capability_json["features"][
                "einvoice_xbrl_parser"
            ]
        )

    def test_direct_job_creation_is_blocked(self):
        with self.assertRaises(AccessError):
            self.env["sudo.cn.einvoice.xbrl.job"].create({})

    def test_enqueue_creates_audited_run_and_prevents_duplicate_running_job(self):
        job = self._enqueue("queue")

        self.assertEqual(job.state, "queued")
        self.assertEqual(job.parse_run_id.state, "running")
        self.assertEqual(
            job.parse_run_id.parser_distribution,
            "arelle-release==2.42.1",
        )
        self.assertTrue(
            job.parse_run_id.parser_version.startswith(
                "19.0.1.1.0+arelle.2.42.1+"
            )
        )
        self.assertIn(
            "taxonomy.trim_role_uri_whitespace_v1",
            job.parse_run_id.parser_version,
        )
        with self.assertRaises(UserError):
            self.env["sudo.cn.einvoice.xbrl.job"].with_company(
                self.company
            ).enqueue(
                job.dataset_id,
                job.source_attachment_id,
                job.taxonomy_bundle_id,
                timeout=300,
            )

    def test_worker_environment_drops_uncontrolled_variables(self):
        job = self._enqueue("worker-environment")
        temporary = Path("/tmp/sdoo-cn-xbrl-worker-test")

        with patch.dict(
            "os.environ",
            {
                "PATH": "/usr/bin",
                "PYTHONPATH": "/uncontrolled/python/path",
                "SDOO_TEST_SECRET": "must-not-leak",
            },
            clear=False,
        ):
            environment = job._worker_environment(temporary)

        self.assertEqual(environment["PATH"], "/usr/bin")
        self.assertEqual(environment["HOME"], str(temporary))
        self.assertEqual(environment["TMPDIR"], str(temporary))
        self.assertEqual(environment["PYTHONNOUSERSITE"], "1")
        self.assertNotIn("PYTHONPATH", environment)
        self.assertNotIn("SDOO_TEST_SECRET", environment)

    def test_cron_claims_and_processes_queued_job(self):
        job = self._enqueue("cron")
        result = self._completed_result(job.parse_run_id, "cron")

        with patch.object(
            type(job),
            "_execute_worker",
            return_value=result,
        ):
            processed = self.env[
                "sudo.cn.einvoice.xbrl.job"
            ]._cron_process_jobs(limit=1)

        self.assertEqual(processed, 1)
        self.assertEqual(job.state, "succeeded")
        self.assertEqual(job.parse_run_id.state, "succeeded")
        self.assertEqual(job.parse_run_id.document_count, 1)

    def test_successful_worker_result_creates_current_normalized_ledger(self):
        job = self._enqueue("success")
        result = self._completed_result(job.parse_run_id, "success")

        with patch.object(
            type(job),
            "_execute_worker",
            return_value=result,
        ):
            processed = job._process()

        self.assertTrue(processed)
        self.assertEqual(job.state, "succeeded")
        self.assertEqual(job.parse_run_id.state, "succeeded")
        self.assertEqual(job.parse_run_id.document_count, 1)
        self.assertEqual(job.parse_run_id.document_ids.quality_state, "warning")
        self.assertTrue(job.parse_run_id.document_ids.is_current_result)
        self.assertEqual(job.worker_result_checksum, "d" * 64)
        self.assertEqual(
            job.taxonomy_compatibility_profile,
            "trim_role_uri_whitespace_v1",
        )
        self.assertEqual(job.taxonomy_patch_count, 1)
        self.assertEqual(job.working_taxonomy_checksum, "e" * 64)

    def test_worker_compatibility_mismatch_fails_before_ledger_creation(self):
        job = self._enqueue("compatibility-mismatch")
        result = self._completed_result(
            job.parse_run_id,
            "compatibility-mismatch",
        )
        result["taxonomy_patch_count"] = 2

        with patch.object(
            type(job),
            "_execute_worker",
            return_value=result,
        ):
            processed = job._process()

        self.assertFalse(processed)
        self.assertEqual(job.state, "failed")
        self.assertEqual(job.parse_run_id.state, "failed")
        self.assertEqual(
            job.parse_run_id.error_code,
            "WORKER_COMPATIBILITY_COUNT_MISMATCH",
        )
        self.assertFalse(job.parse_run_id.document_ids)

    def test_worker_validation_error_fails_without_normalized_output(self):
        job = self._enqueue("validation-error")
        result = self._completed_result(job.parse_run_id, "validation-error")
        result.update(
            {
                "documents": [],
                "error_count": 2,
                "warning_count": 1,
            }
        )

        with patch.object(
            type(job),
            "_execute_worker",
            return_value=result,
        ):
            processed = job._process()

        self.assertFalse(processed)
        self.assertEqual(job.state, "failed")
        self.assertEqual(job.parse_run_id.state, "failed")
        self.assertEqual(job.parse_run_id.error_code, "XBRL_VALIDATION_FAILED")
        self.assertFalse(job.parse_run_id.document_ids)

    def test_failed_retry_does_not_replace_previous_success(self):
        dataset = self._dataset("retry")
        taxonomy = self._taxonomy("retry")
        jobs = self.env["sudo.cn.einvoice.xbrl.job"].with_company(self.company)
        first = jobs.enqueue(
            dataset,
            dataset.source_attachment_ids[:1],
            taxonomy,
        )
        with patch.object(
            type(first),
            "_execute_worker",
            return_value=self._completed_result(first.parse_run_id, "first"),
        ):
            self.assertTrue(first._process())

        failed = jobs.enqueue(
            dataset,
            dataset.source_attachment_ids[:1],
            taxonomy,
        )
        failed_result = {
            "schema_version": 1,
            "status": "failed",
            "error_code": "TEST_WORKER_FAILURE",
            "error_summary": "测试工作进程失败。",
            "worker_exit_code": 2,
            "worker_result_checksum": "e" * 64,
        }
        with patch.object(
            type(failed),
            "_execute_worker",
            return_value=failed_result,
        ):
            self.assertFalse(failed._process())

        self.assertEqual(first.parse_run_id.state, "succeeded")
        self.assertEqual(failed.parse_run_id.state, "failed")
        self.assertTrue(first.parse_run_id.document_ids.is_current_result)

    def test_cancel_marks_base_parse_run_failed(self):
        job = self._enqueue("cancel")

        job.action_cancel()

        self.assertEqual(job.state, "cancelled")
        self.assertEqual(job.parse_run_id.state, "failed")
        self.assertEqual(job.parse_run_id.error_code, "JOB_CANCELLED")

    def test_stale_processing_job_is_recovered_after_worker_interruption(self):
        job = self._enqueue("stale")
        self.env.cr.execute(
            """
                UPDATE sudo_cn_einvoice_xbrl_job
                   SET state = 'processing',
                       started_at = NOW() - INTERVAL '1 day'
                 WHERE id = %s
            """,
            (job.id,),
        )
        job.invalidate_recordset(["state", "started_at"])

        recovered = job._recover_stale_jobs()

        self.assertEqual(recovered, 1)
        self.assertEqual(job.state, "failed")
        self.assertEqual(job.parse_run_id.state, "failed")
        self.assertEqual(
            job.parse_run_id.error_code,
            "INTERRUPTED_WORKER_RECOVERED",
        )

    def test_taxonomy_tampering_blocks_enqueue(self):
        dataset = self._dataset("taxonomy-tamper")
        taxonomy = self._taxonomy("taxonomy-tamper")
        taxonomy.bundle_attachment_ids.raw = b"tampered"

        with self.assertRaises(UserError):
            self.env["sudo.cn.einvoice.xbrl.job"].with_company(
                self.company
            ).enqueue(
                dataset,
                dataset.source_attachment_ids[:1],
                taxonomy,
            )
