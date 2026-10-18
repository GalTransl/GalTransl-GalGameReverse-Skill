# SPDX-License-Identifier: GPL-3.0-only
"""Synthetic GxEngine GXP fixtures; no game assets.

The builder below restates the documented layout and the XOR stream on its own,
so the module is exercised against a second implementation of the same spec.
That catches refactors, not a wrong spec: real-archive confirmation is still
required before claiming engine support.
"""

import struct
import unittest

from python.archives.gxp import (HEADER_SIZE, KEY, open_gpx, pack_gpx, read_member)

NAME = "data.gpx"


def stream(name, length, start=0):
    raw = name.encode("ascii")
    return bytes((((start + j) & 0xFF) ^ KEY[(start + j) % 23] ^ raw[(start + j) % len(raw)])
                 for j in range(length))


def xor(data, name, start=0):
    return bytes(a ^ b for a, b in zip(data, stream(name, len(data), start)))


def build(members, crypt=0, trailer=b""):
    index, payload = bytearray(), bytearray()
    for name, body in members:
        encoded = name.encode("utf-16-le")
        entry = bytearray()
        entry += struct.pack("<i", 36 + len(encoded))
        entry += struct.pack("<I", len(body)) + b"\x00\x00\x00\x00"
        entry += struct.pack("<iiii", len(encoded) // 2, 1, 2, len(payload))
        entry += b"\x00\x00\x00\x00" + encoded + b"\x00\x00\x00\x00"
        index += entry
        payload += xor(body, NAME) if crypt else body
    stored = bytearray()
    pos = 0
    while pos < len(index):
        total, = struct.unpack_from("<i", index, pos)
        if crypt:
            stored += xor(index[pos:pos + 4], NAME, 0)
            stored += xor(index[pos + 4:pos + total], NAME, 4)
        else:
            stored += index[pos:pos + total]
        pos += total
    header = bytearray(HEADER_SIZE)
    header[0:4] = b"GXP\x00"
    struct.pack_into("<I", header, 20, crypt)
    struct.pack_into("<I", header, 24, len(members))
    struct.pack_into("<I", header, 28, len(stored))
    struct.pack_into("<I", header, 40, HEADER_SIZE + len(stored))
    return bytes(header) + bytes(stored) + bytes(payload) + trailer


class GxpTests(unittest.TestCase):
    def setUp(self):
        self.members = [("text/a.txt", b"hello"), ("b.bin", b"\x00\x01\x02")]
        self.raw = build(self.members)

    def test_index_roundtrip_and_payload_read(self):
        archive = open_gpx(self.raw, NAME)
        self.assertEqual([e.name for e in archive.entries], ["text/a.txt", "b.bin"])
        self.assertEqual(read_member(self.raw, archive, archive.entries[0]), b"hello")
        self.assertEqual(pack_gpx(self.raw, NAME, {}), self.raw)

    def test_encrypted_archive_roundtrip(self):
        raw = build(self.members, crypt=1, trailer=b"TAIL")
        archive = open_gpx(raw, NAME)
        self.assertEqual(read_member(raw, archive, archive.entries[1]), b"\x00\x01\x02")
        self.assertEqual(pack_gpx(raw, NAME, {}), raw)
        grown = pack_gpx(raw, NAME, {"b.bin": b"\x00\x01\x02\x03\x04"})
        check = open_gpx(grown, NAME)
        self.assertEqual(read_member(grown, check, check.entries[1]), b"\x00\x01\x02\x03\x04")
        self.assertEqual(read_member(grown, check, check.entries[0]), b"hello")
        # The opaque trailer stays where it was; appended payloads follow it.
        self.assertIn(b"TAIL", grown)

    def test_growth_appends_and_keeps_other_members(self):
        grown = pack_gpx(self.raw, NAME, {"text/a.txt": b"hello world"})
        archive = open_gpx(grown, NAME)
        self.assertEqual(read_member(grown, archive, archive.entries[0]), b"hello world")
        self.assertEqual(read_member(grown, archive, archive.entries[1]), b"\x00\x01\x02")
        self.assertGreater(archive.entries[0].offset, archive.entries[1].offset)

    def test_rejects_wrong_magic_truncation_and_traversal(self):
        with self.assertRaises(ValueError):
            open_gpx(b"XPX\0" + b"\0" * 60, NAME)
        bad = bytearray(self.raw)
        struct.pack_into("<I", bad, 28, 1 << 30)
        with self.assertRaises(ValueError):
            open_gpx(bytes(bad), NAME)
        with self.assertRaises(ValueError):
            open_gpx(build([("..\\evil", b"x")]), NAME)
        with self.assertRaises(ValueError):
            pack_gpx(self.raw, NAME, {"missing": b"x"})
        with self.assertRaises(ValueError):
            open_gpx(build(self.members, crypt=1), "データ.gpx")

    def test_index_trailing_bytes_and_count_drift_are_rejected(self):
        raw = bytearray(build([("a.txt", b"x"), ("b.txt", b"y")]))
        struct.pack_into("<I", raw, 24, 1)  # claim one entry while the index holds two
        with self.assertRaises(ValueError):
            open_gpx(bytes(raw), NAME)


if __name__ == "__main__":
    unittest.main()
