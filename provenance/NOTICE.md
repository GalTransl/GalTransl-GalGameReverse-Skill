# 来源、改编与许可证说明

本 Skill 是可独立复制的资料与源码包，不包含商业游戏资源、不需要调用四个参考项目，也不导入 GalTransl。所有来源仓库的精确提交、链接和注册位置见 [sources.json](sources.json)；每组改编参考的 JSON 记录及源码头进一步列出文件、符号、算法范围和验证状态。

## 许可分层

- 新写的 Skill 文档、目录整理、公共辅助及测试按根 [GPLv3 许可证](../LICENSE) 提供；可以依据该许可证第3版或后续版本使用这些新增部分。**本包已有 GPL 许可基础，允许按义务移植 GPL 算法；GPL 本身不是算法缺口，也不要求实现只能来自 MIT。**
- 基于 GPL 源码改编的引擎参考保留适用许可、版权/作者与修改说明；分发时履行对应的源码及许可提供义务。不能因为从 Rust/C# 换成 Python 就当成无许可负担的独立代码。
- MIT 来源仍保留原版权、MIT许可和免责声明；本包的整理不删除其权利和义务。
- 原始上游文件或第三方片段有更具体声明时，必须同时保留该声明。仅把不同许可的代码放在不同目录不自动解决所有组合分发问题。
- 这里是来源与分发说明，不以根目录某一种许可覆盖所有第三方材料。未明确许可的源码不应直接复制进来；只有资料线索不代表已经分发相应实现。

## 参考项目

| 来源 | 精确版本位置 | 许可及保留声明 |
|---|---|---|
| GARbro-Mod | `sources.json` / 各参考头 | [MIT 原文](licenses/MIT-GARbro.txt)，Copyright (c) 2014–2020 morkt；相关文件头可能有更具体年份/作者 |
| VNTextPatch-net8 | 同上 | [MIT 原文](licenses/MIT-VNTextPatch.txt)，Copyright (c) 2021 arcusmaximus |
| msg-tool | 同上 | [GPLv3 原文](licenses/GPL-3.0.txt)，Cargo.toml 标识 GPL-3.0-or-later；归属上游 lifegpc/msg-tool contributors 及文件中列出的原作者 |
| SExtractor | 同上 | [GPLv3 原文](licenses/GPL-3.0.txt)，归属上游 satan53x/SExtractor contributors 及具体工具的原作者 |

GARbro 的根 MIT **不代表所有内嵌代码**。必须区分已经明确的许可义务与真正未知授权：

- KogadoCocotte 已有 GPLv2 声明，不应标为“授权不明”。先核对具体文件是 GPLv2-only 还是 GPLv2-or-later，再处理与本包 GPLv3 组合的兼容性；若是 v2-only，不能未经依据直接作为 GPLv3 组合派生实现分发。
- Lz4Stream 有原作者 BSD 式声明，也不是“未知授权”。核对实际条款及版本、保留版权/条件/免责声明，确认组合分发的兼容性，而非因根许可证不同就一概排除。
- NScripter 部分压缩段注明 ONScripter/Okumura 来源；来源名本身不能替代具体文件/片段的许可审查，不能据此把整个来源都标成未知。
- 真正缺少授权文本、归属不明或条款版本无法确认的材料，才记录为“许可待核”，在补齐依据前不直接复制实现。资料研究、独立范围界定仍可继续。

上述组件不因出现在来源清单就已随本包分发；新增移植应逐文件记录实际采用范围及义务。把不同许可代码放在不同目录，不自动解决组合许可问题。

## 改编方式

归档布局与解密资料另见 [算法出处清单](garbro-archive-excerpts.json)及[逐文件原通知](garbro-archive-notices.md)。Markdown 中的 C# 片段是独立的算法资料，保留来源的字段和变换表达式，不编译、链接或导入为本包运行代码；界面、writer、案例注释和内置逐游戏名称列表已省去。Kogado Cocotte 原片段仍依其 GNU GPL Version 2 声明分发，附 [GPLv2 原文](licenses/GPL-2.0.txt)，不改标 GPLv3；LZ4 的 BSD 条款和其他文件原通知同时保留。没有文件级通知的组件不据此认定为无版权，亦不以根 MIT 覆盖另有声明的片段。

公共 JIS 替换及固定字表参考 SExtractor，详见 [版本、许可与改动记录](jis-substitution.json)。`python/common/jis_cn_jp.json` 为上游字表原样副本；配套公共模块重构为显式编码会话并增加失败检查，保留 GPL 通知。另随包保存用户指定的 UIF x86 DLL，来源、哈希和独立许可状态见 [UIF 说明](../assets/uif/README.md)，不将其重新标为 GPL；未分发字体。

- 将非 Python 参考中的结构、固定宽度整数、位运算、索引、编码和重定位语义转译为 Python，而非只换语法或包装原 executable。
- 将 SExtractor 的原生 Python 算法拆成显式参数/返回值，移除 GUI、全局状态、本机路径、import时批处理及隐式 native 扩展。
- 为不完整、宽松或游戏专用的上游路径保留边界，并加入拒绝未知版本、越界、丢失编码和冲突的条件。不能继承未知 opcode 的缺省空模板或解码失败回退原 bytes 后声称成功。
- 资料中描述的 upstream writer 不一定在本包实现；每篇引擎页及对应 module docstring 才是这份参考的实际适用范围。`source_only` 是上游注册证据，不是当前 Python 能力状态。

### BGI 的 MIT / GPL 来源

BGI 归档/DSC、标准 V1 扫描与工作流参考 GARbro-Mod 的 `ArcFormats/Ethornell/ArcBGI.cs`（MIT）、VNTextPatch-net8 的 `Scripts/Ethornell/`（MIT）与 msg-tool 的 `src/scripts/bgi/`（GPL-3.0-or-later）。精确提交见 `sources.json`，采用的文件/符号范围见当前模块头。MIT 版权、许可和免责声明与 GPL 派生部分的通知、许可及源码义务都须保留，不能把混合改编统一改标 MIT。

这些是开发期算法来源，不是使用者运行依赖。许可允许移植不等于已经验证正确：标准 V1 的显式布局不含 `0x0461`，上游的宽松回退不能移植成支持声明；BP/BSI 等上游入口也不自动变成本包能力。

## 不随包提供的内容

游戏专有资源、可执行文件、私有密钥、完整上游工作树、.NET BinaryFormatter `Formats.dat`、GUI或 native `.pyd`。如格式需要用户游戏的辅助表或授权获取的密钥，调用者必须显式提供，不会后台下载或猜测成功。

## 验证声明

合成 fixtures 和局部算法测试不是特定游戏的可用保证。运行结果保存在本次游戏结果目录，不收入来源记录。上游文档的历史验证不自动变成当前 Python 改编的验证。
