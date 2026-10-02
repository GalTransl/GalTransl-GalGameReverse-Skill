# Yatagarasu：PKG v1 密钥索引归档

## 能力边界
- 状态：`partial / container-only`。
- Python：`python/archives/yatagarasu.py`。
- 实现来源 PKG v1 的完整小型容器编解码。
- 不包含后续 PKG 版本或内部文本 VM。
- 不提供对白提取、控制码翻译或任意字节替换 writer。

## 识别与外层签名
- 起始 u32 是整个 PKG 字节长度 XOR key。
- 第二个 u32 是用同一四字节 key 加密后的成员数。
- 没有固定字符串魔数，因此必须结合索引验证。
- `key` 必须由调用者显式给出，不复制某作品的固定密钥。
- 读时要求外层签名与实际文件长度、显式 key 相符。

## 索引布局
- 每项 136 字节，也就是 88h。
- 前 128 字节为 UTF-8 NUL 名字字段。
- 后八字节为 u32 成员长度、u32 绝对文件偏移。
- 整张索引按四字节周期 XOR。
- 第一、第二项名字区的 7Ch..7Fh 存放明文 key 字节。
- 本实现把名字限制为 123 字节，避免侵入保留密钥位置。
- 这个限制比来源按字符/字节截断更保守且可逆。

## 数据成员变换
- 每个成员独立从 key 的第零字节开始 XOR。
- 不能把所有成员连接后只做一次连续 XOR。
- 第一个成员长度不是四的倍数时，两种处理会产生不同结果。
- `pack_pkg` 正确重启每个成员的密钥相位。
- member count、大小、偏移和总文件签名一起重建。

## 容器到剧本
- `unpack_pkg` 返回有序 `(name, bytes)`。
- 只读成员名，不写入磁盘或信任路径。
- PKG 可装任意资源，名字不能证明它是对白脚本。
- 下一阶段需确认真实剧本格式、文字编码与地址机制。
- 当前没有 name/message/choice 级 API。
- 不在解密 bytes 内扫描任意 CP932/UTF-8 字符串当对白。

## 回填与边界
- 替换输入应该是独立脚本 writer 生成的正确成员 bytes。
- 所有成员按原始顺序重建，不擅自重新排序。
- 拒绝重复/穿越名字、过长编码名和不一致嵌入 key。
- 索引必须与数据连续衔接，累计成员终点必须等于 EOF。
- 解包默认累计输出预算 64 MiB。
- 数据内的控制码和内部地址不会由 PKG 容器 writer 自动修复。

## Python 示例
```python
from python.archives.yatagarasu import pack_pkg, unpack_pkg
key = 0x12345678  # 合成夹具 key
arc = pack_pkg([("a", b"ABC"), ("b", b"D")], key=key)
items = unpack_pkg(arc, key=key)
assert items[1] == ("b", b"D")
```
- 实际工程必须保存原成员顺序与独立验证过的 key。

## 部署条件与缺失阶段
- 缺少真实剧本格式、名字/消息语义、变长与控制流修复。
- 缺少 PKG 后续版本、长名字兼容策略和非连续数据布局。
- 若原索引还有未确认扩展字段，不能直接套本子集。
- 字形、编码、换行和资源优先级尚未游戏内验证。
- 容器解密校验通过只代表结构与 key 一致，不代表翻译可运行。

## 来源、许可与测试
- SExtractor 提交 `8d8d976fd04ae54e7c677705af937273d04a376a`。
- 核心源码：`tools/Yatagarasu/pkg_pack_v1.py`。
- 说明：`tools/Yatagarasu/README.md`，上游署名 Steins;Gate。
- 来源仓库 GPL-3.0；保留贡献者归属和来源提交。
- 改编移除了随机/目录入口和硬编码密钥。
- 合成测试覆盖总长签名、嵌入 key、成员独立相位、往返。
- 另测 key 不匹配和侵入密钥保留区的长名字拒绝。
- 测试：`tests/test_engines_tools_b.py`，没有真实资源或网络。
