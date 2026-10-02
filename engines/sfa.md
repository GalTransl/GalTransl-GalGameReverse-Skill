# SFA：FGA Huffman 成员与 AOS 文本线索

## 模块分工

| 层 | 模块与接口 |
|---|---|
| 归档 | [archives/sfa.py](../python/archives/sfa.py)：`compress_member`、`decompress_member` |
| 脚本 | [engines/sfa.py](../python/engines/sfa.py)：`extract_aos_lines` |

按下述版本与阶段限制调用；成员 codec 或索引子集不等于完整解包器。

## 能力边界
- 状态：`partial / member-codec-and-text-dialect`。
- Python：`python/engines/sfa.py`。
- 实现 FGA 内成员的真实 Huffman 编解码。
- 另有保守的、已解码 AOS 行级提取参考。
- 不包含 FGA 多索引块归档重建或完整 AOS writer。

## FGA 容器线索
- 来源归档索引块大小为 `0x318`。
- 每块最多三十二个 `0x18` 字节条目。
- 条目包含十二字节名字、偏移、大小与保留字段。
- 满块使用十二个 FF 名字标记指向下一索引块。
- 索引大小与压缩成员实际占用关系需保持原布局。
- 这些容器知识只作路线说明，当前 API 不打包完整 FGA。

## 成员 Huffman 算法
- 非空成员先写 u32 解压长度。
- bitstream 为 MSB-first。
- 树按先序写入：内部节点标志 1，再左子树、右子树。
- 叶节点标志 0，随后八位字节值。
- 正文按从根到叶的 0/1 路径编码。
- 本实现使用确定性的频率/序号排序，避免同频比较不稳定。
- 空成员沿用来源的空 bytes 约定。
- 单一符号使用来源的单 bit 零码写法。

## 解压边界
- 解压长度默认上限 64 MiB。
- 树节点最多 511，深度最多 255。
- 缺 bit、截断树和超过输出预算都会失败。
- 叶子、树和正文均从本地 bytes 解析，没有 `.pyd`。
- 不把解压成功当成文本身份已经确认。

## AOS name / message
- `extract_aos_lines` 要求输入已确认的 AOS 文本方言。
- 只认 `[name]message` 明确说话行。
- 选择项仅限 `btnset` 且带 `"slctwnd"` 的已知形态。
- 不沿用来源“剩余所有行都是正文”的宽泛兜底。
- `cvon`、注释、资源路径和普通任意字符串不会被当对白。
- 返回字符 span 便于复核，不提供任意字符串替换 writer。

## Python 示例
```python
from python.archives.sfa import compress_member, decompress_member
packed = compress_member(b"ABBAAABA")
assert decompress_member(packed) == b"ABBAAABA"
```
```python
from python.engines.sfa import extract_aos_lines
records = extract_aos_lines('[仮名]試験\ncvon("voice")\n')
assert records[0]["message"] == "試験"
```
- 压缩函数只返回成员数据，不包含 FGA 文件级索引。

## 回填与部署缺口
- 真实成员 codec 会重算解压长度、编码树和 bitstream。
- 但 AOS 控制语法、脚本 writer 和完整 FGA 重封仍需补足。
- 不知道脚本编码时不能直接把解压结果当 CP932。
- 名字/选项之外的文本方言、控制序列、换行和引用未完全实现。
- 重新生成的 Huffman 树可不同于原树，解压结果才是比较重点。
- 字库、原包成员排序和游戏资源加载规则未验证。

## 来源、许可与测试
- SExtractor 提交 `8d8d976fd04ae54e7c677705af937273d04a376a`。
- 成员算法：`tools/SFA/fga_pack.py`。
- 文本规则：`src/reg.yaml` 的 `SFA_AOS`。
- 上游署名 Steins;Gate，README 标注 Lilim SFA engine。
- 来源仓库 GPL-3.0；保留贡献者归属。
- 已测单符号固定向量、多符号往返、恶意深树和预算限制。
- 已测 AOS 正文/选择项与任意命令字符串排除。
- 测试 `tests/test_engines_tools_b.py`，全为合成输入。
