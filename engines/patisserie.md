# Patisserie：OZ / OFST 归档

## 能力边界
- 状态：`partial / container-only`。
- Python：`python/archives/patisserie.py`。
- 实现有界解包和真实 DATA/DFLT 封包。
- 没有剧本 VM、name/message 提取或对白回填。
- 不把资源归档能够重建宣传为文本链路已完成。

## 识别线索
- 魔数 `OZ 00 01`，随后四字节 `OFST`。
- 文件 `0x08` 处 u32 是偏移表字节长度。
- 长度必须非零、四字节对齐且计数在上限内。
- 偏移表从 `0x0C` 起，每项一个绝对 u32 地址。
- 第一项必须紧接表尾，后续项严格递增。
- 本子集每个条目必须是 DATA 或 DFLT，未知封装拒绝。

## 归档结构
- DATA：四字节标记、u32 原始长度、原始 bytes。
- DFLT：四字节标记、u32 压缩长度、u32 解压长度、zlib 流。
- 成员名不在偏移表里，通常需要外部 `.lst`。
- `pack_oz` 接收已确定顺序的 bytes 列表，不自行排序。
- 写出所有成员后，每个绝对偏移按新块尺寸重算。
- 压缩后比原文更小才选 DFLT，否则写 DATA。

## 容器到剧本
- `unpack_oz` 只返回匿名有序成员。
- 外部文件名列表与条目编号的对应由调用者保留。
- 成员可能是音频、图片、脚本或其他资源。
- 即使能解压，也不能直接当 CP932 文本处理。
- 需要下一阶段识别成员格式和文本引用语义。

## name / message 状态
- 当前没有 name/message API。
- 不用任意 Unicode、汉字或 NUL 字符串扫描代替剧本解码。
- 不知道脚本控制码、字符串表和跳转格式时应停止自动回填。
- 修改一个已独立验证的剧本成员之后，才调用归档重封。

## 长度与安全边界
- 所有偏移、块长度和 EOF 都进行相互校验。
- zlib 解压使用上限，拒绝声明大小超额的块。
- 校验流终止、未消费数据、额外压缩流和实际输出长度。
- 默认总解压上限 64 MiB，可由调用方显式调整。
- 不解压到目录，不需要信任归档内文件名。
- 原始编码、文本控制码不在本容器模块中变换。

## Python 示例
```python
from python.archives.patisserie import pack_oz, unpack_oz
archive = pack_oz([b"synthetic", b"ABCD" * 100])
members = unpack_oz(archive, max_output=1024 * 1024)
assert members[0] == b"synthetic"
```
- 真正项目中必须复用原索引顺序和外部名字表。
- 此例证明归档算法，不提供商业剧本内容。

## 部署条件与缺失步骤
- 缺少 `.lst` / `lists.bin` 关联管理和文件名自动发现。
- 缺少所有剧本成员的 name/message/choice 语义层。
- 缺少原容器额外填充、未知块和版本变体支持。
- 重新压缩可能不同于原压缩流，不能要求压缩字节恒等。
- 游戏路径、资源优先级、字库和换行须独立验证。
- 不会读取参考仓库或调用 GARbro 运行时。

## 来源、许可与证据
- SExtractor 提交 `8d8d976fd04ae54e7c677705af937273d04a376a`。
- 核心源码：`tools/Patisserie/bin_pack.py`。
- 归属说明：`tools/Patisserie/README.md`，署名 Steins;Gate。
- 按来源仓库 GPL-3.0 许可进行函数化改编。
- 补充只读核对：GARbro-Mod `ArcFormats/Patisserie/ArcBIN.cs`。
- 补充提交 `bc26d991ef5cdc0e1ecb32122ee9a48c3375750c`，MIT，morkt 2016。
- 当前 Python 算法由 SExtractor 结构重写，不引入 C# 运行依赖。
- 合成测试 DATA/DFLT 混合、索引地址、重复偏移和解压预算。
- 测试文件 `tests/test_engines_tools_b.py`；无真实游戏运行。
