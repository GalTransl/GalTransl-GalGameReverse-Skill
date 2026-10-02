# GSD：先 decode 的 v2 族 SPT 与 global.dat

## 首先区分两个版本概念
- `src/extract_GSD.py` 顶部注明 `Engine: GSD v2`。
- `engine.ini` 明说 SPT 要先用 GSDTools decode，v3 请用 GSDTools 提取。
- 同一预设又有 version 参数 `1/2/3`；这些是提取器命令布局 profile。
- 不能把 profile=3 宣称为已支持 GSD 第三代引擎。
- 本 leaf 只接受**已 decode 的 GSD v2 族** profile 1 或 2。
- profile 3 和完整 GSD v3 都明确拒绝，避免制造兼容性承诺。
- 文件名 `.spt` 不证明数据已 decode，必须保留转换来源。
- `global.dat` 是名字表来源，不是可任意省略的辅助文件。

## 目录、容器与转换
- 典型工作集由 `data.gsp` 包、提取后的 `.spt`、同目录 global.dat 组成。
- `tools/GSD/decode.bat` 调用 `SPT_Decoder.exe` 输出到 `dec/`。
- `tools/GSD/pack.bat` 调用 `GSP_Editor.exe` 处理 `dec/new/`。
- README 指向 ReVN 发布物及 `ZQF-ReVN/RxGSD` 源码。
- 这两条命令是上游工作流证据，不是本包附带或自动执行的工具。
- 当前 leaf 不读取 GSP、不执行 EXE、也不猜解码密钥。
- 应将原 SPT、decode 后 SPT 和所用版本分别记录，不能覆盖唯一原件。
- 未 decode 输入不可通过“跳过不合法 cell”修补成有效文本。

## 对话记录定位
- [read_dialogue](../python/engines/gsd.py#L50) 要求调用方提供候选 offset。
- profile 1 的起始四个 LE32 为 `1,0,0,FFFFFFFF`。
- profile 2 的对应签名为 `1,0,0,0`。
- 该签名可能出现在非文本数据，不能单靠搜索成功认定整文件已解析。
- name_id 位于记录起点加 `0x28`。
- name_id=`FFFFFFFF` 表示没有可附加的姓名。
- 字符 cell 数位于起点加 `0x34`。
- 固定文本头总长 `0x40`；之后每个 cell 长 `0x0C`。
- count 包含最后一个结束 cell，支持范围为 2 至 `0x300`。
- 整个 `count*12` 区域必须在输入范围内，不允许截断返回。

## cell 不是普通字符串
- 普通字符 opcode 是 LE32 值 `07`。
- 字符字节位于 cell 的 `[8,12)`，遇 NUL 结束。
- profile 1 的结束 opcode 是 `08`。
- profile 2 的结束 opcode 是 `0A`，还允许控制 opcode `05/08/09`。
- 控制 cell 的参数不是可翻译字符，不应塞进普通 Unicode 文本。
- [Dialogue.text_runs](../python/engines/gsd.py#L20) 将普通字符连续解码。
- 遇到控制 cell 时返回 typed Cell 对象，保留完整十二字节。
- 这样不会把源压缩成三字节的控制串误当汉字再编码。
- 最后的结束 cell 独立保存，profile 1 的遗留字符信息也不丢弃。
- 严格编码失败会报错，不使用忽略错误来合并破碎双字节字符。

## global.dat 名字表
- [read_global_names](../python/engines/gsd.py#L86) 返回按 ID 顺序排列的名字。
- global.dat 从偏移八开始遍历名字表之前的 section。
- 每个 section 先有 command_count。
- 每条前置 command 是两个 LE32 长度字符串，再加 `0x23` 个整数。
- 本函数要求显式 skip_sections，不照搬源按长度猜 section 数的算法。
- 名字区先有 count，每个名字记录固定 `0x104` 字节。
- NUL 必须在该记录内部，禁止越过记录边界寻找结束。
- 姓名严格解码，空名可保留；记录个数超出文件会报错。
- 解析 SPT 后可用 name_id 查这个元组，越界应由调用方报错。
- 源 SPT 提取附加的名字位置为 `[-1,-1,-1]`，即不在 SPT 内写回。
- 不能用角色 ID 的文本显示名替换数字 ID。

## 选择与写回边界
- 源 `getSelect` 通过 `select.spt/dialog.spt` 特征定位选项。
- profile 1/2 的选项 opcode 是 `23`，profile 3 则变为 `25`。
- 选项还涉及开闭 NUL、长度字段和后续九字节步进。
- 本 leaf 没有移植选项提取，必须在交付报告中明确遗漏。
- [write_spt](../python/engines/gsd.py#L117) 始终抛出 `NotImplementedError`。
- 这包括普通字符重排、控制 cell 重建、count 修正和最终 encode 阶段。
- 源 writer 将所有 `>=80` 字节按双字节推进，不能盲目用于半角假名/新编码。
- 源 global writer 复用或清空记录头的行为也未照搬，避免破坏不透明字段。
- 因此本页提供真实解析算法，但不伪称完整往返已经实现。

## 使用示意
```python
from python.engines import gsd
names = gsd.read_global_names(global_bytes, skip_sections=verified_section_count)
entry = gsd.read_dialogue(decoded_spt, verified_offset, profile=2)
name = None if entry.name_id is None else names[entry.name_id]
runs = entry.text_runs(encoding="cp932")
```
- runs 中非 str 的对象是必须原样保留的控制 cell。
- 部署前仍需完整 GSDTools writer/encode/pack，并在游戏内回归测试。

## 验证与许可
- 合成测试覆盖 profile 1/2、name ID、控制保留、结束 opcode 与名字记录。
- 测试拒绝短 cell、错误 profile、未实现 writer；未使用付费 API 或真实游戏。
- SExtractor commit 为 `8d8d976fd04ae54e7c677705af937273d04a376a`。
- 原路径：`src/extract_GSD.py`、`src/engine.ini`、`tools/GSD/*` 上述文本文件。
- 原符号：`GSDManager.clear/readGlobal/getText/getSelect/writeSpt`。
- [固定源码](https://github.com/satan53x/SExtractor/blob/8d8d976fd04ae54e7c677705af937273d04a376a/src/extract_GSD.py)。
- 改编按 SExtractor GPLv3 保守标为 GPL-3.0-only，外部 ReVN 工具许可须另核实。
- 精确来源和阶段范围见 [provenance](../provenance/sextractor-core.json)。
