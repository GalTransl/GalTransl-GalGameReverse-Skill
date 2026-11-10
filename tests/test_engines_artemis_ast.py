"""Synthetic tests for the Artemis AST text-scenario reference.

Fixtures are hand-written; no commercial game data is used. The shapes mirror
the ones verified against a real multi-volume release and a shipped Chinese
patch (see engines/artemis-ast.md): ``rt2`` line breaks, ruby, ``exfont``,
multi-slot names, ``select``, ``savetitle``, and ``delay`` tables with
``[1000] =`` keys, in the CRLF/one-statement-per-line layout the real corpus
uses.
"""

from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from python.common import contract
from python.engines import artemis_ast as ast


BODY = """astver = 2.0
ast = {
\tblock_00000 = {
\t\t{"savetitle", text="\u7b2c\u4e00\u7ae0"},
\t\t{"text"},
\t\tdelay = {
\t\t\t[1000] = {
\t\t\t\t{"se", id=1, file="se0148"},
\t\t\t},
\t\t},
\t\ttext = {
\t\t\tvo = {
\t\t\t\t{"vo", file="fem_shi_00004", ch="shi"},
\t\t\t},
\t\t\tja = {
\t\t\t\t{
\t\t\t\t\tname = {"\u9759\u6d41", "\uff1f\uff1f\uff1f"},
\t\t\t\t\t"\u300c\u305d\u3046\u3067\u3059\u304b\u3002",
\t\t\t\t\t{"ruby", text="\u3064\u3076\u3089\u304e"},
\t\t\t\t\t"\u5186\u6728",
\t\t\t\t\t{"/ruby"},
\t\t\t\t\t"\u3061\u3083\u3093\u3067\u3059\u304b\uff1f\u300d",
\t\t\t\t\t{"rt2"},
\t\t\t\t\t"\u304b\u308c\u3053\u308c\uff11\uff10\u5e74\u3050\u3089\u3044\u524d\u3067\u3059\u3002",
\t\t\t\t\t{"rt2"},
\t\t\t\t},
\t\t\t},
\t\t},
\t\tlinknext = "block_00001",
\t\tline = 150,
\t},
\tblock_00001 = {
\t\t{"text"},
\t\ttext = {
\t\t\tja = {
\t\t\t\t{
\t\t\t\t\tname = {"\u9759\u6d41"},
\t\t\t\t\t{"exfont", size="f2"},
\t\t\t\t\t"\u300c\u3044\u3044\u3048\u300d",
\t\t\t\t\t{"exfont"},
\t\t\t\t\t{"rt2"},
\t\t\t\t},
\t\t\t\t{
\t\t\t\t\t"\u300c\u307e\u305f\u6765\u3066\u304f\u3060\u3055\u3044\u306d\u300d",
\t\t\t\t},
\t\t\t},
\t\t},
\t\tline = 160,
\t},
\tblock_00002 = {
\t\t{"select", label="label01"},
\t\tselect = {
\t\t\tja = {
\t\t\t\t"\u306f\u3044",
\t\t\t\t"\u3044\u3044\u3048",
\t\t\t},
\t\t},
\t\tline = 170,
\t},
\tlabel = {
\t\ttop = { block="block_00000", label=1 },
\t},
}
"""
SOURCE = BODY.replace("\n", "\r\n").encode("utf-8")
UNITS = 6
MESSAGES = (
    "第一章",
    "「そうですか。円木ちゃんですか？」\nかれこれ１０年ぐらい前です。",
    "「いいえ」",
    "「また来てくださいね」",
    "はい",
    "いいえ",
)
FIRST = MESSAGES[1]
MINIMAL = b'astver = 2.0\nast = {\n\tlabel = { top = { block="block_00000", label=1 } },\n}\n'


def read(data=SOURCE, **kwargs):
    return ast.read_ast(data, encoding="utf-8", **kwargs)


class ProbeTests(unittest.TestCase):
    def test_header_forms(self):
        self.assertTrue(ast.looks_like_ast(b"astver = 2.0\r\nast = {}"))
        self.assertTrue(ast.looks_like_ast(b'\xef\xbb\xbfastname = "x"\r\nast = {}'))
        self.assertTrue(ast.looks_like_ast(b"\n\n  ast = {}"))
        self.assertFalse(ast.looks_like_ast(b"ASB\x00\x00\x01\x00"))
        self.assertFalse(ast.looks_like_ast(b"*top\r\n[adv]\r\n"))
        self.assertFalse(ast.looks_like_ast(b""))
        self.assertFalse(ast.looks_like_ast(1234))

    def test_bom_and_newline_are_kept(self):
        document = read(b"\xef\xbb\xbf" + SOURCE)
        self.assertTrue(document.bom)
        self.assertEqual(document.encoding, "utf-8-sig")
        self.assertEqual(document.newline, "\r\n")
        self.assertEqual(document.patch(document.rows()), b"\xef\xbb\xbf" + SOURCE)
        self.assertEqual(read(MINIMAL).newline, "\n")
        self.assertEqual(read(MINIMAL).astver, "2.0")

    def test_encoding_is_not_guessed_loosely(self):
        self.assertEqual(read(SOURCE).encoding, "utf-8")
        with self.assertRaises(ast.AstError) as caught:
            ast.read_ast(SOURCE, encoding="utf-16")
        self.assertEqual(caught.exception.code, "bad_encoding")


class HeaderTests(unittest.TestCase):
    def test_astver_and_astname(self):
        document = read(SOURCE)
        self.assertEqual(document.astver, "2.0")
        self.assertIsNone(document.astname)
        named = read(MINIMAL.replace(b"astver = 2.0", b'astver = 2.0\nastname = "chapter01"'))
        self.assertEqual(named.astname, "chapter01")
        headerless = read(MINIMAL.replace(b"astver = 2.0\n", b""))
        self.assertIsNone(headerless.astver)
        no_name = read(MINIMAL.replace(b"astver = 2.0\n", b"astname = 3\n"))
        self.assertIsNone(no_name.astname)

    def test_unsupported_version(self):
        with self.assertRaises(ast.AstError) as caught:
            read(MINIMAL.replace(b"2.0", b"1.0"))
        self.assertEqual(caught.exception.code, "unsupported_version")
        with self.assertRaises(ast.AstError) as caught:
            read(MINIMAL.replace(b"2.0", b'"2.0"'))
        self.assertEqual(caught.exception.code, "bad_header")

    def test_trailing_data_is_rejected(self):
        with self.assertRaises(ast.AstError) as caught:
            read(SOURCE + b"extra = 1\r\n")
        self.assertEqual(caught.exception.code, "trailing_data")


class UnitTests(unittest.TestCase):
    def setUp(self):
        self.document = read()
        self.units = self.document.units

    def test_order_and_kinds(self):
        self.assertEqual(len(self.units), UNITS)
        self.assertEqual([unit.kind for unit in self.units],
                         ["title", "message", "message", "message", "choice", "choice"])
        self.assertEqual([unit.block for unit in self.units][:3],
                         ["block_00000", "block_00000", "block_00001"])
        self.assertEqual(self.units[0].script_line, 150)
        self.assertEqual(self.units[-1].script_line, 170)

    def test_messages(self):
        self.assertEqual([unit.message for unit in self.units], list(MESSAGES))

    def test_name_slots_are_all_kept(self):
        self.assertEqual(self.units[1].names, ("静流", "？？？"))
        self.assertEqual(self.units[1].name_keys, (None, None))
        self.assertEqual(self.units[2].names, ("静流",))
        self.assertEqual(self.units[3].names, ())
        self.assertEqual(self.units[4].names, ())

    def test_rt2_becomes_a_newline_and_line_count_is_kept(self):
        self.assertEqual(self.units[1].lines, 2)
        self.assertTrue(self.units[1].trailing_break)
        self.assertEqual(self.units[1].break_tag, "rt2")
        self.assertFalse(self.units[1].blank_lines)
        self.assertEqual(self.units[3].lines, 0)
        self.assertFalse(self.units[3].trailing_break)

    def test_ruby_and_inline_are_reported_not_merged(self):
        self.assertEqual(self.units[1].furigana, ("つぶらぎ",))
        self.assertEqual(self.units[1].inline, ())
        self.assertEqual(self.units[2].inline, ("exfont", "exfont"))
        self.assertEqual(self.units[2].line_lead[0], ('{"exfont", size="f2"}',))
        self.assertEqual(self.units[2].line_tail[0], ('{"exfont"}',))

    def test_rows_export_the_last_slot_as_the_display_name(self):
        rows = self.document.rows()
        self.assertEqual(rows[0], {"message": "第一章"})
        self.assertEqual(rows[1]["name"], "？？？")
        self.assertNotIn("names", rows[1])
        self.assertEqual(list(rows[1]), ["name", "message"])
        self.assertEqual(rows[2]["name"], "静流")
        self.assertEqual(rows[4], {"message": "はい"})

    def test_metadata_matches_row_count(self):
        rows = self.document.rows()
        self.assertEqual(len(self.document.locators()), len(rows))
        self.assertEqual(len(self.document.name_policies()), len(rows))
        self.assertEqual(len(self.document.protected_tokens()), len(rows))
        self.assertEqual(self.document.name_policies(),
                         ["absent", "writable", "writable", "absent", "absent", "absent"])
        self.assertEqual(self.document.protected_tokens(), [[]] * len(rows))
        locator = self.document.locators()[1]
        self.assertEqual(locator["name_slots"], 2)
        self.assertEqual(locator["source_lines"], 2)
        self.assertEqual(locator["inline_commands"], [])
        self.assertEqual(locator["furigana"], ["つぶらぎ"])

    def test_slot_zero_is_identity_context(self):
        self.assertEqual(self.units[1].identity_name, "静流")
        self.assertEqual(self.units[1].display_name, "？？？")
        locators = self.document.locators()
        self.assertEqual(locators[1]["name_identity"], "静流")
        self.assertEqual(locators[2]["name_identity"], "静流")
        self.assertIsNone(locators[3]["name_identity"])


class RoundtripTests(unittest.TestCase):
    def test_empty_change_is_byte_identical(self):
        document = read()
        self.assertEqual(document.patch(document.rows()), SOURCE)
        self.assertEqual(ast.patch_ast(SOURCE, document.rows(), encoding="utf-8"), SOURCE)

    def test_translation_survives_a_reparse(self):
        document = read()
        rows = document.rows()
        rows[1]["name"] = "？？？"
        rows[1]["message"] = "「原来如此，圆木当店长时的常客吗？」\n那是十年前左右的事了。"
        rows[2]["message"] = "「不用了」"
        rows[3]["message"] = "「欢迎下次再来」"
        rows[4]["message"] = "好"
        rows[5]["message"] = "不好"
        rebuilt = ast.patch_ast(SOURCE, rows, encoding="utf-8")
        after = read(rebuilt)
        self.assertEqual([unit.message for unit in after.units],
                         [row["message"] for row in rows])
        self.assertEqual(after.units[1].names, ("静流", "？？？"))

    def test_only_the_display_slot_is_written(self):
        document = read()
        rows = document.rows()
        rows[1]["name"] = "神秘人"
        rows[2]["name"] = "静"
        raw = document.patch(rows)
        rebuilt = read(raw)
        # Slot 0 keeps the identity; a lone slot gains an appended display slot.
        self.assertEqual(rebuilt.units[1].names, ("静流", "神秘人"))
        self.assertEqual(rebuilt.units[2].names, ("静流", "静"))
        self.assertEqual(rebuilt.rows()[1]["name"], "神秘人")
        self.assertEqual(rebuilt.rows()[2]["name"], "静")
        text = raw.decode("utf-8")
        self.assertIn('name = {"静流", "神秘人"},', text)
        self.assertIn('name = {"静流", "静"},', text)
        # A name-only edit leaves the box itself (furigana included) untouched.
        self.assertIn("つぶらぎ", text)
        self.assertEqual(rebuilt.units[1].message, document.units[1].message)
        # The appended display slot is replaced, not appended again, next time.
        again = rebuilt.rows()
        again[2]["name"] = "小静"
        self.assertEqual(read(rebuilt.patch(again)).units[2].names, ("静流", "小静"))

    def test_display_slot_and_message_change_together(self):
        document = read()
        rows = document.rows()
        rows[2]["name"] = "静"
        rows[2]["message"] = "「不用了」"
        after = read(document.patch(rows))
        self.assertEqual(after.units[2].names, ("静流", "静"))
        self.assertEqual(after.units[2].message, "「不用了」")

    def test_unchanged_display_name_adds_no_slot(self):
        document = read()
        rows = document.rows()
        rows[2]["message"] = "「また」"
        after = read(document.patch(rows))
        self.assertEqual(after.units[2].names, ("静流",))

    def test_identity_slot_cannot_be_targeted(self):
        document = read()
        rows = document.rows()
        rows[1] = {"names": ["静", "？？？"], "message": rows[1]["message"]}
        with self.assertRaises(ast.AstError) as caught:
            document.patch(rows)
        self.assertEqual(caught.exception.code, "bad_name")

    def test_non_text_structure_is_untouched(self):
        document = read()
        rows = document.rows()
        rows[1]["message"] = "改写"
        rows[2]["message"] = "改写"
        rebuilt = ast.patch_ast(SOURCE, rows, encoding="utf-8").decode("utf-8")
        for fragment in ("delay = {", "[1000] = {", '{"se", id=1, file="se0148"}',
                         '{"vo", file="fem_shi_00004", ch="shi"}',
                         'linknext = "block_00001"', "line = 150", "line = 160",
                         'top = { block="block_00000", label=1 }'):
            self.assertIn(fragment, rebuilt)
        self.assertNotIn("つぶらぎ", rebuilt)            # furigana is dropped, by design
        self.assertIn('{"exfont", size="f2"}', rebuilt)  # inline stays in place

    def test_rewritten_box_shape(self):
        document = read()
        rows = document.rows()
        rows[1]["message"] = "一行目\n二行目"
        rebuilt = ast.patch_ast(SOURCE, rows, encoding="utf-8").decode("utf-8")
        self.assertIn('\t\t\t\t\t"一行目\\n二行目",\r\n\t\t\t\t\t{"rt2"},', rebuilt)
        block = rebuilt.split("block_00000 = {")[1].split("block_00001 = {")[0]
        self.assertEqual(block.count('"一行目\\n二行目"'), 1)
        self.assertEqual(block.count('{"rt2"}'), 1)

    def test_box_without_trailing_break_keeps_none(self):
        document = read()
        rows = document.rows()
        rows[3]["message"] = "「ありがとう」"
        rebuilt = ast.patch_ast(SOURCE, rows, encoding="utf-8").decode("utf-8")
        block = rebuilt.split("block_00001 = {")[1].split("block_00002 = {")[0]
        self.assertEqual(block.count('{"rt2"}'), 1)   # only the exfont box keeps one
        self.assertIn('\t\t\t\t\t"「ありがとう」",\r\n\t\t\t\t},', rebuilt)

    def test_blank_line_layout_is_preserved(self):
        source = SOURCE.replace(b"\t\t\t\t{\r\n\t\t\t\t\tname",
                                b"\t\t\t\t{\r\n\r\n\t\t\t\t\tname")
        self.assertNotEqual(source, SOURCE)
        document = ast.read_ast(source, encoding="utf-8")
        self.assertTrue(document.units[1].blank_lines)
        self.assertTrue(document.units[2].blank_lines)
        self.assertEqual(document.patch(document.rows()), source)
        rows = document.rows()
        rows[1]["message"] = "改写"
        rebuilt = ast.patch_ast(source, rows, encoding="utf-8")
        self.assertIn(b"\t\t\t\t{\r\n\r\n\t\t\t\t\tname", rebuilt)
        self.assertIn(b'\r\n\r\n\t\t\t\t\t"\xe6\x94\xb9\xe5\x86\x99",', rebuilt)

    def test_inline_commands_keep_their_line_when_the_line_count_matches(self):
        document = read()
        rows = document.rows()
        rows[2]["message"] = "「いいえ、けっこうです」"
        after = read(ast.patch_ast(SOURCE, rows, encoding="utf-8"))
        self.assertEqual(after.units[2].line_lead[0], ('{"exfont", size="f2"}',))
        self.assertEqual(after.units[2].line_tail[0], ('{"exfont"}',))
        self.assertEqual(after.units[2].inline, ("exfont", "exfont"))

    def test_inline_commands_fall_back_when_the_line_count_changes(self):
        document = read()
        rows = document.rows()
        rows[2]["message"] = "一段目\n二段目"
        after = read(ast.patch_ast(SOURCE, rows, encoding="utf-8"))
        self.assertEqual(after.units[2].inline, ())    # reported, never silent
        self.assertEqual(after.units[2].message, "一段目\n二段目")
        self.assertEqual(self.lines_of(after.units[2]), 2)

    @staticmethod
    def lines_of(unit):
        return unit.message.count("\n") + 1


class LuaSyntaxTests(unittest.TestCase):
    SOURCE = (
        "astver = 2.0\nast = {\n"
        "\tblock_00000 = {\n"
        '\t\t{"text"},\n'
        "\t\tparams = {\n"
        '\t\t\t[1] = "kk",\n'
        '\t\t\t["quoted key"] = 2.5,\n'
        '\t\t\tlong = [[a "quote" survives]],\n'
        "\t\t\tnothing = nil,\n"
        "\t\t\tneg = -3,\n"
        "\t\t},\n"
        "\t\ttext = {\n\t\t\tja = {\n\t\t\t\t{\n"
        '\t\t\t\t\t"line\\nbreak",\n'
        '\t\t\t\t\t{"rt2"},\n'
        "\t\t\t\t},\n\t\t\t},\n\t\t},\n\t\tline = 1,\n\t},\n"
        '\tlabel = { top = { block="block_00000", label=1 } },\n}\n'
    ).encode("utf-8")

    def test_bracketed_and_quoted_keys_long_strings_and_nil(self):
        document = read(self.SOURCE)
        self.assertEqual(document.units[0].message, "line\nbreak")
        self.assertEqual(document.patch(document.rows()), self.SOURCE)

    def test_ret2_also_breaks_a_line(self):
        source = self.SOURCE.replace(b'\t\t\t\t\t{"rt2"},\n', b'\t\t\t\t\t{"ret2"},\n')
        document = read(source)
        self.assertEqual(document.units[0].break_tag, "ret2")
        rows = document.rows()
        rows[0]["message"] = "一行目\n二行目"
        rebuilt = read(ast.patch_ast(source, rows, encoding="utf-8"))
        self.assertEqual(rebuilt.units[0].break_tag, "ret2")

    def test_lua_escapes(self):
        self.assertEqual(ast.unescape_lua(r"\065\066\067"), "ABC")
        self.assertEqual(ast.unescape_lua(r"\x41\u4F60\u{597D}"), "A\u4f60\u597d")
        self.assertEqual(ast.unescape_lua(r"a\\b\"c\nd\te"), 'a\\b"c\nd\te')
        with self.assertRaises(ast.AstError) as caught:
            ast.unescape_lua("\\我")
        self.assertEqual(caught.exception.code, "unknown_escape")
        self.assertEqual(ast.unescape_lua("\\我", lenient=True), "\\我")

    def test_lenient_reading_of_a_patched_release(self):
        source = SOURCE.replace("ですか？".encode("utf-8"), "ですか\\我？".encode("utf-8"))
        self.assertNotEqual(source, SOURCE)
        with self.assertRaises(ast.AstError):
            read(source)
        self.assertIn("\\我", read(source, lenient_escapes=True).units[1].message)

    def test_escape_policy_on_write(self):
        self.assertEqual(ast.escape_lua("a\nb"), "a\\nb")
        with self.assertRaises(ast.AstError) as caught:
            ast.escape_lua('say "hi"')
        self.assertEqual(caught.exception.code, "unsafe_character")
        self.assertEqual(ast.escape_lua('say "hi"', allow_lua_escapes=True),
                         'say \\"hi\\"')
        document = read()
        rows = document.rows()
        rows[1]["message"] = '引用符"入り"'
        with self.assertRaises(ast.AstError) as caught:
            document.patch(rows)
        self.assertEqual(caught.exception.code, "unsafe_character")
        self.assertTrue(document.patch(rows, allow_lua_escapes=True))

    def test_write_then_read_of_an_escaped_literal(self):
        document = read()
        rows = document.rows()
        rows[1]["message"] = "a\\b"
        rebuilt = read(ast.patch_ast(SOURCE, rows, encoding="utf-8",
                                     allow_lua_escapes=True))
        self.assertEqual(rebuilt.units[1].message, "a\\b")

    def test_keyed_name_form_is_read_and_written(self):
        source = SOURCE.replace(
            'name = {"静流", "？？？"}'.encode("utf-8"),
            'name = { name="静流", ja="？？？" }'.encode("utf-8"))
        document = read(source)
        self.assertEqual(document.units[1].names, ("静流", "？？？"))
        self.assertEqual(document.units[1].name_keys, ("name", "ja"))
        self.assertEqual(document.patch(document.rows()), source)
        self.assertEqual(document.rows()[1]["name"], "？？？")
        rows = document.rows()
        rows[1]["name"] = "？？"
        rebuilt = ast.patch_ast(source, rows, encoding="utf-8")
        after = read(rebuilt)
        self.assertEqual(after.units[1].names, ("静流", "？？"))
        self.assertEqual(after.units[1].name_keys, ("name", "ja"))

    def test_lone_keyed_slot_is_context_only(self):
        source = SOURCE.replace('name = {"静流"},'.encode("utf-8"),
                                'name = { name="静流" },'.encode("utf-8"), 1)
        self.assertNotEqual(source, SOURCE)
        document = read(source)
        self.assertEqual(document.name_policies()[2], "context")
        self.assertEqual(document.patch(document.rows()), source)
        rows = document.rows()
        rows[2]["name"] = "静"
        with self.assertRaises(ast.AstError) as caught:
            document.patch(rows)
        self.assertEqual(caught.exception.code, "name_not_writable")


class RejectionTests(unittest.TestCase):
    def test_old_top_level_layout(self):
        source = (b'ast = { label = {}, text = { [1] = {} }, }\n')
        with self.assertRaises(ast.AstError) as caught:
            read(source)
        self.assertEqual(caught.exception.code, "old_layout")

    def test_missing_label(self):
        with self.assertRaises(ast.AstError) as caught:
            read(b"ast = { block_00000 = {}, }\n")
        self.assertEqual(caught.exception.code, "missing_label")

    def test_any_named_top_level_table_and_unknown_inline(self):
        self.assertEqual(read(b'ast = { label = { top = {} }, chapter = {}, }\n').units, ())
        with self.assertRaises(ast.AstError) as caught:
            read(b'ast = { ["a"] = {}, ["a"] = {}, label = { top = { block="a" } }, }\n')
        self.assertEqual(caught.exception.code, "duplicate_key")
        broken = SOURCE.replace(b'{"rt2"}', b'{"zzz"}', 1)
        with self.assertRaises(ast.AstError) as caught:
            read(broken)
        self.assertEqual(caught.exception.code, "unknown_inline")
        self.assertEqual(len(read(broken, extra_inline_tags={"zzz"}).units), UNITS)

    def test_duplicate_name_table(self):
        broken = SOURCE.replace('name = {"静流"},'.encode("utf-8"),
                                'name = {"静流"},\r\n\t\t\t\t\tname = {"x"},'.encode("utf-8"), 1)
        self.assertNotEqual(broken, SOURCE)
        with self.assertRaises(ast.AstError) as caught:
            read(broken)
        self.assertEqual(caught.exception.code, "duplicate_name")

    def test_truncated_and_unknown_tokens(self):
        with self.assertRaises(ast.AstError) as caught:
            read(b"ast = { block_00000 = {")
        self.assertEqual(caught.exception.code, "unexpected_end")
        with self.assertRaises(ast.AstError) as caught:
            read(b"astver = 2.0\njunk = 1\n")
        self.assertEqual(caught.exception.code, "bad_header")

    def test_row_shape_rejections(self):
        document = read()
        base = document.rows()
        with self.assertRaises(ast.AstError) as caught:
            document.patch(base[:-1])
        self.assertEqual(caught.exception.code, "row_count")

        empty = list(base)
        empty[2] = {"name": "静流", "message": ""}
        with self.assertRaises(ast.AstError) as caught:
            document.patch(empty)
        self.assertEqual(caught.exception.code, "bad_message")

        broken = list(base)
        broken[3] = {"message": "x", "name": "静流"}
        with self.assertRaises(ast.AstError) as caught:
            document.patch(broken)
        self.assertEqual(caught.exception.code, "name_not_writable")

        wrong_slots = list(base)
        wrong_slots[1] = {"names": ["静流"], "message": "x"}
        with self.assertRaises(ast.AstError) as caught:
            document.patch(wrong_slots)
        self.assertEqual(caught.exception.code, "bad_name")

        no_message = list(base)
        no_message[2] = {"name": "静流"}
        with self.assertRaises(ast.AstError) as caught:
            document.patch(no_message)
        self.assertEqual(caught.exception.code, "bad_row")

        both = list(base)
        both[2] = {"name": "静流", "names": ["静流"], "message": "x"}
        with self.assertRaises(ast.AstError) as caught:
            document.patch(both)
        self.assertEqual(caught.exception.code, "bad_name")

    def test_unsafe_and_empty_payload(self):
        document = read()
        rows = document.rows()
        rows[1]["message"] = "改\r\n写"
        with self.assertRaises(ast.AstError) as caught:
            document.patch(rows)
        self.assertEqual(caught.exception.code, "bad_message")
        with self.assertRaises(ast.AstError) as caught:
            ast.read_ast(SOURCE, encoding="utf-8", max_bytes=16)
        self.assertEqual(caught.exception.code, "too_large")
        with self.assertRaises(ast.AstError) as caught:
            read(b"astver = 2.0\nast = { block_00000 = { text = { ja = { {} } }, },"
                 b' label = { top = {} } }\n')
        self.assertEqual(caught.exception.code, "empty_box")


QUOTED = (
    "astver = 2.0\r\nast = {\r\n"
    '\t["0001_00001"] = {\r\n'
    '\t\t{"text"},\r\n'
    "\t\ttext = {\r\n\t\t\tja = {\r\n\t\t\t\t{\r\n"
    '\t\t\t\t\tname = {"遥斗", "Haruto"},\r\n'
    '\t\t\t\t\t"「おはよう」",\r\n'
    '\t\t\t\t\t{"rt2"},\r\n'
    "\t\t\t\t},\r\n\t\t\t},\r\n\t\t},\r\n"
    '\t\tlinknext = "0001_00002",\r\n'
    "\t},\r\n"
    '\t["0001_00002"] = {\r\n'
    '\t\t{"text"},\r\n'
    "\t\ttext = {\r\n\t\t\tja = {\r\n\t\t\t\t{\r\n"
    '\t\t\t\t\t"朝だ。",\r\n'
    "\t\t\t\t},\r\n\t\t\t},\r\n\t\t},\r\n"
    "\t},\r\n"
    '\tlabel = { top = { block = "0001_00001", label = 1 }, },\r\n'
    "}\r\n"
).encode("utf-8")


class QuotedBlockKeyTests(unittest.TestCase):
    def test_quoted_string_block_keys_are_blocks(self):
        document = ast.read_ast(QUOTED)
        self.assertEqual([unit.block for unit in document.units],
                         ["0001_00001", "0001_00002"])
        self.assertEqual(document.rows()[0], {"name": "Haruto", "message": "「おはよう」"})
        self.assertEqual(document.patch(document.rows()), QUOTED)

    def test_quoted_key_rewrite_keeps_identity_and_links(self):
        document = ast.read_ast(QUOTED)
        rows = document.rows()
        rows[0]["name"] = "遥斗君"
        rows[0]["message"] = "「早上好，今天也要加油」"
        rows[1]["message"] = "天亮了。"
        rebuilt = document.patch(rows)
        after = ast.read_ast(rebuilt)
        self.assertEqual(after.units[0].names, ("遥斗", "遥斗君"))
        self.assertEqual([u.message for u in after.units], [r["message"] for r in rows])
        self.assertIn(b'["0001_00002"] = {', rebuilt)
        self.assertIn(b'linknext = "0001_00002"', rebuilt)


class EncodingRoundtripTests(unittest.TestCase):
    def test_bomless_utf8_with_default_arguments_is_byte_identical(self):
        document = ast.read_ast(SOURCE)          # no encoding argument
        self.assertFalse(document.bom)
        self.assertEqual(document.encoding, "utf-8")
        rebuilt = document.patch(document.rows())
        self.assertEqual(rebuilt, SOURCE)
        self.assertFalse(rebuilt.startswith(b"\xef\xbb\xbf"))
        rows = document.rows()
        rows[1]["message"] = "改写"
        changed = ast.patch_ast(SOURCE, rows)
        self.assertFalse(changed.startswith(b"\xef\xbb\xbf"))

    def test_bom_is_kept_with_default_arguments(self):
        source = b"\xef\xbb\xbf" + SOURCE
        document = ast.read_ast(source)
        self.assertTrue(document.bom)
        self.assertEqual(document.patch(document.rows()), source)
        rows = document.rows()
        rows[1]["message"] = "改写"
        self.assertTrue(document.patch(rows).startswith(b"\xef\xbb\xbf"))
        self.assertFalse(document.patch(rows)[3:].startswith(b"\xef\xbb\xbf"))

    def test_explicit_utf8_sig_on_a_bomless_file_adds_no_bom(self):
        document = ast.read_ast(SOURCE, encoding="utf-8-sig")
        self.assertFalse(document.bom)
        self.assertEqual(document.patch(document.rows()), SOURCE)

    def test_cp932_fallback_roundtrip(self):
        source = MINIMAL.replace(b"astver = 2.0", 'astname = "第一"'.encode("cp932"))
        document = ast.read_ast(source)
        self.assertEqual(document.encoding, "cp932")
        self.assertEqual(document.patch(document.rows()), source)


class ProbeBoundaryTests(unittest.TestCase):
    def test_multibyte_character_across_the_probe_boundary(self):
        head = 'astver = 2.0\nastname = "'.encode("utf-8")
        body = head + "あ".encode("utf-8") * 40 + b'"\nast = {}\n'
        for cut in range(len(head) + 1, len(head) + 9):
            with self.subTest(cut=cut):
                self.assertTrue(ast.looks_like_ast(body, max_bytes=cut))
        self.assertTrue(ast.looks_like_ast(b"\xef\xbb\xbf" + body, max_bytes=len(head) + 5))

    def test_cp932_character_across_the_probe_boundary(self):
        body = 'astname = "'.encode("cp932") + "漢字".encode("cp932") * 20
        self.assertTrue(ast.looks_like_ast(body, max_bytes=len(body) - 1))

    def test_invalid_bytes_inside_the_prefix_still_fail(self):
        self.assertFalse(ast.looks_like_ast(b"astver\xff\xfe = 2.0", encoding="utf-8"))
        self.assertFalse(ast.looks_like_ast(b"\x80\x81 = 1"))


class DocumentPatchVerificationTests(unittest.TestCase):
    def test_document_patch_reuses_its_parse_options(self):
        source = SOURCE.replace("ですか？".encode("utf-8"), "ですか\\我？".encode("utf-8"))
        document = read(source, lenient_escapes=True)
        self.assertTrue(document.lenient_escapes)
        rows = document.rows()
        rows[2]["message"] = "「不用了」"
        after = read(document.patch(rows), lenient_escapes=True)
        self.assertEqual(after.units[2].message, "「不用了」")
        broken = SOURCE.replace(b'{"rt2"}', b'{"zzz"}', 1)
        tagged = read(broken, extra_inline_tags={"zzz"})
        self.assertEqual(tagged.extra_inline_tags, frozenset({"zzz"}))
        rows = tagged.rows()
        rows[3]["message"] = "「好」"
        self.assertEqual(read(tagged.patch(rows), extra_inline_tags={"zzz"}).units[3].message,
                         "「好」")

    def test_document_patch_rejects_a_rebuild_that_does_not_reparse_equal(self):
        document = read()
        rows = document.rows()
        rows[2]["message"] = "「不用了」"
        original = ast.render

        def tampered(doc, new_rows, **kwargs):
            return original(doc, new_rows, **kwargs).replace("line = 150", "line = 151")

        with mock.patch.object(ast, "render", tampered):
            with self.assertRaises(ast.AstError) as caught:
                document.patch(rows)
        self.assertEqual(caught.exception.code, "verification_failed")

        def wrong_text(doc, new_rows, **kwargs):
            return original(doc, new_rows, **kwargs).replace("不用了", "不要了")

        with mock.patch.object(ast, "render", wrong_text):
            with self.assertRaises(ast.AstError) as caught:
                document.patch(rows)
        self.assertEqual(caught.exception.code, "verification_failed")


class ContractTests(unittest.TestCase):
    def manifest(self):
        document = read()
        rows = document.rows()
        manifest = contract.make_manifest(
            engine="artemis", variant="ast-text/astver=2.0", reference="test",
            sources={"script/01.ast": SOURCE}, rows=rows,
            locators=document.locators(), encoding="utf-8",
            name_policies=document.name_policies(),
            protected_tokens=document.protected_tokens())
        return document, rows, manifest

    def test_manifest_and_validation(self):
        document, rows, manifest = self.manifest()
        translated = [dict(row) for row in rows]
        translated[1]["message"] = "「……」"
        contract.validate_translation(manifest, {"script/01.ast": SOURCE}, rows, translated)
        rebuilt = ast.patch_ast(SOURCE, translated, encoding="utf-8")
        self.assertEqual(read(rebuilt).units[1].message, "「……」")

    def test_a_title_has_no_name_slot(self):
        document, rows, manifest = self.manifest()
        translated = [dict(row) for row in rows]
        translated[0]["name"] = "X"
        with self.assertRaises(contract.FormatError):
            contract.validate_translation(manifest, {"script/01.ast": SOURCE},
                                          rows, translated)
        with self.assertRaises(ast.AstError) as caught:
            document.patch(translated)
        self.assertEqual(caught.exception.code, "name_not_writable")


if __name__ == "__main__":
    unittest.main()
