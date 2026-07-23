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
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_data_readiness_badge_clarity"
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
        self.assertIn("Blocked by:", dataset.cn_data_readiness_blocker_summary)
        self.assertIn("dataset not sealed", dataset.cn_data_readiness_blocker_summary)
        self.assertIn(
            "integrity not verified",
            dataset.cn_data_readiness_blocker_summary,
        )
        self.assertIn(
            "authenticity not verified",
            dataset.cn_data_readiness_blocker_summary,
        )
        self.assertIn("no normalized records", dataset.cn_data_readiness_blocker_summary)

    def test_dataset_readiness_labels_translate_in_chinese_context(self):
        dataset = self.env["sudo.cn.external.dataset"].create(
            {
                "profile_id": self.profile.id,
                "dataset_type": "vat_filing",
                "period_start": "2026-06-01",
                "period_end": "2026-06-30",
                "coverage_scope": "partial",
                "declared_record_count": 0,
                "currency_id": self.currency.id,
            }
        ).with_context(lang="zh_CN")

        self.assertEqual(
            dataset.cn_data_readiness_period_label,
            "2026-06-01 至 2026-06-30",
        )
        summary = dataset.cn_data_readiness_blocker_summary
        for expected in (
            "受阻原因：",
            "数据集未封存",
            "完整性尚未核验",
            "真实性尚未验证",
            "独立复核待完成",
            "无规范化记录",
        ):
            self.assertIn(expected, summary)
        for forbidden in (
            "Blocked by:",
            "dataset not sealed",
            "integrity not verified",
            "authenticity not verified",
            "independent review pending",
            "no normalized records",
        ):
            self.assertNotIn(forbidden, summary)
        self.assertEqual(
            dataset.env._("review control exception"),
            "复核控制存在例外",
        )

        field_labels = dataset.fields_get(
            ["cn_data_readiness_blocker_summary"]
        )
        self.assertEqual(
            field_labels["cn_data_readiness_blocker_summary"]["string"],
            "数据准备阻断",
        )
