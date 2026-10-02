# SPDX-License-Identifier: GPL-3.0-only
"""BlueGale BDT XOR and indexwww.dat label index; pure bytes in/out."""
import re
import struct


def xor_bdt(data: bytes) -> bytes:
    return bytes(value ^ 0xFF for value in data)


def build_index(plain_bdt: bytes, *, capacity: int = 0xFA0) -> bytes:
    """8-byte label + LE offset + distance to next label; last distance is zero.

    Offsets count bytes from the plaintext BDT start and point at '$' or '%',
    after any leading tabs. Exact CRLF splitting follows extract_BlueGale_bdt.
    """
    if not 1 <= capacity <= 0xFA0:
        raise ValueError("index capacity must be 1..4000")
    entries = []
    seen = set()
    base = 0
    for line in plain_bdt.split(b"\r\n"):
        match = re.fullmatch(rb"\t*[$%](.*)", line)
        if match:
            name = match.group(1)
            if not name or len(name) > 8 or b"\0" in name:
                raise ValueError("label cannot be stored losslessly in 8 bytes")
            if name in seen:
                raise ValueError("ambiguous duplicate label")
            seen.add(name)
            entries.append((name, base + match.start(1) - 1))
        base += len(line) + 2
    if len(entries) > capacity:
        raise ValueError("index capacity exceeded; refusing to truncate")
    output = bytearray()
    for i, (name, offset) in enumerate(entries):
        length = entries[i + 1][1] - offset if i + 1 < len(entries) else 0
        output.extend(struct.pack("<8sII", name, offset, length))
    output.extend(bytes((capacity - len(entries)) * 16))
    return bytes(output)


def dialogue_spans(line: str) -> tuple[tuple[str, int, int], ...]:
    """Source BDT quote/!name grammar, char spans; no command evaluation."""
    if re.match(r"^\s*[($%#]", line):
        return ()
    match = re.fullmatch(r'(?:V[0-9A-Z]+)?\s*!(?P<name>[^\s]+?)\s*"(?P<message>.+)', line)
    if match:
        return tuple((role, *match.span(role)) for role in ("name", "message"))
    match = re.fullmatch(r'\s*"(?P<message>.+)', line)
    if match:
        return (("message", *match.span("message")),)
    match = re.fullmatch(r"\s*QP([^,]+),([^,]+)(?:,([^,]+))?", line)
    if match:
        return tuple(("choice", *match.span(i)) for i in range(1, 4) if match.group(i) is not None)
    return ()


def package_script(plain_bdt: bytes) -> tuple[bytes, bytes]:
    """Return encrypted BDT and matching index; caller owns transactional deployment."""
    return xor_bdt(plain_bdt), build_index(plain_bdt)
