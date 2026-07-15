from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


PACKET_XMLIDS = (
    "review_packet_cn_base_reg_001_draft",
    "review_packet_cn_acc_period_001_draft",
    "review_packet_cn_vat_inv_ready_001_draft",
    "review_packet_cn_acc_evidence_001_draft",
    "review_packet_cn_profile_tax_001_draft",
    "review_packet_cn_einvoice_reconciliation_ready_001_draft",
    "review_packet_cn_vat_reconciliation_ready_001_draft",
)


@tagged("post_install", "-at_install")
class TestChinaRuleReviewPacket(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.packets = cls.env["sudo.cn.rule.review.packet"].browse(
            [
                cls.env.ref(f"sudo_country_pack_cn.{xmlid}").id
                for xmlid in PACKET_XMLIDS
            ]
        )
        cls.author = new_test_user(
            cls.env,
            login="cn_review_packet_author",
            groups=(
                "base.group_user,"
                "sudo_global_finance.group_compliance_rule_author"
            ),
        )
        cls.compliance_user = new_test_user(
            cls.env,
            login="cn_review_packet_reader",
            groups=(
                "base.group_user,"
                "sudo_global_finance.group_compliance_user"
            ),
        )
        cls.professional = new_test_user(
            cls.env,
            login="cn_review_packet_professional",
            groups=(
                "base.group_user,"
                "sudo_global_finance.group_compliance_professional_reviewer"
            ),
        )

    def test_packaged_candidates_cover_every_linked_source(self):
        self.assertEqual(len(self.packets), 7)
        self.assertEqual(len(self.packets.mapped("citation_ids")), 14)
        self.assertEqual(set(self.packets.mapped("readiness_state")), {"ready"})
        for packet in self.packets:
            self.assertEqual(
                set(packet.citation_ids.mapped("source_id").ids),
                set(packet.rule_version_id.authority_source_ids.ids),
            )
            self.assertRegex(packet.candidate_checksum, r"^[0-9a-f]{64}$")
            self.assertNotIn(
                "direct_requirement",
                packet.citation_ids.mapped("citation_type"),
            )

    def test_review_packet_is_bound_into_rule_and_professional_payloads(self):
        version = self.packets[0].rule_version_id
        business_payload = version._checksum_payload()
        professional_payload = version._professional_checksum_payload()

        self.assertEqual(
            business_payload["cn_review_packet"],
            self.packets[0].governance_payload(),
        )
        self.assertEqual(
            professional_payload["cn_review_packet"],
            self.packets[0].governance_payload(),
        )

    def test_author_edit_changes_checksum_and_creates_audit_event(self):
        packet = self.packets[0]
        original_checksum = packet.candidate_checksum
        packet.with_user(self.author).write(
            {
                "reviewer_questions": (
                    packet.reviewer_questions + "\n补充测试审阅问题。"
                )
            }
        )

        self.assertNotEqual(packet.candidate_checksum, original_checksum)
        self.assertIn(
            self.author,
            packet.rule_version_id.payload_preparer_ids,
        )
        self.assertEqual(
            self.env["sudo.compliance.audit.event"].search_count(
                [
                    ("event_key", "=", "cn_rule_review_packet.updated"),
                    ("model_name", "=", packet._name),
                    ("record_id", "=", packet.id),
                ]
            ),
            1,
        )

    def test_compliance_reader_cannot_change_candidate(self):
        with self.assertRaises(AccessError):
            self.packets[0].with_user(self.compliance_user).write(
                {"reviewer_questions": "不得写入"}
            )

    def test_citation_cannot_use_unlinked_source(self):
        packet = self.packets[0]
        unrelated_source = self.env.ref(
            "sudo_country_pack_cn.source_cn_accounting_law_2024_candidate"
        )
        with self.assertRaisesRegex(ValidationError, "已经关联"):
            self.env["sudo.cn.rule.review.citation"].with_user(
                self.author
            ).create(
                {
                    "packet_id": packet.id,
                    "source_id": unrelated_source.id,
                    "citation_type": "supporting_context",
                    "locator": "测试条款",
                    "claim_summary": "不得保存的测试引用。",
                    "applicability_note": "来源未关联。",
                }
            )

    def test_professional_signoff_is_blocked_before_source_approval(self):
        version = self.packets[0].rule_version_id.with_user(self.professional)
        with self.assertRaisesRegex(UserError, "尚不能专业签核"):
            version.action_professional_signoff()

    def test_china_publish_gate_requires_review_packet(self):
        rule = self.env["sudo.compliance.rule"].with_user(self.author).create(
            {
                "name": "缺少专业复核包的中国测试规则",
                "code": "CN-TEST-REVIEW-PACKET-MISSING",
                "country_id": self.env.ref("base.cn").id,
                "domain_key": "CN.TEST",
                "cn_rule_nature": "data_readiness",
            }
        )
        version = self.env["sudo.compliance.rule.version"].with_user(
            self.author
        ).create(
            {
                "rule_id": rule.id,
                "version": "DRAFT-TEST",
                "effective_from": "2026-01-01",
                "next_review_date": "2026-12-31",
                "evaluator_type": "manual",
                "requires_human_review": True,
            }
        )

        with self.assertRaisesRegex(UserError, "必须完善专业复核包"):
            version._check_publish_gate()

    def test_review_packet_actions_open_and_print_native_records(self):
        version = self.packets[0].rule_version_id
        report = self.env.ref(
            "sudo_country_pack_cn.action_report_cn_rule_review_packet"
        )
        open_action = version.action_open_cn_review_packet()
        print_action = version.with_context(
            discard_logo_check=True
        ).action_print_cn_review_packet()

        self.assertFalse(report.binding_model_id)
        self.assertEqual(open_action["res_model"], self.packets._name)
        self.assertEqual(open_action["res_id"], self.packets[0].id)
        self.assertEqual(print_action["type"], "ir.actions.report")
        self.assertEqual(
            print_action["report_name"],
            "sudo_country_pack_cn.report_cn_rule_review_packet",
        )

    def test_review_packet_report_renders_candidate_boundary(self):
        report = self.env.ref(
            "sudo_country_pack_cn.action_report_cn_rule_review_packet"
        )
        html, _report_type = report._render_qweb_html(
            report.report_name,
            self.packets[0].ids,
        )

        self.assertIn("候选草案".encode(), html)
        self.assertIn("数据准备度".encode(), html)
        self.assertIn(self.packets[0].candidate_checksum.encode(), html)
