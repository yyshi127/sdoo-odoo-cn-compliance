from __future__ import annotations

import ast
import csv
import re
import sys
from pathlib import Path
from xml.etree import ElementTree


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ADDON_ROOT = REPOSITORY_ROOT / "addons" / "sudo_country_pack_cn"
TEXT_SUFFIXES = {".csv", ".md", ".py", ".xml", ".yml", ".yaml"}
SECRET_PATTERNS = {
    "private key": re.compile(r"BEGIN (?:RSA |OPENSSH )?PRIVATE KEY"),
    "credential assignment": re.compile(
        r"(?i)(?:api[_-]?key|password|secret|token)\s*=\s*[^\s]"
    ),
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
    for relative_path in manifest.get("data", []):
        if not (ADDON_ROOT / relative_path).is_file():
            fail(f"manifest data file does not exist: {relative_path}")
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


def validate_rule_drafts(
    fact_keys: set[str],
    fact_ids: dict[str, str],
) -> None:
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

    version_case_results: dict[str, set[str]] = {
        xml_id: set() for xml_id in versions
    }
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
        if "authority_source_ids" in fields:
            fail(f"draft version must not claim governed sources: {xml_id}")
        if field_text(fields, "stale_policy", xml_id) != "block_all":
            fail(f"draft version must block evaluation when stale: {xml_id}")
        if field_text(fields, "requires_human_review", xml_id) != "True":
            fail(f"draft version must require human review: {xml_id}")

        rule_ref = fields.get("rule_id")
        rule_id = rule_ref.attrib.get("ref") if rule_ref is not None else None
        if rule_id not in rules:
            fail(f"{xml_id} references an unknown China rule")
        rules_with_versions.add(rule_id)

        condition_field = fields.get("condition_json")
        if condition_field is None:
            fail(f"{xml_id} has no declarative condition")
        condition = literal_eval_field(condition_field, xml_id)
        used_fact_keys = condition_fact_keys(condition)
        if not used_fact_keys:
            fail(f"{xml_id} condition does not reference a fact")
        unknown_keys = used_fact_keys - fact_keys
        if unknown_keys:
            fail(f"{xml_id} references unknown facts: {sorted(unknown_keys)}")

        required_field = fields.get("required_fact_ids")
        if required_field is None:
            fail(f"{xml_id} has no required fact declaration")
        required_refs = set(
            ref_pattern.findall(required_field.attrib.get("eval", ""))
        )
        required_keys = {fact_ids[ref] for ref in required_refs if ref in fact_ids}
        if len(required_keys) != len(required_refs):
            fail(f"{xml_id} references an unknown fact definition")
        if required_keys != used_fact_keys:
            fail(f"{xml_id} condition and required facts differ")

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


def main() -> int:
    validate_text_and_syntax()
    manifest = validate_manifest()
    validate_hooks(manifest)
    fact_keys, fact_ids = validate_fact_definitions()
    validate_rule_drafts(fact_keys, fact_ids)
    validate_taxpayer_classification_security()
    print(f"validated {ADDON_ROOT.name} {manifest['version']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, SyntaxError, UnicodeError) as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
