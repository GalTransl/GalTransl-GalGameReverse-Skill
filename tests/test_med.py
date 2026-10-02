import io
from pathlib import Path
import struct
import tempfile
import unittest

from python.archives import med as archive
from python.common.binary import FormatError
from python.common.contract import dump_rows, load_json
from python.common.jis_workflow import prepare_translations
from python.engines import med_extract as workflow
from python.engines import med_script as med


def frame(op, args=b"", line=1):
    return struct.pack("<HBB", line, len(args) + 1, op) + args


def ref(op, idx):
    return frame(op, struct.pack("<H", idx))


def script(code, strings=(), targets=(), labels=()):
    code += b"\0"
    tail = struct.pack(f"<{len(targets)}H", *targets)
    tail += b"".join(s.encode("cp932") + b"\0" for s in (*strings, *labels))
    return struct.pack("<IIHHI", len(code) + len(tail), len(code), len(strings), len(labels), 99) + code + tail


def bundle(items, *, gap=b"", trailer=b"TAIL"):
    width = 28
    header = b"MDN0" + struct.pack("<HH", width, len(items)) + b"OPAQUE!!"
    offset = 16 + width * len(items) + len(gap)
    table, body = bytearray(), bytearray(gap)
    for name, data in items:
        table.extend(name.encode("cp932").ljust(width - 8, b"\0"))
        table.extend(struct.pack("<II", len(data), offset))
        body.extend(data)
        offset += len(data)
    return header + table + body + trailer


def example():
    # One shared name, two physical fragments; resource aliases first message.
    code = ref(0x0d, 0) + ref(0x14, 1) + ref(1, 1) + frame(0)
    code += ref(1, 2) + frame(0) + frame(4)
    code += ref(1, 1) + frame(0) + frame(4)
    code += frame(0x0a, struct.pack("<H", 3) + b"\0\0\xf5\0\0\xff")
    code += ref(0x2c, 4)
    return script(code, ("【案内人】", "最初の文。", "次の文。", "選ぶ", "章\\N一"), (0,), ("LABEL",))


class ScriptTests(unittest.TestCase):
    def test_identity_empty_and_labels(self):
        for data in (example(), script(b""), script(frame(0x1f))):
            rows, metadata = med.export(data)
            self.assertEqual(med.rebuild(data, rows, metadata), data)
        self.assertEqual(med.parse(example()).labels, (b"LABEL",))

    def test_roles_and_name_page_scope(self):
        rows, m = med.export(example())
        self.assertEqual(list(rows[0]), ["name", "message"])
        self.assertEqual(rows[0]["name"], rows[1]["name"])
        self.assertNotIn("name", rows[2])
        self.assertEqual([r["locator"]["kind"] for r in m["records"]],
                         ["message", "message", "message", "choice", "title"])

    def test_growth_shrink_and_resource_alias_isolation(self):
        data = example()
        rows, m = med.export(data)
        rows[0]["message"] = "文" * 70
        rows[1]["message"] = "短"
        rows[2]["message"] = "別の翻訳"
        rows[0]["name"] = rows[1]["name"] = "新しい案内人"
        rows[3]["message"] = "選択項目"
        rows[4]["message"] = "新章\\N二"
        result = med.rebuild(data, rows, m)
        old, new = med.parse(data), med.parse(result)
        self.assertEqual(med.export(result)[0], rows)
        self.assertEqual(new.strings[:len(old.strings)], old.strings)
        self.assertEqual(old.targets, new.targets)
        self.assertEqual(old.labels, new.labels)
        self.assertEqual(old.frames[1], new.frames[1])  # voice points at original
        self.assertEqual(len(new.code), len(old.code))
        self.assertGreater(len(result), len(data))

    def test_shared_name_conflict(self):
        rows, m = med.export(example())
        rows[0]["name"] = "別名"
        with self.assertRaisesRegex(FormatError, "sharing a name"):
            med.rebuild(example(), rows, m)

    def test_sentinels_and_unpaired_definition_literal(self):
        code = ref(0x0d, 0xffff) + ref(1, 0) + frame(0) + frame(4)
        code += frame(0x0a, b"\xff\xff" + b"\0" * 6) + ref(1, 1)
        data = script(code, ("表示文", "DEFINITION"))
        rows, m = med.export(data)
        self.assertEqual(rows, [{"message": "表示文"}])
        self.assertEqual(med.rebuild(data, rows, m), data)

    def test_rule_table_is_not_dialogue_and_is_name_independent(self):
        data = script(ref(2, 0) + ref(1, 1) + frame(0) + frame(4),
                      ("#RULE_DEFINE", "S50手動1\t\tS55"))
        rows, m = med.export(data)
        self.assertEqual(rows, [])
        self.assertEqual(med.summary(data)["rule_literals"], 1)
        self.assertEqual(med.rebuild(data, rows, m), data)
        # ASCII dialogue is still dialogue outside a marked rule table.
        ordinary = script(ref(1, 0) + frame(0), ("Hello!",))
        self.assertEqual(med.export(ordinary)[0], [{"message": "Hello!"}])
        for literal in ("表示される日本語", "A\t"):
            bad = script(ref(2, 0) + ref(1, 1) + frame(0), ("#RULE_DEFINE", literal))
            with self.assertRaisesRegex(FormatError, "rule-table literal"):
                med.export(bad)

    def test_control_changes_and_nuls_refused(self):
        for change in ("失われた改行", "章\\X一", "章\\N一\0", "章\\N一@x"):
            with self.subTest(change=change):
                rows, m = med.export(example())
                rows[-1]["message"] = change
                with self.assertRaises(FormatError):
                    med.rebuild(example(), rows, m)

    def test_malformed_layouts(self):
        base = example()
        bad_length = bytearray(base); bad_length[0] ^= 1
        bad_count = bytearray(base); struct.pack_into("<H", bad_count, 8, 99)
        bad_target = bytearray(base); struct.pack_into("<H", bad_target, 16 + len(med.parse(base).code), 1)
        cases = [bytes(bad_length), bytes(bad_count), bytes(bad_target),
                 script(frame(0xfe)), script(frame(1)), script(b"\0\0\0\x01"),
                 script(ref(1, 9) + frame(0), ("文",)),
                 script(ref(0x0d, 0x8000), ("【名】",))]
        for data in cases:
            with self.subTest(data=data[:16]):
                with self.assertRaises(FormatError):
                    med.export(data)

    def test_manifest_and_fields(self):
        rows, m = med.export(example())
        m["records"][0]["locator"]["frame"] += 1
        with self.assertRaisesRegex(FormatError, "manifest"):
            med.rebuild(example(), rows, m)
        rows.pop()
        with self.assertRaises(FormatError):
            med.rebuild(example(), rows)

    def test_jis_chinese_through_actual_archive_reader(self):
        data = example()
        original, _ = med.export(data)
        translated = [dict(r) for r in original]
        translated[0]["message"] = "这是中文显示测试，验证变长字符串。"
        plan = prepare_translations({"scene.json": original}, {"scene.json": translated},
            encoding="cp932", extra_texts=[s.decode("cp932") for s in med.parse(data).strings], proxy_policy="unused")
        source = bundle([("scene", data), ("empty", script(b""))])
        packed = archive.rebuild(source, {"scene": med.rebuild(data, plan.stored["scene.json"])})
        ent = archive.index(io.BytesIO(packed), len(packed))[0]
        readback, _ = med.export(archive.read_member(io.BytesIO(packed), ent))
        self.assertTrue(plan.verify({"scene.json": readback})["display_rows_verified"])

    def test_signed_string_allocation_limit(self):
        data = script(ref(1, 0) + frame(0), ("文",) * 0x8000)
        rows, _ = med.export(data)
        rows[0]["message"] = "変える"
        with self.assertRaisesRegex(FormatError, "signed 16-bit"):
            med.rebuild(data, rows)


class ArchiveTests(unittest.TestCase):
    def test_gaps_trailer_growth_and_shrink(self):
        raw = bundle([("a", b"1234"), ("b", b"567890")], gap=b"GAP")
        self.assertEqual(archive.rebuild(raw, {}), raw)
        result = archive.rebuild(raw, {"a": b"A" * 20, "b": b"B"})
        es = archive.index(io.BytesIO(result), len(result))
        self.assertEqual(archive.read_member(io.BytesIO(result), es[1]), b"B")
        self.assertEqual(es[1].offset - es[0].offset, 20)
        self.assertEqual(result[72:75], b"GAP")
        self.assertTrue(result.endswith(b"TAIL"))

    def test_invalid_index_names_overlap_and_budget(self):
        valid = bundle([("a", b"one"), ("b", b"two")])
        overlap = bytearray(valid); struct.pack_into("<I", overlap, 16 + 28 + 24, 72)
        giant = bytearray(valid); struct.pack_into("<I", giant, 36, archive.MAX_MEMBER + 1)
        for raw in (valid[:20], b"MDN1" + valid[4:], bytes(overlap), bytes(giant),
                    bundle([("../a", b"1")]), bundle([("a", b"1"), ("A", b"2")])):
            with self.subTest(raw=raw[:8]):
                with self.assertRaises(FormatError):
                    archive.index(io.BytesIO(raw), len(raw))

    def test_unknown_replacement(self):
        with self.assertRaises(FormatError):
            archive.rebuild(bundle([("a", b"1")]), {"z": b"2"})


class WorkflowTests(unittest.TestCase):
    def test_extract_edit_pack_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "md_scr.med"
            src.write_bytes(bundle([("scene", example()), ("empty", script(b""))]))
            work = root / "work"
            report = workflow.extract(src, work)
            self.assertEqual(report["json_files"], 1)
            self.assertEqual((work / "rebuilt/roundtrip/md_scr.med").read_bytes(), src.read_bytes())
            noedit = root / "noedit"
            workflow.pack(work, noedit)
            self.assertEqual((noedit / "md_scr.med").read_bytes(), src.read_bytes())
            rows = load_json((work / "gt_input/scene.json").read_bytes())
            rows[0]["message"] = "長い文章に変更するテスト。"
            (work / "gt_output/scene.json").write_bytes(dump_rows(rows))
            result = workflow.pack(work, root / "changed")
            self.assertEqual(result["changed_members"], ["scene"])
            self.assertEqual(load_json((root / "changed/readback/gt_input/scene.json").read_bytes()), rows)
            with self.assertRaises(FileExistsError):
                workflow.pack(work, root / "changed")
            with self.assertRaises(FileExistsError):
                workflow.extract(src, work)
            (work / "gt_input/scene.json").write_bytes(dump_rows(rows))
            with self.assertRaisesRegex(FormatError, "original JSON"):
                workflow.pack(work, root / "bad")
            self.assertFalse((root / "bad").exists())


if __name__ == "__main__":
    unittest.main()
