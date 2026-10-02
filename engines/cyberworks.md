# Cyberworks：a0 的 S/T 长度块

## 识别与适用范围
- 本页对应 SExtractor 的 Cyberworks CSystem/a0 长度块分支。
- 不把所有 `.a0` 或所有 Cyberworks 文件视为同一版本。
- 输入是已取得的块流，没有额外容器层。
- 每个块以小端 u32 长度开始，该长度不含自身四字节。
- 来源接受的非零块长上限为 `0xffff`，参考模块保持此边界。
- 零长度是停止块流的显式尾部哨兵。

## 容器与剧本
- 本模块不解归档、不解通用压缩，也不检测游戏目录。
- 块内部 `S/T` 文本和其他 `M` 指令必须区别对待。
- 不应将整个文件按 UTF-16 解码后做正则替换。
- 外层块长、内层文本长、前后缀是三个不同结构部分。
- 返回成品是同一 a0 块流，不是游戏归档。

## 源码依据
- 仓库：SExtractor。
- 固定版本：`8d8d976fd04ae54e7c677705af937273d04a376a`。
- 许可：GPL-3.0。
- 文件：`src/extract_Cyberworks.py`。
- 符号：`initExtra`、`readFileDataImp`、`replaceEndImp`。
- 来源默认文本编码 UTF-16LE，存在 `readJIS/noTextLen` 等分支。
- 本模块用显式参数替代全局 ExVar，且不依赖来源运行时。

## Python 接口
- 模块：[cyberworks.py](../python/engines/cyberworks.py)。
- `Block(kind, prefix, text, suffix)` 保存精确块结构。
- `read_blocks(data, encrypted=True, s_has_length=True)` 返回块元组与 tail。
- `write_blocks(blocks, tail=b"", ...) -> bytes` 重建两层长度。
- `patch_blocks(data, replacements, ...) -> bytes` 按块序号替换文本 bytes。
- 非文本块也占序号；不能按“第几条对白”误当块序号。

## 使用示例
```python
from python.engines.cyberworks import Block, write_blocks, read_blocks
block = Block("T", b"T1234", "本文".encode("utf-16-le"), b"\xfe")
data = write_blocks((block,))
blocks, tail = read_blocks(data)
assert blocks[0].text.decode("utf-16-le") == "本文"
assert blocks[0].suffix == b"\xfe"
```

## S 块的真实边界
- S 前缀为一个字节 `0x53`。
- 有长度模式中，随后是 u32 文本字节长度。
- 本模块的加密 S 只接受长度小于 256 的明确分支。
- 密钥是长度低字节，逐字节 XOR 文本。
- 来源面对更长 S 使用未明确的空密钥分支，本模块不猜测。
- 文本之后直到外层块末尾的字节保存为 suffix。
- `s_has_length=False` 时，块内余下内容全部是文本。
- 无长度 S 必须显式 `encrypted=False`，不能自动套用加密。

## T 块的真实边界
- T 前缀固定保留五字节，包括 `0x54` 与四个不解释的字节。
- 之后的 u32 是 UTF-16 代码单元数量，不是 Unicode 字符数。
- 文本字节长度严格等于该数乘 2。
- 密钥为长度字段的低两字节，循环 XOR 文本。
- UTF-16 代理对占两个单元，不能按 Python `len(str)` 填长。
- 后缀独立保留，不算作译文，不能吞掉 `0xfe` 等控制字节。

## name/message 与姓名
- 块标签自身并未给出可靠的角色姓名字段。
- 默认保持 `name=None`，message 来源于调用方确认的文本区。
- T 的五字节前缀不能擅自当成姓名索引。
- 同一文本块的控制前后缀应随 sidecar 保存。
- 若项目存在姓名嵌入规则，应另建明确、可逆的文本层规则。
- 路径和非文本 M 块不能作为翻译对象。

## 回填、编码与坏输入
- 文本接口直接使用 bytes，调用方必须显式编码。
- 回写会重算 S 的字节长度、T 的单元长度和外层块长。
- 奇数长度 T 文本、错误前缀、M 被改成文本均拒绝。
- 文本长度超出块界、短头部、短长度字段均拒绝。
- 未知标签保留为完整 M 块，不尝试翻译其可打印字节。
- 非空 tail 必须以四个零字节开头。
- 截断不是 tail：无哨兵的残余字节会导致异常。
- 不扩增块数、不自动按换行拆成多条 S 指令。

## 部署限制与验证状态
- 已实现上述有限 S/T 变体的完整长度块重建。
- 加密 S 长度超过 255、未知变体或额外外层封装不在支持范围。
- 字体、JIS 替换、文本控制语法和调用语义未在此实现。
- 合成测试覆盖 S/T/M、UTF-16 代理对、后缀和零哨兵尾部。
- 覆盖无长度明文 S、变长 T 回写与空修改逐字节一致。
- 坏输入覆盖长度越界、错误头部、奇数 T 与 S 加密上限。
- 测试文件：[test_engines_secondary.py](../tests/test_engines_secondary.py)。
- 未对真实游戏进行启动与视觉验证；局部结构通过不等于部署通过。
