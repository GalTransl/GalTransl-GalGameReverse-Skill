# Mware：Squirrel literal 与引用级克隆

## 识别与适用范围
- VNTextPatch 的 Mware 分支以 `.nut` 为候选剧本扩展名。
- `.nut` 也可能是别种 Squirrel 源码/字节码，不能只看扩展名。
- 本页仅实现其 Squirrel v2 字面量编码和局部引用重建计划。
- 不提供全文件格式识别或 Squirrel VM 反汇编。
- 输入池范围与引用集合必须由完整结构分析先行建立。
- 正确目标是某个引用的文本，而不是整个文件中相同字节。

## 容器与剧本
- 资源归档、NUT 外壳、函数对象、literal pool 是不同层次。
- 本函数输入是已定位的 literal 对象或一个池的结构化值。
- 不能把归档字节直接当字面量流解码。
- 本模块不读取游戏目录，也不调用外部 Squirrel 程序。
- 返回池字节仍需要安装进原函数对象，并修复相关字段。

## 源码依据
- 仓库：VNTextPatch-net8。
- 固定版本：`d9c0fab7b72fdcf87d674ef12a84d3829c9188be`。
- 许可：MIT。
- 文件：`VNTextPatch.Shared/Scripts/Mware/SquirrelObject.cs`。
- 符号：`Read`、`Write`、`ObjectType`。
- 引用处理依据：同目录 `MwareScript.cs`。
- 关键符号：`MergeIntoLiteralPools`、`PatchLiteralPools`、`PatchLiteralReferences`。
- 来源已经区分 literal pool 值与具体引用操作数，不能退化成全局替换。

## Python 接口
- 模块：[mware.py](../python/engines/mware.py)。
- `read_literal(data, offset=0, encoding="cp932") -> (value, end)`。
- `write_literal(value, encoding="cp932") -> bytes`。
- `clone_translated_references(values, indexes, widths, replacements, ...) -> dict`。
- 返回 `values/indexes/pool`，分别是新池值、新引用索引、序列化池字节。
- replacements 的键是引用序号，不是 literal 索引。
- widths 明确描述每个引用操作数为 1 字节还是 4 字节。

## 使用示例
```python
from python.engines.mware import clone_translated_references
plan = clone_translated_references(
    ["same", 7], [0, 0, 0], [1, 1, 4], {0: "訳一", 1: "訳二"}
)
assert plan["values"] == ("same", 7, "訳一", "訳二")
assert plan["indexes"] == (2, 3, 0)
# 第三处未翻译的资源引用仍然看到原始 same。
```

## 真实字面量布局
- 每项首先读取小端 32 位类型标记。
- Null 标记为 `0x01000001`，没有后续载荷。
- Integer 标记为 `0x05000002`，载荷为带符号 i32。
- Float 标记为 `0x05000004`，载荷为 IEEE 754 binary32。
- String 标记为 `0x08000010`，后接 i32 字节长度与编码数据。
- 字符串是长度前缀，不以 NUL 结束，内部 NUL 可作为数据。
- 未知类型、负长度、短载荷会拒绝。
- Python bool 不作为整数 literal 接受，以避免隐式类型混淆。

## name/message 与姓名
- literal 标记只能说明它是字符串，不能证明它是对白。
- 来源依据反汇编识别出的引用类型区分姓名与正文。
- `<voice ... name='...'>`、段落与注释也是上层文本语义。
- 本模块不伪装已实现这些引用发现和文本区间分析。
- sidecar 应带函数/池身份、引用身份、旧 literal 索引和角色。
- 相同 literal 值被路径、命令和对白共享时必须按引用区分。

## 回填策略与地址限制
- 本参考采用更保守的 copy-on-write：每个改变的引用追加新 literal。
- 原池值不被覆盖，未见到的资源引用不会被连带修改。
- 译文与原文相同则无需克隆。
- 新索引超过 u8 范围的 1 字节引用立即拒绝，不截断索引。
- 4 字节引用也必须保持非负 i32 范围。
- 函数返回计划，不修改 NUT 中操作数的位置。
- 安装新池以后还需更新池计数、位移、函数结构与外壳长度。
- 来源涉及外壳 `8/0xc` 等位置的修补，本模块不擅自套到未知 NUT。

## 编码与控制码
- 默认严格 CP932，允许调用方显式指定已确认的编码。
- 未移植来源的动态编码猜测与自定义编码隧道。
- 字面量里的换行、注释、voice 标签不能随意抹去。
- 本模块不做段落换行或文本格式化，避免连带改动非对白部分。
- float NaN 载荷和编码别名在值级重建时可能规范化，不承诺任意池位元一致。

## 验证状态与缺口
- 合成测试覆盖四种类型、小端布局和长度边界。
- 重点测试同一个 literal 被多处引用时的独立翻译和资源保留。
- 覆盖未知 tag、负长度、bool 错类型与 u8 新索引溢出。
- 测试文件：[test_engines_secondary.py](../tests/test_engines_secondary.py)。
- 未完成全 VM 反汇编、引用发现、段落角色提取、完整 NUT writer。
- 没有真实游戏载入验证；此结果只能证明局部池计划成立。
- 不允许以全文件字符串替换填补这些缺口。
