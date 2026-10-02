# Kaguya：message.dat 与 LINK6

## 识别与选择

先检查独立的 `message.dat`，不要因存在 `scr.arc` 就认定对白在归档中。同名备份、汉化文件与原始文本表分开识别，不按遍历顺序混用。

| 格式 | 识别依据 | 随包能力 |
|---|---|---|
| ver4 文本表 | `[SCR-MESSAGE]ver4.0`，21 字节头，后接索引表 | 解析、导出、回填与重建 |
| 早期分块文本（旧称 02/03） | `[SCR-MESSAGE]` 后的版本字段、头长和连续长度块共同确认 | 下文提供布局与适配规则；现有 CLI 尚不支持 |
| LINK6 归档 | `LINK6` 头与有效成员索引 | 未压缩、未加密成员读写；其他成员可按存储字节保留 |

共同签名不能证明不同版本可共用 writer。

## ver4 提取与回填

在仓库根目录执行，输入为含 `message.dat` 的目录，输出必须是新目录：

```text
python -m python.engines.kaguya_extract extract /path/to/game --output /path/to/game/game_extract --verify-edits
python -m python.engines.kaguya_extract pack /path/to/game/game_extract --output /path/to/game/game_extract/rebuilt
```

| 产物 | 用途 |
|---|---|
| `gt_input/message.json` | UTF-8 原文，姓名在正文前；按组导出对白，之后是选项 |
| `gt_output/message.json` | 同名译文，保持记录数量、顺序和字段 |
| `original/` | 原始文本表及存在的伴随文件；`scripts/` 为 LINK6 解出的成员 |
| `metadata/message.json` | 原文哈希、定位信息与控制数据契约 |
| `roundtrip/` | 由 parser/writer 重建的原文文件 |
| `reports/extraction.json` | 提取数量、未引用槽、尾部及往返结果 |
| `rebuilt/message.dat`、`verification.json` | 回填结果与验证报告 |

CLI 只选择输入目录根部的 `message.dat`。没有 SCR 调用点到对白的映射时，保留 `message.json`，不猜章节名拆分。`--verify-edits` 在内存中进行变长回填、重解析，不把测试句混入原文产物。

回填校验原始文件哈希及重新解析所得 manifest；未提供译文时报告 `translation_provided=false`，不当作翻译完成。独立文本表仍输出为独立文件，不重新塞进 `scr.arc`。

交付时建议先试注 `message.json` 的少量正文，说明开场触发位置是否已确认。告诉用户：“译文按同名文件放回 `gt_output` 后告诉我，我来回写。”

## ver4 表结构与回填约束

整数均为小端。头长 `0x15`；`header[0x13]` 非零时，取 `header[0x14]` 为 XOR 密钥，否则不异或。只对字符串或消息块异或，表计数、长度和组索引不参与。

| 顺序 | 布局 |
|---|---|
| 姓名表 | `i32 数量`，每项 `i16 字节长度 + CP932 字符串` |
| 选项表 | 同姓名表；字符串长度不超过 32767 |
| 消息表 | `i32 数量`，每项 `i32 块长度 + 消息块` |
| 解密后的消息块 | `i32 正文字节长度 + CP932 正文 + u8 语音数量 + UTF-16LE NUL 结尾的语音名列表` |
| 分组表 | `i32 数量`，每组 `i32 姓名索引 + u8 消息数量 + i32 消息索引列表`；姓名索引 `-1` 表示无姓名 |

消息块必须精确消费，计数与索引必须有效。分组表后的尾部不解释为额外文本：低层 API 默认拒绝，显式 `allow_trailer=True` 才保留；CLI 保留并校验尾部，不代表已知其语义。

- 按消息的出现位置导出，不去重；未引用槽留在原表。
- 修改某次出现的正文时追加消息槽，仅更新对应组引用，保留原槽和语音绑定。改名也追加姓名槽，同组各行须给出一致姓名。
- 选项原位更新，组数及每组消息数不变；不修改 SCR 字节码或 `params.dat`。
- 未改字段复用原始编码字节，避免 CP932 别名导致无修改也改变文件。

## 早期 02/03 message.dat 分块格式

此格式是顺序长度块，不含 ver4 的姓名、消息和分组索引表。“02/03”不是已确认的完整版本签名，以下取头规则用于样本分析，不能单独作为自动识别依据。

### 文件头与块边界

| 偏移 | 长度 | 含义 |
|---|---|---|
| `0x00` | 13 | ASCII `[SCR-MESSAGE]` |
| `0x0D` | 4 | 版本字段；末字节位于 `0x10` |
| `0x11` | 1 或 2 | 原样保留的附加头字段 |
| `0x12` 或 `0x13` | 至 EOF 或零长度标记 | 连续数据块 |

已有格式资料采用的取头条件是：版本末字节小于 `0x03` 时附加 1 字节；`0x03 <= 值 < 0x34` 时附加 2 字节；大于等于 `0x34` 不走此分支。**数值 `0x03` 与 ASCII `'3'`（`0x33`）不同**，这组条件不是版本白名单。适配时须确认完整版本字段、首块起点及所有后续边界，不自行改成对 `ver2.0` / `ver3.0` 字符串的判断。

每块为 `u32 小端 payload 字节数 + payload`，长度不包含自身的 4 字节。payload 每字节 XOR `0xFF` 后解析；头、长度不异或，不能照搬 ver4 的头部密钥开关。

- 长度为零时停止：零长度标记及其后的全部字节原样保留，不再提取文本。
- 恰好在完整块后到 EOF 也可结束；不足 4 字节的长度字段或越界 payload 属于截断，不能当作尾部吞掉。
- 在分配、异或前限制文件大小、块数量和单块大小。

### 解密后的文本块

首个 NUL 前是姓名或选项字符串，其后紧接一个 `u8 count`：

| 条件 | 字段解释 | 导出方式 |
|---|---|---|
| `count > 0` | `姓名 + NUL + count + 后续 NUL 结尾的正文串` | 非空姓名作为 `name`，后续非空正文按原顺序导出为 `message` |
| `count == 0` | 首串为选项 | 非空首串导出为无姓名的 `message` |

正文起点为首个 NUL 后 2 字节；空姓名表示无姓名，空串仍占原结构位置。选项的 count 本身也是零字节，不要重复当作正文分隔符。

已有资料把 count 描述为内容数量，但读取逻辑仅用它区分姓名/选项，再扫描后续 NUL。它不足以证明所有变体都恰好有 count 条正文，也没有解释选项后的其他字段。适配时核对声明数量、实际字符串数与块尾消费情况；不一致或有余字节时先分析，不能任意跳过或伪造文本槽。缺少首个 NUL、count 字节或正文终止符均需报错。

### 回写规则

1. 确认编码后严格解码；CP932 是候选，不从共同签名推断，也不套用 ver4 的 `F040` 映射。
2. sidecar 保存块序号、字符串位置、姓名共享关系和原字节；JSON 姓名在正文前，同块多条正文的改名须一致。
3. 只替换已确认的字符串范围，禁止新增 NUL；保留分隔符、count、空串、头和尾部。变长后重算 payload 的**编码字节长度**，再 XOR `0xFF` 并写入长度前缀。
4. 验证真实 parser/writer 原文逐字节往返，再做变长中文回填、重解析及非文本字节对照。验证完成前不要将该分支标记为完整支持。

## 编码与中文显示

ver4 正文、姓名和选项使用严格 CP932，语音名使用 UTF-16LE。`F040` 与全角百分号相互映射，按 SJIS 字符边界处理。单独的“％”姓名是不可改上下文；改写字段保持特殊百分号数量、LF 数量及结尾换行状态。姓名也可能含 LF。

中文超出 CP932 时优先使用[公共 JIS 替换流程](../guides/jis-substitution.md)，将代理 JSON 交给现有 writer，不逐引擎实现编码器。重读输出后验证代理文本及还原中文，再交付对应映射和字体或 hook 配置。字节回填成功不等于已验证游戏显示。

## LINK6 容器

记录从 `8 + header[7]` 开始，每条为 `u32 整条记录长度 + u16 flags + 7字节附属信息 + u16 文件名字节数 + UTF-16LE 文件名 + payload`；末尾为零 u32。

索引可列出带 flags 的成员，读取明文仅支持 `flags=0`。重封包重算记录长度，保留头部、原文件名和附属信息。未替换的压缩/加密成员可复制存储字节，不能直接用明文替换。当前不支持 BMR、LZ、图片解密或 LINK3/4/5；提取 SCR 不代表已实现其字节码解析。

## 实现与检查

- [kaguya.py](../python/engines/kaguya.py)：ver4 底层读写。
- [kaguya_extract.py](../python/engines/kaguya_extract.py)：ver4 JSON 契约与工作目录流程。
- [kaguya_link.py](../python/archives/kaguya_link.py)：LINK6 容器。
- [test_kaguya.py](../tests/test_kaguya.py)、[test_engines_secondary.py](../tests/test_engines_secondary.py)：ver4 与容器回归；不覆盖早期分块格式。

```text
python -m unittest discover -s tests -p test_kaguya.py
python -m unittest discover -s tests -p test_engines_secondary.py
python tools/check_skill.py
```

许可：ver4 与 LINK6 的来源通知见 [MIT-VNTextPatch](../provenance/licenses/MIT-VNTextPatch.txt)、[MIT-GARbro](../provenance/licenses/MIT-GARbro.txt)；早期分块布局依据 SExtractor `extract_Kaguya_dat.py`，沿用 [GPL-3.0](../provenance/licenses/GPL-3.0.txt)。
