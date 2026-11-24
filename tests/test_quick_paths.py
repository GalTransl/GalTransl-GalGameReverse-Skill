"""Engine pages lead with the command to run.

Regression background: sessions read whole extractor sources and research
notes before trying the documented extract command, because the command sat
deep inside the page. The section is generated so every page stays uniform.
"""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from update_quick_paths import HEADING, render, stale_pages  # noqa: E402

PAGE = ("# 标题\n\n开头的说明段落，不是小节标题。\n\n## 用法\n\n```text\n"
        "python -m python.engines.demo_extract extract \"<游戏目录>\" \"<输出>\" --verify-edits\n"
        "python -m python.engines.demo_extract pack \"<输出>\" \"<补丁>\"\n```\n\n"
        "## 另一种来源\n\n```text\n"
        "python -m python.engines.demo_extract extract \"<游戏目录>\" \"<输出>\" --loose\n```\n")


class QuickPathTests(unittest.TestCase):
    def test_section_follows_the_title_and_lists_only_extract_commands(self):
        updated = render(PAGE)
        head, rest = updated.split("## 用法", 1)
        self.assertTrue(head.startswith(f"# 标题\n\n{HEADING}\n"))
        self.assertEqual(head.count("python -m python.engines.demo_extract extract"), 2)
        self.assertNotIn(" pack ", head)
        self.assertIn("开头的说明段落", head)
        self.assertEqual("## 用法" + rest, PAGE[PAGE.index("## 用法"):])

    def test_regeneration_keeps_the_prose_after_the_section(self):
        """The first version ended the section at the next heading and so
        swallowed an intro paragraph on the second run."""
        once = render(PAGE)
        self.assertEqual(render(once), once)
        edited = once.replace("--loose", "--loose --smoke-test")
        again = render(edited)
        self.assertEqual(again.count("--loose --smoke-test"), 2)
        self.assertIn("开头的说明段落", again)

    def test_pages_without_extract_commands_are_left_alone(self):
        page = "# 标题\n\n只有 Python 接口。\n\n## 用法\n\n```text\npython tools/x.py\n```\n"
        self.assertEqual(render(page), page)
        self.assertEqual(render(render(PAGE).replace("python -m python.engines.demo_extract extract", "run")),
                         PAGE.replace("python -m python.engines.demo_extract extract", "run"))

    def test_direct_extract_modules_and_interpreter_switches_are_listed(self):
        """Extractors without an ``extract`` subcommand, or documented with -B / -X utf8,
        were left out, so detection named the page but gave no command to run."""
        page = ("# 标题\n\n## 用法\n\n```text\n"
                "python -B -m python.engines.demo_extract \"<游戏目录>\" --archive a.int\n"
                "python -B -m python.engines.demo_extract pack \"<工作区>\" \"<补丁>\"\n"
                "python -m python.engines.demo_extract \"<工作区>\" \"<回读>\" --readback \"<补丁>\"\n"
                "python -X utf8 -m python.engines.other_tool extract \"<游戏目录>\" \"<输出>\"\n"
                "python -X utf8 -m python.engines.other_tool rebuild \"<输出>\" \"<新目录>\"\n"
                "python -m python.engines.demo_pack \"<工作区>\" \"<补丁>\"\n```\n")
        head = render(page).split("## 用法", 1)[0]
        self.assertEqual([line for line in head.splitlines() if line.startswith("python ")],
                         ["python -B -m python.engines.demo_extract \"<游戏目录>\" --archive a.int",
                          "python -X utf8 -m python.engines.other_tool extract \"<游戏目录>\" \"<输出>\""])

    def test_detection_next_steps_repeat_the_page_section(self):
        sys.path.insert(0, str(ROOT))
        from python.detect import next_steps
        for engine in ("catsystem2", "qlie", "escude", "entis-gls", "kirikiri"):
            with self.subTest(engine=engine):
                stats = {"candidate_stats": {engine: {"by_strength": {"probe": 1}, "matched_files": 1}}}
                step = next_steps(stats)[0]
                text = (ROOT / step["engine_page"]).read_text(encoding="utf-8")
                section = text.split(HEADING, 1)[1].split("```text", 1)[1].split("```", 1)[0]
                self.assertEqual(step["extract_commands"], section.strip().splitlines()[:4])
                self.assertTrue(step["extract_commands"])

    def test_bundled_pages_are_current_and_line_endings_survive(self):
        self.assertEqual(stale_pages(ROOT), [])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "engines").mkdir()
            (root / "engines/demo.md").write_bytes(PAGE.replace("\n", "\r\n").encode("utf-8"))
            self.assertEqual(stale_pages(root), ["engines/demo.md"])
            self.assertEqual(stale_pages(root, write=True), ["engines/demo.md"])
            raw = (root / "engines/demo.md").read_bytes()
            self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))
            self.assertEqual(stale_pages(root), [])


if __name__ == "__main__":
    unittest.main()
