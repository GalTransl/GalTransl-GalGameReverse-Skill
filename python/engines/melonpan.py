# Provenance group: tools-a; sources (repository-relative):
#   SExtractor/tools/Melonpan/ttd_pack.py
#   SExtractor/tools/Melonpan/xorff.py
# Symbols: parse_ttd, xor_file
# Validation: tests/test_engines_tools_a.py, synthetic fixtures only.
# Rewritten standard-library bytes API; scope: container-index-script-xor.
# SPDX-License-Identifier: GPL-3.0-only
# SExtractor tools/Melonpan/ttd_pack.py: parse_ttd; commit
# 8d8d976fd04ae54e7c677705af937273d04a376a. Strict WCW index rewrite; no IO.
"""Melonpan WCW TTD fixed-record width inferred from first payload offset."""
# Layer split: engines; format algorithms and original notices retained.
# Companion module: python/archives/melonpan.py



def script_xor(data: bytes) -> bytes:
    """tools/Melonpan/xorff.py transform; apply only to confirmed script layer."""
    return bytes(b ^ 255 for b in data)
