# SPDX-License-Identifier: GPL-3.0-only
# Adapted from SExtractor src/reg.yaml:CSV_Livemaker and src/extract_CSV.py
# Source commit: 8d8d976fd04ae54e7c677705af937273d04a376a
# Upstream attribution: satan53x / SExtractor contributors.
"""External Livemaker CSV dialect only; no native LSB parser/compiler."""
import csv
import io
import re


def _rows(text, delimiter):
    if len(text) > 8_000_000 or delimiter not in (",", "\t"):
        raise ValueError("invalid Livemaker CSV input/budget")
    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True))
    if not rows or rows[0].count("Original text") != 1:
        raise ValueError("exactly one Original text column required")
    col = rows[0].index("Original text")
    if col + 1 >= len(rows[0]) or any(len(r) != len(rows[0]) for r in rows):
        raise ValueError("CSV must have a writable next column and rectangular rows")
    return rows, col


def extract_csv(text, *, delimiter=","):
    """Stable data-row indices; bracket name only at the start of Original text."""
    rows, col = _rows(text, delimiter)
    entries = []
    for i, row in enumerate(rows[1:]):
        value = row[col]
        if not value:
            continue
        match = re.match(r"^【([^】\r\n]+)】", value)
        entries.append({"row": i, "name": match[1] if match else "",
                        "message": value[match.end():] if match else value,
                        "original": value})
    return entries


def rewrite_csv(text, replacements, *, delimiter=",", line_ending="\r\n"):
    """Map data-row -> {message, optional name}; write only Original text + 1.

    Source column, IDs, and other CSV cells remain semantically identical.
    CSV quoting is regenerated; original textual formatting is not guaranteed.
    """
    rows, col = _rows(text, delimiter)
    source = {e["row"]: e for e in extract_csv(text, delimiter=delimiter)}
    if set(replacements) - set(source) or line_ending not in ("\n", "\r\n"):
        raise ValueError("unknown CSV row or invalid line ending")
    for i, replacement in replacements.items():
        if "message" not in replacement:
            raise ValueError("message is required")
        old = source[i]
        name = replacement.get("name", old["name"])
        message = replacement["message"]
        if not isinstance(name, str) or not isinstance(message, str):
            raise ValueError("Livemaker name/message must be text")
        if any(c in name for c in "【】\r\n\x00") or "\x00" in message or (old["name"] and not name):
            raise ValueError("invalid Livemaker name/message")
        if name and not old["name"]:
            raise ValueError("cannot add a speaker to a narration CSV row")
        rows[i + 1][col + 1] = ("【" + name + "】" if old["name"] else "") + message
    if not replacements:
        return text
    out = io.StringIO(newline="")
    writer = csv.writer(out, delimiter=delimiter, lineterminator=line_ending)
    writer.writerows(rows)
    return out.getvalue()
