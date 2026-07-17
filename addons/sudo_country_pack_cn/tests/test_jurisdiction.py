import json
import uuid

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestChinaJurisdictionPackagedSafety(TransactionCase):
    def test_packaged_country_pack_does_not_seed_active_jurisdictions_or_local_rules(self):
        self.assertFalse(
            self.env["sudo.cn.jurisdiction.version"].search(
                [("state", "=", "active")]
            )
        )
        rules = self.env["sudo.compliance.rule"].search(
            [("code", "like", "CN-%")]
        )
        self.assertGreaterEqual(len(rules), 11)
        self.assertFalse(rules.version_ids.filtered("cn_jurisdiction_ids"))
        features = self.env.ref(
            "sudo_country_pack_cn.compliance_country_pack_cn"
        ).capability_json["features"]
        self.assertTrue(features["jurisdiction"])
        self.assertTrue(features["jurisdiction_governance"])
        self.assertTrue(features["local_rule_scope"])


@tagged("post_install", "-at_install")
class TestChinaJurisdictionGovernance(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.country = cls.env.ref("base.cn")
        cls.currency = cls.env.ref("base.CNY")
        cls.country_pack = cls.env.ref(
            "sudo_country_pack_cn.compliance_country_pack_cn"
        )
        cls.company = cls.env["res.company"].create(
            {
                "name": "China Jurisdiction Test Company",
                "currency_id": cls.currency.id,
                "country_id": cls.country.id,
                "account_fiscal_country_id": cls.country.id,
            }
        )
        cls.author = new_test_user(
            cls.env,
            login="cn_jurisdiction_author",
            groups=(
                "base.group_user,"
                "sudo_global_finance.group_compliance_rule_author"
            ),
            company_id=cls.company.id,
            company_ids=[cls.company.id],
        )
        cls.approver = new_test_user(
            cls.env,
            login="cn_jurisdiction_approver",
            groups=(
                "base.group_user,"
                "sudo_global_finance.group_compliance_rule_approver"
            ),
            company_id=cls.company.id,
            company_ids=[cls.company.id],
        )
        cls.author_approver = new_test_user(
            cls.env,
            login="cn_jurisdiction_author_approver",
            groups=(
                "base.group_user,"
                "sudo_global_finance.group_compliance_rule_author,"
                "sudo_global_finance.group_compliance_rule_approver"
            ),
            company_id=cls.company.id,
            company_ids=[cls.company.id],
        )
        cls.manager = new_test_user(
            cls.env,
            login="cn_jurisdiction_manager",
            groups=(
                "base.group_user,"
                "sudo_global_finance.group_compliance_manager"
            ),
            company_id=cls.company.id,
            company_ids=[cls.company.id],
        )
        cls.reader = new_test_user(
            cls.env,
            login="cn_jurisdiction_reader",
            groups=(
                "base.group_user,"
                "sudo_global_finance.group_compliance_user"
            ),
            company_id=cls.company.id,
            company_ids=[cls.company.id],
        )
        cls.profile = cls.env["sudo.compliance.profile"].with_company(
            cls.company
        ).create(
            {
                "company_id": cls.company.id,
                "country_id": cls.country.id,
                "country_pack_id": cls.country_pack.id,
            }
        )
        cls.source = cls._create_valid_source()

    @classmethod
    def _create_valid_source(cls):
        source = cls.env["sudo.compliance.authority.source"].with_user(
            cls.author
        ).create(
            {
                "name": "China jurisdiction governed test source",
                "country_id": cls.country.id,
                "authority": "Test China authority",
                "source_type": "tax_guide",
                "snapshot_kind": "official_web_capture",
                "official_url": "https://example.test/cn-jurisdiction",
                "official_version": "TEST-2026.1",
                "published_date": "2026-01-01",
                "next_review_date": "2027-12-31",
            }
        )
        attachment = cls.env["ir.attachment"].with_user(cls.author).create(
            {
                "name": "cn-jurisdiction-source.html",
                "raw": b"Governed China jurisdiction test source",
                "mimetype": "text/html",
                "res_model": source._name,
                "res_id": source.id,
            }
        )
        source.write({"snapshot_attachment_id": attachment.id})
        source.action_compute_hash()
        source.action_submit_review()
        source.with_user(cls.approver).action_approve()
        return cls.env["sudo.compliance.authority.source"].browse(source.id)

    def _code(self, prefix):
        return "%s-%s" % (prefix, uuid.uuid4().hex[:8].upper())

    def _create_jurisdiction(
        self,
        prefix="CN-TEST",
        level="national",
        parent=None,
        source=None,
        effective_from="2026-01-01",
        effective_to=False,
        activate=True,
    ):
        source = source or self.source
        jurisdiction = self.env[
            "sudo.cn.jurisdiction.version"
        ].with_user(self.author).create(
            {
                "name": "%s jurisdiction" % prefix,
                "code": self._code(prefix),
                "version": "TEST-2026.1",
                "level": level,
                "parent_id": parent.id if parent else False,
                "effective_from": effective_from,
                "effective_to": effective_to,
                "authority_source_ids": [Command.set(source.ids)],
                "scope_note": "Controlled runtime boundary for jurisdiction tests.",
            }
        )
        jurisdiction.action_submit_review()
        jurisdiction.with_user(self.approver).action_approve()
        if activate:
            jurisdiction.with_user(self.approver).action_activate()
        return self.env["sudo.cn.jurisdiction.version"].browse(
            jurisdiction.id
        )

    def _create_assignment(
        self,
        jurisdiction,
        profile=None,
        domain="vat",
        role="tax_registration",
        valid_from="2026-01-01",
        valid_to=False,
        verify=True,
        complete=True,
        manager=None,
    ):
        profile = profile or self.profile
        manager = manager or self.manager
        assignment = self.env["sudo.cn.profile.jurisdiction"].with_user(
            manager
        ).with_company(profile.company_id).create(
            {
                "profile_id": profile.id,
                "jurisdiction_id": jurisdiction.id,
                "applicability_domain": domain,
                "role": role,
                "valid_from": valid_from,
                "valid_to": valid_to,
                "source_type": (
                    "tax_registration_document" if complete else False
                ),
                "source_date": "2026-07-01" if complete else False,
                "source_reference": "TEST/JURISDICTION/001" if complete else False,
                "scope_note": (
                    "Controlled company applicability boundary."
                    if complete
                    else False
                ),
            }
        )
        if complete:
            attachment = self.env["ir.attachment"].with_user(manager).create(
                {
                    "name": "cn-jurisdiction-assignment.txt",
                    "raw": b"Controlled company jurisdiction evidence",
                    "mimetype": "text/plain",
                    "res_model": assignment._name,
                    "res_id": assignment.id,
                }
            )
            assignment.write(
                {"evidence_attachment_ids": [Command.set(attachment.ids)]}
            )
        if verify:
            assignment.action_verify()
        return self.env["sudo.cn.profile.jurisdiction"].browse(
            assignment.id
        )

    def _create_rule_version(
        self,
        prefix,
        jurisdictions=None,
        domain="vat",
        state="active",
    ):
        jurisdictions = jurisdictions or self.env[
            "sudo.cn.jurisdiction.version"
        ]
        code = self._code(prefix)
        rule = self.env["sudo.compliance.rule"].with_context(
            install_mode=True
        ).create(
            {
                "name": "%s rule" % prefix,
                "code": code,
                "country_id": self.country.id,
                "domain_key": "CN.TEST.JURISDICTION",
                "cn_rule_nature": "data_readiness",
                "description": "Runtime jurisdiction selection test only.",
            }
        )
        version = self.env["sudo.compliance.rule.version"].with_context(
            install_mode=True
        ).create(
            {
                "rule_id": rule.id,
                "version": "TEST-2026.1",
                "effective_from": "2026-01-01",
                "next_review_date": "2027-12-31",
                "evaluator_type": "manual",
                "risk_level": "medium",
                "stale_policy": "block_all",
                "authority_source_ids": [Command.set(self.source.ids)],
                "requires_human_review": True,
                "state": state,
                "author_id": self.author.id,
                "test_state": "passed",
                "professional_review_state": "approved",
                "cn_jurisdiction_ids": [Command.set(jurisdictions.ids)],
                "cn_jurisdiction_domain": domain,
            }
        )
        return version

    def _assessment(self, versions=None):
        values = {
            "profile_id": self.profile.id,
            "evaluation_date": "2026-07-15",
            "period_start": "2026-07-01",
            "period_end": "2026-07-31",
        }
        if versions is not None:
            values["rule_version_ids"] = [Command.set(versions.ids)]
        return self.env["sudo.compliance.assessment"].with_company(
            self.company
        ).create(values)

    def _complete_assessment_with_selected(self, assessment, versions):
        assessment._engine_write(
            {
                "rule_version_ids": [Command.set(versions.ids)],
                "state": "completed",
            }
        )
        assessment.invalidate_recordset()
        return assessment

    def test_jurisdiction_create_cannot_forge_governance_state(self):
        jurisdiction = self.env[
            "sudo.cn.jurisdiction.version"
        ].with_user(self.author).create(
            {
                "name": "Forged jurisdiction",
                "code": self._code("CN-FORGE"),
                "version": "1",
                "level": "national",
                "effective_from": "2026-01-01",
                "scope_note": "Test boundary.",
                "authority_source_ids": [Command.set(self.source.ids)],
                "state": "active",
                "reviewer_id": self.approver.id,
                "checksum": "0" * 64,
            }
        )
        self.assertEqual(jurisdiction.state, "draft")
        self.assertEqual(jurisdiction.author_id, self.author)
        self.assertFalse(jurisdiction.reviewer_id)
        self.assertFalse(jurisdiction.checksum)
        with self.assertRaises(AccessError):
            jurisdiction.write({"state": "active"})

    def test_jurisdiction_requires_independent_review_and_freezes_checksum(self):
        jurisdiction = self.env[
            "sudo.cn.jurisdiction.version"
        ].with_user(self.author_approver).create(
            {
                "name": "Independent review jurisdiction",
                "code": self._code("CN-INDEPENDENT"),
                "version": "1",
                "level": "national",
                "effective_from": "2026-01-01",
                "scope_note": "Controlled independent review boundary.",
                "authority_source_ids": [Command.set(self.source.ids)],
            }
        )
        jurisdiction.action_submit_review()
        with self.assertRaisesRegex(UserError, "不同用户"):
            jurisdiction.with_user(self.author_approver).action_approve()
        jurisdiction.with_user(self.approver).action_approve()
        approved_checksum = jurisdiction.checksum
        self.assertEqual(len(approved_checksum), 64)
        jurisdiction.with_user(self.approver).action_activate()
        self.assertEqual(jurisdiction.state, "active")
        self.assertEqual(jurisdiction.integrity_state, "verified")
        self.assertEqual(jurisdiction.checksum, approved_checksum)

    def test_invalid_official_source_blocks_jurisdiction(self):
        draft_source = self.env[
            "sudo.compliance.authority.source"
        ].with_user(self.author).create(
            {
                "name": "Draft source",
                "country_id": self.country.id,
                "authority": "Test authority",
                "source_type": "tax_guide",
                "official_url": "https://example.test/draft-jurisdiction",
                "next_review_date": "2027-12-31",
            }
        )
        jurisdiction = self.env[
            "sudo.cn.jurisdiction.version"
        ].with_user(self.author).create(
            {
                "name": "Invalid source jurisdiction",
                "code": self._code("CN-INVALID-SOURCE"),
                "version": "1",
                "level": "national",
                "effective_from": "2026-01-01",
                "scope_note": "Controlled test boundary.",
                "authority_source_ids": [Command.set(draft_source.ids)],
            }
        )
        with self.assertRaisesRegex(UserError, "官方来源"):
            jurisdiction.action_submit_review()

    def test_hierarchy_cycle_and_parent_period_are_guarded(self):
        parent = self._create_jurisdiction("CN-PARENT")
        child = self.env["sudo.cn.jurisdiction.version"].with_user(
            self.author
        ).create(
            {
                "name": "Child before parent",
                "code": self._code("CN-CHILD-EARLY"),
                "version": "1",
                "level": "province",
                "parent_id": parent.id,
                "effective_from": "2025-01-01",
                "scope_note": "Invalid period test.",
                "authority_source_ids": [Command.set(self.source.ids)],
            }
        )
        with self.assertRaisesRegex(UserError, "上级辖区"):
            child.action_submit_review()

        first = self.env["sudo.cn.jurisdiction.version"].with_user(
            self.author
        ).create(
            {
                "name": "Cycle first",
                "code": self._code("CN-CYCLE-A"),
                "version": "1",
                "level": "province",
                "effective_from": "2026-01-01",
            }
        )
        second = self.env["sudo.cn.jurisdiction.version"].with_user(
            self.author
        ).create(
            {
                "name": "Cycle second",
                "code": self._code("CN-CYCLE-B"),
                "version": "1",
                "level": "prefecture",
                "parent_id": first.id,
                "effective_from": "2026-01-01",
            }
        )
        with self.assertRaises(ValidationError):
            first.write({"parent_id": second.id})

    def test_active_jurisdiction_is_immutable_and_source_tamper_is_visible(self):
        jurisdiction = self._create_jurisdiction("CN-IMMUTABLE")
        with self.assertRaisesRegex(UserError, "只有草稿"):
            jurisdiction.with_user(self.author).write(
                {"scope_note": "Attempted mutation"}
            )
        self.source.snapshot_attachment_id.sudo().write(
            {"raw": b"tampered official source content"}
        )
        jurisdiction.invalidate_recordset()
        self.assertEqual(jurisdiction._current_integrity_state(), "source_invalid")

    def test_assignment_requires_complete_evidence(self):
        jurisdiction = self._create_jurisdiction("CN-ASSIGN-INCOMPLETE")
        assignment = self._create_assignment(
            jurisdiction,
            complete=False,
            verify=False,
        )
        with self.assertRaisesRegex(UserError, "来源"):
            assignment.action_verify()
        self.assertEqual(assignment.state, "draft")

    def test_assignment_verification_freezes_evidence_and_detects_tamper(self):
        jurisdiction = self._create_jurisdiction("CN-ASSIGN-VERIFY")
        assignment = self._create_assignment(jurisdiction)
        self.assertEqual(assignment.state, "verified")
        self.assertEqual(assignment.integrity_state, "verified")
        self.assertEqual(assignment.jurisdiction_checksum, jurisdiction.checksum)
        self.assertEqual(len(assignment.verification_checksum), 64)
        assignment.evidence_attachment_ids.sudo().write(
            {"raw": b"tampered company jurisdiction evidence"}
        )
        assignment.invalidate_recordset()
        self.assertEqual(
            assignment._current_integrity_state(), "checksum_mismatch"
        )

    def test_overlapping_verified_assignment_is_rejected(self):
        jurisdiction = self._create_jurisdiction("CN-ASSIGN-OVERLAP")
        self._create_assignment(
            jurisdiction,
            valid_from="2026-01-01",
            valid_to="2026-12-31",
        )
        second = self._create_assignment(
            jurisdiction,
            valid_from="2026-06-01",
            valid_to="2027-01-31",
            verify=False,
        )
        with self.assertRaisesRegex(UserError, "已有已核验"):
            second.action_verify()

    def test_assignment_record_rule_isolates_companies(self):
        jurisdiction = self._create_jurisdiction("CN-MULTI-COMPANY")
        own = self._create_assignment(jurisdiction)
        other_company = self.env["res.company"].create(
            {
                "name": "Other China Jurisdiction Company",
                "currency_id": self.currency.id,
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
                "country_pack_id": self.country_pack.id,
            }
        )
        multi_manager = new_test_user(
            self.env,
            login="cn_jurisdiction_multi_manager",
            groups=(
                "base.group_user,"
                "sudo_global_finance.group_compliance_manager"
            ),
            company_id=self.company.id,
            company_ids=[self.company.id, other_company.id],
        )
        other = self._create_assignment(
            jurisdiction,
            profile=other_profile,
            manager=multi_manager,
        )
        visible = self.env["sudo.cn.profile.jurisdiction"].with_user(
            self.reader
        ).search([("id", "in", [own.id, other.id])])
        self.assertEqual(visible, own)
        with self.assertRaises(AccessError):
            other.with_user(self.reader).check_access("read")

    def test_local_rule_scope_changes_checksum_and_publish_gate(self):
        jurisdiction = self._create_jurisdiction("CN-RULE-SCOPE")
        local = self._create_rule_version(
            "CN-LOCAL-CHECKSUM", jurisdiction, state="draft"
        )
        national = self._create_rule_version(
            "CN-NATIONAL-CHECKSUM", state="draft"
        )
        self.assertIn("cn_jurisdictions", local._checksum_payload())
        self.assertNotIn("cn_jurisdictions", national._checksum_payload())

        invalid_scope = self.env[
            "sudo.cn.jurisdiction.version"
        ].with_user(self.author).create(
            {
                "name": "Unapproved rule scope",
                "code": self._code("CN-UNAPPROVED-SCOPE"),
                "version": "1",
                "level": "national",
                "effective_from": "2026-01-01",
            }
        )
        invalid_version = self._create_rule_version(
            "CN-INVALID-RULE-SCOPE", invalid_scope, state="draft"
        )
        with self.assertRaisesRegex(UserError, "地方适用范围"):
            invalid_version._check_publish_gate()

    def test_descendant_assignment_selects_matching_rule_and_excludes_other_scope(self):
        national = self._create_jurisdiction("CN-ROOT")
        guangdong = self._create_jurisdiction(
            "CN-GD", level="province", parent=national
        )
        guangzhou = self._create_jurisdiction(
            "CN-GZ", level="prefecture", parent=guangdong
        )
        beijing = self._create_jurisdiction(
            "CN-BJ", level="province", parent=national
        )
        self._create_assignment(guangzhou)
        gd_rule = self._create_rule_version("CN-GD-RULE", guangdong)
        bj_rule = self._create_rule_version("CN-BJ-RULE", beijing)

        assessment = self._assessment()
        selected = self.env["sudo.compliance.engine"]._select_versions(
            assessment
        )
        self.assertIn(gd_rule, selected)
        self.assertNotIn(bj_rule, selected)
        self.assertEqual(assessment.cn_jurisdiction_coverage_state, "complete")
        self.assertEqual(assessment.cn_jurisdiction_selected_rule_count, 1)
        self.assertEqual(assessment.cn_jurisdiction_excluded_rule_count, 1)
        statuses = {
            item["rule_code"]: item["status"]
            for item in assessment.cn_jurisdiction_scope_snapshot_json[
                "scoped_rules"
            ]
        }
        self.assertEqual(statuses[gd_rule.rule_id.code], "selected")
        self.assertEqual(statuses[bj_rule.rule_id.code], "excluded")

    def test_missing_assignment_limits_assessment_while_national_rule_runs(self):
        jurisdiction = self._create_jurisdiction("CN-MISSING-ASSIGNMENT")
        local = self._create_rule_version("CN-LOCAL-MISSING", jurisdiction)
        national = self._create_rule_version("CN-NATIONAL-FALLBACK")
        assessment = self._assessment()

        selected = self.env["sudo.compliance.engine"]._select_versions(
            assessment
        )
        self.assertIn(national, selected)
        self.assertNotIn(local, selected)
        self.assertEqual(
            assessment.cn_jurisdiction_coverage_state, "incomplete"
        )
        self._complete_assessment_with_selected(assessment, selected)
        self.assertEqual(assessment.report_state, "limited")

    def test_tampered_assignment_blocks_local_rule_as_integrity_error(self):
        jurisdiction = self._create_jurisdiction("CN-TAMPERED-ASSIGNMENT")
        assignment = self._create_assignment(jurisdiction)
        assignment.evidence_attachment_ids.sudo().write(
            {"raw": b"tampered assignment evidence"}
        )
        local = self._create_rule_version("CN-LOCAL-TAMPER", jurisdiction)
        national = self._create_rule_version("CN-NATIONAL-TAMPER-FALLBACK")
        assessment = self._assessment()

        selected = self.env["sudo.compliance.engine"]._select_versions(
            assessment
        )
        self.assertIn(national, selected)
        self.assertNotIn(local, selected)
        self.assertEqual(
            assessment.cn_jurisdiction_coverage_state, "integrity_error"
        )
        self.assertEqual(assessment.cn_jurisdiction_blocked_rule_count, 1)

    def test_explicit_out_of_scope_rule_is_rejected(self):
        national = self._create_jurisdiction("CN-EXPLICIT-ROOT")
        guangdong = self._create_jurisdiction(
            "CN-EXPLICIT-GD", level="province", parent=national
        )
        beijing = self._create_jurisdiction(
            "CN-EXPLICIT-BJ", level="province", parent=national
        )
        self._create_assignment(guangdong)
        beijing_rule = self._create_rule_version(
            "CN-EXPLICIT-BJ-RULE", beijing
        )
        assessment = self._assessment(beijing_rule)
        with self.assertRaisesRegex(UserError, "不匹配"):
            self.env["sudo.compliance.engine"]._select_versions(assessment)

    def test_assessment_scope_fields_cannot_be_forged_and_snapshot_tamper_is_detected(self):
        national_rule = self._create_rule_version("CN-SNAPSHOT-NATIONAL")
        assessment = self.env["sudo.compliance.assessment"].with_company(
            self.company
        ).create(
            {
                "profile_id": self.profile.id,
                "evaluation_date": "2026-07-15",
                "cn_jurisdiction_coverage_state": "complete",
                "cn_jurisdiction_scope_snapshot_json": {"forged": True},
                "cn_jurisdiction_scope_checksum": "0" * 64,
            }
        )
        self.assertEqual(
            assessment.cn_jurisdiction_coverage_state, "not_assessed"
        )
        self.assertFalse(assessment.cn_jurisdiction_scope_snapshot_json)
        with self.assertRaises(AccessError):
            assessment.write({"cn_jurisdiction_coverage_state": "complete"})

        selected = self.env["sudo.compliance.engine"]._select_versions(
            assessment
        )
        self.assertIn(national_rule, selected)
        self.assertEqual(
            assessment.cn_jurisdiction_scope_integrity_state, "verified"
        )
        assessment._cn_jurisdiction_scope_write(
            {
                "cn_jurisdiction_scope_snapshot_json": {
                    "schema": "tampered",
                    "payload": json.dumps({"unexpected": True}),
                }
            }
        )
        assessment.invalidate_recordset()
        self.assertEqual(
            assessment.cn_jurisdiction_scope_integrity_state,
            "checksum_mismatch",
        )
