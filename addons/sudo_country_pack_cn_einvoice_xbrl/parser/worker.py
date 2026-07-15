from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import logging
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

from contract import (
    ContractError,
    SOURCE_LIMITS,
    TAXONOMY_LIMITS,
    discover_xbrl_instances,
    safe_extract_zip,
    sha256_file,
    xml_root_tag,
)
from normalizer import normalize_model


SUPPORTED_ARELLE_VERSION = "2.42.1"
XBRL_INSTANCE_TAG = "{http://www.xbrl.org/2003/instance}xbrl"
LINKBASE_NAMESPACE = "http://www.xbrl.org/2003/linkbase"
XLINK_NAMESPACE = "http://www.w3.org/1999/xlink"
ROLE_TYPE_TAG = "{%s}roleType" % LINKBASE_NAMESPACE
STRICT_COMPATIBILITY_PROFILE = "strict"
ROLE_URI_WHITESPACE_PROFILE = "trim_role_uri_whitespace_v1"
SUPPORTED_COMPATIBILITY_PROFILES = {
    STRICT_COMPATIBILITY_PROFILE,
    ROLE_URI_WHITESPACE_PROFILE,
}
MAX_RESULT_BYTES = 100 * 1024 * 1024
ROLE_TYPE_START_TAG_PATTERN = re.compile(
    rb"<(?:[A-Za-z_][A-Za-z0-9_.-]*:)?roleType(?=[\s/>])[^<>]*>",
    re.DOTALL,
)
ROLE_URI_ATTRIBUTE_PATTERN = re.compile(
    rb"(?P<prefix>\broleURI\s*=\s*)(?P<quote>['\"])(?P<value>[^'\"]*)(?P=quote)",
    re.DOTALL,
)
XML_WHITESPACE = b" \t\r\n"


class WorkerError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def _apply_resource_limits(request):
    try:
        import resource
    except ImportError:
        return
    memory_limit = int(request.get("memory_limit_bytes") or 0)
    cpu_limit = int(request.get("cpu_limit_seconds") or 0)
    if memory_limit > 0:
        resource.setrlimit(
            resource.RLIMIT_AS,
            (memory_limit, memory_limit),
        )
    if cpu_limit > 0:
        resource.setrlimit(
            resource.RLIMIT_CPU,
            (cpu_limit, cpu_limit + 5),
        )


def _safe_source_name(value):
    name = PurePosixPath(str(value or "source.xml").replace("\\", "/")).name
    return name if name not in ("", ".", "..") else "source.xml"


def _prepare_source(source_path, source_name, work_root):
    source_path = Path(source_path)
    source_root = work_root / "source"
    source_root.mkdir(mode=0o700)
    suffix = Path(source_name).suffix.lower() or source_path.suffix.lower()
    if suffix == ".zip":
        safe_extract_zip(source_path, source_root, SOURCE_LIMITS)
        instances = discover_xbrl_instances(source_root)
    elif suffix in {".xml", ".xbrl"}:
        if source_path.stat().st_size > SOURCE_LIMITS["max_member_bytes"]:
            raise WorkerError("SOURCE_TOO_LARGE", "XBRL 源文件大小超限。")
        target = source_root / _safe_source_name(source_name)
        shutil.copyfile(source_path, target)
        if xml_root_tag(target) != XBRL_INSTANCE_TAG:
            raise WorkerError("NOT_XBRL_INSTANCE", "源文件不是 XBRL 实例文档。")
        instances = [target]
    else:
        raise WorkerError("UNSUPPORTED_SOURCE_FORMAT", "仅支持 XML、XBRL 或 ZIP。")
    return source_root, instances


def _taxonomy_tree_checksum(taxonomy_root):
    digest = hashlib.sha256()
    paths = (
        candidate
        for candidate in taxonomy_root.rglob("*")
        if candidate.is_file()
    )
    for path in sorted(
        paths,
        key=lambda item: item.relative_to(taxonomy_root).as_posix(),
    ):
        relative_name = path.relative_to(taxonomy_root).as_posix().encode(
            "utf-8"
        )
        digest.update(len(relative_name).to_bytes(8, "big"))
        digest.update(relative_name)
        digest.update(sha256_file(path).encode("ascii"))
    return digest.hexdigest()


def _patch_role_uri_whitespace(content, expected_patch_count):
    patch_count = 0

    def patch_start_tag(match):
        nonlocal patch_count

        def patch_attribute(attribute_match):
            nonlocal patch_count
            value = attribute_match.group("value")
            normalized = value.strip(XML_WHITESPACE)
            if value == normalized:
                return attribute_match.group(0)
            if not normalized:
                raise WorkerError(
                    "INVALID_ROLE_URI_COMPATIBILITY",
                    "角色 URI 不能在兼容处理后变为空值。",
                )
            patch_count += 1
            return b"".join(
                (
                    attribute_match.group("prefix"),
                    attribute_match.group("quote"),
                    normalized,
                    attribute_match.group("quote"),
                )
            )

        return ROLE_URI_ATTRIBUTE_PATTERN.sub(
            patch_attribute,
            match.group(0),
        )

    patched = ROLE_TYPE_START_TAG_PATTERN.sub(patch_start_tag, content)
    if patch_count != expected_patch_count:
        raise WorkerError(
            "UNSAFE_ROLE_URI_COMPATIBILITY_ENCODING",
            "角色 URI 空白无法通过受控最小字节修改安全处理。",
        )
    try:
        original_root = ElementTree.fromstring(content)
        patched_root = ElementTree.fromstring(patched)
    except ElementTree.ParseError as exc:
        raise WorkerError(
            "UNSAFE_ROLE_URI_COMPATIBILITY_ENCODING",
            "角色 URI 空白无法通过受控最小字节修改安全处理。",
        ) from exc
    expected_role_uris = [
        (role_type.get("roleURI") or "").strip()
        for role_type in original_root.iter(ROLE_TYPE_TAG)
    ]
    actual_role_uris = [
        role_type.get("roleURI") or ""
        for role_type in patched_root.iter(ROLE_TYPE_TAG)
    ]
    if actual_role_uris != expected_role_uris:
        raise WorkerError(
            "UNSAFE_ROLE_URI_COMPATIBILITY_ENCODING",
            "角色 URI 空白无法通过受控最小字节修改安全处理。",
        )
    return patched


def _apply_taxonomy_compatibility(taxonomy_root, profile):
    if profile not in SUPPORTED_COMPATIBILITY_PROFILES:
        raise WorkerError(
            "UNSUPPORTED_COMPATIBILITY_PROFILE",
            "分类标准技术兼容方案不在允许范围内。",
        )
    patched_files = []
    patch_count = 0
    xsd_paths = (
        path
        for path in taxonomy_root.rglob("*")
        if path.is_file() and path.suffix.lower() == ".xsd"
    )
    for path in sorted(
        xsd_paths,
        key=lambda item: item.relative_to(taxonomy_root).as_posix(),
    ):
        content = path.read_bytes()
        if len(content) > 5 * 1024 * 1024:
            raise WorkerError("XSD_TOO_LARGE", "分类标准 XSD 文件超限。")
        if b"<!DOCTYPE" in content.upper():
            raise WorkerError(
                "XML_DTD_FORBIDDEN",
                "分类标准不能包含 DTD。",
            )
        try:
            parser = ElementTree.XMLParser(
                target=ElementTree.TreeBuilder(insert_comments=True)
            )
            tree = ElementTree.parse(path, parser=parser)
        except (OSError, ElementTree.ParseError) as exc:
            raise WorkerError(
                "INVALID_TAXONOMY_XSD",
                "分类标准包含无效 XSD。",
            ) from exc
        file_patch_count = 0
        for role_type in tree.getroot().iter(ROLE_TYPE_TAG):
            role_uri = role_type.get("roleURI") or ""
            normalized = role_uri.strip()
            if role_uri == normalized:
                continue
            if not normalized:
                raise WorkerError(
                    "INVALID_ROLE_URI_COMPATIBILITY",
                    "角色 URI 不能在兼容处理后变为空值。",
                )
            patch_count += 1
            if profile == ROLE_URI_WHITESPACE_PROFILE:
                file_patch_count += 1
        if file_patch_count:
            patched_files.append(
                (
                    path,
                    _patch_role_uri_whitespace(content, file_patch_count),
                )
            )
    if patch_count and profile == STRICT_COMPATIBILITY_PROFILE:
        raise WorkerError(
            "TAXONOMY_COMPATIBILITY_REQUIRED",
            "分类标准包含已识别的角色 URI 空白问题，严格模式拒绝处理。",
        )
    if not patch_count and profile == ROLE_URI_WHITESPACE_PROFILE:
        raise WorkerError(
            "COMPATIBILITY_PROFILE_NOT_APPLICABLE",
            "分类标准不存在所选技术兼容方案对应的问题。",
        )
    for path, patched_content in patched_files:
        path.write_bytes(patched_content)
    return patch_count, _taxonomy_tree_checksum(taxonomy_root)


def _prepare_taxonomy(
    taxonomy_path,
    entry_point_path,
    work_root,
    compatibility_profile,
    expected_patch_count,
):
    taxonomy_root = work_root / "taxonomy"
    taxonomy_root.mkdir(mode=0o700, parents=True)
    safe_extract_zip(taxonomy_path, taxonomy_root, TAXONOMY_LIMITS)
    entry_parts = PurePosixPath(entry_point_path).parts
    entry_point = taxonomy_root.joinpath(*entry_parts).resolve()
    if taxonomy_root.resolve() not in entry_point.parents:
        raise WorkerError("UNSAFE_ENTRY_POINT", "分类标准入口路径越界。")
    if not entry_point.is_file():
        raise WorkerError("ENTRY_POINT_NOT_FOUND", "分类标准入口文件不存在。")
    patch_count, working_checksum = _apply_taxonomy_compatibility(
        taxonomy_root,
        compatibility_profile,
    )
    if patch_count != expected_patch_count:
        raise WorkerError(
            "TAXONOMY_COMPATIBILITY_COUNT_MISMATCH",
            "分类标准兼容修正数与封存记录不一致。",
        )
    return entry_point, patch_count, working_checksum


def _rewrite_schema_reference(instance_path, entry_point, work_root, index):
    try:
        from lxml import etree
    except ImportError as exc:
        raise WorkerError("LXML_NOT_AVAILABLE", "Arelle 的 lxml 依赖不可用。") from exc
    parser = etree.XMLParser(
        resolve_entities=False,
        load_dtd=False,
        no_network=True,
        huge_tree=False,
        remove_comments=False,
    )
    try:
        tree = etree.parse(str(instance_path), parser)
    except (OSError, etree.XMLSyntaxError) as exc:
        raise WorkerError("INVALID_INSTANCE_XML", "XBRL 实例 XML 无效。") from exc
    if tree.getroot().tag != XBRL_INSTANCE_TAG:
        raise WorkerError("NOT_XBRL_INSTANCE", "源文件不是 XBRL 实例文档。")
    schema_refs = tree.xpath(
        "/xbrli:xbrl/link:schemaRef",
        namespaces={
            "xbrli": "http://www.xbrl.org/2003/instance",
            "link": LINKBASE_NAMESPACE,
        },
    )
    if len(schema_refs) != 1:
        raise WorkerError(
            "SCHEMA_REFERENCE_COUNT",
            "XBRL 实例必须且只能包含一个分类标准引用。",
        )
    prepared_root = work_root / "prepared"
    prepared_root.mkdir(mode=0o700, exist_ok=True)
    relative_entry_point = os.path.relpath(
        entry_point,
        prepared_root,
    ).replace(os.sep, "/")
    schema_refs[0].set(
        "{%s}href" % XLINK_NAMESPACE,
        relative_entry_point,
    )
    prepared = prepared_root / ("instance-%06d.xml" % index)
    tree.write(
        str(prepared),
        encoding="UTF-8",
        xml_declaration=True,
        pretty_print=False,
    )
    return prepared


def _log_level(message):
    level = message.get("level") or message.get("levelname") or ""
    if isinstance(level, int):
        return logging.getLevelName(level).upper()
    return str(level).upper()


def _log_code(message):
    code = message.get("messageCode") or message.get("code") or "UNCLASSIFIED"
    return str(code)[:128]


def _log_digest(messages):
    canonical = []
    for message in messages:
        canonical.append(
            {
                "level": _log_level(message),
                "code": _log_code(message),
                "message": str(
                    message.get("msg") or message.get("message") or ""
                )[:2000],
            }
        )
    content = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _validation_counts(messages):
    warning_count = 0
    error_count = 0
    error_codes = []
    for message in messages:
        level = _log_level(message)
        if level in {"WARNING", "WARN"}:
            warning_count += 1
        elif level in {"ERROR", "CRITICAL", "FATAL"}:
            error_count += 1
            error_codes.append(_log_code(message))
    return warning_count, error_count, list(dict.fromkeys(error_codes))[:10]


def _parse_instance(prepared_path, source_key, namespace):
    try:
        from arelle.RuntimeOptions import RuntimeOptions
        from arelle.api.Session import Session
    except ImportError as exc:
        raise WorkerError("ARELLE_NOT_AVAILABLE", "Arelle 运行库不可用。") from exc
    options = RuntimeOptions(
        entrypointFile=str(prepared_path),
        internetConnectivity="offline",
        keepOpen=True,
        logFile="logToStructuredMessage",
        logFormat="[%(messageCode)s] %(message)s",
        logPropagate=False,
        validate=True,
        disablePersistentConfig=True,
    )
    with Session() as session:
        run_result = session.run(options)
        models = session.get_models()
        messages = session.get_log_messages()
        if len(models) != 1:
            raise WorkerError(
                "ARELLE_MODEL_COUNT",
                "Arelle 未返回唯一 XBRL 模型。",
            )
        payload, diagnostics = normalize_model(
            models[0],
            source_key,
            namespace,
        )
    warning_count, error_count, error_codes = _validation_counts(messages)
    warning_count += sum(
        item["severity"] == "warning" for item in diagnostics
    )
    error_count += sum(item["severity"] == "error" for item in diagnostics)
    error_codes.extend(
        item["code"]
        for item in diagnostics
        if item["severity"] == "error"
    )
    if not run_result and not error_count:
        error_count = 1
        error_codes.append("ARELLE_RUN_FAILED")
    if not payload.get("source_fact_count"):
        error_count += 1
        error_codes.append("NO_EXPECTED_NAMESPACE_FACTS")
    return {
        "document": payload,
        "warning_count": warning_count,
        "error_count": error_count,
        "error_codes": list(dict.fromkeys(error_codes))[:10],
        "messages": messages,
    }


def execute(request):
    _apply_resource_limits(request)
    arelle_version = importlib.metadata.version("arelle-release")
    if arelle_version != SUPPORTED_ARELLE_VERSION:
        raise WorkerError(
            "UNSUPPORTED_ARELLE_VERSION",
            "Arelle 版本不在已验证范围内。",
        )
    source_path = Path(request["source_path"]).resolve()
    taxonomy_path = Path(request["taxonomy_path"]).resolve()
    observed_sha256 = sha256_file(source_path)
    if observed_sha256 != request["expected_source_sha256"]:
        raise WorkerError(
            "INPUT_HASH_MISMATCH",
            "工作进程读取的源文件哈希与封存值不一致。",
        )
    if sha256_file(taxonomy_path) != request["expected_taxonomy_sha256"]:
        raise WorkerError(
            "TAXONOMY_HASH_MISMATCH",
            "工作进程读取的分类标准包哈希与封存值不一致。",
        )
    with tempfile.TemporaryDirectory(prefix="sdoo-cn-xbrl-worker-") as temporary:
        work_root = Path(temporary)
        os.chmod(work_root, 0o700)
        entry_point, patch_count, working_checksum = _prepare_taxonomy(
            taxonomy_path,
            request["entry_point_path"],
            work_root,
            request["taxonomy_compatibility_profile"],
            int(request["expected_compatibility_patch_count"]),
        )
        source_root, instances = _prepare_source(
            source_path,
            request["source_name"],
            work_root,
        )
        documents = []
        messages = []
        warning_count = 0
        error_count = 0
        error_codes = []
        for index, instance in enumerate(instances, start=1):
            prepared = _rewrite_schema_reference(
                instance,
                entry_point,
                work_root,
                index,
            )
            source_key = instance.relative_to(source_root).as_posix()
            parsed = _parse_instance(
                prepared,
                source_key,
                request["taxonomy_namespace"],
            )
            documents.append(parsed["document"])
            messages.extend(parsed["messages"])
            warning_count += parsed["warning_count"]
            error_count += parsed["error_count"]
            error_codes.extend(parsed["error_codes"])
    return {
        "schema_version": 1,
        "status": "completed",
        "observed_input_sha256": observed_sha256,
        "arelle_version": arelle_version,
        "source_fact_count": sum(
            document.get("source_fact_count", 0) for document in documents
        ),
        "warning_count": warning_count,
        "error_count": error_count,
        "error_codes": list(dict.fromkeys(error_codes))[:10],
        "parser_log_checksum": _log_digest(messages),
        "taxonomy_compatibility_profile": request[
            "taxonomy_compatibility_profile"
        ],
        "taxonomy_patch_count": patch_count,
        "working_taxonomy_checksum": working_checksum,
        "documents": documents if not error_count else [],
    }


def _write_result(path, result):
    payload = json.dumps(
        result,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(payload) > MAX_RESULT_BYTES:
        payload = json.dumps(
            {
                "schema_version": 1,
                "status": "failed",
                "error_code": "RESULT_TOO_LARGE",
                "error_summary": "规范化结果超过安全大小限制。",
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--request", required=True)
    parser.add_argument("--result", required=True)
    arguments = parser.parse_args()
    observed_sha256 = None
    try:
        request = json.loads(Path(arguments.request).read_text(encoding="utf-8"))
        result = execute(request)
    except ContractError as exc:
        result = {
            "schema_version": 1,
            "status": "failed",
            "error_code": exc.code,
            "error_summary": exc.message,
            "observed_input_sha256": observed_sha256,
        }
    except WorkerError as exc:
        result = {
            "schema_version": 1,
            "status": "failed",
            "error_code": exc.code,
            "error_summary": exc.message,
            "observed_input_sha256": observed_sha256,
        }
    except Exception as exc:
        result = {
            "schema_version": 1,
            "status": "failed",
            "error_code": "UNEXPECTED_WORKER_FAILURE",
            "error_summary": "解析工作进程发生未预期错误：%s" % type(exc).__name__,
            "observed_input_sha256": observed_sha256,
        }
    _write_result(arguments.result, result)
    return 0 if result.get("status") == "completed" else 2


if __name__ == "__main__":
    sys.exit(main())
