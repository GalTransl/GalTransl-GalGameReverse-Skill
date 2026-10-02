# Kirikiri / KAG：KS 文本与 XP3 / PSB SCN 往返

## 新游戏先走格式族路线

带 BOM 的 KAG `.ks` 若使用 `@nm t=` / `[np]` / `@exlink txt=`，参考 [KAG 明文对白工作流](kirikiri/kag-text.md)。它有通用提取/回写入口，不走 PSB/SCN 的 `kirikiri_extract`。

先读 [Kirikiri 通用方法、能力分层与移植契约](kirikiri/workflow.md)。使用 `kirikiri_probe` 分开验证索引、过滤器和内层格式；不要把标准 XP3 索引的 `plain` 标签理解成正文必然未加密。过滤器配置与游戏名分离，现有 SCN 入口支持 `--filter-spec`；KAG 词法验证和完整对白读写是两个阶段。

遇到 `Hxv4` 扩展和哈希/短 Unicode 文件名时，继续读 [Hxv4 静态解密与重封包](kirikiri/hxv4.md)。制作 `patch.xp3` 时重点阅读该页“Hxv4 扁平 patch.xp3”：根目录哈希与有效 Poly1305 标签均不可省略。已验证静态配置、名称核验、正文过滤和保留身份的归档 writer；对白语义回填与游戏加载需分别验证。

已知 PSB SCN 的 Hxv4 对白流程使用 `python -m python.engines.kirikiri_hxv4_text extract "游戏/data.xp3" "游戏/游戏名_extract" --exe "游戏/启动程序.exe"`；回填使用同模块的 `pack "提取目录" "新打包目录"`。它复用共享 SCN 契约，另行核验原始 Hx 身份并输出加密包。不要直接对这类项目使用普通 `kirikiri_extract pack` 的明文中间包。

## 先按内层格式分流

| 证据 | 路线 |
|---|---|
| 解码后为 KAG 文本的 `.ks` | 本页原有有限 KS reader/writer；不能泛化宏与标签 |
| 《千恋＊万花》原版 `data.xp3` / `patch.xp3`，`sen:` 名称表、Cx 过滤、`PSB\0` v3 的 `.ks.scn` | [Senren 原版 SCN 路线](#senren-原版-scn-路线)，不得按 KS 文本或无过滤 XP3 处理 |
| 《LOVEREC.》原 `data.xp3`，`eliF` 名称表、标记加密但实际明文且校验正确的 PSB v2 SCN | [LOVEREC 原版 SCN 路线](#loverec-原版-scn-路线)，不得套用 Senren Cx，也不要误选中文 `patch.xp3` |
| PSB v3 SCN 中正文为语言数组（5 槽/6 槽外层） | [多语言 SCN](#多语言-scnnekopara-vol4-与-oppai-academy)，选择已有语言槽后回填 |
| 汉化组 `scenario.pck`、`Script.pck` 等 `EVB\0` 容器 | 与原版 XP3 分开识别；下面的原版流程不读取这些文件 |

## 统一 PSB SCN 批处理入口

使用 [kirikiri_extract.py](../python/engines/kirikiri_extract.py)，按归档特征和内层结构处理，不按游戏目录名选择逻辑：

```text
python -m python.engines.kirikiri_extract extract "游戏目录" "新的提取目录" --archives data.xp3 --verify-edits
python -m python.engines.kirikiri_extract pack "提取目录" "新的打包目录"
```

- `--archives` 接收游戏目录下的归档相对路径，按参数顺序后者覆盖前者；默认只读 `data.xp3`。先判断原版/汉化来源，再显式选择补丁，不自动推断语言或加载优先级。
- `--overlay path` 默认按完整成员路径覆盖。已证实补丁将剧本移到根目录时才用 `--overlay basename`。不同路径的同名剧本会获得稳定的导出后缀，映射保存在报告中。
- [kirikiri_xp3.py](../python/archives/kirikiri_xp3.py) 有界读取索引，选择 `plain`、`elif-plain` 或已验证的 `senren-cx` 适配器。`--archive-profile` 可显式约束识别结果；未知过滤器需要增加适配器，不能复制一套按游戏命名的批处理脚本。
- `--output-format same` 默认沿用输入适配器；混合格式输入必须明确选择 `plain`、`elif-plain` 或 `senren-cx` 输出。选择输出格式只确认容器可重读，不代表目标游戏会加载。
- 内层支持未加密、无资源区的 PSB v2/v3：单语言 6/9 槽及下述多语言 5/6 槽 SCN。未知方言拒绝。KAG 文本继续走下述 KS 接口，TJS 字节码、其他 PSB 方言和任意商业过滤器尚不属于这个批处理入口。
- `--language-index` 为从 0 开始的已有语言槽，默认 0；实际语言须根据样本核对，不能按编号推断语言。报告保存所选槽，`pack` 自动沿用。不插入语言，不自动补缺失译文槽。
- 导出、回填、缓存重建、结构验证共用一套流程；游戏差异放归档适配器或格式解析器。新目录 profile 为 `kirikiri-psb-scn/1`；已交付的 Senren / LOVEREC 旧提取目录可直接用此入口 `pack`，无需重提取。

测试见 [test_kirikiri_extract.py](../tests/test_kirikiri_extract.py)：任意归档文件名、路径重名、覆盖选择、空剧情、混合格式与输出选择。

## KS 能力边界
- 引擎 ID：`kirikiri`。
- 参考模块：[python/engines/kirikiri.py](../python/engines/kirikiri.py)。
- 实现的是有限 KAG 方言的字符区间提取与替换，不是完整 TJS 编译器。
- 输入已经正确解码的 `str`，输出区间或新的 `str`；模块不读写文件。
- 未识别的行内标签直接拒绝，不拿正则扫描结果冒充全格式支持。

## 识别证据
- `.xp3` 容器、`.ks` 剧本、`.tjs` 系统脚本是组合线索，不是单项定论。
- KS 中的 `*label`、`@command`、`[command]`、`;comment` 支持 KAG 判断。
- 文件扩展名被修改时仍应检查 BOM、解码结果和真实语法。
- XP3 签名只证明容器格式，不能证明成员都是 KS。
- `.scn` 可能是另一种序列化剧本，不能按 KS 文本处理。
- `.soc` 与 TJS 字节码同样不是普通文本。

## 格式方言
- VN 的 KS reader 会按 UTF-8 BOM、UTF-16LE BOM、否则 Shift-JIS 选择编码。
- VN writer 默认 UTF-16；本模块不继承这个隐含转码决策。
- KAG 标签/宏可由游戏脚本扩展，因此不存在仅按引擎名通用的属性名单。
- 本子集允许 `[r]`、`[l]`、`[p]`、`[cm]`、`[ns]`、`[nse]`。
- 支持 `#名字`、标签 `|标题` 及普通文本片段。
- `[iscript]` 与宏块作为不透明内容跳过，要求存在相应结束标记。
- 其他 `@` 行命令不提取；其他行内命令报错。
- Ruby、带引号的标签属性、动态 `eval` 不在此子集。

## 容器到剧本路线
1. 确认原始文件与资源清单，避免用后缀批量替换所有成员。
2. XP3 容器参考 [python/archives/xp3.py](../python/archives/xp3.py) 模块。
3. 容器解密/过滤器处理完成后，再对候选 KS 做严格文本解码。
4. 保留成员原路径、编码、BOM 和换行元数据交给公共 manifest。
5. 修改后的文本重编码后才能进入已验证的部署路线。
- 本页不假定归档模块的函数名，也不假定它支持所有商业加密方案。

## 源码与算法对应
- 来源：`VNTextPatch-net8`，许可 MIT。
- 提交：`d9c0fab7b72fdcf87d674ef12a84d3829c9188be`。
- 路径：`VNTextPatch.Shared/Scripts/Kirikiri/KirikiriKsScript.cs`。
- `GetRanges` 对应块状态与逐行遍历。
- `GetLineRanges/GetNameRanges/GetLabelRanges` 对应行类别和字段位置。
- `GetMessageRanges` 对应标签切分以及 `ns/nse` 的 name/message 状态切换。
- Python 保留每个区间的原始位置，不使用 VN 的跨行合并及自动换行。
- 修正了缩进导致 `#` 后名字起点不能直接用行首加一的问题。

## Python 接口与示例
```python
from python.engines.kirikiri import kag_spans, patch_kag
text = '#Alice\r\nHello[r]world[l]\r\n'
fields = kag_spans(text)
assert [f.kind for f in fields] == ['name', 'message', 'message']
patched = patch_kag(text, {1: '你好'})
assert patched == '#Alice\r\n你好[r]world[l]\r\n'
```
- `kag_spans(str) -> tuple[Span, ...]`：start/end 为 Python 字符下标。
- `patch_kag(str, dict[区间序号, str]) -> str`：序号属于原提取结果。
- 不把字符下标当作文件字节偏移；编码工作在调用层完成。

## name / message 映射
- `#` 和 `ns/nse` 范围内文本产生独立 `name` 字段。
- 相邻多个名字不会被覆盖为最后一个；调用层按顺序保留全部字段。
- 名字以 `$` 开头时返回 `name_variable`，例如 `$str20`。
- 变量仍在结果中，但 `writable=False`，禁止把变量写成显示名。
- `title` 是标签标题，不应混同正文或丢掉。
- 本模块不猜测一个名字要关联几条正文，也不自动拆分多人名。

## 回填、长度与控制码
- 从后向前替换区间，原标签、空白和换行保持不变。
- 禁止译文注入括号标签、NUL、物理换行以及行命令前缀。
- 换行应保留原 `[r]` 标签；需要重新排版时另做经审核的标签级变更。
- 不改变 label、宏名、跳转目标、图像或音频参数。
- 本层无二进制地址更新；XP3 中长度/校验等由容器层负责。
- 编码失败必须返回调用者，不能用 `errors=ignore/replace` 消除字符。

## 部署条件
- 先确认游戏允许何种编码、外置脚本或补丁容器加载方式。
- 不能承诺创建 `patch.xp3` 就必然被加载；优先级需实际验证。
- 脚本签名、私有过滤器、路径大小写和补丁顺序都可能影响加载。
- 原包只读；写出、备份、路径约束与 manifest 由父 Skill 统一管理。
- 首先用空改动测试，再测试单句、选择、回滚和存档路径。

## 验证与缺口
- 合成测试覆盖 name、正文、标签标题、代码块、宏块和变量保留。
- 覆盖未闭合块、未知标签、标签注入的拒绝行为。
- 测试位置：`tests/test_engines_primary.py` 中 `TextDialectTests`。
- VN `FolderScriptCollection.cs` 的 `new KirikiriScnScript()` 被注释禁用。
- 但 `msg-tool/src/scripts/kirikiri/scn.rs` 确有 SCN 实现，不能写成“无人支持”。
- msg-tool 来源提交 `f72716cee88554d40c1cdface2812493b14ca653`，GPL-3.0-or-later。
- 通用 KS 模块没有实现 SCN。下面另有 Senren PSB v3 专用配置路线，仍不代表任意 TJS/宏或其他 SCN 方言可写。

## Senren 原版 SCN 路线

统一入口：[kirikiri_extract.py](../python/engines/kirikiri_extract.py)。依赖 Python 3.11+ 标准库，不执行 EXE/DLL/TJS，不需要安装外部项目。

```text
python -m python.engines.kirikiri_extract extract "游戏目录" "新的提取目录" --archives data.xp3 patch.xp3 --overlay basename --verify-edits
python -m python.engines.kirikiri_extract pack "提取目录" "新的打包目录"
```

目标目录必须不存在；已有 `<游戏名>_extract` 时换新名字。上述命令只打开指定的 `data.xp3`、`patch.xp3`，不递归扫描、不读取任何 PCK；源归档按流读取索引、按预算解码 SCN，原包 SHA-256 用分块读取核对。其他游戏根据归档与覆盖证据调整参数。

- `gt_input/`：按真实剧本名平铺的 UTF-8 name/message JSON，可直接导入 GalTransl。
- `gt_output/`：同名译文回填入口；缺少的译文使用原文，不认识的文件名拒绝。
- `original/`：解密后的 SCN 基准；`metadata/`：源哈希、树引用路径、姓名策略、控制码。
- `reports/extraction.json`：源包哈希、全部 SCN 索引、采用的成员、统计与验证结果。
- `rebuilt/roundtrip/scenario.xp3`：原文经 SCN writer 与 Senren 加密封包得到的新剧情归档。
- `rebuilt/smoke-test/scenario.xp3`：仅 `--verify-edits` 生成，为所有正文加上 `验证`，用于变长 UTF-8 回填测试，不是翻译成品。

### Senren XP3 与 Cx

[kirikiri_senren.py](../python/archives/kirikiri_senren.py) 按有界索引读取：头中的索引指针先指向 `0x80` 跳转块，再指向实际索引。`sen:` 记录指向独立 zlib 名称表，`hnfn` 记录包含 Adler-32、UTF-16LE 名称和 NUL。不能假设名字就是 info 中的 hash 字符串。优先使用名称 MD5/显式名称匹配；Adler-32 不唯一时保留资源别名，不猜测同哈希对应的文件。源索引的两条 `startup.tjs` 记录不能合并进一个字典；仅剧情成员集合要求唯一。

原包还含故意不一致的安全提示记录（固定 hash、段布局及 stub 标记），专用 reader 仅识别并排除这个已核对的记录，不宽松放过普通成员的错误长度。其他未知段标志、名称结构或长度均拒绝。

Cx 使用 mask `308`、offset `1846` 和固定的三组指令排列；控制块来自 msg-tool 的 `senren_banka.bin`，作为 [4096 字节专用资源](../python/archives/kirikiri_senren_cb.bin) 随模块携带并核对 SHA-256。解释的是受限算术表达式，不调用本机机器码或 `eval`。失败的 128 字节程序生成尝试会消耗随机数，回退 stage 时不能重置 seed。XOR 过滤是对称的，解压后过滤，以明文 Adler-32 验证；回写按新明文 checksum 重新过滤再 zlib 压缩。

`build` 新建剧情专用的加密 XP3，更新 File info/segm/adlr 和 sen 名称映射。它不复制媒体资源，也不声称新包与原 `data.xp3` 或 `patch.xp3` 逐字节相同。原文的**每个 SCN** 可以逐字节往返，封包的验证则是重新解密、解包后每个成员与预期 bytes 一致。

### PSB 树、姓名和派生文本

[kirikiri_psb.py](../python/engines/kirikiri_psb.py) 支持未加密的 PSB v2/v3、无二进制 resource 区段的结构，校验名称 trie、字符串索引、树节点边界与完整区段顺序；v3 另校验头部 Adler-32。不把任意字节中的日文当作对白。v2/v3 以外的 PSB 版本、内层加密、资源节点、未知 node tag、重叠/循环引用拒绝。

[kirikiri_scn.py](../python/engines/kirikiri_scn.py) 从 `scenes[].texts` 的单语言 6/9 槽 tuple 提取正文，并从 `scenes[].selects[].text` 提取选项。tuple 的首槽是内部角色 ID：显示名槽存在时 `name` 可写，否则导出的 `name` 仅作上下文，不能改内部 ID。声音、场景状态、源行号、跳转目标不属于译文。

字符串池会被不同位置共享；甚至树节点也可能重复引用。writer 按**完整树路径**定位每次引用，改变的字符串追加到新池项，不能全局替换旧字符串 ID，也不能只用物理节点地址区分记录。重建受影响容器的相对偏移、字符串索引宽度、全局区段地址和头校验；未修改的子树保留原始字节。变长验证比较整棵树的非文本语义摘要，防止对白修改波及资源文件名、角色 ID 或代码参数。

JSON 的物理换行映射回字面 `\n`。保留 `[读音]字`、`[读音,n]`、百分号控制和颜色控制序列；译文不能增删或重排控制码。9 槽 tuple 的 7/8 槽是派生的读音/搜索文本，必须与正文同步重建：`[读音,1]` 消费后续两个字，`[・]` 是强调标记，读音缓存仍保留正文字符。不能直接照搬只消费一个字符的 ruby 正则。读取时先验证原缓存与规则相符，未知变体拒绝。

### 回填与部署边界

回填会重新解析原 SCN，重建完整 manifest，与保存的 manifest、原文 JSON、源哈希比较；不信任 sidecar 地址。纯 name/message 数组仍必须保持顺序，无法检测无 ID 的等长重排。全部文本、显示名与控制码验证后才生成新归档；全部成员再次解包并核对内容。

原版目录有独立 `.sig` 文件。新归档**没有生成或伪造这些签名**，也没有验证原版启动器是否接受新包、补丁加载次序或中文字体。`scenario.xp3` 是待部署的测试/翻译产物名称，不能仅凭格式正确就称为可直接覆盖的游戏补丁。原文件与已有汉化包均不修改。

回归测试：[test_kirikiri_senren.py](../tests/test_kirikiri_senren.py)。出处见 [Kirikiri 算法来源](../provenance/kirikiri-sources.json)。

## eliF 索引与 PSB v2 SCN 路线

适用于 `eliF` 名称映射与 PSB v2 的已知 SCN profile。`info flags=0x80000000` 不足以判断正文加密：必须按段解压后核验 Adler-32 和完整 PSB 树。入口仅对该 profile 显式允许 `marked_plaintext=True`，不能推广到包内其他资源或其他游戏。

从 skill 根目录运行 [kirikiri_extract.py](../python/engines/kirikiri_extract.py)：

```text
python -m python.engines.kirikiri_extract extract "游戏目录" "新的提取目录" --verify-edits
python -m python.engines.kirikiri_extract pack "提取目录" "新的打包目录"
```

两个输出目录都必须不存在，父目录必须已存在。提取只读 `data.xp3` 的索引、选定 SCN 和流式原包哈希，不递归扫描、不载入整个包，不执行 `BootStrap.exe`、游戏或转换工具。源 SCN 累计预算 256 MiB、单个 32 MiB；索引预算 16 MiB。导出 `gt_input` 平铺 JSON，译文放同级 `gt_output`，保留文件名和顺序。空缺译文按原文回填，未知文件名拒绝；原文、manifest 或源哈希不一致时拒绝写包。

`original/` 保留原始 PSB；`list/map` 系统索引在 `original/system/`，没有对白 JSON。输出 `rebuilt/roundtrip/scenario.xp3` 和可选的 `rebuilt/smoke-test/scenario.xp3`。前者是原文经 parser/writer 处理后的剧情包；后者为全部正文加入 `验证` 的测试包。正式 `pack` 生成 `scenario.xp3` 与 `verification.json`，不安装或覆盖游戏。

### eliF 索引及 PSB v2 的实际差异

[kirikiri_elif.py](../python/archives/kirikiri_elif.py) 读取原版的双级 XP3 索引，以及明文转换包的单级索引。`eliF` 包含内容 Adler-32 和 UTF-16LE 真实名，`File/info` 中可能仅有名称 MD5。名字映射优先核对别名/真实名；同 Adler-32 不能强行合并成员。错误的段范围、名称长度、解压长度和正文校验都会拒绝。

`!scnlist.txt` 存在指向偏移 13、落在 XP3 头内的特殊坏条目。reader 对这个**精确已知条目**保留诊断，`read_member` 拒绝读取，不猜偏移修复、不让失败混入剧情成功统计。其余成员仍严格拒绝越界；原版 `data.xp3` 的剧情流程不涉及该坏条目。

共享 [kirikiri_psb.py](../python/engines/kirikiri_psb.py) 现在区分 v2/v3：v2 头长 40，无 v3 的头校验字段；header-length 槽可为 40 或 0，都按明确布局解析并保留原值。回写 v2 时不能在偏移 40 写 Adler-32，否则会破坏紧随其后的名称 trie。统一入口按实际 PSB 头选择 v2/v3，共享树路径克隆、变长索引、派生文本和姓名策略；读取历史提取目录时仍核对其原版本约束。

输出为新的**明文 eliF XP3 剧情包**：使用真实路径生成名称映射，重建 zlib 段、长度、偏移和正文 Adler-32。原文的每个 SCN 可逐字节一致；新剧情包不包含媒体，不等同于逐字节重建整个原 `data.xp3`。全部包成员必须重新解包比较。不要把 `.sig` 签名、补丁加载优先级或中文字体兼容视为已验证。

测试见 [test_kirikiri_loverec.py](../tests/test_kirikiri_loverec.py)，覆盖 v2 的两种头长、中文变长、共享字符串保持、标记明文的显式验证、文件名映射、坏校验拒绝，以及提取/回填入口不读取汉化或追加包。

## 多语言 SCN

仍使用同一个 `kirikiri_extract` 入口；先核对 XP3 索引、正文 Adler-32 与 PSB 结构，再选择语言槽。

```text
python -m python.engines.kirikiri_extract extract "游戏目录" "新的提取目录" --archives data.xp3 adult.xp3 --language-index 0 --verify-edits
python -m python.engines.kirikiri_extract pack "提取目录" "新的打包目录"
```

示例提取目录已存在时必须换新名字。先核对所选语言槽，其他语言槽保留在原 SCN 内，不混入本次 JSON。`gt_input` 可直接导入 GalTransl，译文放同级 `gt_output`。

### 结构与回填

- 5 槽外层：`[内部角色ID, 语言数组, voices, sourceLine, state]`。语言项为 `[显示名, 正文, 可见长度]`，或再追加读音与搜索缓存。长度规则是去除控制码、换行并展开 ruby 正文后的字符数，不能用带控制码的字符串长度代替。
- 6 槽外层：`[内部角色ID, 外层显示名, 语言数组, voices, sourceLine, state]`。语言项为 `[显示名, 正文]`，或再追加两个缓存。仅所选语言项的显式显示名可写，内部 ID 和外层字段保留。
- 多语言选项从 `selects[].language[index].text` 读取；仅槽 0 为 null 时采用选项本身的 `text`。缺失的其他语言槽拒绝，不偷偷回退。仅含非负整数 `selidx` 的标记，以及符合 [工作流](kirikiri/workflow.md) 严格字段规则的链接记录，在语言选择前识别为非文本结构，保留并计入诊断，不导出为空译文。
- 多语言文字长度由 PSB 整数节点写回；整数宽度变化会重建容器偏移。正文、姓名、整数长度和缓存均按完整树路径修改，验证时整棵树其余语义（包括其他语言、场景代码、资源路径）必须保持一致。
- 读音缓存存在省略 ruby 读音中 `・` 的变体。仅当原缓存精确符合“读音去中点”规则时，在该记录 manifest 保存此变体并沿用；其他缓存不符仍拒绝。原文回填保持全部 SCN 字节一致，不把样本差异扩散为所有游戏的缓存规则。

回归见 [test_kirikiri_multilang.py](../tests/test_kirikiri_multilang.py)。每个语言槽须核对其控制码和缓存方言，不能由一个槽成功推断其他槽均可回填。
