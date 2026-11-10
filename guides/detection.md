# 从游戏目录识别引擎和容器

## 识别是证据链，不是扩展名匹配

1. 查看有限深度目录：可执行文件名、资源包、剧本目录、运行库、配套表。不要运行可执行文件或加载 DLL。
2. 检查完整魔数和关键头字段，并验证表项数量、文件大小、偏移范围。后缀与目录布局只是弱证据。
3. 同时保留多个候选。同一扩展名可能被不同引擎或方言复用；后缀、厂商品牌和可打印字符串均不足以独立判定。
4. 结合源文件与引擎页面核查版本和方言。某库“支持”只代表特定 parser 被注册，不代表该游戏或 writer 能工作。
5. 若只知道归档格式，先解出候选剧本，再识别脚本语义；厂商、归档格式与脚本引擎之间并非一对一。

辅助器 [detect.py](../python/detect.py) 最多扫描有限文件/深度和文件头，返回 `weak-extension`、`weak-layout`、`header-hint`、`footer-hint`、`content-probe`、`layout-probe`、`volume-set`。它不校验完整目录、不识别全部加密、不执行程序，也不直接选 writer。所有读取都有字节上限：文件头 2 KiB、QLIE 包尾 256 字节、PE 头、BGI 索引、重复归档的头部哈希。

### 证据强度、展示上限与扫描中断

- 每条证据带 `strength`：`probe`（魔数、包尾、内容或布局探测）> `filename`（特征文件名）> `extension`（扩展名）。`candidates[engine]` 按强度排序，同强度按发现顺序；`max_evidence` 默认 12（CLI `--max-evidence N`），只限制**展示**。每个候选中出现过的每种强度至少保留 1 条，因此上限小于强度种类数时展示条数可略超上限；为 0 时只给计数。
- `candidate_stats[engine]` 提供 `total_hits`、`shown_hits`、`matched_files`、`capped` 与 `by_strength`（各强度的命中数）。hit 是证据条数：同一文件可贡献多个 hit，不能把 `total_hits` 当文件数。
- `evidence_capped` 表示有候选证据被展示上限裁剪。只显示 12 条不等于只发现 12 个成员/文件，更不证明覆盖全部脚本。
- `truncated` 表示扫描中断，`truncated_reason` 列出原因：`max_files`、`max_depth`、`max_seconds`（CLI `--max-files`、`--max-depth`、`--max-seconds`）。统计只覆盖实际扫描范围，与展示裁剪不同，两者都不是解析成功率。
- 遍历为广度优先；同一层先进入 `game`、`data`、`archive`、`pac`、`pack`、`resources`、`StreamingAssets`、`*_Data` 等常见目录，避免深层插件目录先耗尽文件配额。

### 版本与运行环境字段

- `format_versions` 汇总读到的头部版本（计数）：`yuris-ypf`（YPF 头版本字，只有 v482 有完整路线）、`qlie-filepack`（包尾 `FilePackVerX.Y`，随包 reader/writer 覆盖 3.0 与 3.1）、`renpy-rpa`（`RPA-3.0`、改名的 `ARC-3.0`、`RPA-3.2`、`RPA-2.0`；随包 reader 只接受 3.0/ARC-3.0）、`entis`（子类型）、`unityfs`（bundle 格式版本）、`unity-serialized`（serialized 版本）。对应 hit 另带 `version`、`unity_version` 或 `subtype`。
- Entis：偏移 `0x10` 为 `ERISA-Archive file` 的标为 NOA 归档（`subtype: noa`，随包无 reader），为 `Cotopha Image file` 的才是 CSX；其他子签名标 `other`。
- `executables` 列出扫描根及其下两层内 `*.exe` 的 PE Machine：`x86`、`x64`、`arm64` 等，非 PE 记 `not-pe`。选择 JIS hook DLL 时按实际游戏 EXE 的位数，不按启动器。
- `unity`：`scripting_backend` 为 `mono`（存在 `*_Data/Managed/Assembly-CSharp.dll`）、`il2cpp`（存在 `GameAssembly.dll` 或 `il2cpp_data`）、两者或 `undetermined`。这只是运行时后端，不决定资源或剧情的序列化布局；`.assets`、`globalgamemanagers` 的 serialized 版本仅在头部声明大小与实际大小一致时报告。

### 已有补丁与旧实验产物

`existing_patch_hints` 列出可能是已有补丁或旧实验产物的线索（每条带同样的 `note`，展示上限见 `existing_patch_hint_stats`）。它们只提示“先确认原版来源再提取”，不证明文件被修改：

- `hook-dll`：EXE 同目录（或扫描根）中的常见代理 DLL 名，如 `winmm.dll`、`version.dll`、`d3d9.dll`、`dinput8.dll`、`dsound.dll`、`winhttp.dll`，附 PE 位数。
- `patch-config`：`uif_config.json`、`CialloHook.ini`、`version.ini`、`winmm.ini`、`jis-mapping.json`、`doorstop_config.ini`。
- `backup-file`：`*.bak`、`*.org`（含 `*.exe.org`）、`*.orig`；`copy-named-file` / `copy-named-directory`：名字带“副本”“备份”“コピー”“- Copy”“backup”等的 EXE/DLL/归档或目录。
- `duplicate-archive`：同名或同大小的归档，大小一致且前 4 MiB 的 SHA-256 相同；只比较头部，总量有文件数/字节/时间上限，超限时给出 `duplicate-check-capped`。
- `bgi-loose-override`：与 BGI `.arc` 成员同名的松散文件（`.arc` 同目录或扫描根），只读 `.arc` 索引。逐个试探有限字节的编码：整体可严格解码为 UTF-8 且含非 ASCII，记 `utf-8`；否则按 NUL 分段统计，记 `utf-8-strings`、`cp932-compatible-strings`（日文 CP932 与 GBK 都可能落在此类）或 `undetermined`。出现 UTF-8 时 `summary` 为“疑似 UTF-8 汉化覆盖”。提取应以 `.arc` 内原版成员为准，松散文件另作对照。

### 派生目录与目录兜底

- 默认跳过派生目录：名字以 `_extract` 结尾或带 `_extract_…` 后缀（如 `_extract_2`、`_extract_pack_…`）的目录，`…Extract…_Output` 形式的解包输出，同时含 `gt_input` 与 `metadata`/`reports` 的工作区，以及根下有 `verification.json` 的封包输出。仅以 `_output` 结尾的普通目录（如媒体插件的 `audio_output`）照常扫描。被跳过的目录列在 `skipped_directories`（展示有上限，总数见 `skipped_directory_count`）。这些是旧提取结果或第三方解包输出，不是游戏原件；确需检查时加 `--include-derived`。被扫描的根目录本身不受此规则影响。
- 文件头未命中任何内置规则时，用前 4 字节查 [formats.json](../catalog/formats.json)，命中写入 `catalog_hints`（标签最多 5 个、总数有上限，统计见 `catalog_hint_stats`）。常见通用头（PNG、Ogg、RIFF、MZ、ZIP、CAB 等）和小于 `0x10000` 的版本/计数字不参与。它只是资料线索：用 `tools/query_catalog.py --magic` 继续查来源，不代表存在对应引擎页或已支持。
- CLI 固定以 UTF-8 输出 JSON，不受控制台代码页影响。

```text
python /path/to/GalTransl-GalGameReverse-Skill/python/detect.py /path/to/game --max-evidence 24
```

不能把“没有候选”解释为“没有脚本”。归档内成员需另读索引/探测；目录检测不会因此自动获得包内全部内容。

## 按证据查引擎页

用候选引擎名、扩展名或魔数搜索 `engines/`，或查 [引擎页目录](../catalog/engines.md)（[JSON 版](../catalog/engines.json)含别名与公开函数），找到对应的 `engines/<id>.md`，在该页核对魔数、布局、配套文件、版本和下一层解析入口。具体格式的识别表与例外维护在引擎页；此处只规定识别流程。

## 搜索资料目录

[formats.json](../catalog/formats.json) 保存上游有效编译/注册来源。目录行数不是支持引擎数：它包含同引擎变体、归档资源集合和某些只读格式。`CanWrite`、`Create` 的源声明不等于所有读取版本都可重封包。

用随包[查询器](../tools/query_catalog.py)筛选，默认每页 20 项；`--details` 展开当前页的原始表达式、继承和来源证据。条件同时使用时取交集；`--text` 可搜索别名、源路径和描述。返回 `total`、`returned` 和 `next_offset`，用 `--offset` 接续；不要把一页结果当完整目录。

```text
python /path/to/skill/tools/query_catalog.py --tag XP3 --details
python /path/to/skill/tools/query_catalog.py --extension .dat --limit 10 --offset 0
python /path/to/skill/tools/query_catalog.py --magic 5850330d
```

魔数为文件顺序的四字节十六进制。无固定魔数的格式不会由 `--magic` 命中，仍需结合其他证据。

存储 schema 2 保留原字段与全部证据：`shared` 中的对象由 `{"$ref":索引}` 引用；`{"$source":[路径,行号,可选符号]}` 复用顶层来源版本。条目内 `null` 路径表示该条目的源路径，空符号或以 `.` 开头的符号相对 `qualified_class`。每个条目的根 `source` 总保留路径。程序读取请用 [load_formats](../python/common/source_catalog.py)，它兼容旧 schema 1 并还原完整 schema 1 对象；生成工具直接写去重格式，无需外部源码即可查询。

优先按完整魔数、格式 Tag、别名、扩展名的组合查找，接着读随包的具体引擎页及对应 Python 模块；`source_file` / 源符号仅作历史出处记录，不要求访问其指向的外部代码。`family_hint` 或上游源码目录名只是线索；同一目录可能收录多个格式族，不可机械合并为同一引擎。

`source-registries.json` 中的 `source_only` 表示记录来自上游注册，不表示当前 Python 没有实现，也不表示已有可用 writer。能力需对照引擎页/模块，缺口按 [增补指南](extending-engines.md) 根据随包资料与样本继续只读研究并补齐实现。

## 先索引，再判定内层

优先使用只读头/索引的接口，先验证条目数和范围，再探测候选成员的小段头部。不要为列目录就把整包、大视频或全部成员载入内存。索引预算与成员预算分别设置。

对选中成员按已确认的层次读取、解密或解压，再检查内层签名、版本和结构。压缩封装只描述存储方式，不能证明其中是剧本；无后缀成员也可能是目标。成员名称、目录名和总数都不能代替内容分类。

## 安全解包

- 先看 index，检查条目数、单项大小、累计大小、压缩比；真正解压过程中还要限制实际产出。
- 对每个 archive entry 保留原始名称/标识，不要先放进字典而丢失重名信息。先用 [validate_names](../python/common/safety.py) 检查路径和冲突。
- 拒绝绝对路径、盘符/UNC、`..`、NUL、Windows ADS、设备名、尾随点/空格，以及大小写/NFC 归一化后的重复输出。
- 不跟随 symlink、hardlink、junction/reparse point。输出根及其父级必须可信，不能由恶意并发进程替换。
- 加密层和压缩层顺序必须符合格式。仅看到“解包成功”不能确认返回的是明文；若上游在解码失败时回退原始字节，不能照搬并标为成功。
- `write_new_tree()` 只写不存在或已存在的普通空目录，且会检查所有输出；它无法补救 parser 在调用前就无界分配内存。叶子参考的参数限额同样必须设置。
- 索引含 Pickle 时只能解释允许的数据 opcode，禁止不受限 `pickle.loads`。GARbro `Formats.dat` 是 .NET BinaryFormatter 对象图，不是 JSON 或运行时依赖。

对纯资源格式，不要因为能解包图片或声音就宣称已找到对白。需要对实际剧本做下一层证据检查。
