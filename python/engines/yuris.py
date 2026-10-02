"""YU-RIS YSTB section XOR, CP932-aware control bytes and YSCM command dictionary.
Source: VNTextPatch-net8, VNTextPatch.Shared/Scripts/Yuris/YurisScenarioScript.cs,
ToggleScriptEncryption/YurisControlCodesToStandard/StandardControlCodesToYuris;
YurisCommandList.cs (ReadCommand); Util/BinaryUtil.cs (Xor).
Commit d9c0fab7b72fdcf87d674ef12a84d3829c9188be; source license MIT.
No automatic XOR-key guessing, expression VM or complete YBN patcher.
"""
import struct


def toggle_ybn_sections(data: bytes, key: int) -> bytes:
    """XOR each of the four YSTB sections, restarting LE key phase per section."""
    if len(data) < 32 or data[:4] != b"YSTB":
        raise ValueError("expected YSTB scenario, not YSCF/YSCM")
    if type(key) is not int or not 0 <= key <= 0xFFFFFFFF:
        raise ValueError("YU-RIS key must be u32")
    count, = struct.unpack_from("<I", data, 8)
    sizes = struct.unpack_from("<IIII", data, 12)
    if sizes[0] != count * 4 or 32 + sum(sizes) != len(data):
        raise ValueError("YSTB section/count mismatch")
    key_bytes, out, start = struct.pack("<I", key), bytearray(data), 32
    for size in sizes:
        for index in range(size):
            out[start + index] ^= key_bytes[index % 4]
        start += size
    return bytes(out)


def convert_control_bytes(data: bytes, *, to_yuris: bool = False) -> bytes:
    """Convert EF F0/F2/F3/F5 <-> CRLF/\\p/\\c/\\u without touching SJIS trails.

    Input/output are raw CP932-like byte sequences, not encoded whole YBN files.
    Unknown EF controls and incomplete multibyte characters reject the subset.
    """
    forward = {b"\xef\xf0": b"\r\n", b"\xef\xf2": b"\\p",
               b"\xef\xf3": b"\\c", b"\xef\xf5": b"\\u"}
    mapping = {value: key for key, value in forward.items()} if to_yuris else forward
    out, pos = bytearray(), 0
    while pos < len(data):
        pair = data[pos:pos + 2]
        if pair in mapping:
            out.extend(mapping[pair])
            pos += 2
            continue
        first = data[pos]
        if not to_yuris and first == 0xEF:
            raise ValueError("unknown YU-RIS EF control")
        size = 2 if 0x81 <= first <= 0x9F or 0xE0 <= first <= 0xFC else 1
        if pos + size > len(data):
            raise ValueError("incomplete CP932 character")
        if size == 2 and not (0x40 <= data[pos + 1] <= 0xFC and data[pos + 1] != 0x7F):
            raise ValueError("invalid CP932 trail byte")
        out.extend(data[pos:pos + size])
        pos += size
    return bytes(out)


def read_command_list(data: bytes, encoding: str = "cp932", *, allow_message_tail: bool = False) -> tuple[tuple[str, tuple], ...]:
    """ysc.ybn/YSCM -> commands in ID order; attributes keep ID order + two raw bytes.

    Do not hard-code WORD/_/GOSUB IDs: locate their names in this returned tuple.
    Duplicate command names and unsupported trailing sections are rejected.
    """
    if len(data) < 16 or data[:4] != b"YSCM":
        raise ValueError("expected YSCM command dictionary")
    count, = struct.unpack_from("<I", data, 8)
    if count > 255:
        raise ValueError("YU-RIS command ID exceeds byte range")
    pos = 16

    def string():
        nonlocal pos
        end = data.find(b"\0", pos)
        if end < 0:
            raise ValueError("unterminated YSCM name")
        value = data[pos:end].decode(encoding, errors="strict")
        pos = end + 1
        return value

    commands, names = [], set()
    for _ in range(count):
        name = string()
        if name in names or pos >= len(data):
            raise ValueError("duplicate/truncated YSCM command")
        names.add(name)
        attr_count = data[pos]
        pos += 1
        attrs = []
        for _ in range(attr_count):
            attr_name = string()
            if pos + 2 > len(data):
                raise ValueError("truncated YSCM attribute metadata")
            attrs.append((attr_name, data[pos:pos + 2]))
            pos += 2
        commands.append((name, tuple(attrs)))
    if pos != len(data):
        if not allow_message_tail or struct.unpack_from("<I", data, 4)[0] != 482 or len(data) - pos < 257 or data[-257] != 0:
            raise ValueError("unsupported YSCM trailing data")
        # msg-tool yscm.rs (GPLv3): diagnostic cstrings then a 256-byte opaque
        # table. Extension adapted under GPL-3.0-only; retain MIT origin above.
        # The complete YSCM remains an immutable source, including that table.
        for message in data[pos:-257].split(b"\0"):
            text = message.decode(encoding, errors="strict")
            if any(ord(char) < 32 and char not in "\r\n\t" for char in text):
                raise ValueError("invalid YSCM diagnostic string table")
    return tuple(commands)
