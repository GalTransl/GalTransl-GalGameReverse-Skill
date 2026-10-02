# SLGSystem：SZS100__ 容器与两种密码模式

## 能力边界
- 状态：`partial / container-roundtrip`。
- Python：`python/archives/slgsystem.py`。
- 实现 SZS 索引、成员加解密和重封。
- 不包含来源 README 链出的独立剧本工具。
- 不把解密后的成员全部当作可译文本。

## 识别与归档布局
- 魔数八字节 `SZS100__`。
- 紧随 u32 version 和 u32 member count。
- 索引从 16 开始，每项 272 字节。
- 前 256 字节为 CP932 NUL 文件名，分目录使用分号。
- 后十六字节是 u64 绝对偏移与 u64 存储长度。
- 接口把分号目录表达为 `/`，禁止歧义或路径穿越组件。
- 索引计数、名称、位置、重叠和输出预算均受检查。

## 密钥与变体
- `seed` 与 `mode` 必须显式提供，不内置游戏密钥表。
- 每个成员单独从 seed 重置 LCG。
- 递推 `x = (x * 0x343FD + 0x269EC3) & 0xFFFFFFFF`。
- 取 `(x >> 16) & 0xFF` 作为密钥字节。
- xor 模式：明文为 `(stored ^ 0x90) ^ keybyte`。
- sub 模式：明文为 `((stored ^ 0x90) - keybyte) & 255`。
- sub 的加密方向必须先加 keybyte，再 XOR 90，不能直接复用解密。

## 容器到剧本
- `unpack_szs` 返回原 version 和有序 `(name, bytes)`。
- 调用方自行确认哪些成员是剧本。
- 无密码模式和种子证据时不能靠“看起来像文字”认定解密正确。
- 此容器没有本模块可验证的强密码校验。
- 来源里另有密钥推导资料，但没有在本模块自动扫描可执行文件。

## name / message 与控制码
- 当前没有剧本级 name/message API。
- 索引文件名不是角色名字。
- 不修改成员内字符串长度、跳转、选择项或控制码。
- 译后成员必须由独立且完整的脚本 writer 生成。
- 只有那之后才能把新 bytes 交给 SZS 重封。

## 重封算法
- `pack_szs` 保持传入成员顺序与显式 version。
- 先分配完整索引，再顺序加密写成员。
- 所有偏移、大小重算为 u64。
- 不猜原 `_order.txt` 路径，也不读取当前工作目录。
- 名称和重叠不合法时整体失败。
- 外部名字编码固定遵循此来源的 CP932 方言。

## Python 示例
```python
from python.archives.slgsystem import pack_szs, unpack_szs
seed = 123  # 合成夹具种子，不是某游戏的密钥
arc = pack_szs([("script/a", b"synthetic")], version=1, seed=seed, mode="sub")
version, members = unpack_szs(arc, seed=seed, mode="sub")
assert members[0][1] == b"synthetic"
```
- 实际部署使用独立取得并验证过的 seed 和 mode。

## 部署条件与缺失步骤
- 缺少字节码反编译、名字/消息/选择项语义以及对应重编译。
- 缺少未知版本、额外头字段和多种容器变体支持。
- 加解密往返不等于使用的密钥适合原游戏。
- 字库、换行、资源优先级与存档兼容性须另行验证。
- 不调用游戏、外部工具、参考仓库或网络。

## 来源、许可与测试
- SExtractor 提交 `8d8d976fd04ae54e7c677705af937273d04a376a`。
- 核心源码：`tools/SLGSystem/szs_tool.py`。
- 路线：`tools/SLGSystem/README.md`。
- 上游署名 Steins;Gate、 多了芒果，来源仓库 GPL-3.0。
- 已测 xor/sub 固定单字节向量和两模式容器往返。
- 已测 272 字节索引位置、目录名校验和输出预算。
- 测试：`tests/test_engines_tools_b.py`；只有合成数据。
