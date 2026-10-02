# Ransel：BCD / BCL 配对归档

## 能力边界
- 状态：`partial / container-only`。
- Python：`python/archives/ransel.py`。
- 实现 BinaryCombineData 二进制内容与文本索引的同步重建。
- 不含内部文本方言、名字识别或剧本控制流。
- 不依赖原工具的 GUI、工作目录和 `PackName` 全局变量。

## 识别与配对
- BCD 从 `BinaryCombineData\0` 开始，共十八字节。
- BCL 首行为 `[BinaryCombineData]`。
- BCL 第二行给出对应 BCD 的文件名。
- 调用时必须显式传入 `archive_name`，并核查配对。
- 文件后缀 `.bcd/.bcl` 只能作为线索，不能替代签名和索引验证。

## 索引形态
- 每个成员是 `[成员名]`、十进制绝对偏移、十进制长度。
- 记录之间有空行；字符编码采用 CP932。
- 内容区在 BCD 签名之后连续连接成员。
- 封包根据每个成员 bytes 长度递增计算偏移。
- 不是字符数，也不是相对第一个成员的偏移。
- BCL 与 BCD 必须一起更新，否则旧索引会指向错误区域。

## 容器到剧本
- `unpack_bcd` 返回有序 `(name, bytes)` 列表。
- 名字作为元数据，不写入磁盘路径。
- 本模块不确认哪个成员是脚本、字体或图像。
- 需要外部格式识别继续解析成员。
- 不能把来源默认包名 `text` 当作通用语义证据。

## name / message 与回填
- 当前没有 name/message 提取 API。
- 归档索引里的 `name` 是文件名，不是角色名。
- 不使用全局 byte replace 或“可打印字符串”当对白 writer。
- 只有已经完成内部格式回填的成员 bytes 才能交给 `pack_bcd`。
- 容器重建不会改动成员内控制码或文本编码。

## 有界校验
- 成员计数上限十万，索引输入限制十六百万字节。
- 拒绝重复文件名、方括号/换行/NUL 注入。
- 偏移与长度必须是十进制数字。
- 当前读取子集要求成员连续排列，尾部没有未索引 bytes。
- 越界、截断、错误配对名称都会明确失败。
- 不运行目录选择对话框，不创建输出目录。

## Python 示例
```python
from python.archives.ransel import pack_bcd, unpack_bcd
bcd, bcl = pack_bcd([("a.bin", b"A"), ("b.bin", b"BB")],
                    archive_name="text.bcd")
items = unpack_bcd(bcd, bcl, archive_name="text.bcd")
assert items[1] == ("b.bin", b"BB")
```
- BCL 输出为 CP932 bytes，写盘时不再二次转码。
- 调用者保留原文件顺序，函数不按操作系统目录顺序猜排序。

## 部署条件与缺失步骤
- 缺少成员脚本语法、角色/正文/选项提取及控制流重定位。
- 缺少非连续布局、未知索引扩展字段的兼容实现。
- 若游戏依赖原 CRLF，调用者需核对 BCL 换行要求。
- 函数输出索引采用 LF，与来源 Python 文本层写法一致。
- 替换时必须同步部署 BCD 和 BCL，并先做无改写比较。
- 未进行游戏运行、字体、编码和存档兼容性测试。

## 来源、许可与测试
- 来源 SExtractor 提交 `8d8d976fd04ae54e7c677705af937273d04a376a`。
- 核心源码：`tools/Ransel/pack_bcd.py`。
- 保留 satan53x / SExtractor 贡献者归属。
- 来源仓库 GPL-3.0；本实现提炼成纯 bytes 函数。
- 已测十八字节头、成员偏移和十进制长度。
- 已测双文件往返、配对名不符和内容截断拒绝。
- 测试文件 `tests/test_engines_tools_b.py`。
- 没有原工具运行时、真实游戏或网络访问。
