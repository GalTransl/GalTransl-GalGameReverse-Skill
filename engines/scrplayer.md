# ScrPlayer：XOR 字符串表与命令指针

## 识别与版本
- 对应 SExtractor `Engine_ScrPlayer`，成员后缀 `.scr`。
- 剧本文件保留 16 字节头，源码并未定义通用脚本 magic。
- 外层 `pack` / `pac2` magic 属于资源包，不是 SCR 命令头。
- GARbro-Mod `ScrPlayer/ArcPAK.cs` 用这两个签名区分容器版本。
- pac2 索引还需要专用 XOR key，不能用字符串表的 `7F` 密钥替代。
- 容器可能有四/八字节对齐的索引记录，leaf 不处理该层。
- 提取器有 opcode profile 1 至 6，同一个 opcode 参数语义可不同。
- 源 version 0 合并多个 profile，后项会覆盖前项，不是安全自动识别。
- 本参考拒绝 version 0，必须明确提供已核实 profile。

## 容器 → 剧本
- 用匹配容器版本工具提取完整 `.scr` 成员，保留原相对名字。
- 不把解密后的目录索引当脚本文本，也不直接覆盖唯一原包。
- 本模块没有 PAK reader/writer，不承诺 loose-file 部署规则。
- 公共层记录容器、版本、编码、成员哈希及输出去向。
- 验证脚本头和两段长度后，才能认为进入正确的成员格式。

## SCR 两段布局
- [parse_script](../python/engines/scrplayer.py#L41) 从偏移 `0x10` 读 command_size。
- 命令段紧跟在这个四字节长度后，即 `0x14`。
- 命令段之后再读一个 string_size，然后是加密字符串段。
- 两个段长度必须恰好覆盖文件，不接受截尾或额外未知尾。
- 字符串段逐字节 XOR `7F`，解密后按 NUL 切分。
- 最后一个终止 NUL 必须存在，末尾空项也保留。
- 每项地址是相对于**字符串段起点**的 byte offset。
- 地址表按原编码字节数加一个终止 NUL 累加。
- 指针必须指向字符串边界，不能指向某个多字节字符的中间。

## 指令与 profile
- 每条命令首字节为 opcode，第二字节为总命令长度。
- 长度至少四字节且须是四的倍数，不能为零或越界。
- 参数按命令内偏移 `4,8,12,...` 读取 LE32。
- profile 表中 1 表示“可翻译且需要重定位”。
- -1 表示“不可翻译但仍必须重定位”，典型为声频/资源名字。
- 0 表示普通数值，不可拿去当字符串地址。
- 参数 `FFFFFFFF` 是 IgnoreParam，应保留且不查字符串表。
- `5E` 多个 profile 为 `(1,-1,1)`，首字段 name、末字段 message。
- profile 3 的 `5E` 是 `(0,0,-1,1)`，首两个参数不是姓名。
- profile 6 的 `5E` 还有第四个数值参数，不能用三参版本解析。
- profile 1 的 `AA` 是五个可译字符串；profile 2 的 `6A` 混合多种参数。
- choice opcode 在部分 profile 为 `65`，另一些为 `64`。
- 已知 opcode 的实参个数必须与所选 profile 精确匹配。
- 未知命令记录其位置并保留原 bytes，不假称已经理解参数。

## name/message 与显示转换
- Reference 指明原命令位置、操作数字段位置、字符串序号和是否可译。
- `5E` 且首参数为可译字符串时才标记 name。
- 其他可译字段标记 message，选择语义可由调用方结合 opcode 进一步区分。
- 源 `fixOrig` 把半角假名/标点转换为全角显示形式。
- 那是导出显示转换，不是证明原始 bytes 可以无损反推。
- 本 leaf 不自动执行 fixOrig，保留字符串表的真实编码字节。
- 同一 string index 可被多条命令引用，不能随意复制成互相矛盾的译文。
- 控制码、尾换行和资源 ID 需要按字段语义保留。

## 重定位 writer
- [replace_strings](../python/engines/scrplayer.py#L89) 仅允许可译引用指向的字符串。
- 新文本 bytes 不得含 NUL，不能改变字符串表项数量。
- 先重建所有字符串的 offset，再更新每个已知 1/-1 引用。
- 因而前面的 name 变长时，后面的不可译 voice 指针也会正确移动。
- 只修正可译项的指针会产生隐蔽故障，本实现不会这样做。
- 数值参数和 IgnoreParam 不动，命令段原长度保持。
- string_size 根据重组后的真实大小更新，字符串段再 XOR 7F。
- 只要有未知命令，任何变长请求都会 `NotImplementedError`。
- 若存在未被任何已知引用使用的非空字符串，也拒绝变长。
- 这些是完整引用覆盖无法证明时的保守停止条件。
- 等字节长修改仍可在含未知命令的文件中进行，因为不移动表内地址。
- 输出只是 SCR 成员，不包含外层资源包地址更新。

## 调用示意
```python
from python.engines import scrplayer
script = scrplayer.parse_script(member_bytes, version=1)
result_bytes = scrplayer.replace_strings(member_bytes, {verified_string_index: encoded_translation}, version=1)
```
- version 应来自原脚本验证，不建议依次尝试直到其中一个不报错。
- 公共层负责写盘和封包，不由 leaf 依据 cwd 选择目录。

## 验证与缺口
- 合成测试确认 name 变长后 voice 和 message 两个指针都移动。
- no-op 回填字节完全一致，重复解析后各字符串保持预期。
- 测试覆盖 profile 3 数值参数、IgnoreParam、短文件和 version 0 拒绝。
- 未知命令时变长失败、等长成功的分支也经过测试。
- 尚未测试商业游戏、全 profile 的真实脚本或资源包部署。
- 未实现 PAK/pac2 封包、未知 opcode 推断、字库修改和 UI 宽度检查。
- 任何缺失覆盖都应明示，不能仅输出文件存在就报告重定位成功。

## 来源与许可
- SExtractor commit `8d8d976fd04ae54e7c677705af937273d04a376a`。
- 原路径：`src/extract_ScrPlayer.py`、`src/engine.ini`。
- 原符号：`StrCodeConfig`、`Script.read/write`、`Command.read/write`、`generateAddrList`。
- [固定源码](https://github.com/satan53x/SExtractor/blob/8d8d976fd04ae54e7c677705af937273d04a376a/src/extract_ScrPlayer.py)。
- 容器线索来自 GARbro-Mod 固定 commit `bc26d991ef5cdc0e1ecb32122ee9a48c3375750c` 的 `ArcFormats/ScrPlayer/ArcPAK.cs`。
- 改编 Python 按 SExtractor GPLv3 标 GPL-3.0-only；GARbro 的 MIT 头归属保留于来源记录。
- 验证范围和阶段能力详见 [provenance](../provenance/sextractor-core.json)。
