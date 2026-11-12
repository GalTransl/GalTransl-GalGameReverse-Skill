# ExHibit：RLD v3 静态解密、文本提取与回注

## 入口与边界

- 引擎 ID：`exhibit`。识别证据是 `ExHIBIT.ini`、`resident.dll`、`rld/*.rld` 和 RLD 魔数 `00 44 4C 52`；不只凭目录名选 writer。
- [完整 RLD 读写](../python/engines/exhibit_rld.py)、[静态密钥恢复](../python/engines/exhibit_keys.py)、[提取与回注入口](../python/engines/exhibit_extract.py) 均只使用 Python 标准库。
- 完整支持范围是 **v3/tag256、CP932、松散 RLD**：结构化读取全部 opcode，导出 op28 对白与已识别的 op21 TAB/1010 选项，按原加密方式写回完整文件。
- [旧片段接口](../python/engines/exhibit.py) 保持兼容，只接受 28/48/21/191；其 XOR 端点也与完整 v3 profile 不同，不要混用。
- PE 资源读取和密钥候选扫描都是静态操作，不执行或加载游戏 EXE/DLL。其他版本、加密方式或归档内 RLD 需要先适配对应层。

## Agent 操作流程

1. 枚举实际 `rld/`，检查 16 字节明文头、版本、offset、count，保留文件哈希。脚本可能已经是松散文件，无需先寻找归档。
2. 查找同版本 `defChara.rld`，用于解析间接姓名。`def.rld` 与其余 RLD 可能使用不同密钥；不能把两者混为同一份定义文件。
3. 先尝试全文件明文解析；若加密，传主程序 EXE 与原版 INI，从位图/INI 恢复剧情 seed。加密 `def.rld` 从 `resident.dll` 候选常量中恢复；也可显式传有证据的 seed。
4. 执行提取入口，验证所有文件原文回写逐字节相同，并做增长文本回写。新输出放在游戏的 `<游戏名>_extract/`，保留已有输出，失败不发布半成品。
5. 按主流程交付 Markdown 表格，说明来源、编码、脚本/JSON/文本数量、未解析姓名与文本范围、各阶段验证状态。游戏启动/显示没有实测就明确写未验证。
6. 从 INI 的 `[exec] entry`、`[release] entry` 和 op17 跳转字符串核对开场路径，推荐一个具体 JSON 试注；不要把按文件名字典序第一项自动当作开场。

以下命令供 agent 执行；默认交付时让用户把同名译文放回 `gt_output/`，告诉 agent 后由 agent 回写。

```text
python -m python.engines.exhibit_extract extract "游戏目录" "游戏目录/游戏名_extract" --exe "游戏目录/主程序.exe" --smoke-test
python -m python.engines.exhibit_extract rebuild "游戏目录/游戏名_extract" "游戏目录/游戏名_extract/回注结果"
```

可选参数：`--scripts-dir` 指定实际松散 RLD 目录；`--ini`、`--resident` 指定配套文件；`--seed`、`--def-seed` 接受十进制或 `0x` 十六进制。默认 INI 为 `ExHIBIT.ini`，运行库为 `resident.dll`。显式 seed 也必须经过完整解析验证。

| 路径 | 用途 |
|---|---|
| `gt_input/*.json` | UTF-8、平铺、name 在 message 之前；不导出空脚本 |
| `gt_output/` | 用户返回同名译文，保持条数、顺序和姓名策略 |
| `original/encrypted/*.rld` | 原存储文件，回写基准；明文输入也保存在这里 |
| `original/rld/*.rld` | 完整解密脚本，供只读分析，不直接部署 |
| `metadata/*.json` | 源哈希、op/字符串/选项位置、姓名策略、seed 和配套定义身份 |
| `rebuilt/roundtrip/rld/` | 经过 parser/writer 且与原文件一致的 RLD |
| `rebuilt/growth-test/rld/` | 启用 smoke-test 时，各文本文件首行增加 ` ABC` 的离线测试产物 |
| `reports/extraction.json` | 全部成员状态、数量、密钥恢复依据、未解析 ID、验证结果 |

`rebuild`（别名 `pack`）只输出实际变化的 `rld/*.rld`，保留原文件名。未提供译文的成员不需要部署；未知译文文件名报错，避免静默漏回填。原文 JSON、manifest、配套定义或源文件改变则拒绝回写。输出目录须不存在或为可复用的已有目录（不含同名产物或非空结果目录），不覆盖已有产物。换行保护项调整后，旧 metadata 无法通过 manifest 比对；应从哈希验证通过的原件重新提取到新目录，再放回同名译文。

回读 `rebuild` 结果不需要复制 `original/encrypted`、INI 或 `resident.dll` 拼验证副本：

```text
python -m python.engines.exhibit_extract readback "游戏目录/游戏名_extract" "回注结果目录" "新的回读目录"
```

`readback` 用回注目录的 `rld/<成员名>` 替换对应成员，其余成员取自工作区 `original/encrypted` 并核对报告中的大小和哈希；seed 取自工作区报告。回注目录只允许原清单中的 `rld/*.rld`，以及 `rebuild` 自身写出的 `reports/rebuild.json`、`README.txt` 和旧 `auto` 模式的 JIS 配置/hook 文件，其他文件或链接拒绝。全部成员重新解密、完整解析并做无改动往返，输出 `gt_input/`、`metadata/` 与 `reports/readback.json`。回读目录不能位于工作区或回注目录之内，这两个目录都不会被写入。

## v3/tag256 完整格式

| 偏移 | 内容 |
|---|---|
| `0x00` | 魔数 `\0DLR` |
| `0x04` | u32 version，当前 profile 为 3 |
| `0x08` | u32 offset，当前 profile 为 `0x110` |
| `0x0C` | u32 指令数 |
| `0x10` | u32 import/tag 条目数 |
| `0x14` | 固定 256 字节 tag 区，CP932、逗号分隔名称与 NUL padding |
| `0x114` | 第一条指令，即 **offset + 4** |

不要从 `0x110` 开始读指令：那里仍在 tag 区，零填充可能伪装成 opcode 0，导致末尾真实指令落入“未处理尾部”。本 profile 从 `0x114` 读取恰好 count 条并要求到达 EOF；不把残余字节视为可忽略尾部。tag 条目数不只有 0/1，须与名称数量匹配。

每条指令为 `u16 opcode + u8 integerCount + u8 flags/stringCount`，之后是 integerCount 个 u32 和低四位指定数量的 NUL 结尾 CP932 字符串。高四位 flags 原样保留。

**结构长度由参数数量决定，不由 opcode 白名单决定。** 遇到新 opcode，先验证参数范围、字符串终止与完整 count/EOF；结构读写不需要逐条增加宽度表。但能跳过结构不代表能把内部字符串当对白。op191 等未知业务操作的文本、资源路径、变量和数字参数均原样保留。

writer 用解析得到的原始字节跨度替换允许的文本，不重编码未修改字符串，保留 CP932 同字异码。不插入/删除指令、不改 integer 参数、跳转字符串、tag 或数量。该 profile 的运行时顺序解码指令；不同版本若出现文件字节地址或附加索引，必须补齐重定位，不能沿用这一假设。

## 密钥恢复与 XOR

### 剧情 seed：位图与 INI

1. 从主 EXE 的 PE 资源读取 `RT_BITMAP=2 / ID=152`；多个语言副本必须一致。
2. 当前接受 BITMAPINFOHEADER 40 字节、未压缩 24/32 位、正高度且宽高至少 32 的 DIB。按实际行 stride 读取**存储顺序最后 32 行、第 31 列（从 0 起）蓝色通道最低位**，每位执行 `v = (v << 1) | bit`。
3. 将 INI `[setting]` 值按以下顺序拼接为 CP932 字节，不插入分隔符，缺项为空：`CLASS`；仅当 `SYSVER < 1` 时拼 `TITLE`；随后拼 `W_VIEW H_VIEW N_REG N_STRREG N_SYSREG N_LOCREG N_USAVE N_ASAVE N_QSAVE N_CG N_MESSAGE N_SCENE N_SOUND`；仅当数值 `FLAGS & 4 != 0` 时，最后拼 `FLAGS GUID SVDATA`。读取 FLAGS 判断条件不意味着先将它拼一次。
4. 四个字节位置独立模 256 累加：`checksum = Σ ((sum(data[lane::4]) & 255) << (8*lane))`。
5. `scenario_seed = bitmap_bits XOR checksum`。随后解密所有选中剧情文件，完整解析才算验证成功。

不支持压缩/调色板/负高度位图时明确报 profile 缺口；不要凭图像看起来一样就颠倒行序或忽略 padding。INI 数值接受十进制或 `0x` 十六进制，不能执行表达式。受保护 INI 字段改变会改变 seed；试注时保留它们，不顺手改标题、分辨率或存档设置。

### def seed：有界静态候选验证

从 x86 `resident.dll` 可执行节扫描 `C7 /0 [reg+disp32], imm32`（含 SIB 形式）的 u32 常量，另尝试 seed 0。先验证解密头部 tag/count，再解析整个 `def.rld`，只接受唯一通过者。候选数上限 20,000，不执行 DLL、不遍历全部 32 位空间。编译方式不同、非 x86 或无唯一结果时使用有证据的 `--def-seed`，或者基于样本扩展静态恢复器。

### 生成密钥表与端点

- 使用旧 MT19937 的 **69069 打包半字初始化器**，不是 Python random，也不是常见的 1812433253 初始化器。实现见 `mt_keys`，输出前 256 个 u32；保留对应合成向量测试。
- seed 0 在此运行时表示不加密。
- 头部前 16 字节不加密。从 16 起按 u32 做 `word XOR seed XOR keys[index & 255]`，最多 `0x3FF0` 个字。
- 终点（不包含）为 `min(floor(file_size/4)*4, 0xFFD0)`。不足一个 u32 的末尾及终点后的字节不变。
- 旧片段 API 的 `0xFFCF` 截断会少处理最后一个完整 u32；完整 v3 不使用它。文本增长后必须按新文件长度重新加密，不能沿用原加密区长度。

## 文本与姓名策略

- op28：首串是姓名表示，第二串为正文；其他字符串和全部整数保持原样。
- 首串 `*` 时，第一整数是 name_id，查同版本 `defChara.rld` 的 op48 CSV：field0 为 ID、field3 为显示名。解析出的 name 仅作只读上下文，译文须保持原样；不要把译后姓名写入 `*`。
- 找不到 ID 时不猜造人名，不假定一定是旁白：省略 JSON name，在 manifest 与报告保留未解析 ID。
- `$noname$` 无姓名；其他 `$` 开头名称按变量保留。直接显示名可写，但不能改成 `*` 或 `$...` 哨兵。修改共享姓名定义需要独立适配，不自动联动定义。
- op21 TAB/1010：无整数、flags 高位 `0x60`、一个字符串，按 TAB 分为 30 字段。field0 为 `1010`，field4 为选择数量 1–11，field14–24 为最多 11 个选项槽，未用槽须为 `*`。field0–13、25–28 为数字字段，末尾 field29 为空。只导出有效选项文字，保留数字参数、TAB、占位符与末尾空字段。
- 其他 op21 布局明确报错以促成适配，不默默漏掉选项；op191 不能笼统当作选择指令。
- 目前是普通显示文本 profile：编辑必须保留换行以外的 C0 控制字符及其顺序；换行可以比原文少，但不能新增或跨其他控制符移动。禁止 NUL 和选项内 TAB。遇到 `\\ [] {} <> $ %` 这类未分类语法，原样回写可行，编辑时须先补充控制码规则，不假设它们都是装饰文字。
- 正文里的**全角变量**写作全角 `＄` 加全角或半角字母，例如 `＄Ｎ`，运行时替换为玩家输入的名字等值。`＄` 后连续的字母整体作为一个受保护 token，与 C0 控制符放在同一序列比较：译文须保留相同 token、相同数量与相对顺序，不能删除、改字母或调换。紧跟变量的译文不要直接接拉丁字母，否则会被并入 token 而被拒绝。半角 ASCII `$` 仍属未分类语法，含它的行只能原样保留。
- **私用区外字**：INI 中 `EUDC=*.tte` 表示游戏加载外字字体，正文中的私用区字符 U+E000–U+F8FF 是外字字形（CP932 中 U+E000–U+E757 对应用户区 `F040`–`F9FC`），例如心形符号。原文行已有的私用区字符同样作为受保护 token，数量与顺序须一致。原文行未出现的私用区字符按普通文字处理，这是为了兼容 JIS 代理字。但游戏使用外字时这些码位已被外字字体占用，JIS 代理不能选用私用区码位，否则会显示成外字图形；用公共 JIS 流程的私用区代理（`unused` 策略）前先检查 INI。
- **外字保留码位**：`extract` 读取 INI（`--ini` 或游戏根目录 `ExHIBIT.ini`），有 `EUDC=` 时在每个 manifest 的 `settings.reserved_codepoints` 写入保留码位，单个码位写整数，连续段写 `"U+XXXX-U+YYYY"`。范围包括全部脚本字符串中出现的私用区字符，再加上外字字体 cmap 中实际有字形的私用区码位；字体文件不在游戏目录内、缺失或 cmap 无法安全解析时，保守地保留整段 U+E000–U+F8FF。`reports/extraction.json` 的 `eudc` 记录字体路径、哈希、所用方法和失败原因。公共 JIS 流程会读取该键，避免把这些码位用作代理。
- 受保护 token 已写入 manifest；规则调整后旧 metadata 无法通过 manifest 比对，须从哈希验证通过的原件重新提取到新目录。

## 中文回注与部署

新任务优先走 [公共 JSON JIS 流程](../guides/jis-substitution.md)，原有 `rebuild` 使用 `--jis-mode off` 读取公共层生成的工作副本，再用 `readback` 重新提取实际产物交给公共层核对：

```text
python -m python.common.jis_workflow prepare "提取工作区" "JIS准备目录" --encoding cp932
python -m python.engines.exhibit_extract rebuild "JIS准备目录/workspace" "重建目录" --jis-mode off
python -m python.engines.exhibit_extract readback "提取工作区" "重建目录" "回读目录"
python -m python.common.jis_workflow finalize "JIS准备目录" "重建目录" "回读目录/gt_input" "交付目录"
```

不再为此扩展引擎 JIS 分支；以下 `auto` 接口保留兼容既有调用。

`rebuild` 默认 `--jis-mode auto`：调用公共 JIS 替换模块，在整个脚本集合保留原字符，检查代理字符冲突，真实中文只在可写文本编码边界转换。原始 JSON 保留中文；重建后既核对 CP932 存储文本，也反向核对实际中文。冲突或缺映射时报错，不有损替换。需要纯 CP932 时可显式 `--jis-mode off`。

当前实现保守地预留全部原始字符串（包括未分类 UI），所以少量中文试注也可能与原日文代理字冲突。不得关闭冲突检查强行输出；先选可编码或无冲突的短句检查加载，再决定完整译文的映射/字体策略。未经证实不能直接把 CP932 改为 GBK/UTF-8。

使用了替换字符才生成 `uif_config.json`、`jis-mapping.json` 和 `JIS-部署说明.txt`。hook 按公共策略：`rebuild --exe` 或提取时记录且仍存在的主 EXE 决定 CialloHook 位数，并在码页探针未确认固定 CP932 时强制 ACP 932（附 LE/LEP 依赖）；EXE 已不在时只按记录的 PE 位数选 hook、不强制 932；`--hook`、`--force-cp932` 与 [JIS 公共流程](../guides/jis-substitution.md) 相同，UIF 仅以 `--hook uif-x86` 手动兜底。只有 seed、没有 EXE 架构证据时不擅自选 DLL。

让用户先试一个开场文件。回注结果按原 `rld/` 相对路径部署，并保留原备份；这是松散脚本替换。使用 hook 时将结果目录中的 hook DLL、其配置（及强制 932 时的 LE/LEP 依赖）与同批 `uif_config.json` 放在实际主 EXE 目录，现有 hook/配置先检查合并；也可选映射版本一致、无冲突的专用日繁/JIS 替换字体，并确认游戏实际选用。游戏加载、hook 和字形效果需要用户实测，再决定批量翻译策略。

## 验证与新方言适配

- 合成测试：[tests/test_exhibit_rld.py](../tests/test_exhibit_rld.py)；旧片段测试保留在 [tests/test_engines_primary.py](../tests/test_engines_primary.py)。覆盖旧 MT 向量、加密端点/增长、完整头与末条指令、未知 opcode 保留、CP932 原字节、姓名/选项、静态 seed、JIS、工作区校验、回读合并与 EUDC 保留码位。
- 新方言按“明文头 → 密钥来源 → 加密区间 → 指令起点/count/EOF → 显示语义 → 增长回写”分层定位。缺某个 opcode 名称不妨碍可验证的结构读取；能读结构也不代表所有 UI 文本均可翻译。
- 无法完整解析时保留有限头部、失败偏移、参数数量及版本证据。对齐问题不以吞掉尾部或减小 count 掩盖；密钥问题不靠有损 CP932 解码隐藏。
- 实际运行记录、游戏名和台词仅保存在各游戏结果目录，不写入本页或 provenance。

## 既有接口出处

旧 `exhibit.py` 的片段与间接姓名接口源于 msg-tool `src/scripts/ex_hibit/rld.rs`（GPL-3.0-or-later，提交 `f72716cee88554d40c1cdface2812493b14ca653`）。这里只保留出处说明；完整 profile、静态恢复步骤和验证方法已随包提供，不要求 agent 获取外部源码。
