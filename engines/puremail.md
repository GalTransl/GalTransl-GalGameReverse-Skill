# PureMail：OBJ V1 / V2 索引文本池

## 能力边界
- 状态：`partial / indexed-string-roundtrip`。
- Python：`python/engines/puremail.py`。
- 支持可读源码明确描述的两种连续字符串表布局。
- 这是索引字符串回填，不是完整剧本 VM 语义识别。
- DAT 容器版本与 OBJ 版本相互独立，不允许自动绑定。

## 识别与布局
- OBJ 没有本模块确认的通用魔数，调用者必须指定 `version`。
- V1 每项为小端 `u16 地址 + u16 长度`，占四字节。
- V2 每项为小端 `u32 地址 + u16 长度`，占六字节。
- 第零项指向字符串之后的不透明区，并带原始长度字段。
- 第一条字符串地址除以索引步长得到索引项总数。
- 此推导必须整除，且至少包含不透明区项和一条字符串。
- 本实现只接受连续、不重叠、无别名的字符串区。
- 所有地址、大小、区段结尾均在输入内验证。

## 容器到剧本
- 来源还提供 `dat_repack.py` 和 `dat_repack_v2.py`。
- 本页不实现 DAT 解包/重压缩，也不运行这些原始入口。
- 先确认外层 DAT 版本，再独立确认每个 OBJ 的索引版本。
- Overflow 目录里的按变体工具不能与此结构混用。
- 输入是单个已解包 OBJ 的 bytes。

## 提取 name / message
- `extract_obj` 输出 `index`、`text`、`role="unclassified"`。
- 一基字符串索引对应原索引表第 1 项起的条目。
- 不把所有索引字符串自动标为正文。
- 名字、消息、资源名的区别需要调用者的额外语义证据。
- 默认 CP932 严格解码，解码失败不会静默忽略。
- NUL 及其他控制字符保留在字符串中，不使用含糊的转义回转。

## 回填算法
- `rewrite_obj` 接收 `{一基索引: 文本}`。
- 重编码后计算每项实际字节长度。
- 重建整个地址/长度索引，再顺序写出字符串。
- 第零项地址改为新字符串区结尾，长度字段保持原值。
- 不透明尾区从原始第零项地址至 EOF 原样保留。
- V1 地址超过 65535、任意字符串长度超过 65535 均拒绝。
- V2 地址使用 u32，不能让 Python 整数静默截断。
- 译文的低位控制字节序列必须与原文一致。
- 无修改的合成连续布局可字节完全一致。

## Python 示例
```python
from python.engines.puremail import extract_obj, rewrite_obj
# obj_bytes 是已经确认 V2 的原始 OBJ bytes。
records = extract_obj(obj_bytes, version=2)
# reviewed_index 必须是人工或外部语义分析确认的文本索引。
rebuilt = rewrite_obj(obj_bytes, {reviewed_index: "合成試験"}, version=2)
```
- 若原字符串含 NUL，替换字符串也必须保留相应控制序列。
- 不能把输出直接按另一种 OBJ 版本塞回 DAT。

## 部署条件与缺失步骤
- 尚缺 DAT 层重建、压缩和原始封包排序验证。
- 尚缺 OBJ 字节码中的名字/对白/选项角色判定。
- 尚缺非连续、重叠、共享或带内嵌地址的 OBJ 变体。
- 不能推断不透明尾区内是否还有未知绝对指针。
- 首次接入必须用真实版本做外部无改写比较与游戏验证。
- CP932 之外的目标编码只接受显式参数，不等于引擎已支持该编码。

## 来源、许可与测试
- SExtractor 提交：`8d8d976fd04ae54e7c677705af937273d04a376a`。
- 源码：`tools/PureMail/obj_processor.py`。
- 源码：`tools/PureMail/obj_processor_v2.py`。
- 路线说明：`tools/PureMail/README.md`。
- 上游署名 Steins;Gate，来源仓库许可 GPL-3.0。
- 去除了 CLI、目录默认值、文件 IO 和忽略编码错误的降级。
- 合成测试覆盖 V1/V2、尾指针修正、控制字节及地址溢出。
- 测试：`tests/test_engines_tools_b.py`，没有真实游戏部署结论。
