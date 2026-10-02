# ScenePlayer：PMX 剧本归档

## 能力边界
- 状态：`partial / container-only`。
- Python：`python/archives/sceneplayer.py`。
- 支持 PMX 的整体 zlib/XOR 包装和成员表重建。
- 虽然来源称它为剧本归档，本页仍未实现内部剧本语义。
- 不提供通用对白提取或二进制字符串回填。

## 识别与包装顺序
- PMX 没有可靠的固定四字节明文魔数。
- 来源读取器结合 `.pmx` 后缀与首字节 `0x78 ^ 0x21` 判断。
- 本模块检查首字节 59h，再验证整个 zlib 结构和索引。
- 解包顺序为逐字节 XOR 21h，然后 zlib 解压。
- 封包顺序相反：先构造原始内容、zlib 压缩，再 XOR 21h。
- 不能把成员内脚本误当成还需要再次 XOR 的压缩流。

## 解压后布局
- 第一个 u32 是成员数量。
- 后续每项 `0x24` 字节：三十二字节 NUL 文件名和 u32 大小。
- 成员数据紧接整个索引区，按相同顺序连续排列。
- 没有每个成员的显式地址字段，地址来自累计大小。
- 每个文件名字节长度最多 31，不能按 Unicode 字符数截断。
- 源 Python 使用 UTF-8 名字，接口默认遵循此写入方言。
- 已核实 CP932 名字的项目可显式传 `name_encoding`。

## 容器到剧本
- `unpack_pmx` 返回有序 `(name, bytes)` 列表。
- 不根据文件名或文字比例自动生成翻译任务。
- PMX 解包只完成容器阶段。
- 下一步需要实际成员的剧本格式、编码和引用证据。
- 若成员是纯文本，也应先确认命令和对话边界。

## name / message 与控制码
- 索引中的 name 是成员名，不是人物名。
- 当前没有 name/message/choice 提取 API。
- 对脚本内容完全按 bytes 保留，不变更控制码。
- 内部字符串长度、地址、校验和不由容器函数处理。
- 缺少这些证据时，不应该执行文本层替换。

## 真实重封与边界检查
- `pack_pmx` 使用已确认的顺序生成计数、名字、大小表。
- 拒绝重复、绝对/穿越路径与超长编码名。
- 解压默认总上限 64 MiB，不直接无限制 inflate。
- 校验流 EOF、压缩尾部、实际索引长度和成员累计终点。
- 所有输出在内存中返回，没有磁盘路径副作用。
- 重压缩结果可能与原流不同，应比较解压后的结构和成员。

## Python 示例
```python
from python.archives.sceneplayer import pack_pmx, unpack_pmx
arc = pack_pmx([("a.txt", b"synthetic"), ("b.txt", b"fixture")])
items = unpack_pmx(arc)
assert items[1][0] == "b.txt"
```
- 真项目中的 `items` 必须保持原始成员排序。

## 部署条件与未实现阶段
- 缺少成员语法、名字/正文/选择项抽取与回填。
- 缺少 PMA、PMP、PMW 等其他资源格式支持。
- 缺少不同命名编码版本的自动判定。
- 字体、文本编码、换行和游戏资源优先级需要外部确认。
- 有效 PMX 文件不等于游戏一定接受被修改的脚本。

## 来源、许可与测试
- SExtractor 提交 `8d8d976fd04ae54e7c677705af937273d04a376a`。
- 核心源码：`tools/ScenePlayer/pmx_pack.py`。
- 上游署名 Steins;Gate；来源仓库 GPL-3.0。
- 只读核对 GARbro-Mod `ArcFormats/ScenePlayer/ArcPMX.cs`。
- GARbro 提交 `bc26d991ef5cdc0e1ecb32122ee9a48c3375750c`，MIT，morkt 2017。
- Python 结构依据 SExtractor 重写，未调用任何 C# 运行时。
- 已测 XOR/zlib 顺序、连续成员、编码名上限、截断和解压预算。
- 测试 `tests/test_engines_tools_b.py`，只含合成资源。
