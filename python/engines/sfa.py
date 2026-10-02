# SPDX-License-Identifier: GPL-3.0-only
# Adapted from SExtractor tools/SFA/fga_pack.py and src/reg.yaml:SFA_AOS
# Source commit: 8d8d976fd04ae54e7c677705af937273d04a376a
# Upstream attribution: Steins;Gate; SExtractor contributors.
"""SFA member Huffman codec and a conservative AOS text-dialect recognizer."""
# Layer split: engines; format algorithms and original notices retained.
# Companion module: python/archives/sfa.py
import re


def extract_aos_lines(text):
    """Only explicit [name]message lines and btnset(...\"slctwnd\"...) choices.

    Unlike the broad upstream fallback, arbitrary non-command lines are NOT
    classified as dialogue. Offsets are Unicode positions within decoded AOS.
    """
    if len(text) > 8_000_000:
        raise ValueError("AOS text exceeds budget")
    entries, position = [], 0
    for line_no, line in enumerate(text.splitlines(keepends=True)):
        body = line.rstrip("\r\n")
        match = re.fullmatch(r"\[([^\[\]\r\n]+)\](.+)", body)
        if match:
            entries.append({"line": line_no, "name": match[1], "message": match[2],
                            "span": (position + match.start(2), position + match.end(2))})
        elif re.match(r'^\s*btnset\b', body):
            match = re.search(r'"slctwnd"[^"\r\n]*"([^"\r\n]+)"', body)
            if match:
                entries.append({"line": line_no, "name": "", "message": match[1],
                                "kind": "choice", "span": (position + match.start(1), position + match.end(1))})
        position += len(line)
    return entries
