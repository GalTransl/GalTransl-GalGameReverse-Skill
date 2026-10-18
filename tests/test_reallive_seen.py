# SPDX-License-Identifier: GPL-3.0-only
"""Synthetic RealLive SEEN fixtures; no game assets or key tables."""

import struct
import unittest

from python.archives.reallive_seen import (HEADER_SIZE, MASK_TABLE, lz_compress,
                                          lz_decompress, open_seen, read_section)


def xor(data, key):
    return bytes(value ^ key[i] for i, value in enumerate(data))


def mask_plaintext(payload):
    """Apply the fixed post-decompression XOR window to plain section data."""
    out = bytearray(payload)
    for i in range(256, min(len(out), 513)):
        out[i] ^= MASK_TABLE[(i - 256) % len(MASK_TABLE)]
    return bytes(out)


def build_section(payload, *, compress=True, key_table=None, prefix=b"\xee" * 48):
    """Assemble one section: literal prefix, optional LZ tail and key XOR."""
    stored = mask_plaintext(payload) if compress else b""
    stream = lz_compress(stored) if compress else b""
    crypto = min(len(stream), len(key_table)) if key_table is not None else 0
    head = bytearray(prefix)
    struct.pack_into("<III", head, 32, len(head), len(stored), crypto)
    raw = bytes(head) + stream
    if crypto:
        raw = raw[:len(head)] + xor(raw[len(head):len(head) + crypto], key_table) + raw[len(head) + crypto:]
    return raw


def build_seen(sections):
    """Lay out ``{table index: raw section}`` after the 80000-byte table."""
    header = bytearray(HEADER_SIZE)
    body = bytearray()
    for index in sorted(sections):
        raw = sections[index]
        struct.pack_into("<II", header, index * 8, HEADER_SIZE + len(body), len(raw))
        body += raw
    return bytes(header + body)


class SeenLzTests(unittest.TestCase):
    def test_roundtrip_literals_matches_and_overlap(self):
        samples = (b"", b"A", b"hello world", b"AB" * 400, bytes(range(256)) * 2)
        for sample in samples:
            stream = lz_compress(sample)
            self.assertEqual(lz_decompress(stream, len(sample)), sample)

    def test_rejects_zero_distance_and_truncated_stream(self):
        with self.assertRaises(ValueError):
            lz_decompress(b"PACK\0\0\0\0" + b"\x00" + struct.pack("<H", 0), 2)
        with self.assertRaises(ValueError):
            lz_decompress(b"PACK", 1)
        with self.assertRaises(ValueError):
            lz_decompress(b"PACK\0\0\0\0" + b"\x01", 1)


class SeenContainerTests(unittest.TestCase):
    def test_index_and_roundtrip(self):
        first = build_section(b"first")
        second = build_section(b"script" * 20)
        raw = build_seen({0: first, 3: second})
        archive = open_seen(raw)
        self.assertEqual([section.index for section in archive.sections], [0, 3])
        self.assertEqual(read_section(raw, archive.sections[0]), first[:48] + b"first")
        self.assertEqual(read_section(raw, archive.sections[1]),
                         second[:48] + b"script" * 20)

    def test_uncompressed_section_returns_prefix_only(self):
        raw_section = build_section(b"ignored", compress=False)
        raw = build_seen({1: raw_section})
        self.assertEqual(read_section(raw, open_seen(raw).sections[0]), raw_section[:48])

    def test_key_table_and_mask_window(self):
        key = bytes(range(16))
        payload = bytes(range(200)) + bytes(range(256)) + b"tail"
        raw_section = build_section(payload, key_table=key)
        raw = build_seen({0: raw_section})
        section = open_seen(raw).sections[0]
        with self.assertRaises(ValueError):
            read_section(raw, section)
        self.assertEqual(read_section(raw, section, key), raw_section[:48] + payload)

    def test_mask_touches_only_offsets_256_to_512(self):
        payload = bytes(range(256)) * 2 + b"tail"
        head = bytearray(48)
        struct.pack_into("<III", head, 32, 48, len(payload), 0)
        raw = build_seen({0: bytes(head) + lz_compress(payload)})
        out = read_section(raw, open_seen(raw).sections[0])[48:]
        expected = bytearray(payload)
        for i in range(256, 513):
            expected[i] ^= MASK_TABLE[(i - 256) % len(MASK_TABLE)]
        self.assertEqual(out, bytes(expected))
        self.assertEqual(out[:256], payload[:256])
        self.assertEqual(out[513:], payload[513:])

    def test_rejects_out_of_range_sections(self):
        with self.assertRaises(ValueError):
            open_seen(b"\0" * 100)
        header = bytearray(HEADER_SIZE)
        struct.pack_into("<II", header, 0, HEADER_SIZE + 10, 10)
        with self.assertRaises(ValueError):
            open_seen(bytes(header))

    def test_rejects_short_keys_and_truncated_tails(self):
        raw_section = build_section(b"payload" * 10, key_table=b"\x01\x02")
        raw = build_seen({0: raw_section})
        with self.assertRaises(ValueError):
            read_section(raw, open_seen(raw).sections[0], b"\x01")
        head = bytearray(48)
        struct.pack_into("<III", head, 32, 48, 64, 0)
        raw = build_seen({0: bytes(head) + b"PACK\0\0\0\0"})
        with self.assertRaises(ValueError):
            read_section(raw, open_seen(raw).sections[0])


if __name__ == "__main__":
    unittest.main()
