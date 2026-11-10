"""Synthetic PE32/PE32+ fixtures for the read-only code-page probe."""
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from python.common.binary import FormatError
from python.common.codepage_probe import SJIS_TABLE_SIGNATURE, probe_codepage

ROOT = Path(__file__).resolve().parents[1]
TEXT_RVA, IDATA_RVA, RDATA_RVA = 0x1000, 0x2000, 0x3000
FILLER = ("Sleep", "ExitProcess", "CreateFileW", "ReadFile", "CloseHandle", "GetLastError",
          "HeapAlloc", "HeapFree", "GetProcessHeap", "VirtualAlloc", "VirtualFree", "lstrlenW")


def _align(value, alignment):
    return (value + alignment - 1) // alignment * alignment


def build_imports(imports, pointer):
    """imports: [(dll, [name or int ordinal])] -> (idata bytes, {name: iat rva})."""
    descriptors = 20 * (len(imports) + 1)
    blob = bytearray(descriptors)
    iat = {}
    entries = []
    for dll, names in imports:
        ilt_at = len(blob)
        blob += bytes(pointer * (len(names) + 1))
        iat_at = len(blob)
        blob += bytes(pointer * (len(names) + 1))
        entries.append((dll, names, ilt_at, iat_at))
    for index, (dll, names, ilt_at, iat_at) in enumerate(entries):
        for slot, name in enumerate(names):
            if isinstance(name, int):
                value = (1 << (8 * pointer - 1)) | name
            else:
                value = IDATA_RVA + len(blob)
                blob += b"\0\0" + name.encode() + b"\0"
                if len(blob) % 2:
                    blob += b"\0"
                iat[name] = IDATA_RVA + iat_at + slot * pointer
            for at in (ilt_at, iat_at):
                blob[at + slot * pointer:at + (slot + 1) * pointer] = value.to_bytes(pointer, "little")
        name_rva = IDATA_RVA + len(blob)
        blob += dll.encode() + b"\0"
        struct.pack_into("<IIIII", blob, 20 * index, IDATA_RVA + ilt_at, 0, 0, name_rva, IDATA_RVA + iat_at)
    return bytes(blob), iat


def build_pe(code_fn, imports, *, x64=False, filler=True, text_name=b".text", rdata=b"",
             image_base=None):
    """Minimal PE with .text (exec), .idata and optional .rdata sections.

    code_fn(iat, image_base) returns the .text bytes; iat maps imported
    names to IAT slot RVAs.
    """
    pointer = 8 if x64 else 4
    image_base = image_base if image_base is not None else (0x140000000 if x64 else 0x400000)
    imports = list(imports)
    if filler:
        imports.append(("KERNEL32.dll", list(FILLER)))
    idata, iat = build_imports(imports, pointer)
    text = code_fn(iat, image_base)
    sections = [(text_name, TEXT_RVA, text, 0x60000020), (b".idata", IDATA_RVA, idata, 0xC0000040)]
    if rdata:
        sections.append((b".rdata", RDATA_RVA, rdata, 0x40000040))
    optional_size = 240 if x64 else 224
    header_size = 0x400
    out = bytearray(header_size)
    out[:2] = b"MZ"
    struct.pack_into("<I", out, 0x3C, 0x40)
    out[0x40:0x44] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", out, 0x44, 0x8664 if x64 else 0x14C, len(sections), 0, 0, 0, optional_size,
                     0x0102)
    opt = 0x58
    struct.pack_into("<H", out, opt, 0x20B if x64 else 0x10B)
    if x64:
        struct.pack_into("<Q", out, opt + 24, image_base)
    else:
        struct.pack_into("<I", out, opt + 28, image_base)
    struct.pack_into("<II", out, opt + 32, 0x1000, 0x200)
    struct.pack_into("<I", out, opt + 56, 0x4000 + _align(len(rdata), 0x1000))
    struct.pack_into("<I", out, opt + 60, header_size)
    dirs_at = opt + (108 if x64 else 92)
    struct.pack_into("<I", out, dirs_at, 16)
    struct.pack_into("<II", out, dirs_at + 4 + 8, IDATA_RVA, len(idata))
    table = opt + optional_size
    raw = header_size
    payload = bytearray()
    for index, (name, rva, blob, flags) in enumerate(sections):
        size = _align(len(blob), 0x200)
        struct.pack_into("<8sIIIIIIHHI", out, table + 40 * index, name, len(blob), rva, size, raw, 0, 0, 0, 0,
                         flags)
        payload += blob + bytes(size - len(blob))
        raw += size
    return bytes(out + payload)


def x86_call(iat, image_base, name):
    return b"\xFF\x15" + struct.pack("<I", image_base + iat[name])


def x64_call(iat, position, name):
    """call [rip+IAT] placed at .text offset position."""
    return b"\xFF\x15" + struct.pack("<i", iat[name] - (TEXT_RVA + position + 6))


MBTWC_ARGS = b"\x6A\x00\x6A\x00\x6A\xFF\x50\x6A\x00"  # cch, out, -1, src, flags (before CodePage)
KERNEL_CONV = ("KERNEL32.dll", ["MultiByteToWideChar", "WideCharToMultiByte", "GetACP"])


class ProbeCase(unittest.TestCase):
    def probe(self, data, **options):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "game.exe"
            path.write_bytes(data)
            return probe_codepage(path, **options)

    def codepages(self, result):
        return [site["codepage"] for site in result["conversion_calls"]]


class X86Tests(ProbeCase):
    def test_direct_call_push_zero_is_acp(self):
        def code(iat, base):
            return (b"\x55\x8B\xEC" + MBTWC_ARGS + b"\x6A\x00" + x86_call(iat, base, "MultiByteToWideChar")
                    + b"\xC3")
        result = self.probe(build_pe(code, [KERNEL_CONV]))
        self.assertEqual(result["format"], "PE32")
        self.assertEqual(result["conversion_calls"][0]["rva"], f"0x{TEXT_RVA + 14:08X}")
        self.assertEqual(self.codepages(result), [0])
        site = result["conversion_calls"][0]
        self.assertEqual((site["codepage_name"], site["via"]), ("CP_ACP", "call [IAT]"))
        self.assertEqual((result["verdict"], result["confidence"]), ("acp-following", "weak"))
        self.assertFalse(result["packing"]["suspected"])
        self.assertIn("MultiByteToWideChar", {item["name"] for item in result["imports"]["relevant"]})

    def test_push_932_is_fixed(self):
        def code(iat, base):
            return (MBTWC_ARGS + b"\x68\xA4\x03\x00\x00" + x86_call(iat, base, "MultiByteToWideChar")
                    + b"\x68\xA4\x03\x00\x00" + x86_call(iat, base, "WideCharToMultiByte"))
        result = self.probe(build_pe(code, [KERNEL_CONV]))
        self.assertEqual(self.codepages(result), [932, 932])
        self.assertEqual((result["verdict"], result["confidence"]), ("fixed-cp932", "strong"))

    def test_mov_esi_iat_then_call_esi(self):
        def code(iat, base):
            load = b"\x8B\x35" + struct.pack("<I", base + iat["MultiByteToWideChar"])  # mov esi,[IAT]
            return (load + MBTWC_ARGS + b"\x6A\x00\xFF\xD6"       # call esi with CP_ACP
                    + b"\x6A\x01\x58"                               # unrelated code
                    + b"\x8B\xC8\xFF\xD6"                           # call esi without a push: not confirmed
                    + MBTWC_ARGS + b"\x53\xFF\xD6" + b"\xC3")      # push ebx: unknown
        result = self.probe(build_pe(code, [KERNEL_CONV]))
        self.assertEqual(self.codepages(result), [0, "unknown"])
        self.assertEqual(result["conversion_calls"][0]["via"], "mov esi,[IAT]; call esi")
        self.assertEqual(result["conversion_calls"][1]["basis"], "push ebx")
        self.assertEqual(result["verdict"], "acp-following")

    def test_xor_or_mov_register_before_push(self):
        def code(iat, base):
            return (MBTWC_ARGS + b"\x33\xDB\x53" + x86_call(iat, base, "MultiByteToWideChar")
                    + MBTWC_ARGS + b"\xBF\xA4\x03\x00\x00\x57" + x86_call(iat, base, "MultiByteToWideChar"))
        result = self.probe(build_pe(code, [KERNEL_CONV]))
        self.assertEqual(self.codepages(result), [0, 932])
        self.assertEqual(result["verdict"], "mixed")

    def test_mixed_and_implausible_or_interleaved_values(self):
        def code(iat, base):
            call = x86_call(iat, base, "MultiByteToWideChar")
            return (MBTWC_ARGS + b"\x6A\x00" + call
                    + MBTWC_ARGS + b"\x68\xA4\x03\x00\x00" + call
                    + MBTWC_ARGS + b"\x6A\x08" + call                    # 8 is not a code page
                    + MBTWC_ARGS + b"\x6A\x00\x89\x45\xFC" + call        # mov between push and call
                    + MBTWC_ARGS + b"\xFF\x75\x08" + call)               # push [ebp+8]
        result = self.probe(build_pe(code, [KERNEL_CONV]))
        self.assertEqual(self.codepages(result), [0, 932, "unknown", "unknown", "unknown"])
        self.assertIn("not a plausible code page", result["conversion_calls"][2]["basis"])
        self.assertEqual(result["conversion_calls"][3]["basis"], "no push immediately before the call")
        self.assertEqual(result["verdict"], "mixed")
        self.assertIsNone(result["confidence"])

    def test_jmp_thunk_call(self):
        def code(iat, base):
            body = MBTWC_ARGS + b"\x6A\x00\xE8"
            thunk_at = len(body) + 4 + 1
            body += struct.pack("<i", thunk_at - (len(body) + 4)) + b"\xC3"
            return body + b"\xFF\x25" + struct.pack("<I", base + iat["MultiByteToWideChar"])
        result = self.probe(build_pe(code, [KERNEL_CONV]))
        self.assertEqual(self.codepages(result), [0])
        self.assertEqual(result["conversion_calls"][0]["via"], "call jmp-thunk [IAT]")


class AcpBranchTests(ProbeCase):
    def test_getacp_charset_switch_is_strong_acp(self):
        def code(iat, base):
            unknown = MBTWC_ARGS + b"\x53" + x86_call(iat, base, "MultiByteToWideChar")
            getacp = (x86_call(iat, base, "GetACP") + b"\x05\x5C\xFC\xFF\xFF"   # add eax,-932
                      + b"\x83\xF8\x12\x77\x10"
                      + b"\xB0\x80\xC3\xB0\x88\xC3\xB0\x81\xC3\xB0\x86\xC3\xB0\x01\xC3")
            return unknown + getacp
        result = self.probe(build_pe(code, [KERNEL_CONV]))
        acp = result["getacp_calls"][0]
        self.assertEqual(acp["followed_by_codepages"], [932])
        self.assertEqual(acp["followed_by_charsets"], ["0x80", "0x81", "0x86", "0x88"])
        self.assertIn("GB2312_CHARSET", acp["charset_names"])
        self.assertTrue(acp["acp_branch"])
        self.assertEqual(self.codepages(result), ["unknown"])
        self.assertEqual((result["verdict"], result["confidence"]), ("acp-following", "strong"))

    def test_getacp_followed_by_compare_chain(self):
        def code(iat, base):
            return (x86_call(iat, base, "GetACP")
                    + b"\x2D\xA4\x03\x00\x00\x74\x10"     # sub eax,932; jz
                    + b"\x83\xE8\x04\x74\x0C"             # sub eax,4 (936); jz
                    + b"\x83\xE8\x0D\x74\x08"             # sub eax,13 (949); jz
                    + b"\x48\x74\x05\xC3")                # dec eax (950); jz
        result = self.probe(build_pe(code, [KERNEL_CONV]))
        self.assertEqual(result["getacp_calls"][0]["followed_by_codepages"], [932, 936, 949, 950])
        self.assertEqual(sorted({c["basis"] for c in result["codepage_compares"]}), ["direct", "sub-chain"])
        self.assertEqual(result["verdict"], "acp-following")

    def test_distant_compares_alone_are_not_counted(self):
        def code(iat, base):
            far = b"\x90" * 400
            return (x86_call(iat, base, "GetACP") + b"\xC3" + far
                    + b"\x3D\xA4\x03\x00\x00\x74\x02\x81\xF9\xA8\x03\x00\x00\xC3")
        result = self.probe(build_pe(code, [KERNEL_CONV]))
        self.assertEqual(result["summary"]["compare_codepages"], [932, 936])
        self.assertEqual([c["instruction"] for c in result["codepage_compares"]], ["cmp eax,imm32", "cmp ecx,imm32"])
        self.assertFalse(result["getacp_calls"][0]["acp_branch"])
        self.assertEqual(result["verdict"], "undetermined")
        self.assertTrue(any("not counted" in reason for reason in result["reasons"]))


class X64Tests(ProbeCase):
    def test_ecx_immediates(self):
        def code(iat, base):
            out = bytearray()
            for prefix in (b"\x41\xB9\xA4\x03\x00\x00\x33\xC9",       # mov r9d,932; xor ecx,ecx -> 0
                           b"\xB9\xA8\x03\x00\x00\x45\x33\xC9",       # mov ecx,936; xor r9d,r9d -> 936
                           b"\x41\xB9\x00\x00\x00\x00",               # r9d only -> unknown
                           b"\xB9\xA4\x03\x00\x00\x8B\x4D\x60"):      # overwritten by mov ecx,[rbp+60h]
                out += b"\x48\x83\xEC\x28" + prefix
                out += x64_call(iat, len(out), "MultiByteToWideChar")
            return bytes(out + b"\xC3")
        result = self.probe(build_pe(code, [KERNEL_CONV], x64=True))
        self.assertEqual((result["format"], result["architecture"]), ("PE32+", "x64"))
        self.assertEqual(self.codepages(result), [0, 936, "unknown", "unknown"])
        self.assertEqual(result["conversion_calls"][0]["basis"], "xor ecx,ecx")
        self.assertEqual(result["verdict"], "acp-following")

    def test_x64_fixed_and_window_stops_at_previous_call(self):
        def code(iat, base):
            out = bytearray(b"\xB9\xA4\x03\x00\x00")
            out += x64_call(iat, len(out), "WideCharToMultiByte")
            out += b"\xB9\x00\x00\x00\x00\xE8\x00\x00\x00\x00"       # ecx clobbered by a call
            out += x64_call(iat, len(out), "MultiByteToWideChar")
            return bytes(out + b"\xC3")
        result = self.probe(build_pe(code, [KERNEL_CONV], x64=True))
        self.assertEqual(self.codepages(result), [932, "unknown"])
        self.assertEqual(result["verdict"], "fixed-cp932")
        self.assertEqual(result["confidence"], "weak")

    def test_x64_mov_reg_then_call_reg(self):
        def code(iat, base):
            out = bytearray(b"\x48\x8B\x05")
            out += struct.pack("<i", iat["MultiByteToWideChar"] - (TEXT_RVA + 7))
            out += b"\x33\xC9\xFF\xD0\xC3"
            return bytes(out)
        result = self.probe(build_pe(code, [KERNEL_CONV], x64=True))
        self.assertEqual(self.codepages(result), [0])
        self.assertEqual(result["conversion_calls"][0]["via"], "mov rax,[rip+IAT]; call rax")


class UndeterminedAndPackingTests(ProbeCase):
    def test_no_conversion_imports_with_ansi_drawing(self):
        def code(iat, base):
            return x86_call(iat, base, "TextOutA") + b"\xC3"
        result = self.probe(build_pe(code, [("GDI32.dll", ["TextOutA", "CreateFontA"]),
                                            ("KERNEL32.dll", ["GetCPInfo", 123])]))
        self.assertEqual(result["verdict"], "undetermined")
        self.assertEqual(result["conversion_calls"], [])
        self.assertTrue(any("ANSI (A) GDI" in reason for reason in result["reasons"]))
        self.assertTrue(any("no named MultiByteToWideChar" in reason for reason in result["reasons"]))
        self.assertEqual(result["imports"]["relevant_ordinals"][0]["ordinal"], 123)

    def test_packer_section_downgrades(self):
        def code(iat, base):
            return MBTWC_ARGS + b"\x6A\x00" + x86_call(iat, base, "MultiByteToWideChar")
        result = self.probe(build_pe(code, [KERNEL_CONV], text_name=b"UPX1"))
        self.assertEqual(self.codepages(result), [0])
        self.assertEqual(result["verdict"], "undetermined")
        self.assertTrue(result["packing"]["suspected"])
        self.assertIn("UPX", result["packing"]["hints"][0])

    def test_few_imports_and_high_entropy(self):
        def code(iat, base):
            return bytes((i * 167 + 13) & 0xFF for i in range(3000))
        result = self.probe(build_pe(code, [KERNEL_CONV], filler=False))
        hints = " ".join(result["packing"]["hints"])
        self.assertIn("named imports", hints)
        self.assertIn("entropy", hints)
        self.assertEqual(result["verdict"], "undetermined")

    def test_embedded_sjis_table(self):
        def acp(iat, base):
            return MBTWC_ARGS + b"\x6A\x00" + x86_call(iat, base, "MultiByteToWideChar")
        table = b"\0" * 16 + SJIS_TABLE_SIGNATURE + b"\0" * 16
        result = self.probe(build_pe(acp, [KERNEL_CONV], rdata=table))
        self.assertTrue(result["embedded_sjis_table"]["found"])
        self.assertEqual(result["verdict"], "mixed")
        result = self.probe(build_pe(lambda iat, base: b"\xC3", [KERNEL_CONV], rdata=table))
        self.assertEqual((result["verdict"], result["confidence"]), ("fixed-cp932", "strong"))

    def test_unreadable_import_table_is_a_packing_hint(self):
        data = bytearray(build_pe(lambda iat, base: b"\xC3", [KERNEL_CONV]))
        dirs_at = 0x58 + 92
        struct.pack_into("<I", data, dirs_at + 4 + 8, 0x7FFF0000)
        result = self.probe(bytes(data))
        self.assertIn("outside the file data", result["imports"]["error"])
        self.assertEqual(result["verdict"], "undetermined")


class MalformedTests(ProbeCase):
    def test_rejects_truncated_or_malformed_headers(self):
        good = build_pe(lambda iat, base: MBTWC_ARGS + b"\x6A\x00" + x86_call(iat, base, "MultiByteToWideChar"),
                        [KERNEL_CONV])
        cases = [b"", b"MZ" + bytes(10), good[:0x50], good[:0x100], b"ZM" + good[2:]]
        bad_offset = bytearray(good)
        struct.pack_into("<I", bad_offset, 0x3C, 0x7FFFFFF0)
        no_sections = bytearray(good)
        struct.pack_into("<H", no_sections, 0x46, 0)
        bad_magic = bytearray(good)
        struct.pack_into("<H", bad_magic, 0x58, 0x999)
        wrong_machine = bytearray(good)
        struct.pack_into("<H", wrong_machine, 0x44, 0x8664)
        for data in cases + [bytes(bad_offset), bytes(no_sections), bytes(bad_magic), bytes(wrong_machine)]:
            with self.assertRaises(FormatError):
                self.probe(data)
        with self.assertRaisesRegex(FormatError, "budget"):
            self.probe(good, max_bytes=len(good) - 1)

    def test_truncations_and_bit_flips_never_crash(self):
        good = build_pe(lambda iat, base: MBTWC_ARGS + b"\x6A\x00" + x86_call(iat, base, "MultiByteToWideChar"),
                        [KERNEL_CONV])
        variants = [good[:cut] for cut in range(0, len(good), 97)]
        for offset in list(range(0x3C, 0x200, 3)) + list(range(0x400, len(good), 41)):
            flipped = bytearray(good)
            flipped[offset] ^= 0xFF
            variants.append(bytes(flipped))
        for data in variants:
            try:
                result = self.probe(data)
            except FormatError:
                continue
            self.assertIn(result["verdict"], ("acp-following", "fixed-cp932", "mixed", "undetermined"))


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-B", "-m", "python.common.jis_workflow", "codepage",
                               *map(str, args)], cwd=ROOT, capture_output=True)

    def test_cli_single_and_multiple(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe = root / "游戏.exe"
            exe.write_bytes(build_pe(lambda iat, base: MBTWC_ARGS + b"\x6A\x00"
                                     + x86_call(iat, base, "MultiByteToWideChar"), [KERNEL_CONV]))
            (root / "bad.exe").write_bytes(b"MZ")
            single = self.run_cli(exe)
            self.assertEqual(single.returncode, 0, single.stderr)
            self.assertIn("游戏.exe", single.stdout.decode("utf-8"))  # UTF-8, not escaped
            report = json.loads(single.stdout)
            self.assertEqual((report["ok"], report["schema"], report["verdict"]),
                             (True, "codepage-probe/1", "acp-following"))
            self.assertIn("note", report)
            both = self.run_cli(exe, root / "bad.exe", "--max-sites", "0")
            self.assertEqual(both.returncode, 1)
            self.assertNotIn(b"Traceback", both.stderr)
            report = json.loads(both.stdout)
            self.assertFalse(report["ok"])
            self.assertEqual([item["ok"] for item in report["results"]], [True, False])
            self.assertIn("FormatError", report["results"][1]["error"])
            missing = self.run_cli(root / "missing.exe")
            self.assertEqual(missing.returncode, 1)
            self.assertFalse(json.loads(missing.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()
