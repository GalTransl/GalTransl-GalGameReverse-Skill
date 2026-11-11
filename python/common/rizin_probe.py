"""Optional static deep probe of a game EXE with the bundled rizin.

Static analysis only: rizin opens the file read-only (no ``-w``, no ``-d``),
with ``-N`` (no user rc files) and ``cfg.sandbox=true``; the game is never
started. Runs are bounded by a timeout. Without a usable rizin the callers
fall back to the byte-pattern probe in ``codepage_probe``.

The probe refines the code-page evidence:
- every MultiByteToWideChar / WideCharToMultiByte call site with its CodePage
  argument read from the instructions before the call, and whether the call
  converts a path (a MAX_PATH-sized buffer) rather than text;
- GetACP call sites whose containing function maps code pages to font
  charsets (0x80/0x86/0x88/0x81);
- font creation call sites, with an immediate CreateFontA/W charset.

Bundled build: assets/rizin (rizin 0.10.0, Windows-only, LGPL-3.0); see
assets/rizin/README.md.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BUNDLED = ROOT / "assets" / "rizin" / "bin" / "rizin.exe"
ENV = "GALTRANSL_RIZIN"
DEFAULT_TIMEOUT = 180
MAX_OUTPUT = 64 << 20
SCHEMA = "rizin-codepage-probe/1"

CONVERSIONS = ("MultiByteToWideChar", "WideCharToMultiByte")
FONT_APIS = ("CreateFontA", "CreateFontW", "CreateFontIndirectA", "CreateFontIndirectW",
             "D3DXCreateFontA", "D3DXCreateFontW", "D3DXCreateFontIndirectA", "D3DXCreateFontIndirectW")
ACP_CODEPAGES = {0: "CP_ACP", 3: "CP_THREAD_ACP"}
NAMED_CODEPAGES = {0: "CP_ACP", 1: "CP_OEMCP", 3: "CP_THREAD_ACP", 932: "shift_jis", 936: "gbk",
                   949: "korean", 950: "big5", 65001: "utf-8"}
CJK_CHARSETS = {0x80: "SHIFTJIS_CHARSET", 0x86: "GB2312_CHARSET", 0x88: "CHINESEBIG5_CHARSET",
                0x81: "HANGUL_CHARSET"}
CJK_CODEPAGES = (932, 936, 949, 950)
PATH_BUFFERS = {0x104, 0x208, 0x7FFF, 0x8000}
STOP_TYPES = {"call", "ucall", "rcall", "icall", "ircall", "ret", "jmp", "ujmp", "rjmp", "ijmp", "irjmp",
              "cjmp", "ucjmp", "trap"}
X86_REGS = {"eax", "ebx", "ecx", "edx", "esi", "edi", "ebp"}
SEP = "GALTRANSL_RIZIN_SECTION_BREAK"


class RizinUnavailable(Exception):
    pass


def find_rizin(rizin="auto"):
    """Resolve the rizin executable: explicit path, $GALTRANSL_RIZIN, bundled.

    "off" (argument or environment) disables rizin. Returns None when no
    usable executable exists (the bundled build is Windows-only).
    """
    choice = rizin if rizin not in (None, "auto") else os.environ.get(ENV, "auto")
    if choice in ("off", "none", ""):
        return None
    if choice != "auto":
        path = Path(choice)
        if not path.is_file():
            raise RizinUnavailable(f"rizin not found: {path}")
        return path
    return BUNDLED if os.name == "nt" and BUNDLED.is_file() else None


def run(rizin, exe, commands, *, timeout=DEFAULT_TIMEOUT):
    """Run one read-only rizin batch; return the outputs split by section."""
    script = f"; echo {SEP}; ".join(commands)
    args = [str(rizin), "-N", "-q", "-e", "cfg.sandbox=true", "-e", "scr.color=0",
            "-e", "scr.interactive=false", "-e", "scr.utf8=false", "-c", script, str(Path(exe).resolve())]
    with tempfile.TemporaryDirectory() as cwd:
        try:
            done = subprocess.run(args, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
                                  timeout=timeout, check=False)
        except subprocess.TimeoutExpired as error:
            raise RizinUnavailable(f"rizin timed out after {timeout}s") from error
    if done.returncode != 0:
        raise RizinUnavailable(f"rizin exited with {done.returncode}")
    if len(done.stdout) > MAX_OUTPUT:
        raise RizinUnavailable("rizin output exceeds budget")
    text = done.stdout.decode("utf-8", "replace")
    return [part.strip() for part in text.split(SEP)]


def json_values(text):
    """Decode a stream of concatenated JSON values (iterator output)."""
    decoder, values, pos = json.JSONDecoder(), [], 0
    while True:
        while pos < len(text) and text[pos] not in "[{":
            pos += 1
        if pos >= len(text):
            return values
        value, pos = decoder.raw_decode(text, pos)
        values.append(value)


def _imm(text):
    text = text.strip()
    try:
        return int(text, 0) & 0xFFFFFFFF
    except ValueError:
        return None


def _resolve_reg(ops, reg):
    """Value of a register from the straight-line ops before its use."""
    for op in reversed(ops):
        dis = op.get("disasm", op.get("opcode", ""))
        m = re.match(r"(xor|sub)\s+(\w+),\s*(\w+)$", dis)
        if m and m[2] == reg and m[3] == reg:
            return 0, f"{m[1]} {reg},{reg}"
        m = re.match(r"mov\s+(\w+),\s*(.+)$", dis)
        if m and m[1] == reg:
            value = _imm(m[2])
            return (value, dis) if value is not None else (None, dis)
        if re.match(rf"\w+\s+{reg}\b", dis):
            return None, dis
    return None, None


def _straight(ops):
    """Ops after the last control transfer before the call site."""
    tail = []
    for op in reversed(ops):
        if op.get("type") in STOP_TYPES:
            break
        tail.append(op)
    return list(reversed(tail))


def x86_args(ops, count):
    """Stack arguments of a stdcall/cdecl call: nearest push is argument 0."""
    ops = _straight(ops)
    args, before = [], ops
    for i in range(len(ops) - 1, -1, -1):
        dis = ops[i].get("disasm", ops[i].get("opcode", ""))
        if not dis.startswith("push "):
            continue
        operand = dis[5:].strip()
        value, basis = _imm(operand), dis
        if value is None and operand in X86_REGS:
            value, found = _resolve_reg(ops[:i], operand)
            basis = f"{dis} <- {found}" if found else dis
        args.append({"value": value, "basis": basis})
        if len(args) == count:
            break
    return args


def x64_args(ops, count):
    """rcx, rdx, r8, r9 then [rsp+0x20+8*n]."""
    ops = _straight(ops)
    regs = ("ecx", "edx", "r8d", "r9d")
    full = ("rcx", "rdx", "r8", "r9")
    args = []
    for n in range(count):
        if n < 4:
            value, basis = _resolve_reg(ops, regs[n])
            if basis is None:
                value, basis = _resolve_reg(ops, full[n])
        else:
            value, basis = None, None
            slot = 0x20 + 8 * (n - 4)
            for op in reversed(ops):
                dis = op.get("disasm", op.get("opcode", ""))
                m = re.match(rf"mov\s+(?:dword|qword)\s+\[rsp\s*\+\s*0x{slot:x}\],\s*(.+)$", dis)
                if m:
                    value, basis = _imm(m[1]), dis
                    break
        args.append({"value": value, "basis": basis})
    return args


def call_args(ops, count, bits):
    return x64_args(ops, count) if bits == 64 else x86_args(ops, count)


def classify_conversion(api, args):
    codepage = args[0]["value"] if args else None
    size = args[5]["value"] if len(args) > 5 else None
    basis = (args[0]["basis"] or "") if args else ""
    if codepage is not None:
        source = "immediate"
    elif re.search(r"\[(?:ebp|rbp)\s*\+\s*0x", basis) or re.search(r"<- mov \w+,\s*(?:e?[cd]x|r[cd]x)$", basis):
        source = "caller-argument"
    else:
        source = "unresolved"
    purpose = "path" if size in PATH_BUFFERS else "text-or-unknown"
    return {"api": api, "codepage": codepage if codepage is not None else "unknown",
            "codepage_name": NAMED_CODEPAGES.get(codepage), "codepage_source": source,
            "buffer_size": size, "purpose": purpose,
            "basis": args[0]["basis"] if args else None}


def charset_branch(ops):
    """Font charsets and code pages a GetACP-using function maps between."""
    charsets, codepages = set(), set()
    for op in ops:
        dis = op.get("disasm", op.get("opcode", ""))
        m = re.match(r"mov\s+(?:byte\s+\[[^\]]+\]|al|bl|cl|dl|[re]?[abcd]x|e[sd]i|r\w+),\s*(0x[0-9a-f]+)$", dis)
        if m and int(m[1], 16) in CJK_CHARSETS:
            charsets.add(int(m[1], 16))
        m = re.match(r"(cmp|sub|add)\s+\w+,\s*(0x[0-9a-f]+|\d+)$", dis)
        if m:
            value = int(m[2], 0)
            if m[1] == "add":
                value = (-value) & 0xFFFFFFFF if value > 0x7FFFFFFF else None
            if value in CJK_CODEPAGES:
                codepages.add(value)
    return {"charsets": [f"0x{c:02X}" for c in sorted(charsets)],
            "charset_names": [CJK_CHARSETS[c] for c in sorted(charsets)],
            "codepages": sorted(codepages),
            "acp_branch": len(charsets) >= 2 or (len(charsets) >= 1 and len(codepages) >= 1)}


def _import_flags(imports, names):
    flags = {}
    for item in imports:
        name = item.get("name", "")
        if name in names and item.get("plt"):
            flags.setdefault(name, []).append(item["plt"])
    return flags


def verdict(conversions, getacp, embedded_sjis=False):
    text = [c for c in conversions if c["purpose"] != "path" and isinstance(c["codepage"], int)]
    acp = [c for c in text if c["codepage"] in ACP_CODEPAGES]
    fixed = [c for c in text if c["codepage"] == 932]
    branch = any(g["acp_branch"] for g in getacp)
    reasons = []
    paths = sum(c["purpose"] == "path" for c in conversions)
    if paths:
        reasons.append(f"{paths} conversion call(s) use a MAX_PATH-sized buffer: path conversion, not script text")
    if branch:
        reasons.append("GetACP result selects CJK font charsets: text display follows the system ACP")
    if acp:
        reasons.append(f"{len(acp)} non-path conversion(s) decode with CP_ACP/CP_THREAD_ACP")
    if fixed:
        reasons.append(f"{len(fixed)} non-path conversion(s) decode with a fixed 932")
    if embedded_sjis:
        reasons.append("embedded SJIS->Unicode table (byte probe): engine has its own CP932 decoder")
    unresolved = sum(not isinstance(c["codepage"], int) for c in conversions)
    if unresolved:
        reasons.append(f"{unresolved} conversion call(s) take the code page from a caller/register (unresolved)")
    acp_side, fixed_side = bool(acp or branch), bool(fixed or embedded_sjis)
    if acp_side and fixed_side:
        result, confidence = "mixed", None
    elif acp_side:
        result, confidence = "acp-following", "strong" if branch else "medium"
    elif fixed_side:
        result, confidence = "fixed-cp932", "strong" if len(fixed) >= 2 or embedded_sjis else "medium"
    else:
        result, confidence = "undetermined", None
        reasons.append("no non-path conversion with a resolved code page and no GetACP charset branch")
    return result, confidence, reasons


def probe(exe, *, rizin="auto", timeout=DEFAULT_TIMEOUT, embedded_sjis=False):
    """Deep code-page probe. Raises RizinUnavailable if rizin is missing/fails."""
    binary = find_rizin(rizin)
    if binary is None:
        raise RizinUnavailable("no rizin available (bundled build is Windows-only; set GALTRANSL_RIZIN)")
    info, imports = (json_values(part) for part in run(binary, exe, ["iIj", "iij"], timeout=timeout))
    info = info[0] if info else {}
    bits = info.get("bits", 32)
    imports = imports[0] if imports else []
    wanted = (*CONVERSIONS, "GetACP", *FONT_APIS)
    flags = _import_flags(imports, wanted)
    order = [(name, addr) for name in wanted for addr in flags.get(name, [])]
    commands = ["aaa"]
    for name, addr in order:
        window = "pdj 40" if name == "GetACP" else "pdj -24"
        commands += [f"axtj @ {addr}", f"{window} @@c:axtq @ {addr}"]
        if name == "GetACP":
            commands.append(f"pdfj @@c:axtq @ {addr}")
    sections = run(binary, exe, commands, timeout=timeout)[1:]
    conversions, getacp, fonts = [], [], []
    for i, (name, addr) in enumerate(order):
        step = 3 if name == "GetACP" else 2
        base = sum(3 if n == "GetACP" else 2 for n, _ in order[:i])
        xrefs = (json_values(sections[base]) or [[]])[0]
        windows = json_values(sections[base + 1])
        functions = json_values(sections[base + 2]) if step == 3 else []
        for j, ref in enumerate(xrefs):
            site = {"rva": f"0x{ref.get('from', 0):x}", "function": ref.get("fcn_name")}
            ops = windows[j] if j < len(windows) and isinstance(windows[j], list) else []
            if name in CONVERSIONS:
                conversions.append({**site, **classify_conversion(name, call_args(ops, 6, bits))})
            elif name == "GetACP":
                fn = functions[j] if j < len(functions) and isinstance(functions[j], dict) else {}
                getacp.append({**site, **charset_branch(fn.get("ops") or ops)})
            else:
                entry = {**site, "api": name}
                if name in ("CreateFontA", "CreateFontW"):
                    charset = call_args(ops, 9, bits)
                    value = charset[8]["value"] if len(charset) > 8 else None
                    entry["charset"] = f"0x{value:02X}" if isinstance(value, int) else "unknown"
                fonts.append(entry)
    result, confidence, reasons = verdict(conversions, getacp, embedded_sjis)
    return {"schema": SCHEMA, "rizin": str(binary), "bits": bits, "verdict": result, "confidence": confidence,
            "reasons": reasons, "conversion_calls": conversions, "getacp_calls": getacp, "font_calls": fonts,
            "note": "rizin 静态分析（只读、沙盒、不运行游戏）；码页来自调用前指令，路径转换已排除。"
                    "unresolved 的调用点可按 guides/rizin.md 手动追调用方。"}
