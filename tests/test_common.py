"""Synthetic tests only: no game assets, upstream installations, or network."""

from copy import deepcopy
from pathlib import Path
import os
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from python.common.binary import (Edit, FormatError, Reader, apply_edits,
                                  bounded_zlib, checked_slice, relocate_u32)
from python.common.contract import (dump_rows, load_json, make_manifest,
                                    validate_rows, validate_translation)
from python.common.safety import Limits, logical_path, validate_names, write_new_tree


class BinaryTests(unittest.TestCase):
    def test_slice_and_utf16_alignment(self):
        with self.assertRaises(FormatError):
            checked_slice(b"a", 0, 2)
        with self.assertRaises(FormatError):
            checked_slice(b"a", -1, 1)
        with self.assertRaises(FormatError):
            checked_slice(b"a", True, 0)
        # The 00 00 crossing two code units is not the terminator.
        reader = Reader(b"A\0\0\x01\0\0")
        self.assertEqual(reader.terminated(unit=2), b"A\0\0\x01")
        self.assertEqual(reader.pos, 6)
        with self.assertRaises(FormatError):
            Reader(b"abcd").terminated(max_bytes=3)
        with self.assertRaises(FormatError):
            Reader(b"1234").unpack("I")

    def test_zlib_bounds_and_framing(self):
        compressed = zlib.compress(b"abc" * 1000)
        self.assertEqual(bounded_zlib(compressed, max_output=3000, expected_size=3000), b"abc" * 1000)
        for invalid, limit in ((compressed, 2999), (compressed[:-1], 4000),
                               (compressed + b"x", 4000), (b"garbage", 4000)):
            with self.subTest(limit=limit, input_size=len(invalid)):
                with self.assertRaises(FormatError):
                    bounded_zlib(invalid, max_output=limit)
        self.assertEqual(bounded_zlib(zlib.compress(b""), max_output=0), b"")

    def test_relocation_updates_field_and_target(self):
        # Header points beyond a 3-byte text span; another pointer moves too.
        original = struct.pack("<I", 11) + b"abc" + struct.pack("<I", 4) + b"Z"
        modified, mapping = apply_edits(original, [Edit(4, 7, b"abcdef")])
        rebuilt = relocate_u32(original, modified, mapping, [0, 7])
        self.assertEqual(struct.unpack_from("<I", rebuilt, 0)[0], 14)
        self.assertEqual(struct.unpack_from("<I", rebuilt, 10)[0], 4)
        self.assertEqual(rebuilt[14:], b"Z")
        self.assertEqual(mapping.map(12), 15)
        with self.assertRaises(FormatError):
            mapping.map(5)
        with self.assertRaises(FormatError):
            relocate_u32(original, modified, mapping, [0, 0])
        with self.assertRaises(FormatError):
            apply_edits(original, [Edit(4, 7, b"x"), Edit(6, 8, b"y")])
        with self.assertRaises(FormatError):
            apply_edits(original, [Edit(4, 4, b"x")])

    def test_reject_pointer_fields_overlapping_same_length_edits(self):
        original = struct.pack("<I", 8) + b"abcdZ"
        for edit in (Edit(0, 4, b"TEXT"), Edit(1, 3, b"XY")):
            modified, mapping = apply_edits(original, [edit])
            with self.subTest(edit=edit), self.assertRaises(FormatError):
                relocate_u32(original, modified, mapping, [0])

    def test_unit_and_relative_base(self):
        original = struct.pack(">I", 2) + b"aaaa" + b"bbbb" + b"end!"
        modified, mapping = apply_edits(original, [Edit(4, 8, b"a" * 8)])
        patched = relocate_u32(original, modified, mapping, [0], base=4, unit=4, endian=">")
        self.assertEqual(struct.unpack_from(">I", patched)[0], 3)


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.rows = [{"name": "Guide", "message": "hello[n]world"}, {"message": "same"}, {"message": "same"}]
        self.sources = {"scenario/a.bin": b"original bytes"}
        self.manifest = make_manifest(
            engine="synthetic", variant="test-only", reference="fixture-1",
            sources=self.sources, rows=self.rows,
            locators=[{"node": i} for i in range(3)], encoding="utf-8",
            name_policies=["writable", "absent", "absent"],
            protected_tokens=[["[n]"], [], []],
        )

    def test_json_and_changed_lengths(self):
        self.assertEqual(validate_rows(load_json(dump_rows(self.rows))), self.rows)
        translated = [{"name": "向导", "message": "更长的译文[n]下一行"}, {"message": "甲"}, {"message": "不同译文"}]
        before = deepcopy(self.manifest)
        self.assertEqual(validate_translation(self.manifest, self.sources, self.rows, translated), translated)
        self.assertEqual(self.manifest, before)
        self.assertEqual(self.rows[1]["message"], "same")
        self.assertNotEqual(self.manifest["records"][1]["id"], self.manifest["records"][2]["id"])

    def test_reject_json_ambiguities(self):
        for data in (b'{"message":"a","message":"b"}', b"[NaN]", b"[Infinity]", b"\xff"):
            with self.subTest(data=data), self.assertRaises(FormatError):
                load_json(data)
        for rows in ({}, ["text"], [{"message": 1}], [{"message": "x", "pre_src": "x"}],
                     [{"message": "x", "name": "a", "names": ["b"]}],
                     [{"message": "\ud800"}]):
            with self.subTest(rows=repr(rows)), self.assertRaises(FormatError):
                validate_rows(rows)
        with self.assertRaises(FormatError):
            load_json(b"[]", max_bytes=1)

    def test_source_count_tokens_and_field_changes(self):
        cases = [self.rows[:1], [{"message": "changed"}] + self.rows[1:]]
        token_loss = deepcopy(self.rows)
        token_loss[0]["message"] = "lost control"
        cases.append(token_loss)
        for translated in cases:
            with self.subTest(translated=translated), self.assertRaises(FormatError):
                validate_translation(self.manifest, self.sources, self.rows, translated)
        with self.assertRaises(FormatError):
            validate_translation(self.manifest, {"scenario/a.bin": b"modified"}, self.rows, self.rows)
        original = deepcopy(self.rows)
        original[1]["message"] = "edited original"
        with self.assertRaises(FormatError):
            validate_translation(self.manifest, self.sources, original, self.rows)

    def test_name_and_encoding_policies(self):
        translated = deepcopy(self.rows)
        translated[0]["name"] = "another name"
        manifest = deepcopy(self.manifest)
        manifest["records"][0]["name_policy"] = "context"
        with self.assertRaises(FormatError):
            validate_translation(manifest, self.sources, self.rows, translated)
        manifest = deepcopy(self.manifest)
        manifest["encoding"] = "ascii"
        translated[0]["message"] = "中文[n]正文"
        with self.assertRaises(FormatError):
            validate_translation(manifest, self.sources, self.rows, translated)

    def test_multiple_speakers_keep_slot_count(self):
        rows = [{"names": ["A", "B"], "message": "hi"}]
        manifest = make_manifest(engine="test", variant="two-speakers", reference="fixture",
                                 sources=self.sources, rows=rows, locators=[{"node": 0}],
                                 encoding="utf-8", name_policies=["writable"])
        translated = [{"names": ["甲", "乙"], "message": "你好"}]
        self.assertEqual(validate_translation(manifest, self.sources, rows, translated), translated)
        translated[0]["names"].pop()
        with self.assertRaises(FormatError):
            validate_translation(manifest, self.sources, rows, translated)

    def test_manifest_schema_rejects_empty_identity_and_bool_integers(self):
        rows, sources = [{"message": "x"}], {"a": b"x"}
        good = make_manifest(engine="test", variant="one", reference="v1", sources=sources,
                             rows=rows, locators=[{"node": 0}], encoding="utf-8")
        mutations = [
            ("missing-engine", lambda m: m.pop("engine")),
            ("null-locator", lambda m: m["records"][0].update(locator=None)),
            ("empty-id", lambda m: m["records"][0].update(id="")),
            ("bool-position", lambda m: m["records"][0].update(position=False)),
            ("bool-count", lambda m: m["translation"].update(count=True)),
            ("bool-size", lambda m: m["sources"][0].update(size=True)),
            ("list-settings", lambda m: m.update(settings=[])),
        ]
        for label, mutate in mutations:
            manifest = deepcopy(good)
            mutate(manifest)
            with self.subTest(label=label), self.assertRaises(FormatError):
                validate_translation(manifest, sources, rows, rows)

    def test_empty_exports_still_validate_encoding_and_settings(self):
        kwargs = dict(engine="test", variant="empty", reference="v1", sources={"a": b"x"},
                      rows=[], locators=[])
        with self.assertRaises(FormatError):
            make_manifest(**kwargs, encoding="not-a-real-codec")
        with self.assertRaises(FormatError):
            make_manifest(**kwargs, encoding="utf-8", settings=[])
        manifest = make_manifest(**kwargs, encoding="utf-8")
        manifest["encoding"] = "not-a-real-codec"
        with self.assertRaises(FormatError):
            validate_translation(manifest, {"a": b"x"}, [], [])

    def test_equal_length_reordering_is_not_detectable(self):
        translated = deepcopy(self.rows)
        translated[1]["message"], translated[2]["message"] = "second", "first"
        self.assertEqual(validate_translation(self.manifest, self.sources, self.rows, translated), translated)
        self.assertIn("not-detectable", self.manifest["translation"]["order"])


class SafetyTests(unittest.TestCase):
    def test_paths(self):
        self.assertEqual(logical_path("folder\\scene.ks"), "folder/scene.ks")
        for path in ("../x", "/x", "C:/x", "a:b", "a//b", "a/./b", "a/../b",
                     "CON", "aux.txt", "com¹.log", "a.", "b ", "x\0y", "\\\\host\\x"):
            with self.subTest(path=path), self.assertRaises(FormatError):
                logical_path(path)
        for names in (["A.ks", "a.ks"], ["a", "a/b"], ["a/b", "a"],
                      ["café.txt", "cafe\u0301.txt"]):
            with self.subTest(names=names), self.assertRaises(FormatError):
                validate_names(names)

    def test_new_tree_never_overwrites(self):
        with tempfile.TemporaryDirectory() as root:
            destination = Path(root) / "new"
            entries = [("script/场景.ks", b"dialogue"), ("script/next.ks", b"next")]
            self.assertEqual(write_new_tree(destination, entries), [name for name, _ in entries])
            self.assertEqual((destination / "script/场景.ks").read_bytes(), b"dialogue")
            with self.assertRaises(FileExistsError):
                write_new_tree(destination, [("script/场景.ks", b"replacement")])
            self.assertEqual((destination / "script/场景.ks").read_bytes(), b"dialogue")
            with self.assertRaises(FormatError):
                write_new_tree(Path(root) / "invalid", [("../escape", b"x")])
            self.assertFalse((Path(root) / "invalid").exists())
            with self.assertRaises(FormatError):
                write_new_tree(Path(root) / "oversized", [("a", b"ab")], Limits(max_file_bytes=1))
            self.assertFalse((Path(root) / "oversized").exists())

    def test_symlink_parent_rejected_if_supported(self):
        with tempfile.TemporaryDirectory() as root:
            real = Path(root) / "real"
            real.mkdir()
            link = Path(root) / "link"
            try:
                link.symlink_to(real, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("platform does not permit creating symlinks")
            with self.assertRaises(FormatError):
                write_new_tree(link / "new", [("x", b"x")])
            self.assertFalse((real / "new").exists())


if __name__ == "__main__":
    unittest.main()
