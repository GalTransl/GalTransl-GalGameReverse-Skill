# Artemis Engine：AST 文本剧本（`.ast`）

## 能力边界

- 引擎 ID：`artemis-ast`。**容器与 `artemis`（ASB 树）、`artemis-scp`（SCP 文本）同源**，但剧本方言、模块和解析器都不同，不要互相套用。
- 参考模块：[python/engines/artemis_ast.py](../python/engines/artemis_ast.py)。容器走 [python/archives/pfs.py](../python/archives/pfs.py)，见 [artemis-scp](artemis-scp.md)。
- 剧本：`.ast` 的 Lua 表文本解析；**命名块布局**与**位置块布局**两种拓扑；`name/message` 导出、受保护内联命令 token、可写人名回填、章节标题、选择支及选择提示。
- 不做：游戏启动、字体/字形、加载优先级实测、`>1 GB` 单卷的流式重封包、新增语言键。
- **名字消歧**：[ast](ast.md) 是另一个东西（`ARC1`/`ARC2` 容器 + `.adv` 脚本，来自 GARbro `ArcFormats/ArcAST.cs`），与 Artemis 的 `.ast` 无关。同理 `AZSystem` 的 `.asb` 也不是 Artemis 的 `.asb`。

## 识别证据

- 文件开头是 `astver = <number>`、`astname = "..."` 或直接 `ast = {`；三者可缺一，但顺序固定。`astver` 目前只认 `2.0`。
- 编码与换行以原件为准。BOM 按前 3 字节判定，不按解码器是否成功判定；默认先 UTF-8 再 CP932，显式传 `encoding` 时严格单一编码。无 BOM 文件写回不会新增 BOM，带 BOM 的保留 BOM。
- 按 `ast` 表的拓扑选布局（`Document.layout`）：

  | 布局 | 识别条件 | 文本位置 |
  |---|---|---|
  | `blocks`（命名块） | 顶层有 `label = { top = { block = "...", ... } }` | 每个块自己的 `text`/`select` 表 |
  | `positional`（位置块） | 无 `label.top`；顶层是位置表（块）加 `text = { [N] = {...} }` 与 `label` | 顶层 `text` 表的 `[N]` 条目 |

- 命名块：其余顶层成员都是块，键可以是裸名（`block_00000 = {`）或带引号字符串（`["0001_00001"] = {`），不要求固定前缀；顶层键重复以 `duplicate_key` 拒绝；混入位置成员以 `bad_structure` 拒绝。
- 位置块：顶层只允许位置表、`text` 与至多一个 `label`；其他成员 `unknown_layout_member`。块内若自带 `text`/`select` 表（两种布局混用）同样拒绝。`text` 表可出现多次，全部读取；`[N]` 键可不连续，同一 `[N]` 重复时两份都导出并在 locator 标 `duplicate_entry`（哪一份生效由运行时决定，两份都译最稳）。块内 `crc`/`lang` 与 `[N]` 的对应关系未证明，读写都不依赖它。
- 两种都没有：`missing_label`。

## 格式方言

```text
astver = 2.0                                   -- 命名块布局
ast = {
    block_00000 = {
        {"savetitle", text="第Ⅰ章"},
        {"text"},
        delay = { [1000] = { {"se", id=1, file="se0148"}, }, },
        text = {
            linemode = { start="1" },          -- 属性成员：保留，不当语言
            vo = { {"vo", file="fem_shi_00004", ch="shi"}, },
            ja = {
                {
                    name = {"<身份名>", "<显示名>"},
                    "「…", {"ruby", text="…"}, "…", {"/ruby"}, "…",
                    {"heroname", mode="fn"}, "…」",
                    {"rt2"},
                },
            },
        },
        linknext = "block_00001",
        line = 150,
    },
    label = { top = { block = "block_00000", label=1 }, },
}
```

```text
ast = {                                        -- 位置块布局
    { {"savetitle", text="…"}, {"text"}, crc="…", lang="…", line=23 },
    { {"select", file="a", text="…"}, {"select", name="sel01"}, line=40 },
    text = {
        [1] = { vo = {...}, name = {name="<身份名>", en="<英文显示名>"},
                ja = { {"…", {"rt2"}} }, en = { {"…", {"rt2"}} } },
        [2] = { lane=1, name = {name="<身份名>"} },            -- 只有姓名、没有文本框
        [3] = { select = { ja = {"…", "…"}, en = {"…", "…"} } },
        [4] = { ja = { name = {"name", name="<显示名>"}, {"…"} } },  -- 最旧变体
    },
    label = {},
}
```

- 值是 Lua 子集：带引号字符串、`[[长字符串]]`、整数/浮点（含负数）、`nil`、`true`/`false`、表。表成员可以是值或 `key = value`；键可以是裸名、`"带引号"`、`[1]`。**裸标识符**（如框里的 `{fn}`）是 Lua 全局变量引用，值只在运行时存在，以 `bare_identifier` 拒绝；遇到时改用覆盖链中更早、未被改坏的成员版本。
- **`delay = { [1000] = {...} }` 是真实存在的**：只凭"没报错"不能证明解析器正确，一个把 `[` 当普通标量的解析器会把这些表读成垃圾子树却依旧"成功"。本模块把孤立的 `[` 当错误。
- 压缩成一行的文件（整个 `ast={{...},...}` 无换行）同样支持；改写这类框时保持单行，不臆造缩进。

### 语言表

- `text` 表（命名块）或 `[N]` 条目（位置块）的成员按形状分类：
  - **语言表**：至少一个位置成员、且每个位置成员都是文本框的表；可带一个语言级 `name`。
  - **属性**：标量（`hide=true`）或只含标量键值对的表（`linemode={}`、`linemode={start="1"}`、`lane=1`）。保留原样，不导出。
  - `vo`、`vlNN`、`lvN` 是语音层；位置块条目里的 `name`、`select` 另行处理。
  - 其他形状（如 `{ {mode="x"} }`）以 `unknown_text_member` 拒绝，不猜。
- `select` 表：`select = { ja = {"…", …}, en = {...} }` 按语言取；直接是字符串列表（无语言键）时视为与语言无关的选项（locator `language` 为空）。
- **语言选择**：`language=` 显式指定；不指定时取文档中第一个出现的语言键（`Document.selected_language`），全部语言见 `Document.languages`。不要写死 `ja`。
  - 某个表有别的语言却缺所选语言：该表不导出，记入 `Document.skipped`（引擎按所选语言取表，缺失时不显示或回退到其他语言，翻译它没有意义；需要时先补语言键）。
  - 整个成员都没有所选语言（只有其他语言）：`no_language_table`。
  - 只有语音或属性、没有语言表（如只放 `vo` 的块）：零条文本，原样往返，不报错。

### 文本框与受保护 token

- 引擎按顺序执行框内成员：字符串打印，表当作标签执行。`{"rt2"}`/`{"ret2"}` 结束一行，因此正文 = 字符串片段按换行拼接。**`\n` 与 `rt2` 语义等价**：已发行的汉化补丁把 `"A", {"rt2"}, "B", {"rt2"}` 改写为 `"A\nB", {"rt2"}`；不含 token 的框按这种写法回写，并沿用原来的换行标签。
- 其余内联命令**原样作为受保护 token 出现在正文里**，token 就是该命令的 Lua 源码切片，例如 `x{"heroname", mode="fn"}y`、`{"exfont", size="f2"}「…」{"exfont"}`。内置：`exfont`、`txkey`、`txruby`、`heroname`（打印玩家输入的名字）、`gaiji`（用外字字体打印 `text`）。未知标签以 `unknown_inline` 拒绝；确认它应原样保留后用 `extra_inline_tags={"tag"}` 放行，同样成为 token。
- **译文必须包含同样的 token、顺序不变**（位置可在正文内移动）；缺失、多出、换序或正文里出现不属于本框的 `{"` 都以 `token_mismatch` 拒绝。`protected_tokens()` 给出每行去重后的 token，可直接交给 `contract.make_manifest`。
- 原文字面量里含 `{"`（与 token 前缀冲突）以 `ambiguous_token` 拒绝；跨行的内联命令以 `multiline_inline` 拒绝。
- `{"ruby", text="…"}`/`{"/ruby"}` 是振假名，不进 token：正文只含被注音的字；改写该框时振假名丢弃，并在 locator 的 `furigana` 中报告。
- 转义是 **Lua 全集**：`\n \r \t \v \b \f \a \' \" \\ \ddd \xXX \uXXXX \u{...}`。未知转义默认拒绝（`unknown_escape`），`lenient_escapes=True` 时按字面保留——已发行的汉化补丁里真的存在 `\我` 这类非法转义。
- 写回默认只转义 `\n`，因为该补丁只证明了 `\n` 可用；`"`、`\`、CR 与其它控制字符需要显式 `allow_lua_escapes=True`，否则以 `unsafe_character` 拒绝，而不是静默丢弃。英文文本常含 `"`，改写时通常需要该开关。

## Python 接口与示例

```python
from python.engines import artemis_ast as ast

document = ast.read_ast(raw, language=None)   # None = 文档中第一个语言键
document.layout, document.languages, document.selected_language, document.skipped
rows = document.rows()                         # [{"name": "…", "message": "…\n…"}]
locators = document.locators()                 # layout / block / index / span / language / name_form / tokens …
policies = document.name_policies()            # "writable" | "context" | "absent"
tokens = document.protected_tokens()           # 每行的内联命令 token
rebuilt = document.patch(rows)                 # 重解析校验；相同 rows 得到相同字节
```

- `looks_like_ast(data)`：只探测头部（`astver`/`astname`/`ast` 后跟 `=`），用来在 ASB 与 SCP 之间选路，不是支持承诺。探测只解码前缀，截断点落在多字节字符中间时按增量解码回退到完整字符，不会误判。
- `read_ast(data, *, encoding, language, extra_inline_tags, lenient_escapes, max_bytes)`。
- `render(document, rows)` → 文本；`encode_ast(document, text)` → bytes；`patch_ast(data, rows, ...)` = `read_ast(...).patch(rows)`。
- **优先用 `Document.patch`**：`Document` 保存解析时的编码/BOM、`language`、`extra_inline_tags`、`lenient_escapes`，回填后用同一组参数重解析并校验，不必再传一遍参数；`patch_ast` 需调用者保证参数与分析时一致。批量处理多语言游戏时对每个成员传同一个 `language`。

## name / message 映射

- 对白：所选语言表的每个文本框一条；旁白就是没有姓名的框。块标识：命名块用块名，位置块条目用 `text[N]`（多个 `text` 表时 `text#2[N]`），位置块本身用 `#N`（从 1 起）。
- 行只导出**显示名** `name`，不接受 `names`（`bad_name`）。身份名写入 locator 的 `name_identity`，只作上下文、永不改写。三种姓名形态（`locator.name_form`）：

  | 形态 | 位置与写法 | 显示名 | 回填 |
  |---|---|---|---|
  | `slots` | 框内 `name = {"身份", "显示"}` | 最后一槽 | 替换最后一槽；只有一槽时**追加**显示槽（`{"A"}` → `{"A", "译名"}`），不覆盖身份 |
  | `keyed` | 框内 `name = {name="身份", ja="显示"}` | 最后一个键 | 替换最后一个键；只有一个带键槽时为 `context`（追加需臆造键名），改名以 `name_not_writable` 拒绝 |
  | `entry` | 位置块条目 `name = {name="身份", en="…", cn="…"}` | `name[所选语言]`，没有则 `name.name` | 有所选语言键就替换；没有就追加该语言键（`, ja="译名"`，分隔符沿用表内写法），`name` 身份键不动 |
  | `command` | 最旧变体语言表内 `name = {"name", name="…"}` | `text` 属性，没有则 `name` | 直接替换该语言表里的这一项（各语言各有一份，官方本地化即按此改写） |

  - 位置块条目的姓名与文本框是一对一的；一个姓名表对应多个框以 `ambiguous_name` 拒绝，条目级与语言级同时声明姓名以 `duplicate_name` 拒绝，条目姓名缺 `name` 身份键以 `bad_name` 拒绝。
  - 只有姓名、没有任何语言表的条目（聊天类界面的贴图消息等）导出为 `message` 为空的一行，locator 标 `boxless`：可改姓名，给正文以 `bad_message` 拒绝。
  - 只改姓名不改正文时只编辑姓名字面量，振假名等框内结构不动。
- 选择支 `choice`：命名块与位置块条目的 `select.<语言>[i]`；与语言无关的字符串列表直接导出。位置块中**没有任何条目带 `select` 表**时（最旧变体），选项写在块命令 `{"select", text=…, text_<语言>=…}` 里，导出该命令按语言解析出的文字，同一命令的 `mw`/`mw_<语言>` 作为 `prompt`（选择时消息窗显示的提示）。命名块的块级 `{"select", text=…}` 不导出（显示文字取自 `select` 表）。
- 标题 `title`：`{"savetitle", text=…}`。块命令属性按语言解析：`text_<语言>` 或 `<语言>` 键优先，没有则用 `text`；两者同时存在以 `ambiguous_attribute` 拒绝。没有专属键时改写的是各语言共用的 `text` 回退值。
- 选项、提示、标题都没有姓名槽，给 `name`/`names` 以 `name_not_writable` 拒绝。

## 回填、长度与控制码

- 只替换单元自己的字节区间：文本框替换花括号内部，选项/提示/标题替换字符串字面量（含引号），姓名只改姓名表内的字面量或追加一项。其余字节——其他语言表、`delay`、`vo`、`lane`/`linemode` 等属性、`crc`/`lang`/`linknext`/`line`、块级命令、`label`——一律不动。
- 未改动的单元不产生任何编辑，所以**原文空改动往返逐字节一致**。
- 改写后的框：不含 token 时为"单个字面量 + 原本的尾换行标签"；含 token 时逐行写出"字面量与 token 按原顺序交替 + 行间换行标签"。原本在语句之间插空行的文件保留空行风格，单行压缩文件保持单行。框内姓名按原文切片写回（只替换显示槽）。
- 含 token 的框若译文以空行结尾而原框没有尾换行标签，无法表示，以 `bad_message` 拒绝。
- 拒绝：空消息（原本非空）、嵌入 CR/NUL、`"`/`\` 等不可写字符（除非 `allow_lua_escapes`）、条数不符、出现 `names`、给选项或标题塞姓名、token 不符。
- `Document.patch`（及调用它的 `patch_ast`）用解析时的参数重新解析，比对 BOM、布局与所选语言、跳过列表、单元数量与身份、每条文案、内联命令 token 序列、完整姓名槽（含身份槽与键名）、**全部单元区间之外的字节**，命名块再比对块级非文本骨架；任一不符以 `verification_failed` 拒绝。

## 部署条件与未验证项

- 多分卷与补丁制作见 [PFS 覆盖卷](artemis.md#打包技巧新增-pfs-覆盖卷)，加载结果须单独试注确认。
- 如需新增语言键，先核对语言配置、文本键及 UI/资源选择逻辑；当前 writer 只修改选定语言，不自动创建语言表、语言切换、字体或资源配置。
- 未做字体/字形、存档、选择支排版与游戏启动验证；`entry` 形态追加语言键、`heroname`/`gaiji` token 回写只经过格式往返验证，游戏内显示未验证。

## 源码与算法对应

- 剧本：[artemis_ast.py](../python/engines/artemis_ast.py)，格式资料来源 msg-tool（GPL-3.0-or-later）；内联标签资料来源 SExtractor（GPL-3.0），通知见 [NOTICE](../provenance/NOTICE.md)。
- 语言键、姓名显示规则（`name[语言] or name.name`、`text or name`）、`text_<语言>` 属性回退、`heroname`/`gaiji` 打印文字、缺语言时不显示等行为，依据各发行版随包系统脚本中对 `ast.text`、姓名表和选择支的读取方式整理为上述规则。
- 解析约束：语言键不写死；语言表按形状判定、属性成员保留；姓名身份槽只读；未知内联标签拒绝而不是跳过；孤立 `[` 与裸标识符视为错误；`astver` 只认 `2.0`；写回默认只转义 `\n`。
- 容器：[python/archives/pfs.py](../python/archives/pfs.py)，见 [artemis-scp](artemis-scp.md)。

## 验证与缺口

- 合成测试：`tests/test_engines_artemis_ast.py`。覆盖头部三种形态、带引号块键、无 BOM/带 BOM 默认参数逐字节往返、探测截断跨多字节字符、`Document.patch` 重解析校验（含篡改 token 与区间外字节）、`rt2`/`ret2`、ruby、内联 token 的导出/回写/换行数变化/缺失换序多出、`heroname`/`gaiji`、属性成员（`linemode`/`hide=true`）与纯语音表、布尔值、裸标识符、多语言选择与缺语言跳过、四种姓名形态与追加语言键、位置块布局（多语言、只有姓名的条目、重复 `[N]`、块命令选项与提示、`text_<语言>` 标题）、单行压缩文件、`select`/`savetitle`、`delay` 的 `[1000] =`、`[[长串]]`/`["引号键"]`/`nil`、Lua 转义与宽松读取、空行风格，以及全部拒绝路径。
- 缺口：新增语言键流程、大卷流式写出及尾部附加表用途；字体、存档和游戏加载需单独验证。
