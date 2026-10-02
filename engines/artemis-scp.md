# Artemis Engine：SCP 文本剧本（`.txt` / `.iet`）与 pf8 多分卷

## 能力边界

- 引擎 ID：`artemis-scp`。**容器与 `artemis`（ASB 树）同源**，但剧本方言、模块和解析器都不同，不要互相套用。
- 参考模块：[python/archives/pfs.py](../python/archives/pfs.py)（容器）、[python/engines/artemis_scp.py](../python/engines/artemis_scp.py)（剧本）。
- 容器：`pf0/pf2/pf6/pf8` 的索引读取、成员读取与 **pf0/pf2/pf6/pf8 写出**；pf8 载荷 XOR；多分卷命名空间合并与覆盖链。
- 剧本：`.txt` / `.iet` 的 SCP 文本解析、`name/message` 导出、受保护 token、可写人名回填。
- 不做：游戏启动、字体/字形、加载优先级实测、DSC 之类的外壳、`>1 GB` 单卷的流式重封包。

## 先排除三个身份陷阱

1. **目录名和厂商名不是引擎身份。** 本项目收件路径里同时出现过的目录名与厂商字符串，和引擎、品牌三方互不相干；`Copyright.txt` 里写明的是引擎（`Artemis Engine`，Copyright (C)2009 Daiju Hanaoka (Mikage)）。判断引擎要读 `Copyright.txt` / 引擎特征，不要读文件夹名。
2. **扩展名不决定方言。** `.pfs` 只是 Artemis 容器；`.txt` 不一定是文本，`.iet` 也不一定是 ASB。已有参考把 `.asb/.iet` 归为编译字节码，但在本族的实测样本里 `.iet` 是**纯文本 SCP**（`system/button.iet` 头两字节是 `//`）。一律先验内容。同一发行版还可以同时带第三种剧本：`.ast`（Lua 表文本，`astver = 2.0`），走 [artemis-ast](artemis-ast.md)，别用本页的行语法去读它。
3. **同名成员跨卷覆盖。** 同一个逻辑名可以同时存在于 `root.pfs` 和各 `root.pfs.NNN`，内容不同；按卷序解析才能拿到玩家实际看到的那一份。

## 识别证据

- 容器：文件头 `pf8`（或 `pf6`/`pf2`/`pf0`），第 4 字节起为 `u32 index_size`。
- 多分卷命名族：`root.pfs`、`root.pfs.000`…`root.pfs.012`（编号可以不连续，缺失 `005`–`009` 是正常的）。每卷都是**独立自洽**的归档，不是"索引在前卷、数据在后卷"的虚拟拼接。
- 剧本：UTF-8 文本，行首为 `//`、`;`、`*`、`#`、`[` 或普通文本；`[&scpsupport ...]`、`[&linetag ...]` 预处理指令与 `tag.ini` 是强特征。
- 采样实证（供对照，不是支持保证）：9 卷 / 40060 条记录 / 39458 个唯一名 / 586 处覆盖；剧本 144 个 `scenario/**/*.txt`，共 27638 条 `name/message`。

## 容器方言（pf8）

```text
"pf8" | u32 index_size | index
index[0..3] = u32 条目数
pf6/pf8 记录 = u32 name_len | name | u32 unknown | u32 offset | u32 size   （name_len + 16）
pf2     记录 = u32 name_len | name | 12 字节填充 | u32 offset | u32 size   （count 在 index+4）
pf0     记录 = 0x104 字节 ASCII 名 | u32 offset | u32 size                  （0x10c）
```

- 名称编码：实测样本为 **UTF-8**；`read_index` 默认自动判定（先 UTF-8 再 CP932），显式传入则严格单一编码。不要照抄"pf 系一律 CP932"的假设。
- pf8 载荷：`key = SHA1(index)`，`index` 是**声明的整个索引**（含尾部表），逐成员 `payload[i] ^= key[i % 20]`，每成员从 0 重新起算。
- **尾部附加表**：`index_size` 常大于条目表。实测样本的尾部是 `u32 计数(=条目数+1) + 计数×u64 + u32`，两个上游参考实现都忽略它。处理要点：
  - 不能因"索引有剩余字节"就拒绝整卷；
  - 它**必须计入 SHA-1**，否则 key 错误、载荷全成乱码；
  - 数值已解码（7 卷 / 32570 条目逐值核对）：`u64[i] = Σ(j≤i)(len(name_j)+16) − 8`，最后一个 `u64` 为 0，末尾 `u32 = 4 + Σ(len(name_j)+16)` 即记录区大小；也就是条目记录长度的累计表。那个 `−8` 仍是拟合值，重封包仍按原字节保留，不重算。
- `offset` 是 32 位、相对本卷起点；实测各卷 `max(offset+size) == 文件大小`（无空洞、无越界），因此按原偏移顺序重排可逐字节还原。
- 索引条目顺序**不等于**偏移顺序，重封包必须分别保留"记录顺序"和"物理顺序"。

## 剧本方言（SCP 文本）

```text
// 或 ;          注释（';' 会整行注释掉标签/指令，实测 349 行）
*label           标签
[tag attr="v"]   指令（只解释 tag 名与带引号的属性；']' 之后的 // 注释原样保留）
#name a,b        行标签（由 [&linetag prefix="#"] 注入），不是对白，必须跳过
（空行）          消息分隔
其它              对白或旁白文本行
```

- **消息 = 连续文本行的极大串。** 首行以 `「『（(` 开头 = 对白，否则旁白。
- **起始 `「` 与结尾 `」` 是结构字符**：译文丢掉起始引号，该条会重新解析成旁白（说话人归属丢失）。`patch_script` 会直接拒绝，不要绕过。
- 行内指令：`[ルビ rb="漢/かん"]`、`[恋人呼称 chara="…"]` 嵌在正文中间，必须作为受保护 token 原样保留。
- 换行 CRLF；文件可能是 UTF-8 无 BOM 或带 BOM（实测 144 个剧本里 17 个带 BOM）——带 BOM 却不按 `utf-8-sig` 解码，会把首行吃成一个假消息。

### 说话人判定（本族最容易错的一处）

按证据强度排序，`read_script` 就是这样实现的：

1. 命令带 `name="…"` → 该属性的值就是显示文本（`name_policy = "writable"`）。
2. 命令只有语音属性（`file`/`voice`）→ **tag 名就是角色键**（`name_policy = "context"`）。实测 `[幸枝 file="sachie_t023"]` 这类**没有 `name=` 属性**的命令占了绝大多数，只认 `name=` 会把 96% 的对白说错人。
3. 无属性的非 ASCII tag 且不是已声明指令 → **未知说话人**：清空上一位说话人，本条不给名字（`name_policy = "absent"`）。`[主人公]` 属于这类；它的显示名由引擎在运行时替换（玩家命名），脚本里没有字面量。需要时用 `speaker_tags={"主人公"}` 显式把它作为 `context` 名暴露出来。
4. 其余命令（`[背景 ...]`、`[イベントCG ...]`、`[画面シェイク ...]`、`[セーブタイトル ...]` 等）**不影响说话人**，否则会把旁白挂到"背景"名下。

说话人会持续到下一个说话人命令或未知说话人 tag。`tag.ini`（随包携带，实测位于 `root.pfs:tag.ini`）列出的是**指令**，用来排除 `[var name="…"]` 这类"带 name 属性但不是说话人"的命令；用法是 `TagSchema.parse(...)` 后传给 `tag_schema=`，不传则退回内置的 `{"var", "macro"}`。

## Python 接口与示例

容器（`read_index` 只读头/索引，不载入载荷，因此 `>1 GB` 的单卷也能只读索引）：

```python
from python.archives import pfs

paths = pfs.volume_paths("game/root.pfs")          # base + 同族 NNN，按卷序
read = [(p, pfs.read_index(p)) for p in paths]
index, resolved = read[-1][1], pfs.resolve_volumes([(p, i) for p, i in read])
member = resolved.by_name()["scenario/00/0001共通.txt"]   # 覆盖链在 member.overrides
with open(member.volume, "rb") as stream:
    raw = pfs.read_member(stream, index, member.entry).data
rebuilt = pfs.repack(index, {e.ordinal: pfs.read_member(stream, index, e).data
                             for e in index.entries})      # 未改动则逐字节一致
```

剧本（`Record.text` 用 `\n` 表示盒内换行，与 JSON 一致）：

```python
from python.engines import artemis_scp

script = artemis_scp.read_script(raw, tag_schema=None, speaker_tags={"主人公"})
rows = script.rows()                    # [{"name": ..., "message": ...}, {"message": ...}]
for locator, record in zip(script.locators(), script.records):
    print(locator["line_start"], record.tokens)          # 受保护 token
patched = script.patch(rows)            # 相同 rows 应得到相同字节
```

**用 `script.patch(rows)`，不要用 `patch_script(raw, rows)`。** 说话人策略（`tag_schema` /
`speaker_tags` / `command_tags`）决定每条记录有没有名字槽；回填时换了一套策略，结果会"看起来
通过"却把名字槽丢掉或错位。`Script.patch` 复用解析时的策略，`patch_script` 则需要调用者再传一遍；
漏传会以 `name_not_writable` 等明确错误拒绝，而不是静默写出。

配合 [交换契约](../guides/roundtrip-contract.md) 生成 manifest（`rows` / `locators` / `name_policies` / `protected_tokens` 都由 `Script` 提供），再用 `validate_translation` 校验译文，最后 `script.patch` 回填——与其它引擎相同的两步契约，没有额外的"工作流"概念。

## name / message 映射

- 对白：`name` 来自说话人命令；旁白：无 `name`。
- `name_policy` 三态：`writable`（命令自带 `name=`，可改写）、`context`（只有 tag 名/运行时名，**只作翻译提示，绝不写回**）、`absent`（无名）。
- `speaker_tag` 记录在 locator 里，即使 `name` 为 `absent` 也保留，便于人工核对与后续补表。
- 同一条说话人命令被多条记录引用时，译文给不同名字 → 拒绝（`shared_name_conflict`），不能默认后者覆盖前者。

## 回填、长度与控制码

- 只改文本行与 `writable` 的 `name=` 属性值；标签、指令、注释、行标签一律不动。
- 禁止在译文中出现行首 `[`/`//`/`;`/`#`/`*`、嵌入 `\r`、尾部换行、空消息——它们会改变记录边界，`patch_script` 逐条拒绝。
- 回填后重新解析并核对：记录数、每条 kind/行号区间、消息文本、`writable` 人名一致。
- 重新编码保持原编码与 BOM 状态（`encode_script`）。

## 部署条件与未验证项

- **多分卷覆盖顺序为静态推断**：实测 `root.pfs` 与 `root.pfs.010` 的同名剧本内容不同，`.010` 含明显校对修正（如 `ほぐした方がじゃないれふかぁ` → `…いいんじゃない…`），据此按"后卷覆盖前卷"解析；**未在游戏中实机确认**加载顺序。
- 容器重封包只证明"容器自洽"：已验证恒等重封包逐字节一致，以及替换成员后重新解析通过；**没有**验证游戏会加载新卷。
- 尾部附加表的数值已解码（见“容器方言（pf8）”一节），但重封包仍按原字节保留、不重算；若游戏拒绝重封包，先怀疑这里。
- 单卷重封包在内存中进行：实测 630 MB 卷可恒等重建，`1 GB` 以上需要提高预算或等流式 writer。
- 未做字体/字形、存档、选择肢排版与游戏启动验证；译文能否显示取决于字体与编码，本页不承诺。

## 源码与算法对应

- 容器：[python/archives/pfs.py](../python/archives/pfs.py)。来源 GARbro-Mod `ArcFormats/Artemis/ArcPFS.cs`（MIT，commit `bc26d991ef5cdc0e1ecb32122ee9a48c3375750c`）与 msg-tool `src/scripts/artemis/archive/pfs.rs`（GPL-3.0-or-later，commit `f72716c…`）。`read_index`/`read_member` 对应 `OpenPf`；`build`/`repack` 为新增 writer（上游只有 reader）。
- 剧本：[python/engines/artemis_scp.py](../python/engines/artemis_scp.py)。行语法与说话人处理参照 msg-tool `src/scripts/artemis/txt.rs`、`src/scripts/artemis/panmimisoft/txt.rs`（GPL-3.0-or-later），并按实测样本收紧：`;` 整行注释、无 `name=` 的语音 tag、未知说话人清空、引号为结构字符。msg-tool 的 `;>>` 规则与"非 ASCII tag 即说话人"在本样本上会误判，未照搬。
- `tag.ini` 语义：`[tag]` 段 + `0=attr` 属性顺序表，用于区分指令与角色 tag。

## 验证与缺口

- 合成测试见 [tests/test_archives.py](../tests/test_archives.py) 的 `PFSTests` 与 [tests/test_engines_artemis_scp.py](../tests/test_engines_artemis_scp.py)。
- 真实语料只读运行：144 个剧本 → 27638 条；**空改动往返 144/144 逐字节一致**；恒等重封包在 `root.pfs`(8.6 MB)、`.001`(666 MB)、`.004`、`.010`(630 MB)、`.011`、`.012` 上**逐字节一致**。
- 缺口：`>1 GB` 卷（`.000`/`.002`/`.003`）无流式 writer；尾部表数值已知但 `-8` 常数与用途未解释；卷序未实机验证；`.iet` 里的系统 UI 文本（`[dialog message=…]` 等）未纳入 `name/message` 导出。另一种是 `.ast` Lua 表剧本，见 [artemis-ast](artemis-ast.md)。
