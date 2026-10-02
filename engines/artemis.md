# Artemis：ASB 项目树的保真读写

## 能力边界
- 引擎 ID：`artemis`。
- 参考模块：[python/engines/artemis.py](../python/engines/artemis.py)。
- 实现 `ASB\0\0` 项目列表、命令属性和标签节点的读写。
- “树”指列表中嵌套命令/属性结构，不代表任意 Lua AST 都受支持。
- 输入输出为内存 bytes/结构；无原库运行时依赖。
- **同一引擎还有另外两种剧本方言**：`.txt`/`.iet` 可以是 SCP 文本而不是 ASB，解析器在 [artemis-scp](artemis-scp.md)；`.ast` 是第三种——Lua 表文本剧本，解析器在 [artemis-ast](artemis-ast.md)。选错页面会把整部对白读成"没有剧本"。

## 识别证据
- ASB 前五字节为 `41 53 42 00 00`，随后是小端 u32 项目数。
- `.asb` 是线索；msg-tool 同一 builder 还列出 `.iet`。
- `.ast`、文本 `.txt` 与 `.asb` 是不同入口，不应共用二进制 parser。`.ast` 不是二进制：它是带 `astver` 头的 Lua 表文本，走 [artemis-ast](artemis-ast.md)。
- `.pfs` 的 `pf0/pf2/pf6/pf8` 是容器版本线索，须独立核对索引；解包版本与 AST/SCP/ASB 剧本方言分别确认。
- `.asb` 后缀也被 [AZSystem](azsystem.md) 使用，以完整头和结构区分。
- **`.iet` 不是 ASB 的同义词**：`.iet` 也可能是 UTF-8 SCP 文本（见 [artemis-scp](artemis-scp.md)）。先读前若干字节，看到 `ASB\0\0` 才走本页。
- 引擎身份读 `Copyright.txt`，不要读收件目录名或品牌名。
- 抽取一条 `print`、一条 `name` 并核对相邻命令，比仅看可读字符串可靠。
- 节点类型必须是已知 0/1；遇到其他类型即停止。

## 格式方言
- 类型 0：命令名、行号、属性数及有序键值对。
- 类型 1：标签名字符串。
- 每个字符串是 u32 UTF-8 字节数 + 内容 + NUL。
- 长度不包含 NUL；长度不是 Unicode 字符数。
- 命令可包含未知属性或未知名字，结构正确时原样保留。
- 重复属性键拒绝，避免字典覆盖导致静默丢数据。
- 不接受尾部未知区块，也不自动把损坏长度修成“可解析”。

## 容器到剧本路线
1. 从资源证据确定 PFS/PF2 或外置文件路线。
2. PFS 参考 [python/archives/pfs.py](../python/archives/pfs.py) 模块：`read_index`（只读头/索引，不载入载荷）、`read_member`、`volume_paths`/`resolve_volumes`（多分卷覆盖链）、`build`/`repack`（pf6/pf8 写出）。
3. 校验提取成员路径和原始哈希，候选 ASB 先独立解析。
4. `.ast` 转 [artemis-ast](artemis-ast.md)；SCP 文本 `.txt`/`.iet` 转 [artemis-scp](artemis-scp.md)。都不强行塞给 `read_asb`。
5. 保存 ASB 树、提取字段身份与原始字节，之后只修改批准的属性。
- 本模块不处理容器 XOR、目录索引、压缩或加载优先级；pf8 载荷 XOR、索引尾部附加表、多卷覆盖由 `pfs.py` 处理。
- pf8 载荷 XOR key 来自索引的 SHA-1；修改 index 后 key 会变化，不能只复制旧密文而不按新索引重新处理载荷。
- 名称编码不要固定假设 CP932：`read_index` 默认自动判定，pf8 的成员名可以使用 UTF-8。

## 源码与算法对应
- 来源：`VNTextPatch-net8`，MIT。
- 提交：`d9c0fab7b72fdcf87d674ef12a84d3829c9188be`。
- 路径：`VNTextPatch.Shared/Scripts/Artemis/ArtemisAsbScript.cs`。
- `ReadFile/ReadItem/ReadString` 对应 `read_asb`。
- `WriteItem/WriteString` 对应 `write_asb`。
- `GetTextReferences` 对应 `text_fields` 的命令/属性白名单。
- VN 的 `WriteItem` 会把原行号写成 0；Python 刻意保留原 line_number。
- 属性顺序也被保留，不依赖字典排序重建。
- Python 不采用 VN 的整段 print/ruby 合并重写，避免丢失附加属性。

## Python 接口与示例
```python
from python.engines.artemis import Command, Label, write_asb, read_asb, patch_asb
items = (Label('start'), Command('print', 42, (('data', 'hello'),)))
raw = write_asb(items)
assert read_asb(raw) == items
changed = patch_asb(raw, {(1, 'data'): '你好'})
assert read_asb(changed)[1].line_number == 42
```
- `read_asb(bytes) -> tuple[Command | Label, ...]`。
- `write_asb(items) -> bytes`。
- `text_fields(items)` 返回 item、attribute、kind、text。
- `patch_asb(bytes, {(item, attribute): text}) -> bytes`。

## name / message 映射
- `name` 的属性 `0` 对应 `name`，不覆盖其他同类命令。
- `print.data` 对应独立正文片段 `message`。
- `ruby.text` 对应 `ruby_reading`，不是第二条正文。
- `sel_text.text` 对应 `choice`。
- `RegisterTextToHistory.1` 对应 `history`，不是可忽略的重复噪声。
- 连续多个人名和上下文命令保留顺序；叶模块不臆造单一说话人。
- 空字段也保持身份，避免回填序号漂移。

## 回填、长度与控制码
- 仅字段白名单允许翻译，不允许改命令名、标签或任意脚本表达式。
- 字符串按 UTF-8 重新编码，并更新自身 u32 字节数。
- NUL 拒绝；节点数和属性数由结构重算。
- 现有 ruby、print、/ruby 的命令边界保持不动。
- 不主动增删打印命令，因此没有跨命令位置变更的额外假设。
- 每个节点仍保留行号和非翻译属性。
- 回填后应重新读取整树并比对非翻译字段。

## 打包技巧：新增 PFS 覆盖卷

- 可以把修改后的文件单独打包为 `xx.pfs.0xx` 形式的补丁卷：前缀沿用现有包名，末尾数字序号取**当前同族所有包的最大序号之后**，后加载的高序号卷覆盖前面卷中的同名成员。例如已有 `game.pfs`、`game.pfs.000`、`game.pfs.012`，可生成 `game.pfs.013`。
- 每个补丁卷都是独立、完整的 PFS 归档；只需包含要替换的成员，不必重打整个原包，也不是把原包按字节切片。容器版本及成员名编码应与目标兼容，由 `pfs.py` 的 writer 正确重建索引和载荷。
- **保留成员在原包中的完整逻辑路径和大小写**，例如原文件为 `scenario/common/start.asb`，补丁中仍用该路径；不要扁平化或额外套一层目录，否则不能覆盖原成员。该技巧属于容器层，同样适用于 ASB、SCP 和 AST 剧本。
- 编号按数值比较，并沿用现有补零宽度；先枚举已有补丁，避免新包序号仍低于更晚的官方或汉化补丁。回填基准也应取覆盖链中最终生效的成员。
- agent 默认在新结果目录生成高序号补丁卷，重新读取并核对成员与覆盖链，然后告知用户其对应的原包目录。先用少量中文确认目标发行版实际加载了补丁，再批量制作；部署与游戏启动沿用主流程授权边界。

## 部署条件
- 必须确认目标 ASB 编码与命令约定确实匹配该方言。
- 选择、历史和 ruby 字段未必与窗口正文使用同一排版限制。
- 外置目录或补丁归档是否生效需要实测，不在纯 Python 模块中猜测。
- 所有磁盘写出、路径安全和 manifest 交给父 Skill 公共实现。
- 树读写成功只证明结构成立，不证明游戏运行时接受新字形。

## 验证与缺口
- 合成测试覆盖 UTF-8 多字节长度、非零行号、属性顺序与未知命令保留。
- 空改动 ASB 在本方言下逐字节一致。
- 容器侧另有测试覆盖尾部附加表、UTF-8/CP932 名称判定、多卷覆盖链与 pf8 恒等重封包；格式说明见 [artemis-scp](artemis-scp.md)。
- 覆盖重复键、未知节点、尾随垃圾、NUL、非文本属性回填拒绝。
- 测试位置：`tests/test_engines_primary.py` 中 `ArtemisTests`。
- `msg-tool/src/scripts/artemis/asb.rs` 还含更复杂控制流及源码转换。
- 其提交为 `f72716cee88554d40c1cdface2812493b14ca653`，GPL-3.0-or-later。
- 本参考不是该 Rust 全量模块的移植，不支持任意 `.iet` 控制流编辑。
- 没有商业素材、游戏运行时或付费 API 验证。
