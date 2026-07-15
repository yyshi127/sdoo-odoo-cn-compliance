from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestChinaExternalDataset(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.country = cls.env.ref("base.cn")
        cls.company = cls.env["res.company"].create(
            {
                "name": "China External Dataset Test Company",
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
        cls.reviewer = cls.env["res.users"].create(
            {
                "name": "China Dataset Independent Reviewer",
                "login": "cn_dataset_independent_reviewer",
                "company_id": cls.company.id,
                "company_ids": [Command.set(cls.company.ids)],
                "group_ids": [
                    Command.link(
                        cls.env.ref(
                            "sudo_global_finance.group_compliance_manager"
                        ).id
                    )
                ],
            }
        )

    def _attachment(self, suffix="1", content=None):
        return self.env["ir.attachment"].create(
            {
                "name": f"cn-external-dataset-{suffix}.csv",
                "raw": (
                    f"controlled dataset {suffix}".encode()
                    if content is None
                    else content
                ),
                "mimetype": "text/csv",
            }
        )

    def _complete_values(self, suffix="1"):
        attachment = self._attachment(suffix)
        return {
            "profile_id": self.profile.id,
            "dataset_type": "electronic_invoice",
            "period_start": "2026-01-01",
            "period_end": "2026-06-30",
            "coverage_scope": "full",
            "scope_note": "覆盖测试期间全部受控导出记录，未执行税法判断。",
            "source_channel": "official_export",
            "source_system_name": "测试官方系统",
            "source_reference": f"CN-DATASET-{suffix}",
            "source_generated_at": "2026-06-30 09:00:00",
            "data_format": "csv",
            "authorization_basis": "测试公司自有账户受控导出，仅用于自动化测试。",
            "acquired_at": "2026-06-30 10:00:00",
            "declared_record_count": 2,
            "currency_id": self.env.ref("base.CNY").id,
            "declared_total_amount": 1060,
            "declared_tax_amount": 60,
            "source_attachment_ids": [Command.set(attachment.ids)],
            "authenticity_state": "not_checked",
        }

    def _dataset(self, suffix="1", **overrides):
        values = self._complete_values(suffix)
        values.update(overrides)
        return self.env["sudo.cn.external.dataset"].create(values)

    def _seal(self, dataset):
        return dataset.with_user(self.reviewer).with_company(
            self.company
        ).action_seal()

    def test_create_cannot_forge_sealed_state_or_collector(self):
        dataset = self.env["sudo.cn.external.dataset"].create(
            {
                **self._complete_values("forged"),
                "state": "sealed",
                "acquired_by_id": self.reviewer.id,
                "seal_checksum": "f" * 64,
            }
        )

        self.assertEqual(dataset.state, "draft")
        self.assertEqual(dataset.acquired_by_id, self.env.user)
        self.assertFalse(dataset.seal_checksum)

    def test_incomplete_or_empty_dataset_cannot_be_sealed(self):
        empty_attachment = self._attachment("empty", content=b"")
        dataset = self.env["sudo.cn.external.dataset"].create(
            {
                "profile_id": self.profile.id,
                "dataset_type": "vat_filing",
                "period_start": "2026-04-01",
                "period_end": "2026-06-30",
                "declared_record_count": 0,
                "source_attachment_ids": [
                    Command.set(empty_attachment.ids)
                ],
            }
        )

        with self.assertRaises(UserError):
            self._seal(dataset)

        self.assertEqual(dataset.state, "draft")

    def test_independent_reviewer_seals_checksum_and_audit_event(self):
        dataset = self._dataset()

        self._seal(dataset)

        self.assertEqual(dataset.state, "sealed")
        self.assertEqual(dataset.sealed_by_id, self.reviewer)
        self.assertEqual(dataset.review_control_state, "independent")
        self.assertEqual(len(dataset.seal_checksum), 64)
        self.assertEqual(dataset._current_integrity_state(), "verified")
        manifest = dataset.sealed_file_manifest_json
        self.assertEqual(len(manifest["source_attachments"]), 1)
        self.assertEqual(
            len(manifest["source_attachments"][0]["sha256"]),
            64,
        )
        event = self.env["sudo.compliance.audit.event"].search(
            [
                ("model_name", "=", dataset._name),
                ("record_id", "=", dataset.id),
                ("event_key", "=", "cn_external_dataset.sealed"),
            ]
        )
        self.assertEqual(len(event), 1)
        self.assertTrue(event.details_json["independent_review"])
        self.assertFalse(event.details_json["separation_exception_used"])
        self.assertNotIn("source_reference", event.details_json)

    def test_same_person_requires_audited_exception_reason(self):
        dataset = self._dataset("same-person")

        with self.assertRaises(UserError):
            dataset.action_seal()

        dataset.separation_exception_reason = (
            "当前仅为隔离测试环境且没有第二名复核用户，正式使用前必须改为双人复核。"
        )
        dataset.action_seal()

        self.assertEqual(dataset.state, "sealed")
        self.assertEqual(dataset.review_control_state, "exception")
        event = self.env["sudo.compliance.audit.event"].search(
            [
                ("model_name", "=", dataset._name),
                ("record_id", "=", dataset.id),
                ("event_key", "=", "cn_external_dataset.sealed"),
            ]
        )
        self.assertTrue(event.details_json["separation_exception_used"])
        self.assertFalse(event.details_json["independent_review"])

    def test_signed_voucher_requires_positive_authenticity_evidence(self):
        dataset = self._dataset(
            "signed",
            source_channel="signed_electronic_voucher",
        )

        with self.assertRaises(UserError):
            self._seal(dataset)

        dataset.write(
            {
                "authenticity_state": "official_tool_passed",
                "authenticity_method": "财政部电子凭证工具包测试桩",
                "authenticity_reference": "VERIFY-TEST-001",
                "authenticity_evidence_attachment_ids": [
                    Command.set(self._attachment("verification").ids)
                ],
            }
        )
        self._seal(dataset)

        self.assertEqual(dataset.authenticity_state, "official_tool_passed")
        self.assertEqual(dataset.integrity_state, "verified")

    def test_failed_authenticity_result_requires_failure_evidence(self):
        dataset = self._dataset(
            "failed-authenticity",
            authenticity_state="official_tool_failed",
        )

        with self.assertRaises(UserError):
            self._seal(dataset)

        dataset.write(
            {
                "authenticity_method": "测试验证工具，不用于生产",
                "authenticity_reference": "FAILED-VERIFY-TEST-001",
                "authenticity_evidence_attachment_ids": [
                    Command.set(self._attachment("failed-result").ids)
                ],
            }
        )
        self._seal(dataset)

        self.assertEqual(dataset.state, "sealed")
        self.assertEqual(dataset.authenticity_state, "official_tool_failed")

    def test_direct_state_change_edit_and_delete_are_blocked_after_seal(self):
        dataset = self._dataset("locked")
        self._seal(dataset)

        with self.assertRaises(AccessError):
            dataset.write({"state": "draft"})
        with self.assertRaises(AccessError):
            dataset.write({"scope_note": "封存后不得直接改写。"})
        with self.assertRaises(UserError):
            dataset.unlink()

    def test_source_attachment_tampering_changes_integrity_state(self):
        dataset = self._dataset("tamper")
        self._seal(dataset)

        dataset.source_attachment_ids.raw = b"changed after seal"

        self.assertEqual(
            dataset._current_integrity_state(),
            "checksum_mismatch",
        )

    def test_sealed_replacement_supersedes_original(self):
        original = self._dataset("original")
        self._seal(original)
        replacement = original.copy({"supersedes_id": original.id})

        self._seal(replacement)

        self.assertEqual(original.state, "superseded")
        self.assertEqual(replacement.state, "sealed")
        self.assertEqual(replacement.supersedes_id, original)
        self.assertEqual(original.replacement_ids, replacement)
        event = self.env["sudo.compliance.audit.event"].search(
            [
                ("record_id", "=", original.id),
                ("event_key", "=", "cn_external_dataset.superseded"),
            ]
        )
        self.assertEqual(event.details_json["replacement_id"], replacement.id)

    def test_replacement_must_keep_profile_and_dataset_type(self):
        original = self._dataset("type-original")
        self._seal(original)

        with self.assertRaises(ValidationError):
            self._dataset(
                "wrong-type",
                dataset_type="tax_payment",
                supersedes_id=original.id,
            )

    def test_non_china_profile_is_rejected(self):
        country = self.env.ref("base.us")
        company = self.env["res.company"].create(
            {
                "name": "Non-China External Dataset Company",
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
            self.env["sudo.cn.external.dataset"].with_company(company).create(
                {
                    **self._complete_values("non-cn"),
                    "profile_id": profile.id,
                }
            )

    def test_sensitive_data_requires_control_note(self):
        dataset = self._dataset(
            "sensitive",
            dataset_type="iit_withholding",
            contains_sensitive_data=True,
            data_control_note=False,
        )

        with self.assertRaises(UserError):
            self._seal(dataset)

        dataset.data_control_note = "仅授权薪税复核人员访问，并按测试制度到期删除。"
        self._seal(dataset)
        self.assertEqual(dataset.state, "sealed")

    def test_company_rule_and_read_only_user_access(self):
        own = self._dataset("own")
        other_company = self.env["res.company"].create(
            {
                "name": "Other China External Dataset Company",
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
        self.env["sudo.cn.external.dataset"].with_company(other_company).create(
            {
                **self._complete_values("other"),
                "profile_id": other_profile.id,
            }
        )
        user = self.env["res.users"].create(
            {
                "name": "China Dataset Read Only User",
                "login": "cn_dataset_read_only_user",
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
        model = self.env["sudo.cn.external.dataset"].with_user(
            user
        ).with_company(self.company)

        visible = model.search([])

        self.assertIn(own, visible)
        self.assertEqual(set(visible.mapped("company_id").ids), {self.company.id})
        with self.assertRaises(AccessError):
            model.create(self._complete_values("forbidden-create"))
        with self.assertRaises(AccessError):
            own.with_user(user).write({"scope_note": "普通用户不可修改。"})
