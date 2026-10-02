# SPDX-License-Identifier: GPL-3.0-only
"""SystemC encrypted FPK and cross-checked ACT/DAT/SPT regression fixtures."""
from copy import deepcopy
import json
from pathlib import Path
import struct
import tempfile
import unittest

from python.archives.systemc import (decode_zlc2, decode_zlc2_literals, encode_zlc2_literals,
    decode_member, read_fpk_index, unpack_fpk, rebuild_fpk)
from python.common.binary import FormatError
from python.common.safety import Limits
from python.engines.systemc import export_act, inject_act
from python.engines.systemc_extract import extract, pack


def archive(members):
    """Independent fixture builder: index between members, nonzero preserved gaps."""
    key = b"test"
    out = bytearray(struct.pack("<I", 0x80000000 | len(members)))
    entries = []
    index_at = None
    for i, (name, content) in enumerate(members.items()):
        if i == 1 or len(members) == 1:
            index_at = len(out)
            out.extend(bytes(len(members) * 36))
            out.extend(b"after-index-gap")
        payload = encode_zlc2_literals(content)
        entries.append(struct.pack("<II24sI", len(out), len(payload), name.encode("cp932"), i + 987))
        out.extend(payload)
        out.extend(b"gap")
    encoded = b"".join(entries)
    out[index_at:index_at + len(encoded)] = bytes(v ^ key[i % 4] for i, v in enumerate(encoded))
    return bytes(out + key + struct.pack("<I", index_at))


def fixture():
    lines = ["", "***SC_A0000_000_A0000_10\t//section", "EF_NOP", "仮名　（０００１）　声優別名",
             "「確認$Sです。", "続き$Lです」", "", "地の文。", "", "//最後", ""]
    dat = b"section\0".ljust(80, b"\0") + struct.pack("<19i", 2, 10, 0, 0, 0, *([0] * 14))
    commands = [(37, 0, 0, -1, -1, 0, 4, 0), (1, 1, 1, -1, 3, 3, 7, 0),
                (1, 2, 0, -1, 7, 1, 7, 0)]
    return {"ACT_A.txt": "\r\n".join(lines).encode("cp932"),
            "ACT_A.DAT": struct.pack("<I", 1) + dat,
            "A0000_00.spt": struct.pack("<I", len(commands)) + b"".join(struct.pack("<8i", *r) for r in commands),
            "charaid.tbl": "//キャラ\r\n仮名 1\r\nナレーション 0\r\n".encode("cp932"),
            "orphan.spt": b"opaque old compiled script", "resource.bin": b"untouched"}


class ZlcTests(unittest.TestCase):
    def test_overlap_msb_and_legacy_subset(self):
        encoded = b"ZLC2" + struct.pack("<I", 6) + b"\x40A\x01\x02"
        self.assertEqual(decode_zlc2(encoded), b"AAAAAA")
        with self.assertRaises(ValueError):
            decode_zlc2_literals(encoded)
        self.assertEqual(decode_zlc2(encoded + b"\0"), b"AAAAAA")

    def test_bad_match_truncation_tail_and_budget(self):
        header = b"ZLC2" + struct.pack("<I", 3)
        for body in (b"\x80\x01\0", b"\x80\x01", b"\0a", b"\0abcxx"):
            with self.subTest(body=body), self.assertRaises(FormatError):
                decode_zlc2(header + body)
        with self.assertRaises(FormatError):
            decode_zlc2(encode_zlc2_literals(b"abc"), max_output=2)

    def test_distance_zero_and_clipped_final_match(self):
        prefix = bytes(range(256)) * 16
        literals = encode_zlc2_literals(prefix)[8:]
        encoded = b"ZLC2" + struct.pack("<I", 4097) + literals + b"\x80\0\0"
        self.assertEqual(decode_zlc2(encoded), prefix + prefix[:1])

    def test_nested_layers(self):
        payload = b"nested"
        for _ in range(3):
            payload = encode_zlc2_literals(payload)
        self.assertEqual(decode_member(payload), b"nested")
        with self.assertRaises(FormatError):
            decode_member(payload, max_layers=2)


class FpkTests(unittest.TestCase):
    def test_layout_roundtrip_and_growth_before_middle_index(self):
        members = fixture()
        original = archive(members)
        index, unpacked = unpack_fpk(original)
        self.assertEqual(unpacked, members)
        self.assertEqual(rebuild_fpk(original, members), original)
        new = dict(members, **{"ACT_A.txt": b"grow" * 300})
        rebuilt = rebuild_fpk(original, new)
        new_index, actual = unpack_fpk(rebuilt)
        self.assertEqual(actual, new)
        self.assertGreater(new_index.offset, index.offset)
        self.assertEqual([e.raw_index[8:] for e in index.entries], [e.raw_index[8:] for e in new_index.entries])
        self.assertIn(b"after-index-gap", rebuilt)
        self.assertEqual(rebuilt.count(b"gap"), original.count(b"gap"))

    def test_unsafe_duplicate_and_overlap_index(self):
        for names in ({"../x": b"a", "ok": b"b"}, {"a": b"a", "A": b"b"}):
            with self.assertRaises(FormatError):
                read_fpk_index(archive(names))
        raw = bytearray(archive(fixture()))
        idx = read_fpk_index(raw)
        # Re-encrypt first offset to point into the index itself.
        raw[idx.offset:idx.offset + 4] = bytes(v ^ idx.key[i] for i, v in enumerate(struct.pack("<I", idx.offset)))
        with self.assertRaises(FormatError):
            read_fpk_index(raw)

    def test_decompression_total_budget(self):
        raw = archive({"a": b"a" * 300, "b": b"b" * 300})
        # Archive size is larger than logical payload for literals; use compressed
        # single member to independently exercise member budget.
        with self.assertRaises(FormatError):
            unpack_fpk(raw, limits=Limits(max_file_bytes=200))
        with self.assertRaises(FormatError):
            rebuild_fpk(raw, {"unknown": b"a"})


class ScriptTests(unittest.TestCase):
    def test_name_context_line_ranges_and_length_change(self):
        members = fixture()
        rows, meta = export_act("ACT_A.txt", members)
        self.assertEqual(rows, [{"name": "仮名", "message": "「確認$Sです。\n続き$Lです」"}, {"message": "地の文。"}])
        self.assertEqual(inject_act("ACT_A.txt", members, rows, meta, rows), members["ACT_A.txt"])
        translated = deepcopy(rows)
        translated[0]["message"] = "「変長の確認$Sです。\n続き$Lです」"
        out = inject_act("ACT_A.txt", members, rows, meta, translated)
        old_lines, new_lines = members["ACT_A.txt"].split(b"\r\n"), out.split(b"\r\n")
        self.assertEqual(len(old_lines), len(new_lines))
        self.assertEqual([i for i, (a, b) in enumerate(zip(old_lines, new_lines)) if a != b], [4])
        self.assertEqual(export_act("ACT_A.txt", dict(members, **{"ACT_A.txt": out}))[0], translated)

    def test_translation_invariants(self):
        members = fixture()
        rows, meta = export_act("ACT_A.txt", members)
        for bad in ("one line", "「$L確認\n続き$S」", "「$S確認\nEF_NEW_$L",
                    "「$S確認\n\x00$L", "「$S确认\n続き$L」", "「$S確認\n &new;$L"):
            changed = deepcopy(rows)
            changed[0]["message"] = bad
            with self.subTest(bad=bad), self.assertRaises((FormatError, UnicodeError)):
                inject_act("ACT_A.txt", members, rows, meta, changed)
        changed = deepcopy(rows)
        changed[0]["name"] = "変更"
        with self.assertRaises(FormatError):
            inject_act("ACT_A.txt", members, rows, meta, changed)

    def test_tampered_locator_and_source(self):
        members = fixture()
        rows, meta = export_act("ACT_A.txt", members)
        meta["records"][0]["locator"]["message_line"] = 2
        with self.assertRaises(FormatError):
            inject_act("ACT_A.txt", members, rows, meta, rows)
        for key, position, number in (("ACT_A.DAT", 84, 3), ("A0000_00.spt", 4, 999),
                                     ("A0000_00.spt", 44, 2), ("A0000_00.spt", 84, 3)):
            bad = dict(members)
            content = bytearray(bad[key])
            struct.pack_into("<i", content, position, number)
            bad[key] = bytes(content)
            with self.subTest(key=key,position=position), self.assertRaises(FormatError):
                export_act("ACT_A.txt", bad)

    def test_missing_dependency_and_unreferenced_prose(self):
        members = fixture()
        del members["A0000_00.spt"]
        with self.assertRaises(FormatError):
            export_act("ACT_A.txt", members)
        members = fixture()
        members["ACT_A.txt"] = members["ACT_A.txt"].replace(b"//", "漏れ".encode("cp932"))
        with self.assertRaises(FormatError):
            export_act("ACT_A.txt", members)

    def test_selection_and_no_dialogue(self):
        members = fixture()
        members["ACT_A.txt"] = members["ACT_A.txt"].replace(b"***SC_", b"***SS_")
        rows, meta = export_act("ACT_A.txt", members)
        self.assertTrue(all(r["locator"]["kind"] == "selection" for r in meta["records"]))
        members["ACT_A.txt"] = b"\r\n***SC_A0000_00_A0000_10\r\nEF_NOP\r\n"
        dat = bytearray(members["ACT_A.DAT"])
        struct.pack_into("<i", dat, 88, 3)
        members["ACT_A.DAT"] = bytes(dat)
        members["A0000_00.spt"] = struct.pack("<I8i", 1, 37, 0, 0, -1, -1, 0, 4, 0)
        self.assertEqual(export_act("ACT_A.txt", members)[0], [])
        with tempfile.TemporaryDirectory() as temp:
            game = Path(temp)
            (game / "data.fpk").write_bytes(archive(members))
            report = extract(game, game / "output")
            self.assertEqual(report["json_files"], 0)
            self.assertFalse((game / "output/gt_input/ACT_A.json").exists())

    def test_workspace_cli_flow(self):
        with tempfile.TemporaryDirectory() as temp:
            game = Path(temp)
            original = archive(fixture())
            (game / "data.fpk").write_bytes(original)
            work = game / "extract"
            report = extract(game, work, verify_edits=True)
            self.assertEqual(report["json_rows"], 2)
            self.assertEqual(report["unreferenced_spt"], ["orphan.spt"])
            self.assertTrue(pack(work, work / "no_translation")["byte_identical"])
            translated = json.loads((work / "gt_input/ACT_A.json").read_text(encoding="utf-8"))
            translated[1]["message"] = "地の文を変更。"
            (work / "gt_output/ACT_A.json").write_text(json.dumps(translated, ensure_ascii=False), encoding="utf-8")
            result = pack(work, work / "translated")
            self.assertEqual(result["changed_rows"], 1)
            _, packed = unpack_fpk((work / "translated/data.fpk").read_bytes())
            self.assertEqual(export_act("ACT_A.txt", packed)[0], translated)
            self.assertEqual((game / "data.fpk").read_bytes(), original)
            with self.assertRaises(FileExistsError):
                extract(game, work)


if __name__ == "__main__":
    unittest.main()
