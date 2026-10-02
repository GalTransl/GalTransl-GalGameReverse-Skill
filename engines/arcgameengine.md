# ArcGameEngine：AGE 字符串池算法

## 识别与适用范围
- 本页聚焦 VNTextPatch 的 ArcGameEngine/AGE 脚本分支。
- `AgeScript`、反汇编器、汇编器和字符串池 builder 是不同组件。
- 这里提供其中可独立验证的真实字符串池算法。
- 未移植整个 AGE VM，因此不以文件名或偶然文本宣称识别成功。
- 必须先由调用方证明输入字节是该分支的字符串池。
- 池内地址不是字节偏移，而是四字节为单位的相对地址。

## 容器与剧本
- 引擎资源容器的拆包不能由字符串池函数代替。
- 剧本内代码段、字符串段、其他资源也必须区分。
- 本模块输出仅为池内容及每条输入字符串的相对地址。
- 将池放回脚本以后，池基址和所有使用者仍需结构化更新。
- 本模块不会自动打开文件或调用归档程序。

## 源码依据
- 仓库：VNTextPatch-net8。
- 固定版本：`d9c0fab7b72fdcf87d674ef12a84d3829c9188be`。
- 许可：MIT，保留原许可及著作权声明。
- 文件：`VNTextPatch.Shared/Scripts/ArcGameEngine/AgeStringPoolBuilder.cs`。
- 核心符号：`AgeStringPoolBuilder.Add`。
- 来源按照字符串去重，以池长度除 4 计算相对地址。
- 字符串编码后追加 NUL，再补零到四字节对齐。
- 整个结果连同 NUL 和填充一起 XOR `0xff`。

## Python 接口
- 模块：[arcgameengine.py](../python/engines/arcgameengine.py)。
- `build_string_pool(strings, encoding="cp932") -> (bytes, tuple[int,...])`。
- 返回值一是加密池字节，二是与输入一一对应的地址列表。
- 输入中重复的 Unicode 字符串共享同一个池地址。
- `read_pool_string(pool, word_address, encoding="cp932") -> str`。
- reader 接受池相对的四字节单位地址，不能传入文件绝对偏移。
- 函数使用标准库，导入时无磁盘访问。

## 使用示例
```python
from python.engines.arcgameengine import build_string_pool, read_pool_string
pool, refs = build_string_pool(["a", "本文", "a", ""])
assert refs == (0, 1, 0, 3)
assert pool[:4] == bytes([0x9e, 0xff, 0xff, 0xff])
assert read_pool_string(pool, refs[1]) == "本文"
```

## 输入与输出边界
- 输入字符串不允许含 NUL，以防提前终止。
- 默认使用严格 CP932 编解码，不做字符替代。
- 空字符串有效，仍消耗一个四字节对齐块。
- 字符串顺序决定首次出现时的地址，重复输入不再追加内容。
- reader 要求整个池长度四字节对齐。
- 地址必须是非负整数且在池内。
- 解密终止零在密文中表现为 `0xff`。
- 终止符后到下一个四字节边界必须都是密文 `0xff`。
- 未找到终止符、非零填充、非法编码或越界地址均拒绝。

## name/message 与姓名
- 字符串池本身不区分姓名、对白、路径和其他字面量。
- 不能将池内所有字符串都送去翻译。
- name/message 角色必须来自使用该地址的指令与调用语义。
- 同一字符串可能被对白与资源指令共享。
- 上层应保存引用身份，而不仅是“原文字串”。
- 不应通过全局替换同文字符串来改变共享资源名。

## 回填结构
- builder 是真实池序列化器，不是完整脚本 writer。
- 它会重算每条新字符串的相对地址与填充。
- 它不会寻找旧池，不会修改现有指令的地址字段。
- 原池中未导出的资源字符串需由调用方保留。
- 如果重建池改变了顺序，所有引用必须使用新地址。
- 地址单位转换要显式进行，不能把 word 地址当 byte 地址。

## 编码与控制码
- 来源使用 `SjisTunnelEncoding`；本模块仅使用标准库严格编码。
- 因而不能声称已经支持来源的自定义中文字符隧道。
- 编码失败意味着缺少部署前提，不应自动写问号。
- 文本中的变量和控制片段保持原样。
- 是否有额外文本控制语法，要从具体调用指令确认。
- 不能只依据池 codec 成功，就推断游戏字体能显示。

## 缺口与部署限制
- 未完成 AGE 指令反汇编、调用识别、角色推断。
- 未完成池重定位、操作数重写、脚本头字段更新。
- 未完成容器层解包与回包。
- 不提供全引擎 CLI，也不包装外部程序冒充 writer。
- 接口可作为完整结构工具中的局部算法单元使用。

## 验证状态
- 合成测试核对 XOR、NUL、四字节填充和地址单位。
- 覆盖重复字符串共享地址、空串以及多字节 CP932。
- 坏输入测试覆盖池不对齐、地址越界、缺终止符和坏填充。
- 额外检查 NUL 输入与不可编码字符失败。
- 测试文件：[test_engines_secondary.py](../tests/test_engines_secondary.py)。
- 尚无真实脚本或游戏运行验证，状态为局部池算法已测。
