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
            work.mkdir()
            report = workflow.extract(game, work, archives=["story.arc"], smoke_test=True)
            self.assertEqual((report["scripts"], report["json_files"], report["empty_scripts"]), (2, 1, 1))
            self.assertFalse((work / "gt_input/empty.json").exists())
            rows = json.loads((work / "gt_input/intro.json").read_text(encoding="utf-8"))
            rows[0]["message"] += " 新句子"
            (work / "gt_output/intro.json").write_text(json.dumps(rows), encoding="utf-8")
            packed.mkdir()
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

    def test_all_translation_errors_listed_with_json_name_and_tokens(self):
        s = rpyc.parse(sample())
        original, m = rpyc.export(s, names={"e": "Alice"})
        rows = [dict(r) for r in original]
        rows[0]["message"] = "Hello world"
        rows[1]["message"] = ""
        rows[4]["message"] = "UI [unfinished"
        with self.assertRaises(rpyc.TranslationErrors) as caught:
            rpyc.patch(s, rows, m, names={"e": "Alice"}, label="intro.json")
        errors = caught.exception.errors
        self.assertEqual(len(errors), 3)
        self.assertEqual(errors[0], "intro.json #0: changed controls (expected tokens "
                                    "['[player]', '{b}', '{/b}'], actual [])")
        self.assertEqual(errors[1], "intro.json #1: empty text")
        self.assertTrue(errors[2].startswith("intro.json #4: unterminated"))
        rows = [dict(r) for r in original]
        del rows[0]["name"]
        with self.assertRaisesRegex(rpyc.TranslationErrors, r"intro\.json #0: fields"):
            rpyc.patch(s, rows, m, names={"e": "Alice"}, label="intro.json")

    def test_pack_lists_errors_from_every_file_and_cli_is_readable(self):
        import subprocess, sys
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); game = root / "game"; game.mkdir()
            (game / "story.arc").write_bytes(archive({"a.rpyc": sample(), "b.rpyc": sample("Plain {i}text{/i}")}))
            work = root / "work"
            workflow.extract(game, work, archives=["story.arc"])
            for name in ("a.json", "b.json"):
                rows = json.loads((work / "gt_input" / name).read_text(encoding="utf-8"))
                rows[0]["message"] = "no controls"
                (work / "gt_output" / name).write_text(json.dumps(rows), encoding="utf-8")
            with self.assertRaises(rpyc.TranslationErrors) as caught:
                workflow.pack(work, root / "packed")
            self.assertEqual([e.split(":")[0] for e in caught.exception.errors], ["a.json #0", "b.json #0"])
            self.assertFalse((root / "packed").exists())
            repo = Path(__file__).resolve().parents[1]
            done = subprocess.run([sys.executable, "-X", "utf8", "-m", "python.engines.renpy_extract", "pack",
                                   str(work), str(root / "packed")], cwd=repo, capture_output=True, text=True,
                                  encoding="utf-8")
            self.assertEqual(done.returncode, 1)
            self.assertNotIn("Traceback", done.stderr)
            self.assertIn("a.json #0: changed controls", done.stderr)
            self.assertIn("b.json #0: changed controls", done.stderr)

    def test_unresolved_speaker_warning_counts_and_context_archive(self):
        def define(var, source, line):
            pycode = Raw(b"crenpy.ast\nPyCode\n)\x81" + encode((1, source, ("file", line), "eval")) + b"b")
            return node("Define", line, varname=var, code=pycode, store="store", operator="=")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); game = root / "game"; game.mkdir()
            (game / "story.arc").write_bytes(archive({"story.rpyc": sample()}))
            (game / "defs.arc").write_bytes(archive({"defs.rpyc": envelope(program([define("e", 'Character("Alice")', 1)]))}))
            report = workflow.extract(game, root / "alone", archives=["story.arc"])
            self.assertEqual((report["unresolved_speaker_rows"], report["unresolved_speakers"]), (1, {"e": 1}))
            self.assertIn("Character", report["warnings"][0])
            report = workflow.extract(game, root / "both", archives=["story.arc", "defs.arc"])
            self.assertEqual(report["unresolved_speaker_rows"], 0)
            self.assertNotIn("warnings", report)
            rows = json.loads((root / "both/gt_input/story.json").read_text(encoding="utf-8"))
            self.assertEqual(rows[0]["name"], "Alice")

    def test_path_traversal_rejected_and_archived_source_is_only_noted(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / "story.arc").write_bytes(archive({"../intro.rpyc": sample()}))
            with self.assertRaises(ValueError):
                workflow.load_archives(root, ["story.arc"])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); game = root / "game"; game.mkdir()
            (game / "story.arc").write_bytes(archive({"intro.rpyc": sample(), "intro.rpy": b"source"}))
            report = workflow.extract(game, root / "work", archives=["story.arc"])
            self.assertEqual(report["loader_notes"][0]["name"], "intro.rpy")
            self.assertIn("never loaded", report["loader_notes"][0]["note"])



def translate_sample(extra_say=False, caption="Pick this", with_identifier=True):
    """Ren'Py 8 style: slot 1 plain Say, slot 2 Translate/TranslateSay with identifiers."""
    def nodes(transformed):
        say = dict(who="e", what="Hello  [player]", attributes=("happy",), with_="dissolve", interact=True,
                   arguments=None, temporary_attributes=None)
        voice = obj("UserStatement", dict(line="voice 'v/1'", translatable=True, filename="game/story.rpy",
                                          linenumber=19, name=("story", 123, 19), next=None))
        narr = node("Say", 20, who=None, what='Quote "x" BACKSLASH end'.replace("BACKSLASH", chr(92)),
                    attributes=None, with_=None, interact=False, arguments=None, temporary_attributes=None)
        literal = dict(who="'Stranger'", what="Hi", attributes=None, with_=None, interact=True,
                       arguments=None, temporary_attributes=None)
        out = []
        if transformed and with_identifier:
            out += [node("TranslateSay", 10, identifier="start_1a2b3c4d", language=None, alternate=None, **say),
                    node("Translate", 19, identifier="start.local_5e6f", language=None, alternate=None,
                         block=[voice, narr]),
                    node("TranslateSay", 25, identifier="start_9999aaaa", language=None, alternate=None, **literal)]
        else:
            out += [node("Say", 10, **say), voice, narr, node("Say", 25, **literal)]
        out.append(node("Menu", 30, items=[(caption, "True", []), ("", "True", [])]))
        if extra_say:
            out.append(node("Say", 40, who=None, what="unwrapped", attributes=None, with_=None, interact=True,
                            arguments=None, temporary_attributes=None))
        return out
    return envelope(program(nodes(False)), program(nodes(True)))


def game_dir(root, members=None, loose=None):
    game = root / "game"
    game.mkdir()
    if members is not None:
        (game / "story.arc").write_bytes(archive(members))
    for name, data in (loose or {}).items():
        path = game.joinpath(*name.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return game


def write_rows(path, rows):
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")


class LooseSourceTests(unittest.TestCase):
    def test_loose_overrides_archive_and_packs_loose_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game = game_dir(root, {"chapters/intro.rpyc": sample("Archived {b}x{/b}"), "other.rpyc": sample("Other")},
                            {"chapters/intro.rpyc": sample("Loose {b}x{/b}"), "cache/skip.rpyc": b"junk"})
            with self.assertRaisesRegex(ValueError, "add --loose"):
                workflow.extract(game, root / "w0", archives=["story.arc"])
            report = workflow.extract(game, root / "work", archives=["story.arc"], loose=True, smoke_test=True)
            self.assertEqual(report["overrides"],
                             [{"name": "chapters/intro.rpyc", "effective": "loose", "shadowed": "story.arc"}])
            self.assertEqual([f["name"] for f in report["loose"]["files"]], ["chapters/intro.rpyc"])
            rows = json.loads((root / "work/gt_input/intro.json").read_text(encoding="utf-8"))
            self.assertEqual(rows[0]["message"], "Loose {b}x{/b}")
            self.assertTrue((root / "work/rebuilt/growth-test/game/chapters/intro.rpyc").exists())
            rows[0]["message"] = "松散来源的更长中文 {b}x{/b}"
            write_rows(root / "work/gt_output/intro.json", rows)
            result = workflow.pack(root / "work", root / "packed")
            self.assertEqual(result["archives"], [])
            self.assertFalse((root / "packed/changed-archives").exists())
            data = (root / "packed/loose/game/chapters/intro.rpyc").read_bytes()
            self.assertEqual(rpyc.export(rpyc.parse(data))[0][0]["message"], rows[0]["message"])

    def test_loose_only_without_archives(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game = game_dir(root, None, {"script.rpyc": sample()})
            report = workflow.extract(game, root / "work", loose=True)
            self.assertEqual((report["scripts"], report["archives"]), (1, []))
            with self.assertRaises(ValueError):
                workflow.extract(game, root / "w2")

    def test_rpy_digest_rules(self):
        import hashlib
        source = b"label start:\n    'x'\n"
        compiled = sample()[:-16] + hashlib.md5(source).digest()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game = game_dir(root, None, {"script.rpyc": compiled, "script.rpy": source})
            report = workflow.extract(game, root / "ok", loose=True)
            self.assertIn("MD5 equals", report["loader_notes"][0]["note"])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game = game_dir(root, None, {"script.rpyc": sample(), "script.rpy": source})
            with self.assertRaisesRegex(ValueError, "--rpy"):
                workflow.extract(game, root / "bad", loose=True)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game = game_dir(root, {"script.rpyc": sample()}, {"script.rpy": source})
            with self.assertRaisesRegex(ValueError, "both load"):
                workflow.extract(game, root / "bad", archives=["story.arc"])

    def test_project_root_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "renpy").mkdir()
            (root / "game").mkdir()
            with self.assertRaisesRegex(ValueError, "game/ directory"):
                workflow.discover_loose(root)


class NewLanguageTests(unittest.TestCase):
    def test_duplicate_identifier_and_existing_language_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game = game_dir(root, {"story.rpyc": translate_sample(), "side.rpyc": translate_sample()})
            with self.assertRaisesRegex(ValueError, "duplicate translation identifier"):
                workflow.extract(game, root / "dup", archives=["story.arc"], tl_language="schinese")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game = game_dir(root, {"story.rpyc": translate_sample(), "tl/english/x.rpyc": envelope(program([]))})
            with self.assertRaisesRegex(ValueError, "already exists"):
                workflow.extract(game, root / "w", archives=["story.arc"], tl_language="english")

    def test_tl_generation_readback_and_pack(self):
        from python.engines import renpy_tl as tl
        bs = chr(92)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game = game_dir(root, {"story.rpyc": translate_sample()})
            report = workflow.extract(game, root / "work", archives=["story.arc"], tl_language="schinese",
                                      smoke_test=True)
            self.assertEqual(report["mode"], "tl-new")
            self.assertTrue((root / "work/rebuilt/growth-test/game/tl/schinese/story.rpy").exists())
            rows = json.loads((root / "work/gt_input/story.json").read_text(encoding="utf-8"))
            self.assertEqual(rows, [{"message": "Hello  [player]"}, {"message": 'Quote "x" ' + bs + " end"},
                                    {"name": "Stranger", "message": "Hi"}, {"message": "Pick this"}])
            rows[0]["message"] = "你好  [player]，这是一段明显更长的中文句子"
            rows[1]["message"] = '引号 "x" ' + bs + " 结束"
            rows[3]["message"] = "选这个"
            write_rows(root / "work/gt_output/story.json", rows)
            result = workflow.pack(root / "work", root / "packed", font="fonts/cjk.ttf")
            self.assertEqual(result["written"][0]["identifiers"], 3)
            raw = (root / "packed/new-language/game/tl/schinese/story.rpy").read_bytes()
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
            text = raw.decode("utf-8")
            self.assertIn("translate schinese start_local_5e6f:", text)
            self.assertIn('    e happy "你好 ' + bs + ' [player]，这是一段明显更长的中文句子" with dissolve', text)
            self.assertIn("    voice 'v/1'", text)
            self.assertIn("    'Stranger' \"Hi\"", text)
            self.assertIn(' nointeract', text)
            parsed = tl.parse(text)
            self.assertEqual([b.get("identifier") for b in parsed],
                             ["start_1a2b3c4d", "start_local_5e6f", "start_9999aaaa", None])
            self.assertEqual(parsed[0]["items"][0]["what"], rows[0]["message"])
            self.assertEqual(parsed[1]["items"][1]["what"], rows[1]["message"])
            self.assertFalse(parsed[1]["items"][1]["interact"])
            self.assertEqual(parsed[3]["pairs"], [("Pick this", "选这个")])
            font = (root / "packed/new-language/game/tl/schinese/gt_font.rpy").read_text(encoding="utf-8")
            self.assertIn('gui.text_font = "fonts/cjk.ttf"', font)
            with self.assertRaises(ValueError):
                workflow.pack(root / "work", root / "badfont", font='x".ttf')
            rows[0]["message"] = "缺少控制码"
            write_rows(root / "work/gt_output/story.json", rows)
            with self.assertRaisesRegex(rpyc.TranslationErrors, r"story\.json #0: changed controls"):
                workflow.pack(root / "work", root / "bad")
            self.assertFalse((root / "bad").exists())

    def test_shared_menu_caption_exported_once(self):
        from python.engines import renpy_tl as tl
        script = rpyc.parse(translate_sample())
        seen = set()
        first = tl.rows(tl.plan(script, filename="a.rpyc"), {}, seen)[0]
        second = tl.rows(tl.plan(script, filename="b.rpyc"), {}, seen)[0]
        self.assertEqual(len(first) - len(second), 1)

    def test_missing_identifier_refused(self):
        from python.engines import renpy_tl as tl
        for raw in (translate_sample(extra_say=True), translate_sample(with_identifier=False),
                    envelope(program([node("Say", 1, who=None, what="only slot one")]))):
            with self.subTest(), self.assertRaises(tl.MissingIdentifier):
                tl.plan(rpyc.parse(raw), filename="x.rpyc")


class SourceWorkspaceTests(unittest.TestCase):
    SCRIPT = ('define e = Character("艾琳", color="#fff",\r\n    who_bold=True)\r\n'
              'label start:\r\n'
              '    e happy "Hello  there" with dissolve\r\n'
              '    "Narration {b}bold{/b}"\r\n'
              '    mystery "Unknown speaker"\r\n'
              '    menu:\r\n'
              '        "Choice A" if flag:\r\n'
              '            pass\r\n'
              'translate english strings:\r\n'
              '    old "Start"\r\n'
              '    new "Begin' + chr(92) + 'tnow"\r\n')

    def test_rpy_workspace_roundtrip(self):
        from python.engines import renpy_source
        bs = chr(92)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game = game_dir(root, None, {"script.rpy": b"\xef\xbb\xbf" + self.SCRIPT.encode("utf-8")})
            report = renpy_source.extract(game, root / "work")
            self.assertIn("mystery", report["warnings"][0])
            rows = json.loads((root / "work/gt_input/script.json").read_text(encoding="utf-8"))
            self.assertEqual(rows, [{"name": "艾琳", "message": "Hello there"}, {"message": "Narration {b}bold{/b}"},
                                    {"message": "Choice A"}, {"message": "Begin\tnow"}])
            report2 = renpy_source.extract(game, root / "work2", speakers=["mystery"])
            self.assertNotIn("warnings", report2)
            rows[0]["message"] = '你好  “引号” "直引号" ' + bs + " 反斜线"
            rows[1]["message"] = "旁白 {b}粗体{/b}"
            rows[3]["message"] = "开始\t吧"
            write_rows(root / "work/gt_output/script.json", rows)
            result = workflow.pack(root / "work", root / "packed")
            self.assertEqual(result["changed"][0]["changed_rows"], 3)
            data = (root / "packed/loose/game/script.rpy").read_bytes()
            self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
            self.assertEqual(renpy_source.export_rows_only("script.rpy", data, report["speakers"], {"e": "艾琳"}), rows)
            self.assertEqual(data.count(b"\r\n"), self.SCRIPT.count("\r\n"))
            rows[1]["message"] = "缺控制码"
            write_rows(root / "work/gt_output/script.json", rows)
            with self.assertRaisesRegex(rpyc.TranslationErrors, r"script\.json #1"):
                workflow.pack(root / "work", root / "bad")

    def test_cli_rpy_flag_conflicts(self):
        import subprocess, sys
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            done = subprocess.run([sys.executable, "-X", "utf8", "-m", "python.engines.renpy_extract", "extract",
                                   temp, str(Path(temp) / "o"), "--rpy", "--loose"], cwd=repo,
                                  capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(done.returncode, 1)
            self.assertIn("cannot be combined", done.stderr)

if __name__ == "__main__":
    unittest.main()
