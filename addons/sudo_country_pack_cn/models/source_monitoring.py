import hashlib
import json
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


_CN_SOURCE_MONITOR_WRITE_MARKER = object()
_CN_SOURCE_MONITOR_RUN_MARKER = object()
_CN_SOURCE_MONITOR_SCHEDULE_MARKER = object()
_CN_SOURCE_MONITOR_SCHEMA = "sdoo.cn.authority-source-monitor.v1"
_CN_SOURCE_IMPACT_SCHEMA = "sdoo.cn.authority-source-rule-impact.v1"
_CN_SOURCE_TERMINAL_STATES = {"unchanged", "changed", "failed", "cancelled"}


class SourceBaselineIntegrityError(UserError):
    pass


def _checksum(payload):
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _date_string(value):
    return fields.Date.to_string(value) if value else None


def _datetime_string(value):
    return fields.Datetime.to_string(value) if value else None


def _safe_text(value, limit=2000):
    text = " ".join(str(value or "").split())
    return text[:limit]


class SudoComplianceAuthoritySource(models.Model):
    _inherit = "sudo.compliance.authority.source"

    cn_is_source = fields.Boolean(
        string="中国官方来源",
        compute="_compute_cn_is_source",
    )
    cn_monitor_enabled = fields.Boolean(
        string="启用远端变化监测",
        copy=False,
        help="这是内部来源复核频率，不是法定申报或纳税期限。",
    )
    cn_monitor_interval_days = fields.Integer(
        string="检查间隔（天）",
        default=30,
        copy=False,
        help="仅控制系统何时再次检查官方链接，不替代人工复核日期。",
    )
    cn_next_monitor_date = fields.Date(
        string="下次远端检查",
        default=fields.Date.context_today,
        index=True,
        copy=False,
    )
    cn_last_monitor_at = fields.Datetime(
        string="最后远端检查时间",
        readonly=True,
        copy=False,
    )
    cn_last_monitor_state = fields.Selection(
        [
            ("never", "尚未检查"),
            ("unchanged", "内容未变化"),
            ("changed", "检测到变化"),
            ("failed", "检查失败"),
        ],
        string="最后检查结果",
        default="never",
        readonly=True,
        copy=False,
        index=True,
    )
    cn_last_monitor_message = fields.Text(
        string="最后检查说明",
        readonly=True,
        copy=False,
    )
    cn_latest_monitor_run_id = fields.Many2one(
        "sudo.cn.authority.source.monitor.run",
        string="最新检查记录",
        readonly=True,
        copy=False,
        ondelete="set null",
    )
    cn_latest_change_candidate_id = fields.Many2one(
        "sudo.compliance.authority.source",
        string="最新变化候选",
        readonly=True,
        copy=False,
        ondelete="restrict",
    )
    cn_monitor_predecessor_id = fields.Many2one(
        "sudo.compliance.authority.source",
        string="监测来源前版",
        readonly=True,
        copy=False,
        ondelete="restrict",
        index=True,
    )
    cn_monitor_run_ids = fields.One2many(
        "sudo.cn.authority.source.monitor.run",
        "source_id",
        string="远端检查记录",
        readonly=True,
    )
    cn_monitor_run_count = fields.Integer(
        string="远端检查次数",
        compute="_compute_cn_monitor_run_count",
    )
    cn_latest_impacted_rule_count = fields.Integer(
        string="最新受影响规则版本",
        related="cn_latest_monitor_run_id.impacted_rule_count",
        readonly=True,
    )
    cn_latest_active_rule_count = fields.Integer(
        string="最新受影响生效规则",
        related="cn_latest_monitor_run_id.active_impacted_rule_count",
        readonly=True,
    )

    _cn_monitor_config_fields = {
        "cn_monitor_enabled",
        "cn_monitor_interval_days",
        "cn_next_monitor_date",
    }
    _cn_monitor_system_fields = {
        "cn_last_monitor_at",
        "cn_last_monitor_state",
        "cn_last_monitor_message",
        "cn_latest_monitor_run_id",
        "cn_latest_change_candidate_id",
        "cn_monitor_predecessor_id",
    }

    @api.depends("country_id.code")
    def _compute_cn_is_source(self):
        for source in self:
            source.cn_is_source = source.country_id.code == "CN"

    def _compute_cn_monitor_run_count(self):
        grouped = (
            self.env["sudo.cn.authority.source.monitor.run"]._read_group(
                [("source_id", "in", self.ids)],
                ["source_id"],
                ["__count"],
            )
            if self.ids
            else []
        )
        counts = {source.id: count for source, count in grouped}
        for source in self:
            source.cn_monitor_run_count = counts.get(source.id, 0)

    @api.model_create_multi
    def create(self, vals_list):
        if (
            self.env.context.get("cn_source_monitor_write")
            is not _CN_SOURCE_MONITOR_WRITE_MARKER
        ):
            for values in vals_list:
                if set(values) & self._cn_monitor_system_fields:
                    raise AccessError(
                        _("中国官方来源监测状态只能由受控流程写入。")
                    )
        return super().create(vals_list)

    def write(self, values):
        changed = set(values)
        internal = (
            self.env.context.get("cn_source_monitor_write")
            is _CN_SOURCE_MONITOR_WRITE_MARKER
        )
        if changed & self._cn_monitor_system_fields and not internal:
            raise AccessError(_("中国官方来源监测状态只能由受控流程写入。"))
        if changed & self._cn_monitor_config_fields and not internal:
            if not self._can_author():
                raise AccessError(
                    _("只有规则维护人员可以配置中国官方来源监测。")
                )
        return super().write(values)

    @api.constrains(
        "cn_monitor_enabled",
        "cn_monitor_interval_days",
        "country_id",
    )
    def _check_cn_monitor_configuration(self):
        for source in self:
            if not 1 <= source.cn_monitor_interval_days <= 365:
                raise ValidationError(_("来源远端检查间隔必须在 1 至 365 天之间。"))
            if source.cn_monitor_enabled and source.country_id.code != "CN":
                raise ValidationError(_("中国来源监测只能用于中国官方来源。"))

    def _cn_monitor_write(self, values):
        return self.with_context(
            cn_source_monitor_write=_CN_SOURCE_MONITOR_WRITE_MARKER
        ).write(values)

    def _cn_validate_monitor_baseline(self):
        self.ensure_one()
        if self.country_id.code != "CN":
            raise UserError(_("只能检查中国官方来源。"))
        if self.status != "valid":
            raise UserError(_("只有经过独立复核且当前有效的官方来源可以检查变化。"))
        if not self.official_url:
            raise UserError(_("当前官方来源没有可检查的官方链接。"))
        if not self.snapshot_attachment_id or not self.content_hash:
            raise SourceBaselineIntegrityError(
                _("当前官方来源缺少批准快照或 SHA-256。")
            )
        if not self._is_publishable_snapshot():
            raise SourceBaselineIntegrityError(
                _("当前来源快照性质不能作为正式规则依据。")
            )
        raw = self.snapshot_attachment_id.sudo().raw
        if not raw or hashlib.sha256(raw).hexdigest() != self.content_hash:
            raise SourceBaselineIntegrityError(
                _("当前批准快照内容与已登记 SHA-256 不一致。")
            )
        return True

    def _cn_mark_monitor_baseline_compromised(self, message, run=None):
        self.ensure_one()
        if self.status == "valid":
            self.action_mark_change_detected()
        values = {
            "cn_monitor_enabled": False,
            "cn_next_monitor_date": False,
            "cn_last_monitor_at": fields.Datetime.now(),
            "cn_last_monitor_state": "failed",
            "cn_last_monitor_message": _safe_text(message),
        }
        if run:
            values["cn_latest_monitor_run_id"] = run.id
        self._cn_monitor_write(values)
        return True

    def action_cn_queue_monitor(self):
        if not self._can_author():
            raise AccessError(_("只有规则维护人员可以发起来源远端检查。"))
        runs = self.env["sudo.cn.authority.source.monitor.run"]
        for source in self:
            runs |= runs.enqueue(source, request_kind="manual")
        if len(runs) == 1:
            action = self.env.ref(
                "sudo_country_pack_cn.action_cn_source_monitor_runs"
            ).read()[0]
            action.update(
                {
                    "view_mode": "form",
                    "views": [
                        (
                            self.env.ref(
                                "sudo_country_pack_cn."
                                "view_cn_source_monitor_run_form"
                            ).id,
                            "form",
                        )
                    ],
                    "res_id": runs.id,
                    "target": "current",
                    "context": {},
                }
            )
            return action
        return self.action_cn_open_monitor_runs()

    def action_cn_open_monitor_runs(self):
        self.ensure_one()
        action = self.env.ref(
            "sudo_country_pack_cn.action_cn_source_monitor_runs"
        ).read()[0]
        action["domain"] = [("source_id", "=", self.id)]
        action["context"] = {}
        return action

    def action_cn_open_change_candidate(self):
        self.ensure_one()
        candidate = self.cn_latest_change_candidate_id
        if not candidate:
            raise UserError(_("当前来源没有远端变化候选。"))
        return {
            "type": "ir.actions.act_window",
            "name": _("官方来源变化候选"),
            "res_model": "sudo.compliance.authority.source",
            "res_id": candidate.id,
            "view_mode": "form",
            "views": [
                (
                    self.env.ref(
                        "sudo_global_finance.view_compliance_authority_source_form"
                    ).id,
                    "form",
                )
            ],
            "target": "current",
        }

    def action_mark_replaced(self):
        result = super().action_mark_replaced()
        china_sources = self.filtered(lambda source: source.country_id.code == "CN")
        if china_sources:
            china_sources._cn_monitor_write(
                {
                    "cn_monitor_enabled": False,
                    "cn_next_monitor_date": False,
                }
            )
        return result


class SudoChinaAuthoritySourceMonitorRun(models.Model):
    _name = "sudo.cn.authority.source.monitor.run"
    _description = "China Official Source Remote Monitor Run"
    _order = "requested_at desc, id desc"

    name = fields.Char(string="检查记录", compute="_compute_name", store=True)
    source_id = fields.Many2one(
        "sudo.compliance.authority.source",
        string="中国官方来源",
        required=True,
        ondelete="restrict",
        index=True,
    )
    country_id = fields.Many2one(
        related="source_id.country_id",
        string="国家/地区",
        store=True,
        readonly=True,
    )
    state = fields.Selection(
        [
            ("queued", "待检查"),
            ("processing", "检查中"),
            ("unchanged", "内容未变化"),
            ("changed", "检测到变化"),
            ("failed", "检查失败"),
            ("cancelled", "已取消"),
        ],
        string="状态",
        required=True,
        default="queued",
        readonly=True,
        index=True,
    )
    request_kind = fields.Selection(
        [("manual", "人工发起"), ("scheduled", "定时检查")],
        string="发起方式",
        required=True,
        readonly=True,
    )
    requested_by_id = fields.Many2one(
        "res.users",
        string="发起人",
        required=True,
        readonly=True,
    )
    requested_at = fields.Datetime(
        string="发起时间",
        required=True,
        readonly=True,
        index=True,
    )
    started_at = fields.Datetime(string="开始时间", readonly=True)
    completed_at = fields.Datetime(string="完成时间", readonly=True)
    baseline_content_hash = fields.Char(
        string="批准快照 SHA-256",
        required=True,
        readonly=True,
    )
    source_snapshot_json = fields.Json(string="来源基线快照", readonly=True)
    source_snapshot_checksum = fields.Char(
        string="来源基线快照 SHA-256",
        required=True,
        readonly=True,
    )
    remote_content_hash = fields.Char(string="远端内容 SHA-256", readonly=True)
    remote_final_url = fields.Char(string="实际检查地址", readonly=True)
    remote_http_status = fields.Integer(string="远端 HTTP 状态", readonly=True)
    remote_content_type = fields.Char(string="远端内容类型", readonly=True)
    remote_content_size = fields.Integer(string="远端字节数", readonly=True)
    remote_etag = fields.Char(string="远端 ETag", readonly=True)
    remote_last_modified = fields.Char(string="远端最后修改", readonly=True)
    candidate_source_id = fields.Many2one(
        "sudo.compliance.authority.source",
        string="远端变化候选",
        readonly=True,
        copy=False,
        ondelete="restrict",
    )
    candidate_content_hash = fields.Char(
        string="候选快照 SHA-256",
        readonly=True,
    )
    candidate_integrity_state = fields.Selection(
        [
            ("not_applicable", "无变化候选"),
            ("verified", "候选完整性正常"),
            ("missing", "候选快照缺失"),
            ("changed", "候选内容已变化"),
        ],
        string="候选完整性",
        compute="_compute_candidate_integrity_state",
    )
    impacted_rule_version_ids = fields.Many2many(
        "sudo.compliance.rule.version",
        "sudo_cn_source_monitor_rule_version_rel",
        "run_id",
        "version_id",
        string="受影响规则版本",
        readonly=True,
    )
    impacted_rule_count = fields.Integer(string="受影响规则版本", readonly=True)
    active_impacted_rule_count = fields.Integer(
        string="受影响生效规则",
        readonly=True,
    )
    review_impacted_rule_count = fields.Integer(
        string="受影响审批中规则",
        readonly=True,
    )
    impact_snapshot_json = fields.Json(string="规则影响快照", readonly=True)
    impact_snapshot_checksum = fields.Char(
        string="规则影响 SHA-256",
        readonly=True,
    )
    result_summary = fields.Text(string="检查结论", readonly=True)
    error_code = fields.Char(string="错误代码", readonly=True)
    error_message = fields.Text(string="错误说明", readonly=True)
    result_checksum = fields.Char(string="结果 SHA-256", readonly=True, index=True)
    result_integrity_state = fields.Selection(
        [
            ("unavailable", "尚无结果"),
            ("verified", "完整性正常"),
            ("checksum_mismatch", "结果已变化"),
        ],
        string="结果完整性",
        compute="_compute_result_integrity_state",
    )

    _active_source_unique = models.UniqueIndex(
        "(source_id) WHERE state IN ('queued', 'processing')",
        "同一官方来源只能有一个待检查或检查中的远端监测批次。",
    )

    @api.depends("source_id", "requested_at")
    def _compute_name(self):
        for run in self:
            run.name = "%s / %s" % (
                run.source_id.display_name or _("中国官方来源"),
                _datetime_string(run.requested_at) or _("待检查"),
            )

    @api.depends("candidate_source_id", "candidate_content_hash")
    def _compute_candidate_integrity_state(self):
        for run in self:
            candidate = run.candidate_source_id
            if not candidate:
                run.candidate_integrity_state = "not_applicable"
                continue
            attachment = candidate.snapshot_attachment_id
            raw = attachment.sudo().raw if attachment else b""
            if not raw or not candidate.content_hash or not run.candidate_content_hash:
                run.candidate_integrity_state = "missing"
                continue
            actual = hashlib.sha256(raw).hexdigest()
            run.candidate_integrity_state = (
                "verified"
                if actual == candidate.content_hash == run.candidate_content_hash
                else "changed"
            )

    @api.depends(
        "state",
        "result_checksum",
        "source_snapshot_json",
        "source_snapshot_checksum",
        "impact_snapshot_json",
        "impact_snapshot_checksum",
    )
    def _compute_result_integrity_state(self):
        for run in self:
            if run.state not in _CN_SOURCE_TERMINAL_STATES or not run.result_checksum:
                run.result_integrity_state = "unavailable"
                continue
            source_snapshot_valid = bool(
                run.source_snapshot_json
                and run.source_snapshot_checksum
                and _checksum(run.source_snapshot_json)
                == run.source_snapshot_checksum
            )
            impact_snapshot_valid = bool(
                not run.impact_snapshot_checksum
                or (
                    run.impact_snapshot_json
                    and _checksum(run.impact_snapshot_json)
                    == run.impact_snapshot_checksum
                )
            )
            if (
                source_snapshot_valid
                and impact_snapshot_valid
                and run._current_result_checksum() == run.result_checksum
            ):
                run.result_integrity_state = "verified"
            else:
                run.result_integrity_state = "checksum_mismatch"

    @api.model_create_multi
    def create(self, vals_list):
        if (
            self.env.context.get("cn_source_monitor_run")
            is not _CN_SOURCE_MONITOR_RUN_MARKER
        ):
            raise AccessError(_("来源远端检查记录只能由受控流程创建。"))
        now = fields.Datetime.now()
        for values in vals_list:
            values.update(
                {
                    "state": "queued",
                    "requested_by_id": self.env.user.id,
                    "requested_at": now,
                    "started_at": False,
                    "completed_at": False,
                    "result_checksum": False,
                    "error_code": False,
                    "error_message": False,
                }
            )
        return super().create(vals_list)

    def write(self, values):
        if (
            self.env.context.get("cn_source_monitor_run")
            is not _CN_SOURCE_MONITOR_RUN_MARKER
        ):
            raise AccessError(_("来源远端检查记录只能由受控流程更新。"))
        return super().write(values)

    def unlink(self):
        raise AccessError(_("来源远端检查记录属于审计记录，不可删除。"))

    def copy(self, default=None):
        raise AccessError(_("来源远端检查记录不可复制。"))

    def _transition_write(self, values):
        return self.with_context(
            cn_source_monitor_run=_CN_SOURCE_MONITOR_RUN_MARKER
        ).write(values)

    @api.model
    def enqueue(self, source, request_kind="manual"):
        source.ensure_one()
        if not source._can_author() and not self.env.is_superuser():
            raise AccessError(_("只有规则维护人员可以发起来源远端检查。"))
        if request_kind not in {"manual", "scheduled"}:
            raise ValidationError(_("未知的来源检查发起方式。"))
        scheduled_request = (
            self.env.context.get("cn_source_monitor_schedule")
            is _CN_SOURCE_MONITOR_SCHEDULE_MARKER
        )
        if request_kind == "scheduled" and not scheduled_request:
            raise AccessError(_("定时来源检查只能由系统任务发起。"))
        try:
            source._cn_validate_monitor_baseline()
        except SourceBaselineIntegrityError as exc:
            source._cn_mark_monitor_baseline_compromised(exc)
            raise
        active = self.search(
            [
                ("source_id", "=", source.id),
                ("state", "in", ("queued", "processing")),
            ],
            limit=1,
        )
        if active:
            raise UserError(_("当前官方来源已有待检查或检查中的批次。"))
        source_snapshot = self._source_snapshot_payload(source)
        run = self.with_context(
            cn_source_monitor_run=_CN_SOURCE_MONITOR_RUN_MARKER
        ).create(
            {
                "source_id": source.id,
                "request_kind": request_kind,
                "baseline_content_hash": source.content_hash,
                "source_snapshot_json": source_snapshot,
                "source_snapshot_checksum": _checksum(source_snapshot),
            }
        )
        self.env["sudo.compliance.audit.event"]._log_records(
            run,
            "cn.authority_source_monitor.queued",
            new_state="queued",
            details={
                "source_id": source.id,
                "request_kind": request_kind,
                "baseline_content_hash": source.content_hash,
            },
        )
        return run.with_context(cn_source_monitor_run=None)

    @api.model
    def _source_snapshot_payload(self, source):
        source.ensure_one()
        return source.with_context(lang="en_US").snapshot_payload()

    def _impact_snapshot(self):
        self.ensure_one()
        versions = self.env["sudo.compliance.rule.version"].search(
            [("authority_source_ids", "in", self.source_id.id)],
            order="rule_id, effective_from, version, id",
        )
        items = [
            {
                "version_id": version.id,
                "rule_id": version.rule_id.id,
                "rule_code": version.rule_id.code,
                "version": version.version,
                "state": version.state,
                "effective_from": _date_string(version.effective_from),
                "effective_to": _date_string(version.effective_to),
                "next_review_date": _date_string(version.next_review_date),
                "test_state": version.test_state,
                "professional_review_state": version.professional_review_state,
                "checksum": version.checksum or None,
            }
            for version in versions
        ]
        snapshot = {
            "schema": _CN_SOURCE_IMPACT_SCHEMA,
            "source_id": self.source_id.id,
            "source_content_hash": self.baseline_content_hash,
            "rule_versions": items,
        }
        return versions, snapshot

    def _result_payload(self):
        self.ensure_one()
        return {
            "schema": _CN_SOURCE_MONITOR_SCHEMA,
            "run_id": self.id,
            "source_id": self.source_id.id,
            "state": self.state,
            "request_kind": self.request_kind,
            "requested_by_id": self.requested_by_id.id,
            "requested_at": _datetime_string(self.requested_at),
            "started_at": _datetime_string(self.started_at),
            "completed_at": _datetime_string(self.completed_at),
            "baseline_content_hash": self.baseline_content_hash,
            "source_snapshot_checksum": self.source_snapshot_checksum,
            "remote": {
                "content_hash": self.remote_content_hash or None,
                "final_url": self.remote_final_url or None,
                "http_status": self.remote_http_status or None,
                "content_type": self.remote_content_type or None,
                "content_size": self.remote_content_size or 0,
                "etag": self.remote_etag or None,
                "last_modified": self.remote_last_modified or None,
            },
            "candidate": {
                "source_id": self.candidate_source_id.id or None,
                "content_hash": self.candidate_content_hash or None,
            },
            "impact": {
                "snapshot_checksum": self.impact_snapshot_checksum or None,
                "rule_count": self.impacted_rule_count,
                "active_rule_count": self.active_impacted_rule_count,
                "review_rule_count": self.review_impacted_rule_count,
            },
            "result_summary": self.result_summary or None,
            "error_code": self.error_code or None,
            "error_message": self.error_message or None,
        }

    def _current_result_checksum(self):
        self.ensure_one()
        return _checksum(self._result_payload())

    def _finalize_result(self, values):
        self.ensure_one()
        self._transition_write({**values, "result_checksum": False})
        self._transition_write({"result_checksum": self._current_result_checksum()})

    def _remote_values(self, capture, remote_hash):
        return {
            "remote_content_hash": remote_hash,
            "remote_final_url": capture["final_url"],
            "remote_http_status": capture["http_status"],
            "remote_content_type": capture["content_type"],
            "remote_content_size": len(capture["content"]),
            "remote_etag": capture.get("etag") or False,
            "remote_last_modified": capture.get("last_modified") or False,
        }

    def _create_change_candidate(self, capture):
        self.ensure_one()
        source = self.source_id
        today = fields.Date.context_today(source)
        candidate = source.with_context(
            cn_source_monitor_write=_CN_SOURCE_MONITOR_WRITE_MARKER
        ).copy(
            {
                "name": _(
                    "%(name)s（远端变化候选 %(date)s）",
                    name=source.name,
                    date=fields.Date.to_string(today),
                ),
                "official_version": False,
                "published_date": False,
                "next_review_date": today,
                "cn_monitor_enabled": False,
                "cn_next_monitor_date": False,
                "cn_monitor_predecessor_id": source.id,
            }
        )
        candidate._store_official_web_capture(capture)
        return candidate

    def _process_success(self):
        self.ensure_one()
        source = self.source_id
        source._cn_validate_monitor_baseline()
        if source.content_hash != self.baseline_content_hash:
            raise UserError(_("来源批准快照在排队后发生变化，请重新发起检查。"))
        if (
            _checksum(self._source_snapshot_payload(source))
            != self.source_snapshot_checksum
        ):
            raise UserError(_("来源治理元数据在排队后发生变化，请重新发起检查。"))

        capture = source._download_official_snapshot(source.official_url)
        remote_hash = hashlib.sha256(capture["content"]).hexdigest()
        versions, impact = self._impact_snapshot()
        impact_checksum = _checksum(impact)
        active_count = len(versions.filtered(lambda version: version.state == "active"))
        review_count = len(
            versions.filtered(
                lambda version: version.state in {"pending_review", "approved"}
            )
        )
        completed_at = fields.Datetime.now()
        today = fields.Date.context_today(source)
        common_values = {
            **self._remote_values(capture, remote_hash),
            "completed_at": completed_at,
            "impacted_rule_version_ids": [(6, 0, versions.ids)],
            "impacted_rule_count": len(versions),
            "active_impacted_rule_count": active_count,
            "review_impacted_rule_count": review_count,
            "impact_snapshot_json": impact,
            "impact_snapshot_checksum": impact_checksum,
            "error_code": False,
            "error_message": False,
        }
        if remote_hash == self.baseline_content_hash:
            summary = _(
                "远端内容 SHA-256 与批准快照一致；该技术检查不替代来源人工复核。"
            )
            self._finalize_result(
                {
                    **common_values,
                    "state": "unchanged",
                    "result_summary": summary,
                    "candidate_source_id": False,
                    "candidate_content_hash": False,
                }
            )
            source._cn_monitor_write(
                {
                    "cn_last_monitor_at": completed_at,
                    "cn_last_monitor_state": "unchanged",
                    "cn_last_monitor_message": summary,
                    "cn_latest_monitor_run_id": self.id,
                    "cn_latest_change_candidate_id": False,
                    "cn_next_monitor_date": today
                    + timedelta(days=source.cn_monitor_interval_days),
                }
            )
            event_key = "cn.authority_source_monitor.unchanged"
        else:
            candidate = self._create_change_candidate(capture)
            source.action_mark_change_detected()
            summary = _(
                "远端内容与批准快照不同，已冻结独立草稿候选并标记原来源变化；"
                "必须完成人工来源复核和规则影响判断。"
            )
            self._finalize_result(
                {
                    **common_values,
                    "state": "changed",
                    "result_summary": summary,
                    "candidate_source_id": candidate.id,
                    "candidate_content_hash": candidate.content_hash,
                }
            )
            source._cn_monitor_write(
                {
                    "cn_monitor_enabled": False,
                    "cn_next_monitor_date": False,
                    "cn_last_monitor_at": completed_at,
                    "cn_last_monitor_state": "changed",
                    "cn_last_monitor_message": summary,
                    "cn_latest_monitor_run_id": self.id,
                    "cn_latest_change_candidate_id": candidate.id,
                }
            )
            event_key = "cn.authority_source_monitor.changed"

        self.env["sudo.compliance.audit.event"]._log_records(
            self,
            event_key,
            previous_state="processing",
            new_state=self.state,
            details={
                "source_id": source.id,
                "baseline_content_hash": self.baseline_content_hash,
                "remote_content_hash": remote_hash,
                "candidate_source_id": self.candidate_source_id.id or None,
                "impacted_rule_count": self.impacted_rule_count,
                "active_impacted_rule_count": self.active_impacted_rule_count,
                "result_checksum": self.result_checksum,
            },
        )
        return True

    def _mark_failed(self, code, message, baseline_compromised=False):
        self.ensure_one()
        completed_at = fields.Datetime.now()
        safe_code = _safe_text(code, 128) or "SOURCE_MONITOR_FAILED"
        safe_message = _safe_text(message) or _("来源远端检查失败。")
        result_summary = (
            _(
                "来源远端检查失败，批准快照完整性异常；来源已停止作为有效依据。"
            )
            if baseline_compromised
            else _("来源远端检查失败，原批准快照和来源状态未改变。")
        )
        self._finalize_result(
            {
                "state": "failed",
                "completed_at": completed_at,
                "result_summary": result_summary,
                "error_code": safe_code,
                "error_message": safe_message,
            }
        )
        source = self.source_id
        if source.exists():
            if baseline_compromised:
                source._cn_mark_monitor_baseline_compromised(
                    safe_message,
                    run=self,
                )
            else:
                retry_days = min(max(source.cn_monitor_interval_days, 1), 7)
                next_monitor_date = (
                    fields.Date.context_today(source) + timedelta(days=retry_days)
                    if source.status == "valid"
                    else False
                )
                source._cn_monitor_write(
                    {
                        "cn_last_monitor_at": completed_at,
                        "cn_last_monitor_state": "failed",
                        "cn_last_monitor_message": safe_message,
                        "cn_latest_monitor_run_id": self.id,
                        "cn_next_monitor_date": next_monitor_date,
                    }
                )
        self.env["sudo.compliance.audit.event"]._log_records(
            self,
            "cn.authority_source_monitor.failed",
            previous_state="processing",
            new_state="failed",
            details={"source_id": source.id, "error_code": safe_code},
        )
        return False

    def _process(self):
        self.ensure_one()
        if self.state != "queued":
            raise UserError(_("只有待检查的来源监测批次可以执行。"))
        self._transition_write(
            {"state": "processing", "started_at": fields.Datetime.now()}
        )
        self.env["sudo.compliance.audit.event"]._log_records(
            self,
            "cn.authority_source_monitor.processing",
            previous_state="queued",
            new_state="processing",
        )
        try:
            with self.env.cr.savepoint():
                return self._process_success()
        except SourceBaselineIntegrityError as exc:
            return self._mark_failed(
                "SOURCE_BASELINE_INTEGRITY_ERROR",
                exc,
                baseline_compromised=True,
            )
        except (AccessError, UserError, ValidationError) as exc:
            return self._mark_failed("SOURCE_MONITOR_INPUT_ERROR", exc)
        except Exception as exc:
            return self._mark_failed(
                "UNEXPECTED_SOURCE_MONITOR_FAILURE",
                _(
                    "来源远端检查发生未预期错误：%(kind)s",
                    kind=type(exc).__name__,
                ),
            )

    @api.model
    def _cron_enqueue_due_sources(self, limit=20):
        today = fields.Date.context_today(self)
        china = self.env.ref("base.cn")
        sources = self.env["sudo.compliance.authority.source"].sudo().search(
            [
                ("country_id", "=", china.id),
                ("status", "=", "valid"),
                ("cn_monitor_enabled", "=", True),
                ("cn_next_monitor_date", "<=", today),
            ],
            order="cn_next_monitor_date, id",
            limit=max(int(limit or 20), 1),
        )
        queued = 0
        for source in sources:
            if self.sudo().search_count(
                [
                    ("source_id", "=", source.id),
                    ("state", "in", ("queued", "processing")),
                ]
            ):
                continue
            self.sudo().with_context(
                cn_source_monitor_schedule=_CN_SOURCE_MONITOR_SCHEDULE_MARKER
            ).enqueue(source, request_kind="scheduled")
            queued += 1
        return queued

    @api.model
    def _cron_process_runs(self, limit=2):
        processed = 0
        for _index in range(max(int(limit or 2), 1)):
            self.env.cr.execute(
                """
                    SELECT id
                      FROM sudo_cn_authority_source_monitor_run
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

    def action_process_now(self):
        if not self.source_id._can_author():
            raise AccessError(_("只有规则维护人员可以执行来源远端检查。"))
        for run in self:
            run._process()
        return True

    def action_cancel(self):
        if not self.source_id._can_author():
            raise AccessError(_("只有规则维护人员可以取消来源远端检查。"))
        for run in self:
            if run.state != "queued":
                raise UserError(_("只有待检查的来源监测批次可以取消。"))
            run._finalize_result(
                {
                    "state": "cancelled",
                    "completed_at": fields.Datetime.now(),
                    "result_summary": _("来源远端检查在执行前取消。"),
                    "error_code": False,
                    "error_message": False,
                }
            )
            self.env["sudo.compliance.audit.event"]._log_records(
                run,
                "cn.authority_source_monitor.cancelled",
                previous_state="queued",
                new_state="cancelled",
            )
        return True

    def action_open_source(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("中国官方来源"),
            "res_model": "sudo.compliance.authority.source",
            "res_id": self.source_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_open_candidate(self):
        self.ensure_one()
        if not self.candidate_source_id:
            raise UserError(_("当前检查记录没有变化候选。"))
        return {
            "type": "ir.actions.act_window",
            "name": _("官方来源变化候选"),
            "res_model": "sudo.compliance.authority.source",
            "res_id": self.candidate_source_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_open_impacted_rules(self):
        self.ensure_one()
        action = self.env.ref(
            "sudo_global_finance.action_compliance_rule_versions"
        ).read()[0]
        action["domain"] = [("id", "in", self.impacted_rule_version_ids.ids)]
        action["context"] = {}
        return action
