"""Synthetic NeXAS fixtures only; no copyrighted game data."""
import copy
import ast
import builtins
import io
import struct
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from python.archives import nexas as pac
from python.common.binary import FormatError
from python.common.contract import dump_rows
from python.engines import nexas_bin as nexas
from python.engines.nexas_extract import default_archives, extract, main, pack, parse_packlist, verify_archive
from tools.check_skill import runtime_dependency_errors


def bin_file(commands, strings, *, extras=(), trailer=b"\x02\0\0\0debug-table\0"):
    return (struct.pack("<I", len(extras)) + b"".join(struct.pack("<II", *p) for p in extras)
            + struct.pack("<I", len(commands)) + b"".join(struct.pack("<II", *p) for p in commands)
            + struct.pack("<I", len(strings))
            + b"".join((s.encode("cp932") if isinstance(s, str) else s) + b"\0" for s in strings)
            + trailer)


def message_bin(text="@v12345678原文@n次の行", *, trailer=b"opaque-tail\0", name="名前"):
    # Also reference the message from an unrelated resource call.
    return bin_file([(0, 1), (5, 1), (0, 2), (5, 1), (7, 0x4006f),
                     (0, 2), (5, 1), (7, 0x501d5)], ["", name, text], trailer=trailer)


def archive(entries, mode=0, marker=0x75):
    data = bytearray(struct.pack("<4sII", b"PAC" + bytes([marker]), len(entries), mode))
    index = bytearray()
    for name, payload in entries:
        encoded = name.encode("cp932")
        field = encoded + bytes(64 - len(encoded))
        index.extend(field + struct.pack("<III", len(data), len(payload), len(payload)))
        data.extend(payload)
    tail = bytes(x ^ 255 for x in pac.huffman_encode(bytes(index)))
    return bytes(data) + tail + struct.pack("<I", len(tail))


class NexasOptionalDependencyTests(unittest.TestCase):
    def test_checker_scopes_optional_import_and_requires_lazy_guard(self):
        code = 'def codec():\n    try:\n        import zstandard\n    except ImportError:\n        raise ValueError("missing codec")\n'
        tree = ast.parse(code)
        self.assertEqual(runtime_dependency_errors(tree, 'python/archives/nexas.py'), [])
        self.assertTrue(runtime_dependency_errors(tree, 'python/archives/another.py'))
        for unsafe in ('import zstandard',
                       'def codec():\n    import zstandard',
                       'try:\n    import zstandard\nexcept ImportError:\n    pass',
                       'def codec():\n    try:\n        pass\n    except ImportError:\n        import zstandard'):
            with self.subTest(code=unsafe):
                self.assertTrue(runtime_dependency_errors(ast.parse(unsafe), 'python/archives/nexas.py'))
        self.assertTrue(runtime_dependency_errors(ast.parse(code.replace('zstandard', 'other_codec')),
                                                  'python/archives/nexas.py'))

    def test_missing_codec_does_not_block_indexes_or_standard_modes(self):
        original_import = builtins.__import__

        def without_zstd(name, *args, **kwargs):
            if name == 'zstandard':
                raise ModuleNotFoundError('synthetic missing optional codec')
            return original_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=without_zstd):
            for mode in (0, 2, 3, 4, 5, 6, 7):
                raw = archive([('a.bin', b'x')], mode=mode)
                index = pac.read_index(io.BytesIO(raw))
                if mode in (6, 7):
                    with self.assertRaisesRegex(FormatError, 'optional zstandard'):
                        pac.rebuild(io.BytesIO(raw), index, {'a.bin': b'new text'})
                    if mode == 6:
                        with self.assertRaisesRegex(FormatError, 'optional zstandard'):
                            pac.read_member(io.BytesIO(raw), index, index.entries[0])
                    else:
                        self.assertEqual(pac.read_member(io.BytesIO(raw), index, index.entries[0]), b'x')
                else:
                    rebuilt = pac.rebuild(io.BytesIO(raw), index, {'a.bin': b'new text'})
                    updated = pac.read_index(io.BytesIO(rebuilt))
                    self.assertEqual(pac.read_member(io.BytesIO(rebuilt), updated, updated.entries[0]), b'new text')


class NexasArchiveTests(unittest.TestCase):
    def test_huffman_golden_and_corruption(self):
        self.assertEqual(pac.huffman_decode(b"\x20\x80", 7), b"A" * 7)
        for data in [b"", b"a", bytes(range(256)) * 3, b"abracadabra" * 10]:
            self.assertEqual(pac.huffman_decode(pac.huffman_encode(data), len(data)), data)
        for data in [b"", b"\xff" * 100, b"\x20\x81", b"\x20\x80\x00"]:
            with self.assertRaises(FormatError):
                pac.huffman_decode(data, 7)
        with self.assertRaises(FormatError):
            pac.huffman_decode(b"\x20\x80", 50, max_output=49)

    def test_pacu_and_raw_preservation(self):
        source = archive([("台本.bin", message_bin()), ("image.png", b"image-data")], marker=0xbf)
        idx = pac.read_index(io.BytesIO(source))
        rebuilt = pac.rebuild(io.BytesIO(source), idx, {"台本.bin": message_bin("長く変更した文です")})
        verification = verify_archive(source, rebuilt, {"台本.bin": message_bin("長く変更した文です")})
        self.assertEqual(verification["untouched_packed_members_verified"], 1)
        self.assertEqual(pac.read_index(io.BytesIO(rebuilt)).marker, 0xbf)

    def test_compression_roundtrip(self):
        for mode in [2, 3, 4, 6, 7]:
            if mode in (6, 7):
                try:
                    pac._zstd()
                except FormatError:
                    continue
            source = archive([("a.bin", b"x")], mode=mode)
            idx = pac.read_index(io.BytesIO(source))
            for payload in [b"abc" * 10000, b"a", b""]:
                built = pac.rebuild(io.BytesIO(source), idx, {"a.bin": payload})
                index = pac.read_index(io.BytesIO(built))
                self.assertEqual(pac.read_member(io.BytesIO(built), index, index.entries[0]), payload)

    def test_reject_paths_ranges_and_truncated_members(self):
        for names in [["../a.bin"], ["a.bin", "A.bin"], ["NUL.bin"]]:
            with self.assertRaises(FormatError):
                pac.read_index(io.BytesIO(archive([(n, b"x") for n in names])))
        source = archive([("a.bin", b"a" * 40)], mode=4)
        index = pac.read_index(io.BytesIO(source))
        packed = pac.rebuild(io.BytesIO(source), index, {"a.bin": b"a" * 10000})
        index = pac.read_index(io.BytesIO(packed))
        bad = bytearray(packed)
        bad[index.entries[0].offset] ^= 255
        with self.assertRaises(FormatError):
            pac.read_member(io.BytesIO(bad), index, index.entries[0])
        with self.assertRaises(FormatError):
            pac.read_index(io.BytesIO(source[:-1]))


class NexasScriptTests(unittest.TestCase):
    def test_original_roundtrip_alias_bytes_and_extra_table(self):
        # CP932 duplicate encodings must not be decoded/re-encoded on a no-op.
        data = bin_file([(0, 1), (5, 1), (0, 2), (5, 1), (7, 0x4006f)],
                        ["", "名", b"\xfa\x40"], extras=[(4, 0), (2, 3)])
        rows, manifest = nexas.export(data, source_name="scene.bin")
        self.assertEqual(nexas.inject(data, rows, manifest, rows, source_name="scene.bin"), data)

    def test_changed_reference_does_not_change_shared_resource(self):
        data = message_bin()
        rows, manifest = nexas.export(data, source_name="scene.bin")
        translated = copy.deepcopy(rows)
        translated[0] = {"name": "長い名前", "message": "@v12345678異なる長さの本文です@n二行目"}
        rewritten = nexas.inject(data, rows, manifest, translated, source_name="scene.bin")
        old, new = nexas.parse(data), nexas.parse(rewritten)
        self.assertEqual(new.raw_strings[:3], old.raw_strings)
        self.assertEqual(new.raw_commands[5], old.raw_commands[5])
        self.assertEqual(new.trailer, old.trailer)
        self.assertEqual(nexas.records(new)[0], translated)
        # A shorter translation may drop @n but must keep the voice tag.
        one_line = copy.deepcopy(rows)
        one_line[0] = {"name": "長い名前", "message": "@v12345678一行にまとめた本文"}
        shortened = nexas.inject(data, rows, manifest, one_line, source_name="scene.bin")
        self.assertEqual(nexas.records(nexas.parse(shortened))[0], one_line)

    def test_custom_special_choice_continuation(self):
        strings = ["", "名前", "@v12345678本文", "@d@m32", "@k", "選択肢", "続き@nです"]
        commands = [(0, 2), (14, 0x80000000), (0, 1), (5, 1), (0, 3), (4, 0),
                    (0, 2), (6, 1), (9, 1), (4, 0), (0, 4), (6, 1), (9, 1), (5, 1),
                    (7, 0x4006f), (0, 6), (5, 1), (7, 0x10071),
                    (0, 0), (5, 0), (0, 5), (5, 1), (0, 1), (5, 0), (7, 0x30066)]
        data = bin_file(commands, strings)
        rows, manifest = nexas.export(data, source_name="a.bin")
        self.assertEqual([r["locator"]["kind"] for r in manifest["records"]],
                         ["special-text", "custom-message", "continuation", "choice"])
        self.assertEqual(rows[1]["name"], "名前")
        self.assertNotIn("name", rows[2])
        self.assertEqual(nexas.inject(data, rows, manifest, rows, source_name="a.bin"), data)
        changed = [{**row, "message": row["message"] + "追記"} for row in rows]
        built = nexas.inject(data, rows, manifest, changed, source_name="a.bin")
        self.assertEqual(nexas.records(nexas.parse(built))[0], changed)

    def test_no_heuristic_japanese_resource_export(self):
        data = bin_file([(0, 1), (5, 1), (7, 0x501d5)], ["", "喫茶店ドアベル"])
        self.assertEqual(nexas.export(data, source_name="a.bin")[0], [])

    def test_reject_invalid_translation_identity_and_structure(self):
        data = message_bin()
        rows, manifest = nexas.export(data, source_name="a.bin")
        for text in ["no controls", "@n@v12345678順序変更", "@v12345678未知@x@n", "@v12345678\0@n", "@v12345678😀@n"]:
            with self.assertRaises((FormatError, UnicodeError)):
                nexas.inject(data, rows, manifest, [{**rows[0], "message": text}], source_name="a.bin")
        altered = copy.deepcopy(manifest)
        altered["records"][0]["locator"]["message_prefix"] = 0
        with self.assertRaises(FormatError):
            nexas.inject(data, rows, altered, rows, source_name="a.bin")
        with self.assertRaises(FormatError):
            nexas.export(bin_file([(0xdead, 1)], [""]), source_name="a.bin")
        with self.assertRaises(FormatError):
            nexas.parse(bin_file([], ["a"], trailer=b"")[:-1])
        with self.assertRaises(FormatError):
            nexas.export(bin_file([(7, 0x4006f)], [""]), source_name="a.bin")


class NexasWorkflowTests(unittest.TestCase):
    def test_overlay_extract_inject_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base = archive([("scene.bin", message_bin("元の文")), ("empty.bin", bin_file([], [""]))])
            patch = archive([("scene.bin", message_bin("更新した文")), ("image.png", b"image")], marker=0xbf)
            (root / "Script.pac").write_bytes(base)
            (root / "Update3.pac").write_bytes(patch)
            out = root / "extract"
            out.mkdir()
            report = extract(root, out, ["Script.pac", "Update3.pac"])
            summary = report["summary"]
            self.assertEqual(report["status"], "complete")
            self.assertEqual(report["profile"], nexas.PROFILE)
            self.assertTrue((out / "reports/translation-state.md").is_file())
            self.assertEqual(summary["exported_files"], 1)
            self.assertEqual(summary["empty_scripts"], 1)
            self.assertEqual(summary["original_bin_roundtrips"], 3)
            self.assertEqual(sorted(p.name for p in (out / "gt_input").iterdir()), ["scene.json"])
            translated = [{"name": "名前", "message": "少し長い翻訳の文"}]
            (out / "gt_output/scene.json").write_bytes(dump_rows(translated))
            (out / 'packed').mkdir()
            result = pack(out, out / "packed")
            self.assertEqual(result["changed_scripts"], 1)
            built = (out / "packed/Update3.pac").read_bytes()
            idx = pac.read_index(io.BytesIO(built))
            changed = pac.read_member(io.BytesIO(built), idx, idx.entries[0])
            self.assertEqual(nexas.records(nexas.parse(changed))[0], translated)
            self.assertEqual((root / "Script.pac").read_bytes(), base)
            self.assertEqual((root / "Update3.pac").read_bytes(), patch)
            with self.assertRaises(FileExistsError):
                pack(out, out / "packed")
            with self.assertRaises(FileExistsError):
                extract(root, out, ["Script.pac", "Update3.pac"])


F69 = nexas.DIALECT_FUNC69


def func69_bin(text="@v12345678本文@n二行目", *, name="名前", extra=()):
    """Earlier FUNC table: message 0x40069, continuation 0x1006A, choice 0x30062."""
    strings = ["", name, text, "続き", "選択肢", "通知文", "@d@m32", "@k"]
    commands = [(0, 1), (5, 1), (0, 2), (5, 1), (7, 0x40069),
                (0, 3), (5, 1), (7, 0x1006A),
                (0, 0), (5, 0), (0, 4), (5, 1), (0, 0), (5, 0), (7, 0x30062),
                (0, 5), (5, 1), (0, 0), (5, 0), (7, 0x2006E),
                # name + (effect + text) + control suffix custom message
                (0, 1), (5, 1), (0, 6), (4, 0), (0, 2), (6, 1), (9, 1), (4, 0),
                (0, 7), (6, 1), (9, 1), (5, 1), (7, 0x40069),
                # operand-less comparison operator, then conditional jump
                (4, 0), (0, 0), (6, 1), (22, 0), (66, 3), *extra]
    return bin_file(commands, strings)


def packlist(names, header=struct.pack("<III", 2, 1, 2)):
    return header + b"".join(n.encode() + b"\0" + struct.pack("<I", g) for n, g in names)


class NexasDialectTests(unittest.TestCase):
    def test_func69_dialect_selected_exported_and_edit_roundtrip(self):
        data = func69_bin()
        scripts = [nexas.parse(data)]
        self.assertIs(nexas.select_dialect(scripts), F69)
        self.assertIs(nexas.select_dialect([nexas.parse(message_bin())]), nexas.DIALECT_EXTRAS)
        # Default dialect sees no message site here; the guard refuses, not exports empty.
        with self.assertRaisesRegex(FormatError, "opcode outside|shaped call"):
            nexas.export(data, source_name="a.bin")
        rows, manifest = nexas.export(data, source_name="a.bin", dialect=F69)
        self.assertEqual([r["locator"]["kind"] for r in manifest["records"]],
                         ["message", "continuation", "choice", "notification", "custom-message"])
        self.assertEqual(manifest["engine"]["variant"], F69.profile)
        self.assertEqual(nexas.inject(data, rows, manifest, rows, source_name="a.bin"), data)
        edited = [dict(r, message=r["message"] + "長" * (i + 1)) for i, r in enumerate(rows)]
        edited[0]["name"] = "ずっと長い名前"
        built = nexas.inject(data, rows, manifest, edited, source_name="a.bin")
        new, old = nexas.parse(built), nexas.parse(data)
        self.assertEqual(nexas.records(new, F69)[0], edited)
        self.assertEqual(new.raw_strings[:len(old.raw_strings)], old.raw_strings)
        self.assertEqual(new.trailer, old.trailer)

    def test_selection_refuses_unknown_or_ambiguous_message_tables(self):
        unknown = bin_file([(0, 1), (5, 1), (0, 2), (5, 1), (7, 0x40077)], ["", "名", "本文"])
        with self.assertRaisesRegex(FormatError, r"FUNC 0x40077 x1"):
            nexas.select_dialect([nexas.parse(unknown)])
        with self.assertRaisesRegex(FormatError, "no single NeXAS FUNC dialect"):
            nexas.select_dialect([nexas.parse(func69_bin()), nexas.parse(message_bin())])
        # A message-shaped call outside the selected table blocks the member.
        mixed = func69_bin(extra=[(0, 1), (5, 1), (0, 2), (5, 1), (7, 0x40077)])
        with self.assertRaisesRegex(FormatError, r"shaped call to FUNC 0x40077"):
            nexas.records(nexas.parse(mixed), F69)

    def test_stack_operator_shape_is_checked(self):
        with self.assertRaisesRegex(FormatError, "operator opcode 22"):
            nexas.records(nexas.parse(func69_bin(extra=[(5, 0), (22, 0)])), F69)
        with self.assertRaisesRegex(FormatError, "operator opcode 63"):
            nexas.records(nexas.parse(func69_bin(extra=[(4, 0), (6, 1), (0, 1), (63, 0)])), F69)
        with self.assertRaisesRegex(FormatError, "operator opcode 12"):
            nexas.records(nexas.parse(func69_bin(extra=[(4, 0), (6, 1), (12, 5)])), F69)

    def test_extras_voice_suffix_is_part_of_the_token(self):
        extras = nexas.DIALECT_EXTRAS
        self.assertEqual(nexas.controls("@v12345678b「本文」", extras), ["@v12345678b"])
        self.assertEqual(nexas.controls("@v12345678_a「本文」", extras), ["@v12345678_a"])
        self.assertEqual(nexas.controls("@v12345678「本文」", extras), ["@v12345678"])
        for bad in ["@v12345678ab「", "@v123456789「", "@v12345678_「", "@v12345678b1", "@v1234567「"]:
            with self.subTest(text=bad), self.assertRaises(FormatError):
                nexas.controls(bad, extras)
        data = message_bin("@v12345678b「本文」@n次")
        rows, manifest = nexas.export(data, source_name="a.bin")
        self.assertEqual(manifest["records"][0]["message_tokens"], ["@v12345678b"])
        for text in ["@v12345678「訳文」", "@v12345678c「訳文」"]:
            with self.subTest(text=text), self.assertRaises(FormatError):
                nexas.inject(data, rows, manifest, [dict(rows[0], message=text)], source_name="a.bin")
        ok = [dict(rows[0], message="@v12345678b「長い訳文です」")]
        built = nexas.inject(data, rows, manifest, ok, source_name="a.bin")
        self.assertEqual(nexas.records(nexas.parse(built))[0], ok)

    def test_func69_controls_ruby_and_boundaries(self):
        good = "@v1234567a「@s4040@r漢字@かんじ@です@t0100@hFACE_A1@n@k"
        self.assertEqual(nexas.controls(good, F69),
                         ["@v1234567a", "@s4040", "@r", "@", "@", "@t0100", "@hFACE_A1", "@n", "@k"])
        self.assertEqual(nexas.controls("@vA1234567「", F69), ["@vA1234567"])
        self.assertEqual(nexas.controls("@v12345678b「", F69), ["@v12345678b"])
        for bad in ["@v1234567「", "@v1234567890「", "@vかな", "@s40401", "@s404",
                    "@r漢字@かんじ", "@r@かんじ@", "@HFACE", "@x"]:
            with self.subTest(text=bad), self.assertRaises(FormatError):
                nexas.controls(bad, F69)
        with self.assertRaises(FormatError):
            nexas.controls("@r漢字@かんじ@", nexas.DIALECT_EXTRAS)
        data = func69_bin("@v12345678@s4040「@r漢字@かんじ@です」@n次")
        rows, manifest = nexas.export(data, source_name="a.bin", dialect=F69)
        self.assertEqual(manifest["records"][0]["message_tokens"], ["@v12345678", "@s4040", "@r"])
        ok = [dict(rows[0], message="@v12345678@s4040「@r中文@zhong@です」"), *rows[1:]]
        built = nexas.inject(data, rows, manifest, ok, source_name="a.bin")
        self.assertEqual(nexas.records(nexas.parse(built), F69)[0][0], ok[0])
        for text in ["@v12345678@s4040「中文です」@n次", "@v12345678@s4040「@r中文@zhong です」@n次",
                     "@v12345678@s4040「@r中文@zhong@です」@n次@n", "@v12345678x@s4040「@r中文@zhong@」"]:
            with self.subTest(text=text), self.assertRaises(FormatError):
                nexas.inject(data, rows, manifest, [dict(rows[0], message=text), *rows[1:]],
                             source_name="a.bin")


class NexasPacklistTests(unittest.TestCase):
    def test_parse_packlist_layout(self):
        names = [("Update2", 0), ("Update", 0), ("Config", 1), ("Script", 1), ("Voice", 2)]
        self.assertEqual(parse_packlist(packlist(names)), [n for n, _ in names])
        for bad in [b"", packlist([]), packlist(names)[:-1], packlist([("Bad/Name", 0)]),
                    packlist([("Script", 1), ("script", 1)])]:
            with self.subTest(raw=bad[-12:]), self.assertRaises(FormatError):
                parse_packlist(bad)

    def test_default_archives_from_packlist_present_on_disk(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            listing = packlist([("Update3", 0), ("Update2", 0), ("Update", 0), ("Config", 1),
                                ("Script", 1), ("Voice", 2)])
            (root / "Config.pac").write_bytes(archive([("packlist.dat", listing)]))
            (root / "Script.pac").write_bytes(archive([("scene.bin", message_bin())]))
            (root / "Update3.pac").write_bytes(archive([("scene.bin", message_bin("新")),
                                                        ("packlist.dat", listing)]))
            (root / "Voice.pac").write_bytes(archive([("a.ogg", b"x")]))
            chosen, evidence = default_archives(root)
            self.assertEqual(chosen, ["Script.pac", "Update3.pac"])
            self.assertEqual(evidence["absent_on_disk"], ["Update2.pac", "Update.pac"])
            (root / "Update3.pac").write_bytes(archive([("packlist.dat", packlist([("Script", 1)]))]))
            with self.assertRaisesRegex(FormatError, "differs from Config.pac"):
                default_archives(root)
            (root / "Config.pac").unlink()
            with self.assertRaisesRegex(FormatError, "--archives"):
                default_archives(root)


class NexasBlockedMemberTests(unittest.TestCase):
    def test_blocked_member_partial_verbatim_and_refused_on_pack(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            broken = func69_bin("@Hbroken本文")
            base = archive([("good.bin", func69_bin()), ("bad.bin", broken)])
            (root / "Script.pac").write_bytes(base)
            out = root / "extract"
            report = extract(root, out, ["Script.pac"], verify_edits=True)
            self.assertEqual(report["status"], "partial")
            self.assertEqual(report["profile"], F69.profile)
            self.assertEqual([b["member"] for b in report["blocked"]], ["bad.bin"])
            self.assertIn("Script.pac:bad.bin", report["blocked"][0]["reason"])
            self.assertIn("command 2", report["blocked"][0]["reason"])
            self.assertEqual(report["edit_check"]["members"], 1)
            self.assertTrue(report["delivery"]["translation_notes"])
            self.assertEqual(sorted(p.name for p in (out / "gt_input").iterdir()), ["good.json"])
            rebuilt = (out / "roundtrip/Script.pac").read_bytes()
            self.assertEqual(rebuilt, pac.rebuild(io.BytesIO(base), pac.read_index(io.BytesIO(base)), {}))
            idx = pac.read_index(io.BytesIO(rebuilt))
            self.assertEqual(pac.read_member(io.BytesIO(rebuilt), idx, idx.entries[1]), broken)
            (out / "gt_output/bad.json").write_bytes(dump_rows([{"message": "x"}]))
            with self.assertRaisesRegex(FormatError, "blocked"):
                pack(out, root / "packed")
            (out / "gt_output/bad.json").unlink()
            rows = nexas.records(nexas.parse(func69_bin()), F69)[0]
            translated = [dict(r, message=r["message"] + "訳") for r in rows]
            (out / "gt_output/good.json").write_bytes(dump_rows(translated))
            result = pack(out, root / "packed")
            self.assertEqual(result["copied_blocked_scripts"], ["bad.bin"])
            built = (root / "packed/Script.pac").read_bytes()
            idx = pac.read_index(io.BytesIO(built))
            self.assertEqual(nexas.records(nexas.parse(pac.read_member(io.BytesIO(built), idx, idx.entries[0])),
                                           F69)[0], translated)
            self.assertEqual(pac.read_member(io.BytesIO(built), idx, idx.entries[1]), broken)

    def test_no_message_table_is_failure_not_empty_export(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            odd = bin_file([(0, 1), (5, 1), (0, 2), (5, 1), (7, 0x40077)], ["", "名", "本文"])
            (root / "Script.pac").write_bytes(archive([("a.bin", odd)]))
            with self.assertRaisesRegex(FormatError, "no single NeXAS FUNC dialect"):
                extract(root, root / "out", ["Script.pac"])
            self.assertFalse((root / "out").exists())

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "Script.pac").write_bytes(archive([("good.bin", func69_bin()),
                                                       ("bad.bin", func69_bin("@Hx本文"))]))
            for argv, code in [(["extract", str(root), "--output", str(root / "a"), "--archives", "Script.pac"], 1),
                               (["extract", str(root), "--output", str(root / "b"), "--archives", "Missing.pac"], 2),
                               (["extract", str(root), "--output", str(root / "c")], 2)]:
                with self.subTest(argv=argv), patch("sys.argv", ["nexas_extract", *argv]), \
                        patch("sys.stdout", io.StringIO()), patch("sys.stderr", io.StringIO()) as err:
                    with self.assertRaises(SystemExit) as caught:
                        main()
                    self.assertEqual(caught.exception.code, code)
                    if code == 2:
                        self.assertIn("error: extract:", err.getvalue())


if __name__ == "__main__":
    unittest.main()
