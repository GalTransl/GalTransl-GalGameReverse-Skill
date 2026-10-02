"""Synthetic EAGLS fixtures: no copyrighted game data required."""
import copy
import struct
import tempfile
import unittest
from pathlib import Path

from python.archives.eagls import crypt_index, read_index, pack_archive
from python.engines.eagls import crypt_script, read_labels
from python.engines.eagls_text import Profile, export_script, rebuild_script, parse_script
from python.engines.eagls_extract import extract, rebuild, load_profile
from python.common.contract import dump_rows


def script(body, profile):
    raw = body.encode(profile.encoding)
    table = bytearray(profile.text_offset)
    for n, name in enumerate((b"Start", b"End")):
        struct.pack_into(f"<{profile.label_size - 4}sI", table, n * profile.label_size,
                         name, raw.index(b"$" + name))
    plain = bytes(table) + raw + b"\0\x80"[-profile.version:]
    return crypt_script(plain, text_offset=profile.text_offset, key=profile.key, version=profile.version)


def archive(members, long=True, base=5963):
    width, fmt = (24, "<QQ") if long else (20, "<II")
    idx, pak = bytearray(), bytearray()
    for name, data in members:
        idx.extend(name.encode().ljust(width, b"\0"))
        idx.extend(struct.pack(fmt, base + len(pak), len(data)))
        pak.extend(data)
    idx.extend(bytes(width + struct.calcsize(fmt)) + b"preserved padding" + struct.pack("<I", 123))
    return crypt_index(bytes(idx), b"key"), bytes(pak)


class EaglsArchiveTests(unittest.TestCase):
    def test_short_long_bases_relocation_padding(self):
        for long in (False, True):
            for base in (0, 5963):
                idx, pak = archive([("a.dat", b"aaa"), ("b.dat", b"bb")], long, base)
                self.assertEqual(pack_archive(idx, pak, {}, key=b"key", long_offsets=long), (idx, pak))
                new_idx, new_pak = pack_archive(idx, pak, {"a.dat": b"larger"}, key=b"key", long_offsets=long)
                plain, entries = read_index(new_idx, len(new_pak), key=b"key", long_offsets=long)
                self.assertEqual(entries[1].offset, 6)
                self.assertEqual(new_pak, b"largerbb")
                self.assertEqual(plain[-21:], crypt_index(idx, b"key")[-21:])

    def test_bad_offsets_names_and_truncation(self):
        for names in (("../a", "b"), ("a.dat", "A.dat")):
            idx, pak = archive([(n, b"x") for n in names])
            with self.assertRaises(ValueError):
                read_index(idx, len(pak), key=b"key", long_offsets=True)
        idx, pak = archive([("a.dat", b"x"), ("b.dat", b"y")])
        plain = bytearray(crypt_index(idx, b"key"))
        struct.pack_into("<Q", plain, 64, 5963)
        with self.assertRaises(ValueError):
            read_index(crypt_index(bytes(plain), b"key"), 2, key=b"key", long_offsets=True)
        with self.assertRaises(ValueError):
            read_index(idx, 1, key=b"key", long_offsets=True)
        with self.assertRaises(ValueError):
            pack_archive(idx, pak, {"missing": b"x"}, key=b"key", long_offsets=True)


class EaglsTextTests(unittest.TestCase):
    def setUp(self):
        self.profile = Profile(text_offset=144, source_characters="遅", target_characters="迟")
        self.body = '$Start\n&1"narration"#花子,104=voice01\r\n&2"遅い"&3"next"\r\n52("_SelStr12","yes")52("_SelStr0","")\r\n$End\r\n43()\r\n'
        self.raw = script(self.body, self.profile)

    def test_names_one_shot_choices_and_identity(self):
        rows, manifest = export_script(self.raw, self.profile)
        self.assertEqual(rows, [{"message": "narration"}, {"name": "花子", "message": "迟い"},
                                {"message": "next"}, {"message": "yes"}])
        self.assertEqual(rebuild_script(self.raw, rows, manifest, self.profile), self.raw)

    def test_changed_name_body_and_label_relocation(self):
        rows, manifest = export_script(self.raw, self.profile)
        rows[1] = {"name": "太郎", "message": "迟い ABC LONGER"}
        modified = rebuild_script(self.raw, rows, manifest, self.profile)
        before, _, _ = parse_script(self.raw, self.profile)
        after, actual, _ = parse_script(modified, self.profile)
        self.assertEqual(actual, rows)
        self.assertIn(b",104=voice01", after)
        self.assertEqual(after[-2:], before[-2:])
        old = dict(read_labels(before, text_offset=144))[b"End"]
        new = dict(read_labels(after, text_offset=144))[b"End"]
        self.assertEqual(new - old, len(after) - len(before))

    def test_invalid_translation_and_manifest(self):
        original, manifest = export_script(self.raw, self.profile)
        for value in ('bad"quote', 'bad\nline', 'injected#', '😀', '遅'):
            rows = copy.deepcopy(original)
            rows[1]["message"] = value
            with self.subTest(value=value), self.assertRaises((ValueError, UnicodeError)):
                rebuild_script(self.raw, rows, manifest, self.profile)
        changed = copy.deepcopy(manifest)
        changed["records"][0]["locator"]["message"][0] += 1
        with self.assertRaises(ValueError):
            rebuild_script(self.raw, original, changed, self.profile)

    def test_v1_and_alis_label_width(self):
        p = Profile(text_offset=408, label_size=136, version=1, key=b"ADVSYS")
        raw = script('$Start\r\n&1"hello"\r\n$End\r\n', p)
        rows, meta = export_script(raw, p)
        self.assertEqual(rebuild_script(raw, rows, meta, p), raw)

    def test_ambiguous_mapping_and_enabled_tunnel(self):
        with self.assertRaises(ValueError):
            Profile(source_characters="AB", target_characters="CC")
        with self.assertRaises(ValueError):
            load_profile(b'{"tunnel_decoder":{"enable":true}}')

    def test_workspace_roundtrip_partial_translation_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            idx, pak = archive([("sc01.dat", self.raw), ("system.dat", script('$Start\n$End\n43()\n', self.profile))])
            (root / "SCPACK.idx").write_bytes(idx)
            (root / "SCPACK.pak").write_bytes(pak)
            report = extract(root, root / "work", profile=self.profile, key=b"key", smoke_test=True)
            self.assertEqual(report["rows"], 4)
            self.assertFalse((root / "work/gt_input/system.json").exists())
            rows, _ = export_script(self.raw, self.profile)
            rows[0]["message"] = "changed"
            (root / "work/gt_output/sc01.json").write_bytes(dump_rows(rows))
            result = rebuild(root / "work", root / "patch")
            self.assertEqual(result["translated_members"], ["sc01.dat"])
            with self.assertRaises(FileExistsError):
                extract(root, root / "work", profile=self.profile, key=b"key")
            self.assertEqual((root / "SCPACK.pak").read_bytes(), pak)


if __name__ == "__main__":
    unittest.main()
