# U-GOS：.o 指针引用的字符串块

## 能力边界
- 状态：`partial / reviewed-pointer-pool-roundtrip`。
- Python：`python/engines/ugos.py`。
- 引擎名线索是 μ-GameOpertionSystem，不能等同任意 `.o`。
- 只覆盖来源 `o_tool.py` 确认的 opcode 长度和指针格式。
- 候选提取仍有内容过滤；不声称完整 VM 语义分析。

## 必需的外部边界
- 输入为已解包字节码及独立核实的 `code_end`。
- 只从零到 `code_end` 逐条读取已知指令。
- 不沿用上游把整个文件一直扫到 EOF 的做法。
- 未知 opcode 或截断操作数直接拒绝。
- 本子集要求被引用的字符串块位于代码区之后。
- 若代码/数据交错，必须先使用更完整的反汇编器，不可猜边界。

## 指针与块格式
- opcode 02 的字符串地址为 u32。
- opcode 12h 的字符串地址为 u16。
- opcode 22h 的字符串地址为 u8。
- 目标块是 `u16 字节长度 + 原始字符串载荷`。
- 校验指针宽度、目标、载荷长度和输入上限。
- 来源可移除的控制字节是 00、07、08、09、0A。
- 本实现仅接受这些控制字节位于载荷前后边缘。
- 中间夹控制码的块需要真实分段模型，因此拒绝而非删除。

## 提取 name / message
- `extract_o` 对指针目标去重，输出 `status="candidate"`。
- 路径扩展名、脚本控制前缀和纯 ASCII 候选被排除。
- 含 `「` 时，前缀按来源规则作为 name，剩余为 message。
- 没有左引号时不猜名字。
- 同时提供完整 `text`，回填使用完整文本而不是拼接猜测。
- 候选必须人工或外部语义复核，不能直接视作所有真实对白。

## 回填与指针修正
- `rewrite_o` 按原块起点接收新完整文本。
- 控制前后缀原样保留，译文不能插入控制字节。
- 变化块追加到 EOF，保留旧代码和旧池布局。
- 同一旧目标的全部已知指针别名同时指向新块。
- 指针宽度容纳不了新地址时整体失败，不返回半写坏结果。
- 新块长度超过 65535 时失败。
- 未变更的块不追加，空替换表字节完全一致。

## Python 示例
```python
from python.engines.ugos import extract_o, rewrite_o
records = extract_o(o_bytes, code_end=verified_code_end)
# 完整新文本包括必要的名字和括号；这里只用合成旁白。
rebuilt = rewrite_o(o_bytes, {records[0]["target"]: "合成試験"},
                    code_end=verified_code_end)
```
- `verified_code_end` 不是自动扫描得到的“第一个可打印字符串位置”。
- 不应把候选列表未经复核直接提交翻译。

## 容器与缺失阶段
- 来源另有 `det_tool.py` 的 DET 配对归档路线，本页未实现。
- 缺少完整 VM、未列出的引用 opcode、动态字符串表达式。
- 缺少代码区边界自动判定与内部控制码分段。
- 若还有未识别别名，追加式回填不能保证所有使用点同步。
- 字库、目标编码、游戏内换行及保存兼容性未验证。

## 来源、许可与测试
- SExtractor 提交 `8d8d976fd04ae54e7c677705af937273d04a376a`。
- 核心证据：`tools/U-GOS/o_tool.py`。
- 路线/贡献说明：`tools/U-GOS/README.md`。
- 上游标注 Cosetto 提供容器路线、朝比奈真冬提供批量扩展。
- Python 算法改编按来源仓库 GPL-3.0，保留贡献者归属。
- 合成测试覆盖共享 u32 指针同步、控制边缘、u8 溢出拒绝。
- 另测未知 opcode 与内部控制字节拒绝。
- 测试文件 `tests/test_engines_tools_b.py`；无原游戏运行。
