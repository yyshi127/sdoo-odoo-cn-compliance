from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import ChinaXbrlCommon, NAMESPACE


@tagged("post_install", "-at_install")
class TestChinaXbrlTaxonomyBundle(ChinaXbrlCommon):
    def test_seal_validates_and_freezes_official_taxonomy_bundle(self):
        bundle = self._taxonomy("valid")

        self.assertEqual(bundle.state, "sealed")
        self.assertEqual(bundle.integrity_state, "verified")
        self.assertEqual(len(bundle.bundle_sha256), 64)
        self.assertEqual(bundle.bundle_file_count, 2)
        self.assertEqual(
            bundle.compatibility_profile,
            "trim_role_uri_whitespace_v1",
        )
        self.assertEqual(bundle.compatibility_patch_count, 1)
        self.assertEqual(
            bundle.entry_point_path,
            "official/einv-20231231/einv_entry_point_2023-12-31.xsd",
        )
        self.assertEqual(bundle.sealed_by_id, self.reviewer)
        with self.assertRaises(AccessError):
            bundle.write({"version": "changed"})
        with self.assertRaises(UserError):
            bundle.unlink()

    def test_detected_role_uri_whitespace_requires_controlled_profile(self):
        bundle = self._taxonomy("compatibility", seal=False)
        bundle.write(
            {
                "compatibility_profile": "strict",
                "compatibility_reason": False,
            }
        )

        with self.assertRaisesRegex(UserError, "角色 URI 尾空格"):
            bundle.with_user(self.reviewer).action_seal()

        bundle.write(
            {
                "compatibility_profile": "trim_role_uri_whitespace_v1",
                "compatibility_reason": (
                    "已复核测试标准包问题，仅允许修剪角色 URI 两端空白且保留原始包。"
                ),
            }
        )
        bundle.with_user(self.reviewer).action_seal()

        self.assertEqual(bundle.state, "sealed")
        self.assertEqual(bundle.compatibility_patch_count, 1)

    def test_wrong_namespace_and_unsafe_archive_are_rejected(self):
        wrong_attachment = self._attachment(
            "wrong-namespace.zip",
            self._taxonomy_bytes("urn:not-official"),
        )
        wrong = self.env["sudo.cn.xbrl.taxonomy.bundle"].create(
            {
                "official_title": "错误命名空间测试",
                "namespace": NAMESPACE,
                "version": "2023-12-31",
                "publication_date": "2025-05-19",
                "source_url": "https://kjs.mof.gov.cn/test/einvoice.html",
                "source_reference": "WRONG-NAMESPACE",
                "entry_point_hint": "einv_entry_point_2023-12-31.xsd",
                "bundle_attachment_ids": [Command.set(wrong_attachment.ids)],
                "separation_exception_reason": (
                    "隔离测试环境由同一管理员登记和封存，仅验证安全门禁。"
                ),
            }
        )
        with self.assertRaises(UserError):
            wrong.action_seal()

        traversal_attachment = self._attachment(
            "unsafe.zip",
            self._zip_bytes({"../entry.xsd": b"<schema/>"}),
        )
        wrong.bundle_attachment_ids = [Command.set(traversal_attachment.ids)]
        wrong.entry_point_hint = "entry.xsd"
        with self.assertRaises(UserError):
            wrong.action_seal()

    def test_tampering_after_seal_invalidates_bundle(self):
        bundle = self._taxonomy("tamper")

        bundle.bundle_attachment_ids.raw = b"tampered"
        bundle.invalidate_recordset(["integrity_state"])

        self.assertEqual(bundle.integrity_state, "checksum_mismatch")

    def test_replacement_supersedes_only_after_new_bundle_is_sealed(self):
        original = self._taxonomy("replacement")
        action = original.action_create_replacement()
        replacement = self.env["sudo.cn.xbrl.taxonomy.bundle"].browse(
            action["res_id"]
        )

        self.assertEqual(original.state, "sealed")
        self.assertEqual(replacement.state, "draft")
        attachment = self._attachment(
            "replacement.zip",
            self._taxonomy_bytes(),
        )
        replacement.bundle_attachment_ids = [Command.set(attachment.ids)]
        replacement.with_user(self.reviewer).action_seal()

        self.assertEqual(original.state, "superseded")
        self.assertEqual(replacement.state, "sealed")
        self.assertEqual(replacement.supersedes_id, original)
