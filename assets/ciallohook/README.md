# 随包 CialloHook version.dll（x86 / x64）

用户指定纳入仓库的 CialloHook Release 核心 DLL 原样副本，作为 JIS 替换回注的第二种显示 hook，也是 64 位游戏唯一的随包 hook。仅作为输出资源复制，不加载执行。

| 项目 | x86：`version.dll` | x64：`x64/version.dll` |
|---|---|---|
| 来源 | 发布 `v1.7`（标签提交 `08aa96fb17ef115352932e5753f58b15dc978959`）的 `out/bin/x86/Release/version.dll` | 用户以 v1.7 源码目录本地构建的 `out/bin/x64/Release/version.dll` |
| 大小 | 1508352 字节 | 1722368 字节 |
| PE Machine | `0x014C`，x86（32 位） | `0x8664`，x64（64 位） |
| SHA-256 | `45a690c147467bf34168ecdeedb1d682848e99617dde41402faf83c291dc54ad` | `37257c9e71aaef006d21391998e89603ff4d8a09409a87496a5f8d1afc88c958` |
| 导出 | 209 项：`winmm` 与 `version` 两组代理函数（另含 x86 专有的 `*32Message`、`WOW32*`、`NotifyCallbackData` 共 12 项） | 197 项：同样的 `winmm` 与 `version` 代理函数 |
| CLI | `--hook ciallohook-x86` | `--hook ciallohook-x64`（或 `x64`） |

- 上游仓库：https://github.com/Lite0812/CialloHook 。两种构建中的 `CialloHook.dll`、`winmm.dll` 都与同目录 `version.dll` 逐字节相同。同一本地构建的 x86 `version.dll` 与上表 x86 副本逐字节相同（SHA-256 一致），说明两者出自同一 v1.7 源码。
- 导入表只有 Windows 系统 DLL：SHLWAPI、KERNEL32、USER32、GDI32、ADVAPI32、ole32、gdiplus、COMCTL32、bcrypt、SHELL32；无 VC 运行库或其他第三方 DLL 依赖，无需随附其他文件。
- 未随包：CialloLauncher、LE/LEP 转区依赖、PAK 工具、WebM 模块、pdb/lib 及上游示例 ini/json。

上游仓库根目录与本地源码目录均未发现 LICENSE 文件，GitHub license 元数据为 null；本仓库不将此第三方二进制重新标为 GPL。源码静态链接 Microsoft Detours、miniz、zstd、LZMA SDK 等组件，其许可以上游源码为准。

## 位数判断

DLL 位数必须与实际运行的游戏 EXE 一致；**位数不匹配的 DLL 不会被加载**，游戏照常启动但不会发生字符还原。EXE 位数看 PE 头的 Machine 字段：文件偏移 `0x3C` 处的 32 位值指向 `PE\0\0` 签名，其后 2 字节即 Machine，`0x014C` 为 32 位，`0x8664` 为 64 位。可只读运行：

```text
python -m python.common.jis_workflow arch "游戏目录/实际启动的.exe"
```

输出 Machine、位数及可用的 `--hook` 值。正式准备可加 `--exe "实际启动的.exe"`，hook 位数不符时拒绝生成。启动器与主程序位数可能不同，以实际加载脚本、绘制文本的进程为准。UIF 只有 32 位版本，64 位游戏只能选 CialloHook x64。

## 与 UIF 的分工

两者读取同一份 `uif_config.json`，同一游戏只选其一，不叠加两次字符替换。

| 项目 | UIF（[assets/uif](../uif/README.md)） | CialloHook（本目录） |
|---|---|---|
| 位数 | 仅 x86 | x86、x64 |
| 代理文件名 | `winmm.dll` | `version.dll`（可改名 `winmm.dll`） |
| 配置 | `uif_config.json` | `version.ini` + 同一 `uif_config.json` |
| 字符替换接口 | 默认 TextOutA/W、GetGlyphOutlineA/W，可配 `hook_functions` | TextOut、ExtTextOut、DrawText、GetGlyphOutline、GetTextExtent 系列 A/W，另有部分引擎兼容层 |
| A 接口写回 | 原接口 | 映射后的中文无法用 CP932 编码时改调 W 接口 |
| 字体 | 不改字体（JIS 模板关闭 font_manager） | 可替换为系统字体或外部字体文件，并调整字符集与字形度量 |
| 适用 | 32 位游戏的简单 GDI 路径 | 64 位游戏；UIF 未生效、需要更换含中文字形的字体或 `winmm.dll` 名称已被占用时 |

## 生成的配置与读取规则

JIS `artifacts(hook="ciallohook")` / `artifacts(hook="ciallohook-x64")` 或 CLI `--hook ciallohook-x86` / `--hook ciallohook-x64` 输出对应位数的 `version.dll`、相同的 `version.ini` 和 `uif_config.json`。`version.ini` 为无 BOM 的 UTF-8，只开启字形映射：

```ini
[CialloHook]
Charset = 0x00
Font =
EnableCharsetSpoof = false
EnableCnJpMap = true
CnJpMapJson = uif_config.json
CnJpMapReadEncoding = 932
```

另含 `[LoadMode] Mode = proxy`、`[EngineCompat]` 自动保守模式，以及写文件的 `[Debug]` 日志。

- **配置查找**：DLL 所在目录的 `<DLL名>.ini` → 同目录 `CialloHook.ini` → 当前目录的同名两项。改名为 `winmm.dll` 时，配置须同时改名为 `winmm.ini`（或 `CialloHook.ini`）。
- **映射格式**：`CnJpMapJson` 文件按 UTF-8 或带 BOM 的 UTF-16LE 读取；含 `source_characters` / `target_characters` 时按 UIF 格式读取，`source[i]` 显示为 `target[i]`，与本项目生成的方向一致；不读取 `enable` 字段。扁平 `{"中文": "代理字"}` 格式同样受支持，仅接受单字对单字。
- **代码页**：`CnJpMapReadEncoding = 932` 让 A 接口字节按代码页 932 转为 Unicode 后查表。CP932 用户自定义区 `F040..F9FC` 对应 `U+E000..U+E757`，因此 `--proxy-policy unused` 分配的私用代理字可被查到。
- **不要使用上游示例 `subs_cn_jp.json`**：其 3018 项与本项目随包 SExtractor 固定表（2999 项）有数十项不同，不能还原本批代理字。始终指向本批 `uif_config.json`。
- **资源查找**：映射 JSON、字体文件按已启用的补丁目录 → CustomPak → 游戏根目录查找；生成配置未启用 `[FilePatch]`，即读取游戏 EXE 目录。
- **字体**：`Font` 可写系统字体名（如 `SimHei`）或字体文件路径，文件内部名称不同时补 `FontName`；`RedirectFontCount` / `RedirectFromFont_i` / `RedirectToFont_i` 可只替换指定原字体。CP932 游戏不要随意设置非零 `Charset`：未映射的日文 A 接口文本会按新字符集解释而乱码。字体调整属于试注后的修正，由 agent 根据显示结果修改。
- **私用代理字**：运行时显示尚未在真实游戏中验证；外字字体（EUDC）或引擎自用的私用区码位应通过 `reserved_codepoints` 排除，见[公共 JIS 指南](../../guides/jis-substitution.md#私用代理字与保留码位)。

交付时提醒用户：把与游戏 EXE 位数一致的 `version.dll`、`version.ini` 与 `uif_config.json` 一起放到实际游戏 EXE 目录，再按引擎规则部署脚本/补丁，测试修改的对白及未修改 UI；`version.dll` 未加载时再试 `winmm.dll` 名称。已有同名 DLL/配置先检查合并，不盲目覆盖；不保证每个游戏都会加载代理 DLL。
