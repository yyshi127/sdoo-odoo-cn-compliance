import logging

from odoo import api, fields, models

from .cit_period_reconciliation import (
    _CIT_PERIOD_TRANSITION_MARKER,
    _CIT_PERIOD_SNAPSHOT_LANG,
    _checksum as _cit_checksum,
)
from .iit_period_reconciliation import (
    _IIT_PERIOD_TRANSITION_MARKER,
    _IIT_PERIOD_SNAPSHOT_LANG,
    _checksum as _iit_checksum,
)
from .invoice_reconciliation import (
    _RECONCILIATION_TRANSITION_MARKER,
    _RECONCILIATION_SNAPSHOT_LANG,
    _checksum as _invoice_checksum,
)
from .vat_period_reconciliation import (
    _VAT_PERIOD_TRANSITION_MARKER,
    _VAT_PERIOD_SNAPSHOT_LANG,
    _checksum as _vat_checksum,
)

_logger = logging.getLogger(__name__)


def _monitor_candidates(model, limit):
    limit = max(int(limit or 1), 1)
    domain = [("state", "=", "succeeded")]
    unchecked = model.search(
        domain + [("source_checked_at", "=", False)],
        order="finished_at desc, id desc",
        limit=limit,
    )
    remaining = limit - len(unchecked)
    checked = model.browse()
    if remaining:
        checked = model.search(
            domain + [("source_checked_at", "!=", False)],
            order="source_checked_at asc, id asc",
            limit=remaining,
        )
    return model.browse(unchecked.ids + checked.ids)


def _monitor_current_results(model, limit):
    queued = 0
    for run in _monitor_candidates(model, limit):
        try:
            with model.env.cr.savepoint():
                active = model.search_count(
                    [
                        ("profile_id", "=", run.profile_id.id),
                        ("period_start", "=", run.period_start),
                        ("period_end", "=", run.period_end),
                        ("state", "in", ("queued", "processing")),
                    ],
                    limit=1,
                )
                checked_at = fields.Datetime.now()
                if active:
                    run._cn_source_monitor_write(
                        {"source_checked_at": checked_at}
                    )
                    continue

                current_checksums = run._cn_current_source_checksums()
                stored_checksums = run._cn_stored_source_checksums()
                run._cn_source_monitor_write(
                    {"source_checked_at": checked_at}
                )
                if current_checksums == stored_checksums:
                    continue

                replacement = run._cn_enqueue_source_recalculation()
                queued += 1
                model.env["sudo.compliance.audit.event"]._log_records(
                    run,
                    run._cn_source_change_event_key,
                    previous_state="succeeded",
                    new_state="succeeded",
                    details={
                        "replacement_run_id": replacement.id,
                        "period_start": fields.Date.to_string(
                            run.period_start
                        ),
                        "period_end": fields.Date.to_string(run.period_end),
                        "stored_checksums": stored_checksums,
                        "current_checksums": current_checksums,
                        "reason": "source_snapshot_changed",
                    },
                )
        except Exception as exc:  # noqa: BLE001
            _logger.exception(
                "China reconciliation source monitor failed for %s,%s",
                run._name,
                run.id,
            )
            run._cn_source_monitor_write(
                {"source_checked_at": fields.Datetime.now()}
            )
            model.env["sudo.compliance.audit.event"]._log_records(
                run,
                run._cn_source_monitor_failed_event_key,
                previous_state=run.state,
                new_state=run.state,
                details={
                    "period_start": fields.Date.to_string(run.period_start),
                    "period_end": fields.Date.to_string(run.period_end),
                    "error_type": type(exc).__name__,
                    "reason": "source_monitor_failed",
                },
            )
    return queued


class SudoChinaEinvoiceReconciliationSourceMonitor(models.Model):
    _inherit = "sudo.cn.einvoice.reconciliation.run"

    source_checked_at = fields.Datetime(
        string="来源最近检查时间",
        readonly=True,
        copy=False,
    )
    _cn_source_change_event_key = (
        "cn_einvoice_reconciliation.source_change_recalculation_queued"
    )
    _cn_source_monitor_failed_event_key = (
        "cn_einvoice_reconciliation.source_monitor_failed"
    )

    def _cn_source_monitor_write(self, values):
        return self.with_context(
            cn_reconciliation_transition=_RECONCILIATION_TRANSITION_MARKER
        ).write(values)

    def _cn_current_source_checksums(self):
        self.ensure_one()
        run = self.with_context(lang=_RECONCILIATION_SNAPSHOT_LANG)
        documents = run._source_documents()
        moves = (
            run._ledger_moves()
            if documents
            else run.env["account.move"].browse()
        )
        _indexes, _move_count, ledger_checksum = run._build_move_indexes(
            moves
        )
        source_checksum = _invoice_checksum(
            [
                {
                    "document_id": document.id,
                    "document_checksum": document.document_checksum,
                    "parse_run_checksum": document.parse_run_id.output_checksum,
                }
                for document in documents
            ]
        )
        return {
            "source_snapshot_checksum": source_checksum,
            "ledger_snapshot_checksum": ledger_checksum,
        }

    def _cn_stored_source_checksums(self):
        self.ensure_one()
        return {
            "source_snapshot_checksum": self.source_snapshot_checksum or None,
            "ledger_snapshot_checksum": self.ledger_snapshot_checksum or None,
        }

    def _cn_enqueue_source_recalculation(self):
        self.ensure_one()
        return self.env[self._name].with_company(self.company_id).enqueue(
            self.profile_id,
            self.period_start,
            self.period_end,
        )

    @api.model
    def _cn_monitor_current_results(self, limit=5):
        return _monitor_current_results(self, limit)


class SudoChinaVatPeriodReconciliationSourceMonitor(models.Model):
    _inherit = "sudo.cn.vat.period.reconciliation.run"

    source_checked_at = fields.Datetime(
        string="来源最近检查时间",
        readonly=True,
        copy=False,
    )
    _cn_source_change_event_key = (
        "cn_vat_period_reconciliation.source_change_recalculation_queued"
    )
    _cn_source_monitor_failed_event_key = (
        "cn_vat_period_reconciliation.source_monitor_failed"
    )

    def _cn_source_monitor_write(self, values):
        return self.with_context(
            cn_vat_period_transition=_VAT_PERIOD_TRANSITION_MARKER
        ).write(values)

    def _cn_current_source_checksums(self):
        self.ensure_one()
        run = self.with_context(lang=_VAT_PERIOD_SNAPSHOT_LANG)
        issues = {}
        accounting = run._collect_accounting(issues)
        einvoices = run._collect_einvoices(issues)
        filing = run._collect_filing(issues)
        payments = run._collect_payments(issues)
        return {
            "accounting_snapshot_checksum": _vat_checksum(
                accounting["snapshot"]
            ),
            "accounting_scope_snapshot_checksum": _vat_checksum(
                accounting["scope_snapshot"]
            ),
            "einvoice_snapshot_checksum": _vat_checksum(
                einvoices["snapshot"]
            ),
            "filing_snapshot_checksum": _vat_checksum(filing["snapshot"]),
            "payment_snapshot_checksum": _vat_checksum(payments["snapshot"]),
        }

    def _cn_stored_source_checksums(self):
        self.ensure_one()
        return {
            "accounting_snapshot_checksum": (
                self.accounting_snapshot_checksum or None
            ),
            "accounting_scope_snapshot_checksum": (
                self.accounting_scope_snapshot_checksum or None
            ),
            "einvoice_snapshot_checksum": (
                self.einvoice_snapshot_checksum or None
            ),
            "filing_snapshot_checksum": self.filing_snapshot_checksum or None,
            "payment_snapshot_checksum": self.payment_snapshot_checksum or None,
        }

    def _cn_enqueue_source_recalculation(self):
        self.ensure_one()
        return self.env[self._name].with_company(self.company_id).enqueue(
            self.profile_id,
            self.period_start,
            self.period_end,
            self.vat_tax_type_code,
        )

    @api.model
    def _cn_monitor_current_results(self, limit=5):
        return _monitor_current_results(self, limit)


class SudoChinaCitPeriodReconciliationSourceMonitor(models.Model):
    _inherit = "sudo.cn.cit.period.reconciliation.run"

    source_checked_at = fields.Datetime(
        string="来源最近检查时间",
        readonly=True,
        copy=False,
    )
    _cn_source_change_event_key = (
        "cn_cit_period_reconciliation.source_change_recalculation_queued"
    )
    _cn_source_monitor_failed_event_key = (
        "cn_cit_period_reconciliation.source_monitor_failed"
    )

    def _cn_source_monitor_write(self, values):
        return self.with_context(
            cn_cit_period_transition=_CIT_PERIOD_TRANSITION_MARKER
        ).write(values)

    def _cn_current_source_checksums(self):
        self.ensure_one()
        run = self.with_context(lang=_CIT_PERIOD_SNAPSHOT_LANG)
        issues = []
        accounting = run._collect_accounting(issues)
        filing = run._collect_filing(issues)
        payments = run._collect_payments(issues)
        return {
            "accounting_scope_snapshot_checksum": _cit_checksum(
                accounting["scope_snapshot"]
            ),
            "accounting_snapshot_checksum": _cit_checksum(
                accounting["snapshot"]
            ),
            "filing_snapshot_checksum": _cit_checksum(filing["snapshot"]),
            "payment_snapshot_checksum": _cit_checksum(payments["snapshot"]),
        }

    def _cn_stored_source_checksums(self):
        self.ensure_one()
        return {
            "accounting_scope_snapshot_checksum": (
                self.accounting_scope_snapshot_checksum or None
            ),
            "accounting_snapshot_checksum": (
                self.accounting_snapshot_checksum or None
            ),
            "filing_snapshot_checksum": self.filing_snapshot_checksum or None,
            "payment_snapshot_checksum": self.payment_snapshot_checksum or None,
        }

    def _cn_enqueue_source_recalculation(self):
        self.ensure_one()
        return self.env[self._name].with_company(self.company_id).enqueue(
            self.profile_id,
            self.period_start,
            self.period_end,
            self.return_period_type,
            self.cit_tax_type_code,
        )

    @api.model
    def _cn_monitor_current_results(self, limit=5):
        return _monitor_current_results(self, limit)


class SudoChinaIitPeriodReconciliationSourceMonitor(models.Model):
    _inherit = "sudo.cn.iit.period.reconciliation.run"

    source_checked_at = fields.Datetime(
        string="来源最近检查时间",
        readonly=True,
        copy=False,
    )
    _cn_source_change_event_key = (
        "cn_iit_period_reconciliation.source_change_recalculation_queued"
    )
    _cn_source_monitor_failed_event_key = (
        "cn_iit_period_reconciliation.source_monitor_failed"
    )

    def _cn_source_monitor_write(self, values):
        return self.with_context(
            cn_iit_period_transition=_IIT_PERIOD_TRANSITION_MARKER
        ).write(values)

    def _cn_current_source_checksums(self):
        self.ensure_one()
        run = self.with_context(lang=_IIT_PERIOD_SNAPSHOT_LANG)
        issues = []
        scope = run._collect_scope(issues)
        payroll = run._collect_payroll(issues, scope)
        filing = run._collect_filing(issues, scope)
        payments = run._collect_payments(issues)
        accounting = run._collect_accounting(issues, scope, payments)
        return {
            "accounting_scope_snapshot_checksum": _iit_checksum(
                scope["snapshot"]
            ),
            "accounting_snapshot_checksum": _iit_checksum(
                accounting["snapshot"]
            ),
            "payroll_snapshot_checksum": _iit_checksum(payroll["snapshot"]),
            "filing_snapshot_checksum": _iit_checksum(filing["snapshot"]),
            "payment_snapshot_checksum": _iit_checksum(payments["snapshot"]),
        }

    def _cn_stored_source_checksums(self):
        self.ensure_one()
        return {
            "accounting_scope_snapshot_checksum": (
                self.accounting_scope_snapshot_checksum or None
            ),
            "accounting_snapshot_checksum": (
                self.accounting_snapshot_checksum or None
            ),
            "payroll_snapshot_checksum": self.payroll_snapshot_checksum or None,
            "filing_snapshot_checksum": self.filing_snapshot_checksum or None,
            "payment_snapshot_checksum": self.payment_snapshot_checksum or None,
        }

    def _cn_enqueue_source_recalculation(self):
        self.ensure_one()
        return self.env[self._name].with_company(self.company_id).enqueue(
            self.profile_id,
            self.period_start,
            self.period_end,
            self.iit_tax_type_code,
        )

    @api.model
    def _cn_monitor_current_results(self, limit=5):
        return _monitor_current_results(self, limit)


class SudoComplianceProfileReconciliationSourceMonitor(models.Model):
    _inherit = "sudo.compliance.profile"

    @api.model
    def _cron_monitor_cn_reconciliation_sources(self, limit=20):
        per_model_limit = max(int(limit or 1) // 4, 1)
        queued = 0
        for model_name in (
            "sudo.cn.einvoice.reconciliation.run",
            "sudo.cn.vat.period.reconciliation.run",
            "sudo.cn.cit.period.reconciliation.run",
            "sudo.cn.iit.period.reconciliation.run",
        ):
            queued += (
                self.env[model_name]
                .sudo()
                ._cn_monitor_current_results(limit=per_model_limit)
            )
        return queued
