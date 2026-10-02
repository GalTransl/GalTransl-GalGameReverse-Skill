# Kaguya：message.dat ver4.0 与 LINK6 容器往返

## 先找独立文本表

精确签名为 [SCR-MESSAGE]ver4.0，头长 0x15。header[0x13] 非零时，用 header[0x14] 对文本和消息块做 XOR。**ver4 的对白可在游戏根目录独立的 message.dat 内，不需要先解压 scr.arc，也不要把它重新塞进 scr.arc。**

- [kaguya.py](../python/engines/kaguya.py)：ver4 表的 reader/writer，CP932、姓名、选项、消息、语音与分组。
- [kaguya_extract.py](../python/engines/kaguya_extract.py)：GalTransl 导出、manifest 校验、按引用回填和批量 CLI。
- [kaguya_link.py](../python/archives/kaguya_link.py)：LINK6 索引、未压缩/未加密成员提取、保留记录头的重封包。
- 不支持 SExtractor 的早期 02/03 message.dat 分块格式；其共同签名不能作为 writer 兼容证据。

Love×Holic 样本根目录 message.dat 是日文 CP932；%DEFAULT FOLDER%/message.dat 是另一份已改编码的中文文件。后者在 CP932 下大量失败，不能把它当原文或按目录遍历顺序覆盖前者。当前 CLI 只选择显式游戏目录根部的 message.dat，另记录已知备份的哈希，不混合导出。已有汉化 EXE/DLL 不意味着当前 reader 支持其编码或字体方案。

## 可直接使用的流程

在 skill 根目录运行，替换示意路径。所有输出必须是新目录；重跑换新名字，不覆盖已有结果。

~~~text
python -m python.engines.kaguya_extract extract /path/to/game --output /path/to/game/game_extract --verify-edits
~~~

| 产物 | 用途 |
|---|---|
| gt_input/message.json | 按消息组顺序导出，之后是选项；UTF-8 name/message |
| gt_output/ | 放 GalTransl 结果，仍叫 message.json，保持数组顺序 |
| original/message.dat | 原始文本表，回填依据 |
| original/scr.arc、original/params.dat | 存在时保存伴随文件并记录哈希 |
| original/scripts/ | LINK6 解出的原名 SCR；未解释或修改字节码 |
| metadata/message.json | 原文哈希、组/消息/姓名索引、控制数据契约 |
| roundtrip/message.dat | 经 parser/writer 重写的原文文本表 |
| roundtrip/scr.arc | 经 LINK6 writer 重封的原文容器 |
| reports/extraction.json | 表计数、未引用槽、尾部与往返结果 |

**把 game_extract/gt_input 导入 GalTransl 翻译。** 独立文本表没有已验证的 SCR 调用点到对白的映射，所以使用其真实源名 message.json，不按猜测的剧情文件名拆分。--verify-edits 会在内存里对全部导出记录改长后回填并重读，将结果写入报告；测试文本不混入交付用原文包。

翻译完成后：

~~~text
python -m python.engines.kaguya_extract pack /path/to/game/game_extract --output /path/to/game/game_extract/rebuilt
~~~

pack 默认读 gt_output/message.json，验证所有原始伴随文件哈希，重新从原文解析 manifest 后回填。输出 rebuilt/message.dat 和 verification.json；缺少译文时生成原文副本，明确报告 translation_provided=false，未匹配 JSON 不猜配。--translations 仅供显式测试目录使用。不会安装输出、修改游戏文件、执行 EXE/DLL 或自动启动游戏。

## 表结构、共享引用与回填

- 名字表和选项表：i32 数量，每项 i16 字节长度 + XOR 后 CP932 字符串，长度上限 32767。
- 消息表：i32 数量，每项 i32 消息块长度。解密后为 i32 正文长度、正文、u8 语音数量、UTF-16LE NUL 结尾的语音名。必须精确消费块内字节。
- 分组表：i32 数量，每组为 i32 姓名索引（-1 无姓名）、u8 消息数量和对应 i32 消息索引。所有索引必须有效。
- 同一消息可在多个组或同组多次出现，导出不去重。未被任何组引用的消息留在原表，不猜造姓名或加入翻译队列；报告列出这些槽。
- API 保持 Document(header, names, choices, messages, groups) 兼容，新增 trailer 及不参与语义相等比较的原始文本字节字段。
- 无修改字段复用已校验的原始 CP932 字节，解决 CP932 别名映射导致无修改也变字节的问题。
- 高层 inject 对改写的消息出现位置追加新消息槽并更新该组索引，保留原共享槽、未引用槽和语音。改名也追加姓名槽，同一组多条消息必须给出一致姓名。选项保持原槽位和顺序，因为脚本可直接引用它们。
- 原消息组数量、每组消息数量不变。不修改 SCR 字节码、跳转或 params.dat，也不靠字符串搜索替换修补引用。

直接修改低层 Document.messages[i] 会影响所有引用该槽的组；需要按出现位置翻译时使用高层 inject。

## 尾部数据的实测处理

旧 reader 要求恰好到 EOF。Love×Holic 的所有 ver4 表都完整且索引有效，但表结束后还有 **28,787 字节**。同目录中文副本也带有相同尾部。VNTextPatch 的上游 reader 按声明组数读取，没有继续解释该尾部；这不能证明游戏运行时如何使用它。

低层 read_message_dat(data) **仍默认拒绝尾部**；显式 allow_trailer=True 才保存到 Document.trailer。高层 CLI 使用这个明示的保留方言，记录尾部长度和 SHA-256，并要求每次回填后完全一致。它不会把余字节当额外消息组、修正声明计数、截断原文件或宣称已经解析尾部语义。无论是否保留尾部，坏计数、截断消息块和越界索引仍拒绝。

这个选择保留了样本的文件数据，已验证格式往返；尾部的运行时意义仍未验证。遇到另一种尾部或游戏变体，应重新建立证据，不默认为同一扩展。

## 编码、姓名与换行

正文、姓名、选项为严格 CP932；语音名为严格 UTF-16LE。特殊 SJIS 码点 F040 映射为全角百分号，写入反向映射，按码点边界处理。新译文必须可无损编码和反解码，不做替代字符、截断或隐式 GBK 切换。

Love×Holic 的姓名表有单独的“％”值，导出作为不可改的上下文姓名，不猜其实际角色名。正文和姓名的特殊百分号数量保持不变。低层 reader 能保留带长度的 NUL 数据，但高层翻译接口拒绝新控制字符。

**姓名也可能有 LF**：本样本第 32 槽显示名跨两行。因此不能一律禁止姓名换行；高层回填保持各字段 LF 数量及结尾换行状态。正文原有 LF 是显示布局，不自动删掉或换成其他控制语法。纯 name/message 数组仍须保序；同条数重排无法由 sidecar 自动识别。

当前实现不包含 SJIS tunnel、字体补丁或已有汉化版的编码映射。

## LINK6 的范围

LINK6 归档从 8 + header[7] 开始逐条读取：u32 整条记录长度、u16 flags、7 字节附属信息、u16 文件名字节数、UTF-16LE 文件名、payload，末尾为一个零 u32。

索引器可列出带 flags 的成员而不读取大 payload。实际读取只支持 flags=0。重封包重新计算记录长度，保留头部前缀、原 UTF-16 文件名和附属信息；没有替换的压缩/加密成员可以按存储字节复制，但禁止用明文替换这些成员。不承诺 BMR、LZ、图片解密或 LINK3/4/5 支持。

Love×Holic 的 scr.arc 中 220 个成员均为 flags=0、[SCR-Ver5.1] 脚本。这仅验证容器和脚本头，不代表已实现完整 SCR 字节码解析。图像包的压缩或加密不阻止先处理独立 message.dat。

## Love×Holic 实测（2026-10-01）

- 主表：125 个姓名、74 个选项、35,658 个消息槽、35,569 个组。
- 导出 35,647 条组内消息和 74 个选项，合计 **35,721 条**；78 个组含两条消息，其余组各一条。11 个未引用消息槽保留在原表。
- 主 message.dat 经高层导出、原文回填、底层 writer 后逐字节一致；包括头部 XOR 状态、原始码点、语音和完整尾部。
- scr.arc 解出 220 个 SCR，再经 LINK6 writer 重封，整包及全部成员逐字节一致。
- 全部 35,721 条导出记录改长、可写姓名改名后，回填并重读与预期 JSON 一致；消息的语音绑定和原始共享槽不变。
- 原 message.dat、scr.arc、params.dat 的哈希保持不变。没有运行游戏，未验证显示宽度、存档兼容、尾部运行时意义或补丁加载。

[专用测试](../tests/test_kaguya.py) 覆盖严格尾部拒绝与显式保留、CP932 别名、多行姓名、共享引用克隆、组内姓名冲突、控制码/manifest、LINK6 坏记录和不覆盖写入。既有 ver4 测试仍在 [test_engines_secondary.py](../tests/test_engines_secondary.py)。

~~~text
python -m unittest discover -s tests -p test_kaguya.py -v
python -m unittest discover -s tests -p test_engines_secondary.py
~~~

## 来源

- ver4 核心源于 VNTextPatch-net8（MIT），固定提交 d9c0fab7b72fdcf87d674ef12a84d3829c9188be，VNTextPatch.Shared/Scripts/KaguyaScript.cs 的 ReadString/ReadMessage/ReadMessageGroup/WriteString/WriteMessage；通知见 [MIT-VNTextPatch](../provenance/licenses/MIT-VNTextPatch.txt)。原文保字节、尾部保留和高层引用克隆为本项目新增。
- LINK6 布局参考 GARbro-Mod [ArcLINK.cs](https://github.com/nanami5270/GARbro-Mod/blob/bc26d991ef5cdc0e1ecb32122ee9a48c3375750c/ArcFormats/Kaguya/ArcLINK.cs) 的 LinkReader/Link6Reader；morkt MIT 通知见 [MIT-GARbro](../provenance/licenses/MIT-GARbro.txt)。
- 旧版本对照为 SExtractor 8d8d976fd04ae54e7c677705af937273d04a376a 的 src/extract_Kaguya_dat.py（GPLv3）；其 02/03 分支不是本 ver4 writer。
