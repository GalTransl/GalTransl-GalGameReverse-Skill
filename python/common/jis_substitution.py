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
from pathlib import Path

from .binary import FormatError
from .contract import load_json

MAPPING_SHA256 = "c7d435172c76e6773bba3e2c593c9fd435fefceef22fa2082e41fa8d574b0ba0"
HOOK_SHA256 = "b83f896edd06662078eadd5ea7970ab5bfd320cd8ec319e72b1455473c897e41"
HOOK_PATH = Path(__file__).resolve().parents[2] / "assets/uif/winmm.dll"


def is_cp932(encoding):
    return codecs.lookup(encoding).name == "cp932"


def _json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


class JisSubstitution:
    """Strict CP932 encoder and display decoder for a complete output package.

    Reserve all untouched display text before writing. encode() also reserves
    every directly encodable character it sees. A collision detected in a later
    file must abort publication of the entire package. Call artifacts() only
    after all engine writers, reparses and archive checks have succeeded.
    """
    encoding = "cp932"

    def __init__(self, encoding="cp932"):
        if not is_cp932(encoding):
            raise FormatError("JIS substitution requires proven CP932 script encoding")
        raw = Path(__file__).with_name("jis_cn_jp.json").read_bytes()
        if hashlib.sha256(raw).hexdigest() != MAPPING_SHA256:
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
        self._used = {}
        self._direct = set()
        self._preset_mapping = dict(self._mapping)
        self._remapped = {}

    @staticmethod
    def _direct_chars(text):
        direct = set()
        for char in set(text):
            try:
                raw = char.encode("cp932", "strict")
            except UnicodeEncodeError:
                continue
            if raw.decode("cp932", "strict") != char:
                raise FormatError(f"CP932 alias does not roundtrip: U+{ord(char):04X}")
            direct.add(char)
        return direct

    @staticmethod
    def _check_collision(direct, used):
        conflicts = direct.intersection(used.values())
        if conflicts:
            raise FormatError("JIS proxy also occurs as literal display text: " + "".join(sorted(conflicts)))

    def reserve(self, text):
        """Reserve untouched source/UI text (decoded with its proven codec)."""
        direct = self._direct | self._direct_chars(text)
        self._check_collision(direct, self._used)
        self._direct = direct

    def plan(self, texts, *, remap_conflicts=False):
        """Plan all translations before encoding; optionally use unused CP932 PUA.

        Default behavior retains the SExtractor preset and rejects collisions.
        Opt-in remapping uses U+E000..U+E757 (stable double-byte CP932 private
        characters), requiring the generated hook config or a custom font.
        Reserve every known untouched display character first. Never reassign
        a proxy after any bytes have been emitted by this session.
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
        conflicts = [char for char in needed if self._mapping[char] in self._direct]
        if conflicts and not remap_conflicts:
            self._check_collision(self._direct, {char: self._mapping[char] for char in needed})
        forbidden = self._direct | set(self._mapping.values())
        candidates = (chr(code) for code in range(0xE000, 0xE758) if chr(code) not in forbidden)
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
        direct = self._direct | self._direct_chars(text)
        used = dict(self._used)
        result = []
        for char in text:
            if char in direct:
                result.append(char)
            elif char in self._mapping:
                used[char] = self._mapping[char]
                result.append(used[char])
            else:
                raise FormatError(f"missing JIS substitution: U+{ord(char):04X} {char!r}")
        self._check_collision(direct, used)
        raw = "".join(result).encode("cp932", "strict")
        if max_bytes is not None and len(raw) > max_bytes:
            raise FormatError(f"JIS encoded text exceeds byte capacity ({len(raw)} > {max_bytes})")
        self._direct, self._used = direct, used
        return raw

    def display(self, stored_text):
        """Decode only parsed text fields for the second, semantic roundtrip."""
        return stored_text.translate(str.maketrans({v: k for k, v in self._used.items()}))

    def summary(self):
        return {"mode": "sextractor-jis-substitution", "script_encoding": "cp932",
                "mapping_sha256": MAPPING_SHA256, "used_count": len(self._used),
                "remapped_count": len(self._remapped),
                "preset_font_compatible": not bool(self._remapped),
                "runtime_verified": False}

    def artifacts(self, *, include_hook=True):
        """Return files to publish atomically WITH the rewritten game resources.

        No config is needed for a pass-through run. Bundle the pinned x86 UIF
        DLL by default; set include_hook=False for another runtime/architecture.
        Nothing is installed. Existing configurations must be merged by the agent
        after inspecting the existing hook; this template must not replace one.
        """
        if not self._used:
            return []
        hook_files = []
        if include_hook:
            hook = HOOK_PATH.read_bytes()
            if hashlib.sha256(hook).hexdigest() != HOOK_SHA256:
                raise FormatError("bundled UIF winmm.dll hash mismatch")
            hook_files = [("winmm.dll", hook)]
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
                      hook={"included": include_hook, "architecture": "x86",
                            "sha256": HOOK_SHA256 if include_hook else None},
                      preset_font_conflicts=font_conflicts,
                      collision_scope="only display text supplied to this session; other UI needs runtime testing")
        readme = """JIS 替换回注：部署与测试

本目录脚本保存的是 CP932 代理字符；gt_input/gt_output 保留真实中文。
uif_config.json 的 source 是代理日文，target 是预期中文，不可颠倒。
本结果未附带字体，也未验证游戏实际加载、hook 或字形显示。

方案一：使用兼容的 UniversalInjectorFramework hook。
https://github.com/satan53x/UniversalInjectorFramework
若结果附带 winmm.dll，它是 SExtractor 提供的 x86（32 位）版本。
64 位游戏不要使用此版本，应由 agent 准备对应构建；未附带时另选兼容构建。
确认与游戏进程位数及加载方式匹配；若使用 winmm.dll 代理，
将该 hook 的 winmm.dll 与本目录 uif_config.json 放到实际游戏 EXE 目录，
并按本引擎已确认的加载方式部署回注资源。代理 DLL 是否被加载需实测。
若已有 winmm.dll、uif_config.json 或其他汉化 hook，先交给 agent 检查合并；
不要覆盖现有 DLL/配置，不要叠加两次字符替换或同时开启 JIS tunneling。
Hook 恢复中文后，游戏还需实际选用包含这些中文字形的普通字体。

方案二：使用与 jis-mapping.json 中 mapping_sha256 对应的专用日繁/JIS 替换字体。
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
                      "以下方案二的固定预设字体路线不可使用。尚未验证游戏的 hook 加载及私用字符显示。\n\n" + readme)
        return [*hook_files, ("uif_config.json", _json(config)), ("jis-mapping.json", _json(report)),
                ("JIS-部署说明.txt", readme.encode("utf-8"))]
