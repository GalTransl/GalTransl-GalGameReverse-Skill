"""JIS encoding policy and actual CP932 archive reinjection regression tests."""
from copy import deepcopy
import json
import hashlib
import struct
from pathlib import Path
import tempfile
import unittest

from python.common.binary import FormatError
from python.common.contract import make_manifest, validate_translation, dump_rows
from python.common.jis_substitution import JisSubstitution, is_cp932, HOOK_SHA256
from python.engines.systemc import export_act, inject_act
from python.engines.systemc_extract import extract, pack
from python.archives.systemc import unpack_fpk
from tests.test_systemc import fixture, archive


class JisTests(unittest.TestCase):
    def test_upstream_mapping_and_config_direction(self):
        codec = JisSubstitution()
        text = "你好，说这句话。ABC\n$S"
        raw = codec.encode(text)
        self.assertEqual(raw.decode("cp932"), "凜好，説這句話。ABC\n$S")
        self.assertEqual(codec.display(raw.decode("cp932")), text)
        artifacts = dict(codec.artifacts())
        hook = artifacts["winmm.dll"]
        self.assertEqual(hashlib.sha256(hook).hexdigest(), HOOK_SHA256)
        pe = struct.unpack_from("<I", hook, 60)[0]
        self.assertEqual(hook[pe:pe+4], b"PE\0\0")
        self.assertEqual(struct.unpack_from("<H", hook, pe+4)[0], 0x14c)
        without_hook = dict(codec.artifacts(include_hook=False))
        self.assertNotIn("winmm.dll", without_hook)
        self.assertEqual(without_hook["uif_config.json"], artifacts["uif_config.json"])
        config = json.loads(artifacts["uif_config.json"])
        sub = config["character_substitution"]
        self.assertEqual(raw.decode("cp932").translate(str.maketrans(
            sub["source_characters"], sub["target_characters"])), text)
        self.assertFalse(config["font_manager"]["enable"])
        self.assertFalse(config["tunnel_decoder"]["enable"])

    def test_pass_through_aliases_and_explicit_encoding(self):
        codec = JisSubstitution("ms932")
        self.assertTrue(is_cp932("932"))
        text = "日本語 中文 ABC\t\r\n"
        self.assertEqual(codec.encode(text), text.encode("cp932"))
        self.assertEqual(codec.artifacts(), [])
        for encoding in ("utf-8", "utf-16le", "shift_jis", "gbk"):
            with self.assertRaises(FormatError):
                JisSubstitution(encoding)
        for text in ("😀", "〜", "\ud800"):
            with self.assertRaises(FormatError):
                codec.encode(text)

    def test_collision_across_files_in_both_orders_and_within_field(self):
        for first, second in (("你", "凜"), ("凜", "你")):
            codec = JisSubstitution()
            codec.encode(first)
            with self.assertRaises(FormatError):
                codec.encode(second)
        codec = JisSubstitution()
        with self.assertRaises(FormatError):
            codec.encode("你和凜")
        codec.reserve("未修改的凜")
        with self.assertRaises(FormatError):
            codec.encode("你")

    def test_budget_and_determinism_no_partial_use_after_failure(self):
        a, b = JisSubstitution(), JisSubstitution()
        with self.assertRaises(FormatError):
            a.encode("你", max_bytes=1)
        self.assertEqual(a.artifacts(), [])
        with self.assertRaises(FormatError):
            a.encode("你😀")
        self.assertEqual(a.artifacts(), [])
        a.encode("你这")
        b.encode("这"); b.encode("你")
        self.assertEqual(a.artifacts(), b.artifacts())
        self.assertEqual(len(a.encode("你", max_bytes=2)), 2)

    def test_font_full_preset_collision_report(self):
        codec = JisSubstitution()
        codec.reserve("凜")
        codec.encode("这")
        report = json.loads(dict(codec.artifacts())["jis-mapping.json"])
        self.assertIn("凜", report["preset_font_conflicts"])
        self.assertEqual(report["chinese_to_proxy"], {"这": "這"})

    def test_contract_keeps_real_chinese_name_and_names_and_invariants(self):
        for name_fields in ({"name": "太郎"}, {"names": ["太郎", "花子"]}):
            rows = [dict(name_fields, message="本文$S")]
            sources = {"a": b"source"}
            meta = make_manifest(engine="test", variant="test", reference="test",
                sources=sources, rows=rows, locators=[{"offset": 0}], encoding="cp932",
                name_policies=["writable"], protected_tokens=[["$S"]])
            changed = deepcopy(rows)
            changed[0]["message"] = "你$S"
            if "name" in changed[0]: changed[0]["name"] = "这"
            else: changed[0]["names"] = ["这", "她"]
            snapshot = deepcopy(changed)
            codec = JisSubstitution()
            self.assertEqual(validate_translation(meta, sources, rows, changed, text_codec=codec), snapshot)
            self.assertEqual(changed, snapshot)
            with self.assertRaises(FormatError):
                validate_translation(meta, sources, rows, changed)
            bad = deepcopy(changed); bad[0]["message"] = "你"
            with self.assertRaises(FormatError):
                validate_translation(meta, sources, rows, bad, text_codec=codec)
            with self.assertRaises(FormatError):
                validate_translation(meta, {"a": b"tampered"}, rows, changed, text_codec=codec)
            wrong = deepcopy(meta); wrong["encoding"] = "utf-8"
            with self.assertRaises(FormatError):
                validate_translation(wrong, sources, rows, changed, text_codec=codec)

    def test_actual_systemc_archive_pack_and_semantic_reparse(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = archive(fixture())
            (root / "data.fpk").write_bytes(original)
            work = root / "extract"
            extract(root, work)
            before = (work / "gt_input/ACT_A.json").read_bytes()
            changed = json.loads(before)
            changed[1]["message"] = "你好，这是中文。"
            translated = dump_rows(changed)
            (work / "gt_output/ACT_A.json").write_bytes(translated)
            result = pack(work, root / "rebuilt")
            self.assertEqual(hashlib.sha256((root / "rebuilt/winmm.dll").read_bytes()).hexdigest(), HOOK_SHA256)
            self.assertGreater(result["text_encoding"]["used_count"], 0)
            config = json.loads((root / "rebuilt/uif_config.json").read_bytes())["character_substitution"]
            _, actual = unpack_fpk((root / "rebuilt/data.fpk").read_bytes())
            rows, _ = export_act("ACT_A.txt", actual)
            restored = [{k: v.translate(str.maketrans(config["source_characters"], config["target_characters"]))
                         for k, v in row.items()} for row in rows]
            self.assertEqual(restored, changed)
            for name, raw in fixture().items():
                if name != "ACT_A.txt": self.assertEqual(actual[name], raw)
            self.assertEqual((root / "data.fpk").read_bytes(), original)
            self.assertEqual((work / "gt_input/ACT_A.json").read_bytes(), before)
            self.assertEqual((work / "gt_output/ACT_A.json").read_bytes(), translated)
            with self.assertRaises(FormatError):
                pack(work, root / "strict", jis_mode="off")
            self.assertFalse((root / "strict").exists())

    def test_engine_limits_controls_and_context_names_still_enforced(self):
        members = fixture(); rows, meta = export_act("ACT_A.txt", members)
        for change in ({"message": "你" * 2049}, {"name": "你"}):
            edited = deepcopy(rows); edited[0].update(change)
            with self.assertRaises(FormatError):
                inject_act("ACT_A.txt", members, rows, meta, edited, text_codec=JisSubstitution())
        edited = deepcopy(rows); edited[1]["message"] = "你" * 2049
        with self.assertRaises(FormatError):
            inject_act("ACT_A.txt", members, rows, meta, edited, text_codec=JisSubstitution())


if __name__ == "__main__":
    unittest.main()
