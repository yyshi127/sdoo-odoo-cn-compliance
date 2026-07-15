from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PARSER_ROOT = (
    REPOSITORY_ROOT
    / "addons"
    / "sudo_country_pack_cn_einvoice_xbrl"
    / "parser"
)
WORKER_PATH = PARSER_ROOT / "worker.py"
sys.path.insert(0, str(PARSER_ROOT))
SPEC = importlib.util.spec_from_file_location(
    "cn_xbrl_worker_compatibility",
    WORKER_PATH,
)
WORKER = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(WORKER)

ROLE_TYPE_TAG = "{http://www.xbrl.org/2003/linkbase}roleType"


class TestXbrlWorkerCompatibility(unittest.TestCase):
    def _schema(self, role_uri="http://example.test/role/100801 "):
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<xsd:schema xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
            'xmlns:link="http://www.xbrl.org/2003/linkbase" '
            'targetNamespace="urn:test:entry">'
            '<xsd:annotation><xsd:appinfo>'
            f'<link:roleType id="testRole" roleURI="{role_uri}"/>'
            '</xsd:appinfo></xsd:annotation>'
            '</xsd:schema>'
        ).encode()

    def test_controlled_profile_trims_only_working_copy_role_uri(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            schema_path = root / "entry.xsd"
            original = self._schema()
            schema_path.write_bytes(original)
            (root / "readme.txt").write_text("fixture", encoding="utf-8")

            count, checksum = WORKER._apply_taxonomy_compatibility(
                root,
                "trim_role_uri_whitespace_v1",
            )

            parsed = ElementTree.parse(schema_path)
            role_type = next(parsed.getroot().iter(ROLE_TYPE_TAG))
            self.assertEqual(count, 1)
            self.assertEqual(
                role_type.attrib["roleURI"],
                "http://example.test/role/100801",
            )
            self.assertNotEqual(schema_path.read_bytes(), original)
            self.assertEqual(checksum, WORKER._taxonomy_tree_checksum(root))
            self.assertEqual(len(checksum), 64)

    def test_strict_profile_rejects_detected_issue_without_writing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            schema_path = root / "entry.xsd"
            original = self._schema()
            schema_path.write_bytes(original)

            with self.assertRaisesRegex(
                WORKER.WorkerError,
                "严格模式拒绝处理",
            ):
                WORKER._apply_taxonomy_compatibility(root, "strict")

            self.assertEqual(schema_path.read_bytes(), original)

    def test_profile_must_match_detected_issue_and_sealed_count(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            taxonomy_path = root / "taxonomy.zip"
            with zipfile.ZipFile(taxonomy_path, "w") as archive:
                archive.writestr("entry.xsd", self._schema())

            with self.assertRaisesRegex(
                WORKER.WorkerError,
                "修正数与封存记录不一致",
            ):
                WORKER._prepare_taxonomy(
                    taxonomy_path,
                    "entry.xsd",
                    root / "work",
                    "trim_role_uri_whitespace_v1",
                    2,
                )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "entry.xsd").write_bytes(
                self._schema("http://example.test/role/100801")
            )
            with self.assertRaisesRegex(
                WORKER.WorkerError,
                "不存在所选技术兼容方案",
            ):
                WORKER._apply_taxonomy_compatibility(
                    root,
                    "trim_role_uri_whitespace_v1",
                )


if __name__ == "__main__":
    unittest.main()
