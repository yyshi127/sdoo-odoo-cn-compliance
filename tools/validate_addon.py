from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from xml.etree import ElementTree


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ADDON_ROOT = REPOSITORY_ROOT / "addons" / "sudo_country_pack_cn"
TEXT_SUFFIXES = {".md", ".py", ".xml", ".yml", ".yaml"}
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


def validate_fact_definitions() -> None:
    path = ADDON_ROOT / "data" / "compliance_fact_data.xml"
    root = ElementTree.parse(path).getroot()
    facts: list[dict[str, str]] = []
    for record in root.findall(".//record"):
        if record.attrib.get("model") != "sudo.compliance.fact.definition":
            continue
        facts.append(
            {
                field.attrib["name"]: (field.text or "").strip()
                for field in record.findall("field")
            }
        )
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


def main() -> int:
    validate_text_and_syntax()
    manifest = validate_manifest()
    validate_hooks(manifest)
    validate_fact_definitions()
    print(f"validated {ADDON_ROOT.name} {manifest['version']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, SyntaxError, UnicodeError) as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
