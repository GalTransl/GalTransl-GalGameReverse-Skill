# Majiro：MJO 异或与文本 / Ruby 指令片段

## 能力边界
- 引擎 ID：`majiro`。
- 参考模块：[python/engines/majiro.py](../python/engines/majiro.py)。
- 实现完整 MJO V/X 头边界检查和代码区 XOR 状态转换。
- 另实现正文、换行与 Ruby 的真实指令片段汇编/反汇编。
- 不提供把变长片段塞回任意 MJO 的全量 writer。

## 识别证据
- 16 字节签名为 `MajiroObjV1.000\0` 或 `MajiroObjX1.000\0`。
- V 为明文代码，X 为 XOR 代码；不是整文件一起 XOR。
- `.mjo` 与资源 `.arc` 是不同层次。
- 代码区前存在入口点、行数、函数表与代码大小。
- 验证签名还不够，代码区长度必须恰好抵达文件末尾。
- 不使用扫描日文字符串作为完整函数/分支证明。

## 格式方言
- 签名后依次为 entryPoint、numLines、numFunctions 三个 u32。
- 每个函数表项为 nameHash + code-relative address，共 8 字节。
- 函数表后 u32 codeSize，再后面才是代码。
- 因此 codeOffset 为 `32 + 8*numFunctions`。
- 指令 opcode 为 u16，小字符串长度为 u16 且包括 NUL。
- 0801=ldstr，0840=text，0841=proc，0842=ctrl。
- 0810=callp 的参数在此为 hash/u32零值/u16参数数。
- Ruby 系统调用 hash 为 `0x3198FD01`。

## 容器到剧本路线
1. 识别 Majiro 归档版本并列出 MJO 成员。
2. 容器参考 [python/archives/majiro.py](../python/archives/majiro.py) 模块。
3. 取出成员后先用 `normalize_mjo` 规范到 V 状态。
4. 做完整反汇编时记录函数表、入口点、相对分支及所有代码区间。
5. 本文的片段算法仅作为该流程中的可测试构件。
- 不假定归档模块函数名，不把归档 CRC 与剧本 XOR 表混为一谈。

## 源码与算法对应
- 来源：`VNTextPatch-net8`，MIT。
- 提交：`d9c0fab7b72fdcf87d674ef12a84d3829c9188be`。
- 路径：`VNTextPatch.Shared/Scripts/Majiro/MajiroScript.cs`。
- `ReadHeader` 对应 `_code_base/normalize_mjo`。
- `GetEncryptionValue/GetEncryptionTable/Decrypt` 对应 `xor_code`。
- `AssembleText` 对应文本、Ruby 和换行片段生成。
- `MajiroAssembler.cs/WriteOperands` 证明 u16 字符串长度含 NUL。
- `MajiroOpcodes.cs` 与 `MajiroSyscalls.cs` 提供 opcode/hash 常量证据。
- 本模块不依赖 VN 自动换行器、字符隧道或字体组件。

## Python 接口与示例
```python
from python.engines.majiro import assemble_text, disassemble_text, xor_code
text = 'Hello[漢/かん]\nNext'
fragment = assemble_text(text)
assert disassemble_text(fragment) == text
assert assemble_text('A').hex() == '4008020041004108'
assert xor_code(xor_code(b'example')) == b'example'
```
- `normalize_mjo(data, encrypted=False) -> bytes` 只转换代码 XOR 和签名。
- `assemble_text(str, encoding='cp932') -> bytes` 产生指令片段。
- `disassemble_text(bytes) -> str` 只接收该规范片段语法。
- XOR 的 key 是 256 个 CRC32 多项式表项按小端展开，共 1024 字节循环。

## name / message 映射
- 文本片段本身只接收完整显示文本，不自动删掉前缀姓名。
- VN 会尝试从 `姓名「正文」` 中拆出 name/message，且一段可含多组。
- 上层若做这种转换，必须保留所有名字、引号及段内顺序。
- `ldstr` 也可能是选择、内部参数、Ruby 读音，不能统一当正文。
- 本反汇编器仅把规范的两个 ldstr + Ruby call 还原为 `[底文/读音]`。
- 任意函数调用、未知 ctrl 或混合 ldstr 用途直接拒绝。

## 回填、长度与控制码
- 每个 text 后面生成 proc；换行生成字符串值为 `n` 的 ctrl。
- Ruby 分别生成底文和读音的两个 ldstr，再生成 callp。
- 片段中的长度按严格编码后的字节数 + 1 计算。
- 单字符串最多 65534 个内容字节，超过 u16 容量拒绝。
- 不截断多字节字符，不静默换编码，不吞 NUL。
- 完整 MJO 的绝对地址相对代码区，而分支是相对操作数末尾。
- VN 的分支更新公式为 `新目标 - map(原操作数位置 + 4)`。
- 插入本片段后若不更新入口、函数表、分支和 codeSize，文件不可部署。

## 部署条件
- 原文件加密状态是独立元数据；不要因为能读 V 就假定游戏接受 V。
- 完整重定位实现需证明所有可到达代码及表项，而非只修最近分支。
- 重新封装资源包时保持成员名称与包版本。GARbro 能写 Majiro 归档 V1 不等于能原样重建 V3；容器 writer 的版本能力与本页 MJO 代码格式分别核实。
- 空改动先做加密往返，再做单句、Ruby、分支与存档验证。
- 公共层负责备份、manifest 与文件写出；本模块没有 CLI 或文件 IO。

## 验证与缺口
- 合成测试验证 CRC 表首项和跨 1024 字节的 XOR 自反性。
- 验证 MJO 签名切换、头部不变及 codeSize 不匹配拒绝。
- 验证真实指令黄金字节、Ruby 和换行片段往返。
- 覆盖未知 opcode、错误 Ruby 文法和超长字符串。
- 测试位置：`tests/test_engines_primary.py` 中 `MajiroTests`。
- 未实现任意 MJO 反汇编、分支修复、函数表修复或选择系统调用。
- 指令片段示例不能作为完整 writer 能力承诺。
- 没有商业素材、引擎运行时或付费服务验证。
