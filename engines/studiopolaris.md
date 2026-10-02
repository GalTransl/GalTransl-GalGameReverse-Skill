# StudioPolaris：已解密 SCD_ 字节码

## 能力边界
- 状态：`partial / decrypted-script-roundtrip`。
- Python：`python/engines/studiopolaris.py`。
- 支持来源表中明确列出的 SCD_ 指令长度及文本块。
- 包含正文变长后的内联跳转、头部标签重定位。
- 不运行 `scddecompress.exe`，不加载上游 `opcode.py`。

## 识别与结构
- 四字节签名为 `SCD_`。
- 文件 `0x04` 处 u32 是代码区绝对起点。
- 从 8 至代码区起点是重复的 `u32 目标 + CP932 NUL 标签名`。
- 标签和跳转存储的是相对代码区的偏移。
- 解析时逐条推进指令，不在任意字节间扫描字符串。
- 未知指令、未终止字符串和越界操作数一律失败。
- 文件上限 64 MiB；外部解密结果不合规则不继续回填。

## 文本和其他操作数
- opcode `00` 是 TEXT，可含多个以双 NUL 分隔的正文段。
- opcode `01/02` 带类型化引用，字符串引用不是自动对白。
- opcode `04` 是跳转族，随后是子码和 u32 目标。
- opcode `05/06` 的比较/运算子码做范围校验。
- 来源表列出的单字节 statement 原样保留。
- `SHOW_NAME` 等语义不等于本模块已经恢复了栈上的名字参数。

## 提取 name / message
- `extract_scd` 只提取 TEXT 指令的字符串参数。
- 多个文本段用逻辑 `\n` 连接为一条 message。
- 返回的 `offset` 是旧代码区中的指令起点。
- 不自动抽取 `PUSH_REF STRING` 内的路径、变量或名字。
- 因栈流分析未实现，不输出猜测的 name。
- 选择肢中经栈传递的字符串也不在保证范围内。

## 回填与地址修正
- `rewrite_scd` 接收 `{旧 TEXT 偏移: 新 message}`。
- 新 message 的逻辑换行编码回多段 TEXT。
- 第一遍生成每条新指令并构建旧起点到新起点映射。
- 第二遍修正每个已解析跳转及所有头部标签目标。
- 目标必须原先就落在已解析的指令边界上。
- 不修改头部标签名、其他操作数或外部资源字符串。
- 空段、NUL 和 CR 会造成方言歧义，替换时拒绝。
- 已知指令无改写路径可做到字节完全一致。

## Python 示例
```python
from python.engines.studiopolaris import extract_scd, rewrite_scd
records = extract_scd(decrypted_scd_bytes)
changes = {records[0]["offset"]: "合成試験"}
rebuilt = rewrite_scd(decrypted_scd_bytes, changes)
```
- 示例从已解密剧本开始；没有任何 EXE 调用。
- 大文件应先验证全文件解析与空回填一致。

## 部署条件与未实现部分
- 源 README 指定反编译前仍需解密，本模块没有该阶段。
- 尚缺外层打包/加密、栈式 name/choice 语义恢复。
- 尚缺 TEXT 内特定作品控制码的完整词法。
- 未经字体/编码支持验证，换成 GBK 不会自动获得中文显示。
- 来源中低/中置信度 statement 的意义仍需真实 VM 证据。
- 不能把结构通过当成所有分支和存档的游戏内验证。

## 来源、许可与测试
- SExtractor 提交 `8d8d976fd04ae54e7c677705af937273d04a376a`。
- 源码：`tools/StudioPolaris/disassembler.py`、`assembler.py`。
- 长度/子码表：`tools/StudioPolaris/opcode.py`。
- 路线：`tools/StudioPolaris/README.md`；上游署名 Steins;Gate。
- 来源仓库 GPL-3.0；未复制污染 stdlib opcode 的加载逻辑。
- 合成测试覆盖头标签与跳转同步变长、资源字符串排除。
- 另测非边界目标、未知 opcode 和歧义空段拒绝。
- 测试：`tests/test_engines_tools_b.py`；没有解密 EXE 或游戏运行。
