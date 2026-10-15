"""Synthetic Emote PSB resource-package fixtures; no games or original files.

The fixtures are assembled from the documented header, name-trie, object-tree and
payload-table layout, so the reader is exercised without any game archive.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import contextlib
import io
import struct
import tempfile
import unittest
import zlib
from unittest import mock

from python.archives.emote_psb import MAGIC, Psb, output_names, main
from python.engines.kirikiri_psb import array

HEADER_FIELDS = {"names": 4, "strings": 8, "strings_data": 12, "chunk_offsets": 16,
                 "chunk_lengths": 20, "chunk_data": 24, "root": 28}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
TLG = b"TLG5.0\0raw" + b"\x01" * 12


def _name_arrays(keys):
    trie = {}
    for index, key in enumerate(keys):
        node = trie
        for byte in key.encode("utf-8"):
            node = node.setdefault(byte, {})
        node[0] = index
    bases, parents, used = [0], [0xFFFFFFFF], {0}

    def grow(index):
        while len(bases) <= index:
            bases.append(0)
            parents.append(0xFFFFFFFF)

    def assign(node, index):
        first = 1
        while any(first + byte in used for byte in node):
            first += 1
        grow(index)
        bases[index] = first
        for byte in node:
            used.add(first + byte)
            grow(first + byte)
            parents[first + byte] = index
        for byte, child in node.items():
            if byte == 0:
                bases[first] = child
            else:
                assign(child, first + byte)

    assign(trie, 0)
    return array(bases) + array(parents)


def build_package(spec, *, version=3, checksum=True):
    """Assemble a resource package from ``[(name, payload)]`` in table order."""
    keys = sorted(name for name, _payload in spec)
    order = {key: index for index, key in enumerate(keys)}

    def encode(value):
        if isinstance(value, int):
            width = max(1, (value.bit_length() + 7) // 8)
            if width > 4:
                raise ValueError("fixture chunk index too wide")
            return bytes([24 + width]) + value.to_bytes(width, "little")
        if isinstance(value, dict):
            ordered = sorted(value, key=keys.index)
            children = [encode(value[key]) for key in ordered]
            prefix = b"\x21" + array([order[key] for key in ordered])
        elif isinstance(value, list):
            children = [encode(item) for item in value]
            prefix = b"\x20"
        else:
            raise ValueError("unsupported fixture value")
        offsets, length, stored = [], 0, []
        for chunk in children:
            offsets.append(length)
            length += len(chunk)
            stored.append(chunk)
        return prefix + array(offsets) + b"".join(stored)

    names = _name_arrays(keys)
    root = encode({name: index for index, (name, _payload) in enumerate(spec)})
    payloads = [payload for _name, payload in spec]
    relative, cursor = [], 0
    for payload in payloads:
        relative.append(cursor)
        cursor += len(payload)
    header_size = 44 if version == 3 else 40
    root_at = header_size + len(names)
    strings_at = root_at + len(root)
    strings_data = strings_at + len(array([]))
    chunk_offsets = strings_data
    chunk_lengths = chunk_offsets + len(array(relative))
    chunk_data = chunk_lengths + len(array([len(p) for p in payloads]))
    body = struct.pack("<8I", header_size, header_size, strings_at, strings_data,
                       chunk_offsets, chunk_lengths, chunk_data, root_at)
    if version == 3:
        trailer = struct.pack("<I", zlib.adler32(body) & 0xFFFFFFFF) if checksum else b"\xff" * 4
    else:
        trailer = b""
    return (MAGIC + struct.pack("<HH", version, 0) + body + trailer + names + root
            + array([]) + array(relative) + array([len(p) for p in payloads])
            + b"".join(payloads))


def retarget(data, **fields):
    """Replace header fields and refresh the v3 checksum; structure stays valid."""
    copy = bytearray(data)
    for name, value in fields.items():
        struct.pack_into("<I", copy, 8 + HEADER_FIELDS[name], value)
    if copy[4] == 3:
        struct.pack_into("<I", copy, 40, zlib.adler32(bytes(copy[8:40])) & 0xFFFFFFFF)
    return bytes(copy)


class EmotePsbTests(unittest.TestCase):
    def test_named_payloads_are_extracted_in_table_order(self):
        package = Psb(build_package([("cg001.tlg", TLG), ("a1b2.png", PNG)]))
        self.assertEqual(package.version, 3)
        self.assertEqual([(r.name, r.kind, r.extension) for r in package.resources()],
                         [("cg001.tlg", "tlg", ".tlg"), ("a1b2.png", "png", ".png")])
        self.assertEqual(package.extract(), [("cg001.tlg", TLG), ("a1b2.png", PNG)])
        self.assertEqual(package.summary()["payloads"], 2)
        self.assertEqual(package.summary()["named_payloads"], 2)

    def test_wide_chunk_index_and_positional_fallback(self):
        spec = [(f"layer{i:03d}.tlg", TLG + bytes([i % 251])) for i in range(300)]
        package = Psb(build_package(spec))
        extracted = package.extract()
        self.assertEqual(len(extracted), 300)
        self.assertEqual(extracted[299], ("layer299.tlg", TLG + bytes([299 % 251])))
        self.assertEqual(package.summary()["payload_kinds"], {"tlg": 300})

    def test_unknown_payload_kinds_keep_a_neutral_extension(self):
        package = Psb(build_package([("blob.bin", b"\x01\x02\x03\x04")]))
        self.assertEqual([(r.kind, r.extension) for r in package.resources()],
                         [("unknown", ".bin")])

    def test_script_object_tree_is_not_read_as_a_package(self):
        from test_kirikiri_senren import fixture_tree
        package = Psb(fixture_tree({"scenes": [{"texts": [["id", None, "text", None, 1, {}]]}]}))
        self.assertEqual(package.chunk_table(), [])
        self.assertEqual(package.resources(), [])
        self.assertEqual(package.extract(), [])

    def test_version_two_packages_are_read(self):
        package = Psb(build_package([("cg001.tlg", TLG)], version=2))
        self.assertEqual(package.version, 2)
        self.assertEqual(package.extract(), [("cg001.tlg", TLG)])

    def test_header_rejects_bad_magic_version_encryption_and_checksum(self):
        with self.assertRaisesRegex(ValueError, "not a PSB package"):
            Psb(b"not a psb" + bytes(48))
        for version, message in ((4, "unsupported PSB version"), (1, "unsupported PSB version")):
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, message):
                Psb(MAGIC + struct.pack("<HH", version, 0) + bytes(40))
        encrypted = MAGIC + struct.pack("<HH", 3, 1) + bytes(40)
        with self.assertRaisesRegex(ValueError, "encrypted PSB"):
            Psb(encrypted)
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            Psb(build_package([("cg001.tlg", TLG)], checksum=False))

    def test_section_bounds_and_chunk_ranges_are_enforced(self):
        data = build_package([("cg001.tlg", TLG)])
        with self.assertRaisesRegex(ValueError, "section bounds"):
            Psb(retarget(data, root=1 << 20))
        with self.assertRaisesRegex(ValueError, "section bounds"):
            Psb(retarget(data, chunk_data=len(data) + 8))
        with self.assertRaisesRegex(ValueError, "chunk range"):
            Psb(data[:-1]).resources()

    def test_unsafe_container_names_fall_back(self):
        package = Psb(build_package([("../evil.tlg", TLG)]))
        self.assertEqual([r.name for r in package.resources()], ["../evil.tlg"])
        self.assertEqual(output_names(package.resources()), ["resource_000.tlg"])

    def test_cli_lists_and_extracts_without_overwriting(self):
        data = build_package([("cg001.tlg", TLG), ("a1b2.png", PNG)])
        with tempfile.TemporaryDirectory() as work:
            source = Path(work) / "entry.dpak"
            source.write_bytes(data)
            out = Path(work) / "out"
            with contextlib.redirect_stdout(io.StringIO()):
                with mock.patch("sys.argv", ["emote_psb", "list", str(source)]):
                    main()
                with mock.patch("sys.argv", ["emote_psb", "extract", str(source), str(out)]):
                    main()
            self.assertEqual(sorted(p.name for p in out.iterdir()), ["a1b2.png", "cg001.tlg"])
            self.assertEqual((out / "cg001.tlg").read_bytes(), TLG)
            self.assertEqual((out / "a1b2.png").read_bytes(), PNG)
            with contextlib.redirect_stdout(io.StringIO()):
                with mock.patch("sys.argv", ["emote_psb", "extract", str(source), str(out)]):
                    with self.assertRaises(FileExistsError):
                        main()


if __name__ == "__main__":
    unittest.main()
