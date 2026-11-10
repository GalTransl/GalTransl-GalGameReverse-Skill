# Artemis Engine：AST 文本剧本（`.ast`）

## 能力边界

- 引擎 ID：`artemis-ast`。**容器与 `artemis`（ASB 树）、`artemis-scp`（SCP 文本）同源**，但剧本方言、模块和解析器都不同，不要互相套用。
- 参考模块：[python/engines/artemis_ast.py](../python/engines/artemis_ast.py)。容器走 [python/archives/pfs.py](../python/archives/pfs.py)，见 [artemis-scp](artemis-scp.md)。
- 剧本：`.ast` 的 Lua 表文本解析、`name/message` 导出、可写人名回填、章节标题与选择支。
- 不做：游戏启动、字体/字形、加载优先级实测、`>1 GB` 单卷的流式重封包、旧布局 `.ast`（见下）。
- **名字消歧**：[ast](ast.md) 是另一个东西（`ARC1`/`ARC2` 容器 + `.adv` 脚本，来自 GARbro `ArcFormats/ArcAST.cs`），与 Artemis 的 `.ast` 无关。同理 `AZSystem` 的 `.asb` 也不是 Artemis 的 `.asb`。

## 识别证据

- 文件开头是 `astver = <number>`、`astname = "..."` 或直接 `ast = {`；三者可缺一，但顺序固定。`astver` 目前只认 `2.0`。
- 编码与换行以原件为准。BOM 按前 3 字节判定，不按解码器是否成功判定；默认先 UTF-8 再 CP932，显式传 `encoding` 时严格单一编码。无 BOM 文件写回不会新增 BOM，带 BOM 的保留 BOM。
- 顶层必有 `label = { top = { block = "...", label=N }, ... }`；其余顶层成员都是块，键可以是裸名（`block_00000 = {`）或带引号字符串（`["0001_00001"] = {`），块名以 `label.top.block`、`linknext` 等引用为准，不要求固定前缀。顶层键重复以 `duplicate_key` 拒绝。没有 `label.top` 但有顶层 `text` 表 = **旧布局**，本模块明确拒绝（`old_layout`），不猜。

## 格式方言

```text
astver = 2.0
astname = "chapter01"          -- 可缺
ast = {
    block_00000 = {
        {"savetitle", text="第Ⅰ章"},
        {"text"},
        delay = { [1000] = { {"se", id=1, file="se0148"}, }, },
        text = {
            vo = { {"vo", file="fem_shi_00004", ch="shi"}, },
            ja = {
                {
                    name = {"静流", "？？？"},
                    "「そうですか。",
                    {"ruby", text="つぶらぎ"},
                    "円木",
                    {"/ruby"},
                    "ちゃんですか？」",
                    {"rt2"},
                    "かれこれ１０年ぐらい前です。",
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

- 值是 Lua 子集：带引号字符串、`[[长字符串]]`、整数/浮点（含负数）、`nil`、表。表成员可以是值或 `key = value`；键可以是裸名、`"带引号"`、`[1]`。
- **`delay = { [1000] = {...} }` 是真实存在的**：只凭"没报错"不能证明解析器正确，一个把 `[` 当普通标量的解析器会把这些表读成垃圾子树却依旧"成功"。本模块把孤立的 `[` 当错误。
- 对白在 `text.<语言>`；一个元素 = 一个文本框。语言键取**第一个不是 `vo`/`vlNN`/`lvN`/`name` 的成员**；不要写死为 `ja`，可用 `language=` 指定。
- `{"rt2"}`（以及 `{"ret2"}`，msg-tool 把两者都映射为换行）结束一行渲染，因此框内正文 = 字符串片段按换行拼接。**`\n` 与 `rt2` 语义等价**：一份已发行的汉化补丁把 `"A", {"rt2"}, "B", {"rt2"}` 改写为单个字面量 `"A\nB", {"rt2"}`，分隔符总数不变，只是换了一种写法。本模块采用同样的规范化写法，并沿用该框原本用的换行标签。
- 无字面量的内联命令：`{"ruby", text="..."}`/`{"/ruby"}`（振假名）、`{"exfont" ...}`/`{"exfont"}`、`{"txkey"}`、`{"txruby"}`。未知内联标签直接拒绝；确认它不带字面量时用 `extra_inline_tags={"tag"}` 放行。
- 转义是 **Lua 全集**：`\n \r \t \v \b \f \a \' \" \\ \ddd \xXX \uXXXX \u{...}`。未知转义默认拒绝（`unknown_escape`），`lenient_escapes=True` 时按字面保留——已发行的汉化补丁里真的存在 `\我` 这类非法转义。
- 写回默认只转义 `\n`，因为该补丁只证明了 `\n` 可用；`"`、`\`、CR 与其它控制字符需要显式 `allow_lua_escapes=True`，否则以 `unsafe_character` 拒绝，而不是静默丢弃。

## Python 接口与示例

```python
from python.engines import artemis_ast as ast

document = ast.read_ast(raw, encoding="utf-8")
rows = document.rows()                     # [{"name": "？？？", "message": "…\n…"}]
locators = document.locators()             # block / index / span / source_lines / name_slots / name_identity
policies = document.name_policies()        # "writable" | "context" | "absent"
tokens = document.protected_tokens()       # 本方言没有正文内受保护字面量
rebuilt = document.patch(rows)             # 重解析校验；相同 rows 得到相同字节
```

- `looks_like_ast(data)`：只探测头部（`astver`/`astname`/`ast` 后跟 `=`），用来在 ASB 与 SCP 之间选路，不是支持承诺。探测只解码前缀，截断点落在多字节字符中间时按增量解码回退到完整字符，不会误判。
- `read_ast(data, *, encoding, language, extra_inline_tags, lenient_escapes, max_bytes)`。
- `render(document, rows)` → 文本；`encode_ast(document, text)` → bytes；`patch_ast(data, rows, ...)` = `read_ast(...).patch(rows)`。
- **优先用 `Document.patch`**：`Document` 保存解析时的编码/BOM、`language`、`extra_inline_tags`、`lenient_escapes`，回填后用同一组参数重解析并校验（见下文），不必再传一遍参数；`patch_ast` 需调用者保证参数与分析时一致。

## name / message 映射

- 对白：`text.<lang>[i]`；旁白同一个元素只是没有 `name`。
- 姓名：与 ASB `name` 命令同一规则——**槽 0 是固定的角色身份，最后一槽是显示名**。官方多语言数据中槽 0 不随语言变化，只有最后一槽变（如 `{"<身份名>", "<英文显示名>"}`、`{"<身份名>", "女子"}`）。
  - 行只导出显示名：`name` = 最后一槽；槽 0 写入 locator 的 `name_identity`，只作上下文，不导出、不改写。不接受 `names`（以 `bad_name` 拒绝）。
  - 多槽：只替换最后一槽的字面量。单槽：译名不同时**追加**显示槽（`{"A"}` → `{"A", "译名"}`），不覆盖身份；译名与原文相同则不改动。只改姓名不改正文时只编辑姓名字面量，振假名等框内结构不动。
  - 语言键形态 `name = { name="...", ja="..." }` 同样以最后一个键为显示槽，键名保留；只有一个带键槽时无法在不臆造键名的情况下追加，策略为 `context`，改名以 `name_not_writable` 拒绝。
- `select.<lang>[i]` → `choice`，`{"savetitle", text="..."}` → `title`；两者都没有姓名槽，给 `name`/`names` 会以 `name_not_writable` 拒绝。
- `protected_tokens()` 恒为空数组：本方言的正文里没有控制码字面量；换行是真实换行，不是 token。真要看结构，读 locator 的 `source_lines`、`furigana`、`inline_commands`。

## 回填、长度与控制码

- 只替换单元自己的字节区间：文本框替换花括号内部，选项/标题替换字符串字面量（含引号）。其余字节——`delay` 表、`vo` 表、`linknext`/`line`、块级命令、`label`——一律不动。
- 未改动的单元不产生任何编辑，所以**原文空改动往返逐字节一致**。
- 改写后的框按"单个字面量 + 原本的尾换行标签"输出；行分隔用 `\n`。原本在语句之间插空行的文件，写回时保留空行风格。
- **振假名无法迁移**：改写框时 `ruby` 被丢弃，通过 locator 的 `furigana` 报告，不静默删除。
- **内联命令尽量保位**：译文行数与原文一致时，`exfont`/`txkey` 按原行内前后位置重放；行数不一致时无法定位，回退为合并字面量，并把 `inline_commands` 写进 locator。
- 拒绝：空消息（原本非空）、嵌入 CR/NUL、`"`/`\` 等不可写字符（除非 `allow_lua_escapes`）、条数不符、出现 `names`、给选项或标题塞姓名。
- `Document.patch`（及调用它的 `patch_ast`）会用解析时的参数重新解析，比对 BOM、单元数量与身份、每条文案、完整姓名槽（含身份槽与键名）以及块级非文本骨架，任一不符以 `verification_failed` 拒绝。

## 部署条件与未验证项

- 多分卷与补丁制作见 [PFS 覆盖卷](artemis.md#打包技巧新增-pfs-覆盖卷)，加载结果须单独试注确认。
- 如需新增语言键，先核对语言配置、文本键及 UI/资源选择逻辑；当前 writer 只修改选定语言，不自动创建语言切换、字体或资源配置。
- 未做字体/字形、存档、选择支排版与游戏启动验证。

## 源码与算法对应

- 剧本：[artemis_ast.py](../python/engines/artemis_ast.py)，格式资料来源 msg-tool（GPL-3.0-or-later）；内联标签资料来源 SExtractor（GPL-3.0），通知见 [NOTICE](../provenance/NOTICE.md)。
- 解析约束：语言键不写死为 `ja`；姓名槽全部保留，身份槽只读、最后一槽为显示名；未知内联标签拒绝而不是跳过；孤立 `[` 视为错误；`astver` 只认 `2.0`；写回默认只转义 `\n`。
- 不是该 Rust 模块的全量移植：**旧布局 `.ast` 未实现**，发现即以 `old_layout` 拒绝。
- 容器：[python/archives/pfs.py](../python/archives/pfs.py)，见 [artemis-scp](artemis-scp.md)。

## 验证与缺口

- 合成测试：`tests/test_engines_artemis_ast.py`。覆盖头部三种形态、带引号块键、无 BOM/带 BOM 默认参数逐字节往返、探测截断跨多字节字符、`Document.patch` 重解析校验、`rt2`/`ret2`、ruby、`exfont` 保位与回退、身份槽/显示槽与单槽追加、语言键姓名、`select`/`savetitle`、`delay` 的 `[1000] =`、`[[长串]]`/`["引号键"]`/`nil`、Lua 转义与宽松读取、空行风格、以及全部拒绝路径。
- 缺口：旧布局 `.ast`、新增语言键流程、大卷流式写出及尾部附加表用途；字体、存档和游戏加载需单独验证。
