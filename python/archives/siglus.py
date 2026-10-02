"""Siglus Scene.pck container decryption + bounded LZ decoding, not text extraction.

Supports the 0x5c header and ordered scene name/index/data tables. An explicit
16-byte game_key is REQUIRED when header[0x54] is 1; no key database, key
inference, executable inspection or guessing. Other flag values are rejected.
Output .ss bytes remain Siglus bytecode; no string-table editor/recompiler,
archive writer, or deployment compatibility claim is provided. Names are
untrusted and must be handled by a caller-supplied safe output layer.

Reference: GARbro-Mod, ArcFormats/RealLive/ArcSCENE.cs,
SceneOpener.TryOpen/OpenEntry/DefaultKey; ArcFormats/RealLive/ImageG00.cs,
G00Reader.LzDecompress(min_count=2, bytes_pp=1); commit
bc26d991ef5cdc0e1ecb32122ee9a48c3375750c (MIT).
Copyright (C) 2016, 2026 by morkt

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
from dataclasses import dataclass
import struct

# Source constant from SceneOpener.DefaultKey (MIT notice above).
DEFAULT_KEY = bytes.fromhex(
    "70 f8 a6 b0 a1 a5 28 4f b5 2f 48 fa e1 e9 4b de "
    "b7 4f 62 95 8b e0 03 80 e7 cf 0f 6b 92 01 eb f8 "
    "a2 88 ce 63 04 38 d2 6d 8c d2 88 76 a7 92 71 8f "
    "4e b6 8d 01 79 88 83 0a f9 e9 2c db 67 db 91 14 "
    "d5 9a 4e 79 17 23 08 96 0e 1d 15 f9 a5 a0 6f 58 "
    "17 c8 a9 46 da 22 ff fd 87 12 42 fb a9 b8 67 6c "
    "91 67 64 f9 d1 1e e4 50 64 6f f2 0b de 40 e7 47 "
    "f1 03 cc 2a ad 7f 34 21 a0 64 26 98 6c ed 69 f4 "
    "b5 23 08 6e 7d 92 f6 eb 93 f0 7a 89 5e f9 f8 7a "
    "af e8 a9 48 c2 ac 11 6b 2b 33 a7 40 0d dc 7d a7 "
    "5b cf c8 31 d1 77 52 8d 82 ac 41 b8 73 a5 4f 26 "
    "7c 0f 39 da 5b 37 4a de a4 49 0b 7c 17 a3 43 ae "
    "77 06 64 73 c0 43 a3 18 5a 0f 9f 02 4c 7e 8b 01 "
    "9f 2d ae 72 54 13 ff 96 ae 0b 34 58 cf e3 00 78 "
    "be e3 f5 61 e4 87 7c fc 80 af c4 8d 46 3a 5d d0 "
    "36 bc e5 60 77 68 08 4f bb ab e2 78 07 e8 73 bf"
)


@dataclass(frozen=True)
class Entry:
    name: str
    data: bytes
    offset: int
    stored_size: int
    content_type: str = "siglus-bytecode"


def _range(data, offset, size):
    if offset < 0 or size < 0 or offset > len(data) or size > len(data) - offset:
        raise ValueError("Siglus range outside input")
    return data[offset:offset + size]


def lz_decompress(data: bytes, *, max_output_size: int = 64 << 20,
                  max_input_size: int = 80 << 20) -> bytes:
    """Decode plaintext Scene LZ frame, including its two u32 length fields.

    LSB-first control: 1 literal, 0 LE u16 reference. Distance = word >> 4;
    count = (word & 15) + 2. Overlapping copies are intentional. Unlike the
    permissive reference reader, short output and extra input are errors.
    """
    if not isinstance(data, bytes) or len(data) > max_input_size:
        raise ValueError("Siglus LZ input type/size")
    if min(max_input_size, max_output_size) < 0:
        raise ValueError("negative Siglus LZ limit")
    packed, expected = struct.unpack("<II", _range(data, 0, 8))
    if packed != len(data) or packed < 8 or expected > max_output_size:
        raise ValueError("Siglus LZ length/budget mismatch")
    output, pos = bytearray(), 8
    while len(output) < expected:
        control = _range(data, pos, 1)[0]
        pos += 1
        for bit in range(8):
            if len(output) == expected:
                break
            if control & (1 << bit):
                output.extend(_range(data, pos, 1))
                pos += 1
            else:
                word, = struct.unpack("<H", _range(data, pos, 2))
                pos += 2
                distance, count = word >> 4, (word & 15) + 2
                if not 0 < distance <= len(output) or count > expected - len(output):
                    raise ValueError("invalid Siglus LZ backreference/length")
                for _ in range(count):
                    output.append(output[-distance])
    if pos != len(data):
        raise ValueError("Siglus LZ trailing bytes")
    return bytes(output)


def extract(data: bytes, *, game_key: bytes | None = None,
            max_entries: int = 100_000, max_file_size: int = 64 << 20,
            max_packed_size: int = 80 << 20, max_total_size: int = 256 << 20,
            max_archive_size: int = 512 << 20) -> list[Entry]:
    """Return .ss bytecode after container-level validation/decryption only.

    Header auxiliary metadata [0x04,0x34) and word 0x58 are retained in the
    input but are not interpreted. Supported scene tables must be ordered:
    name-index, UTF16 names, position-index, encrypted payloads. Alternative
    table order is explicitly unsupported. No key authenticity check exists.
    """
    if not isinstance(data, bytes) or len(data) > max_archive_size:
        raise ValueError("Siglus input type/size")
    if min(max_entries, max_file_size, max_packed_size, max_total_size, max_archive_size) < 0:
        raise ValueError("negative Siglus limit")
    header = _range(data, 0, 0x5c)
    header_len, = struct.unpack_from("<I", header)
    if header_len != 0x5c:
        raise ValueError("unsupported Scene.pck header size")
    name_index, count, names_at, name_count, pos_index, pos_count, data_at, data_count = struct.unpack_from("<8I", header, 0x34)
    if not 0 < count <= max_entries or len({count, name_count, pos_count, data_count}) != 1:
        raise ValueError("Siglus scene table counts disagree/limit")
    if not (0x5c <= name_index and name_index + count * 8 <= names_at <= pos_index
            and pos_index + count * 8 <= data_at <= len(data)):
        raise ValueError("Siglus scene table bounds/order unsupported")
    flag, = struct.unpack_from("<I", header, 0x54)
    if flag not in (0, 1):
        raise ValueError("unknown Siglus extra-key flag")
    if flag and (not isinstance(game_key, bytes) or len(game_key) != 16):
        raise ValueError("Scene.pck requires an explicitly supplied 16-byte game key")
    if not flag and game_key is not None:
        raise ValueError("game key supplied for Scene.pck without extra-key flag")
    records, names, total = [], set(), 0
    for number in range(count):
        name_rel, name_units = struct.unpack("<II", _range(data, name_index + number * 8, 8))
        name_start = names_at + name_rel * 2
        if not 0 < name_units <= 4096 or name_start + name_units * 2 > pos_index:
            raise ValueError("Siglus name range/length invalid")
        name = _range(data, name_start, name_units * 2).decode("utf-16-le", errors="strict") + ".ss"
        if "\0" in name or name in names:
            raise ValueError("NUL/duplicate Siglus scene name")
        relative, size = struct.unpack("<II", _range(data, pos_index + number * 8, 8))
        if size > max_packed_size:
            raise ValueError("Siglus packed member budget")
        offset = data_at + relative
        encrypted = _range(data, offset, size)
        frame = bytes(value ^ DEFAULT_KEY[i % 256]
                      ^ (game_key[i % 16] if flag else 0)
                      for i, value in enumerate(encrypted))
        payload = lz_decompress(frame, max_output_size=min(max_file_size, max_total_size - total),
                                max_input_size=max_packed_size)
        total += len(payload)
        names.add(name)
        records.append(Entry(name, payload, offset, size))
    return records
