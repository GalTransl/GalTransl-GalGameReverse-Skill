# GARbro 归档算法摘录的读取约定

按 [格式索引](../../catalog/garbro-archive-index.md)选择入口。资料摘录保留实际 C# 字段表达式与解码分支，没有执行 C#，也不是可以直接运行的脚本。无需访问外部源码；源路径仅记录出处。专用辅助算法通过各页链接随包提供，外部 key、方案库和游戏配套数据明确作为输入条件。

## 整数、字符串与位置

- `ArcView.View.ReadUInt16/32/64`、`ReadInt16/32/64`、`BinaryReader` 默认小端；`BigEndian`、`Binary.BigEndian` 表示交换/大端解释。必须先验证所读跨度完整。
- `uint`/`ulong` 算术分别按 32/64 位无符号溢出，`byte` 截为 8 位；`int` 有符号。旋转不能换成普通移位。偏移与预算检查应先提升到足够宽的整数，不能依赖溢出后的 placement。
- `ReadString(offset,width)`、`ReadCString(width)`、`Binary.GetCString` 默认按 CP932 读取有界 NUL 字节串，除非调用指定其他 Encoding；`Encoding.Unicode` 为 UTF-16LE。不允许有损解码，名称编码不自动等于剧情编码。
- `ReadInt32/UInt32()` 无参数形式使用流当前位置并推进；带位置的 View 读取不改变流位置。`Seek`、`Position`、`StreamRegion` 和 `base_offset` 决定真实基址，不能把不同流的位置相加。
- `ReadBytes` 必须核对实际读取长度；读取表前验证 `count*record_size`、索引区、名称区和数据区的完整关系。

## 框架 API 的格式语义

| API | 实施时的含义 |
|---|---|
| `AsciiEqual` | 在指定字节位置比较 ASCII magic；默认位置 0；不负责证明其他结构 |
| `CheckPlacement(file_size)` | 检查成员偏移与尺寸是否落在文件内；独立实现还需排除索引区、溢出、冲突跨度等格式违规 |
| `Create<Entry/PackedEntry>` | 创建目录记录，推测的资源类型/后缀不是真实包内名字 |
| `PackedEntry.IsPacked/UnpackedSize` | 由入口赋值的压缩标记/声明尺寸；不要只看 Size 与 UnpackedSize 不同就自动解压 |
| `CreateStream(offset,size)` / `StreamRegion` | 只读取该有限子跨度，默认原样；默认 OpenEntry 也是原始跨度 |
| `PrefixStream(prefix,tail)` | 前缀 bytes 与尾流拼接；并不是对整个文件重复解密 |
| `Binary.CopyOverlapped` | 逐字节重叠复制，使刚输出字节可继续作为回指输入；不能改成先切片再复制 |
| `VFS`、`LookupGame`、`Query`、`KnownSchemes` | 文件发现/外部方案选择。改成安全路径下的显式配套文件和参数；没有数据时标明缺失，不调用 GUI，不执行游戏 |
| `ResourceScheme` / `Formats.dat` | 来源工具方案容器；禁止使用未知 BinaryFormatter 反序列化，参数须来自可审查的独立结构 |

## 通用压缩与密码

算法摘录中的 `name_list_parameter` 是显式传入的名称列表/列表标识，替代来源工具内置的逐游戏 `.lst` 资源路径；本包不复制这些列表或资源名。按该分支的索引哈希、signature 或校验选择匹配列表，缺少列表时保留哈希身份并报告无法还原原名，不能假称已取得真实名称。界面本地化文本不作为格式算法随包提供。

zlib、DEFLATE、BZip2、LZMA、Zstandard 等名称对应不同封装，不得因“都能解压”混用。验证输出预算、声明大小、EOF 和残留输入。调用中的 FrameSize、FrameFill、FrameInitPos、位序和跳过头长是方言规则，优先于库默认值。专用 LZSS、range、字典和密码实现见各页配套算法链接。

来源使用 SharpZipLib、SevenZip 等标准 codec API 时，可用可靠的相同格式库替代，但要保持参数和封装；它们不是要求使用者安装 GARbro 的 DLL。类型别名表明确短名称对应的类型/命名空间，专用读取流与解密算法仍以随包配套链接为准。

CRC32 默认为反射 IEEE 多项式 `0xEDB88320`，初态 `0xFFFFFFFF`、结果取反；`UpdateCrc` 接收显式内部状态，不能额外初始化/取反。Adler32 初态 s1=1、s2=0、模 65521，结果 `(s2<<16)|s1`。校验范围必须按调用的 start/count；某格式可选两种 checksum 不意味着所有格式都可忽略校验。

DES/AES/Blowfish/Camellia 等须匹配调用处的块模式、key 字节序、IV、填充和仅部分前缀加密的规则。方案参数存在不代表它适用于同族全部版本；成员密码、索引密码和剧情自身密码分别确认。

## 未覆盖边界

摘录不保留 GUI、资源注册、writer、媒体渲染和清理代码。若某归档的 OpenEntry 依赖媒体转换，须在适配时明确 raw 成员和渲染结果的区别；不能把去掉图像/音频转换当作已经完成那个转换算法。全部注册项包含多帧图像等特殊 ArchiveFormat，它们不因此变成剧情归档。

源码中的静默跳过、catch 回退、截断和 EOF 提前返回不得直接继承为“提取成功”。源代码列有函数但抛出 NotImplementedException 时，仍是来源缺口。所有源码级别证据均需经过独立有界实现、合成正反例和实际样本验证后才能更新支持声明。
