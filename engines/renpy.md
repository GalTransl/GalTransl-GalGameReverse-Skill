# Ren’Py：RPA/ARC3 归档与 RPYC2 编译脚本回填

覆盖归档与松散 RPYC2 原位回填、新建 `tl/<语言>` 翻译语言及松散 `.rpy` 源码回填。目录输出遵循 [公共安全写出约定](../guides/python-reference-api.md#安全写出示例)：父目录须已存在，目标须不存在或为普通空目录；非空目录、文件和链接拒绝。

## 识别与入口

- `game/`、`renpy/`、`.rpy` / `.rpyc` 和 `.rpa` 是组合线索；扩展名不能代替结构验证。
- 标准 `RPA-3.0` 与改名的 `ARC-3.0` 可共用本页容器算法，仍须验证索引、XOR 偏移、前缀和压缩数据。其他魔数不能通过改头强行套用。
- 入口是 [renpy_extract.py](../python/engines/renpy_extract.py)；容器 [rpa.py](../python/archives/rpa.py)；tl 生成/读回 [renpy_tl.py](../python/engines/renpy_tl.py)；`.rpy` 工作区 [renpy_source.py](../python/engines/renpy_source.py)，词法器 [renpy.py](../python/engines/renpy.py)。
- 不导入 Ren’Py / 游戏模块，不执行游戏 EXE、Python、表达式或 Pickle 对象构造器，不调用 `pickle.loads` / `Unpickler`。`renpy/*.py` 只当文本读取。

## 回注方式选择

| 方式 | 适用条件 | 所需证据 | 产物 |
|---|---|---|---|
| 新建 tl 语言（推荐） | 原文脚本编译时带 translate identifier（RPYC 槽 2 中有 `Translate` / `TranslateSay`）；目标语言名尚不存在 | 每句对白都有编译 identifier；游戏可切换语言（语言菜单、`config.language` 或环境变量） | `new-language/game/tl/<语言>/*.rpy`，不改原文与其他语言 |
| 改写已有 tl | 已有 `tl/<语言>` 且就是要显示的语言 | 该语言脚本在所选归档或松散目录中 | 同名归档或 `loose/game/tl/...rpyc` |
| 原位改写 RPYC | 没有可用 identifier、或必须替换原文语言 | 有效脚本来源（见覆盖规则）；同名 `.rpy` 不会取代该 RPYC | 同名归档或 `loose/game/...rpyc` |
| `.rpy` 源码改写 | 游戏只发布或同时发布可编译的松散 `.rpy` | `.rpy` 是实际加载的来源；`game/` 可写以便重新编译 | `loose/game/...rpy` |
| 补丁包（新增归档） | 仅当加载配置证明新包优先 | `config.archives` 顺序、loader handler 的扩展名/魔数 | 本工具不生成；需另行确认 |

查看加载配置（只读，不运行）：`scan` 会把 `../renpy/loader.py` 作为文本读取，报告 `get_supported_extensions` / `get_supported_headers`（例如改名为 `.arc` 并注册 `ARC-3.0 ` 头）及是否存在 `force_archives`。`extract` 还在编译脚本的 Python 源文本中搜索 `config.archives`、`config.force_archives`、`config.file_open_callback`、`config.searchpath`、`config.language`、`config.default_language`，结果列在报告 `config_hints`。默认 `config.archives` 由 `renpy/main.py` 生成：`game/` 中受支持扩展名的归档按文件名排序后反转，查找时取列表中第一个命中的归档，即**文件名排序靠后的归档优先**；游戏若改写 `config.archives` 则以其为准。

## 加载与覆盖规则

依据 Ren’Py 8 的 `renpy/loader.py`、`renpy/script.py`（按文本核对）：

- **松散文件优先于归档。** 文件列表先扫描 `game/` 目录（跳过 `cache/`、`saves/` 与点开头的名字）再扫描归档，同名只记第一个；打开文件时 `file_open_callback` → 文件系统 → 归档，`config.force_archives` 为真时跳过文件系统。因此 `game/x.rpyc` 覆盖任意归档中的 `x.rpyc`。
- **归档内的 `.rpy` 从不作为脚本加载**（`scan_script_files` 对归档中的 `.rpy` 直接跳过）。工作区只在报告 `loader_notes` 中记录，不再拒绝。
- **同目录 `.rpy` 与 `.rpyc` 按 MD5 取舍，不看时间戳。** 读取 `.rpyc` 末 16 字节的源码 MD5，与 `.rpy` 的 MD5 相同且未加 `--compile` 时加载 `.rpyc`，否则编译 `.rpy` 并在可写时重写 `.rpyc`。所以：
  - 原位改写 RPYC 保留原摘要，只要旁边的 `.rpy` 未改，改写后的 RPYC 仍被加载；摘要不符时工作区拒绝并提示改用 `--rpy`。
  - 改写 `.rpy` 后旧 `.rpyc` 不必删除，摘要失配会触发重新编译；`game/` 只读（如部分 macOS 打包）时无法生成新 `.rpyc`。
  - 松散 `x.rpy` 与归档内 `x.rpyc` 会被当作两个脚本同时加载，工作区直接拒绝。
- 同一脚本出现在多个所选归档中时仍拒绝，提示按 `config.archives` 顺序只选有效的一份。

## Agent 工作流程

```text
python -m python.engines.renpy_extract scan "游戏目录/game"
python -m python.engines.renpy_extract extract "游戏目录/game" "<输出>/ws" --archives scripts.rpa tl.rpa --loose --smoke-test
python -m python.engines.renpy_extract extract "游戏目录/game" "<输出>/ws_tl" --archives scripts.rpa --loose --tl-language schinese
python -m python.engines.renpy_extract extract "游戏目录/game" "<输出>/ws_rpy" --rpy [--speakers 角色变量 ...]
python -m python.engines.renpy_extract pack "<输出>/ws" "<输出>/ws/新回包目录" [--font fonts/中文字体.ttf]
```

1. `scan` 只读归档头和索引、松散脚本名及 loader 文本证据，列出 `.rpy`、`.rpyc`、`.rpym`、`.rpymc` 及大小。明确选择脚本包。**Character 定义所在的包要一起选上**，否则 `who` 只有变量名。`who` 未解析时 stderr 输出 `WARNING`，报告记录 `unresolved_speaker_rows` 与 `unresolved_speakers`（不计 `extend`、`narrator`、`centered`、`vcentered`、`nvl`）。
2. `extract` 的来源是 `--archives` 与 `--loose`（`game/` 下递归的 `.rpyc`）的并集，松散文件按虚拟来源 `loose` 与归档成员统一建 manifest。即使未给 `--loose` 也会扫描松散文件名：所选归档成员被松散文件覆盖时报错要求加 `--loose`。报告 `overrides` 列出 `{name, effective: loose, shadowed: 归档}`，被覆盖的归档成员不导出。参数必须是 `game/` 目录本身。
3. 默认模式（原位改写 RPYC2）对选中脚本完整解析并原文回填，要求逐字节一致；`--tl-language` 生成新语言；`--rpy` 为源码工作区（只读松散 `.rpy`，不可与前两者混用）。
4. 保留 `original/archives`、`original/loose`、`original/scripts`（`--rpy` 为 `original/rpy`）、`metadata`、`reports`。`gt_input` 平铺 UTF-8 JSON；同名冲突才加来源后缀（归档名，松散文件用目录名），仍重名再加序号，以报告 `outputs.json` 为准。空脚本不生成 JSON。
5. `--smoke-test` 在每个非空脚本首行追加中文：RPYC 模式输出 `rebuilt/growth-test/game`（归档或松散路径），tl 模式输出 `rebuilt/growth-test/game/tl/<语言>/`。均为离线验证，不是正式译文。`rebuilt/roundtrip/game` 是原文往返归档。
6. 中文原文和 `tl/english/` 等语言层分别导出；不能把一种语言的条数、排序硬套给另一种。
7. 按主流程交付 Markdown 概况表，推荐开场 JSON 少量试注；译文放回同名 `gt_output` 后由 agent 回包。误改 `gt_input` 时先保存到 `gt_output`，再从哈希通过的原始数据恢复，不改 manifest。

## 新建 tl 语言

Ren’Py 6.15 起，编译时把每句默认语言对白包进带 identifier 的 `Translate` 块；Ren’Py 8 的 RPYC 槽 1（静态转换前）仍是普通 `Say`，identifier 只在槽 2 的 `Translate` / `TranslateSay` 中。生成规则：

- 只取默认语言（`language` 为 None）的块。identifier 从 AST 原样读取，写入时按 Ren’Py 生成器把 `.` 换成 `_`；**绝不按哈希重新计算**（重复时 Ren’Py 会追加后缀，计算值不可靠）。槽 2 缺失、或任何 `Say` 不在 `Translate` 块内时整份拒绝（`MissingIdentifier`），改用原位改写。
- 每个块写成 `translate <语言> <identifier>:`，先以注释列出原句，再写译句：`who 属性 @ 临时属性 "译文" [nointeract] [with 表达式]`。块内的 `voice` 等语句按原文逐字保留。`who` 只接受变量名或单个字符串字面量（`"名字" "台词"` 形式）；带参数的 say、复杂 `who` 表达式拒绝。全部为空文本的块（如空 `extend`）不生成，原文照常运行。
- 菜单选项写入文件末尾的 `translate <语言> strings:`，`old` 为原选项文本、`new` 为译文（Python 字面量转义）。同一语言里同一 `old` 只能有一个译文，否则 Ren’Py 报错，因此相同选项只在首次出现处导出一行。字符串翻译是全局的，同文的其他界面文字也会随之替换。
- 写出 UTF-8 BOM 文件 `tl/<语言>/<原脚本相对路径>.rpy`。回包后用 `renpy_tl.parse` 和通用 `.rpy` 词法器分别读回，核对 identifier、说话人、属性、with 子句、逐字语句与全部译文。语言名已在归档路径、松散 `tl/` 目录或编译翻译节点中出现时拒绝，避免重复定义。
- Character 名称、screen、Python 字符串不在范围内；`name` 仍只作上下文。
- 启用语言（依据 `renpy/common/00start.rpy`、`00defaults.rpy`）：优先级为环境变量 `RENPY_LANGUAGE` > `config.language` > 玩家偏好；`config.default_language` 只在首次运行、偏好未设置时生效。游戏有语言菜单时用 `Language("<语言>")` 动作切换。Ren’Py 首次启动会编译新增 `.rpy`，需要 `game/` 可写。
- 字体：原字体缺中文字形时需要中文字体。`pack --font fonts/x.ttf` 另写 `tl/<语言>/gt_font.rpy`，内容为 `translate <语言> python:` 中设置 `gui.text_font`、`gui.name_text_font`、`gui.interface_text_font`；依据是 `gui` 存储在切换语言时被清理并执行该语言的 `translate python` 块。只适用于使用 gui 变量的工程，字体文件须另行放入 `game/`。**该写法的运行效果未经游戏验证**，不使用 gui 变量的工程需按其 style 定义另行适配。
- 部署：把 `new-language/game/tl/<语言>/` 复制到游戏副本的 `game/tl/` 下；不覆盖任何原文件。

## `.rpy` 源码工作区

- 只读取 `game/` 下松散 `.rpy`（UTF-8，可带 BOM；保留 CRLF/LF 与注释）。字符串按 Ren’Py 词法：say/菜单文本折叠连续空格，只识别 `\\`、`\"`、`\'`、`\ `（空格）、`\n`、`\{`、`\[`、`\%`、`\uXXXX`，其他转义拒绝；`translate strings` 的 `old`/`new` 与 `define` 参数按 Python 字面量。写回时用对应规则转义，连续空格写成 `\ `。
- 识别：旁白、白名单说话人的 say（可带属性、`@` 临时属性、`nointeract`、`id`、`with`）、`"名字" "台词"`、`menu:` / `menu 名称:` 下的选项（可带 `if` 条件）、`translate strings` 的 `new`。说话人白名单来自所有文件的 `define x = Character(...)`（含关键字参数、`_()` 包裹）及 `--speakers`。Python、screen、transform、`translate python/style` 等块与括号续行保守跳过；三引号字符串、行内续接字符串报错。
- 形似 say 但说话人未声明、或带 say 参数的行不导出，报告 `skipped_say_like_lines` 并在 stderr 警告；确认是角色变量后用 `--speakers` 重跑。
- 报告 `compiled` 记录旁边松散 `.rpyc` 状态（`rpyc-matches-source` / `source-newer-than-rpyc` / `no-loose-rpyc`）。回包输出 `loose/game/<相对路径>.rpy`，重新词法解析核对全部条目。改写原文会改变对白 identifier，已有 `tl/<语言>` 中对应句将失配，需重新生成或保留原文语言。

## 容器读写范围

- `read_index(stream, **limits)` 支持 RPA/ARC 3.0 的单 chunk 索引，索引偏移是头中 16 位十六进制数，后跟 8 位 XOR key。
- 文件长度是含前缀的总长；读取长度必须减掉索引中的 prefix，不能多读下一成员。
- 数据专用 Pickle 解释器覆盖协议 0–5 的有限数据指令，含协议 4/5 的 `FRAME`、`MEMOIZE`、短 Unicode；索引中 GLOBAL、REDUCE、BUILD 与容器 memo 引用仍拒绝。
- `rebuild(data, replacements)` 保留原魔数、key、前缀形式、成员顺序和间隙，随长度变化重算偏移与索引。未修改时保留原压缩索引并逐字节重建；重包后再次提取，逐成员核对改动数据。
- 重写索引沿用原 Pickle 协议（`read_index().protocol`）。协议 3–5 用标准序列化；协议 0–2 用随包数据写出器，保持 Python 2 的类型（`STRING` / `BINSTRING`、`UNICODE` / `BINUNICODE`），不产生 `BINBYTES` 或 `GLOBAL`/`REDUCE`。写出后再用数据解释器核对；协议超出 0–5 或含其他类型时拒绝。
- 工作区每包上限 64 MiB，选中归档与松散脚本累计 128 MiB，松散脚本数 4096；索引扫描可检查更大的媒体包，但不意味着支持整包流式重建。
- 多 chunk、重叠范围、未知魔数/自定义扰码、越界、重名或不安全路径明确拒绝。

## RPYC2 的安全语义读写

实现：[renpy_rpyc.py](../python/engines/renpy_rpyc.py)、[renpy_pickle.py](../python/engines/renpy_pickle.py)。

- `RENPY RPC2` 之后是 `<slot, offset, compressed_size>` 小端表，零记录结束；各槽独立 zlib 压缩，末尾保留 16 字节源码 MD5。它是 `.rpy` 源码的摘要，加载器据此在 `.rpy` / `.rpyc` 间取舍，不能按译文重新计算或清零。
- 接受 slot 1 及可选 slot 2；slot 1 是静态转换前 AST，slot 2 是转换后 AST。用文件、行号、节点身份、角色和选项位置配对，允许 Say 转成 TranslateSay，但两套文本身份/内容必须一致。
- Pickle 协议 2–5 的支持子集被解释为惰性对象图。GLOBAL、STACK_GLOBAL、NEWOBJ、REDUCE、BUILD 仅记录类名、参数和状态；列表/字典子类的填充数据独立保留，绝不调用真实类。
- memo 别名和循环引用保留。改写字符串时保留旧值及 memo 写入，再弹出栈顶并压入新值，防止共用字符串的文件名、代码、查找键等跟着改变。
- 改动后的 Pickle 去掉 FRAME 记录，按原协议输出不分帧流；不改协议版本，不重新实例化或序列化游戏对象。
- 对改动前后完整可达对象图做摘要比较，仅允许指定的字符串节点变化。再校验各槽重新提取文本、RPYC 外壳及归档成员；跳转、条件、节点 name、identifier、alternate、Python/PyCode、资源路径和未知非文本属性都必须保留。
- 未支持旧版 RPYC、缺失源码槽、未知额外槽、外部缓冲区/PERSISTENT ID/扩展 opcode、异常根结构、文本身份冲突或两槽不一致。保留诊断后适配具体格式，不绕过验证。

## 文本与姓名范围

| AST 字段 | 处理 |
|---|---|
| Say / TranslateSay 的 `what` | 对白或旁白 |
| Menu 的 `items[i][0]` | 选项或菜单标题；条件、分支保持原样 |
| TranslateString 的 `new` | 当前语言显示译文；`old` 查找键不改 |
| Define 中静态 Character 名称 | 解析字符串常量或 `_()` 包裹常量，仅作只读姓名上下文 |
| Python、screen、ATL、UserStatement 及其他字段 | 原样保留，不扫引号冒充对白 |

- 跨文件合并静态 Character 声明；已存在的语言翻译表可提供该语言的姓名。动态表达式、冲突定义保留为未解析上下文，不猜姓名。
- `who` 常是人物变量名，不是展示姓名。导出 JSON 的 `name` 在 `message` 上方，默认只读；人物改名需要另外适配声明/名称表，不能逐句替换变量 ID。
- 插值模板姓名如 `[playername]` 原样作为上下文，不虚构玩家的实际名字。
- 控制符保护包含 `{b}`、`{/b}`、`[name]`、带嵌套索引与引号的插值，以及 `[[`、`{{` 和 `%s` / `%(name)s` 等格式占位符。修改文本时保持完整 token 顺序，拒绝新增/删除控制语法、NUL 或空消息。
- 原文和导出文本都是 Unicode，以 UTF-8 存储，无需套用 CP932/JIS。缺字先核对游戏实际使用的字体。
- 翻译表可能含 UI、编辑器残留和未使用条目；报告中区分 `translation-new`、`say`、`choice`，不能宣称全部是主线剧情。

## 回包与部署

- `pack` 按报告 `mode` 分派（`rpyc` / `tl-new` / `rpy`），校验原始数据哈希、重新生成的原文与 manifest、译文文件名、数量、姓名槽及控制符。未提供译文的成员原样保留（tl 模式不生成该文件，游戏回退到原文）。
- 译文错误逐条收集，检查完所有 JSON 后一次列出再失败，不写出结果；格式为 `<文件>.json #<下标>: 原因`，控制符不符时附 `expected tokens` / `actual`。CLI 只在 stderr 输出可读错误、退出码 1。
- RPYC 模式：归档成员输出 `changed-archives/game/` 同名完整归档（重包后逐成员读回）和 `loose/game/` 编译脚本两种备选；来源本是松散文件的只输出 `loose/game/`。按上面的覆盖规则二选一，不要两套叠加，不要擅自命名为 `patch.rpa`。
- 仅修改 AST 文本时保留源摘要、脚本版本和节点身份，不自动删除缓存或存档。实际运行未生效时，先核对语言选择、覆盖关系（`config.force_archives`）和 `.rpy` 是否取代了 RPYC。
- 游戏加载、字体显示、换行、菜单与存读档仍需运行验证；离线往返不能替代它。游戏文件覆盖与启动沿用主 Skill 授权边界。

## 保留的 `.rpy` 源码接口

`renpy.extract(script, filename="script.rpy", speakers=(), diagnostics=None)` 与 `renpy.patch(script, replacements, filename="script.rpy", speakers=())` 使用 Unicode 字符偏移（脚本须先去掉 BOM），`Target.syntax` 区分 `say` 与 `python` 字面量规则；`renpy.characters(script)` 返回 Character 变量与字面姓名。`patch` 写后立即重新解析核对。

## 新方言适配与回归

先区分容器变体、RPYC 外壳、Pickle 指令、AST 字段及加载策略。逐层记录有限的结构诊断；对不认识的字段先证明其为显示文本，再定义定位和回写规则。不要全局替换相同字符串，不根据类名猜构造器行为；未知对象保持惰性。

新增支持须有合成正反例：双槽差异、共享 memo、循环与容器子类、控制符、非文本字段不变、长度增长、索引前缀、截断/越界、恶意构造器不执行、路径与不覆盖输出、松散覆盖、`.rpy` 摘要规则、tl 生成读回与缺失 identifier 拒绝。测试：[test_renpy_rpyc.py](../tests/test_renpy_rpyc.py)、[test_archives.py](../tests/test_archives.py)、[test_engines_secondary.py](../tests/test_engines_secondary.py)。实际游戏报告只留在结果目录，不收入 Skill 验证案例。
