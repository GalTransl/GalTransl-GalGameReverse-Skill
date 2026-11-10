# SPDX-License-Identifier: GPL-3.0-only
"""SExtractor-compatible JIS substitution, without global codec patches.

Mapping/algorithm: satan53x/SExtractor contributors, helper_text.py and
subs_cn_jp.json at 8d8d976fd04ae54e7c677705af937273d04a376a.
See provenance/jis-substitution.json. Unlike upstream, missing characters,
non-roundtripping CP932 and ambiguous proxy use fail; never replace with spaces.
One session per output package; only feed parsed display text, never filenames.
Optional plan(remap_conflicts=True) allocates unused CP932 private characters;
this extension needs its generated hook mapping, not a SExtractor preset font.
"""
import codecs
import hashlib
import json
from functools import lru_cache
from pathlib import Path
import re

from .binary import FormatError
from .contract import load_json

MAPPING_SHA256 = "0d503680cc62e032b8d0574328842d2b19162774ac19184e8af67be70c147c80"
ASSETS = Path(__file__).resolve().parents[2] / "assets"
HOOK_SHA256 = "b83f896edd06662078eadd5ea7970ab5bfd320cd8ec319e72b1455473c897e41"
HOOK_PATH = ASSETS / "uif/winmm.dll"
CIALLOHOOK_SHA256 = "45a690c147467bf34168ecdeedb1d682848e99617dde41402faf83c291dc54ad"
CIALLOHOOK_PATH = ASSETS / "ciallohook/version.dll"
CIALLOHOOK_X64_SHA256 = "37257c9e71aaef006d21391998e89603ff4d8a09409a87496a5f8d1afc88c958"
CIALLOHOOK_X64_PATH = ASSETS / "ciallohook/x64/version.dll"
# Pinned delivery assets; copied, never loaded here. Windows does not load a
# DLL whose PE machine differs from the game EXE (x86 0x014C, x64 0x8664).
HOOKS = {
    "uif": {"path": HOOK_PATH, "sha256": HOOK_SHA256, "dll": "winmm.dll", "config": None,
            "architecture": "x86", "machine": 0x14C},
    "ciallohook": {"path": CIALLOHOOK_PATH, "sha256": CIALLOHOOK_SHA256, "dll": "version.dll",
                   "config": "version.ini", "architecture": "x86", "machine": 0x14C},
    "ciallohook-x64": {"path": CIALLOHOOK_X64_PATH, "sha256": CIALLOHOOK_X64_SHA256, "dll": "version.dll",
                       "config": "version.ini", "architecture": "x64", "machine": 0x8664},
}
CIALLOHOOK_NAMES = ("ciallohook", "ciallohook-x64")
# Locale Emulator dependencies for CialloHook [LocaleEmulator] (restart the game
# under ACP 932). Pinned copies from CialloHook v1.7 third/LE and third/LEP;
# copied, never loaded here. CialloHook tries LEP first, then LE (x86 only).
LOCALE_EMULATOR_DIR = ASSETS / "ciallohook/locale-emulator"
LOCALE_EMULATOR_FILES = {
    "LoaderDll_x86.dll": ("LEP", "b542c7caf63538b044a678e8859abbc29cf3444629b729aaec3faf1bcb68e2e2", 0x14C),
    "LocaleEmulatorPlus_x86.dll": ("LEP", "ab98822b1de1c3c4b40d6acb14009771e6fba5c9c8b425a26e767d734cde2822", 0x14C),
    "LoaderDll_x64.dll": ("LEP", "70c35241a7d72653f362c25a1381b06f8a052639b8b7dc4789a3ac8fe0d708c7", 0x8664),
    "LocaleEmulatorPlus_x64.dll": ("LEP", "1680512fa217483998673e3b4fffe6ff4c3c273d48754d0c879f506368dd25bc", 0x8664),
    "LoaderDll.dll": ("LE", "82fae0f44f4ca0c9c37907df74cef2415eeb5fae1cf8d4f36f34ffcaf7e3cc0c", 0x14C),
    "LocaleEmulator.dll": ("LE", "c79c175fdad174aa46a72197d148316299a56f950aaab1b84930d09ee1084a88", 0x14C),
}
LOCALE_EMULATOR_DEPENDENCIES = {
    "x86": ("LoaderDll_x86.dll", "LocaleEmulatorPlus_x86.dll", "LoaderDll.dll", "LocaleEmulator.dll"),
    "x64": ("LoaderDll_x64.dll", "LocaleEmulatorPlus_x64.dll"),
}
# CialloHook [CodePage] only rewrites calls whose CodePage equals a non-zero
# FromCodePage, so it cannot turn CP_ACP into 932; restarting under LE can.
LOCALE_EMULATOR_INI = """
# 强制 ACP=932：系统 ACP 不是 932 时借 LE/LEP 以日文区域重启游戏（需同目录 LE/LEP 依赖）。
# 重启失败、启动器/DRM 异常或存档读写出错时改为 Enable = false。
[LocaleEmulator]
Enable = true
AnsiCodePage = 932
OemCodePage = 932
LocaleID = 0x411
DefaultCharset = 128
HookUILanguageAPI = 0
Timezone = Tokyo Standard Time
"""
# CP932 user-defined area F040..F9FC <-> U+E000..U+E757 (Python and Windows
# code page 932 agree). 'unused' proxies are allocated from the HIGH end down:
# engines and EUDC fonts conventionally occupy the low end (U+E000...).
PRIVATE_FIRST, PRIVATE_LAST = 0xE000, 0xE757
# CialloHook reads uif_config.json's character_substitution directly
# (source = proxy, target = Chinese); only the glyph-map hook is enabled.
CIALLOHOOK_INI = """# CialloHook 配置（JIS 替换回注生成，UTF-8）
# 与 version.dll 同名，读取同目录 uif_config.json 的 character_substitution。
[CialloHook]
Charset = 0x00
# 留空不替换字体；代理字恢复为中文后若显示方框，再由 agent 调整 Font。
Font =
EnableCharsetSpoof = false
EnableCnJpMap = true
CnJpMapVerboseLog = false
CnJpMapJson = uif_config.json
CnJpMapReadEncoding = 932

[LoadMode]
Mode = proxy

[EngineCompat]
Enable = true
Mode = auto
FeatureSet = all
RuntimePatch = safe

[Debug]
Enable = true
LogToFile = true
LogToConsole = false
"""


def locale_emulator_files(architecture):
    """(name, bytes) of the pinned LE/LEP dependencies for one hook bitness."""
    files = []
    for name in LOCALE_EMULATOR_DEPENDENCIES[architecture]:
        package, digest, _ = LOCALE_EMULATOR_FILES[name]
        raw = (LOCALE_EMULATOR_DIR / package / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise FormatError(f"bundled Locale Emulator {package}/{name} hash mismatch")
        files.append((name, raw))
    return files


def is_cp932(encoding):
    return codecs.lookup(encoding).name == "cp932"


def mapping_sha256(raw):
    """Hash the preset after CRLF->LF normalization.

    The repository normalizes tracked text, so a Windows checkout (CRLF) and a
    Linux/macOS checkout (LF) must verify identically; only content edits count.
    """
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


def batch_mapping_sha256(chinese_to_proxy):
    """SHA-256 of the actual batch mapping: compact UTF-8 JSON, keys sorted."""
    raw = json.dumps(dict(sorted(chinese_to_proxy.items())), ensure_ascii=False,
                     separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


_CODEPOINT = re.compile(r"U\+([0-9A-Fa-f]{4,6})")


def _codepoint(text):
    match = _CODEPOINT.fullmatch(text.strip())
    if not match:
        raise FormatError(f"reserved codepoint must look like U+E000: {text!r}")
    return int(match.group(1), 16)


def parse_reserved_codepoints(values):
    """Normalize reserved codepoints to sorted, merged inclusive ranges.

    Accepted items: an int, "U+E000", or an inclusive range "U+E000-U+E0FF".
    A string may also hold a comma-separated list (CLI form).
    """
    if isinstance(values, (str, int)):
        values = [values]
    if not isinstance(values, (list, tuple)):
        raise FormatError("reserved_codepoints must be a list")
    ranges = []
    for item in values:
        if isinstance(item, bool):
            raise FormatError("reserved codepoint cannot be a boolean")
        if isinstance(item, int):
            ranges.append((item, item))
        elif isinstance(item, str):
            parts = [p.strip() for p in item.split(",")]
            if not all(parts):
                raise FormatError(f"empty reserved codepoint item: {item!r}")
            for part in parts:
                low, sep, high = part.partition("-")
                low = _codepoint(low)
                ranges.append((low, _codepoint(high) if sep else low))
        else:
            raise FormatError("reserved_codepoints items must be int or 'U+XXXX[-U+YYYY]' strings")
    merged = []
    for low, high in sorted(ranges):
        if not 0 <= low <= high <= 0x10FFFF:
            raise FormatError(f"invalid reserved codepoint range: {low:#x}-{high:#x}")
        if merged and low <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(high, merged[-1][1]))
        else:
            merged.append((low, high))
    return tuple(merged)


def format_reserved_codepoints(ranges):
    return [f"U+{a:04X}" if a == b else f"U+{a:04X}-U+{b:04X}" for a, b in ranges]


def is_private(char):
    return PRIVATE_FIRST <= ord(char) <= PRIVATE_LAST


@lru_cache(maxsize=None)
def _direct_char(char):
    """True if the character is stored as itself in strict CP932."""
    try:
        raw = char.encode("cp932", "strict")
    except UnicodeEncodeError:
        return False
    if raw.decode("cp932", "strict") != char:
        raise FormatError(f"CP932 alias does not roundtrip: U+{ord(char):04X}")
    return True


class JisSubstitution:
    """Strict CP932 encoder and display decoder for a complete output package.

    Reserve all untouched display text before writing. encode() also reserves
    every directly encodable character it sees. A collision detected in a later
    file must abort publication of the entire package. Call artifacts() only
    after all engine writers, reparses and archive checks have succeeded.
    reserved_codepoints (engine/EUDC-occupied) are never used as proxies.
    """
    encoding = "cp932"  # Python codec actually used for storage bytes

    def __init__(self, encoding="cp932", *, reserved_codepoints=()):
        if not is_cp932(encoding):
            raise FormatError("JIS substitution requires proven CP932 script encoding")
        self.script_encoding = encoding
        raw = Path(__file__).with_name("jis_cn_jp.json").read_bytes()
        if mapping_sha256(raw) != MAPPING_SHA256:
            raise FormatError("JIS preset changed; update provenance and matching font policy")
        self._mapping = load_json(raw)
        if (not isinstance(self._mapping, dict)
                or any(len(k) != 1 or not isinstance(v, str) or len(v) != 1
                       for k, v in self._mapping.items())
                or len(set(self._mapping.values())) != len(self._mapping)):
            raise FormatError("JIS preset must be a one-character bijection")
        for proxy in self._mapping.values():
            encoded = proxy.encode("cp932", "strict")
            if len(encoded) != 2 or encoded.decode("cp932") != proxy:
                raise FormatError("JIS proxy must be a stable two-byte CP932 character")
        self._reserved = parse_reserved_codepoints(reserved_codepoints)
        self._used = {}
        self._proxies = set()
        self._direct = set()
        self._avoid = set()
        self._preset_mapping = dict(self._mapping)
        self._remapped = {}
        self._display_table = None

    @property
    def reserved_codepoints(self):
        return format_reserved_codepoints(self._reserved)

    def is_reserved(self, char):
        code = ord(char)
        return any(low <= code <= high for low, high in self._reserved)

    @staticmethod
    def _direct_chars(text):
        return {char for char in set(text) if _direct_char(char)}

    def _check_collision(self, direct, proxies):
        conflicts = set(direct).intersection(proxies)
        conflicts.update(p for p in proxies if self.is_reserved(p))
        if conflicts:
            raise FormatError("JIS proxy also occurs as literal display text or reserved codepoint: "
                              + "".join(sorted(conflicts)))

    def reserve(self, text):
        """Reserve untouched source/UI text (decoded with its proven codec)."""
        new = self._direct_chars(text) - self._direct
        self._check_collision(new, self._proxies)
        self._direct |= new

    def avoid_private(self, text):
        """Keep private-use characters seen anywhere (e.g. EUDC glyphs) out of
        the 'unused' pool without reserving the rest of a replaced line."""
        self._avoid.update(char for char in text if is_private(char))

    def preflight(self, texts):
        """Report all fixed-mapping conflicts before encoding, without mutation."""
        if self._used:
            raise FormatError("cannot preflight JIS proxies after encoding has started")
        direct = set(self._direct)
        characters = set()
        for text in texts:
            direct.update(self._direct_chars(text))
            characters.update(text)
        needed = sorted(characters - direct)
        missing = [char for char in needed if char not in self._mapping]
        conflicts = []
        for char in needed:
            proxy = self._mapping.get(char)
            if proxy is not None and (proxy in direct or self.is_reserved(proxy)):
                item = {"character": char, "proxy": proxy}
                if self.is_reserved(proxy):
                    item["reserved_codepoint"] = True
                conflicts.append(item)
        return {"mapping_sha256": MAPPING_SHA256, "required_count": len(needed),
                "conflicts": conflicts, "missing_characters": missing,
                "ok": not conflicts and not missing}

    def plan(self, texts, *, remap_conflicts=False):
        """Plan all translations before encoding; optionally use unused CP932 PUA.

        Default behavior retains the SExtractor preset and rejects collisions.
        Opt-in remapping allocates from U+E757 DOWN to U+E000 (stable
        double-byte CP932 user-defined characters F9FC..F040), skipping
        literal/avoided private characters and reserved codepoints. It needs
        the generated hook config or a custom font. Reserve every known
        untouched display character first. Never reassign a proxy after any
        bytes have been emitted by this session.
        """
        if self._used:
            raise FormatError("cannot plan JIS proxies after encoding has started")
        characters = set()
        for text in texts:
            self.reserve(text)
            characters.update(text)
        needed = sorted(characters - self._direct)
        missing = [char for char in needed if char not in self._mapping]
        if missing:
            raise FormatError(f"missing JIS substitution: U+{ord(missing[0]):04X}")
        conflicts = [char for char in needed
                     if self._mapping[char] in self._direct or self.is_reserved(self._mapping[char])]
        if conflicts and not remap_conflicts:
            self._check_collision(self._direct, {self._mapping[char] for char in needed})
        forbidden = self._direct | self._avoid | set(self._mapping.values())
        candidates = (chr(code) for code in range(PRIVATE_LAST, PRIVATE_FIRST - 1, -1)
                      if chr(code) not in forbidden and not self.is_reserved(chr(code)))
        replacements = {}
        for char in conflicts:
            proxy = next(candidates, None)
            if proxy is None:
                raise FormatError("unused CP932 private-character pool exhausted")
            raw = proxy.encode("cp932", "strict")
            if len(raw) != 2 or raw.decode("cp932") != proxy:
                raise FormatError("private proxy is not stable double-byte CP932")
            replacements[char] = proxy
        self._mapping.update(replacements)
        self._remapped.update(replacements)

    def encode(self, text, *, max_bytes=None):
        new_direct = self._direct_chars(text) - self._direct
        new_used = {}
        result = []
        for char in text:
            if char in self._direct or char in new_direct:
                result.append(char)
            elif char in self._mapping:
                new_used[char] = self._mapping[char]
                result.append(new_used[char])
            else:
                raise FormatError(f"missing JIS substitution: U+{ord(char):04X} {char!r}")
        proxies = set(new_used.values())
        self._check_collision(new_direct, self._proxies | proxies)
        self._check_collision(self._direct, proxies)
        raw = "".join(result).encode("cp932", "strict")
        if max_bytes is not None and len(raw) > max_bytes:
            raise FormatError(f"JIS encoded text exceeds byte capacity ({len(raw)} > {max_bytes})")
        self._direct |= new_direct
        if any(char not in self._used for char in new_used):
            self._used.update(new_used)
            self._proxies |= proxies
            self._display_table = None
        return raw

    def display(self, stored_text):
        """Decode only parsed text fields for the second, semantic roundtrip."""
        if self._display_table is None:
            self._display_table = str.maketrans({v: k for k, v in self._used.items()})
        return stored_text.translate(self._display_table)

    def summary(self):
        return {"mode": "sextractor-jis-substitution", "script_encoding": self.script_encoding,
                "mapping_sha256": MAPPING_SHA256,
                "batch_mapping_sha256": batch_mapping_sha256(self._used),
                "used_count": len(self._used),
                "remapped_count": len(self._remapped),
                "reserved_codepoints": self.reserved_codepoints,
                "preset_font_compatible": not bool(self._remapped),
                "runtime_verified": False}

    def artifacts(self, *, include_hook=True, hook="ciallohook", force_cp932=False):
        """Return files to publish atomically WITH the rewritten game resources.

        No config is needed for a pass-through run. Bundle a pinned hook whose
        architecture matches the game EXE: hook="ciallohook" (default, x86
        version.dll + ini), "ciallohook-x64" (x64 version.dll + ini) or the
        manual fallback "uif" (x86 winmm.dll); all read the same
        uif_config.json. There is no x64 UIF. Set include_hook=False for
        another runtime/architecture. force_cp932=True (CialloHook only) adds
        [LocaleEmulator] to version.ini plus the pinned LE/LEP dependencies of
        the hook's bitness, so the game restarts under ACP 932. Nothing is
        installed. Existing configurations must be merged by the agent after
        inspecting the existing hook; this template must not replace one.
        """
        if hook not in HOOKS:
            raise FormatError(f"unknown JIS hook: {hook}")
        if force_cp932 and (not include_hook or hook not in CIALLOHOOK_NAMES):
            raise FormatError("force_cp932 needs a bundled CialloHook (UIF cannot restart under another locale)")
        if not self._used:
            return []
        selected = HOOKS[hook]
        hook_files, locale_files = [], []
        if include_hook:
            raw = selected["path"].read_bytes()
            if hashlib.sha256(raw).hexdigest() != selected["sha256"]:
                raise FormatError(f"bundled {hook} {selected['dll']} hash mismatch")
            hook_files = [(selected["dll"], raw)]
            if selected["config"]:
                ini = CIALLOHOOK_INI + (LOCALE_EMULATOR_INI if force_cp932 else "")
                hook_files.append((selected["config"], ini.encode("utf-8")))
            if force_cp932:
                locale_files = locale_emulator_files(selected["architecture"])
                hook_files += locale_files
        pairs = sorted(self._used.items())
        config = {
            "injector": {"enable": True, "print_loaded_modules": False},
            "allocate_console": False,
            "tunnel_decoder": {"enable": False, "mapping": ""},
            "character_substitution": {"enable": True,
                "source_characters": "".join(v for k, v in pairs),
                "target_characters": "".join(k for k, v in pairs)},
            "font_manager": {"enable": False},
        }
        # A full preset font replaces ALL its glyphs, unlike our used-only UIF
        # config. Report additional collisions even for unused substitutions.
        font_conflicts = sorted(self._direct.intersection(
            v for k, v in self._preset_mapping.items() if k != v))
        report = dict(self.summary(), chinese_to_proxy=dict(pairs),
                      custom_chinese_to_proxy=dict(sorted(self._remapped.items())),
                      hook={"included": include_hook, "name": hook if include_hook else None,
                            "architecture": selected["architecture"] if include_hook else None,
                            "files": [name for name, _ in hook_files],
                            "sha256": selected["sha256"] if include_hook else None,
                            "force_cp932": bool(force_cp932),
                            "locale_emulator_files": {name: LOCALE_EMULATOR_FILES[name][1]
                                                      for name, _ in locale_files}},
                      preset_font_conflicts=font_conflicts,
                      collision_scope="only display text supplied to this session; other UI needs runtime testing")
        readme = """JIS 替换回注：部署与测试

本目录脚本保存的是 CP932 代理字符；gt_input/gt_output 保留真实中文。
uif_config.json 的 source 是代理日文，target 是预期中文，不可颠倒。
本结果未附带字体，也未验证游戏实际加载、hook 或字形显示。

方案一与方案二都读取同一个 uif_config.json，只选其一，不要同时放入两个 hook。
DLL 位数必须与实际游戏 EXE 一致（PE 头 Machine：0x014C 为 32 位，0x8664 为 64 位），
位数不匹配的 DLL 不会被加载。UIF 只有 32 位版本；64 位游戏只能用 CialloHook x64。
按本引擎已确认的加载方式部署回注资源。
代理 DLL 是否被加载需实测。若已有 winmm.dll、version.dll、uif_config.json、
CialloHook.ini/version.ini 或其他汉化 hook，先交给 agent 检查合并；
不要覆盖现有 DLL/配置，不要叠加两次字符替换或同时开启 JIS tunneling。
Hook 恢复中文后，游戏还需实际选用包含这些中文字形的普通字体。

方案一（默认）：CialloHook（version.dll 代理，32 位与 64 位各有一个构建）。
https://github.com/Lite0812/CialloHook
将 version.dll、version.ini 与 uif_config.json 放到实际游戏 EXE 目录。
覆盖 TextOut/ExtTextOut/DrawText/GetGlyphOutline/文本宽度等 A/W 接口及部分引擎兼容层，
A 接口无法用 CP932 写回中文时改走 W 接口；还可替换字体。
version.ini 默认不替换字体并在游戏目录写日志；version.dll 不被加载时可改名为
winmm.dll，并把 version.ini 同时改名为 winmm.ini。

方案二（兜底）：UniversalInjectorFramework（winmm.dll 代理，仅 32 位）。
https://github.com/satan53x/UniversalInjectorFramework
仅在 CialloHook 无法加载时由 agent 改配。将 winmm.dll 与 uif_config.json
放到实际游戏 EXE 目录。默认只 hook TextOutA/W、GetGlyphOutlineA/W。

方案三：使用与 jis-mapping.json 中 mapping_sha256 对应的专用日繁/JIS 替换字体。
SExtractor 的 WenQuanYi_cnjp.ttf / MSGothic_WenQuanYi_cnjp.ttf 是候选，
必须核对其映射版本；普通日文字体、繁体字体不能还原代理字符。
安装字体后，还需让游戏选择/加载该字体（或按引擎方式替换实际字体资源）。
如果 preset_font_conflicts 非空，完整预设字体会误显示这些原有字符，
不能直接使用，应改用本次映射定制字体或兼容 hook；不要同时使用替换字体
和开启 character_substitution 的 hook。此工具不生成字体。

请测试本次修改的对白、姓名、选项以及未修改的日文/UI；检查代理字、缺字、
方框、标点和换行。缺字时检查实际使用的字体，而不是只确认安装成功。
把测试结果告诉 agent；后续回写和配置调整由 agent 完成，无需手动运行命令。
"""
        if self._remapped:
            readme = ("本批包含自定义 CP932 私用代理字。必须使用本批 uif_config.json 配套的兼容 hook，\n"
                      "或按本批映射定制字体；SExtractor 固定日繁/JIS 替换字体不适用于本批。\n"
                      "以下方案三的固定预设字体路线不可使用。尚未验证游戏的 hook 加载及私用字符显示。\n\n" + readme)
        if force_cp932:
            readme = ("强制 932（转区重启）已开启：version.ini 含 [LocaleEmulator] Enable = true。\n"
                      "把 " + "、".join(name for name, _ in locale_files) + "\n"
                      "与 version.dll 放在同一游戏 EXE 目录。系统 ACP 不是 932 时，游戏启动后会被\n"
                      "以日文区域（ACP 932）重新启动一次；已是 932 时不重启。\n"
                      "可能的问题：Steam/DRM/启动器/反作弊因重启失效；安全软件拦截 LE 注入；\n"
                      "游戏或存档路径含 CP932 不能表示的字符（如中文用户名、中文目录）时存档读写失败。\n"
                      "出现这些问题时把 version.ini 的 [LocaleEmulator] Enable 改为 false 并告诉 agent，\n"
                      "改用 GBK 回写或手动转区。尚未在真实游戏验证转区效果。\n\n" + readme)
        if include_hook:
            bits = "64" if selected["architecture"] == "x64" else "32"
            readme = (f"本结果附带的 hook：{'方案二 UIF' if hook == 'uif' else '方案一 CialloHook'}"
                      f"（{selected['architecture']}，只用于 {bits} 位游戏 EXE）。\n\n" + readme)
        return [*hook_files, ("uif_config.json", _json(config)), ("jis-mapping.json", _json(report)),
                ("JIS-部署说明.txt", readme.encode("utf-8"))]
