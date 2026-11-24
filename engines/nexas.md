# NeXAS：PAC 尾索引与 BIN 字符串池回填

## 快速路径

识别为本格式后先直接运行提取命令：按实际路径替换占位符，多条命令对应不同方言或来源，按下文的识别条件选一条。提取器自行校验格式并用原文走真实的解析与回写，结构不符时拒绝并指出失败位置。命令成功就不必读实现源码或研究资料；失败时再按报错读本页对应章节和 `python/` 中的实现。

```text
python -m python.engines.nexas_extract extract /path/to/game --output /path/to/game/game_extract --verify-edits
```

## 入口与范围

检查 PAC 前三字节 `PAC`、偏移 4 的成员数、偏移 8 的压缩类型及尾部索引。第四字节不一定为零，不能仅匹配 `PAC\0`。

- [PAC 读写](../python/archives/nexas.py)：64 字节名称、Huffman 尾索引方言；成员类型 0/5 原始、2 Huffman、3/4 zlib、6/7 Zstandard。尚不支持前置索引、旧版反码 PAC 或类型 1 LZSS。
- [BIN 读写](../python/engines/nexas_bin.py)：extras_count、extras、commands_count、8 字节指令对、strings_count、CP932 NUL 字符串、trailer。语义导出按 FUNC 编号方言表进行（见下文“FUNC 方言”），未知 opcode、消息参数形状或控制码按成员明确拒绝。
- [批量 CLI](../python/engines/nexas_extract.py)：按 packlist 或显式优先级读取多个包，导出 JSON、manifest、原文往返 PAC，并支持译文重封包。
- [旧 ASM 编辑器](../python/engines/nexas.py)：继续支持 SExtractor 根目录反汇编器的 ASM，其 assemble_bin() 仍未实现；新 BIN writer 不接受任意 ASM。

PAC 6/7 的 Zstandard 压缩读写需要可选 Python 包 **zstandard**（可用 python -m pip install zstandard 安装）；类型 7 的未压缩成员仍可直接读取。其他层使用标准库，导入模块或只读 PAC 索引不要求安装它。不调用游戏 EXE、补丁 DLL、GUI 或外部封包程序。静态检查器仅在本 PAC 模块中允许这一明确声明的可选依赖，并要求函数内延迟导入及 `ImportError` 处理；缺包时只在调用 Zstandard 功能时给出清楚的错误，不影响其他压缩类型。

## 核对补丁和 BIN 方言

先只读各 PAC 索引，不要为查剧本解压 Voice/Visual。read_index(stream) 不读取成员内容；选定条目再用 read_member(stream, index, entry)，有单项解压预算。

不传 `--archives` 时，提取器读取 `Config.pac` 中的 `packlist.dat`：12 字节头（三个 u32，不解释）后为若干“NUL 结尾 ASCII 包名 + u32 分组”，必须恰好读到文件末尾。补丁包（UpdateN…Update）列在基础包之前，按文件顺序为高到低优先级；提取器取其中**磁盘上实际存在且含 .bin 成员**的包，倒序作为低到高优先级。列表中不存在的包只记入 `reports/extraction.json` 的 `archive_selection.absent_on_disk`，不会被猜测或创建；其他包内的 `packlist.dat` 副本与 `Config.pac` 不一致、布局不符或缺少 `Config.pac` 时拒绝，须显式传 `--archives`。显式 `--archives` 始终优先。

BIN 方言与 PAC 压缩类型没有对应关系。含 extras 的布局必须按 `extras_count` 读取完整字段，不假定首字为零，也不擅自添加或删除填充字。

## 导出与回封

从 skill 根目录运行，替换下面的示意路径。输出目录须不存在或为可复用的已有目录（不含同名产物或非空结果目录），且父目录已存在；冲突时改用新名字。

~~~text
python -m python.engines.nexas_extract extract /path/to/game --output /path/to/game/game_extract --verify-edits
~~~

`--archives`（可选）从低优先级到高优先级，后者覆盖同名成员。`--verify-edits` 另对每个有文本的有效脚本的全部记录做变长试编辑（正文追加不同长度文字、姓名加字），经 BIN writer 与 PAC writer 重建后重新读索引、解压并重新解析，比对记录与非文本结构，结果记入 `edit_check`；试编辑包不写盘。输出目录包含：

| 目录 | 内容 |
|---|---|
| gt_input/ | 平铺的原剧本名.json，只输出有文本的脚本 |
| gt_output/ | GalTransl 译文，文件名和数组顺序不变 |
| original/archives/ | 所选输入 PAC 的完整副本 |
| original/scripts/ | 按覆盖顺序选出的原始 BIN |
| metadata/ | JSON 对应哈希、指令引用、字段和控制码契约 |
| roundtrip/ | 经过 BIN writer 和 PAC writer 的原文往返包 |
| reports/ | 索引、来源映射、逐包验证、packlist 原始证据、`translation-state.md` 状态表 |

报告 `status` 为 `complete` 或 `partial`，退出码分别为 0 和 1；参数、文件、PAC 或方言选择失败时输出 `error: <命令>: <原因>`，退出码 2。单个脚本解析、控制码或原文往返失败时该成员记为 `blocked`（原因含包名、成员名与指令序号），不发布 JSON，重封包时按原压缩字节复制；`pack` 遇到同名译文直接拒绝。所有有效脚本都受阻时整体失败。提取结果中的 `delivery` 已给出交付四项及需保留的控制码说明。

译文按同名文件放回 `gt_output` 后告诉 agent，由 agent 校验并回写：

~~~text
python -m python.engines.nexas_extract pack /path/to/game/game_extract --output /path/to/game/game_extract/rebuilt
~~~

pack 验证原 PAC 哈希，并重新从 PAC 解析原文、定位器和 manifest；按文件名读取译文，缺少译文的成员保持原压缩 payload，未匹配 JSON 列入报告。译文只写回成员实际所属的高优先级包；底包旧版本不会被改成补丁版本。每个生成 PAC 都重读索引、解压被替换成员并比对，其余成员的压缩 payload 逐字节核对。--translations 只用于显式测试目录，正常流程使用 gt_output。换行保护项调整后，旧 metadata 无法通过 manifest 比对；应从哈希验证通过的原 PAC 重新提取到新目录，再放回同名译文。

只生成副本，不覆盖安装目录。roundtrip 是原文验证产物，rebuilt 才是用户译文的候选包，两者都不自动部署或启动游戏。没有译文时 changed_scripts=0，不应称为汉化包。

## 语义与字符串引用

按指令调用点确定字段，不把短日文猜作人名，不把所有 LOAD_STRING 当对白。FUNC 参数 `0xNNNNIIII` 高 16 位为实参个数、低 16 位为函数编号；同一调用形状在不同引擎版本中位于不同编号，因此编号来自方言表：

| 指令形状 | 导出 |
|---|---|
| 两个 op=5,arg=1 单字符串参数，随后 FUNC message | 姓名与正文，空姓名省略 |
| FUNC message 前的已验证复合串接模式（姓名 + effect/正文 串接 + 纯控制后缀） | custom-message，保留 effect 和纯控制后缀 |
| 单字符串随后 FUNC continuation | 追加对白，不猜姓名 |
| PUSH / LOAD_STRING / PUSH，随后 FUNC choice | 选项，数值参数保留 |
| op=0xE,arg 高字节=0x80 的单字符串参数 | special-text，空值和纯控制串不输出 |
| notification 编号的单字符串实参 | 已核对的 UI 提示 |

### FUNC 方言

| profile（代码标识） | message | continuation | choice | notification | 额外 opcode | 控制码 |
|---|---|---|---|---|---|---|
| `aikiss3-extras-v1` | 0x4006F | 0x10071 | 0x30066 | 0x20023/0x20075/0x20015/0x10017 | — | 见下文通用集合及 @i |
| `nexas-func40069-v1` | 0x40069 | 0x1006A | 0x30062 | 0x20023/0x2006E/0x20015/0x10017 | 12/15/22/63 | 通用集合及 @s、注音 @r |

方言按结构证据选择，不按游戏名：统计所选全部 BIN 中“两个单字符串参数紧接 FUNC”的调用，恰好一个方言的 message 编号有此类调用时选用它；都没有或多于一个时整体拒绝，并列出出现此形状的 FUNC 编号，不会静默导出近乎空的结果。选定后，若某成员把同样的（姓名, 正文）形状传给方言表以外的 FUNC，该成员受阻。报告的 `dialect_evidence` 记录各方言的调用点数。

opcode 12/15/22/63 是无操作数的二元运算：在全部样本中都紧跟右操作数 opcode 6，参数为 0、无 op=0 前缀，15/22 之后与 16/21/23–26 一样接条件跳转 66。指令为定长 8 字节，接受它们不涉及长度猜测；每个调用点仍复查上述形状，不符即拒绝。另一 2 参数整数调用（`(5,0,1),(5,0,1)`）不是选项；选项的判定只依据上表形状。

资源调用（音效名、剧本文件名、图片名等）中的日文字符串不会进入翻译队列。op=0xE 以普通变量号赋值、再由 op=8 取字符串的界面文字，以及单字符串传给方言表外 FUNC 的调用，当前均不导出（语义未证实）；如需翻译，先补齐该调用的证据再扩充方言表。special-text 与 custom-message 可能引用同一原文但用于不同指令；保留每次引用，**不按正文去重**，翻译时注意保持这些副本文意一致。报告条数是可回填记录数，不是去重对白数。

BIN writer 不重排原字符串池、指令或 EXTRA 表。原文回填重新解析并序列化所有字符串，保留原 CP932 字节，避免 CP932 重复映射造成无修改也变字节。修改时追加新字符串，只改变对应 op=0 前缀的字符串 ID；其他资源引用相同旧槽时不会被连带修改。命令区长度和条目序号不变，跳转无需重定位。尾部数据按字符串表结束位置读取并整体保留，不能丢弃 dat0 对应内容，也不能把尾部调试变量名当对白。

## 控制码与编码

- JSON 保留 @t 四位延时、@h 资源标识、@n/@k/@d、@m 两位参数及语音号；回填校验**完整序列与参数**。@n 换行可以比原文少，但其余控制码禁止增删或重排，@n 也不能跨到其他控制码之前。
- @h 参数可为空，不能吞掉紧随其后的正文。
- `aikiss3-extras-v1`：@v 为八位数字，可带一个字母或“_字母”后缀（如 `@v12345678b`、`@v12345678_a`，与 Voice.pac 成员名一致），后缀属于语音号、不可编辑；语音号后紧跟 ASCII 字母、数字或 `_` 时边界不明而拒绝。另有 @i 两位参数。`nexas-func40069-v1`：@v 为 8–9 个 ASCII 字母或数字（与 Voice.pac 成员名长度一致，可含字母前缀或后缀）；@s 后接四位数字；注音为 `@r底字@读音@`，底字和读音可翻译，三个标记不可增删，底字与读音都不能为空。该方言中 @v、@t、@s、@m 若紧跟可延长参数的字符（字母数字或数字）即视为边界不明而拒绝；注音结束的 `@` 若同时能读成控制码（如 `@n`）也拒绝。
- 未列出的 `@` 组合（如大写 `@H`、`@v` 后无编号）不猜测其运行时含义，所在成员受阻；需先以 EXE 或运行证据确认解析规则。
- 不把真实 CR/LF、TAB、NUL 写进字符串，换行用 @n。
- 新文本须严格 CP932 编码且可反向解码为同一 Unicode 文本，不替换、不截断。中文字符集、字体与运行时适配是另一个阶段；已有汉化 EXE 不证明 writer 可以直接改用 GBK。
- 纯 name/message JSON 必须保持数组顺序，条数相同的重排无法自动证明身份正确。

## 验证

- [合成测试](../tests/test_nexas.py) 覆盖压缩、坏数据、共享引用、CP932 原字节、控制码/manifest 拒绝、补丁优先级与不覆盖输出，以及两种 FUNC 方言的选择与拒绝（无方言、多方言、表外消息形状）、运算 opcode 形状复查、注音/@s/@v 边界正反例、packlist 解析与默认包选择、受阻成员原样复制与 `pack` 拒绝、`--verify-edits`、退出码。运行 python -m unittest discover -s tests -p test_nexas.py -v。

未启动游戏验证显示、换行、字体、存档兼容或运行时加载。成功范围是格式与文本往返，不能称为已验证可运行的中文补丁。

## 旧 ASM 路线与来源

旧 nexas.extract_fields() / replace_fields() 只改带地址标签、TAB 和已知助记符的字符串内部跨度。其姓名分类是上下文启发式，不能代替 BIN 语义。保留单引号、TAB、真实 CR/LF、NUL 的拒绝规则及字面量 \n；ASM、dat0、未匹配 JSON 和转换器须配套。不能改后缀得到 BIN，不能丢失上游 JSON 的 true/false 标记。

- GARbro-Mod [ArcPAC.cs](https://github.com/nanami5270/GARbro-Mod/blob/bc26d991ef5cdc0e1ecb32122ee9a48c3375750c/ArcFormats/Nexas/ArcPAC.cs) 与同提交 ArcFormats/HuffmanCompression.cs：PAC 布局、反码尾索引及压缩类型。morkt MIT 通知见 [MIT-GARbro](../provenance/licenses/MIT-GARbro.txt)。writer 和严格边界检查为本项目实现。
- BIN 布局和控制码资料来源为 SExtractor 的 NeXAS 工具，含 masagrator/NXGameScripts 来源链，按 GPL-3.0-only 保留归属；见 [许可与来源](../provenance/NOTICE.md)。
