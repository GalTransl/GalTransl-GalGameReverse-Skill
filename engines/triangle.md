# Triangle：MOP / EXD / KLH 的独立文本块

## 能力边界
- 状态：`partial / isolated-block-roundtrip`。
- Python：`python/engines/triangle.py`。
- 只处理已经可靠切出的单条 TEXT 或 CHOICE 指令。
- 不提供完整 SD 反汇编、自动识别或全文件跳转重定位。
- 文本块能变长不代表可直接原位覆盖整个 SD。

## 识别与版本
- 来源说明该系列是无文件头的 16 位小端栈式 VM。
- MOP 与 EXD：TEXT=74、CHOICE=75。
- KLH：TEXT=72、CHOICE=73。
- 必须显式给 `profile`，不能依赖后缀自动猜测。
- 块头为 `u16 opcode + u16 段数`。
- 块必须恰好覆盖输入，没有多余尾字节。

## 指令段结构
- 文本与选项通常是 NUL 结尾 CP932 字符串。
- TEXT 中段首 `M/N/V/W/@` 及大小写变体是命令段。
- `V/v` 段结束后额外携带六字节参数，必须原样保留。
- `N/n` 后面的值是名字引用编号，不是显示名称。
- 非命令正文段的连续序列构成一条逻辑 message。
- CHOICE 中每个 NUL 字符串独立成为一项。

## 提取 name / message
- `extract_block` 返回正文涵盖的段索引 `segments`。
- 同时返回当前 `name_id`，不虚构名字池内容。
- 命令段会结束当前正文 run，不能拼过控制边界。
- 默认严格 CP932 解码，禁止吞掉不可解码字节。
- 选择项不会误用正文命令前缀判定。
- 原始分段保留在 `parse_block` 的输出里。

## 回填独有算法
- `rewrite_block` 的键是正文 run 的首段索引。
- 按目标编码的每个字符字节长度贪心折行。
- 不切断多字节字符，也不允许单字符超出行宽。
- 用新行段替换原正文 run，并更新 u16 段数。
- 所有名字、语音和等待命令段保持原字节。
- 新正文行若以命令前缀开头则拒绝，防止改变指令语义。
- 没有修改的 run 保留原分段，空替换表字节一致。
- 输入译文不接受 NUL、CR/LF 或空串来偷偷制造新控制段。

## Python 示例
```python
from python.engines.triangle import extract_block, rewrite_block
records = extract_block(isolated_instruction, profile="MOP")
first_segment = records[0]["segments"][0]
block = rewrite_block(isolated_instruction, {first_segment: "合成試験"},
                      profile="MOP", line_bytes=62)
```
- `line_bytes` 是显式部署参数，不保证任意游戏都适用 62。
- `block` 只是一条新指令，尚不是可部署的完整 SD。

## 容器与部署缺口
- 来源完整工具另有整文件指令表与跳转目标修正流程。
- 特殊跳转包含 GOSUB/JMP、跳转表；KLH 还有嵌入数据块。
- 本参考没有复制启发式重同步和不透明数据块推测。
- 变长输出必须先交给独立核实的全文件重布局器。
- 缺少名字池解析、外层资源包装、引擎字库和排版验证。
- 未确认代码边界时禁止用本模块在任意 SD 字节位置试写。

## 来源、许可与测试
- SExtractor 提交 `8d8d976fd04ae54e7c677705af937273d04a376a`。
- `tools/Triangle/mop_sd.py`：profile、段与语音尾参数布局。
- `tools/Triangle/text_extract.py`：正文 run 与名字编号语义。
- `tools/Triangle/text_inject.py`：按编码字节折行和段数重建。
- 上游署名 多了芒果；来源仓库 GPL-3.0。
- 已测连续正文合并、字符边界折行、voice 六字节保留。
- 已测 KLH 选择项、错误 profile、缺 NUL 和命令前缀拒绝。
- 测试：`tests/test_engines_tools_b.py`，没有完整游戏执行验证。
