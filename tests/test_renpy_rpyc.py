"""Synthetic Ren'Py fixtures only; never load game/runtime objects."""
import io
import json
from pathlib import Path
import pickle
import struct
import tempfile
import unittest
from unittest.mock import patch as mock_patch
import zlib

from python.archives import rpa
from python.engines import renpy_pickle as symbolic
from python.engines import renpy_rpyc as rpyc
from python.engines import renpy_extract as workflow


class Raw(bytes):
    pass


def encode(value):
    if isinstance(value, Raw):
        return value
    if value is None:
        return b"N"
    if type(value) is bool:
        return b"\x88" if value else b"\x89"
    if type(value) is int:
        return b"J" + struct.pack("<i", value)
    if isinstance(value, str):
        raw = value.encode("utf-8")
        return b"X" + struct.pack("<I", len(raw)) + raw
    if isinstance(value, dict):
        return b"}(" + b"".join(encode(k) + encode(v) for k, v in value.items()) + b"u"
    if isinstance(value, list):
        return b"](" + b"".join(encode(v) for v in value) + b"e"
    if isinstance(value, tuple):
        return b"(" + b"".join(encode(v) for v in value) + b"t"
    raise TypeError(type(value))


def obj(name, state, module="renpy.ast"):
    return Raw(b"c" + module.encode() + b"\n" + name.encode() + b"\n)\x81" + encode((None, state)) + b"b")


def node(name, line, **attrs):
    return obj(name, dict(attrs, filename="game/story.rpy", linenumber=line, name=("story", 123, line), next=None))


def program(nodes, *, framed=True):
    body = encode(({"version": 5003000, "key": "unlocked"}, nodes)) + b"."
    return b"\x80\x05" + (b"\x95" + struct.pack("<Q", len(body)) if framed else b"") + body


def envelope(first, second=None):
    slots = [first] if second is None else [first, second]
    offset = 10 + (len(slots) + 1) * 12
    table, body = bytearray(), bytearray()
    for i, p in enumerate(slots, 1):
        data = zlib.compress(p)
        table.extend(struct.pack("<III", i, offset + len(body), len(data)))
        body.extend(data)
    return rpyc.MAGIC + table + bytes(12) + body + b"SOURCE-MD5-HASH!"


def sample(message="Hello [player] {b}world{/b}"):
    def nodes(transformed):
        return [node("TranslateSay" if transformed else "Say", 10, who="e", what=message),
                node("Menu", 20, items=[("Pick this", "flag == 1", [node("Say", 21, who=None, what="Branch")]), ("Other", "True", [])]),
                node("TranslateString", 30, language="english", old="Lookup key", new="Translated UI"),
                node("Python", 40, code="print('do not touch')")]
    return envelope(program(nodes(False)), program(nodes(True)))


def archive(members, magic=b"ARC-3.0", prefix=True, protocol=5):
    out, index = bytearray(bytes(34) + b"Made with engine.\n"), {}
    for name, payload in members.items():
        head = payload[:3] if prefix else b""
        index[name] = [(len(out) ^ 0x42424242, len(payload) ^ 0x42424242, head)]
        out.extend(payload[len(head):])
        out.extend(b"gap")
    out[:34] = magic + f" {len(out):016x} 42424242\n".encode()
    out.extend(zlib.compress(pickle.dumps(index, protocol=protocol)))
    return bytes(out)


class SymbolicTests(unittest.TestCase):
    def test_inert_reduce_and_build_never_execute(self):
        payload = b"\x80\x05cos\nsystem\n" + encode(("MUST NOT RUN",)) + b"R."
        with mock_patch("os.system", side_effect=AssertionError("executed")):
            p = symbolic.parse(payload)
            self.assertEqual(symbolic.class_name(p.root.value), ("os", "system"))
            self.assertEqual(symbolic.rewrite(p, {}), payload)

    def test_shared_memo_text_does_not_modify_other_use(self):
        text = Raw(encode("shared") + b"q\x63")
        nodes = [node("Say", 1, who=None, what=text), node("Python", 2, code=Raw(b"h\x63"))]
        raw = envelope(program(nodes))
        s = rpyc.parse(raw)
        rows, m = rpyc.export(s)
        rows[0]["message"] = "很长的中文替换"
        new = rpyc.patch(s, rows, m)
        p = rpyc.parse(new).slots[1]
        py = next(v for v in p.objects if symbolic.class_name(v) == ("renpy.ast", "Python"))
        self.assertEqual(symbolic.scalar(symbolic.attributes(py)["code"]), "shared")

    def test_edit_memo_get_only(self):
        raw = b"\x80\x05]" + encode("same") + b"q\x01ah\x01a."
        p = symbolic.parse(raw)
        second = p.root.value.data[1]
        changed = symbolic.parse(symbolic.rewrite(p, {second.site: "new"}))
        self.assertEqual([symbolic.scalar(v) for v in changed.root.value.data], ["same", "new"])

    def test_subclass_payloads_and_cycles(self):
        raw = b"\x80\x05crenpy.revertable\nRevertableList\n)\x81q\x01h\x01a."
        p = symbolic.parse(raw)
        self.assertEqual(symbolic.rewrite(p, {}), raw)
        self.assertEqual(symbolic.graph_digest(p), symbolic.graph_digest(symbolic.parse(raw)))
        raw = b"\x80\x05ccollections\ndefaultdict\n)R" + encode("key") + encode("value") + b"s."
        p = symbolic.parse(raw)
        self.assertEqual(symbolic.scalar(p.root.value.data["items"].value.data["key"]), "value")

    def test_malformed_frames_and_unsafe_extensions_rejected(self):
        for raw in (b"\x80\x05Pexternal\n.", b"\x80\x05\x82\x01.", b"\x80\x05h\x7f.",
                    b"\x80\x05\x95" + struct.pack("<Q", 100) + b"N.",
                    b"\x80\x05\x95" + struct.pack("<Q", 1) + encode("crosses") + b".",
                    b"\x80\x05N.junk"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                symbolic.parse(raw)

    def test_budgets(self):
        raw = program([])
        for limits in ({"max_bytes": 4}, {"max_ops": 3}, {"max_stack": 1}):
            with self.assertRaises(ValueError):
                symbolic.parse(raw, **limits)


class RPYCTextTests(unittest.TestCase):
    def test_identity_and_both_slot_growth_nontext_preserved(self):
        raw = sample()
        s = rpyc.parse(raw)
        rows, m = rpyc.export(s, names={"e": "Alice"})
        self.assertEqual([r["message"] for r in rows], ["Hello [player] {b}world{/b}", "Pick this", "Other", "Branch", "Translated UI"])
        self.assertEqual(list(rows[0]), ["name", "message"])
        self.assertEqual(rpyc.patch(s, rows, m, names={"e": "Alice"}), raw)
        for row in rows:
            row["message"] += " 中文增长测试"
        new = rpyc.patch(s, rows, m, names={"e": "Alice"})
        self.assertEqual(new[-16:], raw[-16:])
        checked = rpyc.parse(new)
        for p in checked.slots.values():
            tr = next(v for v in p.objects if symbolic.class_name(v) == ("renpy.ast", "TranslateString"))
            self.assertEqual(symbolic.scalar(symbolic.attributes(tr)["old"]), "Lookup key")

    def test_unknown_nontext_fields_preserved(self):
        payload = node("Say", 1, who=None, what="text", future_field={"id": 99, "flags": [True, None]})
        s = rpyc.parse(envelope(program([payload])))
        rows, m = rpyc.export(s)
        rows[0]["message"] = "新文本"
        rpyc.patch(s, rows, m)

    def test_slot_disagreement_rejected(self):
        s = rpyc.parse(envelope(program([node("Say", 1, who=None, what="one")]), program([node("Say", 1, who=None, what="two")])))
        with self.assertRaisesRegex(ValueError, "differ"):
            rpyc.export(s)

    def test_controls_context_count_and_manifest(self):
        s = rpyc.parse(sample())
        original, m = rpyc.export(s, names={"e": "Alice"})
        for change in ("Hello [intruder] {b}world{/b}", "Hello [player] world", "Hello [player] {b}world{/b} {image=extra}"):
            rows = [dict(r) for r in original]; rows[0]["message"] = change
            with self.assertRaises(ValueError):
                rpyc.patch(s, rows, m, names={"e": "Alice"})
        rows = [dict(r) for r in original]; rows[0]["name"] = "Bob"
        with self.assertRaises(ValueError):
            rpyc.patch(s, rows, m, names={"e": "Alice"})
        with self.assertRaises(ValueError):
            rpyc.patch(s, original[:-1], m, names={"e": "Alice"})
        m["records"][0]["locator"]["line"] += 1
        with self.assertRaises(ValueError):
            rpyc.patch(s, original, m, names={"e": "Alice"})

    def test_control_scanner_quotes_nesting_and_escapes(self):
        self.assertEqual(rpyc.controls("字 [[ {{ [items['x]'][0]!t] {b}文{/b}"), ["[[", "{{", "[items['x]'][0]!t]", "{b}", "{/b}"])
        for value in ("[unfinished", "{b", "[x['q]"):
            with self.assertRaises(ValueError):
                rpyc.controls(value)

    def test_printf_tokens_and_character_resolution(self):
        self.assertEqual(rpyc.controls("%(filename)s %02d %%"), ["%(filename)s", "%02d", "%%"])
        def define(var, source, line):
            pycode = Raw(b"crenpy.ast\nPyCode\n)\x81" + encode((1, source, ("file", line), "eval")) + b"b")
            return node("Define", line, varname=var, code=pycode, store="store", operator="=")
        p = symbolic.parse(program([define("e", 'Character(_("Alice"), color="#fff")', 1),
                                    define("dynamic", 'Character(player_name)', 2),
                                    define("conflict", 'Character("A")', 3),
                                    define("conflict", 'Character("B")', 4)]))
        self.assertEqual(rpyc.character_names(p), {"e": "Alice"})

    def test_bad_envelope(self):
        raw = sample()
        overlap = bytearray(raw); struct.pack_into("<I", overlap, 14, 10)
        duplicate = bytearray(raw); struct.pack_into("<I", duplicate, 22, 1)
        for data in (raw[:-1], b"not rpyc", bytes(overlap), bytes(duplicate), raw + b"tail"):
            with self.assertRaises(ValueError):
                rpyc.parse(data)


class RPAAndWorkspaceTests(unittest.TestCase):
    def test_protocols_magic_prefix_growth_and_identity(self):
        for protocol in (3, 4, 5):
            for magic in (b"RPA-3.0", b"ARC-3.0"):
                raw = archive({"one.rpyc": sample(), "media.bin": b"preserve"}, magic, protocol=protocol)
                self.assertEqual(rpa.rebuild(raw, {}), raw)
                for replacement in (b"x", b"new content much larger" * 30):
                    new = rpa.rebuild(raw, {"one.rpyc": replacement})
                    self.assertEqual({e.name: e.data for e in rpa.extract(new)}, {"one.rpyc": replacement, "media.bin": b"preserve"})
                    self.assertEqual(new[:7], magic)

    def test_index_only_does_not_read_payload(self):
        raw = archive({"media": b"x" * 10000})
        index_at = int(raw[8:24], 16)
        class Tracking(io.BytesIO):
            def read(self, size=-1):
                pos = self.tell()
                self_test.assertTrue(pos == 0 and size == 34 or pos >= index_at)
                return super().read(size)
        self_test = self
        self.assertEqual(rpa.read_index(Tracking(raw)).entries[0].length, 10000)

    def test_workspace_and_partial_translation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); game = root / "game"; game.mkdir()
            original = archive({"chapters/intro.rpyc": sample(), "empty.rpyc": envelope(program([])), "media": b"same"})
            (game / "story.arc").write_bytes(original)
            work, packed = root / "work", root / "packed"
            report = workflow.extract(game, work, archives=["story.arc"], smoke_test=True)
            self.assertEqual((report["scripts"], report["json_files"], report["empty_scripts"]), (2, 1, 1))
            self.assertFalse((work / "gt_input/empty.json").exists())
            rows = json.loads((work / "gt_input/intro.json").read_text(encoding="utf-8"))
            rows[0]["message"] += " 新句子"
            (work / "gt_output/intro.json").write_text(json.dumps(rows), encoding="utf-8")
            result = workflow.pack(work, packed)
            self.assertEqual(result["changed"][0]["changed_rows"], 1)
            rebuilt = (packed / "changed-archives/game/story.arc").read_bytes()
            members = {e.name: e.data for e in rpa.extract(rebuilt)}
            self.assertEqual(members["media"], b"same")
            self.assertEqual(rpyc.export(rpyc.parse(members["chapters/intro.rpyc"]))[0], rows)
            self.assertEqual((game / "story.arc").read_bytes(), original)
            with self.assertRaises(FileExistsError):
                workflow.pack(work, packed)
            (work / "gt_input/intro.json").write_text(json.dumps(rows), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "gt_input changed"):
                workflow.pack(work, root / "bad")

    def test_source_override_and_path_traversal_rejected(self):
        for members in ({"../intro.rpyc": sample()}, {"intro.rpyc": sample(), "intro.rpy": b"source"}):
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp); (root / "story.arc").write_bytes(archive(members))
                with self.assertRaises(ValueError):
                    workflow.load_archives(root, ["story.arc"])


if __name__ == "__main__":
    unittest.main()
