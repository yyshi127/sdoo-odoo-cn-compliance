from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestChinaAssessmentDataBasis(TransactionCase):
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
                "name": "China Assessment Data Basis Test Company",
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

    def _assessment(self):
        return self.env["sudo.compliance.assessment"].with_company(
            self.company
        ).create(
            {
                "profile_id": self.profile.id,
                "evaluation_date": "2026-07-01",
                "period_start": "2026-06-01",
                "period_end": "2026-06-30",
            }
        )

    def test_country_pack_advertises_assessment_data_basis(self):
        self.assertTrue(
            self.country_pack.capability_json["features"][
                "china_assessment_data_basis"
            ]
        )

    def test_assessment_without_datasets_shows_missing_data_basis(self):
        assessment = self._assessment()
        assessment.invalidate_recordset()

        self.assertEqual(assessment.cn_data_basis_state, "missing")
        self.assertEqual(assessment.cn_data_basis_dataset_count, 0)
        self.assertIn("电子发票", assessment.cn_data_basis_next_action)

    def test_assessment_opens_period_scoped_data_basis(self):
        assessment = self._assessment()
        action = assessment.action_cn_open_assessment_data_basis()

        self.assertEqual(action["res_model"], "sudo.cn.external.dataset")
        self.assertIn(("profile_id", "=", self.profile.id), action["domain"])
        self.assertIn(("period_end", ">=", assessment.period_start), action["domain"])
        self.assertIn(("period_start", "<=", assessment.period_end), action["domain"])
        self.assertEqual(
            action["context"]["search_default_group_dataset_type"],
            1,
        )

    def test_draft_dataset_makes_data_basis_warning(self):
        self.env["sudo.cn.external.dataset"].create(
            {
                "profile_id": self.profile.id,
                "dataset_type": "electronic_invoice",
                "period_start": "2026-06-01",
                "period_end": "2026-06-30",
                "coverage_scope": "partial",
                "declared_record_count": 1,
                "currency_id": self.currency.id,
            }
        )
        assessment = self._assessment()
        assessment.invalidate_recordset()

        self.assertEqual(assessment.cn_data_basis_state, "warning")
        self.assertEqual(assessment.cn_data_basis_dataset_count, 1)
        self.assertEqual(assessment.cn_data_basis_warning_count, 1)
