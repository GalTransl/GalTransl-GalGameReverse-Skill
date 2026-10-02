# ANIM：滚动密钥 DAT / SCE 局部参考

## 适用范围与判定
- 本页对应 SExtractor `Engine_ANIM`，不是所有含 ANIM 字样的资源。
- 预设后缀为 `.dat`；源码还对文件名以 `sce` 结尾的情况分支。
- 扩展名不足以识别引擎，必须结合目录来源和解密后的结构检查。
- 本次核实的源码没有强制校验固定 magic；不能捏造一个通用签名。
- 首 `0x14` 字节是本算法保留的头部。
- 头部 `[4,0x14)` 的 16 字节是初始密钥，不是文本。
- 明文中连续 NUL 常用于分段，不能把空段或 NUL 直接删掉。
- DAT 的文本起点是 `0x14`。
- SCE 的文本起点是 `LE32[0x18] + 0x14`，须在解密后读取。
- 未知包内成员先保留原名和原相对目录，再确认它是 DAT 还是 SCE。

## 容器 → 剧本
- 这份 leaf 不识别或解包外层资源容器。
- 输入必须是已从正确容器取出的单个加密成员，或明确已解密的成员。
- 不能对“看不见日文”的任意 DAT 反复 XOR 直到看起来像文本。
- 建议记录原成员哈希、头部、后缀判定和解密开关。
- 对源工具已解密的成员再解密一次，会破坏正文。
- 容器 writer、启动目录覆盖优先级和游戏补丁名均未在此实现。

## 引擎特有算法
- [crypt](../python/engines/anim.py#L46) 对 `0x14` 之后逐字节 XOR。
- 每 16 字节重新计算一次密钥，依据该组最后一个**明文字节**。
- 因而加密与解密不能盲目共享“最后输出字节”作为更新依据。
- [switch_key](../python/engines/anim.py#L9) 使用 `last_plain & 7` 选择八个分支。
- 加法全部按 8 位取模，溢出不是编码错误。
- 更新是顺序赋值，不是对原 key 的并行映射。
- 例如分支 6 先更新 key[9]，随后 key[15] 和 key[1] 使用更新后的值。
- 分支 3 中 key[13] 同样依赖本轮更新后的 key[11]。
- 所以“整理”为列表推导并一次替换全部 key 会改变格式。
- 不完整的末组只处理实际存在的字节，不读越界。
- 小于 `0x14` 的输入直接拒绝，不返回部分解密结果。

## 文本、name 与控制
- [nul_tokens](../python/engines/anim.py#L77) 返回非空原始字节跨度。
- 返回的 start/end 都是**明文成员内的字节偏移**，不是字符位置。
- tokens 不宣称每一项都是台词；调用方仍要筛选控制串。
- 源预设先跳过 NUL 和长度不超过一字节的项。
- `^w\d+([a-z])$` 捕获的单字符是姓名变量，不是显示姓名本体。
- 源 `guessName` 试图把未知变量与下一条文本关联。
- 这种推断可能把台词认成姓名，leaf 故意不自动改写变量。
- 应保留 `w001a` 一类原始标识，并把显示名映射作为旁路信息。
- 源预设 `dontImportName=1` 也说明姓名变量不宜直接替换。
- `@`、`[` 开头的段可能包含控制信息，不能全段无差别翻译。
- 编码由调用方明确指定，例如严格 `cp932` 解码。
- 源预设中的 `ignoreDecodeError=1` 没有移植；坏字节必须保留证据并报错。

## 安全回填
- [replace_token](../python/engines/anim.py#L91) 只允许同字节数替换。
- 它同时校验旧跨度与 raw 一致，拒绝错文件或陈旧 token。
- 新内容不得含 NUL，避免改变段边界。
- 不截断超长译文，也不使用 `errors='ignore'` 丢字符。
- 等字符数不等于等字节数；编码完成后才比较长度。
- SCE 后续区段和跳转信息没有完整解析，因此变长直接 `NotImplementedError`。
- 完成明文局部修改后，应调用 `crypt(..., decrypt=False)` 恢复密文。
- 密钥链导致一个块修改可能影响后续密文；不能只替换密文中的对应小段。
- 公共层负责备份、冲突检测和安全写盘，本模块无文件访问。

## 调用示意
```python
from python.engines import anim
plain = anim.crypt(member_bytes, decrypt=True)
tokens = anim.nul_tokens(plain, sce=False)
# 先人工/规则确认 token 的语义，再严格编码译文。
changed = anim.replace_token(plain, tokens[0], encoded_translation)
result_bytes = anim.crypt(changed, decrypt=False)
```
- `encoded_translation` 必须已通过长度和游戏字库检查。
- 空 token 列表不是“翻译完成”，应回到格式判定阶段。

## 验证与阶段缺口
- 合成测试覆盖八种 key 更新分支和多组数据的加解密互逆。
- 固定向量校验了顺序 key 更新，避免只有互逆测试却双方都写错。
- 测试包含 DAT/SCE 起点、NUL 跨度、短头拒绝和变长拒绝。
- 没有使用商业游戏资产或调用付费 API。
- 未验证任何具体游戏可部署性、字库兼容性或非标准 ANIM 版本。
- 未实现外层容器、完整指令语义、跳转重定位、名称猜测自动写入。
- 对未匹配版本应报告“格式未支持”，而不是自动回退通用字符串扫描。

## 源码与许可
- 固定来源：SExtractor `8d8d976fd04ae54e7c677705af937273d04a376a`。
- 核实文件：`src/extract_ANIM.py`、`src/engine.ini`。
- 核实符号：`decrypt`、`encrypt`、`switch_key`、`readFileDataImp`、`parseImp`。
- [上游固定源码](https://github.com/satan53x/SExtractor/blob/8d8d976fd04ae54e7c677705af937273d04a376a/src/extract_ANIM.py)。
- 上游滚动密钥段还标注 `from game_translation`，不删除其来源链。
- SExtractor 根许可证为 GNU GPL v3；本改编按 GPL-3.0-only 保守标注。
- 分发时应随包保留 GPLv3 完整文本和改编来源，不声称为 MIT 独立实现。
- 机器可读范围、符号和验证记录见 [provenance](../provenance/sextractor-core.json)。
