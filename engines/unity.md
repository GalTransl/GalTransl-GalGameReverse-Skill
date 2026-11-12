# Unity：UnityFS / serialized 容器、TextAsset、Utage 剧情表与 .bin/.idx 容器

目录输出遵循 [公共安全写出约定](../guides/python-reference-api.md#安全写出示例)：父目录须已存在，目标须不存在或为可复用的已有目录（不含同名产物或非空结果目录）；文件和链接拒绝。

## 选择路径

本页支持多层能力，不代表任意 Unity 游戏都使用同一种剧情格式。

| 已确认的输入 | 随包实现 | 能力边界 |
|---|---|---|
| 任意 Unity 游戏目录，先找文本位置 | [只读扫描](../python/engines/unity_scan.py)，流程见[文本定位](unity/locating-text.md) | 列容器版本、对象类别、TextAsset 名称/编码/熵、MonoBehaviour 类名；不解析 global-metadata |
| UnityFS 格式版本 6/7/8，块为 None/LZMA/LZ4/LZ4HC | [容器](../python/archives/unityfs.py) | 解包节点；替换节点后重建为**无压缩**数据块并逐节点读回 |
| serialized file v17–v22，小端，有或无 TypeTree | [容器](../python/archives/unity_serialized.py) | 头部、类型表、TypeTree、对象表、externals/script types/reference types；对象重定位重建 |
| TextAsset（class 49），在 serialized 文件或 UnityFS 包内 | [工作区 CLI](../python/engines/unity_textasset.py) | 整段替换 `m_Script` 并重建 serialized 与 bundle；不解析剧本方言、不生成 gt_input |
| Unity serialized file v20，小端、TypeTree 已剥离；对象类为 `Utage.AdvImportBook` | [容器](../python/archives/unity_serialized.py)、[剧情语义](../python/engines/unity_utage.py)、[工作区 CLI](../python/engines/unity_utage_extract.py) | 指定 Utage 布局的整表提取、UTF-8 变长回填、完整 `.assets` 重建 |
| 已有可靠字段位置的 Utage mono DAT 对齐字符串 | [局部字符串接口](../python/engines/unity.py) | 单记录解码和等占位替换；不能代替完整资产 writer |
| 同名 `.bin` + `.idx` 资源对，索引为 AES-CBC 密文 MsgPack | [容器](../python/archives/unity_arc.py) | 索引解密、成员解密与 `.bin`/`.idx` 重写；key/IV 为方言参数 |
| MsgPack 单字符串，内容含 `\text`/`\endtext` 块 | [剧本行接口](../python/engines/unity_snr.py) | 块内行替换与整串重打包；不解析块外的剧本命令 |

`*_Data`、`GameAssembly.dll`、StreamingAssets 只帮助识别，不能证明剧情是 Utage。Mono/IL2CPP 是运行时差异，也不能单独确定资源的序列化布局。不要把所有可读字符串、TextAsset 或 MonoBehaviour 自动当对白。

Utage book profile 仍只接受 TypeTree 已剥离的 v20 资产（其他版本即使容器可读也会拒绝）。任意 MonoBehaviour schema、字体图集重建、big-endian serialized、v16 及更早或 v23 以后的版本、LZHAM 块、旧 UnityWeb/UnityRaw 外壳都不支持；遇到时先补齐对应布局与测试，不套用现有 profile。工具仅使用标准库，不加载或执行游戏程序集、EXE、DLL、表达式，也不依赖额外 Unity 工具。

## 先扫描再选路径

不知道文本在哪时，先跑只读扫描，按 [文本定位流程](unity/locating-text.md) 的顺序判断和停止：

```text
python -m python.engines.unity_scan "/game" --output "/work/unity_scan"
```

扫描遍历游戏目录下的 `*_Data`（含 StreamingAssets），对 `.assets`、`globalgamemanagers`、`level*`、UnityFS 包（任意扩展名，按 `UnityFS\0` 魔数识别）逐个报告。默认预算：文件数 20000、对象/松散文件读取 2 GiB、每个包解压 256 MiB；超出时该容器标 `partial` 并在 `budget.exhausted` 列出，不静默丢弃。`preview` 只截取少量字符供定位，扫描结果放结果目录，不收入 Skill。

## UnityFS 容器

- 头部：`UnityFS\0`、BE u32 格式版本（只接受 6/7/8）、播放器版本串、引擎版本串、BE i64 文件总长、blocks info 压缩/原始长度、flags。总长必须等于文件大小。
- flags：低 6 位为 blocks info 压缩（0 无、1 LZMA、2 LZ4、3 LZ4HC；4 LZHAM 拒绝）；`0x40` 表示块表与目录合并，必须存在；`0x80` 表示 blocks info 在文件末尾；`0x200` 表示首个数据块前补齐到 16 字节。`0x200` 只在 2020.3.34、2021.3.2、2022.1.1 及以后引擎上按对齐解释；更早引擎上同一位曾被厂商加密方案使用，直接拒绝。其他未知位一律拒绝。
- 版本 7 及以上，头部结束后补齐到 16 字节再接 blocks info（或在 `0x80` 时直接接数据）。所有 padding 必须为零；数据块必须精确铺到 blocks info（`0x80`）或文件末尾。
- blocks info：16 字节哈希、块表（BE u32 原始长、压缩长、u16 flags；低 6 位压缩方式，`0x40` 为 streamed）、节点表（BE i64 偏移、i64 长度、u32 flags、NUL 结尾 UTF-8 路径）。节点 flags `0x4` 是 serialized 文件，`.resS`/`.resource` 节点是原始数据。路径重复、越界、未知位都拒绝。
- LZMA 块是 5 字节属性加无长度字段的 LZMA1 流，用标准库解码并核对长度；LZ4/LZ4HC 用随包纯 Python 块解码器，偏移、长度与输出大小全部校验。`BundleReader` 只解压读取范围覆盖的块，带解压预算；无压缩块按需直接读取。

### 重建

`unityfs.rebuild(data, {节点路径: 新内容})` 按原偏移顺序重组数据流，保留节点间原始字节、节点表顺序、路径、flags、格式版本、两个版本串、blocks info 的位置（头后或末尾）和 `0x200` 对齐；数据写成**一个无压缩块并带 streamed 标志**，blocks info 也不压缩。写出后用同一 reader 重读，逐节点比较。

- 选择无压缩而不移植 LZ4 压缩器：读写路径都能完整核对，且避免新增未经实机验证的压缩器。代价是文件变大，体积约等于全部节点之和；压缩包重建后可能大数倍。
- 运行时证据：Unity 构建选项本身可以产出无压缩 AssetBundle，已见到正式发行的 v6 包正是“单个无压缩块 + streamed 标志”的形态，因此该变体在格式上属于 Unity 自身产出的布局。但本工具产出的包**尚未在任何游戏中验证加载**，按“未验证运行时”交付。
- blocks info 哈希非零且内容有改动时拒绝重建（算法未确认）；全零哈希保持全零。
- 游戏若用自带清单（例如同目录的平台清单包）或在加载时传入 CRC 校验 bundle，内容改变后可能拒绝加载；遇到加载失败先查这一点，不要猜改清单。

预算：单文件 64 GiB 扫描、blocks info 16 MiB、块数 1M、节点 65536、读取默认 512 MiB、内存重建 512 MiB。

## serialized v17–v22

- 头部前 16 字节为 BE u32（metadata 长、文件长、版本、数据偏移），随后 1 字节端序（只接受 0 小端）和 3 字节保留零。v22 前述三个旧字段为 0，改由 BE u32 metadata 长、i64 文件长、i64 数据偏移、i64 保留零（共 48 字节头）给出。
- metadata：Unity 版本串、平台、TypeTree 开关、类型表、对象表、script types、externals、v20+ reference types、user information，必须精确读到 metadata 结尾。
- 类型项：classID、stripped、scriptTypeIndex；MonoBehaviour（114）或带脚本的 reference type 有 16 字节 script ID，之后 16 字节类型哈希；开 TypeTree 时接节点表：v17–v18 每节点 24 字节，v19 起 32 字节（多 u64 refTypeHash）；字符串偏移高位置 1 时查 Unity 内置公共字符串表，否则查本地表；v21 起普通类型后有依赖数组，reference type 后有类名/命名空间/程序集三个字符串。
- 对象表：每项先按 4 字节对齐，再读 i64 PathID；偏移 v22 为 i64、更早为 u32，后接 u32 长度与类型索引。对象不得重叠或越界。
- `walk_object` 按 TypeTree 读取整个对象：基本类型按名称定宽，数组为 `size`+元素，`0x4000` meta 标志表示读完后 4 字节对齐，必须正好读完对象。未知公共字符串、未知基本类型和 `ManagedReferencesRegistry` 都拒绝。
- `rebuild` 只改对象表里的偏移/长度和头部文件长，非目标对象、对象间零 padding 与不透明间隙、metadata 其他字节逐字节保留，并重读核对。对象须 8 字节对齐。

预算：metadata 16 MiB、单对象 32 MiB、内存重建 128 MiB、对象数 4M、TypeTree 节点 65536、单对象 walk 4M 步。

## TextAsset 整段替换

TextAsset（class 49）：

- 有 TypeTree：根类型必须是 `TextAsset`，顶层字段只能是 `m_Name`、`m_Script`（2017 之前的引擎另有 `m_PathName`），且都是 `string`；`m_Script` 的对齐以 TypeTree meta 标志为准。
- 无 TypeTree：按 `m_Name` 字符串 + `m_Script`（LE i32 字节长 + 原始字节 + 4 字节对齐）读取，引擎主版本小于 2017 时再读 `m_PathName`；必须正好读完对象，否则拒绝，不猜额外字段。
- `m_Script` 是原始字节，可以是 UTF-8（可能带 BOM、CRLF）、UTF-16、CP932 或二进制；不要统一解码后再写回。

```text
python -m python.engines.unity_textasset extract "/game/Game_Data/Data/scenario_bundle" "/work/ta" --name "_01*" --target "Game_Data/Data/scenario_bundle"
python -m python.engines.unity_textasset pack "/work/ta" "/work/ta_out" --text
```

- `extract` 可用 `--name`（m_Name 通配，可重复）、`--path-id`、`--node` 选择；写出 `original/<容器>`、`original/textassets/<m_Name>.txt|.bytes`、`metadata/manifest.json`、`reports/extraction.json` 和 `rebuilt/roundtrip/<target>`。提取时会用真实 writer 先做原样重建：serialized 必须逐字节相同，bundle 重读后所有节点与对象逐字节相同（bundle 本身因改为无压缩而不同）。
- `pack` 从 `replace/`（或 `--source-dir`）读取与 `original/textassets` 同名的文件。默认按原始字节替换；`--text` 把文件当 UTF-8 文本读入，再按 manifest 记录的原编码写回（保留 UTF-8 BOM / UTF-16 BOM；CP932 无法编码的字会报错，走 [JIS 替换流程](../guides/jis-substitution.md) 或改用原始字节）。二进制 TextAsset 不能用 `--text`。
- 回写会核对原容器与原文副本的哈希，重建 serialized 和 bundle，重读后要求：目标 TextAsset 的 `m_Script` 等于替换内容、`m_Name` 及 `m_Script` 以外的字节不变，其他对象与非 serialized 节点逐字节不变。结果在 `files/<target>`，另有 `readback/textassets/` 与 `reports/rebuild.json`。
- 这是整段替换，不理解剧本命令、姓名或语音标记；剧情翻译还需要该方言自己的 parser，见 [文本定位](unity/locating-text.md#textasset-行式剧本的观察)。游戏加载与显示未验证。

## Utage：定位与输入确认

1. 检查具体 `.assets`、场景文件及配套资源的大小。先用 `open_checked`、`read_index` 枚举索引，再以 `read_object(..., prefix=...)` 限量查看对象头。大型 `resources.assets` 和 `.resS` 不应为寻找文本而整包载入。
2. MonoBehaviour 头包含 GameObject PPtr、enabled、MonoScript PPtr 和 `m_Name`。通过本文件或外部 serialized asset 内的 MonoScript 解析类名、命名空间，确认 `Utage.AdvImportBook`，而非只凭 `.book` 后缀。
3. 外部 MonoScript 依赖用 `--dependency` 显式传入，例如含类型信息的 `globalgamemanagers.assets`。PPtr 的 fileID=0 指本文件，正数指外部表的一基序号。工具不会根据不可信资源路径自动打开任意外部文件；候选 book/chapter 缺类型信息会报错。
4. 区分原始日文、已有汉化和备份。**输入文件名可以不同于实际部署文件名**，用 `--target` 明确相对于游戏目录的目标路径。选择备份做基准时，不覆盖当前游戏文件，也不把备份名误当加载文件名。
5. 查看 `AdvChapterData` 的书本引用、设置表和入口跳转。它的 Character 表可以提供姓名上下文；当前设置表只读。表名排序第一可能是开发测试菜单，不能据此认定游戏开场。未核实可达性时明确说明。

可供 agent 执行的索引扫描示意：

```python
from python.archives import unity_serialized as asset
with asset.open_checked(source_path) as stream:
    index = asset.read_index(stream)
    candidates = [(obj.path_id, obj.size) for obj in index.objects if obj.class_id == 114]
```

预算：metadata 16 MiB、单对象 32 MiB、整文件重建 128 MiB；索引扫描文件上限 16 GiB（v21 及更早同时受 32 位文件长度约束）。输入与最多 16 份显式依赖合计不超过 192 MiB。超预算时保留诊断，缩小输入或完善流式 writer；不要提高限制后无界读取媒体。

## Utage book profile

当前 profile 为 `utage-book-v0-empty-entities`：

- `AdvImportBook`：MonoBehaviour 头 → `importVersion=0` → sheet 数组。
- 每张 sheet：`StringGrid` → `entityIndexTbl` → `entityDataList`。两份 entity 数组必须为空；非空表示尚未支持的实体布局，立即拒绝，不猜跳过长度。
- `StringGrid`：rows 数组 → name → type → textLength → headerRow。
- 每行：rowIndex → strings 数组 → isEmpty（bool + 对齐）→ isCommentOut（bool + 对齐）。每个字符串是 LE32 UTF-8 **字节长度**、原始字节、四字节绝对对齐的零 padding。
- `sheetName`、运行时列索引、调试缓存等不属于这份序列化布局，不因为类字段中存在就读写它们。
- 剧情表 `textLength` 是**所有行、所有单元格的 UTF-16 code unit 总数**，不是 UTF-8 字节数，也不是 Python 字符数；非 BMP 字符算两个单位。提取校验它，回写重新计算。剧情表缓存与实际不符时报错给出 book 名、表名及缓存值/实际值：资产可能已被其他工具修改，应改用原始备份，不自动修正缓存。
- `AdvChapterData`：MonoBehaviour 头 → chapterName → book PPtr 数组 → settings StringGrid 数组（没有 sheet 的 entity 数组）。其缓存可能保留旧导入值，当前只报告缓存差异并原样保留整个对象，不擅自修复设置。

数组、单字段、总单元格、偏移、padding 和尾部必须全部满足边界。文件解析完必须精确到结尾。新增布局先独立建 profile 与测试，不在当前解析器里吞掉未知尾部。

## 导出语义

- 按 `Command`、`Arg1`、`Text` 等**表头名称**定位列。允许前置空列、短行；拒绝重名表头。不要固定假定第 8、11 或 12 列是正文。
- 跳过 `isEmpty`、`isCommentOut`、`//` 注释命令及标签行；保留原始行、索引、单元格和标志。
- 当前对白规则包括空 Command 的默认文本/角色行，以及明确的 `Text`、`Character`；`Selection` 的 Text 是选项，跳转参数保持原样。
- 已确认不消费 Text 的标准命令（`Wait/Bg/Bgm/BgEvent/Jump/Se/StopSe/CharacterOff`）中的内容保留为非对白并计数。**未知命令带非空 Text 时停止语义导出**；先确定命令及其额外文本命令行为，再扩充规则。不能把“这一列有日文”当作显示证据。
- `name` 在 `message` 上方。当前 `name` **仅为只读上下文**：Arg1 可以是显示名，也可以是角色资源键；已知键用 Character.NameText 提供上下文，未解析值保留原样。Arg2 的模式/名称覆盖参数记入 metadata，不猜成可翻译姓名。当前只回写 `message`，姓名、角色键与设置表不在翻译范围内。
- 按 sheet 自身名字生成平铺 JSON；冲突时添加对象/表索引后缀，映射以 metadata 为准。无文本表不产生空文件。开发表与不可达表不会被悄悄删掉，报告只声明实际提取范围。
- 顺序、字段、姓名、变量、富文本标签和转义必须保留；换行可以比原文少，但不能新增或跨其他 token 移动。`<param=...>`、ruby 标签及其参数按原 token 保护；只翻译标签之间的正文。保留纯空白/控制用原文行，不接受把正常对白清空。不要合并物理行或跨条目重排。

## 工作区提取与回填

下面命令供 agent 执行；交付时遵循主流程，由 agent 负责回写打包。

```text
python -m python.engines.unity_utage_extract extract "/game/Game_Data/dialogue-backup.assets" "/game/new_extract" --dependency "/game/Game_Data/globalgamemanagers.assets" --target "Game_Data/sharedassets0.assets"
python -m python.engines.unity_utage_extract pack "/game/new_extract" "/game/new_extract/rebuilt/translation"
```

输出包含 `gt_input/`、`gt_output/`、`original/`、`metadata/`、`reports/` 和 `rebuilt/roundtrip/`。提取会通过实际表 writer 和容器 writer 重建全部目标书本，并要求完整资产原文往返逐字节一致。

回填从 `gt_output` 读取同名 JSON，缺失文件保留原文，未知文件名报告但不猜配。重新读取原资产/依赖并核对哈希，重新生成条目和 manifest，与 `gt_input`、metadata 比较；源文件或 manifest 被改就停止。用户误改 `gt_input` 时按主流程先保存修改、再恢复原文，不能改 manifest 绕过校验。

译文错误检查完全部表后一次列出，格式为 `<文件>.json #<JSON 下标>: 原因 (table '<表名>' row <表内行号>)`；下标从 0 开始，表内行号仅供对照原表。控制符不符时附期望/实际 token。CLI 的错误只输出到 stderr（退出码 1），结果 JSON 以 UTF-8 原样输出路径与表名，不做 `\u` 转义。

writer 会重建 UTF-8 字符串、四字节 padding、表 textLength、对象大小、八字节对象对齐、对象表偏移和文件长度。保留 PathID、类型、外部引用、非目标对象及不透明间隙。回填后重读容器的实际偏移、重读剧情并核对译文；反向撤销允许的文本编辑后要求原 book 字节完整恢复。配套 `.resS/.resource` 引用与数据保持原样。

打包结果在 `files/<target>`，另有 `readback/gt_input` 和回写报告。它是**完整 serialized asset**，不是自动可加载的 `patch` 包。尚未验证的游戏加载规则不能从格式自洽推断。

## 小规模试注与显示

按主流程用表格交代来源、脚本编码、对象/表/JSON/文本数与各阶段验证状态。推荐一个已核对的开场表，或注明触发位置尚待确认的候选。用户把少量译文按同名放回 `gt_output` 后，agent 实际生成测试资产。

正文与 JSON 均为 UTF-8，优先直接回写；**不套用 CP932 的 JIS 替换或 UIF hook**。变长离线回读成功仍需测试实际加载和显示。用户部署时先另存当前同名文件，将 `files/` 中的相对路径放回对应位置，日文备份另保留；覆盖游戏和启动游戏沿用授权边界。

若中文缺字/方框，检查实际使用的 Unity 字体、fallback 与动态/静态图集覆盖；修改脚本编码不能解决缺字。若补丁未生效，核对部署文件名、对象来源和后加载资源；若崩溃或截断，核对 schema、缓存长度、对象偏移和外部引用。不要把磁盘 UTF-8 与运行时 .NET UTF-16 字符串混为一谈。

确认实际组件使用 TextMeshPro 后，按 [TMP 字体构建与接入方法](unity/tmp-fonts.md) 准备字符集、烘焙配套 SDF 字体/材质/图集，并验证资源引用和显示。该页只提供方法论，当前没有随包 TMP 构建器；普通 Unity Font 或非 TMP 文本组件另行适配。

## 适配新 Utage 布局

以资源本身、类型信息和静态程序元数据确认字段顺序、序列化属性、数组与引用；TypeTree 存在时优先利用它，缺失时必须证明完整 schema。允许静态读取 IL2CPP 元数据或反汇编以确认字段/命令语义，不加载执行游戏代码。仅从可打印字符串反推字段位置不足以启用 writer。

验证顺序：完整消费对象 → 原文重建相同 → 变长中文及非 BMP 字符 → 重新解析、核对未改字段与对象 → 游戏显示另测。增加相应合成正反例，尤其是列偏移、注释、缓存计数、非空实体表、未知命令、原文/manifest 改动。若存在本地化多语言列、命令覆盖插件、不同导入版本或实体缓存，不把当前规则扩大为“全部 Utage 支持”。

回归入口：[test_unity_utage.py](../tests/test_unity_utage.py)；UnityFS、serialized v17–v22、TextAsset 与扫描见 [test_unityfs.py](../tests/test_unityfs.py)。提交前运行相关测试与 `python tools/check_skill.py`；运行报告只放结果目录。

## 容器实现来源

UnityFS、serialized v17–v22、TypeTree 公共字符串表和 TextAsset 布局为独立实现，对照了公开的格式描述并用合成样本及真实文件只读核对；未复制外部实现代码，LZ4 块解码按公开的 LZ4 块格式规范编写。参考项目与许可见 [unity-containers](../provenance/unity-containers.json)；使用本 Skill 不需要访问这些仓库。

## 旧 DAT 局部接口与来源

`unity.decode_aligned_string(data, length_offset)` 要求可靠长度字段位置、严格解码及零 padding；`encode_aligned_string(text)` 生成独立记录。`replace_aligned_string` 只允许新旧记录含 padding 的总占位相等，变长时抛 `NotImplementedError`，因为它不了解外层索引/指针。此旧接口的 padding 按字符串字节长度计算；它没有固定 magic，不能批量套用所有 `.dat`。

旧 leaf 改编自 SExtractor `src/extract_Unity_dat.py`、`src/engine.ini` 的 Unity_dat 段（commit `8d8d976fd04ae54e7c677705af937273d04a376a`，GPL-3.0-only），保留原模块的许可说明；来源记录见 [sextractor-core](../provenance/sextractor-core.json)。它把正则候选扫描改为显式 offset，并增加严格边界及变长拒绝。

完整 book 路径参考了 [unity-text-locator](https://github.com/timeance/unity-text-locator) 的 Utage 对象定位、行/列定位和读回验证思路（该项目 AGPL-3.0-only），未复制其实现代码。这里独立实现 stripped-TypeTree profile、表头识别、命令语义和 v20 writer，随本项目按 GPL-3.0-only 提供；使用本 Skill 不需要访问该外部仓库。

## .bin/.idx 资源容器

与 Utage 表路线无关，这是另一类 Unity 归档：`.bin` 放密文成员，`.idx` 放加密目录。

- `.idx` 记录：`i32` 密文长度 + AES-CBC/PKCS#7 密文；长度必须是 16 的倍数且不越界。
- 解密后的记录是 MsgPack 映射，键至少包含 `fileName`、`index`、`size`。
- 参考实现的 `fileName` 用 str16、键用 fixstr、整数用 int32；读取端同时接受 fixstr/str8/str16/str32 与各整数宽度。
- `.bin` 布局为每条 `u32` 密文长度 + 密文；目录中的 `index` 指向密文起点，不是长度字段。
- 成员整体用同一 AES-CBC 密钥解密，PKCS#7 去填充；填充非法即拒绝。
- key 与 IV 是参考工具写死的 ASCII 常量，属于单个会社/样本的方言参数，不是 Unity 通性；
  其他构建必须提供自己的 key 对，不把这两个常量推广。
- `build_bin` 重新加密并重算 `u32` 长度前缀与偏移，重新解析索引、解密每个成员比对后才返回。
- 不做：索引中未出现的成员、加密 key 推断；UnityFS 与 serialized 文件走上文的独立容器。

```python
from python.archives.unity_arc import build_bin, read_index, read_member

entries = read_index(idx_bytes)
member = read_member(bin_bytes, entries[0])
rebuilt_bin, rebuilt_idx = build_bin({"data/scenario.bin": patched_bytes})
```

## SNR 剧本（MsgPack 字符串）

- 整个文件是一个 MsgPack 字符串；不是 `serialized file`，也不能按 `.assets` 解析。
- 字符串内容按 `\n` 分行；`\text` 前缀开启块，`\endtext` 前缀关闭块，其余块内行是显示文本。
- 标记行按前缀识别，块行上的附加字段原样保留。
- 行尾换行会产生一个末尾空行，读写都必须保留；不能用“每行补一个换行”的方式重建。
- 只允许替换块内行的整行内容；含 `\n`/`\r` 或本身以标记开头的译文拒绝。
- 重打包后重新分行比对行序、块标志与每行文本。
- 不做：块外命令语义、跳转/变量修复、多字符串结构或压缩外壳。

```python
from python.engines.unity_snr import apply_snr_texts, open_snr

script, lines = open_snr(snr_bytes)
writable = {line.index: line.text for line in lines if line.in_text}
patched = apply_snr_texts(snr_bytes, {1: "新しい行"})
```

- 来源：翻译肋手 v4.9D 的 `GameRes.Unity.ArcBIN`、`BinDeserializer`、`ArcSNR`（GARbro 派生）。
- 独立改写：严格记录边界、索引长度与密文块对齐校验、写回重算偏移；
  SNR 不再复制“每行后追加换行”导致空行累积的行为。
- 测试：[test_unity_arc.py](../tests/test_unity_arc.py) 覆盖 AES FIPS/SP800 向量、MsgPack 记录、
  `.bin`/`.idx` 往返、截断拒绝、SNR 块标志、no-op 字节一致与非法译文拒绝。
- 未使用真实 `.bin`/`.idx` 或 SNR 样本，未验证游戏加载与显示。
