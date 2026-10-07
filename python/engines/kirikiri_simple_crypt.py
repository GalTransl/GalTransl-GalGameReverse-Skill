"""Bounded Kirikiri SimpleCrypt UTF-16LE source-text wrapper.

The header is ``fe fe <mode> ff fe``. Mode 0 transforms 16-bit code units;
mode 1 swaps adjacent bits; mode 2 stores two u64 lengths and a zlib stream.
The compressed length excludes the header and both length fields.

Format/algorithm reference: krkrz base/TextStream.cpp, W.Dee and contributors,
BSD-3-Clause; notice in provenance/kirikiri-textstream-BSD.txt. The original
header probe referenced msg-tool simple_crypt.rs (GPL-3.0-or-later). Precise
source scope is recorded in provenance/kirikiri-sources.json.

This API handles the wrapper only, independently of XP3/Hx, MDF and KAG
semantics. It is not automatically applied by the extraction CLIs.
"""
import struct
import zlib

HEADER = 5
BOM = b"\xff\xfe"
BOM_BE = b"\xfe\xff"
MODES = (0, 1, 2)
MAX_INPUT_SIZE = 64 << 20


def detect(data):
    """Return the mode byte for a SimpleCrypt buffer, else None."""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        return None
    data = memoryview(data).cast('B')
    if len(data) < HEADER:
        return None
    if data[0] != 0xFE or data[1] != 0xFE or data[3] != 0xFF or data[4] != 0xFE:
        return None
    return data[2] if data[2] in MODES else None


def swap_adjacent_bits(value):
    """Exchange bit pairs within one byte; the operation is its own inverse."""
    return (((value & 0xAA) >> 1) | ((value & 0x55) << 1)) & 0xFF


def _mode0(payload):
    if len(payload) % 2:
        raise ValueError("SimpleCrypt truncated UTF-16 code unit")
    out = bytearray(len(payload))
    for offset in range(0, len(payload), 2):
        value = payload[offset] | payload[offset + 1] << 8
        if value >= 0x20:
            value ^= ((value & 0xFE) << 8) ^ 1
        struct.pack_into('<H', out, offset, value)
    return bytes(out)


def _mode1(payload):
    return bytes(swap_adjacent_bits(value) for value in payload)


def _mode2(payload, *, max_output_size):
    if len(payload) < 16:
        raise ValueError("SimpleCrypt mode 2 length fields are truncated")
    packed, unpacked = struct.unpack_from("<QQ", payload, 0)
    if packed != len(payload) - 16 or unpacked > max_output_size or unpacked % 2:
        raise ValueError("SimpleCrypt mode 2 size fields")
    inflater = zlib.decompressobj()
    try:
        out = inflater.decompress(payload[16:], unpacked + 1)
    except zlib.error as exc:
        raise ValueError("SimpleCrypt mode 2 zlib stream") from exc
    if len(out) != unpacked or inflater.unconsumed_tail or inflater.unused_data or not inflater.eof:
        raise ValueError("SimpleCrypt mode 2 inflated size mismatch")
    return out


UNPACKERS = {0: _mode0, 1: _mode1, 2: _mode2}


def unpack(data, *, max_output_size=MAX_INPUT_SIZE):
    """Return (UTF-16LE plaintext with BOM, mode); budget includes the BOM."""
    if type(max_output_size) is not int or max_output_size <= 0:
        raise ValueError("SimpleCrypt output budget")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise ValueError("SimpleCrypt input budget")
    data = memoryview(data).cast('B')
    if len(data) > MAX_INPUT_SIZE:
        raise ValueError("SimpleCrypt input budget")
    mode = detect(data)
    if mode is None:
        raise ValueError("not a SimpleCrypt buffer")
    body = bytes(data[HEADER:])
    if mode == 2:
        plain = BOM + _mode2(body, max_output_size=max_output_size - len(BOM))
    else:
        if len(body) + len(BOM) > max_output_size:
            raise ValueError("SimpleCrypt output budget")
        plain = BOM + UNPACKERS[mode](body)
    # Text wrappers cannot silently accept partial code units or invalid UTF-16.
    plain[2:].decode('utf-16-le')
    return plain, mode


def pack(plaintext, mode, *, level=9):
    """Wrap UTF-16LE plaintext; reject mode 0 code units with no inverse."""
    if type(mode) is not int or mode not in MODES:
        raise ValueError("unsupported SimpleCrypt mode")
    if not isinstance(plaintext, (bytes, bytearray, memoryview)):
        raise TypeError("SimpleCrypt plaintext must be bytes")
    plaintext = memoryview(plaintext).cast('B')
    if len(plaintext) > MAX_INPUT_SIZE:
        raise ValueError("SimpleCrypt plaintext budget")
    plaintext = bytes(plaintext)
    if not plaintext.startswith(BOM):
        raise ValueError("SimpleCrypt plaintext must start with a UTF-16LE BOM")
    payload = plaintext[2:]
    payload.decode('utf-16-le')
    if mode == 0:
        body = _mode0(payload)
        if _mode0(body) != payload:
            raise ValueError("SimpleCrypt mode 0 has no inverse for this text")
    elif mode == 1:
        body = _mode1(payload)
    else:
        packed = zlib.compress(payload, level)
        body = struct.pack("<QQ", len(packed), len(payload)) + packed
    if HEADER + len(body) > MAX_INPUT_SIZE:
        raise ValueError("SimpleCrypt packed input budget")
    return bytes([0xFE, 0xFE, mode, 0xFF, 0xFE]) + body


def text_codec(plaintext):
    """Return (codec, bom_length) for unwrapped plaintext."""
    if plaintext.startswith(BOM):
        return "utf-16-le", 2
    if plaintext.startswith(BOM_BE):
        return "utf-16-be", 2
    raise ValueError("SimpleCrypt plaintext without a UTF-16 BOM")
