# SPDX-License-Identifier: GPL-3.0-only
# Adapted from SExtractor tools/Tanaka/SCB1_{unpack,pack}.py; src/reg.yaml:_BIN_Tanaka
# Source commit: 8d8d976fd04ae54e7c677705af937273d04a376a
# Upstream attribution: satan53x / SExtractor contributors.
"""Tanaka SCB1 template repacking and bounded, already-isolated text records."""
# Layer split: engines; format algorithms and original notices retained.
# Companion module: python/archives/tanaka.py



def parse_text_record(record, *, encoding="cp932"):
    """Single match from _BIN_Tanaka, excluding 02 0A separators.

    The length byte is an opaque stored length, not assumed equal to payload
    size. Record bounds must be established by the caller; no raw byte scanning.
    """
    if len(record) < 4 or record[0] < 4 or record[-1] != 0:
        raise ValueError("invalid Tanaka text record")
    op = record[1]
    begin = 6 if op == 0x24 else 2
    if op not in (0x25, 0x09, 0x24) or (op == 0x24 and record[2:6] != bytes(4)):
        raise ValueError("unsupported Tanaka text opcode")
    raw = record[begin:-1]
    if len(raw) < (2 if op == 0x09 else 1) or any(b < 0x20 or b > 0xFC for b in raw):
        raise ValueError("payload outside documented Tanaka byte dialect")
    if op == 0x25 and not 0x81 <= raw[0] <= 0xFC:
        raise ValueError("name record must begin with a double-byte character")
    return {"role": "name" if op == 0x25 else "message", "text": raw.decode(encoding), "begin": begin}


def rewrite_text_record(record, text, *, encoding="cp932"):
    item = parse_text_record(record, encoding=encoding)
    raw = text.encode(encoding)
    length = record[0] + len(raw) - (len(record) - item["begin"] - 1)
    if not 4 <= length <= 255:
        raise ValueError("Tanaka length-byte overflow")
    out = bytes([length]) + record[1:item["begin"]] + raw + b"\x00"
    parse_text_record(out, encoding=encoding)
    return out
