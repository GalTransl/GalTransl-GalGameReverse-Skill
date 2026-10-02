# Provenance group: tools-a; sources (repository-relative):
#   SExtractor/tools/FlyingShine/flytool.py
# Symbols: parse_header, read_entries, decrypt_script_payload, encrypt_script_payload
# Validation: tests/test_engines_tools_a.py, synthetic fixtures only.
# Rewritten standard-library bytes API; scope: container-script-shell-roundtrip.
# SPDX-License-Identifier: GPL-3.0-only
# SExtractor tools/FlyingShine/flytool.py: parse_header, read_entries,
# decrypt_script_payload, encrypt_script_payload; commit
# 8d8d976fd04ae54e7c677705af937273d04a376a. Bounds-only bytes rewrite, no OGG edits.
"""FlyingShine PD/2 index and CRLF-derived script XOR. No guessed text syntax."""
# Layer split: archives; format algorithms and original notices retained.
# Companion module: python/engines/flyingshine.py
import struct


MAGIC = b"FlyingShinePDFile\0"


def index(data: bytes) -> list[dict]:
    if len(data) < 32 or data[:18] != MAGIC:
        raise ValueError("not PD/2")
    key, count = data[20], struct.unpack_from("<I", data, 28)[0]
    end = 32 + count * 48
    if not count or end > len(data):
        raise ValueError("invalid PD count")
    result = []
    for pos in range(32, end, 48):
        rec = bytes(b ^ key for b in data[pos:pos + 48])
        stop = rec[:36].find(b"\0")
        if stop <= 0:
            raise ValueError("unterminated PD name")
        shift, off, size = struct.unpack_from("<III", rec, 36)
        off, size = off - shift, size - shift
        if off < end or size < 0 or off + size > len(data):
            raise ValueError("PD entry outside data region")
        result.append({"name": rec[:stop].decode("cp932"), "name_field": rec[:36],
                       "shift": shift, "offset": off, "size": size, "stored": data[off:off + size]})
    return result


def rebuild(data: bytes, payloads: list[bytes]) -> bytes:
    """Rebuild stored (already encrypted) payloads; preserve header/name/shift."""
    records = index(data)
    if len(payloads) != len(records):
        raise ValueError("entry count cannot change")
    out, body = bytearray(data[:32]), bytearray()
    off, key = 32 + 48 * len(records), data[20]
    for record, raw in zip(records, payloads):
        shift = record["shift"]
        if max(off, len(raw)) + shift > 0xFFFFFFFF:
            raise ValueError("PD shifted field overflow")
        rec = record["name_field"] + struct.pack("<III", shift, off + shift, len(raw) + shift)
        out += bytes(b ^ key for b in rec)
        body += raw
        off += len(raw)
    return bytes(out + body)
