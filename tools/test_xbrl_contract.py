from __future__ import annotations

import importlib.util
import io
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    REPOSITORY_ROOT
    / "addons"
    / "sudo_country_pack_cn_einvoice_xbrl"
    / "parser"
    / "contract.py"
)
SPEC = importlib.util.spec_from_file_location("cn_xbrl_contract", CONTRACT_PATH)
CONTRACT = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(CONTRACT)

NAMESPACE = "http://xbrl.mof.gov.cn/taxonomy/2023-12-31/einv"


def zip_bytes(files, compression=zipfile.ZIP_DEFLATED):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=compression) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return stream.getvalue()


class TestXbrlContract(unittest.TestCase):
    def _schema(self, namespace=NAMESPACE):
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<xsd:schema xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
            f'targetNamespace="{namespace}"/>'
        ).encode()

    def _instance(self):
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<xbrli:xbrl '
            'xmlns:xbrli="http://www.xbrl.org/2003/instance"/>'
        ).encode()

    def _schema_with_role_whitespace(self):
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<xsd:schema xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
            'xmlns:link="http://www.xbrl.org/2003/linkbase" '
            f'targetNamespace="{NAMESPACE}">'
            '<xsd:annotation><xsd:appinfo>'
            '<link:roleType id="testRole" '
            'roleURI="http://example.test/role/100801 "/>'
            '</xsd:appinfo></xsd:annotation>'
            '</xsd:schema>'
        ).encode()

    def test_taxonomy_inspection_resolves_unique_entry_point(self):
        data = zip_bytes(
            {
                "official/einv-20231231/einv_entry_point_2023-12-31.xsd": (
                    self._schema()
                ),
                "official/einv-20231231/einv/linkbase/labels.xml": b"<labels/>",
            }
        )

        result = CONTRACT.inspect_taxonomy_bundle(
            data,
            "einv_entry_point_2023-12-31.xsd",
            NAMESPACE,
        )

        self.assertEqual(
            result["entry_point_path"],
            "official/einv-20231231/einv_entry_point_2023-12-31.xsd",
        )
        self.assertEqual(result["file_count"], 2)
        self.assertEqual(len(result["sha256"]), 64)

    def test_taxonomy_inspection_counts_role_uri_whitespace(self):
        data = zip_bytes({"entry.xsd": self._schema_with_role_whitespace()})

        result = CONTRACT.inspect_taxonomy_bundle(
            data,
            "entry.xsd",
            NAMESPACE,
        )

        self.assertEqual(result["role_uri_whitespace_count"], 1)

    def test_taxonomy_namespace_must_match(self):
        data = zip_bytes({"entry.xsd": self._schema("urn:not-official")})

        with self.assertRaisesRegex(
            CONTRACT.ContractError,
            "命名空间",
        ):
            CONTRACT.inspect_taxonomy_bundle(data, "entry.xsd", NAMESPACE)

    def test_path_traversal_and_case_collisions_are_rejected(self):
        traversal = zip_bytes({"../escape.xsd": self._schema()})
        collision = zip_bytes(
            {
                "TAXONOMY/entry.xsd": self._schema(),
                "taxonomy/ENTRY.xsd": self._schema(),
            }
        )

        with self.assertRaises(CONTRACT.ContractError):
            CONTRACT.inspect_taxonomy_bundle(
                traversal,
                "entry.xsd",
                NAMESPACE,
            )
        with self.assertRaises(CONTRACT.ContractError):
            CONTRACT.inspect_taxonomy_bundle(
                collision,
                "entry.xsd",
                NAMESPACE,
            )

    def test_symbolic_links_are_rejected(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            info = zipfile.ZipInfo("entry.xsd")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, "target.xsd")

        with self.assertRaises(CONTRACT.ContractError):
            CONTRACT.inspect_taxonomy_bundle(
                stream.getvalue(),
                "entry.xsd",
                NAMESPACE,
            )

    def test_extreme_compression_ratio_is_rejected(self):
        data = zip_bytes(
            {
                "entry.xsd": self._schema(),
                "payload.bin": b"0" * (2 * 1024 * 1024),
            }
        )

        with self.assertRaisesRegex(
            CONTRACT.ContractError,
            "压缩比",
        ):
            CONTRACT.inspect_taxonomy_bundle(data, "entry.xsd", NAMESPACE)

    def test_safe_extraction_and_instance_discovery(self):
        data = zip_bytes(
            {
                "batch/invoice-1.xml": self._instance(),
                "batch/readme.txt": b"controlled test fixture",
            }
        )
        with tempfile.TemporaryDirectory() as temporary:
            archive_path = Path(temporary) / "source.zip"
            output_path = Path(temporary) / "output"
            archive_path.write_bytes(data)

            extracted = CONTRACT.safe_extract_zip(
                archive_path,
                output_path,
                CONTRACT.SOURCE_LIMITS,
            )
            instances = CONTRACT.discover_xbrl_instances(output_path)

        self.assertEqual(len(extracted), 2)
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0].name, "invoice-1.xml")

    def test_dtd_is_rejected_before_instance_processing(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "invoice.xml"
            path.write_text(
                '<!DOCTYPE x [<!ENTITY leak SYSTEM "file:///etc/passwd">]>'
                '<xbrli:xbrl '
                'xmlns:xbrli="http://www.xbrl.org/2003/instance"/>',
                encoding="utf-8",
            )

            with self.assertRaises(CONTRACT.ContractError):
                CONTRACT.xml_root_tag(path)

    def test_dtd_in_taxonomy_linkbase_is_rejected(self):
        data = zip_bytes(
            {
                "entry.xsd": self._schema(),
                "labels.xml": (
                    b'<!DOCTYPE labels [<!ENTITY leak SYSTEM "file:///etc/passwd">]>'
                    b"<labels>&leak;</labels>"
                ),
            }
        )

        with self.assertRaisesRegex(
            CONTRACT.ContractError,
            "DTD",
        ):
            CONTRACT.inspect_taxonomy_bundle(
                data,
                "entry.xsd",
                NAMESPACE,
            )


if __name__ == "__main__":
    unittest.main()
