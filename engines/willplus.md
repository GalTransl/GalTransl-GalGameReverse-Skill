# WillPlus / AdvHD：ARC/AR2 解包与 WS2 v1 代码子集

## 能力边界
- 引擎 ID：`willplus`。
- 参考模块：[python/engines/willplus.py](../python/engines/willplus.py)。
- 归档模块：[python/archives/willplus.py](../python/archives/willplus.py)，提供 Will ARC v1、Pulltop ARC/AR2 v2 的目录与成员读取，以及显式成员 codec。
- 实现已证明 WS2 v1 代码区域的消息、名字、选择及绝对跳转更新。
- 不自动识别全部 WS2 版本，不剥离猜测的文件尾部。
- 输出是代码区域 bytes，不是保证可部署的完整 `.ws2` 文件。

## 识别证据
- `.ws2`、AdvHD/Will 资源布局与可解释 opcode 是组合证据。
- 不能通过单个 `%K`、`%L` 或可读人名决定格式。
- VN 会尝试 V1/V2/V3 disassembler，说明版本差异确实存在。
- Will 旧版剧本、WS2、资源 ARC/AR2 不应混为一个格式。
- 代码区域必须由调用层证实从偏移 0 起始且与使用的指令表一致。
- 只要遇到未知 opcode，本参考即拒绝继续解析。

## 格式方言
- 操作码为 u8，参数包含 i16、i32、cstring 等不同宽度。
- 本子集接收 00、02、05、06、0F、13、14、15、17。
- 02/06：一个 u32 绝对跳转地址。
- 14：i32 + 内部字符串 + 正文字符串。
- 15：人物名字 cstring。
- 0F：u8 选择数，逐项 i16/文本/u8/i16，随后一个 02/06 跳转。
- 每个地址目标必须是已解析的指令起点。
- 不接受跳到字符串内部、代码尾部之外或未证明区域。

## 容器到剧本路线
1. 确认 ARC/AR2 版本及成员扩展名，不直接在包上替换文字。
2. 使用本页归档接口；GARbro-Mod 的 `ArcFormats/Will/ArcWILL.cs`、`ArcPulltop.cs` 是布局与成员 codec 的来源。
3. 提取完整 WS2 后验证版本、代码起点、尾部与地址基准。
4. 仅将符合子集的完整零基代码区域交给本模块。
5. 回填结果经外围尾部/容器验证后，才进入公共写出流程。
- VN `Disassemble` 的循环界限是文件长度减 8；本模块不猜那 8 字节含义。
- 不能随意把任意 WS2 的末八字节剪掉就宣称得到安全代码区域。

## ARC/AR2 的两套目录

两者都没有可靠魔数，`version` 必须显式选择。扩展名 `.arc` 可用于两套布局，结构成功也不能单独证明所属引擎。**归档版本与 WS2 指令集版本独立。**

| 接口参数 | 索引布局 | 成员地址 |
|---|---|---|
| `version=1, name_size=9` | `u32` 扩展名组数；每组 `char[4] ext, u32 count, u32 dir_offset`；每成员 `char[9] basename, u32 size, u32 offset` | 绝对偏移 |
| `version=1, name_size=13` | 与上相同，basename 固定字段改为 13 字节 | 绝对偏移 |
| `version=2` | `u32 count, u32 index_size`；目录从 8 起，每条 `u32 size, u32 relative_offset, UTF-16LE NUL-terminated name` | `8 + index_size + relative_offset` |

- v1 默认严格 CP932；组数上限 255，每组不超过 65535 项，另受调用者总数预算限制。各组目录不得重叠，成员不得落在目录中。
- v1 的 9/13 是**包含名字终止空间的整个固定字段宽度**，对应上游 writer 的 NameLength=8/12；不混用这两种口径。不自动猜宽度。组扩展名替换 basename 的已有后缀，保留原大小写；上游 reader 转小写，本实现不做此归一化。
- v2 必须恰好消费声明的目录字节数，UTF-16LE 按两字节单元扫描 NUL，不在汉字的低/高字节中提前结束；坏 surrogate、空名及未终止名字拒绝。
- 两种布局均验证整个目录后才返回；路径穿越、重名、文件/目录冲突、越界或超预算不返回部分成功。

## 成员解码与调用示例

```python
from pathlib import Path
from python.archives.willplus import read_index, read_member, decode_member

# 此例要求已确认普通 v2 场景包，且不是包含 Model 的例外包。
with Path("game/Script.arc").open("rb") as stream:
    index = read_index(stream, version=2)
    entry = next(e for e in index.entries if e.name.lower().endswith(".ws2"))
    stored = read_member(stream, index, entry, max_stored_size=64 << 20)
    ws2 = decode_member(stored, codec="script-ror2", max_output_size=64 << 20)
# 继续证明 WS2 版本、文件尾部和代码基址，不能直接交给 v1 子集解析器。
```

`decode_member` 默认 `codec="raw"`，不依据扩展名偷偷改 bytes：

- `script-ror2`：每字节循环右移 2 位。上游 v1 对 SCR/WSC 使用此规则；v2 对 WS2/JSON 使用，但**归档 basename 含区分大小写的 `Model` 时跳过**。调用者据实际包选择，已解密数据不能再旋转一次。
- `psp`：PSP 资源前四字节为输出大小；LSB-first 控制位，1=literal，0=两字节回指；4096 字节零初始化环形窗口，写指针从 1 起，回指地址 `hi<<4 | lo>>4`，长度 `2 + (lo & 15)`。允许重叠回指，检查越过声明输出、截断及尾随压缩数据。
- `raw`：原样返回，经输出预算检查；不代表已经确认是明文 WS2。

`read_index` 只读目录，默认 100000 项 / 16 MiB（包括头和目录间隙）；`max_name_bytes=4096` 限制 v2 单名（含终止符）。`read_member` 只读选中成员；两个流接口均恢复位置并支持短读。成员必须是当前索引的原对象，调用者保持同一归档不变；只检测长度变化，不检测同大小修改。批量处理另设累计输出预算，写盘使用公共新目录接口。

没有 ARC writer，不包含 WS2 尾部处理或全版本指令集。出处及 MIT 声明见 [common-archives-v1.json](../provenance/common-archives-v1.json)，[合成测试](../tests/test_archives_common_engines.py)覆盖两种 v1 宽度、v2 Unicode、固定旋转向量、PSP 零窗口/重叠/环形边界、坏输入及预算。未做真实游戏归档或加载验证。

## 源码与算法对应
- 来源：`VNTextPatch-net8`，MIT。
- 提交：`d9c0fab7b72fdcf87d674ef12a84d3829c9188be`。
- 路径：`VNTextPatch.Shared/Scripts/AdvHd/AdvHdDisassemblerV1.cs`。
- `OperandTemplates` 对应有限 opcode 的布局。
- `AdvHdDisassemblerBase.cs` 的三个 Handle 方法对应 name/message/choice。
- `AdvHdScript.cs` 的 `RemoveControlCodes/AddControlCodes` 对应显示转换。
- `VNTextPatch.Shared/Util/BinaryPatcher.cs` 的 MapOffset/PatchAddress 对应重定位。
- 不用 `SExtractor/src/extract_WillPlus.py` 的片段匹配替代完整指令证明。

## Python 接口与示例
```python
from python.engines.willplus import parse_ws2_v1_subset, patch_ws2_v1_subset
code = b'\x15%LCA\0\x00'
layout = parse_ws2_v1_subset(code)
assert layout.fields[0].text == 'A'
patched = patch_ws2_v1_subset(code, {0: 'Alice'})
assert patched == b'\x15%LCAlice\0\x00'
```
- `Layout.fields` 保留 start/end/kind/raw/text。
- `Layout.addresses` 保存原操作数字节位置与原目标。
- replacements 以字段原序号为键，未知键拒绝。
- `parse_ws2_v1_subset` 会完整走完代码区域，而非抽取几段可读内容。

## name / message 映射
- 15 产生 name，14 的第三参数才是 message。
- 14 的第二参数为内部字符串，不送给翻译器。
- 每个选择文本产生独立 choice，并保留原跳转参数。
- 连续名字字段不折叠成最后一条；配对关系交给上层证据。
- 名字以 `$` 开头时禁止写入，避免破坏姓名变量。
- 没有本地名字槽的上下文姓名不得硬塞入正文参数。

## 回填、长度与控制码
- 名字前缀 `%LC/%LF/%LR` 从原串继承。
- 正文结尾 `%K` 等 ASCII 控制串从原串继承。
- 显示换行变成 `空格 + \n`，对应 VN 防止行末字符截断的处理。
- 译文不能额外注入 `%`、反斜线或 NUL。
- 区间长度变更形成原位置到新位置映射。
- 每个 02/06 操作数的位置与目标都经过映射后再写出。
- 字符串内部地址、不支持编码及 u32 地址溢出拒绝。
- 写完立即重新解析，确保所有目标仍是指令边界。

## 部署条件
- 实际剧本出现其他 opcode 时，应依据随包格式资料与样本结构扩充 parser，而非跳过。
- V2/V3 的参数差异必须单独核查，不能在同一字节上尝试“修到成功”。
- 必须同时证明尾部结构及容器成员尺寸更新路线。
- 外置脚本加载与字体编码都要运行时测试。
- 公共层负责目标路径、原文件保护、manifest 和原子写出。

## 验证与缺口
- 合成测试覆盖 name 前缀、message 后缀、换行、字段增长。
- 覆盖跳到文件后方的地址更新与选择指令嵌入跳转。
- 覆盖未知 opcode、字符串内部跳转与控制码注入拒绝。
- 测试位置：`tests/test_engines_primary.py` 中 `WillTests`。
- SExtractor 来源提交 `8d8d976fd04ae54e7c677705af937273d04a376a`，GPL-3.0。
- 本 Python 算法主体取自 MIT VN 源，没有依赖 SExtractor manager。
- 已有上述归档成员旋转解码；仍缺全版本指令集、其他加密变体、完整文件尾部与商业运行验证。
