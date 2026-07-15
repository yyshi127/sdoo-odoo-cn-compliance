from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
NORMALIZER_PATH = (
    REPOSITORY_ROOT
    / "addons"
    / "sudo_country_pack_cn_einvoice_xbrl"
    / "parser"
    / "normalizer.py"
)
SPEC = importlib.util.spec_from_file_location(
    "cn_xbrl_normalizer",
    NORMALIZER_PATH,
)
NORMALIZER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(NORMALIZER)

NAMESPACE = "http://xbrl.mof.gov.cn/taxonomy/2023-12-31/einv"


class QName:
    def __init__(self, namespace, local_name):
        self.namespaceURI = namespace
        self.localName = local_name


class Unit:
    def __init__(self, code="CNY"):
        self.measures = (
            [QName(NORMALIZER.ISO_4217_NAMESPACE, code)],
            [],
        )


class Fact:
    def __init__(
        self,
        local_name,
        value=None,
        *,
        children=None,
        currency=None,
    ):
        self.qname = QName(NAMESPACE, local_name)
        self.value = value
        self.xValue = value
        self.isNil = value is None and not children
        self.modelTupleFacts = list(children or [])
        self.isTuple = bool(children)
        self.contextID = "c1"
        self.unitID = "u1" if currency else None
        self.unit = Unit(currency) if currency else None


class Model:
    def __init__(self, facts):
        self.facts = facts


def item(name, value, currency=None):
    return Fact(name, value, currency=currency)


def entry(direction, subject, amount):
    return Fact(
        NORMALIZER.ACCOUNTING_ENTRY_TUPLE,
        children=[
            item("DebitOrCredit", direction),
            item("NameOfGeneralLedgerSubject", subject),
            item("RecordedAmount", amount, "CNY"),
        ],
    )


class TestXbrlNormalizer(unittest.TestCase):
    def _model(self):
        accounting_document = Fact(
            NORMALIZER.ACCOUNTING_DOCUMENT_TUPLE,
            children=[
                item("NumberOfAccountingDocuments", "R0009"),
                item("PostingDate", "2026-06-30"),
                item("AccountingPeriod", "2026-06"),
                entry("借方", "原材料", "9000.00"),
                entry("借方", "应交税费", "1170.00"),
                entry("贷方", "银行存款", "10170.00"),
            ],
        )
        return Model(
            [
                item("InvoiceNumber", "22442000000921291350"),
                item("SellerName", "测试销售方有限公司"),
                item("SellerIdNum", "91440101TESTSELLER1"),
                item("TotalAmWithoutTax", "9000.00", "CNY"),
                item("TotalTaxAm", "1170.00", "CNY"),
                item("TotalTax-includedAmount", "10170.00", "CNY"),
                item("RequestTime", "2026-06-30 08:30:00"),
                item("WhetherEinvoiceHasBeenBooked", "true"),
                accounting_document,
            ]
        )

    def test_normalizes_invoice_and_nested_accounting_entries(self):
        payload, diagnostics = NORMALIZER.normalize_model(
            self._model(),
            "batch/invoice.xml",
            NAMESPACE,
        )

        self.assertFalse(diagnostics)
        self.assertEqual(payload["invoice_number"], "22442000000921291350")
        self.assertEqual(payload["currency_code"], "CNY")
        self.assertEqual(payload["is_booked"], "true")
        self.assertEqual(payload["source_document_key"], "batch/invoice.xml")
        self.assertGreater(payload["source_fact_count"], 10)
        self.assertEqual(len(payload["source_fact_digest"]), 64)
        documents = payload["accounting_documents"]
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]["voucher_number"], "R0009")
        self.assertEqual(len(documents[0]["entries"]), 3)
        self.assertEqual(documents[0]["entries"][2]["direction"], "贷方")

    def test_equal_duplicate_fact_is_warning(self):
        model = self._model()
        model.facts.append(item("SellerName", "测试销售方有限公司"))

        payload, diagnostics = NORMALIZER.normalize_model(
            model,
            "invoice.xml",
            NAMESPACE,
        )

        self.assertEqual(payload["seller_name"], "测试销售方有限公司")
        self.assertEqual(diagnostics[0]["severity"], "warning")
        self.assertEqual(diagnostics[0]["code"], "DUPLICATE_FACT")

    def test_conflicting_duplicate_fact_is_error(self):
        model = self._model()
        model.facts.append(item("InvoiceNumber", "DIFFERENT"))

        _payload, diagnostics = NORMALIZER.normalize_model(
            model,
            "invoice.xml",
            NAMESPACE,
        )

        self.assertIn(
            "CONFLICTING_DUPLICATE_FACT",
            {item["code"] for item in diagnostics},
        )
        self.assertIn("error", {item["severity"] for item in diagnostics})

    def test_multiple_currency_units_are_not_silently_collapsed(self):
        model = self._model()
        model.facts.append(item("TotalTaxAm", "1.00", "USD"))

        payload, diagnostics = NORMALIZER.normalize_model(
            model,
            "invoice.xml",
            NAMESPACE,
        )

        self.assertIsNone(payload["currency_code"])
        self.assertIn(
            "MULTIPLE_CURRENCIES",
            {item["code"] for item in diagnostics},
        )


if __name__ == "__main__":
    unittest.main()
