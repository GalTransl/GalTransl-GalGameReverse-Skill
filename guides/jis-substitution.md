# CP932 中文回注：公共 JSON JIS 流程

确认**脚本正文**使用 CP932、且引擎**固定按 CP932 解码**后，中文回注优先走本页的公共流程。不要为了 JIS 给每个引擎增加 codec 参数、专用开关、冲突检查和 hook 配置生成逻辑。引擎只负责原有的文本语义、长度/偏移、加密和归档读写；公共层负责 JSON 中真实中文与 CP932 代理字符的转换及显示核对。

## 先判定运行时码页

剧本以 CP932 存储只说明它在日文系统上被写出，不说明引擎运行时怎样解码。两类引擎需要不同路线：

| 运行时行为 | 典型证据 | 简中系统（ACP 936）上的表现 | 回注路线 |
|---|---|---|---|
| 固定 CP932 | `MultiByteToWideChar(932, …)`；自带 SJIS 表；A 接口配合固定 `SHIFTJIS_CHARSET` 字体 | 原版不转区也能正常显示日文 | 本页 JIS 流程 + hook |
| 跟随系统 ACP | `MultiByteToWideChar(CP_ACP=0, …)`；`GetACP()` 结果按 932/936/950/949 分支选字体 charset | 原版不转区时日文乱码，需 LE/日文区域才正常 | 整体转码为 GBK 回写，不用 JIS |

ACP 跟随的引擎上 JIS 代理必然失败：代理文件中未被代理的常用字仍是 CP932 字节，按 936 解码即乱码；代理字在进入映射表前已被错误解码，hook 只能偶然命中字节恰好也是合法 GBK 的少数字；代理字度量也与中文不同。叠加字体替换、charset 伪装、码页 hook 也无法可靠补救。

判定步骤：

1. 只读探测实际加载脚本、绘制文本的 EXE（不是启动器）：

   ```text
   python -m python.common.jis_workflow codepage "游戏目录/实际启动的.exe"
   ```

   输出 `verdict`：`acp-following`、`fixed-cp932`、`mixed` 或 `undetermined`，以及 `confidence`、调用点（`conversion_calls`，CodePage 解不出记 `unknown`）、`getacp_calls`、`embedded_sjis_table`、`packing` 与 `reasons`。这是字节模式启发式，不是反汇编，只作选路线的证据；只对多字节 ANSI 剧本有意义，UTF-8/UTF-16 剧本不必看。多个 EXE 可一次传入。
   - `acp-following` + `strong`：`GetACP()` 之后紧跟按 932/936/950/949 分支或载入字体 charset（0x80/0x86/0x88/0x81），是最直接的证据。`weak` 只有若干 `CP_ACP` 转换调用，可能只用于路径或系统文本，需旁证。
   - `fixed-cp932`：转换调用的 CodePage 为 932，或程序内嵌 SJIS→Unicode 表。
   - `mixed`：两类证据都有，常见于少量 `CP_ACP` 处理路径、剧本另走 932 或自带表的引擎。不能据此直接选 GBK；默认仍走 JIS，并按第 3 步做小样本对照确认。
   - `undetermined`：疑似加壳、导入表不可读、只有 A 接口绘制或解不出常量；A 接口按 DC 字体 charset 对应码页解释字节，仅 `DEFAULT_CHARSET` 时才用 ACP。
   - 不在 `GetACP` 附近的码页常量比较（C 运行库的码页→区域表到处都有）只列出，不计入结论。
2. 结合用户的运行环境：原版在简中系统不转区就乱码、需要 Locale Emulator 才正常，是 ACP 跟随的旁证；已有 GBK 汉化在简中系统直接可用也是旁证。
3. `undetermined` 或 `mixed` 时先小样本对照：同一开场句分别做 JIS 版本与 GBK 版本，在用户的目标系统码页下各试一次，以实际显示决定路线。

确认 ACP 跟随后：

- **整体转码**：所有运行时按 ACP 读取的文本成员（剧本、姓名表、选项、未翻译行）都从 CP932 严格转码为 GBK，不能只改译文行而留下 CP932 字节，否则同一文件两种语义。GBK 无法表示的字符须逐个报告并由译者/agent 明确给出替换，不静默替换。需要引擎 writer 支持指定输出编码（例如 [SystemC](../engines/systemc.md) 的 `--output-encoding gbk`）；writer 不支持时先补齐实现，不手工拼接字节。
- **运行条件**：补丁只能在 ACP 为 936 的系统上正确显示，**不能再开 Locale Emulator 或日文区域**（ACP 变回 932 后整篇乱码）。交付时把这一点明确告诉用户。
- **hook 配置**：不需要字形映射。若仍用 CialloHook（例如换字体），设 `EnableCnJpMap = false`，`[CodePage]` 关闭，`Charset` 保持 `0x00`（引擎自己按 ACP 选 charset）；只有默认字体缺中文字形时才设 `Font`。不交付 `uif_config.json`/UIF。
- 繁中系统（ACP 950）、韩文系统（949）同理只能用对应编码，一份 GBK 补丁不能跨系统通用。

## 入口与适用条件

- [jis_workflow.py](../python/common/jis_workflow.py)：通用 `prepare` / `finalize` / `arch` / `codepage` CLI，`prepare --jis-preflight` 只读预检，以及不依赖引擎的 `preflight_translations` / `prepare_translations` API。没有引擎分支或注册表，不修改全局 codec。
- [jis_substitution.py](../python/common/jis_substitution.py)：SExtractor 固定映射、冲突检测、私用代理字分配、保留码位、配置及 hook 产物。仅依赖标准库，无需安装外部项目。
- 工作区采用主 Skill 的 `original/metadata/reports/gt_input/gt_output` 结构；引擎接受 UTF-8 的最小 name/names/message JSON，并已有严格 CP932 writer 与真实重提取能力。
- 必须确认**存储编码**。JSON 本身是 UTF-8，某些 manifest 的 encoding 也是交换层 UTF-8；都不能代替脚本编码证据。严格 shift_jis、UTF-8、UTF-16、GBK 不使用此流程，Kirikiri PSB/SCN 不因 XP3 文件名编码而触发它。`--encoding` 的实际写法（如 `cp932`、`CP932`、`windows-31j`）原样记入报告的 `script_encoding`。
- 原脚本已使用 UIF 替换或 tunneling 时先识别原映射。工作区声明已有 source/target 字符表、已启用旧映射，或 `original/` 中 `CialloHook.ini`/`version.ini`/`winmm.ini` 开启 `EnableCnJpMap` 时，公共准备器拒绝直接叠加；应先制定合并/还原方案。游戏目录已有 hook 也需检查，不能用新子集配置覆盖仍在使用的旧映射。

`prepare` / `finalize` 的输出父目录须已存在，目标须不存在或为普通空目录；非空目录、文件和链接拒绝。

## 常规路线：试注用 unused + hook，全量后再看固定表

日文原作的未翻译日文本身就会用到大量常用汉字（時、間、為、変、説、経、応等）和全角符号，而它们恰好是固定表的代理字。只翻译几句就与仍会显示的原文冲突，是**正常情况**，不是异常。按以下顺序处理：

1. **试注 / 部分翻译**：直接用 `--proxy-policy unused`，并按游戏 EXE 位数配 hook（32 位 `--hook uif-x86` 或 `ciallohook-x86`，64 位 `--hook ciallohook-x64`）。冲突字改用私用区代理，必须随本批 `uif_config.json` 使用 hook 或按本批映射定制字体。
2. **全量翻译后**：仍会显示的日文只剩 UI、姓名等少量文本，可再用 `--jis-preflight` 按固定表预检；通过时可回到默认 `fixed`，兼容 SExtractor 预设字体，hook 也照常可用。
3. 预检或正式准备失败时，按报告的 `next_steps` 选择下一步；固定表缺字（`missing_characters`）两种策略都不能解决，须改写译文。

## 预留范围

预留字是“仍会以原样显示”的字符，代理字不能与它们重合。范围由 `--reserve-scope`（API `reserve_scope`）决定：

| 值 | 预留内容 |
|---|---|
| `untranslated`（默认） | 未提供译文的文件，以及已提供文件中与原文相同的行、字段和多人名槽 |
| `all` | 全部 `gt_input` 原文，包括已被译文替换的行；只在有证据表明被替换的原文仍会显示（例如引擎另有未导出的引用）时使用 |

按**位置**判断：某行在一处被翻译、在另一处原样保留时，保留处的字符仍预留。两种范围都预留译文中的直接 CP932 字符、`--extra-text` 额外文本及保留码位。已被替换行中的私用区字符虽不预留，仍不会被分配为代理字。

## 打包前只读预检

任何满足上述交换契约的 CP932 引擎工作区，先用同一个公共入口检查固定映射：

```text
python -m python.common.jis_workflow prepare "原工作区" --encoding cp932 --jis-preflight
python -m python.common.jis_workflow prepare "原工作区" --encoding cp932 --jis-preflight --extra-text "已解码文本/ui.txt"
```

无需输出目录；即使提供也不创建或写入。预检不生成代理 JSON、配置或 DLL，不回写脚本、不重封包。默认读取 `gt_output`，可用 `--translations "译文目录"` 改选；该参数也适用于正式 `prepare`。

控制台输出 UTF-8 JSON（中文不转义）。`conflicts` 一次列出所有冲突中文字符、固定代理字、`translation_locations` 与 `literal_locations`；每个列表最多 `--max-locations` 条（默认 20，`0` 不限），`translation_location_count` / `literal_location_count` 给出总数。JSON 位置包括文件、记录号、`name`/`names`/`message` 字段，多人名另含槽号；`gt_input` 位置是仍预留的原文，`gt_output` 位置是改动过的译文；额外文本按物理行定位，保留码位以 `{"source": "reserved_codepoints", "origin": ...}` 标明来源。记录号、槽号和行号从 1 开始，记录号不是 JSON 文件的物理行号。CLI 的额外文本来源标签为 `<序号>-<文件名>`，纯 API 可提供相对来源名与解码文本的字典。

`missing_characters` 列出缺少映射的字符，`missing_translations` 列出仍保留原文的 JSON，`reserve_scope`、`reserved_codepoints` 记录本次预留条件，`next_steps` 给出建议。存在冲突或缺映射时退出码为 1，否则为 0。预检针对固定映射，与 `--proxy-policy unused` 不组合。

预检和正式准备共用文件集合、记录数、字段及多人名槽数校验，并拒绝声明已有映射的工作区。预检不自行解码原始二进制资源；未导出的姓名表、UI 或其他显示文本必须由原 parser 正确解码后传入 `--extra-text` / `extra_texts`。它不能代替引擎的源哈希、控制码、姓名可写性、容量、封包或游戏显示验证。

## Agent 完成的四步

1. **准备工作副本。** 读取原 `gt_input` 和用户 `gt_output`，按预留范围预留仍显示的原文与译文中的直接字符；有已解码的系统文本、姓名表、UI 或控制参数时，一并作为 `extra_texts` 输入。只转换译文 JSON 的显示字段，不转换文件名、资源路径或整份二进制脚本。原文、manifest、源资源和用户译文保持不变。冲突或缺字时不写输出目录，输出与预检同格式的诊断 JSON（`stage: "prepare"`），退出码 1。
2. **调用原引擎打包器。** 给它公共目录中的 `workspace/`，把重建资源写入另一个新目录。原 writer 继续校验源哈希、条数、姓名可写性、控制语法、实际字节长度、标签/偏移并加密封包。JIS JSON 转换成功不等于引擎回写成功。
3. **真正重新提取。** 用原引擎提取器读取上一步实际生成的资源，得到完整的 `gt_input`，包括未翻译文件。不能直接拿准备目录里的代理 JSON 当作资源回读结果；引擎提供“工作区 + 重建目录”回读入口时直接使用（如 Escu:de `--readback`、ExHIBIT `readback`、MED `pack --readback` / `readback`、CatSystem2 `catsystem2_extract pack --readback` / `readback`），它们从工作区原件补齐未变成员；没有入口的引擎，才在只读验证副本中补齐未变成员再提取。回读结果放在单独的新目录，不要放进重建目录，因为 `finalize` 会发布整个重建目录。
4. **公共核对与交付。** `finalize` 检查准备目录快照未变、`uif_config.json` 与计划中的 `batch_mapping_sha256` 一致、重提取的文件集合/行/姓名与预期代理文本一致，再反向还原并比对真实中文；未翻译文本也必须不变。全部通过后才在新交付目录发布重建资源、映射、配置和兼容 hook。

以下命令供 agent 执行，不默认交给用户手动运行：

```text
python -m python.common.jis_workflow arch "游戏目录/实际启动的.exe"
python -m python.common.jis_workflow prepare "原工作区" "新的JIS准备目录" --encoding cp932 --proxy-policy unused --hook ciallohook-x86 --exe "游戏目录/实际启动的.exe"
```

然后调用对应引擎原有的打包和提取命令：输入 `新的JIS准备目录/workspace`，输出新的重建目录，再把实际资源提取到新的回读目录。最后：

```text
python -m python.common.jis_workflow finalize "新的JIS准备目录" "重建资源目录" "回读目录/gt_input" "新的交付目录"
```

`--hook` 选择与游戏 EXE 位数一致的 DLL：`x86`（同 `uif-x86`）附带 UIF `winmm.dll`；`ciallohook-x86` 附带 CialloHook x86 `version.dll` 与 `version.ini`；`x64`（同 `ciallohook-x64`）附带 CialloHook x64 `version.dll` 与 `version.ini`；默认 `none` 不选 DLL。没有 x64 UIF。位数判断见下文[显示部署](#用户下一步与显示部署)；提供 `--exe` 时位数不符直接拒绝。`--extra-text` 可重复指定额外已解码的 UTF-8 文本。准备器复制标准工作区四个来源目录，跳过旧 `rebuilt/`；当前文件/总字节预算为 128/512 MiB，超限明确报错，不使用硬链接、符号链接或覆盖用户目录来规避复制。CLI 的其他错误也以 `{"ok": false, "error": ...}` 输出并以退出码 1 结束。

SystemC、ExHibit 已有的内联 JIS 接口保留兼容；走公共准备流程时关闭其自动处理（例如 `--jis-mode off`）。不要照这些旧接口再为其他引擎复制一套。特殊工作区可调用下面的公共 API 组织已有 parser/writer，仍不需要改引擎的编码函数。

## 固定映射与冲突处理

默认 `--proxy-policy fixed` 使用随包 SExtractor 2999 项固定映射：保留无损 CP932 字符，只替换无法编码且表中存在的中文。代理字若也是预留字或保留码位则报错；未知汉字、emoji、不可逆 CP932 别名也报错，不截断、不填空格。

`--proxy-policy unused` 仍优先用固定映射，只为冲突字分配私用代理字。先收集整批原文、译文及额外文本，再按字符排序分配，所有文件共享同一映射，不受文件处理顺序影响；不会在字节写出后改变映射，池耗尽则报错。

这是本项目的自定义扩展，**不再兼容 SExtractor 固定日繁/JIS 替换字体**。报告会写 `remapped_count`、`custom_chinese_to_proxy` 和 `preset_font_compatible=false`。必须使用本批配置对应的 hook，或按本批映射定制字体。私用字符能离线编码不代表游戏的渲染和 hook 已实测，仍先小规模试注。

未知外部 UI、其他归档和旧补丁仍需补充文本清单与运行测试，不能把本次扫描当成全游戏显示保证。

## 私用代理字与保留码位

CP932 用户自定义区 `F040..F9FC` 对应 Unicode `U+E000..U+E757`（1880 字），Python 与 Windows 代码页 932 一致，CialloHook 的 `CnJpMapReadEncoding = 932` 也按此转换。引擎和外字字体（EUDC）通常从低端 `U+E000` 起占用，因此 `unused` **从 `U+E757` 向下分配**，并跳过：

- 工作区原文（含已被替换的行）、译文和额外文本中已出现的私用区字符；
- 引擎 manifest 或 CLI 声明的保留码位。

保留码位的来源与格式：

- **manifest**：`metadata/` 下任一 JSON 顶层 `settings.reserved_codepoints`。值为列表，元素可以是整数码位（如 `57344`）、`"U+E000"`，或闭区间 `"U+E000-U+E0FF"`；十六进制 4–6 位，大小写不限。重叠区间自动合并。格式错误时预检和准备均拒绝。
- **CLI**：`--reserve-codepoints "U+E000,U+E010-U+E01F"`，可重复，与 manifest 声明合并；纯 API 的 `reserved_codepoints` 接受同样的列表，或 `{来源名: 列表}` 字典。

引擎在 parser 证据表明某码位有特殊含义时写入该键，例如 F040 被引擎当作其他字符时保留 `U+E000`，游戏启用外字字体时保留其占用范围。不确定范围时宁可多保留；`jis-plan.json` 的 `reserved_codepoint_sources` 记录每个来源。

## 公共 API

```python
from python.common.jis_workflow import JisDiagnosticsError, preflight_translations, prepare_translations

diagnostics = preflight_translations(
    original_rows_by_filename, translated_rows_by_filename,
    encoding="cp932", extra_texts=decoded_ui_texts,
    reserve_scope="untranslated", reserved_codepoints=["U+E000"],
)
# 先检查 diagnostics["conflicts"]、diagnostics["missing_characters"] 和 diagnostics["next_steps"]。

try:
    plan = prepare_translations(
        original_rows_by_filename, translated_rows_by_filename,
        encoding="cp932", extra_texts=decoded_ui_texts,
        proxy_policy="unused",  # 全量翻译且固定表预检通过时可用 fixed
    )
except JisDiagnosticsError as error:
    report = error.report  # 与预检同格式，stage == "prepare"
# plan.stored 是代理文本；只在独立工作副本中供原有引擎 writer 使用。
# 原 writer 校验、重建、再从真实产物提取后：
verification = plan.verify(actual_reextracted_rows_by_filename)
# 与重建资源一起通过 write_new_tree 发布到新目录。
artifacts = plan.codec.artifacts(include_hook=True, hook="ciallohook-x64")  # 或 "uif" / "ciallohook"（x86）
```

`plan.original`、`plan.translated` 保留真实文本，`plan.stored` 仅含提供译文的文件；verify 要求所有原文文件的实际回读。转换不会修改原输入对象或原 manifest。纯 API 不自动识别已有游戏映射，由调用方先完成检查。低层 `JisSubstitution` 与公共契约的 `text_codec` 接口仍可供既有集成使用，但不再作为每个新引擎的必改步骤。

## 目录与身份

| 准备目录内容 | 用途 |
|---|---|
| `workspace/original`、`metadata`、`reports`、`gt_input` | 原来源逐字节复制，原引擎正常读取 |
| `workspace/gt_output` | 只供 writer 使用的代理译文 |
| `chinese/` | 此次真实中文译文副本 |
| `support/` | 待核对的配置/hook，准备阶段不视为可部署产物 |
| `jis-plan.json` | 文件集合、准备快照哈希、映射策略、预留范围、保留码位来源、hook 位数与状态 |

报告中的哈希：`mapping_sha256` 是随包固定表本身的哈希，用于核对预设字体版本；`batch_mapping_sha256` 是本批实际 `chinese_to_proxy` 映射（按键排序的紧凑 UTF-8 JSON）的 SHA-256，每批随用字和私用分配而变，用于核对 `uif_config.json` 与本批产物配套。

最终交付保留重建资源的相对路径，并增加 `reports/jis-workflow.json`，分别记录存储文本核对、中文还原核对和运行时未验证状态。相同条数的译文重排仍不能靠普通 JSON 自动识别，必须保持原顺序。`finalize` 依赖 agent 提供真正的引擎回读，不自行猜归档格式，也不以自身 JSON 互转冒充重封包验证。

## 用户下一步与显示部署

发生实际字符替换时，公共流程在**最终交付目录**输出：

- `uif_config.json`：source 是 CP932 代理日文/私用字符，target 是真实中文；tunneling 关闭。方向不可颠倒。
- `jis-mapping.json`：固定表版本、本批映射哈希、实际映射、私用字符分配、保留码位、hook 位数、固定字体兼容性与冲突清单。
- `winmm.dll`：选择 `x86`/`uif-x86` 时附带仓库固定哈希的 [UIF 工具](../assets/uif/README.md)（仅 32 位），与配置在一起；不自动安装或执行。
- `version.dll` + `version.ini`：选择 `ciallohook-x86` 或 `ciallohook-x64` 时附带对应位数、固定哈希的 [CialloHook](../assets/ciallohook/README.md) 及只开启字形映射的配置，`CnJpMapJson` 指向同目录 `uif_config.json`；不自动安装或执行。
- `JIS-部署说明.txt`：本批 hook/字体条件、位数要求与显示测试步骤；不生成字体。

**判断位数**：读取实际游戏 EXE 的 PE 头 Machine 字段（偏移 `0x3C` 的值指向 `PE\0\0`，其后 2 字节）：`0x014C` 为 32 位，`0x8664` 为 64 位；`arch` 子命令只读输出该值和可用的 `--hook`。启动器与主程序可能位数不同，以实际绘制文本的进程为准。**位数不匹配的 DLL 不会被加载**，表现为游戏正常运行但仍显示代理日文/私用字符。

agent 最终必须给出实际目录和操作说明。将匹配游戏位数的 hook DLL、其配置与本批 `uif_config.json` 放到实际游戏 EXE 目录，再按引擎既有规则部署资源；已有同名文件先检查、备份或合并，同一游戏只用一种 hook，不叠加两次替换。恢复中文后，游戏还须选用包含中文字形的普通字体。

两种 hook 互补：UIF 只有 32 位，只 hook 默认的 TextOut/GetGlyphOutline 路径，配置简单；CialloHook 有 32/64 位，覆盖更多 GDI 文本与测宽接口及部分引擎兼容层，A 接口无法写回中文时改走 W 接口，并可替换字体。32 位游戏一般先用 UIF；UIF 未生效、显示方框需换字体，或 `winmm.dll` 已被其他补丁占用时改用 CialloHook；64 位游戏只能用 CialloHook x64。CialloHook 的字体、字符集与文件名调整见[其说明](../assets/ciallohook/README.md)，不要使用其上游示例 `subs_cn_jp.json`，它与本项目固定表不同。

只有 `preset_font_compatible=true` 且预设字体冲突清单为空时，才考虑映射版本匹配的 SExtractor `WenQuanYi_cnjp.ttf` / `MSGothic_WenQuanYi_cnjp.ttf`，并让游戏实际选用。普通日文/繁体字体不能还原代理字。使用 unused 私用字符映射时，上述固定预设字体不可用；选择本批 hook 配置或定制字体。不要同时开启 hook 字符还原和替换字体。

让用户先测试一个开场文件或前几句，检查对白、姓名、选项、未改日文、标点和换行。显示结果反馈后再由 agent 调整映射、字体或经证实支持的编码方案；回写与配置准备由 agent 执行。覆盖游戏、安装 hook/字体、启动游戏沿用主 Skill 授权边界。

## 来源与验证

固定表和低层语义的来源见 [jis-substitution.json](../provenance/jis-substitution.json)，私用字符规划、保留码位和 JSON 公共流程为本项目新增实现。测试位于 [test_jis_substitution.py](../tests/test_jis_substitution.py)、[test_jis_workflow.py](../tests/test_jis_workflow.py) 与 [test_jis_preflight.py](../tests/test_jis_preflight.py)：覆盖公共只读预检与定位、预留范围、结构化拒绝、冲突、自高位的稳定分配、保留码位、x64 hook 产物、快照篡改、姓名/多人名、引擎控制码拒绝，以及不同引擎的原 writer、重提取和公共交付。游戏运行记录只放各游戏结果目录。
