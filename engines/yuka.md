# Yuka：YKS002 类型化文本池

## 能力边界
- 状态：`partial / typed-script-roundtrip`。
- Python：`python/engines/yuka.py`。
- 当前只实现 YKS002，不把 YKS001 当作相同布局。
- UTF-8 字符串与八字节二进制数值使用不同重定位规则。
- 不扫描所有非 ASCII 或长字符串冒充对白。

## 识别与结构
- 签名必须为 `YKS002\0\0`，头长为 `0x30`。
- 头部记录 S1、S2、S3、S4 的位置和字节大小。
- 当前实现要求四区连续，且 S4 结尾恰好到 EOF。
- S1 是命令索引，S2 是操作数索引数组。
- S3 每项 `{type, f1, f2}`，共十二字节。
- S4 同时容纳 NUL UTF-8 字符串和八字节 INT/FLOAT 数据。
- `FFFFFFFF` 是无引用哨兵，不作为池地址。

## 类型证据
- 01 CMD 的 f1 为命令名；07 STRING 的 f2 为字符串。
- 05 INT、06 FLOAT 的 f2 为八字节二进制对象地址。
- 08 PARAM 通过 f2 指向 S2 操作数链。
- 0B VAR 的 f1 为变量名，例如选择项关联变量。
- 未知类型直接拒绝，避免漏修其潜在地址。
- 池越界、无 NUL、T/B 同址冲突和后缀重叠均不能写回。

## 提取 name / message
- 仅识别紧邻 `GraphicTextOut` 的 STRING，并检查附近 PARAM。
- PARAM 操作数链中第二个 INT 的值为 1 时判为名字。
- 其他第二个 INT 值对应本方言的正文输出。
- 从正文之前有限范围找独立 name，遇 `KeyWait` 停止。
- 选择项要求随后有限范围出现 `Select.Text` 前缀 VAR。
- 名字保留 `name_id`，正文保留 S3 `id`。
- 纯控制串不导出，不采用上游“长 ASCII/非 ASCII”兜底。
- PARAM 内嵌名字而非独立 STRING 的变体尚未实现。

## 回填与地址修正
- `rewrite_yks` 接收 `{已提取正文或名字 S3 编号: 文本}`。
- 相同池偏移共享译文，冲突翻译会拒绝。
- 译文必须保留已识别的 `@x(...)` 控制码序列。
- 按类型建立池对象清单，变长重建时保留未引用 gap/尾部。
- 修正所有 T/B 类型池地址，不改 I/L 类型索引和字面值。
- 八字节 INT/FLOAT 内容不做 UTF-8 解码或文本替换。
- 更新 S4 字节大小，S1/S2 与 S3 项数保持不变。
- 翻译字符串若同时承担命令名等非对白角色或未审核别名则拒绝。

## Python 示例
```python
from python.engines.yuka import extract_yks, rewrite_yks
records = extract_yks(yks_bytes)
changes = {records[0]["id"]: "合成試験"}
rebuilt = rewrite_yks(yks_bytes, changes)
```
- 名字需要改写时，使用实际返回的非空 `name_id`。
- 不允许自行把资产节点编号塞进替换表。

## 部署条件与缺失阶段
- 本实现从裸 YKS002 开始，不负责外层 DAT/归档。
- YKS001 与 v1.1 在来源中有独立脚本，只作资料线索。
- 尚缺 PARAM 内嵌名字、其他输出命令与动态栈语义。
- 尚缺游戏内字形、排版、选项长度、所有分支验证。
- 不应把规范连续布局扩展为未知重叠池或加密变体。
- 结构变化后的外部索引、校验和、重封条件须独立核实。

## 来源、许可与测试
- SExtractor 提交 `8d8d976fd04ae54e7c677705af937273d04a376a`。
- 主源码：`tools/Yuka/yks_text_v2.py`。
- 版本说明：`tools/Yuka/README.md`。
- 上游署名：瑜瑜、Steins;Gate；来源仓库 GPL-3.0。
- 改编保留类型 schema，去除 CLI、文件 IO 和宽泛文本兜底。
- 已测名字/正文/选择项关联、T/B 地址重建、INT 二进制不变。
- 已测未引用 gap、控制码、未知类型及 YKS001 拒绝。
- 测试：`tests/test_engines_tools_b.py`，只有合成节点和自写文本。
