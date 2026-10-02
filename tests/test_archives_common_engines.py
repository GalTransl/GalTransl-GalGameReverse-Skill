"""Independent hand-built GARbro-layout fixtures, never commercial assets.

No production writer is used. Fixed codec vectors make a reader/writer sharing
the same mistake insufficient to pass. Stream guards reject any payload read
during indexing, including for a virtual archive containing a 1 GiB member.
"""

from dataclasses import replace
import io
import struct
import unittest
import zlib

from python.archives import yuris, willplus, softpal
from python.common.binary import FormatError


def ypf_fixture(*, version=0x12C, extra=b"", writer_bound=False):
    # 9 -> 11 in all three default swap tables; ~11 == F4. Name XOR key A5.
    # Second name has 6 bytes and is unaffected by table 10; ~6 == F9.
    names = [b"start.ybn", "声.ogg".encode("cp932")]
    encrypted_names = [bytes.fromhex("d6 d1 c4 d7 d1 8b dc c7 cb"),
                       bytes(value ^ 0xA5 for value in names[1])]
    bodies = [bytes.fromhex("78 9c 73 74 72 06 00 01 8d 00 c7"), b"RAW"]
    end = 32 + sum(23 + len(name) + len(extra) for name in names)
    table, offset = bytearray(), end
    for i, (name, encrypted, body) in enumerate(zip(names, encrypted_names, bodies)):
        encoded_len = 0xF4 if i == 0 else (0xCA if version in (0x122, 0x196, 0x1D9, 0x1F4) else 0xF9)
        table.extend(struct.pack("<IB", zlib.crc32(name), encoded_len))
        table.extend(encrypted)
        table.extend(struct.pack("<BBIIII", 0 if i == 0 else 6, 1 if i == 0 else 0,
                                 3, len(body), offset, zlib.adler32(body)))
        table.extend(extra)
        offset += len(body)
    header = struct.pack("<4sIII", b"YPF\0", version, 2, end if writer_bound else end - 32) + bytes(16)
    return header + table + b"".join(bodies), end


def will_v1_fixture(name_size=9, names=("START", "日本")):
    # Two extension groups, absolute directory and member offsets.
    header_end = 28
    end = header_end + 2 * (name_size + 8)
    table = (struct.pack("<I4sII4sII", 2, b"WSC\0", 1, header_end,
                         b"OGG\0", 1, header_end + name_size + 8))
    for i, name in enumerate(names):
        table += name.encode("cp932").ljust(name_size, b"\0")
        table += struct.pack("<II", 3, end + i * 3)
    # ROL2 of 00 41 FF is 00 05 FF (fixed vector, not a production encoder).
    return table + bytes.fromhex("00 05 ff") + b"OGG", end


def will_v2_fixture(names=("start.ws2", "日本.json")):
    rows = []
    for i, name in enumerate(names):
        rows.append(struct.pack("<II", 3, i * 3) + name.encode("utf-16le") + b"\0\0")
    table = b"".join(rows)
    end = 8 + len(table)
    return struct.pack("<II", len(rows), len(table)) + table + bytes.fromhex("00 05 ff") + b"RAW", end


def pac_fixture(version=1, name_size=16, names=("TEXT.DAT", "日本.SRC")):
    start = 0x3FE if version == 1 else 0x804
    end = start + len(names) * (name_size + 8)
    header = bytearray(start)
    if version == 2:
        header[:4] = b"PAC "
    struct.pack_into("<I", header, 0 if version == 1 else 8, len(names))
    table = bytearray()
    for i, name in enumerate(names):
        table.extend(name.encode("cp932").ljust(name_size, b"\0"))
        table.extend(struct.pack("<II", 3, end + i * 3))
    return bytes(header + table) + b"TXT" + b"SRC", end


class GuardedStream(io.BytesIO):
    def __init__(self, data, allowed_end, *, short_reads=False):
        super().__init__(data)
        self.allowed_end = allowed_end
        self.short_reads = short_reads
        self.read_calls = []

    def read(self, size=-1):
        if size < 0 or self.tell() + size > self.allowed_end:
            raise AssertionError("unbounded read or payload read during indexing")
        self.read_calls.append((self.tell(), size))
        return super().read(min(size, 3) if self.short_reads else size)


class YpfTests(unittest.TestCase):
    def index(self, data, **kwargs):
        return yuris.read_index(io.BytesIO(data), version=0x12C, name_key=0xA5, **kwargs)

    def test_fixed_zlib_and_raw_and_names(self):
        data, end = ypf_fixture()
        stream = io.BytesIO(data)
        index = self.index(data, verify_name_hash=True)
        self.assertEqual(index.index_end, end)
        self.assertEqual([e.name for e in index.entries], ["start.ybn", "声.ogg"])
        for entry, expected in zip(index.entries, (b"ABC", b"RAW")):
            stored = yuris.read_member(stream, index, entry)
            self.assertEqual(yuris.decode_member(entry, stored, verify_checksum=True), expected)
        self.assertEqual(index.entries[0].extra, b"")

    def test_versions_extra_fields_and_both_directory_bound_conventions(self):
        for version in yuris.SUPPORTED_VERSIONS:
            extra = b"EXTRMORE" if version == 0xDE else b"EXTR" if version >= 0x1D9 else b""
            for writer_bound in (False, True):
                with self.subTest(version=hex(version), writer_bound=writer_bound):
                    data, end = ypf_fixture(version=version, extra=extra, writer_bound=writer_bound)
                    index = yuris.read_index(io.BytesIO(data), version=version, name_key=0xA5,
                                             swap_table=yuris.SWAP_TABLE_00 if version == 0x1F4 else None,
                                             verify_name_hash=True)
                    self.assertEqual(index.index_end, end)
                    self.assertEqual(index.entries[1].name, "声.ogg")
                    self.assertEqual(index.entries[0].extra, extra)

    def test_unknown_or_mismatched_version_and_scheme(self):
        data, _ = ypf_fixture()
        for kwargs in ({"version": 999}, {"version": 0xF7}, {"name_key": -1},
                       {"swap_table": b"\1"}, {"swap_table": b"\1\1"},
                       {"extra_header_size": 2}, {"extra_header_size": 4}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                yuris.read_index(io.BytesIO(data), **({"version": 0x12C, "name_key": 0xA5} | kwargs))
        data, _ = ypf_fixture(version=0x1F4, extra=b"EXTR")
        with self.assertRaises(FormatError):
            yuris.read_index(io.BytesIO(data), version=0x1F4, name_key=0xA5)

    def test_name_hash_detects_wrong_key(self):
        data, _ = ypf_fixture()
        with self.assertRaisesRegex(FormatError, "CRC32"):
            yuris.read_index(io.BytesIO(data), version=0x12C, name_key=0xA4, verify_name_hash=True)

    def test_explicit_swap_and_extra_overrides(self):
        data, end = ypf_fixture(version=0x1D9, extra=b"")
        data = bytearray(data)
        data[36] = 0xFB  # Custom pair 9 <-> 4: encoded length is ~4.
        data[68] = 0xF9  # Length 6 is unchanged in this custom table.
        index = yuris.read_index(io.BytesIO(data), version=0x1D9, name_key=0xA5,
                                 swap_table=b"\x09\x04", extra_header_size=0,
                                 verify_name_hash=True)
        self.assertEqual(index.index_end, end)
        self.assertEqual([e.name for e in index.entries], ["start.ybn", "声.ogg"])

    def test_count_directory_flags_offsets_and_raw_length(self):
        data, end = ypf_fixture()
        changes = ((0, b"BAD!"), (8, struct.pack("<I", 0)),
                   (12, struct.pack("<I", 1)), (32 + 5 + 9 + 1, b"\x02"),
                   (32 + 5 + 9 + 10, struct.pack("<I", end - 1)),
                   (64 + 5 + 6 + 2, struct.pack("<I", 999)))
        for pos, value in changes:
            bad = bytearray(data)
            bad[pos:pos + len(value)] = value
            with self.subTest(pos=pos), self.assertRaises(ValueError):
                self.index(bad)

    def test_zlib_truncation_tail_size_budget_checksum_and_unknown_codec(self):
        data, _ = ypf_fixture()
        entry = self.index(data).entries[0]
        stored = data[entry.offset:entry.offset + entry.size]
        with self.assertRaises(FormatError):
            yuris.decode_member(entry, stored, max_output_size=2)
        for payload in (stored[:-1], stored + b"tail", b"not-zlib"):
            with self.subTest(payload=payload), self.assertRaises(FormatError):
                yuris.decode_member(replace(entry, size=len(payload)), payload)
        for edited in (replace(entry, unpacked_size=4), replace(entry, checksum=0)):
            with self.assertRaises(FormatError):
                yuris.decode_member(edited, stored, verify_checksum=True)
        with self.assertRaises(FormatError):
            yuris.decode_member(entry, stored, compression="snappy")

    def test_ybn_script_bytes_remain_encrypted(self):
        plain = b"YSTB" + bytes(range(80))
        stored = zlib.compress(plain)
        entry = replace(self.index(ypf_fixture()[0]).entries[0], size=len(stored), unpacked_size=len(plain))
        self.assertEqual(yuris.decode_member(entry, stored), plain)


class WillTests(unittest.TestCase):
    def test_v1_both_name_widths_absolute_offsets(self):
        for width in (9, 13):
            data, end = will_v1_fixture(width)
            index = willplus.read_index(io.BytesIO(data), version=1, name_size=width)
            self.assertEqual(index.index_end, end)
            self.assertEqual([e.name for e in index.entries], ["START.WSC", "日本.OGG"])
            raw = willplus.read_member(io.BytesIO(data), index, index.entries[0])
            self.assertEqual(willplus.decode_member(raw, codec="script-ror2"), b"\0A\xff")
            self.assertEqual(willplus.decode_member(raw), b"\0\5\xff")

    def test_v2_utf16_names_relative_offsets_and_stored_default(self):
        data, end = will_v2_fixture()
        index = willplus.read_index(io.BytesIO(data), version=2)
        self.assertEqual(index.index_end, end)
        self.assertEqual([e.name for e in index.entries], ["start.ws2", "日本.json"])
        self.assertEqual(willplus.read_member(io.BytesIO(data), index, index.entries[1]), b"RAW")
        # Model archives and files already decoded are caller-selected raw.
        self.assertEqual(willplus.decode_member(b"\0A\xff", codec="raw"), b"\0A\xff")

    def test_v1_unsafe_base_not_hidden_by_extension_replacement(self):
        for name in ("../evil", "a/b", "a\\b", "foo.", "CON"):
            data, _ = will_v1_fixture(names=(name, "B"))
            with self.subTest(name=name), self.assertRaises(FormatError):
                willplus.read_index(io.BytesIO(data), version=1, name_size=9)
        data, _ = will_v1_fixture(names=("START", "start"))
        data = bytearray(data)
        data[16:20] = b"WSC\0"
        with self.assertRaises(FormatError):
            willplus.read_index(io.BytesIO(data), version=1, name_size=9)

    def test_psp_fixed_literal_overlap_and_zero_frame_vectors(self):
        vectors = (("03 00 00 00 07 41 42 43", b"ABC"),
                   ("08 00 00 00 03 41 42 00 14", b"ABABABAB"),
                   ("02 00 00 00 00 00 00", b"\0\0"))
        for vector, plain in vectors:
            self.assertEqual(willplus.decode_member(bytes.fromhex(vector), codec="psp"), plain)

    def test_psp_frame_wrap(self):
        # 4096 literals leave frame_pos=1; offset FFF spans the ring boundary.
        literals = b"".join(b"\xff" + bytes(range(i, i + 8)) for i in range(0, 256, 8)) * 16
        data = struct.pack("<I", 4100) + literals + bytes.fromhex("00 ff f2")
        expected = bytes(range(256)) * 16 + bytes.fromhex("fe ff fe ff")
        self.assertEqual(willplus.decode_member(data, codec="psp"), expected)

    def test_psp_malformed_and_budgets(self):
        for payload in (b"", bytes.fromhex("02 00 00 00"),
                        bytes.fromhex("02 00 00 00 00 00"),
                        bytes.fromhex("02 00 00 00 00 00 0f"),
                        bytes.fromhex("00 00 00 00 ff")):
            with self.subTest(payload=payload), self.assertRaises(FormatError):
                willplus.decode_member(payload, codec="psp")
        with self.assertRaises(FormatError):
            willplus.decode_member(bytes.fromhex("ff ff ff ff"), codec="psp", max_output_size=100)
        for codec in ("raw", "script-ror2"):
            with self.assertRaises(FormatError):
                willplus.decode_member(b"123", codec=codec, max_output_size=2)
        with self.assertRaises(FormatError):
            willplus.decode_member(b"", codec="guess")

    def test_v1_layout_count_directory_overlap_and_placement(self):
        data, end = will_v1_fixture()
        for pos, value in ((0, 0), (8, 0), (8, 0x10000), (12, 4), (24, 28),
                           (41, end - 1), (41, len(data) + 1)):
            bad = bytearray(data)
            struct.pack_into("<I", bad, pos, value)
            with self.subTest(pos=pos, value=value), self.assertRaises(FormatError):
                willplus.read_index(io.BytesIO(bad), version=1, name_size=9)
        for kwargs in ({"version": 3}, {"version": 1}, {"version": 1, "name_size": 8},
                       {"version": 2, "name_size": 9}):
            with self.assertRaises(FormatError):
                willplus.read_index(io.BytesIO(data), **kwargs)

    def test_v2_bad_utf16_termination_count_offset_and_tail(self):
        data, end = will_v2_fixture()
        cases = []
        bad = bytearray(data)
        bad[16:18] = b"\0\xd8"  # Unpaired high surrogate.
        cases.append(bad)
        bad = bytearray(data)
        bad[34:36] = b"xx"  # Delete first terminator.
        cases.append(bad)
        for pos, value in ((0, 0), (0, 0xFFFFFFFF), (4, 1), (12, len(data))):
            bad = bytearray(data)
            struct.pack_into("<I", bad, pos, value)
            cases.append(bad)
        bad = bytearray(data[:end] + b"\0\0" + data[end:])
        struct.pack_into("<I", bad, 4, end - 8 + 2)
        cases.append(bad)
        for bad in cases:
            with self.subTest(data=bytes(bad[:20])), self.assertRaises(ValueError):
                willplus.read_index(io.BytesIO(bad), version=2)
        with self.assertRaises(FormatError):
            willplus.read_index(io.BytesIO(data), version=2, max_name_bytes=4)


class PacTests(unittest.TestCase):
    def test_three_layouts_and_multibyte_names(self):
        for version, width in ((1, 16), (1, 32), (2, 32)):
            data, end = pac_fixture(version, width)
            index = softpal.read_index(io.BytesIO(data), version=version, name_size=width)
            self.assertEqual(index.index_end, end)
            self.assertEqual([e.name for e in index.entries], ["TEXT.DAT", "日本.SRC"])
            self.assertEqual(softpal.read_member(io.BytesIO(data), index, index.entries[1]), b"SRC")

    def test_script_dollar_fixed_vector_and_untouched_header_tail(self):
        # Stored LE words: 78563412 -> rotate low byte 12 by 4 -> 21,
        # then XOR F7D5859D == 8F83B1BC (LE BC B1 83 8F).
        header = b"$TEXT_LIST_****\0"
        stored = header + bytes.fromhex("12 34 56 78 01 23 45 67") + b"XYZ"
        expected = header + bytes.fromhex("bc b1 83 8f bd a6 90 90") + b"XYZ"
        self.assertEqual(softpal.decode_member(stored, codec="script-dollar"), expected)
        self.assertEqual(softpal.decode_member(stored), stored)
        self.assertEqual(softpal.decode_member(header, codec="script-dollar"), header)

    def test_script_shift_wrap(self):
        header = b"$" + bytes(15)
        stored = header + bytes.fromhex("01 00 00 00") * 9
        # Shift counts 4,5,6,7,0,1,2,3,4; XOR low key byte 9D.
        lows = bytes.fromhex("8d bd dd 1d 9c 9f 99 95 8d")
        expected = header + b"".join(bytes((low, 0x85, 0xD5, 0xF7)) for low in lows)
        self.assertEqual(softpal.decode_member(stored, codec="script-dollar"), expected)

    def test_codec_and_budget_refusals(self):
        for raw in (b"$short", b"_" + bytes(20)):
            with self.assertRaises(FormatError):
                softpal.decode_member(raw, codec="script-dollar")
        with self.assertRaises(FormatError):
            softpal.decode_member(b"123", max_output_size=2)
        with self.assertRaises(FormatError):
            softpal.decode_member(b"", codec="vafs")

    def test_header_count_first_offset_size_and_layout_refusals(self):
        data, end = pac_fixture(2, 32)
        cases = [(0, b"bad!"), (8, struct.pack("<I", 0)),
                 (0x804 + 36, struct.pack("<I", end + 1)),
                 (0x804 + 32, struct.pack("<I", 0xFFFFFFFF))]
        for pos, value in cases:
            bad = bytearray(data)
            bad[pos:pos + len(value)] = value
            with self.assertRaises(FormatError):
                softpal.read_index(io.BytesIO(bad), version=2)
        for kwargs in ({"version": 3}, {"version": 1}, {"version": 1, "name_size": 24},
                       {"version": 2, "name_size": 16}):
            with self.assertRaises(FormatError):
                softpal.read_index(io.BytesIO(data), **kwargs)


class SharedArchiveTests(unittest.TestCase):
    def cases(self):
        return ((yuris, ypf_fixture(), {"version": 0x12C, "name_key": 0xA5}),
                (willplus, will_v1_fixture(), {"version": 1, "name_size": 9}),
                (willplus, will_v2_fixture(), {"version": 2}),
                (softpal, pac_fixture(), {"version": 1, "name_size": 16}),
                (softpal, pac_fixture(2, 32), {"version": 2}))

    def test_index_only_and_partial_reads_position_restored(self):
        for module, (data, end), kwargs in self.cases():
            with self.subTest(module=module.__name__, kwargs=kwargs):
                stream = GuardedStream(data, end, short_reads=True)
                stream.seek(2)
                index = module.read_index(stream, **kwargs)
                self.assertEqual(stream.tell(), 2)
                self.assertEqual(index.index_end, end)
                stream.allowed_end = len(data)
                entry = index.entries[1]
                self.assertEqual(module.read_member(stream, index, entry), data[entry.offset:entry.offset + entry.size])
                self.assertEqual(stream.tell(), 2)

    def test_index_budgets_and_truncation_restore_position(self):
        for module, (data, end), kwargs in self.cases():
            for extra in ({"max_entries": 1}, {"max_index_size": end - 1},
                          {"max_index_size": 0}, {"max_entries": -1}):
                with self.subTest(module=module.__name__, extra=extra), self.assertRaises(FormatError):
                    module.read_index(io.BytesIO(data), **kwargs, **extra)
            for length in (0, 4, end - 1, len(data) - 1):
                stream = io.BytesIO(data[:length])
                stream.seek(2)
                with self.subTest(length=length), self.assertRaises(ValueError):
                    module.read_index(stream, **kwargs)
                self.assertEqual(stream.tell(), 2)

    def test_membership_stored_budget_and_changed_archive(self):
        for module, (data, end), kwargs in self.cases():
            index = module.read_index(io.BytesIO(data), **kwargs)
            stream = GuardedStream(data, end)
            with self.assertRaises(FormatError):
                module.read_member(stream, index, index.entries[0], max_stored_size=0)
            self.assertEqual(stream.read_calls, [])
            with self.assertRaises(FormatError):
                module.read_member(io.BytesIO(data), index, replace(index.entries[0]))
            with self.assertRaises(FormatError):
                module.read_member(io.BytesIO(data + b"!"), index, index.entries[0])

    def test_path_and_collision_refusals(self):
        for names in (("../a", "b"), ("A", "a"), ("CON", "b"), ("a", "a/b"), ("a ", "b")):
            for module, build, kwargs in ((willplus, will_v2_fixture, {"version": 2}),
                                           (softpal, pac_fixture, {"version": 1, "name_size": 16})):
                data, _ = build(names=names)
                with self.subTest(module=module.__name__, names=names), self.assertRaises(FormatError):
                    module.read_index(io.BytesIO(data), **kwargs)
        data, _ = ypf_fixture()
        bad = bytearray(data)
        bad[37:46] = bytes(b ^ 0xA5 for b in b"../xx.ybn")
        with self.assertRaises(FormatError):
            yuris.read_index(io.BytesIO(bad), version=0x12C, name_key=0xA5)

    def test_gigabyte_payload_not_read_or_charged_at_index_stage(self):
        class VirtualStream(GuardedStream):
            def seek(self, offset, whence=0):
                if whence == 2:
                    return super().seek((1 << 34) + offset)
                return super().seek(offset, whence)

        for module, (original, end), kwargs in self.cases():
            data = bytearray(original[:end])
            if module is yuris:
                struct.pack_into("<II", data, 32 + 5 + 9 + 2, 1 << 30, 1 << 30)
            elif module is willplus:
                struct.pack_into("<I", data, 8 if kwargs["version"] == 2 else 28 + 9, 1 << 30)
            else:
                struct.pack_into("<I", data, (0x804 + 32) if kwargs["version"] == 2 else (0x3FE + 16), 1 << 30)
            stream = VirtualStream(data, end)
            index = module.read_index(stream, **kwargs)
            self.assertEqual(index.archive_size, 1 << 34)
            self.assertEqual(index.entries[0].size, 1 << 30)
            with self.assertRaises(FormatError):
                module.read_member(stream, index, index.entries[0])


if __name__ == "__main__":
    unittest.main()
