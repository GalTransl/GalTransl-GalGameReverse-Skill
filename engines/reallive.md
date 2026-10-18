# RealLive：SEEN 容器、文本 token 与换行指令片段

## 识别与适用范围
- GARbro 的 `ArcFormats/RealLive` 目录同时收录 Siglus、AVG32 和 Flix，源码目录名不能作为本引擎身份。`Scene.pck` 路线见 [Siglus](siglus.md)。
- RealLive 的完整剧本不是“找到字符串再替换”的文本文件。
- 来源处理的是已经准备好的 `.rl` 剧本字节。
- SEEN 等外层封装、解密/解压和 VM 指令需要各自的结构阶段。
- 本页给出 SEEN 容器的 section 还原，以及引号文本编码与函数调用换行的片段算法。
- 不声称能识别整个 RealLive 文件或重建所有 VM 地址。
- 任意扩展名、正则命中日文、引号成对都不能替代 VM 边界证据。

## 容器与剧本
- 打包文件、压缩脚本和反汇编后的代码范围不是同一种输入。
- 应由独立容器/剧本分析阶段取得有效代码与文本范围。
- 文本 token 模块不拆容器；SEEN 外层由 [reallive_seen.py](../python/archives/reallive_seen.py) 处理。
- 容器模块只还原 section 字节，不做 VM 反汇编、地址重定位或文本回填。
- 生成的片段只有安装到合法指令位置才有意义。
- 未修复地址前不能将变长片段写进游戏副本并宣称完成。

## SEEN 容器
- 头部 80000 字节；参考实现按 5000 条 `(u32 offset, u32 size)` 读取，`size` 为 0 的是空槽，头部其余字节在参考实现中未使用。
- section 内 `+32` 为原样前缀长度，`+36` 为解压后长度（0 表示尾段不压缩），`+40` 为使用外部 `KeyTable.mem` XOR 的字节数。
- 压缩尾位于 `offset + prefix`，先跳过 8 字节流头；控制位低位优先，1 为字面量，0 为 u16 回溯（低 4 位加 2 为长度，高 12 位为距离）。
- 解压后偏移 256..512（含）再与固定 16 字节表 XOR；窗口取自参考条件 `(uint)(index - 256) > 256`，尚未用真实样本核对。
- 密钥表由调用方提供；section 声明加密而未提供密钥时报错，不从固定路径读取 `KeyTable.mem`。
- `lz_compress` 是合法的字面量/回溯编码器，供重封包使用；不声称与原始压缩器的选择一致。
- `read_section` 输出前缀加解压明文，不解释 VM 指令。

## 源码依据
- 仓库：VNTextPatch-net8，许可 MIT。
- 固定版本：`d9c0fab7b72fdcf87d674ef12a84d3829c9188be`。
- 文件：`VNTextPatch.Shared/Scripts/RealLive/RealLiveAssembler.cs`。
- 符号：`WriteString`、`WriteFunctionCall`、`WriteLineBreak`。
- 消息拼接依据：同目录 `RealLiveScript.cs` 的 `EncodeMessage`。
- 完整来源先反汇编收集 `_textRanges/_addressOffsets`。
- 完整写入最后对地址列表执行重定位，本模块没有伪装该能力。
- SEEN 容器来源：翻译肋手 v4.9D 的 `WindowsFormsApplication1.Archive.RealLive.ArcSeen`。
- 移植剔除调试弹窗、硬编码的 section 索引和原地改写文件缓冲区的做法。

## Python 接口
- 文本模块：[reallive.py](../python/engines/reallive.py)。
- `quote_text(text) -> bytes` 构造单个非空 CP932 引号 token。
- `unquote_text(data) -> str` 只读取此有限 token 子集。
- `assemble_message(message, name=None) -> bytes` 构造局部消息片段。
- `LINE_BREAK` 是经过来源参数核对的八字节换行调用。
- 容器模块：[reallive_seen.py](../python/archives/reallive_seen.py)。
- `open_seen(data) -> SeenArchive` 建立非空 section 表（`index`、`offset`、`size`）。
- `read_section(data, section, key_table=None) -> bytes` 还原单个 section 载荷。
- `lz_decompress(stream, unpacked_size)` 与 `lz_compress(payload)` 为流级接口。
- 任何接口均不读写磁盘、不导入 VM 或来源库；密钥表由调用方传入。

## 使用示例
```python
from python.engines.reallive import quote_text, unquote_text, assemble_message
quoted = quote_text('表「a"b」')
assert unquote_text(quoted) == '表「a"b」'
fragment = assemble_message("一行目\n二行目", name="名前")
# fragment 仍需完整结构工具安装与重定位，不能直接正则回填。
```

## 特有文本编码
- 引号 token 使用 ASCII `"` 包裹 CP932 数据。
- 字符串里的 ASCII 双引号写成反斜线加双引号。
- SJIS 双字节字符整体复制，尾字节不能误认作语法符号。
- 例如 `表` 的第二字节 `0x5c` 不是 ASCII 反斜线。
- 为避免末尾反斜线与闭引号歧义，本子集拒绝独立 ASCII 反斜线。
- token 内 NUL、物理 CR/LF 也拒绝，换行应生成 VM 调用。
- 该限制比泛化转义器保守，不假定未知 RealLive 字符串语法。

## 换行指令布局
- 函数调用从字节 `#` 开始。
- 后续字段为 u8 type、u8 module、u16 function、u16 参数数、u8 overload。
- 本换行使用 `(0, 3, 201, 0, 0)`，u16 均为小端。
- `assemble_message` 把显式 LF/CRLF 转成换行调用。
- 不做像素级排版，不猜游戏窗口宽度。
- 空行也可表达为换行调用，而不是伪造空文本 token。

## name/message 与姓名
- 来源姓名在正文前作为 `【姓名】` 的未引号字符串写入。
- 本接口同样仅在显式传入 name 时添加该前缀。
- 姓名中拒绝引号、反斜线、NUL、换行及括号定界符。
- 不能根据文件中的任意 `【...】` 正则命中推断 VM 文本范围。
- 此模块不删除日文对白引号，避免来源显示规范化造成不可逆损失。
- 上层 sidecar 需区分姓名字段、对白字段和实际 VM 引用位置。

## 输入输出边界
- `unquote_text` 要求输入恰好是一个非空 token，不接受后续任意代码。
- 不支持的转义、裸双引号、短 SJIS 字符都会报错。
- 片段输出不包含文件头、压缩流或地址表。
- 默认且唯一的文本编码是 CP932。
- 无自定义 SJIS tunnel、字体扩展与中文替代字符策略。

## 部署缺口
- 未完成 RealLiveDisassembler 的 opcode/表达式语法。
- 未完成所有分支、调用、选择项及地址来源识别。
- 未完成代码基址映射、地址字段更新与 SEEN 封装重建。
- 全 VM 地址绝不能靠 regex 字符串替换修复。
- 当前接口只为将来的完整结构工具提供可测组装单元。

## 验证状态
- 合成测试核对 CP932 双字节边界、双引号转义和解码回读。
- 核对换行调用的精确八字节布局及消息片段计数。
- 覆盖非法姓名、NUL、孤立转义、缺闭引号与截断字节。
- 测试文件：[test_engines_secondary.py](../tests/test_engines_secondary.py)。
- SEEN 测试覆盖 section 表、字面量与回溯的 LZ 往返、密钥表 XOR、256..512 窗口、越界与截断拒绝。
- SEEN 测试文件：[test_reallive_seen.py](../tests/test_reallive_seen.py)。
- 无真实 SEEN 文件、VM 运行或游戏启动验证，不能以测试通过宣称整引擎支持。
