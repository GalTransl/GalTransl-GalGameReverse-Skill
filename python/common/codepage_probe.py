"""Read-only static probe: does an EXE decode text with a fixed CP932 or the system ACP?

New implementation for this skill. Parses PE32/PE32+ headers and the import
table, then pattern-matches executable sections for calls to
MultiByteToWideChar/WideCharToMultiByte and recovers the CodePage argument
conservatively, plus GetACP calls and code-page constant comparisons.

Limits by design: no disassembler, no emulation, no loading or executing the
file. Matching is byte-pattern based; anything that is not an unambiguous
immediate becomes "unknown" rather than a guess. Delay-load imports, APIs
resolved through GetProcAddress, packed/encrypted code and engines with their
own SJIS tables are not resolved. The verdict is evidence for choosing a
re-injection route, never proof of what the game displays.
"""
from collections import Counter
import math
from pathlib import Path
import stat
import struct

from .binary import FormatError

SCHEMA = "codepage-probe/1"
MAX_FILE_BYTES = 256 << 20
MAX_SECTIONS = 96
MAX_DESCRIPTORS = 4096
MAX_THUNKS = 65536
MAX_TOTAL_IMPORTS = 200000
MAX_NAME = 512
MAX_SITES = 100
PE_MACHINES = {0x14C: "x86", 0x8664: "x64", 0xAA64: "arm64"}

KERNEL_APIS = (
    "MultiByteToWideChar", "WideCharToMultiByte", "GetACP", "GetOEMCP", "GetCPInfo", "GetCPInfoExA",
    "GetCPInfoExW", "IsDBCSLeadByte", "IsDBCSLeadByteEx", "SetThreadLocale", "GetThreadLocale",
    "GetUserDefaultLCID", "GetSystemDefaultLCID")
GDI_APIS = tuple(f"{base}{suffix}" for base in (
    "CreateFont", "CreateFontIndirect", "TextOut", "ExtTextOut", "GetGlyphOutline", "GetTextExtentPoint32")
    for suffix in "AW")
USER_APIS = ("DrawTextA", "DrawTextW", "DrawTextExA", "DrawTextExW")
D3DX_APIS = ("D3DXCreateFontA", "D3DXCreateFontW", "D3DXCreateFontIndirectA", "D3DXCreateFontIndirectW")
CONVERSION_APIS = ("MultiByteToWideChar", "WideCharToMultiByte")
CALL_APIS = CONVERSION_APIS + ("GetACP",)

CODEPAGE_NAMES = {0: "CP_ACP", 1: "CP_OEMCP", 2: "CP_MACCP", 3: "CP_THREAD_ACP", 42: "CP_SYMBOL",
                  932: "shift_jis", 936: "gbk", 949: "korean", 950: "big5", 1200: "utf-16le",
                  54936: "gb18030", 65000: "utf-7", 65001: "utf-8"}
# Values a CodePage argument can reasonably take; any other immediate means
# the matched bytes were probably not the CodePage push, so report unknown.
PLAUSIBLE_CODEPAGES = frozenset(set(CODEPAGE_NAMES) | {
    37, 437, 850, 852, 866, 874, 1201, 1250, 1251, 1252, 1253, 1254, 1255, 1256, 1257, 1258, 1361,
    10000, 10001, 20127, 20932, 20936, 20949, 28591, 28592, 50220, 50221, 50222, 50225, 51932,
    51936, 51949, 52936})
ACP_CODEPAGES = frozenset({0, 3})  # follow the system / thread ANSI code page
COMPARE_CODEPAGES = (932, 936, 949, 950, 65001)

PACKER_SECTIONS = {
    "upx0": "UPX", "upx1": "UPX", "upx2": "UPX", ".vmp0": "VMProtect", ".vmp1": "VMProtect",
    ".vmp2": "VMProtect", ".themida": "Themida", ".winlice": "WinLicense", ".enigma1": "Enigma",
    ".enigma2": "Enigma", ".aspack": "ASPack", ".petite": "Petite", ".nsp0": "NsPack",
    ".nsp1": "NsPack", ".mpress1": "MPRESS", ".mpress2": "MPRESS", "pec2": "PECompact",
    "pecompact": "PECompact", ".packed": "packer", ".rlpack": "RLPack", ".svkp": "SVKP",
    ".bind": "SteamStub DRM wrapper", ".spack": "packer", ".perplex": "Perplex", ".yp": "Y0da"}
HIGH_ENTROPY = 7.2
FEW_IMPORTS = 12
# SJIS 0x8140..0x814B (JIS X 0208 row 1 start) as UTF-16LE: the head of an
# engine-internal SJIS->Unicode table. Stable across CP932/JIS variants.
SJIS_TABLE_SIGNATURE = struct.pack("<12H", 0x3000, 0x3001, 0x3002, 0xFF0C, 0xFF0E, 0x30FB,
                                   0xFF1A, 0xFF1B, 0xFF1F, 0xFF01, 0x309B, 0x309C)

NOTE = ("静态启发式，只作为选择回注路线的证据，仅在剧本已确认是 CP932 等多字节 ANSI 编码时有意义：CodePage=0 的调用也可能只用于路径或系统文本，"
        "未知调用可能正是剧本解码路径。最终须小样本实测：在目标系统码页下分别注入一行 GBK 与一行 JIS 代理文本对照显示。")


class _Pe:
    pass


def _u16(data, offset):
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def _read_bounded(path, limit):
    path = Path(path)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise FormatError(f"not an ordinary file: {path}")
    if info.st_size > limit:
        raise FormatError(f"PE exceeds {limit} byte budget: {path}")
    with path.open("rb") as stream:
        data = stream.read(min(info.st_size, limit) + 1)
    if len(data) > limit:
        raise FormatError(f"PE grew beyond {limit} byte budget: {path}")
    return data


def _parse_headers(data):
    if len(data) < 64 or data[:2] != b"MZ":
        raise FormatError("not a PE file (no MZ header)")
    pe_offset = _u32(data, 0x3C)
    if pe_offset > min(len(data), 1 << 20) - 24 or data[pe_offset:pe_offset + 4] != b"PE\0\0":
        raise FormatError("not a PE file (bad PE header offset/signature)")
    pe = _Pe()
    pe.data = data
    pe.machine, count = struct.unpack_from("<HH", data, pe_offset + 4)
    optional_size = _u16(data, pe_offset + 20)
    optional = pe_offset + 24
    if not 0 < count <= MAX_SECTIONS:
        raise FormatError(f"PE section count out of range: {count}")
    if optional_size < 2 or optional + optional_size > len(data):
        raise FormatError("truncated PE optional header")
    magic = _u16(data, optional)
    if magic == 0x10B:
        pe.format, pe.pointer, base_at, dirs_count_at = "PE32", 4, 28, 92
        pe.image_base = _u32(data, optional + base_at) if optional_size >= 32 else None
    elif magic == 0x20B:
        pe.format, pe.pointer, base_at, dirs_count_at = "PE32+", 8, 24, 108
        pe.image_base = struct.unpack_from("<Q", data, optional + base_at)[0] if optional_size >= 32 else None
    else:
        raise FormatError(f"unsupported PE optional header magic 0x{magic:X}")
    if optional_size < dirs_count_at + 4 or pe.image_base is None:
        raise FormatError("truncated PE optional header")
    pe.size_of_headers = _u32(data, optional + 60)
    dirs = min(_u32(data, optional + dirs_count_at), 16, (optional_size - dirs_count_at - 4) // 8)
    directory = [struct.unpack_from("<II", data, optional + dirs_count_at + 4 + 8 * i) for i in range(dirs)]
    pe.import_rva, pe.import_size = directory[1] if dirs > 1 else (0, 0)
    table = optional + optional_size
    if table + 40 * count > len(data):
        raise FormatError("truncated PE section table")
    pe.sections = []
    for index in range(count):
        raw_name, vsize, rva, raw_size, raw_ptr = struct.unpack_from("<8sIIII", data, table + 40 * index)
        characteristics = _u32(data, table + 40 * index + 36)
        name = raw_name.split(b"\0", 1)[0].decode("latin-1")
        if raw_ptr > len(data):
            raw_size = 0
        raw_size = min(raw_size, max(0, len(data) - raw_ptr))
        pe.sections.append({"name": name, "rva": rva, "vsize": vsize, "raw_ptr": raw_ptr, "raw_size": raw_size,
                            "executable": bool(characteristics & 0x20000020)})
    return pe


def _rva_offset(pe, rva, size):
    if 0 <= rva and rva + size <= min(pe.size_of_headers, 1 << 20, len(pe.data)):
        return rva
    for section in pe.sections:
        delta = rva - section["rva"]
        if 0 <= delta and delta + size <= section["raw_size"]:
            return section["raw_ptr"] + delta
    raise FormatError(f"RVA 0x{rva:X} is outside the file data")


def _cstring(data, pe, rva):
    offset = _rva_offset(pe, rva, 1)
    end = data.find(b"\0", offset, offset + MAX_NAME + 1)
    if end < 0:
        raise FormatError(f"unterminated or overlong import name at RVA 0x{rva:X}")
    return data[offset:end].decode("latin-1")


def _imports(data, pe):
    """Return [(dll, name or None, ordinal or None, iat_rva)] with bounded walks."""
    if not pe.import_rva:
        return []
    result, descriptor = [], pe.import_rva
    for _ in range(MAX_DESCRIPTORS):
        offset = _rva_offset(pe, descriptor, 20)
        lookup, _, _, name_rva, iat = struct.unpack_from("<IIIII", data, offset)
        if not (lookup or name_rva or iat):
            return result
        dll = _cstring(data, pe, name_rva)
        thunk = lookup or iat
        ordinal_flag = 1 << (8 * pe.pointer - 1)
        for index in range(MAX_THUNKS + 1):
            if index == MAX_THUNKS:
                raise FormatError(f"import thunk list too long: {dll}")
            at = _rva_offset(pe, thunk + index * pe.pointer, pe.pointer)
            value = int.from_bytes(data[at:at + pe.pointer], "little")
            if not value:
                break
            slot = iat + index * pe.pointer
            if value & ordinal_flag:
                result.append((dll, None, value & 0xFFFF, slot))
            else:
                result.append((dll, _cstring(data, pe, (value & 0x7FFFFFFF) + 2), None, slot))
            if len(result) > MAX_TOTAL_IMPORTS:
                raise FormatError("import table exceeds budget")
        descriptor += 20
    raise FormatError("import descriptor list too long")


def _relevant_api(dll, name):
    dll = dll.lower()
    if dll in ("kernel32.dll", "kernelbase.dll") or dll.startswith("api-ms-win-core-"):
        return name in KERNEL_APIS
    if dll == "gdi32.dll":
        return name in GDI_APIS
    if dll == "user32.dll":
        return name in USER_APIS
    if dll.startswith("d3dx9_") and dll.endswith(".dll"):
        return name in D3DX_APIS
    return False


def _relevant_dll(dll):
    dll = dll.lower()
    return (dll in ("kernel32.dll", "kernelbase.dll", "gdi32.dll", "user32.dll")
            or dll.startswith("api-ms-win-core-") or (dll.startswith("d3dx9_") and dll.endswith(".dll")))


def _entropy(blob):
    if not blob:
        return 0.0
    total = len(blob)
    return -sum(c / total * math.log2(c / total) for c in Counter(blob).values())


def _codepage_value(value):
    return value if value in PLAUSIBLE_CODEPAGES else None


def _site(api, rva, codepage, basis, via):
    return {"rva": f"0x{rva:08X}", "api": api, "codepage": codepage,
            "codepage_name": CODEPAGE_NAMES.get(codepage) if isinstance(codepage, int) else None,
            "basis": basis, "via": via}


# ---------------------------------------------------------------- x86 ------

_X86_REGS = ("eax", "ecx", "edx", "ebx", "esp", "ebp", "esi", "edi")


def _x86_reg_value(code, end, reg):
    """Resolve reg only from an instruction ending exactly at end."""
    if end >= 2 and code[end - 2] in (0x31, 0x33) and code[end - 1] == 0xC0 | reg << 3 | reg:
        return 0, f"xor {_X86_REGS[reg]},{_X86_REGS[reg]}; push {_X86_REGS[reg]}"
    if end >= 5 and code[end - 5] == 0xB8 + reg:
        value = _u32(code, end - 4)
        return value, f"mov {_X86_REGS[reg]},0x{value:X}; push {_X86_REGS[reg]}"
    return None, None


def _x86_last_push(code, end):
    """Decode the instruction ending at end as a push.

    Returns (codepage | "unknown", basis) or None when no push form ends
    there. Several conflicting decodings are reported as unknown.
    """
    found = []
    if end >= 2 and code[end - 2] == 0x6A:
        value = code[end - 1] - 256 if code[end - 1] >= 0x80 else code[end - 1]
        found.append(("imm", value & 0xFFFFFFFF, f"push 0x{code[end - 1]:02X} (6A imm8)"))
    if end >= 5 and code[end - 5] == 0x68:
        value = _u32(code, end - 4)
        found.append(("imm", value, f"push 0x{value:X} (68 imm32)"))
    if end >= 1 and 0x50 <= code[end - 1] <= 0x57 and code[end - 1] != 0x54:
        reg = code[end - 1] - 0x50
        value, basis = _x86_reg_value(code, end - 1, reg)
        found.append(("imm", value, basis) if basis else ("unknown", None, f"push {_X86_REGS[reg]}"))
    memory = ((2, lambda b: b[0] == 0xFF and 0x30 <= b[1] <= 0x37 and b[1] not in (0x34, 0x35)),
              (3, lambda b: b[0] == 0xFF and 0x70 <= b[1] <= 0x77 and b[1] != 0x74),
              (4, lambda b: b[:3] == b"\xFF\x74\x24"),
              (6, lambda b: b[0] == 0xFF and (b[1] == 0x35 or 0xB0 <= b[1] <= 0xB7 and b[1] != 0xB4)),
              (7, lambda b: b[:3] == b"\xFF\xB4\x24"))
    for size, test in memory:
        if end >= size and test(code[end - size:end]):
            found.append(("unknown", None, "push [mem]"))
    if not found:
        return None
    if len({(kind, value) for kind, value, _ in found}) > 1:
        return "unknown", "ambiguous push decoding: " + " | ".join(basis for _, _, basis in found)
    kind, value, basis = found[0]
    if kind == "unknown":
        return "unknown", basis
    if _codepage_value(value) is None:
        return "unknown", f"{basis}: 0x{value:X} is not a plausible code page"
    return value, basis


def _find_all(code, needle):
    position = code.find(needle)
    while position >= 0:
        yield position
        position = code.find(needle, position + 1)


def _x86_sites(code, image_base, targets):
    """targets: {iat_rva: api}. Yield (api, call position, call end, via)."""
    va_of = {api: [] for api in CALL_APIS}
    for iat_rva, api in targets.items():
        va_of[api].append((image_base + iat_rva) & 0xFFFFFFFF)
    for api, vas in va_of.items():
        for va in vas:
            packed = struct.pack("<I", va)
            for position in _find_all(code, b"\xFF\x15" + packed):
                yield api, position, position + 6, "call [IAT]"
            loads = [(position, 0) for position in _find_all(code, b"\xA1" + packed)]
            for reg in range(8):
                if reg != 4:
                    loads += [(position, reg) for position in _find_all(code, bytes((0x8B, 0x05 | reg << 3)) + packed)]
            for position, reg in loads:
                start = position + (5 if code[position] == 0xA1 else 6)
                yield from ((api, call, call + 2, f"mov {_X86_REGS[reg]},[IAT]; call {_X86_REGS[reg]}")
                            for call in _x86_reg_calls(code, start, reg))
            for thunk in _find_all(code, b"\xFF\x25" + packed):
                yield from ((api, call, call + 5, "call jmp-thunk [IAT]") for call in _rel_calls(code, thunk))


def _x86_reg_calls(code, start, reg, window=512):
    reload = bytes((0x8B, 0x05 | reg << 3))
    end = min(len(code), start + window)
    stops = [p for p in (code.find(reload, start, end), code.find(b"\xCC\xCC", start, end)) if p >= 0]
    end = min(stops + [end])
    call = bytes((0xFF, 0xD0 + reg))
    calls = [start + p for p in _find_all(code[start:end], call)]
    # eax/ecx/edx are clobbered by the first call; only esi/edi/ebx/ebp persist.
    return calls[:1] if reg in (0, 1, 2) else calls


def _rel_calls(code, target):
    """E8 rel32 calls whose destination is target (same section)."""
    for position in _find_all(code, b"\xE8"):
        if position + 5 <= len(code) and position + 5 + struct.unpack_from("<i", code, position + 1)[0] == target:
            yield position


# ---------------------------------------------------------------- x64 ------

_ECX_WRITERS_UNKNOWN = (
    # (length, predicate) for instructions that write ecx/rcx with a value we
    # cannot resolve; their presence after an immediate makes the result unknown.
    (2, lambda b: b[0] == 0x8B and (b[1] & 0xF8) == 0xC8),          # mov ecx, r32
    (2, lambda b: b[0] == 0x89 and (b[1] & 0xC7) == 0xC1),          # mov ecx via 89 /r
    (3, lambda b: 0x40 <= b[0] <= 0x4F and b[1] == 0x8B and (b[2] & 0xF8) == 0xC8),
    (3, lambda b: 0x40 <= b[0] <= 0x4F and b[1] == 0x89 and (b[2] & 0xC7) == 0xC1),
    (3, lambda b: b[0] in (0x8B, 0x8D) and (b[1] & 0xF8) == 0x48),  # mov/lea ecx,[reg+d8]
    (4, lambda b: b[0] in (0x48, 0x49) and b[1] in (0x8B, 0x8D) and (b[2] & 0xF8) == 0x48),
    (4, lambda b: b[0] in (0x8B, 0x8D) and b[1] == 0x4C and b[2] == 0x24),
    (5, lambda b: b[0] in (0x48, 0x49) and b[1] in (0x8B, 0x8D) and b[2] == 0x4C and b[3] == 0x24),
    (6, lambda b: b[0] in (0x8B, 0x8D) and b[1] in (0x0D, 0x8C, 0x89, 0x8D, 0x8E, 0x8F, 0x8B)),
    (7, lambda b: b[0] in (0x48, 0x4C) and b[1] in (0x8B, 0x8D) and b[2] == 0x0D),
    (3, lambda b: b[0] == 0x0F and b[1] in (0xB6, 0xB7, 0xBE, 0xBF) and (b[2] & 0x38) == 0x08),
)


def _rex_extends(code, position):
    return position > 0 and 0x40 <= code[position - 1] <= 0x4F and code[position - 1] & 0x05


def _x64_ecx(code, call, floor, window=64):
    """Find the last ecx write before call; immediates only, else unknown."""
    low = max(floor, call - window)
    best = None  # (start, end, value or None, basis)
    for start in range(call - 2, low - 1, -1):
        byte = code[start]
        candidate = None
        if byte == 0xB9 and start + 5 <= call and not _rex_extends(code, start):
            candidate = (start + 5, _u32(code, start + 1), "mov ecx,imm32 (B9)")
        elif byte in (0x31, 0x33) and code[start + 1] == 0xC9 and not _rex_extends(code, start):
            candidate = (start + 2, 0, "xor ecx,ecx")
        elif byte == 0xC7 and code[start + 1] == 0xC1 and start + 6 <= call and not _rex_extends(code, start):
            candidate = (start + 6, _u32(code, start + 2), "mov ecx,imm32 (C7 C1)")
        if candidate and candidate[0] <= call:
            best = (start,) + candidate
            break
    # Over-matching here only turns a result into "unknown", never a wrong value.
    unknown_after = False
    for length, test in _ECX_WRITERS_UNKNOWN:
        for start in range(max(low, (best[0] + 1) if best else low), call - length + 1):
            if test(code[start:start + length]):
                unknown_after = True
                break
    if best is None:
        return "unknown", ("ecx loaded from a register/memory" if unknown_after
                           else "no ecx write recognised within the call window")
    if unknown_after:
        return "unknown", f"{best[3]} followed by another possible ecx write"
    if _codepage_value(best[2]) is None:
        return "unknown", f"{best[3]}: 0x{best[2]:X} is not a plausible code page"
    return best[2], best[3]


def _x64_floor(code, call, window=64):
    """ECX is volatile: never look back past an earlier call (E8 / FF 15)."""
    low = max(0, call - window)
    floor = low
    for needle, size in ((b"\xE8", 5), (b"\xFF\x15", 6)):
        for offset in _find_all(code[low:call], needle):
            if low + offset + size <= call:
                floor = max(floor, low + offset + size)
    return floor


def _x64_sites(code, base_rva, targets):
    """Yield (api, call position, end, via) for RIP-relative IAT calls."""
    for position in _find_all(code, b"\xFF\x15"):
        if position + 6 <= len(code):
            target = base_rva + position + 6 + struct.unpack_from("<i", code, position + 2)[0]
            if target in targets:
                yield targets[target], position, position + 6, "call [rip+IAT]"
    for position in _find_all(code, b"\xFF\x25"):
        if position + 6 <= len(code):
            target = base_rva + position + 6 + struct.unpack_from("<i", code, position + 2)[0]
            if target in targets:
                yield from ((targets[target], call, call + 5, "call jmp-thunk [rip+IAT]")
                            for call in _rel_calls(code, position))
    for prefix in (0x48, 0x4C):
        for reg in range(8):
            if prefix == 0x48 and reg == 4:
                continue
            for position in _find_all(code, bytes((prefix, 0x8B, 0x05 | reg << 3))):
                if position + 7 > len(code):
                    continue
                target = base_rva + position + 7 + struct.unpack_from("<i", code, position + 3)[0]
                if target not in targets:
                    continue
                name = ("r%d" % (reg + 8)) if prefix == 0x4C else ("rax", "rcx", "rdx", "rbx", "", "rbp", "rsi", "rdi")[reg]
                call = (b"\x41" if prefix == 0x4C else b"") + bytes((0xFF, 0xD0 + reg))
                end = min(len(code), position + 7 + 256)
                stop = code.find(b"\xCC\xCC", position + 7, end)
                end = stop if stop >= 0 else end
                calls = list(_find_all(code[position + 7:end], call))
                if prefix == 0x48 and reg in (0, 1, 2) or prefix == 0x4C and reg < 4:
                    calls = calls[:1]  # volatile register: only the first call uses the loaded pointer
                for offset in calls:
                    hit = position + 7 + offset
                    yield targets[target], hit, hit + len(call), f"mov {name},[rip+IAT]; call {name}"


# --------------------------------------------------------- comparisons ------

_REG32 = ("eax", "ecx", "edx", "ebx", "esp", "ebp", "esi", "edi")


def _compare_at(code, position):
    """Classify the instruction whose imm32/disp32 starts at position.

    Returns (start, text, is_offset) or None. is_offset marks sub/add/lea
    forms that start a `sub; jcc; sub ...` switch chain.
    """
    before = code[max(0, position - 3):position].rjust(3, b"\0")
    if before[2] == 0x3D:
        return position - 1, "cmp eax,imm32", False
    if before[2] == 0x2D:
        return position - 1, "sub eax,imm32", True
    if before[2] == 0x05:
        return position - 1, "add eax,-imm32", True
    if before[1] == 0x81 and before[2] >= 0xC0:
        kind = {0xF8: "cmp", 0xE8: "sub", 0xC0: "add"}.get(before[2] & 0xF8)
        if kind:
            return position - 2, f"{kind} {_REG32[before[2] & 7]},{'-' if kind == 'add' else ''}imm32", kind != "cmp"
    if before[1] == 0x8D and 0x80 <= before[2] <= 0xBF and before[2] & 7 != 4:
        return position - 2, f"lea {_REG32[before[2] >> 3 & 7]},[{_REG32[before[2] & 7]}-imm32]", True
    if before[0] == 0x81 and 0x78 <= before[1] <= 0x7F and before[1] != 0x7C:
        return position - 3, "cmp [reg+disp8],imm32", False
    return None


def _compares(code, base_rva, x64):
    found = {}
    for codepage in COMPARE_CODEPAGES:
        for imm, negative in ((struct.pack("<I", codepage), False), (struct.pack("<i", -codepage), True)):
            for position in _find_all(code, imm):
                decoded = _compare_at(code, position)
                if not decoded or ("-imm32" in decoded[1]) != negative:
                    continue
                start, text, is_offset = decoded
                found[start] = (codepage, text, "direct")
                if is_offset:
                    _sub_chain(code, position + 4, codepage, found, x64)
        for position in _find_all(code, b"\x66\x3D" + struct.pack("<H", codepage)):
            found.setdefault(position, (codepage, "cmp ax,imm16", "direct"))
    return [{"rva": f"0x{base_rva + p:08X}", "codepage": cp, "instruction": text, "basis": basis}
            for p, (cp, text, basis) in sorted(found.items())]


CJK_CODEPAGES = (932, 936, 949, 950)
CHARSETS = {0x80: "SHIFTJIS_CHARSET", 0x81: "HANGUL_CHARSET", 0x86: "GB2312_CHARSET", 0x88: "CHINESEBIG5_CHARSET"}
ACP_WINDOW = 192


def _charset_immediates(window):
    """CJK font charset constants loaded by mov/push forms inside window."""
    found = set()
    for value in CHARSETS:
        dword = struct.pack("<I", value)
        for position in _find_all(window, bytes((value,))):
            if position >= 1 and 0xB0 <= window[position - 1] <= 0xB3:                 # mov r8,imm8
                found.add(value)
            elif position >= 1 and window[position - 1] in (0x68,) + tuple(range(0xB8, 0xC0)) \
                    and window[position:position + 4] == dword:                          # push/mov r32,imm32
                found.add(value)
            elif position >= 3 and window[position - 3] == 0xC6 and 0x40 <= window[position - 2] <= 0x47:
                found.add(value)                                                         # mov byte [reg+d8],imm8
    return sorted(found)


def _acp_followups(code, call_end, compares_by_position):
    """What follows one GetACP call: CJK code-page tests and charset loads."""
    window = code[call_end:call_end + ACP_WINDOW]
    pages = sorted({cp for position, cp in compares_by_position
                    if call_end <= position < call_end + ACP_WINDOW and cp in CJK_CODEPAGES})
    return pages, _charset_immediates(window)


def _sub_chain(code, position, value, found, x64, steps=8):
    """Follow `sub eax,cp; jcc; sub eax,delta; jcc ...` switch chains."""
    for _ in range(steps):
        if position + 2 <= len(code) and 0x70 <= code[position] <= 0x7F:
            position += 2
        elif position + 6 <= len(code) and code[position] == 0x0F and 0x80 <= code[position + 1] <= 0x8F:
            position += 6
        else:
            return
        start = position
        rex = 1 if x64 and position < len(code) and code[position] in (0x41, 0x48, 0x49) else 0
        position += rex
        if position + 3 <= len(code) and code[position] == 0x83 and code[position + 1] >= 0xE8:
            delta, size = code[position + 2], 3
            delta = delta - 256 if delta >= 0x80 else delta
            if code[position + 1] >= 0xF8:   # final cmp reg,imm8 against the remainder
                value_seen = value + delta
                if value_seen in COMPARE_CODEPAGES:
                    found.setdefault(start, (value_seen, "cmp reg,imm8 after sub chain", "sub-chain"))
                return
        elif position + 5 <= len(code) and code[position] == 0x2D:
            delta, size = struct.unpack_from("<i", code, position + 1)[0], 5
        elif not x64 and position < len(code) and 0x48 <= code[position] <= 0x4F:
            delta, size = 1, 1
        elif x64 and position + 2 <= len(code) and code[position] == 0xFF and 0xC8 <= code[position + 1] <= 0xCF:
            delta, size = 1, 2
        else:
            return
        value += delta
        position += size
        if value in COMPARE_CODEPAGES:
            found.setdefault(start, (value, "sub chain", "sub-chain"))


# -------------------------------------------------------------- probe ------

def _packing(pe, imports, import_error, exec_entropy):
    hints = []
    for section in pe.sections:
        packer = PACKER_SECTIONS.get(section["name"].lower())
        if packer:
            hints.append(f"section {section['name']!r} suggests {packer}")
        if section["executable"] and section["vsize"] > 0x1000 and section["raw_size"] == 0:
            hints.append(f"executable section {section['name']!r} has no raw data (unpacked at runtime)")
    named = sum(1 for item in imports if item[1])
    if import_error:
        hints.append(f"import table unreadable ({import_error})")
    elif named < FEW_IMPORTS:
        hints.append(f"only {named} named imports")
    for name, value in exec_entropy.items():
        if value > HIGH_ENTROPY:
            hints.append(f"executable section {name!r} entropy {value:.2f} > {HIGH_ENTROPY}")
    return hints


def _sjis_tables(data, limit=8):
    """File offsets of a built-in SJIS->Unicode table (JIS row 1 as UTF-16LE)."""
    return list(_find_all(data, SJIS_TABLE_SIGNATURE))[:limit]


def _cap(items, max_sites):
    return items[:max_sites] if max_sites else items


def probe_codepage(path, *, max_bytes=MAX_FILE_BYTES, max_sites=MAX_SITES):
    """Return the JSON-ready probe result for one PE file (read-only, bounded).

    Header/section-table damage raises FormatError; an unreadable import
    table (typical of protectors) is reported as a packing hint instead.
    """
    data = _read_bounded(path, max_bytes)
    pe = _parse_headers(data)
    if pe.machine not in (0x14C, 0x8664):
        raise FormatError(f"unsupported PE machine 0x{pe.machine:04X} (x86/x64 only)")
    x64 = pe.machine == 0x8664
    if x64 != (pe.format == "PE32+"):
        raise FormatError("PE machine does not match optional header format")
    try:
        imports, import_error = _imports(data, pe), None
    except FormatError as error:
        imports, import_error = [], str(error)
    relevant = [{"dll": dll, "name": name, "iat_rva": f"0x{slot:08X}"}
                for dll, name, ordinal, slot in imports if name and _relevant_api(dll, name)]
    ordinals = [{"dll": dll, "ordinal": ordinal, "iat_rva": f"0x{slot:08X}"}
                for dll, name, ordinal, slot in imports if name is None and _relevant_dll(dll)]
    targets = {slot: name for dll, name, ordinal, slot in imports
               if name in CALL_APIS and _relevant_api(dll, name)}
    conversions, getacp, compares, exec_entropy = [], [], [], {}
    for section in pe.sections:
        if not section["executable"] or not section["raw_size"]:
            continue
        size = section["raw_size"] if not section["vsize"] else min(section["raw_size"], section["vsize"])
        code = data[section["raw_ptr"]:section["raw_ptr"] + size]
        exec_entropy[section["name"]] = round(_entropy(code), 3)
        base = section["rva"]
        section_compares = _compares(code, base, x64)
        compares += section_compares
        positions = [(int(item["rva"], 16) - base, item["codepage"]) for item in section_compares]
        sites = _x64_sites(code, base, targets) if x64 else _x86_sites(code, pe.image_base, targets)
        seen = set()
        for api, call, end, via in sites:
            if call in seen:
                continue
            seen.add(call)
            if api == "GetACP":
                pages, charsets = _acp_followups(code, end, positions)
                getacp.append({"rva": f"0x{base + call:08X}", "via": via, "followed_by_codepages": pages,
                               "followed_by_charsets": [f"0x{v:02X}" for v in charsets],
                               "charset_names": [CHARSETS[v] for v in charsets],
                               "acp_branch": bool(len(pages) >= 2 or (pages and len(charsets) >= 2))})
                continue
            if x64:
                codepage, basis = _x64_ecx(code, call, _x64_floor(code, call))
            else:
                decoded = _x86_last_push(code, call)
                if decoded is None:
                    if via.startswith("mov"):
                        continue  # a register call without an adjacent push is not confirmed
                    decoded = ("unknown", "no push immediately before the call")
                codepage, basis = decoded
            conversions.append(_site(api, base + call, codepage, basis, via))
    conversions.sort(key=lambda item: item["rva"])
    getacp.sort(key=lambda item: item["rva"])
    hints = _packing(pe, imports, import_error, exec_entropy)
    sjis_table = _sjis_tables(data)
    counts = Counter(str(item["codepage"]) for item in conversions)
    result = {
        "ok": True, "schema": SCHEMA, "file": str(path), "size": len(data),
        "machine": f"0x{pe.machine:04X}", "architecture": PE_MACHINES[pe.machine], "format": pe.format,
        "image_base": f"0x{pe.image_base:X}",
        "sections": [{"name": s["name"], "rva": f"0x{s['rva']:08X}", "virtual_size": s["vsize"],
                      "raw_size": s["raw_size"], "executable": s["executable"],
                      "entropy": exec_entropy.get(s["name"]) if s["executable"] else None}
                     for s in pe.sections],
        "imports": {"dll_count": len({item[0].lower() for item in imports}),
                    "named_count": sum(1 for item in imports if item[1]),
                    "ordinal_count": sum(1 for item in imports if item[1] is None),
                    "error": import_error, "relevant": relevant, "relevant_ordinals": ordinals},
        "conversion_calls": _cap(conversions, max_sites),
        "getacp_calls": _cap(getacp, max_sites),
        "codepage_compares": _cap(compares, max_sites),
        "packing": {"suspected": bool(hints), "hints": hints},
        "embedded_sjis_table": {"found": bool(sjis_table), "file_offsets": [f"0x{o:X}" for o in sjis_table]},
        "summary": {"conversion_calls": len(conversions), "conversion_codepages": dict(sorted(counts.items())),
                    "getacp_calls": len(getacp), "acp_branches": sum(item["acp_branch"] for item in getacp),
                    "codepage_compares": len(compares),
                    "compare_codepages": sorted({item["codepage"] for item in compares}),
                    "max_sites": max_sites or None},
    }
    result["verdict"], result["reasons"] = _verdict(relevant, ordinals, conversions, getacp, compares, hints,
                                                    [f"0x{o:X}" for o in sjis_table])
    result["confidence"] = _confidence(result["verdict"], conversions, getacp, sjis_table)
    result["note"] = NOTE
    return result


def _confidence(verdict, conversions, getacp, sjis_table):
    """strong: a GetACP->charset branch, or 932 conversions/SJIS table without
    competing evidence; weak: only CP_ACP conversion constants (often paths)."""
    if verdict == "acp-following":
        return "strong" if any(item["acp_branch"] for item in getacp) else "weak"
    if verdict == "fixed-cp932":
        return "strong" if sum(c["codepage"] == 932 for c in conversions) >= 2 or sjis_table else "weak"
    return None


def _verdict(relevant, ordinals, conversions, getacp, compares, hints, sjis_table=()):
    names = {item["name"] for item in relevant}
    acp = [c for c in conversions if c["codepage"] in ACP_CODEPAGES]
    fixed = [c for c in conversions if c["codepage"] == 932]
    unknown = [c for c in conversions if c["codepage"] == "unknown"]
    branches = [item for item in getacp if item["acp_branch"]]
    compare_pages = sorted({item["codepage"] for item in compares})
    reasons = []
    if acp:
        reasons.append(f"{len(acp)} conversion call(s) pass CodePage CP_ACP/CP_THREAD_ACP")
    if fixed:
        reasons.append(f"{len(fixed)} conversion call(s) pass CodePage 932")
    other = sorted({c["codepage"] for c in conversions} - ACP_CODEPAGES - {932, "unknown"}, key=str)
    if other:
        reasons.append(f"other constant code pages in conversion calls: {other}")
    if unknown:
        reasons.append(f"{len(unknown)} conversion call(s) with unresolved CodePage")
    if getacp:
        reasons.append(f"{len(getacp)} GetACP call site(s)")
    for item in branches:
        reasons.append(f"GetACP at {item['rva']} is followed by code-page tests {item['followed_by_codepages']}"
                       + (f" and font charsets {item['followed_by_charsets']}" if item["followed_by_charsets"] else "")
                       + " (ACP-based branch)")
    if compare_pages and not branches:
        reasons.append(f"code-page constants compared elsewhere {compare_pages}: not right after a GetACP call "
                       "(C runtime locale tables do this too), so not counted")
    if hints:
        reasons.append("packing/protection suspected: " + "; ".join(hints))
        reasons.append("static evidence may describe only a stub; probe an unpacked EXE or test at runtime")
        return "undetermined", reasons
    if sjis_table:
        reasons.append(f"embedded SJIS->Unicode table at file offset(s) {sjis_table}: the engine can decode "
                       "CP932 itself regardless of the system code page")
    if (acp or branches) and (fixed or sjis_table):
        return "mixed", reasons
    if acp or branches:
        return "acp-following", reasons
    if fixed or sjis_table:
        return "fixed-cp932", reasons
    if not names & set(CONVERSION_APIS):
        reasons.append("no named MultiByteToWideChar/WideCharToMultiByte import"
                       + (" (some relevant DLL functions are imported by ordinal)" if ordinals else ""))
    elif not conversions:
        reasons.append("conversion APIs are imported but no call site was recognised "
                       "(indirect calls, GetProcAddress or unusual code generation)")
    else:
        reasons.append("no conversion call with a CP_ACP or 932 constant was resolved")
    a_only = {n for n in names if n.endswith("A") and n[:-1] + "W" not in names}
    if any(n.startswith(("TextOut", "ExtTextOut", "GetGlyphOutline", "DrawText")) for n in a_only):
        reasons.append("text drawn through ANSI (A) GDI APIs: bytes are interpreted by the selected font's "
                       "charset code page (ACP only for DEFAULT_CHARSET), so this alone does not decide")
    reasons.append("the engine may decode text with its own tables; compare GBK and JIS lines in a small test")
    return "undetermined", reasons



def analyze_codepage(path, *, max_sites=MAX_SITES, rizin="auto", rizin_timeout=None):
    """Byte probe, refined by the optional rizin deep probe when available.

    The byte-probe fields stay unchanged (``byte_verdict`` keeps its verdict);
    ``verdict``/``confidence`` come from rizin when it ran, and
    ``verdict_source`` says which. rizin failures fall back silently to the
    byte probe and are recorded under ``rizin.error``.
    """
    from . import rizin_probe

    result = probe_codepage(path, max_sites=max_sites)
    result.update(byte_verdict=result["verdict"], byte_confidence=result["confidence"],
                  verdict_source="byte-probe")
    if result["packing"]["suspected"]:
        result["rizin"] = {"skipped": "packed or protected executable"}
        return result
    try:
        kwargs = {"timeout": rizin_timeout} if rizin_timeout else {}
        deep = rizin_probe.probe(path, rizin=rizin,
                                 embedded_sjis=result["embedded_sjis_table"]["found"], **kwargs)
    except rizin_probe.RizinUnavailable as error:
        result["rizin"] = {"error": str(error)}
        return result
    result["rizin"] = deep
    result.update(verdict=deep["verdict"], confidence=deep["confidence"], verdict_source="rizin")
    return result
