# SPDX-License-Identifier: GPL-3.0-only
# Adapted from SExtractor tools/Triangle/{mop_sd,text_extract,text_inject}.py
# Source commit: 8d8d976fd04ae54e7c677705af937273d04a376a
# Upstream attribution: 多了芒果; SExtractor contributors.
"""Triangle isolated text/choice blocks, not a full .SD relocator/disassembler."""
import struct

_COMMAND = frozenset(b"MmNnVvWw@")
_PROFILES = {"MOP": (74, 75), "EXD": (74, 75), "KLH": (72, 73)}


def parse_block(data, *, profile):
    if profile not in _PROFILES or len(data) < 4:
        raise ValueError("explicit Triangle profile and complete block required")
    op, count = struct.unpack_from("<HH", data)
    if op not in _PROFILES[profile] or count > (len(data) - 4):
        raise ValueError("not a supported text/choice block")
    kind = "text" if op == _PROFILES[profile][0] else "choice"
    segments, pos = [], 4
    for _ in range(count):
        stop = data.find(b"\x00", pos)
        if stop < 0:
            raise ValueError("unterminated Triangle segment")
        raw, pos = data[pos:stop], stop + 1
        extra = b""
        if kind == "text" and raw[:1] in (b"V", b"v"):
            if pos + 6 > len(data):
                raise ValueError("truncated voice trailer")
            extra, pos = data[pos:pos + 6], pos + 6
        segments.append((raw, extra))
    if pos != len(data):
        raise ValueError("input must contain exactly one isolated block")
    return {"opcode": op, "kind": kind, "segments": segments}


def extract_block(data, *, profile, encoding="cp932"):
    obj = parse_block(data, profile=profile)
    entries, run, name_id = [], [], None

    def flush():
        if run:
            entries.append({"segments": tuple(run), "name_id": name_id,
                            "message": b"".join(obj["segments"][i][0] for i in run).decode(encoding)})
            run.clear()

    for i, (raw, _) in enumerate(obj["segments"]):
        if obj["kind"] == "choice":
            entries.append({"segments": (i,), "message": raw.decode(encoding), "kind": "choice"})
        elif raw and raw[0] not in _COMMAND:
            run.append(i)
        else:
            flush()
            if raw[:1] in (b"N", b"n"):
                name_id = raw[1:].decode("ascii")  # reference, never a fabricated display name
    flush()
    return entries


def rewrite_block(data, replacements, *, profile, line_bytes, encoding="cp932"):
    """Map first segment index of each text run/choice to text; update segment count.

    Return ONLY the rewritten block. Any size change requires the caller's full
    SD instruction/jump-table relocation, intentionally absent from this module.
    """
    if not 1 <= line_bytes <= 65535:
        raise ValueError("invalid encoded line width")
    obj = parse_block(data, profile=profile)
    records = extract_block(data, profile=profile, encoding=encoding)
    by_start = {e["segments"][0]: e for e in records}
    if set(replacements) - set(by_start):
        raise ValueError("replacement must target first segment of an extracted run")
    result, consumed = [], set()
    for i, seg in enumerate(obj["segments"]):
        if i in consumed:
            continue
        if i not in replacements or replacements[i] == by_start[i]["message"]:
            result.append(seg)
            continue
        text = replacements[i]
        if not text or "\x00" in text or "\r" in text or "\n" in text:
            raise ValueError("Triangle expects nonempty text, not embedded control/newlines")
        consumed.update(by_start[i]["segments"])
        if obj["kind"] == "choice":
            result.append((text.encode(encoding), b""))
            continue
        lines, current = [], bytearray()
        for ch in text:
            raw = ch.encode(encoding)
            if len(raw) > line_bytes:
                raise ValueError("line width smaller than one encoded character")
            if current and len(current) + len(raw) > line_bytes:
                lines.append(bytes(current))
                current.clear()
            current.extend(raw)
        if current:
            lines.append(bytes(current))
        if any(line[0] in _COMMAND for line in lines):
            raise ValueError("translated line would be parsed as a command segment")
        result.extend((line, b"") for line in lines)
    if len(result) > 65535:
        raise ValueError("Triangle segment-count overflow")
    return (struct.pack("<HH", obj["opcode"], len(result))
            + b"".join(raw + b"\x00" + extra for raw, extra in result))
