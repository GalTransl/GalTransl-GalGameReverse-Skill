# SPDX-License-Identifier: GPL-3.0-only
"""Synthetic VALKYRIA .dat and .sdt fixtures; no game assets."""

import struct
import unittest

from python.archives.valkyria import build_dat, open_dat, read_member
from python.engines.valkyria import open_sdt, write_sdt, xor_body


def sample_script():
    body = bytearray(b"\x00\x01prefix")
    body += b"\xfe\xf1" + b"\xee\xee" + b"\x00\x00\x00\x00" + "テキスト".encode("cp932") + b"\0"
    body += b"\x8f\xf5" + b"\xff\xf1" + "名前".encode("cp932") + b"\0"
    body += b"\xfb\xf1\x00\x00\x00\x00\x00\x00\xff\xf1" + "別名".encode("cp932") + b"\0"
    body += b"\xe3\xf1" + b"\xff\xff\xff\xff" + b"\x01" + "選択肢".encode("cp932") + b"\0\x00"
    body += b"\x99\x88tail"
    return bytes(body)


class DatTests(unittest.TestCase):
    def test_build_and_read_back(self):
        members = {"script.sdt": b"one", "image.bin": b"two" * 40}
        blob = build_dat(members)
        archive = open_dat(blob)
        self.assertEqual([entry.name for entry in archive.entries], list(members))
        for entry in archive.entries:
            self.assertEqual(read_member(blob, entry), members[entry.name])

    def test_offsets_are_relative_to_payload(self):
        blob = build_dat({"a.bin": b"abc"})
        archive = open_dat(blob)
        self.assertEqual(archive.entries[0].offset, 4 + 268)

    def test_bad_index_and_names_are_refused(self):
        good = build_dat({"a.bin": b"abc"})
        with self.assertRaises(ValueError):
            open_dat(b"\x00\x00\x00\x00" + b"\0" * 300)
        with self.assertRaises(ValueError):
            open_dat(struct.pack("<I", 268 * 9) + b"\0" * 300)
        with self.assertRaises(ValueError):
            build_dat({"x" * 300: b"abc"})


class SdtTests(unittest.TestCase):
    def test_all_four_span_shapes_are_found(self):
        plain, spans = open_sdt(xor_body(sample_script()))
        self.assertEqual([span.kind for span in spans], ["text", "name", "name", "choice"])
        self.assertEqual([span.text for span in spans],
                         ["テキスト", "名前", "別名", "選択肢"])

    def test_offsets_point_at_the_stored_string(self):
        blob = xor_body(sample_script())
        plain, spans = open_sdt(blob)
        for span in spans:
            raw = plain[span.offset:span.offset + span.length]
            self.assertEqual(raw.decode("cp932"), span.text)

    def test_fixed_length_rewrite_pads_with_spaces(self):
        blob = xor_body(sample_script())
        _, spans = open_sdt(blob)
        patched = write_sdt(blob, {0: "短", 3: "選択"}, write_encoding="cp932")
        _, check = open_sdt(patched)
        self.assertEqual(check[0].text, "短" + " " * (spans[0].length - 2))
        self.assertEqual(check[1].text, "名前")
        self.assertEqual(check[3].text, "選択" + " " * (spans[3].length - 4))

    def test_growth_and_unterminated_strings_are_refused(self):
        blob = xor_body(sample_script())
        with self.assertRaises(ValueError):
            write_sdt(blob, {0: "これは長すぎるテキストです" * 3})
        broken = xor_body(b"\xfe\xf1\xee\xee\x00\x00\x00\x00" + b"no terminator")
        with self.assertRaises(ValueError):
            open_sdt(broken)

    def test_xor_is_its_own_inverse(self):
        blob = xor_body(sample_script())
        self.assertEqual(xor_body(blob), sample_script())


if __name__ == "__main__":
    unittest.main()
