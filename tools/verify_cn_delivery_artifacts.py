"""Verify China delivery bundle, manifest and acceptance summary consistency."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BUNDLE_SCHEMA = "sdoo.cn.delivery-bundle.v1"
MANIFEST_SCHEMA = "sdoo.cn.delivery-manifest.v1"
SUMMARY_SCHEMA = "sdoo.cn.delivery-acceptance-summary.v1"


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fail(message: str) -> None:
    raise SystemExit(f"delivery artifact verification failed: {message}")


def _entry_map(payload: dict[str, object], label: str) -> dict[str, dict[str, object]]:
    files = payload.get("files")
    if not isinstance(files, list):
        _fail(f"{label} does not contain a file list")
    result: dict[str, dict[str, object]] = {}
    for entry in files:
        if not isinstance(entry, dict):
            _fail(f"{label} contains a malformed file entry")
        path = entry.get("path")
        if not isinstance(path, str):
            _fail(f"{label} contains a file entry without path")
        result[path] = entry
    return result


def _assert_equal(left: object, right: object, label: str) -> None:
    if left != right:
        _fail(f"{label}: {left!r} != {right!r}")


def _verify_source_control(payload: dict[str, object], label: str) -> None:
    source_control = payload.get("source_control")
    if not isinstance(source_control, dict):
        _fail(f"{label} does not contain source control evidence")
    _assert_equal(
        payload.get("git_commit"),
        source_control.get("commit"),
        f"{label} git commit/source control commit",
    )


def _verify_bundle_file(bundle: Path | None, bundle_metadata: dict[str, object]) -> None:
    if bundle is None:
        metadata_path = bundle_metadata.get("bundle_path")
        bundle = Path(metadata_path) if isinstance(metadata_path, str) else None
    if bundle is None or not bundle.is_file():
        return
    _assert_equal(
        _sha256(bundle),
        bundle_metadata.get("bundle_sha256"),
        "bundle SHA-256",
    )
    _assert_equal(bundle.stat().st_size, bundle_metadata.get("bundle_size"), "bundle size")


def verify(
    *,
    bundle_metadata_path: Path,
    manifest_path: Path,
    summary_path: Path,
    bundle_path: Path | None,
) -> None:
    bundle_metadata = _load(bundle_metadata_path)
    manifest = _load(manifest_path)
    summary = _load(summary_path)

    _assert_equal(bundle_metadata.get("schema"), BUNDLE_SCHEMA, "bundle metadata schema")
    _assert_equal(manifest.get("schema"), MANIFEST_SCHEMA, "manifest schema")
    _assert_equal(summary.get("schema"), SUMMARY_SCHEMA, "summary schema")

    for field in ("addon", "version", "file_count", "aggregate_sha256"):
        _assert_equal(bundle_metadata.get(field), manifest.get(field), field)
    _assert_equal(bundle_metadata.get("git_commit"), manifest.get("git_commit"), "git commit")
    _assert_equal(summary.get("addon"), manifest.get("addon"), "summary addon")
    _assert_equal(summary.get("version"), manifest.get("version"), "summary version")
    _assert_equal(summary.get("git_commit"), manifest.get("git_commit"), "summary git commit")
    _assert_equal(
        bundle_metadata.get("source_control"),
        manifest.get("source_control"),
        "bundle/manifest source control",
    )
    _assert_equal(
        summary.get("source_control"),
        manifest.get("source_control"),
        "summary/manifest source control",
    )
    _verify_source_control(bundle_metadata, "bundle metadata")
    _verify_source_control(manifest, "manifest")
    _verify_source_control(summary, "summary")
    _assert_equal(summary.get("result"), "passed", "summary result")

    summary_manifest = summary.get("manifest")
    if not isinstance(summary_manifest, dict):
        _fail("summary does not contain manifest evidence")
    for field in ("schema", "version", "file_count", "aggregate_sha256"):
        _assert_equal(summary_manifest.get(field), manifest.get(field), f"summary manifest {field}")

    bundle_files = _entry_map(bundle_metadata, "bundle metadata")
    manifest_files = _entry_map(manifest, "manifest")
    _assert_equal(set(bundle_files), set(manifest_files), "file path set")
    for path, bundle_entry in bundle_files.items():
        manifest_entry = manifest_files[path]
        for field in ("size", "sha256"):
            _assert_equal(bundle_entry.get(field), manifest_entry.get(field), f"{path} {field}")

    runtime = summary.get("runtime")
    if isinstance(runtime, dict):
        log = runtime.get("log")
        if isinstance(log, dict):
            _assert_equal(log.get("failed"), 0, "runtime failed count")
            _assert_equal(log.get("errors"), 0, "runtime error count")

    _verify_bundle_file(bundle_path, bundle_metadata)

    print(
        "delivery artifacts verified: "
        f"{manifest.get('version')} / {manifest.get('file_count')} files / "
        f"{manifest.get('aggregate_sha256')}"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify China delivery bundle metadata, manifest and acceptance summary."
    )
    parser.add_argument("--bundle-metadata", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--bundle", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    verify(
        bundle_metadata_path=args.bundle_metadata,
        manifest_path=args.manifest,
        summary_path=args.summary,
        bundle_path=args.bundle,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
