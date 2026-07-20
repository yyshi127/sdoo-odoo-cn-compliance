from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestChinaFilingCenter(TransactionCase):
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
                "name": "China Filing Center Test Company",
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

    def test_country_pack_advertises_filing_center(self):
        self.assertTrue(
            self.country_pack.capability_json["features"]["china_filing_center"]
        )
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_archive_evidence_badge_clarity"
            ]
        )

    def test_workbench_opens_profile_scoped_filing_center(self):
        action = self.profile.action_cn_open_workbench_filing_center()

        self.assertEqual(action["res_model"], "sudo.compliance.filing")
        self.assertIn(("profile_id", "=", self.profile.id), action["domain"])
        self.assertIn(
            ("cn_vat_reconciliation_run_id", "!=", False),
            action["domain"],
        )
        self.assertIn(
            ("cn_cit_reconciliation_run_id", "!=", False),
            action["domain"],
        )
        self.assertIn(
            ("cn_iit_reconciliation_run_id", "!=", False),
            action["domain"],
        )
        self.assertEqual(action["context"]["search_default_cn_controlled"], 1)

    def test_filing_center_exposes_blocker_summary(self):
        filing = self.env["sudo.compliance.filing"].with_company(self.company).new(
            {
                "filing_name": "Filing center blocker summary test",
                "company_id": self.company.id,
                "profile_id": self.profile.id,
                "period_start": "2026-06-01",
                "period_end": "2026-06-30",
                "state": "draft",
                "payment_state": "not_paid",
                "cn_submission_integrity_state": "unsealed",
                "cn_payment_integrity_state": "unsealed",
            }
        )
        filing._compute_cn_filing_center_display()

        self.assertEqual(filing.cn_filing_center_archive_state, "attention")
        self.assertIn("待处理：", filing.cn_filing_center_blocker_summary)
        self.assertIn("申报回执尚未封存", filing.cn_filing_center_blocker_summary)
        self.assertIn("申报尚未提交或确认受理", filing.cn_filing_center_blocker_summary)
        self.assertIn("缴退税证明不完整", filing.cn_filing_center_blocker_summary)
        self.assertIn("未关联正式证据", filing.cn_filing_center_blocker_summary)

    def test_filing_center_blocks_integrity_failures(self):
        filing = self.env["sudo.compliance.filing"].with_company(self.company).new(
            {
                "filing_name": "Filing center blocked test",
                "company_id": self.company.id,
                "profile_id": self.profile.id,
                "period_start": "2026-06-01",
                "period_end": "2026-06-30",
                "state": "accepted",
                "payment_state": "paid",
                "cn_submission_integrity_state": "changed",
                "cn_payment_integrity_state": "verified",
            }
        )
        filing._compute_cn_filing_center_display()

        self.assertEqual(filing.cn_filing_center_archive_state, "blocked")
        self.assertIn("申报封存完整性异常", filing.cn_filing_center_blocker_summary)

    def test_filing_center_marks_traceable_archive_ready(self):
        filing = self.env["sudo.compliance.filing"].with_company(self.company).new(
            {
                "filing_name": "Filing center ready test",
                "company_id": self.company.id,
                "profile_id": self.profile.id,
                "period_start": "2026-06-01",
                "period_end": "2026-06-30",
                "state": "accepted",
                "payment_state": "paid",
                "cn_submission_integrity_state": "verified",
                "cn_payment_integrity_state": "verified",
            }
        )
        filing.cn_filing_center_evidence_state = "verified"

        self.assertEqual(filing._cn_filing_center_archive_state(), "ready")

    def test_filing_center_archive_state_is_searchable(self):
        domain = self.env[
            "sudo.compliance.filing"
        ]._search_cn_filing_center_archive_state("=", "ready")

        self.assertEqual(domain[0][0], "id")
        self.assertEqual(domain[0][1], "in")

    def test_filing_center_search_view_exposes_archive_readiness_filters(self):
        view = self.env.ref(
            "sudo_country_pack_cn.view_cn_filing_center_search"
        )
        arch = view.arch_db

        self.assertIn("cn_archive_ready", arch)
        self.assertIn("cn_archive_attention", arch)
        self.assertIn("cn_archive_blocked", arch)
        self.assertIn("cn_filing_center_archive_state", arch)
