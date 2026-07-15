from datetime import date

from odoo import _, fields, models
from odoo.exceptions import UserError


USCC_REGISTRATION_TYPES = {
    "business_registration",
    "cn_uscc",
    "unified_social_credit_code",
    "uscc",
}
INVOICE_MOVE_TYPES = (
    "out_invoice",
    "out_refund",
    "in_invoice",
    "in_refund",
    "out_receipt",
    "in_receipt",
)


class SudoChinaComplianceEngine(models.AbstractModel):
    _inherit = "sudo.compliance.engine"

    def _fact_provider_registry(self):
        providers = super()._fact_provider_registry()
        providers.update(
            {
                "cn.company.unified_social_credit_code": (
                    self._provide_cn_unified_social_credit_code
                ),
                "cn.company.registration_evidence_count": (
                    self._provide_cn_registration_evidence_count
                ),
                "cn.company.fiscal_year_end_confirmed": (
                    self._provide_cn_fiscal_year_end_confirmed
                ),
                "cn.taxpayer.classification_verified": (
                    self._provide_cn_taxpayer_classification_verified
                ),
                "cn.taxpayer.classification_detail": (
                    self._provide_cn_taxpayer_classification_detail
                ),
                "cn.account.posted_move_count": self._provide_cn_posted_move_count,
                "cn.account.unposted_move_count": (
                    self._provide_cn_unposted_move_count
                ),
                "cn.account.posted_invoice_count": (
                    self._provide_cn_posted_invoice_count
                ),
                "cn.evidence.invoice_missing_attachment_count": (
                    self._provide_cn_invoice_missing_attachment_count
                ),
                "cn.vat_invoice.posted_line_without_tax_count": (
                    self._provide_cn_posted_invoice_line_without_tax_count
                ),
                "cn.master.transaction_partner_missing_tax_id_count": (
                    self._provide_cn_transaction_partner_missing_tax_id_count
                ),
            }
        )
        return providers

    def _taxpayer_classifications(self, assessment):
        classifications = self.env[
            "sudo.cn.taxpayer.classification"
        ]._for_profile_date(
            assessment.profile_id,
            fields.Date.to_date(assessment.evaluation_date),
        )
        if len(classifications) > 1:
            raise UserError(
                _("评估日存在多份中国纳税人身份快照，无法确定唯一身份。")
            )
        return classifications

    @staticmethod
    def _classification_control_state(classification):
        if classification.state != "verified":
            return "draft"
        return classification._current_integrity_state()

    def _provide_cn_taxpayer_classification_verified(
        self, assessment, _definition
    ):
        classifications = self._taxpayer_classifications(assessment)
        if not classifications:
            return {
                "value": None,
                "source_model": "sudo.cn.taxpayer.classification",
                "source_domain": [
                    ("profile_id", "=", assessment.profile_id.id)
                ],
                "record_count": 0,
                "aggregation_method": "single_effective_verified_snapshot",
                "quality_state": "missing",
                "is_complete": False,
                "is_full_dataset": True,
                "provider_version": "1",
            }
        control_state = self._classification_control_state(classifications)
        return {
            "value": control_state == "verified",
            "source_model": classifications._name,
            "source_record_ids": classifications.ids,
            "record_count": 1,
            "aggregation_method": "single_effective_verified_snapshot",
            "is_complete": True,
            "is_full_dataset": True,
            "provider_version": "1",
        }

    def _provide_cn_taxpayer_classification_detail(
        self, assessment, _definition
    ):
        classifications = self._taxpayer_classifications(assessment)
        if not classifications:
            return {
                "value": {"control_state": "missing"},
                "source_model": "sudo.cn.taxpayer.classification",
                "source_domain": [
                    ("profile_id", "=", assessment.profile_id.id)
                ],
                "record_count": 0,
                "aggregation_method": "single_effective_snapshot_detail",
                "quality_state": "missing",
                "is_complete": False,
                "is_full_dataset": True,
                "provider_version": "1",
            }
        control_state = self._classification_control_state(classifications)
        return {
            "value": {
                "control_state": control_state,
                "valid_from": fields.Date.to_string(
                    classifications.valid_from
                ),
                "valid_to": fields.Date.to_string(classifications.valid_to),
                "province_code": classifications.province_id.code or None,
                "local_jurisdiction_code": (
                    classifications.local_jurisdiction_code
                ),
                "vat_taxpayer_status": (
                    classifications.vat_taxpayer_status
                ),
                "vat_filing_frequency": (
                    classifications.vat_filing_frequency
                ),
                "cit_taxpayer_status": (
                    classifications.cit_taxpayer_status
                ),
                "cit_collection_method": (
                    classifications.cit_collection_method
                ),
                "pit_withholding_status": (
                    classifications.pit_withholding_status
                ),
                "accounting_regime": classifications.accounting_regime,
                "source_type": classifications.source_type,
                "evidence_count": len(
                    classifications.evidence_attachment_ids
                ),
            },
            "source_model": classifications._name,
            "source_record_ids": classifications.ids,
            "record_count": 1,
            "aggregation_method": "single_effective_snapshot_detail",
            "is_complete": True,
            "is_full_dataset": True,
            "provider_version": "1",
        }

    @staticmethod
    def _registration_type(registration):
        return (registration.registration_type or "").strip().lower()

    def _uscc_registrations(self, assessment):
        target = fields.Date.to_date(assessment.evaluation_date)
        return assessment.profile_id.registration_ids.filtered(
            lambda registration: (
                self._registration_type(registration)
                in USCC_REGISTRATION_TYPES
                and registration.state == "active"
                and (
                    not registration.valid_from
                    or registration.valid_from <= target
                )
                and (
                    not registration.valid_to
                    or registration.valid_to >= target
                )
            )
        )

    @staticmethod
    def _company_registration_fallback(company):
        for record in (company, company.partner_id):
            for field_name in ("company_registry", "vat"):
                if field_name not in record._fields:
                    continue
                value = record[field_name]
                if value and str(value).strip():
                    return record, str(value).strip()
        return company.env["res.company"], False

    def _provide_cn_unified_social_credit_code(self, assessment, _definition):
        registrations = self._uscc_registrations(assessment)
        numbered = registrations.filtered(
            lambda registration: bool(
                registration.registration_number
                and registration.registration_number.strip()
            )
        )
        if len(numbered) > 1:
            raise UserError(_("存在多个同时有效的统一社会信用代码登记记录。"))
        if numbered:
            return {
                "value": numbered.registration_number.strip(),
                "source_model": numbered._name,
                "source_record_ids": numbered.ids,
                "record_count": 1,
                "aggregation_method": "single_active_controlled_registration",
                "is_complete": True,
                "is_full_dataset": True,
                "provider_version": "1",
            }

        source, fallback = self._company_registration_fallback(
            assessment.company_id
        )
        if fallback:
            return {
                "value": fallback,
                "source_model": source._name,
                "source_record_ids": source.ids,
                "record_count": 1,
                "aggregation_method": "uncontrolled_company_identifier_fallback",
                "quality_state": "truncated",
                "is_complete": False,
                "is_full_dataset": True,
                "provider_version": "1",
            }
        return {
            "value": None,
            "source_model": "sudo.compliance.registration",
            "source_domain": [("profile_id", "=", assessment.profile_id.id)],
            "record_count": len(registrations),
            "aggregation_method": "active_controlled_registration",
            "quality_state": "missing",
            "is_complete": False,
            "is_full_dataset": True,
            "provider_version": "1",
        }

    def _provide_cn_registration_evidence_count(self, assessment, _definition):
        registrations = self._uscc_registrations(assessment)
        if len(registrations) > 1:
            raise UserError(_("存在多个同时有效的统一社会信用代码登记记录。"))
        if not registrations:
            return {
                "value": None,
                "source_model": "sudo.compliance.registration",
                "source_domain": [
                    ("profile_id", "=", assessment.profile_id.id)
                ],
                "record_count": 0,
                "aggregation_method": "registration_attachment_clue_count",
                "quality_state": "missing",
                "is_complete": False,
                "is_full_dataset": True,
                "provider_version": "1",
            }
        count = len(registrations.evidence_attachment_ids)
        return {
            "value": count,
            "source_model": registrations._name,
            "source_record_ids": registrations.ids,
            "record_count": len(registrations),
            "aggregation_method": "registration_attachment_clue_count",
            "quality_state": "complete" if count else "missing",
            "is_complete": bool(count),
            "is_full_dataset": True,
            "provider_version": "1",
        }

    def _provide_cn_fiscal_year_end_confirmed(self, assessment, _definition):
        profile = assessment.profile_id
        try:
            date(2024, profile.fiscal_year_end_month, profile.fiscal_year_end_day)
        except (TypeError, ValueError):
            return {
                "value": None,
                "source_model": profile._name,
                "source_record_ids": profile.ids,
                "record_count": 1,
                "aggregation_method": "validated_confirmed_profile_fields",
                "quality_state": "error",
                "is_complete": False,
                "is_full_dataset": True,
                "provider_version": "1",
            }
        return {
            "value": bool(profile.fiscal_year_end_confirmed),
            "source_model": profile._name,
            "source_record_ids": profile.ids,
            "record_count": 1,
            "aggregation_method": "validated_confirmed_profile_fields",
            "is_complete": True,
            "is_full_dataset": True,
            "provider_version": "1",
        }

    @staticmethod
    def _move_domain(assessment, states=None, move_types=None):
        domain = [("company_id", "=", assessment.company_id.id)]
        if states:
            domain.append(("state", "in", states))
        if move_types:
            domain.append(("move_type", "in", move_types))
        if assessment.period_start:
            domain.append(("date", ">=", assessment.period_start))
        if assessment.period_end:
            domain.append(("date", "<=", assessment.period_end))
        return domain

    def _move_count_payload(self, assessment, states=None, move_types=None):
        domain = self._move_domain(assessment, states, move_types)
        count = (
            self.env["account.move"]
            .with_company(assessment.company_id)
            .search_count(domain)
        )
        return {
            "value": count,
            "source_model": "account.move",
            "source_domain": domain,
            "record_count": count,
            "aggregation_method": "search_count_full_domain",
            "is_complete": True,
            "is_full_dataset": True,
            "provider_version": "1",
        }

    def _provide_cn_posted_move_count(self, assessment, _definition):
        return self._move_count_payload(assessment, states=["posted"])

    def _provide_cn_unposted_move_count(self, assessment, _definition):
        return self._move_count_payload(assessment, states=["draft"])

    def _provide_cn_posted_invoice_count(self, assessment, _definition):
        return self._move_count_payload(
            assessment,
            states=["posted"],
            move_types=INVOICE_MOVE_TYPES,
        )

    def _provide_cn_invoice_missing_attachment_count(
        self, assessment, _definition
    ):
        domain = self._move_domain(
            assessment,
            states=["posted"],
            move_types=INVOICE_MOVE_TYPES,
        )
        moves = (
            self.env["account.move"]
            .with_company(assessment.company_id)
            .search(domain)
        )
        attached_move_ids = set(
            self.env["ir.attachment"]
            .sudo()
            .search(
                [
                    ("res_model", "=", "account.move"),
                    ("res_id", "in", moves.ids),
                    ("res_field", "=", False),
                    ("type", "=", "binary"),
                ]
            )
            .mapped("res_id")
        )
        missing_count = len(moves) - len(attached_move_ids)
        return {
            "value": missing_count,
            "source_model": "account.move",
            "source_domain": domain,
            "record_count": missing_count,
            "aggregation_method": "full_domain_attachment_antijoin",
            "is_complete": True,
            "is_full_dataset": True,
            "provider_version": "1",
        }

    @staticmethod
    def _line_period_domain(assessment):
        domain = [("company_id", "=", assessment.company_id.id)]
        if assessment.period_start:
            domain.append(("date", ">=", assessment.period_start))
        if assessment.period_end:
            domain.append(("date", "<=", assessment.period_end))
        return domain

    def _provide_cn_posted_invoice_line_without_tax_count(
        self, assessment, _definition
    ):
        domain = self._line_period_domain(assessment) + [
            ("parent_state", "=", "posted"),
            ("move_id.move_type", "in", INVOICE_MOVE_TYPES),
            ("tax_ids", "=", False),
            (
                "account_id.account_type",
                "in",
                (
                    "income",
                    "income_other",
                    "expense",
                    "expense_depreciation",
                    "expense_direct_cost",
                ),
            ),
        ]
        count = (
            self.env["account.move.line"]
            .with_company(assessment.company_id)
            .search_count(domain)
        )
        return {
            "value": count,
            "source_model": "account.move.line",
            "source_domain": domain,
            "record_count": count,
            "aggregation_method": "full_period_posted_invoice_tax_antijoin",
            "is_complete": True,
            "is_full_dataset": True,
            "provider_version": "1",
        }

    def _provide_cn_transaction_partner_missing_tax_id_count(
        self, assessment, _definition
    ):
        domain = self._move_domain(
            assessment,
            states=["posted"],
            move_types=INVOICE_MOVE_TYPES,
        )
        moves = (
            self.env["account.move"]
            .with_company(assessment.company_id)
            .search(domain)
        )
        partners = moves.mapped("commercial_partner_id")
        missing = partners.filtered(lambda partner: not partner.vat)
        return {
            "value": len(missing),
            "source_model": "res.partner",
            "source_record_ids": missing.ids,
            "source_domain": [("id", "in", partners.ids)],
            "record_count": len(missing),
            "aggregation_method": "transaction_partner_tax_id_presence_signal",
            "is_complete": True,
            "is_full_dataset": True,
            "provider_version": "1",
        }
