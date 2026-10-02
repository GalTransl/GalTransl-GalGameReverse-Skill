# SystemC / SystemB3：FPK、ACT 与 UTF-8 TXD/PTR

CP932 ACT/DAT/SPT 工作区通过 [systemc_extract.pack](../python/engines/systemc_extract.py) 回注时，默认优先使用 [公共 JIS 替换](../guides/jis-substitution.md) 处理无法编码的中文；`--jis-mode off` 保留严格 CP932。替换会话覆盖整个输出包，结果目录自动包含随包 x86 `winmm.dll`、`uif_config.json`、`jis-mapping.json` 和 `JIS-部署说明.txt`（没有实际替换则不生成）。最终提醒用户按说明部署兼容 hook 或匹配映射的替换字体，并实测加载和显示。低层 `inject_act(..., text_codec=codec)` 支持显式接入；UTF-8 TXD/PTR 不走此方案。

## 模块分工

| 层 | 模块与接口 |
|---|---|
| 归档 | [archives/systemc.py](../python/archives/systemc.py)：ZLC2 回指解码、literal 编码、加密尾索引 FPK 读写 |
| 脚本 | [engines/systemc.py](../python/engines/systemc.py)：`systemc_name_header` |
| UTF-8 文本表 | [systemc_txd.py](../python/engines/systemc_txd.py)：`read_table`、`export_table`、`inject_table` |
| UTF-8 工作区 | [systemc_txd_extract.py](../python/engines/systemc_txd_extract.py)：`extract` / `pack` CLI |

按下述版本与阶段限制调用；成员 codec 或索引子集不等于完整解包器。

## 能力边界
- 状态：按方言分别支持，不能只凭 SystemC.ini 选择 writer。
- Python：`python/engines/systemc.py`。
- 真正实现 ZLC2 纯 literal 成员封装，不是假 byte replace。
- `decode_zlc2_literals` 仍只接受 literal 子集；`decode_zlc2` 支持真实回指，`decode_member` 有界处理嵌套层。
- `read_fpk_index/unpack_fpk/rebuild_fpk` 支持高位文件数、加密尾索引的 FPK。CP932 ACT/DAT/SPT 和本页下方 UTF-8 TXD/PTR 是两条不同文本路线，不要混用。

## ママ×カノ：UTF-8 TXD/PTR 实测（2026-10-01）

### 识别和输入选择

- `SystemC.ini`、`data.fpk`、`languages/japanese.lang`；FPK 首 u32 的高位为 1，成员为 `ACT_A.txt`、`ACT_A.DAT`、`ACT_A_JA.TXD`、`ACT_A_JA.PTR`、`Axxxx_xx.spt` 等配套结构。
- 实测 `data.fpk` 为 4,579,050 字节、534 个成员；与 `日文原版/data.fpk` 的 SHA-256 完全相同。文件夹叫“日文原版”本身不是判断证据。
- `Patch3.fpk` 有 11 个成员，但没有 ACT/TXD/PTR/SPT 剧本表，不合并进文本基准。通过索引检查即可，不必解出大图和声音。
- 运行语言配置为 `code=ja`，文本严格 UTF-8。不能套用 CP932 解码，也不需要创建字符替换映射。这里不自动改 `.lang` 文件、字体或启动游戏。

### PTR/TXD 布局与编译引用

- PTR：`PTR ` magic + u32 条目数 + 8 字节保留区，随后每条 **12 字节**：`u32 text_id / u32 byte_offset / u32 byte_length`。ID 不必从 1 连续编号，不能把它当数组下标。
- TXD 没有分行/记录分隔符；只按 PTR 的 UTF-8 **字节**范围读取。每条内部以第一个 ASCII 逗号分开 `name,message`，姓名可以为空；正文中的后续逗号属于正文。
- 字面量 `\n` 是正文换行，JSON 导出为真实换行，回填反向恢复；不能对整个 TXD 用 CSV 或逗号切分。PTR 必须覆盖整个 TXD，拒绝重复 ID、重叠、空隙、越界和残留字节。
- ACT 源脚本通过行末 `[text_id]` 标记文本；DAT 是 `u32 count + count × 156`，第 80 字节起有场景/行范围；SPT 是 `u32 count + count × 32`。
- SPT opcode=1 的八个 i32 是 `opcode, character_id, voice, -1, ACT_first_line, ACT_line_count, 7, text_id`。本方言最后一项为 TXD ID，**不是旧 Tomefure 方言的固定 0**。
- 导出先核对 DAT 场景身份、SPT ID、ACT 行尾 ID、姓名/语音及 TXD 原文；不把 ACT 的命令、备注或整表任意字符串当对白。
- ACT_B 有两个场景标签前置 ASCII 空格；按 DAT 指向的行识别，并允许行首空格，不能因此漏场景。ACT_A 有三条源文本含行首全角缩进而 TXD 已去除；报告记录这些 ID，导出以实际 TXD 为准，不统一清理其他空格。
- `ACT_W_JA.PTR` 只有 ID 819，但没有本批 DAT/SPT 对应调用。该条及整对文件保持原样，报告为无可导出记录；不要把它混进翻译队列或补造空 JSON。

### 安全回填边界

- 只改 UTF-8 TXD 的文字，按新字节长度重建 PTR；保留 ID、保留区、顺序、未引用条目和未改文本字节。
- **ACT、DAT、SPT、charaid.tbl 不改写**。它们作为原始身份/控制流证据保存；运行时文本翻译不等于重新编译 ACT。姓名是 TXD 内真实可写字段，改变显示姓名不改编译语音/人物 ID。
- 回填重新解析原包和配套来源、核对 JSON 与 manifest，再解析新 TXD/PTR 比对；元数据不能提供任意可信偏移。
- 保持每字段的换行和控制码顺序/数量。本样本验证过 `$S/$L/$M` 及 `&heart;`、`&aseri;`、`&ikari;`、`&namida;`、`&nakigao;`、`&kirari;`、`&egao;`、`&kaminari;`、`&dokuro;`；不编造未知符号的语义，遇到陌生控制码拒绝。
- UTF-8 可编码中文，但中文字体覆盖、自动换行、姓名栏宽度和实际加载仍须游戏内验证，当前没有此验证。

### 可复现命令

在技能根目录运行，`<输出目录>` 取游戏内新建的 `<游戏名>_extract`。已有目录不能覆盖。

```text
python -m python.engines.systemc_txd_extract extract "<游戏目录>" --output "<输出目录>" --verify-edits --reference "日文原版/data.fpk" --reference Patch3.fpk
```

- `gt_input/`：6 个平铺 JSON，**27,665 条**，其中 17,221 条有姓名、70 条为选择文本；可导入 GalTransl。实际文件名为 `ACT_A_JA.json` 至 `ACT_F_JA.json`。
- `gt_output/`：接收同名、同顺序译文。未提供译文的表保留原样；未知 JSON 文件名拒绝。
- `original/data.fpk` 与 `original/members/`：原包、全部解码成员，均为回填基准；`metadata/`：配套来源和文本 ID/场景绑定。
- `rebuilt/roundtrip/data.fpk`：全部文本表经过 parser/writer 后重新封包，与原包逐字节一致。
- `rebuilt/smoke-test/data.fpk`：给所有正文加“验证”的中文变长测试包，约 6.89 MB；实际再解包确认只改了 6 对 TXD/PTR，534 个成员均正确。测试包不能当正式译文补丁安装。
- `reports/extraction.json`：源哈希、表状态、未引用 ID、原文缩进差异、参考包比较及测试结果。

译文放好后回填到另一个新目录：

```text
python -m python.engines.systemc_txd_extract pack "<输出目录>" --output "<输出目录>/rebuilt/translated-01"
```

得到 `data.fpk` 与 `verification.json`，不会覆盖游戏文件。新成员使用 ZLC2 literal 编码，所以变长测试包体积增加不代表数据损坏；未改成员保留原压缩流。原索引的四字节不透明字段、间隙、索引位置关系和密钥由已有 FPK writer 保留。

### 验证与来源

- 文本表和配套关系为本次真实结构研究的新实现；复用现有 SystemC FPK/ZLC2 模块，没有引入外部运行依赖。
- [test_systemc_txd.py](../tests/test_systemc_txd.py) 覆盖 UTF-8 字节长度、中文姓名、稀疏 ID、坏指针、编译身份、未知控制码、manifest 篡改、未引用条目及工作区打包。
- 独立按尾索引、ZLC2 与 PTR 布局再次读取落盘测试包，核对全部 27,665 条中文变长正文；只允许 12 个 TXD/PTR 成员变化。原包、日文副本及 Patch3 源哈希均未变。

## SystemB3 容器线索
- 来源 `fpk_pack_SystemB3.py` 从 u32 文件数开始写 FPK。
- 条目由偏移、压缩尺寸、二十四字节文件名组成。
- 数据成员外层使用 `ZLC2` 和 u32 解压大小。
- 该源码写索引尺寸时与八字节 ZLC2 头的计入关系存在疑点。
- 该旧脚本的普通索引布局不由当前加密尾索引 writer 覆盖；不能互换使用。
- 本页选择证据明确的成员流编码算法作为局部实现。

## literal 成员算法
- `encode_zlc2_literals` 写 `ZLC2`、原始字节数。
- 正文按最多八字节分组。
- 每组先写控制字节 00，再原样写这一组 literal。
- 最后一组允许不足八字节，不擅自填充原始文件。
- 没有字典回指，因此体积通常比输入更大。
- 不推荐用这种“伪压缩”处理大容量资源。

## 有界读取
- `decode_zlc2_literals` 只接受控制字节全为 00 的成员。
- 遇到真实回指位时明确报错，要求完整 LZ 解码器。
- 校验声明大小、每组输入、输出预算及未解析尾部。
- 默认解压上限 64 MiB。
- 空成员也是明确的八字节头，不以空输入冒充完整成员。
- 不加载原目录中的图片/字体资源。

## 文本路线与 name
- `src/reg.yaml` 的 `_BIN_SystemC` 是另一条文本预设线索。
- 预设识别人名后接全角空格、左括号和全角数字。
- `systemc_name_header` 只实现该明确头形态。
- 返回 name 与未动的 suffix，不把其余任意行当 message。
- 输入必须已经确认为正确解码的 SystemC 文本。
- 英文命令、注释前缀和无头字符串不会被推断成姓名。

## 回填与控制码范围
- codec 以 bytes 工作，不改字符编码和控制字节。
- 它重建原始长度和分组控制流，不分析字符串长度或地址。
- 角色名头识别器只读，没有“通用正文替换”接口。
- 内部剧本的段落、指针、选项仍需专用 writer。

## Python 示例
```python
from python.archives.systemc import encode_zlc2_literals, decode_zlc2_literals
member = encode_zlc2_literals(b"synthetic")
assert decode_zlc2_literals(member) == b"synthetic"
```
```python
from python.engines.systemc import systemc_name_header
header = systemc_name_header("仮名　（１２）")
assert header["name"] == "仮名"
```

## 部署条件与缺失步骤
- 上述已验证加密尾索引支持 FPK 读写与真实压缩回指；其他索引布局仍需单独研究。
- 旧的单一姓名头辅助器不具备脚本回填能力；完整配套方言按对应实现选用。
- 来源的 FPN 字库转换属图像工具，本模块没有该实现。
- 字库、代码页、宽度和系统菜单需分别验证。
- 不应把 SystemB3 子集泛化为所有 SystemC/SystemB 版本。

## 来源、许可与测试
- SExtractor 提交 `8d8d976fd04ae54e7c677705af937273d04a376a`。
- 成员源码：`tools/SystemC/fpk_pack_SystemB3.py`。
- 文本规则：`src/reg.yaml` 的 `_BIN_SystemC`。
- 来源仓库 GPL-3.0；保留 satan53x / SExtractor 贡献归属。
- 合成测试验证九字节输入的两组 literal、实际长度及回指拒绝。
- 另测名称头识别、资源字符串排除和预算限制。
- 测试：`tests/test_engines_tools_b.py`；没有游戏部署测试。
