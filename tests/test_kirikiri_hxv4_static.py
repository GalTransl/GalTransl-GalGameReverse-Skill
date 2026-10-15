"""Synthetic PE32/PE32+ resource-directory fixtures for the static PE reader.

Hand-assembled from the documented optional-header layout; no real executable is
copied or loaded. Only the fields the Hxv4 key search reads are populated.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import struct
import unittest

from python.archives.kirikiri_hxv4_static import PE, PE32, PE32PLUS


def _align(value, alignment):
    return (value + alignment - 1) // alignment * alignment


def _resource_tree(entries, base):
    """Serialize a resource tree from ``(type, name, payload)`` entries.

    The tree is type -> name -> language -> data entry, the three levels the
    reader walks. ``type``/``name`` are ``str`` for a named entry or ``int`` for
    an id entry; RVAs are ``base`` plus the offset inside the returned blob.
    """
    types = list(dict.fromkeys(kind for kind, _n, _p in entries))
    names_of = {kind: [name for k, name, _p in entries if k == kind] for kind in types}
    data_of = {(kind, name): payload for kind, name, payload in entries}

    cursor = 16 + 8 * len(types)
    l2_at = {}
    for kind in types:
        l2_at[kind] = cursor
        cursor += 16 + 8 * len(names_of[kind])
    l3_at = {}
    for kind in types:
        for name in names_of[kind]:
            l3_at[(kind, name)] = cursor
            cursor += 16 + 8
    leaf_at = {}
    for kind in types:
        for name in names_of[kind]:
            leaf_at[(kind, name)] = cursor
            cursor += 16
    string_at = {}
    for kind in types:
        for text in [kind] + names_of[kind]:
            if isinstance(text, str) and text not in string_at:
                string_at[text] = cursor
                cursor += 2 + 2 * len(text)
    data_at = {}
    cursor = _align(cursor, 4)
    for kind in types:
        for name in names_of[kind]:
            data_at[(kind, name)] = cursor
            cursor += _align(len(data_of[(kind, name)]), 4)

    blob = bytearray(cursor)

    def directory(at, named, ids):
        struct.pack_into("<IIHHHH", blob, at, 0, 0, 0, 0, len(named), len(ids))
        pos = at + 16
        for text, dest in named:
            struct.pack_into("<II", blob, pos, 0x80000000 | string_at[text], dest)
            pos += 8
        for ident, dest in ids:
            struct.pack_into("<II", blob, pos, ident, dest)
            pos += 8

    directory(0, [(k, l2_at[k]) for k in types if isinstance(k, str)],
              [(k, l2_at[k]) for k in types if isinstance(k, int)])
    for kind in types:
        directory(l2_at[kind], [(n, l3_at[(kind, n)]) for n in names_of[kind] if isinstance(n, str)],
                  [(n, l3_at[(kind, n)]) for n in names_of[kind] if isinstance(n, int)])
        for name in names_of[kind]:
            directory(l3_at[(kind, name)], [], [(0, leaf_at[(kind, name)])])
            struct.pack_into("<IIII", blob, leaf_at[(kind, name)],
                             base + data_at[(kind, name)], len(data_of[(kind, name)]), 0, 0)
    for text, at in string_at.items():
        units = text.encode("utf-16-le")
        struct.pack_into("<H", blob, at, len(units) // 2)
        blob[at + 2:at + 2 + len(units)] = units
    for kind in types:
        for name in names_of[kind]:
            at = data_at[(kind, name)]
            payload = data_of[(kind, name)]
            blob[at:at + len(payload)] = payload
    return bytes(blob)


def build_pe(entries, *, bits=32, image_base=None, salt_store=None, pad=0):
    """Minimal single-section PE (VA == file offset) carrying a resource directory.

    ``salt_store`` is an optional ``(address, target_rva)`` pair written as a
    ``c7 05`` store pair so the 32-bit salt scan has something to find.
    """
    optional_size = 0xE0 if bits == 32 else 0xF0
    headers = _align(0x40 + 4 + 20 + optional_size + 40, 8)
    tree = _resource_tree(entries, headers)
    data = bytearray(headers + len(tree))
    data[0:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x40)
    data[0x40:0x44] = b"PE\0\0"
    struct.pack_into("<HH", data, 0x44, 1, 1)
    struct.pack_into("<H", data, 0x40 + 20, optional_size)
    optional = 0x40 + 24
    struct.pack_into("<H", data, optional, PE32 if bits == 32 else PE32PLUS)
    if bits == 32:
        struct.pack_into("<I", data, optional + 0x1C, 0x400000 if image_base is None else image_base)
    else:
        struct.pack_into("<Q", data, optional + 0x18, 0x140000000 if image_base is None else image_base)
    struct.pack_into("<I", data, optional + (0x5C if bits == 32 else 0x6C), 16)
    struct.pack_into("<I", data, optional + (0x70 if bits == 32 else 0x80), headers)
    data[headers:headers + len(tree)] = tree
    if salt_store is not None:
        address, target = salt_store
        data += b"\xc7\x05" + b"\0" * 4 + struct.pack("<I", address)
        data += b"\xc7\x05" + b"\0" * 4 + struct.pack("<I", target)
    data += b"\0" * pad
    section = optional + optional_size
    struct.pack_into("<II", data, section + 8, len(data), 0)
    struct.pack_into("<I", data, section + 16, len(data))
    struct.pack_into("<I", data, section + 20, 0)
    return bytes(data)


class PeResourceTests(unittest.TestCase):
    def test_pe32_resource_lookup(self):
        root = "bres://./root/".encode("utf-16-le")
        pe = PE(build_pe([("TEXT", 127, root), (10, "STARTUP.TJS", b"tjs")]))
        self.assertEqual((pe.magic, pe.bits, pe.base), (PE32, 32, 0x400000))
        self.assertEqual(pe.resource("TEXT", 127), root)
        self.assertEqual(pe.resource(10, "STARTUP.TJS"), b"tjs")
        with self.assertRaisesRegex(ValueError, "resource missing"):
            pe.resource("TEXT", 1)

    def test_pe32plus_resource_lookup_and_64_bit_image_base(self):
        pe = PE(build_pe([("TEXT", 127, b"root"), (10, "BOOTSTRAP", b"payload")], bits=64))
        self.assertEqual((pe.magic, pe.bits, pe.base), (PE32PLUS, 64, 0x140000000))
        self.assertEqual(pe.resource("TEXT", 127), b"root")
        self.assertEqual(pe.resource(10, "BOOTSTRAP"), b"payload")
        high = PE(build_pe([("TEXT", 127, b"root")], bits=64, image_base=0x180000000))
        self.assertEqual(high.base, 0x180000000)

    def test_unsupported_and_malformed_headers_are_rejected(self):
        with self.assertRaises(ValueError):
            PE(bytes(64))
        blob = bytearray(build_pe([("TEXT", 127, b"root")]))
        struct.pack_into("<H", blob, 0x40 + 24, 0x107)
        with self.assertRaisesRegex(ValueError, "unsupported PE layout"):
            PE(bytes(blob))
        blob = bytearray(build_pe([("TEXT", 127, b"root")]))
        struct.pack_into("<I", blob, 0x40 + 24 + 0x5C, 2)
        with self.assertRaisesRegex(ValueError, "resource data directory"):
            PE(bytes(blob))


class PeSaltScanTests(unittest.TestCase):
    def test_32_bit_store_form_yields_a_candidate(self):
        blob = build_pe([("TEXT", 127, b"root")], salt_store=(0x400000, 8192), pad=0x2000)
        self.assertEqual(PE(blob).salts(), [blob[0:8192]])

    def test_64_bit_store_form_is_not_misapplied(self):
        blob = build_pe([("TEXT", 127, b"root")], bits=64, salt_store=(0x400000, 8192), pad=0x2000)
        self.assertEqual(PE(blob).salts(), [])


if __name__ == "__main__":
    unittest.main()
