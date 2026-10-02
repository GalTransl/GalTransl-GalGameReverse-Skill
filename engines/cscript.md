# CScript：已解压剧本中的有界记录

## 范围与版本
- 对应 `Engine_CScript`，不是任意叫 script 的文件格式。
- 原读取器支持版本参数 `1/10/11`，`0` 是启发式自动选择。
- 自动分支仅看文件首整数是否小于 `0x10`，并非可靠 magic。
- 本参考要求显式版本，拒绝自动猜测。
- leaf 输入为**已经解压且去掉包装头**的脚本 payload。
- 不接受原 scr.dat 容器，也不把压缩成员直接当指令扫描。
- 这里实现文本/选项的局部记录解析，不是完整反汇编器。

## 外层目录与压缩线索
- `tools/CScript/dat_pack.py` 默认输出 `scr.dat`。
- 容器开头是成员数，随后是定长名字加 length/offset 的索引。
- 名字区长度参数常见 `0x2C/0x44/0x64`，必须从原包核实。
- 每条索引总长为 NameLen 加八字节，不存在单一通用表宽。
- 名称为 CP932；排序规则也是原封包器的一部分，不能擅自换排序。
- 提取器版本 1 的成员压缩尺寸字段位于 `0x10` 起。
- 版本 10/11 的尺寸字段从 `0x0C` 起。
- 两个 LE32 依次记录压缩长度与未压缩长度。
- 上游调用 `libs.lzss.lzss_s` 的 native 实现进行压缩/解压。
- `tools/CScript/README.md` 明确提到 Python 3.11 的 `.pyd`。
- 本 leaf 没有复制依赖，也没有使用其他引擎 LZSS 方言冒充。
- [unpack_script](../python/engines/cscript.py#L93) 和 [pack_script](../python/engines/cscript.py#L97) 均明确拒绝。
- 外部转换完成后，应将 payload 及转换工具/版本一同记录在 manifest。

## 局部记录读取
- [parse_record](../python/engines/cscript.py#L33) 需要明确的候选 offset。
- offset 相对于解压 payload，不是容器或包装文件起点。
- 只读取一条已知类型记录，不在全文件匹配四字节后假装已完整解析。
- 返回 Record 中包含 offset、end、version、opcode 与 Field 元组。
- Field 的 raw 与 start/end 都保留原始编码字节。
- 所有整数、跨距和文本长度都做边界检查。

## 版本 1 的差异
- message opcode 为 `3F 00 00 00`。
- opcode 后先跳过 `0x11` 字节序号/前缀。
- 然后 LE32 name_length，加原始 name 字节。
- message 前还有五字节前缀，再读 LE32 message_length 与正文。
- choice opcode 为 `15` 或 `1A`。
- 选项记录先跳八字节，再读取 count。
- count 及控制前缀合计跨过 `0x15` 字节后开始第一项。
- 后续每项之前还要保留五字节前缀。
- 源 profile 的选项 count 范围为 2 至 5。
- 本参考保留这些前缀，不把它们当文本译掉。

## 版本 10 / 11 的差异
- message opcode 为 `11`，随后四字节序号。
- name 与 message 都使用 LE32 字节长度，无 NUL 长度修剪。
- message 后必须有零整数作为源候选校验条件。
- 该零整数不是本 Record.end 的一部分，留在未解析区。
- choice opcode 为 `14`，count 和控制字共八字节。
- 版本 10 各选项直接连续排列。
- 版本 11 从第二个选项起，每项前多一个四字节控制字段。
- 把 10 当 11 会将文本长度读成控制字；应报错而非跳过。
- 源 name 最大 `0x40` 字节，message 最大 `0x200` 字节。
- 选项长度上限按不同 profile 保守继承，禁止无界切片。

## name/message 与转义
- message 记录第一文本 Field 为 name，第二为 message。
- choice 记录所有 Field 标记 choice，不自动拼接。
- 源预设处理字面量 `\n`，它与实际 CRLF 不是同一控制形式。
- 翻译时应保留原转义结构，不能在编码层随意替换成真实换行。
- Python leaf 不执行 `ctrlStr` 配置，更不使用源 `eval` 执行字符串。
- 编码由上层严格指定，未知原字节不丢弃。

## 回填与跳转缺口
- [replace_record](../python/engines/cscript.py#L78) 重新解析并核对旧 Record。
- 只允许同字节数替换，保持全部前缀与布局。
- 变长抛 `NotImplementedError`，并不只改文本长度就输出。
- 原实现有 `dealJump0/dealJumpNormal0/dealJumpCondition0/checkJump`。
- profile 10/11 对应的跳转配置明确有 TODO，不能宣称已解决。
- profile 1 也涉及分支数组、ASCII 跳转标记和地址监听，不是统一四字节修正。
- leaf 没有完整指令覆盖证明，故所有 profile 均不开放重定位。
- 即使局部等长修改成功，还缺包装压缩及容器封包两个独立阶段。

## 调用示意
```python
from python.engines import cscript
record = cscript.parse_record(decompressed_payload, known_offset, version=11)
patched_payload = cscript.replace_record(decompressed_payload, record, {1: encoded_translation})
```
- 这里只返回 payload；不能把它改后缀为原剧本并宣称可运行。

## 验证与许可
- 合成测试覆盖三个 profile 的 name/message、v11 选项前缀与短输入拒绝。
- 验证等长回填和未实现阶段拒绝，无原 `.pyd` 或 GUI 依赖。
- 未使用真实商业游戏资产，也未验证 native LZSS 方言兼容性。
- 固定源提交：`8d8d976fd04ae54e7c677705af937273d04a376a`。
- 来源为 `src/extract_CScript.py` 的 `dealText/0`、`dealSel/0`、`config` 等。
- 另核实 `src/engine.ini`、`tools/CScript/dat_pack.py` 和 `README.md`。
- [固定源码](https://github.com/satan53x/SExtractor/blob/8d8d976fd04ae54e7c677705af937273d04a376a/src/extract_CScript.py)。
- 改编遵循原 GPLv3，保守标为 GPL-3.0-only；详见 [provenance](../provenance/sextractor-core.json)。
