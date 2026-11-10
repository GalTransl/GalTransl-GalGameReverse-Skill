# EAGLS / ALIS：SCPACK、文本尾加密与标签修复

## 模块分工

| 层 | 模块与接口 |
|---|---|
| 归档 | [archives/eagls.py](../python/archives/eagls.py)：`MSVCRTRand`、`crypt_index`、`read_index`、`pack_archive` |
| 脚本 | [engines/eagls.py](../python/engines/eagls.py)：`crypt_script`、`read_labels`、`verify_label_offsets`、`apply_edits_with_labels`、`fix_label_offsets`、`dialogue_spans` |
| 对白 | [eagls_text.py](../python/engines/eagls_text.py)：`Profile`、`export_script`、`rebuild_script` |
| 工作区 CLI | [eagls_extract.py](../python/engines/eagls_extract.py)：提取、原文往返、译文重封包 |

当前支持有明确参数、成员连续存放的 SCPACK IDX/PAK，以及下述源文本方言。工作区用法见下文。

## 识别与范围
- 对应 SExtractor `Engine_EAGLS`，该提取器本身只是 BIN 文本规则代理。
- 实质格式算法在 `tools/EAGLS/EAGLS_script_tool/scpacker.py`。
- 目录线索是 `SCPACK.idx` 与 `SCPACK.pak` 配对，而非单个通用 magic。
- `EAGLS/ALIS` 是工具覆盖的两组布局，不能仅由厂商名决定参数。
- `--alis` 用于 ALIS 布局，须依据记录宽度、文本起点及索引验证选择，不能只凭工具显示的引擎标签。
- 此处不把 ADVSYS 标签扩大解释为其他引擎支持。
- leaf 实现明确参数的字节算法，不运行原 CLI，也不猜密钥。

## 免安装准备：INI 与 wave 目录

部分 EAGLS 游戏未经安装器运行时需要关闭注册检查并调整音频目录。游戏目录只读：agent 先检查并报告，**不直接修改 INI 或移动游戏文件**。

1. **检查**：找到实际游戏程序使用的 `EAGLS.INI`，排除备份、补丁备份和提取结果目录中的副本，报告生效的 `EnableRegister` 值；找不到文件或该键时如实记录，不凭空创建配置。检查 `wave/` 下是否存在 `22/` 或 `44/` 子目录，列出 `wave/22/` 中的文件及其在 `wave/` 根下的同名冲突（同名且内容相同、同名但内容不同）。
2. **报告并请求授权**：向用户说明检查结果、建议的改动（`EnableRegister=1` 改为 `0`；`wave/22/` 中文件移到 `wave/` 根）及影响范围，等待明确授权。
3. **获得授权后，在交付目录生成产物**，仍不写游戏目录：
   - 修改后的 `EAGLS.INI` 副本：只把生效的 `EnableRegister=1` 改为 `0`，保留原编码、换行、节名、注释及其他配置，重新读取确认；已为 `0` 则不生成。
   - 需移动文件清单：列出源与目标相对路径，确认解析后都在游戏目录内；同名且内容相同的标为无需移动，同名但内容不同的标为冲突、不建议覆盖；保留子目录，不建议递归删除。
   - 部署说明：用户（或用户另行明确授权覆盖游戏文件时由 agent）按清单放置 INI 并移动文件，先备份原 INI。
4. 两个子目录都不存在时无需处理音频目录。仅存在 `wave/44/` 而没有 `wave/22/` 时，不套用搬移 `22` 的步骤，也不自行建议改搬 `44`；两者都有时只处理 `22`，保留 `44`。最终报告 INI 当前值、是否生成修改副本、清单文件数量、冲突及未处理项。

## 包索引线索
- 原工具依据索引尺寸启发式选择短/长 offset 版本。
- 短版名称区 20 字节，后接 32 位 offset 和 length。
- 长版名称区 24 字节，后接 64 位 offset 和 length。
- 末尾四字节 seed 不参与索引 XOR。
- [crypt_index](../python/archives/eagls.py) 输入完整 IDX 字节与非空 key。
- 使用该尾部 LE32 seed 初始化 MSVCRT 随机数序列。
- 每个索引字节 XOR `key[rand() % len(key)]`。
- [MSVCRTRand](../python/archives/eagls.py) 的递推为 `214013*s + 2531011`。
- 状态保留低 31 位，输出为状态右移 16 位。
- 本算法加解密相同，不修改 seed 字段。
- `read_index(index, pak_size, key=..., long_offsets=...)` 返回解密索引和有序 `Entry(name, offset, size)`；先校验索引，再读取 PAK。
- 第一条存储地址作为 base，所有成员的物理 offset = 存储地址 − base。不能直接把存储地址当文件偏移，也不能像旧工具一样忽略各条地址、仅按长度顺读。
- reader 拒绝重叠、空隙、尾部未索引字节、缺终止符、危险路径、重名及预算超限。仅实现连续布局，拒绝不等于其他布局必然损坏。
- `pack_archive(index, pak, replacements, key=..., long_offsets=...)` 返回 `(new_idx, new_pak)`，replacements 的值必须是**已加密的完整成员**。保留基址、原始名称字段、索引填充和 seed，更新后续地址和长度；未替换成员按原字节保留。

## 成员文本加密
- [crypt_script](../python/engines/eagls.py) 要求 text_offset、key、version。
- `text_offset` 指成员内文本区起点，前方标签表保持原样。
- version 1 对起点之后**全部**尾字节循环 key XOR，包括尾部标记。
- version 2 取最后一字节作为有符号 int8 seed。
- `0x80..0xFF` 因而应解释为负值，不能按无符号 seed 替代。
- version 2 每隔一个字节 XOR 一次，最后 seed 字节不参与修改。
- seed 序列同样来自 MSVCRT，密钥下标按随机值取模。
- 上游导出正文时剔除末尾 `version` 个字节，不能当成台词翻译。
- 调用方应记录 footer 原样，避免丢失后无法恢复。
- 参数非法或正文空间不足时拒绝，不无声地返回原字节。

## 标签表和地址
- EAGLS 标签记录宽 36 字节，ALIS 为 136 字节。
- 最后四字节是文本区内的相对 offset，其余为名字区。
- 第一个字节为零的记录是表结束标志。
- ALIS 源工具常用 text_offset `136000`，这里不把它硬编码为普适值。
- [read_labels](../python/engines/eagls.py) 验证表边界和每个 offset。
- 标签名不能重名，表必须存在终止空记录。
- **标签表存储的 offset 是权威值。** 标签不一定位于行首，常紧跟在命令之后，例如 `…",0)$LABEL` 或 `…"$LABEL`；不能靠行首搜索重新推导。
- [verify_label_offsets](../python/engines/eagls.py) 校验每个 offset 处的正文以 `$` + 标签名开头，且其后紧接 `:`、`(`、CR、LF 或正文结束；这避免把 `$START` 错配到 `$STARTED`。不符时报错并给出标签名与 offset。
- [apply_edits_with_labels](../python/engines/eagls.py) 先校验原 offset，再按字节跨度替换正文，把每个标签的原 offset 加上其之前全部编辑的长度差，最后重新校验。编辑跨度不能重叠、越出正文或覆盖 `$label` 记号。
- 两者保留原标签名、未用槽位、正文和 footer，只改四字节 offset。工作区提取与回填使用这两个函数。
- [fix_label_offsets](../python/engines/eagls.py) 是旧的行首搜索辅助：只找完整行首 `$label` 且要求唯一出现，紧跟命令的标签会被判为缺失；仅用于没有编辑跨度、标签全部位于行首的场景。
- 没有实现新建标签或全语言语法的标签发现。

## 文本提取与 name
- 源预设按 CRLF 读文本，并设置 startline=1；首行需结合具体成员核实。
- [dialogue_spans](../python/engines/eagls.py) 对单个已解码行操作。
- `&数字"文本"` 提取 message，`#名字` 提取 name；逗号之后的数字及 `=语音标识` 不是姓名。
- `52("_SelStr数字","选项")` 是已验证的选择赋值。空字符串是空槽，不导出。
- `_` 开头的整行按预设跳过；不要把所有脚本命令都当可见文本。
- 输出是字符跨度，不是成员 byte offset。
- `$label`、数字参数、变量、引号和 footer 必须保留。
- 不把 name 猜测结果回写为脚本变量或函数名。
- 编码采用明确、严格的 CP932/目标编码，失败不得忽略。
- `dialogue_spans` 仅保留为旧预设的单行辅助器；批量导出使用 `eagls_text` 的引号边界扫描和字节跨度，避免把命令的字符串参数当对白。
- 不能按行合并消息：一行可能包含多个 `&ID`；姓名命令可能紧跟上一句尾部或单独占行，应交给**后续第一条**消息，随后清空，不把其后的旁白全部标为同一说话人。
- 回填保留逗号参数、语音编号、资源字符串、消息 ID、换行及未修改文本的原始字节。重新从原件解析定位，核对 manifest，不信任外部提供的任意 offset。
- 引号、真实换行、命令分隔符不能注入字段；尚未解释的控制样式字符序列必须保留。此实现不是完整 EAGLS 命令编译器，陌生对白语法需先扩展并验证。

## 正确回填顺序
1. 确認 IDX/PAK 参数，提取完整成员及标签/文本/footer 分界。
2. 按正确版本解密成员，严格解码正文。
3. 只改经核实的文本跨度，保留标签和控制语法。
4. 拼回原标签区与 footer，用 apply_edits_with_labels 按编辑长度差平移原 offset。
5. 调用 crypt_script 恢复成员密文。
6. 用匹配版本的完整封包器更新 PAK 与 IDX。
- 工作区 CLI 会执行以上步骤，并验证原文逐成员与整包往返一致后才发布提取结果。
- 单个成员解析或原文往返失败（未知语法、标签 offset 不符、严格解码失败等）时记为 `blocked`，报告给出成员名、PAK 位置与原因；其余成员照常导出。blocked 成员不生成 JSON、不进入 writer，所有重建包按原加密字节保留；整包往返仍要求 IDX/PAK 逐字节一致。报告 `status=partial` 并列出 `blocked`，CLI 退出码：`0` 完整、`1` 部分（结果已写出）、`2` 失败（不写结果）。为 blocked 成员提供的同名译文在回填时拒收，须先扩展解析器后从原包重新提取。
- 公共层负责备份和目录写盘，leaf 只返回 bytes/结构。

## 工作区与已有字符映射

只选择实际使用的 `SCPACK.idx` / `SCPACK.pak`，不递归混入备份或既有提取目录。已有汉化补丁的输入不代表日文原版。

**不要仅凭严格解码成功选择 GBK。** CP932 与 GBK 可能同时可解码。剧本按 `storage_encoding` 严格编解码；CP932 写不下的中文走[公共 JIS 流程](../guides/jis-substitution.md)。原版游戏不带 `uif_config.json`、`version.ini`/`winmm.ini` 等字符映射；游戏目录中出现它们，说明混入了之前的汉化或试注产物，须改用未改动的原版文件提取，不能把映射当作原作的一部分。

在技能根目录运行（下列游戏路径为示例）：

```text
python -m python.engines.eagls_extract extract "<游戏目录>/script" "<游戏目录>/game_extract" --smoke-test
```

使用默认参数前先核对索引、文本区与加密布局；可通过 `--short-offsets`、`--text-offset`、`--version`、`--label-size`、`--encoding`、`--index-key`、`--script-key` 指定。未知密钥须先研究，不靠默认值宣称成功。

- `gt_input/*.json`：按成员原名生成平铺 JSON；空成员只记入报告。
- `gt_output/`：放翻译结果，文件名和数组顺序保持不变；提取不会把测试文本写进这里。
- `original/`：加密原包；`original/scripts/` 是解密后的完整成员，含标签区和 footer，**不是纯文本文件**。
- `metadata/`：逐成员 manifest，含字节跨度、姓名槽、源哈希和加密参数。manifest 的 UTF-8 指逻辑交换文字，`storage_encoding` 才是成员编码。
- `rebuilt/roundtrip/script/`：真正经过 parser/writer 的原文重封包。
- `rebuilt/smoke-test/script/`：可选的变长测试包，只用于验证；`reports/smoke-translation/` 保存对应测试 JSON。
- `reports/extraction.json`：`status`、数量、全体成员（含 `blocked` 原因）、源哈希、profile 和验证结果。

译文按同名文件放回 `gt_output/` 后告诉 agent，由 agent 校验并回写：

```text
python -m python.engines.eagls_extract rebuild "<游戏目录>/game_extract" "<游戏目录>/game_extract/rebuilt/translated-01"
```

输出目录须不存在或为普通空目录，且父目录已存在。回填按原成员真名匹配；未提供译文的成员保持原字节，未知译文文件名拒绝，不猜配。原始包、原文 JSON 与 manifest 必须保留。输出为配套 `script/SCPACK.idx` 和 `script/SCPACK.pak`；这两个文件必须一起使用，不能只换 PAK。

## 验证与局限
- 合成测试有 MSVCRT 已知向量，不只测自身加解密互逆。
- 测试覆盖 v1/v2、负 seed、隔字节变换、索引 footer 保留。
- 标签测试验证新 offset、禁止前缀误匹配、紧跟 `)` 或 `"` 的标签，以及变长/缩短回填后的 offset 平移。
- 提取时的成员错误进入 `blocked` 列表，回填错误直接失败；两者都带成员名，提取另带 PAK 位置，标签错误另带标签名与 offset。
- 文本规则测试验证 name 与 message 在同一行的提取。
- [test_eagls.py](../tests/test_eagls.py) 覆盖短/长索引、零/非零基址、变长重定位、填充保留、坏偏移、重名/路径、跨行姓名、选择槽、编码拒绝、篡改 manifest 和工作区回填。
- ALIS 的验证边界为合成标签、脚本和归档布局；不支持新建标签或有空隙的归档。
- 没有启动游戏、安装补丁或验证运行时排版。离线格式自洽不能替代实际加载测试；字体与 hook 运行环境是否正常仍属于部署验证。
- 原工具的已知明文 key 搜索没有移植，参数需要有证据地提供。
- 不宣称“IDX 解密成功”就等于“剧本往返完成”。

## 来源与许可
- 固定 SExtractor commit `8d8d976fd04ae54e7c677705af937273d04a376a`。
- 参考 `src/extract_EAGLS.py`、`src/engine.ini`、`tools/EAGLS/README.md`。
- 算法来源为 `scpacker.py` 的 `MSVCRTRand/decrypt_idx/decrypt_slice/fix_offsets`。
- 本次 reader/writer 另参考其 `get_data/encrypt`，增加偏移、边界与保真验证；没有运行上游会原地覆盖原包的 `pack` 命令。
- 参考源码 SHA-256：`9e5626dbd0b0f7385dc4b68dc76d95c64df7c1931b1a6c4f5794b3738dfe3e9a`。已知 key 与 text_offset 另经 GARbro-Mod `ArcFormats/Eagls/ArcEAGLS.cs` 交叉核对；未移植其代码。
- [固定工具源码](https://github.com/satan53x/SExtractor/blob/8d8d976fd04ae54e7c677705af937273d04a376a/tools/EAGLS/EAGLS_script_tool/scpacker.py)。
- tools README 说明 EAGLS_script_tool 由 Cosetto 提供，保留该归属。
- 按 SExtractor 根 GPLv3 保守处理本改编为 GPL-3.0-only；子工具来源链另见 provenance。
- 详细验证边界见 [provenance](../provenance/sextractor-core.json)。
