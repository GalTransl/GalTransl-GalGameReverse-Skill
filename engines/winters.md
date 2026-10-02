# Winters：IFP 无遮罩子集与 ISD 尺寸条件

## 模块分工

| 层 | 模块与接口 |
|---|---|
| 归档 | [archives/winters.py](../python/archives/winters.py)：`pack_ifp`、`unpack_ifp` |
| 脚本 | [engines/winters.py](../python/engines/winters.py)：`pad_isd_to_original` |

按下述版本与阶段限制调用；成员 codec 或索引子集不等于完整解包器。

## 能力边界
- 状态：`partial / container-only`。
- Python：`python/engines/winters.py`。
- 实现可验证的 IFP 稀疏索引布局与成员重封。
- 保留 DAT 路线关于 ISD 不能增长的部署条件参考。
- 没有 ISD 剧本 writer，也不支持全部 Winters 包格式。

## IFP 识别
- 十六字节头为 `IAGS_IFP_01     `。
- `0x10..0x1F` 四个 u32 依次为 1、10h、8000h、0。
- 当前子集严格检查这些字段，未知版本拒绝。
- 数据固定起点为 `0x8010`。
- 索引布局不是从一个地址开始密集存放全部条目。

## 稀疏索引规则
- 第一个索引项位于 `0x20`。
- 第二个及后续项从 `0x660` 开始。
- 每项十六字节：u16 type、u16 mask_type、u32 offset、u32 size、u32 mask_size。
- 全零索引项表示结束。
- 当前不支持 mask_type/mask_size 非零的遮罩成员。
- `pack_ifp` 要求显式 type，不靠未知扩展名默认猜 script。
- 索引和结束项必须在数据区之前装得下，否则拒绝。

## 容器到剧本
- `unpack_ifp` 返回有序 `(type, bytes)`。
- 15h 是来源的 script 类型线索，仍非内部文本语法证明。
- BMP/PNG 等其他类型可能共存，不能全部当文字解码。
- ID/顺序是资源索引，必须保持原游戏对应关系。
- 本参考不制造成员名或自动按 `#编号` 对名字排序。

## name / message 规则资料
- `_BIN_Winters` 预设按 CRLF 分隔成员文本。
- IFP 路线通常从成员 `u32@0x0C` 给出的区域开始。
- DAT 路线预设改用 `u32@0x10`。
- 预设有名字加 `「` 和 NUL 后文字等候选形态。
- 这些模式尚不足以证明完整指令边界，本页不提供伪对白 writer。
- 也不在任意数据里扫描名字和 message。

## 重封与尺寸条件
- IFP writer 重建每个绝对偏移与成员大小。
- 保持输入条目顺序，所有数据从 8010h 顺次连接。
- `pad_isd_to_original` 只允许新 ISD 不大于旧分配尺寸。
- 不足部分用零补齐，超过则拒绝。
- 该补齐函数不是脚本重定位，不会修好已错误的内部地址。
- 来源明确 DAT 路线需要控制原始 ISD 大小，不能忽略此条件。

## Python 示例
```python
from python.archives.winters import pack_ifp, unpack_ifp
from python.engines.winters import pad_isd_to_original
arc = pack_ifp([(0x15, b"synthetic script")])
assert unpack_ifp(arc)[0][0] == 0x15
padded = pad_isd_to_original(b"new", original_size=8)
```
- 合成 script bytes 不代表真实 ISD 方言。

## 部署缺口与注意点
- 缺少 CAPYBARA DAT writer 和其他 Winters 容器变体。
- 来源 DAT 写头字符串与注释长度有疑点，未盲目照抄推广。
- 缺少 ISD 完整解析、name/message 配对、跳转和控制码。
- 缺少遮罩成员、特殊索引项和原包未知头字段保留。
- 字体、编码、换行、资源优先级以及存档兼容性均未验证。
- 仅通过容器合成测试不能判定真实游戏可加载。

## 来源、许可与测试
- SExtractor 提交 `8d8d976fd04ae54e7c677705af937273d04a376a`。
- 主要源码：`tools/Winters/ifp_pack.py`、`bytes_pad.py`。
- 限制证据：`tools/Winters/README.md`、`dat_pack.py`。
- 文本线索：`src/reg.yaml` 的 `_BIN_Winters`。
- 上游署名 Steins;Gate；来源仓库 GPL-3.0。
- 合成测试验证 20h/660h 双索引位置、8010h 数据起点。
- 另测显式类型、遮罩拒绝、索引容量和 ISD 超长拒绝。
- 测试：`tests/test_engines_tools_b.py`，无真实游戏运行。
