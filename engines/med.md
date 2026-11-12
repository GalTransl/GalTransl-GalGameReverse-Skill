# MED / MDN0：有界脚本归档与序号引用回写

## 入口与支持边界

- [med_extract.py](../python/engines/med_extract.py) 提供 `extract` / `pack` 工作区流程；[归档实现](../python/archives/med.py) 与[脚本实现](../python/engines/med_script.py) 分层。
- 当前完整路线是 **明文 `MDN0` + `med-framed-ordinal-v1`**：CP932 字符串池、带长度的指令帧、u16 字符串序号。常见剧情来源是 `md_scr.med`，必须同时通过归档及脚本结构校验，不能仅按后缀判断。
- 不覆盖其他 `MDN*` 媒体包、加密脚本、未知 opcode/参数形状或不同字符串引用方式。错误中包含成员名、opcode 和代码偏移；先研究当前成员，不放宽校验强行导出。
- 加密成员与不同容器 magic 的[研究资料](med/encrypted-members.md)单独记录，未改变明文 MDN0 工作流的支持范围。
- [旧 med.py](../python/engines/med.py) 仍保留无指令语义的 NUL 表定位和等字节长替换 API。旧 leaf 的变长限制不适用于已通过新 profile 的成员，也不能反过来用新 writer 处理仅通过旧边界公式的文件。

## Agent 操作流程

先读取索引及预算，再解析剧情包所有成员。无需执行 EXE/DLL；不要顺手提取图像、音频或修改原文件。以下命令供 agent 执行，输出目录须不存在或为可复用的已有目录（不含同名产物或非空结果目录），且父目录已存在：

```console
python -m python.engines.med_extract extract "GAME/md_scr.med" "GAME/GAME_extract"
python -m python.engines.med_extract pack "GAME/GAME_extract" "NEW_REBUILD" --readback "NEW_READBACK"
```

`extract` 会经过真实脚本 writer 和归档 writer，要求原文往返逐字节一致，再发布结果：

| 路径 | 内容 |
|---|---|
| `original/<原归档名>`、`original/scripts/` | 原始归档及成员，不修改 |
| `gt_input/<成员名>.json` | 非空脚本的 UTF-8 平铺 JSON，姓名在正文前 |
| `gt_output/` | 同名译文；未提供的成员保持原文 |
| `metadata/` | 源哈希、指令偏移、角色、姓名引用和控制符 |
| `rebuilt/roundtrip/<原归档名>` | 实际重建且逐字节一致的原文归档 |
| `reports/extraction.json` | 数量、角色、指令分布和排除范围 |
| `reports/jis-extra-text.txt` | UTF-8，所有成员中未导出的主字符串和标签名（去重，每行一条），仅供 JIS `--extra-text` 预留字符，不是翻译输入 |

`pack` 从原归档重新推导成员、JSON 和 manifest，核对原文及元数据后按文件名配对译文。名字不匹配的文件记录为 `unmatched_translation_files`，不会猜配。重建目录只写同名完整归档、`reports/rebuild.json` 和 `README.txt`。打包时会在内存中从重建归档逐成员回读，与预期行比对。指定 `--readback` 时，再把实际写盘的归档重新提取到该新目录的 `gt_input/`。回读结果不放进重建目录，避免代理 JSON 随资源一起发布。不要把单个脚本或代理 JSON 当作已回注结果。

已有重建目录可单独回读，不要求重新打包：

```console
python -m python.engines.med_extract readback "GAME/GAME_extract" "NEW_REBUILD" "NEW_READBACK"
```

重建目录只允许工作区原归档名、`reports/rebuild.json` 和 `README.txt`，其他文件（包括旧版本写入的 `readback/`）一律拒绝；成员名单须与工作区一致。回读目录不能位于工作区或重建目录之内。换行保护项调整后，旧 metadata 无法通过 manifest 比对；应从哈希验证通过的原件重新提取到新目录，再放回同名译文。

交付依主流程用 Markdown 表格说明实际数量及验证状态，推荐具体开场文件。标题可能是文件第一条，应按 metadata 的 `kind` 找前几条正文试注；不要只按排序认定剧情入口。告诉用户：译文放回同名 `gt_output` 后通知 agent，由 agent 完成回写。

## 归档结构与边界

`MDN0` 的头长 16 字节：偏移 4 为 u16 索引项宽度，偏移 6 为 u16 成员数，偏移 8–15 原样保留。索引从 **0x10** 开始，每项前 `width-8` 字节是 CP932/NUL 填充名字，末尾依次是 u32 长度、u32 绝对文件偏移。

索引读取接口先验证尺寸、路径、重名、重叠及成员预算，再读取 payload。当前归档上限 64 MiB、单成员 8 MiB、4096 项；超限直接说明阶段，不把被省略成员算作成功。只支持平铺名字。writer 保留索引顺序、名字原始槽、物理成员顺序、间隙和尾部，更新实际大小和偏移，并重新读取所有成员。

## 脚本结构

全部数值为小端，头长 16 字节：

| 偏移 | 字段 |
|---|---|
| 0 | u32 文件长度减 16 |
| 4 | u32 代码区字节数，含末尾单字节零哨兵 |
| 8 | u16 主字符串数 A |
| 10 | u16 标签数 B |
| 12 | 源行元数据，原样保留，不当作指令数 |

代码区后依次是 `B × u16` 代码区相对标签目标、A 个 NUL 结尾主字符串、B 个 NUL 结尾标签名。文本起点仍是 `16 + LE32[4] + 2*LE16[10]`。A=B=0 时允许文本起点恰好 EOF。标签目标必须落在指令帧起点，两个池的数量及文件尾必须完全吻合。

指令帧是 `u16 源行号 + u8 payload长度 + u8 opcode + 参数`，长度包含 opcode。通过帧中明确的长度读取，另以 `SHAPES` 核对当前 profile 的 opcode/参数形状。非文本指令保留全部原字节；这不表示已实现该引擎全部指令语义。

## 导出语义

| 指令 | 处理 |
|---|---|
| `01`，参数 u16，紧随 `00` | 正文/旁白；独立的定义 literal 不按日文扫描导出，并记录排除数量 |
| `0D`，参数 u16 | `【姓名】` 显示字符串；JSON 去掉外括号，writer 恢复；`FFFF` 清空姓名 |
| `04` | 页面边界，后续正文不沿用上一页姓名 |
| `0A`，8 字节参数 | 前 u16 为选项文字；`FFFF` 表示无文字，保留结构；其余参数不变 |
| `2C`，参数 u16 | 章节/存档标题，sidecar 标为 `title` |
| 语音、背景、立绘、调用与标签引用 | 保留，不作为台词导出 |

物理分行分别导出，不把多个字符串拼成一个字符串。单个姓名指令覆盖多条正文时，sidecar 的 `name_frame` 相同；译名必须一致，否则停止回写。姓名不跨调用/跳转或页面边界推断，不能通过资源 ID 猜造姓名。

**定义表也可能含 `01 + 00`，不能仅凭这对指令认定对白。** 首条 `02` 引用 `#RULE_DEFINE` 标记时，核对指令集合及连续 TAB 分隔的两列标识符映射，按规则表整体保留；标识符允许包含日文，不能依语言判定。记录 `rule_definition_literals`，不生成其翻译 JSON。未知规则标记或出现不符合表结构的 literal 则停止。这一识别依赖内容结构，不依赖成员恰好叫 `_DEF`，也不普遍排除 ASCII 对白。

保护字面 `\N` 以外的控制符、制表符及标记符顺序；`\N` 与物理换行都可减少，但不能新增或跨其他控制符移动。拒绝新增 NUL、未知反斜线转义、空译文和改变字段/条数。原文与译文相同行数的重排无法自动识别，仍须保持顺序。

## 变长回写原则

不要全局替换原字符串槽：同一条字符串可能被正文和资源指令共用。writer 将变化的译文追加到**主字符串池末尾、标签名池之前**，只修改已证明是显示文本的指令操作数。原池前缀和所有旧序号保留，相同旧文本也可以在不同引用处使用不同译文。

代码长度、指令地址、标签目标和非文本参数均不移动；更新 A 和总长度，重新解析并比较全部导出行、原字符串池、标签及屏蔽已知文本操作数后的代码。无修改时也走完整 writer，并要求字节一致。姓名/选择/标题可能按有符号 16 位读序号，因此追加 ID 限于 0–32767，不能把 u16 可写范围当作运行时可用范围。

## 中文、部署与验证

脚本 writer 只做严格 CP932 编码。中文优先沿用[公共 JIS 流程](../guides/jis-substitution.md)，不要给 MED 单独实现另一套 JIS 开关：

1. agent 调用公共 `prepare`，用 `--extra-text` 传入提取时生成的 `reports/jis-extra-text.txt`，预留未导出字符串池和标签中的字符；用户译文仍保留真实中文。
2. 对 prepare 生成的 `workspace` 调用 MED `pack --readback`，一次完成重封包和实际归档回读，不需要再单独运行 `extract`。
3. 用公共 `finalize` 对全部回读 JSON 核对代理文本和还原中文，生成同名归档、配置、映射及合适位数的 hook。固定映射冲突时可明确选择 `unused`，但此时不能声称预设替换字体兼容。

```console
python -m python.common.jis_workflow prepare "GAME/GAME_extract" "JIS_PREP" --encoding cp932 --extra-text "GAME/GAME_extract/reports/jis-extra-text.txt"
python -m python.engines.med_extract pack "JIS_PREP/workspace" "JIS_REBUILD" --readback "JIS_READBACK"
python -m python.common.jis_workflow finalize "JIS_PREP" "JIS_REBUILD" "JIS_READBACK/gt_input" "JIS_DELIVERY"
```

`reports/jis-extra-text.txt` 在提取时生成，旧工作区没有这个文件，需要从哈希验证通过的原归档重新提取到新目录。无法按 CP932 解码的池项不会写入这个文件，而是逐成员列在 `reports/extraction.json` 的 `jis_extra_text.undecodable_cp932_strings`，需要单独核对。

不假设存在通用 `patch.med` 加载机制。交付的是同名完整剧情归档；备份和部署依授权处理，不覆盖原游戏。最终告诉用户配置所在位置，以及将结果目录中按 EXE 位数选择的 CialloHook（`version.dll`/`version.ini`，强制 932 时含 LE/LEP 依赖）与 `uif_config.json` 放到实际游戏 EXE 目录的用法；存在其他 hook 时先核对合并。字体路线必须是映射匹配的专用替换字体，普通日文或繁体字体无效。离线往返与中文还原不等于游戏内显示已验证。

[合成测试](../tests/test_med.py) 覆盖归档间隙/重封包、空脚本、帧/索引错误、姓名关联、原池复用隔离、变长引用、控制符、JIS 回读、回读目录与重建目录分离、extra-text 导出及工作区拒绝覆盖。新方言须先核实长度字段、引用基准和加载端读取方式，再添加独立 profile 或有证据的形状/语义；不按游戏名另建脚本。

## 来源与许可

- 归档索引参考 GARbro `ArcFormats/DxLib/ArcMED.cs`，Copyright (C) 2016 morkt，MIT 通知随[归档模块](../python/archives/med.py)保留；重封包和严格边界校验为新增实现。
- 旧文本边界参考 SExtractor `src/extract_MED.py`、`src/engine.ini` 的 MED 段，基线 `8d8d976fd04ae54e7c677705af937273d04a376a`，GPL-3.0-only；出处见 [provenance](../provenance/sextractor-core.json)。
- 新指令语义与引用级 writer 为独立实现。使用所需的格式、算法和约束均在本包，不依赖外部仓库或运行时分析工具。
