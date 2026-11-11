import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

from python.common import rizin_probe
from python.common.codepage_probe import analyze_codepage
from python.common.rizin_probe import (BUNDLED, RizinUnavailable, charset_branch, classify_conversion,
                                       find_rizin, json_values, verdict, x64_args, x86_args)
from tests.test_codepage_probe import KERNEL_CONV, build_pe, x86_call


def ops(*lines, kind=None):
    return [{"disasm": line, "type": kind or ("push" if line.startswith("push") else "mov")} for line in lines]


def conv(codepage, purpose="text-or-unknown"):
    return {"codepage": codepage, "purpose": purpose}


class ParserTests(unittest.TestCase):
    def test_x86_args_nearest_push_is_codepage(self):
        args = x86_args(ops("push 0x104", "push eax", "push 0xffffffff", "push esi", "push 0x01", "push 0x00"), 6)
        self.assertEqual([a["value"] for a in args], [0, 1, None, 0xFFFFFFFF, None, 0x104])
        cls = classify_conversion("MultiByteToWideChar", args)
        self.assertEqual((cls["codepage"], cls["codepage_name"], cls["purpose"]), (0, "CP_ACP", "path"))

    def test_x86_register_resolution_and_control_flow_boundary(self):
        seq = ops("xor ebx, ebx", "push 0x10", "push ebx")
        self.assertEqual(x86_args(seq, 2)[0]["value"], 0)
        seq = ops("mov edi, 0x3a4", "push edi")
        self.assertEqual(x86_args(seq, 1)[0]["value"], 932)
        seq = [{"disasm": "mov ebx, 0x3a4", "type": "mov"}, {"disasm": "call fcn", "type": "call"},
               {"disasm": "push ebx", "type": "rpush"}]
        self.assertIsNone(x86_args(seq, 1)[0]["value"])
        cls = classify_conversion("MultiByteToWideChar", x86_args(ops("mov ebx, edx", "push ebx"), 1))
        self.assertEqual((cls["codepage"], cls["codepage_source"]), ("unknown", "caller-argument"))
        cls = classify_conversion("MultiByteToWideChar", x86_args(ops("push dword [ebp+0x8]"), 1))
        self.assertEqual(cls["codepage_source"], "caller-argument")

    def test_x64_registers_and_stack_slots(self):
        seq = ops("mov dword [rsp+0x28], 0x104", "mov r9d, 0xffffffff", "xor edx, edx", "mov ecx, 0x3a8")
        args = x64_args(seq, 6)
        self.assertEqual(args[0]["value"], 936)
        self.assertEqual(args[1]["value"], 0)
        self.assertEqual(args[5]["value"], 0x104)
        self.assertIsNone(x64_args(ops("mov ecx, dword [rbx]"), 1)[0]["value"])

    def test_charset_branch(self):
        branch = charset_branch(ops("add eax, 0xfffffc5c", "mov al, 0x80", "mov al, 0x86", "mov al, 0x01"))
        self.assertEqual(branch["codepages"], [932])
        self.assertEqual(branch["charsets"], ["0x80", "0x86"])
        self.assertTrue(branch["acp_branch"])
        self.assertFalse(charset_branch(ops("mov al, 0x01", "cmp eax, 0x3a4"))["acp_branch"])

    def test_verdict_rules(self):
        branch = [{"acp_branch": True}]
        self.assertEqual(verdict([conv(0, "path")], branch)[:2], ("acp-following", "strong"))
        self.assertEqual(verdict([conv(0)], [])[:2], ("acp-following", "medium"))
        self.assertEqual(verdict([conv(932), conv(932)], [])[:2], ("fixed-cp932", "strong"))
        self.assertEqual(verdict([conv(0, "path"), conv(932)], [])[:2], ("fixed-cp932", "medium"))
        self.assertEqual(verdict([conv(0), conv(932)], [])[0], "mixed")
        self.assertEqual(verdict([conv(3)], [], embedded_sjis=True)[0], "mixed")
        self.assertEqual(verdict([conv("unknown")], [])[0], "undetermined")

    def test_json_stream_and_lookup(self):
        self.assertEqual(json_values('[1]\n[{"a":2}]\n{"b":3}'), [[1], [{"a": 2}], {"b": 3}])
        self.assertEqual(json_values(""), [])
        with mock.patch.dict(os.environ, {"GALTRANSL_RIZIN": "off"}):
            self.assertIsNone(find_rizin())
        with self.assertRaises(RizinUnavailable):
            find_rizin("C:/no/such/rizin.exe")

    def test_fallback_when_rizin_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "game.exe"
            path.write_bytes(build_pe(lambda iat, base: b"\x6A\x00" + x86_call(iat, base, "MultiByteToWideChar")
                                      + b"\xC3", [KERNEL_CONV]))
            result = analyze_codepage(path, rizin="off")
            self.assertEqual(result["verdict_source"], "byte-probe")
            self.assertIn("error", result["rizin"])


@unittest.skipUnless(os.name == "nt" and BUNDLED.is_file(), "bundled rizin is Windows-only")
class BundledRizinTests(unittest.TestCase):
    def build(self, tmp, cch, codepage):
        def code(iat, base):
            body = b"\x55\x89\xE5"  # push ebp; mov ebp, esp
            body += b"\x68" + struct.pack("<I", cch) + b"\x6A\x00\x6A\xFF\x50\x6A\x01"
            body += b"\x68" + struct.pack("<I", codepage) + x86_call(iat, base, "MultiByteToWideChar")
            return body + b"\x5D\xC3"
        path = Path(tmp) / f"game_{cch:x}_{codepage}.exe"
        path.write_bytes(build_pe(code, [KERNEL_CONV]))
        return path

    def test_bundled_rizin_classifies_text_and_path_conversions(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = rizin_probe.probe(self.build(tmp, 0x400, 0), rizin=str(BUNDLED))
            self.assertEqual(text["conversion_calls"][0]["codepage"], 0)
            self.assertEqual(text["conversion_calls"][0]["purpose"], "text-or-unknown")
            self.assertEqual(text["verdict"], "acp-following")
            path = rizin_probe.probe(self.build(tmp, 0x104, 0), rizin=str(BUNDLED))
            self.assertEqual(path["conversion_calls"][0]["purpose"], "path")
            self.assertEqual(path["verdict"], "undetermined")
            fixed = analyze_codepage(self.build(tmp, 0x400, 932), rizin=str(BUNDLED))
            self.assertEqual((fixed["verdict_source"], fixed["verdict"]), ("rizin", "fixed-cp932"))
            self.assertIn("byte_verdict", fixed)


if __name__ == "__main__":
    unittest.main()
