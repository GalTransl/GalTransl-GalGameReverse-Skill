"""Seekable, bounded BGI index/member tests (GPL-3.0-or-later)."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dataclasses import FrozenInstanceError, replace
import hashlib
import io
import struct
import unittest

from python.archives import bgi
from bgi_fixtures import literal_dsc, pack_archive


class SparseStream:
    """Advertise a multi-GiB file but materialize only a few allowed ranges."""
    def __init__(self, size, segments, chunk_limit=None):
        self.size = size
        self.segments = segments
        self.chunk_limit = chunk_limit
        self.pos = 0
        self.reads = []

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        self.pos = (0 if whence == 0 else self.pos if whence == 1 else self.size) + offset
        if self.pos < 0:
            raise ValueError("negative seek")
        return self.pos

    def read(self, size=-1):
        if size < 0:
            raise AssertionError("unbounded read")
        self.reads.append((self.pos, size))
        if self.chunk_limit is not None:
            size = min(size, self.chunk_limit)
        for offset, data in self.segments:
            if offset <= self.pos < offset + len(data):
                chunk = data[self.pos - offset:self.pos - offset + size]
                self.pos += len(chunk)
                return chunk
        return b""


def _large_archive(version=2):
    stride, name_size = (0x20, 0x10) if version == 1 else (0x80, 0x60)
    script = b"BurikoCompiledScriptVer1.00\0" + b"\0\xffbinary"
    prefix = bytearray(pack_archive([("script", script), ("movie", b"")], version))
    struct.pack_into("<I", prefix, 16 + stride + name_size + 4, 0xffffffff)
    index_end = 16 + 2 * stride
    movie_at = index_end + len(script)
    movie_header = b"video\0".ljust(0x220, b"\0")
    stream = SparseStream(movie_at + 0xffffffff, [(0, bytes(prefix)), (movie_at, movie_header)])
    return stream, script, index_end


class BgiIndexTests(unittest.TestCase):
    def failure(self, code, function, *args, **kwargs):
        with self.assertRaises(bgi.BgiArchiveError) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        self.assertIsInstance(caught.exception, ValueError)
        return caught.exception

    def test_two_layouts_and_immutable_records(self):
        files = [("日本.scr", b"raw bytes"), ("empty", b"")]
        for version in (1, 2):
            with self.subTest(version=version):
                data = pack_archive(files, version)
                stream = io.BytesIO(data)
                stream.seek(3)
                index = bgi.read_index(stream)
                end = 16 + len(files) * (0x20 if version == 1 else 0x80)
                self.assertEqual(stream.tell(), 3)
                self.assertEqual((index.version, index.archive_size, index.index_end), (version, len(data), end))
                self.assertIsInstance(index.entries, tuple)
                self.assertEqual([(e.ordinal, e.name, e.offset, e.size) for e in index.entries],
                                 [(0, files[0][0], end, 9), (1, "empty", end + 9, 0)])
                self.assertEqual(index.index_sha256, hashlib.sha256(data[:end]).hexdigest())
                with self.assertRaises(FrozenInstanceError):
                    index.version = 3
                with self.assertRaises(FrozenInstanceError):
                    index.entries[0].size = 999
                entries = [bgi.read_member(stream, index, e) for e in index.entries]
                self.assertEqual([(e.name, bgi.require_plain(e)) for e in entries], files)
                self.assertEqual(stream.tell(), 3)

    def test_index_hash_is_complete_header_and_index_not_payload(self):
        data = pack_archive([("a", b"ABC")])
        index = bgi.read_index(io.BytesIO(data))
        self.assertNotEqual(index.index_sha256, hashlib.sha256(data).hexdigest())
        self.assertNotEqual(index.index_sha256, hashlib.sha256(data[16:index.index_end]).hexdigest())
        self.assertEqual(bgi.read_index(io.BytesIO(data[:-1] + b"X")).index_sha256, index.index_sha256)
        padding_changed = bytearray(data)
        padding_changed[16 + 0x70] = 1
        self.assertNotEqual(bgi.read_index(io.BytesIO(padding_changed)).index_sha256, index.index_sha256)

    def test_sparse_large_archive_index_never_reads_payload_or_charges_movie(self):
        for version in (1, 2):
            stream, script, end = _large_archive(version)
            stream.seek(7)
            index = bgi.read_index(stream)
            self.assertGreater(index.archive_size, 4 << 30)
            self.assertEqual(index.entries[1].size, 0xffffffff)
            self.assertEqual(stream.tell(), 7)
            self.assertEqual(sum(size for _, size in stream.reads), end)
            self.assertTrue(all(offset + size <= end for offset, size in stream.reads))
            stream.reads.clear()
            selected = bgi.read_member(stream, index, index.entries[0], max_stored_size=len(script))
            self.assertEqual(selected.stored_data, script)
            self.assertEqual(stream.reads, [(end, len(script))])
            self.assertEqual(stream.tell(), 7)

    def test_sparse_movie_probe_is_bounded_and_v1_magic_visible(self):
        stream, script, _ = _large_archive()
        index = bgi.read_index(stream)
        stream.reads.clear()
        probe = bgi.probe_member(stream, index, index.entries[0])
        self.assertEqual(probe.codec, "raw")
        self.assertTrue(probe.header.startswith(b"BurikoCompiledScriptVer1.00\0"))
        self.assertEqual(probe.unpacked_size, len(script))
        stream.reads.clear()
        movie = bgi.probe_member(stream, index, index.entries[1])
        self.assertEqual(movie.codec, "raw")
        self.assertEqual(movie.unpacked_size, 0xffffffff)
        self.assertEqual(len(movie.header), 0x220)
        self.assertEqual(stream.reads, [(index.entries[1].offset, 0x220)])
        with self.assertRaises(FrozenInstanceError):
            movie.codec = "dsc"

    def test_optional_archive_size_cap_only_when_requested(self):
        stream, _, _ = _large_archive()
        error = self.failure("index_budget", bgi.read_index, stream, max_archive_size=512 << 20)
        self.assertEqual(error.stage, "index")
        self.assertEqual(stream.reads, [])
        self.assertGreater(bgi.read_index(stream, max_archive_size=None).archive_size, 4 << 30)

    def test_stored_budget_rejects_before_payload_read(self):
        stream, _, _ = _large_archive()
        index = bgi.read_index(stream)
        stream.reads.clear()
        error = self.failure("stored_budget", bgi.read_member, stream, index, index.entries[1])
        self.assertEqual((error.stage, error.offset), ("stored", index.entries[1].offset))
        self.assertEqual(stream.reads, [])

    def test_dsc_advertised_output_not_charged_at_probe_or_stored_stage(self):
        frame = bytearray(literal_dsc(b"x"))
        struct.pack_into("<I", frame, 0x14, 0xffffffff)
        data = pack_archive([("a", bytes(frame))])
        stream = io.BytesIO(data)
        index = bgi.read_index(stream)
        probe = bgi.probe_member(stream, index, index.entries[0])
        self.assertEqual((probe.codec, probe.unpacked_size), ("dsc", 0xffffffff))
        self.assertEqual(probe.header, bytes(frame[:0x220]))
        entry = bgi.read_member(stream, index, index.entries[0], max_stored_size=len(frame))
        self.assertEqual(entry.stored_data, bytes(frame))
        error = self.failure("decoded_budget", bgi.decode_member, entry)
        self.assertEqual(error.stage, "decode")
        with self.assertRaises(ValueError):
            bgi.inspect(data)  # Legacy API intentionally keeps its old combined budget.

    def test_short_partial_reads_are_supported(self):
        data = pack_archive([("a", literal_dsc(b"hello")), ("b", b"raw")])
        stream = SparseStream(len(data), [(0, data)], chunk_limit=3)
        stream.seek(2)
        index = bgi.read_index(stream)
        probe = bgi.probe_member(stream, index, index.entries[0])
        self.assertEqual(probe.codec, "dsc")
        entry = bgi.read_member(stream, index, index.entries[0])
        self.assertEqual(bgi.decode_member(entry), b"hello")
        self.assertEqual(stream.tell(), 2)

    def test_premature_eof_is_typed_at_header_index_probe_and_member(self):
        data = pack_archive([("a", b"123456")])
        for stop in (3, 20):
            stream = SparseStream(len(data), [(0, data[:stop])])
            stream.seek(1)
            error = self.failure("truncated", bgi.read_index, stream)
            self.assertEqual(error.stage, "index")
            self.assertEqual(error.offset, stop)
            self.assertEqual(stream.tell(), 1)
        index = bgi.read_index(io.BytesIO(data))
        for function, stage in ((bgi.probe_member, "probe"), (bgi.read_member, "stored")):
            stream = SparseStream(len(data), [(0, data[:-2])])
            error = self.failure("truncated", function, stream, index, index.entries[0])
            self.assertEqual((error.stage, error.offset), (stage, len(data) - 2))

    def test_entry_forgery_and_other_index_are_rejected_without_payload_reads(self):
        data = pack_archive([("a", b"123"), ("b", b"456")])
        stream = SparseStream(len(data), [(0, data)])
        index = bgi.read_index(stream)
        foreign = bgi.read_index(io.BytesIO(data)).entries[0]
        original = index.entries[0]
        forged = (replace(original), replace(original, name="evil"), replace(original, offset=0),
                  replace(original, size=-1), replace(original, ordinal=-1), foreign,
                  replace(original, ordinal=1), None)
        stream.reads.clear()
        for entry in forged:
            for function in (bgi.probe_member, bgi.read_member):
                self.failure("index_membership", function, stream, index, entry)
        self.assertEqual(stream.reads, [])

    def test_archive_size_change_rejected(self):
        data = pack_archive([("a", b"123")])
        index = bgi.read_index(io.BytesIO(data))
        for changed in (data[:-1], data + b"extra"):
            for function in (bgi.probe_member, bgi.read_member):
                stream = io.BytesIO(changed)
                stream.seek(4)
                self.failure("archive_changed", function, stream, index, index.entries[0])
                self.assertEqual(stream.tell(), 4)

    def test_member_ranges_revalidated_even_in_forged_index(self):
        data = pack_archive([("a", b"123")])
        index = bgi.read_index(io.BytesIO(data))
        for offset, size in ((0, 1), (index.index_end, -1), (len(data), 1), (len(data) + 1, 0)):
            entry = bgi.IndexEntry(0, "a", offset, size)
            forged = replace(index, entries=(entry,))
            self.failure("archive_bounds", bgi.read_member, io.BytesIO(data), forged, entry)
        bad = replace(index, index_end=0)
        self.failure("index_membership", bgi.read_member, io.BytesIO(data), bad, bad.entries[0])

    def test_bad_signatures_counts_index_and_member_ranges(self):
        for version in (1, 2):
            data = pack_archive([("a", b"123")], version)
            namesize = 0x10 if version == 1 else 0x60
            self.failure("archive_signature", bgi.read_index, io.BytesIO(b"BAD!" + data[4:]))
            for count in (0, 100001, 0xffffffff):
                bad = bytearray(data)
                struct.pack_into("<I", bad, 12, count)
                self.failure("index_budget", bgi.read_index, io.BytesIO(bad))
            bad = bytearray(data)
            struct.pack_into("<I", bad, 12, 2)
            self.failure("archive_bounds", bgi.read_index, io.BytesIO(bad))
            for rel, size in ((0xffffffff, 1), (0, 4), (4, 0), (0xffffffff, 0xffffffff)):
                bad = bytearray(data)
                struct.pack_into("<II", bad, 16 + namesize, rel, size)
                self.failure("archive_bounds", bgi.read_index, io.BytesIO(bad))

    def test_count_and_index_budgets_before_table_read(self):
        data = pack_archive([("a", b"abc")])
        for limits in ({"max_entries": 0}, {"max_index_size": 143}, {"max_index_size": 15}):
            stream = SparseStream(len(data), [(0, data)])
            self.failure("index_budget", bgi.read_index, stream, **limits)
            self.assertTrue(all(offset + size <= 16 for offset, size in stream.reads))
        index = bgi.read_index(io.BytesIO(data), max_index_size=144, max_entries=1)
        self.assertEqual(index.index_end, 144)

    def test_empty_duplicate_and_bad_encoding_names(self):
        data = pack_archive([("a", b"x"), ("a", b"y")])
        self.failure("index_name", bgi.read_index, io.BytesIO(data))
        data = bytearray(pack_archive([("a", b"x")]))
        data[16] = 0
        self.failure("index_name", bgi.read_index, io.BytesIO(data))
        data[16] = 0x81  # truncated CP932 double-byte character
        self.failure("index_name", bgi.read_index, io.BytesIO(data))
        self.failure("index_name", bgi.read_index, io.BytesIO(data), name_encoding="unknown-codec")
        data[16:19] = "中".encode("utf-8")
        self.assertEqual(bgi.read_index(io.BytesIO(data), name_encoding="utf-8").entries[0].name, "中")

    def test_name_not_materialized_or_falsely_classified(self):
        data = pack_archive([("../outside.scr", b"raw image\0\xff")])
        stream = io.BytesIO(data)
        index = bgi.read_index(stream)
        self.assertEqual(index.entries[0].name, "../outside.scr")
        self.assertEqual(bgi.probe_member(stream, index, index.entries[0]).codec, "raw")

    def test_unsupported_and_truncated_wrappers_are_typed(self):
        bse = bytearray(0x50)
        bse[:6] = b"BSE 1."
        struct.pack_into("<H", bse, 8, 0x200)
        samples = ((b"DSC FORMAT 2.00\0" + b"\0" * 600, "unsupported_codec"),
                   (b"DSC", "truncated"), (b"DSC FORMAT 1.00\0", "truncated"),
                   (b"BSE", "truncated"), (b"BSE 2." + b"\0" * 80, "unsupported_codec"),
                   (b"BSE 1.", "truncated"), (bytes(bse), "unsupported_codec"))
        for payload, code in samples:
            stream = io.BytesIO(pack_archive([("a", payload)]))
            index = bgi.read_index(stream)
            for function in (bgi.probe_member, bgi.read_member):
                with self.subTest(payload=payload[:16], function=function.__name__):
                    self.failure(code, function, stream, index, index.entries[0])

    def test_bse_and_compressedbg_are_tagged_but_decode_unsupported(self):
        for version in (0x100, 0x101):
            bse = bytearray(0x50)
            bse[:6] = b"BSE 1."
            struct.pack_into("<H", bse, 8, version)
            stream = io.BytesIO(pack_archive([("a", bytes(bse)), ("b", b"CompressedBG___\0")]))
            index = bgi.read_index(stream)
            for row, codec in zip(index.entries, ("bse", "compressedbg-image")):
                probe = bgi.probe_member(stream, index, row)
                self.assertEqual((probe.codec, probe.unpacked_size), (codec, None))
                entry = bgi.read_member(stream, index, row)
                self.failure("unsupported_codec", bgi.decode_member, entry)

    def test_nonbinary_nonseekable_and_failed_reads(self):
        self.failure("stream_io", bgi.read_index, io.StringIO("PackFile    " + "\0" * 80))
        self.failure("stream_io", bgi.read_index, object())

        class Broken(io.BytesIO):
            def read(self, size=-1):
                raise OSError("synthetic failure")

        self.failure("stream_io", bgi.read_index, Broken(pack_archive([("a", b"x")])))

        class NoSeek(io.BytesIO):
            def seek(self, *args):
                raise io.UnsupportedOperation("synthetic nonseekable")

        self.failure("stream_io", bgi.read_index, NoSeek())

    def test_invalid_limits_are_typed(self):
        data = pack_archive([("a", b"x")])
        for limits in ({"max_entries": -1}, {"max_index_size": -1}, {"max_archive_size": -1},
                       {"max_entries": 1.2}, {"max_index_size": True}):
            self.failure("invalid_limit", bgi.read_index, io.BytesIO(data), **limits)
        stream = io.BytesIO(data)
        index = bgi.read_index(stream)
        self.failure("invalid_limit", bgi.read_member, stream, index, index.entries[0], max_stored_size=-1)


if __name__ == "__main__":
    unittest.main()
