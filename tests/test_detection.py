import itertools
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

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
            self.assertEqual(limited["truncated_reason"], ["max_files"])
            self.assertEqual(limited["files_seen"], 1)
            self.assertEqual(report["truncated_reason"], [])

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
                             {"total_hits": 20, "shown_hits": 12, "matched_files": 20, "capped": True,
                              "by_strength": {"probe": 20}})
            complete = detect_directory(root, max_evidence=25)
            self.assertFalse(complete["evidence_capped"])
            self.assertEqual(complete["candidate_stats"]["bgi"]["shown_hits"], 20)

    def test_unique_file_count_differs_from_evidence_count(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "scene.asb").write_bytes(b"ASB\0\0" + bytes(40))
            report = detect_directory(root, max_evidence=0)
            self.assertEqual(report["candidate_stats"]["artemis"],
                             {"total_hits": 2, "shown_hits": 0, "matched_files": 1, "capped": True,
                              "by_strength": {"probe": 1, "extension": 1}})
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
            self.assertEqual(report["truncated_reason"], ["max_depth"])
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


def _pe(machine: int) -> bytes:
    head = bytearray(0x80)
    head[:2] = b"MZ"
    struct.pack_into("<I", head, 0x3C, 0x40)
    head[0x40:0x44] = b"PE\0\0"
    struct.pack_into("<H", head, 0x44, machine)
    return bytes(head)


def _bgi_arc(members: dict) -> bytes:
    table, payload = bytearray(), bytearray()
    for name, data in members.items():
        row = bytearray(0x80)
        row[:len(name)] = name.encode("cp932")
        struct.pack_into("<II", row, 0x60, len(payload), len(data))
        table += row
        payload += data
    return b"BURIKO ARC20" + struct.pack("<I", len(members)) + bytes(table) + bytes(payload)


def _unity_serialized(version: int, unity: bytes, *, size_delta: int = 0) -> bytes:
    body = bytearray(256)
    if version >= 22:
        struct.pack_into(">I", body, 8, version)
        struct.pack_into(">IQQ", body, 20, 64, len(body) + size_delta, 128)
        body[48:48 + len(unity) + 1] = unity + b"\0"
    else:
        struct.pack_into(">4I", body, 0, 64, len(body) + size_delta, version, 128)
        body[20:20 + len(unity) + 1] = unity + b"\0"
    return bytes(body)


class DetectionAdditionsTests(unittest.TestCase):
    NOTE = "可能是已有补丁或旧实验产物，确认原版来源后再提取"

    def test_existing_patch_hints(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "winmm.dll").write_bytes(_pe(0x14C))
            (root / "uif_config.json").write_bytes(b"{}")
            (root / "CialloHook.ini").write_bytes(b"[x]")
            (root / "jis-mapping.json").write_bytes(b"{}")
            (root / "game.exe.org").write_bytes(b"MZ")
            (root / "data.xp3.bak").write_bytes(b"x")
            for name in ("data - Copy", "游戏副本", "backup_old", "plain"):
                (root / name).mkdir()
            (root / "plain" / "version.dll").write_bytes(_pe(0x14C))   # no EXE beside it
            (root / "bin").mkdir()
            (root / "bin" / "real.exe").write_bytes(_pe(0x8664))
            (root / "bin" / "dinput8.dll").write_bytes(_pe(0x8664))
            (root / "game - 副本.exe").write_bytes(_pe(0x14C))
            archive = b"XP3\r\n \n\x1a\x8bg\x01" + bytes(100_000)
            (root / "data.xp3").write_bytes(archive)
            (root / "plain" / "data.xp3").write_bytes(archive)
            (root / "voice.xp3").write_bytes(b"XP3\r\n \n\x1a\x8bg\x01" + b"\x01" * 100_000)
            report = detect_directory(root)
            hints = report["existing_patch_hints"]
            self.assertTrue(all(hint["note"] == self.NOTE for hint in hints))
            by_kind = {}
            for hint in hints:
                by_kind.setdefault(hint["kind"], []).append(hint)
            self.assertEqual(sorted((h["file"], h["machine"]) for h in by_kind["hook-dll"]),
                             [("bin/dinput8.dll", "x64"), ("winmm.dll", "x86")])
            self.assertEqual([h["file"] for h in by_kind["copy-named-file"]], ["game - 副本.exe"])
            self.assertEqual({h["file"] for h in by_kind["patch-config"]},
                             {"uif_config.json", "CialloHook.ini", "jis-mapping.json"})
            self.assertEqual({h["file"] for h in by_kind["backup-file"]}, {"game.exe.org", "data.xp3.bak"})
            self.assertEqual({h["directory"] for h in by_kind["copy-named-directory"]},
                             {"data - Copy", "游戏副本", "backup_old"})
            self.assertEqual([sorted(h["files"]) for h in by_kind["duplicate-archive"]],
                             [["data.xp3", "plain/data.xp3"]])
            self.assertNotIn("duplicate-check-capped", by_kind)

    def test_clean_directory_has_no_patch_hints(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "game.exe").write_bytes(_pe(0x8664))
            (root / "data.xp3").write_bytes(b"XP3\r\n \n\x1a\x8bg\x01" + bytes(100_000))
            (root / "bgm.xp3").write_bytes(b"XP3\r\n \n\x1a\x8bg\x01" + b"\x02" * 100_001)
            report = detect_directory(root)
            self.assertEqual(report["existing_patch_hints"], [])
            self.assertEqual(report["executables"], [{"file": "game.exe", "machine": "x64"}])

    def test_bgi_loose_override_and_encoding(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "data01000.arc").write_bytes(_bgi_arc({"start": b"A" * 40, "flow": b"B" * 40,
                                                            "inside": b"C" * 40}))
            (root / "start").write_bytes("BurikoCompiledScriptVer1.00\0这是中文\0译文\0".encode("utf-8"))
            japanese = b"\x01\x02\0" + b"\0".join("日本語の台詞です".encode("cp932") for _ in range(4)) + b"\0\xff"
            (root / "flow").write_bytes(japanese)
            report = detect_directory(root)
            hints = [h for h in report["existing_patch_hints"] if h["kind"] == "bgi-loose-override"]
            self.assertEqual(len(hints), 1)
            hint = hints[0]
            self.assertEqual(hint["archive"], "data01000.arc")
            self.assertEqual(hint["count"], 2)
            encodings = {item["member"]: item["encoding"] for item in hint["files"]}
            self.assertEqual(encodings, {"start": "utf-8", "flow": "cp932-compatible-strings"})
            self.assertEqual(hint["summary"], "疑似 UTF-8 汉化覆盖")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "data01000.arc").write_bytes(_bgi_arc({"start": b"A" * 40}))
            (root / "flow").write_bytes(b"unrelated")
            report = detect_directory(root)
            self.assertFalse(any(h["kind"] == "bgi-loose-override" for h in report["existing_patch_hints"]))

    def test_strong_evidence_survives_many_extension_hits(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for number in range(40):
                (root / f"{number:02}.fpk").write_bytes(bytes(40))
            (root / "SystemC.ini").write_bytes(b"[x]\n")
            report = detect_directory(root)
            hits = report["candidates"]["systemc"]
            self.assertEqual(hits[0]["file"], "SystemC.ini")
            self.assertEqual(hits[0]["strength"], "filename")
            self.assertEqual(len(hits), 12)
            self.assertEqual(report["candidate_stats"]["systemc"]["by_strength"],
                             {"filename": 1, "extension": 40})
            (root / "z.ypf").write_bytes(b"YPF\0" + struct.pack("<III", 0x1E2, 3, 100) + bytes(40))
            for number in range(20):
                (root / f"{number:02}.ybn").write_bytes(bytes(8))
            (root / "ysc.ybn").write_bytes(bytes(8))
            tight = detect_directory(root, max_evidence=1)
            strengths = [hit["strength"] for hit in tight["candidates"]["yuris"]]
            self.assertEqual(strengths, ["probe", "filename", "extension"])

    def test_bfs_prefers_common_game_folders_and_reports_reason(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plugin = root / "aaa_plugins" / "deep"
            plugin.mkdir(parents=True)
            for number in range(10):
                (root / "aaa_plugins" / f"p{number}.js").write_bytes(b"x")
                (plugin / f"q{number}.js").write_bytes(b"x")
            (root / "data").mkdir()
            (root / "data" / "script.xp3").write_bytes(b"XP3\r\n \n\x1a\x8bg\x01" + bytes(20))
            report = detect_directory(root, max_files=3)
            self.assertIn("kirikiri", report["candidates"])
            self.assertEqual(report["truncated_reason"], ["max_files"])
            ticks = itertools.count(0, 10.0)
            with mock.patch("python.detect.time.monotonic", lambda: next(ticks)):
                slow = detect_directory(root, max_seconds=5.0)
            self.assertTrue(slow["truncated"])
            self.assertEqual(slow["truncated_reason"], ["max_seconds"])

    def test_pe_machine_is_shallow_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "a32.exe").write_bytes(_pe(0x14C))
            (root / "b64.exe").write_bytes(_pe(0x8664))
            (root / "c.exe").write_bytes(b"not a program")
            deep = root / "a" / "b" / "c"
            deep.mkdir(parents=True)
            (root / "a" / "d.exe").write_bytes(_pe(0x14C))
            (deep / "e.exe").write_bytes(_pe(0x14C))      # below EXECUTABLE_MAX_DEPTH
            report = detect_directory(root)
            self.assertEqual(sorted((e["file"], e["machine"]) for e in report["executables"]),
                             [("a/d.exe", "x86"), ("a32.exe", "x86"), ("b64.exe", "x64"), ("c.exe", "not-pe")])

    def test_version_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "bn.ypf").write_bytes(b"YPF\0" + struct.pack("<III", 0x1E2, 3, 100) + bytes(40))
            (root / "old.ypf").write_bytes(b"YPF\0" + struct.pack("<III", 0xDE, 3, 100) + bytes(40))
            (root / "data.pack").write_bytes(bytes(300) + b"FilePackVer3.1\0\0" + bytes(12))
            (root / "a.rpa").write_bytes(b"RPA-2.0 0000000000000022\n" + bytes(20))
            (root / "b.rpa").write_bytes(b"ARC-3.0 0000000000000022 00000000\n" + bytes(20))
            (root / "c.rpa").write_bytes(b"RPA-3.0 0000000000000022 00000000\n" + bytes(20))
            report = detect_directory(root, max_evidence=50)
            versions = report["format_versions"]
            self.assertEqual(versions["yuris-ypf"], {"482": 1, "222": 1})
            self.assertEqual(versions["qlie-filepack"], {"3.1": 1})
            self.assertEqual(versions["renpy-rpa"], {"RPA-2.0": 1, "ARC-3.0": 1, "RPA-3.0": 1})
            ypf = {hit["file"]: hit for hit in report["candidates"]["yuris"] if hit["kind"] == "header-hint"}
            self.assertEqual(ypf["bn.ypf"]["version"], 482)
            self.assertIn("0x1E2", ypf["bn.ypf"]["evidence"])
            qlie = report["candidates"]["qlie"][0]
            self.assertEqual(qlie["version"], "3.1")
            self.assertIn("FilePackVer3.1", qlie["evidence"])

    def test_entis_noa_is_not_csx(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "data.noa").write_bytes(b"Entis\x1a\0\0" + bytes(8) + b"ERISA-Archive file" + bytes(40))
            (root / "s.csx").write_bytes(b"Entis\x1a\0\0" + bytes(8) + b"Cotopha Image file" + bytes(40))
            (root / "x.dat").write_bytes(b"Entis\x1a\0\0" + bytes(8) + b"Something else" + bytes(40))
            (root / "readme.dat").write_bytes(b"Entis is a word in text, not a header at all......")
            report = detect_directory(root)
            hits = {hit["file"]: hit for hit in report["candidates"]["entis-gls"]}
            self.assertEqual(hits["data.noa"]["subtype"], "noa")
            self.assertIn("NOA", hits["data.noa"]["evidence"])
            self.assertNotIn("CSX", hits["data.noa"]["evidence"])
            self.assertEqual(hits["s.csx"]["subtype"], "csx")
            self.assertEqual(hits["x.dat"]["subtype"], "other")
            self.assertNotIn("readme.dat", hits)
            self.assertEqual(report["format_versions"]["entis"], {"noa": 1, "csx": 1, "other": 1})

    def test_unity_backend_and_versions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            managed = root / "Bin" / "Game_Data" / "Managed"
            managed.mkdir(parents=True)
            (managed / "Assembly-CSharp.dll").write_bytes(b"MZ")
            (root / "Game_Data").mkdir()
            (root / "Game_Data" / "globalgamemanagers").write_bytes(_unity_serialized(22, b"2021.3.5f1"))
            (root / "Game_Data" / "resources.assets").write_bytes(_unity_serialized(17, b"5.6.7f1"))
            (root / "Game_Data" / "broken.assets").write_bytes(_unity_serialized(17, b"5.6.7f1", size_delta=4))
            (root / "data.unity3d").write_bytes(b"UnityFS\0" + struct.pack(">I", 7) + b"5.x.x\0"
                                                + b"2019.4.1f1\0" + bytes(40))
            report = detect_directory(root, max_evidence=50)
            self.assertEqual(report["unity"]["scripting_backend"], "mono")
            self.assertEqual(report["format_versions"]["unity-serialized"], {"22": 1, "17": 1})
            self.assertEqual(report["format_versions"]["unityfs"], {"7": 1})
            hits = {hit["file"]: hit for hit in report["candidates"]["unity"] if hit["kind"] == "header-hint"}
            self.assertEqual(hits["Game_Data/globalgamemanagers"]["unity_version"], "2021.3.5f1")
            self.assertEqual(hits["data.unity3d"]["unity_version"], "2019.4.1f1")
            self.assertNotIn("Game_Data/broken.assets", hits)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "GameAssembly.dll").write_bytes(b"MZ")
            (root / "Game_Data" / "il2cpp_data").mkdir(parents=True)
            report = detect_directory(root)
            self.assertEqual(report["unity"]["scripting_backend"], "il2cpp")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "Game_Data" / "Managed").mkdir(parents=True)
            (root / "Game_Data" / "Managed" / "Other.dll").write_bytes(b"MZ")
            report = detect_directory(root)
            self.assertIsNone(report["unity"])


if __name__ == "__main__":
    unittest.main()
