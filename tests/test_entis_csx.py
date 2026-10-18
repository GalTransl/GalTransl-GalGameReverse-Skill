# SPDX-License-Identifier: GPL-3.0-only
"""Synthetic EntisGLS .csx fixtures; no game assets."""

import struct
import unittest

from python.archives.entis_csx import (HEADER_SIZE, build_csx, parse_chunks, parse_conststr,
                                       parse_image, patch_image, rebuild_conststr)


def csx(chunks, trailer=b"\x00tail"):
    head = bytearray(HEADER_SIZE)
    head[0:5] = b"Entis"
    head[16:16 + 18] = b"Cotopha Image file"
    body = bytearray()
    for name, payload in chunks:
        body += name.ljust(8).encode("ascii") + struct.pack("<q", len(payload)) + payload
    return bytes(head) + bytes(body) + trailer


def conststr(entries):
    out = bytearray(struct.pack("<i", len(entries)))
    for text, extras in entries:
        encoded = text.encode("utf-16-le")
        out += struct.pack("<i", len(encoded) // 2) + encoded
        out += struct.pack("<i", len(extras)) + b"".join(struct.pack("<i", v) for v in extras)
    return bytes(out)


def image(*literals, tail=b"\x09\x00"):
    """csicCall(immediate, 0, literal) for each literal, then return."""
    out = bytearray()
    for text in literals:
        encoded = text.encode("utf-16-le")
        out += b"\x08\x00" + struct.pack("<i", 0) + struct.pack("<I", len(encoded) // 2) + encoded
    return bytes(out) + tail


class CsxTests(unittest.TestCase):
    def setUp(self):
        self.raw = csx([("conststr", conststr([("花子", (7, 8)), ("", ()), ("abc", ())])),
                        ("image   ", image("Title"))])

    def test_directory_and_trailer(self):
        chunks = parse_chunks(self.raw)
        self.assertEqual([c.name for c in chunks], ["conststr", "image"])
        self.assertEqual(chunks[0].offset, HEADER_SIZE)
        self.assertTrue(rebuild_conststr(self.raw, {}).endswith(b"\x00tail"))

    def test_conststr_entries_keep_empty_slots_and_extras(self):
        entries = parse_conststr(self.raw)
        self.assertEqual([e.text for e in entries], ["花子", "", "abc"])
        self.assertEqual(entries[0].extras, (7, 8))
        self.assertEqual([e.writable for e in entries], [True, False, True])

    def test_conststr_growth_updates_chunk_and_reparses(self):
        rebuilt = rebuild_conststr(self.raw, {0: "更长的姓名", 2: "abcd"})
        entries = parse_conststr(rebuilt)
        self.assertEqual(entries[0].text, "更长的姓名")
        self.assertEqual(entries[1].text, "")
        self.assertEqual(entries[2].text, "abcd")
        # The following chunk moved but its payload and the trailer are intact.
        self.assertEqual(parse_image(rebuilt)[0].text, "Title")
        self.assertTrue(rebuilt.endswith(b"\x00tail"))

    def test_conststr_rejects_placeholder_and_unknown_slot(self):
        with self.assertRaises(ValueError):
            rebuild_conststr(self.raw, {1: "x"})
        with self.assertRaises(ValueError):
            rebuild_conststr(self.raw, {3: "x"})
        with self.assertRaises(ValueError):
            rebuild_conststr(self.raw, {0: "bad\0"})

    def test_image_literal_patch_is_fixed_length(self):
        patched = patch_image(self.raw, {0: "標題"})
        # The slot keeps its 5-char width, so the tail is space padded.
        self.assertEqual(parse_image(patched)[0].text, "標題   ")
        self.assertEqual(len(patched), len(self.raw))
        with self.assertRaises(ValueError):
            patch_image(self.raw, {0: "too long for the slot"})
        with self.assertRaises(ValueError):
            patch_image(self.raw, {0: "a\0"})

    def test_image_walk_is_strict(self):
        broken = csx([("image   ", image("Title", tail=b"\x09\x00\x00"))])
        with self.assertRaises(ValueError):
            parse_image(broken)  # trail byte cannot start an instruction
        unknown = csx([("image   ", b"\x01\x00")])
        with self.assertRaises(ValueError):
            parse_image(unknown)  # csicFree has no operand table here
        high = csx([("image   ", b"\x90\x00\x00\x00")])
        with self.assertRaises(ValueError):
            parse_image(high)

    def test_container_validation(self):
        with self.assertRaises(ValueError):
            parse_chunks(b"Entis" + b"\0" * 100)
        bad = bytearray(self.raw)
        struct.pack_into("<q", bad, HEADER_SIZE + 8, 1 << 40)
        with self.assertRaises(ValueError):
            parse_chunks(bytes(bad))
        with self.assertRaises(ValueError):
            build_csx(self.raw, [type(parse_chunks(self.raw)[0])("toolongname", 0, b"x")])


if __name__ == "__main__":
    unittest.main()
