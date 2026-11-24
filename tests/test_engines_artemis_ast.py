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
EXFONT_ON = '{"exfont", size="f2"}'
EXFONT_OFF = '{"exfont"}'
MESSAGES = (
    "第一章",
    "「そうですか。円木ちゃんですか？」\nかれこれ１０年ぐらい前です。",
    EXFONT_ON + "「いいえ」" + EXFONT_OFF,
    "「また来てくださいね」",
    "はい",
    "いいえ",
)
FIRST = MESSAGES[1]
MINIMAL = b'astver = 2.0\nast = {\n\tlabel = { top = { block="block_00000", label=1 } },\n}\n'


def boxed(text):
    """The exfont box's message: its two inline commands stay as tokens."""
    return EXFONT_ON + text + EXFONT_OFF


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
        self.assertEqual(self.units[2].tokens, (EXFONT_ON, EXFONT_OFF))

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
        self.assertEqual(self.document.protected_tokens(),
                         [[], [], [EXFONT_ON, EXFONT_OFF], [], [], []])
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
        rows[2]["message"] = boxed("「不用了」")
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
        rows[2]["message"] = boxed("「不用了」")
        after = read(document.patch(rows))
        self.assertEqual(after.units[2].names, ("静流", "静"))
        self.assertEqual(after.units[2].message, boxed("「不用了」"))

    def test_unchanged_display_name_adds_no_slot(self):
        document = read()
        rows = document.rows()
        rows[2]["message"] = boxed("「また」")
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
        rows[2]["message"] = boxed("改写")
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

    def test_inline_tokens_are_written_back_in_place(self):
        document = read()
        rows = document.rows()
        rows[2]["message"] = boxed("「いいえ、けっこうです」")
        raw = ast.patch_ast(SOURCE, rows, encoding="utf-8")
        after = read(raw)
        self.assertEqual(after.units[2].tokens, (EXFONT_ON, EXFONT_OFF))
        self.assertEqual(after.units[2].inline, ("exfont", "exfont"))
        self.assertIn(('\t\t\t\t\t' + EXFONT_ON + ',\r\n\t\t\t\t\t"「いいえ、けっこうです」",'
                       '\r\n\t\t\t\t\t' + EXFONT_OFF + ',\r\n\t\t\t\t\t{"rt2"},')
                      .encode("utf-8"), raw)

    def test_inline_tokens_survive_a_line_count_change(self):
        document = read()
        rows = document.rows()
        rows[2]["message"] = EXFONT_ON + "一段目\n二段目" + EXFONT_OFF
        after = read(ast.patch_ast(SOURCE, rows, encoding="utf-8"))
        self.assertEqual(after.units[2].message, rows[2]["message"])
        self.assertEqual(after.units[2].tokens, (EXFONT_ON, EXFONT_OFF))
        self.assertEqual(after.units[2].lines, 2)       # one rt2 between, one trailing

    def test_missing_moved_or_extra_tokens_are_rejected(self):
        document = read()
        for message in ("「いいえ」",                               # tokens dropped
                        EXFONT_OFF + "「いいえ」" + EXFONT_ON,     # order swapped
                        boxed("「いいえ」") + EXFONT_OFF,          # one added
                        boxed('{"heroname"}')):                    # foreign token
            rows = document.rows()
            rows[2]["message"] = message
            with self.subTest(message=message):
                with self.assertRaises(ast.AstError) as caught:
                    document.patch(rows, allow_lua_escapes=True)
                self.assertEqual(caught.exception.code, "token_mismatch")
        rows = document.rows()
        rows[3]["message"] = EXFONT_OFF + "x"                      # token-free box
        with self.assertRaises(ast.AstError) as caught:
            document.patch(rows, allow_lua_escapes=True)
        self.assertEqual(caught.exception.code, "token_mismatch")


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
    def test_positional_layout_is_recognised_and_strays_rejected(self):
        document = read(b'ast = { {{"text"}}, label = {}, text = { [1] = {} }, }\n')
        self.assertEqual(document.layout, "positional")
        self.assertEqual(document.units, ())
        with self.assertRaises(ast.AstError) as caught:
            read(b'ast = { {{"text"}}, chapter = {}, text = {}, }\n')
        self.assertEqual(caught.exception.code, "unknown_layout_member")
        with self.assertRaises(ast.AstError) as caught:
            read(b'ast = { { {"text"}, text = { ja = { {"a"} } } }, text = {}, }\n')
        self.assertEqual(caught.exception.code, "unknown_layout_member")

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
        rows[2]["message"] = boxed("「不用了」")
        after = read(document.patch(rows), lenient_escapes=True)
        self.assertEqual(after.units[2].message, boxed("「不用了」"))
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
        rows[2]["message"] = boxed("「不用了」")
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


def block_file(*blocks):
    """A named-block (label.top) file from block bodies; CRLF like the real corpus."""
    body = "astver = 2.0\nast = {\n"
    for number, block in enumerate(blocks):
        body += f"\tblock_{number:05d} = {{\n{block}\t}},\n"
    body += '\tlabel = { top = { block="block_00000", label=1 } },\n}\n'
    return body.replace("\n", "\r\n").encode("utf-8")


def text_block(members):
    return '\t\t{"text"},\n\t\ttext = {\n' + members + "\t\t},\n"


def ja_box(*parts):
    inner = "".join(f"\t\t\t\t\t{part},\n" for part in parts)
    return "\t\t\tja = {\n\t\t\t\t{\n" + inner + "\t\t\t\t},\n\t\t\t},\n"


class TextMemberTests(unittest.TestCase):
    """Attribute members of a text table are kept, never taken for a language."""

    SOURCE = block_file(
        text_block('\t\t\tlinemode = { start="1" },\n' + ja_box('"one"', '{"rt2"}')),
        text_block("\t\t\tlinemode = {},\n\t\t\thide = true,\n"
                   '\t\t\tvo = { {"vo", file="v1", ch="a"}, },\n'
                   + ja_box('"two"', '{"rt2"}')),
        text_block('\t\t\tvo = { {"vo", file="v2", ch="a"}, },\n'),
    )

    def test_attributes_before_the_language_are_skipped(self):
        document = read(self.SOURCE)
        self.assertEqual([row["message"] for row in document.rows()], ["one", "two"])
        self.assertEqual(document.languages, ("ja",))
        self.assertEqual(document.selected_language, "ja")
        self.assertEqual(document.patch(document.rows()), self.SOURCE)

    def test_voice_only_text_has_no_box_and_round_trips(self):
        source = block_file(text_block('\t\t\tvo = { {"vo", file="v2", ch="a"}, },\n'))
        document = read(source)
        self.assertEqual(document.units, ())
        self.assertEqual(document.patch([]), source)

    def test_booleans_parse_as_values(self):
        document = read(self.SOURCE.replace(b"hide = true", b"hide = false"))
        self.assertEqual(len(document.units), 2)
        table = document.ast.items[1].value.get("text")
        self.assertEqual(table.get("hide").kind, "bool")

    def test_unknown_member_shape_is_rejected_not_guessed(self):
        source = self.SOURCE.replace(b'linemode = { start="1" }',
                                     b'float = { {mode="x"} }')
        with self.assertRaises(ast.AstError) as caught:
            read(source)
        self.assertEqual(caught.exception.code, "unknown_text_member")

    def test_bare_identifier_is_a_runtime_reference(self):
        source = block_file(text_block(ja_box('"a"', "{fn}", '"b"')))
        with self.assertRaises(ast.AstError) as caught:
            read(source)
        self.assertEqual(caught.exception.code, "bare_identifier")


class MultiLanguageBlockTests(unittest.TestCase):
    SOURCE = block_file(
        text_block(ja_box('"ja1"', '{"rt2"}') + '\t\t\ten = {\n\t\t\t\t{\n'
                   '\t\t\t\t\t"en1",\n\t\t\t\t\t{"rt2"},\n\t\t\t\t},\n\t\t\t},\n'),
        text_block(ja_box('"ja2"', '{"rt2"}')),
    )

    def test_default_is_the_first_language_and_others_are_selectable(self):
        self.assertEqual([r["message"] for r in read(self.SOURCE).rows()], ["ja1", "ja2"])
        english = read(self.SOURCE, language="en")
        self.assertEqual([r["message"] for r in english.rows()], ["en1"])
        self.assertEqual(english.languages, ("ja", "en"))
        self.assertEqual(english.skipped, ({"kind": "message", "block": "block_00001"},))
        rows = english.rows()
        rows[0]["message"] = "英文改写\n第二行"
        raw = english.patch(rows)
        self.assertIn(b'"ja1"', raw)
        self.assertEqual(read(raw, language="en").rows(), rows)

    def test_absent_language_is_an_error(self):
        with self.assertRaises(ast.AstError) as caught:
            read(self.SOURCE, language="cn")
        self.assertEqual(caught.exception.code, "no_language_table")


HERO = '{"heroname", mode="fn"}'


class InlineTokenTests(unittest.TestCase):
    SOURCE = block_file(text_block(ja_box('"x"', HERO, '"y"', '{"rt2"}', '"z"',
                                          '{"gaiji", text="(1)"}', '{"rt2"}')))

    def test_mid_line_commands_are_tokens_in_place(self):
        document = read(self.SOURCE)
        self.assertEqual(document.rows(), [{"message": f'x{HERO}y\nz{{"gaiji", text="(1)"}}'}])
        self.assertEqual(document.protected_tokens(), [[HERO, '{"gaiji", text="(1)"}']])
        self.assertEqual(document.patch(document.rows()), self.SOURCE)

    def test_rewrite_puts_tokens_back_between_literals(self):
        document = read(self.SOURCE)
        rows = [{"message": f'甲{HERO}乙丙\n丁{{"gaiji", text="(1)"}}戊'}]
        raw = document.patch(rows)
        self.assertIn(('\t\t\t\t\t"甲",\r\n\t\t\t\t\t' + HERO + ',\r\n\t\t\t\t\t"乙丙",\r\n'
                       '\t\t\t\t\t{"rt2"},\r\n').encode("utf-8"), raw)
        self.assertEqual(read(raw).rows(), rows)

    def test_verification_compares_inline_commands(self):
        document = read(self.SOURCE)
        rows = [{"message": f'甲{HERO}乙\nz{{"gaiji", text="(1)"}}'}]
        original = ast.render

        def dropped(doc, new_rows, **kwargs):
            return original(doc, new_rows, **kwargs).replace(HERO + ",", "", 1)

        with mock.patch.object(ast, "render", dropped):
            with self.assertRaises(ast.AstError) as caught:
                document.patch(rows)
        self.assertEqual(caught.exception.code, "verification_failed")

    def test_contract_counts_tokens(self):
        document = read(self.SOURCE)
        rows = document.rows()
        manifest = contract.make_manifest(
            engine="artemis", variant="ast-text", reference="test",
            sources={"a.ast": self.SOURCE}, rows=rows, locators=document.locators(),
            encoding="utf-8", name_policies=document.name_policies(),
            protected_tokens=document.protected_tokens())
        with self.assertRaises(contract.FormatError):
            contract.validate_translation(manifest, {"a.ast": self.SOURCE}, rows,
                                          [{"message": "x y z"}])

    def test_literal_that_looks_like_a_token_is_rejected(self):
        source = block_file(text_block(ja_box('"a{\\"b"', '{"rt2"}')))
        with self.assertRaises(ast.AstError) as caught:
            read(source)
        self.assertEqual(caught.exception.code, "ambiguous_token")

    def test_multiline_inline_command_is_rejected(self):
        source = block_file(text_block(ja_box('"a"', '{"exfont",\n size="f2"}')))
        with self.assertRaises(ast.AstError) as caught:
            read(source)
        self.assertEqual(caught.exception.code, "multiline_inline")


POSITIONAL = (
    "ast = {\n"
    "\t{\n"
    '\t\t{"savetitle", text="序章", en="Prologue"},\n'
    '\t\t{"text"},\n'
    '\t\tcrc ="00000001",\n'
    '\t\tlang="0001_00001",\n'
    "\t\tline=10,\n"
    "\t},\n"
    "\t{\n"
    '\t\t{"text"},\n'
    "\t\tline=20,\n"
    "\t},\n"
    "\t{\n"
    '\t\t{"select", file="a", text="はい"},\n'
    '\t\t{"select", file="b", text="いいえ"},\n'
    '\t\t{"select", name="sel01", mode="auto"},\n'
    "\t\tline=30,\n"
    "\t},\n"
    "\ttext = {\n"
    "\t\t[1] = {\n"
    '\t\t\tvo = { {"vo", file="v001", ch="aaa"}, },\n'
    '\t\t\tname = {name="遥", en="Haruka"},\n'
    '\t\t\tja = {\n\t\t\t\t{\n\t\t\t\t\t"「おはよう」",\n\t\t\t\t\t{"rt2"},\n\t\t\t\t},\n\t\t\t},\n'
    '\t\t\ten = {\n\t\t\t\t{\n\t\t\t\t\t"Morning.",\n\t\t\t\t\t{"rt2"},\n\t\t\t\t},\n\t\t\t},\n'
    "\t\t},\n"
    "\t\t[2] = {\n"
    "\t\t\tlane=1,\n"
    '\t\t\tname = {name="遥"},\n'
    "\t\t},\n"
    "\t\t[3] = {\n"
    '\t\t\tja = {\n\t\t\t\t{\n\t\t\t\t\t"朝だ。",\n\t\t\t\t\t{"gaiji", text="(1)"},\n'
    '\t\t\t\t\t{"rt2"},\n\t\t\t\t},\n\t\t\t},\n'
    '\t\t\ten = {\n\t\t\t\t{\n\t\t\t\t\t"Dawn.",\n\t\t\t\t\t{"rt2"},\n\t\t\t\t},\n\t\t\t},\n'
    "\t\t},\n"
    "\t\t[4] = {\n"
    '\t\t\tselect = {\n\t\t\t\tja = {"はい", "いいえ"},\n\t\t\t\ten = {"Yes", "No"},\n'
    "\t\t\t},\n"
    "\t\t},\n"
    "\t\t[5] = {\n"
    '\t\t\tja = {\n\t\t\t\t{\n\t\t\t\t\t"独白。",\n\t\t\t\t},\n\t\t\t},\n'
    "\t\t},\n"
    "\t},\n"
    "\tlabel = { scene = { block=1, label=1 }, },\n"
    "}\n"
).replace("\n", "\r\n").encode("utf-8")


class PositionalLayoutTests(unittest.TestCase):
    def test_rows_per_language(self):
        japanese = ast.read_ast(POSITIONAL)
        self.assertEqual(japanese.layout, "positional")
        self.assertEqual(japanese.languages, ("ja", "en"))
        self.assertEqual(japanese.rows(), [
            {"message": "序章"},
            {"name": "遥", "message": "「おはよう」"},
            {"name": "遥", "message": ""},
            {"message": '朝だ。{"gaiji", text="(1)"}'},
            {"message": "はい"}, {"message": "いいえ"},
            {"message": "独白。"},
        ])
        self.assertEqual([u.kind for u in japanese.units],
                         ["title", "message", "message", "message", "choice", "choice",
                          "message"])
        self.assertEqual(japanese.locators()[1]["name_identity"], "遥")
        self.assertTrue(japanese.locators()[2]["boxless"])
        english = ast.read_ast(POSITIONAL, language="en")
        self.assertEqual([r["message"] for r in english.rows()],
                         ["Prologue", "Morning.", "", "Dawn.", "Yes", "No"])
        self.assertEqual(english.rows()[1]["name"], "Haruka")
        self.assertEqual(english.skipped, ({"kind": "message", "block": "text[5]"},))
        for document in (japanese, english):
            self.assertEqual(document.patch(document.rows()), POSITIONAL)

    def test_display_name_key_is_appended_or_replaced(self):
        japanese = ast.read_ast(POSITIONAL)
        rows = japanese.rows()
        rows[1]["name"] = "小遥"
        rows[2]["name"] = "小遥"
        raw = japanese.patch(rows)
        # The separator is copied from the table; a lone pair gets a bare comma.
        self.assertIn('name = {name="遥", en="Haruka", ja="小遥"},'.encode("utf-8"), raw)
        self.assertIn('name = {name="遥",ja="小遥"},'.encode("utf-8"), raw)
        after = ast.read_ast(raw)
        self.assertEqual(after.rows()[1]["name"], "小遥")
        self.assertEqual(after.units[1].identity_name, "遥")
        self.assertEqual(ast.read_ast(raw, language="en").rows()[1]["name"], "Haruka")
        english = ast.read_ast(POSITIONAL, language="en")
        rows = english.rows()
        rows[1]["name"] = "Haru"
        raw = english.patch(rows)
        self.assertIn('name = {name="遥", en="Haru"},'.encode("utf-8"), raw)

    def test_variable_length_edit_keeps_everything_else(self):
        japanese = ast.read_ast(POSITIONAL)
        rows = japanese.rows()
        rows[0]["message"] = "序章：很长的标题"
        rows[1]["message"] = "「早上好」\n第二行"
        rows[3]["message"] = '天亮了，{"gaiji", text="(1)"}真早'
        rows[4]["message"] = "是"
        raw = japanese.patch(rows)
        after = ast.read_ast(raw)
        self.assertEqual(after.rows(), rows)
        text = raw.decode("utf-8")
        for fragment in ('en="Prologue"', '"Morning."', '"Dawn."', '{"Yes", "No"}',
                         'crc ="00000001"', "lane=1", '{"select", file="a", text="はい"}',
                         "label = { scene = { block=1, label=1 }, }"):
            self.assertIn(fragment, text)
        self.assertEqual(ast.read_ast(raw, language="en").rows(),
                         ast.read_ast(POSITIONAL, language="en").rows())

    def test_boxless_entry_takes_no_message(self):
        japanese = ast.read_ast(POSITIONAL)
        rows = japanese.rows()
        rows[2]["message"] = "新增"
        with self.assertRaises(ast.AstError) as caught:
            japanese.patch(rows)
        self.assertEqual(caught.exception.code, "bad_message")

    def test_repeated_entry_keys_are_all_exported(self):
        source = POSITIONAL.replace(b"\t\t[5] = {", b"\t\t[3] = {")
        document = ast.read_ast(source)
        flagged = [u.block for u in document.units if u.duplicate_entry]
        self.assertEqual(flagged, ["text[3]", "text[3]"])
        self.assertEqual(document.patch(document.rows()), source)

    def test_entry_name_rules(self):
        two_boxes = POSITIONAL.replace(
            '"「おはよう」",\r\n\t\t\t\t\t{"rt2"},\r\n\t\t\t\t},'.encode("utf-8"),
            '"「おはよう」",\r\n\t\t\t\t},\r\n\t\t\t\t{\r\n\t\t\t\t\t"b",\r\n\t\t\t\t},'
            .encode("utf-8"))
        no_identity = POSITIONAL.replace('name = {name="遥"}'.encode("utf-8"),
                                         'name = {ja="遥"}'.encode("utf-8"))
        both = POSITIONAL.replace(
            '"朝だ。"'.encode("utf-8"), '"朝だ。"'.encode("utf-8")).replace(
            "\t\t[3] = {\r\n".encode("utf-8"),
            '\t\t[3] = {\r\n\t\t\tname = {name="x"},\r\n'.encode("utf-8")).replace(
            '\t\t\tja = {\r\n\t\t\t\t{\r\n\t\t\t\t\t"朝だ。"'.encode("utf-8"),
            '\t\t\tja = {\r\n\t\t\t\tname = {"name", name="y"},\r\n\t\t\t\t{\r\n'
            '\t\t\t\t\t"朝だ。"'.encode("utf-8"))
        for source, code in ((two_boxes, "ambiguous_name"), (no_identity, "bad_name"),
                             (both, "duplicate_name")):
            self.assertNotEqual(source, POSITIONAL)
            with self.subTest(code=code):
                with self.assertRaises(ast.AstError) as caught:
                    ast.read_ast(source)
                self.assertEqual(caught.exception.code, code)


COMPACT = (
    'ast={{{"savetitle",text="第一話",text_cn="第一话"},{"text"},},{{"text"},},'
    '{{"select",file="a",text="進む",text_cn="前进"},'
    '{"select",name="s1",mw="どうする",mw_cn="怎么办"},},'
    'text={[1]={ja={name={"name",name="遥"},{"「やあ」",{"rt2"},},},'
    'cn={name={"name",name="遥"},{"「嗨」",{"rt2"},},},},'
    '[2]={vo={{"vo",file="v1"},},ja={{"朝。",},},cn={{"早。",},},},},label={},}'
).encode("utf-8")


class CompactLanguageNameTests(unittest.TestCase):
    """Minified files, language-level names and ``text_<lang>`` attributes."""

    def test_rows_and_roundtrip(self):
        japanese = ast.read_ast(COMPACT)
        self.assertEqual(japanese.rows(), [
            {"message": "第一話"}, {"message": "進む"}, {"message": "どうする"},
            {"name": "遥", "message": "「やあ」"}, {"message": "朝。"}])
        self.assertEqual([u.kind for u in japanese.units],
                         ["title", "choice", "prompt", "message", "message"])
        chinese = ast.read_ast(COMPACT, language="cn")
        self.assertEqual([r["message"] for r in chinese.rows()],
                         ["第一话", "前进", "怎么办", "「嗨」", "早。"])
        for document in (japanese, chinese):
            self.assertEqual(document.patch(document.rows()), COMPACT)

    def test_edits_stay_on_one_line_and_in_one_language(self):
        chinese = ast.read_ast(COMPACT, language="cn")
        rows = chinese.rows()
        rows[0]["message"] = "第一话·改"
        rows[1]["message"] = "继续前进"
        rows[3] = {"name": "小遥", "message": "「你好啊」\n第二行"}
        raw = chinese.patch(rows)
        self.assertNotIn(b"\n", raw)
        self.assertIn('cn={name={"name",name="小遥"},{"「你好啊」\\n第二行",{"rt2"},}'
                      .encode("utf-8"), raw)
        self.assertIn('ja={name={"name",name="遥"},{"「やあ」",{"rt2"},}'.encode("utf-8"), raw)
        self.assertEqual(ast.read_ast(raw, language="cn").rows(), rows)
        self.assertEqual(ast.read_ast(raw).rows(), ast.read_ast(COMPACT).rows())

    def test_two_overrides_for_one_language_are_ambiguous(self):
        source = COMPACT.replace(b'text_cn="', b'cn="x",text_cn="', 1)
        with self.assertRaises(ast.AstError) as caught:
            ast.read_ast(source, language="cn")
        self.assertEqual(caught.exception.code, "ambiguous_attribute")


if __name__ == "__main__":
    unittest.main()
