# Violent BIN 规则：只读 JIS 候选证据

## 这不是一个引擎
- 状态：`analysis-only / candidate-only`。
- Python：`python/engines/violent.py`。
- `_BIN_Violent` 是暴力候选查找规则，不是可识别 VM 家族。
- 模块没有 writer，也不输出伪造的 name/message 角色。
- 保留它是为了说明来源中的分析能力和不可跨越的证据边界。

## 输入必须有界
- `scan_candidates` 要求调用者明确给出 start/end。
- 输入必须已经是待分析的明文字节区域。
- 不自动解密、解压或遍历任意文件系统。
- 单次扫描区域最多 64 MiB。
- 可设置候选数量上限，超限直接失败。
- 没有给出区域边界时不会偷偷扫整个未知包。

## 来源 JIS 子集
- `_BIN_Violent` 使用 NUL 作为切分边界。
- 至少四字节，首字节需在来源指定的双字节范围内。
- 默认允许的单字节只有 CR 和 LF。
- 双字节 lead 允许 81..9F、E0..EF、FA..FB。
- trail 允许 40..7E 或 80..FC。
- FC 行额外只接受 trail 40..4B。
- 这不是完整 CP932，更不是所有 Unicode/GBK 的通用检测器。
- F0..F9 私用区、ASCII 和半角假名不会自动放开。

## 双重验证
- `is_allowed_sjis` 先执行字节对规则校验。
- 候选随后还要能被 CP932 严格解码。
- 字节范围成立但码位不可解码，仍不输出候选。
- 最后缺少 NUL 的尾片段不作为完整字符串。
- 一字节孤立 lead、非法 trail 都不能“忽略错误继续”。

## 输出语义
- 每项包含 offset、end、text、`role="unknown"`。
- `status` 明确是 `candidate-only`。
- 没有 name、message 或 dialogue 字段。
- 字符串可能是资源路径、调试输出、字库表或参数。
- 即使文本像台词，也需要指令引用与容器语义证据确认。
- 不能把候选清单直接当可回填的翻译清单。

## 为什么没有 writer
- 来源规则没有给出每个候选的原始长度字段。
- 没有完整地址表、跳转指令或名字/正文角色表。
- 变长替换可能移动资源、代码和后续成员。
- 定长截断也可能破坏多字节字符或控制码。
- 因此不提供以 byte replace 冒充引擎支持的函数。
- 必须先找到实际引擎，再使用经过验证的专用 writer。

## Python 示例
```python
from python.engines.violent import scan_candidates
blob = "試験".encode("cp932") + b"\x00"
evidence = scan_candidates(blob, start=0, end=len(blob))
assert evidence[0]["role"] == "unknown"
```
- 这个示例仅证明字节候选算法，不证明任何游戏脚本格式。

## 后续需要的证据
- 找到实际容器和解包/解密路线。
- 确认候选被哪条字节码指令或哪个表项引用。
- 区分名字、正文、选项、控制参数与资产路径。
- 确定编码、长度计量单位、结束符和地址基址。
- 确认全部 relocation 与部署路径后才设计 writer。
- 没有这些证据，应该停止在分析结果阶段。

## 来源、许可与测试
- SExtractor 提交 `8d8d976fd04ae54e7c677705af937273d04a376a`。
- 规则：`src/reg.yaml` 的 `_BIN_Violent`。
- 字节对算法：`src/common.py` 的 `isShiftJis`、`checkJIS`。
- 来源仓库 GPL-3.0，保留 satan53x / SExtractor 贡献者归属。
- 已测允许的 CRLF、合法双字节、ASCII 和私用区拒绝。
- 已测末尾缺 NUL、未知角色标记与候选数量限制。
- 测试：`tests/test_engines_tools_b.py`，没有商业文本或运行游戏。
