"""Default CialloHook selection and forced ACP 932 (CialloHook [LocaleEmulator] + LE/LEP)."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from python.common import jis_workflow
from python.common.binary import FormatError
from python.common.contract import dump_rows
from python.common.jis_substitution import (CIALLOHOOK_INI, LOCALE_EMULATOR_DEPENDENCIES, LOCALE_EMULATOR_FILES,
                                            LOCALE_EMULATOR_INI, JisSubstitution)
from python.common.jis_workflow import finalize, prepare
from python.common.safety import write_new_tree
from python.engines import eagls_extract
from tests.test_codepage_probe import KERNEL_CONV, MBTWC_ARGS, build_pe, x64_call, x86_call
from tests import test_jis_workflow

ROOT = Path(__file__).resolve().parents[1]
LE_SECTION = ("[LocaleEmulator]\nEnable = true\nAnsiCodePage = 932\nOemCodePage = 932\nLocaleID = 0x411\n"
              "DefaultCharset = 128\nHookUILanguageAPI = 0\nTimezone = Tokyo Standard Time\n")


def x86_exe(codepage):
    """Synthetic 32-bit EXE whose MultiByteToWideChar call passes `codepage`."""
    def code(iat, base):
        out = b""
        for value in codepage:
            out += MBTWC_ARGS + b"\x68" + struct.pack("<I", value) + x86_call(iat, base, "MultiByteToWideChar")
        return out + b"\xC3"
    return build_pe(code, [KERNEL_CONV])


def x64_exe(codepage):
    def code(iat, base):
        out = bytearray()
        for value in codepage:
            out += b"\xB9" + struct.pack("<I", value)
            out += x64_call(iat, len(out), "MultiByteToWideChar")
        return bytes(out + b"\xC3")
    return build_pe(code, [KERNEL_CONV], x64=True)


def machine(raw):
    return struct.unpack_from("<H", raw, struct.unpack_from("<I", raw, 0x3C)[0] + 4)[0]


class ArtifactTests(unittest.TestCase):
    def codec(self):
        codec = JisSubstitution()
        codec.encode("你好")
        return codec

    def test_force_x86_and_x64_dependencies(self):
        for hook, arch, bits in (("ciallohook", "x86", 0x14C), ("ciallohook-x64", "x64", 0x8664)):
            with self.subTest(hook=hook):
                artifacts = dict(self.codec().artifacts(hook=hook, force_cp932=True))
                expected = LOCALE_EMULATOR_DEPENDENCIES[arch]
                self.assertTrue(set(expected) <= set(artifacts))
                self.assertFalse(set(LOCALE_EMULATOR_FILES) - set(expected) & set(artifacts))
                for name in expected:
                    raw = artifacts[name]
                    self.assertEqual(hashlib.sha256(raw).hexdigest(), LOCALE_EMULATOR_FILES[name][1])
                    self.assertEqual(machine(raw), bits)
                ini = artifacts["version.ini"].decode("utf-8")
                self.assertTrue(ini.startswith(CIALLOHOOK_INI))
                self.assertIn(LE_SECTION, ini)
                self.assertEqual(ini.count("[LocaleEmulator]"), 1)
                report = json.loads(artifacts["jis-mapping.json"])["hook"]
                self.assertTrue(report["force_cp932"])
                self.assertEqual(set(report["locale_emulator_files"]), set(expected))
                self.assertIn("强制 932", artifacts["JIS-部署说明.txt"].decode("utf-8"))
        self.assertEqual(LOCALE_EMULATOR_DEPENDENCIES["x86"][:2], ("LoaderDll_x86.dll", "LocaleEmulatorPlus_x86.dll"))

    def test_off_keeps_previous_ini_and_no_dependencies(self):
        artifacts = dict(self.codec().artifacts(hook="ciallohook"))
        self.assertEqual(artifacts["version.ini"], CIALLOHOOK_INI.encode("utf-8"))
        self.assertFalse(set(LOCALE_EMULATOR_FILES) & set(artifacts))
        self.assertNotIn("强制 932", artifacts["JIS-部署说明.txt"].decode("utf-8"))
        self.assertTrue(LOCALE_EMULATOR_INI.endswith("Timezone = Tokyo Standard Time\n"))

    def test_force_requires_ciallohook_and_checks_hash(self):
        codec = self.codec()
        for options in ({"hook": "uif"}, {"include_hook": False}):
            with self.assertRaisesRegex(FormatError, "CialloHook"):
                codec.artifacts(force_cp932=True, **options)
        # Rejected before the pass-through shortcut as well.
        with self.assertRaises(FormatError):
            JisSubstitution().artifacts(hook="uif", force_cp932=True)
        package, digest, bits = LOCALE_EMULATOR_FILES["LocaleEmulator.dll"]
        with mock.patch.dict(LOCALE_EMULATOR_FILES, {"LocaleEmulator.dll": (package, "0" * 64, bits)}):
            with self.assertRaisesRegex(FormatError, "hash mismatch"):
                codec.artifacts(hook="ciallohook", force_cp932=True)
            codec.artifacts(hook="ciallohook-x64", force_cp932=True)  # x64 does not ship LE

    def test_provenance_matches_pinned_files(self):
        recorded = json.loads((ROOT / "provenance/jis-substitution.json").read_bytes())["bundled_locale_emulator"]
        expected = {f"assets/ciallohook/locale-emulator/{package}/{name}": (digest, f"0x{bits:04X}")
                    for name, (package, digest, bits) in LOCALE_EMULATOR_FILES.items()}
        self.assertEqual({k: (v["sha256"], v["pe_machine"]) for k, v in recorded["files"].items()}, expected)
        for relative, item in recorded["files"].items():
            raw = (ROOT / relative).read_bytes()
            self.assertEqual((len(raw), machine(raw)), (item["size"], int(item["pe_machine"], 16)))

    def test_default_hook_is_ciallohook(self):
        artifacts = dict(self.codec().artifacts())
        self.assertIn("version.dll", artifacts)
        self.assertNotIn("winmm.dll", artifacts)


class PrepareDecisionTests(unittest.TestCase):
    def workspace(self, root):
        write_new_tree(root / "work", [
            ("gt_input/a.json", dump_rows([{"message": "原"}])),
            ("gt_output/a.json", dump_rows([{"message": "测"}])),
            ("original/source.bin", b"source"), ("metadata/a.json", b"{}")])
        return root / "work"

    def prepare(self, root, name, exe_bytes=None, **options):
        exe = None
        if exe_bytes is not None:
            exe = root / f"{name}.exe"
            exe.write_bytes(exe_bytes)
        options.setdefault("include_hook", True)
        info = prepare(self.workspace(root) if not (root / "work").exists() else root / "work", root / name,
                       encoding="cp932", proxy_policy="unused", exe=exe, **options)
        plan = json.loads((root / name / "jis-plan.json").read_bytes())
        support = {n[len("support/"):] for n in plan["support"]}
        return info, plan, support

    def test_auto_verdicts(self):
        cases = [("acp86", x86_exe([0]), "ciallohook", "acp-following", True, "x86"),
                 ("fixed86", x86_exe([932, 932]), "ciallohook", "fixed-cp932", False, "x86"),
                 ("mixed86", x86_exe([0, 932]), "ciallohook", "mixed", True, "x86"),
                 ("acp64", x64_exe([0]), "ciallohook-x64", "acp-following", True, "x64"),
                 ("fixed64", x64_exe([932, 932]), "ciallohook-x64", "fixed-cp932", False, "x64")]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, exe, hook, verdict, force, arch in cases:
                with self.subTest(name=name):
                    info, plan, support = self.prepare(root, name, exe)
                    self.assertEqual((plan["hook"], plan["force_cp932"]), (hook, force))
                    record = plan["runtime_codepage"]
                    self.assertEqual((record["verdict"], record["force_cp932"], record["force_cp932_mode"]),
                                     (verdict, force, "auto"))
                    self.assertTrue(record["decision_reason"])
                    self.assertEqual((info["hook"], info["force_cp932"]), (hook, force))
                    self.assertEqual(set(LOCALE_EMULATOR_DEPENDENCIES[arch]) <= support, force)
                    self.assertEqual(plan["warnings"], [])
                    ini = (root / name / "support/version.ini").read_text(encoding="utf-8")
                    self.assertEqual("[LocaleEmulator]" in ini, force)

    def test_probe_error_is_undetermined_and_forces(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.object(jis_workflow, "probe_codepage", side_effect=FormatError("unsupported PE")):
                _, plan, support = self.prepare(root, "broken", x86_exe([932]))
            record = plan["runtime_codepage"]
            self.assertEqual((record["verdict"], record["force_cp932"]), ("undetermined", True))
            self.assertIn("unsupported PE", record["probe_error"])
            self.assertIn("LoaderDll.dll", support)

    def test_manual_overrides_and_uif(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, plan, support = self.prepare(root, "off", x86_exe([0]), force_cp932="off")
            self.assertFalse(plan["force_cp932"])
            self.assertEqual(plan["runtime_codepage"]["verdict"], "acp-following")
            self.assertTrue(plan["warnings"])
            self.assertFalse(set(LOCALE_EMULATOR_FILES) & support)
            _, plan, support = self.prepare(root, "on", x86_exe([932, 932]), force_cp932="on")
            self.assertTrue(plan["force_cp932"])
            self.assertEqual(plan["runtime_codepage"]["verdict"], "fixed-cp932")
            self.assertIn("LocaleEmulator.dll", support)
            _, plan, _ = self.prepare(root, "on-noexe", force_cp932=True, hook="ciallohook-x64")
            self.assertTrue(plan["force_cp932"])
            for name, options in (("uif-on", {"hook": "uif", "force_cp932": "on"}),
                                  ("none-on", {"include_hook": False, "force_cp932": "on"})):
                with self.assertRaisesRegex(FormatError, "CialloHook"):
                    self.prepare(root, name, x86_exe([0]), **options)
                self.assertFalse((root / name).exists())
            # Auto + explicit UIF fallback: no forced 932, but a warning.
            _, plan, support = self.prepare(root, "uif-auto", x86_exe([0]), hook="uif")
            self.assertEqual((plan["hook"], plan["force_cp932"]), ("uif", False))
            self.assertTrue(plan["warnings"])
            self.assertIn("winmm.dll", support)

    def test_no_exe_auto_hook_is_none_with_warnings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            info, plan, support = self.prepare(root, "noexe")
            self.assertEqual((plan["hook"], plan["include_hook"], plan["force_cp932"]), (None, False, False))
            self.assertEqual(len(info["warnings"]), 2)
            self.assertIsNone(plan["runtime_codepage"]["verdict"])
            self.assertFalse({"version.dll", "winmm.dll"} & support)
            with self.assertRaisesRegex(FormatError, "no bundled hook"):
                exe = bytearray(x86_exe([0]))
                struct.pack_into("<H", exe, struct.unpack_from("<I", exe, 0x3C)[0] + 4, 0xAA64)
                self.prepare(root, "arm", bytes(exe))


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-B", "-m", "python.common.jis_workflow", *map(str, args)],
                              cwd=ROOT, capture_output=True)

    def test_cli_defaults_and_legacy_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work = PrepareDecisionTests.workspace(None, root)
            exe64 = root / "game64.exe"
            exe64.write_bytes(x64_exe([0]))
            exe86 = root / "game86.exe"
            exe86.write_bytes(x86_exe([932, 932]))
            base = ("prepare", work)
            common = ("--encoding", "cp932", "--proxy-policy", "unused")
            result = self.run_cli(*base, root / "a", *common, "--exe", exe64)
            self.assertEqual(result.returncode, 0, result.stderr)
            out = json.loads(result.stdout.decode("utf-8"))
            self.assertEqual((out["hook"], out["force_cp932"]), ("ciallohook-x64", True))
            self.assertEqual(out["runtime_codepage"]["verdict"], "acp-following")
            self.assertTrue((root / "a/support/LocaleEmulatorPlus_x64.dll").is_file())
            result = self.run_cli(*base, root / "b", *common)
            out = json.loads(result.stdout.decode("utf-8"))
            self.assertEqual((result.returncode, out["hook"], out["force_cp932"]), (0, None, False))
            self.assertTrue(any("--exe" in warning for warning in out["warnings"]))
            result = self.run_cli(*base, root / "c", *common, "--hook", "x86", "--exe", exe86)
            out = json.loads(result.stdout.decode("utf-8"))
            self.assertEqual((result.returncode, out["hook"], out["force_cp932"]), (0, "uif", False))
            self.assertTrue((root / "c/support/winmm.dll").is_file())
            result = self.run_cli(*base, root / "d", *common, "--hook", "uif-x86", "--force-cp932", "on")
            self.assertEqual(result.returncode, 1)
            self.assertNotIn(b"Traceback", result.stderr)
            self.assertFalse((root / "d").exists())
            result = self.run_cli(*base, root / "e", *common, "--hook", "ciallohook-x86", "--exe", exe86,
                                  "--force-cp932", "on")
            out = json.loads(result.stdout.decode("utf-8"))
            self.assertEqual((result.returncode, out["hook"], out["force_cp932"]), (0, "ciallohook", True))
            result = self.run_cli(*base, root / "f", *common, "--hook", "none", "--exe", exe86)
            out = json.loads(result.stdout.decode("utf-8"))
            self.assertEqual((result.returncode, out["hook"], out["force_cp932"]), (0, None, False))
            arch = json.loads(self.run_cli("arch", exe86).stdout)
            self.assertEqual(arch["auto_hook"], "ciallohook")


class FinalizeTests(unittest.TestCase):
    def test_force_cp932_published_after_engine_readback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work, profile = test_jis_workflow.WorkspaceTests.fixture(None, root)
            exe = root / "game.exe"
            exe.write_bytes(x86_exe([0]))
            prepare(work, root / "prepared", encoding="cp932", proxy_policy="unused", include_hook=True, exe=exe)
            eagls_extract.rebuild(root / "prepared/workspace", root / "engine-output")
            eagls_extract.extract(root / "engine-output/script", root / "readback", profile=profile, key=b"key")
            report = finalize(root / "prepared", root / "engine-output", root / "readback/gt_input", root / "delivery")
            self.assertTrue(report["force_cp932"])
            self.assertEqual(report["runtime_codepage"]["verdict"], "acp-following")
            for name in ("version.dll", "version.ini", *LOCALE_EMULATOR_DEPENDENCIES["x86"]):
                self.assertTrue((root / "delivery" / name).is_file(), name)
            self.assertIn("[LocaleEmulator]", (root / "delivery/version.ini").read_text(encoding="utf-8"))
            delivered = json.loads((root / "delivery/reports/jis-workflow.json").read_bytes())
            self.assertTrue(delivered["force_cp932"])


if __name__ == "__main__":
    unittest.main()
