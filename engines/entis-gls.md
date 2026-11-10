# Entis GLS：NOA 归档、SRCXML 多语言消息与 CSX 容器

## 能力边界
- 引擎 ID：`entis-gls`，Python 模块名 `entis_gls`。
- 模块：
  - [python/archives/entis_noa.py](../python/archives/entis_noa.py)：NOA 索引、成员解码、扁平 NOA 写出；
  - [python/archives/entis_erisa.py](../python/archives/entis_erisa.py)：ERISA-N 解压与 BSHF 解密；
  - [python/engines/entis_srcxml.py](../python/engines/entis_srcxml.py)：引擎方言 SRCXML 词法读取与保字节回写；
  - [python/engines/entis_extract.py](../python/engines/entis_extract.py)：mounts / extract / rebuild / readback 工作流；
  - [python/engines/entis_gls.py](../python/engines/entis_gls.py)：严格 XML 的 SRCXML 语义往返；
  - [python/archives/entis_csx.py](../python/archives/entis_csx.py)：CSX 分块、`conststr` 与 `image` 字面量。
- 支持状态（分阶段）：
  - NOA 解包：raw 与 ERISA-N（`0x80000010`）用真实样本验证。BSHF、ERISA 加密（`0xC0000010`）和 SimpleCrypt32 按资料移植，需显式口令，未见真实样本。`0xA0000010` 等其他编码一律拒绝。
  - 语义提取：引擎方言 SRCXML 的 `msg`、`select/menu`，以及 `open_line_msg` 标题。
  - 回填与封包：变长译文写回 SRCXML。可生成只含改动成员（raw 存储）的 NOA，也可覆盖到某个现有 NOA 的副本。写出后用真实 reader 读回校验。
  - 游戏显示：**未验证**。补丁包按成员名覆盖、raw 成员被引擎接受，这两点都只是根据结构证据推断。
- 不做：ERISA-N 压缩、NOA 子目录写出、CSX 编译/反汇编、从 EXE 推导加密口令。

## 识别证据
- NOA 的特征：
  - 偏移 0 为 `Entis\x1a\0\0`；
  - 偏移 8 为 `u32 0x02000400`；
  - 偏移 `0x10` 为 `ERISA-Archive file`。
  - 偏移 `0x10` 为 `Cotopha Image file` 的是 CSX。扩展名不能单独作为依据。
- `.srcxml` 与 `xscript` 根元素是直接线索；`code` 下 `msg` 带 `name_*`/`text_*` 属性。
- 引擎 EXE 的 RCDATA 资源 `IDR_COTOMI` 是 ERISA-N 压缩的启动 XML：
  - `<script src="…csx">` 给出要执行的 CSX；
  - `<archive path=…>` 按顺序列出挂载的 NOA；
  - `<file path=…>` 列出松散目录。
  - `mounts` 子命令只读解码该资源，不执行 EXE。
- `.csx` 是另一组版本化代码格式，不应送进 XML parser。

## 剧本文本在哪里：SRCXML 还是 CSX
判断方法如下。按顺序核对，结论写入报告：
1. 用 `mounts` 查看 `<script src>`：它是常驻的引擎/系统脚本（CSX 镜像），不一定含剧情。
2. 对 CSX 运行 `parse_conststr`，查找 `.srcxml`、`xscript`、`text_`、`name_` 等常量。出现即说明 CSX 在运行时读取 SRCXML，并按语言后缀取属性。
3. 抽取几条 SRCXML 正文，分别按 UTF-16LE、UTF-8、CP932 在 CSX 中搜索。搜不到则正文只在 SRCXML。
4. 第 2、3 步都成立时翻译 SRCXML。只有 CSX、且正文在 `conststr`/`image` 中时，才走下文 CSX 路线。

已核对的方言结论：
- SRCXML 是带多语言属性的剧情源（如 `text_JA`/`text_EN`/`text_ZHTW`），运行时由 CSX 解释。
- CSX 是框架脚本，不含剧情正文，改 CSX 不能翻译剧情。
- 现有 `entis_csx` 能读这类 CSX 的分块目录与 `conststr`。但 `image` 遇到未建模的操作码（如 opcode 1）就会拒绝，因此这类文件无法用 `entis_csx` 提取或回写 CSX 字面量；翻译剧情也用不到它。

## SRCXML 引擎方言
- 文件为 UTF-8（带 `<?xml … encoding="utf-8"?>`，可无 BOM，CRLF），**不是严格 XML**：
  - 属性名可以 `@` 开头（`@l` 为源行号）；
  - 正文可含 XML 1.0 禁止的字符引用（如 `&#8;`）。
  - 因此 `entis_gls`（ElementTree）会拒绝这类文件，须改用 `entis_srcxml`。
- 引擎写出的属性值转义约定：
  - U+0020 及以下字符写作 `&#N;`，空格总是写作 `&#32;`，属性值内没有字面空格；
  - `&`、`"` 分别写作 `&amp;`、`&quot;`。
- 写回与校验：
  - 写回时沿用上述约定；`<`/`>` 写作 `&#60;`/`&#62;`（已有证据表明引擎接受数字引用）。
  - 提取时逐个检查原值能否按此约定还原。有不符即判该成员失败，不猜写法。
- 词法读取有界：
  - 拒绝 DTD/ENTITY/CDATA、未知实体、标签不配对、重复属性、未加引号的值、多个根元素和非 UTF-8 声明；
  - 限制 32 Mi 字符、100 万元素、256 层嵌套。
- 记录：
  - `xscript/code/msg`：`name_<语言>` 为姓名，`text_<语言>` 为正文；
  - `select/menu`：`text_<语言>` 为选项；无后缀的 `text` 不是翻译槽位，保持原样；
  - `open_line_msg`：`title_<语言>` 为聊天窗标题。
  - 有多种语言时必须指定后缀；目标语言缺属性即报错。
- 姓名策略：
  - 非空姓名可写；空姓名不导出 `name`。
  - `%name` 等引擎变量（`%fname`、`%fp`、`%name`、`%nck`、`%nick`）只作上下文，不可改。
- 控制码与换行：
  - 上述 `%` 变量和反斜杠序列（如注音 `\r;漢字;かな:`、换行 `\n`）都列为保护 token，数量改变即拒绝。
  - 译文不得含真实换行，用脚本自己的 `\n` 序列。
- 回写范围：
  - 只替换被改属性值的字节，其余字节不变；未改动的文件重写后逐字节一致。
  - 写回后重新解析，逐条比对记录类型、正文和姓名。

## NOA 容器
小端；除特别说明外，偏移都从文件头算起。
- 头部 0x40 字节，依次为：
  - magic；
  - `u32 0x02000400`、`u32 0`；
  - 40 字节描述（`ERISA-Archive file` 补零）；
  - `u64` 正文大小（等于文件大小 − 0x40）。
- 0x40 处为 `DirEntry` 记录：8 字节 tag、`u64` 载荷长度。载荷为 `u32` 条数加逐条目录项，每项依次为：
  - `u64` 解码后大小；
  - `u32` 属性；
  - `u32` 编码；
  - `i64` 偏移（相对本 `DirEntry` 记录起点）；
  - 8 字节 ERISA 时间（秒、分、时、星期、日、月、`u16` 年）；
  - `u32` extra 长度与 extra；
  - `u32` 名称长度与以 NUL 结尾的名称。
- 成员记录为 `filedata` tag + `u64` 存储长度 + 存储字节。raw 成员的存储长度必须等于目录项中的大小。
- 属性：
  - `0x10` 为子目录：该偏移处记录的载荷以嵌套 `DirEntry` 开始，嵌套偏移相对嵌套记录起点（按资料实现，真实样本中未见）；
  - `0x20`/`0x40` 为目录结束标记；
  - `0x01000000` 表示名称为 UTF-8。无此标志的非 ASCII 名称须显式传入 `name_encoding`。
- 编码：
  - `0`：raw；
  - `0x80000010`：ERISA-N。存储字节 = Nemesis 码流 + `u32` 校验值；校验值是把解码数据按小端 `u32`（末尾补零）逐字异或的结果。读取时核对，不符即报错。
  - `0x40000000`：BSHF；
  - `0xC0000010`：先 BSHF 再 ERISA-N；
  - `0x20000000`：SimpleCrypt32，extra 偏移 4 处为乘法 key。
  - 后三种都需要口令。
- 读取约束：
  - 目录项数、目录字节、嵌套深度、名称和 extra 长度都有上限；
  - 成员范围不得越出文件；路径须通过安全检查，大小写折叠后不得重名；
  - 目录载荷必须恰好走完。
- ERISA-N 解码：
  - 纯 Python 实现，限制输出大小和步数；
  - 模型槽位溢出或码流提前结束都会报错，不返回不完整的数据；
  - 约 2 MB 输出需要数秒。
- 写出（`build_noa`）：
  - 只写扁平目录与 UTF-8 名称；
  - 新成员用 raw 存储；
  - 已有成员可经 `member_from_entry` 原样搬运，保留 ERISA-N 码流、时间与 extra；
  - 写完用 `read_index`/`read_stored` 重新读取，逐项比对。
- 不实现 ERISA-N 压缩，原因是编码器需要逆向自适应概率模型与区间编码，而上游没有可移植的实现。
- raw 写出的依据：同版本 NOA 中已有 raw 成员（语音包、图像包全是 raw），且读取路径按每条目录项的编码分派。即便如此，引擎是否接受 raw 剧本仍属**未验证运行时**。

## 挂载顺序与补丁
- `IDR_COTOMI` 的 `<archive>` 列表就是启动挂载表。已见方言中：
  - `patch2.noa`、`patch1.noa` 排在基础包之前；
  - 补丁包与列表中后面的包有同名成员，其中多数内容不同。
  - 由此推断同名成员按列表顺序先到先得。这一点未经运行验证。
- 挂载表是固定的，新增的 `patch3.noa` 不会被加载。可选做法有两种：
  - 用 `rebuild --base <列表中最靠前的补丁包>` 生成同名副本：原成员原样搬运，改动的 SRCXML 追加或替换进去；
  - 或让 `--base` 指向含剧本的原包，整包重封。
  - 部署时须先备份，并由用户授权替换。
- CSX 也会自行打开挂载表之外的包（`conststr` 中可见 `.noa` 名称）。`extract` 报告中的 `unlisted_archives` 会列出未在挂载表中的 NOA。
- 没有 `IDR_COTOMI` 时按文件名排序，不推断覆盖关系；可用 `--archive` 按优先级显式指定。

## 工作流命令
```text
python -X utf8 -m python.engines.entis_extract mounts "游戏目录/主程序.exe"
python -X utf8 -m python.engines.entis_extract extract "游戏目录" "游戏目录/游戏名_extract" --language JA
python -X utf8 -m python.engines.entis_extract rebuild "游戏目录/游戏名_extract" "新输出目录" --base "游戏目录/patch2.noa" [--target-language ZHTW]
python -X utf8 -m python.engines.entis_extract readback "游戏目录/游戏名_extract" "新输出目录/patch2.noa" "新回读目录"
python -X utf8 -m python.archives.entis_noa ls "游戏目录/script.noa"
python -X utf8 -m python.archives.entis_noa verify "游戏目录/script.noa"
```
- `extract`：
  - 按挂载顺序选出每个 `.srcxml` 的生效副本；
  - 写出 `gt_input/<脚本名>.json`、`original/<包名>/<成员>`、`metadata/<包名>/<成员>.json`（manifest）和 `reports/`；
  - 没有文本的成员只记入报告；
  - 每个成员都做一次恒等回写，要求逐字节一致。
- `rebuild`：
  - 用 manifest 校验 `gt_output` 中同名 JSON 的条数、字段、姓名策略和保护 token；
  - 写入 `--target-language` 槽位，默认与提取语言相同；
  - 目标语言与提取语言不同时，该文件的所有记录都写入目标槽位。目标槽位姓名为空或为变量时跳过姓名，并计入报告；
  - 读回新 NOA 逐条比对，再写出 `reports/rebuild.json`。
- `readback`：从新 NOA 重新导出 JSON，供与 `gt_output` 比对。
- 中文显示：SRCXML 为 UTF-8，不需要 JIS 替换。但启动 XML 可能指定预渲染的位图字体（`<fonts>` 中的 `.bmf`），简体字有没有字形须试注确认。

## 容器到剧本路线
1. 先按文件头区分资源容器与剧本，再按上文方法判断剧情在 SRCXML 还是 CSX。
2. 严格按 UTF-8 解码，明确提取语言与写回语言。
3. 方言文件走 `entis_srcxml`；严格 XML 文件也可用 `entis_gls`（语义往返，不保字节）。
4. 回写后按挂载规则生成补丁或重封包，并读回验证。
- CSX 走下面独立的容器路线，不与 XML 路线互相转换；改后缀不能把 CSX 变成 SRCXML。

## CSX 容器与 conststr 表
- 识别：文件前五字节 `Entis`，偏移 16 起 18 字节为 `Cotopha Image file`；两者缺一即拒绝。
- 头部固定 64 字节；之后是分块序列，每块为 8 字节 ASCII 名（其余补零）、`int64` 载荷长度、载荷。
- 遇到首字节为 0 的块名即结束目录，其后到文件尾是未解释的 trailer，重写时原样保留。
- 块名必须唯一；负长度或越界长度直接报错，不按剩余字节截断。
- 已知块：`conststr`（字符串常量表）与 `image`（CS 字节码）。
- `conststr` 载荷：`int32` 条数，每条为 `int32` 字符数、`chars*2` 字节 UTF-16LE、`int32` 附加数、附加数个 `int32`。
- 字符数为 0 的槽位是占位，不产生可写文本；其余槽位通过重建整个块支持变长新文本。
- `image` 载荷按操作码走：只解释有明确操作数形状的指令，未知操作码在指令边界处报错，不做重同步。
- 字符串字面量为 `uint32` 字符数；`0` 表示缺席，`0x80000000` 表示引用并跟一个 `int32`；其余为 UTF-16LE 字节。
- 走完必须正好落在载荷末尾，否则视为布局不符。
- 接口：`parse_chunks` / `build_csx` / `parse_conststr` / `rebuild_conststr` / `parse_image` / `patch_image`。
- 能力层级：`script-header-string-spans`。`conststr` 可增长；`image` 字面量定长，超长拒绝，短文本补 UTF-16 空格。
- 不做：其他块的语义、CS 求值、`image` 增长后的跳转重写、块顺序调整、NOA/DAT 归档。

```python
from python.archives.entis_csx import parse_conststr, rebuild_conststr, parse_image, patch_image

raw = open("script.csx", "rb").read()
entries = parse_conststr(raw)
patched = rebuild_conststr(raw, {0: "短い"})        # 块内变长
literals = parse_image(raw)
patched = patch_image(patched, {0: "短"})           # 段内定长
```

- 变长 `conststr` 会改变后续块偏移，但块目录按顺序重排，trailer 原样后移。
- `rebuild_conststr`、`patch_image` 返回新字节串，不修改输入，重新解析并逐条比对后才返回。

## 源码与算法对应
- 来源：`msg-tool`，GPL-3.0-or-later。
- 提交：`f72716cee88554d40c1cdface2812493b14ca653`。
- 路径：`src/scripts/entis_gls/srcxml.rs`。
- `SrcXmlScript::extract_messages` 对应 msg/select/menu 遍历与语言属性选择。
- `SrcXmlScript::import_messages` 对应定向修改 name/text 属性。
- Python 使用严格 XML，不采用 xml5ever 的错误恢复结果继续写回。
- Python 修正菜单先出现的语言探测，并拒绝多语言歧义。
- 不继承原实现可能忽略多余译文的问题；未知序号和字段都拒绝。

## Python 接口与示例
```python
from python.engines.entis_gls import extract_srcxml, patch_srcxml
xml = '<xscript><code><msg name_ja="A" text_ja="旧" text_en="old"/></code></xscript>'
records = extract_srcxml(xml, language='ja')
out = patch_srcxml(xml, {0: {'message': '新 & 文', 'name': 'B'}}, language='ja')
assert extract_srcxml(out, 'ja')[0].message == '新 & 文'
assert 'text_en="old"' in out
```
- `extract_srcxml(str, language=None) -> tuple[Message, ...]`。
- `patch_srcxml(str, {index: {'message': ..., 'name': ...}}, language=None) -> str`。
- Message 保存 kind、属性名、name_writable，而不是只留自由文案。
- 空改动直接返回原 str；有改动输出语义等价的 XML 字符串。

## name / message 映射
- msg.name 是本地姓名字段，menu 没有人名写入通道。
- 缺少 name 属性时 `name_writable=False`，拒绝凭上下文创建姓名。
- 多人名若原来就是属性内容，按原字符串保留，不自动拆成单人。
- 额外解析出的上下文名单应放公共 manifest，不能覆盖原属性模型。
- 每个 menu 是独立 choice；空 text 仍保留记录。
- 不翻译 voice、jump、ID、目标语言之外的属性或非目标节点文本。

## 回填、长度与控制码
- XML 属性转义由 ElementTree 完成，不手工替换 `&` 后二次转义。
- 允许合法 XML 字符；NUL、非法低控制字符、代理项等拒绝。
- 不处理 DTD/ENTITY；输入遇到这类声明即拒绝。
- 输出会规范化属性引号、实体拼写、自闭合元素等词法形式。
- 文档内部注释和处理指令保留；文档外声明不承诺逐字节保持。
- 未实现 SRCXML 到 CSX 编译，XML 本身没有二进制偏移表可修复。
- 返回前重新解析输出，检查 XML 结构与目标语言属性仍然成立。
- 调用层负责 XML 声明、文件编码和容器大小更新。

## 部署条件
- 先按上文方法确认游戏执行的是 SRCXML，还是只用编译后的 CSX。
- 如果只有 CSX 执行路线，可用 `conststr` 读写与 `image` 定长回写。但编译/反汇编仍不完整，不能声称已形成闭环。
- NOA 补丁按挂载表覆盖只是推断，需试注确认生效；替换原包前先备份。
- 替换后需验证正文、名字、选项、聊天标题和语言切换。
- 游戏自己的文本控制语法应原样保留在属性值中。
- 所有磁盘写入、manifest 与原文件保护由父 Skill 公共层完成。

## 验证与缺口
- `entis_gls` 合成测试：`tests/test_engines_primary.py` 中的 `EntisTests`。
  - 覆盖普通 msg/menu、空名空文、语言选择与其他语言保留；
  - 覆盖菜单先出现时的自动语言识别，以及 XML `&`/引号转义往返；
  - 覆盖注释保留，以及多语言歧义、缺属性、DTD 和非法字符的拒绝。
- CSX 合成测试见 [test_entis_csx.py](../tests/test_entis_csx.py)：
  - 覆盖块目录、`conststr` 变长往返、`image` 字面量定长回写；
  - 覆盖未知操作码与越界的拒绝。
- NOA / ERISA-N / 方言 / 工作流合成测试见 [test_entis_noa.py](../tests/test_entis_noa.py)：
  - 容器：扁平与嵌套目录、raw 与 ERISA-N 成员、校验不符、截断与预算；
  - 加密：BSHF 置换互逆，无口令与未知编码时拒绝；
  - 结构反例：越界、计数、标签、路径穿越、名称编码、重名；
  - 方言：转义、保字节回写、控制码与姓名策略；
  - 工作流：extract → rebuild → readback 闭环。
- ERISA-N 合成向量只固定了解码结果。解码器的正确性由真实归档的异或校验全部吻合来佐证（只读回归，样本未收入仓库）。
- CSX 来源为翻译肋手 v4.9D 的 `GameRes.EntisGLS.ArcCSX`（GARbro 派生）。本仓库独立改写为严格边界：未知操作码不重同步，整段必须精确走完。
- 真实样本只读回归已覆盖：
  - NOA 索引、ERISA-N 解码与校验；
  - SRCXML 方言解析与恒等回写；
  - 变长中文回写，以及打包后读回。
- 游戏显示与补丁加载均未验证。
- 不支持：ERISA-N 压缩写出、NOA 子目录写出、从 EXE 取口令、命名空间方言、CSX 其他块的语义、完整编译/反汇编。
- 32 MiB 字符串上限是参考防护，不代表所有生产环境的资源策略。
