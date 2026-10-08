"""Synthetic-only contract tests; no commercial assets, subprocesses or network."""
from pathlib import Path
import importlib
import json
import struct
import sys
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from python.engines import (artemis, bgi, catsystem2, entis_gls, escude, exhibit,
                            favorite, kirikiri, majiro, musica, qlie, silky,
                            softpal, willplus, yuris)


def make_map(items):
    out = bytearray(struct.pack("<I", len(items)) + b"\0" * (8 * len(items)))
    for row, (index, text) in enumerate(items):
        struct.pack_into("<II", out, 4 + row * 8, index, len(out))
        out.extend(text.encode("utf-16-le") + b"\0\0")
    return bytes(out)


def make_cst(items, compressed=True):
    prefix = b"screen!!"
    pool, offsets = bytearray(), []
    for kind, text in items:
        offsets.append(len(pool))
        pool.extend(bytes((1, kind)) + text.encode("cp932") + b"\0")
    table = b"".join(struct.pack("<I", offset) for offset in offsets)
    raw = struct.pack("<IIII", len(prefix + table + pool), 1, 8, 8 + len(table)) + prefix + table + pool
    packed = zlib.compress(raw) if compressed else raw
    return b"CatScene" + struct.pack("<II", len(packed) if compressed else 0, len(raw)) + packed


def make_bgi(strings, terminal=0x140):
    base = len(bgi.MAGIC) + 4
    code_size = 8 * len(strings) + 8
    pool = bytearray()
    code = bytearray()
    for text in strings:
        code.extend(struct.pack("<II", 3, code_size + len(pool)))
        pool.extend(text.encode("cp932") + b"\0")
    code.extend(struct.pack("<II", terminal, 0x1B))
    return bgi.MAGIC + struct.pack("<I", 4) + code + pool, code_size, base


def make_escr(strings, vm=b"\x00\x05\x01"):
    pool, offsets = bytearray(), []
    for raw in strings:
        offsets.append(len(pool))
        pool.extend(raw + b"\0")
    return (b"ESCR1_00" + struct.pack("<I", len(strings))
            + b"".join(struct.pack("<I", offset) for offset in offsets)
            + struct.pack("<I", len(vm)) + vm + struct.pack("<I", 0x12345678) + pool)


class SilkyTests(unittest.TestCase):
    def test_noncontiguous_indices_empty_and_all_pointers(self):
        data = make_map([(17, "A"), (902, ""), (3, "B")])
        old = silky.read_map(data)
        patched = silky.patch_map(data, {0: "ABCDE"})
        new = silky.read_map(patched)
        self.assertEqual([r.index for r in new], [17, 902, 3])
        self.assertEqual([r.text for r in new], ["ABCDE", "", "B"])
        self.assertEqual(new[1].offset, old[1].offset + 8)
        self.assertEqual(new[2].offset, old[2].offset + 8)

    def test_utf16_alignment_and_non_bmp(self):
        data = make_map([(8, "A"), (5, "𠮷")])
        self.assertEqual([r.text for r in silky.read_map(data)], ["A", "𠮷"])
        self.assertEqual(silky.patch_map(data, {}), data)

    def test_unsorted_table_and_trailer(self):
        data = bytearray(make_map([(100, "A"), (2, "BC")]))
        first, second = data[4:12], data[12:20]
        data[4:12], data[12:20] = second, first
        data.extend(b"TRAIL")
        patched = silky.patch_map(bytes(data), {0: "LONGER"})
        self.assertEqual([r.text for r in silky.read_map(patched)], ["LONGER", "A"])
        self.assertTrue(patched.endswith(b"TRAIL"))

    def test_alias_conflict_and_shared_pointer(self):
        data = bytearray(make_map([(1, "A"), (77, "")]))
        offset, = struct.unpack_from("<I", data, 8)
        struct.pack_into("<I", data, 16, offset)
        with self.assertRaises(ValueError):
            silky.patch_map(bytes(data), {0: "B"})
        out = silky.patch_map(bytes(data), {0: "B", 1: "B"})
        rows = silky.read_map(out)
        self.assertEqual(rows[0].offset, rows[1].offset)

    def test_reject_interior_and_missing_nul(self):
        data = bytearray(make_map([(1, "AB"), (2, "C")]))
        offset, = struct.unpack_from("<I", data, 8)
        struct.pack_into("<I", data, 16, offset + 2)
        with self.assertRaises(ValueError):
            silky.read_map(bytes(data))
        with self.assertRaises(ValueError):
            silky.read_map(make_map([(1, "A")])[:-2])


class ArtemisTests(unittest.TestCase):
    def sample(self):
        return (artemis.Label("start"), artemis.Command("name", 47, (("0", "Alice"),)),
                artemis.Command("ruby", 48, (("text", "かん"),)),
                artemis.Command("print", 48, (("data", "漢"), ("other", "keep"))),
                artemis.Command("/ruby", 48),
                artemis.Command("sel_text", 49, (("text", "yes"),)),
                artemis.Command("unknown", 50, (("$str20", "do not edit"),)))

    def test_tree_noop_preserves_line_numbers_order(self):
        tree = self.sample()
        data = artemis.write_asb(tree)
        self.assertEqual(artemis.read_asb(data), tree)
        self.assertEqual(artemis.patch_asb(data, {}), data)

    def test_text_fields_include_name_ruby_choice(self):
        self.assertEqual([f.kind for f in artemis.text_fields(self.sample())],
                         ["name", "ruby_reading", "message", "choice"])

    def test_growth_keeps_unknowns_and_utf8_lengths(self):
        tree = self.sample()
        data = artemis.write_asb(tree)
        out = artemis.read_asb(artemis.patch_asb(data, {(3, "data"): "翻訳後の長文"}))
        self.assertEqual(dict(out[3].attributes)["data"], "翻訳後の長文")
        self.assertEqual(out[-1], tree[-1])
        self.assertEqual(out[3].line_number, 48)

    def test_name_override_preserves_identity_and_numbered_slots(self):
        for attrs in ((("0", "actor_key"),),
                      (("1", "Shown"), ("0", "actor_key")),
                      (("0", "actor_key"), ("1", "alias"), ("2", "Shown"))):
            tree = (artemis.Command("name", 42, attrs), *self.sample()[2:])
            raw = artemis.write_asb(tree)
            field = artemis.text_fields(artemis.read_asb(raw))[0]
            self.assertEqual(field.attribute, str(len(attrs) - 1))
            self.assertEqual(artemis.patch_asb(raw, {(0, field.attribute): field.text}), raw)
            result = artemis.patch_asb(raw, {(0, field.attribute): "更长的显示姓名"})
            parsed = artemis.read_asb(result)
            self.assertEqual(dict(parsed[0].attributes)["0"], "actor_key")
            self.assertEqual(artemis.text_fields(parsed)[0].text, "更长的显示姓名")
            self.assertEqual(parsed[0].line_number, 42)
            self.assertEqual(parsed[1:], tree[1:])
            if len(attrs) > 1:
                self.assertEqual(tuple(k for k, _ in parsed[0].attributes), tuple(k for k, _ in attrs))
                with self.assertRaises(ValueError):
                    artemis.patch_asb(raw, {(0, "0"): "wrong identity"})

    def test_unknown_name_slot_layout_is_refused(self):
        for attrs in ((), (("1", "name"),), (("0", "key"), ("2", "name")),
                      (("0", "key"), ("display", "name"))):
            raw = artemis.write_asb((artemis.Command("name", 1, attrs),))
            with self.assertRaises(ValueError):
                artemis.patch_asb(raw, {})

    def test_reject_unknown_type_and_trailer(self):
        data = artemis.write_asb((artemis.Label("x"),))
        with self.assertRaises(ValueError):
            artemis.read_asb(data + b"?")
        with self.assertRaises(ValueError):
            artemis.read_asb(data[:9] + struct.pack("<I", 2) + data[13:])

    def test_reject_unknown_field_nul_duplicate(self):
        data = artemis.write_asb(self.sample())
        with self.assertRaises(ValueError):
            artemis.patch_asb(data, {(6, "$str20"): "oops"})
        with self.assertRaises(ValueError):
            artemis.patch_asb(data, {(3, "data"): "A\0B"})
        with self.assertRaises(ValueError):
            artemis.write_asb((artemis.Command("x", 0, (("a", "1"), ("a", "2"))),))


class EntisTests(unittest.TestCase):
    def test_plain_and_select(self):
        xml = '<xscript><code><msg name="A" text="Hello"/><select><menu text="Yes"/></select></code></xscript>'
        records = entis_gls.extract_srcxml(xml)
        self.assertEqual([(r.name, r.message) for r in records], [("A", "Hello"), (None, "Yes")])
        patched = entis_gls.patch_srcxml(xml, {0: {"message": 'A & "B"', "name": "B"}})
        self.assertEqual(entis_gls.extract_srcxml(patched)[0].message, 'A & "B"')

    def test_language_and_other_attributes_survive(self):
        xml = '<xscript><code><!--keep--><msg name_ja="A" text_ja="旧" name_en="X" text_en="old" voice="v"/></code></xscript>'
        with self.assertRaises(ValueError):
            entis_gls.extract_srcxml(xml)
        out = entis_gls.patch_srcxml(xml, {0: {"message": "新"}}, "ja")
        self.assertIn('text_en="old"', out)
        self.assertIn('voice="v"', out)
        self.assertIn('<!--keep-->', out)

    def test_first_localized_choice_autodetection(self):
        xml = '<xscript><code><select><menu text_ja="選択"/></select></code></xscript>'
        self.assertEqual(entis_gls.extract_srcxml(xml)[0].message, "選択")

    def test_empty_name_record_and_noop(self):
        xml = '<xscript><code><msg name="" text=""/></code></xscript>'
        record = entis_gls.extract_srcxml(xml)[0]
        self.assertIsNone(record.name)
        self.assertTrue(record.name_writable)
        self.assertEqual(entis_gls.patch_srcxml(xml, {}), xml)

    def test_reject_dtd_missing_language_and_absent_name(self):
        with self.assertRaises(ValueError):
            entis_gls.extract_srcxml('<!DOCTYPE xscript [<!ENTITY x "x">]><xscript/>')
        xml = '<xscript><code><msg text="x"/></code></xscript>'
        with self.assertRaises(ValueError):
            entis_gls.extract_srcxml(xml, "ja")
        with self.assertRaises(ValueError):
            entis_gls.patch_srcxml(xml, {0: {"name": "invented"}})
        with self.assertRaises(ValueError):
            entis_gls.patch_srcxml(xml, {0: {"message": "\x01"}})


class CatSystemTests(unittest.TestCase):
    def test_compressed_and_uncompressed(self):
        for packed in (True, False):
            data = make_cst([(0x21, "A"), (0x20, "hello"), (0x30, "1 label choice")], packed)
            scene = catsystem2.read_cst(data)
            self.assertEqual([r.kind for r in scene.records], [0x21, 0x20, 0x30])
            self.assertEqual(scene.compressed, packed)
            self.assertEqual(catsystem2.patch_cst(data, {}), data)

    def test_append_and_repoint_preserve_other_records(self):
        data = make_cst([(0x20, "A"), (0x20, ""), (0xF0, "file")])
        old = catsystem2.read_cst(data)
        new = catsystem2.read_cst(catsystem2.patch_cst(data, {0: "Much longer\\ntext"}))
        self.assertEqual(new.records[0].text, "Much longer\\ntext")
        self.assertGreaterEqual(new.records[0].offset, len(old.payload))
        self.assertEqual(new.records[1:], old.records[1:])
        self.assertEqual(new.payload[16:24], old.payload[16:24])

    def test_reject_corrupt_size_and_stream(self):
        data = make_cst([(0x20, "A")])
        with self.assertRaises(ValueError):
            catsystem2.read_cst(data[:-1])
        with self.assertRaises(ValueError):
            catsystem2.read_cst(data, max_output=16)
        bad = bytearray(data)
        bad[-1] ^= 1
        with self.assertRaises(ValueError):
            catsystem2.read_cst(bytes(bad))

    def test_reject_nontext_and_embedded_nul(self):
        data = make_cst([(0x30, "command"), (0x20, "A")])
        with self.assertRaises(ValueError):
            catsystem2.patch_cst(data, {0: "not a command translator"})
        with self.assertRaises(ValueError):
            catsystem2.patch_cst(data, {1: "bad\0"})


class TextDialectTests(unittest.TestCase):
    def test_kag_names_blocks_and_literal_spans(self):
        text = '#Alice\r\nHello[r]world[l]\r\n[iscript]\r\n"not dialogue"\r\n[endscript]\r\n*label|Title\r\n'
        fields = kirikiri.kag_spans(text)
        self.assertEqual([(s.kind, s.text) for s in fields],
                         [("name", "Alice"), ("message", "Hello"), ("message", "world"), ("title", "Title")])
        out = kirikiri.patch_kag(text, {1: "New"})
        self.assertIn('New[r]world[l]\r\n', out)
        self.assertIn('"not dialogue"', out)

    def test_kag_name_context_and_macro(self):
        text = '[macro name=x]\n[unhandled whatever]\n[endmacro]\n[ns]$str20[nse]body\n'
        fields = kirikiri.kag_spans(text)
        self.assertEqual(fields[0].kind, "name_variable")
        with self.assertRaises(ValueError):
            kirikiri.patch_kag(text, {0: "lost variable"})

    def test_kag_reject_unsupported_and_injection(self):
        for text in ('text[unknown]', '[iscript]\nx', 'text['):
            with self.assertRaises(ValueError):
                kirikiri.kag_spans(text)
        with self.assertRaises(ValueError):
            kirikiri.patch_kag('hello', {0: '[jump target=x]'})

    def test_qlie_indent_choices_and_embedded_speaker(self):
        text = '  【Alice】  \r\n  id,Bob,Hello[n]world  \r\n^select,Yes,,No\r\n@command\r\n'
        fields = qlie.qlie_fields(text)
        self.assertEqual([f.text for f in fields], ["Alice", "Bob", "Hello\nworld", "Yes", "", "No"])
        out = qlie.patch_qlie(text, {0: "Ann", 2: "New\nline", 4: "Maybe"})
        self.assertIn('  【Ann】  \r\n', out)
        self.assertIn('  id,Bob,New[n]line  \r\n', out)
        self.assertIn('^select,Yes,Maybe,No', out)

    def test_qlie_refuse_choice_delimiters_and_context(self):
        with self.assertRaises(ValueError):
            qlie.patch_qlie('^select,Yes,No', {0: 'yes,no'})
        with self.assertRaises(ValueError):
            qlie.patch_qlie('【$str20】', {0: 'lost'})
        with self.assertRaises(ValueError):
            qlie.patch_qlie('plain', {0: 'id,A,body'})

    def test_musica_message_select_and_escapes(self):
        text = '.message 1 voice @Alice Hello\\nworld\\$21\r\n.select Yes:go No:stop\r\n.other untouched\r\n'
        fields = musica.musica_fields(text)
        self.assertEqual([f.text for f in fields], ["Alice", "Hello\nworld!", "Yes", "No"])
        out = musica.patch_musica(text, {0: "Ann", 1: "New line\nnext", 2: "Accept"})
        self.assertIn('@Ann New　line\\nnext\r\n', out)
        self.assertIn('.select Accept:go No:stop\r\n', out)

    def test_musica_empty_name_and_refuse_syntax(self):
        text = '.message 1 v  Text\n'
        self.assertEqual([f.kind for f in musica.musica_fields(text)], ["message"])
        with self.assertRaises(ValueError):
            musica.patch_musica('.select Yes:go', {0: 'Other:target'})
        with self.assertRaises(ValueError):
            musica.patch_musica('.message 1 v @$str20 Text', {0: 'lost'})
        with self.assertRaises(ValueError):
            musica.decode_text('bad\\x')


class BgiTests(unittest.TestCase):
    def test_magic_without_extension_and_roles(self):
        data, size, base = make_bgi(["Alice", "Hello"])
        self.assertEqual(bgi.code_offset(data), base)
        self.assertEqual([r.kind for r in bgi.scan_v1_subset(data, size)], ["name", "message"])

    def test_pool_growth_and_dedup(self):
        data, size, base = make_bgi(["Alice", "Hello"])
        refs = bgi.scan_v1_subset(data, size)
        out = bgi.patch_v1_pool(data, size, {refs[0].operand: "Same", refs[1].operand: "Same"})
        reread = bgi.scan_v1_subset(out, size)
        self.assertEqual(reread[0].address, reread[1].address)
        self.assertEqual(reread[1].text, "Same")
        self.assertEqual(struct.unpack_from('<I', out, refs[0].operand)[0], size)

    def test_choices_and_internal_empty(self):
        data, size, _ = make_bgi(["Yes", "No"], 0x160)
        self.assertEqual([r.kind for r in bgi.scan_v1_subset(data, size)], ["choice", "choice"])
        data, size, _ = make_bgi(["", "Hello"])
        refs = bgi.scan_v1_subset(data, size)
        self.assertEqual(refs[0].kind, "internal")
        with self.assertRaises(ValueError):
            bgi.patch_v1_pool(data, size, {refs[0].operand: "invented"})

    def test_unknown_opcode_and_unknown_pool_tail_refused(self):
        data, size, base = make_bgi(["Hello"])
        bad = data[:base] + struct.pack('<I', 0xDEAD) + data[base + 4:]
        with self.assertRaises(ValueError):
            bgi.scan_v1_subset(bad, size)
        with self.assertRaises(ValueError):
            bgi.patch_v1_pool(data + b"opaque", size, {})


class WillTests(unittest.TestCase):
    def sample(self):
        name = b'\x15%LCA\0'
        message = b'\x14' + struct.pack('<I', 9) + b'voice\0Hello%K\0'
        target = len(name) + 5 + len(message)
        return name + b'\x02' + struct.pack('<I', target) + message + b'\0'

    def test_roles_controls_and_address_growth(self):
        code = self.sample()
        before = willplus.parse_ws2_v1_subset(code)
        self.assertEqual([f.text for f in before.fields], ['A', 'Hello'])
        out = willplus.patch_ws2_v1_subset(code, {0: 'Alice', 1: 'New\nline'})
        after = willplus.parse_ws2_v1_subset(out)
        self.assertEqual(after.fields[0].raw, '%LCAlice')
        self.assertEqual(after.fields[1].raw, 'New \\nline%K')
        self.assertEqual(after.addresses[0][1], len(out) - 1)

    def test_choice_format(self):
        prefix = b'\x0f\x01' + struct.pack('<h', 2) + b'Yes\0' + b'\0\0\0'
        target = len(prefix) + 5
        code = prefix + b'\x02' + struct.pack('<I', target) + b'\0'
        out = willplus.patch_ws2_v1_subset(code, {0: 'Long choice'})
        layout = willplus.parse_ws2_v1_subset(out)
        self.assertEqual(layout.fields[0].kind, 'choice')
        self.assertEqual(layout.addresses[0][1], len(out) - 1)

    def test_refuse_unknown_and_interior_jump(self):
        with self.assertRaises(ValueError):
            willplus.parse_ws2_v1_subset(b'\xff')
        with self.assertRaises(ValueError):
            willplus.parse_ws2_v1_subset(b'\x02\x01\0\0\0')
        with self.assertRaises(ValueError):
            willplus.patch_ws2_v1_subset(self.sample(), {1: 'bad%K'})


class MajiroTests(unittest.TestCase):
    def test_crc_table_and_repeat(self):
        self.assertEqual(majiro.xor_code(b'\0' * 8), bytes.fromhex('0000000096300777'))
        raw = bytes(range(256)) * 5
        self.assertEqual(majiro.xor_code(majiro.xor_code(raw)), raw)

    def test_mjo_header_preserved_and_signature(self):
        code = b'\x01\x02\x03'
        data = majiro.PLAIN + struct.pack('<IIII', 0, 0, 0, len(code)) + code
        encrypted = majiro.normalize_mjo(data, encrypted=True)
        self.assertEqual(encrypted[:16], majiro.ENCRYPTED)
        self.assertEqual(encrypted[16:32], data[16:32])
        self.assertEqual(majiro.normalize_mjo(encrypted), data)
        with self.assertRaises(ValueError):
            majiro.normalize_mjo(data + b'?')

    def test_text_ruby_fragment_roundtrip(self):
        text = 'Hello[漢/かん]\nNext'
        fragment = majiro.assemble_text(text)
        self.assertEqual(majiro.disassemble_text(fragment), text)
        self.assertIn(struct.pack('<HIIH', 0x810, 0x3198FD01, 0, 2), fragment)
        self.assertEqual(majiro.assemble_text('A'), bytes.fromhex('4008020041004108'))

    def test_string_length_limit_and_unknown_code(self):
        with self.assertRaises(ValueError):
            majiro.assemble_text('A' * 65535)
        with self.assertRaises(ValueError):
            majiro.disassemble_text(b'\xff\xff')
        with self.assertRaises(ValueError):
            majiro.assemble_text('bad[ruby]')


class SoftpalTests(unittest.TestCase):
    def sample(self):
        code = b'Sv20' + b'\0' * 8 + struct.pack('<II', 4, 4)
        text = b'_hdr' + b'\0' * 4 + b'Hello<br>world\0'
        point = b'$POINT_LIST_****' + struct.pack('<II', 0, 4)
        return code, text, point

    def test_point_labels_reverse_and_base(self):
        code, _, point = self.sample()
        self.assertEqual(softpal.point_labels(point, len(code)), (16, 12))

    def test_append_changes_one_operand_and_no_labels(self):
        code, text, point = self.sample()
        operands = ((12, 'message'), (16, 'context_name'))
        old = softpal.read_text_records(code, text, operands)
        self.assertEqual(old[0].text, 'Hello\nworld')
        new_code, new_text, new_point = softpal.append_text_records(code, text, point, operands, {12: 'New\nbody'})
        self.assertEqual(new_point, point)
        self.assertEqual(new_text[:len(text)], text)
        self.assertEqual(struct.unpack_from('<I', new_code, 12)[0], len(text))
        self.assertEqual(new_code[16:20], code[16:20])
        self.assertEqual(softpal.read_text_records(new_code, new_text, operands)[0].text, 'New\nbody')

    def test_unknown_encryption_and_context_refused(self):
        code, text, point = self.sample()
        with self.assertRaises(ValueError):
            softpal.read_text_records(code, b'$' + text[1:], ((12, 'message'),))
        with self.assertRaises(ValueError):
            softpal.append_text_records(code, text, point, ((12, 'context_name'),), {12: 'lost'})
        with self.assertRaises(ValueError):
            softpal.append_text_records(code, text, point, ((12, 'message'),), {16: 'unproven'})


class YurisTests(unittest.TestCase):
    def test_xor_phase_resets_each_section(self):
        sizes = (4, 3, 5, 1)
        data = b'YSTB' + struct.pack('<IIIIIII', 1, 1, *sizes, 0) + b'\0' * sum(sizes)
        encrypted = yuris.toggle_ybn_sections(data, 0x04030201)
        self.assertEqual(encrypted[32:], bytes((1, 2, 3, 4, 1, 2, 3, 1, 2, 3, 4, 1, 1)))
        self.assertEqual(yuris.toggle_ybn_sections(encrypted, 0x04030201), data)
        with self.assertRaises(ValueError):
            yuris.toggle_ybn_sections(data[:-1], 1)

    def test_controls_and_sjis_backslash_trail(self):
        raw = b'\x81\x5cp\xef\xf0A\xef\xf2\xef\xf3\xef\xf5'
        display = yuris.convert_control_bytes(raw)
        self.assertEqual(display, b'\x81\x5cp\r\nA\\p\\c\\u')
        self.assertEqual(yuris.convert_control_bytes(display, to_yuris=True), raw)
        with self.assertRaises(ValueError):
            yuris.convert_control_bytes(b'\xef\xf1')

    def test_command_dictionary_ids_and_metadata(self):
        data = b'YSCM' + struct.pack('<III', 1, 2, 0) + b'WORD\0\x01text\0\x12\x34_\0\x00'
        result = yuris.read_command_list(data)
        self.assertEqual(result, (('WORD', (('text', b'\x12\x34'),)), ('_', ())))
        with self.assertRaises(ValueError):
            yuris.read_command_list(data + b'?')


class EscudeTests(unittest.TestCase):
    def test_pool_growth_offsets_empty_and_vm_preserved(self):
        data = make_escr((b'A', b'', b'B'))
        original = escude.read_escr(data)
        out = escude.patch_escr(data, {0: 'Long\nline'})
        result = escude.read_escr(out)
        self.assertEqual(result.strings, (b'Long<r>line', b'', b'B'))
        self.assertEqual(result.vm, original.vm)
        self.assertEqual(result.unknown, original.unknown)
        self.assertEqual(struct.unpack_from('<I', out, 16)[0], len(b'Long<r>line') + 1)

    def test_engine_single_byte_mapping_and_context(self):
        self.assertEqual(escude.decode_engine_string(b'!?\xa0'), '！？　')
        # The trail 0xA0 is part of a two-byte CP932 code and must not be mapped.
        pair = 'あ'.encode('cp932')
        self.assertEqual(escude.decode_engine_string(pair), 'あ')
        records = escude.extract_escr(make_escr((b'A', b'')), {0: ('Alice', 'Bob')})
        self.assertEqual(records[0].names, ('Alice', 'Bob'))
        self.assertFalse(records[0].name_writable)
        self.assertEqual(len(records), 2)

    def test_reject_noncanonical_pool_and_nul(self):
        data = bytearray(make_escr((b'A', b'B')))
        struct.pack_into('<I', data, 16, 0)
        with self.assertRaises(ValueError):
            escude.read_escr(bytes(data))
        with self.assertRaises(ValueError):
            escude.patch_escr(make_escr((b'A',)), {0: 'bad\0'})


class ExhibitTests(unittest.TestCase):
    def test_op_fragment_binary_roundtrip(self):
        ops = (exhibit.Op(28, 0xA0, (7,), ('*', 'Hello')), exhibit.Op(21, 0, (), ('choice?',)))
        self.assertEqual(exhibit.read_ops(exhibit.write_ops(ops)), ops)

    def test_indirect_and_direct_names_not_lost(self):
        definitions = (exhibit.Op(48, 0, (), ('7,unused,unused,Alice',)),)
        names = exhibit.name_table(definitions)
        ops = (exhibit.Op(28, 0, (7,), ('*', 'Hello')),
               exhibit.Op(28, 0, (), ('Bob', 'Next')),
               exhibit.Op(28, 0, (), ('$noname$', 'Narration')),
               exhibit.Op(191, 0, (), ('unsupported choice',)))
        records = exhibit.extract_dialogue(ops, names)
        self.assertEqual(records[0].names, ('Alice',))
        self.assertEqual(records[0].name_id, 7)
        self.assertFalse(records[0].name_writable)
        out = exhibit.patch_dialogue(ops, {0: {'message': 'New'}, 1: {'name': 'Ben'}}, names)
        self.assertEqual(out[0].strings, ('*', 'New'))
        self.assertEqual(out[1].strings[0], 'Ben')
        self.assertEqual(out[3], ops[3])
        with self.assertRaises(ValueError):
            exhibit.patch_dialogue(ops, {0: {'name': 'lost'}}, names)
        with self.assertRaises(ValueError):
            exhibit.patch_dialogue(ops, {3: {'message': 'pretend supported'}}, names)

    def test_xor_bounds_and_involution(self):
        data = b'\0DLR' + b'\0' * (0xFFD0 - 4)
        keys = tuple(range(256))
        out = exhibit.xor_rld(data, 0xAABBCCDD, keys)
        self.assertEqual(out[:16], data[:16])
        self.assertEqual(out[0xFFCC:], data[0xFFCC:])
        self.assertEqual(exhibit.xor_rld(out, 0xAABBCCDD, keys), data)

    def test_unknown_ops_and_string_count_refused(self):
        with self.assertRaises(ValueError):
            exhibit.read_ops(b'\xff\xff\0\0')
        with self.assertRaises(ValueError):
            exhibit.write_ops((exhibit.Op(28, 0, (), ('x',) * 16),))


class FavoriteTests(unittest.TestCase):
    def test_u8_encoded_length_boundary(self):
        self.assertEqual(favorite.encode_literal('A'), b'\x0e\x02A\0')
        self.assertEqual(favorite.encode_literal('あ' * 127)[1], 255)
        with self.assertRaises(ValueError):
            favorite.encode_literal('あ' * 128)
        with self.assertRaises(ValueError):
            favorite.encode_literal('bad\0')

    def test_forward_and_backward_targets_relocated(self):
        # Absolute file addresses: jump@4 -> ret@18; literal@9; call@13 -> jump@4.
        code = b'\x06' + struct.pack('<I', 18) + favorite.encode_literal('A') + b'\x02' + struct.pack('<I', 4) + b'\x04'
        old = favorite.parse_code(code)
        self.assertEqual(old[-1].address, 18)
        result = favorite.relocate_code(code, {9: 'Longer'})
        new = favorite.parse_code(result.code)
        self.assertEqual(new[0].operands[0], new[-1].address)
        self.assertEqual(new[-2].operands[0], 4)
        self.assertEqual(result.addresses[19], 4 + len(result.code))

    def test_speaker_candidates_keep_every_name(self):
        code = b'\x01\x03\0' + favorite.encode_literal('？Alice') + favorite.encode_literal('Alice') + b'\x04'
        self.assertEqual(favorite.speaker_candidates(code), {4: ('？Alice', 'Alice')})

    def test_unknown_syscalls_and_bad_targets_refused(self):
        with self.assertRaises(ValueError):
            favorite.parse_code(b'\x03\0\0')
        with self.assertRaises(ValueError):
            favorite.parse_code(b'\x06\x05\0\0\0')
        with self.assertRaises(ValueError):
            favorite.parse_code(b'\x0e\x02A?')


class IndependenceTests(unittest.TestCase):
    def test_all_engine_modules_import_without_reference_repositories(self):
        names = ('kirikiri', 'artemis', 'bgi', 'catsystem2', 'willplus', 'majiro', 'silky',
                 'softpal', 'yuris', 'musica', 'qlie', 'entis_gls', 'escude', 'exhibit', 'favorite')
        for name in names:
            self.assertIsNotNone(importlib.import_module('python.engines.' + name))


class ArtifactContractTests(unittest.TestCase):
    IDS = ('kirikiri', 'artemis', 'artemis-scp', 'bgi', 'catsystem2', 'willplus', 'majiro',
           'silky', 'softpal', 'yuris', 'musica', 'qlie', 'entis-gls', 'escude', 'exhibit',
           'favorite')

    def test_primary_documents_cover_structure_sources_and_local_code(self):
        root = Path(__file__).resolve().parents[1]
        for engine in self.IDS:
            text = (root / 'engines' / (engine + '.md')).read_text(encoding='utf-8')
            # Variant sections may nest their structure/source/API headings.
            headings = sum(line.startswith(('## ', '### ')) for line in text.splitlines())
            self.assertGreaterEqual(headings, 4, engine)
            # Engine pages own format details and recipes; only SKILL.md has
            # a size limit, enforced by tools/check_skill.py.
            self.assertIn('../python/engines/' + engine.replace('-', '_') + '.py', text, engine)
            self.assertTrue('MIT' in text or 'GPL' in text, engine)

    def test_primary_provenance_matches_ids_and_commits(self):
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / 'provenance' / 'primary.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['schema_version'], 1)
        self.assertEqual({item['id'] for item in manifest['engines']}, set(self.IDS))
        self.assertEqual(manifest['sources']['vntextpatch']['commit'],
                         'd9c0fab7b72fdcf87d674ef12a84d3829c9188be')
        self.assertEqual(manifest['sources']['msg_tool']['commit'],
                         'f72716cee88554d40c1cdface2812493b14ca653')
        for item in manifest['engines']:
            self.assertTrue((root / item['module']).is_file())
            self.assertTrue(item['limitations'])
            self.assertTrue(item['algorithms'])

    def test_leaf_imports_are_stdlib_and_no_path_hacks(self):
        import ast
        root = Path(__file__).resolve().parents[1]
        allowed = {'dataclasses', 'struct', 're', 'zlib', 'xml.etree.ElementTree'}
        for engine in self.IDS:
            source = (root / 'python' / 'engines' / (engine.replace('-', '_') + '.py')).read_text(encoding='utf-8')
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertTrue(all(alias.name in allowed for alias in node.names), engine)
                elif isinstance(node, ast.ImportFrom):
                    if engine == 'bgi' and node.level == 1 and node.module == 'bgi_v1_opcodes':
                        self.assertEqual([(alias.name, alias.asname) for alias in node.names],
                                         [('OPERAND_TEMPLATES', None), ('operand_template', None),
                                          ('LAYOUT_STACK', None), ('LAYOUT_EXPLICIT', None),
                                          ('LAYOUT_EXPLICIT565', None)])
                    else:
                        self.assertIn(node.module, allowed, engine)
            self.assertNotIn('sys.path', source, engine)
            self.assertNotIn('C:/Users/', source, engine)
            self.assertTrue(all(isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign,
                                                 ast.FunctionDef, ast.ClassDef, ast.Expr))
                                for node in tree.body), engine)

    def test_qlie_unbalanced_control_injection_refused(self):
        for replacement in ('text[', 'text]', 'text[[n]'):
            with self.assertRaises(ValueError):
                qlie.patch_qlie('text', {0: replacement})


if __name__ == '__main__':
    unittest.main()
