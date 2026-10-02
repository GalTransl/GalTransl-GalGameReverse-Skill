# SPDX-License-Identifier: GPL-3.0-only
# Adapted from SExtractor src/reg.yaml:_BIN_NSystem and src/extract_TXT.py/preLen logic
# Source commit: 8d8d976fd04ae54e7c677705af937273d04a376a
# Upstream attribution: satan53x / SExtractor contributors.
"""NSystem preset: bounded address table and isolated record algorithms, not full VM."""
import struct
import re


def address_table(data):
    """Resolve 0x458 + (u32@14 + u32@18)*4 without eval or global settings."""
    if len(data) < 0x458:
        raise ValueError("NSystem header too short")
    count = struct.unpack_from("<I", data, 0x14)[0] + struct.unpack_from("<I", data, 0x18)[0]
    base = 0x458 + count * 4
    if count > 100_000 or base > len(data):
        raise ValueError("NSystem address table exceeds file/budget")
    values = struct.unpack_from("<%dI" % count, data, 0x458)
    if any(value > len(data) - base for value in values):
        raise ValueError("NSystem relative address exceeds file")
    return {"base": base, "fields": [(0x458 + i * 4, base + value) for i, value in enumerate(values)]}


def parse_message_record(record, *, encoding="cp932"):
    """Exact one preset record AFTER DA07/D807; length u16 at text_start-18."""
    if len(record) < 20 or record[1] > 1 or record[17] != 3 or record[-1] != 0:
        raise ValueError("not the NSystem message-record dialect")
    stored = struct.unpack_from("<H", record)[0]
    raw = record[18:-1]
    if stored - 27 != len(raw) or not raw or not 0x81 <= raw[0] <= 0xFC:
        raise ValueError("NSystem preLen-27 mismatch")
    if any(b < 0x20 or b > 0xFC for b in raw):
        raise ValueError("NSystem payload outside preset byte range")
    return {"message": raw.decode(encoding), "stored_length": stored}


def rewrite_message_record(record, text, *, encoding="cp932"):
    """Rebuild isolated record, update stored byte length (+27), preserve header.

    Does NOT relocate addresses in an enclosing script. Variable-size output must
    only be installed after a separately verified full-script address-fix stage.
    """
    parse_message_record(record, encoding=encoding)
    raw = text.encode(encoding)
    stored = len(raw) + 27
    if stored > 0x1FF:
        raise ValueError("length would leave the documented [00-01] second-byte dialect")
    out = struct.pack("<H", stored) + record[2:18] + raw + b"\x00"
    parse_message_record(out, encoding=encoding)
    return out


def name_identifier(record):
    """Preset name token is an uppercase identifier, NOT a resolved display name."""
    if len(record) > 65536:
        raise ValueError("NSystem identifier record exceeds budget")
    match = re.match(rb"^[\s\S][\x00-\x01][\s\S]{5}\x03([A-Z]+)_*([0-9]+)\x00", record)
    if not match:
        return None
    return {"name_id": match[1].decode("ascii"), "number": match[2].decode("ascii")}
