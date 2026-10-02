# SPDX-License-Identifier: GPL-3.0-only
# Adapted from SExtractor tools/StudioPolaris/{opcode,disassembler,assembler}.py
# Source commit: 8d8d976fd04ae54e7c677705af937273d04a376a
# Upstream attribution: Steins;Gate; SExtractor contributors.
"""Already-decrypted SCD_ VM: TEXT operands and code-relative label relocation."""
import struct


def parse_scd(data):
    if len(data) < 8 or data[:4] != b"SCD_":
        raise ValueError("expected already-decrypted SCD_ file")
    base = struct.unpack_from("<I", data, 4)[0]
    if not 8 <= base <= len(data) or len(data) > 64 * 1024 * 1024:
        raise ValueError("invalid SCD code offset/budget")
    pos = 8

    def take(n, end):
        nonlocal pos
        if pos + n > end:
            raise ValueError("truncated SCD operand")
        raw = data[pos:pos + n]
        pos += n
        return raw

    def zstr(end):
        nonlocal pos
        stop = data.find(b"\x00", pos, end)
        if stop < 0:
            raise ValueError("unterminated SCD string")
        raw = data[pos:stop]
        pos = stop + 1
        return raw

    labels = []
    while pos < base:
        field = pos
        target = int.from_bytes(take(4, base), "little")
        zstr(base).decode("cp932")
        labels.append((field, target))
    insts = []
    while pos < len(data):
        start = pos
        op = take(1, len(data))[0]
        texts, jump = None, None
        if op == 0:
            texts = [zstr(len(data))]
            while pos < len(data) and data[pos] == 0:
                pos += 1
                texts.append(zstr(len(data)))
        elif op in (1, 2):
            sub = take(1, len(data))[0]
            if sub == 1:
                take(1, len(data))
            elif 2 <= sub <= 7:
                take(2, len(data))
            elif sub == 8:
                zstr(len(data))
            else:
                raise ValueError("unsupported SCD value-ref opcode")
        elif op == 4:
            sub = take(1, len(data))[0]
            if sub > 4:
                raise ValueError("unsupported SCD jump opcode")
            jump = int.from_bytes(take(4, len(data)), "little")
        elif op in (5, 6):
            sub = take(1, len(data))[0]
            if sub > (5 if op == 5 else 7):
                raise ValueError("unsupported SCD arithmetic opcode")
        elif op == 3 or (0x14 <= op <= 0x64 and op not in (0x27, 0x2E, 0x2F, 0x30)) or 0x96 <= op <= 0x9F:
            pass
        else:
            raise ValueError("unknown SCD opcode at %#x" % start)
        insts.append({"offset": start - base, "raw": data[start:pos], "texts": texts, "jump": jump})
    boundaries = {i["offset"] for i in insts}
    for _, target in labels:
        if target not in boundaries:
            raise ValueError("header label is not on an instruction boundary")
    for inst in insts:
        if inst["jump"] is not None and inst["jump"] not in boundaries:
            raise ValueError("jump is not on an instruction boundary")
    return {"base": base, "labels": labels, "instructions": insts}


def extract_scd(data, *, encoding="cp932"):
    """Only opcode-00 TEXT. STRING references are not automatically dialogue/name."""
    return [{"offset": inst["offset"], "message": "\n".join(s.decode(encoding) for s in inst["texts"])}
            for inst in parse_scd(data)["instructions"] if inst["texts"] is not None]


def rewrite_scd(data, replacements, *, encoding="cp932"):
    """Map old code-relative TEXT offset -> message; rebuild and relocate all known jumps."""
    obj = parse_scd(data)
    allowed = {i["offset"] for i in obj["instructions"] if i["texts"] is not None}
    if set(replacements) - allowed:
        raise ValueError("replacement does not target a TEXT instruction")
    chunks, remap, cursor = [], {}, 0
    for inst in obj["instructions"]:
        remap[inst["offset"]] = cursor
        raw = inst["raw"]
        if inst["offset"] in replacements:
            message = replacements[inst["offset"]]
            parts = message.split("\n")
            if any(not s or "\x00" in s or "\r" in s for s in parts):
                raise ValueError("empty/NUL/CR TEXT segments are ambiguous")
            original = "\n".join(s.decode(encoding) for s in inst["texts"])
            if message != original:
                raw = b"\x00" + b"\x00\x00".join(s.encode(encoding) for s in parts) + b"\x00"
        chunks.append(bytearray(raw))
        cursor += len(raw)
    header = bytearray(data[:obj["base"]])
    for field, target in obj["labels"]:
        struct.pack_into("<I", header, field, remap[target])
    for inst, chunk in zip(obj["instructions"], chunks):
        if inst["jump"] is not None:
            struct.pack_into("<I", chunk, 2, remap[inst["jump"]])
    result = bytes(header) + b"".join(chunks)
    parse_scd(result)
    return result
