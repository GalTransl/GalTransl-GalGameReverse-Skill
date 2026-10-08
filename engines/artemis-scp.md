# Artemis Engine：SCP 文本剧本（`.txt` / `.iet`）与 pf8 多分卷

## 能力边界

- 引擎 ID：`artemis-scp`。**容器与 `artemis`（ASB 树）同源**，但剧本方言、模块和解析器都不同，不要互相套用。
- 参考模块：[python/archives/pfs.py](../python/archives/pfs.py)（容器）、[python/engines/artemis_scp.py](../python/engines/artemis_scp.py)（剧本）。
- 容器：`pf0/pf2/pf6/pf8` 的索引读取、成员读取与 **pf0/pf2/pf6/pf8 写出**；pf8 载荷 XOR；多分卷命名空间合并与覆盖链。
- 剧本：`.txt` / `.iet` 的 SCP 文本解析、`name/message` 导出、受保护 token、可写人名回填。
- 不做：游戏启动、字体/字形、加载优先级实测、DSC 之类的外壳、`>1 GB` 单卷的流式重封包。

## 先排除三个身份陷阱

1. **目录名和厂商名不是引擎身份。** 核对引擎标识、资源头及 `Copyright.txt`，不根据安装目录名选择格式。
2. **扩展名不决定方言。** `.iet` 可能是 SCP 文本；ASB 必须核对二进制头。同一发行版也可包含 Lua 表形式的 `.ast`，见 [artemis-ast](artemis-ast.md)。
3. **同名成员跨卷覆盖。** 同一个逻辑名可以同时存在于 `root.pfs` 和各 `root.pfs.NNN`，内容不同；按卷序解析才能拿到玩家实际看到的那一份。

## 识别证据

- 容器：文件头 `pf8`（或 `pf6`/`pf2`/`pf0`），第 4 字节起为 `u32 index_size`。
- 多分卷命名族：`root.pfs`、`root.pfs.000`…`root.pfs.012`（编号可以不连续）。每卷都是**独立自洽**的归档，不是"索引在前卷、数据在后卷"的虚拟拼接。
- 剧本：UTF-8 文本，行首为 `//`、`;`、`*`、`#`、`[` 或普通文本；`[&scpsupport ...]`、`[&linetag ...]` 预处理指令与 `tag.ini` 是强特征。

## 容器方言（pf8）

```text
"pf8" | u32 index_size | index
index[0..3] = u32 条目数
pf6/pf8 记录 = u32 name_len | name | u32 unknown | u32 offset | u32 size   （name_len + 16）
pf2     记录 = u32 name_len | name | 12 字节填充 | u32 offset | u32 size   （count 在 index+4）
pf0     记录 = 0x104 字节 ASCII 名 | u32 offset | u32 size                  （0x10c）
```

- 名称编码可能是 UTF-8 或 CP932；`read_index` 默认自动判定（先 UTF-8 再 CP932），显式传入则严格单一编码。不要照抄"pf 系一律 CP932"的假设。
- pf8 载荷：`key = SHA1(index)`，`index` 是**声明的整个索引**（含尾部表），逐成员 `payload[i] ^= key[i % 20]`，每成员从 0 重新起算。
- **尾部附加表**：`index_size` 可能大于条目表。已知布局为 `u32 计数(=条目数+1) + 计数×u64 + u32`，须先核对目标布局：
  - 不能因"索引有剩余字节"就拒绝整卷；
  - 它**必须计入 SHA-1**，否则 key 错误、载荷全成乱码；
  - 附加表存在累计记录长度的布局：`u64[i] = Σ(j≤i)(len(name_j)+16) − 8`，末项为 0，末尾 `u32 = 4 + Σ(len(name_j)+16)`。其中 `−8` 的用途未确认，不作为通用公式；writer 保留原表，不重算。
- `offset` 是相对本卷起点的 32 位偏移。读取须检查越界和重叠，重封包按实际物理顺序处理，不能假设无空洞。
- 索引条目顺序**不等于**偏移顺序，重封包必须分别保留"记录顺序"和"物理顺序"。

## 剧本方言（SCP 文本）

```text
// 或 ;          注释（';' 会整行注释掉标签/指令）
*label           标签
[tag attr="v"]   指令（只解释 tag 名与带引号的属性；']' 之后的 // 注释原样保留）
#name a,b        行标签（由 [&linetag prefix="#"] 注入），不是对白，必须跳过
（空行）          消息分隔
其它              对白或旁白文本行
```

- **消息 = 连续文本行的极大串。** 首行以 `「『（(` 开头 = 对白，否则旁白。
- **起始 `「` 与结尾 `」` 是结构字符**：译文丢掉起始引号，该条会重新解析成旁白（说话人归属丢失）。`patch_script` 会直接拒绝，不要绕过。
- 行内指令：`[ルビ rb="漢/かん"]`、`[恋人呼称 chara="…"]` 嵌在正文中间，必须作为受保护 token 原样保留。
- 换行 CRLF；文件可能是 UTF-8 无 BOM 或带 BOM——带 BOM 却不按 `utf-8-sig` 解码，会把首行吃成一个假消息。

### 说话人判定（本族最容易错的一处）

按证据强度排序，`read_script` 就是这样实现的：

1. 命令带 `name="…"` → 该属性的值就是显示文本（`name_policy = "writable"`）。
2. 非 ASCII 角色命令只有语音属性（`file`/`voice`）→ tag 名作为原始姓名，默认 `writable`；译名通过新增 `name="…"` 覆盖显示，角色 tag 和语音参数保持不变。
3. 无属性的非 ASCII tag 且不是已声明指令 → **未知说话人**：清空上一位说话人，本条不给名字（`name_policy = "absent"`）。仅凭裸 tag 无法区分角色、运行时姓名与指令；确认该 tag 支持显示名属性后，用 `speaker_tags={"角色标识"}` 显式启用显示名回注。不能把全部未知 tag 自动视为角色。
4. 其余命令（`[背景 ...]`、`[イベントCG ...]`、`[画面シェイク ...]`、`[セーブタイトル ...]` 等）**不影响说话人**，否则会把旁白挂到"背景"名下。

说话人会持续到下一个说话人命令或未知说话人 tag。游戏中的 `tag.ini`列出的是**指令**，用来排除 `[var name="…"]` 这类"带 name 属性但不是说话人"的命令；用法是 `TagSchema.parse(...)` 后传给 `tag_schema=`，不传则退回内置的 `{"var", "macro"}`。

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

script = artemis_scp.read_script(raw, tag_schema=None, speaker_tags={"角色标识"})
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
- `name_policy` 三态：`writable`（已识别角色命令，可修改或新增显示 `name=`）、`context`（`$` 开头的变量姓名，只作提示）、`absent`（旁白或未确认角色）。原文姓名不变时保留原命令字节，不额外添加属性。
- `speaker_tag` 记录在 locator 里，即使 `name` 为 `absent` 也保留，便于人工核对与后续补表。
- 同一条说话人命令被多条记录引用时，译文给不同名字 → 拒绝（`shared_name_conflict`），不能默认后者覆盖前者。

## 回填、长度与控制码

- 只改文本行与 `writable` 的显示 `name=`；属性缺失时在角色命令的闭括号前新增，原 tag、其他参数和尾部注释保留。重复属性、未闭合命令或引号拒绝。
- 禁止在译文中出现行首 `[`/`//`/`;`/`#`/`*`、嵌入 `\r`、尾部换行、空消息——它们会改变记录边界，`patch_script` 逐条拒绝。
- 回填后重新解析并核对：记录数、每条 kind/行号区间、消息文本、`writable` 人名一致。
- 重新编码保持原编码与 BOM 状态（`encode_script`）。

## 部署条件与未验证项

- 多分卷按后卷覆盖前卷解析，补丁制作见 [PFS 覆盖卷](artemis.md#打包技巧新增-pfs-覆盖卷)；须通过少量试注确认目标发行版实际加载顺序。
- 容器重封包须验证恒等重建、变长替换及重新解析；通过不代表游戏会加载新卷。
- 尾部附加表的数值已解码（见“容器方言（pf8）”一节），但重封包仍按原字节保留、不重算；若游戏拒绝重封包，先怀疑这里。
- 单卷重封包在内存中进行；大包先核对内存预算，当前无流式 writer。
- 未做字体/字形、存档、选择肢排版与游戏启动验证；译文能否显示取决于字体与编码，本页不承诺。

## 源码与算法对应

- 容器：[pfs.py](../python/archives/pfs.py)，格式来源 GARbro-Mod（MIT）与 msg-tool（GPL-3.0-or-later），许可通知见 [NOTICE](../provenance/NOTICE.md)。
- 剧本：[artemis_scp.py](../python/engines/artemis_scp.py)，行语法来源 msg-tool（GPL-3.0-or-later）；`;` 整行注释、语音 tag 姓名、未知说话人清空及引号结构按本页规则处理。
- `tag.ini` 语义：`[tag]` 段 + `0=attr` 属性顺序表，用于区分指令与角色 tag。
- 显示名新增规则与 msg-tool 的 `set_attr("name", ...)` 一致，来源见 [文本字段来源](../provenance/common-text-fields.json)。

## 验证与缺口

- 合成测试见 [tests/test_archives.py](../tests/test_archives.py) 的 `PFSTests` 与 [tests/test_engines_artemis_scp.py](../tests/test_engines_artemis_scp.py)。
- 缺口：`>1 GB` 卷无流式 writer；尾部表数值已知但 `-8` 常数与用途未解释；卷序未实机验证；`.iet` 里的系统 UI 文本（`[dialog message=…]` 等）未纳入 `name/message` 导出。另一种是 `.ast` Lua 表剧本，见 [artemis-ast](artemis-ast.md)。
