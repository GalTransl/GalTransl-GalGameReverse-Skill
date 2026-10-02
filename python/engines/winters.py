# SPDX-License-Identifier: GPL-3.0-only
# Adapted from SExtractor tools/Winters/ifp_pack.py and bytes_pad.py
# Source commit: 8d8d976fd04ae54e7c677705af937273d04a376a
# Upstream attribution: Steins;Gate; SExtractor contributors.
"""Winters IFP unmasked-member container subset; ISD text semantics are external."""
# Layer split: engines; format algorithms and original notices retained.
# Companion module: python/archives/winters.py



def pad_isd_to_original(rebuilt, *, original_size):
    """DAT-route deployment precondition, not a substitute for script relocation."""
    if original_size < len(rebuilt) or original_size > 64 * 1024 * 1024:
        raise ValueError("rebuilt ISD exceeds its original allocation")
    return rebuilt + bytes(original_size - len(rebuilt))
