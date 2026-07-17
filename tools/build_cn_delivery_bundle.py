"""Build an auditable China country-pack delivery bundle.

The bundle uses the same file inventory as the delivery manifest and writes a
deterministic tar.gz archive with normalized ownership, permissions and mtimes.
"""

from __future__ import annotations

import argparse
import importlib.util
import gzip
import hashlib
import io
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUNDLE_SCHEMA = "sdoo.cn.delivery-bundle.v1"
ACCEPTANCE_PATH = ROOT / "tools" / "run_cn_delivery_acceptance.py"
SPEC = importlib.util.spec_from_file_location("cn_delivery_acceptance", ACCEPTANCE_PATH)
acceptance = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(acceptance)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tar_info(path: Path, arcname: str) -> tarfile.TarInfo:
    info = tarfile.TarInfo(arcname)
    info.size = path.stat().st_size
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    info.mode = 0o644
    return info


def _write_bundle(path: Path) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    path.parent.mkdir(parents=True, exist_ok=True)
    files = acceptance._manifest_paths()
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for file_path in files:
                    relative = file_path.relative_to(ROOT).as_posix()
                    data = file_path.read_bytes()
                    archive.addfile(_tar_info(file_path, relative), io.BytesIO(data))
                    entries.append(
                        {
                            "path": relative,
                            "size": len(data),
                            "sha256": hashlib.sha256(data).hexdigest(),
                        }
                    )
    return entries


def _write_metadata(path: Path, bundle_path: Path, entries: list[dict[str, object]]) -> None:
    payload = {
        "schema": BUNDLE_SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "addon": "sudo_country_pack_cn",
        "version": acceptance._addon_version(),
        "git_commit": acceptance._git_commit(),
        "source_control": acceptance._source_control_summary(),
        "bundle_path": str(bundle_path),
        "bundle_size": bundle_path.stat().st_size,
        "bundle_sha256": _sha256(bundle_path),
        "file_count": len(entries),
        "aggregate_sha256": acceptance._aggregate_sha256(entries),
        "files": entries,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "delivery bundle metadata written: "
        f"{path} ({payload['file_count']} files, {payload['bundle_sha256']})"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a China delivery bundle.")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "dist" / "sdoo-cn-compliance-delivery.tgz",
        help="Output tar.gz bundle path.",
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=ROOT / "dist" / "sdoo-cn-compliance-delivery.bundle.json",
        help="Output bundle metadata JSON path.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    entries = _write_bundle(args.output)
    _write_metadata(args.metadata, args.output, entries)
    print(f"delivery bundle written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
