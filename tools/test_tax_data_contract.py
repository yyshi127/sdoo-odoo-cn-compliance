import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT
    / "addons"
    / "sudo_country_pack_cn"
    / "services"
    / "tax_data_contract.py"
)
SPEC = importlib.util.spec_from_file_location("tax_data_contract", MODULE_PATH)
CONTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTRACT)


def encoded(payload):
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def filing_payload():
    return {
        "schema": "sdoo.cn.tax-data.v1",
        "dataset_type": "vat_filing",
        "source_schema": "controlled-test-vat-return",
        "source_schema_version": "2026.1",
        "record_count": 1,
        "records": [
            {
                "source_record_key": "VAT-2026-06",
                "taxpayer_id": "91440101MA5D123451",
                "period_start": "2026-06-01",
                "period_end": "2026-06-30",
                "currency_code": "CNY",
                "tax_payable_amount": "0.00",
                "lines": [
                    {
                        "line_code": "L01",
                        "line_name": "测试行",
                        "amount_type": "tax",
                        "current_amount": "0.00",
                    }
                ],
            }
        ],
    }


def cit_filing_payload():
    return {
        "schema": "sdoo.cn.tax-data.v1",
        "dataset_type": "cit_filing",
        "source_schema": "controlled-test-cit-return",
        "source_schema_version": "2026.1",
        "record_count": 1,
        "records": [
            {
                "source_record_key": "CIT-2025-ANNUAL",
                "taxpayer_id": "91440101MA5D123451",
                "period_start": "2025-01-01",
                "period_end": "2025-12-31",
                "currency_code": "CNY",
                "tax_year": 2025,
                "return_period_type": "annual_reconciliation",
                "return_type_code": "CIT-ANNUAL",
                "taxable_income_amount": "0.00",
                "payable_amount": "0.00",
                "refundable_amount": "0.00",
                "lines": [
                    {
                        "line_code": "A100000-19",
                        "line_name": "应纳税所得额",
                        "amount_type": "taxable_income",
                        "current_amount": "0.00",
                    }
                ],
            }
        ],
    }


class TestTaxDataContract(unittest.TestCase):
    def test_valid_filing_contract_preserves_zero_text(self):
        result = CONTRACT.load_tax_data_contract(encoded(filing_payload()))

        self.assertEqual(result.dataset_type, "vat_filing")
        self.assertEqual(result.records[0]["tax_payable_amount"], "0.00")
        self.assertEqual(len(result.checksum), 64)

    def test_utf8_bom_is_accepted(self):
        raw = b"\xef\xbb\xbf" + encoded(filing_payload())
        result = CONTRACT.load_tax_data_contract(raw)

        self.assertEqual(result.source_schema_version, "2026.1")

    def test_expected_dataset_type_is_enforced(self):
        with self.assertRaisesRegex(
            CONTRACT.TaxDataContractError,
            "does not match",
        ):
            CONTRACT.load_tax_data_contract(
                encoded(filing_payload()),
                expected_dataset_type="tax_payment",
            )

    def test_unknown_root_field_is_rejected(self):
        payload = filing_payload()
        payload["token"] = "must-not-be-stored"

        with self.assertRaisesRegex(
            CONTRACT.TaxDataContractError,
            "unknown fields: token",
        ):
            CONTRACT.load_tax_data_contract(encoded(payload))

    def test_duplicate_json_key_is_rejected(self):
        with self.assertRaisesRegex(
            CONTRACT.TaxDataContractError,
            "duplicate JSON key: schema",
        ):
            CONTRACT.load_tax_data_contract(
                b'{"schema":"one","schema":"two"}'
            )

    def test_nonstandard_json_constant_is_rejected(self):
        with self.assertRaisesRegex(
            CONTRACT.TaxDataContractError,
            "non-standard JSON constant: NaN",
        ):
            CONTRACT.load_tax_data_contract(b'{"record_count":NaN}')

    def test_unknown_record_field_is_rejected(self):
        payload = filing_payload()
        payload["records"][0]["unexpected"] = 1

        with self.assertRaisesRegex(
            CONTRACT.TaxDataContractError,
            "unknown fields: unexpected",
        ):
            CONTRACT.load_tax_data_contract(encoded(payload))

    def test_record_count_must_match(self):
        payload = filing_payload()
        payload["record_count"] = 2

        with self.assertRaisesRegex(
            CONTRACT.TaxDataContractError,
            "record_count does not match",
        ):
            CONTRACT.load_tax_data_contract(encoded(payload))

    def test_duplicate_record_key_is_rejected(self):
        payload = filing_payload()
        payload["records"].append(dict(payload["records"][0]))
        payload["record_count"] = 2

        with self.assertRaisesRegex(
            CONTRACT.TaxDataContractError,
            "duplicate source_record_key",
        ):
            CONTRACT.load_tax_data_contract(encoded(payload))

    def test_duplicate_vat_line_code_is_rejected(self):
        payload = filing_payload()
        payload["records"][0]["lines"].append(
            dict(payload["records"][0]["lines"][0])
        )

        with self.assertRaisesRegex(
            CONTRACT.TaxDataContractError,
            "duplicate line_code",
        ):
            CONTRACT.load_tax_data_contract(encoded(payload))

    def test_cit_filing_contract_preserves_zero_and_lines(self):
        result = CONTRACT.load_tax_data_contract(encoded(cit_filing_payload()))

        self.assertEqual(result.dataset_type, "cit_filing")
        self.assertEqual(result.records[0]["taxable_income_amount"], "0.00")
        self.assertEqual(result.records[0]["lines"][0]["current_amount"], "0.00")

    def test_duplicate_cit_line_code_is_rejected(self):
        payload = cit_filing_payload()
        payload["records"][0]["lines"].append(
            dict(payload["records"][0]["lines"][0])
        )

        with self.assertRaisesRegex(
            CONTRACT.TaxDataContractError,
            "duplicate line_code",
        ):
            CONTRACT.load_tax_data_contract(encoded(payload))

    def test_unknown_cit_line_field_is_rejected(self):
        payload = cit_filing_payload()
        payload["records"][0]["lines"][0]["calculated_by_system"] = True

        with self.assertRaisesRegex(
            CONTRACT.TaxDataContractError,
            "unknown fields: calculated_by_system",
        ):
            CONTRACT.load_tax_data_contract(encoded(payload))

    def test_invalid_json_is_rejected(self):
        with self.assertRaisesRegex(
            CONTRACT.TaxDataContractError,
            "not valid UTF-8 JSON",
        ):
            CONTRACT.load_tax_data_contract(b"{")

    def test_non_bytes_input_is_rejected(self):
        with self.assertRaisesRegex(
            CONTRACT.TaxDataContractError,
            "must be bytes",
        ):
            CONTRACT.load_tax_data_contract("{}")

    def test_payment_contract_is_supported(self):
        payload = {
            "schema": "sdoo.cn.tax-data.v1",
            "dataset_type": "tax_payment",
            "source_schema": "controlled-test-payment",
            "source_schema_version": "1",
            "record_count": 1,
            "records": [
                {
                    "source_record_key": "PAY-2026-06-001",
                    "taxpayer_id": "91440101MA5D123451",
                    "tax_type_code": "VAT",
                    "period_start": "2026-06-01",
                    "period_end": "2026-06-30",
                    "payment_date": "2026-07-10",
                    "payment_status": "succeeded",
                    "currency_code": "CNY",
                    "amount": "100.00",
                    "payer_account_masked": "****1234",
                }
            ],
        }

        result = CONTRACT.load_tax_data_contract(encoded(payload))

        self.assertEqual(result.dataset_type, "tax_payment")


if __name__ == "__main__":
    unittest.main()
