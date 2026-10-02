# SPDX-License-Identifier: GPL-3.0-only
"""GXP header relations, bounded member reads, and rejection of bad input.

Fixtures are synthetic and carry independent expected bytes/offsets; the reader
and writer do not share a code path that could validate each other's mistakes.
"""

import struct
import unittest

from python.archives.gxp import (HEADER_SIZE, GxpHeader, describe, index_bytes,
                                 read_header, read_member)
from python.common.binary import FormatError

from tests.gxp_fixtures import build_gxp


class TestGxpHeader(unittest.TestCase):
    def test_header_relations_hold(self):
        blob = build_gxp(b"AAA", b"BBBB")
        hdr = read_header(blob)
        self.assertEqual(hdr.version, 100)
        self.assertEqual(hdr.marker, 0x10203040)
        self.assertEqual(hdr.member_count, 2)
        self.assertEqual(hdr.data_size, 7)
        # data_offset == 0x30 + index_size, and data reaches EOF.
        self.assertEqual(hdr.data_offset + hdr.data_size, len(blob))
        self.assertEqual(hdr.index_end, hdr.data_offset)

    def test_describe_reports_without_decoding(self):
        info = describe(build_gxp(b"x"))
        self.assertEqual(info["magic"], "GXP")
        self.assertEqual(info["member_count"], 1)
        self.assertEqual(info["file_size"], len(build_gxp(b"x")))

    def test_rejects_non_gxp(self):
        with self.assertRaises(FormatError):
            read_header(b"NOPE" + bytes(HEADER_SIZE))

    def test_rejects_truncated_header(self):
        with self.assertRaises(FormatError):
            read_header(b"GXP\x00" + bytes(4))

    def test_rejects_broken_offset_relation(self):
        blob = bytearray(build_gxp(b"AAA"))
        struct.pack_into("<Q", blob, 0x28, 0x1000)  # data_offset no longer matches
        with self.assertRaises(FormatError):
            read_header(bytes(blob))

    def test_rejects_data_not_reaching_eof(self):
        blob = bytearray(build_gxp(b"AAA"))
        struct.pack_into("<Q", blob, 0x20, 0xFFFF)  # data_size too large
        with self.assertRaises(FormatError):
            read_header(bytes(blob))


class TestGxpMembers(unittest.TestCase):
    def test_index_region_is_bounded_by_header(self):
        blob = build_gxp(b"AAA")
        hdr = read_header(blob)
        self.assertEqual(len(index_bytes(blob, hdr)), hdr.index_size)

    def test_read_member_exact(self):
        blob = build_gxp(b"AAAA", b"BB")
        hdr = read_header(blob)
        self.assertEqual(read_member(blob, 0, 4, hdr), b"AAAA")
        self.assertEqual(read_member(blob, 4, 2, hdr), b"BB")
        self.assertEqual(read_member(blob, 0, 6, hdr), b"AAAABB")

    def test_member_range_past_end_is_rejected(self):
        blob = build_gxp(b"AAAA")
        hdr = read_header(blob)
        with self.assertRaises(FormatError):
            read_member(blob, 0, 5, hdr)
        with self.assertRaises(FormatError):
            read_member(blob, 3, 2, hdr)
        with self.assertRaises(FormatError):
            read_member(blob, -1, 1, hdr)
        with self.assertRaises(FormatError):
            read_member(blob, 0, -1, hdr)

    def test_zero_members(self):
        blob = build_gxp()
        hdr = read_header(blob)
        self.assertEqual(hdr.member_count, 0)
        self.assertEqual(hdr.data_size, 0)


if __name__ == "__main__":
    unittest.main()
