# Unison / Softpal Lazy：VAL 分离式字符串池

## 能力边界
- 状态：`partial / reviewed-text-pool-roundtrip`。
- Python：`python/engines/unison.py`。
- 基于来源 Unison 工具中的 Softpal Lazy VAL 布局。
- 不泛化为全部 Unison 或 Softpal 引擎版本。
- 必须提供经过外部确认的 DISPLAY_TEXT 指令起点。

## 文件布局
- 九字节头的前三字节是小端 u24 代码区字节数。
- 接下来三字节是 u24 字符串偏移表项数。
- 最后三字节意义未完全确认，逐字节保留。
- seg_A 是字节码；seg_B 是 u32 相对字符串池偏移表。
- seg_C 是 NUL 结尾字符串及可能的未索引尾部。
- 指令使用字符串索引，不直接使用池内字节地址。
- 索引数、区域边界、每个 NUL 终止符都先检查。

## 语义确认和误报
- 已知正文指令形式为 `DD 00 00 00 + u16 strIdx`。
- 已知 `83 00 + u16 strIdx` 是资源/脚本引用。
- 上游指出在参数里按字节扫描 DD 会产生假命中。
- 因此这里不把任意 `DD 00` 或任意非 ASCII 字符串当正文。
- `sites` 必须是独立语义分析确认的指令起点列表。
- 当前代码检查每个 site 的完整 type-zero 形式和索引范围。

## 提取 name / message
- `extract_val` 对已验证引用的字符串索引去重。
- 输出 `site`、`index`、`message` 和空 name。
- 不做上游跨若干条目的引号平衡合并。
- 没有名字池证据时，不从对话内容猜角色。
- 默认严格 CP932，不吞错误字节。
- 原始池中的路径和系统项不会因可读而被导出。

## 回填池算法
- `rewrite_val` 只接受已审核正文索引的替换。
- seg_A 不动，未知头部三字节不动。
- 按旧池偏移排序重建不同对象，修正 seg_B 每个索引。
- 精确保留对象之间的 gap 和池尾未索引 bytes。
- 共享起点采用同一新对象；冲突译文、未审核的别名索引必须拒绝。
- 后缀式重叠对象不支持，因为其引用语义不能安全推断。
- 不能插入 NUL，低位控制字节序列必须保持。
- 由于代码引用索引，单纯池变长不需要改代码跳转。

## Python 示例
```python
from python.engines.unison import extract_val, rewrite_val
records = extract_val(val_bytes, sites=reviewed_instruction_sites)
rebuilt = rewrite_val(val_bytes, {records[0]["index"]: "合成試験"},
                      sites=reviewed_instruction_sites)
```
- 不要把 `bytes.find(b"\xDD\x00")` 的结果直接当 reviewed sites。
- 输出是 VAL bytes，不是 VCT 归档。

## 部署条件与缺失阶段
- 来源还有 `vct_extract.py`、`vct_pack.py`，本参考未实现该容器。
- 缺少完整反汇编、其他文字输出 opcode、资源/正文共享冲突分析。
- 索引池重建要求文本对象边界不重叠。
- 所有修改过的字形和代码页仍需引擎侧支持。
- 不能假定 GBK 参数等同已经改好引擎 DBCS 分支。
- 缺少游戏内分页、姓名、选择项、存档验证。

## 来源、许可与测试
- SExtractor 提交 `8d8d976fd04ae54e7c677705af937273d04a376a`。
- `tools/Unison/lazy_common.py`：u24 布局、引用形态和误报说明。
- `tools/Unison/val_extract.py`：索引去重与上游合并行为。
- `tools/Unison/README.md`：完整容器/文本路线线索。
- 上游署名 Steins;Gate；来源仓库 GPL-3.0。
- 合成测试验证 seg_A 不变、偏移增长、未知头部与池尾保留。
- 资源索引和非 DISPLAY_TEXT site 的回填会拒绝。
- 测试 `tests/test_engines_tools_b.py`；没有真实 VM 执行。
