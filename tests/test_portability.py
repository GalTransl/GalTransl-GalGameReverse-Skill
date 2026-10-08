"""Static package checks; neither parses nor executes commercial game files."""

import ast
import hashlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PortabilityTests(unittest.TestCase):
    def test_archive_layer_does_not_import_script_layer(self):
        for path in (ROOT / "python" / "archives").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertFalse(any(alias.name == "python.engines" or
                                         alias.name.startswith("python.engines.")
                                         for alias in node.names), path.name)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    self.assertFalse(module == "python.engines" or
                                     module.startswith("python.engines.") or
                                     (node.level == 2 and
                                      (module == "engines" or module.startswith("engines."))), path.name)
                    if (node.level == 2 and not module) or (not node.level and module == "python"):
                        self.assertNotIn("engines", [alias.name for alias in node.names], path.name)

    def test_reference_modules_have_no_upstream_runtime_imports(self):
        forbidden = {"GalTransl", "PyQt5", "PySide6", "var_extract", "main_extract",
                     "lzss_s", "pandas", "rapidjson"}
        for path in (ROOT / "python").rglob("*.py"):
            with self.subTest(module=str(path.relative_to(ROOT))):
                tree = ast.parse(path.read_text(encoding="utf-8-sig"))
                imported = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imported.update(alias.name.split(".")[0] for alias in node.names)
                    elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                        imported.add(node.module.split(".")[0])
                self.assertFalse(imported & forbidden, imported & forbidden)

    def test_no_unapproved_native_or_game_binaries(self):
        forbidden = {".exe", ".dll", ".pyd", ".so", ".dylib", ".rpyc", ".xp3", ".rpa"}
        # UIF is a documented delivery asset, never a Python runtime dependency.
        allowed = {"assets/uif/winmm.dll":
                   "b83f896edd06662078eadd5ea7970ab5bfd320cd8ec319e72b1455473c897e41"}
        for relative, expected_hash in allowed.items():
            self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(),
                             expected_hash, relative)
        unexpected = sorted(path.relative_to(ROOT).as_posix() for path in ROOT.rglob("*")
                            if path.is_file() and path.suffix.lower() in forbidden
                            and path.relative_to(ROOT).as_posix() not in allowed)
        self.assertEqual(unexpected, [])

    def test_safety_paths_referenced_in_entry(self):
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        for required in ("guides/roundtrip-contract.md", "guides/detection.md",
                         "guides/validation-and-deployment.md", "provenance/NOTICE.md"):
            self.assertIn(required, text)


if __name__ == "__main__":
    unittest.main()
