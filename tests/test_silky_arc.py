# SPDX-License-Identifier: GPL-3.0-only
"""Synthetic Silky ARC fixtures; no game assets."""

import struct
import unittest

from python.archives.silky_arc import (
    build_ai6win,
    build_arc,
    decrypt_name,
    encrypt_name,
    lzss_compress,
    lzss_decompress,
    open_ai6win,
    open_arc,
    open_arc_old,
    read_member,
)


def plain_arc(members):
    index_size = 0
    for name in members:
        index_size += 1 + len(name.encode("cp932")) + 1 + 12
    index, body = bytearray(), bytearray()
    for name, payload in members.items():
        encoded = encrypt_name(name.encode("cp932") + b"\0")
        index += bytes([len(encoded)]) + encoded
        index += struct.pack(">III", len(payload), len(payload),
                             4 + index_size + len(body))
        body += payload
    return struct.pack("<I", index_size) + bytes(index) + bytes(body)


class LzssTests(unittest.TestCase):
    def test_handwritten_literal_and_match(self):
        self.assertEqual(lzss_decompress(b"\x03AB", 2), b"AB")
        stream = b"\x07ABC" + bytes([0xEE, 0xF0])
        self.assertEqual(lzss_decompress(stream, 6), b"ABCABC")

    def test_roundtrip_compressible_and_random_like(self):
        for payload in (b"A" * 500, b"line one\nline two\n" * 60, bytes(range(1, 200)) * 3):
            packed = lzss_compress(payload)
            self.assertLess(len(packed), len(payload))
            self.assertEqual(lzss_decompress(packed, len(payload)), payload)

    def test_truncated_stream_is_refused(self):
        with self.assertRaises(ValueError):
            lzss_decompress(b"\x03A", 2)
        with self.assertRaises(ValueError):
            lzss_decompress(b"\x00\xEE", 8)


class ArcTests(unittest.TestCase):
    def test_name_transform_roundtrip(self):
        raw = "シナリオ".encode("cp932") + b"\0"
        stored = encrypt_name(raw)
        self.assertNotEqual(stored, raw)
        self.assertEqual(decrypt_name(stored), raw)

    def test_build_and_read_back_with_and_without_compression(self):
        members = {"script.mes": b"text line\n" * 80, "voice.dat": bytes(range(64))}
        for compress in (True, False):
            archive_bytes = build_arc(members, compress=compress)
            archive = open_arc(archive_bytes)
            self.assertEqual([entry.name for entry in archive.entries], list(members))
            for entry in archive.entries:
                self.assertEqual(read_member(archive_bytes, entry), members[entry.name])

    def test_packed_flag_follows_size_difference(self):
        packed = build_arc({"a.mes": b"same\n" * 100}, compress=True)
        archive = open_arc(packed)
        self.assertTrue(archive.entries[0].packed)
        plain = build_arc({"a.mes": b"same\n" * 100}, compress=False)
        self.assertFalse(open_arc(plain).entries[0].packed)

    def test_open_rejects_bad_index_and_names(self):
        good = plain_arc({"a.bin": b"abc"})
        broken = bytearray(good)
        broken[4] = 0
        with self.assertRaises(ValueError):
            open_arc(bytes(broken))
        with self.assertRaises(ValueError):
            open_arc(good[:-1])
        no_nul = bytearray(good)
        no_nul[10] = 0x00          # the stored terminator is last name byte
        with self.assertRaises(ValueError):
            open_arc(bytes(no_nul))

    def test_legacy_directory_is_read_only(self):
        name = "old.bin".encode("cp932").ljust(32, b"\0")
        payload = b"legacy"
        blob = struct.pack("<i", 1) + name + struct.pack("<II", 44, len(payload)) + payload
        archive = open_arc_old(blob)
        self.assertEqual(archive.entries[0].name, "old.bin")
        self.assertEqual(read_member(blob, archive.entries[0]), payload)

    def test_ai6win_roundtrip_and_fixed_name_slot(self):
        members = {"scene000.mes": b"message line\n" * 50, "layer.bin": bytes(range(32))}
        blob = build_ai6win(members)
        archive = open_ai6win(blob)
        self.assertEqual([entry.name for entry in archive.entries], list(members))
        for entry in archive.entries:
            self.assertEqual(read_member(blob, entry), members[entry.name])
        self.assertEqual(len(blob) % 4, 0)

    def test_ai6win_rejects_bad_count_and_unterminated_name(self):
        blob = bytearray(build_ai6win({"a.mes": b"x" * 40}))
        with self.assertRaises(ValueError):
            open_ai6win(b"\xff\xff\xff\x7f" + bytes(272))
        broken = bytearray(blob)
        broken[4:264] = b"\x01" * 260
        with self.assertRaises(ValueError):
            open_ai6win(bytes(broken))


if __name__ == "__main__":
    unittest.main()
