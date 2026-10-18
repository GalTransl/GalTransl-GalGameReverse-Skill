# SPDX-License-Identifier: GPL-3.0-only
"""Synthetic Bishop GSC fixtures; no game assets."""

import struct
import unittest

from python.archives.bishop_gsc import apply_gsc_texts, open_gsc


def build_gsc(strings, encoding="cp932", *, string_segment=None, string_size=None):
    """Header, two leading sections, the NUL string run and four trailing ones."""
    if string_segment is None:
        string_segment = b"".join(text.encode(encoding) + b"\x00" for text in strings)
    if string_size is None:
        string_size = len(string_segment)
    sections = (b"\x11\x12", b"\x21", b"\x31" * 2, b"\x41" * 4, b"\x51" * 3, b"\x61")
    header = struct.pack("<9i", 0x01020304, 0x05060708, len(sections[0]), len(sections[1]),
                         string_size, len(sections[2]), len(sections[3]) // 2,
                         len(sections[4]), len(sections[5]))
    return (header + sections[0] + sections[1] + string_segment
            + sections[2] + sections[3] + sections[4] + sections[5])


class GscReadTests(unittest.TestCase):
    def test_reads_positions_lengths_and_text(self):
        raw = build_gsc(["こんにちは", "世界"])
        script = open_gsc(raw)
        self.assertEqual([entry.text for entry in script.strings], ["こんにちは", "世界"])
        first = raw.index("こんにちは".encode("cp932"))
        self.assertEqual(script.strings[0].position, first)
        self.assertEqual(script.strings[0].maxlength, len("こんにちは".encode("cp932")))
        self.assertEqual(script.string_offset, 36 + 2 + 1)

    def test_empty_slots_and_single_nul_section(self):
        self.assertEqual(open_gsc(build_gsc([], string_segment=b"\x00")).strings, ())
        self.assertEqual(open_gsc(build_gsc([], string_segment=b"a")).strings, ())
        raw = build_gsc(["a", "", "b"], string_segment=b"a\x00\x00b\x00")
        self.assertEqual([entry.text for entry in open_gsc(raw).strings], ["a", "b"])

    def test_rejects_unsupported_and_inconsistent_layouts(self):
        with self.assertRaises(ValueError):
            open_gsc(build_gsc([], string_segment=b"", string_size=0))
        with self.assertRaises(ValueError):
            open_gsc(build_gsc(["abc"])[:20])
        broken = bytearray(build_gsc(["abc"]))
        struct.pack_into("<i", broken, 0x10, len(broken))
        with self.assertRaises(ValueError):
            open_gsc(bytes(broken))
        with self.assertRaises(ValueError):
            open_gsc(build_gsc([], string_segment=b"abc"))
        with self.assertRaises(ValueError):
            open_gsc(build_gsc([], string_segment=b"\x81\x00"))


class GscWriteTests(unittest.TestCase):
    def test_short_translation_is_space_padded(self):
        raw = build_gsc(["こんにちは", "世界"])
        script = open_gsc(raw)
        patched = apply_gsc_texts(raw, script, ["你好", "世界"])
        self.assertEqual(len(patched), len(raw))
        self.assertNotEqual(raw, patched)
        revised = open_gsc(patched, encoding="gbk")
        self.assertEqual([entry.text for entry in revised.strings],
                         ["你好" + " " * 6, "世界"])

    def test_equal_length_and_rejected_oversize(self):
        raw = build_gsc(["abc"])
        script = open_gsc(raw)
        patched = apply_gsc_texts(raw, script, ["xyz"])
        self.assertEqual(open_gsc(patched).strings[0].text, "xyz")
        with self.assertRaises(ValueError):
            apply_gsc_texts(raw, script, ["abcd"])
        with self.assertRaises(ValueError):
            apply_gsc_texts(raw, script, [])
        with self.assertRaises(ValueError):
            apply_gsc_texts(raw, script, [""])


if __name__ == "__main__":
    unittest.main()
