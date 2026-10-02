"""Synthetic fixtures only: serialized v20 and Utage book read/write contracts."""
import copy
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest

from python.archives import unity_serialized as a
from python.common.binary import FormatError
from python.engines import unity_utage as u
from python.engines import unity_utage_extract as workflow


def i(value):
    return struct.pack("<i", value)


def string(value):
    raw = value.encode("utf-8")
    return i(len(raw)) + raw + bytes(-len(raw) % 4)


def base(name="synthetic.book", script_id=900, file_id=0):
    return struct.pack("<iqB3xiq", 0, 0, 1, file_id, script_id) + string(name)


def grid_bytes(name="sheet:opening", shift=False, custom=None):
    values = custom if custom is not None else [
        (["Command", "Arg1", "Text", "Voice"], False, False),
        (["", "actor_key", "原文<param=x>\n次の行", "voice001"], False, False),
        (["Selection", "*next", "選択肢", ""], False, False),
        (["Wait", "1", "備考", ""], False, False),
        (["", "", "コメント", ""], False, True),
        (["//comment", "", "注釈", ""], False, False),
        (["", "", "空行フラグ", ""], True, False),
        (["Jump", "*next"], False, False),
    ]
    rows = []
    total = 0
    for ordinal, (cells, empty, comment) in enumerate(values):
        cells = ["", *cells] if shift else cells
        total += sum(len(s.encode("utf-16-le")) // 2 for s in cells)
        rows.append(i(ordinal * 2) + i(len(cells)) + b"".join(map(string, cells)) + i(empty) + i(comment))
    return i(len(rows)) + b"".join(rows) + string(name) + i(1) + i(total) + i(0)


def book_bytes(grids=None, file_id=0):
    grids = [grid_bytes()] if grids is None else grids
    return base(file_id=file_id) + i(0) + i(len(grids)) + b"".join(g + i(0) + i(0) for g in grids)


def chapter_bytes():
    table = grid_bytes("settings:Character", custom=[
        (["CharacterName", "NameText"], False, False),
        (["actor_key", "役名"], False, False)])
    return base("boot.chapter", 901) + string("") + i(1) + struct.pack("<iq", 0, 10) + i(1) + table


def mono_script(class_name):
    return string(class_name) + bytes(20) + string(class_name) + string("Utage") + string("Assembly-CSharp.dll")


def asset(objects=None, externals=()):
    if objects is None:
        objects = [(900, 115, mono_script("AdvImportBook")),
                   (901, 115, mono_script("AdvChapterData")), (10, 114, book_bytes()),
                   (20, 114, chapter_bytes()), (50, 49, b"opaque-nontext\x01\x02")]
    classes = list(dict.fromkeys(cls for _, cls, _ in objects))
    m = bytearray(b"2019.2.0f1\0" + i(19) + b"\0" + i(len(classes)))
    for cls in classes:
        m.extend(i(cls) + b"\0" + struct.pack("<h", -1) + bytes(16 if cls != 114 else 32))
    m.extend(i(len(objects)))
    data = bytearray()
    for pid, cls, raw in objects:
        m.extend(bytes(-(20 + len(m)) % 4))
        data.extend(bytes(-len(data) % 8))
        m.extend(struct.pack("<qIIi", pid, len(data), len(raw), classes.index(cls)))
        data.extend(raw)
    m.extend(i(0) + i(len(externals)))
    for ext in externals:
        m.extend(b"\0" + bytes(16) + i(0) + ext.encode() + b"\0")
    m.extend(i(0) + b"\0")
    offset = (20 + len(m) + 15) // 16 * 16
    header = struct.pack(">4I", len(m), offset + len(data), 20, offset) + bytes(4)
    return header + m + bytes(offset - 20 - len(m)) + data


class SerializedTests(unittest.TestCase):
    def test_identity_and_variable_object_relocation(self):
        raw = asset()
        self.assertEqual(a.rebuild(raw, {}), raw)
        old = a.read_index(io.BytesIO(raw))
        change = next(o for o in old.objects if o.path_id == 10)
        payload = raw[change.offset:change.offset + change.size] + b"arbitrary length"
        new = a.rebuild(raw, {10: payload})
        index = a.read_index(io.BytesIO(new))
        for x, y in zip(old.objects, index.objects):
            self.assertEqual(y.offset % 8, 0)
            self.assertEqual((x.path_id, x.class_id), (y.path_id, y.class_id))
            self.assertEqual(new[y.offset:y.offset + y.size], payload if x.path_id == 10 else raw[x.offset:x.offset + x.size])

    def test_header_bounds_and_versions(self):
        raw = asset()
        for value in (b"", raw[:19], raw[:-1], raw + b"x"):
            with self.subTest(size=len(value)), self.assertRaises(FormatError):
                a.read_index(io.BytesIO(value))
        for offset, fmt, value in ((8, ">I", 22), (12, ">I", 1), (16, "B", 1), (0, ">I", 0x7fffffff)):
            bad = bytearray(raw)
            struct.pack_into(fmt, bad, offset, value)
            with self.assertRaises(FormatError):
                a.read_index(io.BytesIO(bad))

    def test_opaque_gaps_and_trailer_survive_relocation(self):
        raw = asset()
        index = a.read_index(io.BytesIO(raw))
        gap_at = index.objects[1].offset
        gap, trailer = b"OPAQUE-GAP-12345", b"opaque trailer"
        raw = bytearray(raw[:gap_at] + gap + raw[gap_at:] + trailer)
        struct.pack_into(">I", raw, 4, len(raw))
        for obj in index.objects[1:]:
            struct.pack_into("<I", raw, obj.table_offset, obj.offset - index.data_offset + len(gap))
        raw = bytes(raw)
        self.assertEqual(a.rebuild(raw, {}), raw)
        changed = a.rebuild(raw, {900: b"different sized first object"})
        after = a.read_index(io.BytesIO(changed))
        self.assertEqual(changed[after.objects[1].offset - len(gap):after.objects[1].offset], gap)
        self.assertTrue(changed.endswith(trailer))

    def test_overlap_and_unknown_replacements(self):
        raw = asset()
        index = a.read_index(io.BytesIO(raw))
        bad = bytearray(raw)
        struct.pack_into("<I", bad, index.objects[1].table_offset, 0)
        with self.assertRaises(FormatError):
            a.read_index(io.BytesIO(bad))
        with self.assertRaises(FormatError):
            a.rebuild(raw, {12345: b"unknown"})

    def test_duplicate_ids_and_invalid_types(self):
        raw = asset()
        index = a.read_index(io.BytesIO(raw))
        for offset, fmt, value in ((index.objects[1].table_offset - 8, "<q", 900),
                                   (index.objects[1].table_offset + 8, "<i", 999)):
            bad = bytearray(raw)
            struct.pack_into(fmt, bad, offset, value)
            with self.assertRaises(FormatError):
                a.read_index(io.BytesIO(bad))

    def test_reader_padding_strings_and_offsets(self):
        for raw in (i(-1), i(10) + b"short", i(1) + b"\xff" + bytes(3), i(1) + b"aBAD"):
            with self.assertRaises((FormatError, UnicodeError)):
                a.Reader(raw).string()
        with self.assertRaises(FormatError):
            a.Reader(b"abc", -1)


class UtageTests(unittest.TestCase):
    def test_headers_flags_roles_and_name_context(self):
        for shift in (False, True):
            raw = book_bytes([grid_bytes(shift=shift)])
            b = u.read_book(raw)
            self.assertEqual(u.write_book(b), raw)
            item = u.export_book(b, {"actor_key": "役名"})[0]
            self.assertEqual(len(item["rows"]), 2)
            self.assertEqual(list(item["rows"][0]), ["name", "message"])
            self.assertEqual(item["rows"][0]["name"], "役名")
            self.assertEqual(item["locations"][1]["role"], "selection")
            self.assertEqual(item["excluded_text_cells"], {"Wait": 1, "comment-or-empty": 3})
            self.assertEqual(u.patch_book(raw, {0: item["rows"]}, {"actor_key": "役名"}), raw)

    def test_variable_chinese_non_bmp_and_all_nontext(self):
        raw = book_bytes()
        original = u.read_book(raw)
        rows = u.export_book(original)[0]["rows"]
        rows[0]["message"] = "变长中文与非 BMP：𠮷<param=x>\n第二行也改变长度。"
        changed = u.patch_book(raw, {0: rows})
        self.assertNotEqual(len(raw), len(changed))
        result = u.read_book(changed)
        self.assertEqual(u.export_book(result)[0]["rows"], rows)
        self.assertEqual(result.grids[0].text_length, u.units(result.grids[0]))
        self.assertEqual(result.grids[0].rows[2:], original.grids[0].rows[2:])
        self.assertEqual(result.grids[0].rows[1].strings[3], "voice001")

    def test_wrong_controls_names_counts_and_empty(self):
        raw = book_bytes()
        rows = u.export_book(u.read_book(raw))[0]["rows"]
        candidates = [rows[:-1]]
        for message in ("无变量", "原文<param=y>\n末尾", "原文<param=x>\r\n末尾", "", "坏\0字符", "原文<param=x>\n末尾<bad"):
            other = copy.deepcopy(rows)
            other[0]["message"] = message
            candidates.append(other)
        other = copy.deepcopy(rows)
        other[0]["name"] = "new-key"
        candidates.append(other)
        for candidate in candidates:
            with self.subTest(candidate=candidate), self.assertRaises(FormatError):
                u.patch_book(raw, {0: candidate})

    def test_unknown_command_not_silently_dropped(self):
        raw = book_bytes([grid_bytes(custom=[(["Command", "Arg1", "Text"], False, False),
            (["PluginDialogue", "", "表示"], False, False)])])
        with self.assertRaisesRegex(FormatError, "unclassified"):
            u.export_book(u.read_book(raw))

    def test_unsupported_entity_version_tail_cache(self):
        raw = book_bytes()
        bad_version = bytearray(raw)
        struct.pack_into("<i", bad_version, len(base()), 1)
        bad_cache = bytearray(raw)
        struct.pack_into("<i", bad_cache, len(raw) - 16, 999)
        for bad in (bytes(bad_version), raw + b"tail", raw[:-8] + i(1) + i(0), bytes(bad_cache)):
            with self.assertRaises(FormatError):
                u.read_book(bad)

    def test_duplicate_header(self):
        raw = book_bytes([grid_bytes(custom=[(["Command", "Arg1", "Text", "Text"], False, False)])])
        with self.assertRaises(FormatError):
            u.export_book(u.read_book(raw))

    def test_control_only_original_row_roundtrips(self):
        raw = book_bytes([grid_bytes(custom=[(["Command", "Arg1", "Text"], False, False),
                                            (["", "", " \n　"], False, False)])])
        rows = u.export_book(u.read_book(raw))[0]["rows"]
        self.assertEqual(u.patch_book(raw, {0: rows}), raw)

    def test_chapter_is_readonly_context(self):
        raw = chapter_bytes()
        chapter = u.read_chapter(raw)
        self.assertEqual(u.character_names([chapter]), {"actor_key": "役名"})
        other = copy.deepcopy(chapter)
        other.settings[0].rows[1].strings[1] = "conflict"
        with self.assertRaises(FormatError):
            u.character_names([chapter, other])
        stale = bytearray(raw)
        struct.pack_into("<i", stale, len(raw) - 8, 0)
        self.assertEqual(u.character_names([u.read_chapter(bytes(stale))]), {"actor_key": "役名"})


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "backup.assets"
        self.source.write_bytes(asset())
        self.work = self.root / "extract"

    def extract(self):
        return workflow.extract(self.source, self.work, target="Game_Data/sharedassets0.assets")

    def test_extract_pack_and_readback(self):
        report = self.extract()
        self.assertEqual((report["book_count"], report["rows"]), (1, 2))
        self.assertEqual((self.work / "rebuilt/roundtrip/Game_Data/sharedassets0.assets").read_bytes(), self.source.read_bytes())
        rows = json.loads((self.work / "gt_input/opening.json").read_text(encoding="utf-8"))
        rows[0]["message"] = "中文<param=x>\n不同长度的第二行。"
        (self.work / "gt_output/opening.json").write_bytes(workflow.json_bytes(rows))
        result = workflow.pack(self.work, self.root / "pack")
        self.assertEqual(result["changed_objects"], [10])
        self.assertEqual(json.loads((self.root / "pack/readback/gt_input/opening.json").read_bytes()), rows)
        raw = (self.root / "pack/files/Game_Data/sharedassets0.assets").read_bytes()
        self.assertNotEqual(raw, self.source.read_bytes())
        index = a.read_index(io.BytesIO(raw))
        chapter = next(o for o in index.objects if o.path_id == 20)
        self.assertEqual(raw[chapter.offset:chapter.offset + chapter.size], chapter_bytes())

    def test_missing_translations_roundtrip_and_unknown_files(self):
        self.extract()
        (self.work / "gt_output/unknown.json").write_text("[]")
        result = workflow.pack(self.work, self.root / "pack")
        self.assertEqual(result["unmatched_translation_files"], ["unknown.json"])
        self.assertEqual(result["changed_objects"], [])
        self.assertEqual((self.root / "pack/files/Game_Data/sharedassets0.assets").read_bytes(), self.source.read_bytes())

    def test_stale_input_manifest_and_source_rejected(self):
        self.extract()
        for relative in ("gt_input/opening.json", "metadata/opening.json", "original/backup.assets"):
            path = self.work / relative
            before = path.read_bytes()
            path.write_bytes(b"[]" if relative.endswith("json") else before + b"x")
            with self.subTest(relative=relative), self.assertRaises(FormatError):
                workflow.pack(self.work, self.root / "pack")
            self.assertFalse((self.root / "pack").exists())
            path.write_bytes(before)

    def test_no_overwrite_and_unsafe_target(self):
        self.extract()
        with self.assertRaises(FileExistsError):
            self.extract()
        with self.assertRaises(FormatError):
            workflow.extract(self.source, self.root / "bad", target="../overwrite.assets")
        with self.assertRaises(FormatError):
            workflow.flat("folder/file.assets")

    def test_explicit_external_class_resolution(self):
        self.source.write_bytes(asset([(10, 114, book_bytes(file_id=1))], ["types.assets"]))
        with self.assertRaisesRegex(FormatError, "metadata"):
            workflow.extract(self.source, self.work)
        dep = self.root / "types.assets"
        dep.write_bytes(asset([(900, 115, mono_script("AdvImportBook"))]))
        workflow.extract(self.source, self.work, dependencies=[dep])
        workflow.pack(self.work, self.root / "pack")

    def test_empty_sheet_and_flat_collision(self):
        grids = [grid_bytes("path:opening"), grid_bytes("other:opening", shift=True),
                 grid_bytes("file:empty", custom=[(["Command", "Arg1", "Text"], False, False)])]
        self.source.write_bytes(asset([(900, 115, mono_script("AdvImportBook")), (10, 114, book_bytes(grids))]))
        result = self.extract()
        self.assertEqual(result["grid_count"], 3)
        self.assertEqual(result["json_files"], 2)
        self.assertEqual({p.name for p in (self.work / "gt_input").iterdir()}, {"opening.json", "opening__p10_g1.json"})


if __name__ == "__main__":
    unittest.main()
