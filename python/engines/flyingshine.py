# Provenance group: tools-a; sources (repository-relative):
#   SExtractor/tools/FlyingShine/flytool.py
# Symbols: parse_header, read_entries, decrypt_script_payload, encrypt_script_payload
# Validation: tests/test_engines_tools_a.py, synthetic fixtures only.
# Rewritten standard-library bytes API; scope: container-script-shell-roundtrip.
# SPDX-License-Identifier: GPL-3.0-only
# SExtractor tools/FlyingShine/flytool.py: parse_header, read_entries,
# decrypt_script_payload, encrypt_script_payload; commit
# 8d8d976fd04ae54e7c677705af937273d04a376a. Bounds-only bytes rewrite, no OGG edits.
"""FlyingShine PD/2 index and CRLF-derived script XOR. No guessed text syntax."""
# Layer split: engines; format algorithms and original notices retained.
# Companion module: python/archives/flyingshine.py



def script_decode(data: bytes) -> tuple[bytes, int]:
    if len(data) < 2:
        raise ValueError("script too short")
    key = data[-1] ^ 10
    if data[-2] ^ key != 13:
        raise ValueError("CRLF key check failed; do not guess plaintext")
    return bytes(b ^ key for b in data), key


def script_encode(data: bytes, key: int) -> bytes:
    if not data.endswith(b"\r\n") or not 0 <= key <= 255:
        raise ValueError("PD script needs terminal CRLF and byte key")
    return bytes(b ^ key for b in data)
