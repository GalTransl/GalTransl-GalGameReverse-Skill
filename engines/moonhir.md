# MoonHir：FPK → FBX → 第一文本区块

## 识别与分层
- 对应 SExtractor `Engine_MoonHir`，通常先处理 FPK 包中的 FBX。
- GARbro-Mod `Moonhir/ArcFPK.cs` 检查 `FPK` 签名及偏移四的 `0100`。
- 该容器索引含成员加密标记、offset、size 与文件名。
- `scr` 开头包名只是其成员类型提示，不能代替实际剧本结构检查。
- FBX 外层是压缩包装，解压 payload 才含脚本区块目录。
- 本 leaf 不实现 FPK 加密/索引，也不把 `.fbx` 当通用三维模型格式。
- 上游工具生成的 FBX 固定头为 `FBX 01 gkx 10`。
- 本实现严格要求该已核实头族，不自动兼容未知 FBX 变体。

## 容器与中间文件
- 原 README 强调：GARbro 解包后的 FBX 默认已经解压。
- 而某些游戏免封包加载时需要重新带 FBX 压缩包装。
- 因此“文件名仍是 .fbx”不代表里面仍有 FBX 外层 magic。
- 应明确标记 packed member 与 unpacked payload 两种输入阶段。
- 源脚本通过 `.uncomp` 后缀区分中间文件；leaf 只通过 API 区分。
- 公共层负责文件路径和阶段 manifest，不依赖 cwd 的临时名字。
- [unpack_fbx](../python/engines/moonhir.py#L71) 接受有包装的成员。
- 头第七字节是正文起点，偏移八/十二分别为 packed/unpacked size。
- 输入长度与 packed_size 必须一致，正文起点不能覆盖头。

## 纯 Python 有界 FBX 解码
- [decode_payload](../python/engines/moonhir.py#L12) 实现此 FBX 的两位控制方言。
- 一个控制字节从低到高含四个二位 tag。
- tag 0：直接复制一个字节。
- tag 1：读取一个字节 n，随后复制 `n+2` 个字面量字节。
- tag 2：读取一个**大端** 16 位值 v。
- 其距离为 `(v >> 5)+1`，复制长度为 `(v & 31)+4`。
- 反向复制允许重叠，例如距离一连续扩展重复字符。
- tag 3：先读取 extended control，再按高二位分支。
- ex mode 0：组合低六位及下一个字节，字面量长度加 `0x102`。
- ex mode 1：组合 count 高位及后续 word 低五位，回指长度加 `0x24`。
- ex mode 3：跳过指定计数字节并重启控制组。
- ex mode 2 未在源脚本实现，leaf 明确报 reserved-token 错误。
- 这不是通用 4 KiB 窗口 LZSS，不能替换成别族解码器。
- 解码前设最大输出预算，默认 64 MiB。
- 每个字面量和回指都必须完整存在，不能越过预期输出。
- 回指距离不得超过已输出字节数，拒绝 Python 负索引意外绕回。
- 达到预期输出后只接受已知结束 token 尾型，不吞掉任意垃圾。

## 可用的字面量 writer
- [pack_fbx_literal](../python/engines/moonhir.py#L81) 生成合法的未优化 FBX。
- 它不搜索重复串，因此是“伪压缩”包装，文件可能比真压缩大。
- 大部分数据用 tag 1 字面量块，单字节尾用 tag 0。
- 这修正了源简单 writer 对 count=1 计算负长度的边界问题。
- 控制组不足四项时加 C0 断组，并附 FF C0 尾标记。
- 包装中的 packed/unpacked size 根据实际字节重新计算。
- 空 payload、单字节、256 字节边界和跨控制组均受支持。
- writer 只保证本方言合法，不保证任何游戏额外大小限制都允许增大。

## 剧本文本第一块
- [text_block](../python/engines/moonhir.py#L107) 读取解压脚本的第一块。
- `LE32[8]` 是文本 start，`LE32[12]` 是该块 size。
- start 不得在 16 字节最小头内，end 不得超出 payload。
- start 前与 end 后都必须保留，后面的块不一定是无用填充。
- 源预设在此块按 NUL 拆分，并跳过字母/数字/`[`/`%` 开头项。
- 它没有可靠的独立姓名字段，name 需要额外经过核实的规则。
- 变量、控制标识和 NUL 顺序不能当作可见台词修改。
- byte offset 相对解压 payload，不是压缩 FBX 或 FPK。

## 回填限制与部署
- [replace_text_block](../python/engines/moonhir.py#L116) 要求每个 NUL 项等字节长。
- 仅整块等长仍可能移动内部字符串，所以此处还检查每项长度。
- 条目个数改变、内部字符串长度分布改变或整体变长会拒绝。
- 本参考没有解析后续块的 offset，也没有实现块内引用重定位。
- 合法局部修改后可调用 pack_fbx_literal 重建外包装。
- 然后按实际游戏的 loose-file 加载方案或匹配 FPK writer 部署。
- 不应把已解压 payload 直接改名 `.fbx` 交付给需要包装的游戏。

## 调用示意
```python
from python.engines import moonhir
payload = moonhir.unpack_fbx(packed_fbx)
start, end, original = moonhir.text_block(payload)
changed = moonhir.replace_text_block(payload, edited_block_bytes)
result_bytes = moonhir.pack_fbx_literal(changed)
```
- 如果输入本来是 GARbro 已解压内容，直接从 text_block 开始。

## 验证与来源
- 合成测试覆盖所有已实现 token、重叠回指、边界尾和坏流拒绝。
- roundtrip 覆盖 0/1/2/255/256/257/768/1024/1025 字节。
- 未验证商业游戏、未知 FBX header、FPK 加密或变长区块重定位。
- SExtractor commit `8d8d976fd04ae54e7c677705af937273d04a376a`。
- 主要来源 `tools/MoonHir/moonhir_fbx.py` 的 `pack_fbx/unpack_fbx`。
- 文本块来源 `src/extract_MoonHir.py`；流程来自工具 README。
- [固定工具源码](https://github.com/satan53x/SExtractor/blob/8d8d976fd04ae54e7c677705af937273d04a376a/tools/MoonHir/moonhir_fbx.py)。
- GARbro-Mod 容器线索固定于 `bc26d991ef5cdc0e1ecb32122ee9a48c3375750c` 的 `ArcFormats/Moonhir/ArcFPK.cs`。
- 改编按 SExtractor GPLv3 标 GPL-3.0-only；GARbro 文件含 MIT 许可头，仅用于线索核对。
- 详细阶段与验证记录见 [provenance](../provenance/sextractor-core.json)。
