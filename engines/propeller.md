# Propeller：MSC 长度文本与样式 toggle

## 识别与适用范围
- 来源 Propeller 分支以 `.msc` 为候选扩展名。
- 本页只移植已经定位的文本字段编码，不移植全部 MSC 指令表。
- 文本字段前缀是小端带符号 i32 字节长度。
- 该长度不包括自身四字节。
- 不能在任意 `.msc` 中正则搜索日文就宣布得到了合法文本区。
- 文本位置必须来自结构化反汇编或经过核实的独立字段样本。

## 容器与剧本
- 归档拆包与 MSC 脚本解析是两个阶段。
- 此模块不处理资源包，也不更新归档文件索引。
- 一个文本字段不是一条完整指令，更不是整个 MSC。
- 修改字段大小后，其后代码位置与跳转目标可能变化。
- 所以本模块输出不能直接当作整文件补丁。

## 源码依据
- 仓库：VNTextPatch-net8，许可 MIT。
- 固定版本：`d9c0fab7b72fdcf87d674ef12a84d3829c9188be`。
- 文件：`VNTextPatch.Shared/Scripts/Propeller/PropellerScript.cs`。
- 符号：`FormattingReplacements`、`GetParsedString`、`WritePatched`。
- 来源用 `PropellerV1Disassembler` 获得文本范围与地址字段。
- 完整 writer 在替换后还调用 `PatchAddress`，不是单纯改文字。
- 本参考明确停留在字段与格式控制码层。

## Python 接口
- 模块：[propeller.py](../python/engines/propeller.py)。
- `write_text_field(text) -> bytes` 构建长度字段和内容。
- `read_text_field(data, offset=0) -> (text, end)`。
- `split_names(text) -> {names, message}` 解析重复前导姓名括号。
- 返回 end 是该字段的排他字节偏移。
- 接口仅依赖标准库，不做文件 IO 或外部进程调用。

## 使用示例
```python
from python.engines.propeller import write_text_field, read_text_field, split_names
text = "【甲】/【乙】<b>本文</b>,次\n続き"
field = write_text_field(text)
assert read_text_field(field) == (text, len(field))
assert split_names("【甲】/【乙】本文")["names"] == ("甲", "乙")
```

## 特有算法
- 正常换行映射成文本控制串 `_r`。
- 当正文包含 ASCII 逗号时，来源在开头加入 `<,>`。
- `<b>` 与 `</b>` 都对应 `FC FD`，语义是开关而非不同 opcode。
- `<i>` 与 `</i>` 都对应 `FC FE`。
- `<u>` 与 `</u>` 都对应 `FC FF`。
- reader 对每种样式独立跟踪 toggle 状态，重建起止标签。
- 必须按 SJIS 字符边界读取，不能把合法双字节尾部当控制码。
- 参考实现拒绝未闭合样式，限制为可独立往返的单字段子集。

## 输入输出边界
- writer 输入的是可读文本，不是已经含 `_r` 的原始字段。
- 如果输入含字面 `_r` 或以保留前缀 `<,>` 开头，会拒绝歧义。
- CRLF 先规范化为 LF，孤立 CR 不支持。
- 文本内部 NUL 不接受。
- 所有普通文字严格 CP932 编码。
- reader 检查负长度、越界字段、半个 SJIS 字符与不完整样式状态。
- 未识别 HTML 标记保留为字面文字，不擅自执行或清洗。

## name/message 与姓名
- 来源用前导 `【姓名】`，允许多组姓名以及斜线分隔。
- 本 `split_names` 保存全部姓名，不只保留第一个。
- 姓名集合与正文分离后，上层必须记录原分隔结构。
- 本 writer 不自动发明姓名排版，也不替换姓名括号。
- 不应把 `【...】` 以外的短文本猜成人名。
- 语音/脚本命令参数若不在已识别文本字段中不能提取。

## 回填结构与部署
- i32 长度始终按最终 CP932 字节数重算，包括样式控制字节。
- 本模块没有代码基址和地址字段列表。
- 因而不处理跳转地址、偏移表或外壳长度更新。
- 输入本来是跨字段延续的未闭合样式时，此子集会拒绝。
- 上层如扩展到整文件，必须证明这些状态在何处复位。
- 来源 SJIS tunnel 与自动排版不在本参考中。
- CP932 不能编码的中文不会被替换成问号，应停止部署预检。

## 验证状态
- 合成测试覆盖姓名组、样式 toggle、逗号前缀与 `_r` 换行。
- 检查输出长度和重新读取的文本语义相同。
- 使用含 SJIS 尾部 `0x5c` 的字符检查多字节边界。
- 坏输入涵盖未闭合标签、NUL、保留语法、负长与截断。
- 测试文件：[test_engines_secondary.py](../tests/test_engines_secondary.py)。
- 未完成全 MSC writer、容器回包和游戏运行验证。
- 当前状态为文本字段算法可测，不是完整脚本往返已完成。
