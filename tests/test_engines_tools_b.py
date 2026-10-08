# SPDX-License-Identifier: GPL-3.0-only
# Locally authored synthetic fixtures; per-layout sources and revisions are in
# provenance/tools-b.json. No upstream executable entry points are imported.
"""Offline synthetic fixtures for the independently implemented tools-b references.
No original games, tools, executables, caches, network, or paid APIs are used.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ast
import csv
import io
import struct
import unittest

from python.engines import overflow, puremail, sfa, studiomiris, studiopolaris, systemc, tanaka, triangle, ugos, umesoft, unison, winters, xuse, livemaker, violent, nsystem, system_epsilon, yuka
from python.archives import patisserie, ransel, sfa as sfa_archive, slgsystem, sakanagl, sceneplayer, succubus, systemc as systemc_archive, tanaka as tanaka_archive, umesoft as umesoft_archive, winters as winters_archive, xuse as xuse_archive, yatagarasu


def sj(text):
    return text.encode("cp932")


def obj_fixture(version):
    fmt = "<HH" if version == 1 else "<IH"
    stride = struct.calcsize(fmt)
    strings = [sj("試験") + b"\x00", sj("次")]
    base = 3 * stride
    tail = b"\xFE\x01"
    return (struct.pack(fmt, base + sum(map(len, strings)), len(tail))
            + struct.pack(fmt, base, len(strings[0]))
            + struct.pack(fmt, base + len(strings[0]), len(strings[1]))
            + b"".join(strings) + tail)


def skm_fixture(gap=b""):
    raw = [sj("試験"), sj("次")]
    return (b"SKMSd\x00" + struct.pack("<I", 2)
            + struct.pack("<4I", 0, len(raw[0]), len(raw[0]), len(raw[1]))
            + gap + bytes(b ^ 255 for b in b"".join(raw)) + b"TAIL")


def scd_fixture():
    text = b"\x00" + sj("試験") + b"\x00"
    target = 6 + len(text)
    header = b"SCD_" + struct.pack("<I", 14) + struct.pack("<I", target) + b"L\x00"
    return header + b"\x04\x00" + struct.pack("<I", target) + text + b"\x19"


def scb_fixture():
    header = bytearray(32)
    header[:4] = b"SCB1"
    struct.pack_into("<I", header, 28, 32)
    # 7 bytes per index record; four-byte end sentinel. First payload at 50.
    index = struct.pack("<IB2sIB2sI", 50, 3, b"a\x00", 52, 3, b"b\x00", 0)
    return bytes(header) + index + b"AABBB"


def triangle_fixture():
    segments = [(b"N7", b""), (b"Vvoice", bytes(range(6))),
                (sj("試験"), b""), (sj("本文"), b""), (b"W", b"")]
    return struct.pack("<HH", 74, len(segments)) + b"".join(a + b"\x00" + b for a, b in segments)


def ugos_fixture():
    block = b"\x07" + sj("試験") + b"\x00"
    return b"\x02" + struct.pack("<I", 10) + b"\x02" + struct.pack("<I", 10) + struct.pack("<H", len(block)) + block


def pk_fixture():
    data, name, extra = b"opaque", b"a.scr", b"\x01\x02\x03\x04\x05\x06"
    index = bytes([len(name)]) + name + extra + struct.pack("<II", len(data), 0)
    return data + index + struct.pack("<I", len(index))


def val_fixture():
    code = b"\xDD\x00\x00\x00\x00\x00\x83\x00\x01\x00"
    first = sj("試験") + b"\x00"
    pool = first + b"asset\x00" + b"\xFFTAIL"
    return (len(code).to_bytes(3, "little") + (2).to_bytes(3, "little") + b"\x01\x02\x03"
            + code + struct.pack("<II", 0, len(first)) + pool)


def yks_fixture():
    pool = bytearray(b"\xFE\xFE")  # unreferenced gap must survive rebuilding
    def text(value):
        pos = len(pool)
        pool.extend(value.encode("utf-8") + b"\x00")
        return pos
    gto, wait, select = text("GraphicTextOut"), text("KeyWait"), text("Select.Text0")
    ints = []
    for value in (0, 1, 2):
        ints.append(len(pool))
        pool.extend(struct.pack("<II", value, 0x11223344))
    name, message, choice, asset = text("仮名"), text("試験"), text("候補"), text("asset.png")
    null = 0xFFFFFFFF
    nodes = [(5, null, ints[0]), (5, null, ints[1]), (5, null, ints[2]),
             (8, null, 0), (7, null, name), (1, gto, null),
             (8, null, 3), (7, null, message), (1, gto, null),
             (7, null, choice), (11, select, null), (7, null, asset), (1, wait, null)]
    s2 = struct.pack("<6I", 0, 1, null, 0, 2, null)
    s3 = b"".join(struct.pack("<3I", *node) for node in nodes)
    header = b"YKS002\x00\x00" + struct.pack("<10I", 48, 48, 0, 48, len(s2), 48 + len(s2), len(s3),
                                               48 + len(s2) + len(s3), len(pool), 9)
    return header + s2 + s3 + pool


class TextTables(unittest.TestCase):
    def test_overflow_reference_roles_and_shared_ids(self):
        xml = '<Script><TextResource><TextRes NO="n">仮名</TextRes><TextRes NO="m">試験</TextRes><TextRes NO="asset">image.png</TextRes></TextResource><Frame><Log NAME="n" MESS="m"/><Log MESS="m"/></Frame></Script>'
        rows = overflow.extract_xml(xml)
        self.assertEqual([r["message"] for r in rows], ["試験", "試験"])
        self.assertEqual([r["name"] for r in rows], ["仮名", ""])
        rebuilt = overflow.rewrite_xml(xml, {"m": "合成<&>試験"})
        self.assertEqual(overflow.extract_xml(rebuilt)[1]["message"], "合成<&>試験")
        self.assertIn("image.png", rebuilt)
        self.assertEqual(overflow.rewrite_xml(xml, {}), xml)
        with self.assertRaises(ValueError):
            overflow.rewrite_xml(xml, {"asset": "not dialogue"})
        with self.assertRaises(ValueError):
            overflow.extract_xml('<!DOCTYPE Script [<!ENTITY x "x">]><Script/>')

    def test_overflow_duplicate_and_dangling_resource(self):
        for xml in ('<Script><TextRes NO="1"/><TextRes NO="1"/></Script>',
                    '<Script><Log MESS="missing"/></Script>'):
            with self.assertRaises(ValueError):
                overflow.extract_xml(xml)

    def test_puremail_both_versions_and_tail_pointer(self):
        for version in (1, 2):
            with self.subTest(version=version):
                data = obj_fixture(version)
                self.assertEqual(puremail.rewrite_obj(data, {}, version=version), data)
                self.assertEqual(puremail.extract_obj(data, version=version)[0]["text"], "試験\x00")
                rebuilt = puremail.rewrite_obj(data, {1: "長い試験\x00"}, version=version)
                self.assertEqual(puremail.parse_obj(rebuilt, version=version)["tail"], b"\xFE\x01")
                self.assertEqual(puremail.extract_obj(rebuilt, version=version)[1]["text"], "次")
                self.assertEqual(int.from_bytes(rebuilt[:2 if version == 1 else 4], "little"), len(rebuilt) - 2)
                with self.assertRaises(ValueError):
                    puremail.rewrite_obj(data, {1: "試験"}, version=version)

    def test_puremail_rejects_gaps_and_u16_overflow(self):
        data = bytearray(obj_fixture(1))
        struct.pack_into("<H", data, 8, 13)
        with self.assertRaises(ValueError):
            puremail.parse_obj(data, version=1)
        with self.assertRaises(ValueError):
            puremail.rewrite_obj(obj_fixture(1), {2: "A" * 65535}, version=1)

    def test_skm_dynamic_pool_and_preserved_gap(self):
        for gap in (b"", b"GAP"):
            data = skm_fixture(gap)
            base = 26 + len(gap)
            self.assertEqual(studiomiris.rewrite_skm(data, {}, pool_offset=base), data)
            rebuilt = studiomiris.rewrite_skm(data, {0: "長い試験"}, pool_offset=base)
            obj = studiomiris.parse_skm(rebuilt, pool_offset=base)
            self.assertEqual(obj["gap"], gap)
            self.assertEqual(obj["tail"], b"TAIL")
            self.assertEqual(obj["strings"], [sj("長い試験"), sj("次")])
            self.assertEqual(struct.unpack_from("<I", rebuilt, 18)[0], len(sj("長い試験")))

    def test_skm_bad_offset(self):
        bad = bytearray(skm_fixture())
        struct.pack_into("<I", bad, 10, 0xFFFFFFFF)
        with self.assertRaises(ValueError):
            studiomiris.parse_skm(bad)

    def test_unison_reviewed_sites_and_pool_relocation(self):
        data = val_fixture()
        self.assertEqual(unison.rewrite_val(data, {}, sites=[0]), data)
        self.assertEqual(len(unison.extract_val(data, sites=[0])), 1)
        rebuilt = unison.rewrite_val(data, {0: "長い試験"}, sites=[0])
        before, after = unison.parse_val(data), unison.parse_val(rebuilt)
        self.assertEqual(after["code"], before["code"])
        self.assertEqual(after["extra"], b"\x01\x02\x03")
        self.assertEqual(after["offsets"][1], len(sj("長い試験")) + 1)
        self.assertTrue(after["pool"].endswith(b"\xFFTAIL"))
        with self.assertRaises(ValueError):
            unison.rewrite_val(data, {1: "resource"}, sites=[0])
        with self.assertRaises(ValueError):
            unison.extract_val(data, sites=[6])

    def test_unison_unreviewed_alias_and_suffix_overlap(self):
        data = bytearray(val_fixture())
        base = 9 + len(unison.parse_val(data)["code"])
        struct.pack_into("<I", data, base + 4, 0)
        with self.assertRaises(ValueError):
            unison.rewrite_val(data, {0: "長い試験"}, sites=[0])
        struct.pack_into("<I", data, base + 4, 2)
        with self.assertRaises(ValueError):
            unison.rewrite_val(data, {0: "長い試験"}, sites=[0])

    def test_livemaker_adjacent_column_and_multiline_csv(self):
        out = io.StringIO(newline="")
        csv.writer(out, lineterminator="\r\n").writerows([
            ["ID", "Original text", "Translation", "Other"],
            ["1", "【仮名】試験,本文\n次の行", "stale", "asset.png"],
            ["2", "地の文", "", "keep"],
        ])
        data = out.getvalue()
        rows = livemaker.extract_csv(data)
        self.assertEqual(rows[0]["name"], "仮名")
        rebuilt = livemaker.rewrite_csv(data, {0: {"name": "仮の名", "message": "合成,試験\n次"}})
        cells = list(csv.reader(io.StringIO(rebuilt, newline="")))
        self.assertEqual(cells[1][1], "【仮名】試験,本文\n次の行")
        self.assertEqual(cells[1][2], "【仮の名】合成,試験\n次")
        self.assertEqual(cells[1][3], "asset.png")
        self.assertEqual(livemaker.rewrite_csv(data, {}), data)
        with self.assertRaises(ValueError):
            livemaker.rewrite_csv(data, {1: {"name": "新名", "message": "試験"}})

    def test_livemaker_missing_destination(self):
        with self.assertRaises(ValueError):
            livemaker.extract_csv("ID,Original text\n1,試験\n")


class VirtualMachineSubsets(unittest.TestCase):
    def test_scd_label_and_jump_relocation(self):
        data = scd_fixture()
        self.assertEqual(studiopolaris.rewrite_scd(data, {}), data)
        self.assertEqual(studiopolaris.extract_scd(data), [{"offset": 6, "message": "試験"}])
        rebuilt = studiopolaris.rewrite_scd(data, {6: "長い試験"})
        new_target = 6 + 1 + len(sj("長い試験")) + 1
        self.assertEqual(struct.unpack_from("<I", rebuilt, 8)[0], new_target)
        self.assertEqual(struct.unpack_from("<I", rebuilt, 16)[0], new_target)
        self.assertEqual(studiopolaris.extract_scd(rebuilt)[0]["message"], "長い試験")

    def test_scd_does_not_extract_generic_string_operands(self):
        code = b"\x02\x08asset.png\x00\x19"
        data = b"SCD_" + struct.pack("<I", 8) + code
        self.assertEqual(studiopolaris.extract_scd(data), [])
        self.assertEqual(studiopolaris.rewrite_scd(data, {}), data)
        bad = bytearray(scd_fixture())
        struct.pack_into("<I", bad, 16, 7)
        with self.assertRaises(ValueError):
            studiopolaris.parse_scd(bad)
        with self.assertRaises(ValueError):
            studiopolaris.parse_scd(b"SCD_" + struct.pack("<I", 8) + b"\xFF")
        with self.assertRaises(ValueError):
            studiopolaris.rewrite_scd(scd_fixture(), {6: "試験\n"})

    def test_triangle_run_count_voice_and_character_boundary(self):
        data = triangle_fixture()
        rows = triangle.extract_block(data, profile="MOP")
        self.assertEqual(rows[0]["name_id"], "7")
        self.assertEqual(rows[0]["message"], "試験本文")
        self.assertEqual(triangle.rewrite_block(data, {}, profile="MOP", line_bytes=4), data)
        rebuilt = triangle.rewrite_block(data, {2: "合成試験本文"}, profile="MOP", line_bytes=4)
        obj = triangle.parse_block(rebuilt, profile="MOP")
        self.assertEqual(len(obj["segments"]), 6)
        self.assertEqual(obj["segments"][1], (b"Vvoice", bytes(range(6))))
        self.assertEqual(triangle.extract_block(rebuilt, profile="MOP")[0]["message"], "合成試験本文")
        with self.assertRaises(ValueError):
            triangle.rewrite_block(data, {2: "Name"}, profile="MOP", line_bytes=4)
        with self.assertRaises(ValueError):
            triangle.rewrite_block(data, {2: "試"}, profile="MOP", line_bytes=1)

    def test_triangle_choice_and_profile_rejection(self):
        data = struct.pack("<HH", 73, 1) + sj("候補") + b"\x00"
        self.assertEqual(triangle.extract_block(data, profile="KLH")[0]["kind"], "choice")
        rebuilt = triangle.rewrite_block(data, {0: "選択"}, profile="KLH", line_bytes=4)
        self.assertEqual(triangle.extract_block(rebuilt, profile="KLH")[0]["message"], "選択")
        with self.assertRaises(ValueError):
            triangle.parse_block(data, profile="MOP")
        with self.assertRaises(ValueError):
            triangle.parse_block(data[:-1], profile="KLH")

    def test_ugos_alias_pointer_relocation_and_control_edges(self):
        data = ugos_fixture()
        rows = ugos.extract_o(data, code_end=10)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["message"], "試験")
        self.assertEqual(ugos.rewrite_o(data, {}, code_end=10), data)
        rebuilt = ugos.rewrite_o(data, {10: "長い試験"}, code_end=10)
        self.assertEqual(struct.unpack_from("<I", rebuilt, 1)[0], len(data))
        self.assertEqual(struct.unpack_from("<I", rebuilt, 6)[0], len(data))
        self.assertEqual(rebuilt[10:len(data)], data[10:])
        self.assertEqual(ugos.parse_references(rebuilt, code_end=10)[0]["raw"], b"\x07" + sj("長い試験") + b"\x00")

    def test_ugos_small_pointer_overflow_and_unknown_opcode(self):
        raw = sj("試験")
        data = b"\x22\x02" + struct.pack("<H", len(raw)) + raw
        data = data.ljust(300, b"\x00")
        with self.assertRaises(ValueError):
            ugos.rewrite_o(data, {2: "長い試験"}, code_end=2)
        with self.assertRaises(ValueError):
            ugos.parse_references(b"\xFF", code_end=1)
        damaged = bytearray(ugos_fixture())
        damaged[15] = 7
        with self.assertRaises(ValueError):
            ugos.extract_o(damaged, code_end=10)

    def test_yks_semantic_routes_and_typed_pool_relocation(self):
        data = yks_fixture()
        rows = yuka.extract_yks(data)
        self.assertEqual([(r["id"], r["kind"]) for r in rows], [(7, "message"), (9, "choice")])
        self.assertEqual(rows[0]["name_id"], 4)
        self.assertEqual(rows[0]["name"], "仮名")
        self.assertEqual(yuka.rewrite_yks(data, {}), data)
        rebuilt = yuka.rewrite_yks(data, {4: "仮の名", 7: "長い試験", 9: "選択"})
        after = yuka.parse_yks(rebuilt)
        self.assertEqual(yuka.extract_yks(rebuilt)[0]["message"], "長い試験")
        self.assertEqual(yuka.extract_yks(rebuilt)[0]["name"], "仮の名")
        self.assertTrue(after["pool"].startswith(b"\xFE\xFE"))
        self.assertEqual(after["operands"], yuka.parse_yks(data)["operands"])
        for i in range(3):
            pos = after["nodes"][i][2]
            self.assertEqual(after["pool"][pos:pos + 8], struct.pack("<II", i, 0x11223344))
        self.assertEqual(struct.unpack_from("<I", rebuilt, 40)[0], len(after["pool"]))
        with self.assertRaises(ValueError):
            yuka.rewrite_yks(data, {11: "do not translate assets"})

    def test_yks_wrong_version_unknown_node_and_controls(self):
        data = yks_fixture()
        with self.assertRaises(ValueError):
            yuka.parse_yks(b"YKS001" + data[6:])
        bad = bytearray(data)
        struct.pack_into("<I", bad, yuka.parse_yks(data)["node_base"], 255)
        with self.assertRaises(ValueError):
            yuka.parse_yks(bad)
        with self.assertRaises(ValueError):
            yuka.rewrite_yks(data, {7: "@f(1)試験"})
        alias = bytearray(data)
        parsed = yuka.parse_yks(data)
        struct.pack_into("<I", alias, parsed["node_base"] + 11 * 12 + 8, parsed["nodes"][7][2])
        with self.assertRaises(ValueError):
            yuka.rewrite_yks(alias, {7: "長い試験"})


class ArchiveAndCodecStages(unittest.TestCase):
    def test_oz_data_dflt_and_offsets(self):
        members = [b"x", b"ABCD" * 300, b""]
        data = patisserie.pack_oz(members)
        self.assertEqual(data[:12], b"OZ\x00\x01OFST" + struct.pack("<I", 12))
        first = struct.unpack_from("<I", data, 12)[0]
        self.assertEqual(first, 24)
        self.assertEqual(data[first:first + 8], b"DATA" + struct.pack("<I", 1))
        self.assertEqual(patisserie.unpack_oz(data), members)
        with self.assertRaises(ValueError):
            patisserie.unpack_oz(data, max_output=20)
        bad = bytearray(data)
        struct.pack_into("<I", bad, 16, first)
        with self.assertRaises(ValueError):
            patisserie.unpack_oz(bad)

    def test_bcd_pair_names_and_byte_lengths(self):
        data, index = ransel.pack_bcd([("a", b"A"), ("b", b"BB")], archive_name="text.bcd")
        self.assertEqual(data, b"BinaryCombineData\x00ABB")
        self.assertIn(b"[a]\n18\n1\n", index)
        self.assertEqual(ransel.unpack_bcd(data, index, archive_name="text.bcd"), [("a", b"A"), ("b", b"BB")])
        with self.assertRaises(ValueError):
            ransel.unpack_bcd(data, index, archive_name="wrong.bcd")
        with self.assertRaises(ValueError):
            ransel.unpack_bcd(data[:-1], index, archive_name="text.bcd")

    def test_sfa_huffman_single_symbol_vector_and_roundtrip(self):
        self.assertEqual(sfa_archive.compress_member(b"A"), b"\x01\x00\x00\x00\x20\x80")
        for data in (b"", b"A" * 50, bytes(range(256)), b"ABBAAABA"):
            with self.subTest(size=len(data)):
                self.assertEqual(sfa_archive.decompress_member(sfa_archive.compress_member(data)), data)
        with self.assertRaises(ValueError):
            sfa_archive.decompress_member(sfa_archive.compress_member(b"AA"), max_output=1)
        with self.assertRaises(ValueError):
            sfa_archive.decompress_member(struct.pack("<I", 1) + b"\xFF" * 40)

    def test_sfa_aos_is_not_arbitrary_text(self):
        text = '#comment\ncvon("asset")\n[仮名]試験\nbtnset("slctwnd", "候補")\narbitrary resource\n'
        rows = sfa.extract_aos_lines(text)
        self.assertEqual([r["message"] for r in rows], ["試験", "候補"])
        self.assertEqual(text[slice(*rows[0]["span"])], "試験")

    def test_szs_cipher_vectors_and_archive(self):
        self.assertEqual(slgsystem.crypt_member(b"p", seed=0, mode="xor", decrypt=False), b"\xC6")
        self.assertEqual(slgsystem.crypt_member(b"p", seed=0, mode="sub", decrypt=False), b"\x06")
        members = [("script/a", b"ABC"), ("script/b", b"DEFG")]
        for mode in ("xor", "sub"):
            data = slgsystem.pack_szs(members, version=7, seed=123, mode=mode)
            self.assertEqual(slgsystem.unpack_szs(data, seed=123, mode=mode), (7, members))
            self.assertEqual(struct.unpack_from("<Q", data, 16 + 256)[0], 16 + 2 * 272)
        with self.assertRaises(ValueError):
            slgsystem.pack_szs([("../bad", b"x")], version=1, seed=1, mode="xor")
        with self.assertRaises(ValueError):
            slgsystem.unpack_szs(data, seed=123, mode="sub", max_output=1)

    def test_sakana_word_cipher_tail_and_key_derivation(self):
        raw = bytes(range(19))
        encrypted = sakanagl.crypt_data(raw, key_lo=1, key_hi=2)
        self.assertEqual(encrypted[-3:], raw[-3:])
        self.assertNotEqual(encrypted[:16], raw[:16])
        self.assertEqual(sakanagl.crypt_data(encrypted, key_lo=1, key_hi=2), raw)
        self.assertEqual(sakanagl.member_keys(offset=32, stored_size=3), (2 ^ (3 << 16) ^ 0x2E76034B, 0x2E6))
        with self.assertRaises(ValueError):
            sakanagl.member_keys(offset=3, stored_size=4)

    def test_sakana_decoded_index_tree(self):
        data = (b"\x00\x00\x00\x01\x00\x00\x00\x00" + struct.pack(">i", 1) + b"\x01a"
                + struct.pack(">iHHII", 1, 0, 0x10, 2, 3)
                + struct.pack(">H", 1) + bytes(40) + struct.pack(">H", 0)
                + struct.pack(">Hii", 0, 0, 0))
        result = sakanagl.parse_decoded_index(data)
        self.assertEqual(result["entries"][0]["offset"], 32)
        self.assertFalse(result["entries"][0]["encrypted"])
        self.assertEqual(result["tree"], [(None, 0, 0)])
        with self.assertRaises(ValueError):
            sakanagl.parse_decoded_index(data[:-1])

    def test_pmx_inflate_xor_archive_and_limits(self):
        members = [("a.txt", b"synthetic"), ("b.txt", b"XYZ")]
        data = sceneplayer.pack_pmx(members)
        self.assertEqual(data[0], 0x59)
        self.assertEqual(sceneplayer.unpack_pmx(data), members)
        with self.assertRaises(ValueError):
            sceneplayer.unpack_pmx(data, max_output=20)
        with self.assertRaises(ValueError):
            sceneplayer.pack_pmx([("試" * 16, b"x")], name_encoding="cp932")
        with self.assertRaises(ValueError):
            sceneplayer.unpack_pmx(data[:-1])

    def test_vfa_event_order_chunk_sizes_and_odd_payload(self):
        entries = [{"type": "dir", "name": "script/"},
                   {"type": "file", "name": "a", "data": b"ABC", "stamp": 9, "flags": 7},
                   {"type": "file", "name": "b", "data": b"D", "stamp": 5, "flags": 4}]
        header = struct.pack("<II4s4s", 0x10000, 1, b"dent", b"data")
        data = succubus.build_vfa(entries, header=header)
        parsed = succubus.parse_vfa(data)
        self.assertEqual(parsed["entries"], entries)
        self.assertEqual(succubus.build_vfa(parsed["entries"], header=parsed["header"]), data)
        self.assertEqual(struct.unpack_from("<I", data, 4)[0], len(data) - 8)
        entries[1]["data"] = b"LONGER"
        rebuilt = succubus.build_vfa(entries, header=header)
        self.assertEqual(succubus.parse_vfa(rebuilt)["entries"][2]["data"], b"D")
        with self.assertRaises(ValueError):
            succubus.parse_vfa(data[:-1])

    def test_zlc2_literal_control_groups(self):
        data = bytes(range(9))
        encoded = systemc_archive.encode_zlc2_literals(data)
        self.assertEqual(encoded, b"ZLC2" + struct.pack("<I", 9) + b"\x00" + data[:8] + b"\x00\x08")
        self.assertEqual(systemc_archive.decode_zlc2_literals(encoded), data)
        with self.assertRaises(ValueError):
            systemc_archive.decode_zlc2_literals(encoded[:8] + b"\x80" + encoded[9:])
        with self.assertRaises(ValueError):
            systemc_archive.decode_zlc2_literals(encoded, max_output=8)
        self.assertEqual(systemc.systemc_name_header("仮名　（１２）")["name"], "仮名")
        self.assertIsNone(systemc.systemc_name_header("asset.png"))

    def test_scb1_template_offsets_and_members(self):
        data = scb_fixture()
        self.assertEqual(tanaka_archive.repack_scb1(data, {}), data)
        rebuilt = tanaka_archive.repack_scb1(data, {"a": b"AAAA"})
        entries = tanaka_archive.parse_scb1(rebuilt)
        self.assertEqual(entries[1]["offset"], 54)
        self.assertEqual(entries[1]["data"], b"BBB")
        self.assertEqual(rebuilt[:32], data[:32])
        with self.assertRaises(ValueError):
            tanaka_archive.repack_scb1(data, {"missing": b"x"})

    def test_umesoft_alignment_terminator_and_pk_metadata(self):
        encoded = umesoft_archive.encode_member(b"12345678", kind="scr")
        self.assertEqual(struct.unpack_from("<I", encoded)[0], 16)
        self.assertEqual(encoded[-3:], b"\xFF\x00\x00")
        self.assertEqual(umesoft_archive.decode_literal_member(encoded), b"12345678        ")
        self.assertEqual(umesoft_archive.decode_literal_member(umesoft_archive.encode_member(b"a", kind="tbl")), b"a" + bytes(7))
        data = pk_fixture()
        self.assertEqual(umesoft_archive.repack_pk(data, {}), data)
        rebuilt = umesoft_archive.repack_pk(data, {"a.scr": encoded})
        entry = umesoft_archive.parse_pk(rebuilt)[0]
        self.assertEqual(entry["extra"], b"\x01\x02\x03\x04\x05\x06")
        self.assertEqual(entry["data"], encoded)
        with self.assertRaises(ValueError):
            umesoft_archive.decode_literal_member(encoded[:-1])

    def test_umesoft_narrow_text_rules(self):
        rows = umesoft.extract_script_lines('mes("仮名")\n"試験$L"\n"次\\n"\nimage("asset.png")\narbitrary\n')
        self.assertEqual(rows[0]["name"], "仮名")
        self.assertEqual([r["message"] for r in rows[1:]], ["試験", "次"])

    def test_ifp_sparse_index_and_explicit_types(self):
        members = [(0x15, b"ABC"), (0x0C, b"DE")]
        data = winters_archive.pack_ifp(members)
        self.assertEqual(struct.unpack_from("<I", data, 0x24)[0], 0x8010)
        self.assertEqual(struct.unpack_from("<I", data, 0x664)[0], 0x8013)
        self.assertEqual(winters_archive.unpack_ifp(data), members)
        self.assertEqual(winters.pad_isd_to_original(b"a", original_size=3), b"a\x00\x00")
        with self.assertRaises(ValueError):
            winters.pad_isd_to_original(b"ABC", original_size=2)
        bad = bytearray(data)
        struct.pack_into("<H", bad, 0x22, 1)
        with self.assertRaises(ValueError):
            winters_archive.unpack_ifp(bad)
        with self.assertRaises(ValueError):
            winters_archive.pack_ifp([(0x15, b"")] * 2000)

    def test_xuse_companion_index_gaps_and_cipher(self):
        gd = struct.pack("<I", 2) + b"__AAAAZBB"
        index = b"META" + struct.pack("<4I", 6, 4, 11, 2)
        self.assertEqual(xuse_archive.repack_gd(gd, index, {}), (gd, index))
        out, idx = xuse_archive.repack_gd(gd, index, {0: b"AAAAAA"})
        self.assertEqual(struct.unpack_from("<I", idx, 12)[0], 13)
        self.assertEqual(xuse_archive.parse_gd(out, idx)[1]["data"], b"BB")
        self.assertEqual(out[12:13], b"Z")
        self.assertEqual(idx[:4], b"META")
        self.assertEqual(xuse.crypt_script(b"abcd", key=b"QQQ\x00"), b"032d")
        with self.assertRaises(ValueError):
            xuse_archive.parse_gd(gd, index[:-1])

    def test_pkg_signature_embedded_key_and_per_member_phase(self):
        key = 0x12345678
        members = [("a", b"ABC"), ("b", b"D")]
        data = yatagarasu.pack_pkg(members, key=key)
        self.assertEqual(struct.unpack_from("<I", data)[0], len(data) ^ key)
        self.assertEqual(data[132:136], struct.pack("<I", key))
        self.assertEqual(data[-1], ord("D") ^ 0x78)
        self.assertEqual(yatagarasu.unpack_pkg(data, key=key), members)
        with self.assertRaises(ValueError):
            yatagarasu.unpack_pkg(data, key=key + 1)
        with self.assertRaises(ValueError):
            yatagarasu.pack_pkg([("a" * 124, b"x")], key=key)


class PresetBoundaries(unittest.TestCase):
    def test_nsystem_address_base_is_arithmetic_not_eval(self):
        data = bytearray(0x458 + 8 + 30)
        struct.pack_into("<I", data, 0x14, 1)
        struct.pack_into("<I", data, 0x18, 1)
        struct.pack_into("<II", data, 0x458, 0, 12)
        result = nsystem.address_table(data)
        self.assertEqual(result["base"], 0x460)
        self.assertEqual(result["fields"], [(0x458, 0x460), (0x45C, 0x46C)])
        struct.pack_into("<I", data, 0x14, 0xFFFFFFFF)
        with self.assertRaises(ValueError):
            nsystem.address_table(data)

    def test_nsystem_length_plus27_and_identifier(self):
        raw = sj("試験")
        record = struct.pack("<H", len(raw) + 27) + bytes(15) + b"\x03" + raw + b"\x00"
        self.assertEqual(nsystem.parse_message_record(record)["message"], "試験")
        rebuilt = nsystem.rewrite_message_record(record, "長い試験")
        self.assertEqual(struct.unpack_from("<H", rebuilt)[0], len(sj("長い試験")) + 27)
        self.assertEqual(rebuilt[2:18], record[2:18])
        self.assertEqual(nsystem.name_identifier(b"\x10\x00" + bytes(5) + b"\x03TEST_123\x00"), {"name_id": "TEST", "number": "123"})
        with self.assertRaises(ValueError):
            nsystem.rewrite_message_record(record, "試" * 300)

    def test_tanaka_record_delta_and_opcode_scope(self):
        record = b"\x06\x09" + sj("試験") + b"\x00"
        rebuilt = tanaka.rewrite_text_record(record, "長い試験")
        self.assertEqual(rebuilt[0], 10)
        self.assertEqual(tanaka.parse_text_record(rebuilt)["text"], "長い試験")
        name = b"\x06\x25" + sj("仮名") + b"\x00"
        self.assertEqual(tanaka.parse_text_record(name)["role"], "name")
        with self.assertRaises(ValueError):
            tanaka.parse_text_record(b"\x06\x10" + sj("試験") + b"\x00")

    def test_system_epsilon_length_delta_and_pointer_patterns(self):
        segment = b"\x05\x81\x94" + sj("仮名") + b"\x00"
        rebuilt = system_epsilon.rewrite_segment(segment, "仮の名")
        self.assertEqual(rebuilt[0], 7)
        self.assertEqual(system_epsilon.parse_segment(rebuilt)["role"], "name")
        pointer = b"\x1D\x08\x01\x00" + struct.pack("<I", 0x123)
        self.assertEqual(system_epsilon.pointer_candidates(pointer), [(4, 0x123)])
        excluded = b"\x0C\x08\x00\x00\x0D\x08\x00\x00" + struct.pack("<I", 0x123)
        self.assertEqual(system_epsilon.pointer_candidates(excluded, include_secondary=True), [])
        with self.assertRaises(ValueError):
            system_epsilon.rewrite_segment(segment, "名" * 200)

    def test_violent_candidates_are_not_dialogue(self):
        text = sj("試験")
        data = b"asset.png\x00" + text + b"\x00" + b"\xF0\x40\xF0\x40\x00" + text
        rows = violent.scan_candidates(data, start=0, end=len(data))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["role"], "unknown")
        self.assertEqual(rows[0]["offset"], 10)
        self.assertTrue(violent.is_allowed_sjis(text + b"\r\n"))
        self.assertFalse(violent.is_allowed_sjis(b"ABC"))
        self.assertFalse(violent.is_allowed_sjis(b"\xFC\x4C"))
        with self.assertRaises(ValueError):
            violent.scan_candidates(text + b"\x00", start=0, end=len(text) + 1, max_candidates=0)

    def test_modules_import_only_standard_library_or_shipped_modules(self):
        folder = Path(__file__).resolve().parents[1] / "python"
        names = ["overflow", "puremail", "patisserie", "ransel", "sfa", "slgsystem", "sakanagl",
                 "sceneplayer", "studiomiris", "studiopolaris", "succubus", "systemc", "tanaka",
                 "triangle", "ugos", "umesoft", "unison", "winters", "xuse", "yatagarasu",
                 "livemaker", "violent", "nsystem", "system_epsilon", "yuka"]
        paths = [folder / layer / (name + ".py") for name in names
                 for layer in ("engines", "archives")
                 if (folder / layer / (name + ".py")).is_file()]
        self.assertEqual({path.stem for path in paths}, set(names))
        for path in paths:
            name = str(path.relative_to(folder))
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertTrue(all(a.name.split(".")[0] in sys.stdlib_module_names for a in node.names), name)
                if isinstance(node, ast.ImportFrom):
                    if node.level:
                        package = ["python", *path.relative_to(folder).parent.parts]
                        self.assertLessEqual(node.level, len(package), name)
                        parts = package[:len(package) - node.level + 1]
                        parts.extend((node.module or "").split(".") if node.module else [])
                        target = folder.parent.joinpath(*parts)
                        self.assertTrue(target.with_suffix(".py").is_file() or
                                        (target / "__init__.py").is_file(), name)
                    else:
                        self.assertIn(node.module.split(".")[0], sys.stdlib_module_names, name)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, {"eval", "exec", "open", "__import__"}, name)


if __name__ == "__main__":
    unittest.main()
