from __future__ import annotations

import ast
import csv
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ADDON_ROOT = REPOSITORY_ROOT / "addons" / "sudo_country_pack_cn"
XBRL_ADDON_ROOT = (
    REPOSITORY_ROOT / "addons" / "sudo_country_pack_cn_einvoice_xbrl"
)
TEXT_SUFFIXES = {
    ".csv",
    ".json",
    ".md",
    ".py",
    ".txt",
    ".xml",
    ".yml",
    ".yaml",
}
SECRET_PATTERNS = {
    "private key": re.compile(r"BEGIN (?:RSA |OPENSSH )?PRIVATE KEY"),
    "credential assignment": re.compile(
        r"(?i)\b(?:api[_-]?key|password|secret|token)\s*=\s*[^\s]"
    ),
}
OFFICIAL_SOURCE_HOSTS = {
    "fgk.chinatax.gov.cn",
    "kjs.mof.gov.cn",
    "www.mof.gov.cn",
    "www.gov.cn",
    "xzfg.moj.gov.cn",
}
EXPECTED_OFFICIAL_SOURCE_URLS = {
    "source_cn_accounting_law_2024_candidate": (
        "https://kjs.mof.gov.cn/zhengcefabu/202408/t20240812_3941615.htm"
    ),
    "source_cn_accounting_archives_order_79_candidate": (
        "https://www.gov.cn/gongbao/content/2016/content_5041555.htm"
    ),
    "source_cn_vat_law_2024_candidate": (
        "https://fgk.chinatax.gov.cn/zcfgk/c100009/c5237365/content.html"
    ),
    "source_cn_vat_regulation_order_826_candidate": (
        "https://fgk.chinatax.gov.cn/zcfgk/c100010/c5246349/content.html"
    ),
    "source_cn_invoice_measures_2023_candidate": (
        "https://fgk.chinatax.gov.cn/zcfgk/c100010/c5195084/content.html"
    ),
    "source_cn_tax_collection_law_2015_candidate": (
        "https://fgk.chinatax.gov.cn/zcfgk/c100009/c5195081/content.html"
    ),
    "source_cn_electronic_voucher_standard_2025_candidate": (
        "https://www.mof.gov.cn/jrttts/202505/t20250521_3964264.htm"
    ),
    "source_cn_cit_law_2018_candidate": (
        "https://fgk.chinatax.gov.cn/zcfgk/c100009/c5193018/content.html"
    ),
    "source_cn_cit_regulation_2024_candidate": (
        "https://xzfg.moj.gov.cn/law/download?LawID=1741&type=pdf"
    ),
}
EXPECTED_SOURCE_URL_REPLACEMENTS = {
    "source_cn_accounting_law_2024_candidate": (
        "https://wb.flk.npc.gov.cn/flfg/PDF/"
        "b450cf89277c40918e7077c5418d93d9.pdf",
        EXPECTED_OFFICIAL_SOURCE_URLS[
            "source_cn_accounting_law_2024_candidate"
        ],
    ),
    "source_cn_accounting_archives_order_79_candidate": (
        "https://tfs.mof.gov.cn/caizhengbuling/201512/"
        "t20151214_1613338.htm",
        EXPECTED_OFFICIAL_SOURCE_URLS[
            "source_cn_accounting_archives_order_79_candidate"
        ],
    ),
}
ALLOWED_CN_RULE_NATURES = {
    "statutory_requirement",
    "tax_calculation",
    "filing_deadline",
    "internal_control",
    "data_readiness",
}
CONTROL_RULE_NATURES = {"internal_control", "data_readiness"}
ALLOWED_CN_RULE_HANDLERS = {
    "cn.cit.reconciliation.review.v1": "1",
}
ALLOWED_CN_CITATION_TYPES = {
    "direct_requirement",
    "supporting_context",
    "internal_control_rationale",
    "technical_guidance",
}


def fail(message: str) -> None:
    raise AssertionError(message)


def literal_assignments(tree: ast.Module) -> dict[str, object]:
    values: dict[str, object] = {}
    for node in tree.body:
        if not (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            continue
        try:
            values[node.targets[0].id] = ast.literal_eval(node.value)
        except (TypeError, ValueError):
            continue
    return values


def validate_text_and_syntax() -> None:
    for path in sorted(REPOSITORY_ROOT.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        if path.suffix not in TEXT_SUFFIXES:
            continue
        content = path.read_text(encoding="utf-8", errors="strict")
        if "\ufffd" in content:
            fail(f"replacement character found in {path}")
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(content):
                fail(f"possible {label} found in {path}")
        if path.suffix == ".py":
            ast.parse(content, filename=str(path))
        elif path.suffix == ".json":
            json.loads(content)
        elif path.suffix == ".xml":
            ElementTree.parse(path)


def validate_manifest() -> dict[str, object]:
    path = ADDON_ROOT / "__manifest__.py"
    manifest = ast.literal_eval(path.read_text(encoding="utf-8"))
    if not str(manifest.get("version", "")).startswith("19.0."):
        fail("manifest version must target Odoo 19")
    if not manifest.get("installable"):
        fail("China country pack must remain installable")
    if manifest.get("application"):
        fail("China country pack must not create a second application root")
    data_files = manifest.get("data", [])
    for relative_path in data_files:
        if not (ADDON_ROOT / relative_path).is_file():
            fail(f"manifest data file does not exist: {relative_path}")
    ordered_data = {
        "data/official_source_candidates.xml",
        "data/compliance_rule_drafts.xml",
        "data/rule_review_candidates.xml",
        "reports/rule_review_packet_report.xml",
        "views/rule_review_packet_views.xml",
    }
    if not ordered_data.issubset(data_files):
        fail("manifest must load official sources and rule drafts")
    if data_files.index("data/official_source_candidates.xml") > data_files.index(
        "data/compliance_rule_drafts.xml"
    ):
        fail("official source candidates must load before rule drafts")
    if data_files.index("data/compliance_rule_drafts.xml") > data_files.index(
        "data/rule_review_candidates.xml"
    ):
        fail("rule drafts must load before professional review candidates")
    return manifest


def validate_hooks(manifest: dict[str, object]) -> None:
    path = ADDON_ROOT / "hooks.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    assignments = literal_assignments(tree)
    if assignments.get("PACK_VERSION") != manifest["version"]:
        fail("PACK_VERSION must match the manifest version")
    templates = assignments.get("CN_OBLIGATION_TEMPLATES")
    if not isinstance(templates, tuple) or not templates:
        fail("CN_OBLIGATION_TEMPLATES must be a non-empty tuple")
    codes = [template["code"] for template in templates]
    if len(codes) != len(set(codes)):
        fail("China obligation template codes must be unique")
    for template in templates:
        if not template["code"].startswith("CN-"):
            fail(f"invalid obligation code: {template['code']}")
        if not template["domain_key"].startswith("CN."):
            fail(f"invalid China domain key: {template['domain_key']}")
        if template["filing_required"] and not template["filing_type"]:
            fail(f"filing type missing for {template['code']}")


def validate_country_pack_metadata(manifest: dict[str, object]) -> None:
    path = ADDON_ROOT / "data" / "country_pack_data.xml"
    root = ElementTree.parse(path).getroot()
    records = [
        record
        for record in root.findall(".//record")
        if record.attrib.get("model") == "sudo.compliance.country.pack"
    ]
    if len(records) != 1:
        fail("China country pack metadata must contain exactly one record")
    fields = record_fields(records[0])
    if field_text(fields, "version", records[0].attrib["id"]) != manifest[
        "version"
    ]:
        fail("country pack data version must match the manifest")
    capabilities = literal_eval_field(
        fields["capability_json"],
        records[0].attrib["id"],
    )
    if not isinstance(capabilities, dict):
        fail("country pack capabilities must be a dictionary")
    features = capabilities.get("features", {})
    if features.get("external_dataset") is not True:
        fail("controlled external dataset capability must be declared")
    if features.get("einvoice_normalized_ledger") is not True:
        fail("normalized electronic invoice ledger must be declared")
    if features.get("einvoice_xbrl_parser") is not False:
        fail("XBRL parser must remain disabled until its adapter is delivered")
    if features.get("reconciliation") is not True:
        fail("electronic invoice reconciliation capability must be declared")
    if features.get("vat_period_reconciliation") is not True:
        fail("VAT period reconciliation capability must be declared")
    if features.get("formal_compliance_report") is not True:
        fail("formal compliance report capability must be declared")
    if features.get("vat_filing_payment_archive") is not True:
        fail("controlled VAT filing and payment archive capability must be declared")
    if features.get("cit_filing_normalization") is not True:
        fail("controlled CIT filing normalization capability must be declared")
    if features.get("cit_accounting_reconciliation") is not True:
        fail("controlled CIT accounting reconciliation capability must be declared")
    if features.get("cit_governed_rule_candidates") is not True:
        fail("governed CIT rule candidate capability must be declared")
    if features.get("cit_filing_settlement_archive") is not True:
        fail("controlled CIT filing and settlement archive capability must be declared")


def validate_fact_definitions() -> tuple[set[str], dict[str, str]]:
    path = ADDON_ROOT / "data" / "compliance_fact_data.xml"
    root = ElementTree.parse(path).getroot()
    facts: list[dict[str, str]] = []
    fact_ids: dict[str, str] = {}
    for record in root.findall(".//record"):
        if record.attrib.get("model") != "sudo.compliance.fact.definition":
            continue
        fields = {
            field.attrib["name"]: (field.text or "").strip()
            for field in record.findall("field")
        }
        facts.append(fields)
        fact_ids[record.attrib["id"]] = fields["key"]
    if not facts:
        fail("at least one China fact definition is required")
    keys = [fact["key"] for fact in facts]
    if len(keys) != len(set(keys)):
        fail("China fact definition keys must be unique")
    provider_code = (
        ADDON_ROOT / "models" / "compliance_engine.py"
    ).read_text(encoding="utf-8")
    for fact in facts:
        key = fact["key"]
        if not key.startswith("cn."):
            fail(f"invalid China fact key: {key}")
        if fact["provider_key"] != key:
            fail(f"fact and provider key differ: {key}")
        if f'"{key}"' not in provider_code:
            fail(f"fact provider is not registered: {key}")
    return set(keys), fact_ids


def record_fields(record: ElementTree.Element) -> dict[str, ElementTree.Element]:
    return {
        field.attrib["name"]: field
        for field in record.findall("field")
    }


def field_text(
    fields: dict[str, ElementTree.Element],
    name: str,
    record_id: str,
) -> str:
    field = fields.get(name)
    value = (field.text or "").strip() if field is not None else ""
    if not value:
        fail(f"{record_id} is missing required field {name}")
    return value


def literal_eval_field(
    field: ElementTree.Element,
    record_id: str,
) -> object:
    expression = field.attrib.get("eval")
    if not expression:
        fail(f"{record_id}.{field.attrib['name']} must use an eval expression")
    try:
        return ast.literal_eval(expression)
    except (SyntaxError, ValueError) as exc:
        fail(f"invalid literal expression in {record_id}: {exc}")


def condition_fact_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        fact = value.get("fact")
        if isinstance(fact, str):
            keys.add(fact)
        for child in value.values():
            keys.update(condition_fact_keys(child))
    elif isinstance(value, (list, tuple)):
        for child in value:
            keys.update(condition_fact_keys(child))
    return keys


def validate_official_source_candidates() -> set[str]:
    path = ADDON_ROOT / "data" / "official_source_candidates.xml"
    root = ElementTree.parse(path).getroot()
    if root.attrib.get("noupdate") != "1":
        fail("official source candidates must be protected by noupdate")
    records = [
        record
        for record in root.findall(".//record")
        if record.attrib.get("model")
        == "sudo.compliance.authority.source"
    ]
    if len(records) < 7:
        fail("at least seven China official source candidates are required")

    source_ids: set[str] = set()
    official_urls: set[str] = set()
    forbidden_fields = {
        "content_hash",
        "reviewed_at",
        "reviewer_id",
        "snapshot_attachment_id",
    }
    for record in records:
        xml_id = record.attrib.get("id", "")
        if not xml_id or xml_id in source_ids:
            fail("official source candidate XML IDs must be unique")
        if not xml_id.endswith("_candidate"):
            fail(f"official source candidate ID must be explicit: {xml_id}")
        source_ids.add(xml_id)

        fields = record_fields(record)
        country = fields.get("country_id")
        if country is None or country.attrib.get("ref") != "base.cn":
            fail(f"{xml_id} must be restricted to China")
        field_text(fields, "name", xml_id)
        field_text(fields, "authority", xml_id)
        field_text(fields, "source_type", xml_id)
        field_text(fields, "official_version", xml_id)
        field_text(fields, "published_date", xml_id)

        status = (
            (fields["status"].text or "").strip()
            if "status" in fields
            else "draft"
        )
        if status != "draft":
            fail(f"{xml_id} must remain a draft source candidate")
        snapshot_kind = (
            (fields["snapshot_kind"].text or "").strip()
            if "snapshot_kind" in fields
            else "other"
        )
        if snapshot_kind != "other":
            fail(f"{xml_id} must not claim an official snapshot")
        populated_forbidden = forbidden_fields & set(fields)
        if populated_forbidden:
            fail(
                f"{xml_id} pre-populates governed fields: "
                f"{sorted(populated_forbidden)}"
            )

        official_url = field_text(fields, "official_url", xml_id)
        expected_url = EXPECTED_OFFICIAL_SOURCE_URLS.get(xml_id)
        if official_url != expected_url:
            fail(
                f"{xml_id} does not use its audited official URL: "
                f"{official_url}"
            )
        parsed = urlparse(official_url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in OFFICIAL_SOURCE_HOSTS
            or parsed.username
            or parsed.password
            or parsed.port not in {None, 443}
        ):
            fail(f"{xml_id} does not use an approved official HTTPS host")
        normalized_url = official_url.rstrip("/")
        if normalized_url in official_urls:
            fail(f"official source candidate URLs must be unique: {official_url}")
        official_urls.add(normalized_url)

        review_date = date.fromisoformat(
            field_text(fields, "next_review_date", xml_id)
        )
        if review_date < date.today():
            fail(f"official source candidate is overdue for review: {xml_id}")
    if source_ids != set(EXPECTED_OFFICIAL_SOURCE_URLS):
        fail("audited official source URL manifest is incomplete")
    return source_ids


def validate_rule_drafts(
    fact_keys: set[str],
    fact_ids: dict[str, str],
    source_ids: set[str],
) -> dict[str, set[str]]:
    path = ADDON_ROOT / "data" / "compliance_rule_drafts.xml"
    root = ElementTree.parse(path).getroot()
    records = root.findall(".//record")
    rules = {
        record.attrib["id"]: record_fields(record)
        for record in records
        if record.attrib.get("model") == "sudo.compliance.rule"
    }
    versions = {
        record.attrib["id"]: record_fields(record)
        for record in records
        if record.attrib.get("model") == "sudo.compliance.rule.version"
    }
    cases = [
        (record.attrib["id"], record_fields(record))
        for record in records
        if record.attrib.get("model") == "sudo.compliance.rule.test.case"
    ]
    if len(rules) < 4 or len(versions) < 4:
        fail("at least four governed China rule drafts are required")

    codes = [field_text(fields, "code", xml_id) for xml_id, fields in rules.items()]
    if len(codes) != len(set(codes)):
        fail("China rule codes must be unique")
    if any(not code.startswith("CN-") for code in codes):
        fail("all China rule codes must start with CN-")
    for xml_id, fields in rules.items():
        nature = field_text(fields, "cn_rule_nature", xml_id)
        if nature not in ALLOWED_CN_RULE_NATURES:
            fail(f"invalid China rule nature on {xml_id}: {nature}")
        if nature not in CONTROL_RULE_NATURES:
            fail(
                f"packaged draft controls cannot claim statutory status: {xml_id}"
            )

    version_case_results: dict[str, set[str]] = {
        xml_id: set() for xml_id in versions
    }
    version_source_refs: dict[str, set[str]] = {}
    rules_with_versions: set[str] = set()
    ref_pattern = re.compile(r"ref\(['\"]([^'\"]+)['\"]\)")
    for xml_id, fields in versions.items():
        version = field_text(fields, "version", xml_id)
        if not version.startswith("DRAFT-"):
            fail(f"draft asset contains a non-draft version: {xml_id}")
        state = (fields.get("state").text or "").strip() if fields.get(
            "state"
        ) is not None else "draft"
        if state != "draft":
            fail(f"draft version forces a publishable state: {xml_id}")
        if "professional_review_state" in fields:
            fail(f"draft version must not force professional sign-off: {xml_id}")
        source_field = fields.get("authority_source_ids")
        if source_field is None:
            fail(f"{xml_id} has no official source candidates")
        source_refs = set(
            ref_pattern.findall(source_field.attrib.get("eval", ""))
        )
        if not source_refs:
            fail(f"{xml_id} has no official source candidate references")
        unknown_source_refs = source_refs - source_ids
        if unknown_source_refs:
            fail(
                f"{xml_id} references unknown source candidates: "
                f"{sorted(unknown_source_refs)}"
            )
        version_source_refs[xml_id] = source_refs
        if field_text(fields, "stale_policy", xml_id) != "block_all":
            fail(f"draft version must block evaluation when stale: {xml_id}")
        if field_text(fields, "requires_human_review", xml_id) != "True":
            fail(f"draft version must require human review: {xml_id}")

        rule_ref = fields.get("rule_id")
        rule_id = rule_ref.attrib.get("ref") if rule_ref is not None else None
        if rule_id not in rules:
            fail(f"{xml_id} references an unknown China rule")
        rules_with_versions.add(rule_id)

        required_field = fields.get("required_fact_ids")
        if required_field is None:
            fail(f"{xml_id} has no required fact declaration")
        required_refs = set(
            ref_pattern.findall(required_field.attrib.get("eval", ""))
        )
        required_keys = {fact_ids[ref] for ref in required_refs if ref in fact_ids}
        if len(required_keys) != len(required_refs):
            fail(f"{xml_id} references an unknown fact definition")
        if not required_keys:
            fail(f"{xml_id} has no required facts")

        evaluator_type = field_text(fields, "evaluator_type", xml_id)
        if evaluator_type == "declarative":
            condition_field = fields.get("condition_json")
            if condition_field is None:
                fail(f"{xml_id} has no declarative condition")
            condition = literal_eval_field(condition_field, xml_id)
            used_fact_keys = condition_fact_keys(condition)
            if not used_fact_keys:
                fail(f"{xml_id} condition does not reference a fact")
            unknown_keys = used_fact_keys - fact_keys
            if unknown_keys:
                fail(
                    f"{xml_id} references unknown facts: "
                    f"{sorted(unknown_keys)}"
                )
            missing_required_keys = used_fact_keys - required_keys
            if missing_required_keys:
                fail(
                    f"{xml_id} condition facts are not declared: "
                    f"{sorted(missing_required_keys)}"
                )
        elif evaluator_type == "handler":
            handler_key = field_text(fields, "handler_key", xml_id)
            handler_version = field_text(fields, "handler_version", xml_id)
            if ALLOWED_CN_RULE_HANDLERS.get(handler_key) != handler_version:
                fail(
                    f"{xml_id} uses an unaudited handler or version: "
                    f"{handler_key}@{handler_version}"
                )
        else:
            fail(f"{xml_id} uses an unsupported evaluator: {evaluator_type}")

    if rules_with_versions != set(rules):
        fail("every packaged China rule must have a draft version")

    for xml_id, fields in cases:
        version_field = fields.get("rule_version_id")
        version_id = (
            version_field.attrib.get("ref")
            if version_field is not None
            else None
        )
        if version_id not in versions:
            fail(f"{xml_id} references an unknown draft version")
        facts_field = fields.get("facts_json")
        if facts_field is None:
            fail(f"{xml_id} has no test facts")
        test_facts = literal_eval_field(facts_field, xml_id)
        if not isinstance(test_facts, dict) or not test_facts:
            fail(f"{xml_id} must provide a non-empty fact dictionary")
        unknown_keys = set(test_facts) - fact_keys
        if unknown_keys:
            fail(f"{xml_id} uses unknown facts: {sorted(unknown_keys)}")
        expected = field_text(fields, "expected_result", xml_id)
        if expected not in {"pass", "fail", "unknown"}:
            fail(f"{xml_id} has an invalid expected result")
        version_case_results[version_id].add(expected)

    for version_id, results in version_case_results.items():
        if not {"pass", "fail"}.issubset(results):
            fail(f"{version_id} must have pass and fail test cases")
    return version_source_refs


def validate_rule_review_candidates(
    source_ids: set[str],
    version_source_refs: dict[str, set[str]],
) -> None:
    path = ADDON_ROOT / "data" / "rule_review_candidates.xml"
    root = ElementTree.parse(path).getroot()
    if root.attrib.get("noupdate") != "1":
        fail("professional review candidates must be protected by noupdate")

    packet_records = [
        record
        for record in root.findall(".//record")
        if record.attrib.get("model") == "sudo.cn.rule.review.packet"
    ]
    citation_records = [
        record
        for record in root.findall(".//record")
        if record.attrib.get("model") == "sudo.cn.rule.review.citation"
    ]
    if len(packet_records) != len(version_source_refs):
        fail("every packaged China rule version requires one review packet")
    if len(citation_records) != 20:
        fail("packaged China review candidates require twenty citations")

    required_packet_fields = {
        "scope_summary",
        "applicability_assumptions",
        "exclusions_limitations",
        "conclusion_boundary",
        "reviewer_questions",
    }
    forbidden_packet_fields = {
        "professional_review_state",
        "professional_reviewer_id",
        "professional_reviewed_at",
        "professional_qualification",
        "professional_review_notes",
        "professional_evidence_reference",
        "professional_evidence_checksum",
        "professional_rule_checksum",
    }
    packet_versions: dict[str, str] = {}
    packet_citation_sources: dict[str, set[str]] = {}
    for record in packet_records:
        xml_id = record.attrib.get("id", "")
        if not xml_id or xml_id in packet_versions:
            fail("review packet XML IDs must be unique")
        fields = record_fields(record)
        version_field = fields.get("rule_version_id")
        version_id = (
            version_field.attrib.get("ref")
            if version_field is not None
            else None
        )
        if version_id not in version_source_refs:
            fail(f"{xml_id} references an unknown China rule version")
        if version_id in packet_versions.values():
            fail(f"multiple review packets reference {version_id}")
        packet_versions[xml_id] = version_id
        packet_citation_sources[xml_id] = set()
        for field_name in required_packet_fields:
            value = field_text(fields, field_name, xml_id)
            if value.lower() in {"tbd", "todo", "待补", "待定"}:
                fail(f"{xml_id} contains placeholder review material")
        populated_forbidden = forbidden_packet_fields & set(fields)
        if populated_forbidden:
            fail(
                f"{xml_id} pre-populates professional sign-off fields: "
                f"{sorted(populated_forbidden)}"
            )

    for record in citation_records:
        xml_id = record.attrib.get("id", "")
        fields = record_fields(record)
        packet_field = fields.get("packet_id")
        packet_id = (
            packet_field.attrib.get("ref")
            if packet_field is not None
            else None
        )
        if packet_id not in packet_versions:
            fail(f"{xml_id} references an unknown review packet")
        source_field = fields.get("source_id")
        source_id = (
            source_field.attrib.get("ref")
            if source_field is not None
            else None
        )
        if source_id not in source_ids:
            fail(f"{xml_id} references an unknown official source")
        packet_citation_sources[packet_id].add(source_id)
        citation_type = field_text(fields, "citation_type", xml_id)
        if citation_type not in ALLOWED_CN_CITATION_TYPES:
            fail(f"{xml_id} has an invalid citation type")
        if citation_type == "direct_requirement":
            fail(
                f"packaged internal controls cannot claim a direct legal "
                f"requirement: {xml_id}"
            )
        for field_name in (
            "locator",
            "claim_summary",
            "applicability_note",
        ):
            field_text(fields, field_name, xml_id)

    if set(packet_versions.values()) != set(version_source_refs):
        fail("review packet coverage does not match packaged rule versions")
    for packet_id, version_id in packet_versions.items():
        if packet_citation_sources[packet_id] != version_source_refs[version_id]:
            fail(
                f"{packet_id} does not cite every official source linked to "
                f"{version_id}"
            )

    model_content = (
        ADDON_ROOT / "models" / "rule_review_packet.py"
    ).read_text(encoding="utf-8")
    for contract in (
        'payload["cn_review_packet"]',
        "cn_review_packet_updated",
        "cn_rule_review_packet.updated",
        "action_print_cn_review_packet",
    ):
        if contract not in model_content:
            fail(f"professional review packet contract is missing {contract}")
    governance_content = (
        ADDON_ROOT / "models" / "rule_governance.py"
    ).read_text(encoding="utf-8")
    for contract in (
        "review_packet_required",
        "cn_professional_review_ready",
        "中国规则尚不能专业签核",
    ):
        if contract not in governance_content:
            fail(f"China professional sign-off gate is missing {contract}")
    report_content = (
        ADDON_ROOT / "reports" / "rule_review_packet_report.xml"
    ).read_text(encoding="utf-8")
    if "候选草案，不得用于对外合规结论" not in report_content:
        fail("professional review report must show its candidate boundary")


def validate_upgrade_migration(
    manifest: dict[str, object],
    source_ids: set[str],
    version_source_refs: dict[str, set[str]],
) -> None:
    current_migration_path = (
        ADDON_ROOT
        / "migrations"
        / str(manifest["version"])
        / "post-migration.py"
    )
    if not current_migration_path.is_file():
        fail("current version requires a post-migration script")
    current_content = current_migration_path.read_text(encoding="utf-8")
    if "update_country_pack_metadata" not in current_content:
        fail("current migration must refresh country pack metadata")

    link_migrations = []
    nature_backfill_migrations = []
    source_url_migrations = []
    for migration_path in sorted(
        (ADDON_ROOT / "migrations").glob("*/post-migration.py")
    ):
        content = migration_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(migration_path))
        assignments = literal_assignments(tree)
        links = assignments.get("RULE_SOURCE_LINKS")
        if isinstance(links, dict):
            link_migrations.append((content, links))
        if "backfill_cn_rule_natures" in content:
            nature_backfill_migrations.append(content)
        replacements = assignments.get("SOURCE_URL_REPLACEMENTS")
        if isinstance(replacements, dict):
            source_url_migrations.append((content, replacements))
    if len(nature_backfill_migrations) != 1:
        fail("exactly one migration must backfill governed China rule natures")
    if not link_migrations:
        fail("upgrade migrations must govern rule source links")
    normalized_links = {}
    for content, links in link_migrations:
        if "Command.link" not in content or "Command.set" in content:
            fail("upgrade migrations must preserve existing rule source links")
        for version_id, candidates in links.items():
            if version_id in normalized_links:
                fail(
                    "rule source links cannot be redefined by a later "
                    f"migration: {version_id}"
                )
            normalized_links[version_id] = set(candidates)
    if normalized_links != version_source_refs:
        fail("upgrade migration must cover every packaged rule draft")
    linked_sources = {
        source_id
        for candidates in normalized_links.values()
        for source_id in candidates
    }
    if linked_sources != source_ids:
        fail("upgrade migration must cover every official source candidate")
    if len(source_url_migrations) != 1:
        fail("exactly one migration must govern official source URL changes")
    source_content, replacements = source_url_migrations[0]
    normalized_replacements = {
        source_id: tuple(urls)
        for source_id, urls in replacements.items()
    }
    if normalized_replacements != EXPECTED_SOURCE_URL_REPLACEMENTS:
        fail("official source URL migration does not match the audited manifest")
    for guard in (
        'source.status != "draft"',
        "source.snapshot_attachment_id",
        "source.content_hash",
        "source.official_url != old_url",
        "authority_source.candidate_url_migrated",
    ):
        if guard not in source_content:
            fail(f"official source URL migration is missing guard: {guard}")


def validate_taxpayer_classification_security() -> None:
    access_path = ADDON_ROOT / "security" / "ir.model.access.csv"
    with access_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    model_rows = [
        row
        for row in rows
        if row["model_id:id"] == "model_sudo_cn_taxpayer_classification"
    ]
    expected_groups = {
        "sudo_global_finance.group_compliance_user",
        "sudo_global_finance.group_compliance_manager",
    }
    if {row["group_id:id"] for row in model_rows} != expected_groups:
        fail("China taxpayer classification ACL groups are incomplete")
    user_row = next(
        row
        for row in model_rows
        if row["group_id:id"].endswith("group_compliance_user")
    )
    if user_row["perm_unlink"] != "0":
        fail("compliance users must not delete taxpayer classifications")

    rule_path = ADDON_ROOT / "security" / "compliance_security.xml"
    root = ElementTree.parse(rule_path).getroot()
    company_rules = []
    for record in root.findall(".//record"):
        if record.attrib.get("model") != "ir.rule":
            continue
        fields = record_fields(record)
        model_field = fields.get("model_id")
        if (
            model_field is not None
            and model_field.attrib.get("ref")
            == "model_sudo_cn_taxpayer_classification"
        ):
            company_rules.append(fields)
    if len(company_rules) != 1:
        fail("taxpayer classifications require one company record rule")
    domain = field_text(company_rules[0], "domain_force", "company rule")
    if "company_ids" not in domain or "company_id" not in domain:
        fail("taxpayer classification rule must enforce allowed companies")


def validate_external_dataset_security() -> None:
    access_path = ADDON_ROOT / "security" / "ir.model.access.csv"
    with access_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    model_rows = [
        row
        for row in rows
        if row["model_id:id"] == "model_sudo_cn_external_dataset"
    ]
    expected_groups = {
        "sudo_global_finance.group_compliance_user",
        "sudo_global_finance.group_compliance_manager",
    }
    if {row["group_id:id"] for row in model_rows} != expected_groups:
        fail("China external dataset ACL groups are incomplete")
    user_row = next(
        row
        for row in model_rows
        if row["group_id:id"].endswith("group_compliance_user")
    )
    user_permissions = [
        user_row[key]
        for key in ("perm_read", "perm_write", "perm_create", "perm_unlink")
    ]
    if user_permissions != ["1", "0", "0", "0"]:
        fail("compliance users must have read-only external dataset access")
    manager_row = next(
        row
        for row in model_rows
        if row["group_id:id"].endswith("group_compliance_manager")
    )
    manager_permissions = [
        manager_row[key]
        for key in ("perm_read", "perm_write", "perm_create", "perm_unlink")
    ]
    if manager_permissions != ["1", "1", "1", "1"]:
        fail("compliance managers require controlled dataset maintenance access")

    rule_path = ADDON_ROOT / "security" / "compliance_security.xml"
    root = ElementTree.parse(rule_path).getroot()
    company_rules = []
    for record in root.findall(".//record"):
        if record.attrib.get("model") != "ir.rule":
            continue
        fields = record_fields(record)
        model_field = fields.get("model_id")
        if (
            model_field is not None
            and model_field.attrib.get("ref")
            == "model_sudo_cn_external_dataset"
        ):
            company_rules.append(fields)
    if len(company_rules) != 1:
        fail("external datasets require one company record rule")
    domain = field_text(company_rules[0], "domain_force", "company rule")
    if "company_ids" not in domain or "company_id" not in domain:
        fail("external dataset rule must enforce allowed companies")

    model_init = (ADDON_ROOT / "models" / "__init__.py").read_text(
        encoding="utf-8"
    )
    if "from . import external_dataset" not in model_init:
        fail("external dataset model must be imported")
    view_content = (
        ADDON_ROOT / "views" / "compliance_integration_views.xml"
    ).read_text(encoding="utf-8")
    for required_id in (
        "view_cn_external_dataset_list",
        "view_cn_external_dataset_form",
        "action_cn_external_datasets",
        "menu_cn_external_datasets",
    ):
        if f'id="{required_id}"' not in view_content:
            fail(f"external dataset UI is missing {required_id}")


def validate_invoice_normalization_security() -> None:
    access_path = ADDON_ROOT / "security" / "ir.model.access.csv"
    with access_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    model_names = {
        "model_sudo_cn_external_parse_run",
        "model_sudo_cn_einvoice_document",
        "model_sudo_cn_einvoice_accounting_document",
        "model_sudo_cn_einvoice_accounting_entry",
    }
    expected_groups = {
        "sudo_global_finance.group_compliance_user",
        "sudo_global_finance.group_compliance_manager",
    }
    for model_name in model_names:
        model_rows = [row for row in rows if row["model_id:id"] == model_name]
        if {row["group_id:id"] for row in model_rows} != expected_groups:
            fail(f"normalized invoice ACL groups are incomplete: {model_name}")
        user_row = next(
            row
            for row in model_rows
            if row["group_id:id"].endswith("group_compliance_user")
        )
        permissions = [
            user_row[key]
            for key in (
                "perm_read",
                "perm_write",
                "perm_create",
                "perm_unlink",
            )
        ]
        if permissions != ["1", "0", "0", "0"]:
            fail(f"normalized invoice users must be read-only: {model_name}")
        manager_row = next(
            row
            for row in model_rows
            if row["group_id:id"].endswith("group_compliance_manager")
        )
        if manager_row["perm_unlink"] != "0":
            fail(f"normalized invoice records must not be deleted: {model_name}")

    rule_path = ADDON_ROOT / "security" / "compliance_security.xml"
    root = ElementTree.parse(rule_path).getroot()
    ruled_models = []
    for record in root.findall(".//record"):
        if record.attrib.get("model") != "ir.rule":
            continue
        fields = record_fields(record)
        model_field = fields.get("model_id")
        model_ref = model_field.attrib.get("ref") if model_field is not None else ""
        if model_ref not in model_names:
            continue
        domain = field_text(fields, "domain_force", model_ref)
        if "company_ids" not in domain or "company_id" not in domain:
            fail(f"normalized invoice rule lacks company isolation: {model_ref}")
        ruled_models.append(model_ref)
    if set(ruled_models) != model_names:
        fail("every normalized invoice model requires one company record rule")

    model_init = (ADDON_ROOT / "models" / "__init__.py").read_text(
        encoding="utf-8"
    )
    if "from . import invoice_normalization" not in model_init:
        fail("invoice normalization models must be imported")
    view_path = ADDON_ROOT / "views" / "invoice_normalization_views.xml"
    if not view_path.is_file():
        fail("invoice normalization UI file is missing")
    view_content = view_path.read_text(encoding="utf-8")
    for required_id in (
        "view_cn_external_parse_run_list",
        "view_cn_external_parse_run_form",
        "view_cn_einvoice_document_list",
        "view_cn_einvoice_document_form",
        "action_cn_external_parse_runs",
        "action_cn_einvoice_documents",
        "menu_cn_einvoice_documents",
    ):
        if f'id="{required_id}"' not in view_content:
            fail(f"invoice normalization UI is missing {required_id}")


def validate_invoice_reconciliation() -> None:
    manifest = ast.literal_eval(
        (ADDON_ROOT / "__manifest__.py").read_text(encoding="utf-8")
    )
    required_data_files = {
        "data/invoice_reconciliation_cron.xml",
        "views/invoice_reconciliation_views.xml",
    }
    if not required_data_files.issubset(manifest.get("data", [])):
        fail("invoice reconciliation data files must be loaded by the manifest")

    model_init = (ADDON_ROOT / "models" / "__init__.py").read_text(
        encoding="utf-8"
    )
    if "from . import invoice_reconciliation" not in model_init:
        fail("invoice reconciliation models must be imported")

    model_path = ADDON_ROOT / "models" / "invoice_reconciliation.py"
    if not model_path.is_file():
        fail("invoice reconciliation model is missing")
    model_content = model_path.read_text(encoding="utf-8")
    for required in (
        "RECONCILIATION_ENGINE_VERSION",
        "_LEDGER_MOVE_SNAPSHOT_FIELDS",
        "prefetch_fields=False",
        "_checksum_list_item",
        "_ledger_line_summaries",
        "models.UniqueIndex",
        "FOR UPDATE SKIP LOCKED",
        "source_snapshot_checksum",
        "ledger_snapshot_checksum",
        "result_checksum",
        "move_snapshot_checksum",
        "ACCOUNTING_ENTITY_MISMATCH",
        "DUPLICATE_CURRENT_SOURCE_INVOICE",
        "SOURCE_AUTHENTICITY_FAILED",
        "SOURCE_AUTHENTICITY_NOT_CONFIRMED",
        "SOURCE_COVERAGE_NOT_FULL",
        "SOURCE_INTEGRITY_NOT_VERIFIED",
        "SOURCE_RECORD_COUNT_MISMATCH",
        "SOURCE_REVIEW_CONTROL_EXCEPTION",
        "source_availability_state",
        "account.group_account_user",
        "cn_einvoice_reconciliation.confirmed",
    ):
        if required not in model_content:
            fail(f"invoice reconciliation contract is missing {required}")

    access_path = ADDON_ROOT / "security" / "ir.model.access.csv"
    with access_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    governed_models = {
        "model_sudo_cn_einvoice_reconciliation_run",
        "model_sudo_cn_einvoice_reconciliation_case",
        "model_sudo_cn_einvoice_reconciliation_candidate",
    }
    expected_groups = {
        "sudo_global_finance.group_compliance_user",
        "sudo_global_finance.group_compliance_manager",
    }
    for model_name in governed_models:
        model_rows = [row for row in rows if row["model_id:id"] == model_name]
        if {row["group_id:id"] for row in model_rows} != expected_groups:
            fail(f"invoice reconciliation ACL groups are incomplete: {model_name}")
        user_row = next(
            row
            for row in model_rows
            if row["group_id:id"].endswith("group_compliance_user")
        )
        if [
            user_row[key]
            for key in ("perm_read", "perm_write", "perm_create", "perm_unlink")
        ] != ["1", "0", "0", "0"]:
            fail(f"reconciliation users must be read-only: {model_name}")
        manager_row = next(
            row
            for row in model_rows
            if row["group_id:id"].endswith("group_compliance_manager")
        )
        if manager_row["perm_unlink"] != "0":
            fail(f"reconciliation audit records must not be deleted: {model_name}")

    security_root = ElementTree.parse(
        ADDON_ROOT / "security" / "compliance_security.xml"
    ).getroot()
    ruled_models = set()
    for record in security_root.findall(".//record[@model='ir.rule']"):
        fields = record_fields(record)
        model_field = fields.get("model_id")
        model_ref = model_field.attrib.get("ref") if model_field is not None else ""
        if model_ref not in governed_models:
            continue
        domain = field_text(fields, "domain_force", record.attrib["id"])
        if "company_ids" not in domain or "company_id" not in domain:
            fail(f"reconciliation rule lacks company isolation: {model_ref}")
        ruled_models.add(model_ref)
    if ruled_models != governed_models:
        fail("every invoice reconciliation model requires a company record rule")

    cron_content = (
        ADDON_ROOT / "data" / "invoice_reconciliation_cron.xml"
    ).read_text(encoding="utf-8")
    if "_cron_process_runs(limit=1)" not in cron_content:
        fail("invoice reconciliation must use the bounded native Odoo queue")

    view_path = ADDON_ROOT / "views" / "invoice_reconciliation_views.xml"
    if not view_path.is_file():
        fail("invoice reconciliation UI is missing")
    view_content = view_path.read_text(encoding="utf-8")
    for required_id in (
        "view_cn_einvoice_reconciliation_case_list",
        "view_cn_einvoice_reconciliation_case_form",
        "view_cn_einvoice_reconciliation_run_list",
        "view_cn_einvoice_reconciliation_run_form",
        "view_cn_einvoice_reconciliation_wizard_form",
        "view_cn_einvoice_manual_match_wizard_form",
        "action_cn_einvoice_reconciliation_cases",
        "action_cn_einvoice_reconciliation_runs",
        "menu_cn_einvoice_reconciliation_cases",
        "menu_cn_einvoice_reconciliation_start",
    ):
        if f'id="{required_id}"' not in view_content:
            fail(f"invoice reconciliation UI is missing {required_id}")
    if "decision_integrity_state', '=', 'mismatch'" in view_content:
        fail("non-stored decision integrity must not be used as a search domain")

    test_path = ADDON_ROOT / "tests" / "test_invoice_reconciliation.py"
    if not test_path.is_file():
        fail("invoice reconciliation runtime tests are missing")
    test_tree = ast.parse(test_path.read_text(encoding="utf-8"))
    test_methods = sum(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
        for node in ast.walk(test_tree)
    )
    if test_methods < 10:
        fail("invoice reconciliation requires at least ten runtime tests")
    test_content = test_path.read_text(encoding="utf-8")
    if (
        "def test_move_index_streaming_checksum_matches_legacy_snapshot_list("
        not in test_content
    ):
        fail("invoice reconciliation requires snapshot checksum compatibility coverage")


def validate_tax_data_normalization() -> None:
    manifest = ast.literal_eval(
        (ADDON_ROOT / "__manifest__.py").read_text(encoding="utf-8")
    )
    view_relative_path = "views/tax_data_normalization_views.xml"
    if view_relative_path not in manifest.get("data", []):
        fail("tax data normalization views must be loaded by the manifest")
    if "views/cit_filing_views.xml" not in manifest.get("data", []):
        fail("CIT filing normalization views must be loaded by the manifest")

    model_init = (ADDON_ROOT / "models" / "__init__.py").read_text(
        encoding="utf-8"
    )
    if "from . import tax_data_normalization" not in model_init:
        fail("tax data normalization models must be imported")
    if "from . import cit_filing_normalization" not in model_init:
        fail("CIT filing normalization models must be imported")

    service_init = (ADDON_ROOT / "services" / "__init__.py").read_text(
        encoding="utf-8"
    )
    if "tax_data_contract" not in service_init:
        fail("tax data contract service must be imported")

    contract_path = ADDON_ROOT / "services" / "tax_data_contract.py"
    model_path = ADDON_ROOT / "models" / "tax_data_normalization.py"
    cit_model_path = ADDON_ROOT / "models" / "cit_filing_normalization.py"
    if (
        not contract_path.is_file()
        or not model_path.is_file()
        or not cit_model_path.is_file()
    ):
        fail("tax data normalization implementation is incomplete")
    contract_content = contract_path.read_text(encoding="utf-8")
    model_content = model_path.read_text(encoding="utf-8")
    cit_model_content = cit_model_path.read_text(encoding="utf-8")
    for required in (
        "sdoo.cn.tax-data.v1",
        "duplicate JSON key",
        "non-standard JSON constant",
        "contains unknown fields",
        "record_count does not match",
        "load_tax_data_contract",
    ):
        if required not in contract_content and required not in model_content:
            fail(f"tax data contract is missing {required}")
    for required in (
        "DECLARED_RECORD_COUNT_MISMATCH",
        "TAXPAYER_ENTITY_MISMATCH",
        "UNMASKED_PAYER_ACCOUNT",
        "has_tax_payable_amount",
        "has_amount",
        "contract_checksum",
        "output_checksum",
        "record_checksum",
        "_canonical_issues",
        "superseded",
        "cn_tax_data_import.started",
        "cn_tax_data_import.failed",
        "cn_tax_data_import.succeeded",
    ):
        if required not in model_content:
            fail(f"tax data normalization contract is missing {required}")
    for required in (
        '"cit_filing"',
        "_CIT_FILING_FIELDS",
        "_validate_cit_lines",
    ):
        if required not in contract_content:
            fail(f"CIT filing data contract is missing {required}")
    for required in (
        '_name = "sudo.cn.cit.filing.record"',
        '_name = "sudo.cn.cit.filing.line"',
        '"annual_reconciliation"',
        '"quarterly_prepayment"',
        "has_accounting_profit_amount",
        "has_taxable_income_amount",
        "has_payable_amount",
        "has_refundable_amount",
        "MISSING_CIT_TAXABLE_INCOME",
        "MISSING_CIT_SETTLEMENT_AMOUNT",
        "_TAX_NORMALIZED_RECORD_MARKER",
    ):
        if required not in cit_model_content:
            fail(f"CIT filing normalization contract is missing {required}")

    access_path = ADDON_ROOT / "security" / "ir.model.access.csv"
    with access_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    governed_models = {
        "model_sudo_cn_tax_data_parse_run",
        "model_sudo_cn_vat_filing_record",
        "model_sudo_cn_vat_filing_line",
        "model_sudo_cn_cit_filing_record",
        "model_sudo_cn_cit_filing_line",
        "model_sudo_cn_tax_payment_record",
    }
    expected_groups = {
        "sudo_global_finance.group_compliance_user",
        "sudo_global_finance.group_compliance_manager",
    }
    for model_name in governed_models:
        model_rows = [row for row in rows if row["model_id:id"] == model_name]
        if {row["group_id:id"] for row in model_rows} != expected_groups:
            fail(f"tax data ACL groups are incomplete: {model_name}")
        user_row = next(
            row
            for row in model_rows
            if row["group_id:id"].endswith("group_compliance_user")
        )
        if [
            user_row[key]
            for key in ("perm_read", "perm_write", "perm_create", "perm_unlink")
        ] != ["1", "0", "0", "0"]:
            fail(f"tax data users must be read-only: {model_name}")
        manager_row = next(
            row
            for row in model_rows
            if row["group_id:id"].endswith("group_compliance_manager")
        )
        if manager_row["perm_unlink"] != "0":
            fail(f"tax data audit records must not be deleted: {model_name}")

    security_root = ElementTree.parse(
        ADDON_ROOT / "security" / "compliance_security.xml"
    ).getroot()
    ruled_models = set()
    for record in security_root.findall(".//record[@model='ir.rule']"):
        fields = record_fields(record)
        model_field = fields.get("model_id")
        model_ref = model_field.attrib.get("ref") if model_field is not None else ""
        if model_ref not in governed_models:
            continue
        domain = field_text(fields, "domain_force", record.attrib["id"])
        if "company_ids" not in domain or "company_id" not in domain:
            fail(f"tax data rule lacks company isolation: {model_ref}")
        ruled_models.add(model_ref)
    if ruled_models != governed_models:
        fail("every governed tax data model requires a company record rule")

    view_path = ADDON_ROOT / view_relative_path
    cit_view_path = ADDON_ROOT / "views" / "cit_filing_views.xml"
    if not view_path.is_file() or not cit_view_path.is_file():
        fail("tax data normalization UI is missing")
    view_content = view_path.read_text(encoding="utf-8")
    for required_id in (
        "view_cn_tax_data_parse_run_form",
        "view_cn_vat_filing_record_list",
        "view_cn_vat_filing_record_form",
        "view_cn_tax_payment_record_list",
        "view_cn_tax_payment_record_form",
        "view_cn_tax_data_import_wizard_form",
        "action_cn_tax_data_parse_runs",
        "action_cn_vat_filing_records",
        "action_cn_tax_payment_records",
        "menu_cn_vat_filing_records",
        "menu_cn_tax_payment_records",
        "menu_cn_tax_data_parse_runs",
    ):
        if f'id="{required_id}"' not in view_content:
            fail(f"tax data normalization UI is missing {required_id}")
    cit_view_content = cit_view_path.read_text(encoding="utf-8")
    for required_id in (
        "view_cn_tax_data_parse_run_form_cit",
        "view_cn_cit_filing_record_search",
        "view_cn_cit_filing_record_list",
        "view_cn_cit_filing_record_form",
        "action_cn_cit_filing_records",
        "menu_cn_cit_filing_records",
        "view_cn_external_dataset_form_cit_results",
    ):
        if f'id="{required_id}"' not in cit_view_content:
            fail(f"CIT filing normalization UI is missing {required_id}")
    for boundary_text in (
        "不自动计算税率、优惠、应纳税额或法定截止日",
        "字段一致也不构成税务合规结论",
    ):
        if boundary_text not in cit_view_content:
            fail(f"CIT filing UI boundary is missing: {boundary_text}")

    pure_test_path = REPOSITORY_ROOT / "tools" / "test_tax_data_contract.py"
    runtime_test_path = ADDON_ROOT / "tests" / "test_tax_data_normalization.py"
    if not pure_test_path.is_file() or not runtime_test_path.is_file():
        fail("tax data normalization tests are incomplete")
    test_tree = ast.parse(runtime_test_path.read_text(encoding="utf-8"))
    test_methods = sum(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
        for node in ast.walk(test_tree)
    )
    if test_methods < 13:
        fail("tax data normalization requires at least thirteen runtime tests")


def validate_vat_period_reconciliation() -> None:
    manifest = ast.literal_eval(
        (ADDON_ROOT / "__manifest__.py").read_text(encoding="utf-8")
    )
    required_data_files = {
        "data/vat_period_reconciliation_cron.xml",
        "views/vat_period_reconciliation_views.xml",
    }
    if not required_data_files.issubset(manifest.get("data", [])):
        fail("VAT period reconciliation files must be loaded by the manifest")

    model_init = (ADDON_ROOT / "models" / "__init__.py").read_text(
        encoding="utf-8"
    )
    if "from . import vat_period_reconciliation" not in model_init:
        fail("VAT period reconciliation models must be imported")

    model_path = ADDON_ROOT / "models" / "vat_period_reconciliation.py"
    if not model_path.is_file():
        fail("VAT period reconciliation model is missing")
    model_content = model_path.read_text(encoding="utf-8")
    for required in (
        "VAT_PERIOD_ENGINE_VERSION",
        "models.UniqueIndex",
        "FOR UPDATE SKIP LOCKED",
        "amount_tax_signed",
        'groups="account.group_account_readonly"',
        "accounting_snapshot_checksum",
        "einvoice_snapshot_checksum",
        "filing_snapshot_checksum",
        "payment_snapshot_checksum",
        "result_checksum",
        "MISSING_COMPANY_TAX_ID",
        "ACCOUNTING_SCOPE_INVOICE_TAX_TOTALS_ONLY",
        "DUPLICATE_CURRENT_EINVOICE",
        "DUPLICATE_CURRENT_VAT_PAYMENT",
        "AMBIGUOUS_CURRENT_VAT_FILING",
        "SOURCE_COVERAGE_NOT_FULL",
        "LEDGER_EINVOICE_OUTPUT_DIFFERENCE",
        "LEDGER_EINVOICE_INPUT_DIFFERENCE",
        "LEDGER_FILING_OUTPUT_DIFFERENCE",
        "LEDGER_FILING_INPUT_DIFFERENCE",
        "FILING_PAYMENT_DIFFERENCE",
        "insufficient_data",
        "四方勾稽一致，不等于合规结论",
        "cn_vat_period_reconciliation.queued",
        "cn_vat_period_reconciliation.succeeded",
    ):
        if required not in model_content:
            fail(f"VAT period reconciliation contract is missing {required}")

    access_path = ADDON_ROOT / "security" / "ir.model.access.csv"
    with access_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    governed_models = {
        "model_sudo_cn_vat_period_reconciliation_run",
        "model_sudo_cn_vat_period_reconciliation_issue",
    }
    expected_groups = {
        "sudo_global_finance.group_compliance_user",
        "sudo_global_finance.group_compliance_manager",
    }
    for model_name in governed_models:
        model_rows = [row for row in rows if row["model_id:id"] == model_name]
        if {row["group_id:id"] for row in model_rows} != expected_groups:
            fail(f"VAT period ACL groups are incomplete: {model_name}")
        user_row = next(
            row
            for row in model_rows
            if row["group_id:id"].endswith("group_compliance_user")
        )
        if [
            user_row[key]
            for key in ("perm_read", "perm_write", "perm_create", "perm_unlink")
        ] != ["1", "0", "0", "0"]:
            fail(f"VAT period users must be read-only: {model_name}")
        manager_row = next(
            row
            for row in model_rows
            if row["group_id:id"].endswith("group_compliance_manager")
        )
        if manager_row["perm_unlink"] != "0":
            fail(f"VAT period audit records must not be deleted: {model_name}")

    security_root = ElementTree.parse(
        ADDON_ROOT / "security" / "compliance_security.xml"
    ).getroot()
    ruled_models = set()
    for record in security_root.findall(".//record[@model='ir.rule']"):
        fields = record_fields(record)
        model_field = fields.get("model_id")
        model_ref = model_field.attrib.get("ref") if model_field is not None else ""
        if model_ref not in governed_models:
            continue
        domain = field_text(fields, "domain_force", record.attrib["id"])
        if "company_ids" not in domain or "company_id" not in domain:
            fail(f"VAT period rule lacks company isolation: {model_ref}")
        ruled_models.add(model_ref)
    if ruled_models != governed_models:
        fail("every governed VAT period model requires a company record rule")

    cron_content = (
        ADDON_ROOT / "data" / "vat_period_reconciliation_cron.xml"
    ).read_text(encoding="utf-8")
    if "_cron_process_runs(limit=1)" not in cron_content:
        fail("VAT period reconciliation must use a bounded native Odoo queue")

    view_path = ADDON_ROOT / "views" / "vat_period_reconciliation_views.xml"
    if not view_path.is_file():
        fail("VAT period reconciliation UI is missing")
    view_content = view_path.read_text(encoding="utf-8")
    for required_id in (
        "view_cn_vat_period_reconciliation_run_list",
        "view_cn_vat_period_reconciliation_run_form",
        "view_cn_vat_period_reconciliation_issue_list",
        "view_cn_vat_period_reconciliation_issue_form",
        "view_cn_vat_period_reconciliation_wizard_form",
        "action_cn_vat_period_reconciliation_runs",
        "action_cn_vat_period_reconciliation_issues",
        "action_cn_vat_period_reconciliation_start",
        "menu_cn_vat_period_reconciliation_runs",
        "menu_cn_vat_period_reconciliation_start",
        "menu_cn_vat_period_reconciliation_issues",
    ):
        if f'id="{required_id}"' not in view_content:
            fail(f"VAT period reconciliation UI is missing {required_id}")
    for boundary_text in (
        "不等于税务合规结论",
        "不自动等同于税务风险",
        "不会把缺失解释为通过",
        "四方金额一致，但仍有需要复核的数据限制",
        "执行时点快照",
    ):
        if boundary_text not in view_content:
            fail(f"VAT period UI boundary is missing: {boundary_text}")

    test_path = ADDON_ROOT / "tests" / "test_vat_period_reconciliation.py"
    if not test_path.is_file():
        fail("VAT period reconciliation runtime tests are missing")
    test_tree = ast.parse(test_path.read_text(encoding="utf-8"))
    test_methods = sum(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
        for node in ast.walk(test_tree)
    )
    if test_methods < 15:
        fail("VAT period reconciliation requires at least fifteen runtime tests")


def validate_cit_period_reconciliation() -> None:
    manifest = ast.literal_eval(
        (ADDON_ROOT / "__manifest__.py").read_text(encoding="utf-8")
    )
    required_data_files = {
        "data/cit_period_reconciliation_cron.xml",
        "views/cit_accounting_scope_views.xml",
        "views/cit_period_reconciliation_views.xml",
    }
    if not required_data_files.issubset(manifest.get("data", [])):
        fail("CIT accounting scope and reconciliation files must be loaded")

    model_init = (ADDON_ROOT / "models" / "__init__.py").read_text(
        encoding="utf-8"
    )
    for module_name in ("cit_accounting_scope", "cit_period_reconciliation"):
        if f"from . import {module_name}" not in model_init:
            fail(f"CIT model must be imported: {module_name}")

    scope_path = ADDON_ROOT / "models" / "cit_accounting_scope.py"
    run_path = ADDON_ROOT / "models" / "cit_period_reconciliation.py"
    if not scope_path.is_file() or not run_path.is_file():
        fail("CIT accounting reconciliation implementation is incomplete")
    scope_content = scope_path.read_text(encoding="utf-8")
    run_content = run_path.read_text(encoding="utf-8")
    for required in (
        '_name = "sudo.cn.cit.accounting.scope"',
        '_name = "sudo.cn.cit.accounting.scope.line"',
        "_CIT_SCOPE_TRANSITION_MARKER",
        "_expected_accounts",
        '("active", "=", True)',
        "action_populate_from_chart",
        "action_verify",
        "verification_checksum",
        "checksum_mismatch",
        "同一档案在同一期间只能有一份已核验会计利润口径",
    ):
        if required not in scope_content:
            fail(f"CIT accounting scope contract is missing {required}")
    if '("deprecated", "=", False)' in scope_content:
        fail("CIT accounting scope must use the Odoo 19 active account field")

    for required in (
        "CIT_PERIOD_ENGINE_VERSION",
        "FOR UPDATE SKIP LOCKED",
        "MAX_ACCOUNTING_LINES",
        "MAX_FILING_RECORDS",
        "MAX_PAYMENT_RECORDS",
        "_CIT_PERIOD_TRANSITION_MARKER",
        "accounting_scope_snapshot_checksum",
        "accounting_snapshot_checksum",
        "filing_snapshot_checksum",
        "payment_snapshot_checksum",
        "result_checksum",
        "result_integrity_state",
        "_current_result_checksum",
        "NO_VERIFIED_CIT_ACCOUNTING_SCOPE",
        "NO_CURRENT_CIT_FILING",
        "NO_CURRENT_CIT_PAYMENT_DATASET",
        "CIT_LEDGER_FILING_PROFIT_DIFFERENCE",
        "CIT_FILING_TAXABLE_ARITHMETIC_DIFFERENCE",
        "CIT_PAYABLE_PAYMENT_DIFFERENCE",
        "CIT_REFUNDABLE_REFUND_DIFFERENCE",
        "insufficient_data",
        "受控口径算术一致，不等于合规结论",
        "cn_cit_period_reconciliation.queued",
        "cn_cit_period_reconciliation.succeeded",
    ):
        if required not in run_content:
            fail(f"CIT period reconciliation contract is missing {required}")

    access_path = ADDON_ROOT / "security" / "ir.model.access.csv"
    with access_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    governed_models = {
        "model_sudo_cn_cit_accounting_scope",
        "model_sudo_cn_cit_accounting_scope_line",
        "model_sudo_cn_cit_period_reconciliation_run",
        "model_sudo_cn_cit_period_reconciliation_issue",
    }
    expected_groups = {
        "sudo_global_finance.group_compliance_user",
        "sudo_global_finance.group_compliance_manager",
    }
    for model_name in governed_models:
        model_rows = [row for row in rows if row["model_id:id"] == model_name]
        if {row["group_id:id"] for row in model_rows} != expected_groups:
            fail(f"CIT reconciliation ACL groups are incomplete: {model_name}")
        user_row = next(
            row
            for row in model_rows
            if row["group_id:id"].endswith("group_compliance_user")
        )
        if [
            user_row[key]
            for key in ("perm_read", "perm_write", "perm_create", "perm_unlink")
        ] != ["1", "0", "0", "0"]:
            fail(f"CIT reconciliation users must be read-only: {model_name}")
        if model_name.endswith(("reconciliation_run", "reconciliation_issue")):
            manager_row = next(
                row
                for row in model_rows
                if row["group_id:id"].endswith("group_compliance_manager")
            )
            if manager_row["perm_unlink"] != "0":
                fail(f"CIT reconciliation snapshots must not be deleted: {model_name}")

    security_root = ElementTree.parse(
        ADDON_ROOT / "security" / "compliance_security.xml"
    ).getroot()
    ruled_models = set()
    for record in security_root.findall(".//record[@model='ir.rule']"):
        fields = record_fields(record)
        model_field = fields.get("model_id")
        model_ref = model_field.attrib.get("ref") if model_field is not None else ""
        if model_ref not in governed_models:
            continue
        domain = field_text(fields, "domain_force", record.attrib["id"])
        if "company_ids" not in domain or "company_id" not in domain:
            fail(f"CIT reconciliation rule lacks company isolation: {model_ref}")
        ruled_models.add(model_ref)
    if ruled_models != governed_models:
        fail("every governed CIT reconciliation model requires a company rule")

    cron_content = (
        ADDON_ROOT / "data" / "cit_period_reconciliation_cron.xml"
    ).read_text(encoding="utf-8")
    if "_cron_process_runs(limit=1)" not in cron_content:
        fail("CIT reconciliation must use a bounded native Odoo queue")

    facts = (ADDON_ROOT / "data" / "compliance_fact_data.xml").read_text(
        encoding="utf-8"
    )
    provider = (ADDON_ROOT / "models" / "compliance_engine.py").read_text(
        encoding="utf-8"
    )
    for fact_key in (
        "cn.reconciliation.cit.conclusion_state",
        "cn.reconciliation.cit.blocking_issue_count",
        "cn.reconciliation.cit.difference_issue_count",
        "cn.reconciliation.cit.warning_issue_count",
        "cn.reconciliation.cit.detail",
    ):
        if fact_key not in facts or fact_key not in provider:
            fail(f"CIT reconciliation fact bridge is missing {fact_key}")
    if "sdoo.cn.reconciliation.cit-period.fact.v1" not in provider:
        fail("CIT reconciliation fact snapshot schema is missing")
    if "run._current_result_checksum()" not in provider:
        fail("CIT reconciliation facts must verify the complete result checksum")

    scope_view_path = ADDON_ROOT / "views" / "cit_accounting_scope_views.xml"
    run_view_path = ADDON_ROOT / "views" / "cit_period_reconciliation_views.xml"
    scope_view = scope_view_path.read_text(encoding="utf-8")
    run_view = run_view_path.read_text(encoding="utf-8")
    for required_id in (
        "view_cn_cit_accounting_scope_list",
        "view_cn_cit_accounting_scope_form",
        "action_cn_cit_accounting_scopes",
        "menu_cn_cit_accounting_scopes",
    ):
        if f'id="{required_id}"' not in scope_view:
            fail(f"CIT accounting scope UI is missing {required_id}")
    if "('integrity_state', '=', 'checksum_mismatch')" in scope_view:
        fail("non-stored CIT scope integrity must not be used as a search domain")
    for required_id in (
        "view_cn_cit_period_reconciliation_run_list",
        "view_cn_cit_period_reconciliation_run_form",
        "view_cn_cit_period_reconciliation_issue_list",
        "view_cn_cit_period_reconciliation_issue_form",
        "view_cn_cit_period_reconciliation_wizard_form",
        "action_cn_cit_period_reconciliation_runs",
        "action_cn_cit_period_reconciliation_issues",
        "action_cn_cit_period_reconciliation_start",
        "menu_cn_cit_period_reconciliation_runs",
        "menu_cn_cit_period_reconciliation_start",
        "menu_cn_cit_period_reconciliation_issues",
    ):
        if f'id="{required_id}"' not in run_view:
            fail(f"CIT period reconciliation UI is missing {required_id}")
    for boundary_text in (
        "系统没有把缺少会计口径、申报、缴退税或来源控制解释为通过",
        "差异不自动等同于少缴、多缴、违法",
        "当前受控口径算术一致",
        "不证明纳税调整、税率、优惠、扣除、亏损弥补或申报处理合法",
        "本页保存执行时点快照",
        "结果完整性异常",
        "系统不会自动猜测税种编码",
    ):
        if boundary_text not in run_view:
            fail(f"CIT reconciliation UI boundary is missing: {boundary_text}")

    test_path = ADDON_ROOT / "tests" / "test_cit_period_reconciliation.py"
    if not test_path.is_file():
        fail("CIT reconciliation runtime tests are missing")
    test_content = test_path.read_text(encoding="utf-8")
    test_tree = ast.parse(test_content)
    test_methods = sum(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
        for node in ast.walk(test_tree)
    )
    if test_methods < 10:
        fail("CIT reconciliation requires at least ten runtime tests")
    for test_name in (
        "test_aligned_run_preserves_separate_book_return_payment_facts",
        "test_missing_external_sources_is_insufficient_not_aligned",
        "test_differences_are_review_items_not_blocking_tax_conclusions",
        "test_missing_profit_chain_field_is_not_treated_as_zero",
        "test_payment_total_without_principal_blocks_payable_comparison",
        "test_tampered_verified_scope_blocks_accounting_conclusion",
        "test_fact_provider_exposes_exact_period_auditable_snapshot",
        "test_company_rule_hides_other_company_scope",
        "test_run_and_issue_cannot_be_created_or_changed_manually",
    ):
        if f"def {test_name}(" not in test_content:
            fail(f"CIT reconciliation runtime coverage is missing {test_name}")


def validate_filing_payment_archive() -> None:
    manifest = ast.literal_eval(
        (ADDON_ROOT / "__manifest__.py").read_text(encoding="utf-8")
    )
    if "views/filing_archive_views.xml" not in manifest.get("data", []):
        fail("controlled filing archive views must be loaded by the manifest")

    model_init = (ADDON_ROOT / "models" / "__init__.py").read_text(
        encoding="utf-8"
    )
    if "from . import filing_archive" not in model_init:
        fail("controlled filing archive models must be imported")
    if model_init.index("from . import filing_archive") < model_init.index(
        "from . import vat_period_reconciliation"
    ):
        fail("filing archive extensions must load after VAT reconciliation")

    model_path = ADDON_ROOT / "models" / "filing_archive.py"
    view_path = ADDON_ROOT / "views" / "filing_archive_views.xml"
    if not model_path.is_file() or not view_path.is_file():
        fail("controlled filing archive implementation is incomplete")
    model_content = model_path.read_text(encoding="utf-8")
    for required in (
        '_inherit = "sudo.compliance.filing"',
        '_inherit = "sudo.cn.vat.period.reconciliation.run"',
        '"sdoo.cn.vat-filing-archive.v1"',
        '"sdoo.cn.vat-payment-archive.v1"',
        "_CN_ARCHIVE_TRANSITION_MARKER",
        "_CN_ARCHIVE_LINK_MARKER",
        "_cn_validate_obligation",
        "_cn_verified_evidence",
        "current_document_checksum",
        "source_superseded",
        "filing_payment_difference",
        "filing_receipt",
        "payment_proof",
        "cn.vat_filing_archive.sealed",
        "cn.vat_payment_archive.sealed",
        "action_open_cn_filing_archive",
        "action_open_cn_vat_reconciliation",
    ):
        if required not in model_content:
            fail(f"controlled filing archive contract is missing {required}")
    if "default_due_date" in model_content:
        fail("controlled filing archive must not infer a legal filing deadline")

    view_content = view_path.read_text(encoding="utf-8")
    for required_id in (
        "view_compliance_filing_form_cn_vat_archive",
        "view_compliance_filing_list_cn_vat_archive",
        "view_compliance_filing_search_cn_vat_archive",
        "view_cn_vat_period_reconciliation_run_form_filing_archive",
    ):
        if f'id="{required_id}"' not in view_content:
            fail(f"controlled filing archive UI is missing {required_id}")
    for boundary_text in (
        "系统不会根据期间自动猜测",
        "已验证的回执或缴款证据",
        "不同法律含义的交易",
        "来源批次已经被新结果替代",
    ):
        if boundary_text not in view_content:
            fail(f"controlled filing archive UI boundary is missing: {boundary_text}")

    test_content = (
        ADDON_ROOT / "tests" / "test_vat_period_reconciliation.py"
    ).read_text(encoding="utf-8")
    for test_name in (
        "test_filing_archive_action_does_not_infer_legal_deadline",
        "test_filing_and_payment_archive_seal_full_controlled_chain",
        "test_filing_archive_requires_verified_formal_receipt",
        "test_filing_archive_requires_applicable_vat_obligation",
        "test_filing_archive_rejects_payment_difference",
        "test_filing_archive_detects_checksum_tampering",
        "test_filing_archive_preserves_superseded_historical_snapshot",
        "test_filing_archive_rejects_cross_company_reconciliation",
    ):
        if f"def {test_name}(" not in test_content:
            fail(f"controlled filing archive test is missing {test_name}")


def validate_tax_impact_review() -> None:
    manifest = ast.literal_eval(
        (ADDON_ROOT / "__manifest__.py").read_text(encoding="utf-8")
    )
    required_data_files = {
        "reports/vat_adjustment_report.xml",
        "views/tax_impact_review_views.xml",
    }
    if not required_data_files.issubset(manifest.get("data", [])):
        fail("tax impact review files must be loaded by the manifest")

    model_init = (ADDON_ROOT / "models" / "__init__.py").read_text(
        encoding="utf-8"
    )
    if "from . import tax_impact_review" not in model_init:
        fail("tax impact review models must be imported")
    if model_init.index("from . import tax_impact_review") < model_init.index(
        "from . import vat_period_reconciliation"
    ):
        fail("tax impact extensions must load after VAT reconciliation models")

    model_path = ADDON_ROOT / "models" / "tax_impact_review.py"
    if not model_path.is_file():
        fail("tax impact review model is missing")
    model_content = model_path.read_text(encoding="utf-8")
    for required in (
        '_name = "sudo.cn.tax.impact.case"',
        '"sdoo.cn.tax-impact-review.v1"',
        '("draft", "分析中")',
        '("submitted", "待独立复核")',
        '("reviewed", "已复核")',
        "_check_unique_source_ownership",
        "ORDER BY id FOR UPDATE",
        "submission_checksum",
        "review_checksum",
        "checksum_mismatch",
        "cn_tax_impact_case.submitted",
        "cn_tax_impact_case.reviewed",
        "reviewed_underpayment_amount",
        "reviewed_overpayment_amount",
        "reviewed_timing_amount",
        "tax_impact_integrity_issue_count",
        "action_print_vat_adjustment_report",
    ):
        if required not in model_content:
            fail(f"tax impact review contract is missing {required}")
    if "net_tax_impact_amount" in model_content:
        fail("tax impact review must not publish a netted tax impact amount")

    access_path = ADDON_ROOT / "security" / "ir.model.access.csv"
    with access_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    model_rows = [
        row
        for row in rows
        if row["model_id:id"] == "model_sudo_cn_tax_impact_case"
    ]
    if {
        row["group_id:id"] for row in model_rows
    } != {
        "sudo_global_finance.group_compliance_user",
        "sudo_global_finance.group_compliance_manager",
    }:
        fail("tax impact review ACL groups are incomplete")
    user_row = next(
        row
        for row in model_rows
        if row["group_id:id"].endswith("group_compliance_user")
    )
    if [
        user_row[key]
        for key in ("perm_read", "perm_write", "perm_create", "perm_unlink")
    ] != ["1", "0", "0", "0"]:
        fail("ordinary compliance users must have read-only tax impact access")

    security = (
        ADDON_ROOT / "security" / "compliance_security.xml"
    ).read_text(encoding="utf-8")
    if (
        'ref="model_sudo_cn_tax_impact_case"' not in security
        or "[('company_id', 'in', company_ids)]" not in security
    ):
        fail("tax impact review requires an allowed-company record rule")

    view_content = (
        ADDON_ROOT / "views" / "tax_impact_review_views.xml"
    ).read_text(encoding="utf-8")
    for required in (
        'id="view_cn_tax_impact_case_list"',
        'id="view_cn_tax_impact_case_form"',
        'id="action_cn_tax_impact_cases"',
        'id="menu_cn_tax_impact_cases"',
        "系统不会直接把原始差异相加为少缴税金额",
        "少缴、多缴和期间错配影响分别列示，不进行净额抵销",
    ):
        if required not in view_content:
            fail(f"tax impact review UI is missing {required}")
    if 'name="impact_amount" sum=' in view_content:
        fail("tax impact list views must not aggregate mixed-direction amounts")

    report_content = (
        ADDON_ROOT / "reports" / "vat_adjustment_report.xml"
    ).read_text(encoding="utf-8")
    for required in (
        '<field name="binding_model_id" eval="False"/>',
        "原始勾稽差异可能相互重叠，不得直接相加",
        "已复核潜在少缴税影响",
        "已复核潜在多缴税影响",
        "已复核期间错配影响",
        "不计算净额",
        "不是纳税申报表或税务机关结论",
    ):
        if required not in report_content:
            fail(f"VAT adjustment report boundary is missing {required}")

    test_content = (
        ADDON_ROOT / "tests" / "test_vat_period_reconciliation.py"
    ).read_text(encoding="utf-8")
    for test_name in (
        "test_tax_impact_case_requires_sources_evidence_and_review",
        "test_tax_impact_totals_are_reviewed_and_separate_not_net",
        "test_unquantifiable_case_is_counted_without_amount",
        "test_tax_impact_source_cannot_be_double_counted",
        "test_tax_impact_same_person_review_requires_exception",
        "test_tax_impact_submission_detects_evidence_tampering",
        "test_tax_impact_period_and_company_sources_are_controlled",
        "test_vat_adjustment_report_preserves_conclusion_boundary",
    ):
        if f"def {test_name}(" not in test_content:
            fail(f"tax impact runtime coverage is missing {test_name}")


def validate_formal_compliance_report() -> None:
    manifest = ast.literal_eval(
        (ADDON_ROOT / "__manifest__.py").read_text(encoding="utf-8")
    )
    required_data_files = {
        "data/compliance_report_sequence.xml",
        "reports/compliance_report.xml",
        "views/compliance_report_views.xml",
    }
    if not required_data_files.issubset(manifest.get("data", [])):
        fail("formal compliance report files must be loaded by the manifest")

    model_init = (ADDON_ROOT / "models" / "__init__.py").read_text(
        encoding="utf-8"
    )
    if "from . import compliance_report" not in model_init:
        fail("formal compliance report model must be imported")
    if model_init.index("from . import compliance_report") < model_init.index(
        "from . import tax_impact_review"
    ):
        fail("formal report must load after tax impact review extensions")

    model_content = (
        ADDON_ROOT / "models" / "compliance_report.py"
    ).read_text(encoding="utf-8")
    for required in (
        '_name = "sudo.cn.compliance.report"',
        '"sdoo.cn.compliance-report.v1"',
        '"sdoo.cn.compliance-report-approval.v1"',
        "approval_integrity_state",
        '"submitted", "待独立批准"',
        '"issued", "已签发"',
        '"superseded", "已被替代"',
        '"withdrawn", "已撤回"',
        "snapshot_checksum",
        "approval_checksum",
        "issued_pdf_sha256",
        "_lock_for_transition",
        "FOR UPDATE",
        "cn_compliance_report.submitted",
        "cn_compliance_report.issued",
        "cn_compliance_report.withdrawn",
        "group_cn_report_approver",
        "action_download_issued_pdf",
    ):
        if required not in model_content:
            fail(f"formal compliance report contract is missing {required}")
    if "net_tax_impact" in model_content:
        fail("formal report must not publish a netted tax impact amount")

    with (ADDON_ROOT / "security" / "ir.model.access.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    model_rows = [
        row
        for row in rows
        if row["model_id:id"] == "model_sudo_cn_compliance_report"
    ]
    expected_groups = {
        "sudo_global_finance.group_compliance_user",
        "sudo_global_finance.group_compliance_manager",
        "sudo_country_pack_cn.group_cn_report_approver",
    }
    if {row["group_id:id"] for row in model_rows} != expected_groups:
        fail("formal compliance report ACL groups are incomplete")
    user_row = next(
        row
        for row in model_rows
        if row["group_id:id"].endswith("group_compliance_user")
    )
    if [
        user_row[key]
        for key in ("perm_read", "perm_write", "perm_create", "perm_unlink")
    ] != ["1", "0", "0", "0"]:
        fail("ordinary compliance users must have read-only formal report access")

    security = (
        ADDON_ROOT / "security" / "compliance_security.xml"
    ).read_text(encoding="utf-8")
    for required in (
        'id="group_cn_report_approver"',
        'ref="model_sudo_cn_compliance_report"',
        "[('company_id', 'in', company_ids)]",
    ):
        if required not in security:
            fail(f"formal report security is missing {required}")

    view_content = (
        ADDON_ROOT / "views" / "compliance_report_views.xml"
    ).read_text(encoding="utf-8")
    for required in (
        'id="view_cn_formal_compliance_report_list"',
        'id="view_cn_formal_compliance_report_form"',
        'id="action_cn_formal_compliance_reports"',
        'id="menu_cn_formal_compliance_reports"',
        "提交独立批准",
        "批准并签发",
        "下载已签发 PDF",
        "源资料已变化",
        "PDF 完整性异常",
    ):
        if required not in view_content:
            fail(f"formal compliance report UI is missing {required}")

    report_content = (
        ADDON_ROOT / "reports" / "compliance_report.xml"
    ).read_text(encoding="utf-8")
    for required in (
        '<field name="binding_model_id" eval="False"/>',
        "不是纳税申报表、税务鉴证报告、法律意见、审计意见或税务机关认定",
        "潜在少缴、潜在多缴和期间错配影响分别列示",
        "不计算净额",
        "AI 分析仅为辅助材料",
        "内容快照 SHA-256",
        "批准 SHA-256",
    ):
        if required not in report_content:
            fail(f"formal compliance report boundary is missing {required}")

    test_content = (
        ADDON_ROOT / "tests" / "test_compliance_report.py"
    ).read_text(encoding="utf-8")
    for test_name in (
        "test_submission_freezes_explainable_snapshot_and_audit",
        "test_unreviewed_or_unsigned_findings_block_formal_submission",
        "test_source_change_after_submission_requires_return_and_resubmit",
        "test_independent_approver_issues_immutable_pdf",
        "test_pdf_tampering_is_detected_and_download_blocked",
        "test_approval_tampering_is_detected_and_download_blocked",
        "test_open_verification_task_prevents_clear_conclusion",
        "test_same_person_approval_requires_recorded_exception",
        "test_new_issue_supersedes_previous_report_without_rewriting_pdf",
        "test_withdrawal_preserves_artifact_and_audit_history",
        "test_read_only_user_cannot_prepare_or_mutate_report",
        "test_report_is_company_isolated_and_reviewer_must_have_company",
        "test_only_designated_approver_can_return_or_issue",
        "test_report_html_preserves_boundary_and_non_net_tax_impact",
    ):
        if f"def {test_name}(" not in test_content:
            fail(f"formal report runtime coverage is missing {test_name}")


def validate_xbrl_parser_addon() -> None:
    manifest_path = XBRL_ADDON_ROOT / "__manifest__.py"
    if not manifest_path.is_file():
        fail("optional XBRL parser addon is missing")
    manifest = ast.literal_eval(manifest_path.read_text(encoding="utf-8"))
    if not str(manifest.get("version", "")).startswith("19.0."):
        fail("XBRL parser manifest must target Odoo 19")
    if manifest.get("depends") != ["sudo_country_pack_cn"]:
        fail("XBRL parser must remain an optional child of the China pack")
    if manifest.get("application") or not manifest.get("installable"):
        fail("XBRL parser must be installable without creating an app root")
    external = manifest.get("external_dependencies", {})
    if external.get("python") != ["arelle"]:
        fail("XBRL parser must declare the Arelle Python dependency")
    for relative_path in manifest.get("data", []):
        if not (XBRL_ADDON_ROOT / relative_path).is_file():
            fail(f"XBRL manifest data file is missing: {relative_path}")

    requirements = (
        XBRL_ADDON_ROOT / "requirements.txt"
    ).read_text(encoding="utf-8").strip()
    if requirements != "arelle-release==2.42.1":
        fail("Arelle deployment dependency must remain exactly pinned")

    job_model = (XBRL_ADDON_ROOT / "models" / "xbrl_job.py").read_text(
        encoding="utf-8"
    )
    if (
        f'PARSER_ADDON_VERSION = "{manifest["version"]}"'
        not in job_model
    ):
        fail("XBRL parser runtime version must match its manifest")

    worker = (XBRL_ADDON_ROOT / "parser" / "worker.py").read_text(
        encoding="utf-8"
    )
    for required in (
        'internetConnectivity="offline"',
        "TemporaryDirectory",
        "timeout_seconds",
        "SUPPORTED_ARELLE_VERSION",
        "safe_extract_zip",
        "expected_source_sha256",
        "expected_taxonomy_sha256",
        "taxonomy_compatibility_profile",
        "expected_compatibility_patch_count",
        "working_taxonomy_checksum",
    ):
        if required not in worker and required not in job_model:
            fail(f"XBRL isolation contract is missing {required}")
    for required in (
        "_patch_role_uri_whitespace",
        "UNSAFE_ROLE_URI_COMPATIBILITY_ENCODING",
        "path.write_bytes(patched_content)",
    ):
        if required not in worker:
            fail(f"deterministic taxonomy compatibility is missing {required}")
    compatibility_block = worker.split(
        "def _apply_taxonomy_compatibility", 1
    )[1].split("def _prepare_taxonomy", 1)[0]
    if "tree.write(" in compatibility_block:
        fail("taxonomy compatibility must not reserialize complete XSD files")

    contract = (XBRL_ADDON_ROOT / "parser" / "contract.py").read_text(
        encoding="utf-8"
    )
    for required in (
        "UNSAFE_ARCHIVE_PATH",
        "ARCHIVE_SYMLINK",
        "ENCRYPTED_ARCHIVE",
        "INVALID_COMPRESSION_RATIO",
        "TAXONOMY_NAMESPACE_MISMATCH",
        "XML_DTD_FORBIDDEN",
        "role_uri_whitespace_count",
    ):
        if required not in contract:
            fail(f"XBRL archive security contract is missing {required}")

    hooks = (XBRL_ADDON_ROOT / "hooks.py").read_text(encoding="utf-8")
    if 'features["einvoice_xbrl_parser"]' not in hooks:
        fail("XBRL addon must update the runtime parser capability")
    if "post_init_hook" not in hooks or "uninstall_hook" not in hooks:
        fail("XBRL capability must be enabled and disabled with module lifecycle")

    access_path = XBRL_ADDON_ROOT / "security" / "ir.model.access.csv"
    with access_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    job_user = next(
        row
        for row in rows
        if row["id"] == "access_cn_einvoice_xbrl_job_user"
    )
    if [
        job_user[key]
        for key in ("perm_read", "perm_write", "perm_create", "perm_unlink")
    ] != ["1", "0", "0", "0"]:
        fail("ordinary compliance users must have read-only XBRL job access")
    taxonomy_user = next(
        row
        for row in rows
        if row["id"] == "access_cn_xbrl_taxonomy_user"
    )
    if taxonomy_user["perm_write"] != "0" or taxonomy_user["perm_create"] != "0":
        fail("ordinary users must not maintain taxonomy bundles")

    security = ElementTree.parse(
        XBRL_ADDON_ROOT / "security" / "compliance_security.xml"
    ).getroot()
    rules = security.findall(".//record[@model='ir.rule']")
    if len(rules) != 1:
        fail("XBRL jobs require exactly one company isolation rule")
    fields = record_fields(rules[0])
    if "company_ids" not in field_text(fields, "domain_force", rules[0].attrib["id"]):
        fail("XBRL job record rule must enforce allowed companies")

    cron = (
        XBRL_ADDON_ROOT / "data" / "ir_cron_data.xml"
    ).read_text(encoding="utf-8")
    if "_cron_process_jobs(limit=1)" not in cron:
        fail("XBRL parser must use the bounded native Odoo job queue")
    if "FOR UPDATE SKIP LOCKED" not in job_model:
        fail("XBRL queue must prevent concurrent duplicate processing")
    for required in (
        "taxonomy_compatibility_profile",
        "taxonomy_patch_count",
        "working_taxonomy_checksum",
    ):
        if required not in job_model:
            fail(f"XBRL job audit contract is missing {required}")

    taxonomy_model = (
        XBRL_ADDON_ROOT / "models" / "taxonomy_bundle.py"
    ).read_text(encoding="utf-8")
    for required in (
        "trim_role_uri_whitespace_v1",
        "compatibility_reason",
        "compatibility_patch_count",
    ):
        if required not in taxonomy_model:
            fail(f"taxonomy compatibility governance is missing {required}")

    test_methods = 0
    for test_path in (XBRL_ADDON_ROOT / "tests").glob("test_*.py"):
        tree = ast.parse(test_path.read_text(encoding="utf-8"))
        test_methods += sum(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
            for node in ast.walk(tree)
        )
    if test_methods < 12:
        fail("XBRL parser addon requires at least twelve runtime tests")

    job_tests = (
        XBRL_ADDON_ROOT / "tests" / "test_xbrl_job.py"
    ).read_text(encoding="utf-8")
    for test_name in (
        "test_worker_environment_drops_uncontrolled_variables",
        "test_cron_claims_and_processes_queued_job",
    ):
        if f"def {test_name}(" not in job_tests:
            fail(f"XBRL runtime safety coverage is missing {test_name}")

    compatibility_tests = (
        REPOSITORY_ROOT / "tools" / "test_xbrl_worker_compatibility.py"
    ).read_text(encoding="utf-8")
    for test_name in (
        "test_controlled_profile_trims_only_working_copy_role_uri",
        "test_entity_encoded_whitespace_is_rejected_without_rewriting",
        "test_comment_cannot_mask_unsafe_semantic_whitespace",
    ):
        if f"def {test_name}(" not in compatibility_tests:
            fail(f"XBRL deterministic patch coverage is missing {test_name}")


def main() -> int:
    validate_text_and_syntax()
    manifest = validate_manifest()
    validate_hooks(manifest)
    validate_country_pack_metadata(manifest)
    fact_keys, fact_ids = validate_fact_definitions()
    source_ids = validate_official_source_candidates()
    version_source_refs = validate_rule_drafts(
        fact_keys,
        fact_ids,
        source_ids,
    )
    validate_rule_review_candidates(source_ids, version_source_refs)
    validate_upgrade_migration(manifest, source_ids, version_source_refs)
    validate_taxpayer_classification_security()
    validate_external_dataset_security()
    validate_invoice_normalization_security()
    validate_invoice_reconciliation()
    validate_tax_data_normalization()
    validate_vat_period_reconciliation()
    validate_cit_period_reconciliation()
    validate_filing_payment_archive()
    validate_tax_impact_review()
    validate_formal_compliance_report()
    validate_xbrl_parser_addon()
    print(f"validated {ADDON_ROOT.name} {manifest['version']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, SyntaxError, UnicodeError) as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
