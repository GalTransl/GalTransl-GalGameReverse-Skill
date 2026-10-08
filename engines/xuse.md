# Xuse：GD + DLL 数据索引与脚本 XOR

## 模块分工

| 层 | 模块与接口 |
|---|---|
| 归档 | [archives/xuse.py](../python/archives/xuse.py)：`parse_gd`、`repack_gd` |
| 脚本 | [engines/xuse.py](../python/engines/xuse.py)：`crypt_script` |

按下述版本与阶段限制调用；成员 codec 或索引子集不等于完整解包器。

## 能力边界
- 状态：`partial / container-and-script-transform`。
- Python：`python/engines/xuse.py`。
- 实现 GD 配对索引解析/重建和独立脚本字节变换。
- 这里的 `.dll` 是配对数据索引，绝不加载为可执行模块。
- 不含全部 Xuse 容器、文本 VM 或对白提取。

## GD 配对结构
- GD 前四字节是成员数。
- 同名 DLL 索引至少十二字节。
- 索引的头四字节不透明保留。
- 从索引偏移 4 开始，每项为 u32 数据偏移、u32 大小。
- 数据偏移必须向前、不重叠、在 GD 内。
- 当前额外要求 GD 计数与配对索引项数一致。
- 以 MZ 形态作为计数字段的输入拒绝，避免混淆真正 EXE/DLL。

## 容器重建算法
- `parse_gd` 返回按表序的成员与原始偏移。
- `repack_gd` 接收原 GD、原索引与零基成员替换映射。
- 每项数据增长后重算索引偏移和大小。
- 保留头四字节、成员之间 gap 和最终未索引尾部。
- 原成员排序不变，不根据目录枚举重排资源 ID。
- 同时返回 GD 与 DLL bytes，部署时二者必须同步。

## 脚本 XOR 路线
- SExtractor 的补充工具用于 GD/DLL 解包后的文件。
- `crypt_script` 只对调用者明确选定的成员执行周期 XOR。
- 四字节 key 必须显式参数化，不内置某游戏密钥。
- 密钥相位从成员起点开始重复，变换对称。
- 不对整个 GD 和 DLL 外层索引盲目应用脚本 XOR。
- 图片、音频等其他成员不能因为在同包内就被当作加密剧本。

## name / message 与控制码
- 另有[CD/RIO、XOR53 与 sub_block 研究资料](xuse/cd.md)，尚未实现，也未确认与 GD/DLL 属于同一引擎版本；不能共用本页周期 XOR 或归档 writer。
- 当前没有 name/message 提取 API。
- 解密结果仍需单独识别指令、文本池及控制码。
- 可读日文或 NUL 字符串不是自动回填证据。
- 容器 writer 不改变成员内部地址或编码。
- 脚本变长只能发生在完整内部 writer 已验证之后。

## Python 示例
```python
from python.archives.xuse import parse_gd, repack_gd
from python.engines.xuse import crypt_script
members = parse_gd(gd_bytes, companion_index_bytes)
plain = crypt_script(members[0]["data"], key=verified_four_byte_key)
# 需要在此补上真实内部脚本提取/回填，不直接 replace 任意文本。
stored = crypt_script(rebuilt_script_bytes, key=verified_four_byte_key)
new_gd, new_index = repack_gd(gd_bytes, companion_index_bytes, {0: stored})
```
- 四字节 key 必须来自已验证的具体版本证据。

## 部署条件与未实现部分
- 缺少脚本语法、名字/正文/选项和所有内部 relocation。
- 缺少 XARC、WAG、BIN、NT 等不同 Xuse 归档路线。
- 缺少特定成员的加密身份自动判定。
- 对资源索引名或文件后缀不能作过度推广。
- 字库、文本代码页、加载顺序和游戏执行仍需独立验证。
- 所有 API 仅处理 bytes，没有 import 时 IO 或网络请求。

## 来源、许可与版权
- SExtractor：`8d8d976fd04ae54e7c677705af937273d04a376a`。
- XOR 证据：`tools/Xuse/gd_scr_decrypt.py`、README。
- 来源仓库 GPL-3.0，保留 satan53x / SExtractor 贡献者归属。
- GD 结构补充来自 GARbro-Mod `ArcFormats/Xuse/ArcGD.cs`。
- GARbro 提交 `bc26d991ef5cdc0e1ecb32122ee9a48c3375750c`。
- `Copyright (C) 2016 by morkt`；MIT 许可全文保留于 Python 文件注释。
- 本模块标记 GPL-3.0-only AND MIT，以保留两个来源义务。

## 实际测试
- `tests/test_engines_tools_b.py` 验证配对索引、gap、变长偏移。
- 固定 XOR 向量验证逐字节相位，截断索引明确拒绝。
- 只有合成资源，没有加载 DLL、运行游戏或访问网络。
