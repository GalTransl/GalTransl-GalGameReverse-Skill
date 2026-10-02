# SPDX-License-Identifier: GPL-3.0-only AND MIT
# SExtractor tools/Xuse/gd_scr_decrypt.py
# Source commit: 8d8d976fd04ae54e7c677705af937273d04a376a
# GARbro-Mod ArcFormats/Xuse/ArcGD.cs
# Source commit: bc26d991ef5cdc0e1ecb32122ee9a48c3375750c
# Upstream attribution: satan53x / SExtractor contributors.
# Copyright (C) 2016 by morkt
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.
"""Xuse GD + companion DLL data index; the companion is NOT a loaded executable."""
# Layer split: archives; format algorithms and original notices retained.
# Companion module: python/engines/xuse.py
import struct


def parse_gd(gd, index):
    if len(gd) < 4 or len(index) < 12 or (len(index) - 4) % 8:
        raise ValueError("invalid GD/companion-index bounds")
    count = struct.unpack_from("<I", gd)[0]
    if not 0 < count <= 100_000 or count & 0xFFFF == 0x5A4D or count != (len(index) - 4) // 8:
        raise ValueError("GD count does not agree with companion data index")
    entries, previous_end = [], 4
    for i in range(count):
        offset, size = struct.unpack_from("<II", index, 4 + i * 8)
        if offset < previous_end or size > len(gd) - offset:
            raise ValueError("invalid GD member placement")
        entries.append({"offset": offset, "data": gd[offset:offset + size]})
        previous_end = offset + size
    return entries


def repack_gd(gd, index, replacements):
    """Map 0-based member index -> stored bytes; rebuild companion offsets/lengths.

    Preserve gaps and the unknown first companion DWORD. Ciphering is a separate
    explicit step; arbitrary GD assets must not all be treated as script text.
    """
    entries = parse_gd(gd, index)
    if any(type(i) is not int or not 0 <= i < len(entries) for i in replacements):
        raise ValueError("unknown GD member index")
    output, new_index, previous_end = bytearray(gd[:4]), bytearray(index[:4]), 4
    for i, entry in enumerate(entries):
        output.extend(gd[previous_end:entry["offset"]])
        raw = replacements.get(i, entry["data"])
        new_index.extend(struct.pack("<II", len(output), len(raw)))
        output.extend(raw)
        previous_end = entry["offset"] + len(entry["data"])
    output.extend(gd[previous_end:])
    return bytes(output), bytes(new_index)
