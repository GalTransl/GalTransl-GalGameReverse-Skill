# SPDX-License-Identifier: GPL-3.0-only
"""Synthetic NEKOPACK4 and AGE PAC fixtures; no game assets."""

import struct
import unittest
import zlib

from python.archives.age_pac import (PAGED_I16, PAGED_U32, build_pac, encode_member,
                                     open_pac, read_member)
from python.archives.nekopack import (MAGIC, build_pak, name_checksum, open_pak,
                                      read_member as neko_read, xor_head)


def paged_payload():
    """Two rotated blocks behind the paged marker."""
    blocks = [b"ABCD", b"EFGHIJ"]
    out = bytearray(struct.pack("<i", len(blocks)) + struct.pack("<hI", PAGED_I16, PAGED_U32))
    for block in blocks:
        rotated = bytes(((b << 4) | (b >> 4)) & 0xFF for b in block)
        out += struct.pack("<H", len(rotated) + 4) + b"\x00\x00\x00\x00" + rotated
    return bytes(out)


class NekoPackTests(unittest.TestCase):
    def test_build_read_and_roundtrip(self):
        members = {"ysbin/a.ybn": b"hello world", "b.bin": b"\x00\x01\x02\x03"}
        raw = build_pak(members)
        archive = open_pak(raw)
        self.assertEqual([e.name for e in archive.entries], list(members))
        for entry in archive.entries:
            self.assertEqual(neko_read(raw, entry), members[entry.name])

    def test_checksum_and_head_xor_are_consistent(self):
        raw_name = b"a.bin\x00"
        self.assertEqual(name_checksum(raw_name), 97 + 46 + 98 + 105 + 110 + 0)
        # key starts at size // 8 + 34 and shifts left by three per byte
        self.assertEqual(xor_head(b"\x78\x9c\x00\x00", 100),
                         bytes(b ^ (k & 0xFF) for b, k in
                               zip(b"\x78\x9c\x00\x00", [46, 368, 2944, 23552])))

    def test_rejects_bad_magic_and_corrupt_size_tail(self):
        raw = build_pak({"a.txt": b"x" * 100})
        with self.assertRaises(ValueError):
            open_pak(b"NEKOPACK3" + raw[9:])
        archive = open_pak(raw)
        corrupt = bytearray(raw)
        corrupt[archive.entries[0].offset + archive.entries[0].size - 1] ^= 0xFF
        with self.assertRaises(ValueError):
            neko_read(bytes(corrupt), archive.entries[0])


class AgePacTests(unittest.TestCase):
    def test_variant1_and_variant2_roundtrip(self):
        members = {"scenario.ks": b"*start\r\n\\text\r\nhello", "img.bin": paged_payload()}
        for variant in (1, 2):
            raw = build_pac(members, name_width=32, variant=variant)
            archive = open_pac(raw)
            self.assertEqual(archive.variant, variant)
            for entry in archive.entries:
                self.assertEqual(read_member(raw, entry), members[entry.name])
            self.assertEqual(read_member(raw, archive.entries[1]), paged_payload())

    def test_paged_encode_undoes_read(self):
        payload = paged_payload()
        stored = encode_member(payload)
        self.assertNotEqual(stored, payload)
        raw = build_pac({"a.bin": payload}, name_width=16)
        entry = open_pac(raw).entries[0]
        self.assertEqual(raw[entry.offset:entry.offset + entry.size], stored)
        self.assertEqual(read_member(raw, entry), payload)

    def test_rejects_bad_index_size_and_long_names(self):
        raw = bytearray(build_pac({"a.txt": b"x"}, name_width=16))
        struct.pack_into("<I", raw, 3, 1 << 30)
        with self.assertRaises(ValueError):
            open_pac(bytes(raw))
        with self.assertRaises(ValueError):
            build_pac({"x" * 64 + ".bin": b"x"}, name_width=16)
        with self.assertRaises(ValueError):
            build_pac({}, name_width=16)


if __name__ == "__main__":
    unittest.main()
