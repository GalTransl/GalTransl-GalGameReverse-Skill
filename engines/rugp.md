# rUGP：ReadEncrypted 块编解码与只读文本候选

## 能力与入口

| 阶段 | 当前范围 |
|---|---|
| 识别 | `.rio` / `.ici`、RIO 对象签名和配套文件仅作候选；不凭扩展名确定版本 |
| 物理扫描 | 任意字节对齐的 ReadEncrypted 头，包含跨窗口头及载荷；不是对象 TOC |
| 块解码 / 编码 | 显式密钥、完整 32 字节分块校验、原文逐字节往返与头部低三位保留 |
| 文本研究 | 解码块内 `60 xx 00 len:u8` 的 CP932 候选、偏移及失败诊断 |
| 剧情语义 / 回填 / 重封包 | 未实现完整 VM、对象引用及地址修复；不生成 `gt_input`，不提供剧本 writer |
| 验证等级 | 固定上游向量与人工正反例；未使用真实归档，未验证游戏显示 |

容器算法：[python/archives/rugp.py](../python/archives/rugp.py)。文本候选与只读工作区：[python/engines/rugp.py](../python/engines/rugp.py)。无需上游仓库或第三方 Python 依赖，不加载游戏 EXE/DLL。

## ReadEncrypted 格式

以下均为小端无符号整数，算术按 32 位截断。八字节头为 `word0:u32, word1:u32`：

```text
size  = ~(word0 XOR 0xC92E568B) AND 0xFFFFFFFF
check = word1 XOR 0xC92E568F
要求 size == check >> 3
flags = check AND 7
stored_size = 8 + size + 2 * floor(size / 32)
```

头部低三位用途未确认；reader 保留，encoder 显式传回，不默认清零。`size` 最多为 `0x1FFFFFFF`，实际分配还受单块和累计预算限制。

每轮处理最多 32 字节，`portion` 为本轮明文数，`i` 从 `portion` 递减至 1：

```text
plain_byte = cipher_byte XOR (key AND 0xFF)
checksum = (checksum + plain_byte * i) AND 0xFFFF
key = ~(((key >> 15) AND 1) + key * 2 + 0xA3B376C9) AND 0xFFFFFFFF
```

完整 32 字节后紧随 `checksum:u16`，**包括恰好结束于 32 字节边界的末块**。不足 32 字节的尾段没有校验和；不足 32 字节的整个帧无法通过校验验证密钥，较长帧也只能校验完整块，不能认证短尾完整性。空帧是合法外壳，不代表剧情。

默认 RIO 块密钥为 `0x7E6B8CE2`；ICI 资料密钥为 `0xB29D5A0C`，须调用者显式选择。相同外壳不证明 `.ici`、全部 `.rio` 版本或不同节点使用同一密钥。未知密钥不猜测，不根据乱码自动切换编码。

## 扫描与候选判断

`scan_headers()` 使用四相位扫描，每个窗口多读七字节，头部起点只归属于一个窗口，按物理偏移排序。发现头后，`read_block()` 从完整输入单独读取候选，不要求整个帧位于扫描窗口中。没有最小剧情尺寸、引号数量或日文字符过滤；短文本、纯旁白、ASCII 和重复字符串均保留。

物理扫描可绕开未覆盖的 MFC 对象布局以收集研究证据，**不能由此证明对象可达性、剧情顺序或剧情覆盖率**。头签名匹配、块校验通过及候选可读是三个不同阶段。超出文件、校验错误和预算跳过分别记录；全盘扫描完成不代表全部成员解码成功。原始成员名未知时使用物理偏移标识，不把扫描序号当原剧本名。

文本层只查找来源实现采用的 `60 xx 00 len:u8` 特征，没有把 `xx` 宣称为已解析的 opcode。每个匹配记录块内 `offset/end`、`sub_op`、`length`、原始 `raw_hex`、严格 CP932 文本和 `role="unknown"`。资源后缀仅标注 `resource_hint`，不删除；嵌套或重叠命中保留并标记。非法编码、截断长度和越界有单独诊断，不吞错。解码块中的 `0x03` 只在 `display_hint` 显示为换行；原 `text` 与 `raw_hex` 保留全部控制字节和空白，`0x01/0x05` 不自动剥离。

特征可能位于参数、资源或父块中；这里不推断姓名与正文，不拆分多人名，不按正文去重。未知指令长度、引用及嵌套布局仍须结构研究，不能把候选清单改名为 GalTransl JSON。来源工具的“严格 VM / 全量”表述未作为本包能力声明。

## 只读分析命令与结果

在 Skill 根目录运行，输入为用户提供的普通文件，输出父目录须已存在、目的目录须全新：

```text
python -m python.engines.rugp /path/to/game/scenario.rio -o /path/to/work/rugp-analysis
python -m python.engines.rugp /path/to/game/index.ici -k 0xB29D5A0C -o /path/to/work/ici-analysis
```

结果目录：

```text
rugp-analysis/
  original/blocks/block_<物理偏移>.bin
  decoded/block_<物理偏移>.dec
  metadata/block_<物理偏移>.json
  reports/analysis.json
  README.txt
```

`original/blocks` 仅保存成功解码帧的原始外壳；完整归档与配套文件仍是后续研究和回填基准。报告包含流式源 SHA-256、源文件名、密钥、预算、每帧阶段与拒绝原因。成功帧须真实经过解码及重新编码，并与原始物理帧逐字节核对后才发布。不会覆盖输入或已有输出，也没有 `gt_input/gt_output` 占位翻译队列。

默认输入限 4 GiB，扫描窗口 1 MiB，单块明文 16 MiB，头候选 20,000 个，累计尝试解码 256 MiB，文本候选 100,000 个，全部产物 512 MiB。失败解码也消耗累计预算；短尾不因无校验而算作已认证。CLI 的 `--max-input-mib`、`--max-block-mib`、`--max-decode-mib`、`--max-output-mib`、`--max-header-candidates`、`--max-literal-candidates`、`--chunk-kib` 可显式调整。扫描/候选或产物全局预算耗尽时失败且不发布部分目录，单帧超限标 `skipped`。

## API 与后续适配条件

```python
import io
from python.archives.rugp import decode_block, encrypt_block, scan_headers
from python.engines.rugp import inspect_literals

plain = bytes(range(64))  # 人工载荷，仅验证外壳算法
encoded = encrypt_block(plain, flags=3)
headers = scan_headers(io.BytesIO(encoded), chunk_bytes=11)
block = decode_block(encoded)
assert block.data == plain
assert encrypt_block(block.data, flags=block.header.flags) == encoded
assert len(headers) == 1
evidence = inspect_literals(b"\x60\x1f\x00\x05Hello")
assert evidence[0]["role"] == "unknown"
```

编解码器能接受任意二进制载荷，变长中文载荷往返仅证明外壳长度及校验更新，**不等于中文脚本回填**。要升级到翻译工作区，仍需证明可达脚本集合、VM 指令边界、真实字符串长度方言、消息/姓名/选项引用、控制语法、跳转与对象地址、对象尺寸及加载顺序；再提供原文脚本 writer 往返、变长中文重新解析与非文本结构保留测试。CP932 中文部署后续沿用公共 JIS 流程，不另造有损编码替换。

当前无法推荐可回注的开场 JSON；先根据报告确认结构与开场节点，完成语义 parser/writer 后再按主流程少量试注。此阶段不要求用户翻译候选清单。

## 来源与测试

来源、精确版本、逐文件哈希、MIT 声明及改动范围见 [rugp-sources.json](../provenance/rugp-sources.json) 与 [MIT 通知](../provenance/licenses/MIT-rugp-extractor.txt)。已有 [RIO 格式资料](garbro/ArcFormats/rUGP/ArcRIO.md) 保留对象图及块算法证据，不是使用时的外部源码依赖。

测试：[tests/test_rugp.py](../tests/test_rugp.py)。覆盖上游固定向量、32 字节边界、低三位、显式密钥、原文及变长中文二进制载荷往返、头/帧跨窗口、坏校验、截断/溢出/预算、无引号及短帧、重复候选、严格编码、控制字节、重叠、拒绝覆盖和候选结果隔离。没有商业资源或逐游戏验证记录。
