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
# Layer split: engines; format algorithms and original notices retained.
# Companion module: python/archives/xuse.py



def crypt_script(data, *, key):
    """Caller-supplied four-byte repeating XOR key; only extracted script members."""
    if not isinstance(key, bytes) or len(key) != 4:
        raise ValueError("Xuse script key must be exactly four bytes")
    return bytes(b ^ key[i % 4] for i, b in enumerate(data))
