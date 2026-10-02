"""Synthetic strict DSC decoder tests (GPL-3.0-or-later)."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dataclasses import replace
import inspect
import random
import struct
import unittest
from unittest.mock import patch

from python.archives import bgi, bgi_dsc
from bgi_fixtures import _dsc_frame, literal_dsc, overlap_dsc, pack_archive


def _u32(data, offset, value):
    result = bytearray(data)
    struct.pack_into("<I", result, offset, value)
    return bytes(result)


class DscTests(unittest.TestCase):
    def fails(self, data, code, **limits):
        with self.assertRaises(bgi.BgiArchiveError) as caught:
            bgi_dsc.decode(data, **limits)
        error = caught.exception
        self.assertIsInstance(error, ValueError)
        self.assertEqual(error.code, code)
        self.assertEqual(error.stage, "decode")
        self.assertTrue(error.offset is None or isinstance(error.offset, int))
        return error

    def test_literal_all_bytes_and_binary_not_script(self):
        payload = bytes(range(256)) * 3
        for seed in (0, 1, 0x12345678, 0xffffffff):
            with self.subTest(seed=seed):
                frame = literal_dsc(payload, seed)
                self.assertEqual(frame[0x220:], payload)
                self.assertEqual(bgi_dsc.decode(frame), payload)
        self.assertEqual(bgi_dsc.decode_dsc(literal_dsc(b"image\0\xff")), b"image\0\xff")

    def test_empty_output(self):
        self.assertEqual(bgi_dsc.decode(literal_dsc(b""), max_output_size=0, max_symbols=0), b"")
        empty = _dsc_frame([0] * 512, 0, 0, b"")
        self.assertEqual(bgi_dsc.decode(empty, max_symbols=0), b"")
        self.fails(empty + b"\0", "trailing_data")

    def test_single_symbol_and_unused_branch(self):
        depths = [0] * 512
        depths[65] = 1
        frame = _dsc_frame(depths, 3, 3, b"\0")
        self.assertEqual(bgi_dsc.decode(frame), b"AAA")
        self.fails(frame[:-1] + b"\x80", "invalid_tree")

    def test_manual_overlap_match(self):
        self.assertEqual(bgi_dsc.decode(overlap_dsc()), b"ABABABA")

    def test_match_minimum_and_maximum_length(self):
        for symbol, size in ((256, 4), (511, 259)):
            depths = [0] * 512
            depths[65], depths[66], depths[symbol] = 1, 2, 2
            frame = _dsc_frame(depths, size, 3, b"\x58\0\0")
            with self.subTest(symbol=symbol):
                self.assertEqual(bgi_dsc.decode(frame), (b"AB" * 130)[:size])

    def test_maximum_twelve_bit_distance(self):
        # Fixed depth-9 code for every symbol. 4097 A literals, then symbol
        # 256 (length 2), followed by distance bits 0xfff (4097, not 4095).
        bits = "001000001" * 4097 + "100000000" + "1" * 12
        bits += "0" * (-len(bits) % 8)
        stream = int(bits, 2).to_bytes(len(bits) // 8, "big")
        frame = _dsc_frame([9] * 512, 4099, 4098, stream)
        self.assertEqual(bgi_dsc.decode(frame), b"A" * 4099)
        self.fails(_dsc_frame([9] * 512, 3, 2, b"\x20\xc0\x3f\xfc"), "invalid_backreference")

    def test_source_subtraction_not_xor(self):
        frame = literal_dsc(b"A")
        depths = bgi_dsc._depths(frame, 0x12345678)
        self.assertEqual(depths, [8] * 256 + [0] * 256)
        # Recover k from src = (8+k)&255, then make the wrong XOR table.
        table = bytearray(frame[0x20:0x220])
        wrong = [source ^ ((source - 8) & 255) for source in table[:256]]
        self.assertNotEqual(wrong, [8] * 256)
        table[:256] = bytes(8 ^ ((source - 8) & 255) for source in table[:256])
        self.fails(frame[:0x20] + table + frame[0x220:], "invalid_tree")

    def test_uint32_key_wrap_including_low_word_carry(self):
        # Multiplicative inverse makes mixed == 0xffffffff and next key == 0.
        seed = (-pow(0x015a4e35, -1, 1 << 32)) & 0xffffffff
        frame = literal_dsc(b"uint32", seed)
        self.assertEqual(frame[0x20], 7)  # (8 + 255) & 255
        self.assertEqual(frame[0x21], 8)  # key became zero
        self.assertEqual(bgi_dsc.decode(frame), b"uint32")

    def test_empty_oversubscribed_incomplete_and_extreme_trees(self):
        malformed = ([0] * 512, [1, 1, 1] + [0] * 509,
                     [2, 2] + [0] * 510, [255] + [0] * 511)
        for depths in malformed:
            with self.subTest(depths=depths[:3]):
                self.fails(_dsc_frame(depths, 1, 1, b"\0"), "invalid_tree")

    def test_valid_deep_tree_and_bit_work_limit(self):
        depths = list(range(1, 33)) + [33, 33] + [0] * 478
        frame = _dsc_frame(depths, 1, 1, b"\xff\xff\xff\xff\x80")
        self.fails(frame, "decoded_budget", max_symbols=1)
        self.assertEqual(bgi_dsc.decode(frame, max_symbols=2), bytes([33]))

    def test_truncated_signature_header_lengths_and_literal(self):
        frame = literal_dsc(b"abc")
        for end in (0, 1, 3, 14, 15, 16, 24, 31, 32, 100, 0x21f, 0x220, len(frame) - 1):
            with self.subTest(end=end):
                self.fails(frame[:end], "truncated")

    def test_truncated_match_distance_is_fatal(self):
        self.fails(overlap_dsc()[:-1], "truncated")

    def test_unsupported_version_and_input_type(self):
        self.fails(literal_dsc(b"x").replace(b"1.00", b"2.00", 1), "unsupported_codec")
        self.fails(b"BSE 1." + b"\0" * 600, "unsupported_codec")
        for value in (None, "text", bytearray(literal_dsc(b"x"))):
            with self.subTest(type=type(value)):
                self.fails(value, "input_type")

    def test_output_underflow_overflow_and_count_mismatch(self):
        frame = literal_dsc(b"abc")
        for offset, value in ((0x14, 2), (0x14, 4), (0x18, 0), (0x18, 2), (0x18, 4)):
            with self.subTest(offset=offset, value=value):
                self.fails(_u32(frame, offset, value), "length_mismatch")
        self.fails(_u32(overlap_dsc(), 0x14, 6), "length_mismatch")
        self.fails(_u32(overlap_dsc(), 0x14, 8), "length_mismatch")
        self.fails(_u32(literal_dsc(b"A"), 0x14, 258), "length_mismatch")

    def test_backreference_before_start(self):
        depths = [0] * 512
        depths[65], depths[66], depths[259] = 1, 2, 2
        self.fails(_dsc_frame(depths, 5, 1, b"\xc0\0"), "invalid_backreference")
        # Existing AB prefix but distance=3, while only two bytes exist.
        self.fails(overlap_dsc()[:-1] + b"\x80", "invalid_backreference")

    def test_only_zero_bits_to_byte_boundary_are_padding(self):
        frame = overlap_dsc()
        self.assertEqual(bgi_dsc.decode(frame), b"ABABABA")
        self.fails(frame[:-1] + b"\x01", "trailing_data")
        for trailer in (b"\0", b"\0\0\0", b"junk", b"\xff"):
            self.fails(frame + trailer, "trailing_data")
        self.fails(literal_dsc(b"abc") + b"\0", "trailing_data")

    def test_budgets_are_checked_before_invalid_tree_or_allocation(self):
        frame = literal_dsc(b"abc")
        self.fails(frame, "decoded_budget", max_output_size=2)
        self.fails(frame, "decoded_budget", max_symbols=2)
        self.fails(_u32(frame, 0x14, 0xffffffff), "decoded_budget")
        self.fails(_u32(frame, 0x18, 0xffffffff), "decoded_budget")
        with patch.object(bgi_dsc, "MAX_INPUT_SIZE", len(frame) - 1):
            self.fails(frame, "stored_budget")
        self.assertEqual(bgi_dsc.decode(frame, max_output_size=3, max_symbols=3), b"abc")

    def test_invalid_limits(self):
        for kwargs in ({"max_output_size": -1}, {"max_symbols": -1},
                       {"max_symbols": 1.5}, {"max_output_size": True}):
            with self.subTest(kwargs=kwargs):
                self.fails(literal_dsc(b""), "invalid_limit", **kwargs)

    def test_decode_member_is_explicit_and_preserves_legacy_opacity(self):
        frame = literal_dsc(b"not necessarily a script\0")
        entry = bgi.inspect(pack_archive([("a", frame)]))[0]
        self.assertEqual(entry.stored_data, frame)
        self.assertEqual(bgi.decode_member(entry), b"not necessarily a script\0")
        with self.assertRaises(ValueError):
            bgi.require_plain(entry)
        with self.assertRaises(bgi.BgiArchiveError) as caught:
            bgi.decode_member(replace(entry, unpacked_size=100))
        self.assertEqual(caught.exception.code, "length_mismatch")

    def test_raw_budget_and_metadata_validation(self):
        payload = b"binary\0\xff"
        entry = bgi.Entry("a", payload, 100, "raw", len(payload))
        self.assertIs(bgi.decode_member(entry), payload)
        for bad, limits, code in ((entry, {"max_output_size": 1}, "decoded_budget"),
                                  (replace(entry, unpacked_size=0), {}, "length_mismatch"),
                                  (replace(entry, stored_data="x"), {}, "input_type")):
            with self.assertRaises(bgi.BgiArchiveError) as caught:
                bgi.decode_member(bad, **limits)
            self.assertEqual(caught.exception.code, code)

    def test_bse_image_and_unknown_codecs_stay_unsupported(self):
        for codec in ("bse", "compressedbg-image", "unknown"):
            entry = bgi.Entry("a", b"bytes", 0, codec, None)
            with self.assertRaises(bgi.BgiArchiveError) as caught:
                bgi.decode_member(entry)
            self.assertEqual(caught.exception.code, "unsupported_codec")
            with self.assertRaises(ValueError):
                bgi.require_plain(entry)
        # DSC unwraps exactly one layer, not BSE or image decoding.
        inner = b"BSE 1." + b"\0" * 80
        frame = literal_dsc(inner)
        self.assertEqual(bgi.decode_member(bgi.Entry("a", frame, 0, "dsc", len(inner))), inner)


class EncoderTests(unittest.TestCase):
    """The writer must only be trusted where the strict reader accepts it."""

    def payloads(self):
        rng = random.Random(20261001)
        return {
            "empty": b"",
            "one-byte": b"\0",
            "two-bytes": b"ab",
            "single-run": b"A" * 6000,
            "alternating": b"abcabc" * 900,
            "all-byte-values": bytes(range(256)) * 40,
            "incompressible": bytes(rng.randrange(256) for _ in range(70000)),
            "cp932-text": ("こんにちは、世界。テスト" * 700).encode("cp932"),
            "nul-heavy": b"\0" * 5000 + b"x" + b"\0" * 5000,
            "max-length-run": b"\xff" * 300,
        }

    def test_round_trip_across_payloads_and_seeds(self):
        for name, payload in self.payloads().items():
            for seed in (0, 1, 0x12345678, 0xFFFFFFFF):
                with self.subTest(payload=name, seed=hex(seed)):
                    member = bgi_dsc.encode(payload, seed=seed)
                    self.assertEqual(bgi_dsc.decode(member), payload)

    def test_member_layout_is_the_documented_frame(self):
        payload = b"layout check" * 60
        member = bgi_dsc.encode(payload, seed=0x0BADF00D)
        self.assertTrue(member.startswith(bgi_dsc.MAGIC))
        seed, size, symbols, reserved = struct.unpack_from("<4I", member, 0x10)
        self.assertEqual((seed, size, reserved), (0x0BADF00D, len(payload), 0))
        self.assertLessEqual(symbols, len(payload))
        self.assertLessEqual(len(payload), symbols * 257)
        self.assertGreaterEqual(len(member), 0x220)
        self.assertEqual(_u32(member, 0x10, seed), member)
        self.assertEqual(bgi_dsc.decode(member, max_output_size=len(payload),
                                        max_symbols=symbols), payload)

    def test_deterministic_and_seed_independent_decoding(self):
        payload = b"deterministic payload" * 50
        self.assertEqual(bgi_dsc.encode(payload), bgi_dsc.encode(payload))
        self.assertEqual(bgi_dsc.encode_dsc(payload), bgi_dsc.encode(payload))
        layouts = {bgi_dsc.encode(payload, seed=seed)[0x20:0x220] for seed in (1, 2, 3)}
        self.assertEqual(len(layouts), 3)  # A different seed masks the lengths differently.

    def test_output_is_accepted_by_the_member_reader(self):
        payload = b"script body" * 30
        member = bgi_dsc.encode(payload)
        entry = bgi.Entry("m", member, 0, "dsc", len(payload))
        self.assertEqual(bgi.decode_member(entry), payload)
        self.assertEqual(bgi_dsc.decode_dsc(member), payload)

    def test_single_symbol_and_short_payloads_use_supported_codes(self):
        # Distance 1 is unrepresentable, so runs must still decode exactly.
        for payload in (b"A", b"AA", b"AAA", b"A" * 257, b"A" * 258):
            with self.subTest(length=len(payload)):
                self.assertEqual(bgi_dsc.decode(bgi_dsc.encode(payload)), payload)

    def test_limits_types_and_seed_are_enforced(self):
        payload = b"budget" * 100
        with self.assertRaises(bgi.BgiArchiveError) as caught:
            bgi_dsc.encode(payload, max_output_size=len(payload) - 1)
        self.assertEqual((caught.exception.code, caught.exception.stage),
                         ("decoded_budget", "encode"))
        for kwargs in ({"max_symbols": 0}, {"max_symbols": -1}, {"max_output_size": 0}):
            with self.subTest(**kwargs):
                with self.assertRaises(bgi.BgiArchiveError):
                    bgi_dsc.encode(payload, **kwargs)
        for seed in (-1, 1 << 32, "x", True):
            with self.subTest(seed=seed):
                with self.assertRaises(bgi.BgiArchiveError) as caught:
                    bgi_dsc.encode(payload, seed=seed)
                self.assertEqual(caught.exception.code, "invalid_seed")
        with self.assertRaises(bgi.BgiArchiveError):
            bgi_dsc.encode(bytearray(payload))

    def test_verify_false_still_produces_a_decodable_member(self):
        payload = b"unverified" * 200
        member = bgi_dsc.encode(payload, verify=False)
        self.assertEqual(bgi_dsc.decode(member), payload)

    def test_encoder_output_is_not_accepted_when_a_tree_byte_is_damaged(self):
        member = bytearray(bgi_dsc.encode(b"damage me" * 40))
        member[0x40] ^= 0x01
        with self.assertRaises(bgi.BgiArchiveError):
            bgi_dsc.decode(bytes(member))

    def test_compression_is_bounded_and_not_silently_expanding_for_scripts(self):
        payload = b"message body line\r\n" * 500
        member = bgi_dsc.encode(payload)
        self.assertLess(len(member), len(payload))
        # A member shorter than the 0x220 frame bound has no decodable tree.
        with self.assertRaises(bgi.BgiArchiveError):
            bgi_dsc.decode(member[:0x100])


class BudgetDefaultTests(unittest.TestCase):
    """The symbol cap must never be tighter than the output cap it guards.

    A DSC symbol emits at least one byte and the decoder already enforces
    symbol_count <= output_size, so a smaller symbol cap cannot protect memory -
    it can only turn a member the output cap would have accepted into a
    spurious "budget exceeded, not processed" result for batch callers.
    """

    def test_decoder_defaults_never_make_the_symbol_cap_the_tighter_one(self):
        for function in (bgi_dsc.decode, bgi_dsc.encode, bgi.decode_member):
            parameters = inspect.signature(function).parameters
            with self.subTest(function=function.__name__):
                self.assertGreaterEqual(parameters["max_symbols"].default,
                                        parameters["max_output_size"].default,
                                        function.__name__)

    def test_tighter_symbol_cap_rejects_members_the_output_cap_allows(self):
        payload = b"Q" * 120_000
        frame = literal_dsc(payload)  # one literal per byte: symbols == bytes
        self.assertEqual(bgi_dsc.decode(frame, max_output_size=200_000,
                                        max_symbols=200_000), payload)
        with self.assertRaises(bgi.BgiArchiveError) as caught:
            bgi_dsc.decode(frame, max_output_size=200_000, max_symbols=100_000)
        self.assertEqual(caught.exception.code, "decoded_budget")
        self.assertEqual(caught.exception.stage, "decode")

    def test_member_decoder_carries_the_same_contract(self):
        payload = b"R" * 120_000
        entry = bgi.Entry("m", literal_dsc(payload), 0, "dsc", len(payload))
        self.assertEqual(bgi.decode_member(entry, max_output_size=200_000,
                                           max_symbols=200_000), payload)
        with self.assertRaises(bgi.BgiArchiveError) as caught:
            bgi.decode_member(entry, max_output_size=200_000, max_symbols=100_000)
        self.assertEqual(caught.exception.code, "decoded_budget")


if __name__ == "__main__":
    unittest.main()
