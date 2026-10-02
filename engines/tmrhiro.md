# TmrHiro：text 流的 i16 长度往返

## 识别与适用范围
- 本页对应 TmrHiro ADV System 的 TextScript，不是 CodeScript。
- 来源 TextScript 没有固定扩展名，不能靠后缀自动识别。
- 文件由连续的“长度 + 编码文本”记录构成。
- 长度字段是小端带符号 i16，而不是无符号 u16。
- 文本长度按字节计数，不包含两字节长度字段。
- 没有每条字符串的 NUL 终止要求。
- 必须先由项目证据确认这确实是 text 流，随机二进制也可能偶然符合。

## 容器与剧本
- 资源包、独立代码脚本与独立文本流是不同输入层。
- 本模块只接收已取得的完整 text 字节流。
- 不解容器，不处理代码 opcode，不修补外部文件索引。
- 若游戏通过另一文件的表引用文本，需验证引用是否按记录序号。
- 不应因为 text 文件可重建就宣称整个项目无需其他结构更新。

## 源码依据
- 仓库：VNTextPatch-net8，许可 MIT。
- 固定版本：`d9c0fab7b72fdcf87d674ef12a84d3829c9188be`。
- 文件：`VNTextPatch.Shared/Scripts/TmrHiroAdvSystem/TmrHiroAdvSystemTextScript.cs`。
- 符号：`GetStrings`、`WritePatched`。
- 同目录有独立 `TmrHiroAdvSystemCodeScript.cs`，本模块没有将它混入。
- 来源 writer 以 short 写长度，本参考增加超长显式拒绝。
- 这里是可完整往返的有限格式，而非空壳占位接口。

## Python 接口
- 模块：[tmrhiro.py](../python/engines/tmrhiro.py)。
- `read_text(data, encoding="cp932") -> tuple[str,...]`。
- `write_text(strings, encoding="cp932") -> bytes`。
- `patch_text(data, replacements, encoding="cp932") -> bytes`。
- replacements 的键为原记录序号。
- patch 不允许向不存在的序号写入，避免误增减翻译行数。
- 无 GalTransl、插件、缓存、来源项目或外部进程依赖。

## 使用示例
```python
from python.engines.tmrhiro import read_text, write_text, patch_text
original = write_text(["本文", "", "次の文\n改行"])
assert read_text(original) == ("本文", "", "次の文\n改行")
patched = patch_text(original, {0: "もっと長い文"})
assert read_text(patched)[1:] == read_text(original)[1:]
assert patch_text(original, {}) == original
```

## 输入输出边界
- 空文件表示零条记录，是有效输入。
- 长度 0 表示一个空字符串，也是有效输入。
- 长度为负数直接拒绝，不将其解释成巨大无符号长度。
- 剩余不足两个字节时拒绝短长度字段。
- 声明正文超过文件末尾时拒绝截断记录。
- 解码严格消费整个文件，不忽略尾部垃圾。
- writer 的每条编码结果必须处于 0..32767 字节范围。
- 超范围拒绝，绝不把长度强制截成 short 后继续输出。
- 内部换行及 NUL 都是长度内数据，模块不擅自清洗。

## name/message 与姓名
- 来源把每个记录都导出成 Message，没有独立姓名字段。
- 不能按“文本很短”推断这是 name。
- 如果同一记录含人物名，应保留整串或由上层建立可逆拆分。
- 如果角色名来自代码文件，必须使用那一层的引用证据。
- sidecar 保存记录序号、原始长度、原文与编码策略即可定位回填。
- 不应用正文顺序变化替代真正的记录映射。

## 回填结构
- `write_text` 根据输入字符串序列重新序列化全部记录。
- `patch_text` 只重新编码被改动的记录。
- 未改动记录直接复制原始长度和原始数据字节。
- 这可保留 CP932 中解码后重新编码可能规范化的别名码点。
- 修改记录变长会自然改变后续记录位置，但每条自身长度保持正确。
- 本格式内部没有在已核对源码中出现的单独地址表需要补写。
- 这一结论仅限本 text 流，不延伸到外围归档或代码脚本。

## 编码与控制码
- 默认严格 CP932，可显式选择调用方核实的其他标准库编码。
- 来源 `SjisTunnelEncoding` 的行为未移植。
- 无字体补丁时不要假设中文可直接显示。
- 编码失败会返回异常，而不是替换字符。
- 文本中的变量、换行和原作控制片段应原样保留。
- 本模块不自动换行，也不把长句拆成新记录。

## 部署限制与验证状态
- 已完成有限 text 流的完整读取、序列化和索引回填。
- 未完成 CodeScript 的解析与 writer。CodeScript 中的逗号字段与选择跳转 label 属于另一套语法，不能用本页 TextScript 的长度记录示例处理；扩展时须区分显示文本和跳转目标。
- 未完成外层包、跨文件引用检查、游戏字体和运行验证。
- 合成测试覆盖多条记录、空字符串、换行与变长译文。
- 验证空修改逐字节不变，未修改记录保持不变。
- 坏输入包含负 i16、单字节尾部、正文不足与 32768 字节超限。
- 测试文件：[test_engines_secondary.py](../tests/test_engines_secondary.py)。
- 测试是标准库离线测试，没有使用真实游戏或付费接口。
- 部署前仍需在获授权副本中完成重新提取与游戏加载检查。

## 完整导出与回填示例

这是**真实参考格式 + 人工样例**，演示如何连接叶子算法、JSON、manifest 和安全输出，不是识别任意 `.srp` 的通用工具。TmrHiro 的这个 text 方言是重复的“有符号 i16 字节长度 + CP932 文本”，与该引擎的 CodeScript 指令格式不同。

前置阅读：本页的适用范围和 [数据契约](../guides/roundtrip-contract.md)。没有可靠的格式识别证据时不要套用。

### 导出

```python
from python.engines.tmrhiro import read_text, write_text, patch_text
from python.common.contract import make_manifest, dump_rows, validate_translation

# raw 必须来自已经确认属于此方言的原始文件。
def export_text(raw: bytes):
    rows = [{"message": text} for text in read_text(raw, encoding="cp932")]
    manifest = make_manifest(
        engine="tmrhiro", variant="signed-i16-text",
        reference="python/engines/tmrhiro.py",
        sources={"message": raw}, rows=rows,
        locators=[{"kind": "record-index", "index": i} for i in range(len(rows))],
        encoding="cp932",
    )
    return rows, dump_rows(rows), manifest
```

此格式没有自带可推导姓名的字段，因此只输出 `message`，不凭正文猜造 `name`。重复正文保留不同条目。

### 翻译前：原文往返

在人工样例或编码唯一的源样本上，先检查 `write_text(read_text(raw))` 与原始 bytes 的关系。这确实经过 writer，而不是“未改内容就复制”。CP932 别名字节可能被规范化，因此真实文件还要比较原编码；`patch_text()` 会保留未被替换记录的原字节。

如果源格式并非这一个精确方言，或者发现长度之外还有未处理索引/外壳，停止，不把这个示例扩成通用 writer。

### 回填

```python
def inject_text(raw: bytes, original_rows: list[dict],
                translated_rows: list[dict], manifest: dict) -> bytes:
    checked = validate_translation(
        manifest, {"message": raw}, original_rows, translated_rows,
    )
    replacements = {i: row["message"] for i, row in enumerate(checked)
                    if row["message"] != original_rows[i]["message"]}
    result = patch_text(raw, replacements, encoding="cp932")
    if read_text(result, encoding="cp932") != tuple(row["message"] for row in checked):
        raise ValueError("rebuilt text does not match translation")
    return result
```

`patch_text` 为每条修改后的记录重写正确的字节长度，并拒绝超过 i16 上限的文本。这里没有“只覆盖旧位置但不改长度”的偷懒步骤。

**CP932 不支持任意中文。** 此例会拒绝不能编码的字，不能改成 `errors="replace"`；真实汉化需要先确认游戏的编码/字体或单独验证运行时方案。

### 安全输出与验证

使用 [write_new_tree](../python/common/safety.py) 将结果写到新的独立目录，不覆盖源文件。外层资源包和游戏加载仍需另按引擎页面的容器条件处理，这个例子不声称完成部署。

可运行的完整人工 fixture 在 [test_roundtrip_recipe.py](../tests/test_roundtrip_recipe.py)：
- 独立组装原始字节；
- 实际导出 JSON + manifest 至工作区；
- 原文经过 writer；
- 更长、更短及重复正文的不同译文回填；
- 重新解析与原件不变检查；
- 不能编码的中文在写出前拒绝。

在 Skill 根目录运行：
```text
python -B -m unittest discover -s tests -p test_roundtrip_recipe.py -v
```

测试不使用游戏资产、不访问网络、不调用任何原始工具或翻译 API。
