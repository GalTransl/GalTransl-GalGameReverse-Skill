# Escu:de：ESC-ARC2、分离消息文件与 ESCR1_00

## 先按内层签名分流

| 解包后证据 | 路线 |
|---|---|
| `@code:__` 的 `.bin` + 同名 `@mess:__` 的 `.001` | [分离消息格式与 Haison 实测](#haison-分离消息格式)：标准 CP932、消息池 XOR `0x55`、字节码对白/选项引用、mdb 人物表；**不要套用下文 ESCR 的特殊字符映射**。 |
| `ESCR1_00` | [下文 ESCR1_00 字符串池算法](#escr1_00)；VM 语义和 enum 姓名仍需另行证明。 |
| `ESC-ARC2` | [容器模块](../python/archives/escude.py) 的 `read_index` → 校验成员路径 → `probe_member/read_member`。只读索引不加载大图片/音频；`acp\0` 成员有界解压后再识别内层。 |

`ESC-ARC2` 并不保证内层一定是 ESCR。2026-10-01 对《廃村少女 ～妖し惑ひの籠の郷～》实测发现的是分离消息方言，具体证据、限制、产物接口和测试见本页的 Haison 分离消息格式一节。两种脚本方言的能力边界分别说明。

## ESCR1_00

### 能力边界
- 引擎 ID：`escude`。
- 参考模块：[python/engines/escude.py](../python/engines/escude.py)。
- 实现 ESCR1_00 规范字符串池读取、偏移重算与源码特有字符转换。
- VM bytes 与未知字段保留，不解释任意指令或自行推断姓名。
- ESCR 模块不包含 enum script 的完整分析；容器索引解密和 LZW 在上面的独立容器模块中。

### 识别证据
- 剧本强签名为八字节 `ESCR1_00`。
- `.bin` 同时可能是资源包、列表文件或其他数据，不能只按后缀认定。
- 容器 `ESC-ARC` 与剧本 `ESCR1_00` 是不同结构。
- 要校验字符串数量、偏移表、VM 大小及字符串终止位置。
- 每个偏移必须符合本文规范的顺序字符串池布局。
- 未知间隙、共享偏移或尾部数据在本子集中拒绝。

### 格式方言
- 签名后 u32 stringCount，再后面 stringCount 个 u32 字符串池相对偏移。
- 接着是 u32 vmLength、vmLength 字节 VM、一个 u32 unknown。
- 剩余部分为按索引顺序排列的 NUL 结尾字符串。
- 空字符串仍占一个 NUL，不能从记录列表中移除。
- msg-tool reader 会顺序读字符串；Python 还逐个核对索引值。
- 原字符串可使用 Escude 特殊单字节字符映射，不等于标准 CP932 解码。
- `<r>` 为源码中使用的正文换行标记。

### 容器到剧本路线
1. 若文件是 ESC-ARC2，先用随包容器模块解码，而非直接解析剧本；ESC-ARC1 当前不支持。
2. 参考 `msg-tool/src/scripts/escude/archive.rs`、`crypto.rs`、`lzw.rs`。
3. GARbro-Mod `ArcFormats/Escude/ArcBIN.cs` 也提供容器识别线索。
4. 提取 ESCR1_00 成员，保存 VM、字符串索引及原始 bytes。
5. 需要姓名上下文时，再单独获取同版本 enum script 并证明映射。
- 模块不自动读取 enum 文件或依赖任何原工具安装。

### 源码与算法对应
- 来源：`msg-tool`，GPL-3.0-or-later。
- 提交：`f72716cee88554d40c1cdface2812493b14ca653`。
- 路径：`src/scripts/escude/script.rs`。
- `EscudeBinScript::new` 对应 VM/unknown/字符串池拆分。
- `import_messages` 对应偏移重算、保留 VM 与 `<r>` 编码。
- `StrReplacer::new/replace` 对应 `!/?/A0..DE` 的自定义字符转换。
- 转换按单/双字节字符边界进行，不能全局替换相同字节值。
- 不移植源码里的游戏专用 CustomOps；参考保持通用并明示上下文不足。

### Python 接口与示例
```python
from python.engines.escude import read_escr, extract_escr, patch_escr, decode_engine_string
assert decode_engine_string(b'!?\xa0') == '！？　'
records = extract_escr(data, context_names={0: ('Alice', 'Bob')})
assert records[0].name_writable is False
changed = patch_escr(data, {0: '新正文\n下一行'})
assert read_escr(changed).strings[0].endswith('下一行'.encode('cp932'))
```
- `read_escr(bytes) -> Script(vm, unknown, strings)`，strings 是原 bytes。
- `extract_escr(bytes, context_names=None) -> tuple[Message, ...]`。
- `patch_escr(bytes, {原索引: str}, encoding='cp932') -> bytes`。
- 特殊字符解码单独暴露，便于测试与区分原生编码方言。

### name / message 映射
- 字符串池本身没有统一可写姓名字段。
- msg-tool 会通过 enum script 和 VM 状态补充姓名，但 import 不写这些姓名。
- 因此 Python 的外部 context_names 明确只读。
- 每条记录保留 `names: tuple[str, ...]`，支持多人名不被覆盖。
- 没有提供姓名上下文时返回空 tuple，不伪造一个名字。
- 空正文和全部原索引保持不变，不改变 VM 的字符串索引语义。
- 同一池里可能有非正文字符串，批准翻译范围仍需上层证据。

### 回填、长度与偏移
- 原字符串个数保持不变，避免 VM 中 string index 全部失效。
- 只对指定索引严格编码；未改字符串直接复制原 bytes。
- 每条新偏移等于此前字符串字节长度加各自 NUL 的总和。
- VM bytes 和 unknown u32 原样复制。
- 换行统一变为 `<r>`；不改变其他控制标记或脚本变量。
- 不做反向半角/特殊字符压缩，匹配 msg-tool 的普通编码写出路线。
- 嵌入 NUL、非 cstring 编码、越界索引和 u32 池长度溢出拒绝。
- 未认识的池布局拒绝，不通过忽略偏移表强行继续。

### 部署条件
- 确认该引擎版本允许普通 CP932 编码后的新文字。
- 字体与自定义单字节字符表可能影响标点和假名显示，需专门验证。
- 姓名定义要在真正的 enum/定义文件中改，而不是假装这里可写。
- 容器压缩、加密及成员索引需要独立的完整写回方案。
- 公共层负责原包只读、输出路径、manifest 和事务写出。

### 验证与缺口
- 合成测试验证池增长后全部偏移、空串、VM 与 unknown 字段保留。
- 覆盖特殊单字节映射及双字节字符不误改。
- 验证多人名上下文保留且只读。
- 覆盖非规范池偏移和 NUL 注入拒绝。
- 测试位置：`tests/test_engines_primary.py` 中 `EscudeTests`。
- 本 ESCR 路线未实现全量 VM、enum 解析、专用 CustomOps 与容器回封。
- 不声称池中每条字符串必然是玩家可见正文。
- ESCR 路线只有合成验证；分离消息方言的真实只读/往返验证见下文 Haison 分离消息格式。未做游戏运行验证。

## Haison 分离消息格式

适用证据为 `ESC-ARC2` 归档内同名 `.bin` / `.001`，分别以 `@code:__` / `@mess:__` 开头；只看到 `.bin` 不足以选择此路线。这里的字节码 profile 来自《廃村少女 ～妖し惑ひの籠の郷～》，其他版本需要先核对指令和原生过程表。

### 随包模块与实际范围

- [archives/escude.py](../python/archives/escude.py)：ESC-ARC2 流式索引、有限头部探测、按成员读取、acp LZW 解码与基于原包模板的重封包。不支持 ESC-ARC1。
- [engines/escude_mess.py](../python/engines/escude_mess.py)：消息池读写、完整指令边界扫描、消息/选项引用覆盖核对、显式姓名上下文与控制码保护。`REFERENCE = escude-mess-haison/1`。
- [engines/escude_mdb.py](../python/engines/escude_mdb.py)：Escu:de `mdb\0` 分表读取、人物表解析；不是 Access 数据库，无数据库 writer。
- [合成测试](../tests/test_engines_escude.py)：索引/解压预算、重叠 LZW 引用、错误拒绝、变长池、分支与姓名、控制码和数据库边界。

所有模块只依赖标准库，输入/输出均为流或 bytes，不读取用户目录，不执行游戏代码。外部项目只作为开发期资料。

### ESC-ARC2 与 acp

头为八字节 `ESC-ARC2`；`0x08` 是 u32 seed，`0x0c` 和 `0x10` 是加密的成员数、名称表字节数；随后每成员三个加密 u32：名称表偏移、文件绝对偏移、存储长度。**只有这段 u32 索引加密，名称表是普通 CP932**。密钥按 u32 溢出生成，种子先 XOR `0x65AC9365`，再组合左右移位；见 `_next_key`。

先 `read_index(stream)`，使用公共 `validate_names` 校验全部名称，再读取选中成员。返回的 `index_sha256` 只覆盖头/索引/名称表，不能代替归档或成员 SHA-256。默认最多 100,000 成员、16 MiB 索引；成员默认 64 MiB 存储/解码预算。批量调用还需检查累计解码长度。

`acp\0` 后是**大端** u32 解码长度及 MSB 位流。初始 9 位；`0x100` 结束，`0x101` 增宽，`0x102` 重置。字典记录每个输出 token 的起点，引用长度为相邻起点差加一，复制可重叠。拒绝提前结束、无结束码、未知尾部、越界引用和输出超长；不会沿用上游的零填充或 `min` 截断成功行为。本游戏全部目标成员通过这个严格实现。

### 消息与代码的配对布局

所有结构字段均为小端 u32，只有 acp 的长度例外。

| 格式 | 布局 |
|---|---|
| `@mess:__` | magic，count，poolSize，count 个池相对偏移，poolSize 字节消息池 |
| `@code:__` | magic，codeSize，textCount，textSize，messCount，代码，textCount 个偏移，内部文本池 |

消息池**整体 XOR `0x55`，包括字符串的 NUL**；索引和 count 不 XOR。先解密，再查终止符，不能在密文中搜索 NUL。已验证子集要求每个偏移正好接续上一条 NUL，拒绝别名、间隙、乱序及未知尾部。代码头的 `messCount` 必须等于同名消息文件 count。

`.001` 使用普通 CP932；`!?`、半角片假名都按普通 CP932 保留。旧 ESCR 的 `decode_engine_string` 会改变这些字符，不能复用。`@code` 的内部字符串区与 `.001` 消息区是两个独立池，不可混合导出。

Haison 指令是 u8 opcode 加固定个数 i32 操作数，显式支持 1..45。核心定位：`40=NAME`（人物行号），`41=TEXT`（消息索引），`42=PAGE`，`43=OPTION`（消息索引、代码跳转地址），`45=LINE`（源脚本行号）。扫描全部代码，不按字节搜 `0x29`；所有跳转、调用与选项目标必须落到已解析指令边界。

`extract_pair` 要求 TEXT/OPTION 的引用顺序恰好等于消息池索引顺序，每项恰好引用一次。遇到未引用、重复引用、次序差异、`PUSH_MESS` 间接消费、未知 opcode/native、消息数不匹配时拒绝当前成员，不能只导出已解析的前半段。它不沿某次游戏执行路径收集文本，因此不会漏掉另一条选择分支。

### 姓名上下文与限制

`data.bin/db_scripts.bin` 内 `mdb\0` 数据按表顺序存储：u32 头长；表名池偏移、列数和每列 `(u16 kind, u16 width, u32 列名偏移)`；u32 行数据字节数及行数据；u32 字符串池字节数及池。文件只在末尾用 u32 零结束。当前支持整数列 `kind=1`（1/2/4 字节）、字符串偏移列 `kind=4,width=4`。

`read_names` 严格匹配“登場人物”表及“名前/文字色/キャラID/音声グループ/顔画像”列。NAME 操作数对应**行号**，不是“キャラID”；后者是图片关联，同一个图片 ID 可有多个显示名。“？？？”保持匿名，不能按角色图片解出真名。像“甲＆乙”的显示名本来就是数据库的一个字段，保留为单个 `name`，不擅自拆分。

导出姓名是 `context`，`.001` writer 不修改人物表。规则是 NAME 指令形成显式姓名证据，允许跨越已核对的 CV 原生过程 30、整数参数与清栈/行号指令。连续 TEXT 无 PAGE 时保留该姓名；若中间调用辅助函数，只有其所有静态分支及被调函数均只做已确认不改姓名的操作时才保留。这样本样本的 8 条无 PAGE 连续对白不会丢失说话人。

PAGE、分支合流或不能证明的调用结束局部姓名证据。**这不是全游戏状态模拟**：运行时 frame=0 的 PAGE 可能保留姓名，跨脚本或动态状态也可能继承姓名；缺乏显式证据时返回无姓名，不把它强称为旁白。其他游戏若依赖这些语义，应扩展 profile 和验证，不能直接宣称姓名完整。动态 `%{...}` 姓名当前拒绝。记录中保留 `name_id`、`name_offset`、`code_offset` 和源 `line` 供核对。

### 提取与交接

在 skill 根目录可直接运行专用批处理入口（只依赖标准库）：

```text
python -m python.engines.escude_extract "游戏目录" "新的输出目录"
```

[escude_extract.py](../python/engines/escude_extract.py) 只读取根目录的 `script.bin`、`data.bin`，不递归扫描旧 `_extract`，不载入图片、音频包或汉化 PK02。这是上述 Haison profile 的入口，不是所有 Escu:de 游戏的自动适配器。目标必须不存在；已有结果时另选新目录，绝不覆盖。每个源包上限 8 MiB、成员解码上限 16 MiB、累计解码上限 128 MiB；更大的其他游戏应先核对格式和预算。

入口校验整个脚本包的类型、配对、代码边界、消息引用和人物表，逐文件执行原文及变长回填测试，全部通过后才用 `write_new_tree` 发布。遗漏配对、未知成员及平铺文件名冲突会拒绝本次发布，不能把部分结果宣称完整；发生重名时需补充带归档/成员序号的映射后重试。原包与成员、三份配套源 manifest、每个输出映射及本次统计一起保存到新目录。报告不复用旧提取目录里的测试数或统计常量。

使用主 skill 约定的新 `<游戏名>_extract/`，先验证再发布；脚本成员名用于平铺文件名，例如 `gt_input/a_prologue_01_01.json`。本游戏也有 `staff\\s01_kagome.001`：原件和 manifest 路径先把反斜杠规范为 `/`，翻译文件取 basename 成为 `gt_input/s01_kagome.json`，保留映射并检查名称冲突，不能把 staff 子目录带入翻译目录。把 `.001` 和 `.bin` 原 bytes 都保存在 `original/script/`，人物库保存在 `original/data/db_scripts.bin`。零消息的 `.bin` 标记 `empty`，保留原件和报告，不放空 JSON 到翻译目录。

核心调用（批量命名、预算、事务输出由调用者处理）：

```python
from python.archives.escude import read_index, read_member
from python.engines.escude_mdb import read_names
from python.engines.escude_mess import extract_pair, patch_mess, protected_tokens, REFERENCE
from python.common.safety import validate_names
from python.common.contract import make_manifest, validate_translation

# stream 是调用者已打开的归档；大媒体归档只读索引，不批量载入。
index = read_index(stream)
validate_names([entry.name for entry in index.entries])
# 对选定的 db_scripts.bin / 同名 .bin / .001 调用 read_member。
names = read_names(database_bytes)
records = extract_pair(code_bytes, message_bytes, names=names)
rows = [dict(message=r.message, **({"name": r.name} if r.name is not None else {}))
        for r in records]
locators = [{"kind": r.kind, "pool_index": r.index,
             "code_offset": r.code_offset, "source_line": r.line,
             "name_id": r.name_id, "name_offset": r.name_offset} for r in records]
sources = {"original/script/example.bin": code_bytes,
           "original/script/example.001": message_bytes,
           "original/data/db_scripts.bin": database_bytes}
manifest = make_manifest(
    engine="escude", variant="haison-code-mess", reference=REFERENCE,
    sources=sources, rows=rows, locators=locators, encoding="cp932",
    protected_tokens=[list(dict.fromkeys(protected_tokens(r.message))) for r in records],
)
checked = validate_translation(manifest, sources, rows, rows)
rebuilt = patch_mess(message_bytes, {r.index: row["message"]
                                   for r, row in zip(records, checked)})
assert rebuilt == message_bytes
```

必须保存归档 SHA-256、成员 ordinal/name/offset/stored-size、解码 SHA-256及配对关系。`metadata/` 中用公共 manifest 记录三份配套源哈希和真实 locator。回填前重解析原始文件核对 locator，不信任 sidecar 中任意偏移。

`gt_input/` 可以直接导入 GalTransl；译文回到 `gt_output/`，保持文件名、条数、数组顺序和姓名上下文字段。JSON 中保留字面 `<r>`、ruby/font 标签及其属性；译文不新增、删改或重排这些标签。此版本保守地保留 ruby 读音属性，若要翻译读音或去除 ruby，应单独设计可逆规则。不要把 `<r>` 换为物理换行。

### 回填保证与部署边界

`patch_mess` 严格编码指定槽，重建所有偏移和 poolSize，再恢复 XOR。原文相同的槽保留原 bytes；不增删池项，不改 `.bin`，因此代码跳转及消息索引不需重定位。输出后再次解析并验证译文、原始代码哈希和未改槽。

原文可逐字节往返；变长 CP932 译文通过结构检查。当前 writer 只接受 CP932，中文字符不一定可表示，不能用 `errors='replace'`。原生中文显示、字体、其他编码、松散文件优先级和补丁加载均未验证。已有汉化的 `haison_cn.pk2` 是独立 `PK02` 资源，本次提取与重封的是原版 `script.bin` 日文，不能称为汉化补丁中文提取，也不能假定汉化启动器会优先加载新的原版脚本包。

### 从 gt_output 回填并重封 script.bin

使用 [escude_pack.py](../python/engines/escude_pack.py)，可直接读取上述入口生成的工作区（包括已有 schema `escude-haison-extraction/2` 的结果）：

```text
python -m python.engines.escude_pack "提取工作区" "新的打包输出目录"
```

输出目录的父目录必须存在、目标必须不存在。入口读取工作区 `gt_output/` 的同名 JSON，缺少译文的剧本仍经过原文 parser/writer 校验；不认识的文件名拒绝，`.keep` 可忽略。所有译文必须保留数组顺序、姓名上下文与控制标签。输出 `script.bin` 和 `verification.json`，不会安装、替换游戏文件或处理 PK02 汉化补丁。

回填前在临时目录重新解析工作区保存的两个原始归档，核对报告、全部已保存成员、原文 JSON 和重新生成的完整 manifest。这样不依赖可编辑 sidecar 中的地址，也不会静默忽略人物库或零消息代码文件的变化。译文逐条通过 CP932、姓名、控制码与池索引检查，回填后重新解析配对代码，比较消息与非文本绑定。最终新归档的全部成员再次解包核对。

容器 writer `repack(template, replacements)` 的键为规范化 `/` 成员名，值为解码后的完整 bytes。保持原始 seed、名称表字节、成员顺序以及未改成员的压缩字节；更新变更成员及后续成员的长度/偏移，并按原密钥序列加密索引。支持按索引顺序连续存放的非空成员；有间隙、乱序、未知尾部的模板拒绝，不猜测填充用途。改变的 acp 成员使用 9-bit literal 编码，每 `0x8800` 个 literal 插入字典重置，结尾写结束码和零填充；包会变大，但解码结构不变。原文未变化时仍重建索引，并保留原压缩成员，结果逐字节相同。

诊断用全量变长测试（忽略 `gt_output`，为所有原文加上 `検証：` 前缀，不用于翻译交付）：

```text
python -m python.engines.escude_pack "提取工作区" "新的测试包目录" --verify-edits
```

### 2026-10-01 实测与出处

- 输入原版 `script.bin`：527 个成员，269 个代码文件、258 个消息文件；解压、全部字节码边界与消息引用检查无失败。11 个代码文件无消息。
- 258 个非空 JSON，共 33,014 条：32,966 条 TEXT、48 条 OPTION；其中包括 staff 下的 164 条留言。19,128 条带人物表姓名上下文（19,120 个 NAME 加 8 条无 PAGE 续句）。114 个人物表槽保留匿名和组合名。
- 全部 258 个消息文件通过 parser/writer 原文往返，逐字节一致；每份还通过首条消息加长的回填/重解析测试，其他槽、姓名与代码引用不变，不修改游戏。落盘后再次核对全部 JSON、manifest 和源哈希。
- 本次全库 518 项测试通过（1 项跳过），其中新增 Escu:de 测试 18 项；`tools/check_skill.py` 通过。`skill-creator/quick_validate.py` 因本机缺少可选 PyYAML 未能运行，未为此安装额外依赖。
- 容器源码依据：msg-tool `src/scripts/escude/{archive,crypto,lzw}.rs`，提交 `f72716cee88554d40c1cdface2812493b14ca653`，GPL-3.0-or-later；修改为标准库 Python，并加入边界/预算/严格结束校验。[许可与来源](../provenance/NOTICE.md)。GARbro-Mod `ArcFormats/Escude/ArcBIN.cs`（提交 `bc26d991ef5cdc0e1ecb32122ee9a48c3375750c`）只用于交叉核对 V2 布局。
- 新方言的布局、操作数个数与消息语义通过样本中的 `misc/script.c`、`misc/script.inc`、`adv/adv_script.inc`、`adv/adv.c` 核对；数据库结构由有界二进制表及 `NAME_T`/`db_set` 对照确认。随包只含独立实现、格式事实和人工 fixture，不携带或逐行移植游戏源码。
- 真实原始资源和运行报告留在用户提取目录。没有启动游戏，没有验证补丁加载或字体显示。
