# Unity：Utage 剧情表与 serialized asset 回写

## 选择路径

本页支持两层能力，不代表任意 Unity 游戏都使用同一种剧情格式。

| 已确认的输入 | 随包实现 | 能力边界 |
|---|---|---|
| Unity serialized file v20，小端、TypeTree 已剥离；对象类为 `Utage.AdvImportBook` | [容器](../python/archives/unity_serialized.py)、[剧情语义](../python/engines/unity_utage.py)、[工作区 CLI](../python/engines/unity_utage_extract.py) | 指定 Utage 布局的整表提取、UTF-8 变长回填、完整 `.assets` 重建 |
| 已有可靠字段位置的 Utage mono DAT 对齐字符串 | [局部字符串接口](../python/engines/unity.py) | 单记录解码和等占位替换；不能代替完整资产 writer |

`*_Data`、`GameAssembly.dll`、StreamingAssets 只帮助识别，不能证明剧情是 Utage。Mono/IL2CPP 是运行时差异，也不能单独确定资源的序列化布局。不要把所有可读字符串、TextAsset 或 MonoBehaviour 自动当对白。

当前完整工作区路径不支持 UnityFS/AssetBundle 压缩外壳、其他 serialized 版本、带 TypeTree 的文件、任意 MonoBehaviour schema 或字体图集重建。遇到这些情况先补齐对应容器/类型布局，不套用本 profile。工具仅使用标准库，不加载或执行游戏程序集、EXE、DLL、表达式，也不依赖额外 Unity 工具。

## 定位与输入确认

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

预算：metadata 16 MiB、单对象 32 MiB、整文件重建 128 MiB；索引扫描文件上限 16 GiB（同时受 v20 自身 32 位文件长度约束）。输入与最多 16 份显式依赖合计不超过 192 MiB。超预算时保留诊断，缩小输入或完善流式 writer；不要提高限制后无界读取媒体。

## Utage book profile

当前 profile 为 `utage-book-v0-empty-entities`：

- `AdvImportBook`：MonoBehaviour 头 → `importVersion=0` → sheet 数组。
- 每张 sheet：`StringGrid` → `entityIndexTbl` → `entityDataList`。两份 entity 数组必须为空；非空表示尚未支持的实体布局，立即拒绝，不猜跳过长度。
- `StringGrid`：rows 数组 → name → type → textLength → headerRow。
- 每行：rowIndex → strings 数组 → isEmpty（bool + 对齐）→ isCommentOut（bool + 对齐）。每个字符串是 LE32 UTF-8 **字节长度**、原始字节、四字节绝对对齐的零 padding。
- `sheetName`、运行时列索引、调试缓存等不属于这份序列化布局，不因为类字段中存在就读写它们。
- 剧情表 `textLength` 是**所有行、所有单元格的 UTF-16 code unit 总数**，不是 UTF-8 字节数，也不是 Python 字符数；非 BMP 字符算两个单位。提取校验它，回写重新计算。
- `AdvChapterData`：MonoBehaviour 头 → chapterName → book PPtr 数组 → settings StringGrid 数组（没有 sheet 的 entity 数组）。其缓存可能保留旧导入值，当前只报告缓存差异并原样保留整个对象，不擅自修复设置。

数组、单字段、总单元格、偏移、padding 和尾部必须全部满足边界。文件解析完必须精确到结尾。新增布局先独立建 profile 与测试，不在当前解析器里吞掉未知尾部。

## 导出语义

- 按 `Command`、`Arg1`、`Text` 等**表头名称**定位列。允许前置空列、短行；拒绝重名表头。不要固定假定第 8、11 或 12 列是正文。
- 跳过 `isEmpty`、`isCommentOut`、`//` 注释命令及标签行；保留原始行、索引、单元格和标志。
- 当前对白规则包括空 Command 的默认文本/角色行，以及明确的 `Text`、`Character`；`Selection` 的 Text 是选项，跳转参数保持原样。
- 已确认不消费 Text 的标准命令（`Wait/Bg/Bgm/BgEvent/Jump/Se/StopSe/CharacterOff`）中的内容保留为非对白并计数。**未知命令带非空 Text 时停止语义导出**；先确定命令及其额外文本命令行为，再扩充规则。不能把“这一列有日文”当作显示证据。
- `name` 在 `message` 上方。当前 `name` **仅为只读上下文**：Arg1 可以是显示名，也可以是角色资源键；已知键用 Character.NameText 提供上下文，未解析值保留原样。Arg2 的模式/名称覆盖参数记入 metadata，不猜成可翻译姓名。当前只回写 `message`，姓名、角色键与设置表不在翻译范围内。
- 按 sheet 自身名字生成平铺 JSON；冲突时添加对象/表索引后缀，映射以 metadata 为准。无文本表不产生空文件。开发表与不可达表不会被悄悄删掉，报告只声明实际提取范围。
- 行数、顺序、字段、姓名、换行、变量、富文本标签和转义必须保留。`<param=...>`、ruby 标签及其参数按原 token 保护；只翻译标签之间的正文。保留纯空白/控制用原文行，不接受把正常对白清空。不要合并物理行或跨条目重排。

## 工作区提取与回填

下面命令供 agent 执行；交付时遵循主流程，由 agent 负责回写打包。

```text
python -m python.engines.unity_utage_extract extract "/game/Game_Data/dialogue-backup.assets" "/game/new_extract" --dependency "/game/Game_Data/globalgamemanagers.assets" --target "Game_Data/sharedassets0.assets"
python -m python.engines.unity_utage_extract pack "/game/new_extract" "/game/new_extract/rebuilt/translation"
```

输出包含 `gt_input/`、`gt_output/`、`original/`、`metadata/`、`reports/` 和 `rebuilt/roundtrip/`。提取会通过实际表 writer 和容器 writer 重建全部目标书本，并要求完整资产原文往返逐字节一致。

回填从 `gt_output` 读取同名 JSON，缺失文件保留原文，未知文件名报告但不猜配。重新读取原资产/依赖并核对哈希，重新生成条目和 manifest，与 `gt_input`、metadata 比较；源文件或 manifest 被改就停止。用户误改 `gt_input` 时按主流程先保存修改、再恢复原文，不能改 manifest 绕过校验。

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

回归入口：[test_unity_utage.py](../tests/test_unity_utage.py)。提交前运行相关测试与 `python tools/check_skill.py`；运行报告只放结果目录。

## 旧 DAT 局部接口与来源

`unity.decode_aligned_string(data, length_offset)` 要求可靠长度字段位置、严格解码及零 padding；`encode_aligned_string(text)` 生成独立记录。`replace_aligned_string` 只允许新旧记录含 padding 的总占位相等，变长时抛 `NotImplementedError`，因为它不了解外层索引/指针。此旧接口的 padding 按字符串字节长度计算；它没有固定 magic，不能批量套用所有 `.dat`。

旧 leaf 改编自 SExtractor `src/extract_Unity_dat.py`、`src/engine.ini` 的 Unity_dat 段（commit `8d8d976fd04ae54e7c677705af937273d04a376a`，GPL-3.0-only），保留原模块的许可说明；来源记录见 [sextractor-core](../provenance/sextractor-core.json)。它把正则候选扫描改为显式 offset，并增加严格边界及变长拒绝。

完整 book 路径参考了 [unity-text-locator](https://github.com/timeance/unity-text-locator) 的 Utage 对象定位、行/列定位和读回验证思路（该项目 AGPL-3.0-only），未复制其实现代码。这里独立实现 stripped-TypeTree profile、表头识别、命令语义和 v20 writer，随本项目按 GPL-3.0-only 提供；使用本 Skill 不需要访问该外部仓库。
