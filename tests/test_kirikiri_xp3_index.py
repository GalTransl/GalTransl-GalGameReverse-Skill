"""Synthetic XP3 index-pointer-block variant; no games or original archives.

Some containers store ``0x17`` in the standard index-offset field and keep the
real offset in the qword at file offset ``0x20``. These fixtures are assembled
from that layout so the resolver is exercised independently of the marker byte
that the chained-index variants use.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import io
import struct
import unittest
import zlib

from python.archives import xp3, kirikiri_xp3


MAGIC = b"XP3\r\n \n\x1a\x8bg\x01"
BODY_AT = 0x28


def reader(data):
    def read(at, count):
        if at < 0 or count < 0 or at + count > len(data):
            raise ValueError("XP3 bounds")
        return data[at:at + count]
    return read


def _chunk(tag, data):
    return tag + struct.pack("<Q", len(data)) + data


def pointer_block_archive(payload=b"abc", *, index_compress=False, pointer=None,
                          marker=b"\0" * 9, name="a.txt"):
    """Plain index behind a 0x17 pointer block; marker sits at 0x17, qword at 0x20."""
    encoded = name.encode("utf-16-le")
    index = _chunk(b"File", _chunk(b"info", struct.pack("<IQQH", 0, len(payload), len(payload),
                                                       len(encoded) // 2) + encoded)
                   + _chunk(b"segm", struct.pack("<IQQQ", 0, BODY_AT, len(payload), len(payload)))
                   + _chunk(b"adlr", struct.pack("<I", zlib.adler32(payload))))
    if index_compress:
        packed = zlib.compress(index)
        frame = b"\1" + struct.pack("<QQ", len(packed), len(index)) + packed
    else:
        frame = b"\0" + struct.pack("<Q", len(index)) + index
    index_at = BODY_AT + len(payload)
    target = index_at if pointer is None else pointer
    header = MAGIC + struct.pack("<Q", 0x17) + b"\0" * 4 + marker + struct.pack("<Q", target)
    assert len(header) == BODY_AT
    return header + payload + frame, index_at


class IndexPointerBlockTests(unittest.TestCase):
    def test_resolver_follows_the_pointer_block(self):
        data, index_at = pointer_block_archive()
        self.assertEqual(xp3.resolve_index_offset(reader(data), len(data)), index_at)
        # A container without the marker keeps the offset in the standard field.
        plain = xp3.build([("a.txt", b"abc")], filter_name="none")
        self.assertEqual(xp3.resolve_index_offset(reader(plain), len(plain)),
                         struct.unpack("<Q", plain[11:19])[0])

    def test_extract_reads_through_the_pointer_block(self):
        for compress in (False, True):
            with self.subTest(index_compress=compress):
                data, _ = pointer_block_archive(index_compress=compress)
                entries = xp3.extract(data, filter_name="none")
                self.assertEqual([(e.name, e.data) for e in entries], [("a.txt", b"abc")])

    def test_adapter_detect_and_member_read(self):
        data, _ = pointer_block_archive()
        self.assertEqual(kirikiri_xp3.detect(io.BytesIO(data)), "plain")
        profile, entries = kirikiri_xp3.read_index(io.BytesIO(data))
        self.assertEqual(profile, "plain")
        self.assertEqual([e.name for e in entries], ["a.txt"])
        self.assertEqual(kirikiri_xp3.read_member(io.BytesIO(data), entries[0], profile), b"abc")

    def test_chain_marker_layout_still_resolves_identically(self):
        data, index_at = pointer_block_archive(marker=b"\x80" + b"\0" * 8)
        self.assertEqual(xp3.resolve_index_offset(reader(data), len(data)), index_at)
        self.assertEqual([e.data for e in xp3.extract(data, filter_name="none")], [b"abc"])

    def test_out_of_range_pointer_is_not_adopted(self):
        for pointer in (0, 5, 1 << 20):
            with self.subTest(pointer=pointer):
                data, _ = pointer_block_archive(pointer=pointer)
                self.assertEqual(xp3.resolve_index_offset(reader(data), len(data)), 0x17)
                with self.assertRaises(ValueError):
                    xp3.extract(data, filter_name="none")

    def test_truncated_pointer_block_is_rejected(self):
        data, _ = pointer_block_archive()
        with self.assertRaises(ValueError):
            xp3.resolve_index_offset(reader(data[:0x17]), 0x17)


if __name__ == "__main__":
    unittest.main()
