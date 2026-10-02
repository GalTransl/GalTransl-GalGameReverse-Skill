# SPDX-License-Identifier: GPL-3.0-only
"""Synthetic, offline tests for the 15 SExtractor-derived leaf references."""
from pathlib import Path
import importlib
import json
import struct
import sys
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from python.engines import anim, azsystem, blackrainbow, bluegale, cscript, eagls, gsd, gxengine, med, moonhir, nekosdk, nexas, rpgmaker, scrplayer, unity
from python.archives import eagls as eagls_archive


def u32(value):
    return struct.pack("<I", value)


def terminated(raw):
    return u32(len(raw) + 1) + raw + b"\0"


class AnimTests(unittest.TestCase):
    def test_switch_key_order(self):
        key = anim.switch_key(bytes(range(16)), 6)
        self.assertEqual([key[i] for i in (9, 11, 13, 15, 1, 2, 3, 4)], [12, 16, 20, 19, 17, 16, 23, 20])
        self.assertEqual(anim.switch_key(bytes(range(16)), 0)[8], 13)

    def test_crypt_roundtrip_all_branches(self):
        for mode in range(8):
            plain = b"HEAD" + bytes(range(16)) + bytes([mode]) * 64
            cipher = anim.crypt(plain, decrypt=False)
            self.assertEqual(anim.crypt(cipher, decrypt=True), plain)
        plain = b"HEAD" + bytes(range(16)) + bytes(range(32))
        cipher = anim.crypt(plain, decrypt=False)
        self.assertEqual(cipher[20:36], bytes(16))
        self.assertEqual(cipher[36:40], bytes([16, 31, 2, 1]))

    def test_offsets_and_equal_only(self):
        data = bytes(20) + b"w001a\0abc\0"
        token = anim.nul_tokens(data)[1]
        self.assertEqual(token.start, 26)
        self.assertIn(b"xyz", anim.replace_token(data, token, b"xyz"))
        with self.assertRaises(NotImplementedError):
            anim.replace_token(data, token, b"longer")
        with self.assertRaises(ValueError):
            anim.crypt(b"short", decrypt=True)
        sce = bytes(24) + u32(12) + bytes(4) + b"text\0"
        self.assertEqual(anim.text_start(sce, sce=True), 32)


class AZTests(unittest.TestCase):
    @staticmethod
    def fixture(version):
        sig = {0: 0x1F, 1: 0x1B, 2: 0x1E}[version]
        body = bytes([sig]) + bytes(9) + b"\x04\x07N\0" + b"\x05\x07Hi\0"
        return b"ASB\x1a" + bytes(12) + struct.pack("<H", len(body) + 2) + body

    def test_three_profiles(self):
        for profile in (0, 1, 2):
            fields = azsystem.extract_fields(self.fixture(profile), version=profile)
            self.assertEqual([(f.role, f.raw) for f in fields], [("name", b"N"), ("message", b"Hi")])
            self.assertEqual(fields[0].start, 30)

    def test_control_and_choice(self):
        body = b"\x16" + bytes(9) + b"\x02\x06" + b"\x04\x07A\0"
        data = bytes(16) + struct.pack("<H", len(body) + 2) + body
        self.assertEqual(azsystem.extract_fields(data, version=1)[0].role, "choice")
        with self.assertRaises(ValueError):
            azsystem.read_text_operand(b"\0\x07", 0)

    def test_v1_wrapper_and_bounds(self):
        data = self.fixture(1)
        packed = azsystem.encrypt_v1(data)
        self.assertEqual(azsystem.decrypt_v1(packed)[16:], data[16:])
        self.assertEqual(azsystem.encrypt_v1(azsystem.decrypt_v1(packed)), packed)
        with self.assertRaises(ValueError):
            azsystem.decrypt_v1(packed, max_output=1)
        with self.assertRaises(ValueError):
            azsystem.extract_fields(bytes(18), version=1)
        field = azsystem.extract_fields(data, version=1)[0]
        with self.assertRaises(NotImplementedError):
            azsystem.replace_field(data, field, b"long")


class BlackRainbowTests(unittest.TestCase):
    @staticmethod
    def fixture():
        dialogue = bytes(12) + u32(2) + u32(2) + b"R\0" + blackrainbow.xor_text(b"Hi")
        choice = bytes(8) + u32(1) + b"A"
        opaque = b"opaque"
        body = b"".join(u32(k) + u32(len(v)) + v for k, v in ((8, dialogue), (14, choice), (99, opaque)))
        return bytes(0x48) + u32(len(body)) + body

    def test_segments_roundtrip_and_growth(self):
        data = self.fixture()
        self.assertEqual(blackrainbow.replace_texts(data, {}), data)
        result = blackrainbow.replace_texts(data, {0: b"Longer", 1: b"Choice"})
        header, segments = blackrainbow.parse_script(result)
        self.assertEqual(segments[0].role_bytes, b"R\0")
        self.assertEqual(segments[0].text, b"Longer")
        self.assertEqual(segments[2].prefix, b"opaque")
        self.assertEqual(int.from_bytes(header[-4:], "little"), len(result) - 0x4C)

    def test_reject_truncation_and_unknown_target(self):
        with self.assertRaises(ValueError):
            blackrainbow.parse_script(self.fixture()[:-1])
        with self.assertRaises(ValueError):
            blackrainbow.replace_texts(self.fixture(), {2: b"no"})
        with self.assertRaises(ValueError):
            blackrainbow.xor_text(b"x", b"")


class BlueGaleTests(unittest.TestCase):
    def test_index_offsets(self):
        data = b"\t$START\r\n\"text\r\n%END\r\n"
        index = bluegale.build_index(data, capacity=2)
        self.assertEqual(struct.unpack_from("<8sII", index), (b"START\0\0\0", 1, 15))
        self.assertEqual(struct.unpack_from("<8sII", index, 16), (b"END\0\0\0\0\0", 16, 0))
        cipher, full_index = bluegale.package_script(data)
        self.assertEqual(bluegale.xor_bdt(cipher), data)
        self.assertEqual(len(full_index), 4000 * 16)

    def test_labels_never_truncated(self):
        for value in (b"$123456789", b"$A\r\n$A", b"$"):
            with self.assertRaises(ValueError):
                bluegale.build_index(value)
        with self.assertRaises(ValueError):
            bluegale.build_index(b"$A\r\n$B", capacity=1)

    def test_grammar(self):
        line = 'V001 !花子 "こんにちは'
        fields = bluegale.dialogue_spans(line)
        self.assertEqual([(kind, line[a:b]) for kind, a, b in fields], [("name", "花子"), ("message", "こんにちは")])
        self.assertEqual(len(bluegale.dialogue_spans("QPはい,いいえ,戻る")), 3)


class CScriptTests(unittest.TestCase):
    def test_dialogue_profiles(self):
        for version in (1, 10, 11):
            data = u32(0x3F if version == 1 else 0x11) + bytes(17 if version == 1 else 4)
            data += u32(1) + b"N" + (bytes(5) if version == 1 else b"") + u32(2) + b"Hi" + bytes(4)
            record = cscript.parse_record(data, 0, version=version)
            self.assertEqual([f.raw for f in record.fields], [b"N", b"Hi"])
            self.assertIn(b"Yo", cscript.replace_record(data, record, {1: b"Yo"}))
            with self.assertRaises(NotImplementedError):
                cscript.replace_record(data, record, {1: b"Long"})

    def test_v11_choice_extra_words(self):
        data = u32(0x14) + u32(2) + u32(10) + u32(1) + b"A" + u32(99) + u32(1) + b"B"
        record = cscript.parse_record(data, 0, version=11)
        self.assertEqual([f.raw for f in record.fields], [b"A", b"B"])
        with self.assertRaises(ValueError):
            cscript.parse_record(data[:-1], 0, version=11)
        with self.assertRaises(NotImplementedError):
            cscript.unpack_script(data)


class EAGLSTests(unittest.TestCase):
    def test_rand_known_vector(self):
        random = eagls_archive.MSVCRTRand(1)
        self.assertEqual([random.rand() for _ in range(5)], [41, 18467, 6334, 26500, 19169])

    def test_index_and_script_ciphers(self):
        index = bytes(range(64)) + u32(123)
        self.assertEqual(eagls_archive.crypt_index(eagls_archive.crypt_index(index, b"key"), b"key"), index)
        for version in (1, 2):
            data = b"HEADER" + bytes(range(40)) + b"\xff\x80"
            encrypted = eagls.crypt_script(data, text_offset=6, key=b"secret", version=version)
            self.assertEqual(eagls.crypt_script(encrypted, text_offset=6, key=b"secret", version=version), data)
            self.assertEqual(encrypted[:6], b"HEADER")
        self.assertEqual(encrypted[-1], 0x80)
        self.assertEqual(encrypted[7], data[7])

    def test_fix_label_offsets(self):
        label = b"START" + bytes(27) + u32(0)
        data = label + bytes(36) + b"intro\r\n$START\r\ntext" + b"\0"
        result = eagls.fix_label_offsets(data, text_offset=72, version=1)
        self.assertEqual(eagls.read_labels(result, text_offset=72), ((b"START", 7),))
        self.assertEqual(result[72:], data[72:])
        with self.assertRaises(ValueError):
            eagls.fix_label_offsets(data.replace(b"$START", b"$STARTED"), text_offset=72, version=1)

    def test_script_grammar(self):
        line = '#花子&123"こんにちは"'
        self.assertEqual([line[a:b] for _, a, b in eagls.dialogue_spans(line)], ["花子", "こんにちは"])


class GSDTests(unittest.TestCase):
    @staticmethod
    def fixture(profile):
        head = bytearray(0x40)
        head[:16] = struct.pack("<IIII", 1, 0, 0, 0xFFFFFFFF if profile == 1 else 0)
        head[0x28:0x2C] = u32(2)
        cells = [u32(7) + u32(0) + b"A\0\0\0"]
        if profile == 2:
            cells.append(u32(5) + u32(9) + u32(10))
        cells.append(u32(8 if profile == 1 else 10) + bytes(8))
        head[0x34:0x38] = u32(len(cells))
        return bytes(head) + b"".join(cells)

    def test_cells_controls_and_name_id(self):
        dialogue = gsd.read_dialogue(self.fixture(2), 0, profile=2)
        self.assertEqual(dialogue.name_id, 2)
        self.assertEqual(dialogue.text_runs()[0], "A")
        self.assertIsInstance(dialogue.text_runs()[1], gsd.Cell)
        self.assertEqual(dialogue.cells[1].raw, struct.pack("<III", 5, 9, 10))
        self.assertEqual(gsd.read_dialogue(self.fixture(1), 0, profile=1).text_runs(), ("A",))

    def test_global_names_and_limits(self):
        data = bytes(8) + u32(1) + b"Hanako\0" + bytes(0x104 - 7)
        self.assertEqual(gsd.read_global_names(data, skip_sections=0), ("Hanako",))
        with self.assertRaises(ValueError):
            gsd.read_dialogue(self.fixture(1)[:-1], 0, profile=1)
        with self.assertRaises(NotImplementedError):
            gsd.read_dialogue(self.fixture(1), 0, profile=3)
        with self.assertRaises(NotImplementedError):
            gsd.write_spt(b"")


class GxTests(unittest.TestCase):
    def test_big_endian_fields_and_zlib(self):
        text = "花子".encode()
        body = b"prefix" + b"\x08\x1a" + struct.pack(">I", len(text)) + text + b"suffix"
        data = bytes(20) + struct.pack("<II", len(body), len(body)) + body
        field = gxengine.scan_fields(gxengine.unpack_mwb(data))[0]
        self.assertEqual(field.raw, text)
        rebuilt = gxengine.replace_fields(data, {0: "こんにちは"})
        newbody = gxengine.unpack_mwb(rebuilt)
        self.assertTrue(newbody.endswith(b"suffix"))
        self.assertEqual(gxengine.scan_fields(newbody)[0].raw.decode(), "こんにちは")

    def test_bad_field_and_bomb_limit(self):
        with self.assertRaises(ValueError):
            gxengine.scan_fields(b"\x08\x1a\0\0\0\x09x")
        payload = b"X" * 1000
        packed = zlib.compress(payload)
        data = bytes(20) + struct.pack("<II", len(payload), len(packed)) + packed
        with self.assertRaises(ValueError):
            gxengine.unpack_mwb(data, max_output=100)


class MEDTests(unittest.TestCase):
    def test_boundary_and_nuls(self):
        header = bytearray(20)
        header[4:8] = u32(2)
        header[10:12] = struct.pack("<H", 1)
        data = header + b"A\0\0B\0"
        data[:4] = u32(len(data) - 16)
        table = med.parse_table(bytes(data))
        self.assertEqual(table.start, 20)
        self.assertEqual(table.strings, (b"A", b"", b"B", b""))
        self.assertEqual(med.replace_strings(bytes(data), {}), data)
        with self.assertRaises(NotImplementedError):
            med.replace_strings(bytes(data), {0: b"XX"})
        self.assertEqual(med.classify_text("【花子】"), "name")
        with self.assertRaises(ValueError):
            med.parse_table(bytes(16))


class MoonHirTests(unittest.TestCase):
    def test_literal_writer_all_tail_lengths(self):
        for size in (0, 1, 2, 255, 256, 257, 768, 1024, 1025):
            raw = bytes(i % 256 for i in range(size))
            self.assertEqual(moonhir.unpack_fbx(moonhir.pack_fbx_literal(raw)), raw)

    def test_short_long_backrefs_and_extended_literal(self):
        self.assertEqual(moonhir.decode_payload(b"\x08A\0\0", 5), b"A" * 5)
        self.assertEqual(moonhir.decode_payload(b"\x0cA\x40\0\0", 37), b"A" * 37)
        self.assertEqual(moonhir.decode_payload(b"\x03\0\0" + b"X" * 258, 258), b"X" * 258)
        self.assertEqual(moonhir.decode_payload(b"\x03\xc0\0A", 1), b"A")

    def test_strict_decoder(self):
        for packed, size in ((b"\x02\0\0", 4), (b"\x08A\0\0", 4), (b"\x03\x80", 1), (b"\0", 1)):
            with self.assertRaises(ValueError):
                moonhir.decode_payload(packed, size)
        with self.assertRaises(ValueError):
            moonhir.decode_payload(b"\0A", 100, max_output=2)

    def test_first_block_and_no_relocation(self):
        data = bytes(8) + u32(16) + u32(4) + b"A\0B\0" + b"TAIL"
        self.assertEqual(moonhir.text_block(data), (16, 20, b"A\0B\0"))
        self.assertTrue(moonhir.replace_text_block(data, b"C\0D\0").endswith(b"TAIL"))
        with self.assertRaises(NotImplementedError):
            moonhir.replace_text_block(data, b"AB\0\0")


class NekoTests(unittest.TestCase):
    @staticmethod
    def fixture():
        cmd = nekosdk.COMMANDS[0]
        return nekosdk.MAGIC + bytes(4) + terminated(cmd) + terminated(b"N") + terminated(b"Hi") + b"OPAQUE_CHOICE"

    def test_name_message_and_lengths(self):
        data = self.fixture()
        fields = nekosdk.extract_fields(data)
        self.assertEqual([(f.role, f.raw) for f in fields], [("name", b"N"), ("message", b"Hi")])
        rebuilt = nekosdk.replace_fields(data, {0: b"Name", 1: b"Longer"})
        self.assertEqual([f.raw for f in nekosdk.extract_fields(rebuilt)], [b"Name", b"Longer"])
        self.assertTrue(rebuilt.endswith(b"OPAQUE_CHOICE"))
        self.assertEqual(nekosdk.replace_fields(data, {}), data)

    def test_malformed_and_signature(self):
        with self.assertRaises(ValueError):
            nekosdk.extract_fields(b"invalid")
        data = self.fixture()
        with self.assertRaises(ValueError):
            nekosdk.replace_fields(data, {0: b"a\0b"})
        with self.assertRaises(ValueError):
            nekosdk.extract_fields(data.replace(terminated(b"Hi"), u32(500) + b"Hi\0"))


class NexasTests(unittest.TestCase):
    def test_context_and_lexical_preservation(self):
        asm = "{0x0000}\tPUSH\t0x0\r\n{0x0001}\tLOAD_STRING\t'花子'\r\n{0x0002}\tLOAD_STRING\t'こんにちは\\n世界'\r\n"
        fields = nexas.extract_fields(asm)
        self.assertEqual([f.role for f in fields], ["name", "message"])
        result = nexas.replace_fields(asm, {0: "華子"})
        self.assertEqual(result, asm.replace("花子", "華子"))
        self.assertEqual(nexas.extract_fields("{0x0000}\tLOAD_STRING\t'花子'\n")[0].role, "message")

    def test_quotes_and_unimplemented_writer(self):
        asm = "{0x0001}\tSPECIAL_TEXT\t0x1\t'原文'\n"
        with self.assertRaises(ValueError):
            nexas.replace_fields(asm, {0: "bad'quote"})
        with self.assertRaises(NotImplementedError):
            nexas.assemble_bin(asm, dat0=b"original")


class RPGTests(unittest.TestCase):
    def test_event_codes_and_nested_choice_types(self):
        root = {"events": [None, {"list": [
            {"code": 401, "indent": 0, "parameters": ["Hello\\V[1]"]},
            {"code": 102, "indent": 0, "parameters": [["Yes", "No"], 0, 1, 2, 0]},
            {"code": 101, "parameters": ["FaceName", 0, 0, 2]},
            {"code": 355, "parameters": ["dangerous_code()"]},
            {"code": 320, "parameters": [1, "Actor"]}]}], "name": "DatabaseName"}
        fields = rpgmaker.extract_fields(root, keys=("name",))
        self.assertEqual([f.code for f in fields], [401, 102, 102, 320, None])
        path = fields[0].path
        result = rpgmaker.apply_translations(root, {path: "你好\\V[1]"}, keys=("name",))
        self.assertEqual(root["events"][1]["list"][0]["parameters"][0], "Hello\\V[1]")
        self.assertEqual(result["events"][1]["list"][0]["code"], 401)
        self.assertIsInstance(result["events"][1]["list"][1]["parameters"][0], list)
        with self.assertRaises(ValueError):
            rpgmaker.apply_translations(root, {("events", 1, "list", 0, "code"): "401"})

    def test_embedded_json_boundaries_preserve_native_types(self):
        root = {"plugin": '{ "native": [1, {"ok": true}], "inner": "{\\"name\\":\\"Old\\"}" }'}
        expanded, boundaries = rpgmaker.expand_json_strings(root, (("plugin",), ("plugin", "inner")))
        self.assertEqual(rpgmaker.restore_json_strings(expanded, boundaries), root)
        expanded["plugin"]["inner"]["name"] = "New"
        restored = rpgmaker.restore_json_strings(expanded, boundaries)
        decoded = json.loads(restored["plugin"])
        self.assertIsInstance(decoded["native"], list)
        self.assertIsInstance(decoded["native"][1], dict)
        self.assertIsInstance(decoded["inner"], str)
        self.assertEqual(json.loads(decoded["inner"])["name"], "New")

    def test_vx_tags_and_bytes_are_not_lost(self):
        root = {"ruby_class": "RPG::Map", "@list": [
            {"ruby_class": "RPG::EventCommand", "@code": 401, "@parameters": [{"bytes_str": "Hello"}]}],
            "@table": {"class": "UserDef", "ruby_class": "Table", "data": {"bytes": "AA=="}},
            "@symbol": {"class": "Symbol", "name": "DO_NOT_TRANSLATE"}}
        fields = rpgmaker.extract_fields(root, variant="vx", keys=("name",))
        self.assertEqual(len(fields), 1)
        result = rpgmaker.apply_translations(root, {fields[0].path: "你好"}, variant="vx")
        self.assertEqual(result["@table"], root["@table"])
        self.assertEqual(result["@symbol"], root["@symbol"])
        self.assertEqual(result["@list"][0]["@code"], 401)
        with self.assertRaises(NotImplementedError):
            rpgmaker.load_ruby_marshal(b"\x04\x08")
        with self.assertRaises(NotImplementedError):
            rpgmaker.dump_ruby_marshal(result)

    def test_bad_structures(self):
        with self.assertRaises(ValueError):
            rpgmaker.extract_fields({"code": True, "parameters": []})
        with self.assertRaises(ValueError):
            rpgmaker.extract_fields({"code": 102, "parameters": ["not an array"]})
        with self.assertRaises(ValueError):
            rpgmaker.expand_json_strings({"a": {}}, (("a",),))


class ScrPlayerTests(unittest.TestCase):
    @staticmethod
    def fixture(unknown=False):
        # refs: name offset 0, voice offset 2 (-1), message offset 8
        command = bytes([0x5E, 16, 0, 0]) + u32(0) + u32(2) + u32(8)
        if unknown:
            command += b"\xff\x04\0\0"
        strings = b"N\0voice\0Hi\0"
        return bytes(16) + u32(len(command)) + command + u32(len(strings)) + bytes(b ^ 0x7F for b in strings)

    def test_relocates_nontranslated_voice_pointer(self):
        data = self.fixture()
        script = scrplayer.parse_script(data, version=1)
        self.assertEqual([ref.translate for ref in script.references], [True, False, True])
        result = scrplayer.replace_strings(data, {0: b"LongName", 2: b"Long message"}, version=1)
        parsed = scrplayer.parse_script(result, version=1)
        self.assertEqual(parsed.strings[:3], (b"LongName", b"voice", b"Long message"))
        self.assertEqual(struct.unpack_from("<I", parsed.commands, 8)[0], 9)
        self.assertEqual(struct.unpack_from("<I", parsed.commands, 12)[0], 15)
        self.assertEqual(scrplayer.replace_strings(data, {}, version=1), data)

    def test_unknown_commands_block_variable_length(self):
        data = self.fixture(True)
        with self.assertRaises(NotImplementedError):
            scrplayer.replace_strings(data, {0: b"Long"}, version=1)
        self.assertEqual(scrplayer.parse_script(scrplayer.replace_strings(data, {0: b"X"}, version=1), version=1).strings[0], b"X")
        with self.assertRaises(ValueError):
            scrplayer.parse_script(data, version=0)
        with self.assertRaises(ValueError):
            scrplayer.parse_script(self.fixture()[:-1], version=1)

    def test_profile_three_name_is_numeric(self):
        command = b"\x5e\x14\0\0" + u32(777) + u32(888) + u32(0xFFFFFFFF) + u32(0)
        raw = b"Hi\0"
        data = bytes(16) + u32(len(command)) + command + u32(3) + bytes(b ^ 127 for b in raw)
        refs = scrplayer.parse_script(data, version=3).references
        self.assertEqual([(r.role, r.string_index) for r in refs], [("message", 0)])


class UnityTests(unittest.TestCase):
    def test_byte_length_and_padding(self):
        record = unity.encode_aligned_string("花子")
        self.assertEqual(record[:4], u32(6))
        self.assertEqual(record[-2:], b"\0\0")
        data = record + unity.encode_aligned_string("next")
        parsed = unity.decode_aligned_string(data, 0)
        self.assertEqual(parsed.next_offset, 12)
        self.assertEqual(unity.decode_aligned_string(data, parsed.next_offset).text, "next")
        patched = unity.replace_aligned_string(data, 0, "1234567")
        self.assertEqual(unity.decode_aligned_string(patched, 0).text, "1234567")
        self.assertEqual(patched[12:], data[12:])

    def test_refuse_outer_relocation_and_bad_padding(self):
        data = unity.encode_aligned_string("a")
        with self.assertRaises(NotImplementedError):
            unity.replace_aligned_string(data, 0, "longer than four")
        with self.assertRaises(ValueError):
            unity.decode_aligned_string(data[:-1] + b"X", 0)
        with self.assertRaises(ValueError):
            unity.decode_aligned_string(data, -1)
        self.assertEqual(unity.decode_aligned_string(unity.encode_aligned_string(""), 0).text, "")


class AdditionalBoundaryTests(unittest.TestCase):
    def test_blackrainbow_save_titles(self):
        body = b"".join(u32(kind) + u32(5) + u32(1) + b"T" for kind in (0x1D, 0x1E))
        data = bytes(0x48) + u32(len(body)) + body
        result = blackrainbow.replace_texts(data, {0: b"Save title", 1: b"Other title"})
        self.assertEqual([s.text for s in blackrainbow.parse_script(result)[1]], [b"Save title", b"Other title"])

    def test_cscript_old_choice_prefixes(self):
        data = u32(0x15) + bytes(8) + u32(2) + bytes(17)
        data += u32(1) + b"A" + bytes(5) + u32(1) + b"B"
        record = cscript.parse_record(data, 0, version=1)
        self.assertEqual([(f.role, f.raw) for f in record.fields], [("choice", b"A"), ("choice", b"B")])
        self.assertEqual(cscript.replace_record(data, record, {}), data)

    def test_eagls_alis_label_width(self):
        data = b"LABEL" + bytes(127) + u32(0) + bytes(136) + b"preamble\r\n$LABEL\r\n" + b"\0\x80"
        result = eagls.fix_label_offsets(data, text_offset=272, label_size=136, version=2)
        self.assertEqual(eagls.read_labels(result, text_offset=272, label_size=136), ((b"LABEL", 10),))
        with self.assertRaises(ValueError):
            eagls.read_labels(result, text_offset=136, label_size=136)

    def test_gsd_global_section_skipping(self):
        command = u32(2) + b"aa" + u32(1) + b"b" + bytes(0x8C)
        data = bytes(8) + u32(1) + command + u32(1) + b"Name\0" + bytes(0x104 - 5)
        self.assertEqual(gsd.read_global_names(data, skip_sections=1), ("Name",))
        with self.assertRaises(ValueError):
            gsd.read_global_names(data[:-1], skip_sections=1)

    def test_gsd_strict_character_decode(self):
        data = bytearray(GSDTests.fixture(1))
        data[0x48:0x4C] = b"\x81\0\0\0"
        dialogue = gsd.read_dialogue(bytes(data), 0, profile=1)
        with self.assertRaises(UnicodeDecodeError):
            dialogue.text_runs()

    def test_gx_control_field_and_raw_wrapper(self):
        payload = b"\x05\x1a\0\0\0\x01X"
        data = bytes(20) + u32(len(payload)) + u32(len(payload)) + payload
        self.assertEqual(gxengine.scan_fields(payload)[0].kind, 5)
        self.assertEqual(gxengine.replace_fields(data, {}, compress=False), data)
        with self.assertRaises(ValueError):
            gxengine.replace_fields(data, {0: "X" * 0x300})

    def test_neko_log_command_and_empty_name(self):
        cmd = nekosdk.COMMANDS[1]
        data = nekosdk.MAGIC + u32(len(cmd)) + cmd + terminated(b"") + terminated(b"message\r\nline")
        fields = nekosdk.extract_fields(data)
        self.assertEqual([f.raw for f in fields], [b"", b"message\r\nline"])
        self.assertEqual(nekosdk.replace_fields(data, {}), data)

    def test_scrplayer_all_message_profiles(self):
        for version, config in scrplayer.PROFILES.items():
            kinds = config[0x5E]
            params, texts = [], []
            for kind in kinds:
                if kind:
                    params.append(u32(2 * len(texts)))
                    texts.append(bytes([65 + len(texts)]))
                else:
                    params.append(u32(99))
            command = bytes([0x5E, 4 + 4 * len(kinds), 0, 0]) + b"".join(params)
            plain = b"\0".join(texts) + b"\0"
            data = bytes(16) + u32(len(command)) + command + u32(len(plain)) + bytes(b ^ 127 for b in plain)
            parsed = scrplayer.parse_script(data, version=version)
            target = next(r.string_index for r in parsed.references if r.translate)
            result = scrplayer.replace_strings(data, {target: b"LONG"}, version=version)
            self.assertEqual(scrplayer.parse_script(result, version=version).strings[target], b"LONG")

    def test_structured_cycles_and_invalid_embedded_json(self):
        cycle = []
        cycle.append(cycle)
        with self.assertRaises(ValueError):
            rpgmaker.extract_fields(cycle)
        with self.assertRaises(ValueError):
            rpgmaker.expand_json_strings({"a": "[broken"}, (("a",),))
        with self.assertRaises(TypeError):
            root = {"code": 401, "parameters": ["Hi"]}
            rpgmaker.apply_translations(root, {("parameters", 0): 12})

    def test_truncated_wrappers_and_stale_anim_field(self):
        data = bytes(20) + b"abc\0"
        token = anim.nul_tokens(data)[0]
        with self.assertRaises(ValueError):
            anim.replace_token(data.replace(b"abc", b"xyz"), token, b"def")
        with self.assertRaises(ValueError):
            moonhir.unpack_fbx(moonhir.pack_fbx_literal(b"abc")[:-1])
        with self.assertRaises(ValueError):
            unity.decode_aligned_string(unity.encode_aligned_string("abcdefgh"), 0, max_length=1)


class IsolationTests(unittest.TestCase):
    def test_modules_only_use_standard_library_or_bundled_helper_and_no_import_io(self):
        import ast
        base = Path(__file__).resolve().parents[1] / "python" / "engines"
        names = ("anim", "azsystem", "blackrainbow", "bluegale", "cscript", "eagls", "gsd", "gxengine", "med", "moonhir", "nekosdk", "nexas", "rpgmaker", "scrplayer", "unity")
        for name in names:
            module = importlib.import_module("python.engines." + name)
            self.assertEqual(Path(module.__file__).resolve(), (base / (name + ".py")).resolve())
            tree = ast.parse((base / (name + ".py")).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertIn(alias.name.split(".")[0], sys.stdlib_module_names)
                elif isinstance(node, ast.ImportFrom):
                    if name == "eagls" and node.level == 2 and node.module == "archives.eagls":
                        self.assertEqual([alias.name for alias in node.names], ["MSVCRTRand"])
                        helper = importlib.import_module("python.archives.eagls")
                        self.assertEqual(Path(helper.__file__).resolve(),
                                         (base.parent / "archives" / "eagls.py").resolve())
                    else:
                        self.assertEqual(node.level, 0)
                        self.assertIn(node.module.split(".")[0], sys.stdlib_module_names)
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, {"open", "eval", "exec", "__import__"})


if __name__ == "__main__":
    unittest.main()
