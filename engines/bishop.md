# Bishop / LiosGame GSC：固定头段表、NUL 字符串与 GBK 回写

> 能力层级：`script-header-string-spans`。这是独立算法参考，不是完整引擎支持承诺。

## 识别与适用范围
- GSC 没有可靠魔数，不能按扩展名或日文正则认定为本格式。
- 头部是一组有符号 32 位段长；任一段越界都会让字符串段错位，必须以长度自洽作为识别条件。
- 参考实现的导出路径只处理前两段、字符串段和尾部四段；本模块同样只做这一层。
- 尾部四段只按长度跳过，不解释指令含义。
- 不包含图片、音频或归档解包；GSC 是单个脚本文件。

## 头部布局
| 偏移 | 含义 |
|---|---|
| 0x00、0x04 | 两个未解释的 32 位字 |
| 0x08 | 段 1 字节长度 |
| 0x0C | 段 2 字节长度 |
| 0x10 | 字符串段字节长度；为 0 时拒绝 |
| 0x14 | 段 3 字节长度 |
| 0x18 | 段 4 元素个数，字节长度是该值的两倍 |
| 0x1C | 段 5 字节长度 |
| 0x20 | 段 6 字节长度 |

- 段顺序为段 1、段 2、字符串段、段 3、段 4、段 5、段 6，全部小端。
- 字符串段起点为 `36 + 段1 + 段2`。
- 所有长度必须非负且完整落在文件内；参考实现对越界读取静默取剩余字节，本模块报错。

## 字符串与位置
- 字符串段长度为 1 时参考实现直接返回空表，本模块保留该分支，不再解析尾部段。
- 长度大于 1 的字符串段由 NUL 分隔；连续 NUL 表示空槽，不产生条目。
- 每条记录绝对偏移 `position`、原始字节长度 `maxlength` 和按声明编码解码的 `text`。
- `maxlength` 不含终止 NUL。
- 默认编码 CP932；导出其他编码时由调用方显式传入。
- 末尾残段没有 NUL 终止时报错；参考实现会静默丢弃该残段。

## 回写约束
- 回写只替换字符串段内的字节，段长、段起点和其他段不变。
- 目标编码默认 GBK（代码页 936）。
- 新文本短于原跨度时补 `0x20`；等长时直接写入。
- 新文本长于原跨度时报错；参考实现会截断，可能切断多字节字符，本模块不复制该行为。
- 空译文和含 NUL 的译文拒绝。
- 写入基于输入副本，调用方负责保存到新文件并保留原档。

## Python 调用
```python
from python.archives.bishop_gsc import apply_gsc_texts, open_gsc

raw = open("script.gsc", "rb").read()
script = open_gsc(raw)
texts = [entry.text for entry in script.strings]
patched = apply_gsc_texts(raw, script, texts)
```

- 模块：[bishop_gsc.py](../python/archives/bishop_gsc.py)。
- `open_gsc(data, encoding="cp932") -> GscScript` 读取段表并切分字符串。
- `apply_gsc_texts(data, script, texts, encoding="gbk") -> bytes` 按原跨度回写。

## 源码、许可与改写
- 依据：翻译肋手 v4.9D 的 `GameRes.LiosGame.ArcGSC`。
- 参考实现还提供 `parseStringByStruct`，导出路径没有调用；本模块不移植。
- 独立改写：显式边界、不原地改写输入、不静默截断。
- 同一工具的调用层把条目写成 `BishopExtra`（地址、最大长度）后回填；本模块直接暴露 `position/maxlength`。

## 验证状态
- 合成文件覆盖头部段长、段 4 半长度、空槽、GBK 短文本补位和等长回写。
- 拒绝空字符串段、越界段长、未终止尾串和非法编码字节。
- 测试文件：[test_bishop_gsc.py](../tests/test_bishop_gsc.py)。
- 未使用真实游戏文件，未运行游戏；测试通过不代表脚本执行或显示正确。
