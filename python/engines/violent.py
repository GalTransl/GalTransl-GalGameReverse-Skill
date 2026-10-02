# SPDX-License-Identifier: GPL-3.0-only
# Adapted from SExtractor src/reg.yaml:_BIN_Violent and src/common.py:isShiftJis/checkJIS
# Source commit: 8d8d976fd04ae54e7c677705af937273d04a376a
# Upstream attribution: satan53x / SExtractor contributors.
"""Read-only forensic candidates, NOT an engine, dialogue extractor, or writer."""


def is_allowed_sjis(data):
    """Historical SExtractor JIS subset: double-byte pairs plus CR/LF only.

    Halfwidth katakana, ASCII, F0-F9 private-use rows and EF+ gaps are deliberately
    not widened to arbitrary CP932. Decode validity is checked separately.
    """
    pos = 0
    while pos < len(data):
        a = data[pos]
        if a in (10, 13):
            pos += 1
            continue
        if pos + 1 >= len(data):
            return False
        b = data[pos + 1]
        lead = 0x81 <= a <= 0x9F or 0xE0 <= a <= 0xEF or 0xFA <= a <= 0xFB
        trail = 0x40 <= b <= 0x7E or 0x80 <= b <= 0xFC
        if not ((lead and trail) or (a == 0xFC and 0x40 <= b <= 0x4B)):
            return False
        pos += 2
    return bool(data)


def scan_candidates(data, *, start, end, max_candidates=100_000):
    """Scan an explicitly chosen region of already-decoded binary for NUL strings.

    Returns evidence-only offsets/text. Callers MUST determine instruction/name/
    message roles and relocation rules separately; there is intentionally no writer.
    """
    if not 0 <= start <= end <= len(data) or end - start > 64 * 1024 * 1024 or max_candidates < 0:
        raise ValueError("invalid candidate-scan region/budget")
    out, pos = [], start
    while pos < end:
        stop = data.find(b"\x00", pos, end)
        if stop < 0:
            break  # unterminated tail is not a string record
        raw = data[pos:stop]
        if len(raw) >= 4 and 0x81 <= raw[0] <= 0xFC and is_allowed_sjis(raw):
            try:
                text = raw.decode("cp932")
            except UnicodeDecodeError:
                text = None
            if text is not None:
                if len(out) >= max_candidates:
                    raise ValueError("candidate budget exceeded")
                out.append({"offset": pos, "end": stop, "text": text, "role": "unknown", "status": "candidate-only"})
        pos = stop + 1
    return out
