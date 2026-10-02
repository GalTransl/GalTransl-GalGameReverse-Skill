# ShSystem：只导出特定 scriptcall 0x33

## 必须先知道的能力边界
- VNTextPatch 的 `ShSystemScript.WritePatched` 尚未实现。
- 其方法直接抛出 `NotImplementedException`。
- 本模块也没有 writer，不会给出虚假的“完整回填”接口。
- 来源不是提取全部字符串，而是只关注特定 scriptcall。
- 具体条件是脚本 ID `0x33`、参数数目为 5、第五个参数为字符串字面量。
- 变量、表达式字符串和其他脚本 ID 不满足导出条件。

## 识别与容器分工
- 来源候选扩展名为 `.hst`。
- 脚本头签名必须是八字节 `SHSysSC\0`。
- 其后文件大小是三字节大端值，不是小端 i32。
- 模块检查声明大小与实际输入长度一致。
- 再读 source-info 标志和四个保留字节。
- 有源信息时跳过 CP932 NUL 结尾文件名，得到代码起点。
- 本页处理脚本本身，不提供资源归档拆包或重包。

## 源码依据
- 仓库：VNTextPatch-net8，许可 MIT。
- 固定版本：`d9c0fab7b72fdcf87d674ef12a84d3829c9188be`。
- 文件：`VNTextPatch.Shared/Scripts/ShSystem/ShSystemDisassembler.cs`。
- 符号：`TryReadLiteralExpression/SkipExpression/SkipString/SkipList`。
- 文本筛选依据：同目录 `ShSystemScript.cs`。
- 符号：`HandleScriptCall/GetStrings/WritePatched`。
- 源码中的 opcode `0x03` 是 scriptcall，不是脚本 ID `0x33`。

## Python 接口
- 模块：[shsystem.py](../python/engines/shsystem.py)。
- `read_header(data) -> dict` 返回 code_offset、源信息与保留字节。
- `read_scriptcall(data, opcode_offset) -> dict` 解析一条已定位调用。
- 返回 script_id、所有参数范围、可选 record 及排他 end。
- record 只有满足前述 `0x33` 条件才存在。
- offset 必须指向实际 opcode，不包括可选的源行号前缀。
- 没有扫描任意 `03/33` 字节来发现调用的代码。

## 使用示例
```python
from python.engines.shsystem import read_scriptcall
# 一条已知边界的合成指令：脚本常量51，四个表达式，第五项字面串。
call = b"\x03\x0d\x33\xff" + b"\x02\x01\xff" * 4
call += b"\x01" + "名前\\n本文".encode("cp932") + b"\0\0"
result = read_scriptcall(call, 0)
assert result["record"]["name"] == "名前"
assert result["record"]["message"] == "本文"
```

## 特有表达式算法
- 表达式由 tag 序列构成，`0xff` 结束。
- tag 高四位是 operation，低四位是 index。
- operation 0 的 index 13/14/15 额外消费 1/2/4 字节。
- operation 1/2/3 的 index 14/15 额外消费 1/2 字节。
- 常量表达式必须正好是一个显式常量加终止 tag。
- 两字节和四字节常量使用大端读取。
- 非常量表达式得到未知 script_id，不猜执行结果。

## 字符串与参数列表
- 参数列表先读类型；0 结束，1 是字符串，其他值按表达式处理。
- 字符串首字节小于 `0x20` 时是空串、变量或字符串表达式。
- 只有首字节不小于 `0x20` 的 NUL 串被标记为 literal。
- 小于 6 和小于 12 的变量分支具有不同索引宽度。
- 嵌套表达式按实际边界跳过，不把其中字节当人类文本。
- 每次取字节都做边界检查，截断不会变成部分成功。

## name/message 与姓名
- 来源把字面 `\n` 转成 CRLF。
- 第一个非起始 CRLF 之前的内容作为姓名。
- 之后的内容去掉两端空白，作为 message。
- 没有正长度首行时 `name=None`。
- 这是来源提取约定，trim 会丢失展示空白，不是无损反向格式。
- sidecar 仍需保留原始串和完整参数范围，不能只保存展示 record。

## 编码与回填限制
- 字符串按严格 CP932 解码，不替换非法字节。
- 输出 record 是信息提取结果，不是可直接写回的二进制字段。
- 三字节地址、源行号和头部大小都影响完整回写。
- 本页未给出地址更新算法，因此不允许局部变长回填。
- 不能用一个通用 bytes 替换函数冒充缺失的 `WritePatched`。
- 中文字体或编码扩展是另外的部署前提，目前也没有实现。

## 验证状态与未完成阶段
- 合成测试覆盖真实 `0x03` 调用结构与 `0x33` 精确筛选条件。
- 核对名字/正文拆分、参数末尾位置及大端文件大小头。
- 其他 ID 不导出文本，坏 opcode、短表达式、缺列表结束均拒绝。
- 测试文件：[test_engines_secondary.py](../tests/test_engines_secondary.py)。
- 未移植完整 opcode 表及自动调用发现。
- 未实现 writer、地址重定位、归档回包或游戏运行验证。
- 当前可诚实标注“局部只读导出”，不能标注完整往返支持。
