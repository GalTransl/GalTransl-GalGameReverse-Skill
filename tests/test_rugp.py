"""Artificial rUGP fixtures; no commercial bytecode or game execution."""

from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from python.archives import rugp as archive
from python.common.binary import FormatError
from python.detect import detect_directory
from python.engines.rugp import AnalysisLimits, analyze_archive, inspect_literals


# Frozen against upstream encrypt_block at the version in provenance/rugp-sources.json.
# Plaintext is bytes(range(size)); these vectors do not depend on our encoder.
VECTORS = {
    0: "74a9d1368f562ec9",
    1: "75a9d13687562ec9e2",
    31: "6ba9d13677562ec9e270568e18fb3cc6bbd99f0013fa46aafc4f6851a6c4821a04e723d8b3c598",
    32: "54a9d1368f572ec9e270568e18fb3cc6bbd99f0013fa46aafc4f6851a6c4821a04e723d8b3c598355015",
    33: "55a9d13687572ec9e270568e18fb3cc6bbd99f0013fa46aafc4f6851a6c4821a04e723d8b3c598355015c2",
    64: "34a9d1368f542ec9e270568e18fb3cc6bbd99f0013fa46aafc4f6851a6c4821a04e723d8b3c598355015c25076ae38db1ce69bf9bf2033da668adc6f487186e4a23a24c703f893e5b8155057",
}


def literal(raw, subop=0x1f):
    if isinstance(raw, str):
        raw = raw.encode("cp932")
    return bytes((0x60, subop, 0, len(raw))) + raw


def frame_header(size, flags=0):
    return struct.pack("<II", (~size ^ 0xC92E568B) & 0xFFFFFFFF,
                       ((size << 3) | flags) ^ 0xC92E568F)


class CodecTests(unittest.TestCase):
    def test_frozen_upstream_vectors(self):
        for size, hex_data in VECTORS.items():
            with self.subTest(size=size):
                encoded, plain = bytes.fromhex(hex_data), bytes(range(size))
                self.assertEqual(archive.decode_block(encoded).data, plain)
                self.assertEqual(archive.encrypt_block(plain), encoded)

    def test_flags_exact_boundaries_and_actual_roundtrip(self):
        for size in (0, 1, 7, 31, 32, 33, 63, 64, 65, 255, 256, 1025):
            for flags in range(8):
                with self.subTest(size=size, flags=flags):
                    plain = bytes((i * 37 + 11) & 255 for i in range(size))
                    data = archive.encrypt_block(plain, flags=flags)
                    block = archive.decode_block(b"PRE" + data + b"POST", 3)
                    self.assertEqual(block.data, plain)
                    self.assertEqual(block.header.end, 3 + len(data))
                    self.assertEqual(block.header.flags, flags)
                    self.assertEqual(block.checksum_chunks, size // 32)
                    self.assertEqual(len(data), 8 + size + 2 * (size // 32))
                    self.assertEqual(archive.encrypt_block(block.data, flags=block.header.flags), data)

    def test_variable_chinese_binary_payload_not_script_writer(self):
        # Opaque bytes survive the real frame reader/writer; no VM is inferred.
        prefix, suffix = b"\x99\x00\x01HEADER", b"END\x00\xfe\xff"
        for text in ("中文", "这是一段明显更长的中文测试内容。" * 3, "短"):
            payload = prefix + text.encode("utf-8") + suffix
            frame = archive.encrypt_block(payload, flags=6)
            decoded = archive.decode_block(frame)
            self.assertEqual(decoded.data, payload)
            self.assertTrue(decoded.data.startswith(prefix))
            self.assertTrue(decoded.data.endswith(suffix))
            self.assertEqual(archive.encrypt_block(decoded.data, flags=6), frame)

    def test_custom_keys_and_bad_key_checksum(self):
        for key in (0, 0xFFFFFFFF, archive.ICI_KEY, archive.RIO_KEY):
            data = archive.encrypt_block(bytes(range(64)), key=key)
            self.assertEqual(archive.decode_block(data, key=key).data, bytes(range(64)))
            with self.assertRaisesRegex(FormatError, "checksum"):
                archive.decode_block(data, key=key ^ 1)

    def test_short_frames_do_not_authenticate_key_or_tail(self):
        short = archive.encrypt_block(b"hello")
        self.assertEqual(archive.decode_block(short, key=archive.RIO_KEY ^ 1).checksum_chunks, 0)
        data = bytearray(archive.encrypt_block(bytes(range(33))))
        data[-1] ^= 1
        block = archive.decode_block(data)
        self.assertEqual(block.data[:32], bytes(range(32)))
        self.assertNotEqual(block.data[32], 32)

    def test_checksum_and_all_truncated_prefixes(self):
        original = archive.encrypt_block(bytes(range(65)))
        for stop in range(len(original)):
            with self.subTest(stop=stop), self.assertRaises(FormatError):
                archive.decode_block(original[:stop])
        for pos in (8, 39, 40, 41, 42, 73, 74, 75):
            bad = bytearray(original)
            bad[pos] ^= 1
            with self.subTest(pos=pos), self.assertRaisesRegex(FormatError, "checksum"):
                archive.decode_block(bad)

    def test_header_size_and_budgets_before_allocation(self):
        with self.assertRaisesRegex(FormatError, "budget"):
            archive.decode_block(frame_header(0x1FFFFFFF), max_plain_bytes=16)
        with self.assertRaisesRegex(FormatError, "truncated"):
            archive.decode_block(frame_header(100))
        with self.assertRaisesRegex(FormatError, "relation"):
            archive.decode_block(bytes(8))
        with self.assertRaisesRegex(FormatError, "budget"):
            archive.encrypt_block(bytes(17), max_plain_bytes=16)
        for bad in (-1, 0x100000000, True, "key"):
            with self.subTest(key=bad), self.assertRaises(FormatError):
                archive.encrypt_block(b"", key=bad)
        for flags in (-1, 8, True):
            with self.assertRaises(FormatError):
                archive.encrypt_block(b"", flags=flags)
        for offset in (-1, 1000, True):
            with self.assertRaises(FormatError):
                archive.decode_block(bytes.fromhex(VECTORS[32]), offset)


class ScanTests(unittest.TestCase):
    def test_every_alignment_and_cross_window_header_and_payload(self):
        plain = b"no quotes; pure ASCII." * 10
        encoded = archive.encrypt_block(plain)
        for chunk in (8, 9, 11, 16, 31, 64):
            for offset in range(chunk * 2):
                with self.subTest(chunk=chunk, offset=offset):
                    stream = io.BytesIO(b"\xff" * offset + encoded + b"\xff" * 7)
                    stream.seek(2)
                    headers = archive.scan_headers(stream, chunk_bytes=chunk)
                    self.assertEqual(stream.tell(), 2)
                    self.assertEqual([h.offset for h in headers], [offset])
                    block = archive.read_block(stream, headers[0])
                    self.assertEqual(block.data, plain)
                    self.assertEqual(stream.tell(), 2)

    def test_sort_order_empty_short_adjacent_and_phases(self):
        data, expected = bytearray(), []
        for size in (0, 1, 3, 31, 32, 33):
            data.extend(b"\xff")
            expected.append(len(data))
            data.extend(archive.encrypt_block(b"x" * size))
        found = archive.scan_headers(io.BytesIO(data), chunk_bytes=9)
        self.assertEqual([h.offset for h in found], expected)
        self.assertEqual([h.plain_size for h in found], [0, 1, 3, 31, 32, 33])

    def test_scan_only_does_not_read_large_payload_wholesale(self):
        class BoundedStream(io.BytesIO):
            def read(self, n=-1):
                if not 0 <= n <= 23:
                    raise AssertionError("unbounded payload read")
                return super().read(n)
        data = archive.encrypt_block(bytes(4096))
        found = archive.scan_headers(BoundedStream(data), chunk_bytes=16)
        self.assertEqual([h.offset for h in found], [0])

    def test_invalid_ranges_and_overlarge_candidates_are_retained(self):
        data = frame_header(0x1FFFFFFF) + b"\xff" * 3 + frame_header(100)
        headers = archive.scan_headers(io.BytesIO(data), chunk_bytes=9)
        self.assertEqual([h.offset for h in headers], [0, 11])
        for header in headers:
            with self.assertRaises(FormatError):
                archive.read_block(io.BytesIO(data), header, max_plain_bytes=32)

    def test_scan_budget_restores_position_and_no_duplicates(self):
        stream = io.BytesIO(archive.encrypt_block(b"") * 3)
        stream.seek(4)
        with self.assertRaisesRegex(FormatError, "candidate budget"):
            archive.scan_headers(stream, chunk_bytes=8, max_candidates=2)
        self.assertEqual(stream.tell(), 4)
        with self.assertRaisesRegex(FormatError, "input byte budget"):
            archive.scan_headers(stream, max_input_bytes=8)
        self.assertEqual(stream.tell(), 4)
        self.assertEqual(len(archive.scan_headers(stream, chunk_bytes=8)), 3)
        for chunk in (0, 7, True, 1 << 27):
            with self.assertRaises(FormatError):
                archive.scan_headers(stream, chunk_bytes=chunk)

    def test_selected_header_changed_or_forged_and_short_reads(self):
        data = archive.encrypt_block(b"x" * 32, flags=2)
        header = archive.parse_header(data)
        for bad in (replace(header, flags=3), replace(header, stored_size=9),
                    replace(header, offset=-1), replace(header, plain_size=-1)):
            with self.assertRaises(FormatError):
                archive.read_block(io.BytesIO(data), bad)
        class ShortStream(io.BytesIO):
            def read(self, n=-1):
                return super().read(max(0, n - 1))
        with self.assertRaisesRegex(FormatError, "short read"):
            archive.scan_headers(ShortStream(data))
        with self.assertRaisesRegex(FormatError, "truncated"):
            archive.read_block(ShortStream(data), header)


class CandidateTests(unittest.TestCase):
    def test_no_dedup_or_japanese_quote_ascii_resource_filter(self):
        values = ["同じ文", "同じ文", "Hello", "0 starts here", "  空白  ", "画像.png", ""]
        data = b"\xfe".join(literal(s, 0x20) for s in values)
        rows = inspect_literals(data)
        self.assertEqual([row["text"] for row in rows], values)
        self.assertTrue(rows[-2]["resource_hint"])
        self.assertTrue(all(row["role"] == "unknown" for row in rows))
        self.assertTrue(all("name" not in row and "message" not in row for row in rows))
        self.assertEqual(len({row["offset"] for row in rows}), len(values))

    def test_controls_preserved_and_not_speaker_split(self):
        raw = "【人物甲】「文章」".encode("cp932") + b"\x03\x01\x05" + "【人物乙】「次」".encode("cp932")
        row = inspect_literals(literal(raw))[0]
        self.assertEqual(bytes.fromhex(row["raw_hex"]), raw)
        self.assertIn("\x03\x01\x05", row["text"])
        self.assertIn("\n\x01\x05", row["display_hint"])
        self.assertTrue(row["has_controls"])
        self.assertNotIn("name", row)

    def test_bad_encoding_and_truncated_candidates_have_diagnostics(self):
        for data, reason in ((literal(b"\x81"), "invalid CP932"),
                             (b"\x60\x1f\x00", "length field"),
                             (b"\x60\x1f\x00\xffA", "beyond")):
            row = inspect_literals(data)[0]
            self.assertEqual(row["status"], "blocked")
            self.assertIn(reason, row["reason"])
        rows = inspect_literals(literal(b"\x81") + b"\xff" + literal("正常"))
        self.assertEqual([r["status"] for r in rows], ["blocked", "candidate-only"])

    def test_overlap_unknown_subop_and_linefeed_not_silently_excluded(self):
        nested = literal(literal("inside", 0x0a), 0xff)
        rows = inspect_literals(nested)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["sub_op"], 255)
        self.assertTrue(rows[1]["inside_previous_candidate"])
        self.assertEqual(rows[1]["sub_op"], 10)
        self.assertEqual(inspect_literals(literal(b"0123456789"))[0]["length"], 10)

    def test_byte_and_candidate_budgets(self):
        data = literal("same") * 3
        with self.assertRaisesRegex(FormatError, "candidate budget"):
            inspect_literals(data, max_candidates=2)
        with self.assertRaisesRegex(FormatError, "analysis budget"):
            inspect_literals(data, max_bytes=len(data) - 1)
        self.assertEqual(inspect_literals(b"", max_candidates=0), [])


class WorkspaceTests(unittest.TestCase):
    def make_source(self, root):
        good = archive.encrypt_block(literal("旁白") * 4, flags=7)
        bad = bytearray(archive.encrypt_block(bytes(32)))
        bad[-1] ^= 1
        short = archive.encrypt_block(literal("Hello"))
        data = b"\xff" * 13 + good + b"\xff" + bad + b"\xff" + short + frame_header(100)
        source = root / "scenario.rio"
        source.write_bytes(data)
        return source, data

    def test_real_reader_writer_analysis_and_isolated_candidates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, original = self.make_source(root)
            output = root / "analysis"
            report = analyze_archive(source, output, limits=AnalysisLimits(chunk_bytes=11))
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(report["source_sha256"], hashlib.sha256(original).hexdigest())
            self.assertEqual(report["header_candidates"], 4)
            self.assertEqual(report["decoded_blocks"], 2)
            self.assertEqual(report["blocked_blocks"], 2)
            self.assertEqual(report["literal_candidates"], 5)
            self.assertEqual(report["status"], "candidate-only")
            self.assertEqual(report["decode_status"], "partial")
            self.assertFalse(report["runtime_verified"])
            self.assertEqual(report["script_rebuild"], "unsupported")
            self.assertFalse((output / "gt_input").exists())
            self.assertFalse((output / "gt_output").exists())
            self.assertEqual(json.loads((output / "reports/analysis.json").read_text("utf-8")), report)
            decoded = [item for item in report["members"] if item["status"] == "decoded"]
            self.assertEqual(decoded[0]["flags"], 7)
            self.assertEqual(decoded[1]["integrity"], "unverified-key")
            for member in decoded:
                frame = next((output / "original/blocks").glob(f"*{member['offset']:016x}.bin")).read_bytes()
                block = archive.decode_block(frame)
                self.assertEqual(block.data, (output / member["decoded"]).read_bytes())
                self.assertTrue(member["block_roundtrip"])
                meta = json.loads((output / member["metadata"]).read_text("utf-8"))
                self.assertFalse(meta["complete_vm_parse"])
            with self.assertRaises(FileExistsError):
                analyze_archive(source, output)
            self.assertEqual(source.read_bytes(), original)

    def test_block_and_cumulative_budget_skips_are_visible(self):
        for limits, expected in ((AnalysisLimits(max_block_bytes=8), 3),
                                  (AnalysisLimits(max_decode_bytes=8), 3)):
            with self.subTest(limits=limits), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                source, _ = self.make_source(root)
                report = analyze_archive(source, root / "analysis", limits=limits)
                self.assertEqual(report["skipped_blocks"], expected)
                self.assertEqual(report["blocked_blocks"], 1)

    def test_failed_attempt_consumes_decode_budget(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bad = bytearray(archive.encrypt_block(bytes(32)))
            bad[-1] ^= 1
            source = root / "scenario.rio"
            source.write_bytes(bad + archive.encrypt_block(bytes(32)))
            report = analyze_archive(source, root / "analysis", limits=AnalysisLimits(max_decode_bytes=32))
            self.assertEqual(report["attempted_plain_bytes"], 32)
            self.assertEqual(report["blocked_blocks"], 1)
            self.assertEqual(report["skipped_blocks"], 1)

    def test_global_budgets_publish_no_partial_tree(self):
        budgets = (AnalysisLimits(max_input_bytes=1), AnalysisLimits(max_header_candidates=1),
                   AnalysisLimits(max_literal_candidates=1), AnalysisLimits(max_output_bytes=100))
        for limits in budgets:
            with self.subTest(limits=limits), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                source, original = self.make_source(root)
                output = root / "analysis"
                with self.assertRaises(FormatError):
                    analyze_archive(source, output, limits=limits)
                self.assertFalse(output.exists())
                self.assertEqual(source.read_bytes(), original)

    def test_empty_archive_is_not_claimed_as_extracted(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "empty.rio"
            source.write_bytes(b"")
            report = analyze_archive(source, root / "analysis")
            self.assertEqual(report["decoded_blocks"], 0)
            self.assertEqual(report["decode_status"], "no-candidates")
            self.assertEqual(report["semantic_extraction"], "unverified")
            self.assertFalse((root / "analysis/gt_input").exists())

    def test_cli_and_detection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "scenario.rio"
            source.write_bytes(b"\xcd\x32\x6e\x59" + b"\xff" + archive.encrypt_block(literal("Hello")))
            report = detect_directory(root)
            self.assertIn("rugp", report["candidates"])
            self.assertTrue(any(r["kind"] == "header-hint" for r in report["candidates"]["rugp"]))
            result = subprocess.run([sys.executable, "-m", "python.engines.rugp", str(source),
                                     "-o", str(root / "analysis")], capture_output=True, text=True,
                                    cwd=Path(__file__).resolve().parents[1], check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "candidate-only")
            again = subprocess.run([sys.executable, "-m", "python.engines.rugp", str(source),
                                    "-o", str(root / "analysis")], capture_output=True, text=True,
                                   cwd=Path(__file__).resolve().parents[1], check=False)
            self.assertEqual(again.returncode, 2)


if __name__ == "__main__":
    unittest.main()
