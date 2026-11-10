# YU-RIS：YPF 解包、YBN 分区 XOR 与 ysc.ybn

## 能力边界
- 引擎 ID：`yuris`。
- 参考模块：[python/engines/yuris.py](../python/engines/yuris.py)。
- 归档模块：[python/archives/yuris.py](../python/archives/yuris.py)，实现指定版本/方案的 YPF 索引、选中成员读取及 raw/zlib 解码。
- 实现 YSTB 四分区 XOR、SJIS 感知的控制字节转换和 YSCM 命令表。
- 通用模块没有完整表达式 VM 或自动密钥推断。
- **v482（0x1E2）**支持下节列出的提取、回填及 YPF 模板重封；其他版本不能直接套用。
- **版本字 234–490 只开放解析**：`Scenario`/`commands_from` 接受该范围的 YSTB/YSCM 并报告 `version`，但回填仍只对 v482 生效（`serialize` 与 `rebuild_script` 对其它版本直接拒绝）。放开范围的依据是第三方工具（翻译肋手 v4.9D 反编译）用同一套 `<HHII>` 描述符读取 234–490，**这只是解析边界，不是“布局已证实相同”**；工作区提取遇到非 482 脚本记录为 `unsupported_version`，成员按原字节保留，不出 JSON。
- **YDG 图片与 CP932 字库页面**：支持格式 100 的 QOI/WebP 分块、PNG 模板回封及显式网格字库重建，流程和依赖见 [YDG 与字库](yuris/ydg.md)。图片资源与 YBN 语义分开处理；字库映射复用公共 JIS 流程。

## v482 工作流

| 层 | 实现与范围 |
|---|---|
| v482 YPF | [yuris_482.py](../python/archives/yuris_482.py)：索引、Murmur2 校验、有界解压、模板重封 |
| v482 YBN | [yuris_text.py](../python/engines/yuris_text.py)：WORD、单字符串 EVAL、纯变量 EVAL 透传、姓名定义与选项、独立 manifest、追加式回填 |
| 工作区 | [yuris_extract.py](../python/engines/yuris_extract.py)：`extract` / `rebuild` CLI |
| 验证 | [test_yuris_482.py](../tests/test_yuris_482.py)、[来源记录](../provenance/yuris-482.json) |

### 必须区分的格式细节

- YPF header 的版本为 `0x1E2`，名字 XOR key 为 `FF`，长度置换为 `SWAP_TABLE_00`。记录为 `u32 name_hash / u8 name_length / name / u8 type / u8 packed / u32 raw_size / u32 stored_size / u64 offset / u32 data_hash`。名字及压缩流校验均为 **Murmur2(seed=0)**，不是 CRC32/Adler32。
- **不要用通用 reader 的 `extra_header_size=4` 假装支持该布局**：那会把 offset 的高四字节误读成 checksum，把真正的 checksum 当 extra。v482 使用独立 reader，并逐成员核对两种 Murmur2。
- 原归档索引顺序与物理存放顺序不同。writer 按原物理顺序重建，保留名字字段、目录顺序、间隙及尾部不透明数据，更新存储长度、原长度、64 位偏移、Murmur2。未改成员保留原压缩流；重压缩不作为原文往返的必要条件。
- `ysc.ybn` 版本同为 482，命令数以头部声明为准。命令表后还有诊断 cstring 和最后 **256 字节不透明表**，不是损坏的尾部；`read_command_list(..., allow_message_tail=True)` 仅在此版本验证该布局。整个 YSCM 保持原字节，尾部不交给翻译器。
- YSTB 分区 XOR key 为 `0x96AC6FD3`（小端字节 `D3 6F AC 96`）。这是当前 profile 的参数；其他输入须以完整命令、分区和属性结构确认，不能仅靠 XOR 自反性判断 key。
- 属性 ID 不是唯一键：LET、声明和流程控制重复使用 ID 0，类型高字节也有标志。IF/ELSE/LOOP 后续 type=0 的描述符是**指令目标和池位置**，不能把它当长度、偏移的字符串。这会制造“越界”假象，更不能用它去切分全文。
- 原值区有共享和子串重叠。writer **保留原值区全部字节**，每个修改过的文本属性单独追加新值，只更新该描述符的长度/偏移和值区总长。指令、其他属性、流程目标和行号不变，避免移动整个字符串池后破坏未知表达式引用。重新解析检查全部目标文本及所有非目标属性。

### 对话与显示文字

- raw `WORD` 作为可见文字导出，空 WORD 和空 `_` 不导出。`_`（EVAL）仅支持 YSCM 第一个参数元数据为字符串表达式、且指令只有一个 type=3 参数的完整字符串字面量；空字面量不导出。多参数、动态或组合表达式拒绝，不执行 VM，也不猜片段拼接规则。
- 表达式字节码按 `u8 opcode + u16 载荷长度 + 载荷` 逐 token 切分，只有 `4D`（`M`）携带字符串。`_` 的全部非空参数均为 type=3、能完整切分且只含已证实的非字符串 token（`B`/`W`/`I` 数值，`H`/`V`/`v` 变量引用，`)` 下标结束及 `+ - * / % = ! , s` 运算符，载荷宽度固定）时，按纯变量计算（如 `$x(239)+$x(240)`）原字节透传，不导出、不报错，数量记入报告 `opaque_eval`。含 `M` 但不是单一完整字面量、出现其他 opcode、载荷宽度不符或切分有残尾的仍拒绝。
- `【姓名】正文` 分成 `name` 与 `message`，回填恢复括号；正文引号、原有空格与换行保留，不自动排版。
- `GOSUB ES.CHAR.NAME` 中第一个参数为调用目标，第二个参数（ID 33）为角色键，第三个参数（ID 34）为显示名；只导出第三个参数作为独立姓名定义行（`message` 字段），角色键及后续参数保持原字节。布局不符时拒绝，不沿用选择参数的遍历规则。`ES.SEL.SET` 导出 ID 33..48 的字面量 PSTR 选项，到空参数停止；运行时显示仍须单独验证。
- 姓名/选项表达式必须是完整 `4D + u16长度 + 引号包围的字面量`；回填更新内层 u16 长度。未知组合表达式不会当普通文字替换。
- 剧本按 CP932 严格编解码；CP932 写不下的中文走[公共 JIS 流程](../guides/jis-substitution.md)。原版游戏不带 `uif_config.json`、`version.ini`/`winmm.ini` 等字符映射；游戏目录中出现它们，说明混入了之前的汉化或试注产物，须改用未改动的原版文件提取，不能把映射当作原作的一部分。
- EF 控制序列转换、保护和回填仍使用下文的规则；译文必须保留 `\p/\c/\u` 的顺序与数量。换行可以比原文少，但不能新增或跨这些控制码移动。
- 单字符串 EVAL 同样可拆分 `【姓名】正文`，回填保留字面量封装并更新内层长度。字段语义来源见 [文本字段来源](../provenance/common-text-fields.json)。
- 当前 manifest 参考标识为 `yuris_text/2`。旧提取目录须从哈希通过的原始数据重新导出到新目录；新增/修正的字段会改变条数或定位，不能修改旧 manifest 或按条数猜配译文。

### 可复现命令与产物

在技能根目录运行；`<…>` 均为占位，按实际游戏替换。`<输出目录>` 应是游戏内新建的 `<游戏名>_extract`，可复用已存在的普通空目录，父目录须已存在；已有非空目录不能覆盖。

```text
python -m python.engines.yuris_extract extract "<游戏目录>" "<输出目录>" --archive <剧本包相对路径>.ypf [--loose <原始松散YBN目录>] [--reference-archive <其他包相对路径>.ypf] --smoke-test
```

- `--archive`：游戏目录内的 v482 剧本包，作为重封模板；其成员集合与 YSCM 决定回填范围。
- `--loose`（可选）：与模板成员一一对应的**原始**松散 YBN 目录。省略时直接以 `--archive` 包内成员为文本基准（报告 `selected_baseline` 为 `template-archive-members`），成员须全部位于 `ysc.ybn` 所在目录。
- **基准必须是未改动的原始脚本。** 游戏目录中的松散 `ysbin/` 或更新包可能已被汉化补丁、旧回填或其他工具覆盖；不能确认来源时不要传 `--loose`，改用原始包成员。`--reference-archive` 同样只用于对照原始包，不能把补丁产物当参考来源；报告的 `different_from_loose` 只说明差异，不判断哪一侧是原版。
- 不自动猜测加载优先级、合并冲突文件或回溯扫描旧提取目录。

逐成员处理：某个场景解析或往返失败时只阻断该成员，记录为 `blocked`（含成员名与原因），不生成 JSON，在所有重建包中按原字节保留；其余成员照常导出。存在阻断成员时报告 `status` 为 `partial`、CLI 以非零码退出，须先研究报告 `blocked` 列表中的原因再声称完整提取。

- `gt_input/`：按场景名生成平铺 JSON，无目标文字的场景和配套文件不产生空 JSON。
- `gt_output/`：接收同名、同顺序译文；测试译文只放 `reports/smoke-translation/`，不混入这里。
- `original/game/`：原始包、完整基准 YBN 和 YSCM；`metadata/` 保存重新解析可核对的描述符身份及哈希。
- `rebuilt/roundtrip/`：场景经 parser/writer、原归档经容器 writer 重建后的原文往返结果，配套文件保留。
- `rebuilt/current/<剧本包相对路径>.ypf`：按选定基准生成的完整包，沿用 `--archive` 的相对路径和文件名，须与基准逐成员比对，不与原包往返混淆。
- `rebuilt/smoke-test/`：可选的变长测试脚本和完整包（同样沿用模板路径）；重新提取验证文本、描述符、原池、指令及行号。
- `reports/extraction.json`：`status`、来源哈希、基准选择、逐成员状态（`exported`/`empty`/`non_target`/`unsupported_version`/`blocked`）、`opaque_eval` 计数、包间差异及验证结果。

译文按同名文件放回 `gt_output` 后告诉 agent，由 agent 校验并回写：

```text
python -m python.engines.yuris_extract rebuild "<输出目录>" "<输出目录>/rebuilt/translated-01"
```

输出新目录含按基准相对路径存放的松散 YBN，以及与 `--archive` 同相对路径、同文件名的完整包（例如模板为 `<子目录>/<名>.ypf` 时输出 `<输出目录>/<子目录>/<名>.ypf`），表示替换该模板包的完整新包。缺译文的成员保留**选定基准**；提取时 `blocked` 或 `unsupported_version` 的成员按原字节复制并列入 `copied_unsupported_members`，为其提供的译文按未知文件名拒绝；源文件、原文 JSON 或 manifest 变化也拒绝。没有启动游戏或验证字体、加载优先级与排版，CLI 不安装这些产物。

## 识别证据
- YBN 不是单一格式：`YSTB` 是场景，`YSCF` 是配置。
- `ysc.ybn` 的 `YSCM` 是命令字典，不应当作普通场景翻译。
- VN 在加载场景前会读取同目录的 `ysc.ybn`。
- `.ypf` 是常见资源容器，以 `YPF\0` 签名及成员结构单独核验，不与场景 `YSTB` 混为一层。
- 仅找到可读 WORD 或日文不能证明文件已正确解密。
- 代码数量、四个分区长度和总大小应同时成立。

## 格式方言
- YSTB 头长 0x20，含版本、指令数与四个分区长度。
- 四区依次是指令、属性描述符、属性值、行号。
- 本参考要求指令区大小等于指令数乘四。
- XOR key 按小端四字节循环，并在每个分区重新从 key[0] 开始。
- 不能把从 0x20 到 EOF 的全部 bytes 当作一个不间断 key 流。
- YSCM 的命令 ID 是字典顺序，而不是跨游戏固定常量。
- 命令后有 u8 属性数，各属性为 cstring 名字 + 两字节元数据。
- 本参考保留重复属性项位置与元数据，不用字典悄悄覆盖属性 ID。

## 容器到剧本路线
1. 先处理 YPF 容器，再按成员签名分出 YSTB/YSCM/YSCF。
2. 使用本页的 YPF 接口读取目录与选中成员；源码依据为 GARbro-Mod `ArcFormats/YuRis/ArcYPF.cs`。
3. 保持场景与同版本 ysc.ybn 配套，不复用另一作品的命令编号。
4. 密钥需要独立证据，再做分区 XOR 和结构验证。
5. 只有完整属性/表达式解析器证明范围后才可设计变长回填。
- 通用模块没有 YPF writer；v482 的独立 writer 见上节。两条路线都不自动寻找密钥或安装外部工具。

## YPF 版本与目录布局

`read_index` 必须显式提供 `version` 和文件名 `name_key`。头中实际版本必须一致，不能用文件后缀决定密钥。当前白名单覆盖上游代码中有明确布局线索的以下版本；其他版本先补证据与测试，不自动归入最近一档。

| version | 默认长度置换表 | 默认额外字段长度 |
|---|---|---|
| `0xDE` | `SWAP_TABLE_04` | 8 |
| `0xF7` | `SWAP_TABLE_04` | 0 |
| `0x122` | `SWAP_TABLE_00` | 0 |
| `0x12C` | `SWAP_TABLE_10` | 0 |
| `0x196` | `SWAP_TABLE_00` | 0 |
| `0x1D9` | `SWAP_TABLE_00` | 4 |
| `0x1F4` | 必须显式提供 `swap_table`，存在游戏专用表 | 4 |

- 魔数 `YPF\0`；`u32 version/count/directory_bound` 在 4/8/12，目录从 `0x20` 开始。
- 每条依次为：`u32 name_hash`、`u8 encoded_name_length`、加密名字、`u8 file_type`、`u8 packed`、`u32 unpacked_size/stored_size/absolute_offset/checksum`、额外字段。基础长度 `0x17 + name_length`，多字节名字按编码后的字节数计。
- 名字长度先与 `0xFF` XOR，再用置换表相邻两项互换；名字每字节 XOR `name_key`，默认严格 CP932。表必须是互不重复的字节对。
- `extra_header_size` 可按已证明方案显式传 0/4/8；保留到 `IndexEntry.extra`，不猜其中含义。`packed` 只接收 0/1；raw 成员声明的两种长度必须相同。
- 头部 `directory_bound` 是扫描上界，**不是可靠的 payload 起点**。上游 reader 从 `0x20` 起计剩余量，而 writer 写入包含头部的首数据偏移。本实现逐条扫描到 count，不为“填满 bound”而读入首成员；返回的 `index_end` 是实际目录末端。
- 上游 writer 写名字 CRC32、stored 流 Adler32，但 reader 忽略两者。默认保留字段，只有已确认该校验方言时启用 `verify_name_hash=True` / `verify_checksum=True`；校验失败不能自动换 key 后声称成功。
- 通用压缩仅支持 zlib。使用 Snappy 的方案、EXE/YSER overlay 定位、自动密钥推断和其他版本重封包仍缺失。归档返回解压后的原 YBN bytes，**不做 YSTB 的 ScriptKey XOR**。

## YPF 只读接口

```python
from pathlib import Path
from python.archives.yuris import read_index, read_member, decode_member

# proven_version/name_key 来自实际游戏的方案证据，不能照抄其他游戏的 key。
with Path("game/data.ypf").open("rb") as stream:
    index = read_index(stream, version=proven_version, name_key=name_key)
    entry = next(e for e in index.entries if e.name.lower().endswith(".ybn"))
    stored = read_member(stream, index, entry, max_stored_size=64 << 20)
    ybn = decode_member(entry, stored, compression="zlib", max_output_size=64 << 20)
# ybn 仍需检查 YSTB/YSCM/YSCF 签名及脚本自身的加密条件。
```

- `read_index` 默认 `max_entries=100000`、`max_index_size=16 MiB`（含头部），只读取目录，不按成员大小收费。
- `read_member` 返回所选成员的 stored bytes；`decode_member` 单独限制输出，校验 zlib 终止、尾部和声明长度，失败直接拒绝。
- 索引/读取都恢复流位置，支持合法短读。使用同一未改动的 seekable 二进制流；成员必须是该索引返回的原对象。检查文件总长度变化，但不检测同大小的原地修改，索引不是认证凭据。
- 路径穿越、Windows 保留名、大小写/Unicode 重名及文件/目录冲突拒绝。API 不写盘；批量解码需按剩余总预算逐项收紧上限，之后用公共 `write_new_tree` 写入新的输出目录。
- 通用归档算法出处、修改说明与验证等级见 [common-archives-v1.json](../provenance/common-archives-v1.json)；固定向量和异常输入见 [test_archives_common_engines.py](../tests/test_archives_common_engines.py)。v482 的读写接口见上节。

## 源码与算法对应
- 来源：`VNTextPatch-net8`，MIT。
- 提交：`d9c0fab7b72fdcf87d674ef12a84d3829c9188be`。
- 路径：`VNTextPatch.Shared/Scripts/Yuris/YurisScenarioScript.cs`。
- `ToggleScriptEncryption` 对应四区 XOR。
- `YurisControlCodesToStandard/StandardControlCodesToYuris` 对应控制转换。
- `YurisCommandList.cs/ReadCommand` 对应 YSCM 顺序字典。
- `VNTextPatch.Shared/Util/BinaryUtil.cs/Xor` 证明 key 字节序与循环行为。
- VN 的自动取 key 依赖首属性描述符假设，Python 不把该假设当通用保证。

## Python 接口与示例
```python
from python.engines.yuris import toggle_ybn_sections, convert_control_bytes
raw = b'A\xef\xf0B\xef\xf2'
standard = convert_control_bytes(raw)
assert standard == b'A\r\nB\\p'
assert convert_control_bytes(standard, to_yuris=True) == raw
assert toggle_ybn_sections(toggle_ybn_sections(ystb, key), key) == ystb
```
- `toggle_ybn_sections(bytes, u32_key) -> bytes`，头部不变。
- `convert_control_bytes(bytes, to_yuris=False) -> bytes` 只处理原始文本字节。
- `read_command_list(ysc_bytes) -> tuple[(命令名, 属性tuple), ...]`。
- 按返回序号找到 WORD、`_`、GOSUB 等 ID，不硬编码。

## name / message 映射
- VN 会合并部分 WORD/EVAL 属性，再尝试按日文引号解析姓名与正文。
- GOSUB 的 `ES.CHAR.NAME` 与 `ES.SEL.SET` 也可能产生文本。
- 本局部模块不输出假 name/message；它返回低层字节或命令结构。
- 接入完整提取器时必须保存参与合并的每个属性身份。
- 多人名与变量名保留为独立上下文，不应因合并而丢弃。
- 不能把 ysc 命令名、属性名或 `$str20` 类程序变量当译文替换。

## 回填、长度与控制码
- EF F0=换行，EF F2=翻页，EF F3=等待点击，EF F5=源码未明控制。
- 对应标准表示为 CRLF、`\p`、`\c`、`\u`。
- 逐 SJIS 字符移动，避免把双字节字符尾字节 0x5C 当反斜线控制。
- 未知 EF 控制码或不完整多字节字符直接拒绝。
- EF F5 只按源码可逆表示保留，不给它编造语义。
- 完整回填必须更新属性长度、全部属性值偏移、值区总长及后续区位置。
- 表达式字符串还有 4D/u16长度/引号约定，不能用裸文本替代。
- 本模块不执行这些全文件步骤，返回的局部结果不能直接覆盖整个 YBN。

## 部署条件
- 必須保存原 YSCM 与场景版本、key 来源和分区大小证据。
- 不用“XOR 两次等于原文”证明某个猜测 key 正确；任意 key 都有该性质。
- 先检查解密后的真实指令/属性边界，再谈翻译。
- 最终重加密与包写回必须属于经验证的完整流水线。
- 公共层统一处理原文件保护、目标目录与 manifest。

## 验证与缺口
- 合成测试故意使用非四字节对齐区长，验证每区 key 相位重置。
- 测试控制码往返、SJIS 0x5C 尾字节不误改与未知码拒绝。
- 测试 YSCM 顺序 ID、属性元数据及未知尾部拒绝。
- 测试位置：`tests/test_engines_primary.py` 中 `YurisTests`。
- SExtractor `src/extract_Yuris.py` 是另外的提取路径，不是本模块依赖。
- 其提交 `8d8d976fd04ae54e7c677705af937273d04a376a`，GPL-3.0。
- 完整表达式 VM、其他版本的属性回填/YPF 封包和商业运行验证仍缺失；v482 的特定方言支持以上节为准。
