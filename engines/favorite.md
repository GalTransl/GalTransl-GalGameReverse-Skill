# Favorite：HCB u8 字符串长度与绝对地址更新

## 能力边界
- 引擎 ID：`favorite`。
- 参考模块：[python/engines/favorite.py](../python/engines/favorite.py)。
- 实现 HCB 已证明代码区域的指令子集、字符串编码和重定位。
- 同时提供 SPEAK 函数姓名候选收集，明确属于启发式上下文。
- 不实现整个 HCB 文件、系统导入表、ThreadStart 或超长句拆分 writer。

## 识别证据
- `.hcb` 是候选后缀，但本入口没有统一强魔数可代替结构检查。
- msg-tool 从文件起始 u32 取得 script_len。
- 在 script_len 位置还有一个 main_script 起始地址。
- 从文件偏移 4 开始的指令区分成函数区域与主剧情区域。
- 余下尾部含额外数据和系统导入信息，不能盲目当无用 trailer 删除。
- Favorite 的资源 BIN 与脚本 HCB 不是同一种文件。

## 格式方言
- opcode 为 u8，参数按各 opcode 的真实宽度读取。
- 本子集接收 00、01、02、04、05、06、07、08、09、0A、0B、0C、0E。
- 01 是两个 u8 initstack 参数。
- 02/06/07 使用 u32 绝对地址，分别为 call/jmp/jmpcond。
- 0A/0B/0C 为不同宽度整数；03 syscall 不在本参考子集。
- 0E 字符串是 u8 长度 + cstring，长度包括 NUL。
- 因此内容最多 254 个编码字节，不是 254 个汉字。
- 长度零、提前 NUL、越界及未知 opcode 全部拒绝。

## 容器到剧本路线
1. 先核查 HCB 是外置文件还是具体容器成员。
2. GARbro-Mod `ArcFormats/Favorite/ArcBIN.cs`、`ArcFVP.cs` 是资源层参考。
3. 完整 HCB reader 校验 script_len、main pointer 和系统导入表。
4. 只将已证明的全部代码区域交给本模块，保留原文件绝对基址。
5. 返回的地址映射交给完整文件集成层更新外围头尾。
- 本函数默认 base=4，但调用者不得把任意中间片段冒充整段代码。

## 源码与算法对应
- 来源：`msg-tool`，GPL-3.0-or-later。
- 提交：`f72716cee88554d40c1cdface2812493b14ca653`。
- 路径：`src/scripts/favorite/disasm.rs`。
- `OPS/Data::read_func` 对应参数宽度、cstring 和长度检查。
- `find_speak_functions/collect_speaker_names` 对应姓名候选启发式。
- `src/scripts/favorite/hcb.rs/HcbScript::import_messages` 对应变长回填与地址更新。
- 原 writer 另处理 ThreadStart 前一条 pushint 地址，Python 明确没有覆盖。
- 原 writer 会复制调用块拆超长主剧情句；本参考选择拒绝，避免错误复制控制流。

## Python 接口与示例
```python
from python.engines.favorite import encode_literal, parse_code, relocate_code
code = encode_literal('A') + b'\x04'
assert code == b'\x0e\x02A\0\x04'
changed = relocate_code(code, {4: 'Longer'}, base=4)
assert parse_code(changed.code)[0].operands == ('Longer',)
assert changed.addresses[4 + len(code)] == 4 + len(changed.code)
```
- `encode_literal(str) -> bytes` 包含 0E opcode。
- `parse_code(bytes, base=4) -> tuple[Instruction, ...]`。
- `relocate_code(bytes, {原指令绝对地址: text}) -> Relocated`。
- `Relocated.addresses` 映射全部指令起点及旧 code-end。

## name / message 映射
- HCB pushstring 可能是正文、姓名、资源名或其他参数。
- 不能无条件把全部 0E 字符串当翻译正文。
- 源码把 initstack(3,0)/(5,0) 视为 SPEAK 候选函数。
- `speaker_candidates` 保留该范围里所有非空字符串，包括问号姓名。
- 不照搬“只选最后一个非问号姓名”的有损缩减。
- 候选表是只读上下文，不代表每个主剧情 call 已有可靠 name 槽位。
- 若真的修改定义处字符串，应明确以对应 0E 的原地址批准修改。

## 回填、长度与偏移
- 每条新字符串先严格编码，按字节检查不超过 254。
- 不在多字节字符中间截断，不用宽字符个数当 u8 长度。
- 顺序重建代码时记录每条指令旧绝对地址到新地址。
- 第二遍修复所有已识别 02/06/07 的目标值。
- 目标只能是原解析的指令边界，内部地址或范围外地址拒绝。
- 既处理向前跳转也处理向后跳转。
- 外围必须更新文件开头 script_len 以及旧 script_len 处的 main 指针。
- ThreadStart、系统导入与其他隐藏地址未证明时禁止部署完整文件。
- 输出重新解析，验证更新后的跳转目标仍在正确边界。

## 部署条件
- 必须保留原函数区/主剧情区边界和尾部系统导入表。
- 仅脚本 code bytes 成功往返，不足以证明完整 HCB writer 正确。
- 超长句应先采用有证据的运行时显示方案，本参考绝不自动截断。
- 名字候选要人工或结合控制流验证，不直接变为翻译字段。
- 公共层负责原文件保护、路径、manifest、备份和最终写出。

## 验证与缺口
- 合成测试覆盖 u8 黄金字节、127 个双字节字与 128 个时拒绝。
- 覆盖前跳/后调地址更新和 code-end 映射。
- 覆盖问号/正常姓名同时保留、不支持 syscall、错误长度及目标拒绝。
- 测试位置：`tests/test_engines_primary.py` 中 `FavoriteTests`。
- 没有完整 HCB header/tail writer、ThreadStart 或运行时自动长句拆分。
- 未实现全 opcode、动态说话人和所有字符串用途分析。
- 无商业资产、外部工具、网络和游戏运行验证。
