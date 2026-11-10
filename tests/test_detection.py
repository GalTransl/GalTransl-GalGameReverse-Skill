import json
import os
from pathlib import Path
import struct
import subprocess
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


    def test_derived_directories_are_skipped_unless_requested(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "data.xp3").write_bytes(b"XP3\r\n \n\x1a\x8bg\x01" + bytes(20))
            derived = ("Game_extract", "Game_extract_2", "Game_extract_pack_20260101", "KrkrExtract_Output")
            for name in derived:
                (root / name).mkdir()
                (root / name / "scene.ks").write_bytes(b"fixture")
            workspace = root / "renamed"
            for child in ("gt_input", "reports"):
                (workspace / child).mkdir(parents=True)
            (workspace / "gt_input" / "a.ks").write_bytes(b"fixture")
            packed = root / "deliver"
            packed.mkdir()
            (packed / "verification.json").write_bytes(b"{}")
            (packed / "c.ks").write_bytes(b"fixture")
            # Ordinary folders ending in "_output" (media plugins) and a plain
            # gt_output must still be scanned.
            for name in ("gt_output", "audio_output"):
                (root / name).mkdir()
                (root / name / "b.ks").write_bytes(b"fixture")
            report = detect_directory(root)
            skipped = {item["directory"] for item in report["skipped_directories"]}
            self.assertEqual(skipped, set(derived) | {"renamed", "deliver"})
            self.assertEqual(report["skipped_directory_count"], 6)
            files = {hit["file"] for hit in report["candidates"]["kirikiri"]}
            self.assertEqual(files, {"data.xp3", "gt_output/b.ks", "audio_output/b.ks"})
            full = detect_directory(root, include_derived=True)
            self.assertEqual(full["skipped_directories"], [])
            self.assertEqual(full["candidate_stats"]["kirikiri"]["matched_files"], 9)
            # The scanned root itself is never skipped, whatever its name.
            inner = detect_directory(root / "Game_extract")
            self.assertIn("kirikiri", inner["candidates"])

    def test_txt_noise_is_not_scp(self):
        noise = {
            "README.txt": ("=" * 60 + "\n   Voice release\n\n" + "*" * 60 + "\n   Copying\n" + "*" * 60
                           + "\n# " + "-" * 50 + " #\nSome text here.\nMore text.\n" * 40),
            "strings.txt": "[000000]滑条限制 (WIDESLIDER)[-]\t[000000]x\n" * 60,
            "Copyright.txt": "Copyright (c) 2015 Example.\nAll rights reserved.\n* Redistribution ...\n" * 40,
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, text in noise.items():
                (root / name).write_text(text, encoding="utf-8")
            report = detect_directory(root)
            self.assertNotIn("artemis-scp", report["candidates"])

    def test_engine_layout_and_header_rules(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "Script.pac").write_bytes(b"PAC\x7f" + struct.pack("<II", 158, 7) + bytes(40))
            (root / "bad.pac").write_bytes(b"PAC\x00" + struct.pack("<II", 0, 7) + bytes(40))
            (root / "md_scr.med").write_bytes(b"MDN0\x1c\x00\x49\x00" + bytes(40))
            (root / "md_gra.med").write_bytes(b"MDN1\x1b\x00" + bytes(40))
            (root / "SystemC.ini").write_bytes(b"[x]\n")
            (root / "00.fpk").write_bytes(bytes(40))
            (root / "EAGLS.dll").write_bytes(b"MZ" + bytes(40))
            (root / "SCPACK.idx").write_bytes(bytes(40))
            (root / "UnityPlayer.dll").write_bytes(b"MZ" + bytes(40))
            (root / "data.unity3d").write_bytes(b"UnityFS\0" + bytes(40))
            (root / "kag.parser.js").write_bytes(b"tyrano")
            report = detect_directory(root, max_evidence=50)
            files = lambda engine: {hit["file"] for hit in report["candidates"].get(engine, [])}
            self.assertEqual(files("nexas"), {"Script.pac"})
            self.assertEqual(files("med"), {"md_scr.med", "md_gra.med"})
            self.assertTrue(any("only plain MDN0" in hit["evidence"] for hit in report["candidates"]["med"]
                                if hit["file"] == "md_gra.med"))
            self.assertEqual(files("systemc"), {"SystemC.ini", "00.fpk"})
            self.assertEqual(files("eagls"), {"EAGLS.dll", "SCPACK.idx"})
            self.assertEqual(files("unity"), {"UnityPlayer.dll", "data.unity3d"})
            self.assertEqual(files("tyrano"), {"kag.parser.js"})

    @staticmethod
    def _asar(tree):
        body = json.dumps(tree, separators=(",", ":")).encode("utf-8")
        padded = body + bytes(-len(body) % 4)
        return struct.pack("<4I", 4, len(padded) + 8, len(padded) + 4, len(body)) + padded + b"payload"

    def test_asar_tyrano_layout_and_plain_electron(self):
        tyrano = {"files": {"tyrano": {"files": {"libs.js": {"size": 1, "offset": "0"}}},
                            "data": {"files": {"scenario": {"files": {
                                "first.ks": {"size": 1, "offset": "1"}}}}}}}
        plain = {"files": {"index.html": {"size": 1, "offset": "0"}}}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "resources").mkdir()
            (root / "resources" / "app.asar").write_bytes(self._asar(tyrano))
            other = root / "other"
            other.mkdir()
            (other / "app.asar").write_bytes(self._asar(plain))
            report = detect_directory(root, max_evidence=50)
            hits = {hit["file"]: hit for hit in report["candidates"]["tyrano"]}
            self.assertEqual(hits["resources/app.asar"]["kind"], "header-hint")
            self.assertIn("TyranoScript layout", hits["resources/app.asar"]["evidence"])
            self.assertIn("only Electron asar", hits["other/app.asar"]["evidence"])
            self.assertEqual(report["catalog_hints"], [])

    def test_ks_extension_names_both_kag_engines(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "first.ks").write_bytes(b"*start\n")
            report = detect_directory(root)
            self.assertIn("kirikiri", report["candidates"])
            self.assertIn("tyrano", report["candidates"])

    def test_catalog_magic_fallback_skips_known_and_generic_heads(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "iris.dat").write_bytes(b"IRIS" + bytes(40))      # catalog-only magic
            (root / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n" + bytes(40))
            (root / "app.exe").write_bytes(b"MZ\x90\x00" + bytes(40))
            (root / "redist.cab").write_bytes(b"MSCF" + bytes(40))
            (root / "chrome_100_percent.pak").write_bytes(b"\x05\x00\x00\x00\x01\x00\x00\x00" + bytes(40))
            (root / "data.xp3").write_bytes(b"XP3\r\n \n\x1a\x8bg\x01" + bytes(20))
            report = detect_directory(root)
            files = {hint["file"] for hint in report["catalog_hints"]}
            self.assertEqual(files, {"iris.dat"})
            hint = report["catalog_hints"][0]
            self.assertEqual(hint["kind"], "catalog-magic")
            self.assertIn("DAT/IRIS", hint["tags"])
            self.assertLessEqual(len(hint["tags"]), 5)
            self.assertEqual(report["catalog_hint_stats"]["total_hits"], 1)

    def test_cli_writes_utf8_under_isolated_mode(self):
        script = Path(__file__).resolve().parents[1] / "python" / "detect.py"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "ゲーム目录"
            root.mkdir()
            (root / "剧本データ.xp3").write_bytes(b"XP3\r\n \n\x1a\x8bg\x01" + bytes(20))
            env = {key: value for key, value in os.environ.items()
                   if key not in ("PYTHONIOENCODING", "PYTHONUTF8")}
            completed = subprocess.run([sys.executable, "-I", str(script), str(root)],
                                       capture_output=True, env=env, timeout=120, cwd=temp)
            self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8", "replace"))
            report = json.loads(completed.stdout.decode("utf-8"))
            self.assertEqual(report["candidates"]["kirikiri"][0]["file"], "剧本データ.xp3")
            refused = subprocess.run([sys.executable, "-I", str(script), str(root / "缺失")],
                                     capture_output=True, env=env, timeout=120, cwd=temp)
            self.assertEqual(refused.returncode, 2)
            self.assertIn("scan refused", refused.stderr.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
