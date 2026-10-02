# SPDX-License-Identifier: GPL-3.0-only
# Adapted from SExtractor tools/U-MeSoft/PK_pack.py and src/reg.yaml:U-MeSoft
# Source commit: 8d8d976fd04ae54e7c677705af937273d04a376a
# Upstream attribution: satan53x / SExtractor contributors.
"""U-MeSoft PK index repacker and literal SCR/TBL envelope; no full LZ decoder."""
# Layer split: engines; format algorithms and original notices retained.
# Companion module: python/archives/umesoft.py
import re


def extract_script_lines(text):
    """Conservative decoded SCR dialect: explicit mes name and quoted $L/\\n/\\x0 lines."""
    if len(text) > 8_000_000:
        raise ValueError("SCR exceeds text budget")
    out = []
    for n, line in enumerate(text.splitlines()):
        match = re.match(r'^mes\("([^"\r\n]+)"', line)
        if match:
            out.append({"line": n, "name": match[1], "role": "name"})
            continue
        match = re.fullmatch(r'^"([^"\r\n]+?)(\$L|\\n|\\x0)"$', line)
        if match:
            out.append({"line": n, "message": match[1], "control": match[2]})
    return out
