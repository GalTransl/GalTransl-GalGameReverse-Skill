# SystemNNN：开发版定长槽与发布版 word 地址

## 识别与两个格式
- `.nnn` 开发版与 `.spt` 发布版必须分开处理。
- `.nnn` 使用可辨认的 section 标记和固定文本容量。
- `.spt` 原始字节先整体 XOR `0xff` 才能读结构。
- 发布版内部长度和地址以四字节 word 为单位。
- 不能将 NNN 的固定槽写法套给 SPT，也不能把 SPT 地址当字节。
- 扩展名只是候选提示，必须验证对应结构。

## 容器与剧本
- 本模块读的是已提取的脚本，而非资源归档。
- `.nnn` 中的文本区不是单独容器，不应独立增减槽容量。
- `.spt` 数据项、代码项、消息表与字符串表组成另一布局。
- 本参考只对 NNN 提供固定槽 writer。
- SPT 只提供解密/项遍历/地址单位/字符串块算法，没有完整 writer。

## 源码依据
- 仓库：VNTextPatch-net8，许可 MIT。
- 固定版本：`d9c0fab7b72fdcf87d674ef12a84d3829c9188be`。
- 目录：`VNTextPatch.Shared/Scripts/SystemNnn/`。
- `SystemNnnDevScript.cs`：`GetTextRanges/WritePatched`。
- `SystemNnnReleaseScript.cs`：`Load/GetSptItems/FormatFileText/PatchAddresses`。
- `SystemNnnBaseScript.cs`：姓名与正文组合、格式控制的来源说明。
- 不能忽略来源发布版 writer 最后的地址修补与重新 XOR 阶段。

## Python 接口
- 模块：[systemnnn.py](../python/engines/systemnnn.py)。
- `read_nnn_slots(data, encoding="cp932") -> tuple[Slot,...]`。
- `patch_nnn(data, replacements, encoding="cp932") -> bytes`。
- `read_spt_items(data) -> tuple[dict,...]` 接受加密的发布版字节。
- `word_to_offset(address)` 与 `offset_to_word(offset)` 显式转换单位。
- `encode_spt_text(text, encoding="cp932")` 返回解密态对齐文本块。
- 所有函数均为独立内存算法，无来源项目运行时依赖。

## NNN 使用示例
```python
from python.engines.systemnnn import read_nnn_slots, patch_nnn
# original 是包含已核实 section 的 NNN 原始 bytes。
slots = read_nnn_slots(original)
patched = patch_nnn(original, {0: "名前\r\n「本文」"})
assert len(patched) == len(original)
assert read_nnn_slots(patched)[0].text == "名前\r\n「本文」"
```

## NNN 固定槽结构
- 消息标记为 `--MESSAGEDATA  \0`，共 16 字节。
- 类型在 section 起点加 `0x10`。
- 文本容量在 `+0x3c`，附加表数量在 `+0x4c`。
- 文本位置是 `section + 0x50 + 4 * extra_count`。
- Print/LPrint/Append 接受为文本，Draw 类型不导出。
- 命令标记为 `-COMMANDDATA   \0`，只导出 Case 命令。
- Case 文本在 `section+0x60`，容量取 `+0x24`。
- 类型未知、区间越界、重叠 section、槽内没有 NUL 都会拒绝。

## NNN 回填约束
- 容量包含终止 NUL；译文字节数加一必须不超过容量。
- 超长立即报错，不自动截断、不扩槽、不移动后续数据。
- 短译文写入新 NUL，但保留其后原始填充字节。
- 未修改槽和所有非文本数据保持原样。
- 默认严格 CP932；编码失败不能降级成问号。
- sidecar 必须保存原槽索引、位置、容量及原文身份。

## SPT 算法与边界
- `read_spt_items` 检查输入非空且长度为四的倍数。
- 解密后首项必须是 Data/DataHeader，并有至少八个 word。
- 每项长度是 word 数量，不能为零，也不能越过文件末尾。
- Data/SystemCommand 项需要 code 字段，DataTable 另需 table type。
- 消息表/字符串表的计数和基址须在字数组范围内。
- item 返回字节 offset 和 word_index，避免混淆。
- 文本 builder 添加 NUL，再补零到四字节对齐。
- builder 输出是明文块；没有自行对整脚本重加密。

## name/message 与姓名
- 来源将符合“姓名 CRLF 引号对白”的文本拆成两种角色。
- 来源还移除部分 `//` 注释并进行格式化。
- 本固定槽接口保留整条原始字符串，不做这些有损展示转换。
- 姓名识别若由上层实施，必须记录可逆组合方式。
- SPT 表项本身不能证明某条字符串是姓名还是资源。
- 选项和不同 Print 类型的实际引用仍需完整指令分析。

## 控制码与部署缺口
- 来源的粗体/斜体/下划线、井号替换和排版未在此自动执行。
- 保留原始控制符和变量，不把它们当普通可翻译标点改写。
- 未实现 SPT 选择项扩展计数、文本引用发现及全部地址重定位。
- 不允许把 `encode_spt_text` 宣传成发布版整文件 writer。
- 字体扩展、中文编码方案、外层容器回包均属于未完成阶段。

## 验证状态
- 合成测试覆盖 NNN 固定容量回填、原填充保留与超长拒绝。
- 覆盖 SPT XOR、word 单位、头部/项长度与四字节文本填充。
- 坏输入包括短 section、无标记、非对齐 SPT 和零长度项。
- 测试文件：[test_engines_secondary.py](../tests/test_engines_secondary.py)。
- 未进行真实游戏加载验证，支持声明仅限以上局部边界。
