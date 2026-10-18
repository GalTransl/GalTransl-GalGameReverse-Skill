# SPDX-License-Identifier: GPL-3.0-only
"""Synthetic Kaguya early message blocks and TBLSTR fixtures; no game assets."""

import struct
import unittest

from python.archives.kaguya_tblstr import open_tblstr, patch_tblstr, read_entry
from python.engines.kaguya_early import patch_early_message, read_early_message


def xor(data):
    return bytes(value ^ 0xFF for value in data)


def block(payload):
    return struct.pack("<I", len(payload)) + xor(payload)


def sample_early():
    header = b"[SCR-MESSAGE]" + b"ver2" + b"\x00\x00"
    payload_a = "名前".encode("cp932") + b"\0" + b"\x02"
    payload_a += "一行目".encode("cp932") + b"\0" + "二行目".encode("cp932") + b"\0"
    payload_b = b"\0" + b"\0" + "選択肢".encode("cp932") + b"\0" + b"\x01\x02"
    return header + block(payload_a) + block(payload_b) + b"\0\0\0\0TAIL"


def tbl_record(message_id, text, trailer=b"\0\0", *, minus_two=True):
    encoded = text.encode("cp932")
    length = len(encoded) + (2 if minus_two else 0)
    raw = struct.pack("<ii", message_id, length) + xor(encoded) + trailer
    return raw


class EarlyMessageTests(unittest.TestCase):
    def test_reads_names_messages_and_choice_tail(self):
        document = read_early_message(sample_early())
        blocks, trailer = document.blocks, document.trailer
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0].name, "名前")
        self.assertEqual(blocks[0].messages, ("一行目", "二行目"))
        self.assertEqual(blocks[0].count, 2)
        self.assertIsNone(blocks[0].choice)
        self.assertEqual(blocks[1].name, "")
        self.assertEqual(blocks[1].choice, "選択肢")
        self.assertEqual(blocks[1].tail, b"\x01\x02")
        self.assertEqual(trailer, b"\0\0\0\0TAIL")

    def test_variable_length_rewrite_recomputes_lengths(self):
        patched = patch_early_message(sample_early(), {
            0: {"name": "長い名前", "messages": ["新しい一行目", "短い"]},
            1: {"choice": "別の選択肢"},
        })
        document = read_early_message(patched)
        blocks, trailer = document.blocks, document.trailer
        self.assertEqual(blocks[0].name, "長い名前")
        self.assertEqual(blocks[0].messages, ("新しい一行目", "短い"))
        self.assertEqual(blocks[1].choice, "別の選択肢")
        self.assertEqual(blocks[1].tail, b"\x01\x02")
        self.assertEqual(trailer, b"\0\0\0\0TAIL")

    def test_untouched_block_keeps_its_stored_bytes(self):
        source = sample_early()
        patched = patch_early_message(source, {1: {"choice": "変更"}})
        blocks = read_early_message(source).blocks
        start = blocks[0].offset
        size = blocks[0].payload_size
        self.assertEqual(patched[start:start + 4 + size],
                         source[start:start + 4 + size])

    def test_declared_count_mismatch_is_strict_but_can_be_relaxed(self):
        header = b"[SCR-MESSAGE]" + b"ver2" + b"\x00\x00"
        payload = "名".encode("cp932") + b"\0" + b"\x03" + "一".encode("cp932") + b"\0"
        blob = header + block(payload) + b"\0\0\0\0"
        with self.assertRaises(ValueError):
            read_early_message(blob)
        blocks = read_early_message(blob, strict=False).blocks
        self.assertEqual(blocks[0].messages, ("一",))
        self.assertEqual(blocks[0].count, 3)

    def test_truncated_and_unknown_versions_are_refused(self):
        with self.assertRaises(ValueError):
            read_early_message(b"[SCR-MESSAGE]" + b"ver2" + b"\x00\x00" + b"\x05\x00")
        with self.assertRaises(ValueError):
            read_early_message(b"[SCR-MESSAGE]" + b"ver4" + b"\x00")
        with self.assertRaises(ValueError):
            read_early_message(b"not a kaguya table at all")

    def test_message_count_cannot_change(self):
        with self.assertRaises(ValueError):
            patch_early_message(sample_early(), {0: {"messages": ["だけ"]}})


class TblStrTests(unittest.TestCase):
    def sample(self, dialect):
        record_a = tbl_record(11, "あい", minus_two=dialect != "uf01")
        record_b = tbl_record(22, "うえ", minus_two=dialect != "uf01")
        addresses = [0x20, 0x40]
        if dialect == "ari":
            data = bytearray(b"\0" * 0x60)
            data[0:4] = b"\x00\x00\x00\x00"
            data[0x20:0x20 + len(record_a)] = record_a
            data[0x40:0x40 + len(record_b)] = record_b
            ari = b"\x00\x00\x00\x00" + struct.pack("<ii", *addresses)
            return bytes(data), ari
        if dialect == "embedded":
            data = bytearray(b"\xb8\x33\x25\x00" + b"\0" * 0x5C)
            data[0x20:0x20 + len(record_a)] = record_a
            data[0x40:0x40 + len(record_b)] = record_b
            ari = b"\x00\x00\x00\x00" + struct.pack("<ii", *addresses)
            return bytes(data), ari
        data = bytearray(b"UF01" + struct.pack("<I", 0x60) + b"\0" * 0x58)
        data[0x20:0x20 + len(record_a)] = record_a
        data[0x40:0x40 + len(record_b)] = record_b
        data += struct.pack("<II", *addresses)
        return bytes(data), None

    def test_reads_all_three_dialects(self):
        for dialect in ("ari", "embedded", "uf01"):
            data, ari = self.sample(dialect)
            archive = open_tblstr(data, ari)
            self.assertEqual(archive.dialect, dialect)
            self.assertEqual([read_entry(archive, e) for e in archive.entries],
                             ["あい", "うえ"])
            if dialect != "uf01":
                self.assertEqual(archive.entries[0].length, 4)
                self.assertEqual(archive.entries[0].trailer, b"\0\0")

    def test_embedded_needs_its_ari(self):
        data, _ = self.sample("embedded")
        with self.assertRaises(ValueError):
            open_tblstr(data)

    def test_fixed_slot_patch_and_overlong_refusal(self):
        for dialect in ("ari", "embedded", "uf01"):
            data, ari = self.sample(dialect)
            archive = open_tblstr(data, ari)
            patched = patch_tblstr(data, archive, {0: "亜"}, encoding="gbk")
            again = open_tblstr(patched, ari)
            self.assertEqual(again.entries[0].raw,
                             "亜".encode("gbk") + b" " * (archive.entries[0].length - 2))
            self.assertEqual(again.entries[1].raw, archive.entries[1].raw)
            with self.assertRaises(ValueError):
                patch_tblstr(data, archive, {0: "長すぎる"}, encoding="gbk")

    def test_bad_addresses_are_refused(self):
        data, ari = self.sample("ari")
        broken = bytearray(ari)
        struct.pack_into("<i", broken, 4, 0x10000)
        with self.assertRaises(ValueError):
            open_tblstr(data, bytes(broken))
        with self.assertRaises(ValueError):
            open_tblstr(data[:0x28], ari)


if __name__ == "__main__":
    unittest.main()
