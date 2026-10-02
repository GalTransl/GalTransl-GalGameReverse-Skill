# SPDX-License-Identifier: GPL-3.0-only
"""GXP header relations, bounded member reads, and rejection of bad input.

Fixtures are synthetic and carry independent expected bytes/offsets.
This raw reader has no archive writer or index decoder.
"""

from dataclasses import replace
import io
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
        self.assertEqual(hdr.index_offset, 0x30)
        self.assertEqual(hdr.data_offset, 0x40)
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

    def test_unknown_version_and_marker_rejected(self):
        for kwargs in ({"version": 101}, {"marker": 0}, {"version": 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(FormatError):
                read_header(build_gxp(b"A", **kwargs))

    def test_data_must_not_overlap_header(self):
        blob = bytearray(build_gxp(b"AAA"))
        struct.pack_into("<Q", blob, 0x28, 0x20)
        struct.pack_into("<Q", blob, 0x20, len(blob) - 0x20)
        with self.assertRaises(FormatError):
            read_header(bytes(blob))

    def test_trailing_and_truncated_payload_rejected(self):
        blob = build_gxp(b"AAA")
        for bad in (blob + b"tail", blob[:-1]):
            with self.assertRaises(FormatError):
                read_header(bad)


class TestGxpMembers(unittest.TestCase):
    def test_index_region_is_bounded_by_header(self):
        blob = build_gxp(b"AAA")
        hdr = read_header(blob)
        self.assertEqual(len(index_bytes(blob, hdr)), hdr.index_size)

    def test_index_does_not_skip_a_guessed_preamble(self):
        expected = bytes.fromhex("03 0a 11 18 1f 26 2d 34 3b 42 49 50 57 5e 65 6c")
        for prefix in (b"", b"opaque", b"X" * 0x48):
            blob = build_gxp(b"payload", opaque_prefix=prefix)
            self.assertEqual(index_bytes(blob), prefix + expected)
            self.assertEqual(read_header(blob).index_size, 16)
            self.assertEqual(describe(blob)["raw_index_region_size"], 16 + len(prefix))

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

    def test_empty_regions(self):
        blob = build_gxp(index_size=0)
        self.assertEqual(index_bytes(blob), b"")
        self.assertEqual(read_member(blob, 0, 0), b"")

    def test_stale_or_forged_header_rejected(self):
        blob = build_gxp(b"AAAA")
        hdr = read_header(blob)
        for bad in (replace(hdr, data_offset=-1), read_header(build_gxp(b"B"))):
            with self.assertRaises(FormatError):
                index_bytes(blob, bad)
            with self.assertRaises(FormatError):
                read_member(blob, 0, 1, bad)
        with self.assertRaises(FormatError):
            index_bytes(blob[:-1], hdr)

    def test_budgets_and_invalid_integer_arguments(self):
        blob = build_gxp(b"AAAA")
        self.assertEqual(len(index_bytes(blob, max_size=16)), 16)
        self.assertEqual(read_member(blob, 0, 4, max_size=4), b"AAAA")
        with self.assertRaises(FormatError):
            index_bytes(blob, max_size=15)
        with self.assertRaises(FormatError):
            read_member(blob, 0, 4, max_size=3)
        for value in (-1, True, 1.5):
            with self.assertRaises(FormatError):
                index_bytes(blob, max_size=value)
            for args in ((value, 1), (0, value)):
                with self.assertRaises(FormatError):
                    read_member(blob, *args)


class RecordingStream(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.reads = []

    def read(self, size=-1):
        self.reads.append((self.tell(), size))
        if size < 0:
            raise AssertionError("unbounded read")
        return super().read(size)


class TestGxpStreams(unittest.TestCase):
    def test_header_never_reads_payload_and_restores_position(self):
        stream = RecordingStream(build_gxp(b"PAYLOAD"))
        stream.seek(3)
        self.assertEqual(read_header(stream).data_size, 7)
        self.assertEqual(stream.reads, [(0, 48)])
        self.assertEqual(stream.tell(), 3)
        self.assertEqual(describe(stream)["file_size"], 71)
        self.assertTrue(all(size == 48 for _, size in stream.reads))

    def test_selected_range_only_and_budget_before_allocation(self):
        stream = RecordingStream(build_gxp(b"AAAA", b"BB"))
        stream.seek(5)
        self.assertEqual(read_member(stream, 4, 2), b"BB")
        self.assertEqual(stream.reads, [(0, 48), (68, 2)])
        self.assertEqual(stream.tell(), 5)
        stream.reads.clear()
        with self.assertRaises(FormatError):
            index_bytes(stream, max_size=15)
        self.assertEqual(stream.reads, [(0, 48)])
        stream.reads.clear()
        with self.assertRaises(FormatError):
            read_member(stream, 0, 4, max_size=3)
        self.assertEqual(stream.reads, [])

    def test_short_read_rejected_and_position_restored(self):
        class ShortStream(io.BytesIO):
            def read(self, size=-1):
                return super().read(max(0, size - 1))
        stream = ShortStream(build_gxp(b"A"))
        stream.seek(2)
        with self.assertRaises(FormatError):
            read_header(stream)
        self.assertEqual(stream.tell(), 2)


if __name__ == "__main__":
    unittest.main()
