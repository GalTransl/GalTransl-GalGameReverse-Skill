# SPDX-License-Identifier: GPL-3.0-only
"""Shared read-only JIS diagnostics and the SystemC compatibility adapter."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from python.common.binary import FormatError
from python.common.contract import dump_rows
from python.common.jis_substitution import JisSubstitution, MAPPING_SHA256
from python.common.jis_workflow import preflight_translations, prepare, prepare_translations
from python.common.safety import write_new_tree
from python.engines.systemc_extract import extract, pack
from tests.test_systemc import archive, fixture

ROOT = Path(__file__).resolve().parents[1]


class PreflightCodecTests(unittest.TestCase):
    def test_all_conflicts_missing_mapping_and_no_state_changes(self):
        codec = JisSubstitution()
        codec.reserve("凜這")
        report = codec.preflight(iter(["你这", "测", "測", "😀"]))
        self.assertEqual(report["mapping_sha256"], MAPPING_SHA256)
        self.assertEqual(report["required_count"], 4)
        self.assertEqual(report["conflicts"], [
            {"character": "你", "proxy": "凜"},
            {"character": "测", "proxy": "測"},
            {"character": "这", "proxy": "這"}])
        self.assertEqual(report["missing_characters"], ["😀"])
        self.assertFalse(report["ok"])
        self.assertEqual(codec.artifacts(), [])
        self.assertEqual(codec.encode("测").decode("cp932"), "測")
        with self.assertRaisesRegex(FormatError, "after encoding"):
            codec.preflight(["你"])

    def test_order_independence_and_agreement_with_fixed_plan(self):
        for texts in (["你", "凜"], ["凜", "你"], ["你凜"]):
            codec = JisSubstitution()
            self.assertEqual(codec.preflight(texts)["conflicts"], [{"character": "你", "proxy": "凜"}])
            with self.assertRaisesRegex(FormatError, "JIS proxy"):
                codec.plan(texts)
        codec = JisSubstitution()
        self.assertTrue(codec.preflight(["你好", "日本語"])["ok"])
        codec.plan(["你好", "日本語"])
        self.assertEqual(codec.display(codec.encode("你好").decode("cp932")), "你好")
        with self.assertRaisesRegex(FormatError, "alias"):
            JisSubstitution().preflight(["〜"])


class SystemcPreflightTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.work = self.root / "work"
        members = fixture()
        members["ACT_B.txt"] = members["ACT_A.txt"].replace("//最後".encode("cp932"), "//凜".encode("cp932"))
        members["ACT_B.DAT"] = members["ACT_A.DAT"]
        members["charaid.tbl"] = members["charaid.tbl"].replace("//キャラ".encode("cp932"), "//這".encode("cp932"))
        (self.root / "data.fpk").write_bytes(archive(members))
        extract(self.root, self.work)
        self.rows = json.loads((self.work / "gt_input/ACT_A.json").read_bytes())

    def test_cross_script_and_table_conflicts_with_locations_and_no_writes(self):
        translated = deepcopy(self.rows)
        translated[1]["message"] = "你这你"
        (self.work / "gt_output/ACT_A.json").write_bytes(dump_rows(translated))
        snapshot = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        output = self.root / "unused"
        result = pack(self.work, output, jis_preflight=True)
        self.assertEqual(result["schema"], "systemc-jis-preflight/1")
        self.assertEqual(result["missing_translations"], ["ACT_B.json"])
        self.assertNotIn("output_sha256", result)
        conflicts = result["jis_preflight"]["conflicts"]
        self.assertEqual([c["character"] for c in conflicts], ["你", "这"])
        self.assertEqual(conflicts[0]["literal_locations"], [
            {"source": "extra_texts", "file": "original/members/ACT_B.txt", "line": 10}])
        self.assertEqual(conflicts[1]["literal_locations"], [
            {"source": "extra_texts", "file": "original/members/charaid.tbl", "line": 1}])
        self.assertEqual(conflicts[0]["translation_locations"], [
            {"source": "gt_output", "file": "ACT_A.json", "row": 2, "field": "message"}])
        self.assertFalse(output.exists())
        self.assertEqual(snapshot, {p.relative_to(self.root): p.read_bytes()
                                   for p in self.root.rglob("*") if p.is_file()})
        with self.assertRaisesRegex(FormatError, "JIS proxy"):
            pack(self.work, self.root / "blocked")
        self.assertFalse((self.root / "blocked").exists())

    def test_literal_proxy_in_later_translation_and_missing_mapping(self):
        translated = deepcopy(self.rows)
        translated[0]["message"] = "测$S\n続き$Lです」"
        translated[1]["message"] = "測😀"
        (self.work / "gt_output/ACT_A.json").write_bytes(dump_rows(translated))
        report = pack(self.work, jis_preflight=True)["jis_preflight"]
        self.assertEqual(report["missing_characters"], ["😀"])
        self.assertEqual(report["conflicts"], [{"character": "测", "proxy": "測",
            "literal_locations": [{"source": "gt_output", "file": "ACT_A.json", "row": 2, "field": "message"}],
            "translation_locations": [{"source": "gt_output", "file": "ACT_A.json", "row": 1, "field": "message"}]}])

    def test_cli_exit_status_and_external_translation_directory(self):
        translated = deepcopy(self.rows)
        translated[1]["message"] = "你这"
        (self.work / "gt_output/ACT_A.json").write_bytes(dump_rows(translated))
        command = [sys.executable, "-B", "-m", "python.engines.systemc_extract", "pack", str(self.work), "--jis-preflight"]
        output = self.root / "unused"
        failed = subprocess.run([*command, "--output", str(output)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(failed.returncode, 1, failed.stderr)
        self.assertEqual(len(json.loads(failed.stdout)["jis_preflight"]["conflicts"]), 2)
        self.assertFalse(output.exists())
        external = self.root / "translations"
        external.mkdir()
        translated[1]["message"] = "测试。"
        (external / "ACT_A.json").write_bytes(dump_rows(translated))
        passed = subprocess.run([*command, "--translations", str(external)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(passed.returncode, 0, passed.stderr)
        self.assertTrue(json.loads(passed.stdout)["jis_preflight"]["ok"])
        missing_output = subprocess.run(command[:-1], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(missing_output.returncode, 2)
        disabled = subprocess.run([*command, "--jis-mode", "off"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(disabled.returncode, 2)

    def test_source_identity_and_no_translation(self):
        self.assertTrue(pack(self.work, jis_preflight=True)["jis_preflight"]["ok"])
        with self.assertRaisesRegex(FormatError, "requires --jis-mode auto"):
            pack(self.work, jis_preflight=True, jis_mode="off")
        with self.assertRaisesRegex(FormatError, "output destination"):
            pack(self.work)
        changed = deepcopy(self.rows)
        changed[1]["message"] = "改変"
        (self.work / "gt_input/ACT_A.json").write_bytes(dump_rows(changed))
        with self.assertRaisesRegex(FormatError, "source identity"):
            pack(self.work, jis_preflight=True)


class SharedPreflightTests(unittest.TestCase):
    def test_names_messages_untouched_files_and_named_extra_text(self):
        original = {"a.json": [{"names": ["A", "B"], "message": "text"}],
                    "b.json": [{"message": "凜"}],
                    "c.json": [{"name": "測", "message": "text"}]}
        translated = {"a.json": [{"names": ["你", "这"], "message": "测😀"}]}
        extra = {"ui/menu.txt": "header\r\n這\r\n"}
        snapshot = deepcopy((original, translated, extra))
        report = preflight_translations(original, translated, encoding="cp932", extra_texts=extra)
        self.assertEqual(report["missing_translations"], ["b.json", "c.json"])
        self.assertEqual(report["missing_characters"], ["😀"])
        conflicts = {item["character"]: item for item in report["conflicts"]}
        self.assertEqual(conflicts["你"]["translation_locations"], [
            {"source": "gt_output", "file": "a.json", "row": 1, "field": "names", "slot": 1}])
        self.assertEqual(conflicts["你"]["literal_locations"], [
            {"source": "gt_input", "file": "b.json", "row": 1, "field": "message"}])
        self.assertEqual(conflicts["测"]["literal_locations"], [
            {"source": "gt_input", "file": "c.json", "row": 1, "field": "name"}])
        self.assertEqual(conflicts["这"]["literal_locations"], [
            {"source": "extra_texts", "file": "ui/menu.txt", "line": 2}])
        self.assertEqual((original, translated, extra), snapshot)

    def test_preparation_and_preflight_share_input_validation(self):
        original = {"a.json": [{"names": ["A", "B"], "message": "text"}]}
        for target in ({"a.json": []}, {"unknown.json": []},
                       {"a.json": [{"message": "lost names"}]},
                       {"a.json": [{"names": ["A"], "message": "lost slot"}]}):
            for function in (preflight_translations, prepare_translations):
                with self.assertRaises(FormatError):
                    function(original, target, encoding="cp932")
        for encoding in ("utf-8", "shift_jis", "gbk"):
            with self.assertRaises(FormatError):
                preflight_translations(original, {}, encoding=encoding)
        for extra in ([b"bytes"], {"../unsafe.txt": "text"}):
            with self.assertRaises(FormatError):
                preflight_translations(original, {}, encoding="cp932", extra_texts=extra)
        translated = {"a.json": [{"names": ["A", "B"], "message": "测"}]}
        report = preflight_translations(original, translated, encoding="cp932", extra_texts=iter(["測"]))
        self.assertFalse(report["ok"])
        with self.assertRaisesRegex(FormatError, "JIS proxy"):
            prepare_translations(original, translated, encoding="cp932", extra_texts={"ui.txt": "測"})

    def test_generic_cli_no_writes_exit_status_and_extra_text(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            work = root / "work"
            write_new_tree(work, [("gt_input/a.json", dump_rows([{"message": "text"}])),
                                 ("gt_output/a.json", dump_rows([{"message": "你"}])),
                                 ("original/source.bin", b"source"), ("metadata/a.json", b"{}")])
            extra = root / "ui.txt"
            extra.write_text("凜", encoding="utf-8")
            before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            output = root / "unused"
            command = [sys.executable, "-B", "-m", "python.common.jis_workflow", "prepare",
                       str(work), "--encoding", "cp932", "--jis-preflight"]
            failed = subprocess.run([*command[:6], str(output), *command[6:], "--extra-text", str(extra)],
                                    cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(failed.returncode, 1, failed.stderr)
            conflict = json.loads(failed.stdout)["conflicts"][0]
            self.assertEqual(conflict["literal_locations"], [
                {"source": "extra_texts", "file": "1-ui.txt", "line": 1}])
            self.assertFalse(output.exists())
            self.assertEqual(before, {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()})
            passed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(passed.returncode, 0, passed.stderr)
            self.assertTrue(json.loads(passed.stdout)["ok"])
            with self.assertRaisesRegex(FormatError, "output destination"):
                prepare(work, encoding="cp932")
            invalid = subprocess.run([*command, "--proxy-policy", "unused"],
                                     cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(invalid.returncode, 2)
            with self.assertRaisesRegex(FormatError, "fixed mapping"):
                prepare(work, encoding="cp932", jis_preflight=True, proxy_policy="unused")
            external = root / "external"
            write_new_tree(external, [("a.json", dump_rows([{"message": "😀"}]))])
            missing = subprocess.run([*command, "--translations", str(external)],
                                     cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(missing.returncode, 1, missing.stderr)
            self.assertEqual(json.loads(missing.stdout)["missing_characters"], ["😀"])

    def test_workspace_existing_mapping_rejected_before_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_new_tree(root / "work", [("gt_input/a.json", dump_rows([{"message": "text"}])),
                ("gt_output/.keep", b""), ("original/source.bin", b"source"),
                ("metadata/mapping.json", b'{"source_characters": "A", "target_characters": "B"}')])
            with self.assertRaisesRegex(FormatError, "existing character mapping"):
                prepare(root / "work", encoding="cp932", jis_preflight=True)


if __name__ == "__main__":
    unittest.main()
