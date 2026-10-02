"""Synthetic Escu:de ARC2/acp, @code/@mess and mdb fixtures; no game assets."""
import io
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from python.archives import escude as arc
from python.engines import escude_mess as mess, escude_mdb as mdb
from python.common.safety import validate_names


def acp(tokens, size):
    bits, width = "", 9
    for token in tokens:
        bits += format(token, f"0{width}b")
        if token == 0x101:
            width += 1
        elif token == 0x102:
            width = 9
    bits += "0" * (-len(bits) % 8)
    return b"acp\0" + struct.pack(">I", size) + int(bits, 2).to_bytes(len(bits)//8, "big")


def archive(files, *, bad_offset=None, bad_name=None):
    names = bytearray()
    offsets = []
    for name, _ in files:
        offsets.append(len(names))
        names += name.encode("cp932") + b"\0"
    start = 20 + 12*len(files) + len(names)
    words = [len(files), len(names)]
    payload = bytearray()
    for i, ((_, raw), offset) in enumerate(zip(files, offsets)):
        words += [bad_name if bad_name is not None else offset,
                  bad_offset if bad_offset is not None else start+len(payload), len(raw)]
        payload += raw
    key = 0x12345678
    encrypted = bytearray()
    for word in words:
        key ^= 0x65AC9365
        key = (key ^ (((key >> 1) ^ key) >> 3) ^ (((key << 1) ^ key) << 3)) & 0xffffffff
        encrypted += struct.pack("<I", word ^ key)
    return b"ESC-ARC2" + struct.pack("<I", 0x12345678) + encrypted + names + payload


def message_file(strings):
    pool = bytearray()
    offsets = []
    for s in strings:
        offsets.append(len(pool))
        pool += s.encode("cp932") + b"\0"
    return (b"@mess:__" + struct.pack("<II", len(strings), len(pool))
            + struct.pack(f"<{len(strings)}I", *offsets) + bytes(b ^ 0x55 for b in pool))


def inst(op, *params):
    return bytes((op,)) + struct.pack(f"<{len(params)}i", *params)


def code_file(vm, count, text=b"", offsets=()):
    return (b"@code:__" + struct.pack("<4I", len(vm), len(offsets), len(text), count)
            + vm + struct.pack(f"<{len(offsets)}I", *offsets) + text)


def database(table="登場人物", *, bad_kind=False):
    pool = bytearray()
    def string(s):
        at = len(pool)
        pool.extend(s.encode("cp932") + b"\0")
        return at
    name = string(table)
    specs = [(4, 4, string("名前")), (1, 4, string("文字色")),
             (1, 4, string("キャラID")), (1, 4, string("音声グループ")),
             (4, 4, string("顔画像"))]
    if bad_kind:
        specs[0] = (99, 4, specs[0][2])
    rows = (struct.pack("<5I", string(""), 0, 0, 0, string(""))
            + struct.pack("<5I", string("甲＆乙"), 0xffffff, 1, 2, string("face")))
    header = struct.pack("<III", 48, name, 5) + b"".join(struct.pack("<HHI", *s) for s in specs)
    return b"mdb\0" + header + struct.pack("<I", len(rows)) + rows + struct.pack("<I", len(pool)) + pool + b"\0"*4


class EscudeArchiveTests(unittest.TestCase):
    def test_index_does_not_read_payload(self):
        raw = archive([("start.001", b"x"*1_000_000)])
        class Guard(io.BytesIO):
            def read(self, size=-1):
                if self.tell()+size > 42 or size < 0:
                    raise AssertionError("index read payload")
                return super().read(size)
        index = arc.read_index(Guard(raw))
        self.assertEqual(index.entries[0].size, 1_000_000)
        self.assertEqual(index.data_start, 42)
        self.assertEqual(len(index.index_sha256), 64)

    def test_plain_and_compressed_members(self):
        raw = archive([("a.001", acp([65, 0x103, 0x100], 3)), ("b.bin", b"plain")])
        stream = io.BytesIO(raw)
        entries = arc.read_index(stream).entries
        self.assertEqual(arc.probe_member(stream, entries[0], limit=4), b"acp\0")
        self.assertEqual([arc.read_member(stream, e) for e in entries], [b"AAA", b"plain"])
        with self.assertRaises(ValueError):
            arc.read_member(stream, entries[0], max_output=2)
        with self.assertRaises(ValueError):
            arc.read_member(stream, entries[1], max_stored=4)

    def test_growth_reset_and_overlapping_dictionary(self):
        raw = acp([65, 66, 0x103, 0x101, 0x104, 0x102, 67, 0x103, 0x100], 9)
        self.assertEqual(arc.decode_acp(raw), b"ABABBACCC")

    def test_invalid_lzw(self):
        bad = [acp([0x100], 1), acp([0x103, 0x100], 1),
               acp([65, 0x103, 0x100], 2), acp([65, 0x100], 1)[:-1],
               acp([65, 0x100], 1)+b"\0", b"acp!"+b"\0"*8,
               acp([0x101]*16+[0x100], 0)]
        for raw in bad:
            with self.subTest(raw=raw[:12]), self.assertRaises(ValueError):
                arc.decode_acp(raw)

    def test_dictionary_overflow(self):
        raw = acp([65]*0x8901 + [0x100], 0x8901)
        with self.assertRaisesRegex(ValueError, "dictionary overflow"):
            arc.decode_acp(raw)

    def test_bad_index_and_limits(self):
        cases = [archive([("x", b"a")], bad_offset=0),
                 archive([("x", b"a")], bad_name=1),
                 archive([("x", b"a")])[:-1], b"ESC-ARC1"+b"\0"*12]
        for raw in cases:
            with self.subTest(raw=raw[:20]), self.assertRaises(ValueError):
                arc.read_index(io.BytesIO(raw))
        for kw in ({"max_entries": 0}, {"max_index_bytes": 1}):
            with self.assertRaises(ValueError):
                arc.read_index(io.BytesIO(archive([("x", b"a")])), **kw)

    def test_unsafe_names_require_common_validator(self):
        for files in ([('../x', b'x')], [('A', b'x'), ('a', b'y')]):
            entries = arc.read_index(io.BytesIO(archive(files))).entries
            with self.assertRaises(ValueError):
                validate_names([e.name for e in entries])


class EscudeMessTests(unittest.TestCase):
    def test_pair_names_choices_empties_and_repeated_messages(self):
        vm = (inst(13, 0) + inst(40, 1) + inst(4, 3) + inst(44, 30) + inst(2, 1)
              + inst(45, 7) + inst(41, 0) + inst(41, 1) + inst(42)
              + inst(45, 8) + inst(41, 2) + inst(43, 3, 0) + inst(18))
        records = mess.extract_pair(code_file(vm, 4), message_file(['同じ', '同じ', '', '選ぶ']), names=('', '甲＆乙'))
        self.assertEqual([r.name for r in records], ['甲＆乙', '甲＆乙', None, None])
        self.assertEqual([r.index for r in records], [0, 1, 2, 3])
        self.assertEqual(records[3].kind, 'choice')
        self.assertEqual(records[0].line, 7)

    def test_names_survive_proven_helpers_only(self):
        prefix = inst(40, 1) + inst(41, 0)
        # CALL at 10; next TEXT at 15; RET at 20; helper entry at 21.
        main = prefix + inst(17, 21) + inst(41, 1) + inst(18)
        for proc, expected in ((29, '甲'), (32, None)):
            vm = main + inst(13, 0) + inst(44, proc) + inst(18)
            records = mess.extract_pair(code_file(vm, 2), message_file(['一', '二']), names=('', '甲'))
            self.assertEqual(records[1].name, expected)

    def test_name_helper_checks_both_branches(self):
        main = inst(40, 1) + inst(41, 0) + inst(17, 21) + inst(41, 1) + inst(18)
        helper = inst(13, 0) + inst(16, 37) + inst(44, 29) + inst(18) + inst(44, 35) + inst(18)
        records = mess.extract_pair(code_file(main+helper, 2), message_file(['一', '二']), names=('', '甲'))
        self.assertIsNone(records[1].name)

    def test_roundtrip_growth_shortening_and_plain_cp932(self):
        strings = ['!?ｱ', "原文<r><ruby text='よみ'>字</ruby>", '', '末尾']
        raw = message_file(strings)
        self.assertEqual(mess.patch_mess(raw, dict(enumerate(strings))), raw)
        change = {0: '長い文章です', 1: "短<r><ruby text='よみ'>文</ruby>", 2: '追加'}
        result = mess.read_mess(mess.patch_mess(raw, change))
        self.assertEqual([s.decode('cp932') for s in result.strings], [change[0], change[1], change[2], '末尾'])
        self.assertEqual(mess.read_mess(raw).strings[0].decode('cp932'), '!?ｱ')

    def test_controls_and_unencodable_text_are_rejected(self):
        raw = message_file(['a<r><font color=\'1\'>b'])
        for text in ('a', "a<font color='1'><r>b", "a<r><font color='2'>b", 'a\0', 'a\nb'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                mess.patch_mess(raw, {0: text})
        with self.assertRaises(UnicodeEncodeError):
            mess.patch_mess(message_file(['a']), {0: '😀'})
        with self.assertRaises(ValueError):
            mess.patch_mess(message_file(['a']), {1: 'x'})
        with self.assertRaises(ValueError):
            mess.patch_mess(message_file(['a']), {0: 'x'}, encoding='utf-8')

    def test_invalid_pool_layout(self):
        raw = bytearray(message_file(['a', 'b']))
        struct.pack_into('<I', raw, 20, 0)
        for data in (bytes(raw), message_file(['a'])[:-1], message_file(['a'])+b'x'):
            with self.assertRaises(ValueError):
                mess.read_mess(data)

    def test_unknown_opcode_native_truncation_and_jump(self):
        for vm in (b'\xff', b'\0', inst(41) + b'\0', inst(15, 2), inst(44, 87), inst(43, 0, 3)):
            with self.subTest(vm=vm), self.assertRaises(ValueError):
                mess.read_code(code_file(vm, 1))

    def test_mismatched_unreferenced_and_duplicate_messages(self):
        pool = message_file(['a','b'])
        for vm,count in ((inst(41, 0), 1), (inst(41, 0), 2),
                         (inst(41, 1)+inst(41, 0), 2),
                         (inst(41, 0)+inst(41, 0), 2), (inst(8, 0), 2)):
            with self.subTest(vm=vm), self.assertRaises(ValueError):
                mess.extract_pair(code_file(vm, count), pool)

    def test_speaker_packets_fail_closed(self):
        for vm in (inst(40, 1), inst(40, 1)+inst(44, 32)+inst(41, 0),
                   inst(40, 1)+inst(15, 10)+inst(41, 0), inst(40, 2)+inst(41, 0)):
            with self.assertRaises(ValueError):
                mess.extract_pair(code_file(vm, 1), message_file(['a']), names=('', '甲'))


class EscudeMdbTests(unittest.TestCase):
    def test_names_keep_combined_display_slot(self):
        self.assertEqual(mdb.read_names(database()), ('', '甲＆乙'))
        table = mdb.read_mdb(database())[0]
        self.assertEqual(table.rows[1][1], 0xffffff)
        self.assertEqual(table.offset, 4)

    def test_bad_header_pool_schema_and_terminator(self):
        raw = bytearray(database())
        struct.pack_into('<I', raw, 8, 1)  # middle of a CP932 table name
        for data in (bytes(raw), database()[:-1], database()+b'x', database(bad_kind=True), database(table='wrong')):
            with self.assertRaises(ValueError):
                mdb.read_names(data)
        with self.assertRaises(ValueError):
            mdb.read_mdb(database(), max_rows=1)


if __name__ == '__main__':
    unittest.main()
