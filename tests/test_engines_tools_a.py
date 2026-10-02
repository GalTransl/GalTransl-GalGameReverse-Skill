"""Synthetic-only tests for tools-a references. No upstream imports or game data."""
from pathlib import Path
import sys
import struct
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from python.engines import agsi, digitalworks, flyingshine, frontwing, ice, ivory, malie, masys, melonpan, mnoviolet, nejii
from python.archives import arcx, ast, advsys3, ail, emonengine, flyingshine as flyingshine_archive, hcsystem, hotsoup, ikura, leaf, melonpan as melonpan_archive, mirai, mnoviolet as mnoviolet_archive, nejii as nejii_archive, noncolor


def acv_fixture(magic=True, raw=b"synthetic script\r\n", gap=b"GAP12345", crc=0xA1B2C3D4):
    lo, hi, flag = 0x12345678, 0xABCDEF01, 3
    comp = bytearray(zlib.compress(raw, 9))
    key = struct.pack("<I", crc ^ lo)
    for i in range(len(comp) // 4 * 4):
        comp[i] ^= key[i % 4]
    head = b"ACV1" + struct.pack("<I", 1 ^ 0x8B6A4E5F) if magic else struct.pack("<I", 1 ^ 0x26ACA46E)
    off = len(head) + 21 + len(gap)
    record = struct.pack("<IIBIII", lo, hi, flag ^ (lo & 255),
                         off ^ lo ^ (0x8B6A4E5F if magic else 0), len(comp) ^ lo, 128 ^ lo)
    return head + record + gap + comp


def malie_fixture(fmt, messages=(b"A\0\0\0", b"B\0\0\0"), code=b"\x33\x02\x32"):
    prefix = (b"\0\0" + bytes(16)) if fmt == "data5-v1" else bytes(20)
    prefix += struct.pack("<I", len(code)) + code
    pool = b"".join(messages)
    offsets, pos = [], 0
    for raw in messages:
        offsets.append((pos, len(raw)))
        pos += len(raw)
    table = struct.pack("<I", len(messages))
    if fmt == "utf16-2008-v0":
        table += b"".join(struct.pack("<I", off) for off, _ in offsets)
        return prefix + struct.pack("<I", len(pool)) + pool + table
    table += b"".join(struct.pack("<II", off, size) for off, size in offsets)
    return prefix + table + struct.pack("<I", len(pool)) + pool + (b"opaque signature" if fmt == "data5-v1" else b"")


class ToolsATests(unittest.TestCase):
    def test_agsi_cstr_offsets_and_shared_conflict(self):
        pool = agsi.build_cstr([b"A\0", b"BB\0"])
        self.assertEqual(pool[:16], struct.pack("<4I", 0, 2, 2, 3))
        self.assertEqual(agsi.swap_nibbles(b"\x12\xFA"), b"\x21\xAF")
        changed = agsi.inject_cstr(pool, 2, [(0, "A", "LONG"), (0, "A", "LONG")])
        self.assertEqual(agsi.read_cstr(changed, 2), [b"LONG\0", b"BB\0"])
        self.assertEqual(struct.unpack_from("<II", changed, 8), (5, 3))
        with self.assertRaisesRegex(ValueError, "shared"):
            agsi.inject_cstr(pool, 2, [(0, "A", "X"), (0, "A", "Y")])
        with self.assertRaisesRegex(ValueError, "stale"):
            agsi.inject_cstr(pool, 2, [(0, "old", "X")])
        with self.assertRaises(ValueError):
            agsi.read_cstr(struct.pack("<II", 99, 2) + b"xx", 1)

    def test_agsi_sb2_keeps_code_and_tail(self):
        code = b"\x82\0\0\0\0\xC6\x34\x12\0\0"
        values = [int.from_bytes(b"SB2 ", "little"), 0, 0, len(code), 0, 0, 0, 0, 0, 1, 0]
        original = (struct.pack("<11I", *values) + b"CODE" + code + b"TTBLFTBLFTBLVTBLCSTR" +
                    agsi.build_cstr([b"A\0"]) + b"CDBLDBG_" + bytes(4) + b"DBG_" + bytes(4) + b"tail")
        self.assertEqual(agsi.inject_sb2(original, []), original)
        rebuilt = agsi.inject_sb2(original, [(0, "A", "XYZ")])
        header, segments = agsi.split_sb2(rebuilt)
        self.assertEqual(segments[0], (b"CODE", code))
        self.assertEqual(segments[-1], (b"", b"tail"))
        self.assertEqual(struct.unpack_from("<I", header, 36)[0], 1)

    def test_arcx_lzss_literals_overlap_and_limit(self):
        self.assertEqual(arcx.lzss(b"\x03AB\xEE\xF3", 8), b"ABABABAB")
        self.assertEqual(arcx.lzss(b"\0\0\0", 3), bytes(3))
        with self.assertRaises(ValueError):
            arcx.lzss(b"\x01", 1)
        with self.assertRaises(ValueError):
            arcx.lzss(b"\0\0\0", 2)
        with self.assertRaises(ValueError):
            arcx.lzss(b"\x01A", 1, max_output=0)

    def test_arcx_sequential_not_fixed_index(self):
        name, comp = b"test.scx\0", b"\x03AB\xEE\xF3"
        header_size = 28 + len(name)
        record = struct.pack("<5I", header_size + len(comp), len(name), header_size, len(comp), 8) + bytes(7) + b"\1"
        data = b"HEADER".ljust(16, b"\0") + record + name + comp
        self.assertEqual(len(data[:16]), 16)
        self.assertEqual(arcx.unpack(data, variant="tools-sequential"), [("test.scx", b"ABABABAB")])
        with self.assertRaises(ValueError):
            arcx.unpack(data, variant="garbro-fixed-index")

    def test_ast_arc2_name_xor_and_sizes(self):
        name = b"a.adv"
        first = 17 + len(name)
        data = b"ARC2" + struct.pack("<I", 1) + struct.pack("<IIB", first, 10, len(name)) + bytes(b ^ 255 for b in name) + b"CMP"
        item = ast.index(data)[0]
        self.assertEqual((item["name"], item["offset"], item["unpacked_size"], item["stored"]), ("a.adv", first, 10, b"CMP"))

    def test_advsys3_counter_and_terminator(self):
        data = struct.pack("<IIH", 3, 0x12345678, 3) + b"a.s" + b"ABC" + bytes(4) + b"opaque"
        records, tail = advsys3.unpack(data)
        self.assertEqual(records, [("a.s", 0x12345678, b"ABC")])
        self.assertEqual(advsys3.pack(records, tail), data)
        self.assertEqual(advsys3.unpack(advsys3.pack([("a.s", 7, b"LONGER")]))[0][0][2], b"LONGER")
        with self.assertRaises(ValueError):
            advsys3.pack([("a.s", 1, b"")])

    def test_ail_literal_polarity_and_missing_slots(self):
        raw = b"123456789"
        block = struct.pack("<HI", 1, 9) + b"\0" + b"12345678" + b"\0" + b"9"
        self.assertEqual(ail.literal_block(raw), block)
        packed = ail.pack([None, raw])
        self.assertEqual(packed[:12], struct.pack("<III", 2, 0, len(block)))
        self.assertEqual(ail.stored_entries(packed), [None, block])

    def test_digitalworks_text_alignment(self):
        for kind in ("name", "message"):
            for text in ("Ａ", "ＡＢ"):
                encoded = digitalworks.encode_text_instruction(kind, 0x1234, text)
                self.assertEqual(len(encoded) % 4, 0)
                self.assertEqual(digitalworks.decode_text_instruction(encoded), (kind, 0x1234, text))
        with self.assertRaises(ValueError):
            digitalworks.encode_text_instruction("message", 1, "A")

    def test_emonengine_subtype3_zero_key(self):
        raw = b"synthetic script"
        data = emonengine.pack_scripts([("test.bin", raw)])
        name, off, packed, size = emonengine.zero_key_index(data)[0]
        self.assertEqual((name, off, size), ("test.bin", 8, len(raw)))
        self.assertEqual(data[off:off + 12], bytes(12))
        self.assertEqual(arcx.lzss(data[off + 12:off + 12 + packed], size), raw)
        altered = bytearray(data)
        altered[-4 - 96 - 40] = 1
        with self.assertRaises(ValueError):
            emonengine.zero_key_index(altered)

    def test_flyingshine_shift_index_and_script_key(self):
        plain, key, shift = b"line\r\n", 0x5A, 7
        stored = bytes(b ^ key for b in plain)
        head = flyingshine_archive.MAGIC + struct.pack("<HB3sII", 0x1234, 0x33, b"abc", 123, 1)
        record = b"test.dsf\0".ljust(36, b"\0") + struct.pack("<III", shift, 80 + shift, len(stored) + shift)
        data = head + bytes(b ^ 0x33 for b in record) + stored
        self.assertEqual(flyingshine_archive.index(data)[0]["offset"], 80)
        self.assertEqual(flyingshine.script_decode(stored), (plain, key))
        self.assertEqual(flyingshine_archive.rebuild(data, [stored]), data)
        changed = flyingshine.script_encode(b"longer line\r\n", key)
        self.assertEqual(flyingshine_archive.index(flyingshine_archive.rebuild(data, [changed]))[0]["size"], len(changed))
        with self.assertRaises(ValueError):
            flyingshine.script_encode(b"LF only\n", key)

    def test_frontwing_nodes_and_variable_name(self):
        def node(var, value):
            args = [var + b"\0", value + b"\0"]
            return struct.pack("<HHI", 0x16, 2, 0xAABBCCDD) + b"".join(struct.pack("<H", len(a)) + a for a in args)
        data = b"\0bsc" + struct.pack("<II", 12, 2) + node(b"$Name", b"$str20") + node(b"$Msg", b"test") + b"tail"
        self.assertEqual(frontwing.extract(data)[0]["name"], "$str20")
        self.assertEqual(frontwing.replace_messages(data, {}), data)
        rebuilt = frontwing.replace_messages(data, {1: "longer test"})
        self.assertEqual(frontwing.extract(rebuilt)[0]["message"], "longer test")
        self.assertEqual(frontwing.parse(rebuilt)[1][0][0][4:], bytes.fromhex("ddccbbaa"))
        with self.assertRaises(ValueError):
            frontwing.replace_messages(data, {0: "not a message"})

    def test_hcsystem_utf16_and_nibble_index(self):
        data = hcsystem.pack_raw([("test.bin", b"ABC")])
        item = hcsystem.index(data)[0]
        self.assertEqual((item["name"], item["offset"], item["stored"]), ("test.bin", 88, b"ABC"))
        self.assertEqual(data[12], 0x47)  # 't' nibble-swapped
        with self.assertRaises(ValueError):
            hcsystem.pack_raw([("x" * 32, b"")])

    def test_hotsoup_relative_data_base_and_zero_key(self):
        records = [("a.ax", b"A"), ("b.ax", b"BB")]
        data = hotsoup.pack(records)
        self.assertEqual(struct.unpack_from("<II", data, 4), (80, 2))
        self.assertEqual(struct.unpack_from("<I", data, 16 + 32 + 24)[0], 1)
        self.assertEqual(hotsoup.unpack(data), records)
        bad = bytearray(data)
        bad[36] = 1
        with self.assertRaises(ValueError):
            hotsoup.unpack(bad)

    def test_ice_tokens_and_unpatched_index_limit(self):
        raw = b"\x01\xFF\x02\xE7\xEA\x44\xED\xED\xF6\xEC"
        tokens = ice.tokenize(raw)
        self.assertIn(("char", 258), tokens)
        self.assertIn(("break", 0xEA, 0x44), tokens)
        self.assertEqual(ice.encode_tokens(tokens), raw)
        for idx in (0xE7, 0xE8, 255, 2560):
            with self.assertRaises(ValueError):
                ice.encode_index(idx)
        with self.assertRaises(ValueError):
            ice.tokenize(b"\xFF")

    def test_ikura_mpx_index_no_implicit_decrypt(self):
        header = b"SM2MPX10" + struct.pack("<I", 1) + bytes(20)
        data = header + struct.pack("<12sII", b"test.isf", 52, 3) + b"ISF"
        self.assertEqual(ikura.unpack_mpx(data), [("test.isf", b"ISF")])
        changed = ikura.rebuild_mpx(data, [b"longer ISF"])
        self.assertEqual(changed[:32], header)
        self.assertEqual(ikura.unpack_mpx(changed)[0][1], b"longer ISF")

    def test_ivory_pair_cipher_golden_and_tail(self):
        self.assertEqual(ivory.crypt(bytes(4), 1, encrypt=True), b"\x02\0\0\0")
        data = bytes(range(137))
        enc = ivory.crypt(data, 0x13579BDF, encrypt=True)
        self.assertEqual(enc[-1:], data[-1:])
        self.assertEqual(ivory.crypt(enc, 0x13579BDF), data)
        section = b"cTEX" + struct.pack("<III", 20, 16, 1) + b"DATA"
        file = b"fAGS" + struct.pack("<I", 8 + len(section)) + section
        self.assertEqual(ivory.sections(file), [(b"cTEX", 16, section)])

    def test_leaf_kcap_raw_branch(self):
        data = leaf.pack_raw([("test.sdt", b"SDT")])
        self.assertEqual(data[:8], b"KCAP\1\0\0\0")
        self.assertEqual(struct.unpack_from("<II", data, 36), (44, 3))
        item = leaf.index(data)[0]
        self.assertEqual((item["offset"], item["flag"], item["stored"]), (44, 0, b"SDT"))

    def test_malie_versions_pool_offsets_and_control_bytes(self):
        for fmt in sorted(malie.FORMATS):
            with self.subTest(fmt=fmt):
                data = malie_fixture(fmt)
                image = malie.parse(data, fmt=fmt)
                self.assertEqual(image["pairs"], [(0, 4), (4, 4)])
                self.assertTrue(malie.selftest(data, fmt=fmt)["byte_exact"])
                messages = ["合成".encode("utf-16-le") + b"\x07\0\x06\0", b"B\0\0\0"]
                rebuilt = malie.rebuild_messages(data, messages, fmt=fmt)
                new = malie.parse(rebuilt, fmt=fmt)
                self.assertEqual(new["pairs"], [(0, 8), (8, 4)])
                self.assertEqual(new["prefix"], image["prefix"])
                self.assertEqual(new["tail"], image["tail"])
                self.assertEqual(new["pool"], b"".join(messages))

    def test_malie_op51_width_and_version_gate(self):
        self.assertEqual(malie.instruction_edges(b"\x33\x02\x32", "utf16-2008-v0"), {0, 2, 3})
        self.assertEqual(malie.instruction_edges(b"\x36", "data5-v2"), {0, 1})
        with self.assertRaises(ValueError):
            malie.instruction_edges(b"\x36", "utf16-2008-v0")
        with self.assertRaises(ValueError):
            malie.instruction_edges(b"\x33", "data5-v2")
        with self.assertRaises(ValueError):
            malie.parse(malie_fixture("data5-v1"), fmt="guess")

    def test_masys_expression_only_and_key_reset(self):
        expr = b"\x60" + struct.pack("<I", 0x62006200) + b"\x62\x03\0ABC\x62\x02\0DE\0"
        enc = masys.crypt_expression(expr, b"\x01\x02")
        self.assertEqual(enc[:5], expr[:5])
        self.assertEqual(enc[8:11], b"@@B")
        self.assertEqual(masys.crypt_expression(enc, b"\x01\x02"), expr)
        with self.assertRaises(ValueError):
            masys.crypt_expression(b"\x62\xFF\xFF\0", b"key")
        with self.assertRaises(ValueError):
            masys.crypt_expression(expr, b"")

    def test_melonpan_width_from_first_payload(self):
        record = struct.pack("<III8s", 3, 32, 77, b"a.s")
        data = b"WCW\0" + struct.pack("<II", 1, 123) + record + b"ABC"
        item = melonpan_archive.index(data)[0]
        self.assertEqual((item["name_width"], item["unknown"], item["stored"]), (8, 77, b"ABC"))
        self.assertEqual(melonpan.script_xor(b"\0\x12\xFF"), b"\xFF\xED\0")

    def test_mirai_and_noncolor_headers_are_not_interchangeable(self):
        for module, magic in ((mirai, True), (noncolor, False)):
            data = acv_fixture(magic)
            entries, gap = module.parse(data)
            self.assertEqual(gap, b"GAP12345")
            self.assertEqual(module.unpack(data, crc_low=0xA1B2C3D4), [b"synthetic script\r\n"])
            new = module.rebuild(data, [b"changed longer script\r\n"], crc_low=0xA1B2C3D4)
            self.assertEqual(module.parse(new)[1], gap)
            self.assertEqual(module.parse(new)[0][0]["key_hi"], entries[0]["key_hi"])
            self.assertEqual(module.unpack(new, crc_low=0xA1B2C3D4), [b"changed longer script\r\n"])
            with self.assertRaises(ValueError):
                module.unpack(data, crc_low=0)
            with self.assertRaises(ValueError):
                module.unpack(data, crc_low=0xA1B2C3D4, max_output=5)
        with self.assertRaises(ValueError):
            noncolor.parse(acv_fixture(True))
        with self.assertRaises(ValueError):
            mirai.parse(acv_fixture(False))

    def test_acv_crc_and_dword_remainder(self):
        self.assertEqual(mirai.title_key(b"123456789"), 0xF1A4F00A)
        data = b"1234567"
        self.assertEqual(mirai.xor_dwords(data, 0xFFFFFFFF), bytes(b ^ 255 for b in data[:4]) + b"567")

    def test_mnoviolet_three_widths_and_script_header(self):
        for width in (44, 68, 100):
            data = struct.pack("<I", 1) + b"test".ljust(width, b"\0") + struct.pack("<II", 3, 12 + width) + b"ABC"
            self.assertEqual(mnoviolet_archive.index(data), (width, [("test", b"ABC")]))
        self.assertEqual(mnoviolet.script_header(bytes(16) + struct.pack("<II", 2, 1) + b"\1A"), (b"\1A", 1))

    def test_nejii_container_and_fixed_record_field(self):
        data = nejii_archive.pack_raw([("test.BIN", b"ABC")])
        self.assertEqual(data[-12:-8], b"RK1\0")
        self.assertEqual(nejii_archive.index(data)[0]["stored"], b"ABC")
        name = b"\x6A" + b"Actor\0".ljust(143, b"\0")
        message = b"\x64" + b"hello\0".ljust(129, b"\0") + b"FLAG" + bytes(10)
        records = name + message
        self.assertEqual(nejii.extract_records(records)[0]["name"], "Actor")
        changed = nejii.replace_record(records, 1, "longer hello")
        self.assertEqual(changed[144 + 130:], records[144 + 130:])
        self.assertEqual(len(changed), len(records))
        with self.assertRaises(ValueError):
            nejii.replace_record(records, 1, "x" * 129)

    def test_malie_shared_pool_and_label_alignment_rejected(self):
        fmt = "data5-v2"
        data = bytearray(malie_fixture(fmt))
        image = malie.parse(data, fmt=fmt)
        struct.pack_into("<I", data, len(image["prefix"]) + 12, 0)
        with self.assertRaisesRegex(ValueError, "shared"):
            malie.rebuild_messages(data, [b"A\0\0\0", b"B\0\0\0"], fmt=fmt)
        bad_label = (struct.pack("<4I", 0, 0, 0, 1) + struct.pack("<I", 0x80000002) +
                     b"\0\0" + struct.pack("<III", 1, 0, 5) + b"\x08\0\0\0\0" + bytes(8))
        with self.assertRaisesRegex(ValueError, "label"):
            malie.parse(bad_label, fmt="utf16-2008-v0")

    def test_builders_return_immutable_bytes(self):
        calls = [ail.pack([b"A"]), advsys3.pack([("a", 0, b"A")]),
                 emonengine.pack_scripts([("a", b"A")]),
                 hcsystem.pack_raw([("a", b"A")]), hotsoup.pack([("a", b"A")]),
                 leaf.pack_raw([("a", b"A")]), nejii_archive.pack_raw([("a", b"A")])]
        for result in calls:
            self.assertIsInstance(result, bytes)

    def test_truncation_is_rejected(self):
        parsers = [agsi.split_sb2, ast.index, advsys3.unpack, ail.stored_entries,
                   emonengine.zero_key_index, flyingshine_archive.index, frontwing.parse,
                   hcsystem.index, hotsoup.unpack, ikura.unpack_mpx, ivory.sections,
                   leaf.index, melonpan_archive.index, mirai.parse, noncolor.parse,
                   mnoviolet_archive.index, nejii_archive.index]
        for parser in parsers:
            with self.subTest(parser=parser.__module__), self.assertRaises(ValueError):
                parser(b"X")


if __name__ == "__main__":
    unittest.main()
