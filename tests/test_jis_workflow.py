"""Shared JSON JIS workflow against ordinary, unmodified engine writers."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from python.common.contract import dump_rows
from python.common.jis_workflow import prepare_translations, prepare, finalize
from python.common.jis_substitution import JisSubstitution
from python.engines import eagls_extract
from python.engines.eagls_text import Profile
from tests.test_eagls import archive, script


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
        source = {"x.json": [{"message": "測訳試\ue000"}]}
        target = {"x.json": [{"message": "测试译"}]}
        with self.assertRaises(ValueError):
            prepare_translations(source, target, encoding="cp932")
        plan = prepare_translations(source, target, encoding="cp932", proxy_policy="unused")
        self.assertNotIn("\ue000", plan.stored["x.json"][0]["message"])
        self.assertEqual(len(plan.stored["x.json"][0]["message"].encode("cp932")), 6)
        report = json.loads(dict(plan.codec.artifacts(include_hook=False))["jis-mapping.json"])
        self.assertEqual(report["remapped_count"], 3)
        self.assertFalse(report["preset_font_compatible"])
        other = prepare_translations(source, {"x.json": [{"message": "译试测"}]}, encoding="cp932", proxy_policy="unused")
        self.assertEqual(dict(plan.codec.artifacts()), dict(other.codec.artifacts()))
        plan.verify(plan.stored)

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
        b = script('$Start\r\n&1"unchanged"\r\n$End\r\n', profile)
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
            with self.assertRaises(ValueError):
                prepare(work, root / "fixed", encoding="cp932")
            self.assertFalse((root / "fixed").exists())
            info = prepare(work, root / "prepared", encoding="cp932", proxy_policy="unused", include_hook=True)
            self.assertEqual(info["remapped_count"], 3)
            eagls_extract.rebuild(root / "prepared/workspace", root / "engine-output")
            eagls_extract.extract(root / "engine-output/script", root / "readback", profile=profile, key=b"key")
            report = finalize(root / "prepared", root / "engine-output", root / "readback/gt_input", root / "delivery")
            self.assertEqual(report["verified_files"], 2)
            self.assertTrue(report["display_rows_verified"])
            self.assertTrue((root / "delivery/winmm.dll").is_file())
            self.assertEqual((root / "delivery/script/SCPACK.pak").read_bytes(), (root / "engine-output/script/SCPACK.pak").read_bytes())
            self.assertEqual(before, {p.relative_to(work).as_posix(): p.read_bytes() for p in work.rglob('*') if p.is_file()})
            with self.assertRaises(FileExistsError):
                finalize(root / "prepared", root / "engine-output", root / "readback/gt_input", root / "delivery")

    def test_exhibit_same_workflow_no_new_engine_api(self):
        from python.engines.exhibit_extract import extract as ex, rebuild as pack
        from tests.test_exhibit_rld import script as rld, op
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "game/rld").mkdir(parents=True)
            (root / "game/rld/start.rld").write_bytes(rld(op(28, ("N", "測"))))
            ex(root / "game", root / "work")
            (root / "work/gt_output/start.json").write_bytes(dump_rows([{"name": "N", "message": "测试"}]))
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


if __name__ == "__main__":
    unittest.main()
