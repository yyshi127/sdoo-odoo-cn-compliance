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

        self.assertIn("Blocked by:", filing.cn_filing_center_blocker_summary)
        self.assertIn(
            "submission archive not sealed",
            filing.cn_filing_center_blocker_summary,
        )
        self.assertIn("filing not submitted", filing.cn_filing_center_blocker_summary)
        self.assertIn("payment proof incomplete", filing.cn_filing_center_blocker_summary)
        self.assertIn("no formal evidence linked", filing.cn_filing_center_blocker_summary)
