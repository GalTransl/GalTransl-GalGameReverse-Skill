import os
import struct
import sys
import unittest
import zlib
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from python.engines import kirikiri_simple_crypt as sc


class DetectTest(unittest.TestCase):
    def test_accepts_known_modes(self):
        for mode in sc.MODES:
            self.assertEqual(sc.detect(bytes([0xFE, 0xFE, mode, 0xFF, 0xFE]) + b"xx"), mode)

    def test_rejects_other_buffers(self):
        self.assertIsNone(sc.detect(b"PSB\0\x03\0\0\0"))
        self.assertIsNone(sc.detect(b"mdf\0\x01\0\0\0"))
        self.assertIsNone(sc.detect(bytes([0xFE, 0xFE, 9, 0xFF, 0xFE]) + b"x"))
        self.assertIsNone(sc.detect(b"\xfe\xfe\x01\xff"))
        self.assertIsNone(sc.detect(b"\xff\xfe\x01\xff\xfe"))


class RoundTripTest(unittest.TestCase):
    TEXT = sc.BOM + ';\u30c6\u30b9\u30c8\r\n@cmd  name="\u6f22\u5b57" value=1\r\n\u3042\u3044\r\n'.encode("utf-16-le")

    def test_every_mode_round_trips(self):
        for mode in sc.MODES:
            wrapped = sc.pack(self.TEXT, mode)
            self.assertEqual(sc.detect(wrapped), mode)
            plain, used = sc.unpack(wrapped)
            self.assertEqual(used, mode)
            self.assertEqual(plain, self.TEXT)

    def test_mode0_known_code_units(self):
        # Independent vector from TextStream's u16 rule, including its threshold.
        wrapped = bytes.fromhex('fefe00fffe 1f00 2120 4040 4372 2c62')
        plain, _ = sc.unpack(wrapped)
        self.assertEqual(plain, sc.BOM + '\x1f Aあ中'.encode('utf-16-le'))
        self.assertEqual(sc.pack(plain, 0), wrapped)

    def test_mode0_rejects_code_units_without_an_inverse(self):
        # U+0202 transforms into U+0003, which the reader leaves unchanged.
        with self.assertRaisesRegex(ValueError, 'no inverse'):
            sc.pack(sc.BOM + '\u0202'.encode('utf-16-le'), 0)

    def test_mode1_swaps_adjacent_bits(self):
        wrapped = bytes.fromhex('fefe01fffe 8200 8100 8130 1e8d')
        plain, _ = sc.unpack(wrapped)
        self.assertEqual(plain, sc.BOM + 'ABあ中'.encode('utf-16-le'))
        self.assertEqual(sc.pack(plain, 1), wrapped)

    def test_mode2_honours_declared_sizes(self):
        payload = RoundTripTest.TEXT[2:]
        packed = zlib.compress(payload)
        body = struct.pack("<QQ", len(packed), len(payload)) + packed
        plain, mode = sc.unpack(bytes([0xFE, 0xFE, 2, 0xFF, 0xFE]) + body)
        self.assertEqual(mode, 2)
        self.assertEqual(plain, b"\xff\xfe" + payload)

    def test_mode2_independent_stored_deflate_vector(self):
        # zlib header + final stored block for UTF-16LE AB + Adler-32.
        stream = bytes.fromhex('7801 010400fbff 41004200 018c0084')
        wrapped = bytes.fromhex('fefe02fffe') + struct.pack('<QQ', 15, 4) + stream
        self.assertEqual(sc.unpack(wrapped), (sc.BOM + b'A\0B\0', 2))
        rebuilt = sc.pack(sc.BOM + b'A\0B\0', 2, level=0)
        self.assertEqual(rebuilt, wrapped)

    def test_variable_length_chinese_preserves_source_structure(self):
        from python.engines.kirikiri_kag_text import export_script, rebuild_script
        original = sc.BOM + '*start\r\n@nm t="人物"\r\n本文[np]\r\n'.encode('utf-16-le')
        for mode in sc.MODES:
            with self.subTest(mode=mode):
                wrapped = sc.pack(original, mode)
                plain, used = sc.unpack(wrapped)
                # Wrapper roundtrip is separate from a real semantic writer.
                original_rows, manifest = export_script(plain)
                self.assertEqual(rebuild_script(plain, original_rows, manifest), plain)
                rows = [dict(r) for r in original_rows]
                rows[0]['message'] = '用于验证的较长中文正文'
                changed = rebuild_script(plain, rows, manifest)
                decoded, _ = sc.unpack(sc.pack(changed, used))
                self.assertEqual(decoded, changed)
                self.assertEqual(export_script(decoded)[0], rows)

    def test_bom_budget_and_malformed_utf16(self):
        for mode in sc.MODES:
            wrapped = sc.pack(sc.BOM + b'A\0', mode)
            self.assertEqual(sc.unpack(wrapped, max_output_size=4)[0], sc.BOM + b'A\0')
            with self.assertRaises(ValueError): sc.unpack(wrapped, max_output_size=3)
            for plain in (b'\xfe\xff\x00A', sc.BOM + b'A', sc.BOM + b'\x00\xd8'):
                with self.assertRaises(ValueError): sc.pack(plain, mode)
            self.assertEqual(sc.unpack(sc.pack(sc.BOM, mode), max_output_size=2)[0], sc.BOM)
            with self.assertRaises(ValueError): sc.unpack(sc.pack(sc.BOM, mode), max_output_size=1)
        for mode in (0, 1):
            with self.assertRaises(ValueError): sc.unpack(bytes([254, 254, mode, 255, 254, 0]))
        for budget in (True, 0, -1):
            with self.assertRaises(ValueError): sc.unpack(wrapped, max_output_size=budget)
        for mode in (True, 1.0, -1, 3):
            with self.assertRaises(ValueError): sc.pack(self.TEXT, mode)
        # A typed memoryview's len counts elements, not bytes.
        with patch.object(sc, 'MAX_INPUT_SIZE', 4):
            with self.assertRaises(ValueError): sc.pack(memoryview(self.TEXT).cast('H'), 1)

    def test_mode2_rejects_trailing_truncated_and_misdeclared_streams(self):
        raw = b'A\0' * 100
        packed = zlib.compress(raw)
        bad = [(packed + b'trailing', len(raw)), (packed + packed, len(raw)),
               (packed[:-1], len(raw)), (packed, len(raw) - 2), (packed, len(raw) + 2),
               (zlib.compress(b'x'), 1)]
        for stream, size in bad:
            with self.subTest(size=size), self.assertRaises(ValueError):
                sc.unpack(bytes.fromhex('fefe02fffe') + struct.pack('<QQ', len(stream), size) + stream)
        with self.assertRaises(ValueError):
            sc.unpack(bytes.fromhex('fefe02fffe') + struct.pack('<QQ', len(packed) + 16, len(raw)) + packed)

    def test_text_codec_reports_endianness(self):
        self.assertEqual(sc.text_codec(b"\xff\xfeA\x00"), ("utf-16-le", 2))
        self.assertEqual(sc.text_codec(b"\xfe\xff\x00A"), ("utf-16-be", 2))
        with self.assertRaises(ValueError):
            sc.text_codec(b"plain")

    def test_rejects_malformed_input(self):
        with self.assertRaises(ValueError):
            sc.unpack(b"not simple crypt")
        with self.assertRaises(ValueError):
            sc.pack(b"no bom here", 1)
        with self.assertRaises(ValueError):
            sc.pack(b"\xff\xfe", 7)
        with self.assertRaises(ValueError):
            sc.unpack(bytes([0xFE, 0xFE, 2, 0xFF, 0xFE]) + b"\x00" * 4)
        with self.assertRaises(ValueError):
            sc.unpack(b"\xfe\xfe\x01\xff\xfe" + b"\x00" * 8, max_output_size=4)
        with self.assertRaises(ValueError):
            sc.unpack(bytes([0xFE, 0xFE, 2, 0xFF, 0xFE]) + struct.pack("<QQ", 24, 8) + b"\x00" * 8)


if __name__ == "__main__":
    unittest.main()
