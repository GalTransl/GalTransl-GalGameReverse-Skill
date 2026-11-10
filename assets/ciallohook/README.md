# 随包 CialloHook version.dll（x86 / x64）

用户指定纳入仓库的 CialloHook Release 核心 DLL 原样副本，是 JIS 替换回注的**默认显示 hook**（`--hook auto` 按游戏 EXE 位数选择），也是 64 位游戏唯一的随包 hook；另随包其[转区重启](#强制-932转区重启)所需的 LE/LEP 依赖。仅作为输出资源复制，不加载执行。

| 项目 | x86：`version.dll` | x64：`x64/version.dll` |
|---|---|---|
| 来源 | 发布 `v1.7`（标签提交 `08aa96fb17ef115352932e5753f58b15dc978959`）的 `out/bin/x86/Release/version.dll` | 用户以 v1.7 源码目录本地构建的 `out/bin/x64/Release/version.dll` |
| 大小 | 1508352 字节 | 1722368 字节 |
| PE Machine | `0x014C`，x86（32 位） | `0x8664`，x64（64 位） |
| SHA-256 | `45a690c147467bf34168ecdeedb1d682848e99617dde41402faf83c291dc54ad` | `37257c9e71aaef006d21391998e89603ff4d8a09409a87496a5f8d1afc88c958` |
| 导出 | 209 项：`winmm` 与 `version` 两组代理函数（另含 x86 专有的 `*32Message`、`WOW32*`、`NotifyCallbackData` 共 12 项） | 197 项：同样的 `winmm` 与 `version` 代理函数 |
| CLI | `--hook auto`（x86 EXE）或 `ciallohook-x86` | `--hook auto`（x64 EXE）、`ciallohook-x64` 或 `x64` |

- 上游仓库：https://github.com/Lite0812/CialloHook 。两种构建中的 `CialloHook.dll`、`winmm.dll` 都与同目录 `version.dll` 逐字节相同。同一本地构建的 x86 `version.dll` 与上表 x86 副本逐字节相同（SHA-256 一致），说明两者出自同一 v1.7 源码。
- 导入表只有 Windows 系统 DLL：SHLWAPI、KERNEL32、USER32、GDI32、ADVAPI32、ole32、gdiplus、COMCTL32、bcrypt、SHELL32；无 VC 运行库或其他第三方 DLL 依赖，无需随附其他文件。
- 未随包：CialloLauncher、PAK 工具、WebM 模块、pdb/lib、上游默认 `CialloHook.ini` 与示例映射 `subs_cn_jp.json`。LE/LEP 转区依赖见[强制 932](#强制-932转区重启)。

## 完整配置说明（上游文档原样副本）

全部配置段与键的说明以上游文档为准，随包保存 v1.7 原文，未作修改：

| 文件 | 内容 | SHA-256 |
|---|---|---|
| [upstream/README.md](upstream/README.md) | 加载方式（proxy / loader）、最小配置、配置来源切换、常见用法（字体替换、外部字体、字体重定向/跳过、字形微调、字符集伪装、文本替换、日繁映射、补丁目录与封包、代码页伪装、转区、启动时机、各引擎兼容）、`[EngineCompat]`、主要配置段一览与常见问题 | `a90414af7858008027dcf11e59baac1feaa14c7129ec17db6be0414a8ad1e328` |
| [upstream/CialloHook_Example.ini](upstream/CialloHook_Example.ini) | 带注释的完整示例，逐键列出全部配置段 | `bf64702f8e777cd0daa90bc6c3a435b492924652ff59caab1697f8c84ea7f376` |

两份文件取自标签 `v1.7`，与上游 `main` 当前版本逐字节相同。上游 README 中的 `src/CialloHook/config/CialloHook_Example.ini` 即本目录的 `upstream/CialloHook_Example.ini`。启动器、PAK 工具、WebM 等章节所需组件未随包；LE 转区依赖已随包，见下文。

按上游文档调整 JIS 交付的配置时注意：

- 上游示例和常见问题里的 `CnJpMapJson = subs_cn_jp.json` 不适用，始终指向本批 `uif_config.json`（原因见下文）。
- 上游常见问题对乱码给出的 `Charset = 0x86`、`[CodePage]` 932→936，适用于直接写入 GBK 的汉化，不适用于 JIS 替换回注：剧本仍是 CP932，改这些会让未映射的日文和代理字一起乱码。JIS 回注需要的是让运行时 ACP 变为 932，由生成器按需写入 `[LocaleEmulator]`（见[强制 932](#强制-932转区重启)）；不要手工改成 936 区域。
- 开启 `[FilePatch]`、`[TextReplace]`、`[CodePage]` 等会改变游戏读取文件或编码的行为，只在确有需要时开启，并记录在交付说明里。`[LocaleEmulator]` 只按下文规则开启。

上游仓库根目录与本地源码目录均未发现 LICENSE 文件，GitHub license 元数据为 null；本仓库不将此第三方二进制重新标为 GPL。源码静态链接 Microsoft Detours、miniz、zstd、LZMA SDK 等组件，其许可以上游源码为准。

## 位数判断

DLL 位数必须与实际运行的游戏 EXE 一致；**位数不匹配的 DLL 不会被加载**，游戏照常启动但不会发生字符还原。EXE 位数看 PE 头的 Machine 字段：文件偏移 `0x3C` 处的 32 位值指向 `PE\0\0` 签名，其后 2 字节即 Machine，`0x014C` 为 32 位，`0x8664` 为 64 位。可只读运行：

```text
python -m python.common.jis_workflow arch "游戏目录/实际启动的.exe"
```

输出 Machine、位数、可用的 `--hook` 值及 `auto_hook`。正式准备应加 `--exe "实际启动的.exe"`：默认 `--hook auto` 据此选择 CialloHook 位数，显式 hook 位数不符时拒绝生成；不提供 `--exe` 时 `auto` 不附带 hook 并给出警告。启动器与主程序位数可能不同，以实际加载脚本、绘制文本的进程为准。UIF 只有 32 位版本，64 位游戏只能选 CialloHook x64。

## 与 UIF 的分工

默认使用 CialloHook；UIF 只作 CialloHook 无法加载（代理 DLL 不被加载、与已有补丁冲突等）时的手动兜底，用 `--hook uif-x86`（兼容别名 `x86`）显式选择。两者读取同一份 `uif_config.json`，同一游戏只选其一，不叠加两次字符替换。

| 项目 | UIF（[assets/uif](../uif/README.md)） | CialloHook（本目录） |
|---|---|---|
| 位数 | 仅 x86 | x86、x64 |
| 代理文件名 | `winmm.dll` | `version.dll`（可改名 `winmm.dll`） |
| 配置 | `uif_config.json` | `version.ini` + 同一 `uif_config.json` |
| 字符替换接口 | 默认 TextOutA/W、GetGlyphOutlineA/W，可配 `hook_functions` | TextOut、ExtTextOut、DrawText、GetGlyphOutline、GetTextExtent 系列 A/W，另有部分引擎兼容层 |
| A 接口写回 | 原接口 | 映射后的中文无法用 CP932 编码时改调 W 接口 |
| 字体 | 不改字体（JIS 模板关闭 font_manager） | 可替换为系统字体或外部字体文件，并调整字符集与字形度量 |
| 转区 | 不能，需用户手动以日文区域运行 | 可按需强制 ACP 932（`[LocaleEmulator]` + LE/LEP） |
| 适用 | CialloHook 无法加载时的 32 位兜底 | 默认；32/64 位游戏，需换字体或强制 932 时 |

## 生成的配置与读取规则

JIS `artifacts()`（默认 `hook="ciallohook"`）/ `artifacts(hook="ciallohook-x64")` 或 CLI `--hook auto` / `ciallohook-x86` / `ciallohook-x64` 输出对应位数的 `version.dll`、相同的 `version.ini` 和 `uif_config.json`。`version.ini` 为无 BOM 的 UTF-8，只开启字形映射：

```ini
[CialloHook]
Charset = 0x00
Font =
EnableCharsetSpoof = false
EnableCnJpMap = true
CnJpMapJson = uif_config.json
CnJpMapReadEncoding = 932
```

另含 `[LoadMode] Mode = proxy`、`[EngineCompat]` 自动保守模式，以及写文件的 `[Debug]` 日志。不强制 932 时不写 `[LocaleEmulator]` 段（与 CialloHook 默认 `Enable = false` 等效），配置与此前生成的一致。

- **配置查找**：DLL 所在目录的 `<DLL名>.ini` → 同目录 `CialloHook.ini` → 当前目录的同名两项。改名为 `winmm.dll` 时，配置须同时改名为 `winmm.ini`（或 `CialloHook.ini`）。
- **映射格式**：`CnJpMapJson` 文件按 UTF-8 或带 BOM 的 UTF-16LE 读取；含 `source_characters` / `target_characters` 时按 UIF 格式读取，`source[i]` 显示为 `target[i]`，与本项目生成的方向一致；不读取 `enable` 字段。扁平 `{"中文": "代理字"}` 格式同样受支持，仅接受单字对单字。
- **代码页**：`CnJpMapReadEncoding = 932` 让 A 接口字节按代码页 932 转为 Unicode 后查表。CP932 用户自定义区 `F040..F9FC` 对应 `U+E000..U+E757`，因此 `--proxy-policy unused` 分配的私用代理字可被查到。
- **不要使用上游示例 `subs_cn_jp.json`**：其 3018 项与本项目随包 SExtractor 固定表（2999 项）有数十项不同，不能还原本批代理字。始终指向本批 `uif_config.json`。
- **资源查找**：映射 JSON、字体文件按已启用的补丁目录 → CustomPak → 游戏根目录查找；生成配置未启用 `[FilePatch]`，即读取游戏 EXE 目录。
- **字体**：`Font` 可写系统字体名（如 `SimHei`）或字体文件路径，文件内部名称不同时补 `FontName`；`RedirectFontCount` / `RedirectFromFont_i` / `RedirectToFont_i` 可只替换指定原字体。CP932 游戏不要随意设置非零 `Charset`：未映射的日文 A 接口文本会按新字符集解释而乱码。字体调整属于试注后的修正，由 agent 根据显示结果修改；各键写法见上游 README“常见用法”1–5 与示例 ini 的 `[CialloHook]` 段。
- **私用代理字**：运行时显示尚未在真实游戏中验证；外字字体（EUDC）或引擎自用的私用区码位应通过 `reserved_codepoints` 排除，见[公共 JIS 指南](../../guides/jis-substitution.md#私用代理字与保留码位)。

交付时提醒用户：把与游戏 EXE 位数一致的 `version.dll`、`version.ini` 与 `uif_config.json` 一起放到实际游戏 EXE 目录，再按引擎规则部署脚本/补丁，测试修改的对白及未修改 UI；`version.dll` 未加载时再试 `winmm.dll` 名称。已有同名 DLL/配置先检查合并，不盲目覆盖；不保证每个游戏都会加载代理 DLL。

## 强制 932（转区重启）

**原理**：CialloHook 以 `version.dll`/`winmm.dll` 代理形态加载后，若 `[LocaleEmulator] Enable = true` 且当前 `GetACP()` 不等于 `AnsiCodePage`，就借 Locale Emulator Plus（LEP）或 Locale Emulator（LE）以该区域**重新启动游戏进程**；ACP 已等于目标（且 `HookUILanguageAPI = 0`）时跳过，并用环境变量防止重复重启。重启后 ACP 为 932，跟随 ACP 的引擎与固定 932 的引擎都按 CP932 解码，JIS 代理与 `uif_config.json` 映射一致生效。

`[CodePage]` 不能代替它：该段只在调用传入的 CodePage 精确等于非零 `FromCodePage` 时替换，`FromCodePage = 0` 会使映射失效，也不 hook `GetACP`，无法把 `CP_ACP` 调用改成 932。

**何时开启**：`prepare --force-cp932 auto`（默认）对 `--exe` 运行只读码页探测，`verdict` 为 `fixed-cp932` 时不开启，`acp-following`、`mixed`、`undetermined`（含探测报错，如不支持的 PE）时开启；没有 `--exe` 时不开启并警告。`on`/`off` 手动覆盖，仍记录探测结果。开启要求 hook 为 CialloHook，UIF 或 `--hook none` 配 `on` 直接报错。探测结果与决定理由写入 `jis-plan.json` 和交付报告的 `runtime_codepage`、`force_cp932`。API 为 `artifacts(..., force_cp932=True)` 与 `prepare(..., force_cp932="auto"|"on"|"off")`。

开启时 `version.ini` 追加：

```ini
[LocaleEmulator]
Enable = true
AnsiCodePage = 932
OemCodePage = 932
LocaleID = 0x411
DefaultCharset = 128
HookUILanguageAPI = 0
Timezone = Tokyo Standard Time
```

并按 hook 位数附带依赖（复制时校验固定哈希，平铺到交付目录，与 `version.dll` 同目录）。CialloHook 先尝试 LEP，失败再用 LE；LE 只有 32 位。

| 文件（本目录相对路径） | 位数 | 大小 | SHA-256 | 随附于 |
|---|---|---|---|---|
| `locale-emulator/LEP/LoaderDll_x86.dll` | x86 `0x014C` | 16896 | `b542c7caf63538b044a678e8859abbc29cf3444629b729aaec3faf1bcb68e2e2` | x86 |
| `locale-emulator/LEP/LocaleEmulatorPlus_x86.dll` | x86 `0x014C` | 78848 | `ab98822b1de1c3c4b40d6acb14009771e6fba5c9c8b425a26e767d734cde2822` | x86 |
| `locale-emulator/LE/LoaderDll.dll` | x86 `0x014C` | 6144 | `82fae0f44f4ca0c9c37907df74cef2415eeb5fae1cf8d4f36f34ffcaf7e3cc0c` | x86 |
| `locale-emulator/LE/LocaleEmulator.dll` | x86 `0x014C` | 63488 | `c79c175fdad174aa46a72197d148316299a56f950aaab1b84930d09ee1084a88` | x86 |
| `locale-emulator/LEP/LoaderDll_x64.dll` | x64 `0x8664` | 26624 | `70c35241a7d72653f362c25a1381b06f8a052639b8b7dc4789a3ac8fe0d708c7` | x64 |
| `locale-emulator/LEP/LocaleEmulatorPlus_x64.dll` | x64 `0x8664` | 123392 | `1680512fa217483998673e3b4fffe6ff4c3c273d48754d0c879f506368dd25bc` | x64 |

来源与许可状态：六个文件均原样取自 CialloHook v1.7 源码目录的 `third/LE`、`third/LEP`，二进制均无版本信息。LE 为 Locale-Emulator（xupefei，https://github.com/xupefei/Locale-Emulator ，上游通常为 LGPL-3.0），但来源只能追溯到 CialloHook 仓库，未独立核实对应的上游版本与许可；LEP（Locale Emulator Plus）的来源与许可均未确认。本仓库不重新标注其许可。

**风险**（交付时转告用户）：

- 重启会脱离原启动链：Steam DRM、启动器、反作弊可能失效或拒绝启动。
- 部分系统或安全软件会拦截 LE 注入，表现为重启失败或游戏不启动。
- ACP 为 932 后，游戏/存档路径含 CP932 不能表示的字符（如中文用户名、中文安装目录）时，A 接口读写存档可能失败。
- 尚未在真实游戏中验证转区重启及其后的显示。

**交付提醒**：把 `version.dll`、`version.ini`、`uif_config.json` 与随附的 LE/LEP DLL 一起放到实际游戏 EXE 目录；首次启动可能闪一下后重新打开，属正常现象。出问题时把 `version.ini` 的 `[LocaleEmulator] Enable` 改为 `false`（或删除该段）并告诉 agent，改走 GBK 回写路线，或由用户手动以日文区域（LE、系统区域设置）运行。
