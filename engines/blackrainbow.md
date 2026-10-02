# BlackRainbow：分段脚本与文本 XOR

## 识别边界
- 本页对应 SExtractor `Engine_BlackRainbow`，不要套用同名目录的所有资源。
- 提取预设没有统一后缀，必须先识别外层资源包与脚本成员。
- `script.dat` 和 `data.pak` 在附带工具中是两种不同容器方案。
- 脚本成员本身按固定 `0x4C` 头加若干分段处理。
- 读取器没有校验通用脚本 magic，本页也不提供虚构签名。
- 最低确认条件是头后各段能完整遍历，内部长度一致。
- leaf 还要求头 `[0x48,0x4C)` 等于头后分段总字节数。
- 不符合这些约束的成员应先调查版本，而不是删除检查。

## 外层容器线索
- `tools/BlackRainbow/dat_pack.py` 构造 `script.dat`。
- 其头为 `05 00 00 00 0A 55 DC A2`，后接成员数及数据区起点。
- 每个子文件数据前有 `0x20` 字节文件名和四字节长度。
- 索引偏移相对于该容器的数据区，不是脚本文本区。
- `pak_pack.py` 的 `data.pak` 则把索引和八字节计数尾放在末尾。
- PAK 索引记录成员偏移、压缩长度、未压缩长度及 UTF-16LE 文件名。
- 它按开关使用 zlib；未压缩方案的大小标志为 `FFFFFFFF`。
- 两套工具不能互换，源脚本全局参数也不应当作万能配置。
- 本 leaf 未提供上述容器 reader/writer，只负责已提取脚本成员。

## 分段布局
- [parse_script](../python/engines/blackrainbow.py#L24) 返回头与不可变 Segment 元组。
- 每段开头是 `LE32 kind`、`LE32 body_length`。
- body_length 不含这八字节段头。
- 每次读取必须精确落在下一个段边界，不能靠搜索魔数字节跳过。
- 类型 `08` 为对话/旁白。
- `08` 的 body 先有 `0x0C` 字节前缀。
- 然后是 `role_length` 和 `text_length` 两个小端整数。
- 接着依次为原始 role 字节和加密文本字节。
- role 在源实现中原样保存，不能误当作必须翻译的人名字段。
- 类型 `0E` 是选项，前缀为八字节，然后一个 text_length。
- 类型 `1D/1E` 在读取器注释中是存档标题，前缀长度为零。
- 这三种类型的文本不做对话 XOR。
- 未知 kind 的整个 body 作为 opaque prefix 保留，text 为 None。
- 不允许向未知段注入译文。

## 文本密钥
- [xor_text](../python/engines/blackrainbow.py#L9) 使用循环四字节默认密钥。
- 源默认 key 是 `2B C5 2A 3D`；调用方可传入其他非空 bytes。
- XOR 只应用于 `08` 的文本，不能连带 role 或前缀一起处理。
- key 周期从每段文本起点重新计数。
- 加密与解密使用相同变换。
- 空 key 显式报错，避免除零或返回未加密数据。
- 此算法不是整个 DAT/PAK 的加密算法。

## name/message 和控制
- 源预设从文本内部匹配 `【名字】\r\n正文`。
- 因此“Segment.role_bytes”与提取给翻译器的 name 不一定相同。
- name/message 细分应在严格解码后做，并保留括号及 CRLF。
- 原文允许真实 CRLF；段落合并不能把它误当文件级记录分隔。
- `0E` 应作为 choice，`1D/1E` 宜作为 save_title，不能统称对话。
- leaf 返回 bytes，不对未知控制码做删除、转义或 JIS 替换。
- 显式指定原编码和目标编码；编码失败需要解决字库或字符映射。

## 回填算法
- [replace_texts](../python/engines/blackrainbow.py#L64) 的键是**段序号**。
- 它保留全部未知段、已知段前缀和 role_bytes。
- `08` 重建 role_length、text_length，再对新文本 XOR。
- `0E/1D/1E` 重建其单一 text_length，文本保持未加密。
- 每段 body_length 重新计算，最终更新头末四字节总长度。
- 此能力是已核实的局部分段格式变长，不包含外层包偏移更新。
- 调用方仍须验证当前游戏不存在该版本以外的额外地址约束。
- 不把字节数写成 Unicode 字符数，也不截断过长译文。
- 公共层按原相对目录将结果交给容器工具，不由 leaf 访问文件。

## 调用示意
```python
from python.engines import blackrainbow
header, segments = blackrainbow.parse_script(member_bytes)
# 先核实第 0 段为 text 非 None 的预期语义。
result_bytes = blackrainbow.replace_texts(member_bytes, {0: encoded_translation})
_, reparsed = blackrainbow.parse_script(result_bytes)
assert reparsed[0].text == encoded_translation
```
- 修改后再次解析只能验证结构，不能替代游戏内显示/分支测试。
- 文本中原有控制序列的完整性仍由上层字段策略保证。

## 验证与缺口
- 合成测试覆盖对话、选项、未知段混排和无修改字节一致性。
- 变长测试确认 role 不变、总长度正确、未知 body 未丢失。
- 测试拒绝短文件、外层长度错配和给未知段写文本。
- 尚未验证真实游戏资源、存档标题 UI 宽度或特殊 key 版本。
- 未实现容器解包/封包、可执行文件修改、字库和补丁加载规则。
- 无任何 API 会在未实现容器 writer 时报告成功封包。

## 源码与许可
- 基线为 SExtractor `8d8d976fd04ae54e7c677705af937273d04a376a`。
- 原符号：`readFileDataImp`、`replaceEndImp`、`XorKey`。
- 原路径：`src/extract_BlackRainbow.py`、`src/engine.ini`。
- 容器线索来自 `tools/BlackRainbow/dat_pack.py` 与 `pak_pack.py` 的 `pack`。
- [固定源码](https://github.com/satan53x/SExtractor/blob/8d8d976fd04ae54e7c677705af937273d04a376a/src/extract_BlackRainbow.py)。
- 本改编依原 GPLv3，按 GPL-3.0-only 标注，不消除上游 copyleft。
- 详细许可/验证记录见 [provenance](../provenance/sextractor-core.json)。
