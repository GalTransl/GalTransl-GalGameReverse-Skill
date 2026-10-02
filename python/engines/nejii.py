# Provenance group: tools-a; sources (repository-relative):
#   SExtractor/tools/NEJII/cdt_pack.py
#   SExtractor/tools/NEJII/nejii_tool.py
# Symbols: pack_cdt, parse_cdt, parse_records, inject_bin
# Validation: tests/test_engines_tools_a.py, synthetic fixtures only.
# Rewritten standard-library bytes API; scope: container-raw-pack-fixed-record-text.
# SPDX-License-Identifier: GPL-3.0-only
# SExtractor tools/NEJII/cdt_pack.py: pack_cdt; commit
# 8d8d976fd04ae54e7c677705af937273d04a376a. Bytes-only raw mode, no lzss extension.
"""NEJII CDT trailer index and fixed 144-byte BIN text records; no LZSS decoder."""
# Layer split: engines; format algorithms and original notices retained.
# Companion module: python/archives/nejii.py



def extract_records(data: bytes, *, encoding="cp932") -> list[dict]:
    """nejii_tool.parse_records: 144-byte BIN, explicit 0x64/0x69/0x6A only."""
    if len(data) % 144:
        raise ValueError("BIN must contain whole 144-byte records")
    result, name, name_index = [], "", -999
    for index, start in enumerate(range(0, len(data), 144)):
        rec = data[start:start + 144]
        op = rec[0]
        if op not in (0x64, 0x69, 0x6A):
            continue
        cap = 129 if op == 0x64 else 143
        text = rec[1:1 + cap].split(b"\0", 1)[0].decode(encoding)
        if op == 0x6A:
            name, name_index = text, index
        elif op == 0x64:
            result.append({"record_index": index, "kind": "message",
                           "name": name if index - name_index <= 5 else "", "message": text})
            name, name_index = "", -999
        else:
            result.append({"record_index": index, "kind": "chapter", "name": "", "message": text})
    return result


def replace_record(data: bytes, index: int, text: str, *, encoding="cp932") -> bytes:
    if len(data) % 144 or not 0 <= index < len(data) // 144:
        raise ValueError("invalid BIN record index")
    start = index * 144
    op = data[start]
    if op not in (0x64, 0x69, 0x6A):
        raise ValueError("not a supported text record")
    cap = 129 if op == 0x64 else 143
    raw = text.encode(encoding)
    if b"\0" in raw or len(raw) >= cap:
        raise ValueError("text needs space for NUL; truncation is forbidden")
    return data[:start + 1] + raw.ljust(cap, b"\0") + data[start + 1 + cap:]
