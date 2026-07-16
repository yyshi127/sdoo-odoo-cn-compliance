from dataclasses import dataclass
import hashlib
import json
import re


CONTRACT_SCHEMA = "sdoo.cn.tax-data.v1"
SUPPORTED_DATASET_TYPES = frozenset(
    {
        "vat_filing",
        "cit_filing",
        "tax_payment",
        "iit_withholding",
        "payroll_summary",
    }
)
MAX_CONTRACT_BYTES = 20 * 1024 * 1024
MAX_RECORDS = 10000
MAX_LINES_PER_FILING = 500
MAX_LINES_PER_IIT_RETURN = 10000

_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema",
        "dataset_type",
        "source_schema",
        "source_schema_version",
        "record_count",
        "records",
    }
)
_COMMON_RECORD_FIELDS = frozenset(
    {
        "source_record_key",
        "taxpayer_name",
        "taxpayer_id",
        "period_start",
        "period_end",
        "currency_code",
    }
)
_VAT_FILING_FIELDS = _COMMON_RECORD_FIELDS | frozenset(
    {
        "jurisdiction_code",
        "jurisdiction_name",
        "return_type_code",
        "return_status",
        "submitted_at",
        "submission_reference",
        "revision_number",
        "correction_reference",
        "taxable_sales_amount",
        "output_tax_amount",
        "input_tax_amount",
        "input_tax_transfer_out_amount",
        "prior_credit_amount",
        "tax_payable_amount",
        "tax_refund_amount",
        "closing_credit_amount",
        "lines",
    }
)
_TAX_PAYMENT_FIELDS = _COMMON_RECORD_FIELDS | frozenset(
    {
        "tax_type_code",
        "tax_item_code",
        "payment_date",
        "payment_reference",
        "payment_status",
        "amount",
        "principal_amount",
        "interest_amount",
        "penalty_amount",
        "authority",
        "payment_channel",
        "payer_account_masked",
        "receipt_reference",
    }
)
_CIT_FILING_FIELDS = _COMMON_RECORD_FIELDS | frozenset(
    {
        "jurisdiction_code",
        "jurisdiction_name",
        "tax_year",
        "return_period_type",
        "return_type_code",
        "return_status",
        "submitted_at",
        "submission_reference",
        "revision_number",
        "correction_reference",
        "accounting_profit_amount",
        "adjustment_increase_amount",
        "adjustment_decrease_amount",
        "taxable_income_amount",
        "tax_payable_amount",
        "tax_relief_amount",
        "tax_credit_amount",
        "prepaid_tax_amount",
        "payable_amount",
        "refundable_amount",
        "lines",
    }
)
_IIT_WITHHOLDING_FIELDS = _COMMON_RECORD_FIELDS | frozenset(
    {
        "jurisdiction_code",
        "jurisdiction_name",
        "tax_year",
        "filing_frequency",
        "return_type_code",
        "return_status",
        "submitted_at",
        "submission_reference",
        "revision_number",
        "correction_reference",
        "declared_person_count",
        "declared_line_count",
        "total_income_amount",
        "total_tax_exempt_income_amount",
        "total_basic_deduction_amount",
        "total_special_deduction_amount",
        "total_special_additional_deduction_amount",
        "total_other_deduction_amount",
        "total_donation_deduction_amount",
        "total_taxable_income_amount",
        "total_tax_calculated_amount",
        "total_tax_relief_amount",
        "total_tax_paid_amount",
        "total_payable_refundable_amount",
        "lines",
    }
)
_PAYROLL_SUMMARY_FIELDS = _COMMON_RECORD_FIELDS | frozenset(
    {
        "payroll_frequency",
        "payroll_status",
        "payroll_run_reference",
        "approved_at",
        "declared_person_count",
        "gross_income_amount",
        "tax_exempt_income_amount",
        "employee_social_insurance_amount",
        "employee_housing_fund_amount",
        "other_pre_tax_deduction_amount",
        "net_pay_amount",
        "withheld_iit_amount",
    }
)
_VAT_LINE_FIELDS = frozenset(
    {
        "line_code",
        "line_name",
        "amount_type",
        "current_amount",
        "ytd_amount",
        "tax_rate",
    }
)
_CIT_LINE_FIELDS = frozenset(
    {
        "line_code",
        "line_name",
        "amount_type",
        "current_amount",
        "ytd_amount",
        "tax_rate",
    }
)
_IIT_WITHHOLDING_LINE_FIELDS = frozenset(
    {
        "source_line_key",
        "subject_key",
        "residency_status",
        "income_type_code",
        "current_income_amount",
        "current_tax_exempt_income_amount",
        "current_basic_deduction_amount",
        "current_special_deduction_amount",
        "current_other_deduction_amount",
        "cumulative_income_amount",
        "cumulative_basic_deduction_amount",
        "cumulative_special_deduction_amount",
        "cumulative_special_additional_deduction_amount",
        "cumulative_other_deduction_amount",
        "donation_deduction_amount",
        "taxable_income_amount",
        "tax_rate",
        "quick_deduction_amount",
        "tax_calculated_amount",
        "tax_relief_amount",
        "tax_paid_amount",
        "payable_refundable_amount",
    }
)
_IIT_CONTROLLED_KEY_PATTERN = (
    r"(?:hmac-sha256:[0-9a-f]{64}|"
    r"opaque:(?:[0-9a-f]{32,64}|"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12}))"
)
_IIT_SUBJECT_KEY = re.compile(_IIT_CONTROLLED_KEY_PATTERN)
_IIT_SOURCE_LINE_KEY = re.compile(_IIT_CONTROLLED_KEY_PATTERN)
_IIT_IDENTITY_NUMBER = re.compile(r"(?<!\d)(?:\d{15}|\d{17}[0-9Xx])(?!\d)")


class TaxDataContractError(ValueError):
    pass


@dataclass(frozen=True)
class TaxDataContract:
    dataset_type: str
    source_schema: str
    source_schema_version: str
    records: tuple[dict, ...]
    checksum: str


def _reject_duplicate_keys(pairs):
    payload = {}
    for key, value in pairs:
        if key in payload:
            raise TaxDataContractError(f"duplicate JSON key: {key}")
        payload[key] = value
    return payload


def _reject_nonstandard_constant(value):
    raise TaxDataContractError(f"non-standard JSON constant: {value}")


def _text(value, label, limit):
    if not isinstance(value, str):
        raise TaxDataContractError(f"{label} must be a string")
    normalized = " ".join(value.split()).strip()
    if not normalized:
        raise TaxDataContractError(f"{label} must not be blank")
    if len(normalized) > limit:
        raise TaxDataContractError(f"{label} exceeds {limit} characters")
    return normalized


def _unknown_fields(payload, allowed, label):
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise TaxDataContractError(
            f"{label} contains unknown fields: {', '.join(unknown)}"
        )


def _validate_vat_lines(record, record_index):
    lines = record.get("lines", [])
    if lines is None:
        lines = []
    if not isinstance(lines, list):
        raise TaxDataContractError(
            f"records[{record_index}].lines must be a list"
        )
    if len(lines) > MAX_LINES_PER_FILING:
        raise TaxDataContractError(
            f"records[{record_index}].lines exceeds "
            f"{MAX_LINES_PER_FILING} entries"
        )
    line_codes = set()
    for line_index, line in enumerate(lines):
        if not isinstance(line, dict):
            raise TaxDataContractError(
                f"records[{record_index}].lines[{line_index}] "
                "must be an object"
            )
        _unknown_fields(
            line,
            _VAT_LINE_FIELDS,
            f"records[{record_index}].lines[{line_index}]",
        )
        line_code = _text(
            line.get("line_code"),
            f"records[{record_index}].lines[{line_index}].line_code",
            128,
        )
        if line_code in line_codes:
            raise TaxDataContractError(
                f"records[{record_index}] contains duplicate line_code "
                f"{line_code}"
            )
        line_codes.add(line_code)


def _validate_cit_lines(record, record_index):
    lines = record.get("lines", [])
    if lines is None:
        lines = []
    if not isinstance(lines, list):
        raise TaxDataContractError(
            f"records[{record_index}].lines must be a list"
        )
    if len(lines) > MAX_LINES_PER_FILING:
        raise TaxDataContractError(
            f"records[{record_index}].lines exceeds "
            f"{MAX_LINES_PER_FILING} entries"
        )
    line_codes = set()
    for line_index, line in enumerate(lines):
        if not isinstance(line, dict):
            raise TaxDataContractError(
                f"records[{record_index}].lines[{line_index}] "
                "must be an object"
            )
        _unknown_fields(
            line,
            _CIT_LINE_FIELDS,
            f"records[{record_index}].lines[{line_index}]",
        )
        line_code = _text(
            line.get("line_code"),
            f"records[{record_index}].lines[{line_index}].line_code",
            128,
        )
        if line_code in line_codes:
            raise TaxDataContractError(
                f"records[{record_index}] contains duplicate line_code "
                f"{line_code}"
            )
        line_codes.add(line_code)


def _validate_iit_lines(record, record_index):
    lines = record.get("lines", [])
    if lines is None:
        lines = []
    if not isinstance(lines, list):
        raise TaxDataContractError(
            f"records[{record_index}].lines must be a list"
        )
    if len(lines) > MAX_LINES_PER_IIT_RETURN:
        raise TaxDataContractError(
            f"records[{record_index}].lines exceeds "
            f"{MAX_LINES_PER_IIT_RETURN} entries"
        )
    source_line_keys = set()
    for line_index, line in enumerate(lines):
        label = f"records[{record_index}].lines[{line_index}]"
        if not isinstance(line, dict):
            raise TaxDataContractError(f"{label} must be an object")
        _unknown_fields(line, _IIT_WITHHOLDING_LINE_FIELDS, label)
        source_line_key = _text(
            line.get("source_line_key"),
            f"{label}.source_line_key",
            512,
        )
        if source_line_key in source_line_keys:
            raise TaxDataContractError(
                f"records[{record_index}] contains duplicate source_line_key "
                f"{source_line_key}"
            )
        if _IIT_IDENTITY_NUMBER.search(source_line_key):
            raise TaxDataContractError(
                f"{label}.source_line_key must not contain an identity number"
            )
        if not _IIT_SOURCE_LINE_KEY.fullmatch(source_line_key):
            raise TaxDataContractError(
                f"{label}.source_line_key must be a controlled opaque key"
            )
        source_line_keys.add(source_line_key)
        subject_key = _text(
            line.get("subject_key"),
            f"{label}.subject_key",
            160,
        )
        if not _IIT_SUBJECT_KEY.fullmatch(subject_key):
            raise TaxDataContractError(
                f"{label}.subject_key must be a controlled pseudonymous key"
            )


def load_tax_data_contract(
    raw,
    *,
    expected_dataset_type=None,
    max_records=MAX_RECORDS,
):
    if not isinstance(raw, (bytes, bytearray)):
        raise TaxDataContractError("contract input must be bytes")
    if not raw:
        raise TaxDataContractError("contract input must not be empty")
    if len(raw) > MAX_CONTRACT_BYTES:
        raise TaxDataContractError(
            f"contract input exceeds {MAX_CONTRACT_BYTES} bytes"
        )
    try:
        payload = json.loads(
            bytes(raw).decode("utf-8-sig"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonstandard_constant,
        )
    except (RecursionError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TaxDataContractError("contract input is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise TaxDataContractError("contract root must be an object")
    _unknown_fields(payload, _TOP_LEVEL_FIELDS, "contract root")
    if payload.get("schema") != CONTRACT_SCHEMA:
        raise TaxDataContractError(
            f"schema must be exactly {CONTRACT_SCHEMA}"
        )
    dataset_type = payload.get("dataset_type")
    if dataset_type not in SUPPORTED_DATASET_TYPES:
        raise TaxDataContractError("dataset_type is not supported")
    if expected_dataset_type and dataset_type != expected_dataset_type:
        raise TaxDataContractError(
            "dataset_type does not match the controlled dataset"
        )
    source_schema = _text(payload.get("source_schema"), "source_schema", 256)
    source_schema_version = _text(
        payload.get("source_schema_version"),
        "source_schema_version",
        128,
    )
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        raise TaxDataContractError("records must be a non-empty list")
    if len(records) > max_records:
        raise TaxDataContractError(f"records exceeds {max_records} entries")
    record_count = payload.get("record_count")
    if isinstance(record_count, bool) or not isinstance(record_count, int):
        raise TaxDataContractError("record_count must be an integer")
    if record_count != len(records):
        raise TaxDataContractError(
            "record_count does not match the number of records"
        )
    allowed_fields = {
        "vat_filing": _VAT_FILING_FIELDS,
        "cit_filing": _CIT_FILING_FIELDS,
        "tax_payment": _TAX_PAYMENT_FIELDS,
        "iit_withholding": _IIT_WITHHOLDING_FIELDS,
        "payroll_summary": _PAYROLL_SUMMARY_FIELDS,
    }[dataset_type]
    source_keys = set()
    normalized_records = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise TaxDataContractError(f"records[{index}] must be an object")
        _unknown_fields(record, allowed_fields, f"records[{index}]")
        source_key = _text(
            record.get("source_record_key"),
            f"records[{index}].source_record_key",
            512,
        )
        if source_key in source_keys:
            raise TaxDataContractError(
                f"duplicate source_record_key: {source_key}"
            )
        source_keys.add(source_key)
        if dataset_type == "vat_filing":
            _validate_vat_lines(record, index)
        elif dataset_type == "cit_filing":
            _validate_cit_lines(record, index)
        elif dataset_type == "iit_withholding":
            _validate_iit_lines(record, index)
        normalized_records.append(dict(record, source_record_key=source_key))
    canonical = {
        "schema": CONTRACT_SCHEMA,
        "dataset_type": dataset_type,
        "source_schema": source_schema,
        "source_schema_version": source_schema_version,
        "record_count": len(normalized_records),
        "records": normalized_records,
    }
    checksum = hashlib.sha256(
        json.dumps(
            canonical,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return TaxDataContract(
        dataset_type=dataset_type,
        source_schema=source_schema,
        source_schema_version=source_schema_version,
        records=tuple(normalized_records),
        checksum=checksum,
    )
