# Provenance group: tools-a; sources (repository-relative):
#   SExtractor/tools/MnoViolet/mnv_tool.py
# Symbols: find_name_size, read_entries, is_script_payload
# Validation: tests/test_engines_tools_a.py, synthetic fixtures only.
# Rewritten standard-library bytes API; scope: container-index-script-header.
# SPDX-License-Identifier: GPL-3.0-only
# SExtractor tools/MnoViolet/mnv_tool.py: find_name_size, read_entries;
# commit 8d8d976fd04ae54e7c677705af937273d04a376a. Pure index/header parsing.
"""M no Violet count+fixed-name DAT; returns stored scripts without decompression."""
# Layer split: engines; format algorithms and original notices retained.
# Companion module: python/archives/mnoviolet.py
import struct


def script_header(data: bytes) -> tuple[bytes, int]:
    if len(data) < 24 or data[:16] != bytes(16):
        raise ValueError("not supported zero-header MNV script stream")
    packed, size = struct.unpack_from("<II", data, 16)
    if packed != len(data) - 24 or not 0 < size < 0x10000000:
        raise ValueError("invalid compressed script size")
    return data[24:], size
