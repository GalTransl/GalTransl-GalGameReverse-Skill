# Whale：文本行结构、SELECT 与 [n]

## 识别与适用范围
- 来源 WhaleScript 是 PlainTextScript 分支，没有固定扩展名。
- 一般文本行、标签行、命令行不能混为对白。
- 来源以首字符大于 `0xff` 作为普通消息行的重要线索。
- ASCII 起头的行可能是引擎命令，而不是可翻译叙述。
- `*` 起头的行按标签或结构行跳过。
- 本实现支持普通消息行与明确的 SELECT 子集。
- `CS/MS.HS` 命令参数提取没有在此实现，故保守跳过。

## 容器与剧本
- 容器内提取出的文本文件才是本模块的对象。
- 接口接受已经严格解码的 Python str，而不是归档字节。
- 文本编码与文件读写由调用方显式决定。
- 模块不猜游戏目录，不调用外部 exe，不处理压缩包。
- 输出仍是同一脚本文本，保留未编辑行及原换行风格。

## 源码依据
- 仓库：VNTextPatch-net8，许可 MIT。
- 固定版本：`d9c0fab7b72fdcf87d674ef12a84d3829c9188be`。
- 文件：`VNTextPatch.Shared/Scripts/WhaleScript.cs`。
- 符号：`GetLineRanges/GetMessageRanges/GetSelectRanges`。
- 回填依据：`GetTextForRead/GetTextForWrite/IsAtStartOfLine`。
- 来源还识别 `CS/MS.HS` 并使用日文字符判断，不能把该覆盖范围转嫁给本子集。
- 本模块实现首字符结构保护，不实现像素/等宽自动排版。

## Python 接口
- 模块：[whale.py](../python/engines/whale.py)。
- `extract(script) -> tuple[Target,...]`。
- Target 保存 start/end、role、text、at_line_start、kind。
- start/end 是 Python Unicode 字符索引，不是文件字节偏移。
- `patch(script, replacements) -> str` 按提取序号回填。
- 提取仅针对固定语法，不做跨整文件原文字串替换。

## 使用示例
```python
from python.engines.whale import extract, patch
script = '【名前,voice01】「本文[n]続き」\r\nSELECT "選択,*go"\r\n日本語\r\n'
targets = extract(script)
assert [t.text for t in targets] == ["名前", "本文\n続き", "選択", "日本語"]
changed = patch(script, {2: "別選択", 3: "ASCII\nmore"})
assert 'SELECT "別選択,*go"' in changed
assert "　ASCII[n]　more" in changed
```

## name/message 与姓名
- 支持前导 `【姓名,附加字段】「正文」`。
- 只把逗号前的姓名本身提取为 name，保留附加字段和括号。
- 正文范围不包含外层 `「」`，不会翻译这些定界符。
- 无姓名普通叙述按整行 message 导出。
- 括号内独白以整串保留，不擅自删除外框。
- 姓名括号不闭合或有姓名却无支持的正文形式会拒绝。
- 不根据 ASCII 命令参数猜测人物名或对白。

## SELECT 的边界
- 支持 `SELECT "选择文本,*label"` 及连续多个同类条目。
- `,*label` 是控制流目标，不是翻译内容。
- 目标标签以词字符组成；其他条件表达式属于未支持语法。
- 只有引号内标签分隔逗号之前的文本被导出。
- 回填选项不能包含 ASCII 双引号或逗号，防止破坏结构。
- 语法不完整的 SELECT 不会退化为随意抽取引号内容。

## [n] 与首字符保护
- 提取时把文本控制串 `[n]` 映射成可读 LF。
- 回填时把实际 LF 重新编码为 `[n]`。
- 翻译输入不接受字面 `[n]`，避免无法区分控制换行与普通文字。
- 若替换范围处于物理行开头，且译文首字符不大于 `0xff`，补全角空格。
- 同时在其每个 `[n]` 后增加全角空格，维持后续显示行的结构。
- 已被姓名/引号包围的正文范围不会多加行首结构字符。
- 这是语法保护，不是凭审美给文本随意加空白。

## 编码与回填契约
- patch 保留所有非目标字符与原 CRLF/LF。
- 翻译 CRLF 规范化为 LF，孤立 CR 不支持。
- 姓名中不能引入括号、逗号或换行。
- 空译文、NUL、非法目标索引均拒绝。
- 调用方将结果编码回文件前必须使用原始明确编码严格预检。
- 不把 CP932 无法编码的字符替换成问号，也不提供字体隧道。
- 其他 `[变量]` 或控制片段应由公共翻译契约保护。

## 缺口与验证状态
- 未实现 CS/MS.HS 参数解析、全部 SELECT 变体与自动排版。
- 不提供容器回包、游戏字体修改或整项目 CLI。
- 合成测试覆盖姓名后附加字段不变、正文换行和标签不变。
- 验证 ASCII 译文首字符保护及 CRLF 保留。
- 坏输入测试覆盖非法 SELECT、姓名结构冲突与字面 `[n]`。
- 测试文件：[test_engines_secondary.py](../tests/test_engines_secondary.py)。
- 当前是有限文本子集可回填，未做真实游戏运行验证。
- 扩大覆盖前应先提供相应语法证据，不能改成全局正则扫引号。
