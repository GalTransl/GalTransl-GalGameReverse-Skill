"""Synthetic, offline tests for the fourteen secondary engine algorithm units."""
from dataclasses import replace
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from python.engines import (arcgameengine, circus, cyberworks, hexenhaus, kaguya,
                            mware, propeller, reallive, renpy, shsystem, systemnnn,
                            tmrhiro, whale, yaneurao)


def p32(value):
    return struct.pack("<i", value)


class CircusTests(unittest.TestCase):
    # Actual ffexa profile from msg-tool's pinned info.rs, not a universal key.
    profile = circus.Profile(0x7B69, (0, 0x28), (0x29, 0x2E), (0x2F, 0x49),
                             (0x4A, 0x4D), (0x4E, 0xFF), 0x43, 0x20, 0x4B)

    def test_game_key_token_and_role(self):
        raw = circus.write_text_token("名前", 0x4B, profile=self.profile)
        self.assertEqual(raw[1:-1], bytes((b - 0x20) & 255 for b in "名前".encode("cp932")))
        record = circus.read_token(raw, 0, profile=self.profile)
        self.assertEqual((record["text"], record["role"], record["end"]), ("名前", "name", len(raw)))
        plain = circus.write_text_token("選択", 0x43, profile=self.profile)
        self.assertEqual(circus.read_token(plain, 0, profile=self.profile)["text"], "選択")

    def test_header_and_fixed_tokens(self):
        data = p32(1) + p32(12) + struct.pack("<H", 0x7B69) + b"\0\x01\x02"
        self.assertEqual(circus.read_header(data, profile=self.profile)["code_offset"], 10)
        self.assertEqual(circus.read_token(data, 10, profile=self.profile)["end"], 13)
        newer = p32(1) + p32(3) + b"\0\0" + struct.pack("<H", 0x7B69) + b"\0"
        self.assertEqual(circus.read_header(newer, profile=self.profile)["code_offset"], 13)

    def test_rejections(self):
        for raw in (b"", b"Kabc", b"\0\x01"):
            with self.assertRaises(ValueError):
                circus.read_token(raw, 0, profile=self.profile)
        with self.assertRaises(ValueError):
            circus.write_text_token(" ", 0x4A, profile=self.profile)  # encrypted NUL
        with self.assertRaises(ValueError):
            circus.write_text_token("text", 0x29, profile=self.profile)
        with self.assertRaises(ValueError):
            circus.read_header(b"\0" * 10, profile=self.profile)


class HexenhausTests(unittest.TestCase):
    @staticmethod
    def sample():
        plain = bytes(b ^ 0x53 for b in b"NORI") + b"_beginrp" + b"X" * 8
        plain += "名前「文。」".encode("cp932") + b"SS"
        return bytes(b ^ 0x53 for b in plain)

    def test_fixed_capacity_xor_roundtrip(self):
        data = self.sample()
        slots = hexenhaus.read_slots(data)
        self.assertEqual(len(slots), 1)
        self.assertEqual(slots[0].text, "名前「文。」")
        self.assertEqual(hexenhaus.patch_slots(data, {}), data)
        patched = hexenhaus.patch_slots(data, {0: "名前「字。」"})
        self.assertEqual(len(patched), len(data))
        self.assertEqual(hexenhaus.read_slots(patched)[0].text, "名前「字。」")
        self.assertEqual(hexenhaus.split_name(slots[0].text), {"name": "名前", "message": "「文。」"})

    def test_bounds_and_no_truncation(self):
        data = self.sample()
        for raw in (b"NO", b"NORI", data + b"x"):
            with self.assertRaises(ValueError):
                hexenhaus.read_slots(raw)
        for mapping in ({0: "長" * 100}, {0: "S"}, {8: "短"}):
            with self.assertRaises(ValueError):
                hexenhaus.patch_slots(data, mapping)


class YaneuraoTests(unittest.TestCase):
    def test_length_and_required_lf(self):
        data = yaneurao.write_record(2, "本文")
        self.assertEqual(yaneurao.read_record(data)["text"], "本文\n")
        self.assertEqual(struct.unpack_from("<H", data, 2)[0], 6)
        choice = yaneurao.write_record(0x1E, "選択")
        self.assertEqual(yaneurao.read_record(choice)["text"], "選択")
        resource = struct.pack("<HH", 1, 4) + b"abc\0"
        self.assertEqual(yaneurao.read_record(resource)["role"], "resource")

    def test_invalid_records(self):
        for raw in (b"", b"\2\0\3\0ab\0", b"\2\0\xff\xffx", b"\x90\0\3\0aa\0"):
            with self.assertRaises(ValueError):
                yaneurao.read_record(raw)
        for op, text in ((1, "file"), (2, "a\0b"), (0x1E, ""), (2, "a" * 65535)):
            with self.assertRaises(ValueError):
                yaneurao.write_record(op, text)


class AgeTests(unittest.TestCase):
    def test_encrypted_padding_word_addresses_and_dedup(self):
        pool, addresses = arcgameengine.build_string_pool(["a", "本文", "a", ""])
        self.assertEqual(addresses, (0, 1, 0, 3))
        self.assertEqual(pool[:4], b"\x9e\xff\xff\xff")
        self.assertEqual([arcgameengine.read_pool_string(pool, i) for i in addresses], ["a", "本文", "a", ""])

    def test_bad_pool(self):
        for pool, address in ((b"x", 0), (b"a" * 4, 0), (b"\xff" * 4, 1), (b"\xffx\xff\xff", 0)):
            with self.assertRaises(ValueError):
                arcgameengine.read_pool_string(pool, address)
        with self.assertRaises(ValueError):
            arcgameengine.build_string_pool(["x\0y"])
        with self.assertRaises(UnicodeEncodeError):
            arcgameengine.build_string_pool(["\U0001F600"])


class CyberworksTests(unittest.TestCase):
    def test_s_t_m_and_tail_roundtrip(self):
        blocks = (cyberworks.Block("S", b"S", "本文".encode("utf-16-le"), b"\xfe"),
                  cyberworks.Block("T", b"T1234", "長文\U0001F600".encode("utf-16-le"), b"end"),
                  cyberworks.Block("M", b"", b"", b"\x12opaque"))
        tail = b"\0\0\0\0trailer"
        data = cyberworks.write_blocks(blocks, tail)
        self.assertEqual(cyberworks.read_blocks(data), (blocks, tail))
        self.assertEqual(cyberworks.patch_blocks(data, {}), data)
        changed = cyberworks.patch_blocks(data, {1: "新しい文".encode("utf-16-le")})
        self.assertEqual(cyberworks.read_blocks(changed)[0][1].text.decode("utf-16-le"), "新しい文")
        self.assertEqual(cyberworks.read_blocks(changed)[1], tail)

    def test_s_no_length(self):
        block = cyberworks.Block("S", b"S", b"plain", b"")
        data = cyberworks.write_blocks((block,), encrypted=False, s_has_length=False)
        self.assertEqual(data, p32(6) + b"Splain")
        self.assertEqual(cyberworks.read_blocks(data, encrypted=False, s_has_length=False)[0], (block,))

    def test_bad_boundaries(self):
        for data in (b"x", p32(8) + b"S", p32(5) + b"S" + p32(99), p32(2) + b"T0"):
            with self.assertRaises(ValueError):
                cyberworks.read_blocks(data)
        for block in (cyberworks.Block("S", b"S", b"a" * 256, b""),
                      cyberworks.Block("T", b"T1234", b"a", b"")):
            with self.assertRaises(ValueError):
                cyberworks.write_blocks((block,))
        with self.assertRaises(ValueError):
            cyberworks.read_blocks(b"", s_has_length=False)


class KaguyaTests(unittest.TestCase):
    @staticmethod
    def document():
        return kaguya.Document(kaguya.MAGIC + b"\x01\x53", ("名前",), ("選択％",),
                              (kaguya.Message("本文％", ("voice01", "声\U0001F600")),),
                              (kaguya.Group(0, (0, 0)), kaguya.Group(-1, (0,))))

    def test_ver4_encryption_voice_and_index_roundtrip(self):
        doc = self.document()
        data = kaguya.write_message_dat(doc)
        self.assertEqual(kaguya.read_message_dat(data), doc)
        self.assertEqual(kaguya.write_message_dat(kaguya.read_message_dat(data)), data)
        changed = replace(doc, messages=(replace(doc.messages[0], text="さらに長い本文％"),))
        self.assertEqual(kaguya.read_message_dat(kaguya.write_message_dat(changed)), changed)
        self.assertEqual(changed.groups[0].message_indexes, (0, 0))

    def test_percent_alias(self):
        doc = replace(self.document(), header=kaguya.MAGIC + b"\0\0")
        self.assertIn(b"\xf0\x40", kaguya.write_message_dat(doc))
        # Text fields are length-prefixed; only voice strings are NUL-terminated.
        with_nul = replace(doc, choices=("a\0b",), messages=(kaguya.Message("x\0y"),))
        self.assertEqual(kaguya.read_message_dat(kaguya.write_message_dat(with_nul)), with_nul)

    def test_bad_dat(self):
        data = kaguya.write_message_dat(self.document())
        for raw in (b"[SCR-MESSAGE]ver3.0", data[:-1], data + b"x", data[:21] + p32(-1)):
            with self.assertRaises(ValueError):
                kaguya.read_message_dat(raw)
        for doc in (replace(self.document(), names=("a" * 32768,)),
                    replace(self.document(), groups=(kaguya.Group(9, (0,)),)),
                    replace(self.document(), groups=(kaguya.Group(0, (3,)),))):
            with self.assertRaises(ValueError):
                kaguya.write_message_dat(doc)


class MwareTests(unittest.TestCase):
    def test_tagged_literals(self):
        for value in (None, -31, 1.25, "本文\0後半"):
            data = mware.write_literal(value)
            self.assertEqual(mware.read_literal(data), (value, len(data)))

    def test_shared_literals_are_cloned_per_reference(self):
        result = mware.clone_translated_references(["same", 7], [0, 0, 0], [1, 1, 4], {0: "訳一", 1: "訳二"})
        self.assertEqual(result["values"], ("same", 7, "訳一", "訳二"))
        self.assertEqual(result["indexes"], (2, 3, 0))  # resource ref still original

    def test_bad_literals_and_reference_width(self):
        for data in (b"", p32(9), struct.pack("<Ii", mware.STRING, -1), struct.pack("<Ii", mware.STRING, 10)):
            with self.assertRaises(ValueError):
                mware.read_literal(data)
        with self.assertRaises(ValueError):
            mware.write_literal(True)
        with self.assertRaises(ValueError):
            mware.clone_translated_references(["x"] * 256, [0], [1], {0: "y"})
        with self.assertRaises(ValueError):
            mware.clone_translated_references([1], [0], [4], {0: "y"})


class PropellerTests(unittest.TestCase):
    def test_text_field_toggle_and_length(self):
        text = "【名前】<b>本文</b>,次\n表"
        data = propeller.write_text_field(text)
        self.assertEqual(propeller.read_text_field(data), (text, len(data)))
        self.assertEqual(data[4:7], b"<,>")
        self.assertIn(b"\xfc\xfd", data)
        self.assertEqual(propeller.split_names("【甲】/【乙】本文"), {"names": ("甲", "乙"), "message": "本文"})

    def test_bad_field(self):
        for text in ("_r", "a\0b", "<b>bad", "</i>"):
            with self.assertRaises(ValueError):
                propeller.write_text_field(text)
        for data in (b"", p32(-1), p32(5) + b"x", p32(2) + b"\xfc\xfd"):
            with self.assertRaises(ValueError):
                propeller.read_text_field(data)


class RealLiveTests(unittest.TestCase):
    def test_quote_dbcs_and_instruction_fragment(self):
        text = '表「a"b」'
        data = reallive.quote_text(text)
        self.assertIn("表".encode("cp932"), data)
        self.assertEqual(reallive.unquote_text(data), text)
        self.assertEqual(reallive.LINE_BREAK, b"#\0\3\xc9\0\0\0\0")
        fragment = reallive.assemble_message("甲\n乙", name="名前")
        self.assertTrue(fragment.startswith("【名前】".encode("cp932")))
        self.assertEqual(fragment.count(reallive.LINE_BREAK), 2)

    def test_bad_tokens(self):
        for text in ("", "a\0b", "a\nb", "a\\"):
            with self.assertRaises(ValueError):
                reallive.quote_text(text)
        for data in (b"x", b'"a"b"', b'"a\\q"', b'"\x81"'):
            with self.assertRaises((ValueError, UnicodeDecodeError)):
                reallive.unquote_text(data)
        with self.assertRaises(ValueError):
            reallive.assemble_message("本文", name='bad"name')


class ShSystemTests(unittest.TestCase):
    @staticmethod
    def call(text="名前\\n本文"):
        return b"\x03\x0d\x33\xff" + b"\x02\x01\xff" * 4 + b"\x01" + text.encode("cp932") + b"\0\0"

    def test_specific_scriptcall_export(self):
        data = self.call()
        call = shsystem.read_scriptcall(data, 0)
        self.assertEqual(call["end"], len(data))
        self.assertEqual(call["record"]["name"], "名前")
        self.assertEqual(call["record"]["message"], "本文")
        self.assertIsNone(shsystem.read_scriptcall(data.replace(b"\x0d\x33", b"\x0d\x32", 1), 0)["record"])
        header = b"SHSysSC\0" + (16 + len(data)).to_bytes(3, "big") + b"\0" * 5
        self.assertEqual(shsystem.read_header(header + data)["code_offset"], 16)

    def test_bad_call_and_header(self):
        for data in (b"", b"\x02", self.call()[:-1], b"\x03\x0f\x00"):
            with self.assertRaises(ValueError):
                shsystem.read_scriptcall(data, 0)
        with self.assertRaises(ValueError):
            shsystem.read_header(b"SHSysSC\0" + b"\0" * 8)


class SystemNnnTests(unittest.TestCase):
    @staticmethod
    def nnn():
        header = bytearray(0x50)
        header[:16] = systemnnn.MESSAGE_HEADER
        struct.pack_into("<i", header, 0x3C, 16)
        return bytes(header) + "本文".encode("cp932") + b"\0" + b"x" * 11

    def test_fixed_nnn_patch(self):
        data = self.nnn()
        self.assertEqual(systemnnn.read_nnn_slots(data)[0].text, "本文")
        self.assertEqual(systemnnn.patch_nnn(data, {}), data)
        changed = systemnnn.patch_nnn(data, {0: "新しい文"})
        self.assertEqual(len(changed), len(data))
        self.assertEqual(systemnnn.read_nnn_slots(changed)[0].text, "新しい文")
        self.assertEqual(changed[-3:], b"xxx")

    def test_spt_xor_and_word_units(self):
        plain = struct.pack("<8i", 8, 0x66660001, 0x55550001, 0, 0, 8, 0, 8)
        data = bytes(b ^ 255 for b in plain)
        self.assertEqual(systemnnn.read_spt_items(data)[0]["length_words"], 8)
        self.assertEqual(systemnnn.word_to_offset(7), 28)
        self.assertEqual(systemnnn.offset_to_word(28), 7)
        self.assertEqual(systemnnn.encode_spt_text("本文"), "本文".encode("cp932") + b"\0" * 4)

    def test_bad_nnn_spt(self):
        for data in (b"bad", self.nnn()[:-1]):
            with self.assertRaises(ValueError):
                systemnnn.read_nnn_slots(data)
        with self.assertRaises(ValueError):
            systemnnn.patch_nnn(self.nnn(), {0: "長" * 20})
        for data in (b"", b"xxx", b"\xff" * 32):
            with self.assertRaises(ValueError):
                systemnnn.read_spt_items(data)
        with self.assertRaises(ValueError):
            systemnnn.offset_to_word(6)


class TmrHiroTests(unittest.TestCase):
    def test_complete_text_roundtrip_and_patch(self):
        texts = ("本文", "", "次の文\n改行")
        data = tmrhiro.write_text(texts)
        self.assertEqual(tmrhiro.read_text(data), texts)
        self.assertEqual(tmrhiro.patch_text(data, {}), data)
        changed = tmrhiro.patch_text(data, {0: "もっと長い文"})
        self.assertEqual(tmrhiro.read_text(changed), ("もっと長い文",) + texts[1:])

    def test_signed_length_and_bad_inputs(self):
        for data in (b"x", b"\xff\xff", b"\x04\x00x"):
            with self.assertRaises(ValueError):
                tmrhiro.read_text(data)
        with self.assertRaises(ValueError):
            tmrhiro.write_text(["x" * 32768])
        with self.assertRaises(ValueError):
            tmrhiro.patch_text(b"", {0: "x"})


class WhaleTests(unittest.TestCase):
    def test_names_choices_n_and_line_structure(self):
        script = '*label\r\n【名前,voice01】「本文[n]続き」\r\nSELECT "選択,*go"\r\n日本語\r\nCS "not handled"\r\n'
        targets = whale.extract(script)
        self.assertEqual([t.text for t in targets], ["名前", "本文\n続き", "選択", "日本語"])
        self.assertEqual(whale.patch(script, {}), script)
        changed = whale.patch(script, {1: "新文\n続き", 2: "別選択", 3: "ASCII\nmore"})
        self.assertIn('SELECT "別選択,*go"', changed)
        self.assertIn("　ASCII[n]　more\r\n", changed)
        self.assertIn("【名前,voice01】", changed)

    def test_bad_structure(self):
        for script in ('SELECT "bad"', "【名前】invalid"):
            with self.assertRaises(ValueError):
                whale.extract(script)
        with self.assertRaises(ValueError):
            whale.patch('SELECT "選択,*go"', {0: 'break,"'})
        with self.assertRaises(ValueError):
            whale.patch("本文", {0: "literal[n]"})


class RenpyTests(unittest.TestCase):
    script = '''define e = Character("名前")
image bg = "images/bg.png"
label start:
    # "comment"
    scene bg
    play music "audio/a.ogg"
    e happy "本文 # not comment" # preserve "comment"
    "地の文"
    menu:
        "選択":
            e "選択後"
    python:
        path = "hidden.png"
        "Python docstring"
screen test():
    text "screen string"
translate japanese strings:
    old "old key"
    new "新しい文"
'''

    def test_finite_lexing_not_quote_scan(self):
        targets = renpy.extract(self.script)
        self.assertEqual([t.text for t in targets], ["名前", "本文 # not comment", "地の文", "選択", "選択後", "新しい文"])
        self.assertEqual(targets[1].speaker, "e")
        self.assertEqual(targets[0].role, "name")
        self.assertEqual(renpy.patch(self.script, {}), self.script)

    def test_escaping_patch_and_crlf(self):
        script = self.script.replace("\n", "\r\n")
        changed = renpy.patch(script, {1: '翻訳 "引用" \\ path\n[next] {b}bold{/b}'})
        self.assertEqual(renpy.extract(changed)[1].text, '翻訳 "引用" \\ path\n[next] {b}bold{/b}')
        self.assertIn('image bg = "images/bg.png"\r\n', changed)
        self.assertIn('# preserve "comment"\r\n', changed)
        self.assertIn('old "old key"', changed)
        self.assertEqual(changed.count("\r\n"), script.count("\r\n"))

    def test_external_speaker_whitelist(self):
        script = 'label start:\n    e "本文"\n    voice "voice.ogg"\n'
        self.assertEqual(renpy.extract(script), ())
        self.assertEqual(renpy.extract(script, speakers=("e",))[0].text, "本文")

    def test_reject_compiled_and_unsupported_literals(self):
        with self.assertRaises(ValueError):
            renpy.extract("anything", filename="script.rpyc")
        for script in ('"unterminated', '"""multiline"""', '"bad\\q"', '\t"tab"', '"x\0y"'):
            with self.assertRaises(ValueError):
                renpy.extract(script)
        with self.assertRaises(ValueError):
            renpy.patch(self.script, {99: "x"})


if __name__ == "__main__":
    unittest.main()
