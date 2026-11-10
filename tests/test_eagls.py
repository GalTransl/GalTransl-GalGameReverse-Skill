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
        self.profile = Profile(text_offset=144)
        self.body = '$Start\n&1"narration"#花子,104=voice01\r\n&2"遅い"&3"next"\r\n52("_SelStr12","yes")52("_SelStr0","")\r\n$End\r\n43()\r\n'
        self.raw = script(self.body, self.profile)

    def test_names_one_shot_choices_and_identity(self):
        rows, manifest = export_script(self.raw, self.profile)
        self.assertEqual(rows, [{"message": "narration"}, {"name": "花子", "message": "遅い"},
                                {"message": "next"}, {"message": "yes"}])
        self.assertEqual(rebuild_script(self.raw, rows, manifest, self.profile), self.raw)

    def test_changed_name_body_and_label_relocation(self):
        rows, manifest = export_script(self.raw, self.profile)
        rows[1] = {"name": "太郎", "message": "遅い ABC LONGER"}
        modified = rebuild_script(self.raw, rows, manifest, self.profile)
        before, _, _ = parse_script(self.raw, self.profile)
        after, actual, _ = parse_script(modified, self.profile)
        self.assertEqual(actual, rows)
        self.assertIn(b",104=voice01", after)
        self.assertEqual(after[-2:], before[-2:])
        old = dict(read_labels(before, text_offset=144))[b"End"]
        new = dict(read_labels(after, text_offset=144))[b"End"]
        self.assertEqual(new - old, len(after) - len(before))

    def test_labels_glued_to_commands_and_variable_length_shift(self):
        # Labels directly after ')' or '"' are valid; '$Endless' must not match '$End'.
        body = '43("a",0)$Start\n&1"before"#花子\r\n&2"ここ"$End\n&3"after $Endless"\r\n'
        raw = script(body, self.profile)
        rows, manifest = export_script(raw, self.profile)
        self.assertEqual(rows, [{"message": "before"}, {"name": "花子", "message": "ここ"},
                                {"message": "after $Endless"}])
        self.assertEqual(rebuild_script(raw, rows, manifest, self.profile), raw)
        for first, second in (("much longer narration text", "遅い台詞をもっと長くする"), ("x", "短")):
            changed = copy.deepcopy(rows)
            changed[0]["message"], changed[1]["message"] = first, second
            modified = rebuild_script(raw, changed, manifest, self.profile)
            plain, actual, _ = parse_script(modified, self.profile)
            self.assertEqual(actual, changed)
            labels = dict(read_labels(plain, text_offset=144))
            text = plain[144:-2]
            self.assertEqual(labels[b"Start"], text.index(b"$Start"))
            self.assertEqual(text[labels[b"End"]:labels[b"End"] + 5], b"$End\n")
            self.assertEqual(text[labels[b"End"] - 1:labels[b"End"]], b'"')

    def test_wrong_stored_label_offset_reports_label_and_offset(self):
        raw = script('$Start\n&1"text"\r\n$End\r\n', self.profile)
        plain = bytearray(crypt_script(raw, text_offset=144, key=self.profile.key, version=2))
        struct.pack_into("<I", plain, 36 + 32, 3)
        bad = crypt_script(bytes(plain), text_offset=144, key=self.profile.key, version=2)
        with self.assertRaisesRegex(ValueError, r"\$End offset 3"):
            export_script(bad, self.profile)
        # A prefix of a longer label is not its label token.
        raw = script('$Start\n&1"text"\r\n$Endless\r\n$End\r\n', self.profile)
        plain = bytearray(crypt_script(raw, text_offset=144, key=self.profile.key, version=2))
        struct.pack_into("<I", plain, 36 + 32, bytes(plain[144:]).index(b"$Endless"))
        bad = crypt_script(bytes(plain), text_offset=144, key=self.profile.key, version=2)
        with self.assertRaises(ValueError):
            export_script(bad, self.profile)

    def test_blocked_member_is_isolated_preserved_and_refused(self):
        raw = script('$Start\n&1"text"\r\n$End\r\n', self.profile)
        plain = bytearray(crypt_script(raw, text_offset=144, key=self.profile.key, version=2))
        struct.pack_into("<I", plain, 36 + 32, 3)
        bad = crypt_script(bytes(plain), text_offset=144, key=self.profile.key, version=2)
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            idx, pak = archive([("sc01.dat", self.raw), ("sc02.dat", bad), ("sc03.dat", raw)])
            (root / "SCPACK.idx").write_bytes(idx)
            (root / "SCPACK.pak").write_bytes(pak)
            report = extract(root, root / "work", profile=self.profile, key=b"key")
            self.assertEqual(report["status"], "partial")
            self.assertEqual([b["name"] for b in report["blocked"]], ["sc02.dat"])
            self.assertRegex(report["blocked"][0]["reason"], r"pak offset \d+.*\$End offset 3")
            self.assertEqual(report["no_edit_members_identical"], 2)
            self.assertEqual(report["blocked_members_copied_verbatim"], 1)
            self.assertTrue((root / "work/gt_input/sc01.json").exists())
            self.assertTrue((root / "work/gt_input/sc03.json").exists())
            self.assertFalse((root / "work/gt_input/sc02.json").exists())
            self.assertFalse((root / "work/original/scripts/sc02.dat").exists())
            self.assertEqual((root / "work/rebuilt/roundtrip/script/SCPACK.pak").read_bytes(), pak)
            # A translation for the blocked member is refused, not silently dropped.
            (root / "work/gt_output/sc02.json").write_bytes(dump_rows([{"message": "x"}]))
            with self.assertRaisesRegex(ValueError, r"blocked member.*sc02\.json.*sc02\.dat"):
                rebuild(root / "work", root / "refused")
            (root / "work/gt_output/sc02.json").unlink()
            rows, _ = export_script(raw, self.profile)
            rows[0]["message"] = "a much longer replacement text"
            (root / "work/gt_output/sc03.json").write_bytes(dump_rows(rows))
            result = rebuild(root / "work", root / "patch")
            self.assertEqual(result["translated_members"], ["sc03.dat"])
            self.assertEqual(result["copied_blocked_members"], ["sc02.dat"])
            new_pak = (root / "patch/script/SCPACK.pak").read_bytes()
            _, new_entries = read_index((root / "patch/script/SCPACK.idx").read_bytes(), len(new_pak),
                                        key=b"key", long_offsets=True)
            members = {e.name: new_pak[e.offset:e.offset + e.size] for e in new_entries}
            self.assertEqual(members["sc02.dat"], bad)
            self.assertEqual(members["sc01.dat"], self.raw)
            self.assertEqual(export_script(members["sc03.dat"], self.profile)[0], rows)

    def test_invalid_translation_and_manifest(self):
        original, manifest = export_script(self.raw, self.profile)
        for value in ('bad"quote', 'bad\nline', 'injected#', '😀', '迟'):
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

    def test_legacy_character_table_settings(self):
        from python.engines.eagls_extract import _legacy_profile_settings
        self.assertEqual(_legacy_profile_settings({"version": 2, "source_characters": "", "target_characters": ""}),
                         {"version": 2})
        with self.assertRaises(ValueError):
            _legacy_profile_settings({"version": 2, "source_characters": "A", "target_characters": "B"})
        with self.assertRaises(ValueError):
            Profile().encode("迟")

    def test_workspace_roundtrip_partial_translation_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            idx, pak = archive([("sc01.dat", self.raw), ("system.dat", script('$Start\n$End\n43()\n', self.profile))])
            (root / "SCPACK.idx").write_bytes(idx)
            (root / "SCPACK.pak").write_bytes(pak)
            (root / 'work').mkdir()
            report = extract(root, root / "work", profile=self.profile, key=b"key", smoke_test=True)
            self.assertEqual(report["rows"], 4)
            self.assertEqual((report["status"], report["blocked"]), ("complete", []))
            self.assertFalse((root / "work/gt_input/system.json").exists())
            rows, _ = export_script(self.raw, self.profile)
            rows[0]["message"] = "changed"
            (root / "work/gt_output/sc01.json").write_bytes(dump_rows(rows))
            (root / 'patch').mkdir()
            result = rebuild(root / "work", root / "patch")
            self.assertEqual(result["translated_members"], ["sc01.dat"])
            with self.assertRaises(FileExistsError):
                extract(root, root / "work", profile=self.profile, key=b"key")
            self.assertEqual((root / "SCPACK.pak").read_bytes(), pak)


if __name__ == "__main__":
    unittest.main()
