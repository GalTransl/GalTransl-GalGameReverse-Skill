"""Synthetic Kaguya tables/LINK6 fixtures, independent of installed games."""
import copy
from dataclasses import replace
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest

from python.archives import kaguya_link as link
from python.common.binary import FormatError
from python.common.contract import dump_rows
from python.engines import kaguya
from python.engines.kaguya_extract import export, inject, extract, pack
from python.engines.kaguya_extract import pack as kaguya_pack


def document():
    return kaguya.Document(kaguya.MAGIC + b"\x01\xff", ("名前", "％"), ("選択％",),
        (kaguya.Message("本文\n", ("voice01", "声😀")), kaguya.Message("二つ目\n"),
         kaguya.Message("未使用")),
        (kaguya.Group(0, (0, 1)), kaguya.Group(-1, (0,)), kaguya.Group(1, (1,))),
        trailer=b"\x49\x8b\0\0opaque-suffix\x01\xff")


def link_file(entries):
    out = bytearray(b"LINK6\0\0\x03scr")
    for name, flags, payload in entries:
        raw = name.encode("utf-16-le")
        out.extend(struct.pack("<IH", 15 + len(raw) + len(payload), flags)
                   + b"1234567" + struct.pack("<H", len(raw)) + raw + payload)
    return bytes(out) + bytes(4)


class KaguyaMessageTests(unittest.TestCase):
    def test_explicit_suffix_and_original_roundtrip(self):
        data = kaguya.write_message_dat(document())
        with self.assertRaisesRegex(ValueError, "trailing"):
            kaguya.read_message_dat(data)
        parsed = kaguya.read_message_dat(data, allow_trailer=True)
        self.assertEqual(parsed, document())
        rows, manifest = export(data)
        self.assertEqual(inject(data, rows, manifest, rows), data)
        self.assertEqual(len(rows), 5)
        self.assertEqual(manifest["records"][3]["name_policy"], "context")

    def test_alias_bytes_are_preserved_for_unchanged_text(self):
        doc = replace(document(), raw_names=(b"\xfa\x40",), names=("ⅰ", "％"))
        data = kaguya.write_message_dat(doc)
        parsed = kaguya.read_message_dat(data, allow_trailer=True)
        self.assertEqual(parsed.raw_names[0], b"\xfa\x40")
        self.assertEqual(kaguya.write_message_dat(parsed), data)
        changed = replace(parsed, names=("変更", "％"))
        self.assertEqual(kaguya.read_message_dat(kaguya.write_message_dat(changed), allow_trailer=True).names[0], "変更")

    def test_shared_message_and_name_cloning(self):
        data = kaguya.write_message_dat(document())
        rows, manifest = export(data)
        edited = copy.deepcopy(rows)
        edited[0] = {"name": "別名", "message": "長い変更本文\n"}
        edited[1]["name"] = "別名"
        edited[2]["message"] = "別の出現位置の訳\n"
        edited[-1]["message"] = "変更した選択％"
        rebuilt = inject(data, rows, manifest, edited)
        parsed = kaguya.read_message_dat(rebuilt, allow_trailer=True)
        self.assertEqual(export(rebuilt)[0], edited)
        self.assertEqual(parsed.messages[:3], document().messages)
        self.assertEqual(parsed.groups[2].name_index, 1)
        self.assertNotEqual(parsed.groups[0].message_indexes[0], parsed.groups[1].message_indexes[0])
        self.assertEqual(parsed.messages[parsed.groups[0].message_indexes[0]].voices, document().messages[0].voices)
        self.assertEqual(parsed.trailer, document().trailer)

    def test_multiline_display_name(self):
        doc = replace(document(), names=("長い\n名前", "％"))
        source = kaguya.write_message_dat(doc)
        rows, manifest = export(source)
        changed = copy.deepcopy(rows)
        changed[0]["name"] = changed[1]["name"] = "別の長い\n名前"
        self.assertEqual(export(inject(source, rows, manifest, changed))[0], changed)
        changed[0]["name"] = changed[1]["name"] = "一行に変更"
        self.assertEqual(export(inject(source, rows, manifest, changed))[0], changed)
        longer = copy.deepcopy(rows)
        longer[0]["name"] = longer[1]["name"] = "長い\n\n名前"
        with self.assertRaises(ValueError):
            inject(source, rows, manifest, longer)

    def test_inconsistent_name_controls_encoding_and_manifest_rejected(self):
        data = kaguya.write_message_dat(document())
        rows, manifest = export(data)
        invalid = []
        changed = copy.deepcopy(rows)
        changed[0]["name"] = "違う名前"
        invalid.append(changed)
        changed = copy.deepcopy(rows)
        changed[3]["name"] = "主人公"
        invalid.append(changed)
        for text in ["\n位置変更", "改行\n増加\n", "NUL\0\n", "絵文字😀\n"]:
            changed = copy.deepcopy(rows)
            changed[0]["message"] = text
            invalid.append(changed)
        for changed in invalid:
            with self.assertRaises((ValueError, UnicodeError)):
                inject(data, rows, manifest, changed)
        # Fewer lines than the source are allowed.
        shorter = copy.deepcopy(rows)
        shorter[0]["message"] = "改行なし"
        self.assertEqual(export(inject(data, rows, manifest, shorter))[0], shorter)
        altered = copy.deepcopy(manifest)
        altered["records"][0]["locator"]["message_index"] = 2
        with self.assertRaises(ValueError):
            inject(data, rows, altered, rows)

    def test_bad_table_not_treated_as_suffix(self):
        source = kaguya.write_message_dat(document())
        # Negative first table count still fails even with suffix preservation.
        bad = source[:21] + b"\xff" * 4 + source[25:]
        with self.assertRaises(ValueError):
            kaguya.read_message_dat(bad, allow_trailer=True)
        with self.assertRaises(ValueError):
            kaguya.write_message_dat(document(), max_bytes=10)
        with self.assertRaises(ValueError):
            kaguya.read_message_dat(source, allow_trailer=True, max_bytes=10)


class KaguyaLinkTests(unittest.TestCase):
    def test_noop_and_changed_record_size(self):
        source = link_file([("開始.scr", 0, b"first"), ("次.scr", 0, b"second")])
        stream = io.BytesIO(source)
        index = link.read_index(stream)
        members = {e.name: link.read_member(stream, index, e) for e in index.entries}
        self.assertEqual(link.rebuild(stream, index, members), source)
        built = link.rebuild(stream, index, {"開始.scr": b"longer script data"})
        parsed = link.read_index(io.BytesIO(built))
        self.assertEqual(link.read_member(io.BytesIO(built), parsed, parsed.entries[1]), b"second")
        self.assertEqual(parsed.entries[0].record_header[4:], index.entries[0].record_header[4:])

    def test_encoded_members_only_allow_raw_copy(self):
        source = link_file([("cg.bin", 4, b"encrypted")])
        index = link.read_index(io.BytesIO(source))
        self.assertEqual(link.rebuild(io.BytesIO(source), index, {}), source)
        with self.assertRaises(ValueError):
            link.read_member(io.BytesIO(source), index, index.entries[0])
        with self.assertRaises(ValueError):
            link.rebuild(io.BytesIO(source), index, {"cg.bin": b"new"})

    def test_bad_names_ranges_and_footer(self):
        for source in [link_file([("../x", 0, b"x")]),
                       link_file([("a", 0, b"x"), ("A", 0, b"y")]),
                       link_file([("ok", 0, b"x")])[:-1],
                       link_file([("ok", 0, b"x")]) + b"garbage"]:
            with self.assertRaises(ValueError):
                link.read_index(io.BytesIO(source))


class KaguyaWorkflowTests(unittest.TestCase):
    def test_extract_pack_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = kaguya.write_message_dat(document())
            (root / "message.dat").write_bytes(original)
            (root / "scr.arc").write_bytes(link_file([("開始.scr", 0, b"[SCR-Ver5.1]test")]))
            (root / "params.dat").write_bytes(b"opaque-params")
            out = root / "extract"
            out.mkdir()
            report = extract(root, out, verify_edits=True)
            self.assertEqual(report["json_rows"], 5)
            self.assertEqual(report["unused_message_indexes"], [2])
            self.assertEqual(report["link6"]["members"], 1)
            self.assertEqual((out / "roundtrip/message.dat").read_bytes(), original)
            (out / 'empty-pack').mkdir()
            result = pack(out, out / "empty-pack")
            self.assertFalse(result["translation_provided"])
            self.assertEqual(result["changed_rows"], 0)
            rows = json.loads((out / "gt_input/message.json").read_text(encoding="utf-8"))
            rows[0]["message"] = "別の文章\n"
            (out / "gt_output/message.json").write_bytes(dump_rows(rows))
            result = pack(out, out / "packed")
            self.assertEqual(result["changed_rows"], 1)
            self.assertEqual(export((out / "packed/message.dat").read_bytes())[0], rows)
            self.assertEqual((root / "message.dat").read_bytes(), original)
            with self.assertRaises(FileExistsError):
                pack(out, out / "packed")
            with self.assertRaises(FileExistsError):
                extract(root, out)


class KaguyaJisWorkflowTests(unittest.TestCase):
    """Kaguya through the shared JIS workflow with private ('unused') proxies."""

    def workspace(self, root):
        doc = kaguya.Document(kaguya.MAGIC + b"\x01\xff", ("名前",), (),
                              (kaguya.Message("測試の本文\n"), kaguya.Message("二つ目\n")),
                              (kaguya.Group(0, (0, 1)), kaguya.Group(-1, (0,))))
        game = root / "game"
        game.mkdir()
        (game / "message.dat").write_bytes(kaguya.write_message_dat(doc))
        extract(game, root / "work")
        rows = json.loads((root / "work/gt_input/message.json").read_text(encoding="utf-8"))
        rows[0]["message"] = "测试\n"   # 测/试 fixed proxies are 測/試, still shown in row 3
        rows[1]["message"] = "第二句\n"
        (root / "work/gt_output/message.json").write_bytes(dump_rows(rows))
        return root / "work", rows

    def test_manifest_reserves_f040_and_unused_roundtrip(self):
        from python.common.jis_workflow import finalize, prepare
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            work, rows = self.workspace(root)
            manifest = json.loads((work / "metadata/message.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["settings"]["reserved_codepoints"], ["U+E000"])
            report = prepare(work, encoding="cp932", jis_preflight=True)
            self.assertEqual({c["character"] for c in report["conflicts"]}, {"测", "试"})
            self.assertEqual(report["reserved_codepoints"], {"metadata/message.json": ["U+E000"]})
            info = prepare(work, root / "prepared", encoding="cp932", proxy_policy="unused")
            self.assertEqual(info["remapped_count"], 2)
            self.assertEqual(info["reserved_codepoints"], ["U+E000"])
            kaguya_pack(root / "prepared/workspace", root / "packed")
            extract(root / "packed", root / "readback")
            result = finalize(root / "prepared", root / "packed", root / "readback/gt_input", root / "delivery")
            self.assertTrue(result["display_rows_verified"])
            self.assertEqual(result["batch_mapping_sha256"], info["batch_mapping_sha256"])
            config = json.loads((root / "delivery/uif_config.json").read_text(encoding="utf-8"))
            source = config["character_substitution"]["source_characters"]
            self.assertNotIn("\ue000", source)
            self.assertIn("\ue757", source)

    def test_reserved_e000_never_allocated_and_legacy_error_has_location(self):
        from python.common.jis_workflow import prepare
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            work, rows = self.workspace(root)
            # Only U+E000 would remain; the manifest reservation exhausts the pool instead.
            with self.assertRaisesRegex(FormatError, "pool exhausted"):
                prepare(work, root / "exhausted", encoding="cp932", proxy_policy="unused",
                        reserved_codepoints=["U+E001-U+E757"])
            self.assertFalse((root / "exhausted").exists())
            # A workspace exported before the setting existed still packs.
            path = work / "metadata/message.json"
            manifest = json.loads(path.read_text(encoding="utf-8"))
            del manifest["settings"]["reserved_codepoints"]
            path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            original = json.loads((work / "gt_input/message.json").read_text(encoding="utf-8"))
            self.assertEqual(inject((work / "original/message.dat").read_bytes(), original, manifest, original),
                             (work / "original/message.dat").read_bytes())
            bad = copy.deepcopy(original)
            bad[1]["message"] = "\ue000\n"
            with self.assertRaisesRegex(FormatError, r"row 2 \(r00000002\) field message: U\+E000"):
                inject((work / "original/message.dat").read_bytes(), original, manifest, bad)


if __name__ == "__main__":
    unittest.main()
