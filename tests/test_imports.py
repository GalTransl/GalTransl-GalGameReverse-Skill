"""Import every shipped reference in an isolated process without side effects."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

CHILD = r'''
import importlib
import os
import sys
sys.path.insert(0, sys.argv[1])

def guard(event, args):
    if event == "open":
        flags = args[2]
        forbidden = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
        if isinstance(flags, int) and flags & forbidden:
            raise RuntimeError("module import attempted a file write")
    if event in {"os.chdir", "os.mkdir", "os.remove", "os.rename", "os.rmdir",
                 "os.system", "subprocess.Popen", "socket.connect", "socket.bind"}:
        raise RuntimeError("module import attempted side effect: " + event)

sys.addaudithook(guard)
for name in sys.argv[2:]:
    importlib.import_module(name)
print("Imported " + str(len(sys.argv) - 2) + " modules without observed write/process/network side effects.")
'''


class ImportTests(unittest.TestCase):
    def test_reference_imports_are_independent_and_quiet(self):
        modules = [".".join(path.relative_to(ROOT).with_suffix("").parts)
                   for path in sorted((ROOT / "python").rglob("*.py"))
                   if path.name != "__init__.py" and "__pycache__" not in path.parts]
        self.assertTrue(modules)
        with tempfile.TemporaryDirectory() as work:
            process = subprocess.run([sys.executable, "-I", "-B", "-c", CHILD, str(ROOT), *modules],
                                     cwd=work, capture_output=True, text=True, timeout=60)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            self.assertEqual(process.stdout.strip(),
                             f"Imported {len(modules)} modules without observed write/process/network side effects.")
            self.assertEqual(process.stderr, "")
            self.assertEqual(list(Path(work).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
