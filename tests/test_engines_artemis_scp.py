"""Synthetic tests for the Artemis SCP text-scenario reference.

Fixtures are hand-written; no commercial game data is used. The speaker rules
mirror the ones verified against a real release (see engines/artemis-scp.md).
"""

from pathlib import Path
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
#   0 dialogue "\u5e78\u679d"        (context, from a voice-only attribute)
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
        records = scp.read_script(text.encode("utf-8")).records
        self.assertEqual([r.text for r in records], ["text line"])


class SpeakerTests(unittest.TestCase):
    def test_voice_attribute_gives_a_context_name(self):
        record = _read().records[0]
        self.assertEqual((record.kind, record.name, record.name_policy),
                         ("dialogue", "\u5e78\u679d", "context"))
        self.assertIsNone(record.speaker_line)

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

    def test_speaker_tags_expose_a_context_name(self):
        text = "[\u4e3b\u4eba\u516c]\r\n\u300c\u3042\u300d\r\n"
        records = scp.read_script(text.encode("utf-8"),
                                  speaker_tags=frozenset({"\u4e3b\u4eba\u516c"})).records
        self.assertEqual((records[0].name, records[0].name_policy),
                         ("\u4e3b\u4eba\u516c", "context"))

    def test_command_tags_are_never_read_as_speakers(self):
        text = "[custom name=\"display\"]\r\n\u300c\u3042\u300d\r\n"
        raw = text.encode("utf-8")
        self.assertEqual(scp.read_script(raw).records[0].name, "display")
        schema = scp.TagSchema.parse(TAG_INI, encoding="utf-8")
        self.assertIsNone(scp.read_script(raw, tag_schema=schema).records[0].name)
        self.assertIsNone(scp.read_script(raw, command_tags=frozenset({"custom"})).records[0].name)
        # An explicit speaker pin wins over the built-in command set.
        pinned = scp.read_script("[var name=\"x\" data=\"y\"]\r\n\u300c\u3042\u300d\r\n".encode("utf-8"),
                                 speaker_tags=frozenset({"var"})).records
        self.assertEqual((pinned[0].name, pinned[0].name_policy), ("x", "writable"))

    def test_builtin_command_set_catches_the_name_attribute_trap(self):
        raw = "[var name=\"scenario_path\" data=\"x\"]\r\n\u300c\u3042\u300d\r\n".encode("utf-8")
        self.assertIsNone(scp.read_script(raw).records[0].name)


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
        self.assertEqual(script.name_policies(), ["context", "absent", "absent", "writable", "absent"])
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
        context = [dict(row) for row in base]
        context[0]["name"] = "\u6539\u540d"
        with self.assertRaises(scp.ScpError) as caught:
            scp.patch_script(raw, context, encoding="utf-8")
        self.assertEqual(caught.exception.code, "context_name_changed")
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

    def test_patch_method_carries_the_speaker_policy(self):
        raw = "[\u4e3b\u4eba\u516c]\r\n\u300c\u3042\u300d\r\n".encode("utf-8")
        script = scp.read_script(raw, speaker_tags=frozenset({"\u4e3b\u4eba\u516c"}))
        self.assertEqual(script.speaker_tags, frozenset({"\u4e3b\u4eba\u516c"}))
        rows = script.rows()
        self.assertEqual(script.patch(rows), raw)
        # Rebuilding without the pinned policy would silently lose the name slot.
        with self.assertRaises(scp.ScpError) as caught:
            scp.patch_script(raw, rows)
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


class ProbeTests(unittest.TestCase):
    def test_looks_like_script_accepts_scp_and_rejects_noise(self):
        self.assertTrue(scp.looks_like_script(SCRIPT.encode("utf-8")))
        self.assertFalse(scp.looks_like_script(b"ASB\x00\x00" + bytes(40)))
        self.assertFalse(scp.looks_like_script(b"\x00\x01\x02\x03" * 40))
        self.assertFalse(scp.looks_like_script(b""))

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
