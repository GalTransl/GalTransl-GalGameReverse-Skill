"""Synthetic tests for the Artemis SCP text-scenario reference.

Fixtures are hand-written; no commercial game data is used. The speaker rules
mirror the ones verified against a real release (see engines/artemis-scp.md).
"""

from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from python.engines import artemis_scp as scp

TAG_INI = b"""; Pre-Processing Tag.
[&scpsupport]
0=mode

[var]
0=name
1=data

[custom]
0=name
"""

# Record layout of SCRIPT, by blank-line groups:
#   0 dialogue "\u5e78\u679d"        (writable, from a voice-only attribute)
#   1 narration
#   2 dialogue unknown speaker      (\u4e3b\u4eba\u516c, no name attribute)
#   3 dialogue writable name        (name="\uff1f\uff1f\uff1f", one inline token)
#   4 narration                     (after [var ...], which is a command)
SCRIPT = (
    "// header\r\n"
    "*top\r\n"
    "[&scpsupport mode=\"init\"]\r\n"
    "[adv]\r\n"
    "\r\n"
    "[\u5e78\u679d file=\"sachie_t001\"]\r\n"
    "\u300c\u3042\u308a\u304c\u3068\u3046\r\n"
    "\u3054\u3081\u3093\u306a\u3055\u3044\u300d\r\n"
    "\r\n"
    "\u5f7c\u306f\u7b11\u3063\u305f\u3002\r\n"
    "\r\n"
    "[\u5f71 color=\"black\"]\r\n"
    "[\u4e3b\u4eba\u516c]\r\n"
    "\u300c\u3048\u3048\u300d\r\n"
    "\r\n"
    "[\u307e\u308a\u3082 name=\"\uff1f\uff1f\uff1f\" file=\"marimo_t001\"]\r\n"
    "\u300c[\u30eb\u30d3 rb=\"\u3055/\u3055\"]\u3042\u300d\r\n"
    "\r\n"
    "[var name=\"scenario_path\" data=\"x\"]\r\n"
    "\u4e3b\u4eba\u516c\u306f\u3046\u306a\u305a\u3044\u305f\u3002\r\n"
    "\r\n"
)
ROWS = 5


def _read(text=SCRIPT, **kwargs):
    return scp.read_script(text.encode("utf-8"), encoding="utf-8", **kwargs)


class LineKindTests(unittest.TestCase):
    def test_every_prefix(self):
        cases = {
            "": "blank", "   ": "blank", "// x": "comment", "; x": "comment",
            "  ;#tag": "comment", "*label": "label", "  *#1": "label",
            "#\u7acb\u3061\u7d75 a,b": "linetag", "[adv]": "command",
            "  [\u5f71]": "command", "\u300c\u3042\u300d": "text", "x": "text",
        }
        for line, expected in cases.items():
            with self.subTest(line=line):
                self.assertEqual(scp.line_kind(line), expected)

    def test_semicolon_lines_never_become_messages(self):
        text = "[\u5e78\u679d file=\"a\"]\r\n\u300c\u3042\u300d\r\n;#\u7acb\u3061\u7d75 x,y\r\n\u300c\u3044\u300d\r\n"
        records = scp.read_script(text.encode("utf-8")).records
        self.assertEqual([r.text for r in records], ["\u300c\u3042\u300d", "\u300c\u3044\u300d"])

    def test_linetag_lines_never_become_messages(self):
        text = "#\u7acb\u3061\u7d75 x,y\r\ntext line\r\n"
        records = scp.read_script(text.encode("utf-8"), force=True).records
        self.assertEqual([r.text for r in records], ["text line"])


class SpeakerTests(unittest.TestCase):
    def test_voice_attribute_gives_a_writable_display_name(self):
        record = _read().records[0]
        self.assertEqual((record.kind, record.name, record.name_policy),
                         ("dialogue", "\u5e78\u679d", "writable"))
        self.assertEqual(record.speaker_line, 5)

    def test_name_attribute_is_writable(self):
        record = _read().records[3]
        self.assertEqual((record.kind, record.name, record.name_policy),
                         ("dialogue", "\uff1f\uff1f\uff1f", "writable"))
        self.assertEqual(record.speaker_line, 15)

    def test_ordinary_command_keeps_the_speaker_and_bare_tag_clears_it(self):
        records = _read().records
        self.assertEqual((records[1].kind, records[1].name), ("narration", None))
        self.assertEqual((records[2].name, records[2].name_policy), (None, "absent"))
        self.assertEqual(records[2].speaker_tag, "\u4e3b\u4eba\u516c")

    def test_an_unknown_speaker_never_inherits_the_previous_name(self):
        text = ("[\u5e78\u679d file=\"a\"]\r\n\u300c\u3042\u300d\r\n\r\n"
                "[\u4e3b\u4eba\u516c]\r\n\u300c\u3044\u300d\r\n")
        records = scp.read_script(text.encode("utf-8")).records
        self.assertEqual(records[0].name, "\u5e78\u679d")
        self.assertIsNone(records[1].name)

    def test_speaker_tags_enable_a_display_name_override(self):
        text = "[\u4e3b\u4eba\u516c]\r\n\u300c\u3042\u300d\r\n"
        records = scp.read_script(text.encode("utf-8"), force=True,
                                  speaker_tags=frozenset({"\u4e3b\u4eba\u516c"})).records
        self.assertEqual((records[0].name, records[0].name_policy),
                         ("\u4e3b\u4eba\u516c", "writable"))

    def test_command_tags_are_never_read_as_speakers(self):
        text = "[custom name=\"display\"]\r\n\u300c\u3042\u300d\r\n"
        raw = text.encode("utf-8")
        self.assertEqual(scp.read_script(raw, force=True).records[0].name, "display")
        schema = scp.TagSchema.parse(TAG_INI, encoding="utf-8")
        self.assertIsNone(scp.read_script(raw, tag_schema=schema, force=True).records[0].name)
        self.assertIsNone(scp.read_script(raw, command_tags=frozenset({"custom"}),
                                          force=True).records[0].name)
        # An explicit speaker pin wins over the built-in command set.
        pinned = scp.read_script("[var name=\"x\" data=\"y\"]\r\n\u300c\u3042\u300d\r\n".encode("utf-8"),
                                 speaker_tags=frozenset({"var"}), force=True).records
        self.assertEqual((pinned[0].name, pinned[0].name_policy), ("x", "writable"))

    def test_builtin_command_set_catches_the_name_attribute_trap(self):
        raw = "[var name=\"scenario_path\" data=\"x\"]\r\n\u300c\u3042\u300d\r\n".encode("utf-8")
        self.assertIsNone(scp.read_script(raw, force=True).records[0].name)


class GroupingTests(unittest.TestCase):
    def test_records_group_by_blank_lines_and_keep_order(self):
        records = _read().records
        self.assertEqual(len(records), ROWS)
        self.assertEqual(records[0].text,
                         "\u300c\u3042\u308a\u304c\u3068\u3046\n\u3054\u3081\u3093\u306a\u3055\u3044\u300d")
        self.assertEqual((records[0].line_start, records[0].line_end), (6, 8))
        self.assertEqual(records[0].tokens, ())

    def test_inline_tokens_are_reported(self):
        self.assertEqual(_read().records[3].tokens,
                         ("[\u30eb\u30d3 rb=\"\u3055/\u3055\"]",))

    def test_rows_and_locators_align(self):
        script = _read()
        rows = script.rows()
        self.assertEqual(len(rows), len(script.locators()))
        self.assertEqual(rows[1], {"message": "\u5f7c\u306f\u7b11\u3063\u305f\u3002"})
        self.assertEqual(rows[0]["name"], "\u5e78\u679d")
        self.assertEqual(script.name_policies(), ["writable", "absent", "absent", "writable", "absent"])
        self.assertEqual(list(rows[0]), ["name", "message"])
        self.assertEqual(script.protected_tokens()[3], ["[\u30eb\u30d3 rb=\"\u3055/\u3055\"]"])


class RoundtripTests(unittest.TestCase):
    def test_identity_roundtrip_is_byte_exact(self):
        raw = SCRIPT.encode("utf-8")
        self.assertEqual(scp.patch_script(raw, _read().rows(), encoding="utf-8"), raw)

    def test_bom_and_lf_are_preserved(self):
        raw = b"\xef\xbb\xbf// x\n[a file=\"b\"]\n\xe3\x80\x8c\xe3\x81\x82\xe3\x80\x8d\n"
        script = scp.read_script(raw)
        self.assertTrue(script.bom)
        self.assertEqual(script.newline, "\n")
        self.assertEqual(scp.patch_script(raw, script.rows()), raw)

    def test_translation_changes_only_the_message(self):
        raw = SCRIPT.encode("utf-8")
        rows = _read().rows()
        rows[1]["message"] = "\u4ed6\u7b11\u4e86\u3002"
        rows[3]["name"] = "???"
        rebuilt = scp.patch_script(raw, rows, encoding="utf-8")
        after = scp.read_script(rebuilt, encoding="utf-8")
        self.assertEqual([r.text for r in after.records], [r["message"] for r in rows])
        self.assertEqual(after.records[3].name, "???")
        self.assertEqual(after.records[0].name, "\u5e78\u679d")
        self.assertIn('name="???"', rebuilt.decode("utf-8"))
        self.assertEqual(rebuilt.decode("utf-8").count("\r\n"), SCRIPT.count("\r\n"))

    def test_shorter_translation_changes_record_line_span(self):
        raw = SCRIPT.encode("utf-8")
        rows = _read().rows()
        rows[0]["message"] = "\u300c\u8c22\u8c22\u300d"
        rebuilt = scp.patch_script(raw, rows, encoding="utf-8")
        after = scp.read_script(rebuilt, encoding="utf-8")
        self.assertEqual([row["message"] for row in rows],
                         [record.text for record in after.records])
        self.assertEqual(after.records[0].kind, "dialogue")
        self.assertEqual(after.records[0].line_end - after.records[0].line_start, 1)

    def test_rejects_structural_damage(self):
        raw = SCRIPT.encode("utf-8")
        base = _read().rows()

        def mutate(index, **change):
            rows = [dict(row) for row in base]
            rows[index].update(change)
            return rows

        cases = [
            ("structure_changed", mutate(0, message="\u3042\u308a\u304c\u3068\u3046")),
            ("bad_message", mutate(0, message="")),
            ("bad_message", mutate(1, message="a\rb")),
            ("line_kind_changed", mutate(1, message="[adv]")),
            ("line_kind_changed", mutate(1, message="// x")),
        ]
        for code, rows in cases:
            with self.subTest(code=code, message=rows[0]["message"][:12]):
                with self.assertRaises(scp.ScpError) as caught:
                    scp.patch_script(raw, rows, encoding="utf-8")
                self.assertEqual(caught.exception.code, code)

    def test_rejects_changed_tokens_and_row_counts(self):
        raw = SCRIPT.encode("utf-8")
        base = _read().rows()
        broken = [dict(row) for row in base]
        broken[3]["message"] = "\u300c\u3042\u300d"
        with self.assertRaises(scp.ScpError) as caught:
            scp.patch_script(raw, broken, encoding="utf-8")
        self.assertEqual(caught.exception.code, "token_changed")
        with self.assertRaises(scp.ScpError):
            scp.patch_script(raw, base[:-1], encoding="utf-8")

    def test_names_that_cannot_be_written_are_refused(self):
        raw = SCRIPT.encode("utf-8")
        base = _read().rows()
        added = [dict(row) for row in base]
        added[1]["name"] = "\u65c1\u767d"
        with self.assertRaises(scp.ScpError) as caught:
            scp.patch_script(raw, added, encoding="utf-8")
        self.assertEqual(caught.exception.code, "name_not_writable")
        missing = [dict(row) for row in base]
        missing[3].pop("name")
        with self.assertRaises(scp.ScpError) as caught:
            scp.patch_script(raw, missing, encoding="utf-8")
        self.assertEqual(caught.exception.code, "missing_name")

    def test_add_display_attribute_preserves_tag_voice_and_comments(self):
        for command, kwargs in (('[人物 voice="voice]01"] // name="comment"', {}),
                                ('[人物]', {'speaker_tags': {'人物'}}),
                                ('[人物 alias-name="keep"]', {'speaker_tags': {'人物'}})):
            raw = (command + '\n「Body」\n\n「Again」\n').encode('utf-8')
            script = scp.read_script(raw, **kwargs)
            self.assertEqual(script.patch(script.rows()), raw)
            rows = script.rows()
            for row in rows:
                row['name'] = '更长的显示姓名'
                row['message'] = '「变长的中文正文」'
            result = script.patch(rows)
            parsed = scp.read_script(result, **kwargs)
            self.assertEqual(parsed.rows(), rows)
            self.assertEqual(parsed.records[0].speaker_tag, '人物')
            self.assertIn('name="更长的显示姓名"', result.decode('utf-8'))
            if 'alias-name' in command:
                self.assertIn('alias-name="keep"', result.decode('utf-8'))
            if not kwargs:
                self.assertIn('voice="voice]01"', result.decode('utf-8'))
                self.assertTrue(result.decode('utf-8').splitlines()[0].endswith('// name="comment"'))
            rows[1]['name'] = 'different'
            with self.assertRaises(scp.ScpError) as caught:
                script.patch(rows)
            self.assertEqual(caught.exception.code, 'shared_name_conflict')

    def test_variable_display_name_stays_context_only(self):
        script = _read('[人物 name="$str20" voice="v"]\n「Body」\n', force=True)
        self.assertEqual(script.name_policies(), ['context'])
        self.assertEqual(script.patch(script.rows()), script.text.encode('utf-8'))
        rows = script.rows()
        rows[0]['name'] = 'changed'
        with self.assertRaises(scp.ScpError) as caught:
            script.patch(rows)
        self.assertEqual(caught.exception.code, 'context_name_changed')

    def test_malformed_speaker_command_and_name_injection_rejected(self):
        for command in ('[人物 voice="v"', '[人物 name="a" name="b"]', '[人物 voice="v]'):
            with self.assertRaises(scp.ScpError):
                _read(command + '\n「Body」\n', force=True)
        script = _read('[人物 voice="v"]\n「Body」\n', force=True)
        for name in ('', 'bad"name', 'bad\nname', 'bad\0name'):
            rows = script.rows()
            rows[0]['name'] = name
            with self.assertRaises(scp.ScpError):
                script.patch(rows)

    def test_patch_method_carries_the_speaker_policy(self):
        raw = "[\u4e3b\u4eba\u516c]\r\n\u300c\u3042\u300d\r\n".encode("utf-8")
        script = scp.read_script(raw, speaker_tags=frozenset({"\u4e3b\u4eba\u516c"}),
                                 force=True)
        self.assertEqual(script.speaker_tags, frozenset({"\u4e3b\u4eba\u516c"}))
        rows = script.rows()
        self.assertEqual(script.patch(rows), raw)
        # Rebuilding without the pinned policy would silently lose the name slot.
        with self.assertRaises(scp.ScpError) as caught:
            scp.patch_script(raw, rows, force=True)
        self.assertEqual(caught.exception.code, "name_not_writable")

    def test_one_speaker_command_cannot_receive_two_names(self):
        text = ("[\u307e\u308a\u3082 name=\"\uff1f\uff1f\uff1f\" file=\"a\"]\r\n"
                "\u300c\u3042\u300d\r\n\r\n\u300c\u3044\u300d\r\n")
        raw = text.encode("utf-8")
        rows = scp.read_script(raw, encoding="utf-8").rows()
        self.assertEqual(len(rows), 2)
        rows[0]["name"] = "A"
        rows[1]["name"] = "B"
        with self.assertRaises(scp.ScpError) as caught:
            scp.patch_script(raw, rows, encoding="utf-8")
        self.assertEqual(caught.exception.code, "shared_name_conflict")


LUA_SECTION = (
    "*top\r\n"
    "[adv]\r\n"
    "[lua]\r\n"
    "function init()\r\n"
    "\tlocal msg = \"\u300c\u3053\u3093\u306b\u3061\u306f\u300d\"\r\n"
    "\r\n"
    "\te:tag{\"var\", name=\"x\"}\r\n"
    "end\r\n"
    "[/lua]\r\n"
    "[\u5e78\u679d file=\"sachie_t001\"]\r\n"
    "\u300c\u3042\u308a\u304c\u3068\u3046\u300d\r\n"
    "\r\n"
    "\u5f7c\u306f\u7b11\u3063\u305f\u3002\r\n"
)
LUA_TABLE_SCRIPT = (
    "ast = {\n"
    "\tblock_00000 = {\n"
    "\t\t{\"text\"},\n"
    "\t\ttext = {\n"
    "\t\t\tja = {\n"
    "\t\t\t\t{ \"\u300c\u3042\u300d\" },\n"
    "\t\t\t},\n"
    "\t\t},\n"
    "\t},\n"
    "\t[\"0001\"] = {},\n"
    "}\n"
)
PLAIN_LUA = (
    "-- system script\n"
    "function init()\n"
    "\tlocal t = { [1] = \"a\", [2] = \"b\" }\n"
    "\tprint(\"\u3053\u3093\u306b\u3061\u306f\")\n"
    "end\n"
)


class LuaAndGateTests(unittest.TestCase):
    def test_lua_section_is_skipped_and_kept(self):
        raw = LUA_SECTION.encode("utf-8")
        script = scp.read_script(raw)
        self.assertEqual([r.text for r in script.records],
                         ["\u300c\u3042\u308a\u304c\u3068\u3046\u300d",
                          "\u5f7c\u306f\u7b11\u3063\u305f\u3002"])
        self.assertEqual(script.records[0].name, "\u5e78\u679d")
        self.assertEqual(script.patch(script.rows()), raw)
        rows = script.rows()
        rows[1]["message"] = "\u4ed6\u7b11\u4e86\uff0c\u7b11\u5f97\u5f88\u5f00\u5fc3\u3002"
        rebuilt = script.patch(rows).decode("utf-8")
        self.assertIn("[lua]\r\nfunction init()\r\n", rebuilt)
        self.assertIn("\te:tag{\"var\", name=\"x\"}\r\nend\r\n[/lua]\r\n", rebuilt)

    def test_lua_only_iet_is_rejected_unless_forced(self):
        raw = ("[lua]\r\nfunction a()\r\n\treturn 1\r\nend\r\n[/lua]\r\n").encode("utf-8")
        with self.assertRaises(scp.ScpError) as caught:
            scp.read_script(raw)
        self.assertEqual(caught.exception.code, "not_scp")
        self.assertEqual(scp.read_script(raw, force=True).records, ())

    def test_unbalanced_lua_sections_are_rejected(self):
        for body in ("*top\r\n[adv]\r\n[lua]\r\nx = 1\r\n\u300c\u3042\u300d\r\n",
                     "*top\r\n[adv]\r\n[/lua]\r\n\u300c\u3042\u300d\r\n\u300c\u3044\u300d\r\n"):
            with self.subTest(body=body[:20]):
                with self.assertRaises(scp.ScpError) as caught:
                    scp.read_script(body.encode("utf-8"), force=True)
                self.assertIn(caught.exception.code, ("unterminated_lua", "unbalanced_lua"))

    def test_translation_cannot_open_a_lua_section(self):
        script = scp.read_script(LUA_SECTION.encode("utf-8"))
        rows = script.rows()
        rows[1]["message"] = "[lua]"
        with self.assertRaises(scp.ScpError) as caught:
            script.patch(rows)
        self.assertEqual(caught.exception.code, "line_kind_changed")

    def test_lua_table_scripts_and_plain_lua_are_not_scp(self):
        for sample in (LUA_TABLE_SCRIPT, PLAIN_LUA):
            raw = sample.encode("utf-8")
            with self.subTest(sample=sample[:12]):
                self.assertFalse(scp.looks_like_script(raw))
                with self.assertRaises(scp.ScpError) as caught:
                    scp.read_script(raw)
                self.assertEqual(caught.exception.code, "not_scp")
                with self.assertRaises(scp.ScpError) as caught:
                    scp.patch_script(raw, [])
                self.assertEqual(caught.exception.code, "not_scp")

    def test_long_leading_lua_section_does_not_hide_scp(self):
        lua = "[lua]\r\n" + "".join(f"x{i} = {i}\r\n" for i in range(80)) + "[/lua]\r\n"
        raw = (lua + SCRIPT).encode("utf-8")
        self.assertTrue(scp.looks_like_script(raw))
        self.assertEqual(len(scp.read_script(raw).records), ROWS)


class PfsOffsetTableTests(unittest.TestCase):
    def test_auto_trailing_table_layout_and_readback(self):
        from python.archives import pfs
        entries = [("script\\a.ast", b"alpha"), ("script\\\u7b2c\u4e00.ast", "\u4e2d\u6587".encode("utf-8")),
                   ("system\\first.iet", b"x" * 33)]
        data = pfs.build(entries, version=8, trailing="auto")
        index = pfs.read_index(data)
        raws = [name.encode("utf-8") for name, _ in entries]
        self.assertEqual(index.trailing, pfs.offset_table(raws))
        self.assertTrue(pfs.trailing_matches_offset_table(index))
        # Structure: u32 n+1 | (n+1) x u64 | u32 table offset inside the index.
        n = len(entries)
        self.assertEqual(len(index.trailing), 4 + 8 * (n + 1) + 4)
        count, = struct.unpack_from("<I", index.trailing, 0)
        self.assertEqual(count, n + 1)
        values = struct.unpack_from(f"<{n + 1}Q", index.trailing, 4)
        self.assertEqual(values[-1], 0)
        table_offset, = struct.unpack_from("<I", index.trailing, 4 + 8 * (n + 1))
        self.assertEqual(table_offset, index.index_end - 7 - len(index.trailing))
        # Each u64 locates the record's offset field relative to the record area.
        raw_index = data[7:index.index_end]
        for value, entry in zip(values, index.entries):
            self.assertEqual(struct.unpack_from("<I", raw_index, 4 + value)[0], entry.offset)
        for entry, (name, payload) in zip(index.entries, entries):
            self.assertEqual(entry.name, name)
            self.assertEqual(pfs.read_member(data, index, entry).data, payload)
        # The table is hashed into the key, and an unchanged repack is identical.
        self.assertEqual(pfs.repack(index, {e.ordinal: pfs.read_member(data, index, e).data
                                            for e in index.entries}), data)

    def test_auto_trailing_follows_index_order_and_rejects_other_versions(self):
        from python.archives import pfs
        entries = [("b", b"22"), ("a", b"1")]
        data = pfs.build(entries, version=8, trailing="auto", index_order=[1, 0])
        index = pfs.read_index(data)
        self.assertEqual([e.name for e in index.entries], ["a", "b"])
        self.assertTrue(pfs.trailing_matches_offset_table(index))
        for version in (0, 2):
            with self.assertRaises(pfs.PfsError):
                pfs.build(entries, version=version, trailing="auto")
        with self.assertRaises(pfs.PfsError):
            pfs.build(entries, trailing="other")


class ProbeTests(unittest.TestCase):
    def test_looks_like_script_accepts_scp_and_rejects_noise(self):
        self.assertTrue(scp.looks_like_script(SCRIPT.encode("utf-8")))
        self.assertFalse(scp.looks_like_script(b"ASB\x00\x00" + bytes(40)))
        self.assertFalse(scp.looks_like_script(b"\x00\x01\x02\x03" * 40))
        self.assertFalse(scp.looks_like_script(b""))

    def test_probe_rejects_readme_rules_string_tables_and_licences(self):
        readme = ("=" * 70 + "\r\n    Voice release 1.5\r\n\r\n" + "*" * 70 + "\r\n    Copying\r\n"
                  + "*" * 70 + "\r\n# " + "-" * 60 + " #\r\nSome prose.\r\n")
        table = "".join(f"[{c}]項目{i} (FLAG_{i})[-]\t᠎[{c}]項目{i}\r\n"
                        for i, c in enumerate(["000000", "111111", "FF00AA"] * 5))
        licence = ("Copyright (c) 2015 Example Corp.\nAll rights reserved.\n"
                   "* Redistributions must retain the above notice.\n[1] See terms.\n")
        for sample in (readme, table, licence):
            self.assertFalse(scp.looks_like_script(sample.encode("utf-8"), max_lines=12))
        # Word-like tag names that happen to be hex letters still count.
        self.assertTrue(scp.looks_like_script(
            "*start\r\n[fade time=\"1\"]\r\n「text」\r\n[bg file=\"a\"] // c\r\n".encode("utf-8")))

    def test_tag_schema_ignores_comments_and_keeps_order(self):
        schema = scp.TagSchema.parse(TAG_INI, encoding="utf-8")
        self.assertIn("var", schema.tags)
        self.assertIn("&scpsupport", schema.tags)
        self.assertEqual(schema.attributes["var"], ("name", "data"))

    def test_bad_encoding_is_reported(self):
        with self.assertRaises(scp.ScpError) as caught:
            scp.read_script("\u3042".encode("cp932"), encoding="utf-8")
        self.assertEqual(caught.exception.code, "script_encoding")

    def test_budgets_are_checked(self):
        with self.assertRaises(scp.ScpError):
            scp.read_script(SCRIPT.encode("utf-8"), max_bytes=8)
        with self.assertRaises(scp.ScpError):
            scp.read_script(SCRIPT.encode("utf-8"), max_lines=3)


if __name__ == "__main__":
    unittest.main()
