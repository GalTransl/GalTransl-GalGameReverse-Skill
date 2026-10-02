# Hexenhaus：NORI 的 XOR53 固定槽

## 识别与适用范围
- 候选剧本通常交给 HexenHaus `.bin` 分支处理。
- 原始文件必须以 ASCII `NORI` 开头。
- 来源在确认原始签名之后，将整个文件逐字节 XOR `0x53`。
- 因而解密后的开头不再是 `NORI`，这不是校验失败。
- 解密数据中的 `_beginrp` 是后续扫描锚点。
- 文本扫描从该标记起点加 16 字节开始。
- 本页明确保留来源的两字节扫描启发式，不冒称完整 VM 解析。

## 容器与剧本
- 来源把归档处理放在 `src/scripts/hexen_haus/archive/`。
- ARCC/ODIO/WAG 分支不等于本页的 NORI 字符串布局。
- 应先从容器取得 BIN，保留原始字节作为唯一回填基准。
- 本模块不读取压缩包，不调用来源程序，不修改归档索引。
- 固定槽结果只能回写对应 BIN，归档更新属于另一阶段。

## 源码依据
- 仓库：msg-tool。
- 固定版本：`f72716cee88554d40c1cdface2812493b14ca653`。
- 许可：GPL-3.0-or-later。
- 文件：`src/scripts/hexen_haus/bin.rs`。
- 符号：`BinScript::new`、`extract_messages`、`import_messages`。
- 来源 writer 对超长译文会警告后截断。
- 本参考故意不继承截断行为，超出字节容量一律报错。

## Python 模块
- 模块：[hexenhaus.py](../python/engines/hexenhaus.py)。
- `read_slots(data, encoding="cp932") -> tuple[Slot,...]`。
- `Slot` 保存 `offset/capacity/text`，offset 是整文件绝对字节偏移。
- `patch_slots(data, replacements, encoding="cp932") -> bytes`。
- replacements 的键是解析后的槽序号，不是随意指定的偏移。
- `split_name(text)` 只拆同槽内 `姓名「正文`。
- 所有函数均为内存操作，导入时不访问磁盘。

## 使用示例
```python
from python.engines.hexenhaus import read_slots, patch_slots, split_name
# original 是调用方已取得的 NORI 原始 bytes。
slots = read_slots(original)
view = [split_name(slot.text) for slot in slots]
# 显式挑选一个槽；这里不把姓名自动搬到相邻槽。
patched = patch_slots(original, {0: slots[0].text})
assert len(patched) == len(original)
```

## 真实扫描算法
- 扫描单位为两个解密后字节。
- 任一对应位置遇到 `0x53` 时，来源将其视为槽分隔线索。
- 第一字节为分隔值时，对累计文本末尾还实施两字节尾部检查。
- 末尾不是 `」`、`。`、`』` 时可能剔除最后两字节。
- 第二字节为分隔值的分支不做同样尾部剔除。
- EOF 累积内容也按来源规则去掉尾部两字节。
- 长度不大于两字节的片段不导出。
- 因此短文本、ASCII 结构及未知作品存在漏提取的明确风险。

## 输入输出边界
- 缺签名、缺标记、标记不足 16 字节、奇数字节流均拒绝。
- 字符串严格按指定编码解码，非法编码不会替换为问号。
- 回填只接受重新解析出的合法槽序号。
- 修改区间严格限制在 `offset .. offset+capacity`。
- 其他数据、文件总长、加密头部均保持原样。
- 译文变短使用 ASCII 空格填满槽，不移动任何后续数据。

## name/message 与姓名
- 来源会把没有内嵌姓名的引号对白，与前一条文本尝试合并。
- 该行为可能误吞上一段旁白，本模块不自动照搬。
- `split_name` 在第一个 `「` 前确有文本时才返回姓名。
- `「` 起头的槽保持 `name=None`，不推断跨槽人物名。
- sidecar 应保存槽序号、容量、原文、分割方式和原始哈希。
- 翻译姓名后仍必须满足同一个固定槽容量。

## 回填、编码与控制码
- 容量是编码后的字节数，不是字符数。
- 超容量抛出异常，绝不自动裁短、替换未知字符或降级编码。
- 明文中的 `0x53` 会与启发式分隔机制冲突，因此拒绝。
- NUL 也不允许作为译文数据。
- CP932 是默认而不是字体兼容保证；需要其他编码时显式传参。
- 保留原作引号、句末标点、控制片段与命名变量。
- 短译文的填充可能改变下一次启发式提取的尾部判断。
- 因此以原文件与 sidecar 槽界为回填依据，不以译后重新猜槽为唯一证据。

## 部署限制与验证状态
- 已实现 NORI XOR、来源槽扫描和受限固定容量回写。
- 未实现 VM 结构解析、容器重包或跨槽扩容。
- 合成测试检查 XOR、原样回写、等长替换和总长不变。
- 测试包含签名错误、缺锚点、奇数字节、超长与分隔值冲突。
- 示例等长译文保留尾部标点，能再次提取出预期正文。
- 测试文件：[test_engines_secondary.py](../tests/test_engines_secondary.py)。
- 未做真实游戏启动验证；来源启发式命中不能视为全覆盖。
