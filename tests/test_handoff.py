"""Extraction hand-off: the extractor states the delivery facts once.

Regression background: after a byte-identical extraction, sessions spent many
more calls re-measuring BOMs, hashes and counts and reading the state template
just to fill the final table. The table now holds only what a translator
needs, and the extractor supplies it. Synthetic fixtures only.
"""
import json
from pathlib import Path
import re
import tempfile
import unittest

from python.common.handoff import STATE_FILE, handoff
from python.engines import kaguya
from python.engines.kaguya_extract import extract as kaguya_extract
from python.engines.systemc_extract import extract as systemc_extract
from python.engines.systemc_txd_extract import extract as txd_extract

ROOT = Path(__file__).resolve().parents[1]
DELIVERY_KEYS = {"engine", "gt_input", "gt_output", "json_files", "rows", "suggested_first_json",
                 "translation_notes", "not_verified", "state_file", "next"}


def labels(markdown):
    """First-column labels of every table row, without header rows."""
    found = re.findall(r"^\| ([^|]+?) \|", markdown, re.M)
    return {label for label in found if label not in {"项目", "阶段"}}


class HandoffTests(unittest.TestCase):
    def check(self, report, workspace, *, rows, edit_verified):
        delivery = report["delivery"]
        self.assertEqual(set(delivery), DELIVERY_KEYS)
        self.assertEqual(delivery["rows"], rows)
        self.assertEqual(delivery["gt_input"], str((workspace / "gt_input").resolve()))
        self.assertTrue(delivery["translation_notes"])
        self.assertIn("游戏内加载与显示", delivery["not_verified"])
        self.assertEqual(len(delivery["not_verified"]) == 1, edit_verified)
        self.assertTrue((workspace / "gt_input" / delivery["suggested_first_json"]["file"]).is_file())
        saved = json.loads((workspace / "reports/extraction.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["delivery"], delivery)
        state = (workspace / STATE_FILE).read_text(encoding="utf-8")
        self.assertIn(delivery["gt_input"], state)
        self.assertIn(f"{rows} 条", state)
        for note in delivery["translation_notes"]:
            self.assertIn(note, state)
        return state

    def test_generated_state_matches_the_template_and_the_skill_table(self):
        """The generated file replaces filling the template by hand, and its
        delivery table is the one SKILL.md asks for; neither may drift."""
        template = (ROOT / "templates/translation-state.md").read_text(encoding="utf-8")
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as temp:
            delivery, state = handoff(
                workspace=Path(temp), engine="引擎|方言", json_files=1, rows=7, notes=[],
                verified="字节一致", edit_checked=False, first_json="a.json", first_json_basis="唯一",
                command="extract")
        state = state.decode("utf-8")
        self.assertEqual(labels(template), labels(state))
        for label in ("引擎", "翻译文件", "翻译时注意", "尚未验证"):
            self.assertIn(f"| {label} |", skill)
            self.assertIn(f"| {label} |", state)
        for bullet in re.findall(r"^- ([^：]+)：", template, re.M):
            self.assertIn(f"- {bullet}：", state)
        self.assertIn("引擎\\|方言", state)
        self.assertIn("| 翻译时注意 | 无 |", state)
        self.assertIn("| 试编辑回写 | 未执行 |", state)
        self.assertEqual(len(delivery["not_verified"]), 2)
        self.assertIn("not part of extraction", delivery["next"])

    def test_kaguya_extract_writes_delivery_and_state(self):
        doc = kaguya.Document(kaguya.MAGIC + b"\x01\xff", ("名前",), ("選択",),
                              (kaguya.Message("本文\n"), kaguya.Message("未使用")), (kaguya.Group(0, (0,)),),
                              trailer=b"unknown")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "message.dat").write_bytes(kaguya.write_message_dat(doc))
            (root / "out").mkdir()
            report = kaguya_extract(root, root / "out", verify_edits=True)
            state = self.check(report, root / "out", rows=2, edit_verified=True)
            self.assertIn("未识别的数据", state)

    def test_systemc_extracts_write_delivery_and_state(self):
        from tests.test_systemc import archive, fixture as cp932_fixture
        from tests.test_systemc_txd import fixture as txd_fixture
        for members, run, edit in ((cp932_fixture(), systemc_extract, False), (txd_fixture(), txd_extract, True)):
            with self.subTest(run=run.__module__), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                (root / "data.fpk").write_bytes(archive(members))
                (root / "out").mkdir()
                report = run(root, root / "out", verify_edits=edit)
                rows = report.get("json_rows", report.get("rows"))
                state = self.check(report, root / "out", rows=rows, edit_verified=edit)
                self.assertIn("| 提取与原文往返 | 已验证 |", state)


if __name__ == "__main__":
    unittest.main()
