# Provenance group: tools-a; sources (repository-relative):
#   SExtractor/tools/FrontWing/csb_extract.py
#   SExtractor/tools/FrontWing/csb_inject.py
# Symbols: parse_csb, extract, build_csb, inject
# Validation: tests/test_engines_tools_a.py, synthetic fixtures only.
# Rewritten standard-library bytes API; scope: script-node-rebuild.
# SPDX-License-Identifier: GPL-3.0-only
# SExtractor tools/FrontWing/{csb_extract,csb_inject}.py: parse_csb, extract, build_csb.
# Commit 8d8d976fd04ae54e7c677705af937273d04a376a; provenance/tools-a.json.
# Rewrite: preserve node unknown bytes and suffix; strict decoding; no IO.
"""FrontWing CSB nodes and $Msg/$Name extraction, not every FrontWing VM."""
import struct


def parse(data: bytes) -> tuple[bytes, list[tuple[bytes, list[bytes]]], bytes]:
    if len(data) < 12 or data[:4] != b"\0bsc":
        raise ValueError("not CSB")
    pos, count = struct.unpack_from("<II", data, 4)
    if not 12 <= pos <= len(data) or count > (len(data) - pos) // 8:
        raise ValueError("bad CSB header")
    header, nodes = data[:pos], []
    for _ in range(count):
        if pos + 8 > len(data):
            raise ValueError("truncated CSB node")
        rawhead = data[pos:pos + 8]
        argc = struct.unpack_from("<H", rawhead, 2)[0]
        pos += 8
        args = []
        for _ in range(argc):
            if pos + 2 > len(data):
                raise ValueError("truncated argument length")
            n = struct.unpack_from("<H", data, pos)[0]
            pos += 2
            if pos + n > len(data):
                raise ValueError("truncated argument")
            args.append(data[pos:pos + n])
            pos += n
        nodes.append((rawhead, args))
    return header, nodes, data[pos:]


def extract(data: bytes, *, encoding="cp932") -> list[dict]:
    _, nodes, _ = parse(data)
    output = []
    for i, (head, args) in enumerate(nodes):
        if head[:2] != b"\x16\0" or len(args) != 2 or args[0].rstrip(b"\0") != b"$Msg":
            continue
        name = ""
        for other, prev in reversed(nodes[max(0, i - 7):i]):
            if other[:2] == b"\x16\0" and len(prev) == 2 and prev[0].rstrip(b"\0") == b"$Name":
                name = prev[1].rstrip(b"\0").decode(encoding)
                break
        output.append({"node_index": i, "name": name, "message": args[1].rstrip(b"\0").decode(encoding)})
    return output


def replace_messages(data: bytes, translations: dict[int, str], *, encoding="cp932") -> bytes:
    header, nodes, tail = parse(data)
    for index, text in translations.items():
        if not 0 <= index < len(nodes):
            raise ValueError("node index out of range")
        head, args = nodes[index]
        if head[:2] != b"\x16\0" or len(args) != 2 or args[0].rstrip(b"\0") != b"$Msg" or "\0" in text:
            raise ValueError("not a literal $Msg SET")
        raw = text.encode(encoding)
        if args[1].endswith(b"\0"):
            raw += b"\0"
        if len(raw) > 65535:
            raise ValueError("CSB u16 argument overflow")
        args[1] = raw
    return header + b"".join(head + b"".join(struct.pack("<H", len(arg)) + arg for arg in args)
                             for head, args in nodes) + tail
