from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestChinaTaxpayerClassification(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.country = cls.env.ref("base.cn")
        cls.company = cls.env["res.company"].create(
            {
                "name": "China Taxpayer Classification Test Company",
                "currency_id": cls.env.ref("base.CNY").id,
                "country_id": cls.country.id,
                "account_fiscal_country_id": cls.country.id,
            }
        )
        cls.profile = cls.env["sudo.compliance.profile"].with_company(
            cls.company
        ).create(
            {
                "company_id": cls.company.id,
                "country_id": cls.country.id,
                "country_pack_id": cls.env.ref(
                    "sudo_country_pack_cn.compliance_country_pack_cn"
                ).id,
            }
        )
        cls.province = cls.env["res.country.state"].search(
            [("country_id", "=", cls.country.id)], limit=1
        )
        if not cls.province:
            cls.province = cls.env["res.country.state"].create(
                {
                    "name": "测试省级辖区",
                    "code": "TST",
                    "country_id": cls.country.id,
                }
            )
        cls.engine = cls.env["sudo.compliance.engine"]

    def _attachment(self, suffix="1"):
        return self.env["ir.attachment"].create(
            {
                "name": f"taxpayer-classification-{suffix}.txt",
                "raw": f"controlled classification evidence {suffix}".encode(),
            }
        )

    def _complete_values(self, suffix="1"):
        attachment = self._attachment(suffix)
        return {
            "profile_id": self.profile.id,
            "valid_from": "2026-01-01",
            "province_id": self.province.id,
            "local_jurisdiction_name": "测试市辖区",
            "local_jurisdiction_code": "CN-TEST-LOCAL",
            "tax_authority_name": "测试主管税务机关",
            "tax_authority_code": "CN-TAX-TEST",
            "vat_taxpayer_status": "general",
            "vat_filing_frequency": "monthly",
            "cit_taxpayer_status": "resident",
            "cit_collection_method": "accounts_based",
            "pit_withholding_status": "yes",
            "accounting_regime": "asbe",
            "source_type": "electronic_tax_bureau",
            "source_date": "2026-01-01",
            "source_reference": f"TEST-TAX-PROFILE-{suffix}",
            "scope_note": "测试身份快照，仅用于验证受控生命周期。",
            "evidence_attachment_ids": [Command.set(attachment.ids)],
        }

    def _classification(self, suffix="1", **overrides):
        values = self._complete_values(suffix)
        values.update(overrides)
        return self.env["sudo.cn.taxpayer.classification"].create(values)

    def _assessment(self):
        return self.env["sudo.compliance.assessment"].create(
            {
                "profile_id": self.profile.id,
                "evaluation_date": "2026-06-30",
                "period_start": "2026-01-01",
                "period_end": "2026-06-30",
            }
        )

    def _provider(self, key):
        return self.engine._fact_provider_registry()[key]

    def test_incomplete_snapshot_cannot_be_verified(self):
        classification = self.env[
            "sudo.cn.taxpayer.classification"
        ].create(
            {
                "profile_id": self.profile.id,
                "valid_from": "2026-01-01",
            }
        )

        with self.assertRaises(UserError):
            classification.action_verify()

        self.assertEqual(classification.state, "draft")
        self.assertFalse(classification.verification_checksum)

    def test_create_cannot_seed_a_forged_verified_state(self):
        classification = self.env[
            "sudo.cn.taxpayer.classification"
        ].create(
            {
                **self._complete_values("forged"),
                "state": "verified",
                "verification_checksum": "f" * 64,
            }
        )

        self.assertEqual(classification.state, "draft")
        self.assertFalse(classification.verification_checksum)

    def test_future_source_date_cannot_be_verified(self):
        classification = self._classification(
            "future-source", source_date="2099-01-01"
        )

        with self.assertRaises(UserError):
            classification.action_verify()

        self.assertEqual(classification.state, "draft")

    def test_whitespace_source_reference_is_normalized_and_rejected(self):
        classification = self._classification(
            "blank-reference", source_reference="   "
        )

        with self.assertRaises(UserError):
            classification.action_verify()

        self.assertFalse(classification.source_reference)

    def test_empty_attachment_cannot_satisfy_evidence_gate(self):
        empty_attachment = self.env["ir.attachment"].create(
            {"name": "empty-proof.txt", "raw": b""}
        )
        classification = self._classification(
            "empty-proof",
            evidence_attachment_ids=[Command.set(empty_attachment.ids)],
        )

        with self.assertRaises(UserError):
            classification.action_verify()

        self.assertEqual(classification.state, "draft")

    def test_verification_records_checksum_actor_and_audit_event(self):
        classification = self._classification()

        classification.action_verify()

        self.assertEqual(classification.state, "verified")
        self.assertEqual(classification.verified_by_id, self.env.user)
        self.assertEqual(len(classification.verification_checksum), 64)
        self.assertEqual(
            classification._current_integrity_state(), "verified"
        )
        event = self.env["sudo.compliance.audit.event"].search(
            [
                ("model_name", "=", classification._name),
                ("record_id", "=", classification.id),
                ("event_key", "=", "cn_taxpayer_classification.verified"),
            ]
        )
        self.assertEqual(len(event), 1)
        self.assertEqual(
            event.details_json["checksum"],
            classification.verification_checksum,
        )
        payload = event.details_json["verification_payload"]
        self.assertEqual(payload["vat_taxpayer_status"], "general")
        self.assertEqual(payload["local_jurisdiction_code"], "CN-TEST-LOCAL")
        self.assertEqual(len(payload["attachments"][0]["sha256"]), 64)

    def test_direct_state_write_is_blocked_and_change_resets_verification(self):
        classification = self._classification()
        classification.action_verify()

        with self.assertRaises(AccessError):
            classification.write({"state": "draft"})

        classification.scope_note = "经管理人员修改后需要重新核验。"

        self.assertEqual(classification.state, "draft")
        self.assertFalse(classification.verification_checksum)
        self.assertFalse(classification.verified_by_id)

    def test_verified_snapshot_requires_explicit_reset_before_deletion(self):
        classification = self._classification()
        classification.action_verify()

        with self.assertRaises(UserError):
            classification.unlink()

        classification.action_reset_to_draft()
        self.assertEqual(classification.state, "draft")
        classification.unlink()
        self.assertFalse(classification.exists())

    def test_non_china_profile_cannot_receive_china_classification(self):
        country = self.env.ref("base.us")
        company = self.env["res.company"].create(
            {
                "name": "Non-China Classification Test Company",
                "currency_id": self.env.ref("base.USD").id,
                "country_id": country.id,
                "account_fiscal_country_id": country.id,
            }
        )
        profile = self.env["sudo.compliance.profile"].with_company(
            company
        ).create(
            {"company_id": company.id, "country_id": country.id}
        )

        with self.assertRaises(ValidationError):
            self.env["sudo.cn.taxpayer.classification"].create(
                {"profile_id": profile.id, "valid_from": "2026-01-01"}
            )

    def test_overlapping_verified_snapshots_are_rejected(self):
        first = self._classification("first")
        first.action_verify()
        second = self._classification("second", valid_from="2026-06-01")

        with self.assertRaises(UserError):
            second.action_verify()

        self.assertEqual(second.state, "draft")

    def test_fact_is_missing_without_effective_snapshot(self):
        assessment = self._assessment()

        payload = self._provider(
            "cn.taxpayer.classification_verified"
        )(assessment, False)

        self.assertIsNone(payload["value"])
        self.assertEqual(payload["quality_state"], "missing")
        self.assertFalse(payload["is_complete"])

    def test_draft_and_verified_snapshot_have_distinct_fact_values(self):
        classification = self._classification()
        assessment = self._assessment()
        provider = self._provider("cn.taxpayer.classification_verified")

        draft_payload = provider(assessment, False)
        classification.action_verify()
        verified_payload = provider(assessment, False)
        detail = self._provider(
            "cn.taxpayer.classification_detail"
        )(assessment, False)

        self.assertIs(draft_payload["value"], False)
        self.assertIs(verified_payload["value"], True)
        self.assertEqual(detail["value"]["control_state"], "verified")
        self.assertEqual(detail["value"]["evidence_count"], 1)
        self.assertNotIn("source_reference", detail["value"])
        self.assertNotIn("attachment_ids", detail["value"])

    def test_attachment_change_is_detected_by_assessment_fact(self):
        classification = self._classification()
        classification.action_verify()
        classification.evidence_attachment_ids.raw = b"changed evidence"

        payload = self._provider(
            "cn.taxpayer.classification_verified"
        )(self._assessment(), False)
        detail = self._provider(
            "cn.taxpayer.classification_detail"
        )(self._assessment(), False)

        self.assertIs(payload["value"], False)
        self.assertEqual(
            detail["value"]["control_state"], "checksum_mismatch"
        )

    def test_company_record_rule_isolates_classification_records(self):
        own = self._classification()
        own.action_verify()
        other_company = self.env["res.company"].create(
            {
                "name": "Other China Classification Company",
                "currency_id": self.env.ref("base.CNY").id,
                "country_id": self.country.id,
                "account_fiscal_country_id": self.country.id,
            }
        )
        other_profile = self.env["sudo.compliance.profile"].with_company(
            other_company
        ).create(
            {
                "company_id": other_company.id,
                "country_id": self.country.id,
                "country_pack_id": self.env.ref(
                    "sudo_country_pack_cn.compliance_country_pack_cn"
                ).id,
            }
        )
        self.env["sudo.cn.taxpayer.classification"].with_company(
            other_company
        ).create(
            {
                **self._complete_values("other"),
                "profile_id": other_profile.id,
            }
        )
        user = self.env["res.users"].create(
            {
                "name": "China Classification Restricted User",
                "login": "cn_classification_restricted_user",
                "company_id": self.company.id,
                "company_ids": [Command.set(self.company.ids)],
                "group_ids": [
                    Command.link(
                        self.env.ref(
                            "sudo_global_finance.group_compliance_user"
                        ).id
                    )
                ],
            }
        )

        visible = self.env[
            "sudo.cn.taxpayer.classification"
        ].with_user(user).with_company(self.company).search([])

        self.assertIn(own, visible)
        self.assertEqual(
            set(visible.mapped("company_id").ids),
            {self.company.id},
        )
        with self.assertRaises(AccessError):
            own.with_user(user).with_company(self.company).write(
                {"scope_note": "普通用户不能修改已核验身份。"}
            )
