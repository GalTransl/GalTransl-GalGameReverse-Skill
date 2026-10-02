from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from python.detect import detect_directory


class DetectionTests(unittest.TestCase):
    def test_conflicts_and_header_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "scene.asb").write_bytes(b"ASB\0\0" + bytes(40))
            (root / "unknown.bin").write_bytes(b"not a known format")
            before = (root / "scene.asb").read_bytes()
            report = detect_directory(root)
            self.assertEqual(report["kind"], "candidate-evidence-only")
            self.assertIn("artemis", report["candidates"])
            self.assertIn("azsystem", report["candidates"])
            self.assertTrue(any(hit["kind"] == "header-hint" for hit in report["candidates"]["artemis"]))
            self.assertTrue(all(hit["kind"] == "weak-extension" for hit in report["candidates"]["azsystem"]))
            self.assertEqual((root / "scene.asb").read_bytes(), before)
            self.assertEqual(len(list(root.iterdir())), 2)

    def test_limits_and_footer(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "a.pack").write_bytes(bytes(300) + b"FilePackVer3.1" + bytes(10))
            (root / "b.rpyc").write_bytes(bytes(20))
            report = detect_directory(root)
            self.assertIn("qlie", report["candidates"])
            self.assertIn("renpy", report["candidates"])
            limited = detect_directory(root, max_files=1)
            self.assertTrue(limited["truncated"])
            self.assertEqual(limited["files_seen"], 1)

    def test_small_qlie_footer_is_not_missed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "small.pack").write_bytes(bytes(40) + b"FilePackVer3.1" + bytes(10))
            report = detect_directory(root)
            self.assertIn("qlie", report["candidates"])
            self.assertFalse(report["truncated"])

    def test_evidence_cap_is_separate_from_scan_truncation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for number in range(20):
                (root / f"bundle-{number:02}.arc").write_bytes(b"BURIKO ARC20" + bytes(40))
            report = detect_directory(root)
            self.assertFalse(report["truncated"])
            self.assertTrue(report["evidence_capped"])
            self.assertEqual(len(report["candidates"]["bgi"]), 12)
            self.assertEqual(report["candidate_stats"]["bgi"],
                             {"total_hits": 20, "shown_hits": 12, "matched_files": 20, "capped": True})
            complete = detect_directory(root, max_evidence=25)
            self.assertFalse(complete["evidence_capped"])
            self.assertEqual(complete["candidate_stats"]["bgi"]["shown_hits"], 20)

    def test_unique_file_count_differs_from_evidence_count(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "scene.asb").write_bytes(b"ASB\0\0" + bytes(40))
            report = detect_directory(root, max_evidence=0)
            self.assertEqual(report["candidate_stats"]["artemis"],
                             {"total_hits": 2, "shown_hits": 0, "matched_files": 1, "capped": True})
            self.assertEqual(report["candidates"]["artemis"], [])
            self.assertFalse(report["truncated"])
            with self.assertRaises(ValueError):
                detect_directory(root, max_evidence=-1)

    def test_dsc_header_is_wrapper_evidence_not_script_success(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "animation").write_bytes(b"DSC FORMAT 1.00\0" + bytes(40))
            report = detect_directory(root)
            hits = report["candidates"]["bgi"]
            self.assertEqual(len(hits), 1)
            self.assertIn("wrapper", hits[0]["evidence"])
            self.assertIn("animation", hits[0]["evidence"])
            self.assertEqual(report["candidate_stats"]["bgi"]["matched_files"], 1)

    def test_unknown_and_depth(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "plain.bin").write_bytes(bytes(20))
            report = detect_directory(root)
            self.assertEqual(report["candidates"], {})
            subdir = root / "subdir"
            subdir.mkdir()
            (subdir / "nscript.dat").write_bytes(b"fixture")
            report = detect_directory(root, max_depth=0)
            self.assertTrue(report["truncated"])
            self.assertNotIn("nscripter", report["candidates"])


if __name__ == "__main__":
    unittest.main()
