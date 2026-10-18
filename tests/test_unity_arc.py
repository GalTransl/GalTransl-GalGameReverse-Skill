# SPDX-License-Identifier: GPL-3.0-only
"""Synthetic Unity .bin/.idx and SNR fixtures; no game assets."""

import struct
import unittest

from python.archives.unity_arc import (
    build_bin,
    pack_record,
    read_index,
    read_member,
    unpack_record,
)
from python.common import aes
from python.engines.unity_snr import apply_snr_texts, open_snr, pack_string


class AesTests(unittest.TestCase):
    def test_fips197_vectors(self):
        plain = bytes.fromhex("00112233445566778899aabbccddeeff")
        key128 = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
        key256 = bytes.fromhex(
            "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f")
        self.assertEqual(aes.encrypt_block(plain, key128).hex(),
                         "69c4e0d86a7b0430d8cdb78070b4c55a")
        self.assertEqual(aes.encrypt_block(plain, key256).hex(),
                         "8ea2b7ca516745bfeafc49904b496089")
        self.assertEqual(aes.decrypt_block(
            bytes.fromhex("8ea2b7ca516745bfeafc49904b496089"), key256), plain)

    def test_cbc_vector_without_padding(self):
        key = bytes.fromhex(
            "603deb1015ca71be2b73aef0857d77811f352c073b6108d72d9810a30914dff4")
        iv = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
        plain = bytes.fromhex(
            "6bc1bee22e409f96e93d7e117393172aae2d8a571e03ac9c9eb76fac45af8e51"
            "30c81c46a35ce411e5fbc1191a0a52eff69f2445df4f9b17ad2b417be66c3710")
        cipher = aes.cbc_encrypt(plain, key, iv, use_padding=False)
        self.assertEqual(cipher.hex()[:32], "f58c4c04d6e5f1ba779eabfb5f7bfbd6")
        self.assertEqual(aes.cbc_decrypt(cipher, key, iv, use_padding=False), plain)

    def test_pkcs7_roundtrip_and_rejects_bad_padding(self):
        key = b"k" * 32
        iv = b"v" * 16
        for length in (0, 1, 15, 16, 17, 100):
            payload = b"x" * length
            self.assertEqual(aes.cbc_decrypt(aes.cbc_encrypt(payload, key, iv), key, iv), payload)
        with self.assertRaises(ValueError):
            aes.cbc_decrypt(bytes(16), key, iv)


class UnityIndexTests(unittest.TestCase):
    def test_record_uses_fixmap_fixstr_str16_and_int32(self):
        blob = pack_record("scenario/sample.bin", 20, 48)
        self.assertEqual(blob[0], 0x83)
        self.assertIn(b"\xda\x00\x13", blob)          # str16 length 19
        self.assertIn(b"\xd2\x00\x00\x00\x14", blob)  # index 20
        record = unpack_record(blob)
        self.assertEqual(record["fileName"], "scenario/sample.bin")
        self.assertEqual((record["index"], record["size"]), (20, 48))

    def test_build_and_read_back(self):
        members = {"data/one.bin": b"first payload", "data/two.bin": b"second payload" * 3}
        bin_data, idx_data = build_bin(members)
        entries = read_index(idx_data)
        self.assertEqual([entry.name for entry in entries], list(members))
        for entry in entries:
            self.assertEqual(read_member(bin_data, entry), members[entry.name])

    def test_bin_layout_has_size_prefix(self):
        bin_data, idx_data = build_bin({"a.bin": b"payload"})
        size = struct.unpack_from("<I", bin_data, 0)[0]
        entry = read_index(idx_data)[0]
        self.assertEqual(entry.offset, 4)
        self.assertEqual(entry.size, size)
        self.assertEqual(len(bin_data), 4 + size)

    def test_truncated_index_and_member_are_refused(self):
        bin_data, idx_data = build_bin({"a.bin": b"payload"})
        with self.assertRaises(ValueError):
            read_index(idx_data[:-1])
        entry = read_index(idx_data)[0]
        with self.assertRaises(ValueError):
            read_member(bin_data[:-1], entry)


class SnrTests(unittest.TestCase):
    def script(self):
        return ("\\text name=Alice\n"
                "Older line\n"
                "Second line\n"
                "\\endtext\n"
                "\\jump target=next\n"
                "\\text\n"
                "Kept line\n"
                "\\endtext\n")

    def test_markers_and_flags(self):
        script, lines = open_snr(pack_string(self.script()))
        self.assertEqual(len(lines), 9)          # trailing newline keeps an empty line
        self.assertTrue(all(line.in_text for line in lines if line.index in (1, 2, 6)))
        self.assertFalse(lines[0].in_text)
        self.assertFalse(lines[3].in_text)
        self.assertFalse(lines[5].in_text)
        self.assertEqual(lines[-1].text, "")

    def test_patch_preserves_non_target_lines(self):
        blob = pack_string(self.script())
        patched = apply_snr_texts(blob, {1: "新しい行", 6: "保たれる"})
        text, lines = open_snr(patched)
        self.assertEqual(lines[1].text, "新しい行")
        self.assertEqual(lines[2].text, "Second line")
        self.assertEqual(lines[6].text, "保たれる")
        self.assertEqual(text.count("\\text"), 2)
        self.assertEqual(text.count("\\endtext"), 2)

    def test_noop_is_byte_identical_and_invalid_edits_refused(self):
        blob = pack_string(self.script())
        self.assertEqual(apply_snr_texts(blob, {}), blob)
        with self.assertRaises(ValueError):
            apply_snr_texts(blob, {0: "x"})
        with self.assertRaises(ValueError):
            apply_snr_texts(blob, {1: "two\nlines"})
        with self.assertRaises(ValueError):
            apply_snr_texts(blob, {1: "\\text"})

    def test_wrong_payload_type_is_refused(self):
        with self.assertRaises(ValueError):
            open_snr(b"\x01")


if __name__ == "__main__":
    unittest.main()
