import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


_JOB_TRANSITION_MARKER = object()
SUPPORTED_ARELLE_VERSION = "2.42.1"
PARSER_ADDON_VERSION = "19.0.1.0.0"
MAX_RESULT_BYTES = 100 * 1024 * 1024


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _safe_summary(value, limit=2000):
    if not value:
        return False
    return " ".join(str(value).split()).strip()[:limit] or False


def _is_sha256(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


class SudoChinaEinvoiceXbrlJob(models.Model):
    _name = "sudo.cn.einvoice.xbrl.job"
    _description = "China Electronic Invoice XBRL Parse Job"
    _order = "requested_at desc, id desc"
    _check_company_auto = True

    name = fields.Char(compute="_compute_name", store=True)
    dataset_id = fields.Many2one(
        "sudo.cn.external.dataset",
        string="电子发票数据集",
        required=True,
        ondelete="restrict",
        check_company=True,
        index=True,
        readonly=True,
    )
    profile_id = fields.Many2one(
        related="dataset_id.profile_id",
        store=True,
        index=True,
        readonly=True,
    )
    company_id = fields.Many2one(
        related="dataset_id.company_id",
        store=True,
        index=True,
        readonly=True,
    )
    source_attachment_id = fields.Many2one(
        "ir.attachment",
        string="解析源文件",
        required=True,
        ondelete="restrict",
        readonly=True,
    )
    taxonomy_bundle_id = fields.Many2one(
        "sudo.cn.xbrl.taxonomy.bundle",
        string="分类标准包",
        required=True,
        ondelete="restrict",
        readonly=True,
    )
    taxonomy_compatibility_profile = fields.Selection(
        related="taxonomy_bundle_id.compatibility_profile",
        string="分类标准兼容方案",
        store=True,
        readonly=True,
    )
    taxonomy_patch_count = fields.Integer(
        string="工作副本兼容修正数",
        readonly=True,
    )
    working_taxonomy_checksum = fields.Char(
        string="工作副本分类标准 SHA-256",
        readonly=True,
    )
    parse_run_id = fields.Many2one(
        "sudo.cn.external.parse.run",
        string="解析运行",
        required=True,
        ondelete="restrict",
        check_company=True,
        index=True,
        readonly=True,
    )
    state = fields.Selection(
        [
            ("queued", "待处理"),
            ("processing", "处理中"),
            ("succeeded", "成功"),
            ("failed", "失败"),
            ("cancelled", "已取消"),
        ],
        string="状态",
        required=True,
        default="queued",
        readonly=True,
        index=True,
    )
    requested_at = fields.Datetime(
        string="提交时间",
        required=True,
        readonly=True,
    )
    requested_by_id = fields.Many2one(
        "res.users",
        string="提交人",
        required=True,
        readonly=True,
    )
    started_at = fields.Datetime(string="开始时间", readonly=True)
    finished_at = fields.Datetime(string="完成时间", readonly=True)
    timeout_seconds = fields.Integer(
        string="超时秒数",
        required=True,
        readonly=True,
    )
    worker_exit_code = fields.Integer(string="工作进程退出码", readonly=True)
    result_summary = fields.Text(string="结果摘要", readonly=True)
    worker_result_checksum = fields.Char(string="工作结果校验和", readonly=True)

    _parse_run_unique = models.Constraint(
        "unique(parse_run_id)",
        "每个解析运行只能对应一个 XBRL 任务。",
    )
    _timeout_range = models.Constraint(
        "CHECK(timeout_seconds >= 30 AND timeout_seconds <= 1800)",
        "解析超时必须在 30 至 1800 秒之间。",
    )

    @api.depends("dataset_id", "requested_at")
    def _compute_name(self):
        for job in self:
            requested = fields.Datetime.to_string(job.requested_at) or "-"
            job.name = "%s / %s" % (
                job.dataset_id.display_name or _("电子发票解析"),
                requested,
            )

    @api.model_create_multi
    def create(self, vals_list):
        if (
            self.env.context.get("cn_xbrl_job_transition")
            is not _JOB_TRANSITION_MARKER
        ):
            raise AccessError(_("XBRL 解析任务只能由受控队列创建。"))
        for values in vals_list:
            values.update(
                {
                    "state": "queued",
                    "started_at": False,
                    "finished_at": False,
                    "worker_exit_code": 0,
                    "result_summary": False,
                    "worker_result_checksum": False,
                    "taxonomy_patch_count": 0,
                    "working_taxonomy_checksum": False,
                }
            )
        return super().create(vals_list)

    def write(self, values):
        if (
            self.env.context.get("cn_xbrl_job_transition")
            is not _JOB_TRANSITION_MARKER
        ):
            raise AccessError(_("XBRL 解析任务只能由受控队列更新。"))
        return super().write(values)

    def unlink(self):
        raise AccessError(_("XBRL 解析任务属于审计记录，不可删除。"))

    @api.model
    def _arelle_version(self):
        try:
            version = importlib.metadata.version("arelle-release")
        except importlib.metadata.PackageNotFoundError as exc:
            raise UserError(_("尚未安装 arelle-release 解析依赖。")) from exc
        if version != SUPPORTED_ARELLE_VERSION:
            raise UserError(
                _(
                    "当前 Arelle 版本 %(actual)s 未经验证，要求 %(expected)s。",
                    actual=version,
                    expected=SUPPORTED_ARELLE_VERSION,
                )
            )
        return version

    @api.model
    def enqueue(self, dataset, source_attachment, taxonomy_bundle, timeout=300):
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以提交 XBRL 解析。"))
        dataset.ensure_one()
        source_attachment.ensure_one()
        taxonomy_bundle.ensure_one()
        timeout = int(timeout or 300)
        if timeout < 30 or timeout > 1800:
            raise ValidationError(_("解析超时必须在 30 至 1800 秒之间。"))
        if taxonomy_bundle.state != "sealed":
            raise UserError(_("只能使用当前已封存的分类标准包。"))
        if taxonomy_bundle._current_integrity_state() != "verified":
            raise UserError(_("分类标准包完整性异常，不能提交解析。"))
        arelle_version = self._arelle_version()
        run = self.env["sudo.cn.external.parse.run"]._start_for_dataset(
            dataset,
            source_attachment,
            parser_key="mof_einvoice_xbrl_arelle",
            parser_version=(
                "%s+arelle.%s+taxonomy.%s"
                % (
                    PARSER_ADDON_VERSION,
                    arelle_version,
                    taxonomy_bundle.compatibility_profile,
                )
            ),
            parser_distribution="arelle-release==%s" % arelle_version,
            taxonomy_namespace=taxonomy_bundle.namespace,
            taxonomy_version=taxonomy_bundle.version,
            taxonomy_checksum=taxonomy_bundle.bundle_sha256,
            taxonomy_source_reference=taxonomy_bundle.source_url,
        )
        job = self.with_context(
            cn_xbrl_job_transition=_JOB_TRANSITION_MARKER
        ).create(
            {
                "dataset_id": dataset.id,
                "source_attachment_id": source_attachment.id,
                "taxonomy_bundle_id": taxonomy_bundle.id,
                "parse_run_id": run.id,
                "requested_at": fields.Datetime.now(),
                "requested_by_id": self.env.user.id,
                "timeout_seconds": timeout,
            }
        )
        self.env["sudo.compliance.audit.event"]._log_records(
            job,
            "cn_einvoice_xbrl.queued",
            new_state="queued",
            details={
                "dataset_id": dataset.id,
                "parse_run_id": run.id,
                "taxonomy_bundle_id": taxonomy_bundle.id,
                "source_attachment_id": source_attachment.id,
                "timeout_seconds": timeout,
            },
        )
        return job

    @api.model
    def _worker_path(self):
        return Path(__file__).resolve().parents[1] / "parser" / "worker.py"

    @api.model
    def _worker_environment(self, temporary):
        allowed = {
            "LANG",
            "LC_ALL",
            "LD_LIBRARY_PATH",
            "PATH",
            "PYTHONHOME",
            "SYSTEMROOT",
            "TZ",
            "WINDIR",
        }
        environment = {
            key: value for key, value in os.environ.items() if key in allowed
        }
        environment.update(
            {
                "HOME": str(temporary),
                "TMP": str(temporary),
                "TEMP": str(temporary),
                "TMPDIR": str(temporary),
                "PYTHONNOUSERSITE": "1",
            }
        )
        return environment

    def _worker_request(self, source_path, taxonomy_path):
        self.ensure_one()
        return {
            "schema_version": 1,
            "source_path": str(source_path),
            "source_name": self.source_attachment_id.name,
            "expected_source_sha256": self.parse_run_id.input_sha256,
            "taxonomy_path": str(taxonomy_path),
            "expected_taxonomy_sha256": (
                self.taxonomy_bundle_id.bundle_sha256
            ),
            "entry_point_path": self.taxonomy_bundle_id.entry_point_path,
            "taxonomy_namespace": self.taxonomy_bundle_id.namespace,
            "taxonomy_compatibility_profile": (
                self.taxonomy_bundle_id.compatibility_profile
            ),
            "expected_compatibility_patch_count": (
                self.taxonomy_bundle_id.compatibility_patch_count
            ),
            "memory_limit_bytes": 2 * 1024 * 1024 * 1024,
            "cpu_limit_seconds": self.timeout_seconds,
        }

    def _execute_worker(self):
        self.ensure_one()
        source = self.source_attachment_id.sudo().raw
        taxonomy_attachment = (
            self.taxonomy_bundle_id.bundle_attachment_ids.sudo()[:1]
        )
        taxonomy = taxonomy_attachment.raw
        if not source or not taxonomy:
            raise UserError(_("解析源文件或分类标准包为空。"))
        if _sha256(source) != self.parse_run_id.input_sha256:
            raise UserError(_("解析源文件哈希与封存值不一致。"))
        if _sha256(taxonomy) != self.taxonomy_bundle_id.bundle_sha256:
            raise UserError(_("分类标准包哈希与封存值不一致。"))
        with tempfile.TemporaryDirectory(prefix="sdoo-cn-xbrl-job-") as name:
            temporary = Path(name)
            os.chmod(temporary, 0o700)
            source_suffix = Path(self.source_attachment_id.name or "").suffix
            source_path = temporary / ("source%s" % (source_suffix or ".xml"))
            taxonomy_path = temporary / "taxonomy.zip"
            request_path = temporary / "request.json"
            result_path = temporary / "result.json"
            source_path.write_bytes(source)
            taxonomy_path.write_bytes(taxonomy)
            request_path.write_text(
                json.dumps(
                    self._worker_request(source_path, taxonomy_path),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            for path in (source_path, taxonomy_path, request_path):
                os.chmod(path, 0o600)
            command = [
                sys.executable,
                str(self._worker_path()),
                "--request",
                str(request_path),
                "--result",
                str(result_path),
            ]
            completed = subprocess.run(
                command,
                cwd=temporary,
                env=self._worker_environment(temporary),
                capture_output=True,
                timeout=self.timeout_seconds + 10,
                check=False,
            )
            if not result_path.is_file():
                raise UserError(_("解析工作进程没有返回受控结果。"))
            if result_path.stat().st_size > MAX_RESULT_BYTES:
                raise UserError(_("解析工作进程返回结果超过安全大小限制。"))
            result_bytes = result_path.read_bytes()
            try:
                result = json.loads(result_bytes.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise UserError(_("解析工作进程返回了无效 JSON。")) from exc
            result["worker_exit_code"] = completed.returncode
            result["worker_result_checksum"] = _sha256(result_bytes)
            return result

    def _mark_failed(self, code, summary, *, exit_code=0, checksum=False):
        self.ensure_one()
        safe_code = _safe_summary(code, 128) or "XBRL_JOB_FAILED"
        safe_summary = _safe_summary(summary) or "电子发票 XBRL 解析失败。"
        if self.parse_run_id.state == "running":
            self.parse_run_id._record_failure(safe_code, safe_summary)
        self.with_context(
            cn_xbrl_job_transition=_JOB_TRANSITION_MARKER
        ).write(
            {
                "state": "failed",
                "finished_at": fields.Datetime.now(),
                "worker_exit_code": int(exit_code or 0),
                "worker_result_checksum": checksum or False,
                "result_summary": safe_summary,
            }
        )
        self.env["sudo.compliance.audit.event"]._log_records(
            self,
            "cn_einvoice_xbrl.failed",
            previous_state="processing",
            new_state="failed",
            details={"error_code": safe_code, "exit_code": int(exit_code or 0)},
        )
        return False

    def _consume_worker_result(self, result):
        self.ensure_one()
        if not isinstance(result, dict) or result.get("schema_version") != 1:
            return self._mark_failed(
                "INVALID_WORKER_RESULT",
                "解析工作进程返回结果契约无效。",
            )
        exit_code = int(result.get("worker_exit_code") or 0)
        checksum = result.get("worker_result_checksum") or False
        if result.get("status") == "failed":
            return self._mark_failed(
                result.get("error_code") or "WORKER_FAILED",
                result.get("error_summary") or "解析工作进程执行失败。",
                exit_code=exit_code,
                checksum=checksum,
            )
        if result.get("status") != "completed" or exit_code != 0:
            return self._mark_failed(
                "INVALID_WORKER_EXIT",
                "解析工作进程状态与退出码不一致。",
                exit_code=exit_code,
                checksum=checksum,
            )
        if result.get("arelle_version") != SUPPORTED_ARELLE_VERSION:
            return self._mark_failed(
                "WORKER_VERSION_MISMATCH",
                "解析工作进程使用了未经验证的 Arelle 版本。",
                exit_code=exit_code,
                checksum=checksum,
            )
        compatibility_profile = result.get(
            "taxonomy_compatibility_profile"
        )
        patch_count = result.get("taxonomy_patch_count")
        working_checksum = result.get("working_taxonomy_checksum")
        if compatibility_profile != self.taxonomy_compatibility_profile:
            return self._mark_failed(
                "WORKER_COMPATIBILITY_PROFILE_MISMATCH",
                "工作进程使用的分类标准兼容方案与封存记录不一致。",
                exit_code=exit_code,
                checksum=checksum,
            )
        if (
            not isinstance(patch_count, int)
            or isinstance(patch_count, bool)
            or patch_count != self.taxonomy_bundle_id.compatibility_patch_count
        ):
            return self._mark_failed(
                "WORKER_COMPATIBILITY_COUNT_MISMATCH",
                "工作进程返回的分类标准兼容修正数与封存记录不一致。",
                exit_code=exit_code,
                checksum=checksum,
            )
        if not _is_sha256(working_checksum):
            return self._mark_failed(
                "INVALID_WORKING_TAXONOMY_CHECKSUM",
                "工作进程未返回有效的工作副本分类标准校验和。",
                exit_code=exit_code,
                checksum=checksum,
            )
        success = self.parse_run_id._record_success(
            result.get("documents"),
            observed_input_sha256=result.get("observed_input_sha256"),
            source_fact_count=result.get("source_fact_count"),
            warning_count=result.get("warning_count"),
            error_count=result.get("error_count"),
            parser_log_checksum=result.get("parser_log_checksum"),
        )
        state = "succeeded" if success else "failed"
        summary = self.parse_run_id.result_summary
        self.with_context(
            cn_xbrl_job_transition=_JOB_TRANSITION_MARKER
        ).write(
            {
                "state": state,
                "finished_at": fields.Datetime.now(),
                "worker_exit_code": exit_code,
                "worker_result_checksum": checksum,
                "taxonomy_patch_count": patch_count,
                "working_taxonomy_checksum": working_checksum,
                "result_summary": summary,
            }
        )
        self.env["sudo.compliance.audit.event"]._log_records(
            self,
            "cn_einvoice_xbrl.%s" % state,
            previous_state="processing",
            new_state=state,
            details={
                "parse_run_id": self.parse_run_id.id,
                "document_count": self.parse_run_id.document_count,
                "warning_count": self.parse_run_id.parser_warning_count,
                "error_count": self.parse_run_id.parser_error_count,
                "worker_result_checksum": checksum,
                "taxonomy_compatibility_profile": compatibility_profile,
                "taxonomy_patch_count": patch_count,
                "working_taxonomy_checksum": working_checksum,
            },
        )
        return success

    def _process(self):
        self.ensure_one()
        if self.state != "queued":
            raise UserError(_("只有待处理任务可以执行。"))
        self.with_context(
            cn_xbrl_job_transition=_JOB_TRANSITION_MARKER
        ).write({"state": "processing", "started_at": fields.Datetime.now()})
        self.env["sudo.compliance.audit.event"]._log_records(
            self,
            "cn_einvoice_xbrl.processing",
            previous_state="queued",
            new_state="processing",
        )
        try:
            result = self._execute_worker()
        except subprocess.TimeoutExpired:
            return self._mark_failed(
                "WORKER_TIMEOUT",
                "解析工作进程超过受控执行时限。",
            )
        except (OSError, ValueError, UserError) as exc:
            return self._mark_failed(
                "WORKER_EXECUTION_FAILED",
                _safe_summary(exc) or "解析工作进程执行失败。",
            )
        except Exception as exc:
            return self._mark_failed(
                "UNEXPECTED_JOB_FAILURE",
                "解析队列发生未预期错误：%s" % type(exc).__name__,
            )
        return self._consume_worker_result(result)

    @api.model
    def _recover_stale_jobs(self, limit=10):
        self.env.cr.execute(
            """
                SELECT id
                  FROM sudo_cn_einvoice_xbrl_job
                 WHERE state = 'processing'
                   AND started_at IS NOT NULL
                   AND started_at
                       + (timeout_seconds + 120) * INTERVAL '1 second'
                       < NOW()
                 ORDER BY started_at, id
                 FOR UPDATE SKIP LOCKED
                 LIMIT %s
            """,
            (max(int(limit or 10), 1),),
        )
        jobs = self.browse([row[0] for row in self.env.cr.fetchall()])
        for job in jobs:
            job._mark_failed(
                "INTERRUPTED_WORKER_RECOVERED",
                "解析工作进程中断，后台队列已回收超时任务。",
            )
        return len(jobs)

    @api.model
    def _cron_process_jobs(self, limit=1):
        self._recover_stale_jobs()
        processed = 0
        for _index in range(max(int(limit or 1), 1)):
            self.env.cr.execute(
                """
                    SELECT id
                      FROM sudo_cn_einvoice_xbrl_job
                     WHERE state = 'queued'
                     ORDER BY requested_at, id
                     FOR UPDATE SKIP LOCKED
                     LIMIT 1
                """
            )
            row = self.env.cr.fetchone()
            if not row:
                break
            self.browse(row[0])._process()
            processed += 1
        return processed

    def action_cancel(self):
        if not self.env.user.has_group(
            "sudo_global_finance.group_compliance_manager"
        ):
            raise AccessError(_("只有合规管理员可以取消 XBRL 解析任务。"))
        for job in self:
            if job.state != "queued":
                raise UserError(_("只有待处理任务可以取消。"))
            if job.parse_run_id.state == "running":
                job.parse_run_id._record_failure(
                    "JOB_CANCELLED",
                    "XBRL 解析任务在执行前由合规管理员取消。",
                    error_count=1,
                )
            job.with_context(
                cn_xbrl_job_transition=_JOB_TRANSITION_MARKER
            ).write(
                {
                    "state": "cancelled",
                    "finished_at": fields.Datetime.now(),
                    "result_summary": "任务在执行前取消。",
                }
            )
            self.env["sudo.compliance.audit.event"]._log_records(
                job,
                "cn_einvoice_xbrl.cancelled",
                previous_state="queued",
                new_state="cancelled",
            )
        return True


class SudoChinaExternalDataset(models.Model):
    _inherit = "sudo.cn.external.dataset"

    xbrl_job_ids = fields.One2many(
        "sudo.cn.einvoice.xbrl.job",
        "dataset_id",
        string="XBRL 解析任务",
        readonly=True,
    )
    xbrl_job_count = fields.Integer(
        string="XBRL 解析任务数",
        compute="_compute_xbrl_job_count",
    )

    @api.depends("xbrl_job_ids")
    def _compute_xbrl_job_count(self):
        for dataset in self:
            dataset.xbrl_job_count = len(dataset.xbrl_job_ids)

    def action_open_xbrl_parse_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("提交电子发票 XBRL 解析"),
            "res_model": "sudo.cn.einvoice.parse.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_dataset_id": self.id},
        }

    def action_view_xbrl_jobs(self):
        self.ensure_one()
        action = self.env.ref(
            "sudo_country_pack_cn_einvoice_xbrl.action_cn_einvoice_xbrl_jobs"
        ).read()[0]
        action["domain"] = [("dataset_id", "=", self.id)]
        return action
