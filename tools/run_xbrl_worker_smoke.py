from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKER_PATH = (
    REPOSITORY_ROOT
    / "addons"
    / "sudo_country_pack_cn_einvoice_xbrl"
    / "parser"
    / "worker.py"
)


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--taxonomy", required=True, type=Path)
    parser.add_argument("--entry-point", required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument(
        "--compatibility-profile",
        required=True,
        choices=("strict", "trim_role_uri_whitespace_v1"),
    )
    parser.add_argument("--expected-patch-count", required=True, type=int)
    parser.add_argument("--arelle-path", type=Path)
    arguments = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="sdoo-cn-xbrl-smoke-") as name:
        temporary = Path(name)
        request_path = temporary / "request.json"
        result_path = temporary / "result.json"
        request = {
            "schema_version": 1,
            "source_path": str(arguments.source.resolve()),
            "source_name": arguments.source.name,
            "expected_source_sha256": sha256_file(arguments.source),
            "taxonomy_path": str(arguments.taxonomy.resolve()),
            "expected_taxonomy_sha256": sha256_file(arguments.taxonomy),
            "entry_point_path": arguments.entry_point,
            "taxonomy_namespace": arguments.namespace,
            "taxonomy_compatibility_profile": (
                arguments.compatibility_profile
            ),
            "expected_compatibility_patch_count": (
                arguments.expected_patch_count
            ),
            "memory_limit_bytes": 2 * 1024 * 1024 * 1024,
            "cpu_limit_seconds": 300,
        }
        request_path.write_text(
            json.dumps(request, ensure_ascii=False),
            encoding="utf-8",
        )
        environment = os.environ.copy()
        if arguments.arelle_path:
            existing = environment.get("PYTHONPATH")
            paths = [str(arguments.arelle_path.resolve())]
            if existing:
                paths.append(existing)
            environment["PYTHONPATH"] = os.pathsep.join(paths)
        completed = subprocess.run(
            [
                sys.executable,
                str(WORKER_PATH),
                "--request",
                str(request_path),
                "--result",
                str(result_path),
            ],
            env=environment,
            capture_output=True,
            timeout=320,
            check=False,
        )
        if not result_path.exists():
            print("worker returned no result")
            return 1
        result = json.loads(result_path.read_text(encoding="utf-8"))
        documents = result.get("documents") or []
        accounting_documents = [
            accounting_document
            for document in documents
            for accounting_document in (
                document.get("accounting_documents") or []
            )
        ]
        entries = [
            entry
            for accounting_document in accounting_documents
            for entry in (accounting_document.get("entries") or [])
        ]
        summary = {
            "exit_code": completed.returncode,
            "status": result.get("status"),
            "error_code": result.get("error_code"),
            "error_summary": result.get("error_summary"),
            "arelle_version": result.get("arelle_version"),
            "source_fact_count": result.get("source_fact_count"),
            "warning_count": result.get("warning_count"),
            "error_count": result.get("error_count"),
            "error_codes": result.get("error_codes"),
            "document_count": len(documents),
            "accounting_document_count": len(accounting_documents),
            "accounting_entry_count": len(entries),
            "accounting_entries_have_core_fields": bool(entries)
            and all(
                entry.get(field_name)
                for entry in entries
                for field_name in (
                    "direction",
                    "general_ledger_subject",
                    "amount",
                )
            ),
            "document_key_fields_present": bool(documents)
            and all(
                documents[0].get(field_name)
                for field_name in (
                    "invoice_number",
                    "seller_tax_id",
                    "total_amount",
                    "source_fact_digest",
                )
            ),
            "parser_log_checksum": result.get("parser_log_checksum"),
            "taxonomy_compatibility_profile": result.get(
                "taxonomy_compatibility_profile"
            ),
            "taxonomy_patch_count": result.get("taxonomy_patch_count"),
            "working_taxonomy_checksum": result.get(
                "working_taxonomy_checksum"
            ),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if result.get("status") == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
