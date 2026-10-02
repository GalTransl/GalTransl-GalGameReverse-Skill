# Ren’Py：RPA/ARC3 归档与 RPYC2 编译脚本回填

## 识别与入口

- `game/`、`renpy/`、`.rpy` / `.rpyc` 和 `.rpa` 是组合线索；扩展名不能代替结构验证。
- 标准 `RPA-3.0` 与改名的 `ARC-3.0` 可共用本页容器算法，仍须验证索引、XOR 偏移、前缀和压缩数据。其他魔数不能通过改头强行套用。
- 剧本入口是 [renpy_extract.py](../python/engines/renpy_extract.py)；容器实现是 [rpa.py](../python/archives/rpa.py)。现有 `.rpy` 有限源码词法器 [renpy.py](../python/engines/renpy.py) 继续独立使用。
- 不导入 Ren’Py / 游戏模块，不执行游戏 EXE、Python、表达式或 Pickle 对象构造器，不调用 `pickle.loads` / `Unpickler`。

## Agent 工作流程

先只读归档索引，再选择包含剧本的包。以下命令供 agent 执行，不默认要求用户手动运行；路径和包名用本次实际证据替换。

```text
python -m python.engines.renpy_extract scan "游戏目录/game"
python -m python.engines.renpy_extract extract "游戏目录/game" "游戏目录/游戏名_extract" --archives story.rpa scripts.rpa translations.rpa --smoke-test
python -m python.engines.renpy_extract pack "游戏目录/游戏名_extract" "游戏目录/游戏名_extract/新回包目录"
```

1. `scan` 只读头和索引，列出 `.rpy`、`.rpyc`、`.rpym`、`.rpymc` 及大小；不读取图片、音频等大成员。明确选择脚本包，避免把整个游戏无界装入内存。
2. `extract` 为 RPYC2 工作区：对选中包内所有 `.rpyc` 完整解析并进行原文回填，要求逐字节一致；未知结构会报告归档和成员，不留成功的空模板。
3. 保留 `original/archives`、`original/scripts`、`metadata`、`reports`。`gt_input` 是平铺 UTF-8 JSON；同名冲突才加归档名后缀，同一包内仍重名时再加序号。以报告的 `outputs.json` 映射为准。空脚本不生成 JSON。
4. `--smoke-test` 在每个非空脚本首行追加中文，验证双槽回填、完整对象图与归档重新解析，输出 `rebuilt/growth-test/game`。这是离线验证用归档，不是正式译文。`rebuilt/roundtrip/game` 是原文往返归档。
5. 中文原文和 `tl/english/` 等翻译目录是独立语言层，分别导出；不能把英语条数、排序或行号硬套给原文。报告记录语言、角色、原始路径与槽位置。
6. 按主流程交付 Markdown 概况表，并推荐实际开场 JSON 做少量试注。译文放回同名 `gt_output` 后由 agent 回包。用户误改 `gt_input` 时先保存到 `gt_output`，再从哈希通过的原始归档恢复原文，不能修改 manifest 绕过校验。

## 容器读写范围

- `read_index(stream, **limits)` 支持 RPA/ARC 3.0 的单 chunk 索引，索引偏移是头中 16 位十六进制数，后跟 8 位 XOR key。
- 文件长度是含前缀的总长；读取长度必须减掉索引中的 prefix，不能多读下一成员。
- 数据专用 Pickle 解释器覆盖协议 0–5 的有限数据指令，含协议 4/5 的 `FRAME`、`MEMOIZE`、短 Unicode；索引中 GLOBAL、REDUCE、BUILD 与容器 memo 引用仍拒绝。
- `rebuild(data, replacements)` 保留原魔数、key、前缀形式、成员顺序和间隙，随长度变化重算偏移与索引。未修改时保留原压缩索引并逐字节重建；重包后再次提取，逐成员核对所有改动与未改动数据。
- 当前工作区每包上限 64 MiB，选中包累计 128 MiB；索引扫描可检查更大的媒体包，但不意味着工作区 writer 支持整包流式重建。
- 多 chunk、重叠范围、未知魔数/自定义扰码、越界、重名或不安全路径明确拒绝。不同包中同路径剧本的覆盖顺序不能靠猜测，须先整理有效输入。配对的 `.rpy` / `.rpyc` 也必须先确认源码优先级。

## RPYC2 的安全语义读写

实现：[renpy_rpyc.py](../python/engines/renpy_rpyc.py)、[renpy_pickle.py](../python/engines/renpy_pickle.py)。

- `RENPY RPC2` 之后是 `<slot, offset, compressed_size>` 小端表，零记录结束；各槽独立 zlib 压缩，末尾保留 16 字节源码 MD5。它不是编译文本的校验和，不能按译文重新计算或清零。
- 接受 slot 1，以及可选 slot 2；slot 1 是静态转换前 AST，slot 2 是转换后 AST。用文件、行号、节点身份、角色和选项位置配对，允许 Say 转成 TranslateSay，但两套文本身份/内容必须一致。
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
- 原文和导出文本都是 Unicode，Pickle 文本编码为 UTF-8，无需套用 CP932/JIS。缺字先核对游戏实际使用的字体；能保存 Unicode 不等于该字体一定有对应字形。
- 翻译表可能含 UI、编辑器残留和未使用条目；报告中区分 `translation-new`、`say`、`choice`，不能宣称全部是主线剧情。英语翻译表也不意味着原文动态 screen/Python 字符串已完整提取。

## 回包与部署

- `pack` 校验原始归档哈希、重新生成的原文与 manifest、译文文件名、数量、姓名槽及控制符。未提供译文的成员原样保留；等条数重排无法自动识别，仍要求用户保持原顺序。
- `changed-archives/game/` 只输出发生修改的同名完整归档；`loose/game/` 输出修改后的编译脚本，保留包内路径。
- 优先在游戏副本备份后替换 `game/` 下同名归档。不要沿用其他引擎经验，擅自将文件扁平化或命名为 `patch.rpa`；必须有加载配置证据。
- 松散 `.rpyc` 是否优先于包内成员，取决于当前 loader；确认后才选择该部署方式。不要同时堆叠互相覆盖的两套结果，留意旧 `.rpy`、缓存和既有补丁。
- 仅修改 AST 文本时保留源摘要、脚本版本和节点身份，不自动删除缓存或存档。若实际运行显示未生效，先核对语言选择、资源覆盖和源码重新编译，再有针对性地研究缓存。
- 游戏加载、字体显示、换行、菜单与存读档仍需运行验证；离线往返不能替代它。游戏文件覆盖与启动沿用主 Skill 授权边界。

## 保留的 `.rpy` 源码接口

`renpy.extract(script, filename="script.rpy", speakers=())` 与 `renpy.patch(script, replacements, filename="script.rpy", speakers=())` 继续使用 Unicode 字符偏移。

支持普通单/双引号、简单 Character 声明、白名单 say、旁白、有限缩进 menu、translate strings 的 new。保留原引号、注释、CRLF/LF；转义引号、反斜线、换行。Python、screen、transform、未知块保守跳过；三引号、行续接、未知转义等不在该子集内。`.rpy` 不能与 `.rpyc` 工作区 CLI 混用，也不能把源码直接塞进归档假设运行时会编译。

## 新方言适配与回归

先区分容器变体、RPYC 外壳、Pickle 指令、AST 字段及加载策略。逐层记录有限的结构诊断；对不认识的字段先证明其为显示文本，再定义定位和回写规则。不要全局替换相同字符串，不根据类名猜构造器行为；未知对象保持惰性。

新增支持须有合成正反例：双槽差异、共享 memo、循环与容器子类、控制符、非文本字段不变、长度增长、索引前缀、截断/越界、恶意构造器不执行、路径与不覆盖输出。测试：[test_renpy_rpyc.py](../tests/test_renpy_rpyc.py)、[test_archives.py](../tests/test_archives.py)、[test_engines_secondary.py](../tests/test_engines_secondary.py)。实际游戏报告只留在结果目录，不收入 Skill 验证案例。
