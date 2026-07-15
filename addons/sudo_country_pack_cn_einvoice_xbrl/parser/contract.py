from __future__ import annotations

import hashlib
import io
import stat
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree


XBRL_INSTANCE_TAG = "{http://www.xbrl.org/2003/instance}xbrl"

TAXONOMY_LIMITS = {
    "max_archive_bytes": 100 * 1024 * 1024,
    "max_entries": 5000,
    "max_member_bytes": 50 * 1024 * 1024,
    "max_total_bytes": 500 * 1024 * 1024,
    "max_compression_ratio": 200,
}

SOURCE_LIMITS = {
    "max_archive_bytes": 250 * 1024 * 1024,
    "max_entries": 20000,
    "max_member_bytes": 100 * 1024 * 1024,
    "max_total_bytes": 2 * 1024 * 1024 * 1024,
    "max_compression_ratio": 200,
}


class ContractError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path, chunk_size=1024 * 1024):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_member_name(name):
    raw = unicodedata.normalize("NFC", str(name or "")).replace("\\", "/")
    if not raw or "\x00" in raw or raw.startswith("/"):
        raise ContractError("UNSAFE_ARCHIVE_PATH", "压缩包包含不安全路径。")
    if len(raw) >= 2 and raw[1] == ":":
        raise ContractError("UNSAFE_ARCHIVE_PATH", "压缩包包含盘符路径。")
    trimmed = raw[:-1] if raw.endswith("/") else raw
    parts = trimmed.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ContractError("UNSAFE_ARCHIVE_PATH", "压缩包包含路径穿越。")
    return PurePosixPath(*parts).as_posix()


def validated_members(archive, limits):
    infos = archive.infolist()
    if len(infos) > limits["max_entries"]:
        raise ContractError("ARCHIVE_TOO_MANY_FILES", "压缩包文件数量超限。")
    total_size = 0
    seen = set()
    result = []
    for info in infos:
        normalized = normalized_member_name(info.filename)
        collision_key = normalized.casefold()
        if collision_key in seen:
            raise ContractError("DUPLICATE_ARCHIVE_PATH", "压缩包存在重复路径。")
        seen.add(collision_key)
        unix_mode = (info.external_attr >> 16) & 0xFFFF
        if unix_mode and stat.S_ISLNK(unix_mode):
            raise ContractError("ARCHIVE_SYMLINK", "压缩包不能包含符号链接。")
        if info.flag_bits & 0x1:
            raise ContractError("ENCRYPTED_ARCHIVE", "不支持加密压缩包。")
        if info.is_dir():
            result.append((info, normalized))
            continue
        if info.file_size > limits["max_member_bytes"]:
            raise ContractError("ARCHIVE_MEMBER_TOO_LARGE", "压缩包单文件超限。")
        total_size += info.file_size
        if total_size > limits["max_total_bytes"]:
            raise ContractError("ARCHIVE_EXPANSION_TOO_LARGE", "压缩包展开体积超限。")
        if info.file_size:
            if not info.compress_size:
                raise ContractError("INVALID_COMPRESSION_RATIO", "压缩比无法验证。")
            ratio = info.file_size / info.compress_size
            if ratio > limits["max_compression_ratio"]:
                raise ContractError("INVALID_COMPRESSION_RATIO", "压缩比超过安全限制。")
        result.append((info, normalized))
    return result, total_size


def _open_zip_from_bytes(data, limits):
    if len(data) > limits["max_archive_bytes"]:
        raise ContractError("ARCHIVE_TOO_LARGE", "压缩包原始文件超限。")
    try:
        return zipfile.ZipFile(io.BytesIO(data))
    except (OSError, zipfile.BadZipFile) as exc:
        raise ContractError("INVALID_ZIP", "文件不是有效 ZIP 压缩包。") from exc


def _resolve_entry_point(member_names, hint):
    normalized_hint = normalized_member_name(hint)
    exact = [name for name in member_names if name == normalized_hint]
    if exact:
        return exact[0]
    if "/" in normalized_hint:
        raise ContractError("ENTRY_POINT_NOT_FOUND", "分类标准入口文件不存在。")
    matches = [
        name
        for name in member_names
        if PurePosixPath(name).name == normalized_hint
    ]
    if len(matches) != 1:
        raise ContractError(
            "ENTRY_POINT_NOT_UNIQUE",
            "无法唯一确定分类标准入口文件。",
        )
    return matches[0]


def inspect_taxonomy_bundle(
    data,
    entry_point_hint,
    expected_namespace,
    expected_entry_namespace=None,
):
    archive = _open_zip_from_bytes(data, TAXONOMY_LIMITS)
    with archive:
        members, total_size = validated_members(archive, TAXONOMY_LIMITS)
        files = [name for info, name in members if not info.is_dir()]
        entry_point = _resolve_entry_point(files, entry_point_hint)
        info = next(info for info, name in members if name == entry_point)
        if info.file_size > 5 * 1024 * 1024:
            raise ContractError("ENTRY_POINT_TOO_LARGE", "分类标准入口文件超限。")
        content = archive.read(info)
        role_uri_whitespace_count = 0
        role_type_tag = "{http://www.xbrl.org/2003/linkbase}roleType"
        xml_suffixes = {".xml", ".xbrl", ".xsd"}
        for member_info, member_name in members:
            suffix = PurePosixPath(member_name).suffix.lower()
            if member_info.is_dir() or suffix not in xml_suffixes:
                continue
            if member_info.file_size > 5 * 1024 * 1024:
                raise ContractError(
                    "TAXONOMY_XML_TOO_LARGE",
                    "分类标准 XML 文件超限。",
                )
            xml_content = archive.read(member_info)
            if b"<!DOCTYPE" in xml_content.upper():
                raise ContractError("XML_DTD_FORBIDDEN", "分类标准不能包含 DTD。")
            try:
                xml_root = ElementTree.fromstring(xml_content)
            except ElementTree.ParseError as exc:
                raise ContractError(
                    "INVALID_TAXONOMY_XML",
                    "分类标准包含无效 XML。",
                ) from exc
            if suffix != ".xsd":
                continue
            for role_type in xml_root.iter(role_type_tag):
                role_uri = role_type.attrib.get("roleURI") or ""
                if role_uri != role_uri.strip():
                    role_uri_whitespace_count += 1
    if b"<!DOCTYPE" in content.upper():
        raise ContractError("XML_DTD_FORBIDDEN", "分类标准入口不能包含 DTD。")
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as exc:
        raise ContractError("INVALID_ENTRY_POINT_XML", "分类标准入口 XML 无效。") from exc
    if root.tag.rsplit("}", 1)[-1] != "schema":
        raise ContractError("INVALID_ENTRY_POINT_SCHEMA", "入口文件不是 XML Schema。")
    target_namespace = root.attrib.get("targetNamespace")
    if expected_entry_namespace and target_namespace != expected_entry_namespace:
        raise ContractError(
            "ENTRY_POINT_NAMESPACE_MISMATCH",
            "入口文件命名空间与登记值不一致。",
        )
    schema_namespace = "http://www.w3.org/2001/XMLSchema"
    imported_namespaces = {
        element.attrib.get("namespace")
        for element in root.findall("{%s}import" % schema_namespace)
    }
    if (
        target_namespace != expected_namespace
        and expected_namespace not in imported_namespaces
    ):
        raise ContractError(
            "TAXONOMY_NAMESPACE_MISMATCH",
            "入口文件未导入登记的电子发票事实命名空间。",
        )
    return {
        "entry_point_path": entry_point,
        "file_count": len(files),
        "expanded_size": total_size,
        "sha256": sha256_bytes(data),
        "role_uri_whitespace_count": role_uri_whitespace_count,
    }


def safe_extract_zip(archive_path, destination, limits):
    archive_path = Path(archive_path)
    if archive_path.stat().st_size > limits["max_archive_bytes"]:
        raise ContractError("ARCHIVE_TOO_LARGE", "压缩包原始文件超限。")
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    try:
        archive = zipfile.ZipFile(archive_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ContractError("INVALID_ZIP", "文件不是有效 ZIP 压缩包。") from exc
    extracted = []
    with archive:
        members, _total_size = validated_members(archive, limits)
        for info, normalized in members:
            target = (destination / Path(*PurePosixPath(normalized).parts)).resolve()
            if destination not in target.parents and target != destination:
                raise ContractError("UNSAFE_ARCHIVE_PATH", "压缩包路径越界。")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            written = 0
            with archive.open(info) as source, target.open("wb") as output:
                while chunk := source.read(1024 * 1024):
                    written += len(chunk)
                    if written > limits["max_member_bytes"]:
                        raise ContractError(
                            "ARCHIVE_MEMBER_TOO_LARGE",
                            "压缩包单文件超限。",
                        )
                    output.write(chunk)
            if written != info.file_size:
                raise ContractError("ARCHIVE_SIZE_MISMATCH", "压缩包文件大小异常。")
            extracted.append(target)
    return extracted


def xml_root_tag(path):
    path = Path(path)
    with path.open("rb") as stream:
        header = stream.read(4096)
        if b"<!DOCTYPE" in header.upper():
            raise ContractError("XML_DTD_FORBIDDEN", "XBRL 实例不能包含 DTD。")
        stream.seek(0)
        try:
            for _event, element in ElementTree.iterparse(
                stream,
                events=("start",),
            ):
                return element.tag
        except ElementTree.ParseError as exc:
            raise ContractError("INVALID_XML", "源文件包含无效 XML。") from exc
    raise ContractError("EMPTY_XML", "源 XML 文件为空。")


def discover_xbrl_instances(root, max_instances=10000):
    root = Path(root)
    candidates = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".xml", ".xbrl"}
    )
    instances = [path for path in candidates if xml_root_tag(path) == XBRL_INSTANCE_TAG]
    if not instances:
        raise ContractError("NO_XBRL_INSTANCE", "源数据中没有 XBRL 实例文档。")
    if len(instances) > max_instances:
        raise ContractError("TOO_MANY_XBRL_INSTANCES", "XBRL 实例数量超限。")
    return instances
