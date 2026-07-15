from __future__ import annotations

import ast
import csv
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
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
OFFICIAL_SOURCE_HOSTS = {
    "fgk.chinatax.gov.cn",
    "kjs.mof.gov.cn",
    "tfs.mof.gov.cn",
    "wb.flk.npc.gov.cn",
    "www.mof.gov.cn",
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
    data_files = manifest.get("data", [])
    for relative_path in data_files:
        if not (ADDON_ROOT / relative_path).is_file():
            fail(f"manifest data file does not exist: {relative_path}")
    ordered_data = {
        "data/official_source_candidates.xml",
        "data/compliance_rule_drafts.xml",
    }
    if not ordered_data.issubset(data_files):
        fail("manifest must load official sources and rule drafts")
    if data_files.index("data/official_source_candidates.xml") > data_files.index(
        "data/compliance_rule_drafts.xml"
    ):
        fail("official source candidates must load before rule drafts")
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
    if features.get("reconciliation") is not False:
        fail("reconciliation must remain disabled until it is implemented")


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
    return version_source_refs


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
    for migration_path in sorted(
        (ADDON_ROOT / "migrations").glob("*/post-migration.py")
    ):
        content = migration_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(migration_path))
        links = literal_assignments(tree).get("RULE_SOURCE_LINKS")
        if isinstance(links, dict):
            link_migrations.append((content, links))
    if len(link_migrations) != 1:
        fail("exactly one upgrade migration must govern rule source links")
    content, links = link_migrations[0]
    normalized_links = {
        version_id: set(candidates)
        for version_id, candidates in links.items()
    }
    if normalized_links != version_source_refs:
        fail("upgrade migration must cover every packaged rule draft")
    linked_sources = {
        source_id
        for candidates in normalized_links.values()
        for source_id in candidates
    }
    if linked_sources != source_ids:
        fail("upgrade migration must cover every official source candidate")
    if "Command.link" not in content or "Command.set" in content:
        fail("upgrade migration must preserve existing rule source links")


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
    validate_upgrade_migration(manifest, source_ids, version_source_refs)
    validate_taxpayer_classification_security()
    validate_external_dataset_security()
    print(f"validated {ADDON_ROOT.name} {manifest['version']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, SyntaxError, UnicodeError) as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
