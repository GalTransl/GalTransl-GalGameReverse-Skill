# SPDX-License-Identifier: GPL-3.0-only
"""Synthetic AliceSoft AI2/AIN fixtures; no game assets."""

import struct
import unittest
import zlib

from python.archives.ain import HEADER_SIZE, repack, unpack
from python.engines.alicesoft import cipher, read_ain, rewrite_ain


def ai2(raw, *, stored=None, raw_size=None):
    payload = zlib.compress(raw) if stored is None else stored
    head = bytearray(HEADER_SIZE)
    head[0:4] = b"AI2\x00"
    head[8:12] = (len(raw) if raw_size is None else raw_size).to_bytes(4, "little")
    head[12:16] = len(payload).to_bytes(4, "little")
    return bytes(head) + payload


def msg1(entries):
    out = bytearray(b"MSG1" + struct.pack("<ii", len(entries), 0))
    for text in entries:
        body = cipher(text.encode("cp932"), decrypt=False)
        out += struct.pack("<i", len(body)) + body
    return bytes(out)


def strings(tag, entries):
    out = bytearray(tag + struct.pack("<i", len(entries)))
    for text in entries:
        out += text.encode("cp932") + b"\x00"
    return bytes(out)


def body():
    return (b"VERS" + struct.pack("<i", 5)
            + msg1(["花子「遅い」", "MSG1 decoy inside text"])
            + b"CODE" + b"\x00" * 8
            + strings(b"MSG0", ["plain one", "plain two"])
            + strings(b"STR0", ["nonnull guard", "file name"]))


class AliceSoftAinTests(unittest.TestCase):
    def test_ai2_container_roundtrip_and_limits(self):
        raw = body()
        self.assertEqual(unpack(ai2(raw)), raw)
        rebuilt = repack(ai2(raw), raw)
        self.assertEqual(unpack(rebuilt), raw)
        self.assertEqual(int.from_bytes(rebuilt[8:12], "little"), len(raw))
        with self.assertRaises(ValueError):
            unpack(ai2(raw, raw_size=len(raw) + 1))
        with self.assertRaises(ValueError):
            unpack(ai2(raw)[:-1])

    def test_tables_are_found_once_and_stop_at_boundaries(self):
        tables, texts = read_ain(body())
        self.assertEqual([t.tag for t in tables], ["MSG1", "MSG0", "STR0"])
        self.assertEqual([t.text for t in tables[0].texts],
                         ["花子「遅い」", "MSG1 decoy inside text"])
        self.assertEqual([t.text for t in tables[1].texts], ["plain one", "plain two"])
        self.assertEqual(len(texts), 6)

    def test_msg1_rewrite_pads_with_spaces_inside_the_cipher(self):
        raw = body()
        _, texts = read_ain(raw)
        changed = rewrite_ain(raw, {0: "花子「遅」"})
        _, check = read_ain(changed)
        self.assertEqual(check[0].text, "花子「遅」")
        self.assertEqual(check[0].length, texts[0].length)
        self.assertEqual(check[1].text, texts[1].text)
        # The slot decrypts to text plus spaces, not to cipher residue.
        start = texts[0].offset
        slot = cipher(changed[start:start + texts[0].length], decrypt=True).decode("cp932")
        written = "花子「遅」"
        self.assertEqual(slot, written + " " * (texts[0].length - len(written.encode("cp932"))))

    def test_msg0_rewrite_keeps_slot_length_and_rejects_growth(self):
        raw = body()
        _, texts = read_ain(raw)
        changed = rewrite_ain(raw, {2: "短"})
        _, check = read_ain(changed)
        self.assertEqual(check[2].text, "短")
        self.assertEqual(check[3].text, "plain two")
        with self.assertRaises(ValueError):
            rewrite_ain(raw, {0: "this text is far too long for the slot" * 4})
        with self.assertRaises(ValueError):
            rewrite_ain(raw, {0: "trailing "})

    def test_unknown_index_and_non_boundary_table_are_refused(self):
        raw = body()
        with self.assertRaises(ValueError):
            rewrite_ain(raw, {99: "x"})
        broken = b"\x00" + b"MSG1" + struct.pack("<ii", 1, 0) + struct.pack("<i", 4) + b"\x01\x02\x03\x04" + b"junk"
        with self.assertRaises(ValueError):
            rewrite_ain(broken, {0: "x"})


if __name__ == "__main__":
    unittest.main()
