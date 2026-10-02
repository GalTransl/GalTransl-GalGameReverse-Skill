# Tanaka：SCB1 模板重封与 BIN 文本记录

## 模块分工

| 层 | 模块与接口 |
|---|---|
| 归档 | [archives/tanaka.py](../python/archives/tanaka.py)：`parse_scb1`、`repack_scb1` |
| 脚本 | [engines/tanaka.py](../python/engines/tanaka.py)：`parse_text_record`、`rewrite_text_record` |

按下述版本与阶段限制调用；成员 codec 或索引子集不等于完整解包器。

## 能力边界
- 状态：`partial / container-and-isolated-record`。
- Python：`python/engines/tanaka.py`。
- 覆盖 SCB1 变长成员重封以及已隔离文本记录长度修正。
- 不包含 ARCG 变体和完整剧本 VM。
- 不把外层归档偏移与内部剧情跳转混为一谈。

## SCB1 结构识别
- 来源从文件 `0x1C` 的 u32 读取索引区绝对地址。
- 该布局是主要证据，来源读取器没有可推广的签名检验。
- 索引项从 u32 成员绝对地址开始，零地址终止索引。
- 紧接一字节名称长度；实际名称占用值减一字节。
- 名字以 CP932 解码，末尾 NUL 去除。
- 成员边界由下一项地址确定，最后一项到 EOF。
- 当前要求索引顺序与成员物理顺序一致且名称唯一。

## SCB1 重封
- `parse_scb1` 返回成员名字、原数据和索引字段位置。
- `repack_scb1` 以原包作为显式模板。
- 原头部、索引区大小、名字及第一个成员前的填充保持。
- 按旧条目顺序选择替换数据或原数据。
- 重写每个索引项的绝对地址，不增加删除成员。
- 未知替换名字、异常索引、反向地址全部拒绝。

## 内部文本规则
- `_BIN_Tanaka` 以 `02 0A` 作为分段线索。
- 当前记录 API 接收已经隔离的匹配记录，不包含分隔符。
- 25h 是名字形态，09h 是正文形态。
- 24h 形态在文本前还有四字节零参数。
- 第一字节为来源 `preLen=1` 的存储长度。
- `preLenStrict=False`，不能假设它等于纯文本字节数。
- 默认严格 CP932，并限制为来源明确的字节范围。

## name / message 与回填
- `parse_text_record` 给出 role、text 和正文起点。
- 名字必须以来源要求的双字节前导范围开始。
- `rewrite_text_record` 用原长度加编码后的字节差修正长度。
- 保留 opcode、四字节参数和末尾 NUL。
- 溢出一字节或落到不支持的 opcode 会拒绝。
- 内部记录变长还需要外部完整脚本地址修正，本模块未实现。

## Python 示例
```python
from python.archives.tanaka import parse_scb1, repack_scb1
members = parse_scb1(original_scb)
rebuilt = repack_scb1(original_scb, {members[0]["name"]: rebuilt_member_bytes})
```
```python
from python.engines.tanaka import rewrite_text_record
new_record = rewrite_text_record(isolated_record, "合成試験")
```
- 第二个示例产生局部记录，不能跳过内部脚本重布局直接部署。

## 部署条件与未实现阶段
- 来源另有 `ARCG_pack.py`，与 SCB1 不同，未在本模块实现。
- 缺少容器版本自动识别和文件级签名的可靠推广。
- 缺少消息/名字配对、连续段落和选择项语义。
- 缺少整个脚本的跳转、长度汇总、控制码字典和引用修正。
- 外层重封不能修复内部脚本已经错误的指针。
- 字体、编码和游戏运行验证仍需另外完成。

## 来源、许可与测试
- SExtractor 提交 `8d8d976fd04ae54e7c677705af937273d04a376a`。
- `tools/Tanaka/SCB1_unpack.py`、`SCB1_pack.py`。
- 文本证据：`src/reg.yaml` 的 `_BIN_Tanaka`。
- 长度差逻辑对照 `src/extract_BIN.py`。
- 来源仓库 GPL-3.0；保留 satan53x / SExtractor 贡献者归属。
- 合成测试覆盖原包模板、成员增长后的后一偏移修正。
- 另测文本 opcode、名字角色、长度差和不支持指令拒绝。
- 测试 `tests/test_engines_tools_b.py`，没有商业剧本或 EXE 运行。
