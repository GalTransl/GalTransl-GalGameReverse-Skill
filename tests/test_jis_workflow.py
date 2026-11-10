"""Shared JSON JIS workflow against ordinary, unmodified engine writers."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from python.common.binary import FormatError
from python.common.contract import dump_rows
from python.common.jis_workflow import (HOOK_CHOICES, JisDiagnosticsError, pe_machine, preflight_translations,
                                        prepare_translations, prepare, finalize)
from python.common.jis_substitution import (CIALLOHOOK_X64_SHA256, JisSubstitution, batch_mapping_sha256,
                                            format_reserved_codepoints, parse_reserved_codepoints)
from python.common.safety import write_new_tree
from python.engines import eagls_extract
from python.engines.eagls_text import Profile
from tests.test_eagls import archive, script

ROOT = Path(__file__).resolve().parents[1]


class PlanTests(unittest.TestCase):
    def test_shared_mapping_names_and_unchanged_files(self):
        original = {"a.json": [{"names": ["A", "B"], "message": "hello$S"}],
                    "b.json": [{"message": "world"}]}
        translated = {"a.json": [{"names": ["你", "她"], "message": "这$S"}]}
        snapshot = copy.deepcopy(translated)
        plan = prepare_translations(original, translated, encoding="cp932")
        self.assertEqual(translated, snapshot)
        self.assertEqual(list(json.loads(dump_rows(plan.stored["a.json"]))[0]), ["names", "message"])
        readback = {"a.json": plan.stored["a.json"], "b.json": original["b.json"]}
        self.assertEqual(plan.verify(readback)["verified_rows"], 2)
        with self.assertRaises(ValueError):
            plan.verify({"a.json": readback["a.json"]})
        readback["b.json"] = [{"message": "modified"}]
        with self.assertRaises(ValueError):
            plan.verify(readback)

    def test_unused_proxies_deterministic_and_skip_literal_pua(self):
        # y.json stays untranslated, so its characters and literal PUA stay reserved;
        # the replaced x.json line no longer reserves its kanji but still keeps its PUA.
        source = {"x.json": [{"message": "原文\ue756"}], "y.json": [{"message": "測訳試\ue757"}]}
        target = {"x.json": [{"message": "测试译"}]}
        with self.assertRaises(ValueError):
            prepare_translations(source, target, encoding="cp932")
        plan = prepare_translations(source, target, encoding="cp932", proxy_policy="unused")
        stored = plan.stored["x.json"][0]["message"]
        # Allocated from the top of U+E000..U+E757 downwards, skipping seen PUA.
        self.assertEqual(sorted(stored), ["\ue753", "\ue754", "\ue755"])
        self.assertEqual(len(stored.encode("cp932")), 6)
        report = json.loads(dict(plan.codec.artifacts(include_hook=False))["jis-mapping.json"])
        self.assertEqual(report["remapped_count"], 3)
        self.assertFalse(report["preset_font_compatible"])
        other = prepare_translations(source, {"x.json": [{"message": "译试测"}]}, encoding="cp932", proxy_policy="unused")
        self.assertEqual(dict(plan.codec.artifacts()), dict(other.codec.artifacts()))
        plan.verify(dict(source, **plan.stored))

    def test_private_pool_exhaustion_and_late_literal_collision(self):
        codec = JisSubstitution()
        codec.reserve("測" + "".join(chr(code) for code in range(0xE000, 0xE758)))
        with self.assertRaisesRegex(ValueError, "pool exhausted"):
            codec.plan(["测"], remap_conflicts=True)
        self.assertEqual(codec.artifacts(), [])
        codec = JisSubstitution()
        codec.reserve("測")
        codec.plan(["测"], remap_conflicts=True)
        proxy = codec.encode("测").decode("cp932")
        with self.assertRaises(ValueError):
            codec.reserve(proxy)

    def test_invalid_inputs_and_existing_encoded_session(self):
        source = {"x.json": [{"name": "A", "message": "text"}]}
        for translated in ({"missing.json": source["x.json"]}, {"x.json": []},
                           {"x.json": [{"message": "lost name"}]},
                           {"x.json": [{"name": "A", "message": "😀"}]}):
            with self.assertRaises(ValueError):
                prepare_translations(source, translated, encoding="cp932")
        with self.assertRaises(ValueError):
            prepare_translations(source, source, encoding="utf-8")
        with self.assertRaises(ValueError):
            prepare_translations({"../x.json": []}, {}, encoding="cp932")
        codec = JisSubstitution()
        codec.encode("这")
        with self.assertRaises(ValueError):
            codec.plan(["测"], remap_conflicts=True)


class WorkspaceTests(unittest.TestCase):
    def fixture(self, root):
        profile = Profile(text_offset=144)
        a = script('$Start\r\n&1"測訳試"\r\n52("_SelStr1","choice")\r\n$End\r\n', profile)
        b = script('$Start\r\n&1"測訳試"\r\n$End\r\n', profile)
        idx, pak = archive([("sc00.dat", a), ("sc01.dat", b)])
        game = root / "game"
        game.mkdir()
        (game / "SCPACK.idx").write_bytes(idx)
        (game / "SCPACK.pak").write_bytes(pak)
        work = root / "work"
        eagls_extract.extract(game, work, profile=profile, key=b"key")
        translated = json.loads((work / "gt_input/sc00.json").read_bytes())
        translated[0]["message"] = "测试译文"
        (work / "gt_output/sc00.json").write_bytes(dump_rows(translated))
        return work, profile

    def test_eagls_original_writer_full_archive_readback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work, profile = self.fixture(root)
            before = {p.relative_to(work).as_posix(): p.read_bytes() for p in work.rglob('*') if p.is_file()}
            preflight = prepare(work, encoding="cp932", jis_preflight=True)
            self.assertEqual({item["character"] for item in preflight["conflicts"]}, {"测", "试", "译"})
            with self.assertRaises(ValueError):
                prepare(work, root / "fixed", encoding="cp932")
            self.assertFalse((root / "fixed").exists())
            (root / "prepared").mkdir()
            info = prepare(work, root / "prepared", encoding="cp932", proxy_policy="unused",
                           include_hook=True, hook="uif")
            self.assertEqual(info["remapped_count"], 3)
            eagls_extract.rebuild(root / "prepared/workspace", root / "engine-output")
            eagls_extract.extract(root / "engine-output/script", root / "readback", profile=profile, key=b"key")
            (root / "delivery").mkdir()
            report = finalize(root / "prepared", root / "engine-output", root / "readback/gt_input", root / "delivery")
            self.assertEqual(report["verified_files"], 2)
            self.assertTrue(report["display_rows_verified"])
            self.assertTrue((root / "delivery/winmm.dll").is_file())
            self.assertEqual((root / "delivery/script/SCPACK.pak").read_bytes(), (root / "engine-output/script/SCPACK.pak").read_bytes())
            self.assertEqual(before, {p.relative_to(work).as_posix(): p.read_bytes() for p in work.rglob('*') if p.is_file()})
            with self.assertRaises(FileExistsError):
                finalize(root / "prepared", root / "engine-output", root / "readback/gt_input", root / "delivery")

    def test_ciallohook_delivery_and_existing_map_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work, profile = self.fixture(root)
            prepare(work, root / "prepared", encoding="cp932", proxy_policy="unused",
                    include_hook=True, hook="ciallohook")
            plan = json.loads((root / "prepared/jis-plan.json").read_bytes())
            self.assertEqual(plan["hook"], "ciallohook")
            eagls_extract.rebuild(root / "prepared/workspace", root / "engine-output")
            eagls_extract.extract(root / "engine-output/script", root / "readback", profile=profile, key=b"key")
            report = finalize(root / "prepared", root / "engine-output", root / "readback/gt_input", root / "delivery")
            self.assertTrue({"version.dll", "version.ini", "uif_config.json"} <= set(report["artifacts"]))
            self.assertFalse((root / "delivery/winmm.dll").exists())
            self.assertIn("CnJpMapJson = uif_config.json", (root / "delivery/version.ini").read_text(encoding="utf-8"))
            (work / "original/winmm.ini").write_text("[CialloHook]\nEnableCnJpMap = true\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "CialloHook EnableCnJpMap"):
                prepare(work, root / "stacked", encoding="cp932", proxy_policy="unused")
            self.assertFalse((root / "stacked").exists())
            (work / "original/winmm.ini").write_text("[CialloHook]\n# EnableCnJpMap = true\nEnableCnJpMap = false\n",
                                                     encoding="utf-8")
            prepare(work, root / "disabled-map", encoding="cp932", proxy_policy="unused")

    def test_exhibit_same_workflow_no_new_engine_api(self):
        from python.engines.exhibit_extract import extract as ex, rebuild as pack
        from tests.test_exhibit_rld import script as rld, op
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "game/rld").mkdir(parents=True)
            (root / "game/rld/start.rld").write_bytes(rld(op(28, ("N", "測"))))
            ex(root / "game", root / "work")
            (root / "work/gt_output/start.json").write_bytes(dump_rows([{"name": "N", "message": "测试"}]))
            # The only source line is replaced: only the conservative scope conflicts.
            self.assertTrue(prepare(root / "work", encoding="cp932", jis_preflight=True)["ok"])
            preflight = prepare(root / "work", encoding="cp932", jis_preflight=True, reserve_scope="all")
            self.assertEqual([item["character"] for item in preflight["conflicts"]], ["测"])
            prepare(root / "work", root / "prepared", encoding="cp932", proxy_policy="unused")
            pack(root / "prepared/workspace", root / "packed", jis_mode="off")
            ex(root / "packed", root / "readback")
            result = finalize(root / "prepared", root / "packed", root / "readback/gt_input", root / "delivered")
            self.assertEqual(result["verified_rows"], 1)
            self.assertGreater(result["used_count"], 0)
            self.assertFalse((root / "delivered/winmm.dll").exists())

    def test_existing_mapping_and_snapshot_tamper_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work, profile = self.fixture(root)
            report_path = work / "reports/extraction.json"
            original = report_path.read_bytes()
            report = json.loads(original)
            report["profile"].update(source_characters="A", target_characters="B")
            report_path.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, "existing character mapping"):
                prepare(work, root / "bad", encoding="cp932", proxy_policy="unused")
            report_path.write_bytes(original)
            prepare(work, root / "prepared", encoding="cp932", proxy_policy="unused")
            (root / "prepared/workspace/gt_output/sc00.json").write_text("[]")
            with self.assertRaisesRegex(ValueError, "snapshot changed"):
                finalize(root / "prepared", root / "absent", root / "absent", root / "bad")
            self.assertFalse((root / "bad").exists())

    def test_engine_rejection_and_wrong_readback_do_not_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work, profile = self.fixture(root)
            prepare(work, root / "prepared", encoding="cp932", proxy_policy="unused")
            eagls_extract.rebuild(root / "prepared/workspace", root / "packed")
            # Original rows and partial readbacks cannot substitute for re-extraction.
            with self.assertRaisesRegex(ValueError, "stored rows differ"):
                finalize(root / "prepared", root / "packed", work / "gt_input", root / "bad")
            rows = json.loads((work / "gt_output/sc00.json").read_bytes())
            rows[0]["message"] += '"'
            (work / "gt_output/sc00.json").write_bytes(dump_rows(rows))
            prepare(work, root / "illegal", encoding="cp932", proxy_policy="unused")
            with self.assertRaises(ValueError):
                eagls_extract.rebuild(root / "illegal/workspace", root / "bad-engine")
            self.assertFalse((root / "bad-engine").exists())


class ReserveScopeTests(unittest.TestCase):
    def test_replaced_lines_released_but_shared_untranslated_text_reserved(self):
        original = {"a.json": [{"message": "測"}, {"message": "測"}, {"names": ["測", "B"], "message": "x"}]}
        # Row 1 replaced; row 2 keeps the same text untranslated; names slot 1 replaced.
        translated = {"a.json": [{"message": "测"}, {"message": "測"}, {"names": ["测", "B"], "message": "x"}]}
        report = preflight_translations(original, translated, encoding="cp932")
        self.assertEqual(report["reserve_scope"], "untranslated")
        [conflict] = report["conflicts"]
        self.assertEqual(conflict["literal_locations"], [
            {"source": "gt_input", "file": "a.json", "row": 2, "field": "message"}])
        self.assertEqual(conflict["translation_location_count"], 2)
        translated["a.json"][1]["message"] = "测"
        self.assertTrue(preflight_translations(original, translated, encoding="cp932")["ok"])
        plan = prepare_translations(original, translated, encoding="cp932")
        self.assertEqual(plan.stored["a.json"][1]["message"], "測")
        # Conservative scope and extra UI text still reserve.
        self.assertFalse(preflight_translations(original, translated, encoding="cp932", reserve_scope="all")["ok"])
        self.assertFalse(preflight_translations(original, translated, encoding="cp932", extra_texts=["測"])["ok"])
        with self.assertRaises(FormatError):
            preflight_translations(original, translated, encoding="cp932", reserve_scope="some")

    def test_prepare_refusal_is_structured_and_capped(self):
        original = {f"f{i:02}.json": [{"message": "測"}] for i in range(30)}
        original["t.json"] = [{"message": "原"}]
        translated = {"t.json": [{"message": "测"}]}
        with self.assertRaises(JisDiagnosticsError) as caught:
            prepare_translations(original, translated, encoding="CP932", max_locations=5)
        report = caught.exception.report
        self.assertEqual((report["schema"], report["stage"], report["ok"]), ("jis-json-preflight/1", "prepare", False))
        self.assertEqual(report["script_encoding"], "CP932")
        conflict = report["conflicts"][0]
        self.assertEqual((len(conflict["literal_locations"]), conflict["literal_location_count"]), (5, 30))
        self.assertTrue(any("--proxy-policy unused" in step for step in report["next_steps"]))
        self.assertIn("JIS proxy", str(caught.exception))
        plan = prepare_translations(original, translated, encoding="CP932", proxy_policy="unused")
        self.assertEqual(plan.codec.summary()["script_encoding"], "CP932")

    def test_batch_mapping_hash_follows_actual_mapping(self):
        original = {"a.json": [{"message": "x"}]}
        one = prepare_translations(original, {"a.json": [{"message": "你"}]}, encoding="cp932").codec.summary()
        two = prepare_translations(original, {"a.json": [{"message": "这"}]}, encoding="cp932").codec.summary()
        self.assertEqual(one["mapping_sha256"], two["mapping_sha256"])
        self.assertNotEqual(one["batch_mapping_sha256"], two["batch_mapping_sha256"])
        self.assertEqual(one["batch_mapping_sha256"], batch_mapping_sha256({"你": "凜"}))


class ReservedCodepointTests(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(parse_reserved_codepoints([0xE000, "U+E001", "U+E010-U+E0FF", "U+e100,U+E200"]),
                         ((0xE000, 0xE001), (0xE010, 0xE100), (0xE200, 0xE200)))
        self.assertEqual(format_reserved_codepoints(parse_reserved_codepoints(["U+E000-U+E00F", 57344])),
                         ["U+E000-U+E00F"])
        for bad in (["E000"], ["U+E0FF-U+E000"], [True], [1.5], ["U+E000-"], "", {"U+E000": 1}, ["U+110000"]):
            with self.assertRaises(FormatError, msg=repr(bad)):
                parse_reserved_codepoints(bad)

    def test_unused_skips_reserved_and_seen_private_from_the_top(self):
        original = {"a.json": [{"message": "測訳"}], "b.json": [{"message": "x"}]}
        translated = {"b.json": [{"message": "测译"}]}
        plan = prepare_translations(original, translated, encoding="cp932", proxy_policy="unused",
                                    extra_texts=["\ue755"], reserved_codepoints=["U+E756-U+E757"])
        self.assertEqual(plan.stored["b.json"][0]["message"], "\ue754\ue753")
        # The fixed proxy itself may be reserved, which forces remapping.
        report = preflight_translations({"a.json": [{"message": "x"}]}, {"a.json": [{"message": "你"}]},
                                        encoding="cp932", reserved_codepoints={"cli": ["U+51DC"]})
        self.assertTrue(report["conflicts"][0]["reserved_codepoint"])
        self.assertEqual(report["conflicts"][0]["literal_locations"],
                         [{"source": "reserved_codepoints", "origin": "cli"}])

    def test_manifest_settings_and_cli_are_combined(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = {"settings": {"reserved_codepoints": ["U+E757", "U+E700-U+E755"]}}
            write_new_tree(root / "work", [
                ("gt_input/a.json", dump_rows([{"message": "原"}])),
                ("gt_input/b.json", dump_rows([{"message": "測"}])),
                ("gt_output/a.json", dump_rows([{"message": "测"}])),
                ("original/source.bin", b"source"),
                ("metadata/a.json", json.dumps(manifest).encode())])
            info = prepare(root / "work", root / "prepared", encoding="cp932", proxy_policy="unused",
                           reserved_codepoints=["U+E756"])
            plan = json.loads((root / "prepared/jis-plan.json").read_text(encoding="utf-8"))
            self.assertEqual(plan["reserved_codepoint_sources"],
                             {"metadata/a.json": ["U+E700-U+E755", "U+E757"], "cli": ["U+E756"]})
            self.assertEqual(info["reserved_codepoints"], ["U+E700-U+E757"])
            stored = json.loads((root / "prepared/workspace/gt_output/a.json").read_text(encoding="utf-8"))
            self.assertEqual(stored[0]["message"], "\ue6ff")
            (root / "work/metadata/a.json").write_text('{"settings": {"reserved_codepoints": ["E000"]}}')
            with self.assertRaisesRegex(FormatError, "U\\+E000"):
                prepare(root / "work", encoding="cp932", jis_preflight=True)


class CliAndHookTests(unittest.TestCase):
    def workspace(self, root):
        write_new_tree(root / "work", [
            ("gt_input/a.json", dump_rows([{"message": "原"}])),
            ("gt_input/b.json", dump_rows([{"message": "測"}])),
            ("gt_output/a.json", dump_rows([{"message": "测"}])),
            ("original/source.bin", b"source"), ("metadata/a.json", b"{}")])
        return root / "work"

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-B", "-m", "python.common.jis_workflow", *map(str, args)],
                              cwd=ROOT, capture_output=True)

    def test_prepare_conflict_prints_report_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = self.workspace(root)
            failed = self.run_cli("prepare", work, root / "out", "--encoding", "cp932")
            self.assertEqual(failed.returncode, 1, failed.stderr)
            self.assertNotIn(b"Traceback", failed.stderr)
            text = failed.stdout.decode("utf-8")
            self.assertIn('"character": "测"', text)  # not ASCII-escaped
            report = json.loads(text)
            self.assertEqual((report["stage"], report["schema"]), ("prepare", "jis-json-preflight/1"))
            self.assertTrue(report["next_steps"])
            self.assertFalse((root / "out").exists())
            passed = self.run_cli("prepare", work, root / "out", "--encoding", "cp932", "--proxy-policy", "unused",
                                  "--hook", "x64", "--reserve-codepoints", "U+E757")
            self.assertEqual(passed.returncode, 0, passed.stderr)
            result = json.loads(passed.stdout.decode("utf-8"))
            self.assertEqual(result["reserved_codepoints"], ["U+E757"])
            self.assertTrue((root / "out/support/version.dll").is_file())
            plan = json.loads((root / "out/jis-plan.json").read_text(encoding="utf-8"))
            self.assertEqual((plan["hook"], plan["hook_architecture"]), ("ciallohook-x64", "x64"))
            again = self.run_cli("prepare", work, root / "out", "--encoding", "cp932")
            self.assertEqual(again.returncode, 1)
            self.assertNotIn(b"Traceback", again.stderr)

    def test_x64_artifacts_and_exe_bitness(self):
        codec = JisSubstitution()
        codec.encode("你好")
        artifacts = dict(codec.artifacts(hook="ciallohook-x64"))
        dll = artifacts["version.dll"]
        self.assertEqual(hashlib.sha256(dll).hexdigest(), CIALLOHOOK_X64_SHA256)
        pe = struct.unpack_from("<I", dll, 60)[0]
        self.assertEqual(struct.unpack_from("<H", dll, pe + 4)[0], 0x8664)
        self.assertIn("CnJpMapJson = uif_config.json", artifacts["version.ini"].decode("utf-8"))
        self.assertEqual(artifacts["uif_config.json"], dict(codec.artifacts(hook="uif"))["uif_config.json"])
        report = json.loads(artifacts["jis-mapping.json"])["hook"]
        self.assertEqual((report["name"], report["architecture"]), ("ciallohook-x64", "x64"))
        self.assertIn("x64，只用于 64 位", artifacts["JIS-部署说明.txt"].decode("utf-8"))
        self.assertEqual(HOOK_CHOICES["x64"], "ciallohook-x64")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe = root / "game.exe"
            exe.write_bytes(b"MZ" + bytes(58) + struct.pack("<I", 64) + b"PE\0\0" + struct.pack("<H", 0x8664))
            self.assertEqual(pe_machine(exe), 0x8664)
            arch = self.run_cli("arch", exe)
            self.assertEqual(json.loads(arch.stdout)["hook_choices"], ["x64", "ciallohook-x64"])
            work = self.workspace(root)
            with self.assertRaisesRegex(FormatError, "never loaded"):
                prepare(work, root / "out", encoding="cp932", proxy_policy="unused",
                        include_hook=True, hook="uif", exe=exe)
            self.assertFalse((root / "out").exists())
            prepare(work, root / "out", encoding="cp932", proxy_policy="unused",
                    include_hook=True, hook="ciallohook-x64", exe=exe)


class BoundedReadTests(unittest.TestCase):
    def test_read_is_sized_from_lstat_and_still_bounded(self):
        from python.common import jis_workflow
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.json"
            path.write_bytes(b"0123456789")
            self.assertEqual(jis_workflow._read(path, limit=10), b"0123456789")
            with self.assertRaisesRegex(FormatError, "budget"):
                jis_workflow._read(path, limit=9)
            # A file that grows after lstat is still read up to the budget only.
            info = path.lstat()
            path.write_bytes(b"0123456789abc")
            self.assertEqual(jis_workflow._read_entry(path, info, 20), b"0123456789abc")
            with self.assertRaisesRegex(FormatError, "grew beyond budget"):
                jis_workflow._read_entry(path, info, 11)


if __name__ == "__main__":
    unittest.main()
