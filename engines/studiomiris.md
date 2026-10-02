# StudioMiris：SKMSd 消息资源表

## 能力边界
- 状态：`partial / indexed-string-roundtrip`。
- Python：`python/engines/studiomiris.py`。
- 支持 `SKMSd\0` 的连续索引字符串表。
- 不包含其他 Miris 容器、剧本 VM 或字体处理。
- 不依赖原脚本的当前目录、GUI 或全局状态。

## 识别与结构
- 文件头六字节必须是 `53 4B 4D 53 64 00`。
- `0x06` 是小端 u32 字符串数量。
- 从 `0x0A` 开始，每项为 u32 相对偏移、u32 字节长度。
- 默认字符串池基址为 `0x0A + count * 8`。
- 字符串池用逐字节 XOR FF 编解码。
- 地址相对于字符串池，不是文件绝对地址。
- 默认 CP932 严格解码。

## 固定偏移的陷阱
- 上游提取器把字符串池起点写成了 `0x1732A`。
- 上游写回器却按字符串数量动态生成索引表。
- 不把这个针对样本的常数推广为通用格式定义。
- 本实现默认采用写回器展示的动态布局。
- 如有已证实的索引后填充，可显式传 `pool_offset`。
- `pool_offset` 不能早于索引表末尾或超出文件。
- 索引与池之间的 gap 原样保留，不从工作目录读取辅助文件。

## 容器到文本
- 输入为已经取得的 SKM bytes，例如独立消息资源文件。
- 本模块不负责从封包发现或解密 SKM。
- `extract_skm` 输出稳定零基索引与原字符串。
- 角色固定为 `unclassified`，不是所有资源字符串都是对白。
- 名字和消息拆分需要额外剧本引用证据。
- 不扫描不透明尾部中的“像文本”内容。

## 回填与控制字符
- `rewrite_skm` 按索引替换，不按原文字节全局匹配。
- 重编码后生成新的相对偏移和长度表。
- 所有字符串按原顺序连接，再 XOR FF。
- 保留头部结构、原索引数量、gap 和未索引尾部。
- 译文低位控制字节顺序必须与原条目一致。
- 拒绝非连续/重叠索引和无效索引号。
- 不做遇到不可编码字符便丢弃整条文本的容错。

## Python 示例
```python
from python.engines.studiomiris import extract_skm, rewrite_skm
records = extract_skm(skm_bytes)
# reviewed_index 是外部已确认的消息条目。
rebuilt = rewrite_skm(skm_bytes, {reviewed_index: "合成試験"})
# 非默认布局必须在提取和回填时传同一已核实 pool_offset。
```
- 函数返回 bytes，不创建 `out` / `out1` 等隐式目录。
- 文件名 `msg.skm` 不是解析函数的硬编码条件。

## 部署条件与缺失步骤
- 需要确定实际样本使用动态池基址还是带填充布局。
- 需要证明调用剧本没有引用索引表之外的内部地址。
- 需要外部名字/正文/选择项语义映射。
- 尚无封包层重建和字库/换行验证。
- 合成测试只能证明索引、XOR 和尾部保留算法。
- 不应声称所有 StudioMiris 版本均可直接部署。

## 来源、许可与证据
- SExtractor 提交 `8d8d976fd04ae54e7c677705af937273d04a376a`。
- `tools/StudioMiris/skm_to_txt.py`：签名、索引、XOR、样本基址。
- `tools/StudioMiris/txt_to_skm.py`：动态索引写回算法。
- `tools/StudioMiris/README.md`：上游署名 Coroz。
- 来源仓库 GPL-3.0；代码保留来源与署名。
- 已测动态/显式基址、变长索引、gap/尾部及非法地址。
- 测试文件 `tests/test_engines_tools_b.py`，仅合成资源。
