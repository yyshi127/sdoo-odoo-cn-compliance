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
MOJIBAKE_PATTERNS = {
    # Typical UTF-8 Chinese punctuation/text decoded as Latin-1 or Windows-1252.
    "latin-1 utf8 c3": "\u00c3",
    "latin-1 utf8 c2": "\u00c2",
    "windows-1252 quote/dash": "\u00e2\u20ac",
    "mojibake chinese prefix e4-b8": "\u00e4\u00b8",
    "mojibake chinese prefix e5-203a": "\u00e5\u203a",
    "mojibake chinese prefix e5-160": "\u00e5\u0160",
    "mojibake chinese prefix e6-153": "\u00e6\u0153",
    "mojibake chinese prefix e7-a8": "\u00e7\u00a8",
    "mojibake chinese prefix e8-a7": "\u00e8\u00a7",
    "mojibake chinese prefix e9-a3": "\u00e9\u00a3",
    "mojibake chinese punctuation e3-20ac": "\u00e3\u20ac",
    "mojibake chinese punctuation ef-bc": "\u00ef\u00bc",
}
OFFICIAL_SOURCE_HOSTS = {
    "fgk.chinatax.gov.cn",
    "kjs.mof.gov.cn",
    "www.mof.gov.cn",
    "www.gov.cn",
    "www.chinatax.gov.cn",
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
    "source_cn_iit_law_2018_candidate": (
        "https://fgk.chinatax.gov.cn/zcfgk/c100009/c5193028/content.html"
    ),
    "source_cn_iit_regulation_2018_candidate": (
        "https://www.chinatax.gov.cn/chinatax/n810219/n810744/"
        "n3752930/n3752974/c3963364/content.html"
    ),
    "source_cn_iit_withholding_measures_2018_candidate": (
        "https://www.chinatax.gov.cn/chinatax/n810341/n810765/"
        "n3359382/201812/c4182700/content.html"
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
    "cn.iit.reconciliation.review.v1": "1",
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


def _literal_model_names(value: ast.AST) -> set[str]:
    try:
        literal = ast.literal_eval(value)
    except (TypeError, ValueError):
        return set()
    if isinstance(literal, str):
        return {literal}
    if isinstance(literal, (list, tuple)):
        return {item for item in literal if isinstance(item, str)}
    return set()


def _field_kwarg(call: ast.Call, name: str) -> ast.AST | None:
    return next((keyword.value for keyword in call.keywords if keyword.arg == name), None)


def _literal_true(value: ast.AST | None) -> bool:
    if value is None:
        return False
    try:
        return ast.literal_eval(value) is True
    except (TypeError, ValueError):
        return False


def _model_names_for_class(node: ast.ClassDef) -> set[str]:
    names: set[str] = set()
    for item in node.body:
        if not (
            isinstance(item, ast.Assign)
            and len(item.targets) == 1
            and isinstance(item.targets[0], ast.Name)
            and item.targets[0].id in {"_name", "_inherit"}
        ):
            continue
        names.update(_literal_model_names(item.value))
    return names


def _nonstored_computed_fields_by_model() -> dict[str, set[str]]:
    fields_by_model: dict[str, set[str]] = {}
    for path in sorted((ADDON_ROOT / "models").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            model_names = _model_names_for_class(node)
            if not model_names:
                continue
            for item in node.body:
                if not (
                    isinstance(item, ast.Assign)
                    and len(item.targets) == 1
                    and isinstance(item.targets[0], ast.Name)
                    and isinstance(item.value, ast.Call)
                    and isinstance(item.value.func, ast.Attribute)
                    and isinstance(item.value.func.value, ast.Name)
                    and item.value.func.value.id == "fields"
                ):
                    continue
                call = item.value
                if _field_kwarg(call, "compute") is None:
                    continue
                if _literal_true(_field_kwarg(call, "store")):
                    continue
                if _field_kwarg(call, "search") is not None:
                    continue
                field_name = item.targets[0].id
                for model_name in model_names:
                    fields_by_model.setdefault(model_name, set()).add(field_name)
    return fields_by_model


def _search_domain_field_names(domain: str) -> set[str]:
    return set(re.findall(r"\(['\"]([^'\"]+)['\"]\s*,", domain or ""))


def _search_group_by_field_names(context: str) -> set[str]:
    fields: set[str] = set()
    for group_by in re.findall(
        r"['\"]group_by['\"]\s*:\s*['\"]([^'\"]+)['\"]",
        context or "",
    ):
        fields.add(group_by.split(":", 1)[0])
    return fields


def _env_model_name(value: ast.AST) -> str | None:
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute):
        return _env_model_name(value.func.value)
    if not isinstance(value, ast.Subscript):
        return None
    if not (
        isinstance(value.value, ast.Attribute)
        and value.value.attr == "env"
        and isinstance(value.value.value, ast.Name)
        and value.value.value.id == "self"
    ):
        return None
    try:
        model_name = ast.literal_eval(value.slice)
    except (TypeError, ValueError):
        return None
    return model_name if isinstance(model_name, str) else None


def _domain_field_names(value: ast.AST, variables: dict[str, set[str]]) -> set[str] | None:
    if isinstance(value, ast.Name):
        return variables.get(value.id)
    if isinstance(value, ast.BinOp) and isinstance(value.op, ast.Add):
        left = _domain_field_names(value.left, variables)
        right = _domain_field_names(value.right, variables)
        if left is None or right is None:
            return None
        return left | right
    if not isinstance(value, (ast.List, ast.Tuple)):
        return None
    fields: set[str] = set()
    for item in value.elts:
        if isinstance(item, (ast.List, ast.Tuple)) and item.elts:
            first = item.elts[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                fields.add(first.value.split(".", 1)[0])
    return fields


def _function_domain_variables(node: ast.FunctionDef) -> dict[str, set[str]]:
    assignments: list[tuple[str, ast.AST]] = []
    for item in ast.walk(node):
        if not isinstance(item, ast.Assign) or len(item.targets) != 1:
            continue
        target = item.targets[0]
        if isinstance(target, ast.Name):
            assignments.append((target.id, item.value))

    variables: dict[str, set[str]] = {}
    changed = True
    while changed:
        changed = False
        for name, value in assignments:
            fields = _domain_field_names(value, variables)
            if fields is None:
                continue
            combined = (variables.get(name) or set()) | fields
            if variables.get(name) != combined:
                variables[name] = combined
                changed = True
    return variables


def _function_model_aliases(node: ast.FunctionDef) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for item in ast.walk(node):
        if not isinstance(item, ast.Assign) or len(item.targets) != 1:
            continue
        target = item.targets[0]
        if not isinstance(target, ast.Name):
            continue
        model_name = _env_model_name(item.value)
        if model_name:
            aliases[target.id] = model_name
    return aliases


def _call_receiver_model(
    value: ast.AST,
    aliases: dict[str, str],
    current_model: str | None,
) -> str | None:
    if isinstance(value, ast.Name):
        if value.id == "self":
            return current_model
        return aliases.get(value.id)
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute):
        inherited = _call_receiver_model(value.func.value, aliases, current_model)
        if inherited:
            return inherited
    return _env_model_name(value)


def validate_python_domains_do_not_search_nonstored_computed_fields() -> None:
    computed_fields = _nonstored_computed_fields_by_model()
    if not computed_fields:
        return
    checked_methods = {"search", "search_count", "filtered_domain", "_read_group"}
    for path in sorted((ADDON_ROOT / "models").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
        for class_node in classes:
            model_names = _model_names_for_class(class_node)
            current_model = next(iter(model_names)) if len(model_names) == 1 else None
            functions = [
                node for node in ast.walk(class_node) if isinstance(node, ast.FunctionDef)
            ]
            for function in functions:
                aliases = _function_model_aliases(function)
                domain_variables = _function_domain_variables(function)
                for call in (node for node in ast.walk(function) if isinstance(node, ast.Call)):
                    if not (
                        isinstance(call.func, ast.Attribute)
                        and call.func.attr in checked_methods
                        and call.args
                    ):
                        continue
                    model_name = _call_receiver_model(
                        call.func.value,
                        aliases,
                        current_model,
                    )
                    if not model_name or model_name not in computed_fields:
                        continue
                    domain_fields = _domain_field_names(call.args[0], domain_variables)
                    if domain_fields is None:
                        continue
                    used = domain_fields & computed_fields[model_name]
                    if used:
                        fail(
                            "Python ORM domains cannot search non-stored computed "
                            f"fields {sorted(used)} on {model_name} in {path} "
                            f"function {function.name}"
                        )
        for function in (
            node for node in tree.body if isinstance(node, ast.FunctionDef)
        ):
            aliases = _function_model_aliases(function)
            domain_variables = _function_domain_variables(function)
            for call in (node for node in ast.walk(function) if isinstance(node, ast.Call)):
                if not (
                    isinstance(call.func, ast.Attribute)
                    and call.func.attr in checked_methods
                    and call.args
                ):
                    continue
                model_name = _call_receiver_model(call.func.value, aliases, None)
                if not model_name or model_name not in computed_fields:
                    continue
                domain_fields = _domain_field_names(call.args[0], domain_variables)
                if domain_fields is None:
                    continue
                used = domain_fields & computed_fields[model_name]
                if used:
                    fail(
                        "Python ORM domains cannot search non-stored computed "
                        f"fields {sorted(used)} on {model_name} in {path} "
                        f"function {function.name}"
                    )


def validate_search_views_do_not_filter_nonstored_computed_fields() -> None:
    computed_fields = _nonstored_computed_fields_by_model()
    if not computed_fields:
        return
    for path in sorted((ADDON_ROOT / "views").glob("*.xml")):
        root = ElementTree.parse(path).getroot()
        for record in root.findall(".//record[@model='ir.ui.view']"):
            fields = record_fields(record)
            model_name = field_text(fields, "model", record.attrib.get("id", "view"))
            if not model_name or model_name not in computed_fields:
                continue
            blocked = computed_fields[model_name]
            arch = fields.get("arch")
            if arch is None:
                continue
            for element in arch.findall(".//search//filter"):
                filter_name = element.attrib.get("name", "<unnamed>")
                domain_fields = _search_domain_field_names(element.attrib.get("domain", ""))
                group_fields = _search_group_by_field_names(element.attrib.get("context", ""))
                used = (domain_fields | group_fields) & blocked
                if used:
                    fail(
                        "search view filters/group-by cannot use non-stored "
                        f"computed fields {sorted(used)} in {path} "
                        f"record {record.attrib.get('id')} filter {filter_name}"
                    )
            for element in arch.iter():
                default_group_by = element.attrib.get("default_group_by")
                if not default_group_by:
                    continue
                field_name = default_group_by.split(":", 1)[0]
                if field_name in blocked:
                    fail(
                        "view default_group_by cannot use non-stored computed "
                        f"field {field_name!r} in {path} "
                        f"record {record.attrib.get('id')}"
                    )


def validate_text_and_syntax() -> None:
    for path in sorted(REPOSITORY_ROOT.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        if path.suffix not in TEXT_SUFFIXES:
            continue
        content = path.read_text(encoding="utf-8", errors="strict")
        if "\ufffd" in content:
            fail(f"replacement character found in {path}")
        private_use_chars = sorted(
            {char for char in content if 0xE000 <= ord(char) <= 0xF8FF}
        )
        if private_use_chars:
            codepoints = ", ".join(f"U+{ord(char):04X}" for char in private_use_chars)
            fail(f"private-use mojibake-like character found in {path}: {codepoints}")
        for label, marker in MOJIBAKE_PATTERNS.items():
            if marker in content:
                escaped = marker.encode("unicode_escape").decode("ascii")
                fail(f"possible {label} text mojibake found in {path}: {escaped}")
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
    if features.get("china_report_center_visibility") is not True:
        fail("China report center visibility capability must be declared")
    if features.get("china_report_obligation_readiness") is not True:
        fail("China report obligation readiness capability must be declared")
    if features.get("china_report_remediation_verification") is not True:
        fail("China report remediation verification capability must be declared")
    if features.get("china_report_rescan_gate") is not True:
        fail("China report rescan gate capability must be declared")
    if features.get("china_report_filing_archive_gate") is not True:
        fail("China report filing archive gate capability must be declared")
    if features.get("china_report_filing_archive_snapshot") is not True:
        fail("China report filing archive snapshot capability must be declared")
    if features.get("china_report_risk_closure_snapshot") is not True:
        fail("China report risk closure snapshot capability must be declared")
    if features.get("china_traceability_matrix_visibility") is not True:
        fail("China traceability matrix visibility capability must be declared")
    if features.get("china_ai_guidance_visibility") is not True:
        fail("China AI guidance visibility capability must be declared")
    if features.get("china_ai_obligation_context") is not True:
        fail("China AI obligation context capability must be declared")
    if features.get("china_ai_filing_archive_context") is not True:
        fail("China AI filing archive context capability must be declared")
    if features.get("china_obligation_readiness_visibility") is not True:
        fail("China obligation readiness visibility capability must be declared")
    if features.get("china_assessment_obligation_basis") is not True:
        fail("China assessment obligation basis capability must be declared")
    if features.get("china_workbench_cross_border_overview") is not True:
        fail("China cross-border workbench overview must be declared")
    if features.get("china_cross_border_transaction_register") is not True:
        fail("China cross-border transaction register capability must be declared")
    if features.get("china_cross_border_rule_facts") is not True:
        fail("China cross-border rule fact bridge capability must be declared")
    if features.get("china_cross_border_risk_visibility") is not True:
        fail("China cross-border risk visibility capability must be declared")
    if features.get("china_workbench_filing_archive_summary") is not True:
        fail("China workbench filing archive summary capability must be declared")
    if features.get("china_workbench_state_badge_clarity") is not True:
        fail("China workbench state badge clarity capability must be declared")
    if features.get("china_risk_card_state_badge_clarity") is not True:
        fail("China risk card state badge clarity capability must be declared")
    if features.get("china_risk_closure_status_summary") is not True:
        fail("China risk closure status summary capability must be declared")
    if features.get("china_report_readiness_badge_clarity") is not True:
        fail("China report readiness badge clarity capability must be declared")
    if features.get("china_archive_evidence_badge_clarity") is not True:
        fail("China archive and evidence badge clarity capability must be declared")
    if features.get("china_formal_report_badge_clarity") is not True:
        fail("China formal report badge clarity capability must be declared")
    if features.get("china_workbench_remediation_rescan_summary") is not True:
        fail("China workbench remediation rescan summary capability must be declared")
    if features.get("china_workbench_next_best_action") is not True:
        fail("China workbench next-best-action capability must be declared")
    if features.get("china_delivery_objective_coverage") is not True:
        fail("China delivery objective coverage capability must be declared")
    if features.get("china_business_uat_checklist") is not True:
        fail("China business UAT checklist capability must be declared")
    if features.get("china_production_signoff_template") is not True:
        fail("China production sign-off template capability must be declared")
    if features.get("china_delivery_preview_health_checker") is not True:
        fail("China delivery preview health checker capability must be declared")
    if features.get("china_delivery_index") is not True:
        fail("China delivery index capability must be declared")
    if features.get("china_delivery_readiness_gates") is not True:
        fail("China delivery readiness gates capability must be declared")
    if features.get("china_delivery_preview_health_gate") is not True:
        fail("China delivery preview health gate capability must be declared")
    if features.get("china_delivery_preview_url_match_gate") is not True:
        fail("China delivery preview URL match gate capability must be declared")
    if features.get("china_delivery_strict_readiness_exit") is not True:
        fail("China delivery strict readiness exit capability must be declared")
    if features.get("china_delivery_source_control_traceability") is not True:
        fail("China delivery source control traceability capability must be declared")
    if features.get("china_delivery_source_control_clean_gate") is not True:
        fail("China delivery source control clean gate capability must be declared")
    if features.get("china_delivery_commit_consistency_gate") is not True:
        fail("China delivery commit consistency gate capability must be declared")
    if features.get("china_delivery_preview_module_gate") is not True:
        fail("China delivery preview module gate capability must be declared")
    if features.get("china_real_data_closed_loop_checker") is not True:
        fail("China real-data closed-loop checker capability must be declared")
    if features.get("china_controlled_demo_profile_preparer") is not True:
        fail("China controlled demo profile preparer capability must be declared")
    if features.get("china_controlled_demo_closed_loop_preparer") is not True:
        fail("China controlled demo closed-loop preparer capability must be declared")
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
    if features.get("iit_withholding_normalization") is not True:
        fail("controlled IIT withholding normalization capability must be declared")
    if features.get("payroll_summary_normalization") is not True:
        fail("controlled aggregate payroll normalization capability must be declared")
    if features.get("iit_accounting_reconciliation") is not True:
        fail("controlled IIT accounting reconciliation capability must be declared")
    if features.get("iit_governed_rule_candidates") is not True:
        fail("governed IIT rule candidate capability must be declared")
    if features.get("iit_filing_settlement_archive") is not True:
        fail("controlled IIT filing and settlement archive capability must be declared")
    if features.get("official_source_change_monitoring") is not True:
        fail("governed official source change monitoring must be declared")
    if features.get("jurisdiction") is not True:
        fail("China jurisdiction capability must be declared")
    if features.get("jurisdiction_governance") is not True:
        fail("China jurisdiction governance capability must be declared")
    if features.get("local_rule_scope") is not True:
        fail("China local rule scope capability must be declared")


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
    if len(citation_records) != 29:
        fail("packaged China review candidates require twenty-nine citations")

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
        if "def migrate(env, version)" in content:
            fail(f"migration must use Odoo runtime signature migrate(cr, version): {migration_path}")
        if "api.Environment(cr, SUPERUSER_ID" not in content:
            fail(f"migration must explicitly build an Odoo env from cr: {migration_path}")
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
    if len(company_rules) != 2:
        fail("external datasets require user and manager company record rules")
    domains = [
        field_text(rule, "domain_force", "company rule")
        for rule in company_rules
    ]
    if any("company_ids" not in domain or "company_id" not in domain for domain in domains):
        fail("external dataset rules must enforce allowed companies")
    if not any("iit_withholding" in domain for domain in domains):
        fail("external dataset user rule must restrict sensitive IIT sources")

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
    if "views/iit_withholding_views.xml" not in manifest.get("data", []):
        fail("IIT withholding normalization views must be loaded by the manifest")
    if "views/payroll_summary_views.xml" not in manifest.get("data", []):
        fail("payroll summary normalization views must be loaded by the manifest")

    model_init = (ADDON_ROOT / "models" / "__init__.py").read_text(
        encoding="utf-8"
    )
    if "from . import tax_data_normalization" not in model_init:
        fail("tax data normalization models must be imported")
    if "from . import cit_filing_normalization" not in model_init:
        fail("CIT filing normalization models must be imported")
    if "from . import iit_withholding_normalization" not in model_init:
        fail("IIT withholding normalization models must be imported")
    if "from . import payroll_summary_normalization" not in model_init:
        fail("payroll summary normalization models must be imported")

    service_init = (ADDON_ROOT / "services" / "__init__.py").read_text(
        encoding="utf-8"
    )
    if "tax_data_contract" not in service_init:
        fail("tax data contract service must be imported")

    contract_path = ADDON_ROOT / "services" / "tax_data_contract.py"
    model_path = ADDON_ROOT / "models" / "tax_data_normalization.py"
    cit_model_path = ADDON_ROOT / "models" / "cit_filing_normalization.py"
    iit_model_path = ADDON_ROOT / "models" / "iit_withholding_normalization.py"
    payroll_model_path = (
        ADDON_ROOT / "models" / "payroll_summary_normalization.py"
    )
    if (
        not contract_path.is_file()
        or not model_path.is_file()
        or not cit_model_path.is_file()
        or not iit_model_path.is_file()
        or not payroll_model_path.is_file()
    ):
        fail("tax data normalization implementation is incomplete")
    contract_content = contract_path.read_text(encoding="utf-8")
    model_content = model_path.read_text(encoding="utf-8")
    cit_model_content = cit_model_path.read_text(encoding="utf-8")
    iit_model_content = iit_model_path.read_text(encoding="utf-8")
    payroll_model_content = payroll_model_path.read_text(encoding="utf-8")
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
    for required in (
        '"iit_withholding"',
        "_IIT_WITHHOLDING_FIELDS",
        "_IIT_WITHHOLDING_LINE_FIELDS",
        "_IIT_CONTROLLED_KEY_PATTERN",
        "_IIT_SOURCE_LINE_KEY",
        "_validate_iit_lines",
        "controlled pseudonymous key",
        "must be a controlled opaque key",
        "must not contain an identity number",
    ):
        if required not in contract_content:
            fail(f"IIT withholding data contract is missing {required}")
    for required in (
        '_name = "sudo.cn.iit.withholding.record"',
        '_name = "sudo.cn.iit.withholding.line"',
        "has_declared_person_count",
        "has_total_income_amount",
        "has_total_payable_refundable_amount",
        "IIT_PERSON_COUNT_MISMATCH",
        "IIT_LINE_COUNT_MISMATCH",
        "IIT_INCOME_TOTAL_MISMATCH",
        "IIT_SETTLEMENT_TOTAL_MISMATCH",
        "line_checksum",
        "_TAX_NORMALIZED_RECORD_MARKER",
    ):
        if required not in iit_model_content:
            fail(f"IIT withholding normalization contract is missing {required}")
    for required in (
        '"payroll_summary"',
        "_PAYROLL_SUMMARY_FIELDS",
    ):
        if required not in contract_content:
            fail(f"payroll summary data contract is missing {required}")
    for required in (
        '_name = "sudo.cn.payroll.summary.record"',
        "has_gross_income_amount",
        "has_withheld_iit_amount",
        "MISSING_PAYROLL_PERSON_COUNT",
        "record_checksum",
    ):
        if required not in payroll_model_content:
            fail(f"payroll summary normalization contract is missing {required}")

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
    manager_only_models = {
        "model_sudo_cn_iit_withholding_record",
        "model_sudo_cn_iit_withholding_line",
        "model_sudo_cn_payroll_summary_record",
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
    for model_name in manager_only_models:
        model_rows = [row for row in rows if row["model_id:id"] == model_name]
        if {row["group_id:id"] for row in model_rows} != {
            "sudo_global_finance.group_compliance_manager"
        }:
            fail(f"sensitive IIT ACL must be manager-only: {model_name}")
        manager_row = model_rows[0]
        if manager_row["perm_read"] != "1" or manager_row["perm_unlink"] != "0":
            fail(f"sensitive IIT audit ACL is invalid: {model_name}")

    security_root = ElementTree.parse(
        ADDON_ROOT / "security" / "compliance_security.xml"
    ).getroot()
    ruled_models = set()
    for record in security_root.findall(".//record[@model='ir.rule']"):
        fields = record_fields(record)
        model_field = fields.get("model_id")
        model_ref = model_field.attrib.get("ref") if model_field is not None else ""
        if model_ref not in governed_models | manager_only_models:
            continue
        domain = field_text(fields, "domain_force", record.attrib["id"])
        if "company_ids" not in domain or "company_id" not in domain:
            fail(f"tax data rule lacks company isolation: {model_ref}")
        ruled_models.add(model_ref)
    if ruled_models != governed_models | manager_only_models:
        fail("every governed tax data model requires a company record rule")
    security_content = (ADDON_ROOT / "security" / "compliance_security.xml").read_text(
        encoding="utf-8"
    )
    for required in (
        "cn_external_dataset_manager_company_rule",
        "cn_tax_data_parse_run_manager_company_rule",
        "('dataset_type', 'not in', ('iit_withholding', 'payroll_summary'))",
    ):
        if required not in security_content:
            fail(f"sensitive IIT source access control is missing {required}")

    view_path = ADDON_ROOT / view_relative_path
    cit_view_path = ADDON_ROOT / "views" / "cit_filing_views.xml"
    iit_view_path = ADDON_ROOT / "views" / "iit_withholding_views.xml"
    payroll_view_path = ADDON_ROOT / "views" / "payroll_summary_views.xml"
    if (
        not view_path.is_file()
        or not cit_view_path.is_file()
        or not iit_view_path.is_file()
        or not payroll_view_path.is_file()
    ):
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
    iit_view_content = iit_view_path.read_text(encoding="utf-8")
    for required_id in (
        "view_cn_tax_data_parse_run_form_iit",
        "view_cn_iit_withholding_record_search",
        "view_cn_iit_withholding_record_list",
        "view_cn_iit_withholding_record_form",
        "view_cn_iit_withholding_line_form",
        "action_cn_iit_withholding_records",
        "menu_cn_iit_withholding_records",
        "view_cn_external_dataset_form_iit_results",
    ):
        if f'id="{required_id}"' not in iit_view_content:
            fail(f"IIT withholding normalization UI is missing {required_id}")
    for boundary_text in (
        "不计算工资、扣除、税率或应扣税额",
        "源明细键和人员键只接受受控 HMAC 或不透明值",
        "不得在标准化契约中写入姓名、身份证件、手机、地址或银行账户",
        "明确申报为零的字段会保留并显示为零",
    ):
        if boundary_text not in iit_view_content:
            fail(f"IIT withholding UI privacy boundary is missing: {boundary_text}")
    payroll_view_content = payroll_view_path.read_text(encoding="utf-8")
    for required_id in (
        "view_cn_tax_data_parse_run_form_payroll",
        "view_cn_payroll_summary_record_search",
        "view_cn_payroll_summary_record_list",
        "view_cn_payroll_summary_record_form",
        "action_cn_payroll_summary_records",
        "menu_cn_payroll_summary_records",
        "view_cn_external_dataset_form_payroll_results",
    ):
        if f'id="{required_id}"' not in payroll_view_content:
            fail(f"payroll summary normalization UI is missing {required_id}")

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
    if test_methods < 20:
        fail("tax data normalization requires at least twenty runtime tests")


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


def validate_iit_period_reconciliation() -> None:
    manifest = ast.literal_eval(
        (ADDON_ROOT / "__manifest__.py").read_text(encoding="utf-8")
    )
    required_data_files = {
        "data/iit_period_reconciliation_cron.xml",
        "views/iit_accounting_scope_views.xml",
        "views/iit_period_reconciliation_views.xml",
    }
    if not required_data_files.issubset(manifest.get("data", [])):
        fail("IIT accounting scope and reconciliation files must be loaded")

    model_init = (ADDON_ROOT / "models" / "__init__.py").read_text(
        encoding="utf-8"
    )
    for module_name in ("iit_accounting_scope", "iit_period_reconciliation"):
        if f"from . import {module_name}" not in model_init:
            fail(f"IIT model must be imported: {module_name}")

    scope_path = ADDON_ROOT / "models" / "iit_accounting_scope.py"
    run_path = ADDON_ROOT / "models" / "iit_period_reconciliation.py"
    if not scope_path.is_file() or not run_path.is_file():
        fail("IIT accounting reconciliation implementation is incomplete")
    scope_content = scope_path.read_text(encoding="utf-8")
    run_content = run_path.read_text(encoding="utf-8")
    for required in (
        '_name = "sudo.cn.iit.accounting.scope"',
        '_name = "sudo.cn.iit.accounting.scope.line"',
        "_IIT_SCOPE_TRANSITION_MARKER",
        "payroll_source_schema",
        "payroll_source_schema_version",
        "iit_source_schema",
        "iit_source_schema_version",
        "payable_refundable_sign_convention",
        "evidence_attachment_ids",
        "separation_exception_reason",
        "_overlapping_verified",
        "action_verify",
        "verification_checksum",
        "checksum_mismatch",
        '"unique(scope_id, account_id)"',
    ):
        if required not in scope_content:
            fail(f"IIT accounting scope contract is missing {required}")

    for required in (
        "IIT_PERIOD_ENGINE_VERSION",
        "FOR UPDATE SKIP LOCKED",
        "MAX_ACCOUNTING_LINES",
        "MAX_SOURCE_RECORDS",
        "MAX_PAYMENT_RECORDS",
        "models.UniqueIndex",
        "_IIT_PERIOD_TRANSITION_MARKER",
        "accounting_scope_snapshot_checksum",
        "accounting_snapshot_checksum",
        "payroll_snapshot_checksum",
        "filing_snapshot_checksum",
        "payment_snapshot_checksum",
        "result_checksum",
        "result_integrity_state",
        "_current_result_checksum",
        "NO_VERIFIED_IIT_ACCOUNTING_SCOPE",
        "NO_CURRENT_PAYROLL_SUMMARY",
        "NO_CURRENT_IIT_WITHHOLDING_RETURN",
        "NO_CURRENT_IIT_PAYMENT_DATA",
        "PAYROLL_SOURCE_SCHEMA_MISMATCH",
        "IIT_SOURCE_SCHEMA_MISMATCH",
        "IIT_PAYROLL_FILING_PERSON_COUNT_DIFFERENCE",
        "IIT_LEDGER_PAYROLL_EXPENSE_DIFFERENCE",
        "IIT_EMPLOYEE_PAYABLE_PAYROLL_DIFFERENCE",
        "IIT_LEDGER_PAYROLL_WITHHOLDING_DIFFERENCE",
        "IIT_FILING_PAYROLL_INCOME_DIFFERENCE",
        "IIT_FILING_PAYROLL_TAX_DIFFERENCE",
        "IIT_LEDGER_PAYMENT_DIFFERENCE",
        "IIT_PAYABLE_PAYMENT_DIFFERENCE",
        "IIT_REFUNDABLE_REFUND_DIFFERENCE",
        'payments["payment_dates"]',
        '("date", "in", payment_dates)',
        "has_count_comparison",
        'issue_kind == "difference" and not has_count_comparison',
        "insufficient_data",
        "cn_iit_period_reconciliation.queued",
        "cn_iit_period_reconciliation.succeeded",
        'groups="sudo_global_finance.group_compliance_manager"',
    ):
        if required not in run_content:
            fail(f"IIT period reconciliation contract is missing {required}")

    access_path = ADDON_ROOT / "security" / "ir.model.access.csv"
    with access_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    governed_models = {
        "model_sudo_cn_iit_accounting_scope",
        "model_sudo_cn_iit_accounting_scope_line",
        "model_sudo_cn_iit_period_reconciliation_run",
        "model_sudo_cn_iit_period_reconciliation_issue",
    }
    expected_groups = {
        "sudo_global_finance.group_compliance_user",
        "sudo_global_finance.group_compliance_manager",
    }
    for model_name in governed_models:
        model_rows = [row for row in rows if row["model_id:id"] == model_name]
        if {row["group_id:id"] for row in model_rows} != expected_groups:
            fail(f"IIT reconciliation ACL groups are incomplete: {model_name}")
        user_row = next(
            row
            for row in model_rows
            if row["group_id:id"].endswith("group_compliance_user")
        )
        if [
            user_row[key]
            for key in ("perm_read", "perm_write", "perm_create", "perm_unlink")
        ] != ["1", "0", "0", "0"]:
            fail(f"IIT reconciliation users must be read-only: {model_name}")
        if model_name.endswith(("reconciliation_run", "reconciliation_issue")):
            manager_row = next(
                row
                for row in model_rows
                if row["group_id:id"].endswith("group_compliance_manager")
            )
            if manager_row["perm_unlink"] != "0":
                fail(f"IIT reconciliation snapshots must not be deleted: {model_name}")

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
            fail(f"IIT reconciliation rule lacks company isolation: {model_ref}")
        ruled_models.add(model_ref)
    if ruled_models != governed_models:
        fail("every governed IIT reconciliation model requires a company rule")

    cron_content = (
        ADDON_ROOT / "data" / "iit_period_reconciliation_cron.xml"
    ).read_text(encoding="utf-8")
    if "_cron_process_runs(limit=1)" not in cron_content:
        fail("IIT reconciliation must use a bounded native Odoo queue")

    facts = (ADDON_ROOT / "data" / "compliance_fact_data.xml").read_text(
        encoding="utf-8"
    )
    provider = (ADDON_ROOT / "models" / "compliance_engine.py").read_text(
        encoding="utf-8"
    )
    for fact_key in (
        "cn.reconciliation.iit.conclusion_state",
        "cn.reconciliation.iit.blocking_issue_count",
        "cn.reconciliation.iit.difference_issue_count",
        "cn.reconciliation.iit.warning_issue_count",
        "cn.reconciliation.iit.detail",
    ):
        if fact_key not in facts or fact_key not in provider:
            fail(f"IIT reconciliation fact bridge is missing {fact_key}")
    if "sdoo.cn.reconciliation.iit-period.fact.v1" not in provider:
        fail("IIT reconciliation fact snapshot schema is missing")
    if "IIT_RECONCILIATION_REVIEW_HANDLER" not in provider:
        fail("IIT reconciliation governed review handler is missing")

    scope_view = (
        ADDON_ROOT / "views" / "iit_accounting_scope_views.xml"
    ).read_text(encoding="utf-8")
    run_view = (
        ADDON_ROOT / "views" / "iit_period_reconciliation_views.xml"
    ).read_text(encoding="utf-8")
    for required_id in (
        "view_cn_iit_accounting_scope_list",
        "view_cn_iit_accounting_scope_form",
        "action_cn_iit_accounting_scopes",
        "menu_cn_iit_accounting_scopes",
    ):
        if f'id="{required_id}"' not in scope_view:
            fail(f"IIT accounting scope UI is missing {required_id}")
    for required_id in (
        "view_cn_iit_period_reconciliation_run_list",
        "view_cn_iit_period_reconciliation_run_form",
        "view_cn_iit_period_reconciliation_issue_list",
        "view_cn_iit_period_reconciliation_issue_form",
        "view_cn_iit_period_reconciliation_wizard_form",
        "action_cn_iit_period_reconciliation_runs",
        "action_cn_iit_period_reconciliation_issues",
        "action_cn_iit_period_reconciliation_start",
        "menu_cn_iit_period_reconciliation_runs",
        "menu_cn_iit_period_reconciliation_start",
        "menu_cn_iit_period_reconciliation_issues",
    ):
        if f'id="{required_id}"' not in run_view:
            fail(f"IIT period reconciliation UI is missing {required_id}")
    for required in (
        'groups="sudo_global_finance.group_compliance_manager"',
        "has_count_comparison",
        "五层数据充分性",
        "差异不自动等同于少缴、多缴或违法",
        "当前受控口径下算术一致",
        "系统不会猜测代码、科目或工资金额",
    ):
        if required not in run_view:
            fail(f"IIT reconciliation UI boundary is missing {required}")

    test_path = ADDON_ROOT / "tests" / "test_iit_period_reconciliation.py"
    if not test_path.is_file():
        fail("IIT reconciliation runtime tests are missing")
    test_content = test_path.read_text(encoding="utf-8")
    test_tree = ast.parse(test_content)
    test_methods = sum(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
        for node in ast.walk(test_tree)
    )
    if test_methods < 20:
        fail("IIT reconciliation and archive require at least twenty runtime tests")
    for test_name in (
        "test_aligned_run_uses_payment_date_outside_tax_period",
        "test_missing_sources_is_insufficient_not_aligned",
        "test_fact_provider_exposes_aggregate_exact_period_snapshot",
        "test_amount_differences_are_visible_review_items",
        "test_person_count_difference_is_not_rendered_as_money",
        "test_source_schema_mismatch_blocks_comparison",
        "test_verified_scope_and_results_are_immutable",
        "test_sensitive_sources_are_manager_only_but_run_is_readable",
        "test_iit_reconciliation_drives_remediation_and_exact_period_rescan",
        "test_company_rule_hides_other_company_scope",
        "test_direct_creation_and_manual_changes_are_blocked",
    ):
        if f"def {test_name}(" not in test_content:
            fail(f"IIT reconciliation runtime coverage is missing {test_name}")


def validate_iit_filing_payment_archive() -> None:
    model_init = (ADDON_ROOT / "models" / "__init__.py").read_text(
        encoding="utf-8"
    )
    if "from . import iit_filing_archive" not in model_init:
        fail("IIT filing and settlement archive model must be imported")
    if model_init.index("from . import iit_filing_archive") < model_init.index(
        "from . import iit_period_reconciliation"
    ):
        fail("IIT filing archive must load after IIT reconciliation")

    model_path = ADDON_ROOT / "models" / "iit_filing_archive.py"
    if not model_path.is_file():
        fail("IIT filing and settlement archive implementation is missing")
    model_content = model_path.read_text(encoding="utf-8")
    for required in (
        '_inherit = "sudo.compliance.filing"',
        '_inherit = "sudo.cn.iit.period.reconciliation.run"',
        '"sdoo.cn.iit-withholding-filing-archive.v1"',
        '"sdoo.cn.iit-withholding-settlement-archive.v1"',
        "_CN_IIT_ARCHIVE_LINK_MARKER",
        "cn_iit_reconciliation_run_id",
        "_cn_iit_validate_obligation",
        "_cn_iit_source_record",
        "_cn_iit_validate_payable",
        "_cn_iit_validate_refund",
        "action_seal_cn_iit_refund",
        "action_open_cn_iit_reconciliation",
        "action_open_cn_filing_archive",
        "cn.iit_filing_archive.sealed",
        "cn.iit_payment_archive.sealed",
        "cn.iit_refund_archive.sealed",
        "source_superseded",
        "filing_receipt",
        "payment_proof",
        "refund_receipt",
    ):
        if required not in model_content:
            fail(f"IIT filing archive contract is missing {required}")
    if "default_due_date" in model_content:
        fail("IIT filing archive must not infer a legal filing deadline")
    for sensitive_expression in (
        "record.line_ids",
        '"subject_key"',
        '"source_line_key"',
        '"taxpayer_name"',
        '"taxpayer_id"',
    ):
        if sensitive_expression in model_content:
            fail(
                "IIT filing archive must not copy person-level source data: "
                f"{sensitive_expression}"
            )

    view_content = (
        ADDON_ROOT / "views" / "filing_archive_views.xml"
    ).read_text(encoding="utf-8")
    for required in (
        'id="view_cn_iit_period_reconciliation_run_form_filing_archive"',
        'name="cn_iit_reconciliation_run_id"',
        'name="action_seal_cn_iit_refund"',
        'name="action_open_cn_iit_reconciliation"',
        'name="cn_iit_controlled"',
        "中国个人所得税受控档案",
        "不把姓名、证件号码或人员明细写入申报档案快照",
        "两个结算方向不会被系统静默轧差",
    ):
        if required not in view_content:
            fail(f"IIT filing archive UI is missing {required}")

    test_content = (
        ADDON_ROOT / "tests" / "test_iit_period_reconciliation.py"
    ).read_text(encoding="utf-8")
    for test_name in (
        "test_filing_archive_action_does_not_infer_legal_deadline",
        "test_iit_payable_archive_seals_private_submission_and_payment_chain",
        "test_iit_refund_archive_keeps_refund_distinct_from_payment",
        "test_iit_filing_archive_requires_verified_formal_receipt",
        "test_iit_filing_archive_blocks_unknown_settlement_direction",
        "test_iit_payable_archive_rejects_unreconciled_payment",
        "test_iit_refund_archive_rejects_unreconciled_refund",
        "test_iit_filing_archive_detects_reconciliation_tampering",
        "test_iit_filing_archive_rejects_cross_company_reconciliation",
    ):
        if f"def {test_name}(" not in test_content:
            fail(f"IIT filing archive runtime coverage is missing {test_name}")


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
        "cn_report_center_stage",
        "cn_report_center_integrity_state",
        "cn_report_center_next_action",
        "cn_report_blocker_summary",
        "cn_report_traceability_state",
        "cn_report_traceability_gap_count",
        "cn_report_traceability_next_action",
        "obligation_readiness",
        "_obligation_readiness_payload",
        "filing_archive",
        "_filing_archive_payload",
        "_controlled_filing_domain",
        "remediation_task_count",
        "remediation_verified_count",
        "remediation_pending_verification_count",
        "finding_closure_blocked_count",
        "finding_closure_action_required_count",
        "finding_closure_ready_count",
        '"closure_state"',
        '"closure_summary"',
        "verification_assessment_id",
        "verification_assessment_name",
        "remediation_verification",
        "action_cn_open_report_findings",
        "action_cn_open_report_tasks",
        "action_cn_open_report_evidence",
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
    report_view_root = ElementTree.parse(
        ADDON_ROOT / "views" / "compliance_report_views.xml"
    ).getroot()

    def report_view_field_names(record_id: str) -> set[str]:
        arch = report_view_root.find(
            f".//record[@id='{record_id}']/field[@name='arch']"
        )
        if arch is None:
            fail(f"formal report UX view contract is missing record {record_id}")
        return {
            element.attrib["name"]
            for element in arch.iter("field")
            if element.attrib.get("name")
        }

    report_list_fields = report_view_field_names(
        "view_cn_formal_compliance_report_list"
    )
    report_kanban_fields = report_view_field_names(
        "view_cn_formal_compliance_report_kanban"
    )
    report_form_fields = report_view_field_names(
        "view_cn_formal_compliance_report_form"
    )
    required_report_summary_fields = {
        "cn_report_center_stage",
        "cn_report_center_next_action",
        "cn_report_blocker_summary",
        "cn_report_traceability_state",
        "cn_report_traceability_gap_count",
        "cn_report_fact_basis_state",
        "fact_snapshot_count",
        "fact_issue_count",
        "critical_count",
        "high_count",
        "finding_closure_blocked_count",
        "finding_closure_action_required_count",
        "open_task_count",
        "remediation_pending_verification_count",
        "conclusion_state",
        "state",
        "reviewer_id",
        "cn_report_center_integrity_state",
    }
    for record_id, fields in (
        ("view_cn_formal_compliance_report_list", report_list_fields),
        ("view_cn_formal_compliance_report_kanban", report_kanban_fields),
    ):
        missing = required_report_summary_fields - fields
        if missing:
            fail(
                "formal report summary views must expose clear stage, conclusion, "
                "fact basis, traceability, risk counts, remediation counts, "
                f"reviewer and next action fields in {record_id}: {sorted(missing)}"
            )
    required_report_form_fields = required_report_summary_fields | {
        "assessment_id",
        "profile_id",
        "company_id",
        "period_start",
        "period_end",
        "executive_summary",
        "scope_statement",
        "limitation_statement",
        "management_response",
        "tax_impact_pending_count",
        "reviewed_underpayment_amount",
        "reviewed_overpayment_amount",
        "reviewed_timing_amount",
        "snapshot_checksum",
        "approval_checksum",
        "issued_pdf_sha256",
    }
    missing_form_fields = required_report_form_fields - report_form_fields
    if missing_form_fields:
        fail(
            "formal report form must expose scope, summary, limitations, tax "
            "impact, traceability, audit hashes and next action fields: "
            f"{sorted(missing_form_fields)}"
        )
    for required in (
        'id="view_cn_formal_compliance_report_kanban"',
        'id="view_cn_formal_compliance_report_list"',
        'id="view_cn_formal_compliance_report_form"',
        'id="action_cn_formal_compliance_reports"',
        'id="menu_cn_formal_compliance_reports"',
        "kanban,list,form",
        "cn_report_center_stage",
        "cn_report_center_integrity_state",
        "cn_report_center_next_action",
        "cn_report_blocker_summary",
        "cn_report_traceability_state",
        "cn_report_traceability_gap_count",
        "cn_report_traceability_next_action",
        "remediation_pending_verification_count",
        "remediation_verified_count",
        "action_cn_open_report_findings",
        "action_cn_open_report_tasks",
        "action_cn_open_report_evidence",
        "提交独立批准",
        "批准并签发",
        "下载已签发 PDF",
        "源资料已变化",
        "PDF 完整性异常",
    ):
        if required not in view_content:
            fail(f"formal compliance report UI is missing {required}")
    for required in (
        'decoration-success="cn_report_center_stage == \'issued\'"',
        'decoration-success="cn_report_center_integrity_state == \'verified\'"',
        'decoration-success="cn_report_traceability_state == \'complete\'"',
        'decoration-success="snapshot_integrity_state == \'verified\'"',
    ):
        if required not in view_content:
            fail(f"formal compliance report badge clarity UI is missing {required}")

    report_content = (
        ADDON_ROOT / "reports" / "compliance_report.xml"
    ).read_text(encoding="utf-8")
    for required in (
        "finding_closure_blocked_count",
        "finding_closure_action_required_count",
        "finding_closure_ready_count",
        "report.report_label('closure'",
        "finding.get('closure_summary')",
        "Rule basis:",
        "finding.get('legal_basis')",
        "Evidence required:",
        "finding.get('evidence_required')",
        "Basis warning:",
        "finding.get('source_warning')",
        "finding.get('professional_warning')",
        "Source snapshot:",
        "finding.get('source_snapshot')",
        "source.get('status')",
        "Professional review snapshot:",
        "finding.get('professional_snapshot')",
        "Controlled AI metadata",
        "analysis.get('provider_key')",
        "analysis.get('model_name')",
        "analysis.get('prompt_version')",
        "analysis.get('input_checksum')",
        "analysis.get('record_checksum')",
        "Data basis snapshot",
        "data_basis.get('ready_dataset_count'",
        "data_basis.get('missing_type_summary')",
        "accounting_basis.get('posted_move_count'",
        "accounting_basis.get('draft_move_count'",
        "accounting_basis.get('posted_invoice_count'",
        "Filing/payment archive snapshot",
        "filing_archive.get('sealed_count'",
        "filing_archive.get('archive_count'",
        "filing_archive.get('issue_count'",
        "archive.get('submission_integrity_state')",
        "archive.get('payment_integrity_state')",
        "archive.get('evidence_state')",
        "archive.get('submission_checksum')",
        "archive.get('payment_checksum')",
        "Evidence link context",
        "evidence.get('links')",
        "links.get('assessment')",
        "links.get('finding')",
        "links.get('task')",
        "links.get('filing')",
    ):
        if required not in report_content:
            fail(f"formal compliance report risk closure PDF is missing {required}")
    for required in (
        '<field name="binding_model_id" eval="False"/>',
        "不是纳税申报表、税务鉴证报告、法律意见、审计意见或税务机关认定",
        "潜在少缴、潜在多缴和期间错配影响分别列示",
        "不计算净额",
        "AI 分析仅为辅助材料",
        "纳税义务适用性边界",
        "待验证复扫",
        "verification_assessment_name",
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
        "test_closed_task_without_verification_still_requires_action",
        "test_same_person_approval_requires_recorded_exception",
        "test_new_issue_supersedes_previous_report_without_rewriting_pdf",
        "test_submission_freezes_evidence_link_context",
        "test_withdrawal_preserves_artifact_and_audit_history",
        "test_read_only_user_cannot_prepare_or_mutate_report",
        "test_report_is_company_isolated_and_reviewer_must_have_company",
        "test_only_designated_approver_can_return_or_issue",
        "test_report_html_preserves_boundary_and_non_net_tax_impact",
        "test_report_center_exposes_stage_next_action_and_navigation",
        "test_country_pack_advertises_report_center_visibility",
        "test_pending_obligations_require_report_limitation",
    ):
        if f"def {test_name}(" not in test_content:
            fail(f"formal report runtime coverage is missing {test_name}")
    for required in (
        "china_traceability_matrix_visibility",
        "china_report_obligation_readiness",
        "china_report_remediation_verification",
        "china_report_filing_archive_snapshot",
        "china_report_risk_closure_snapshot",
        "china_formal_report_badge_clarity",
        "cn_report_blocker_summary",
        "remediation_pending_verification_count",
        "finding_closure_blocked_count",
        "closure_state",
        "closure_summary",
        "风险闭环阻断",
        "风险闭环待处理",
        "风险闭环可报告",
        "Rule basis:",
        "Evidence required:",
        "Source snapshot:",
        "Professional review snapshot:",
        "Data basis snapshot",
        "Accounting basis",
        "Filing/payment archive snapshot",
        "Submission / payment / evidence",
        "obligation_readiness",
        "filing_archive",
        "cn_report_traceability_state",
        "cn_report_traceability_gap_count",
        "action_cn_open_report_evidence",
    ):
        if required not in test_content:
            fail(f"formal report traceability coverage is missing {required}")


def validate_official_source_change_monitoring() -> None:
    manifest = ast.literal_eval(
        (ADDON_ROOT / "__manifest__.py").read_text(encoding="utf-8")
    )
    required_data_files = {
        "data/source_monitoring_cron.xml",
        "views/source_monitoring_views.xml",
    }
    if not required_data_files.issubset(manifest.get("data", [])):
        fail("official source monitoring files must be loaded by the manifest")

    model_init = (ADDON_ROOT / "models" / "__init__.py").read_text(
        encoding="utf-8"
    )
    if "from . import source_monitoring" not in model_init:
        fail("official source monitoring model must be imported")

    model_content = (
        ADDON_ROOT / "models" / "source_monitoring.py"
    ).read_text(encoding="utf-8")
    for required in (
        "SourceBaselineIntegrityError",
        "_CN_SOURCE_MONITOR_SCHEDULE_MARKER",
        'source.with_context(lang="en_US").snapshot_payload()',
        "source._download_official_snapshot",
        "source.action_mark_change_detected()",
        "_create_change_candidate",
        '"official_version": False',
        '"published_date": False',
        '"cn_monitor_enabled": False',
        "candidate_integrity_state",
        "result_integrity_state",
        "impact_snapshot_checksum",
        "FOR UPDATE SKIP LOCKED",
        "models.UniqueIndex",
    ):
        if required not in model_content:
            fail(f"official source monitoring contract is missing {required}")
    for forbidden in (
        "action_approve(",
        "action_submit_review(",
        "action_professional_signoff(",
        "action_activate(",
    ):
        if forbidden in model_content:
            fail(
                "source monitoring must not automatically approve sources or "
                f"rules: {forbidden}"
            )

    candidates = (
        ADDON_ROOT / "data" / "official_source_candidates.xml"
    ).read_text(encoding="utf-8")
    for forbidden in (
        'name="cn_monitor_enabled"',
        'name="cn_next_monitor_date"',
        'name="cn_last_monitor_state"',
    ):
        if forbidden in candidates:
            fail("packaged official source candidates must not start monitoring")

    cron_content = (
        ADDON_ROOT / "data" / "source_monitoring_cron.xml"
    ).read_text(encoding="utf-8")
    for required in (
        "_cron_enqueue_due_sources(limit=20)",
        "_cron_process_runs(limit=2)",
    ):
        if required not in cron_content:
            fail(f"bounded source monitoring cron is missing {required}")

    view_content = (
        ADDON_ROOT / "views" / "source_monitoring_views.xml"
    ).read_text(encoding="utf-8")
    for required in (
        "检查远端变化",
        "来源时效监控",
        "原批准快照未被覆盖",
        "必须经过来源独立复核和规则影响判断",
        "检查失败不会把原来源解释为未变化",
        "受影响规则",
    ):
        if required not in view_content:
            fail(f"official source monitoring UI is missing {required}")

    access_path = ADDON_ROOT / "security" / "ir.model.access.csv"
    with access_path.open(encoding="utf-8", newline="") as handle:
        access_rows = {row["id"]: row for row in csv.DictReader(handle)}
    expected_access = {
        "access_cn_source_monitor_run_user": ["1", "0", "0", "0"],
        "access_cn_source_monitor_run_author": ["1", "1", "1", "0"],
        "access_cn_source_monitor_run_approver": ["1", "0", "0", "0"],
        "access_cn_source_monitor_run_manager": ["1", "1", "1", "0"],
    }
    for access_id, expected in expected_access.items():
        row = access_rows.get(access_id)
        if not row:
            fail(f"official source monitoring ACL is missing {access_id}")
        actual = [
            row[key]
            for key in ("perm_read", "perm_write", "perm_create", "perm_unlink")
        ]
        if actual != expected:
            fail(f"official source monitoring ACL is unsafe: {access_id}")

    tests_init = (ADDON_ROOT / "tests" / "__init__.py").read_text(
        encoding="utf-8"
    )
    if "from . import test_source_monitoring" not in tests_init:
        fail("official source monitoring runtime tests must be imported")
    test_path = ADDON_ROOT / "tests" / "test_source_monitoring.py"
    test_content = test_path.read_text(encoding="utf-8")
    test_tree = ast.parse(test_content)
    test_methods = sum(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
        for node in ast.walk(test_tree)
    )
    if test_methods < 11:
        fail("official source monitoring requires at least eleven runtime tests")
    for test_name in (
        "test_packaged_candidates_remain_draft_and_unmonitored",
        "test_unchanged_remote_content_preserves_approved_source",
        "test_changed_content_creates_draft_and_snapshots_rule_impact",
        "test_network_failure_does_not_claim_source_is_unchanged",
        "test_approved_snapshot_tampering_quarantines_source",
        "test_cron_only_queues_due_valid_enabled_sources",
        "test_scheduled_request_cannot_be_spoofed",
        "test_frozen_snapshot_tampering_breaks_result_integrity",
    ):
        if f"def {test_name}(" not in test_content:
            fail(f"official source monitoring runtime coverage is missing {test_name}")


def validate_china_jurisdiction_governance(manifest: dict[str, object]) -> None:
    data_files = set(manifest.get("data", []))
    for required in (
        "views/jurisdiction_views.xml",
        "security/compliance_security.xml",
        "security/ir.model.access.csv",
    ):
        if required not in data_files:
            fail(f"China jurisdiction governance file is not loaded: {required}")

    forbidden_seed_models = {
        "sudo.cn.jurisdiction.version",
        "sudo.cn.profile.jurisdiction",
    }
    for relative_path in manifest.get("data", []):
        if not relative_path.endswith(".xml"):
            continue
        root = ElementTree.parse(ADDON_ROOT / relative_path).getroot()
        for record in root.findall(".//record"):
            if record.attrib.get("model") in forbidden_seed_models:
                fail("packaged China pack must not seed active jurisdiction data")

    model_init = (ADDON_ROOT / "models" / "__init__.py").read_text(
        encoding="utf-8"
    )
    if "from . import jurisdiction" not in model_init:
        fail("China jurisdiction model must be imported")

    model_content = (
        ADDON_ROOT / "models" / "jurisdiction.py"
    ).read_text(encoding="utf-8")
    for required in (
        '_name = "sudo.cn.jurisdiction.version"',
        '_name = "sudo.cn.profile.jurisdiction"',
        'selection_add=[("jurisdiction_governance"',
        "_source_snapshot_matches_hash",
        "cn_jurisdiction_ids",
        "cn_jurisdiction_scope_state",
        "cn_jurisdiction_coverage_state",
        "cn_jurisdiction_scope_snapshot_json",
        "cn_jurisdiction_scope_checksum",
        "_select_versions",
        "_cn_jurisdiction_scope_write",
        "_ASSESSMENT_SCOPE_MARKER",
        "_JURISDICTION_TRANSITION_MARKER",
        "_ASSIGNMENT_TRANSITION_MARKER",
        "cn_is_china_assessment",
    ):
        if required not in model_content:
            fail(f"China jurisdiction governance contract is missing {required}")
    if "if self.cn_jurisdiction_ids:" not in model_content:
        fail("empty China jurisdiction scope must preserve national rule checksum")
    if '"jurisdiction_governance": "set null"' not in model_content:
        fail("jurisdiction release state must use a safe uninstall fallback")
    for forbidden in (
        "create_jurisdiction_seed",
        "default_active_jurisdiction",
        "auto_activate_jurisdiction",
    ):
        if forbidden in model_content:
            fail(f"China jurisdiction governance must not auto-seed: {forbidden}")

    view_content = (
        ADDON_ROOT / "views" / "jurisdiction_views.xml"
    ).read_text(encoding="utf-8")
    for required in (
        'id="action_cn_jurisdiction_versions"',
        'id="menu_cn_jurisdiction_versions"',
        'id="action_cn_profile_jurisdictions"',
        'id="menu_cn_profile_jurisdictions"',
        "cn_jurisdiction_assignment_ids",
        "cn_jurisdiction_scope_state",
        "cn_jurisdiction_coverage_state",
        "cn_is_china_assessment",
    ):
        if required not in view_content:
            fail(f"China jurisdiction governance UI is missing {required}")
    if "default_active" in view_content:
        fail("China jurisdiction action must not hide draft jurisdictions by default")

    with (ADDON_ROOT / "security" / "ir.model.access.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = {row["id"]: row for row in csv.DictReader(handle)}
    expected_access = {
        "access_cn_jurisdiction_version_user": ["1", "0", "0", "0"],
        "access_cn_jurisdiction_version_author": ["1", "1", "1", "1"],
        "access_cn_jurisdiction_version_approver": ["1", "1", "0", "0"],
        "access_cn_jurisdiction_version_manager": ["1", "1", "1", "1"],
        "access_cn_profile_jurisdiction_user": ["1", "1", "1", "0"],
        "access_cn_profile_jurisdiction_manager": ["1", "1", "1", "1"],
    }
    for access_id, expected in expected_access.items():
        row = rows.get(access_id)
        if not row:
            fail(f"China jurisdiction ACL is missing {access_id}")
        actual = [
            row[key]
            for key in ("perm_read", "perm_write", "perm_create", "perm_unlink")
        ]
        if actual != expected:
            fail(f"China jurisdiction ACL is unsafe: {access_id}")

    security = (
        ADDON_ROOT / "security" / "compliance_security.xml"
    ).read_text(encoding="utf-8")
    for required in (
        'id="cn_profile_jurisdiction_company_rule"',
        'ref="model_sudo_cn_profile_jurisdiction"',
        "[('company_id', 'in', company_ids)]",
    ):
        if required not in security:
            fail(f"China jurisdiction company isolation is missing {required}")

    tests_init = (ADDON_ROOT / "tests" / "__init__.py").read_text(
        encoding="utf-8"
    )
    if "from . import test_jurisdiction" not in tests_init:
        fail("China jurisdiction runtime tests must be imported")
    test_path = ADDON_ROOT / "tests" / "test_jurisdiction.py"
    test_content = test_path.read_text(encoding="utf-8")
    test_tree = ast.parse(test_content)
    test_methods = sum(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
        for node in ast.walk(test_tree)
    )
    if test_methods < 16:
        fail("China jurisdiction governance requires at least sixteen runtime tests")
    for test_name in (
        "test_packaged_country_pack_does_not_seed_active_jurisdictions_or_local_rules",
        "test_jurisdiction_create_cannot_forge_governance_state",
        "test_jurisdiction_requires_independent_review_and_freezes_checksum",
        "test_invalid_official_source_blocks_jurisdiction",
        "test_hierarchy_cycle_and_parent_period_are_guarded",
        "test_active_jurisdiction_is_immutable_and_source_tamper_is_visible",
        "test_assignment_requires_complete_evidence",
        "test_assignment_verification_freezes_evidence_and_detects_tamper",
        "test_overlapping_verified_assignment_is_rejected",
        "test_assignment_record_rule_isolates_companies",
        "test_local_rule_scope_changes_checksum_and_publish_gate",
        "test_descendant_assignment_selects_matching_rule_and_excludes_other_scope",
        "test_missing_assignment_limits_assessment_while_national_rule_runs",
        "test_tampered_assignment_blocks_local_rule_as_integrity_error",
        "test_explicit_out_of_scope_rule_is_rejected",
        "test_assessment_scope_fields_cannot_be_forged_and_snapshot_tamper_is_detected",
    ):
        if f"def {test_name}(" not in test_content:
            fail(f"China jurisdiction runtime coverage is missing {test_name}")


def validate_china_compliance_workbench(manifest: dict[str, object]) -> None:
    data_files = set(manifest.get("data", []))
    if "views/workbench_views.xml" not in data_files:
        fail("China compliance workbench view must be loaded")
    if "views/risk_center_views.xml" not in data_files:
        fail("China risk center view must be loaded")
    if "views/report_readiness_views.xml" not in data_files:
        fail("China report readiness view must be loaded")
    if "views/ai_guidance_views.xml" not in data_files:
        fail("China AI guidance view must be loaded")
    if "views/evidence_center_views.xml" not in data_files:
        fail("China evidence center view must be loaded")
    if "views/filing_center_views.xml" not in data_files:
        fail("China filing center view must be loaded")
    if "views/data_readiness_center_views.xml" not in data_files:
        fail("China data readiness center view must be loaded")
    if "views/cross_border_views.xml" not in data_files:
        fail("China cross-border transaction view must be loaded")

    model_init = (ADDON_ROOT / "models" / "__init__.py").read_text(
        encoding="utf-8"
    )
    if "from . import workbench" not in model_init:
        fail("China compliance workbench model must be imported")
    if "from . import cross_border" not in model_init:
        fail("China cross-border transaction model must be imported")

    hook_content = (ADDON_ROOT / "hooks.py").read_text(encoding="utf-8")
    data_content = (
        ADDON_ROOT / "data" / "country_pack_data.xml"
    ).read_text(encoding="utf-8")
    for content, label in (
        (hook_content, "hook metadata"),
        (data_content, "country pack data"),
    ):
        if "china_compliance_workbench" not in content:
            fail(f"China workbench capability is missing from {label}")
        for required in ("china_risk_center", "china_remediation_tracker"):
            if required not in content:
                fail(f"China risk UX capability is missing from {label}: {required}")
        if "china_report_readiness" not in content:
            fail(f"China report readiness capability is missing from {label}")
        if "china_report_obligation_readiness" not in content:
            fail(f"China report obligation readiness capability is missing from {label}")
        if "china_report_remediation_verification" not in content:
            fail(f"China report remediation verification capability is missing from {label}")
        if "china_report_rescan_gate" not in content:
            fail(f"China report rescan gate capability is missing from {label}")
        if "china_report_filing_archive_gate" not in content:
            fail(f"China report filing archive gate capability is missing from {label}")
        if "china_report_filing_archive_snapshot" not in content:
            fail(
                f"China report filing archive snapshot capability is missing from {label}"
            )
        if "china_controlled_ai_guidance" not in content:
            fail(f"China controlled AI guidance capability is missing from {label}")
        if "china_ai_guidance_visibility" not in content:
            fail(f"China AI guidance visibility capability is missing from {label}")
        if "china_ai_obligation_context" not in content:
            fail(f"China AI obligation context capability is missing from {label}")
        if "china_ai_filing_archive_context" not in content:
            fail(f"China AI filing archive context capability is missing from {label}")
        if "china_evidence_center" not in content:
            fail(f"China evidence center capability is missing from {label}")
        if "china_process_visibility" not in content:
            fail(f"China process visibility capability is missing from {label}")
        if "china_risk_action_guidance" not in content:
            fail(f"China risk action guidance capability is missing from {label}")
        if "china_filing_center" not in content:
            fail(f"China filing center capability is missing from {label}")
        if "china_data_readiness_center" not in content:
            fail(f"China data readiness center capability is missing from {label}")
        if "china_assessment_data_basis" not in content:
            fail(f"China assessment data basis capability is missing from {label}")
        if "china_assessment_obligation_basis" not in content:
            fail(f"China assessment obligation basis capability is missing from {label}")
        if "china_remediation_rescan_visibility" not in content:
            fail(f"China remediation rescan capability is missing from {label}")
        if "china_risk_rule_basis_visibility" not in content:
            fail(f"China risk rule basis capability is missing from {label}")
        if "china_traceability_matrix_visibility" not in content:
            fail(f"China traceability matrix capability is missing from {label}")
        if "china_workbench_tax_domain_overview" not in content:
            fail(f"China tax domain overview capability is missing from {label}")
        if "china_obligation_readiness_visibility" not in content:
            fail(f"China obligation readiness capability is missing from {label}")
        if "china_workbench_cross_border_overview" not in content:
            fail(f"China cross-border overview capability is missing from {label}")
        if "china_cross_border_transaction_register" not in content:
            fail(
                f"China cross-border transaction register capability is missing from {label}"
            )
        if "china_cross_border_rule_facts" not in content:
            fail(f"China cross-border rule facts capability is missing from {label}")
        if "china_cross_border_risk_visibility" not in content:
            fail(
                f"China cross-border risk visibility capability is missing from {label}"
            )
        if "china_workbench_filing_archive_summary" not in content:
            fail(
                f"China filing archive workbench summary capability is missing from {label}"
            )
        if "china_workbench_state_badge_clarity" not in content:
            fail(
                f"China workbench state badge clarity capability is missing from {label}"
            )
        if "china_risk_card_state_badge_clarity" not in content:
            fail(
                f"China risk card state badge clarity capability is missing from {label}"
            )
        if "china_report_readiness_badge_clarity" not in content:
            fail(
                f"China report readiness badge clarity capability is missing from {label}"
            )
        if "china_archive_evidence_badge_clarity" not in content:
            fail(
                f"China archive and evidence badge clarity capability is missing from {label}"
            )
        if "china_data_readiness_badge_clarity" not in content:
            fail(
                f"China data readiness badge clarity capability is missing from {label}"
            )
        if "china_workbench_data_readiness_summary" not in content:
            fail(
                f"China workbench data readiness summary capability is missing from {label}"
            )
        if "china_workbench_remediation_rescan_summary" not in content:
            fail(
                f"China workbench remediation rescan summary capability is missing from {label}"
            )
        if "china_workbench_next_best_action" not in content:
            fail(
                f"China workbench next-best-action capability is missing from {label}"
            )
        if "china_delivery_objective_coverage" not in content:
            fail(
                f"China delivery objective coverage capability is missing from {label}"
            )
        if "china_business_uat_checklist" not in content:
            fail(f"China business UAT checklist capability is missing from {label}")
        if "china_production_signoff_template" not in content:
            fail(
                f"China production sign-off template capability is missing from {label}"
            )
        if "china_delivery_preview_health_checker" not in content:
            fail(
                f"China delivery preview health checker capability is missing from {label}"
            )
        if "china_delivery_index" not in content:
            fail(f"China delivery index capability is missing from {label}")
        if "china_delivery_readiness_gates" not in content:
            fail(f"China delivery readiness gates capability is missing from {label}")
        if "china_delivery_preview_health_gate" not in content:
            fail(f"China delivery preview health gate capability is missing from {label}")
        if "china_delivery_preview_url_match_gate" not in content:
            fail(
                f"China delivery preview URL match gate capability is missing from {label}"
            )
        if "china_delivery_strict_readiness_exit" not in content:
            fail(
                f"China delivery strict readiness exit capability is missing from {label}"
            )
        if "china_delivery_source_control_traceability" not in content:
            fail(
                f"China delivery source control traceability capability is missing from {label}"
            )
        if "china_delivery_source_control_clean_gate" not in content:
            fail(
                f"China delivery source control clean gate capability is missing from {label}"
            )
        if "china_delivery_commit_consistency_gate" not in content:
            fail(
                f"China delivery commit consistency gate capability is missing from {label}"
            )
        if "china_delivery_preview_module_gate" not in content:
            fail(
                f"China delivery preview module gate capability is missing from {label}"
            )
        if "china_real_data_closed_loop_checker" not in content:
            fail(
                f"China real-data closed-loop checker capability is missing from {label}"
            )
        if "china_controlled_demo_profile_preparer" not in content:
            fail(
                f"China controlled demo profile preparer capability is missing from {label}"
            )

    model_content = (
        ADDON_ROOT / "models" / "workbench.py"
    ).read_text(encoding="utf-8")
    for required in (
        '_inherit = "sudo.compliance.profile"',
        "cn_workbench_status",
        "cn_workbench_high_risk_count",
        "cn_workbench_open_task_count",
        "cn_workbench_pending_tax_impact_count",
        "cn_workbench_underpayment_amount",
        "cn_workbench_vat_issue_count",
        "cn_workbench_cit_issue_count",
        "cn_workbench_iit_issue_count",
        "cn_workbench_package_label",
        "cn_workbench_scope_label",
        "cn_workbench_data_state",
        "cn_workbench_data_next_action",
        "cn_workbench_dataset_count",
        "cn_workbench_ready_dataset_count",
        "sudo.cn.external.dataset",
        "cn_workbench_vat_domain_state",
        "cn_workbench_cit_domain_state",
        "cn_workbench_iit_domain_state",
        "cn_workbench_vat_next_action",
        "cn_workbench_cit_next_action",
        "cn_workbench_iit_next_action",
        "cn_workbench_obligation_state",
        "cn_workbench_obligation_next_action",
        "cn_workbench_obligation_count",
        "cn_workbench_applicable_obligation_count",
        "cn_workbench_pending_obligation_count",
        "cn_workbench_filing_obligation_count",
        "action_cn_open_workbench_obligations",
        "cn_workbench_cross_border_state",
        "cn_workbench_cross_border_basis",
        "cn_workbench_cross_border_next_action",
        "cn_workbench_cross_border_transaction_count",
        "cn_workbench_cross_border_pending_count",
        "action_cn_open_workbench_taxpayer_classifications",
        "cn_workbench_scan_state",
        "cn_workbench_risk_state",
        "cn_workbench_remediation_state",
        "cn_workbench_rescan_state",
        "cn_workbench_pending_rescan_count",
        "cn_workbench_failed_rescan_count",
        "cn_workbench_verified_remediation_count",
        "cn_workbench_rescan_next_action",
        "cn_workbench_report_state",
        "cn_workbench_evidence_state",
        "cn_workbench_evidence_count",
        "cn_workbench_verified_evidence_count",
        "cn_workbench_filing_archive_state",
        "cn_workbench_filing_archive_next_action",
        "cn_workbench_filing_archive_count",
        "cn_workbench_sealed_filing_archive_count",
        "cn_workbench_filing_archive_issue_count",
        "cn_workbench_rule_basis_state",
        "cn_workbench_rule_basis_summary",
        "cn_workbench_rule_basis_next_action",
        "cn_workbench_rule_version_count",
        "cn_workbench_active_rule_version_count",
        "cn_workbench_rule_governance_issue_count",
        "cn_workbench_rule_pending_professional_count",
        "cn_workbench_source_review_overdue_count",
        "cn_workbench_source_monitor_issue_count",
        "cn_workbench_limitation_summary",
        "cn_workbench_uncertainty_summary",
        "cn_workbench_limitation_next_action",
        "action_cn_open_workbench_rule_basis",
        "cn_workbench_next_best_action_key",
        "cn_workbench_next_best_action_label",
        "cn_workbench_action_summary",
        "_cn_workbench_action_summary",
        "action_cn_open_workbench_next_best_action",
        "action_cn_open_workbench_findings",
        "action_cn_open_workbench_tasks",
        "action_cn_open_workbench_tax_impacts",
        "action_cn_open_workbench_reports",
        "action_cn_risk_center",
        "action_cn_remediation_tracker",
        "action_cn_open_workbench_report_readiness",
        "action_cn_report_readiness",
    ):
        if required not in model_content:
            fail(f"China workbench contract is missing {required}")

    view_content = (
        ADDON_ROOT / "views" / "workbench_views.xml"
    ).read_text(encoding="utf-8")
    workbench_view_root = ElementTree.parse(
        ADDON_ROOT / "views" / "workbench_views.xml"
    ).getroot()

    def workbench_view_field_names(record_id: str) -> set[str]:
        arch = workbench_view_root.find(
            f".//record[@id='{record_id}']/field[@name='arch']"
        )
        if arch is None:
            fail(f"China workbench UX view contract is missing record {record_id}")
        return {
            element.attrib["name"]
            for element in arch.iter("field")
            if element.attrib.get("name")
        }

    workbench_list_fields = workbench_view_field_names(
        "view_cn_compliance_workbench_list"
    )
    required_workbench_list_fields = {
        "company_id",
        "name",
        "cn_workbench_status",
        "cn_workbench_period_label",
        "cn_workbench_closed_loop_state",
        "cn_workbench_closed_loop_gap_count",
        "cn_workbench_closed_loop_summary",
        "cn_workbench_conclusion_boundary_state",
        "cn_workbench_conclusion_boundary_summary",
        "cn_workbench_next_best_action_label",
        "cn_workbench_action_summary",
        "cn_workbench_rule_basis_state",
        "cn_workbench_rule_basis_summary",
        "cn_workbench_rule_governance_issue_count",
        "cn_workbench_rule_pending_professional_count",
        "cn_workbench_source_review_overdue_count",
        "cn_workbench_source_monitor_issue_count",
        "cn_workbench_limitation_summary",
        "cn_workbench_uncertainty_summary",
        "cn_workbench_limitation_next_action",
        "cn_workbench_data_state",
        "cn_workbench_ready_dataset_count",
        "cn_workbench_dataset_count",
        "cn_workbench_high_risk_count",
        "cn_workbench_open_task_count",
        "cn_workbench_overdue_task_count",
        "cn_workbench_pending_review_count",
        "cn_workbench_ai_guidance_state",
        "cn_workbench_pending_tax_impact_count",
        "cn_workbench_underpayment_amount",
        "cn_workbench_reconciliation_issue_count",
        "cn_workbench_next_action",
    }
    missing_workbench_list_fields = (
        required_workbench_list_fields - workbench_list_fields
    )
    if missing_workbench_list_fields:
        fail(
            "China workbench list must expose scope, readiness, rule basis, "
            "limitations, data, risk, remediation, tax impact and next action "
            f"fields: {sorted(missing_workbench_list_fields)}"
        )

    workbench_kanban_fields = workbench_view_field_names(
        "view_cn_compliance_workbench_kanban"
    )
    required_workbench_kanban_fields = required_workbench_list_fields | {
        "cn_workbench_package_label",
        "cn_workbench_scope_label",
        "cn_workbench_finding_count",
        "cn_workbench_tax_impact_case_count",
        "cn_workbench_data_next_action",
        "cn_workbench_posted_move_count",
        "cn_workbench_draft_move_count",
        "cn_workbench_posted_invoice_count",
        "cn_workbench_scan_state",
        "cn_workbench_risk_state",
        "cn_workbench_remediation_state",
        "cn_workbench_rescan_state",
        "cn_workbench_pending_rescan_count",
        "cn_workbench_failed_rescan_count",
        "cn_workbench_verified_remediation_count",
        "cn_workbench_rescan_next_action",
        "cn_workbench_report_state",
        "cn_workbench_evidence_state",
        "cn_workbench_evidence_count",
        "cn_workbench_verified_evidence_count",
        "cn_workbench_filing_archive_state",
        "cn_workbench_filing_archive_next_action",
        "cn_workbench_filing_archive_count",
        "cn_workbench_sealed_filing_archive_count",
        "cn_workbench_filing_archive_issue_count",
        "cn_workbench_ai_guidance_next_action",
        "cn_workbench_ai_guidance_finding_count",
        "cn_workbench_ai_guidance_generated_count",
        "cn_workbench_ai_guidance_current_count",
        "cn_workbench_ai_guidance_limited_count",
        "cn_workbench_ai_guidance_stale_count",
        "cn_workbench_vat_domain_state",
        "cn_workbench_cit_domain_state",
        "cn_workbench_iit_domain_state",
        "cn_workbench_vat_next_action",
        "cn_workbench_cit_next_action",
        "cn_workbench_iit_next_action",
        "cn_workbench_obligation_state",
        "cn_workbench_obligation_next_action",
        "cn_workbench_obligation_count",
        "cn_workbench_applicable_obligation_count",
        "cn_workbench_pending_obligation_count",
        "cn_workbench_filing_obligation_count",
        "cn_workbench_cross_border_state",
        "cn_workbench_cross_border_basis",
        "cn_workbench_cross_border_next_action",
        "cn_workbench_cross_border_transaction_count",
        "cn_workbench_cross_border_pending_count",
        "cn_workbench_conclusion_boundary_next_action",
        "cn_workbench_rule_basis_next_action",
        "cn_workbench_rule_version_count",
        "cn_workbench_active_rule_version_count",
    }
    missing_workbench_kanban_fields = (
        required_workbench_kanban_fields - workbench_kanban_fields
    )
    if missing_workbench_kanban_fields:
        fail(
            "China workbench kanban must expose the complete compliance "
            "closed loop, data/accounting basis, rule governance, tax domains, "
            "risk, remediation, rescan, AI guidance, evidence, filing archive "
            f"and next action fields: {sorted(missing_workbench_kanban_fields)}"
        )
    for required in (
        'id="action_cn_compliance_workbench"',
        'id="menu_cn_compliance_workbench"',
        'view_mode">kanban,list,form',
        "cn_workbench_status",
        "cn_workbench_next_action",
        "cn_workbench_package_label",
        "cn_workbench_scope_label",
        "cn_workbench_data_state",
        "cn_workbench_data_next_action",
        "cn_workbench_dataset_count",
        "cn_workbench_ready_dataset_count",
        "cn_workbench_vat_domain_state",
        "cn_workbench_cit_domain_state",
        "cn_workbench_iit_domain_state",
        "cn_workbench_vat_next_action",
        "cn_workbench_cit_next_action",
        "cn_workbench_iit_next_action",
        "cn_workbench_obligation_state",
        "cn_workbench_obligation_next_action",
        "cn_workbench_obligation_count",
        "cn_workbench_applicable_obligation_count",
        "cn_workbench_pending_obligation_count",
        "cn_workbench_filing_obligation_count",
        "action_cn_open_workbench_obligations",
        "cn_workbench_cross_border_state",
        "cn_workbench_cross_border_basis",
        "cn_workbench_cross_border_next_action",
        "cn_workbench_cross_border_transaction_count",
        "cn_workbench_cross_border_pending_count",
        "action_cn_open_workbench_cross_border_transactions",
        "action_cn_open_workbench_assessments",
        "action_cn_open_workbench_vat_issues",
        "action_cn_open_workbench_cit_issues",
        "action_cn_open_workbench_iit_issues",
        "action_cn_open_workbench_report_readiness",
        "action_cn_open_workbench_data_readiness",
        "action_cn_open_workbench_evidence_center",
        "action_cn_open_workbench_filing_center",
        "cn_workbench_next_best_action_key",
        "cn_workbench_next_best_action_label",
        "cn_workbench_action_summary",
        "cn_workbench_rule_basis_state",
        "cn_workbench_rule_basis_summary",
        "cn_workbench_rule_basis_next_action",
        "cn_workbench_rule_governance_issue_count",
        "cn_workbench_rule_pending_professional_count",
        "cn_workbench_source_review_overdue_count",
        "cn_workbench_source_monitor_issue_count",
        "cn_workbench_limitation_summary",
        "cn_workbench_uncertainty_summary",
        "cn_workbench_limitation_next_action",
        "action_cn_open_workbench_rule_basis",
        "action_cn_open_workbench_next_best_action",
        "下一步最佳动作",
        "行动摘要",
        "规则依据",
        "限制与不确定性",
        'decoration-success="cn_workbench_data_state == \'ready\'"',
        'decoration-danger="cn_workbench_data_state == \'blocked\'"',
        "可扫描 / 总数据集",
        "cn_workbench_scan_state",
        "cn_workbench_risk_state",
        "cn_workbench_remediation_state",
        "cn_workbench_rescan_state",
        "cn_workbench_pending_rescan_count",
        "cn_workbench_failed_rescan_count",
        "cn_workbench_verified_remediation_count",
        "cn_workbench_rescan_next_action",
        "cn_workbench_report_state",
        "cn_workbench_evidence_state",
        "cn_workbench_verified_evidence_count",
        "cn_workbench_evidence_count",
        "cn_workbench_filing_archive_state",
        "cn_workbench_filing_archive_next_action",
        "cn_workbench_filing_archive_count",
        "cn_workbench_sealed_filing_archive_count",
        "cn_workbench_filing_archive_issue_count",
        'decoration-success="cn_workbench_scan_state == \'ready\'"',
        'decoration-warning="cn_workbench_risk_state == \'attention\'"',
        'decoration-danger="cn_workbench_remediation_state == \'blocked\'"',
        'decoration-muted="cn_workbench_filing_archive_state == \'not_started\'"',
    ):
        if required not in view_content:
            fail(f"China workbench UI is missing {required}")
    if "group_by': 'cn_workbench_status'" in view_content:
        fail("China workbench must not group by a non-stored computed status")
    if "('cn_workbench_status'" in view_content:
        fail("China workbench must not search on a non-stored computed status")

    tests_init = (ADDON_ROOT / "tests" / "__init__.py").read_text(
        encoding="utf-8"
    )
    if "from . import test_workbench" not in tests_init:
        fail("China workbench runtime tests must be imported")
    if "from . import test_report_readiness" not in tests_init:
        fail("China report readiness runtime tests must be imported")
    test_content = (
        ADDON_ROOT / "tests" / "test_workbench.py"
    ).read_text(encoding="utf-8")
    for test_name in (
        "test_country_pack_advertises_china_workbench_feature",
        "test_workbench_summarizes_profile_setup_state",
        "test_workbench_summarizes_pending_data_readiness",
        "test_workbench_summarizes_remediation_rescan_status",
        "test_workbench_surfaces_cross_border_identity_boundary",
        "test_workbench_surfaces_cross_border_transaction_register",
        "test_cross_border_transaction_review_freezes_checksum",
        "test_cross_border_fact_provider_exposes_period_snapshot",
        "test_workbench_navigation_actions_are_scoped_to_profile",
        "test_workbench_marks_obligation_readiness_after_review",
    ):
        if f"def {test_name}(" not in test_content:
            fail(f"China workbench runtime coverage is missing {test_name}")
    for required in (
        "china_process_visibility",
        "china_workbench_tax_domain_overview",
        "china_obligation_readiness_visibility",
        "china_workbench_cross_border_overview",
        "china_cross_border_transaction_register",
        "china_cross_border_rule_facts",
        "china_workbench_filing_archive_summary",
        "china_workbench_state_badge_clarity",
        "china_workbench_data_readiness_summary",
        "china_workbench_remediation_rescan_summary",
        "china_workbench_next_best_action",
        "china_delivery_objective_coverage",
        "cn_workbench_package_label",
        "cn_workbench_scope_label",
        "cn_workbench_next_best_action_key",
        "cn_workbench_next_best_action_label",
        "cn_workbench_action_summary",
        "cn_workbench_rule_basis_state",
        "cn_workbench_rule_basis_summary",
        "cn_workbench_rule_basis_next_action",
        "cn_workbench_rule_governance_issue_count",
        "cn_workbench_rule_pending_professional_count",
        "cn_workbench_source_review_overdue_count",
        "cn_workbench_source_monitor_issue_count",
        "cn_workbench_limitation_summary",
        "cn_workbench_uncertainty_summary",
        "cn_workbench_limitation_next_action",
        "action_cn_open_workbench_rule_basis",
        "action_cn_open_workbench_next_best_action",
        "cn_workbench_data_state",
        "cn_workbench_data_next_action",
        "cn_workbench_dataset_count",
        "cn_workbench_ready_dataset_count",
        "cn_workbench_vat_domain_state",
        "cn_workbench_cit_domain_state",
        "cn_workbench_iit_domain_state",
        "cn_workbench_obligation_state",
        "cn_workbench_pending_obligation_count",
        "action_cn_open_workbench_obligations",
        "cn_workbench_cross_border_state",
        "cn_workbench_cross_border_basis",
        "cn_workbench_cross_border_next_action",
        "cn_workbench_cross_border_transaction_count",
        "cn_workbench_cross_border_pending_count",
        "cn_workbench_scan_state",
        "cn_workbench_risk_state",
        "cn_workbench_remediation_state",
        "cn_workbench_rescan_state",
        "cn_workbench_pending_rescan_count",
        "cn_workbench_failed_rescan_count",
        "cn_workbench_verified_remediation_count",
        "cn_workbench_rescan_next_action",
        "cn_workbench_report_state",
        "cn_workbench_evidence_state",
        "cn_workbench_filing_archive_state",
        "cn_workbench_filing_archive_next_action",
        "cn_workbench_filing_archive_count",
        "cn_workbench_filing_archive_issue_count",
    ):
        if required not in test_content:
            fail(f"China process visibility runtime coverage is missing {required}")

    cross_border_model_content = (
        ADDON_ROOT / "models" / "cross_border.py"
    ).read_text(encoding="utf-8")
    for required in (
        '_name = "sudo.cn.cross.border.transaction"',
        "profile_id",
        "counterparty_country_id",
        "related_party",
        "withholding_considered",
        "evidence_attachment_ids",
        "snapshot_checksum",
        "cn_cross_border_readiness_state",
        "sdoo.cn.cross-border-transaction.v1",
        "action_submit",
        "action_mark_reviewed",
        "action_cn_open_workbench_cross_border_transactions",
    ):
        if required not in cross_border_model_content:
            fail(f"China cross-border transaction model is missing {required}")

    cross_border_view_content = (
        ADDON_ROOT / "views" / "cross_border_views.xml"
    ).read_text(encoding="utf-8")
    for required in (
        'id="action_cn_cross_border_transactions"',
        'id="menu_cn_cross_border_transactions"',
        'id="view_cn_cross_border_transaction_kanban"',
        'id="view_cn_cross_border_transaction_list"',
        'id="view_cn_cross_border_transaction_form"',
        "counterparty_country_id",
        "withholding_considered",
        "snapshot_checksum",
        "action_mark_reviewed",
    ):
        if required not in cross_border_view_content:
            fail(f"China cross-border transaction UI is missing {required}")

    fact_content = (
        ADDON_ROOT / "data" / "compliance_fact_data.xml"
    ).read_text(encoding="utf-8")
    rule_content = (
        ADDON_ROOT / "data" / "compliance_rule_drafts.xml"
    ).read_text(encoding="utf-8")
    engine_content = (
        ADDON_ROOT / "models" / "compliance_engine.py"
    ).read_text(encoding="utf-8")
    for fact_key in (
        "cn.cross_border.pending_review_count",
        "cn.cross_border.reviewed_transaction_count",
        "cn.cross_border.detail",
    ):
        if fact_key not in fact_content or fact_key not in engine_content:
            fail(f"China cross-border fact bridge is missing {fact_key}")
    for required in (
        "sdoo.cn.cross-border-facts.v1",
        "_provide_cn_cross_border_pending_review_count",
        "_provide_cn_cross_border_reviewed_transaction_count",
        "_provide_cn_cross_border_detail",
    ):
        if required not in engine_content:
            fail(f"China cross-border fact provider is missing {required}")
    for required in (
        "CN-CROSS-BORDER-CTRL-001",
        "rule_version_cn_cross_border_ready_001_draft",
        "test_cn_cross_border_ready_001_pass",
        "test_cn_cross_border_ready_001_fail",
    ):
        if required not in rule_content:
            fail(f"China cross-border draft rule coverage is missing {required}")

    access_content = (
        ADDON_ROOT / "security" / "ir.model.access.csv"
    ).read_text(encoding="utf-8")
    if "model_sudo_cn_cross_border_transaction" not in access_content:
        fail("China cross-border transaction access control is missing")
    security_content = (
        ADDON_ROOT / "security" / "compliance_security.xml"
    ).read_text(encoding="utf-8")
    if "cn_cross_border_transaction_company_rule" not in security_content:
        fail("China cross-border transaction company rule is missing")

    if "from . import report_readiness" not in model_init:
        fail("China report readiness model must be imported")
    if "from . import ai_guidance" not in model_init:
        fail("China AI guidance model must be imported")
    if "from . import evidence_center" not in model_init:
        fail("China evidence center model must be imported")
    if "from . import risk_center" not in model_init:
        fail("China risk center display model must be imported")
    if "from . import filing_center" not in model_init:
        fail("China filing center model must be imported")
    if "from . import data_readiness_center" not in model_init:
        fail("China data readiness center model must be imported")
    if "from . import assessment_data_basis" not in model_init:
        fail("China assessment data basis model must be imported")
    report_model_content = (
        ADDON_ROOT / "models" / "report_readiness.py"
    ).read_text(encoding="utf-8")
    for required in (
        '_inherit = "sudo.compliance.assessment"',
        "cn_report_readiness_state",
        "cn_report_next_action",
        "cn_report_action_summary",
        "cn_report_readiness_blocker_summary",
        "cn_report_issue_count",
        "cn_report_can_prepare",
        "cn_report_rescan_state",
        "cn_report_rescan_next_action",
        "cn_report_pending_rescan_count",
        "cn_report_failed_rescan_count",
        "cn_report_verified_remediation_count",
        "cn_report_filing_archive_state",
        "cn_report_filing_archive_next_action",
        "cn_report_filing_archive_count",
        "cn_report_filing_archive_issue_count",
        "cn_report_sealed_filing_archive_count",
        "action_cn_open_report_readiness_findings",
        "action_cn_open_report_readiness_tasks",
    ):
        if required not in report_model_content:
            fail(f"China report readiness contract is missing {required}")

    report_view_content = (
        ADDON_ROOT / "views" / "report_readiness_views.xml"
    ).read_text(encoding="utf-8")
    report_readiness_view_root = ElementTree.parse(
        ADDON_ROOT / "views" / "report_readiness_views.xml"
    ).getroot()

    def report_readiness_view_field_names(record_id: str) -> set[str]:
        arch = report_readiness_view_root.find(
            f".//record[@id='{record_id}']/field[@name='arch']"
        )
        if arch is None:
            fail(f"China report readiness UX view contract is missing record {record_id}")
        return {
            element.attrib["name"]
            for element in arch.iter("field")
            if element.attrib.get("name")
        }

    report_readiness_list_fields = report_readiness_view_field_names(
        "view_cn_report_readiness_list"
    )
    report_readiness_kanban_fields = report_readiness_view_field_names(
        "view_cn_report_readiness_kanban"
    )
    required_report_readiness_summary_fields = {
        "company_id",
        "profile_id",
        "period_start",
        "period_end",
        "state",
        "cn_report_readiness_state",
        "cn_report_next_action",
        "cn_report_action_summary",
        "cn_report_readiness_blocker_summary",
        "cn_report_issue_count",
        "cn_report_open_task_count",
        "cn_report_limitation_count",
        "cn_report_pending_tax_impact_count",
        "cn_report_rescan_state",
        "cn_report_rescan_next_action",
        "cn_report_pending_rescan_count",
        "cn_report_failed_rescan_count",
        "cn_report_verified_remediation_count",
        "cn_report_filing_archive_state",
        "cn_report_filing_archive_next_action",
        "cn_report_filing_archive_count",
        "cn_report_filing_archive_issue_count",
        "cn_report_sealed_filing_archive_count",
        "cn_report_ai_guidance_state",
        "cn_report_ai_guidance_next_action",
        "cn_data_basis_state",
        "cn_data_basis_normalized_record_count",
        "cn_data_basis_missing_type_count",
        "cn_data_basis_missing_type_summary",
        "cn_data_basis_next_action",
        "cn_accounting_basis_state",
        "cn_accounting_basis_posted_move_count",
        "cn_accounting_basis_draft_move_count",
        "cn_accounting_basis_next_action",
        "cn_obligation_basis_state",
        "cn_obligation_basis_pending_count",
        "cn_obligation_basis_next_action",
    }
    for record_id, fields in (
        ("view_cn_report_readiness_list", report_readiness_list_fields),
        ("view_cn_report_readiness_kanban", report_readiness_kanban_fields),
    ):
        missing = required_report_readiness_summary_fields - fields
        if missing:
            fail(
                "China report readiness summary views must expose scope, "
                "blockers, data/accounting/obligation basis, rescan, filing "
                "archive, AI guidance and next action fields in "
                f"{record_id}: {sorted(missing)}"
            )
    for required in (
        'id="action_cn_report_readiness"',
        'id="menu_cn_report_readiness"',
        'id="view_cn_report_readiness_kanban"',
        'id="view_cn_report_readiness_list"',
        'id="view_cn_report_readiness_search"',
        "cn_report_readiness_state",
        "cn_report_next_action",
        "cn_report_action_summary",
        "cn_report_readiness_blocker_summary",
        "cn_report_open_task_count",
        "cn_report_limitation_count",
        "cn_report_pending_tax_impact_count",
        "cn_report_rescan_state",
        "cn_report_rescan_next_action",
        "cn_report_pending_rescan_count",
        "cn_report_failed_rescan_count",
        "cn_report_verified_remediation_count",
        "cn_report_filing_archive_state",
        "cn_report_filing_archive_next_action",
        "cn_report_filing_archive_count",
        "cn_report_filing_archive_issue_count",
        "cn_report_sealed_filing_archive_count",
        "cn_data_basis_state",
        "cn_data_basis_dataset_count",
        "cn_data_basis_normalized_record_count",
        "cn_data_basis_next_action",
        "cn_obligation_basis_state",
        "cn_obligation_basis_candidate_count",
        "cn_obligation_basis_pending_count",
        "cn_obligation_basis_next_action",
        "action_cn_open_assessment_obligation_basis",
        "action_cn_open_assessment_data_basis",
        "action_prepare_cn_formal_report",
        "action_open_cn_formal_reports",
        "action_cn_report_readiness_kanban_view",
        'decoration-success="cn_report_readiness_state in (\'ready\', \'issued\')"',
        'decoration-danger="cn_report_readiness_state in (\'needs_review\', \'needs_remediation\')"',
        'decoration-success="cn_data_basis_state == \'ready\'"',
        'decoration-warning="cn_obligation_basis_state in (\'missing\', \'attention\')"',
    ):
        if required not in report_view_content:
            fail(f"China report readiness UI is missing {required}")
    if "('cn_report_readiness_state'" in report_view_content:
        fail("China report readiness must not search on non-stored readiness state")

    risk_view_content = (
        ADDON_ROOT / "views" / "risk_center_views.xml"
    ).read_text(encoding="utf-8")
    risk_model_content = (
        ADDON_ROOT / "models" / "risk_center.py"
    ).read_text(encoding="utf-8")
    risk_view_root = ElementTree.parse(
        ADDON_ROOT / "views" / "risk_center_views.xml"
    ).getroot()

    def view_field_names(record_id: str) -> set[str]:
        arch = risk_view_root.find(
            f".//record[@id='{record_id}']/field[@name='arch']"
        )
        if arch is None:
            fail(f"China risk UX view contract is missing record {record_id}")
        return {
            element.attrib["name"]
            for element in arch.iter("field")
            if element.attrib.get("name")
        }

    risk_list_fields = view_field_names("view_cn_risk_center_finding_list")
    risk_kanban_fields = view_field_names("view_cn_risk_center_finding_kanban")
    remediation_list_fields = view_field_names("view_cn_remediation_tracker_task_list")
    remediation_kanban_fields = view_field_names(
        "view_cn_remediation_tracker_task_kanban"
    )
    required_risk_list_fields = {
        "risk_level",
        "result",
        "review_state",
        "title",
        "cn_risk_period_label",
        "cn_risk_fact_summary",
        "cn_reconciliation_risk_summary",
        "cn_risk_next_action",
        "cn_risk_action_summary",
        "task_assignee_id",
        "task_due_date",
        "task_state",
        "task_verification_state",
        "cn_tax_impact_state",
        "cn_tax_impact_reviewed_underpayment_amount",
    }
    missing_risk_fields = required_risk_list_fields - risk_list_fields
    if missing_risk_fields:
        fail(
            "China risk center list must expose clear risk, cause, impact, "
            f"period, owner, due date, status and next action fields: {sorted(missing_risk_fields)}"
        )
    required_risk_kanban_fields = {
        "risk_level",
        "result",
        "review_state",
        "title",
        "cn_risk_period_label",
        "cn_closure_state",
        "cn_closure_summary",
        "cn_risk_next_action",
        "cn_risk_action_summary",
        "cn_risk_remediation_urgency",
        "cn_risk_responsibility_summary",
        "task_assignee_id",
        "task_due_date",
        "task_state",
        "task_verification_state",
        "cn_risk_data_basis_state",
        "cn_reconciliation_risk_state",
        "cn_tax_impact_state",
        "cn_tax_impact_reviewed_underpayment_amount",
        "cn_tax_impact_summary",
    }
    missing_risk_kanban_fields = required_risk_kanban_fields - risk_kanban_fields
    if missing_risk_kanban_fields:
        fail(
            "China risk center kanban must expose scannable risk, data basis, "
            "impact, owner, due date, closure and next action fields: "
            f"{sorted(missing_risk_kanban_fields)}"
        )
    required_remediation_list_fields = {
        "risk_level",
        "priority",
        "assignee_id",
        "due_date",
        "cn_remediation_period_label",
        "cn_remediation_urgency",
        "cn_remediation_responsibility_summary",
        "cn_remediation_next_action",
        "cn_remediation_action_summary",
        "cn_remediation_blocker_summary",
        "cn_remediation_progress",
        "cn_remediation_tax_impact_state",
        "cn_remediation_tax_impact_reviewed_underpayment_amount",
        "state",
        "verification_state",
        "cn_remediation_rescan_stage",
    }
    missing_remediation_fields = (
        required_remediation_list_fields - remediation_list_fields
    )
    if missing_remediation_fields:
        fail(
            "China remediation tracker list must expose clear risk, impact, "
            "period, owner, due date, status, rescan and next action fields: "
            f"{sorted(missing_remediation_fields)}"
        )
    required_remediation_kanban_fields = {
        "risk_level",
        "priority",
        "assignee_id",
        "due_date",
        "state",
        "verification_state",
        "cn_remediation_period_label",
        "cn_remediation_urgency",
        "cn_remediation_responsibility_summary",
        "cn_remediation_next_action",
        "cn_remediation_action_summary",
        "cn_remediation_blocker_summary",
        "cn_remediation_progress",
        "cn_remediation_summary",
        "cn_remediation_rescan_stage",
        "cn_remediation_evidence_state",
        "cn_remediation_data_basis_state",
        "cn_remediation_tax_impact_state",
        "cn_remediation_tax_impact_reviewed_underpayment_amount",
        "cn_remediation_tax_impact_summary",
    }
    missing_remediation_kanban_fields = (
        required_remediation_kanban_fields - remediation_kanban_fields
    )
    if missing_remediation_kanban_fields:
        fail(
            "China remediation tracker kanban must expose scannable risk, "
            "impact, owner, due date, blocker, evidence, rescan and next action fields: "
            f"{sorted(missing_remediation_kanban_fields)}"
        )
    for required in (
        '_inherit = "sudo.compliance.finding"',
        '_inherit = "sudo.compliance.task"',
        "cn_risk_period_label",
        "cn_risk_next_action",
        "cn_risk_action_summary",
        "cn_risk_evidence_state",
        "cn_traceability_state",
        "cn_traceability_gap_count",
        "cn_traceability_next_action",
        "action_cn_open_traceability_evidence",
        "cn_cross_border_fact_state",
        "cn_cross_border_pending_count",
        "cn_cross_border_reviewed_count",
        "cn_cross_border_transaction_count",
        "cn_cross_border_next_action",
        "_cn_cross_border_fact_summary",
        "cn_risk_rule_basis_state",
        "cn_risk_rule_source_count",
        "cn_risk_rule_release_state",
        "cn_risk_rule_professional_state",
        "action_cn_open_risk_rule_version",
        "cn_remediation_period_label",
        "cn_remediation_next_action",
        "cn_remediation_action_summary",
        "cn_remediation_blocker_summary",
        "cn_remediation_evidence_state",
        "cn_remediation_traceability_state",
        "cn_remediation_traceability_gap_count",
        "cn_remediation_traceability_next_action",
        "cn_remediation_rescan_stage",
        "action_cn_open_remediation_verification_assessment",
        "sudo.compliance.evidence",
    ):
        if required not in risk_model_content:
            fail(f"China risk action guidance model is missing {required}")
    for required in (
        "cn_cross_border_fact_state",
        "cn_cross_border_pending_count",
        "cn_cross_border_reviewed_count",
        "cn_cross_border_transaction_count",
        "cn_cross_border_next_action",
        "跨境事实",
    ):
        if required not in risk_view_content:
            fail(f"China cross-border risk visibility UI is missing {required}")

    report_test_content = (
        ADDON_ROOT / "tests" / "test_report_readiness.py"
    ).read_text(encoding="utf-8")
    risk_test_content = (
        ADDON_ROOT / "tests" / "test_risk_center.py"
    ).read_text(encoding="utf-8")
    for required in (
        "test_cross_border_rule_finding_exposes_fact_review_status",
        "cn_cross_border_fact_state",
        "cn_cross_border_pending_count",
        "cn_cross_border_reviewed_count",
        "china_cross_border_risk_visibility",
    ):
        if required not in risk_test_content:
            fail(f"China cross-border risk visibility coverage is missing {required}")
    for test_name in (
        "test_completed_clean_assessment_discloses_limitations",
        "test_incomplete_assessment_requires_scan_completion",
        "test_country_pack_advertises_report_readiness_badge_clarity",
        "test_report_readiness_blocks_pending_or_failed_rescans",
        "test_report_readiness_surfaces_filing_archive_gate",
        "test_readiness_navigation_actions_are_scoped_to_assessment",
    ):
        if f"def {test_name}(" not in report_test_content:
            fail(f"China report readiness runtime coverage is missing {test_name}")
    if "china_report_readiness_badge_clarity" not in report_test_content:
        fail("China report readiness badge clarity runtime coverage is missing")
    if "china_report_rescan_gate" not in report_test_content:
        fail("China report rescan gate runtime coverage is missing")
    if "china_report_filing_archive_gate" not in report_test_content:
        fail("China report filing archive gate runtime coverage is missing")
    if "cn_report_readiness_blocker_summary" not in report_test_content:
        fail("China report readiness blocker summary runtime coverage is missing")
    if "cn_report_action_summary" not in report_test_content:
        fail("China report action summary runtime coverage is missing")
    for required in (
        "行动摘要",
        "报告阻断事项",
        "整改复扫门禁",
        "申报缴款档案门禁",
        "受控 AI 指引门禁",
    ):
        if required not in report_view_content:
            fail(f"China report readiness UI Chinese clarity is missing {required}")

    data_basis_model_content = (
        ADDON_ROOT / "models" / "assessment_data_basis.py"
    ).read_text(encoding="utf-8")
    for required in (
        '_inherit = "sudo.compliance.assessment"',
        "cn_data_basis_state",
        "cn_data_basis_dataset_count",
        "cn_data_basis_ready_count",
        "cn_data_basis_warning_count",
        "cn_data_basis_blocked_count",
        "cn_data_basis_normalized_record_count",
        "cn_data_basis_next_action",
        "cn_obligation_basis_state",
        "cn_obligation_basis_candidate_count",
        "cn_obligation_basis_applicable_count",
        "cn_obligation_basis_pending_count",
        "cn_obligation_basis_filing_count",
        "cn_obligation_basis_next_action",
        "action_cn_open_assessment_obligation_basis",
        "action_cn_open_assessment_data_basis",
        "sudo_country_pack_cn.action_cn_data_readiness_center",
    ):
        if required not in data_basis_model_content:
            fail(f"China assessment data basis model is missing {required}")

    if "from . import test_assessment_data_basis" not in tests_init:
        fail("China assessment data basis runtime tests must be imported")
    data_basis_test_content = (
        ADDON_ROOT / "tests" / "test_assessment_data_basis.py"
    ).read_text(encoding="utf-8")
    for required in (
        "test_country_pack_advertises_assessment_data_basis",
        "test_assessment_without_datasets_shows_missing_data_basis",
        "test_assessment_opens_period_scoped_data_basis",
        "test_assessment_opens_profile_scoped_obligation_basis",
        "test_draft_dataset_makes_data_basis_warning",
        "test_reviewed_obligations_make_assessment_obligation_basis_ready",
        "china_assessment_data_basis",
        "china_assessment_obligation_basis",
        "cn_data_basis_state",
        "cn_obligation_basis_state",
        "action_cn_open_assessment_data_basis",
        "action_cn_open_assessment_obligation_basis",
    ):
        if required not in data_basis_test_content:
            fail(f"China assessment data basis runtime coverage is missing {required}")

    ai_model_content = (
        ADDON_ROOT / "models" / "ai_guidance.py"
    ).read_text(encoding="utf-8")
    for required in (
        '_inherit = "sudo.compliance.finding"',
        "AI_GUIDANCE_PROVIDER",
        "AI_GUIDANCE_PROMPT_VERSION",
        "cn_ai_guidance_state",
        "cn_ai_guidance_next_action",
        "cn_ai_guidance_input_checksum",
        "obligation_readiness",
        "filing_archive",
        "cn_workbench_obligation_state",
        "cn_workbench_pending_obligation_count",
        "cn_workbench_filing_archive_state",
        "cn_workbench_filing_archive_next_action",
        "Filing/payment archive",
        "_cn_ai_guidance_input",
        "_cn_ai_guidance_text",
        "action_generate_cn_ai_guidance",
        "sudo.compliance.ai.analysis",
        "state\": \"fallback\"",
        "AI 分析仅为辅助材料",
    ):
        if required not in ai_model_content:
            fail(f"China controlled AI guidance contract is missing {required}")

    ai_view_content = (
        ADDON_ROOT / "views" / "ai_guidance_views.xml"
    ).read_text(encoding="utf-8")
    for required in (
        'id="view_compliance_finding_cn_ai_guidance_form"',
        'id="view_compliance_finding_cn_ai_guidance_list"',
        'id="view_compliance_ai_analysis_cn_guidance_list"',
        "action_generate_cn_ai_guidance",
        "action_open_ai_analyses",
        "ai_analysis_count",
        "cn_ai_guidance_state",
        "cn_ai_guidance_next_action",
        "cn_ai_guidance_input_checksum",
        "sudo_global_finance.view_compliance_ai_analysis_list",
    ):
        if required not in ai_view_content:
            fail(f"China controlled AI guidance UI is missing {required}")

    if "action_generate_cn_ai_guidance" not in risk_view_content:
        fail("China risk center must expose controlled AI guidance generation")
    for required in (
        "cn_ai_guidance_state",
        "cn_ai_guidance_next_action",
        "cn_ai_guidance_input_checksum",
    ):
        if required not in risk_view_content:
            fail(f"China risk center AI guidance visibility is missing {required}")

    evidence_model_content = (
        ADDON_ROOT / "models" / "evidence_center.py"
    ).read_text(encoding="utf-8")
    for required in (
        '_inherit = "sudo.compliance.profile"',
        "action_cn_open_workbench_evidence_center",
        "sudo_country_pack_cn.action_cn_evidence_center",
        "sudo.compliance.evidence",
        '_inherit = "sudo.compliance.evidence"',
        "cn_evidence_source_summary",
        "cn_evidence_blocker_summary",
        "assessment_id.profile_id",
        "finding_id.assessment_id.profile_id",
        "task_id.assessment_id.profile_id",
        "filing_id.profile_id",
    ):
        if required not in evidence_model_content:
            fail(f"China evidence center contract is missing {required}")

    evidence_view_content = (
        ADDON_ROOT / "views" / "evidence_center_views.xml"
    ).read_text(encoding="utf-8")
    evidence_view_root = ElementTree.parse(
        ADDON_ROOT / "views" / "evidence_center_views.xml"
    ).getroot()

    def evidence_view_field_names(record_id: str) -> set[str]:
        arch = evidence_view_root.find(
            f".//record[@id='{record_id}']/field[@name='arch']"
        )
        if arch is None:
            fail(f"China evidence center UX view contract is missing record {record_id}")
        return {
            element.attrib["name"]
            for element in arch.iter("field")
            if element.attrib.get("name")
        }

    required_evidence_summary_fields = {
        "name",
        "company_id",
        "evidence_type",
        "evidence_date",
        "issuer",
        "state",
        "cn_evidence_source_summary",
        "cn_evidence_blocker_summary",
        "assessment_id",
        "finding_id",
        "task_id",
        "filing_id",
        "document_checksum",
        "verified_by_id",
        "verified_at",
    }
    for record_id in (
        "view_cn_evidence_center_list",
        "view_cn_evidence_center_kanban",
    ):
        fields = evidence_view_field_names(record_id)
        missing = required_evidence_summary_fields - fields
        if missing:
            fail(
                "China evidence center summary views must expose evidence "
                "identity, source, blocker, linkage, checksum and verification "
                f"fields in {record_id}: {sorted(missing)}"
            )
    for required in (
        'id="view_cn_evidence_center_search"',
        'id="view_cn_evidence_center_list"',
        'id="view_cn_evidence_center_kanban"',
        'id="view_cn_evidence_center_form_inherit"',
        'id="action_cn_evidence_center"',
        'id="menu_cn_evidence_center"',
        "sudo.compliance.evidence",
        "default_group_by=\"state\"",
        "search_default_cn_related",
        "assessment_id.country_id.code",
        "finding_id.assessment_id.country_id.code",
        "task_id.assessment_id.country_id.code",
        "filing_id.country_id.code",
        "document_checksum",
        "cn_evidence_source_summary",
        "cn_evidence_blocker_summary",
        "verified_by_id",
        "verified_at",
        'decoration-success="state == \'verified\'"',
        'decoration-warning="state == \'submitted\'"',
        'decoration-danger="state == \'rejected\'"',
    ):
        if required not in evidence_view_content:
            fail(f"China evidence center UI is missing {required}")

    filing_model_content = (
        ADDON_ROOT / "models" / "filing_center.py"
    ).read_text(encoding="utf-8")
    for required in (
        '_inherit = "sudo.compliance.filing"',
        '_inherit = "sudo.compliance.profile"',
        "cn_filing_center_kind",
        "cn_filing_center_period_label",
        "cn_filing_center_next_action",
        "cn_filing_center_blocker_summary",
        "cn_filing_center_evidence_state",
        "action_cn_open_workbench_filing_center",
        "sudo_country_pack_cn.action_cn_filing_center",
    ):
        if required not in filing_model_content:
            fail(f"China filing center model is missing {required}")

    filing_view_content = (
        ADDON_ROOT / "views" / "filing_center_views.xml"
    ).read_text(encoding="utf-8")
    for required in (
        'id="view_cn_filing_center_search"',
        'id="view_cn_filing_center_list"',
        'id="view_cn_filing_center_kanban"',
        'id="action_cn_filing_center"',
        'id="menu_cn_filing_center"',
        "sudo.compliance.filing",
        "cn_filing_center_kind",
        "cn_filing_center_period_label",
        "cn_filing_center_next_action",
        "cn_filing_center_blocker_summary",
        "cn_filing_center_evidence_state",
        "cn_submission_integrity_state",
        "cn_payment_integrity_state",
        'decoration-success="state in (\'accepted\', \'done\')"',
        'decoration-success="payment_state in (\'paid\', \'not_required\')"',
        'decoration-success="cn_submission_integrity_state == \'verified\'"',
        'decoration-danger="cn_payment_integrity_state in (\'changed\', \'invalid\')"',
        'decoration-muted="cn_filing_center_evidence_state == \'none\'"',
    ):
        if required not in filing_view_content:
            fail(f"China filing center UI is missing {required}")
    if 'default_group_by="cn_filing_center_kind"' in filing_view_content:
        fail("China filing center must not default-group by computed filing kind")

    if "from . import test_ai_guidance" not in tests_init:
        fail("China controlled AI guidance runtime tests must be imported")
    if "from . import test_risk_center" not in tests_init:
        fail("China risk center display runtime tests must be imported")
    if "from . import test_filing_center" not in tests_init:
        fail("China filing center runtime tests must be imported")
    ai_test_content = (
        ADDON_ROOT / "tests" / "test_ai_guidance.py"
    ).read_text(encoding="utf-8")
    for test_name in (
        "test_generate_controlled_ai_guidance_snapshot",
        "test_ai_guidance_visibility_marks_limited_inputs",
        "test_country_pack_advertises_controlled_ai_guidance",
        "test_ai_guidance_stays_limited_until_filing_archives_exist",
    ):
        if f"def {test_name}(" not in ai_test_content:
            fail(f"China controlled AI guidance runtime coverage is missing {test_name}")
    for required in (
        "china_ai_obligation_context",
        "china_ai_filing_archive_context",
        "obligation_readiness",
        "filing_archive",
        "Filing/payment archive",
        "pending_review_count",
        "_reset_obligations",
    ):
        if required not in ai_test_content:
            fail(f"China AI obligation context runtime coverage is missing {required}")

    risk_test_content = (
        ADDON_ROOT / "tests" / "test_risk_center.py"
    ).read_text(encoding="utf-8")
    for required in (
        "test_finding_exposes_period_next_action_and_evidence_status",
        "test_country_pack_advertises_risk_action_guidance",
        "test_remediation_task_exposes_rescan_stage_and_navigation",
        "test_country_pack_advertises_remediation_rescan_visibility",
        "test_finding_exposes_rule_basis_status_and_navigation",
        "test_country_pack_advertises_risk_rule_basis_visibility",
        "test_finding_exposes_traceability_gaps_and_evidence_navigation",
        "test_finding_closure_summary_distinguishes_ready_and_action_required",
        "test_remediation_task_exposes_traceability_gaps",
        "test_remediation_task_blocker_summary_keeps_remaining_gaps_visible",
        "china_risk_action_guidance",
        "china_remediation_rescan_visibility",
        "china_risk_rule_basis_visibility",
        "china_traceability_matrix_visibility",
        "china_risk_card_state_badge_clarity",
        "china_risk_closure_status_summary",
        "cn_risk_period_label",
        "cn_risk_next_action",
        "cn_risk_action_summary",
        "cn_risk_evidence_state",
        "cn_traceability_state",
        "cn_traceability_gap_count",
        "cn_closure_state",
        "cn_closure_summary",
        "action_cn_open_traceability_evidence",
        "cn_risk_rule_basis_state",
        "action_cn_open_risk_rule_version",
        "cn_remediation_rescan_stage",
        "cn_remediation_blocker_summary",
        "cn_remediation_traceability_state",
        "action_cn_open_remediation_verification_assessment",
    ):
        if required not in risk_test_content:
            fail(f"China risk center display runtime coverage is missing {required}")

    filing_test_content = (
        ADDON_ROOT / "tests" / "test_filing_center.py"
    ).read_text(encoding="utf-8")
    for required in (
        "test_country_pack_advertises_filing_center",
        "test_workbench_opens_profile_scoped_filing_center",
        "test_filing_center_exposes_blocker_summary",
        "china_filing_center",
        "china_archive_evidence_badge_clarity",
        "action_cn_open_workbench_filing_center",
        "cn_filing_center_blocker_summary",
        "cn_vat_reconciliation_run_id",
        "cn_cit_reconciliation_run_id",
        "cn_iit_reconciliation_run_id",
    ):
        if required not in filing_test_content:
            fail(f"China filing center runtime coverage is missing {required}")

    filing_search_forbidden = (
        "domain=\"[('cn_submission_integrity_state'",
        "domain=\"[('cn_payment_integrity_state'",
        "domain=\"[('cn_filing_center_evidence_state'",
        "domain=\"['|', ('cn_submission_integrity_state'",
    )
    for forbidden in filing_search_forbidden:
        if forbidden in filing_view_content:
            fail(
                "China filing center search view must not filter on non-searchable computed status fields"
            )

    data_readiness_model_content = (
        ADDON_ROOT / "models" / "data_readiness_center.py"
    ).read_text(encoding="utf-8")
    for required in (
        '_inherit = "sudo.cn.external.dataset"',
        '_inherit = "sudo.compliance.profile"',
        "cn_data_readiness_stage",
        "cn_data_readiness_period_label",
        "cn_data_readiness_record_count",
        "cn_data_readiness_next_action",
        "cn_data_readiness_blocker_summary",
        "action_cn_open_workbench_data_readiness",
        "sudo_country_pack_cn.action_cn_data_readiness_center",
    ):
        if required not in data_readiness_model_content:
            fail(f"China data readiness center model is missing {required}")

    data_readiness_view_content = (
        ADDON_ROOT / "views" / "data_readiness_center_views.xml"
    ).read_text(encoding="utf-8")
    for required in (
        'id="view_cn_data_readiness_center_search"',
        'id="view_cn_data_readiness_center_list"',
        'id="view_cn_data_readiness_center_kanban"',
        'id="action_cn_data_readiness_center"',
        'id="menu_cn_data_readiness_center"',
        "sudo.cn.external.dataset",
        "cn_data_readiness_stage",
        "cn_data_readiness_next_action",
        "cn_data_readiness_record_count",
        "cn_data_readiness_blocker_summary",
        "review_control_state",
        "action_view_parse_runs",
        "action_view_tax_data_parse_runs",
        "action_view_normalized_tax_records",
        'default_group_by="dataset_type"',
    ):
        if required not in data_readiness_view_content:
            fail(f"China data readiness center UI is missing {required}")

    if "domain=\"[('integrity_state'" in data_readiness_view_content:
        fail("China data readiness search view must not filter on non-searchable integrity_state")
    if "group_by': 'integrity_state'" in data_readiness_view_content:
        fail("China data readiness search view must not group by non-stored integrity_state")

    for required in (
        'decoration-success="cn_data_readiness_stage == \'ready\'"',
        'decoration-success="state == \'sealed\'"',
        'decoration-success="integrity_state == \'verified\'"',
        "decoration-success=\"authenticity_state in ('official_tool_passed', 'not_applicable')\"",
        'decoration-success="review_control_state == \'independent\'"',
        'decoration-danger="review_control_state == \'exception\'"',
    ):
        if required not in data_readiness_view_content:
            fail(f"China data readiness badge clarity UI is missing {required}")

    if "from . import test_data_readiness_center" not in tests_init:
        fail("China data readiness center runtime tests must be imported")
    data_readiness_test_content = (
        ADDON_ROOT / "tests" / "test_data_readiness_center.py"
    ).read_text(encoding="utf-8")
    for required in (
        "test_country_pack_advertises_data_readiness_center",
        "test_workbench_opens_profile_scoped_data_readiness_center",
        "test_dataset_exposes_readiness_next_action",
        "china_data_readiness_center",
        "china_data_readiness_badge_clarity",
        "action_cn_open_workbench_data_readiness",
        "cn_data_readiness_stage",
        "cn_data_readiness_next_action",
        "cn_data_readiness_blocker_summary",
    ):
        if required not in data_readiness_test_content:
            fail(f"China data readiness center runtime coverage is missing {required}")

    for required in (
        'id="action_cn_risk_center"',
        'id="menu_cn_risk_center"',
        'id="view_cn_risk_center_finding_kanban"',
        'id="view_cn_risk_center_finding_list"',
        'id="view_cn_risk_center_finding_search"',
        'id="action_cn_remediation_tracker"',
        'id="menu_cn_remediation_tracker"',
        'id="view_cn_remediation_tracker_task_kanban"',
        'id="view_cn_remediation_tracker_task_list"',
        'id="view_cn_remediation_tracker_task_search"',
        'action_cn_risk_center_kanban_view',
        'action_cn_remediation_tracker_kanban_view',
        "assessment_id.profile_id.country_id.code",
        "task_assignee_id",
        "task_due_date",
        "task_verification_state",
        "cn_tax_impact_case_count",
        "verification_state",
        "default_group_by=\"state\"",
        "cn_risk_period_label",
        "cn_risk_next_action",
        "cn_risk_evidence_state",
        "cn_traceability_state",
        "cn_traceability_gap_count",
        "cn_traceability_next_action",
        "action_cn_open_traceability_evidence",
        "cn_risk_rule_basis_state",
        "cn_risk_rule_source_count",
        "cn_risk_rule_release_state",
        "cn_risk_rule_professional_state",
        "action_cn_open_risk_rule_version",
        "cn_remediation_period_label",
        "cn_remediation_next_action",
        "cn_remediation_action_summary",
        "cn_remediation_blocker_summary",
        "cn_remediation_evidence_state",
        "cn_remediation_traceability_state",
        "cn_remediation_traceability_gap_count",
        "cn_remediation_traceability_next_action",
        "cn_remediation_rescan_stage",
        "action_queue_verification_scan",
        "action_cn_open_remediation_verification_assessment",
        "verification_assessment_id",
        "行动摘要",
        "阻断事项",
        "税务影响",
        "证据追溯",
        "事实依据",
        "账票税款勾稽",
        'decoration-danger="risk_level in (\'critical\', \'high\')"',
        'decoration-success="cn_traceability_state == \'complete\'"',
        'decoration-warning="cn_remediation_evidence_state == \'partial\'"',
        'decoration-danger="cn_remediation_rescan_stage in (\'blocked\', \'failed\')"',
    ):
        if required not in risk_view_content:
            fail(f"China risk center UI is missing {required}")
    for forbidden in (
        "current_date",
        "('cn_workbench_status'",
        "group_by': 'cn_workbench_status'",
    ):
        if forbidden in risk_view_content:
            fail(f"China risk center has unsafe UI expression: {forbidden}")


def _coverage_referenced_paths(content: str) -> list[str]:
    path_prefixes = (
        "addons/",
        "data/",
        "docs/",
        "models/",
        "reports/",
        "security/",
        "tests/",
        "tools/",
        "views/",
    )
    references: list[str] = []
    for token in re.findall(r"`([^`]+)`", content):
        item = token.strip()
        if item.startswith(path_prefixes):
            references.append(item)
    return references


def _coverage_path_exists(reference: str) -> bool:
    if reference.startswith(("addons/", "docs/", "tools/")):
        base = REPOSITORY_ROOT
        relative = reference
    else:
        base = ADDON_ROOT
        relative = reference
    if any(char in relative for char in "*?["):
        return any(base.glob(relative))
    return (base / relative).exists()


def validate_delivery_objective_coverage() -> None:
    delivery_index_path = REPOSITORY_ROOT / "docs" / "CHINA_DELIVERY_INDEX.md"
    if not delivery_index_path.is_file():
        fail("China delivery index must be documented")
    delivery_index_content = delivery_index_path.read_text(encoding="utf-8")
    for required in (
        "# China Fiscal Compliance Pack Delivery Index",
        "## Read Order",
        "## Command Index",
        "Release Candidate Is Ready For Business UAT When",
        "Release Candidate Is Ready For Production Sign-off When",
        "docs/CHINA_RELEASE_HANDOFF_CURRENT.md",
        "docs/CHINA_UAT_WALKTHROUGH_SCRIPT.md",
        "tools/check_cn_preview_health.py",
        "tools/audit_cn_objective_completion.py",
        "tools/build_cn_signoff_evidence_chain.py",
        "tools/select_cn_latest_signoff_candidate.py",
        "tools/export_cn_production_signoff_actions.py",
        "tools/render_cn_signoff_evidence_template.py",
        "docs/MILESTONE_70_CHINA_BLOCKER_SUMMARY_VISIBILITY.md",
        "docs/CHINA_CURRENT_PRODUCTION_SIGNOFF_RUNBOOK.md",
    ):
        if required not in delivery_index_content:
            fail(f"China delivery index is missing {required}")

    handoff_path = REPOSITORY_ROOT / "docs" / "CHINA_RELEASE_HANDOFF_CURRENT.md"
    if not handoff_path.is_file():
        fail("China current release handoff must be documented")
    handoff_content = handoff_path.read_text(encoding="utf-8")
    for required in (
        "# China Fiscal Compliance Pack Release Handoff",
        "Delivery version: `19.0.1.130.0`",
        "dist/sdoo-cn-compliance-delivery-m*.tgz",
        "codex_cn_m31_runtime_mNNN",
        "business_uat_ready=true",
        "production_signoff_ready=false",
        "CHINA_UAT_WALKTHROUGH_SCRIPT.md",
        "official-source freshness",
        "China tax professional",
        "audit_cn_objective_completion.py",
        "build_cn_signoff_evidence_chain.py",
        "CHINA_CURRENT_PRODUCTION_SIGNOFF_RUNBOOK.md",
        "cn_objective_completion_audit_mNNN.json",
        "render_cn_signoff_evidence_template.py",
        "cn_signoff_evidence_draft_mNNN.json",
        "validate_cn_signoff_evidence.py",
        "Next Best Work",
    ):
        if required not in handoff_content:
            fail(f"China current release handoff is missing {required}")
    if re.search(r"dist/cn_(?:preview|delivery|signoff|objective)[^\\s`]*_m\\d+[^\\s`]*", handoff_content):
        fail("China current release handoff must use mNNN placeholders, not stale numbered evidence files")

    blocker_visibility_path = (
        REPOSITORY_ROOT / "docs" / "MILESTONE_70_CHINA_BLOCKER_SUMMARY_VISIBILITY.md"
    )
    if not blocker_visibility_path.is_file():
        fail("China blocker summary visibility milestone must be documented")
    blocker_visibility_content = blocker_visibility_path.read_text(encoding="utf-8")
    for required in (
        "# Milestone 70 - China Blocker Summary Visibility",
        "Data readiness center",
        "Evidence center",
        "Filing/payment archive center",
        "Report readiness center",
        "Business UAT should verify",
        "certify a taxpayer position",
    ):
        if required not in blocker_visibility_content:
            fail(f"China blocker visibility milestone is missing {required}")

    current_runbook_path = REPOSITORY_ROOT / "docs" / "CHINA_CURRENT_PRODUCTION_SIGNOFF_RUNBOOK.md"
    if not current_runbook_path.is_file():
        fail("China current production sign-off runbook must be documented")
    current_runbook_content = current_runbook_path.read_text(encoding="utf-8")
    for required in (
        "# China Fiscal Compliance Pack Current Production Sign-off Runbook",
        "latest verified `mNNN` evidence set",
        "tools/select_cn_latest_signoff_candidate.py",
        "--require-highest-status-complete",
        "tools/export_cn_production_signoff_actions.py",
        "dist/sdoo-cn-compliance-delivery-mNNN.tgz",
        "dist/cn_delivery_mNNN_chain_signoff_packet.md",
        "business UAT ready: `true`",
        "production sign-off ready: `false`",
        "`business_uat_decision`",
        "`china_tax_professional_rule_signoff`",
        "`customer_scope_and_data_gap_review`",
        "tools/validate_cn_signoff_evidence.py",
        "--require-production-signoff-ready",
        "not a tax opinion",
    ):
        if required not in current_runbook_content:
            fail(f"China current sign-off runbook is missing {required}")

    uat_path = REPOSITORY_ROOT / "docs" / "CHINA_BUSINESS_UAT_CHECKLIST.md"
    if not uat_path.is_file():
        fail("China business UAT checklist must be documented")
    uat_content = uat_path.read_text(encoding="utf-8")
    for required in (
        "# China Fiscal Compliance Pack Business UAT Checklist",
        "## Preconditions",
        "## Walkthrough",
        "Open the China compliance workbench",
        "Review data readiness",
        "Review risks",
        "Review remediation",
        "Review controlled AI guidance",
        "provider, prompt version, model, input/output checksum and record checksum",
        "Review report readiness and formal reports",
        "Screen and usability checks",
        "Review blocker-summary visibility",
        "blocker_summary_walkthrough",
        "## Acceptance Boundary",
    ):
        if required not in uat_content:
            fail(f"China business UAT checklist is missing {required}")

    walkthrough_path = REPOSITORY_ROOT / "docs" / "CHINA_UAT_WALKTHROUGH_SCRIPT.md"
    if not walkthrough_path.is_file():
        fail("China UAT walkthrough script must be documented")
    walkthrough_content = walkthrough_path.read_text(encoding="utf-8")
    for required in (
        "# China Fiscal Compliance Pack UAT Walkthrough Script",
        "## Session Header",
        "## Pass Criteria",
        "## 1. Compliance Workbench",
        "## 2. Profile, Taxpayer Identity And Obligations",
        "## 3. Data Readiness And External Datasets",
        "## 4. Rule Scan And Assessment",
        "## 5. Risk Center",
        "## 6. Remediation Tracker",
        "## 7. Controlled AI Guidance",
        "## 8. Report Readiness And Compliance Report",
        "## 9. Evidence, Filing And Payment Archives",
        "## 10. Tax Domain Samples",
        "## 11. Screen-Size And Native Odoo UX Check",
        "## Final UAT Decision",
        "risk level, reason, impact amount, applicable period, owner, due date, status and next action",
        "provider, prompt version, model, input checksum, output checksum and record checksum",
        "VAT, CIT, IIT and cross-border",
        "Browser and version",
        "Desktop viewport or resolution",
        "Smaller laptop viewport or resolution",
        "Required screen evidence",
        "| Compliance workbench |",
        "| Risk center |",
        "| Remediation tracker |",
        "| Report readiness |",
        "risk level, reason, impact amount, applicable",
        "blockers and next action remain readable",
    ):
        if required not in walkthrough_content:
            fail(f"China UAT walkthrough script is missing {required}")

    signoff_path = REPOSITORY_ROOT / "docs" / "CHINA_PRODUCTION_SIGNOFF_TEMPLATE.md"
    if not signoff_path.is_file():
        fail("China production sign-off template must be documented")
    signoff_content = signoff_path.read_text(encoding="utf-8")
    for required in (
        "# China Fiscal Compliance Pack Production Sign-off Template",
        "## How To Use This Template",
        "## Release Candidate",
        "## Automated Evidence",
        "## Business UAT Result",
        "## Rule And Source Governance",
        "## Data And Scope Limitations",
        "## Risk And Remediation Status",
        "## Deployment Decision",
        "## Boundary Statement",
        "Blocker-summary walkthrough evidence",
        "Controlled AI guidance evidence reviewed",
        "Controlled AI guidance evidence reference",
        "Controlled AI guidance checksum evidence complete",
        "AI limitation and professional warning disclosure reviewed",
        "Choose `defer` or `reject` instead of `deploy`",
        "deploy with limitations",
        "dist/cn_delivery_status_mNNN.json",
        "dist/cn_signoff_packet_mNNN.md",
        "source commit, manifest aggregate hash and remote runtime acceptance result",
        "Delivery status `business_uat_ready`",
        "Business UAT walkthrough script included in manifest",
        "Official source governance summary ready",
        "Completed UAT walkthrough script reference",
        "Sign-off action packet path",
        "Rule versions requiring China tax professional sign-off",
        "Official-source freshness evidence reference",
        "Official source governance summary evidence reference",
        "Changed source monitor runs",
        "Rule governance issues",
        "External tax/invoice/payment data acquisition basis reviewed",
        "Workbench next-action and limitation summary readable",
        "Risk center risk level, reason, impact amount and next action readable",
        "Remediation tracker owner, due date, status and rescan state readable",
        "Accepted unresolved risks or limitations",
        "Rollback trigger",
        "Post-go-live evidence retention location",
        "Data readiness blockers reviewed",
        "Report readiness blockers reviewed",
    ):
        if required not in signoff_content:
            fail(f"China production sign-off template is missing {required}")

    preview_health_path = REPOSITORY_ROOT / "tools" / "check_cn_preview_health.py"
    if not preview_health_path.is_file():
        fail("China preview health checker must be packaged")
    preview_health_content = preview_health_path.read_text(encoding="utf-8")
    for required in (
        "sdoo.cn.preview-health.v1",
        "Internal Server Error",
        "invalid CSRF token",
        "Database not found",
        "urlopen",
        "preview health passed",
        "preview health failed",
    ):
        if required not in preview_health_content:
            fail(f"China preview health checker is missing {required}")

    preview_module_path = REPOSITORY_ROOT / "tools" / "check_cn_preview_module.py"
    if not preview_module_path.is_file():
        fail("China preview module checker must be packaged")
    preview_module_content = preview_module_path.read_text(encoding="utf-8")
    for required in (
        "sdoo.cn.preview-module.v1",
        "ir.module.module",
        "sudo_country_pack_cn",
        "compliance_country_pack_cn",
        "module_installed_version",
        "country_pack_version",
        "required_capabilities",
        "china_delivery_preview_module_gate",
    ):
        if required not in preview_module_content:
            fail(f"China preview module checker is missing {required}")

    real_data_path = REPOSITORY_ROOT / "tools" / "check_cn_real_data_closed_loop.py"
    if not real_data_path.is_file():
        fail("China real-data closed-loop checker must be packaged")
    real_data_content = real_data_path.read_text(encoding="utf-8")
    for required in (
        "sdoo.cn.real-data-closed-loop.v1",
        "account.move",
        "sudo.compliance.profile",
        "sudo.compliance.assessment",
        "sudo.compliance.finding",
        "sudo.compliance.task",
        "sudo.cn.compliance.report",
        "sudo.cn.external.dataset",
        "sudo.cn.vat.period.reconciliation.run",
        "has_real_accounting_ledger",
        "setup_demo_ready",
        "has_reconciliation_activity",
        "closed_loop_evidence_ready",
        "has_workbench_summary_evidence",
        "has_risk_task_report_summary_evidence",
        "has_risk_finding_visibility_evidence",
        "has_remediation_task_visibility_evidence",
        "has_remediation_verification_rescan_evidence",
        "has_report_visibility_evidence",
        "has_reviewer_view_contract_evidence",
        "reviewer_view_contracts",
        "view_field_contract",
        "has_multi_company_security_contract_evidence",
        "multi_company_security_contracts",
        "company_rule_contract",
        "sample_findings",
        "sample_remediation_tasks",
        "sample_reports",
        "has_evidence_filing_payment_summary_evidence",
        "has_controlled_ai_guidance_evidence",
        "has_text(finding.get(\"period_label\"))",
        "has_text(finding.get(\"tax_impact\"))",
        "has_text(task.get(\"assignee\"))",
        "has_text(task.get(\"due_date\"))",
        "safe_field(report, \"cn_report_blocker_summary\")",
        "has_text(report.get(\"traceability_next_action\"))",
        "sample_evidence",
        "sample_filing_archives",
        "sample_ai_guidance",
        "sample_authority_sources",
        "sample_rule_versions",
        "sample_source_monitor_runs",
        "sample_iit_reconciliation_runs",
        "sample_cross_border_transactions",
        "sdoo_cn_controlled_guidance",
        "has_official_source_freshness_evidence",
        "has_rule_professional_signoff_evidence",
        "has_rule_checksum_traceability_evidence",
        "has_rule_source_governance_evidence",
        "has_customer_scope_gap_review_evidence",
        "has_customer_data_scope_review_evidence",
        "has_customer_evidence_gap_review_evidence",
        "has_open_high_risk_review_evidence",
        "has_iit_payroll_withholding_scope_evidence",
        "has_cross_border_review_scope_evidence",
        "cn_valid_authority_sources",
        "cn_active_rule_versions",
        "cn_source_monitor_runs",
        "active_profile_iit_reconciliation_runs",
        "active_profile_cross_border_transactions",
        "cn_workbench_action_summary",
        "cn_workbench_rule_basis_summary",
        "cn_workbench_limitation_summary",
        "cn_workbench_uncertainty_summary",
        "--require-demo-ready",
        "--require-closed-loop-evidence",
    ):
        if required not in real_data_content:
            fail(f"China real-data closed-loop checker is missing {required}")

    demo_profile_path = REPOSITORY_ROOT / "tools" / "prepare_cn_demo_profile.py"
    if not demo_profile_path.is_file():
        fail("China controlled demo profile preparer must be packaged")
    demo_profile_content = demo_profile_path.read_text(encoding="utf-8")
    for required in (
        "sdoo.cn.demo-profile-preparation.v1",
        "--allow-demo-data",
        "CODEX-DEMO",
        "sudo.compliance.registration",
        "sudo.cn.taxpayer.classification",
        "action_verify",
        "_activation_issues",
        "China demo profile ready",
    ):
        if required not in demo_profile_content:
            fail(f"China controlled demo profile preparer is missing {required}")

    demo_closed_loop_path = (
        REPOSITORY_ROOT / "tools" / "prepare_cn_demo_closed_loop.py"
    )
    if not demo_closed_loop_path.is_file():
        fail("China controlled demo closed-loop preparer must be packaged")
    demo_closed_loop_content = demo_closed_loop_path.read_text(encoding="utf-8")
    for required in (
        "sdoo.cn.demo-closed-loop-preparation.v1",
        "--allow-demo-data",
        "CODEX-DEMO",
        "action_queue_compliance_assessment",
        "action_run_now",
        "action_require_correction",
        "action_create_task",
        "ensure_filing_archive",
        "action_open_cn_filing_archive",
        "action_mark_paid",
        "ensure_ai_guidance",
        "action_generate_cn_ai_guidance",
        "UPDATE sudo_compliance_task SET due_date",
        "cn_submission_integrity_state",
        "cn_payment_integrity_state",
        "sudo.cn.compliance.report",
        "China demo closed loop ready",
    ):
        if required not in demo_closed_loop_content:
            fail(f"China controlled demo closed-loop preparer is missing {required}")

    coverage_path = REPOSITORY_ROOT / "docs" / "CHINA_DELIVERY_OBJECTIVE_COVERAGE.md"
    if not coverage_path.is_file():
        fail("China delivery objective coverage matrix must be documented")
    coverage_content = coverage_path.read_text(encoding="utf-8")
    for required in (
        "# China Fiscal Compliance Pack Objective Coverage",
        "## Coverage Matrix",
        "Installable and upgradeable Odoo 19 plugin",
        "Odoo accounting and business-data basis",
        "External tax data and data sufficiency",
        "Source-governed and versioned rules",
        "Risk discovery and fact traceability",
        "Controlled AI guidance",
        "User experience for overview and next action",
        "audit_cn_objective_completion.py",
        "render_cn_signoff_evidence_template.py",
        "Production boundary",
        "Not A Completion Claim",
    ):
        if required not in coverage_content:
            fail(f"China delivery objective coverage is missing {required}")
    for referenced_path in _coverage_referenced_paths(coverage_content):
        if not _coverage_path_exists(referenced_path):
            fail(
                "China delivery objective coverage references a missing path: "
                f"{referenced_path}"
            )

    runbook_path = REPOSITORY_ROOT / "docs" / "DELIVERY_RUNBOOK_CN.md"
    if not runbook_path.is_file():
        fail("China delivery runbook must be documented")
    runbook_content = runbook_path.read_text(encoding="utf-8")
    for required in (
        "Production Sign-Off Evidence Draft",
        "Objective Completion Audit",
        "tools/audit_cn_objective_completion.py",
        "cn_objective_completion_audit_mNNN.json",
        "tools/render_cn_signoff_evidence_template.py",
        "cn_signoff_evidence_draft_mNNN.json",
        "validate_cn_signoff_evidence.py",
        "Ordered Sign-Off Evidence Chain",
        "tools/build_cn_signoff_evidence_chain.py",
        "--require-production-signoff-ready",
        "must be used for any production release",
        "automation. It exits non-zero",
        "Do not use the bootstrap status",
    ):
        if required not in runbook_content:
            fail(f"China delivery runbook is missing {required}")

    acceptance_tool = (
        REPOSITORY_ROOT / "tools" / "run_cn_delivery_acceptance.py"
    ).read_text(encoding="utf-8")
    for required in (
        'ROOT / "docs" / "CHINA_DELIVERY_INDEX.md"',
        'ROOT / "docs" / "CHINA_RELEASE_HANDOFF_CURRENT.md"',
        'ROOT / "docs" / "CHINA_BUSINESS_UAT_CHECKLIST.md"',
        'ROOT / "docs" / "CHINA_UAT_WALKTHROUGH_SCRIPT.md"',
        'ROOT / "docs" / "CHINA_DELIVERY_OBJECTIVE_COVERAGE.md"',
        'ROOT / "docs" / "CHINA_PRODUCTION_SIGNOFF_TEMPLATE.md"',
        'ROOT / "docs" / "CHINA_PRODUCTION_RELEASE_CONTROL.md"',
        'ROOT / "tools" / "check_cn_preview_health.py"',
        'ROOT / "tools" / "check_cn_preview_module.py"',
        'ROOT / "tools" / "check_cn_real_data_closed_loop.py"',
        'ROOT / "tools" / "prepare_cn_demo_profile.py"',
        'ROOT / "tools" / "prepare_cn_demo_closed_loop.py"',
        'ROOT / "tools" / "audit_cn_objective_completion.py"',
        'ROOT / "tools" / "build_cn_signoff_evidence_chain.py"',
        'ROOT / "tools" / "select_cn_latest_signoff_candidate.py"',
        'ROOT / "tools" / "export_cn_production_signoff_actions.py"',
        'ROOT / "tools" / "generate_cn_signoff_packet.py"',
        'ROOT / "tools" / "render_cn_signoff_evidence_template.py"',
        'ROOT / "tools" / "validate_cn_signoff_evidence.py"',
        'ROOT / "tools" / "test_latest_signoff_candidate.py"',
        'ROOT / "tools" / "test_signoff_validation.py"',
        '"summarize_cn_delivery_status.py"',
    ):
        if required not in acceptance_tool:
            fail(f"China delivery manifest coverage is missing {required}")

    status_tool = (
        REPOSITORY_ROOT / "tools" / "summarize_cn_delivery_status.py"
    ).read_text(encoding="utf-8")
    chain_tool_content = (
        REPOSITORY_ROOT / "tools" / "build_cn_signoff_evidence_chain.py"
    ).read_text(encoding="utf-8")
    latest_selector_content = (
        REPOSITORY_ROOT / "tools" / "select_cn_latest_signoff_candidate.py"
    ).read_text(encoding="utf-8")
    for required in (
        'preview_database = status.get("preview_database")',
        "status preview database is missing",
        "preview database mismatch",
        "preview_database_matches_status",
        "Preview database",
    ):
        if required not in latest_selector_content:
            fail(f"China latest sign-off selector is missing {required}")
    for required in (
        "--require-production-signoff-ready",
        "production sign-off readiness gate failed",
    ):
        if required not in chain_tool_content:
            fail(f"China sign-off chain production readiness guard is missing {required}")
    for required in (
        "DELIVERY_INDEX_PATH",
        "delivery_index",
        "BUSINESS_UAT_PATH",
        "business_uat",
        "UAT_WALKTHROUGH_PATH",
        "uat_walkthrough",
        "RELEASE_HANDOFF_PATH",
        "release_handoff",
        "OBJECTIVE_COVERAGE_PATH",
        "objective_coverage",
        "PRODUCTION_SIGNOFF_PATH",
        "production_signoff",
        "PREVIEW_HEALTH_TOOL_PATH",
        "preview_health_checker",
        "PREVIEW_MODULE_TOOL_PATH",
        "preview_module_checker",
        "REAL_DATA_CLOSED_LOOP_TOOL_PATH",
        "real_data_closed_loop_checker",
        "OBJECTIVE_AUDIT_TOOL_PATH",
        "objective_audit_tool",
        "--objective-audit",
        "objective_audit",
        "OBJECTIVE_AUDIT_SCHEMA",
        "Objective completion audit achieved",
        "sample_profiles",
        "SIGNOFF_PACKET_TOOL_PATH",
        "signoff_packet_tool",
        "SIGNOFF_EVIDENCE_RENDERER_TOOL_PATH",
        "signoff_evidence_renderer_tool",
        "SIGNOFF_VALIDATION_TOOL_PATH",
        "signoff_validation_tool",
        "SIGNOFF_CHAIN_TOOL_PATH",
        "signoff_chain_tool",
        "SIGNOFF_CANDIDATE_SELECTOR_TOOL_PATH",
        "signoff_candidate_selector_tool",
        "PRODUCTION_SIGNOFF_ACTIONS_TOOL_PATH",
        "production_signoff_actions_tool",
        "SIGNOFF_EVIDENCE_TEMPLATE_PATH",
        "signoff_evidence_template",
        "included_in_manifest",
        "Business UAT checklist in manifest",
        "Business UAT walkthrough script in manifest",
        "Current release handoff in manifest",
        "Objective coverage in manifest",
        "Production sign-off template in manifest",
        "Preview health checker in manifest",
        "Real-data closed-loop checker in manifest",
        "Objective completion auditor in manifest",
        "Sign-off packet generator in manifest",
        "Sign-off evidence renderer in manifest",
        "Sign-off evidence validator in manifest",
        "Production sign-off action checklist exporter in manifest",
        "Sign-off evidence template in manifest",
        "Delivery index in manifest",
        "readiness_gates",
        "business_uat_ready",
        "business_uat_blockers",
        "production_signoff_ready",
        "production_signoff_blockers",
        "--preview-health",
        "preview_health",
        "preview health result was not provided",
        "preview health result schema is invalid",
        "preview health URL does not match preview URL",
        "preview health check did not pass",
        "--preview-module",
        "preview_module",
        "preview module result was not provided",
        "preview module result schema is invalid",
        "preview module expected version does not match delivery version",
        "preview module check did not pass",
        "--upgrade-summary",
        "upgrade_summary",
        "upgrade_runtime_passed",
        "Odoo upgrade runtime tests did not pass",
        "--real-data-closed-loop",
        "real_data_closed_loop",
        "source_governance_summary",
        "Official source governance summary ready",
        "Official Source Governance Overview",
        "Official source governance issues",
        "--signoff-validation",
        "signoff_validation",
        "sign-off validation result schema is invalid",
        "sign-off validation version does not match delivery version",
        "sign-off validation source commit does not match delivery source commit",
        "sign-off validation preview URL does not match delivery preview URL",
        "sign-off validation did not pass",
        "blocked_objective_areas",
        "Production Blocked Objective Areas",
        "real-data closed-loop result was not provided",
        "real-data closed-loop result schema is invalid",
        "real-data closed-loop expected version does not match delivery version",
        "real-data demo readiness check did not pass",
        "Real-data setup demo ready",
        "Real-data demo ready",
        "Real-data closed-loop evidence ready",
        "Preview module ok",
        "Preview module version",
        "Preview health ok",
        "Preview health status code",
        "--require-business-uat-ready",
        "--require-production-signoff-ready",
        "business UAT readiness gate failed",
        "production sign-off readiness gate failed",
        "source_control",
        "source worktree was dirty when delivery was built",
        "Source branch",
        "Source commit",
        "Source worktree dirty",
        "--require-source-control-clean",
        "source-control readiness gate failed",
        "source control evidence is missing",
        "source commit is missing",
        "source branch is missing",
        "source worktree is not confirmed clean",
        "Business UAT ready",
        "Production sign-off ready",
        "## Readiness Gates",
    ):
        if required not in status_tool:
            fail(f"China delivery status objective coverage is missing {required}")

    build_tool = (
        REPOSITORY_ROOT / "tools" / "build_cn_delivery_bundle.py"
    ).read_text(encoding="utf-8")
    if "source_control" not in build_tool:
        fail("China delivery bundle metadata must include source control evidence")

    verify_tool = (
        REPOSITORY_ROOT / "tools" / "verify_cn_delivery_artifacts.py"
    ).read_text(encoding="utf-8")
    for required in (
        "source_control",
        "git_commit",
        "bundle/manifest source control",
        "summary/manifest source control",
        "git commit/source control commit",
        "summary git commit",
    ):
        if required not in verify_tool:
            fail(f"China delivery artifact source control verification is missing {required}")

    signoff_packet_tool_content = (
        REPOSITORY_ROOT / "tools" / "generate_cn_signoff_packet.py"
    ).read_text(encoding="utf-8")
    for required in (
        "blocker_summary_walkthrough",
        "uat_walkthrough_script_in_manifest",
        "Screen-by-screen UAT walkthrough script is included in the delivery manifest",
        "current_release_handoff_in_manifest",
        "Current release handoff is included in the delivery manifest",
        "signoff_evidence_template_in_manifest",
        "Machine-readable production sign-off evidence template is included in the delivery manifest",
        "signoff_evidence_renderer_in_manifest",
        "Version-aligned production sign-off evidence draft renderer is included in the delivery manifest",
        "objective_completion_audit_present",
        "Objective completion audit is attached and exposes evidence-ready versus blocked objective areas",
        "workbench_summary_evidence",
        "has_workbench_summary_evidence",
        "risk_task_report_summary_evidence",
        "has_risk_task_report_summary_evidence",
        "has_risk_finding_visibility_evidence",
        "has_remediation_task_visibility_evidence",
        "has_remediation_verification_rescan_evidence",
        "has_report_visibility_evidence",
        "has_reviewer_view_contract_evidence",
        "reviewer_view_contracts",
        "ux_view_clarity_contract_evidence",
        "has_ux_view_clarity_contract_evidence",
        "ux_view_clarity_contracts",
        "Core review pages expose status badges, risk coloring, key amounts, owners, deadlines, blockers and next actions",
        "upgrade_migration_chain_evidence",
        "Current China compliance release includes the module manifest, static validator and current post-migration script in the delivery manifest",
        "upgrade_runtime_evidence",
        "Current China compliance release passed an Odoo module update run using -u sudo_country_pack_cn",
        "upgrade_migration_chain",
        "upgrade_runtime_passed",
        "multi_company_security_contract_evidence",
        "has_multi_company_security_contract_evidence",
        "multi_company_security_contracts",
        "native_menu_action_contract_evidence",
        "has_menu_action_contract_evidence",
        "menu_action_contracts",
        "Core China compliance menus are native Odoo menu entries bound to expected window actions and compliance groups",
        "workbench_action_contract_evidence",
        "has_workbench_action_contract_evidence",
        "workbench_action_contracts",
        "Workbench closed-loop shortcuts return native Odoo window actions scoped to the active China compliance profile",
        "evidence_filing_payment_summary_evidence",
        "has_evidence_filing_payment_summary_evidence",
        "rule_source_governance_evidence",
        "has_official_source_freshness_evidence",
        "has_rule_professional_signoff_evidence",
        "has_rule_checksum_traceability_evidence",
        "has_rule_source_governance_evidence",
        "customer_scope_gap_review_evidence",
        "has_customer_scope_gap_review_evidence",
        "has_customer_data_scope_review_evidence",
        "has_customer_evidence_gap_review_evidence",
        "has_open_high_risk_review_evidence",
        "official_source_governance_summary",
        "Official source governance summary exposes freshness, monitoring and rule sign-off issue counts",
        "iit_payroll_withholding_scope_evidence",
        "has_iit_payroll_withholding_scope_evidence",
        "cross_border_review_scope_evidence",
        "has_cross_border_review_scope_evidence",
        "workbench action/rule-basis/limitation summaries",
        "data readiness, evidence, filing/payment archive, remediation, report center and report readiness blocker summaries",
        "controlled AI guidance disclosures",
        "AI provider, prompt version, input/output checksum, record checksum and professional warning visibility",
        "missing_human_evidence",
        "Missing Human Evidence",
        "objective_areas",
        "Objective areas",
    ):
        if required not in signoff_packet_tool_content:
            fail(f"China sign-off packet blocker walkthrough is missing {required}")

    signoff_validation_tool_content = (
        REPOSITORY_ROOT / "tools" / "validate_cn_signoff_evidence.py"
    ).read_text(encoding="utf-8")
    objective_audit_tool_content = (
        REPOSITORY_ROOT / "tools" / "audit_cn_objective_completion.py"
    ).read_text(encoding="utf-8")
    for required in (
        "AUDIT_SCHEMA",
        "audit",
        "production_signoff_gate",
        "completion_blockers",
        "state_counts",
        "tax_domain_coverage",
        "production_blocker_coverage_binding",
        "coverage_evidence_matches_packet",
        "preview_database",
        "upgrade_migration_chain",
        "upgrade_runtime_passed",
        "has_ux_view_clarity_contract_evidence",
        "ux_view_clarity_contract",
        "ux_view_clarity_contracts",
        "Risk center, remediation tracker and report clarity",
        "has_menu_action_contract_evidence",
        "menu_action_contract",
        "menu_action_contracts",
        "has_workbench_action_contract_evidence",
        "workbench_action_contract",
        "workbench_action_contracts",
        "Native Odoo menu, action, multi-company and record-rule security contract",
        "current_migration",
        "migration_scripts",
        "--require-achieved",
    ):
        if required not in objective_audit_tool_content:
            fail(f"China objective completion auditor is missing {required}")
    signoff_renderer_tool_content = (
        REPOSITORY_ROOT / "tools" / "render_cn_signoff_evidence_template.py"
    ).read_text(encoding="utf-8")
    for required in (
        "render_template",
        "PACKET_SCHEMA",
        "EVIDENCE_SCHEMA",
        "source_commit",
        "production_actions",
        "acceptable_decisions",
        "objective_areas",
        "production_blocker_coverage",
        "production_blocker_coverage_note",
        "placeholder_notice",
    ):
        if required not in signoff_renderer_tool_content:
            fail(f"China sign-off evidence renderer is missing {required}")
    for required in (
        '"preview_url": packet.get("preview_url")',
        "sign-off evidence decisions must be a list",
        "sign-off evidence decision keys must be unique",
        "sign-off evidence contains unknown decision keys",
        "reviewer is missing or still a template placeholder",
        "date must be YYYY-MM-DD",
        "evidence_reference is missing or still a template placeholder",
        "PLACEHOLDER_TEXTS",
        "_valid_iso_date",
        "blocked_objective_areas",
        "objective_areas are missing from the sign-off packet",
        "sign-off evidence production_blocker_coverage does not match the packet",
        "production_blocker_coverage_binding",
        "evidence_matches_packet",
        "ACTION_EVIDENCE_REQUIREMENTS",
        "evidence_reference or notes must mention",
        "walkthrough script",
        "governance summary",
        "monitoring",
    ):
        if required not in signoff_validation_tool_content:
            fail(f"China sign-off validation binding is missing {required}")

    signoff_test_content = (
        REPOSITORY_ROOT / "tools" / "test_signoff_validation.py"
    ).read_text(encoding="utf-8")
    delivery_status_tool_content = (
        REPOSITORY_ROOT / "tools" / "summarize_cn_delivery_status.py"
    ).read_text(encoding="utf-8")
    signoff_template_content = (
        REPOSITORY_ROOT / "docs" / "samples" / "cn_signoff_evidence_template.json"
    ).read_text(encoding="utf-8")
    for required in (
        "test_signoff_packet_requires_blocker_summary_walkthrough",
        "test_signoff_packet_surfaces_uat_walkthrough_script_manifest_evidence",
        "test_signoff_packet_surfaces_current_release_handoff_manifest_evidence",
        "test_signoff_packet_surfaces_signoff_evidence_template_manifest_evidence",
        "test_signoff_packet_surfaces_signoff_evidence_renderer_manifest_evidence",
        "test_signoff_packet_surfaces_objective_completion_audit_evidence",
        "test_signoff_packet_surfaces_workbench_summary_automated_evidence",
        "test_signoff_packet_surfaces_risk_task_report_summary_evidence",
        "test_signoff_packet_blocks_when_risk_visibility_evidence_is_incomplete",
        "test_signoff_packet_blocks_when_reviewer_view_contract_is_missing",
        "test_objective_audit_blocks_when_reviewer_view_contract_is_missing",
        "test_signoff_packet_surfaces_ux_view_clarity_contract_evidence",
        "test_signoff_packet_blocks_when_ux_view_clarity_contract_is_missing",
        "test_objective_audit_blocks_when_ux_view_clarity_contract_is_missing",
        "test_delivery_status_preserves_ux_view_clarity_contract_details",
        "test_delivery_status_markdown_lists_ux_view_clarity_contract_evidence",
        "ux_view_clarity_contract_evidence",
        "test_signoff_packet_surfaces_multi_company_security_contract_evidence",
        "test_signoff_packet_blocks_when_multi_company_security_contract_is_missing",
        "test_objective_audit_blocks_when_multi_company_security_contract_is_missing",
        "test_delivery_status_preserves_multi_company_security_contract_details",
        "test_signoff_packet_surfaces_native_menu_action_contract_evidence",
        "test_signoff_packet_blocks_when_menu_action_contract_is_missing",
        "test_objective_audit_blocks_when_menu_action_contract_is_missing",
        "test_delivery_status_preserves_menu_action_contract_details",
        "test_delivery_status_markdown_lists_menu_action_contract_evidence",
        "native_menu_action_contract_evidence",
        "test_signoff_packet_surfaces_workbench_action_contract_evidence",
        "test_signoff_packet_blocks_when_workbench_action_contract_is_missing",
        "test_objective_audit_blocks_when_workbench_action_contract_is_missing",
        "test_delivery_status_preserves_workbench_action_contract_details",
        "test_delivery_status_markdown_lists_workbench_action_contract_evidence",
        "workbench_action_contract_evidence",
        "test_signoff_packet_surfaces_upgrade_migration_chain_evidence",
        "test_signoff_packet_surfaces_upgrade_runtime_evidence",
        "test_objective_audit_blocks_when_upgrade_migration_chain_is_missing",
        "test_objective_audit_blocks_when_upgrade_runtime_is_missing",
        "test_delivery_status_preserves_upgrade_migration_chain_details",
        "test_delivery_status_markdown_lists_upgrade_migration_chain_evidence",
        "test_delivery_status_markdown_lists_upgrade_runtime_evidence",
        "test_delivery_status_requires_current_migration_in_manifest",
        "test_delivery_status_requires_upgrade_runtime_summary",
        "test_signoff_packet_surfaces_remediation_verification_rescan_evidence",
        "test_signoff_packet_blocks_when_remediation_rescan_evidence_is_missing",
        "test_signoff_packet_surfaces_evidence_filing_payment_summary_evidence",
        "test_signoff_packet_surfaces_official_source_governance_summary",
        "test_signoff_packet_surfaces_rule_governance_detail_evidence",
        "test_signoff_packet_blocks_when_rule_governance_detail_is_missing",
        "test_objective_audit_blocks_when_rule_governance_detail_is_missing",
        "test_signoff_packet_surfaces_customer_scope_gap_review_evidence",
        "test_signoff_packet_blocks_when_customer_scope_gap_review_is_missing",
        "test_objective_audit_blocks_when_customer_scope_gap_review_is_missing",
        "test_signoff_packet_surfaces_iit_and_cross_border_scope_evidence",
        "test_delivery_status_markdown_lists_workbench_summary_evidence",
        "test_delivery_status_markdown_lists_uat_walkthrough_script",
        "test_delivery_status_requires_current_release_handoff_in_manifest",
        "test_delivery_status_requires_signoff_evidence_template_in_manifest",
        "test_delivery_status_requires_signoff_evidence_renderer_in_manifest",
        "production_signoff_required_actions",
        "preview_ready",
        "preview_readiness_blockers",
        "compliance_scope_ready",
        "compliance_scope_blockers",
        "Production Sign-off Required Human Actions",
        "Production Sign-off Blocker Action Matrix",
        "Production Blocker Coverage Binding",
        "production_signoff_blocker_action_matrix",
        "production_deployment_decision",
        "test_delivery_status_surfaces_preview_readiness_blockers",
        "test_delivery_status_surfaces_compliance_scope_blockers",
        "test_delivery_status_markdown_lists_production_blocker_action_matrix",
        "test_delivery_status_required_actions_match_signoff_packet_evidence",
        "test_rendered_signoff_evidence_draft_tracks_packet_actions_and_commit",
        "test_rendered_signoff_evidence_draft_cannot_pass_with_placeholders",
        "test_signoff_evidence_requires_packet_blocker_coverage_match",
        "test_objective_audit_marks_production_signoff_blocker",
        "test_objective_audit_blocks_when_risk_visibility_evidence_is_missing",
        "test_objective_audit_blocks_when_remediation_rescan_evidence_is_missing",
        "test_objective_audit_is_achieved_after_valid_production_signoff",
        "test_objective_audit_rejects_mismatched_signoff_validation_binding",
        "test_signoff_chain_final_packet_includes_objective_audit",
        "test_signoff_chain_accepts_completed_human_evidence",
        "test_delivery_status_requires_objective_auditor_in_manifest",
        "test_delivery_status_markdown_lists_risk_task_report_summary_evidence",
        "test_delivery_status_preserves_reviewer_view_contract_details",
        "test_delivery_status_markdown_lists_evidence_filing_payment_summary_evidence",
        "test_delivery_status_markdown_lists_official_source_governance_overview",
        "test_delivery_status_markdown_lists_iit_and_cross_border_scope_evidence",
        "test_delivery_status_lists_tax_domain_coverage_overview",
        "test_missing_blocker_summary_walkthrough_blocks_production_gate",
        "test_signoff_validation_blocks_actions_without_objective_areas",
        "test_generic_signoff_evidence_reference_blocks_production_gate",
        "test_missing_ai_checksum_scope_blocks_ux_walkthrough",
        "test_signoff_evidence_requires_uat_walkthrough_script_reference",
        "test_signoff_evidence_requires_source_governance_summary_reference",
        "test_delivery_status_requires_uat_walkthrough_script_in_manifest",
        "blocked_objective_areas",
        "blocker_summary_walkthrough",
        "upgrade_migration_chain_evidence",
        "upgrade_runtime_evidence",
        "Upgrade Migration Chain Evidence",
    ):
        if required not in signoff_test_content:
            fail(f"China sign-off blocker walkthrough runtime coverage is missing {required}")
        if required == "blocker_summary_walkthrough" and required not in signoff_template_content:
            fail("China sign-off evidence template is missing blocker_summary_walkthrough")
    for required in (
        "controlled AI guidance evidence",
        "controlled AI limitations",
        "AI provider, prompt version, input/output checksum, record checksum and professional warnings",
        "CHINA_UAT_WALKTHROUGH_SCRIPT.md",
        "Official-source freshness monitoring result and governance summary reference",
        "source governance summary",
        '"objective_areas"',
        '"addresses_blockers"',
        "business UAT decision must be recorded outside this automated status",
        "current official sources and released rules require professional sign-off evidence",
        "customer-specific data gaps, evidence gaps and open critical risks must be reviewed",
    ):
        if required not in signoff_template_content:
            fail(f"China sign-off evidence template is missing {required}")
    signoff_template = json.loads(signoff_template_content)
    for decision in signoff_template.get("decisions") or []:
        if not decision.get("objective_areas"):
            fail(
                "China sign-off evidence template decision is missing objective_areas: "
                f"{decision.get('key')}"
            )
        if not decision.get("addresses_blockers"):
            fail(
                "China sign-off evidence template decision is missing addresses_blockers: "
                f"{decision.get('key')}"
            )
    for required in (
        "Workbench Summary Evidence",
        "Workbench summary evidence ready",
        "Risk/task/report summary evidence ready",
        "Risk, Remediation and Report Summary Evidence",
        "Evidence/filing/payment summary evidence ready",
        "Evidence, Filing and Payment Archive Summary Evidence",
        "Rule/source governance evidence ready",
        "Official source governance summary ready",
        "Official Source Governance Overview",
        "Rule And Source Governance Evidence",
        "Official Sources",
        "Released Rule Versions",
        "Source Monitor Runs",
        "IIT payroll withholding scope evidence ready",
        "Cross-border review scope evidence ready",
        "IIT Payroll Withholding Scope Evidence",
        "Cross-Border Review Scope Evidence",
        "tax_domain_coverage",
        "Tax Domain Coverage Overview",
        "VAT invoice / filing / payment",
        "CIT accounting / filing",
        "IIT payroll / withholding / payment",
        "Cross-border and withholding review",
        "Action summary",
        "Rule basis",
        "Limitations",
        "Uncertainty",
        "sample_profiles",
        "sample_findings",
        "sample_remediation_tasks",
        "sample_reports",
        "sample_evidence",
        "sample_filing_archives",
        "sample_authority_sources",
        "sample_rule_versions",
        "sample_source_monitor_runs",
        "sample_iit_reconciliation_runs",
        "sample_cross_border_transactions",
    ):
        if required not in delivery_status_tool_content:
            fail(f"China delivery status workbench summary evidence is missing {required}")


def validate_china_native_menu_integration() -> None:
    allowed_parents = {
        "sudo_global_finance.menu_global_finance_root",
        "sudo_global_finance.menu_compliance_management",
        "sudo_global_finance.menu_compliance_configuration",
    }
    allowed_group_prefixes = (
        "sudo_global_finance.group_compliance_",
        "sudo_country_pack_cn.group_cn_",
    )
    menu_count = 0
    for path in sorted((ADDON_ROOT / "views").glob("*.xml")):
        root = ElementTree.parse(path).getroot()
        for menu in root.iter("menuitem"):
            menu_id = menu.attrib.get("id", "")
            if not menu_id.startswith("menu_cn"):
                continue
            menu_count += 1
            parent = menu.attrib.get("parent")
            if parent not in allowed_parents:
                fail(
                    "China menu entries must stay under the native global "
                    f"finance compliance menus: {menu_id} parent={parent!r}"
                )
            action = menu.attrib.get("action")
            if not action:
                fail(f"China menu entry must point to a native action: {menu_id}")
            groups = [
                group.strip()
                for group in (menu.attrib.get("groups") or "").split(",")
                if group.strip()
            ]
            if not groups:
                fail(f"China menu entry must declare compliance groups: {menu_id}")
            if any(
                not group.startswith(allowed_group_prefixes)
                for group in groups
            ):
                fail(
                    "China menu entry must only use compliance groups: "
                    f"{menu_id} groups={groups}"
                )
    if menu_count < 30:
        fail("China native menu integration unexpectedly lost menu coverage")


def validate_china_company_security_contract() -> None:
    allowed_without_company_rule = {
        "model_sudo_cn_authority_source_monitor_run",
        "model_sudo_cn_cit_period_reconciliation_wizard",
        "model_sudo_cn_einvoice_manual_match_wizard",
        "model_sudo_cn_einvoice_reconciliation_wizard",
        "model_sudo_cn_iit_period_reconciliation_wizard",
        "model_sudo_cn_jurisdiction_version",
        "model_sudo_cn_rule_review_citation",
        "model_sudo_cn_rule_review_packet",
        "model_sudo_cn_tax_data_import_wizard",
        "model_sudo_cn_vat_period_reconciliation_wizard",
    }
    with (ADDON_ROOT / "security" / "ir.model.access.csv").open(
        encoding="utf-8"
    ) as handle:
        access_rows = list(csv.DictReader(handle))
    allowed_acl_group_prefixes = (
        "sudo_global_finance.group_compliance_",
        "sudo_country_pack_cn.group_cn_",
    )
    accessed_models = {
        row["model_id:id"]
        for row in access_rows
        if row["model_id:id"].startswith("model_sudo_cn_")
    }
    for row in access_rows:
        group = row["group_id:id"]
        if not group.startswith(allowed_acl_group_prefixes):
            fail(
                "China ACL rows must only grant compliance groups: "
                f"{row['id']} group={group!r}"
            )
        if group.endswith("group_compliance_user") and row["perm_unlink"] != "0":
            fail(f"ordinary China compliance users must not delete records: {row['id']}")
        if group.endswith(("group_compliance_rule_approver", "group_cn_report_approver")):
            if row["perm_create"] != "0" or row["perm_unlink"] != "0":
                fail(
                    "China approval groups must not create or delete governed records: "
                    f"{row['id']}"
                )

    security_root = ElementTree.parse(
        ADDON_ROOT / "security" / "compliance_security.xml"
    ).getroot()
    ruled_models: set[str] = set()
    for record in security_root.findall(".//record[@model='ir.rule']"):
        fields = {field.attrib.get("name"): field for field in record.findall("field")}
        model_ref = fields.get("model_id").attrib.get("ref") if fields.get("model_id") is not None else ""
        domain = field_text(fields, "domain_force", record.attrib.get("id", "company rule"))
        if model_ref.startswith("model_sudo_cn_"):
            ruled_models.add(model_ref)
            if "company_ids" not in domain or "company_id" not in domain:
                fail(
                    "China company record rules must enforce allowed companies: "
                    f"{record.attrib.get('id')} domain={domain!r}"
                )
    missing_rules = accessed_models - ruled_models - allowed_without_company_rule
    if missing_rules:
        fail(
            "China ACL models must either have an allowed-company record rule "
            f"or be explicitly allowlisted as global/wizard models: {sorted(missing_rules)}"
        )
    stale_allowlist = allowed_without_company_rule - accessed_models
    if stale_allowlist:
        fail(
            "China company security allowlist references models no longer in ACL: "
            f"{sorted(stale_allowlist)}"
        )


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
    validate_search_views_do_not_filter_nonstored_computed_fields()
    validate_python_domains_do_not_search_nonstored_computed_fields()
    validate_taxpayer_classification_security()
    validate_external_dataset_security()
    validate_invoice_normalization_security()
    validate_invoice_reconciliation()
    validate_tax_data_normalization()
    validate_vat_period_reconciliation()
    validate_cit_period_reconciliation()
    validate_iit_period_reconciliation()
    validate_iit_filing_payment_archive()
    validate_filing_payment_archive()
    validate_tax_impact_review()
    validate_formal_compliance_report()
    validate_official_source_change_monitoring()
    validate_china_jurisdiction_governance(manifest)
    validate_china_compliance_workbench(manifest)
    validate_delivery_objective_coverage()
    validate_china_native_menu_integration()
    validate_china_company_security_contract()
    validate_xbrl_parser_addon()
    print(f"validated {ADDON_ROOT.name} {manifest['version']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, SyntaxError, UnicodeError) as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
