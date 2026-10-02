# AZSystem：ASB 包装与解密后命令

## 识别与版本轴
- 本页对应 `Engine_AZSystem`，输入成员通常为 `.asb`；[Artemis](artemis.md) 也使用该后缀，不能按后缀混用 parser。
- `ASB\x1A` 是 tools v1/v3 包装的线索，但**不能区分 v1 与 v3**。
- tools v2 面向某些非 `\x1A` 头版本；本 leaf 未移植它。
- 另有一条独立版本轴：提取器 opcode profile `0/1/2`。
- 包装解密版本与 opcode profile 不是同一个参数，禁止自动混用。
- 原工具 README 明确：GARbro 解包后已经能看见明文时，不再 decrypt。
- 对目录中的 ASB 先记录原始 magic、压缩长度和输出长度。
- 本函数集不根据后缀猜测加密状态。

## 容器与部署路径
- 先由已确认适用的容器工具提取 ASB 成员。
- `decrypt_v1` 只接受成员字节，不访问原游戏目录。
- 解密后保留原 16 字节头，加上完整解压正文。
- 头中压缩长度在这种中间态可以仍是原值，不应用它切割正文指令。
- 源 `tools/AZSystem/README.md` 记录了 ASB 免封包覆盖方案。
- 其流程是修改明文，再 encrypt，放入游戏根目录。
- 这属于源码记录的路径，不等于本次已在所有 AZSystem 游戏验证。
- 公共层必须让用户确认版本、输出目录和覆盖优先级。

## v1 包装算法
- [decrypt_v1](../python/engines/azsystem.py#L84) 实现 tools 的 v1 方言。
- `LE32[4]` 是压缩字节数，`LE32[8]` 是未压缩字节数。
- 从 `0x10` 开始才是加密压缩正文。
- 密钥为 `uncompressed_size XOR 0x9E370001`。
- 每个完整 little-endian 32 位字减去密钥，按 `2**32` 取模。
- 尾部不满四字节的部分原样保留，这是源算法的确切行为。
- 结果再进行 zlib 解压，不是先解压再 XOR。
- 默认最大输出 64 MiB，必须精确等于声明的未压缩长度。
- 截断、额外 zlib 尾流和超预算输出都会被拒绝。
- [encrypt_v1](../python/engines/azsystem.py#L103) 反向压缩并逐字加密钥。
- 加密同时重写压缩/未压缩长度，保留头 `[12,16)`。

## 解密后命令布局
- [extract_fields](../python/engines/azsystem.py#L38) 从文件 `0x10` 顺序读取。
- 每条命令以 16 位小端总长度开头，长度包含这两个字节。
- 零长度、短于命令最小结构、越过文件末尾均报错。
- 命令正文前六字节参与文本 opcode 签名判定。
- profile 0：message `1F`，choice `1D/11/1C`。
- profile 1：message `1B`，choice `16`。
- profile 2：message `1E`，choice `1B`。
- 上述 opcode 后五字节均为零，不能只匹配单字节。
- 文本参数从**命令正文偏移 10** 开始。
- message 的首参数为 name，第二参数为 message。
- choice 则逐参数读取到命令末尾，保留其顺序。

## 操作数与控制码
- [read_text_operand](../python/engines/azsystem.py#L22) 处理短操作数。
- 操作数第一字节是该操作数总长度，第二字节为 tag。
- tag `07` 是文本，末尾必须有 NUL。
- 文本捕获不含长度、tag 或末尾 NUL。
- tag `06/1C/05/04` 是已知可跳过控制参数，不导出成台词。
- 未知 tag 不做“跳到下一字节试试”，而是明确拒绝。
- 源格式长度只占一字节，绝不允许静默取模或截断。
- 返回跨度是明文 ASB 的字节位置；编码由上层显式处理。

## 回填与地址
- [replace_field](../python/engines/azsystem.py#L74) 只改等字节长字段。
- 替换前检查旧 raw 和位置，译文不能含 NUL。
- 源提取器还尝试修正 `04/05/0A/0D` 命令的跳转。
- 跳转地址基准为剔除 16 字节文件头后的命令区。
- 源逻辑对 `<0x80`、超界和无匹配目标有特殊跳过分支。
- 本参考没有证明这些分支覆盖全指令集，因此不提供变长重定位。
- 变长请求抛出 `NotImplementedError`，不生成“似乎成功”的 ASB。
- 对等长明文完成回填后，仍须按正确包装版本重新加密。

## 调用示意
```python
from python.engines import azsystem
plain = azsystem.decrypt_v1(member_bytes)
fields = azsystem.extract_fields(plain, version=1)
changed = azsystem.replace_field(plain, fields[1], encoded_translation)
result_bytes = azsystem.encrypt_v1(changed)
```
- 示例明确假定包装 v1 与 opcode profile 1，二者都须独立核实。
- 任何未知参数都应停止，不把 v1 作为普适 fallback。

## 验证与限制
- 合成测试涵盖三个 opcode profile、控制参数跳过、字段语义和起点。
- 包装测试验证 zlib 与算术变换互逆、长度预算及短命令拒绝。
- 无真实游戏运行验证；没有使用原模块的 `ExVar` 或 GUI。
- 未实现外层 archive、tools v2/v3、完整跳转重定位、字体/字库修改。
- 可用于理解和验证局部数据，不是完整 ASB 编辑 CLI。

## 来源与许可
- SExtractor 固定提交 `8d8d976fd04ae54e7c677705af937273d04a376a`。
- 原路径：`src/extract_AZSystem.py`、`src/engine.ini`。
- 包装来源：`tools/AZSystem/asb_decrypt.py`、`asb_encrypt.py`、`README.md`。
- 关键符号：`Config.init`、`readText`、`readFileDataImp`、`decryptData`。
- [固定提取源码](https://github.com/satan53x/SExtractor/blob/8d8d976fd04ae54e7c677705af937273d04a376a/src/extract_AZSystem.py)。
- 依 SExtractor GPLv3 根许可证，改编模块标为 GPL-3.0-only。
- 详细来源和验证范围见 [provenance](../provenance/sextractor-core.json)。
