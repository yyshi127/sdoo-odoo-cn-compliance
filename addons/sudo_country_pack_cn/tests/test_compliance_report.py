from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestChinaFormalComplianceReport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(su=True)
        cls.country = cls.env.ref("base.cn")
        cls.currency = cls.env.ref("base.CNY")
        cls.country_pack = cls.env.ref(
            "sudo_country_pack_cn.compliance_country_pack_cn"
        )
        cls.company = cls.env["res.company"].create(
            {
                "name": "China Formal Report Test Company",
                "country_id": cls.country.id,
                "account_fiscal_country_id": cls.country.id,
                "currency_id": cls.currency.id,
            }
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
        cls.rule = cls.env["sudo.compliance.rule"].create(
            {
                "name": "正式报告测试规则",
                "code": "CN-REPORT-TEST",
                "country_id": cls.country.id,
                "domain_key": "CN.REPORT.TEST",
            }
        )
        cls.rule_version = cls.env["sudo.compliance.rule.version"].create(
            {
                "rule_id": cls.rule.id,
                "version": "TEST-1",
                "effective_from": "2026-01-01",
                "next_review_date": "2027-01-01",
                "evaluator_type": "manual",
                "requires_human_review": True,
            }
        )
        manager_group = cls.env.ref(
            "sudo_global_finance.group_compliance_manager"
        )
        user_group = cls.env.ref(
            "sudo_global_finance.group_compliance_user"
        )
        approver_group = cls.env.ref(
            "sudo_country_pack_cn.group_cn_report_approver"
        )
        cls.manager = cls._user(
            "cn_report_manager",
            "China Report Manager",
            manager_group,
        )
        cls.approver = cls._user(
            "cn_report_approver",
            "China Report Approver",
            approver_group,
        )
        cls.reader = cls._user(
            "cn_report_reader",
            "China Report Reader",
            user_group,
        )
        cls.same_person = cls._user(
            "cn_report_same_person",
            "China Report Same Person",
            manager_group | approver_group,
        )

    @classmethod
    def _user(cls, login, name, groups, company=None):
        company = company or cls.company
        return cls.env["res.users"].create(
            {
                "name": name,
                "login": login,
                "company_id": company.id,
                "company_ids": [Command.set(company.ids)],
                "group_ids": [Command.set(groups.ids)],
            }
        )

    def setUp(self):
        super().setUp()
        self.assessment, self.finding = self._assessment("base")

    def _assessment(
        self,
        suffix,
        *,
        result="fail",
        source_warning=False,
        professional_warning=False,
        review=True,
    ):
        assessment = self.env["sudo.compliance.assessment"].with_company(
            self.company
        ).create(
            {
                "profile_id": self.profile.id,
                "evaluation_date": "2026-07-01",
                "period_start": "2026-06-01",
                "period_end": "2026-06-30",
                "rule_version_ids": [Command.set(self.rule_version.ids)],
                "note": "正式报告测试评估说明。",
            }
        )
        finding = self.env["sudo.compliance.finding"]._create_engine(
            {
                "assessment_id": assessment.id,
                "rule_id": self.rule.id,
                "rule_version_id": self.rule_version.id,
                "result": result,
                "risk_level": "high" if result == "fail" else "medium",
                "title": f"正式报告测试结论 {suffix}",
                "summary": "根据受控事实快照形成的测试专业结论。",
                "legal_basis": "测试规则依据快照。",
                "recommendation": "核对事实并完成受控整改复核。",
                "evidence_required": "保存复核工作底稿和整改证据。",
                "requires_human_review": True,
                "source_warning": source_warning,
                "professional_warning": professional_warning,
                "professional_snapshot_json": {
                    "state": "approved" if not professional_warning else "pending"
                },
                "source_snapshot_json": [
                    {
                        "name": "测试官方来源快照",
                        "status": "valid" if not source_warning else "pending_review",
                    }
                ],
                "result_details_json": {"affected_count": 1},
                "checksum": (suffix.encode().hex() + "a" * 64)[:64],
            }
        )
        assessment._engine_write(
            {
                "state": "completed",
                "started_at": "2026-07-01 09:00:00",
                "completed_at": "2026-07-01 09:01:00",
            }
        )
        if review:
            finding.with_user(self.manager).write(
                {"review_notes": "已核对规则事实与报告边界，需要进入整改流程。"}
            )
            finding.with_user(self.manager).action_require_correction()
        return assessment, finding

    def _report(self, assessment=None, preparer=None, reviewer=None, **values):
        assessment = assessment or self.assessment
        preparer = preparer or self.manager
        reviewer = reviewer or self.approver
        defaults = {
            "title": "中国财税合规管理正式报告",
            "assessment_id": assessment.id,
            "executive_summary": (
                "本报告汇总受控规则扫描、人工复核、整改状态和税务影响，"
                "供管理层在限定范围内决策。"
            ),
            "scope_statement": (
                "报告覆盖测试公司二零二六年六月期间、已冻结规则版本、"
                "Odoo 事实快照及报告中列示的证据。"
            ),
            "limitation_statement": (
                "测试环境中的中国候选纳税义务仍需逐项确认适用性和官方来源；"
                "本报告仅按当前受控配置披露限制，不替代真实申报判断。"
            ),
            "management_response": (
                "管理层已指定责任人核对高风险事项，并按整改任务期限补充证据后复扫。"
            ),
            "reviewer_id": reviewer.id,
        }
        defaults.update(values)
        return self.env["sudo.cn.compliance.report"].with_user(
            preparer
        ).with_company(self.company).create(defaults)

    def _issue(self, report, approver=None, pdf=None):
        approver = approver or self.approver
        pdf = pdf or b"%PDF-1.4\nSdoo governed report\n%%EOF"
        report.with_user(approver).write(
            {
                "review_notes": (
                    "已独立核验报告范围、源快照、复核状态、限制和结论边界，同意签发。"
                )
            }
        )
        with patch.object(
            type(report),
            "_render_issued_pdf",
            return_value=pdf,
        ):
            report.with_user(approver).action_issue()
        report.invalidate_recordset()
        return report

    def test_submission_freezes_explainable_snapshot_and_audit(self):
        report = self._report()

        report.with_user(self.manager).action_submit()
        report.invalidate_recordset()

        self.assertEqual(report.state, "submitted")
        self.assertEqual(report.conclusion_state, "limited_action_required")
        self.assertEqual(report.snapshot_json["schema"], "sdoo.cn.compliance-report.v1")
        self.assertEqual(report.snapshot_json["assessment"]["id"], self.assessment.id)
        self.assertEqual(report.snapshot_json["findings"][0]["checksum"], self.finding.checksum)
        self.assertEqual(
            report.snapshot_json["obligation_readiness"]["state"],
            "attention",
        )
        self.assertEqual(
            report.snapshot_json["obligation_readiness"]["candidate_count"],
            len(self.profile.obligation_ids),
        )
        self.assertEqual(report.finding_count, 1)
        self.assertEqual(report.high_count, 1)
        self.assertEqual(len(report.snapshot_checksum), 64)

    def test_pending_obligations_require_report_limitation(self):
        report = self._report(limitation_statement="")

        with self.assertRaisesRegex(
            UserError,
            "Tax obligation applicability is not fully confirmed",
        ):
            report.with_user(self.manager).action_submit()

        report.limitation_statement = (
            "中国候选纳税义务仍处于测试确认阶段，报告结论仅用于受控演示环境。"
        )
        report.with_user(self.manager).action_submit()
        report.invalidate_recordset()

        self.assertTrue(report.has_material_limitations)
        self.assertEqual(
            report.snapshot_json["obligation_readiness"]["pending_review_count"],
            len(self.profile.obligation_ids),
        )
        self.assertIn(
            "obligation_readiness",
            report.snapshot_json,
        )

    def test_report_center_exposes_stage_next_action_and_navigation(self):
        report = self._report()

        self.assertEqual(report.cn_report_center_stage, "draft")
        self.assertEqual(report.cn_report_center_integrity_state, "unsealed")
        self.assertTrue(report.cn_report_center_next_action)

        report.with_user(self.manager).action_submit()
        report.invalidate_recordset()

        self.assertEqual(report.cn_report_center_stage, "approval")
        self.assertEqual(report.cn_report_center_integrity_state, "verified")
        self.assertTrue(report.cn_report_center_next_action)
        self.assertEqual(
            report.action_cn_open_report_findings()["res_model"],
            "sudo.compliance.finding",
        )
        self.assertIn(
            ("assessment_id", "=", self.assessment.id),
            report.action_cn_open_report_findings()["domain"],
        )
        self.assertEqual(
            report.action_cn_open_report_tasks()["res_model"],
            "sudo.compliance.task",
        )
        self.assertIn(
            ("assessment_id", "=", self.assessment.id),
            report.action_cn_open_report_tasks()["domain"],
        )
        self.assertEqual(report.cn_report_traceability_state, "blocked")
        self.assertGreater(report.cn_report_traceability_gap_count, 0)
        self.assertTrue(report.cn_report_traceability_next_action)
        self.assertEqual(
            report.action_cn_open_report_evidence()["res_model"],
            "sudo.compliance.evidence",
        )

        self._issue(report)
        report.invalidate_recordset()

        self.assertEqual(report.cn_report_center_stage, "issued")
        self.assertEqual(report.cn_report_center_integrity_state, "verified")

    def test_country_pack_advertises_report_center_visibility(self):
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_report_center_visibility"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_report_obligation_readiness"
            ]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_traceability_matrix_visibility"
            ]
        )
        self.assertEqual(report.snapshot_integrity_state, "verified")
        with self.assertRaisesRegex(UserError, "只有编制中的报告"):
            report.with_user(self.manager).write({"title": "不能改写"})
        event = self.env["sudo.compliance.audit.event"].search(
            [
                ("event_key", "=", "cn_compliance_report.submitted"),
                ("record_id", "=", report.id),
            ],
            limit=1,
        )
        self.assertEqual(event.details_json["snapshot_checksum"], report.snapshot_checksum)

    def test_unreviewed_or_unsigned_findings_block_formal_submission(self):
        unreviewed, _finding = self._assessment("unreviewed", review=False)
        report = self._report(unreviewed)
        with self.assertRaisesRegex(UserError, "未完成人工复核"):
            report.with_user(self.manager).action_submit()

        unsigned, _finding = self._assessment(
            "unsigned",
            professional_warning=True,
        )
        report = self._report(unsigned)
        with self.assertRaisesRegex(UserError, "真人专业签核"):
            report.with_user(self.manager).action_submit()

    def test_source_change_after_submission_requires_return_and_resubmit(self):
        report = self._report()
        report.with_user(self.manager).action_submit()
        self.assessment.note = "报告提交后发生变化的评估说明。"

        with self.assertRaisesRegex(UserError, "源资料在提交后发生变化"):
            report.with_user(self.approver).write(
                {"review_notes": "已复核但发现源资料发生变化，应退回重新冻结快照。"}
            )
            report.with_user(self.approver).action_issue()

        report.with_user(self.approver).action_return_to_draft()
        report.invalidate_recordset()
        self.assertEqual(report.state, "draft")
        self.assertFalse(report.snapshot_checksum)
        self.assertFalse(report.conclusion_state)

    def test_independent_approver_issues_immutable_pdf(self):
        report = self._report()
        report.with_user(self.manager).action_submit()

        self._issue(report)

        self.assertEqual(report.state, "issued")
        self.assertEqual(report.issued_by_id, self.approver)
        self.assertEqual(len(report.approval_checksum), 64)
        self.assertEqual(len(report.issued_pdf_sha256), 64)
        self.assertEqual(report.approval_integrity_state, "verified")
        self.assertEqual(report.pdf_integrity_state, "verified")
        download = report.with_user(self.reader).action_download_issued_pdf()
        self.assertEqual(download["type"], "ir.actions.act_url")
        with self.assertRaisesRegex(UserError, "封存 PDF"):
            report.action_preview()
        with self.assertRaisesRegex(AccessError, "受控字段"):
            report.with_user(self.manager).write({"issued_at": fields.Datetime.now()})
        with self.assertRaisesRegex(UserError, "不允许删除"):
            report.with_user(self.manager).unlink()

    def test_pdf_tampering_is_detected_and_download_blocked(self):
        report = self._report()
        report.with_user(self.manager).action_submit()
        self._issue(report)
        attachment = self.env["ir.attachment"].sudo().search(
            [
                ("res_model", "=", report._name),
                ("res_id", "=", report.id),
                ("res_field", "=", "issued_pdf"),
            ],
            limit=1,
        )
        self.assertTrue(attachment)

        attachment.raw = b"tampered formal report"
        report.invalidate_recordset()

        self.assertEqual(report.pdf_integrity_state, "checksum_mismatch")
        with self.assertRaisesRegex(UserError, "完整性异常"):
            report.action_download_issued_pdf()

    def test_approval_tampering_is_detected_and_download_blocked(self):
        report = self._report()
        report.with_user(self.manager).action_submit()
        self._issue(report)

        self.env.cr.execute(
            "UPDATE sudo_cn_compliance_report SET review_notes = %s WHERE id = %s",
            ("数据库层篡改后的批准意见。", report.id),
        )
        report.invalidate_recordset()

        self.assertEqual(
            report.approval_integrity_state,
            "checksum_mismatch",
        )
        with self.assertRaisesRegex(UserError, "批准记录.*完整性异常"):
            report.action_download_issued_pdf()

    def test_open_verification_task_prevents_clear_conclusion(self):
        assessment, finding = self._assessment(
            "verification-pass",
            result="pass",
            review=False,
        )
        finding.with_user(self.manager).write(
            {"review_notes": "已确认本次复扫结果通过，但原整改任务仍待授权人员确认关闭。"}
        )
        finding.with_user(self.manager).action_confirm_review()
        task = self.env["sudo.compliance.task"].create_from_finding(self.finding)
        task._transition_write(
            {
                "state": "pending_review",
                "verification_state": "pending_rescan",
                "verification_assessment_id": assessment.id,
            }
        )
        report = self._report(assessment)

        report.with_user(self.manager).action_submit()
        report.invalidate_recordset()

        self.assertEqual(report.open_task_count, 1)
        self.assertEqual(report.conclusion_state, "limited_action_required")

    def test_same_person_approval_requires_recorded_exception(self):
        report = self._report(
            preparer=self.same_person,
            reviewer=self.same_person,
        )
        with self.assertRaisesRegex(UserError, "职责未分离"):
            report.with_user(self.same_person).action_submit()

        report.independence_exception_reason = (
            "测试环境只有一名同时具备编制和批准权限的人员，已由管理层记录受控例外。"
        )
        report.with_user(self.same_person).action_submit()
        self._issue(report, approver=self.same_person)

        self.assertEqual(report.state, "issued")
        event = self.env["sudo.compliance.audit.event"].search(
            [
                ("event_key", "=", "cn_compliance_report.issued"),
                ("record_id", "=", report.id),
            ],
            limit=1,
        )
        self.assertFalse(event.details_json["independent_approval"])

    def test_new_issue_supersedes_previous_report_without_rewriting_pdf(self):
        first = self._report()
        first.with_user(self.manager).action_submit()
        self._issue(first, pdf=b"%PDF-1.4\nfirst\n%%EOF")
        first_pdf_checksum = first.issued_pdf_sha256

        second = self._report(title="中国财税合规管理正式报告第二版")
        self.assertEqual(second.supersedes_id, first)
        second.with_user(self.manager).action_submit()
        self._issue(second, pdf=b"%PDF-1.4\nsecond\n%%EOF")
        first.invalidate_recordset()

        self.assertEqual(first.state, "superseded")
        self.assertEqual(first.issued_pdf_sha256, first_pdf_checksum)
        self.assertEqual(second.state, "issued")
        self.assertEqual(second.revision, 2)

    def test_withdrawal_preserves_artifact_and_audit_history(self):
        report = self._report()
        report.with_user(self.manager).action_submit()
        self._issue(report)
        pdf_checksum = report.issued_pdf_sha256
        report.with_user(self.manager).withdrawal_reason = (
            "签发后发现报告使用范围发生变化，管理层决定撤回并重新执行扫描。"
        )

        report.with_user(self.manager).action_withdraw()
        report.invalidate_recordset()

        self.assertEqual(report.state, "withdrawn")
        self.assertEqual(report.issued_pdf_sha256, pdf_checksum)
        self.assertEqual(report.pdf_integrity_state, "verified")
        event = self.env["sudo.compliance.audit.event"].search(
            [
                ("event_key", "=", "cn_compliance_report.withdrawn"),
                ("record_id", "=", report.id),
            ],
            limit=1,
        )
        self.assertEqual(event.details_json["pdf_sha256"], pdf_checksum)

    def test_read_only_user_cannot_prepare_or_mutate_report(self):
        with self.assertRaisesRegex(AccessError, "只有合规管理员"):
            self._report(preparer=self.reader)
        report = self._report()
        with self.assertRaises(AccessError):
            report.with_user(self.reader).write({"title": "无权修改"})

    def test_report_is_company_isolated_and_reviewer_must_have_company(self):
        other_company = self.env["res.company"].create(
            {
                "name": "China Formal Report Other Company",
                "country_id": self.country.id,
                "account_fiscal_country_id": self.country.id,
                "currency_id": self.currency.id,
            }
        )
        manager_group = self.env.ref(
            "sudo_global_finance.group_compliance_manager"
        )
        approver_group = self.env.ref(
            "sudo_country_pack_cn.group_cn_report_approver"
        )
        other_manager = self._user(
            "cn_report_other_manager",
            "China Report Other Manager",
            manager_group,
            company=other_company,
        )
        other_approver = self._user(
            "cn_report_other_approver",
            "China Report Other Approver",
            approver_group,
            company=other_company,
        )
        report = self._report()
        report_model = self.env["sudo.cn.compliance.report"].with_user(
            other_manager
        ).with_company(other_company)

        self.assertFalse(report_model.search([("id", "=", report.id)]))
        with self.assertRaises(AccessError):
            report.with_user(other_manager).with_company(other_company).read(
                ["name"]
            )
        with self.assertRaises(ValidationError):
            self._report(reviewer=other_approver)

    def test_only_designated_approver_can_return_or_issue(self):
        approver_group = self.env.ref(
            "sudo_country_pack_cn.group_cn_report_approver"
        )
        alternate_approver = self._user(
            "cn_report_alternate_approver",
            "China Report Alternate Approver",
            approver_group,
        )
        report = self._report()
        report.with_user(self.manager).action_submit()

        with self.assertRaises(AccessError):
            report.with_user(alternate_approver).write(
                {
                    "review_notes": (
                        "This alternate approver was not designated for the "
                        "controlled report approval."
                    )
                }
            )
        with self.assertRaises(AccessError):
            report.with_user(alternate_approver).action_return_to_draft()
        with self.assertRaises(AccessError):
            report.with_user(alternate_approver).action_issue()

    def test_report_html_preserves_boundary_and_non_net_tax_impact(self):
        report = self._report()
        report.with_user(self.manager).action_submit()
        action = self.env.ref(
            "sudo_country_pack_cn.action_report_cn_formal_compliance"
        )

        html, _report_type = action._render_qweb_html(
            action.report_name,
            report.ids,
        )

        self.assertFalse(action.binding_model_id)
        self.assertIn("不是纳税申报表".encode(), html)
        self.assertIn("不计算净额".encode(), html)
        self.assertIn("AI 分析仅为辅助材料".encode(), html)
        self.assertIn("预览稿，尚未签发".encode(), html)
        self.assertIn(report.snapshot_checksum.encode(), html)
