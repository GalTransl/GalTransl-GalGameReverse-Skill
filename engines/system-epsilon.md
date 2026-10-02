# SYSTEM-ε：BIN 文本段与候选跳转模式

## 能力边界
- 状态：`partial / preset-segment-only`。
- ID：`system-epsilon`；模块：`python/engines/system_epsilon.py`。
- 来自 `_BIN_SYSTEM-ε` 预设，不是完整引擎反编译器。
- 独立段可重建长度，整文件地址不自动修改。
- 明确区分“指针候选模式”与“已经证明的全部 VM 跳转”。

## 识别与输入边界
- 原预设以 `00 04 00` 分隔文本候选。
- 首行跳过、忽略解码失败等上游选项不作为本模块自动猜测。
- 调用者提供分隔符之后的完整、单一文本段。
- 文本段是非零长度字节、可选名字前缀、文本、NUL。
- 名字前缀为原字节 `81 94`，不自行翻译该标记。
- 无名字前缀时角色为 message。
- 段中间若出现 NUL 或正文为空则拒绝。

## 长度字段的真实含义
- 来源 `preLen=1`，长度字段在整个匹配的开头。
- `preLenStrict=0` 表示不能把存储长度强行解释为正文长度。
- 因此回填使用“原长度 + 编码后字节差”。
- 不凭空发明该字段是否包含 opcode、终止符或其他头部。
- 长度只能是 1..255；溢出或变成零都会拒绝。
- 译文严格编码，不使用忽略编码错误模式。

## 提取 name / message
- `parse_segment` 返回 role、text 和实际正文起点。
- 名字前缀不包含在 text 内，但仍在回填段中保留。
- 不把未分段二进制中的任意 NUL 串作为正文。
- 名字与正文的关联、段落连续性需要外部记录目录。
- 本模块没有作者/游戏名称特例或固定角色映射。

## 回填与控制码
- `rewrite_segment` 按新编码长度修正段头的一字节值。
- 保留原名字标记和 NUL。
- 低位控制字节序列必须相同。
- 译文若让 message 变成名字标记开头，会拒绝角色改变。
- 返回值只是一条记录；没有自称通用 full-file writer。

## 跳转候选证据
- `pointer_candidates` 实现来源的 `addrFix` 字节模式。
- 可显式启用第二组 `addrFix2`，默认关闭。
- 包含 1D/30/2E/2F 指令形态及四字节捕获字段。
- 第二组保留负向后顾对应的排除条件，不扩大为任意 u32。
- 返回 `(字段地址, 存储值)`，不默认其基址或有效性。
- 调用者还需确认指令边界、目标边界与全部其他引用。

## Python 示例
```python
from python.engines.system_epsilon import parse_segment, rewrite_segment
item = parse_segment(isolated_segment)
new_segment = rewrite_segment(isolated_segment, "合成試験")
```
```python
from python.engines.system_epsilon import pointer_candidates
evidence = pointer_candidates(script_bytes, include_secondary=False)
```
- 候选列表不足以授权变长整文件回填。

## 部署条件与缺失步骤
- 缺少容器、解密、完整 opcode 表、记录定位和全量地址修复。
- 缺少名字与消息配对、选择项语义及字体/换行验证。
- 部分二进制参数可以偶然匹配模式，必须复核。
- 未证明完整地址覆盖之前，只能用作分析和局部算法参考。

## 来源、许可与测试
- SExtractor 提交 `8d8d976fd04ae54e7c677705af937273d04a376a`。
- 规则证据：`src/reg.yaml` 的 `_BIN_SYSTEM-ε`。
- 长度修正证据：`src/extract_BIN.py` 与 `src/extract_TXT.py`。
- 来源仓库 GPL-3.0；保留 satan53x / SExtractor 贡献者归属。
- 合成测试验证名字标记、长度差、主模式和排除条件。
- 另测一字节长度溢出拒绝；没有真实游戏执行。
- 测试：`tests/test_engines_tools_b.py`。
