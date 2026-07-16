from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestChinaDataReadinessCenter(TransactionCase):
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
                "name": "China Data Readiness Test Company",
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

    def test_country_pack_advertises_data_readiness_center(self):
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_data_readiness_center"
            ]
        )

    def test_workbench_opens_profile_scoped_data_readiness_center(self):
        action = self.profile.action_cn_open_workbench_data_readiness()

        self.assertEqual(action["res_model"], "sudo.cn.external.dataset")
        self.assertIn(("profile_id", "=", self.profile.id), action["domain"])
        self.assertEqual(action["context"]["default_profile_id"], self.profile.id)
        self.assertEqual(
            action["context"]["search_default_cn_profile_datasets"],
            1,
        )
        self.assertEqual(
            action["context"]["search_default_group_dataset_type"],
            1,
        )

    def test_dataset_exposes_readiness_next_action(self):
        dataset = self.env["sudo.cn.external.dataset"].create(
            {
                "profile_id": self.profile.id,
                "dataset_type": "vat_filing",
                "period_start": "2026-01-01",
                "period_end": "2026-01-31",
                "coverage_scope": "partial",
                "declared_record_count": 0,
                "currency_id": self.currency.id,
            }
        )

        self.assertEqual(dataset.cn_data_readiness_stage, "draft")
        self.assertIn("封存", dataset.cn_data_readiness_next_action)
        self.assertEqual(dataset.cn_data_readiness_record_count, 0)
        self.assertIn("2026-01-01", dataset.cn_data_readiness_period_label)
