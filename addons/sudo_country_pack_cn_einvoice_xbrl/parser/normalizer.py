from __future__ import annotations

import hashlib
import json


ISO_4217_NAMESPACE = "http://www.xbrl.org/2003/iso4217"

ACCOUNTING_DOCUMENT_TUPLE = "InformationOfAccountingDocumentsTuple"
ACCOUNTING_ENTRY_TUPLE = "InformationOfDebitAndCreditEntryTuple"

SCALAR_MAPPING = {
    "invoice_number": "InvoiceNumber",
    "seller_name": "SellerName",
    "seller_tax_id": "SellerIdNum",
    "untaxed_amount": "TotalAmWithoutTax",
    "tax_amount": "TotalTaxAm",
    "total_amount": "TotalTax-includedAmount",
    "request_time": "RequestTime",
    "contract_number": "ContractNumber",
    "is_red": "WhetherEinvoiceIsRedEinvoice",
    "is_booked": "WhetherEinvoiceHasBeenBooked",
    "is_checked": "WhetherEinvoiceHasBeenChecked",
    "is_paid": "WhetherEinvoiceHasBeenPaid",
    "bank_receipt_number": "NumberOfBankElectronicReceipt",
    "accounting_entity_tax_id": (
        "UnifiedSocialCreditCodeOfAccountingEntity"
    ),
    "accounting_entity_name": "NameOfAccountingEntity",
    "usage_confirmation": "UsageConfirmation",
}


def _qname(fact):
    return getattr(fact, "qname", None) or getattr(
        getattr(fact, "concept", None),
        "qname",
        None,
    )


def _local_name(fact):
    qname = _qname(fact)
    return getattr(qname, "localName", None) or getattr(
        qname,
        "localname",
        None,
    )


def _namespace(fact):
    qname = _qname(fact)
    return getattr(qname, "namespaceURI", None) or getattr(
        qname,
        "namespace",
        None,
    )


def _children(fact):
    return list(getattr(fact, "modelTupleFacts", None) or [])


def _is_tuple(fact):
    return bool(getattr(fact, "isTuple", False) or _children(fact))


def _lexical_value(fact):
    if getattr(fact, "isNil", False):
        return None
    value = getattr(fact, "value", None)
    if value is None:
        value = getattr(fact, "xValue", None)
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip() or None


def _unit_code(fact):
    unit = getattr(fact, "unit", None)
    measures = getattr(unit, "measures", None)
    if not measures or len(measures) != 2:
        return None
    numerators, denominators = measures
    if len(numerators) != 1 or denominators:
        return None
    measure = numerators[0]
    namespace = getattr(measure, "namespaceURI", None)
    local_name = getattr(measure, "localName", None)
    return local_name if namespace == ISO_4217_NAMESPACE else None


def _diagnostic(code, severity, message, scope):
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "scope": scope,
    }


def _scalar(facts, concept_name, diagnostics, scope, namespace):
    matches = [
        fact
        for fact in facts
        if _namespace(fact) == namespace and _local_name(fact) == concept_name
    ]
    values = [_lexical_value(fact) for fact in matches]
    values = [value for value in values if value is not None]
    unique_values = list(dict.fromkeys(values))
    if len(matches) > 1:
        severity = "error" if len(unique_values) > 1 else "warning"
        diagnostics.append(
            _diagnostic(
                "CONFLICTING_DUPLICATE_FACT"
                if severity == "error"
                else "DUPLICATE_FACT",
                severity,
                "同一作用域存在重复事实。",
                "%s/%s" % (scope, concept_name),
            )
        )
    return unique_values[0] if unique_values else None


def _fact_digest(facts, namespace):
    canonical = []

    def visit(items, parent_path):
        for index, fact in enumerate(items, start=1):
            if _namespace(fact) != namespace:
                continue
            local_name = _local_name(fact) or "unknown"
            path = "%s/%s[%s]" % (parent_path, local_name, index)
            canonical.append(
                {
                    "path": path,
                    "value": None if _is_tuple(fact) else _lexical_value(fact),
                    "context": getattr(fact, "contextID", None),
                    "unit": getattr(fact, "unitID", None),
                }
            )
            visit(_children(fact), path)

    visit(facts, "root")
    content = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _item_fact_count(facts, namespace):
    count = 0
    for fact in facts:
        if _namespace(fact) == namespace and not _is_tuple(fact):
            count += 1
        count += _item_fact_count(_children(fact), namespace)
    return count


def _currency_code(facts, namespace, diagnostics):
    monetary_names = {
        "TotalAmWithoutTax",
        "TotalTaxAm",
        "TotalTax-includedAmount",
        "RecordedAmount",
    }
    codes = []

    def visit(items):
        for fact in items:
            if (
                _namespace(fact) == namespace
                and _local_name(fact) in monetary_names
            ):
                code = _unit_code(fact)
                if code:
                    codes.append(code)
            visit(_children(fact))

    visit(facts)
    unique_codes = list(dict.fromkeys(codes))
    if len(unique_codes) > 1:
        diagnostics.append(
            _diagnostic(
                "MULTIPLE_CURRENCIES",
                "error",
                "同一电子发票实例包含多个货币单位。",
                "invoice",
            )
        )
    return unique_codes[0] if len(unique_codes) == 1 else None


def _accounting_entries(tuple_fact, diagnostics, document_scope, namespace):
    entries = []
    entry_tuples = [
        fact
        for fact in _children(tuple_fact)
        if (
            _namespace(fact) == namespace
            and _local_name(fact) == ACCOUNTING_ENTRY_TUPLE
        )
    ]
    for index, entry_tuple in enumerate(entry_tuples, start=1):
        scope = "%s/entry[%s]" % (document_scope, index)
        facts = _children(entry_tuple)
        entries.append(
            {
                "direction": _scalar(
                    facts,
                    "DebitOrCredit",
                    diagnostics,
                    scope,
                    namespace,
                ),
                "general_ledger_subject": _scalar(
                    facts,
                    "NameOfGeneralLedgerSubject",
                    diagnostics,
                    scope,
                    namespace,
                ),
                "subsidiary_ledger_subject": _scalar(
                    facts,
                    "NameOfSubsidiaryLedgerSubject",
                    diagnostics,
                    scope,
                    namespace,
                ),
                "amount": _scalar(
                    facts,
                    "RecordedAmount",
                    diagnostics,
                    scope,
                    namespace,
                ),
            }
        )
    return entries


def _accounting_documents(facts, diagnostics, namespace):
    documents = []
    tuples = [
        fact
        for fact in facts
        if (
            _namespace(fact) == namespace
            and _local_name(fact) == ACCOUNTING_DOCUMENT_TUPLE
        )
    ]
    for index, tuple_fact in enumerate(tuples, start=1):
        scope = "invoice/accounting_document[%s]" % index
        children = _children(tuple_fact)
        documents.append(
            {
                "voucher_number": _scalar(
                    children,
                    "NumberOfAccountingDocuments",
                    diagnostics,
                    scope,
                    namespace,
                ),
                "posting_date": _scalar(
                    children,
                    "PostingDate",
                    diagnostics,
                    scope,
                    namespace,
                ),
                "accounting_period": _scalar(
                    children,
                    "AccountingPeriod",
                    diagnostics,
                    scope,
                    namespace,
                ),
                "summary": _scalar(
                    children,
                    "SummaryOfAccountingDocuments",
                    diagnostics,
                    scope,
                    namespace,
                ),
                "entries": _accounting_entries(
                    tuple_fact,
                    diagnostics,
                    scope,
                    namespace,
                ),
            }
        )
    return documents


def normalize_model(model_xbrl, source_document_key, namespace):
    facts = list(getattr(model_xbrl, "facts", None) or [])
    diagnostics = []
    payload = {
        "source_document_key": source_document_key,
        "invoice_type_code": None,
    }
    for target, concept_name in SCALAR_MAPPING.items():
        payload[target] = _scalar(
            facts,
            concept_name,
            diagnostics,
            "invoice",
            namespace,
        )
    payload["currency_code"] = _currency_code(
        facts,
        namespace,
        diagnostics,
    )
    payload["accounting_documents"] = _accounting_documents(
        facts,
        diagnostics,
        namespace,
    )
    payload["source_fact_count"] = _item_fact_count(facts, namespace)
    payload["source_fact_digest"] = _fact_digest(facts, namespace)
    return payload, diagnostics
