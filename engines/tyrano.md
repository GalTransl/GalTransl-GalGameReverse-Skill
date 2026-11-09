# TyranoScript：Electron app.asar、.ks 剧本与补丁

TyranoScript 用 KAG 风格的 `.ks` 剧本，但语法和运行时与 Kirikiri 不同，不能套用 [Kirikiri KAG](kirikiri.md) 的解析器。

| 层 | 模块 |
|---|---|
| 归档 | [archives/asar.py](../python/archives/asar.py)：asar 头部解析、成员读取、流式重建与逐成员核对 |
| 剧本 | [engines/tyrano.py](../python/engines/tyrano.py)：按引擎规则解析 `.ks`、导出对白、原位回写与重解析校验 |
| 工作区 | [engines/tyrano_extract.py](../python/engines/tyrano_extract.py)：`extract` / `pack` CLI |

## 识别

- Electron 构建：`resources/app.asar`（偏移 0 为 u32 `4`，偏移 16 起是 `{"files":` JSON）；头部 JSON 中有 `tyrano/` 目录和 `data/scenario/*.ks`。游戏目录常见 Chromium 运行库（`*.pak`、`icudtl.dat`、`v8_context_snapshot.bin`）。`detect.py` 只读头部 JSON 判断布局。
- 松散构建（NW.js/浏览器）：游戏目录下直接有 `data/scenario/*.ks` 和 `tyrano/plugins/kag/kag.parser.js`。
- `data/system/Config.tjs` 中 `;projectID=`、`;patch_apply_auto=` 决定引擎自带补丁的文件名和是否自动应用。
- 剧本为 UTF-8（可带 BOM），换行 CRLF 或 LF 均有，按原样保留。

## 剧本规则

解析与引擎的 `parseScenario` 一致：按 LF 分行，每行先做 JavaScript `trim`（含全角空格和 BOM），再按首字符分派：

| 行首 | 含义 | 导出 |
|---|---|---|
| `;` | 注释 | 否 |
| 整行 `/*` … `*/` | 块注释 | 否 |
| `#名字` / `#名字:表情` | 说话人；单独 `#` 清空为旁白 | 姓名 |
| `*标签` | 标签 | 否 |
| `@tag ...` | 单行命令 | 否 |
| `_` | 去掉 `_` 后按正文处理，保留其后的前导空白 | 正文 |
| 其他 | 正文与 `[tag]` 混排，方括号可嵌套 | 正文 |

- 一条对白从首段正文开始，到 `[p]`、`[cm]`、`[er]`、`[s]`、`[jump]`、`[call]`、`[return]`、`#`/`*` 行或 `@` 命令为止。引擎把相邻正文行直接拼接，不插入换行；换行只来自 `[r]`。
- 正文之间的标签（`[l]`、`[r]`、`[ruby ...]`、`[font ...]` 等）原样留在 message 里作为受保护字面量，首尾的标签不进入 message。
- `[iscript]` 之后方括号按原文处理，直到某行出现 `endscript`；`[html]…[endhtml]`、`[macro]…[endmacro]` 内的文字是代码、HTML 或模板，不导出（数量记在 `skipped_block_text`）。
- `#名字` 的显示规则：名字是 `[chara_new]` 的 `name`（角色键）时显示其 `jname`；否则直接显示该文字，同时引擎用 `jname → 角色键` 反查立绘做聚焦和表情。
- `[glink text="..."]` 的选项文字导出为无姓名条目。图形按钮（`[button graphic=...]`）不含文字。

## 回写约束

- message 中的标签必须原样、同序、同数量保留；message 首尾必须是正文。译文不能含换行，换行只能用原有的 `[r]`。
- 正文在行首且译文以 `# * @ ; _` 或空白开头时，自动加 `_` 前缀，避免被当作命令。行尾空白会被引擎 trim，落在行尾时直接拒绝。
- 一段正文跨多行时，译文写入第一段，其余行清空。清空或新增正文会改变该剧本的标签序号，旧存档可能从附近位置恢复，试玩建议从新游戏开始。
- 姓名按全工作区统一映射：同一原名只能有一个译名，否则拒绝。写回时同时改所有用到它的 `#` 行和 `jname="原名"` 属性，以保持聚焦和表情联动。`#角色键` 行本身不改，只改 `jname`。没有放入 `gt_output` 的剧本也会套用这份姓名映射。
- 引擎解析带引号的属性时会删掉其中的 ASCII 空格，并把 `#` 当作 `=`。因此姓名和选项译文不得含空格、`# = " ' [ ]`，姓名还不得含 `:`。
- 每个剧本回写后都重新解析：对白和姓名须等于译文，非文本结构（标签、标签行、表情、`jname`/`text` 以外的属性）须与原文一致。

## 工作区

```text
python -m python.engines.tyrano_extract extract "<游戏目录>" "<游戏目录>/<游戏名>_extract"
python -m python.engines.tyrano_extract pack "<工作区>" "<新的输出目录>"
python -m python.engines.tyrano_extract pack "<工作区>" "<新的输出目录>" --mode tpatch
```

- `extract` 读取 `resources/app.asar`（`--asar` 可指定其他相对路径）；找不到时按松散 `data/` 树读取。所有 `data/**/*.ks` 原样存入 `original/`，用于收集 `jname` 和同步改名；对白只从 `--members`（默认 `data/scenario/*.ks`）导出。每个剧本都做原文重建（须逐字节一致）和"验证"前缀的变长冒烟测试。
- **可达性**：剧本基名出现在任意 `storage=` 值或 `.ks/.js/.html/.json/.tjs` 资源文字中，才算被引用；`first.ks`、`make.ks` 是引擎入口。未被引用的剧本（常见为备用稿、旧版本）列在 `reachability.unreferenced`，默认不进入 `gt_input`。若 `dynamic_references` 中有用变量拼接的跳转，且确认未引用的剧本会被它加载，就用 `--include-unreferenced` 重新提取。
- `pack` 先核对原剧本哈希、`gt_input`/`metadata` 未被改动、`gt_output` 文件名都在导出清单中，再回写全部剧本，只输出实际变化的成员。

## 交付方式

Tyrano/Electron 没有像 XP3 那样"不改原包、按编号叠加"的增量补丁。三种产物按来源选择：

| `--mode` | 产物 | 说明 |
|---|---|---|
| `asar`（asar 来源默认） | `<输出>/resources/app.asar` | 流式重建：未改成员逐字节复制，只更新变化成员、后续偏移和 `integrity`。写出后逐成员与原包核对。用户备份原 `resources/app.asar` 后覆盖。 |
| `tpatch` | `<输出>/<projectID>.tpatch` | 引擎自带补丁，zip 内只含变化的剧本。放在 exe 同目录，下次启动时引擎把整个 app.asar 解开、覆盖、重新打包写回原文件，然后删除补丁。需要约两倍包体的临时空间；重新打包是异步的，必须等重启提示出现后再关闭，否则可能写坏 app.asar。仅在用户明确选择时使用，并先备份。`patch_apply_auto=false` 时引擎不会应用。 |
| `loose`（松散来源默认） | 只有变化的 `data/...` 文件 | 按原相对路径覆盖到游戏目录前先备份。 |

- 启用了 asar 头部完整性校验（exe 内嵌头部哈希）的较新 Electron 会拒绝修改过的 app.asar；需要先确认这项校验没有开启，或改用 `resources/app/` 目录方案。
- 中文显示依赖 Chromium 字体回退，一般无需 JIS 替换；若作品指定了只含日文的网页字体（`Config.tjs` 的 `userFace` 或 CSS `@font-face`），需改为含中文的字体。
- 交付时分别说明解包、提取、原文往返、回写重解析、重封包核对和游戏显示的状态；未运行游戏时，显示和存档兼容都写"未验证"。

## 出处

剧本规则依据 TyranoScript（MIT，ShikemokuMK）的解析与标签语义，asar 布局依据 electron/asar（MIT），实现为本 Skill 新写代码，未复制上游源码。来源、符号与偏差见 [Tyrano 来源记录](../provenance/tyrano.json)。
