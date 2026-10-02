# SakanaGL：SX 密码与已解码索引

## 能力边界
- 状态：`partial / cipher-and-decoded-index`。
- Python：`python/archives/sakanagl.py`。
- 实现字密码、成员密钥公式以及解密解压后索引解析。
- 不实现 Zstandard 压缩/解压或完整 SX/SXStorage writer。
- 不引入 `zstandard`、GARbro DLL 或原仓库运行依赖。

## 外层识别
- 来源 SX 外层以 `SSXXDEFL` 开头。
- 后接大端 key、保留字段和加密压缩的索引数据。
- 解密结果含大端解压长度，随后是 Zstandard 流。
- 本模块不接受这个外层流直接作为 decoded index。
- 调用者必须先使用独立验证的流程得到索引明文。

## 字密码算法
- `crypt_data` 接收明确的 `key_lo`、`key_hi` 两个 u32。
- 初始状态与固定异或常量、位移结果混合。
- 每四字节按小端 u32 生成新的异或密钥。
- 所有会溢出的状态运算按 u32 掩码处理。
- 尾部不足四字节的 1..3 字节保持不动，不能擅自补加密。
- 算法是对称的，重复同一参数可以还原。
- `member_keys` 以十六字节对齐偏移和存储长度导出成员密钥。

## 已解码索引布局
- 支持的内部头为大端版本 1 与零保留字段。
- 名字表：i32 数量，随后每个名字 u8 UTF-8 字节长度。
- 成员表：i32 数量，每项为 u16 archive、u16 flags、u32 offset/16、u32 size。
- `flags & 3` 表示压缩；`flags & 0x10 == 0` 表示加密。
- 归档元数据每项四十字节，未知记录每项二十四字节。
- 最后是树节点，携带子项数、名字索引、文件索引。
- 目录的文件索引为 -1；使用迭代栈而非无界递归解析树。

## 容器到剧本的缺口
- 元数据和树仅证明归档结构，不知道成员是否是剧本。
- `parse_decoded_index` 返回名字、成员、原始元数据与树边。
- 不依据字符串中有日文就认定 name/message。
- 没有剧本级提取/回填 API。
- 不构造文件路径或写磁盘，也不相信任意归档内名称。

## 有界与回填原则
- 计数和树节点上限可设置，默认十万。
- 检查所有名字/成员/归档引用及索引读取范围。
- 重复文件树引用和文件带子节点等未知情况拒绝。
- 若要实现 writer，必须同时重算 offset/16、大小和归档元数据。
- 加密密钥依赖新偏移和新存储长度，不能沿用旧密钥。
- 重新压缩 SX 索引后的外层密钥也有长度依赖，当前未实现。

## Python 示例
```python
from python.archives.sakanagl import crypt_data, member_keys, parse_decoded_index
lo, hi = member_keys(offset=32, stored_size=19)
cipher = crypt_data(b"synthetic payload!!", key_lo=lo, key_hi=hi)
plain = crypt_data(cipher, key_lo=lo, key_hi=hi)
index = parse_decoded_index(already_decoded_index_bytes)
```
- 原始 `.sx` 文件不能直接传给最后一个函数。

## 部署条件与缺失步骤
- 缺少 Zstandard、外层 key 生成/封装、分卷匹配和完整重封。
- 缺少脚本 VM、name/message/choice、字体和编码支持验证。
- 没有 MD5 字段更新与游戏内完整性校验的实现保证。
- 即使密码往返通过，也不能直接宣称整个归档可部署。

## 来源、许可与测试
- SExtractor 提交 `8d8d976fd04ae54e7c677705af937273d04a376a`。
- 主源码：`tools/SakanaGL/sxstorage_pack.py`。
- 上游说明它的密码是 GARbro C# 算法的 Python 移植。
- README 署名 Steins;Gate；按来源仓库 GPL-3.0 保留贡献归属。
- 当前未运行原脚本，也未读取原 `.sx` 或游戏资源。
- 已测字密码对称性、明文尾字节、成员密钥和索引树边界。
- 测试：`tests/test_engines_tools_b.py`，合成数据而非真实压缩流。
