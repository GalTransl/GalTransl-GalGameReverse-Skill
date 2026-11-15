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
