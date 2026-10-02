"""Synthetic archive tests; no games, external programs, or original libraries.

Run: python -B -m unittest discover -s tests -p test_archives.py
Fixtures are hand-assembled from field layouts, not copied game archives.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bz2
import hashlib
import io
import pickle
import struct
import tempfile
import unittest
import zlib
from python.archives import xp3, rpa, nscripter, pfs, majiro, bgi, bgi_dsc, bgi_writer, siglus


def _chunk(tag, data):
    return tag + struct.pack("<Q", len(data)) + data


def _xp3(parts=(b"abc",), *, compress=False, repeat=False, index_compress=False,
         info_flags=0, seg_flag=None, section_extra=b"", stored_suffix=b"",
         index_suffix=b"", name="script.ks"):
    body, table, plain = bytearray(), bytearray(), b""
    first = None
    for raw in parts:
        stored = (zlib.compress(raw) if compress else raw) + stored_suffix
        segment = struct.pack("<IQQQ", int(compress) if seg_flag is None else seg_flag,
                              19 + len(body), len(raw), len(stored))
        if first is None:
            first = (segment, raw, len(stored))
        table.extend(segment)
        body.extend(stored)
        plain += raw
    packed_size = len(body)
    if repeat:
        table.extend(first[0])
        plain += first[1]
        packed_size += first[2]
    name_bytes = name.encode("utf-16-le")
    info = struct.pack("<IQQH", info_flags, len(plain), packed_size, len(name_bytes) // 2) + name_bytes
    index = _chunk(b"File", _chunk(b"info", info) + _chunk(b"segm", table)
                   + _chunk(b"adlr", struct.pack("<I", zlib.adler32(plain))) + section_extra)
    if index_compress:
        stored_index = zlib.compress(index) + index_suffix
        index_frame = b"\1" + struct.pack("<QQ", len(stored_index), len(index)) + stored_index
    else:
        index_frame = b"\0" + struct.pack("<Q", len(index)) + index
    return b"XP3\r\n \n\x1a\x8bg\x01" + struct.pack("<Q", 19 + len(body)) + body + index_frame


def _pint(value):
    return b"I" + str(value).encode("ascii") + b"\n"


def _pbytes(value):
    return b"T" + struct.pack("<I", len(value)) + value


def _rpa_index(chunks, *, key=0x12345678, name=b"script.rpy"):
    encoded = b"\x80\x02}(" + _pbytes(name) + b"]("
    for offset, length, prefix in chunks:
        encoded += b"(" + _pint(offset ^ key) + _pint(length ^ key)
        if prefix is not None:
            encoded += _pbytes(prefix)
        encoded += b"t"
    return encoded + b"eu."


def _rpa(index, *, body=b"abc", key=0x12345678):
    return f"RPA-3.0 {34 + len(body):016x} {key:08x}\n".encode("ascii") + body + zlib.compress(index)


def _sar(payload=b"abc", name=b"a.txt"):
    base = 6 + len(name) + 1 + 8
    return struct.pack(">HI", 1, base) + name + b"\0" + struct.pack(">II", 0, len(payload)) + payload


def _nsa(payload=b"abc", *, method=0, raw_size=None, name=b"a.txt", prefix=False):
    base = 6 + len(name) + 1 + 13
    if raw_size is None:
        raw_size = len(payload)
    return ((b"\0\0" if prefix else b"") + struct.pack(">HI", 1, base) + name + b"\0"
            + struct.pack(">BIII", method, 0, len(payload), raw_size) + payload)


def _pfs(version, files=(("a.txt", b"abcdef"),), *, encoding="cp932"):
    if version == 0:
        base = 7 + len(files) * 0x10c
        index, body = bytearray(), bytearray()
        for name, content in files:
            index.extend(name.encode("ascii").ljust(0x104, b"\0"))
            index.extend(struct.pack("<II", base + len(body), len(content)))
            body.extend(content)
        return b"pf0" + struct.pack("<I", len(files)) + index + body
    encoded_names = [name.encode("cp932" if version == 2 else encoding) for name, _ in files]
    index_size = (8 if version == 2 else 4) + sum(len(n) + (24 if version == 2 else 16) for n in encoded_names)
    base = 7 + index_size
    index = bytearray((b"\0" * 4 if version == 2 else b"") + struct.pack("<I", len(files)))
    offset = base
    for (_, content), name in zip(files, encoded_names):
        index.extend(struct.pack("<I", len(name)) + name + b"\0" * (12 if version == 2 else 4))
        index.extend(struct.pack("<II", offset, len(content)))
        offset += len(content)
    key = hashlib.sha1(index).digest()
    body = b"".join(bytes(v ^ key[i % 20] for i, v in enumerate(content)) if version == 8 else content
                    for _, content in files)
    return b"pf" + str(version).encode("ascii") + struct.pack("<I", len(index)) + index + body


def _majiro(version, content=b"obj bytes"):
    names = b"a.mjo\0"
    stride = 4 * (version + 1)
    names_at = 28 + stride * (2 if version == 1 else 1)
    data_at = names_at + len(names)
    if version == 1:
        index = struct.pack("<4I", 0x12345678, data_at, 0, data_at + len(content))
    elif version == 2:
        index = struct.pack("<III", 0x12345678, data_at, len(content))
    else:
        index = struct.pack("<QII", 0x123456789abcdef0, data_at, len(content))
    return (f"MajiroArcV{version}.000\0".encode("ascii")
            + struct.pack("<III", 1, names_at, data_at) + index + names + content)


def _bgi(payload=b"raw script", *, version=1):
    signature, stride, namesize = (b"PackFile    ", 0x20, 0x10) if version == 1 else (b"BURIKO ARC20", 0x80, 0x60)
    index = b"a.scr\0".ljust(namesize, b"\0") + struct.pack("<II", 0, len(payload))
    return signature + struct.pack("<I", 1) + index.ljust(stride, b"\0") + payload


def _lz_literal(payload):
    body = b"".join(bytes([(1 << len(payload[i:i + 8])) - 1]) + payload[i:i + 8]
                    for i in range(0, len(payload), 8))
    return struct.pack("<II", 8 + len(body), len(payload)) + body


def _scene(files=(("start", b"bytecode\x00\xff"),), *, game_key=None, frame_override=None):
    count, name_index = len(files), 0x5c
    names_at = name_index + count * 8
    name_records, names = bytearray(), bytearray()
    for name, _ in files:
        encoded = name.encode("utf-16-le")
        name_records.extend(struct.pack("<II", len(names) // 2, len(encoded) // 2))
        names.extend(encoded)
    pos_index = names_at + len(names)
    data_at = pos_index + count * 8
    positions, body = bytearray(), bytearray()
    for _, plain in files:
        frame = _lz_literal(plain) if frame_override is None else frame_override
        encrypted = bytes(v ^ siglus.DEFAULT_KEY[i % 256] ^ (game_key[i % 16] if game_key else 0)
                          for i, v in enumerate(frame))
        positions.extend(struct.pack("<II", len(body), len(encrypted)))
        body.extend(encrypted)
    header = bytearray(0x5c)
    struct.pack_into("<I", header, 0, 0x5c)
    struct.pack_into("<9I", header, 0x34, name_index, count, names_at, count,
                     pos_index, count, data_at, count, int(game_key is not None))
    return bytes(header + name_records + names + positions + body)


class XP3Tests(unittest.TestCase):
    def read(self, data, **kwargs):
        return xp3.extract(data, filter_name="none", **kwargs)

    def test_manual_multisegment_and_repeated_range(self):
        rows = self.read(_xp3((b"ab", b"cd"), repeat=True))
        self.assertEqual(rows[0].data, b"abcdab")
        self.assertEqual(rows[0].segment_count, 3)
        with self.assertRaises(ValueError):
            self.read(_xp3((b"ab",), repeat=True), max_file_size=3)

    def test_zlib_index_and_contents(self):
        self.assertEqual(self.read(_xp3((b"A" * 100, b"B"), compress=True, index_compress=True))[0].data,
                         b"A" * 100 + b"B")

    def test_writer_four_compression_combinations(self):
        files = [("script.ks", b"a" * 100), ("empty.txt", b"")]
        for index in (False, True):
            for contents in (False, True):
                with self.subTest(index=index, contents=contents):
                    archive = xp3.build(files, filter_name="none", compress_index=index, compress_contents=contents)
                    self.assertEqual([(r.name, r.data) for r in self.read(archive)], files)

    def test_bad_magic_short_header_and_index(self):
        fixture = _xp3()
        for value in (b"", b"MZ" + fixture, b"BAD" + fixture[3:], fixture[:18], fixture[:-1]):
            with self.subTest(length=len(value)), self.assertRaises(ValueError):
                self.read(value)
        broken = bytearray(fixture)
        struct.pack_into("<Q", broken, 11, len(broken) + 1)
        with self.assertRaises(ValueError):
            self.read(bytes(broken))

    def test_encryption_unknown_filter_and_sections_rejected(self):
        for fixture in (_xp3(info_flags=0x80000000), _xp3(seg_flag=2),
                        _xp3(section_extra=_chunk(b"filt", b"")),
                        _xp3(section_extra=_chunk(b"adlr", b"\0" * 4))):
            with self.assertRaises(ValueError):
                self.read(fixture)
        with self.assertRaises(ValueError):
            xp3.extract(_xp3(), filter_name="unknown")
        with self.assertRaises(TypeError):
            xp3.extract(_xp3())
        fixture = bytearray(_xp3())
        index_at, = struct.unpack_from("<Q", fixture, 11)
        fixture[index_at] = 0x80
        with self.assertRaises(ValueError):
            self.read(bytes(fixture))

    def test_checksum_mismatch(self):
        fixture = bytearray(_xp3())
        fixture[19] ^= 1
        with self.assertRaises(ValueError):
            self.read(bytes(fixture))

    def test_zlib_trailing_data_rejected(self):
        for fixture in (_xp3(compress=True, stored_suffix=b"junk"),
                        _xp3(index_compress=True, index_suffix=b"junk")):
            with self.assertRaises(ValueError):
                self.read(fixture)

    def test_segment_bounds_and_totals(self):
        for field, value in ((4, 0xffffffffffffffff), (12, 4), (20, 4)):
            fixture = bytearray(_xp3())
            pos = fixture.index(b"segm") + 12
            struct.pack_into("<Q", fixture, pos + field, value)
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.read(bytes(fixture))

    def test_limits(self):
        fixture = _xp3((b"abc", b"def"), compress=True, index_compress=True)
        for limit in ({"max_entries": 0}, {"max_segments": 1}, {"max_index_size": 4},
                      {"max_total_size": 5}, {"max_archive_size": 10}, {"max_file_size": -1}):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                self.read(fixture, **limit)
        with self.assertRaises(ValueError):
            xp3.build([("a", b"a"), ("a", b"b")], filter_name="none")


class RPATests(unittest.TestCase):
    def test_protocol0_high_byte_prefix(self):
        index = b"(dS'a.rpy'\n(l(I34\nI4\nS'\\xff'\ntas."
        entry = rpa.extract(_rpa(index, key=0))[0]
        self.assertEqual(entry.name, "a.rpy")
        self.assertEqual(entry.data, b"\xffabc")

    def test_protocol0_utf8_byte_filename(self):
        literal = repr("场景.rpy".encode("utf-8")).encode("ascii")[1:]
        index = b"(dS" + literal + b"\n(l(I34\nI3\ntas."
        entry = rpa.extract(_rpa(index, key=0))[0]
        self.assertEqual(entry.name, "场景.rpy")
        self.assertEqual(entry.data, b"abc")

    def test_protocol0_string_requires_quotes_and_newline(self):
        for value in (b"S'unterminated'", b"Sunquoted\n.", b"S'bad\\xQZ'\n."):
            with self.subTest(value=value), self.assertRaises(ValueError):
                rpa._data_pickle(value)

    def test_prefix_total_length_and_high_xor_key(self):
        key = 0xfedcba98
        fixture = _rpa(_rpa_index([(34, 6, b"pre")], key=key), body=b"fix", key=key)
        entry = rpa.extract(fixture)[0]
        self.assertEqual(entry.data, b"prefix")
        self.assertEqual(entry.prefix_size, 3)
        self.assertEqual(entry.offset, 34)

    def test_prefix_only_and_no_prefix(self):
        self.assertEqual(rpa.extract(_rpa(_rpa_index([(34, 3, b"all")]), body=b""))[0].data, b"all")
        self.assertEqual(rpa.extract(_rpa(_rpa_index([(34, 3, None)])))[0].data, b"abc")

    def test_protocol3_and_latin1_unicode_prefix(self):
        mapping = {"a.rpy": [(34 ^ 7, 4 ^ 7, "ÿ")]}
        fixture = _rpa(pickle.dumps(mapping, protocol=3), key=7)
        self.assertEqual(rpa.extract(fixture)[0].data, b"\xffabc")
        mapping["a.rpy"] = [(34 ^ 7, 4 ^ 7, b"Z")]
        self.assertEqual(rpa.extract(_rpa(pickle.dumps(mapping, protocol=3), key=7))[0].data, b"Zabc")

    def test_multiple_chunks_never_silently_drop(self):
        for chunks in ([], [(34, 3, b""), (34, 3, b"")]):
            with self.assertRaisesRegex(ValueError, "multi-chunk"):
                rpa.extract(_rpa(_rpa_index(chunks)))

    def test_wrong_prefix_length_and_bad_ranges(self):
        for chunk in ((34, 1, b"abc"), (0, 3, b""), (36, 3, b""), (34, 1000, b"")):
            with self.subTest(chunk=chunk), self.assertRaises(ValueError):
                rpa.extract(_rpa(_rpa_index([chunk])))

    def test_code_execution_opcodes_rejected(self):
        for program in (b"cos\nsystem\n.", b"\x80\x02}R.", b"\x80\x02}b.", b"Pobject\n."):
            with self.subTest(program=program), self.assertRaises(ValueError):
                rpa.extract(_rpa(program))

    def test_memo_cycles_and_memo_limit(self):
        self.assertEqual(rpa._data_pickle(b"\x80\x02(K\x01q\x00h\x00t."), (1, 1))
        with self.assertRaises(ValueError):
            rpa._data_pickle(b"\x80\x02]q\x00h\x00a.")
        with self.assertRaises(ValueError):
            rpa._data_pickle(b"\x80\x02K\x01q\x02.", max_memo=2)

    def test_pickle_stack_depth_and_ops_limits(self):
        with self.assertRaises(ValueError):
            rpa._data_pickle(b"\x80\x02K\x01" + b"\x85" * 33 + b".")
        with self.assertRaises(ValueError):
            rpa._data_pickle(b"\x80\x02(K\x01K\x02t.", max_stack=2)
        with self.assertRaises(ValueError):
            rpa._data_pickle(b"\x80\x02K\x01.", max_ops=1)
        with self.assertRaises(ValueError):
            rpa._data_pickle(b"\x80\x02K\x01.junk")

    def test_duplicate_dictionary_and_decoded_names(self):
        with self.assertRaises(ValueError):
            rpa._data_pickle(b"}(U\x01aK\x01U\x01aK\x02u.")
        key = 3
        mapping = {"a": [(34 ^ key, 3 ^ key)], b"a": [(34 ^ key, 3 ^ key)]}
        with self.assertRaises(ValueError):
            rpa.extract(_rpa(pickle.dumps(mapping, protocol=3), key=key))

    def test_bad_header_and_truncated_index(self):
        fixture = _rpa(_rpa_index([(34, 3, None)]))
        for bad in (b"", fixture[:33], fixture.replace(b"RPA-3.0", b"RPA-2.0", 1), fixture[:-1], fixture + b"junk"):
            with self.subTest(length=len(bad)), self.assertRaises(ValueError):
                rpa.extract(bad)
        bad = bytearray(fixture)
        bad[8:24] = b"f" * 16
        with self.assertRaises(ValueError):
            rpa.extract(bytes(bad))

    def test_bounded_inflate_and_output(self):
        with self.assertRaises(ValueError):
            rpa.extract(_rpa(b"A" * 10000), max_index_size=100)
        fixture = _rpa(_rpa_index([(34, 3, None)]))
        for limits in ({"max_total_size": 2}, {"max_file_size": 2}, {"max_entries": 0},
                       {"max_pickle_ops": 1}, {"max_pickle_memo": -1}):
            with self.subTest(limits=limits), self.assertRaises(ValueError):
                rpa.extract(fixture, **limits)


class NScripterTests(unittest.TestCase):
    def test_xor_known_bytes_and_roundtrip(self):
        self.assertEqual(nscripter.xor_nscript(b"\x84\x85\x00"), b"\0\1\x84")
        source = "*start\r\n「こんにちは」\\\r\n".encode("cp932")
        self.assertEqual(nscripter.xor_nscript(nscripter.xor_nscript(source)), source)
        with self.assertRaises(ValueError):
            nscripter.xor_nscript(source, max_size=1)

    def test_manual_sar_big_endian(self):
        entry = nscripter.extract_sar(_sar(b"text", "日本.txt".encode("cp932")))[0]
        self.assertEqual((entry.name, entry.data), ("日本.txt", b"text"))

    def test_sar_writer_roundtrip(self):
        files = [("a.txt", b"a"), ("empty", b"")]
        self.assertEqual([(e.name, e.data) for e in nscripter.extract_sar(nscripter.build_sar(files))], files)

    def test_nsa_raw_and_optional_prefix(self):
        for prefix in (False, True):
            self.assertEqual(nscripter.extract_nsa(_nsa(prefix=prefix))[0].data, b"abc")

    def test_nbz_and_suffix_detection(self):
        source = b"abc" * 100
        packed = struct.pack(">I", len(source)) + bz2.compress(source)
        for fixture in (_nsa(packed, method=4, raw_size=len(source)),
                        _nsa(packed, name=b"a.nbz", raw_size=len(packed))):
            entry = nscripter.extract_nsa(fixture)[0]
            self.assertEqual(entry.data, source)
            self.assertEqual(entry.compression, "nbz")

    def test_nsa_writers_raw_and_nbz(self):
        files = [("a.txt", b"a" * 100), ("b", b"")]
        for method in (0, 4):
            self.assertEqual([(e.name, e.data) for e in nscripter.extract_nsa(nscripter.build_nsa(files, compression=method))], files)
        with self.assertRaises(ValueError):
            nscripter.build_nsa([("a.nbz", b"plaintext")])

    def test_nbz_lengths_truncation_trailing_and_limit(self):
        packed = struct.pack(">I", 3) + bz2.compress(b"abc")
        for bad in (packed[:-1], packed + b"junk", struct.pack(">I", 2) + packed[4:], b"\0\0\0\3BZh"):
            with self.assertRaises(ValueError):
                nscripter.decode_nbz(bad)
        with self.assertRaises(ValueError):
            nscripter.decode_nbz(packed, max_output_size=2)
        with self.assertRaises(ValueError):
            nscripter.decode_nbz(packed, max_input_size=4)
        with self.assertRaises(ValueError):
            nscripter.extract_nsa(_nsa(packed, method=4, raw_size=100))

    def test_unsupported_nsa_methods(self):
        for method in (1, 2, 3, 255):
            with self.subTest(method=method), self.assertRaises(ValueError):
                nscripter.extract_nsa(_nsa(method=method))

    def test_short_bad_index_and_oob(self):
        for read, fixture in ((nscripter.extract_sar, _sar()), (nscripter.extract_nsa, _nsa())):
            for bad in (b"", fixture[:5], fixture[:-1], b"\0\0" + fixture[2:]):
                with self.subTest(read=read.__name__, length=len(bad)), self.assertRaises(ValueError):
                    read(bad)
            bad = bytearray(fixture)
            struct.pack_into(">I", bad, 2, len(fixture) + 10)
            with self.assertRaises(ValueError):
                read(bytes(bad))

    def test_limits_mismatched_raw_and_duplicate_names(self):
        with self.assertRaises(ValueError):
            nscripter.extract_nsa(_nsa(raw_size=100))
        for reader, fixture in ((nscripter.extract_sar, _sar()), (nscripter.extract_nsa, _nsa())):
            for limits in ({"max_entries": 0}, {"max_total_size": 2}, {"max_file_size": 2}):
                with self.assertRaises(ValueError):
                    reader(fixture, **limits)
        with self.assertRaises(ValueError):
            nscripter.build_sar([("a", b"a"), ("a", b"b")])
        # These different Unicode names encode to the same CP932 bytes.
        with self.assertRaises(ValueError):
            nscripter.build_sar([("〜", b"a"), ("～", b"b")])
        with self.assertRaises(ValueError):
            nscripter.build_nsa([("日本", b"x")], max_archive_size=2)


class PFSTests(unittest.TestCase):
    def test_four_manual_versions(self):
        for version in (0, 2, 6, 8):
            with self.subTest(version=version):
                entry = pfs.extract(_pfs(version))[0]
                self.assertEqual(entry.data, b"abcdef")
                self.assertEqual(entry.version, version)

    def test_pf8_sha1_period_and_restart(self):
        files = (("one", bytes(range(60))), ("two", b"Z" * 41))
        entries = pfs.extract(_pfs(8, files))
        self.assertEqual([(e.name, e.data) for e in entries], list(files))

    def test_explicit_utf8_names(self):
        fixture = _pfs(8, (("场景.txt", b"data"),), encoding="utf-8")
        self.assertEqual(pfs.extract(fixture, name_encoding="utf-8")[0].name, "场景.txt")

    def test_unsupported_magic_and_truncation(self):
        for version in (0, 2, 6, 8):
            fixture = _pfs(version)
            for bad in (fixture[:2], b"pf9" + fixture[3:], fixture[:-1]):
                with self.assertRaises(ValueError):
                    pfs.extract(bad)

    def test_index_size_name_length_and_data_bounds(self):
        fixture = _pfs(8)
        for offset, value in ((3, 0xffffffff), (7, 0xffffffff), (11, 0xffffffff), (24, 0xffffffff)):
            bad = bytearray(fixture)
            struct.pack_into("<I", bad, offset, value)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                pfs.extract(bytes(bad))

    def test_duplicate_names_and_budgets(self):
        with self.assertRaises(ValueError):
            pfs.extract(_pfs(6, (("a", b"1"), ("a", b"2"))))
        for limits in ({"max_entries": 0}, {"max_file_size": 5}, {"max_total_size": 5}, {"max_index_size": 4}):
            with self.assertRaises(ValueError):
                pfs.extract(_pfs(8), **limits)

    def test_trailing_index_table_is_tolerated_and_hashed(self):
        # Real archives declare more index bytes than the entry records use.
        extra = b"\x04\x00\x00\x00\x01\x00\x00\x00\x02\x00\x00\x00\x03\x00\x00\x00"
        name = b"a.txt"
        record = struct.pack("<I", len(name)) + name + b"\0" * 4
        entry_size = 4 + len(record) + 8
        index_size = entry_size + len(extra)
        index = bytearray(struct.pack("<I", 1) + record)
        index.extend(struct.pack("<II", 7 + index_size, 6))
        index.extend(extra)
        self.assertEqual(len(index), index_size)
        key = hashlib.sha1(bytes(index)).digest()
        body = bytes(v ^ key[i % 20] for i, v in enumerate(b"abcdef"))
        fixture = b"pf8" + struct.pack("<I", index_size) + bytes(index) + body

        self.assertEqual(pfs.extract(fixture)[0].data, b"abcdef")
        index_info = pfs.read_index(fixture)
        self.assertEqual(index_info.trailing, extra)
        self.assertEqual(index_info.index_sha1, hashlib.sha1(bytes(index)).hexdigest())
        # Rebuilding must reproduce the same bytes, trailing table included.
        payloads = {entry.ordinal: pfs.read_member(fixture, index_info, entry).data
                    for entry in index_info.entries}
        self.assertEqual(pfs.repack(index_info, payloads), fixture)

    def test_identity_repack_for_every_supported_version(self):
        for version in (0, 2, 6, 8):
            with self.subTest(version=version):
                fixture = _pfs(version, (("a.txt", b"abcdef"), ("b.bin", bytes(range(40)))))
                index = pfs.read_index(fixture)
                payloads = {entry.ordinal: pfs.read_member(fixture, index, entry).data
                            for entry in index.entries}
                self.assertEqual(pfs.repack(index, payloads), fixture)

    def test_repack_replaces_one_member_and_keeps_the_rest(self):
        fixture = _pfs(8, (("a.txt", b"abcdef"), ("b.bin", b"XYZ")))
        index = pfs.read_index(fixture)
        payloads = {entry.ordinal: pfs.read_member(fixture, index, entry).data
                    for entry in index.entries}
        payloads[1] = b"longer replacement"
        rebuilt = pfs.repack(index, payloads)
        after = pfs.read_index(rebuilt)
        self.assertEqual([entry.name for entry in after.entries], ["a.txt", "b.bin"])
        self.assertEqual(pfs.read_member(rebuilt, after, after.entries[0]).data, b"abcdef")
        self.assertEqual(pfs.read_member(rebuilt, after, after.entries[1]).data, b"longer replacement")
        with self.assertRaises(ValueError):
            pfs.repack(index, {0: b"only one"})

    def test_stream_api_and_path_limits(self):
        fixture = _pfs(8, (("a.txt", b"abcdef"),))
        stream = io.BytesIO(fixture)
        index = pfs.read_index(stream)
        self.assertEqual(pfs.read_member(stream, index, index.entries[0]).data, b"abcdef")
        with self.assertRaises(ValueError):
            pfs.read_index(io.BytesIO(fixture), max_archive_size=4)
        with self.assertRaises(ValueError):
            pfs.read_index(b"pf9" + fixture[3:])
        with self.assertRaises(ValueError):
            pfs.read_member(io.BytesIO(fixture), index, index.entries[0], max_stored_size=2)

    def test_name_encoding_autodetection(self):
        utf8_fixture = _pfs(8, (("シーン.txt", b"x"),), encoding="utf-8")
        cp932_fixture = _pfs(8, (("テスト.txt", b"x"),), encoding="cp932")
        self.assertEqual(pfs.read_index(utf8_fixture).name_encoding, "utf-8")
        self.assertEqual(pfs.read_index(cp932_fixture).name_encoding, "cp932")
        with self.assertRaises(ValueError):
            pfs.read_index(cp932_fixture, name_encoding="utf-8")
        with self.assertRaises(ValueError):
            pfs.read_index(utf8_fixture, name_encoding="no-such-codec")

    def test_volume_set_resolution_and_override_chain(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "base.pfs").write_bytes(_pfs(8, (("only_base.txt", b"1"),
                                                     ("shared.txt", b"old"))))
            (root / "base.pfs.000").write_bytes(_pfs(6, (("shared.txt", b"new"),)))
            (root / "base.pfs.001").write_bytes(_pfs(6, (("other.txt", b"3"),)))
            for supplied in ("base.pfs", "base.pfs.000", "base.pfs.001"):
                found = [Path(path).name for path in pfs.volume_paths(root / supplied)]
                self.assertEqual(found, ["base.pfs", "base.pfs.000", "base.pfs.001"])
            indexes = [(Path(path).name, pfs.read_index(path))
                       for path in pfs.volume_paths(root / "base.pfs")]
            merged = pfs.resolve_volumes(indexes)
            self.assertEqual(sorted(merged.by_name()), ["only_base.txt", "other.txt", "shared.txt"])
            winner = merged.by_name()["shared.txt"]
            self.assertEqual(winner.volume, "base.pfs.000")
            self.assertEqual(winner.overrides, ("base.pfs",))
            with (root / winner.volume).open("rb") as stream:
                self.assertEqual(pfs.read_member(stream, dict(indexes)["base.pfs.000"],
                                                 winner.entry).data, b"new")
        with self.assertRaises(ValueError):
            pfs.volume_paths(Path(temp) / "missing.pfs")

    def test_writer_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            pfs.build([("a", b"1"), ("a", b"2")])
        with self.assertRaises(ValueError):
            pfs.build([("a", "not bytes")])
        with self.assertRaises(ValueError):
            pfs.build([("a", b"1")], index_order=[0, 1])
        with self.assertRaises(ValueError):
            pfs.build([("日本", b"1")], version=0)
        with self.assertRaises(ValueError):
            pfs.build([("日本", b"1")], version=8, name_encoding="ascii")
        with self.assertRaises(ValueError):
            pfs.build([("a", b"1")], version=9)


class MajiroTests(unittest.TestCase):
    def test_three_distinct_index_layouts(self):
        for version in (1, 2, 3):
            entry = majiro.extract(_majiro(version))[0]
            self.assertEqual(entry.data, b"obj bytes")
            self.assertEqual(entry.version, version)
            self.assertEqual(entry.name_hash, 0x123456789abcdef0 if version == 3 else 0x12345678)

    def test_writer_fixed_v1_sorted_crc_and_empty_entry(self):
        files = [("z.mjo", b"zzz"), ("a.mjo", b""), ("b.mjo", b"b")]
        archive = majiro.build_v1(files)
        self.assertEqual(archive[:16], b"MajiroArcV1.000\0")
        entries = majiro.extract(archive)
        self.assertEqual(sorted((e.name, e.data) for e in entries), sorted(files))
        self.assertEqual([e.name_hash for e in entries], sorted(e.name_hash for e in entries))
        self.assertEqual(struct.unpack_from("<II", archive, 28 + len(files) * 8), (0, len(archive)))

    def test_bad_header_table_names_and_sentinel(self):
        fixture = _majiro(1)
        for offset, value in ((16, 0xffffffff), (20, 0), (24, len(fixture) + 1), (40, 0)):
            bad = bytearray(fixture)
            struct.pack_into("<I", bad, offset, value)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                majiro.extract(bytes(bad))
        for bad in (fixture[:15], fixture.replace(b"V1", b"V4", 1), fixture[:-1], fixture + b"extra"):
            with self.assertRaises(ValueError):
                majiro.extract(bad)
        bad = bytearray(fixture)
        bad[49] = ord("x")  # remove the sole name terminator
        with self.assertRaises(ValueError):
            majiro.extract(bytes(bad))

    def test_descending_v1_offsets_and_v2_v3_oob(self):
        for version, offset in ((1, 40), (2, 36), (3, 40)):
            bad = bytearray(_majiro(version))
            struct.pack_into("<I", bad, offset, 1 if version == 1 else 0xffffffff)
            with self.assertRaises(ValueError):
                majiro.extract(bytes(bad))

    def test_writer_name_and_size_limits(self):
        for files in ([('a/b', b"x")], [("a", b"1"), ("a", b"2")], [("a\0b", b"x")]):
            with self.assertRaises(ValueError):
                majiro.build_v1(files)
        with self.assertRaises(ValueError):
            majiro.build_v1([("a", b"x")], max_archive_size=1)
        with self.assertRaises(ValueError):
            majiro.extract(_majiro(2), max_file_size=1)


class BGITests(unittest.TestCase):
    def test_both_headers_and_unwrapped_bytes(self):
        for version in (1, 2):
            entry = bgi.inspect(_bgi(version=version))[0]
            self.assertEqual(entry.codec, "raw")
            self.assertEqual(bgi.require_plain(entry), b"raw script")

    def test_dsc_explicitly_opaque_not_false_success(self):
        stored = bytearray(0x221)
        stored[:16] = b"DSC FORMAT 1.00\0"
        struct.pack_into("<I", stored, 0x14, 7)
        entry = bgi.inspect(_bgi(bytes(stored)))[0]
        self.assertEqual(entry.codec, "dsc")
        self.assertEqual(entry.stored_data, bytes(stored))
        self.assertEqual(entry.unpacked_size, 7)
        with self.assertRaises(ValueError):
            bgi.require_plain(entry)
        struct.pack_into("<I", stored, 0x14, 0xffffffff)
        with self.assertRaises(ValueError):
            bgi.inspect(_bgi(bytes(stored)))

    def test_bse_marked_opaque_and_unknown_rejected(self):
        stored = bytearray(0x50)
        stored[:6] = b"BSE 1."
        struct.pack_into("<H", stored, 8, 0x101)
        entry = bgi.inspect(_bgi(bytes(stored), version=2))[0]
        self.assertEqual(entry.codec, "bse")
        with self.assertRaises(ValueError):
            bgi.require_plain(entry)
        struct.pack_into("<H", stored, 8, 0x200)
        with self.assertRaises(ValueError):
            bgi.inspect(_bgi(bytes(stored), version=2))

    def test_bad_magic_truncation_bounds_and_limit(self):
        fixture = _bgi()
        for bad in (fixture[:15], b"Bad!" + fixture[4:], fixture[:-1], _bgi(b"DSC FORMAT 1.00\0")):
            with self.assertRaises(ValueError):
                bgi.inspect(bad)
        bad = bytearray(fixture)
        struct.pack_into("<I", bad, 0x20, 0xffffffff)
        with self.assertRaises(ValueError):
            bgi.inspect(bytes(bad))
        with self.assertRaises(ValueError):
            bgi.inspect(fixture, max_total_size=2)


class BgiWriterTests(unittest.TestCase):
    """The rewriter must reproduce a layout the reader in this package accepts."""

    def payloads(self):
        return [("days_01", bgi_dsc.encode(b"BurikoCompiledScriptVer1.00\0" + b"body" * 60)),
                ("asset", b"\x89PNG\r\n\x1a\n" + b"data" * 40),
                ("empty", b"")]

    def read_back(self, archive):
        stream = io.BytesIO(archive)
        index = bgi.read_index(stream)
        return stream, index

    def test_both_versions_round_trip_through_the_reader(self):
        for version in (1, 2):
            with self.subTest(version=version):
                members = self.payloads()
                archive = bgi_writer.build_archive(members, version=version)
                stream, index = self.read_back(archive)
                self.assertEqual(index.version, version)
                self.assertEqual([e.name for e in index.entries], [n for n, _ in members])
                self.assertEqual(index.index_end,
                                 16 + len(members) * (0x20 if version == 1 else 0x80))
                for entry, (name, payload) in zip(index.entries, members):
                    stored = bgi.read_member(stream, index, entry)
                    self.assertEqual(stored.stored_data, payload, name)
                    self.assertEqual(entry.offset, index.index_end + sum(
                        len(p) for _, p in members[:entry.ordinal]))
                first = bgi.probe_member(stream, index, index.entries[0])
                self.assertEqual(first.codec, "dsc")
                self.assertTrue(bgi.decode_member(bgi.read_member(stream, index, index.entries[0]))
                                .startswith(b"BurikoCompiledScriptVer1.00\0"))

    def test_row_extra_region_is_preserved_verbatim(self):
        # Real BGI v2 rows carry non-zero bytes after the size field. They are
        # opaque, so a faithful rebuild must copy them instead of zeroing.
        extra = bytes(range(24))
        archive = bgi_writer.build_archive([("a", b"payload", extra)], version=2)
        self.assertEqual(archive[16 + 0x68:16 + 0x80], extra)
        _, index = self.read_back(archive)
        self.assertEqual(index.entries[0].extra, extra)
        self.assertEqual(bgi_writer.row_length(2), 24)
        self.assertEqual(bgi_writer.row_length(1), 8)
        default = bgi_writer.build_archive([("a", b"payload")], version=2)
        self.assertEqual(default[16 + 0x68:16 + 0x80], bytes(24))
        self.assertEqual(bgi.read_index(io.BytesIO(_bgi(version=2))).entries[0].extra, bytes(24))

    def test_names_order_and_offsets_are_preserved_not_sorted(self):
        members = [("zz", b"1"), ("aa", b"22"), ("mid", b"333")]
        archive = bgi_writer.build_archive(members, version=2)
        _, index = self.read_back(archive)
        self.assertEqual([e.name for e in index.entries], ["zz", "aa", "mid"])
        self.assertEqual([e.size for e in index.entries], [1, 2, 3])
        self.assertEqual([e.offset - index.index_end for e in index.entries], [0, 1, 3])

    def test_rejects_unsupported_inputs(self):
        cases = [
            ("empty_archive", [], 2),
            ("unsupported_version", [("a", b"x")], 3),
            ("input_type", [("a", "not-bytes")], 2),
            ("input_type", ["a"], 2),
            ("duplicate_name", [("a", b"x"), ("a", b"y")], 2),
            ("invalid_name", [("x" * 0x61, b"y")], 2),
            ("invalid_name", [("", b"y")], 2),
            ("invalid_name", [("\0", b"y")], 2),
            ("row_extra", [("a", b"x", b"\0" * 3)], 2),
        ]
        for code, members, version in cases:
            with self.subTest(code=code, members=members, version=version):
                with self.assertRaises(bgi.BgiArchiveError) as caught:
                    bgi_writer.build_archive(members, version=version)
                self.assertEqual(caught.exception.code, code)
        for kwargs in ({"max_members": 0}, {"max_total_size": 1}):
            with self.subTest(**kwargs):
                with self.assertRaises(bgi.BgiArchiveError):
                    bgi_writer.build_archive([("a", b"xy")], version=2, **kwargs)
        with self.assertRaises(bgi.BgiArchiveError):
            bgi_writer.build_archive([("日本", b"x")], version=1, name_encoding="ascii")

    def test_v1_name_field_and_verify_flag(self):
        archive = bgi_writer.build_archive([("0123456789abcde", b"x")], version=1)
        _, index = self.read_back(archive)
        self.assertEqual(index.entries[0].name, "0123456789abcde")
        unverified = bgi_writer.build_archive(self.payloads(), version=2, verify=False)
        self.assertEqual([e.name for e in self.read_back(unverified)[1].entries],
                         [n for n, _ in self.payloads()])

    def test_pack_member_chooses_the_stored_form(self):
        raw = b"member body" * 20
        self.assertEqual(bgi_writer.pack_member(raw, compress=False), raw)
        self.assertEqual(bgi_dsc.decode(bgi_writer.pack_member(raw)), raw)
        with self.assertRaises(bgi.BgiArchiveError) as caught:
            bgi_writer.pack_member(raw, compress=False, allow_plain=False)
        self.assertEqual(caught.exception.code, "unsupported_codec")
        with self.assertRaises(bgi.BgiArchiveError):
            bgi_writer.pack_member(bytearray(raw))

    def test_rebuilt_archive_serves_a_patched_script_end_to_end(self):
        from python.engines import bgi as engine
        from bgi_v1_fixtures import make_v1_fixture
        raw = make_v1_fixture((("Alice", "Hello"), (None, "Narration")))
        analysis = engine.scan_v1(raw)
        message = next(ref for ref in analysis.references if ref.text == "Hello")
        patched = engine.patch_v1(raw, {message.operand: "Longer greeting"})
        archive = bgi_writer.build_archive(
            [("scene", bgi_writer.pack_member(patched)), ("video", b"v" * 500)], version=2)
        stream, index = self.read_back(archive)
        decoded = bgi.decode_member(bgi.read_member(stream, index, index.entries[0]))
        rows, _, _ = engine.export_v1(engine.scan_v1(decoded))
        self.assertEqual(rows, [{"name": "Alice", "message": "Longer greeting"},
                                {"message": "Narration"}])
        self.assertEqual(decoded[analysis.code_base + analysis.code_length:len(patched)],
                         patched[analysis.code_base + analysis.code_length:])


class SiglusTests(unittest.TestCase):
    def test_default_key_boundaries(self):
        self.assertEqual(len(siglus.DEFAULT_KEY), 256)
        self.assertEqual(siglus.DEFAULT_KEY[:16].hex(), "70f8a6b0a1a5284fb52f48fae1e94bde")
        self.assertEqual(siglus.DEFAULT_KEY[-16:].hex(), "36bce5607768084fbbabe27807e873bf")

    def test_plain_key_scene_extraction_remains_bytecode(self):
        entry = siglus.extract(_scene())[0]
        self.assertEqual(entry.data, b"bytecode\0\xff")
        self.assertEqual(entry.name, "start.ss")
        self.assertEqual(entry.content_type, "siglus-bytecode")

    def test_key_period_and_reset_per_scene(self):
        files = (("a", bytes(range(256)) * 2), ("b", b"xyz" * 100))
        key = bytes(range(16))
        entries = siglus.extract(_scene(files, game_key=key), game_key=key)
        self.assertEqual([(e.name, e.data) for e in entries], [(n + ".ss", d) for n, d in files])

    def test_missing_bad_wrong_and_unneeded_game_key(self):
        key = bytes(range(16))
        fixture = _scene(game_key=key)
        for bad_key in (None, b"", b"0" * 15, bytes(v ^ 255 for v in key)):
            with self.assertRaises(ValueError):
                siglus.extract(fixture, game_key=bad_key)
        with self.assertRaises(ValueError):
            siglus.extract(_scene(), game_key=key)

    def test_lz_literals_and_overlapping_copy(self):
        self.assertEqual(siglus.lz_decompress(_lz_literal(b"123456789")), b"123456789")
        body = b"\3AB\x23\0"  # two literals; distance 2, length 5
        self.assertEqual(siglus.lz_decompress(struct.pack("<II", 8 + len(body), 7) + body), b"ABABABA")
        self.assertEqual(siglus.lz_decompress(struct.pack("<II", 8, 0)), b"")

    def test_lz_short_long_and_invalid_references(self):
        frame = _lz_literal(b"abc")
        for bad in (frame[:-1], frame + b"x", struct.pack("<II", 11, 2) + b"\0\0\0",
                    struct.pack("<II", 11, 2) + b"\0\xf0\0",
                    struct.pack("<II", 12, 2) + b"\1A\x1f\0"):
            with self.assertRaises(ValueError):
                siglus.lz_decompress(bad)
        with self.assertRaises(ValueError):
            siglus.lz_decompress(frame, max_output_size=2)

    def test_all_scene_count_fields_and_header(self):
        for offset in (0, 0x38, 0x40, 0x48, 0x50, 0x54):
            bad = bytearray(_scene())
            struct.pack_into("<I", bad, offset, 2)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                siglus.extract(bytes(bad))

    def test_name_table_position_and_payload_bounds(self):
        for offset in (0x34, 0x3c, 0x44, 0x4c, 0x60):
            bad = bytearray(_scene())
            struct.pack_into("<I", bad, offset, 0xffffffff)
            with self.assertRaises(ValueError):
                siglus.extract(bytes(bad))
        with self.assertRaises(ValueError):
            siglus.extract(_scene()[:-1])
        with self.assertRaises(ValueError):
            siglus.extract(_scene((('same', b"a"), ('same', b"b"))))

    def test_budgets_and_compressed_bomb_header(self):
        for limits in ({"max_entries": 0}, {"max_file_size": 1}, {"max_total_size": 1}, {"max_packed_size": 1}):
            with self.assertRaises(ValueError):
                siglus.extract(_scene(), **limits)
        with self.assertRaises(ValueError):
            siglus.extract(_scene(frame_override=struct.pack("<II", 8, 0xffffffff)))


if __name__ == "__main__":
    unittest.main()
