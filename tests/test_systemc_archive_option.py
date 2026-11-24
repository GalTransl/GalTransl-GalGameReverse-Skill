"""SystemC: read the original from a backup package and point a failing run at the right route.

Regression background: the Japanese original was kept beside a patched
package as ``data.fpk.bak`` and could only be extracted after copying and
renaming it; a UTF-8 text-table release failed with a bare CP932 error that
did not name the other extractor. Synthetic fixtures only.
"""
from pathlib import Path
import tempfile
import unittest

from python.common.binary import FormatError
from python.engines.systemc_extract import extract, pack
from tests.test_systemc import archive, fixture
from tests.test_systemc_txd import fixture as txd_fixture


class ArchiveOptionTests(unittest.TestCase):
    def test_backup_package_is_read_and_stored_as_data_fpk(self):
        members = fixture()
        broken = dict(members, **{"ACT_A.txt": "本文\r\n".encode("utf-8")})
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = archive(members)
            (root / "data.fpk").write_bytes(archive(broken))
            (root / "data.fpk.bak").write_bytes(original)
            with self.assertRaises(FormatError) as caught:
                extract(root, root / "patched")
            self.assertIn("data.fpk.bak", str(caught.exception))
            self.assertIn("--archive", str(caught.exception))
            report = extract(root, root / "work", archive=root / "data.fpk.bak", verify_edits=True)
            self.assertEqual(report["source_file"], "data.fpk.bak")
            self.assertEqual((root / "work/original/data.fpk").read_bytes(), original)
            self.assertGreater(report["json_rows"], 0)
            pack(root / "work", root / "packed")
            self.assertEqual((root / "packed/data.fpk").read_bytes(), original)

    def test_text_table_package_names_the_other_extractor(self):
        members = dict(txd_fixture(), **{"ACT_A.txt": "テスト。\r\n".encode("utf-8")})
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "data.fpk").write_bytes(archive(members))
            with self.assertRaises(FormatError) as caught:
                extract(root, root / "work")
            self.assertIn("systemc_txd_extract", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
