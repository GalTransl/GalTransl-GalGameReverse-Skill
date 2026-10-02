# U-MeSoft：PK 尾索引与 SCR/TBL literal 封装

## 模块分工

| 层 | 模块与接口 |
|---|---|
| 归档 | [archives/umesoft.py](../python/archives/umesoft.py)：`decode_literal_member`、`encode_member`、`parse_pk`、`repack_pk` |
| 脚本 | [engines/umesoft.py](../python/engines/umesoft.py)：`extract_script_lines` |

按下述版本与阶段限制调用；成员 codec 或索引子集不等于完整解包器。

## 能力边界
- 状态：`partial / archive-and-member-subset`。
- Python：`python/engines/umesoft.py`。
- 真实实现 PK 尾索引重封、成员 literal 编码及受限文本行识别。
- 不实现完整 LZ 回指解压或所有 SCR 命令 writer。
- 不把 `_BIN` 通用提取替代引擎语义。

## PK 归档结构
- 最后四字节是小端 u32 索引字节数。
- 索引区位于 `EOF - 4 - index_size`。
- 每项：u8 名字长度、CP932 名字、六个未知字节、u32 大小、u32 偏移。
- 成员数据在索引之前连续排列。
- 六字节未知值必须从原包保留，不能通用地硬编码来源样本值。
- `parse_pk` 取得结构，`repack_pk` 以原包为模板更新大小/偏移。

## SCR/TBL 成员编码
- 对 `.scr` 使用空格填充，对 `.tbl` 使用零填充。
- 填充到八字节边界，而且已对齐时仍补八字节。
- 前缀 u32 记录填充后的解压长度。
- 对填充后的原始字节逐一 XOR 42h。
- 每八字节写一个控制字节 00，再写八字节 literal。
- 最后写 `FF 00 00` 终止符。
- 这会增加体积，不是优化压缩算法。

## 读取器限制
- `decode_literal_member` 仅支持本编码器产生的 literal 子集。
- 遇到真实压缩回指，不做猜测解码。
- 检查八字节尺寸、控制字节、终止符和输出上限。
- 返回数据保留填充，因为不能推断哪些尾空格原本就是剧本内容。
- 非 SCR/TBL 成员应保持原封装，不自动 XOR 或重新编码。

## name / message 线索
- 来源 `U-MeSoft` 文本预设识别 `mes("名字"...)`。
- `extract_script_lines` 仅提取该名字与带明确尾控制的引号行。
- 支持的行末标记是 `$L`、字面 `\n`、字面 `\x0`。
- 返回 message 时将尾标记分离到 `control` 字段。
- 图片、音频命令及任意不匹配行不作为正文。
- `saveset/menu/mesname` 等其他源码规则尚未在本小参考中实现。

## Python 示例
```python
from python.archives.umesoft import encode_member, repack_pk
stored = encode_member(rebuilt_scr_bytes, kind="scr")
new_pk = repack_pk(original_pk_bytes, {"a.scr": stored})
```
```python
from python.engines.umesoft import extract_script_lines
records = extract_script_lines('mes("仮名")\n"試験$L"\n')
```
- 第一个示例假定 `rebuilt_scr_bytes` 已由独立文本 writer 正确产生。

## 回填与部署条件
- 归档 writer 的替换值是已经封装的存储 bytes，不是纯文本。
- 原顺序、名字与六字节字段保持，仅偏移和长度重算。
- 没有脚本 writer，因此不会错误修改内联控制或命令引号。
- 缺少真实 LZ 解码、SCR 完整语法、选择项与名字关联。
- 缺少具体游戏对齐容忍、字库、代码页和换行验证。
- 非连续 PK、重复名字和无索引尾区不在支持子集。
- 不读取 `OLD.PK` 默认路径，也不运行来源 GUI。

## 来源、许可与测试
- SExtractor 提交 `8d8d976fd04ae54e7c677705af937273d04a376a`。
- 算法：`tools/U-MeSoft/PK_pack.py`。
- 文本证据：`src/reg.yaml` 的 `U-MeSoft`。
- 来源仓库 GPL-3.0；保留 satan53x / SExtractor 贡献者归属。
- 已测“对齐后再补八字节”、不同填充、XOR/literal/终止符。
- 已测 PK 六字节元数据保留与成员尺寸重封。
- 另测受限名字/消息行识别及任意资源命令排除。
- 测试 `tests/test_engines_tools_b.py`，没有真实游戏/API/网络。
