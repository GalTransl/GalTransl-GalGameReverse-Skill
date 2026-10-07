# Kirikiri / KAG：剧本提取、回填与 XP3 补丁

## 使用顺序

1. 先读 [通用工作流](kirikiri/workflow.md)，分别确认 **XP3 索引 → 正文过滤器 → 内层脚本格式 → 对白语义**。这四层不能仅凭游戏名或扩展名合并判断。
2. 明确需要处理的归档、语言及覆盖关系，再按下表选择入口。解密成功不代表可以直接导出对白；能解析脚本也不代表已有对应的加密 writer。
3. 完成原文往返和少量中文回写，重新读取最终归档，再按已确认的加载规则制作补丁。结果与交付遵循主 Skill 的 `gt_input/gt_output` 约定。

## 按格式选择入口

| 已确认的证据 | 处理路线 |
|---|---|
| 带 BOM 的 KAG 文本，宏语义符合 `nm/np/exlink` 方言 | [KAG 文本工作流](kirikiri/kag-text.md)，使用 `kirikiri_kag_extract` |
| 成员头为 `fe fe <mode> ff fe` 或 `mdf\0` | 先解[脚本源码包装层](#脚本源码包装层simplecrypt-与-mdf)，再按内部内容分流 |
| 已解码的简单 KS 文本，使用 `#名字`、`[r]`、`[ns/nse]` 等有限语法 | 本页的 [有限 KS 接口](#有限-ks-接口)，需要调用层完成编码、分组和封包 |
| 完整解析后属于已支持的 PSB v2/v3 SCN | [统一 SCN 入口](#统一-scn-入口)，使用 `kirikiri_extract` |
| XP3 含 `Hxv4` 扩展及哈希/内部 ID 名称 | [Hxv4 静态处理](kirikiri/hxv4.md)；已支持的 SCN 使用 `kirikiri_hxv4_text` |
| TJS 字节码、加密内层 PSB、未知 KAG 宏或 SCN 结构 | 保留诊断，按 [新方言适配方法](kirikiri/workflow.md#适配新文本方言的方法) 补齐证据与读写规则 |

`.ks` 不保证是文本，`.scn` 不保证属于已支持的 SCN 方言；XP3 签名只证明容器格式。`kirikiri_kag.py` 的词法分析也不等于完整对白提取，不能直接把 token 当作翻译 JSON。

## 脚本源码包装层：SimpleCrypt 与 MDF

归档成员可能是**包装后的文本**，而不是纯文本。顺序是先确认归档与过滤器，再解包装层，最后按解出的内容判断它是 KAG 文本、TJS 源码还是 PSB。

| 包装 | 识别 | 处理 |
|---|---|---|
| SimpleCrypt | 头 `fe fe <mode> ff fe`，mode 为 0/1/2 | [kirikiri_simple_crypt.py](../python/engines/kirikiri_simple_crypt.py) 的 `detect` / `unpack` / `pack` |
| MDF | 头 `mdf\0` 后跟 u32 解压长度 | `kirikiri_hxv4_recover.script_names` 有界解压后从 PSB/TJS 收集候选名；不是包装文本的自动提取/回写入口 |

- SimpleCrypt 明文固定为 UTF-16LE：`unpack` 补回一层 BOM，`pack` 去掉一层 BOM；拒绝大端输入、奇数字节和无效 UTF-16，不静默转换端序。
- mode 0 按 u16 处理：`c >= 0x20` 时计算 `c ^ (((c & 0xfe) << 8) ^ 1)`。旧算法有不可逆码元，writer 遇到无法重读为原文的输入直接拒绝。mode 1 交换相邻位，变换自逆。
- mode 2 的两个小端 u64 分别是 **zlib 流本身的字节数**和 **不含 BOM 的解压字节数**；压缩长度不含 16 字节长度区。拒绝截断、尾随流、声明长度不符和超预算；`unpack(max_output_size=...)` 的输出预算包含补回的 BOM，输入另有 64 MiB 上限。
- 解开后再判断内容：SimpleCrypt 中的 KAG 文本按 [KAG 工作流](kirikiri/kag-text.md) 的语义 API 处理，TJS 源码仅静态读取；MDF 中的 PSB/TJS 按对应格式解析。包装头不能证明存在对白，不能把带 UTF-16 BOM 的文本交给 PSB parser。
- 当前 CLI 不自动解开或恢复 SimpleCrypt。调用层必须保存原始包装字节及 mode，完成内部文本的 parser/writer 往返后，用同一 mode 重新包装，再解包复核文本和非文本结构；mode 2 重压缩不保证压缩字节完全一致。来源与算法差异见[出处记录](../provenance/kirikiri-sources.json)。
- 这两种包装与 XP3 索引、独立过滤器、Hx 载荷过滤互不相干，不能互相代替；每一层的参数都要分别确认。

## XP3 索引与正文过滤

先使用 [kirikiri_probe.py](../python/engines/kirikiri_probe.py) 做有界探测，具体参数与验证强度见 [可执行探测流程](kirikiri/workflow.md#可执行探测流程)。

| 索引/适配器 | 关键条件 |
|---|---|
| 标准 `File` / `plain` | `plain` 表示标准索引布局，不证明正文没有加密；独立过滤器用 `--filter-spec` 显式配置 |
| `eliF` / `elif-plain` | 核对真实名称映射、段解压和明文 Adler-32；加密标志本身不能决定正文是否加密 |
| `sen:` / `senren-cx` | 使用随包固定配置和控制块的 Cx 适配器，适用条件必须匹配；不代表任意 Cx 都受支持 |
| `Hxv4` | 需要静态配置、名称哈希核验和认证；走专用归档/文本流程，不叠加普通过滤器猜测 |

[kirikiri_xp3.py](../python/archives/kirikiri_xp3.py) 统一索引适配；独立过滤器、参数来源和处理顺序见通用工作流。名称表中的真实名、内部 ID 和内容校验值是不同信息，同 Adler-32 的资源不能强行合并。已知特殊索引条目的处理只适用于精确识别的结构，不能放宽普通成员的长度或校验规则。

Adler-32 不符时先检查过滤器、种子、段偏移与压缩顺序；校验正确但脚本解析失败时，转向内层格式研究，不继续盲换密码。候选参数应通过多个不同成员验证，再检查整个选中脚本集合。

XP3 写入字段、补丁编号与编码选择见[通用工作流](kirikiri/workflow.md)。

## 统一 SCN 入口

[批处理模块](../python/engines/kirikiri_extract.py) 按归档与脚本结构工作，不按游戏目录名分派。以下命令供 agent 执行：

```text
python -m python.engines.kirikiri_extract extract "游戏目录" "新的提取目录" --archives data.xp3 --verify-edits
python -m python.engines.kirikiri_extract pack "提取目录" "新的打包目录"
```

| 参数 | 用法 |
|---|---|
| `--archives` | 游戏目录下的归档相对路径；默认只读 `data.xp3`，参数顺序中后者覆盖前者。先核对实际加载顺序，不自动追加补丁 |
| `--overlay path` | 默认按完整成员路径覆盖；只有确认根目录覆盖时才使用 `--overlay basename` |
| `--archive-profile` | 显式约束索引识别结果；未知适配器不能靠修改标签绕过 |
| `--filter-spec` | 已支持的独立过滤器 JSON 配置；一个调用使用同一份配置，不同配置的归档应分别处理 |
| `--output-format same` | 默认沿用输入适配器；混合输入需要明确输出格式。输出可重读不等于游戏会加载 |
| `--language-index` | 从 0 开始选择已有语言槽，默认 0；语言含义须核对内容，不由编号推断 |
| `--verify-edits` | 额外进行中文前缀的变长回写验证；生成的 smoke-test 包不是正式译文 |

新输出目录必须不存在。正文按成员预算读取，原包哈希按流核对；不要为提取剧情把整个媒体包载入内存。平铺 JSON 的重名映射、来源、覆盖关系与选择的语言槽保存在报告中，`pack` 沿用原提取配置。

### 文本定位与回写规则

默认先尝试严格方言，不通过时自动退回类型化前缀定位，两者都直接回写，不需要单独的模式开关。

- 类型化前缀：`[角色ID, 显示名, 正文, ...]`、`[角色ID, 语言数组, ...]` 或 `[角色ID, 显示名, 语言数组, ...]`；语言槽以 `[显示名, 正文, ...]` 开头。尾字段不参与定位，其原字节保留在 `original`。
- 派生字段只在**存储值与已知规则精确匹配**时登记为可重写：可见长度、speech/search 缓存各自验证；未匹配的字段路径记入该记录的 `opaque`，原样保留，不按位置猜测写入规则。
- 严格方言指已知的 5/6/9 槽布局、长度与缓存规则；任一项不通过即回退，原因写入 `exports[].verified_dialect_issue`，该成员仍照常导出。
- 正文控制码无法词法化（未知 `#`/`$`/`%` 等）时仍导出该行，但标记 `non_writable`：`pack` 拒绝改写该行而不是猜测；其他可写字段不受影响。

仍须通过有界 PSB 解析；不是对字符串池做全文搜索，也不把资源路径当对白。缺语言槽、错误类型或含糊结构报错，不静默漏行或退到另一种语言。

`opaque` 与 `non_writable` 只表示“已定位但写入依赖未验证”，不等于支持。报告在 `exports[]` 与 `limitations` 中列出，`pack` 保留这些字段原字节，并在译文改动 `non_writable` 行时报错。需要完整回写时先补齐对应写入规则，再重新提取；不得手改报告或元数据绕过校验。该流程不宣称拥有图像文字、任意 TJS、未知 PSB 或未识别 SCN 结构的支持。

### 支持的 SCN 结构与约束

- [PSB parser/writer](../python/engines/kirikiri_psb.py) 支持未加密、无二进制 resource 区段的 PSB v2/v3。检查名称 trie、字符串索引、节点边界和区段顺序；未知版本、节点、重叠或循环引用拒绝。v2 不含 v3 的头校验字段，回写必须按原版本布局处理。
- [SCN 语义层](../python/engines/kirikiri_scn.py) 从 `scenes[].texts` 和 `scenes[].selects` 识别正文、显示名与选项。严格方言覆盖单语言 6/9 槽与已知多语言 5/6 槽；其他形状按类型化前缀定位，只对可验证的派生字段回写。
- 显式显示名槽可写；内部角色 ID、voice、场景状态、源行号与跳转目标保留。没有可写显示名时，导出的 `name` 只是只读上下文。
- 多语言只修改所选槽，其他语言不混入 JSON。选项优先读取 `language[index].text`；仅槽 0 为 null 时允许使用选项自身的 `text`，其他缺失槽拒绝，不自动新增或回退。
- 正文的可见长度、读音及搜索缓存按已知规则同步重建。长度不等于带控制码字符串的长度；ruby、百分号/颜色控制与转义需保留。已识别的去中点/空格变体保存到 manifest 后沿用；与已知规则不一致的派生字段不按位置猜测，保留原字节并记入 `opaque`。
- 已知图片消息的替代文本单独导出为 `image-alt`，不能误当语音缓存。无显示字段的选项仅在符合严格结构规则时保留并记入 `skipped_structural_choices`；具体字段规则见通用工作流。图像文字及 `phonechat` 历史快照不因此自动获得翻译支持。
- 字符串池和树节点可能共享；按完整树路径定位每次引用，不能全局替换字符串 ID 或只按物理节点地址写入。writer 重建相关偏移、索引宽度、区段地址与校验，并比较非文本语义。

### 说话者字段作为显示名（`--speaker-name`）

单语言元组是 `[who, display, message, ...]`；多语言元组的语言槽内是 `[display, message, ...]`。`display` 是显式显示名槽，`who` 是外层说话者字段。

- `who` 为 null 时沿用旁白规则，不导出姓名；`who` 和 `display` 都是字符串时回写 `display`，这是默认路径。
- `display` 为 null 而 `who` 是字符串时，**含义因方言而异**：可能直接显示 `who`，也可能是内部标识符。默认将其导出为只读 `name`（`name_policy=context`），改动会被回写端拒绝。空字符串仍是显式显示名，不等同于 null。
- 需要把这类作品的人名一并汉化时，用 `--speaker-name` 显式开启：`who` 按可写显示名槽导出，回写改 `who` 自身（对话元组第 0 项）。`kirikiri_extract` 与 `kirikiri_hxv4_text` 的 `extract` 都接受该参数，取值随 `reports/extraction.json` 保存，`pack` 沿用同一规则。
- 开启前要有证据：查同作品既有汉化版本的用法，或先只改一个易触发的脚本试注，确认对话窗显示的名字确实来自 `who`。
- 多语言结构的 `who` 由各语言共享；改写会影响其他依赖该字段的语言，其他语言自己的显示名与正文槽仍保持原样。仅需改某一语言的姓名时，不应把共享 `who` 当局部显示名。
- `who` 是整数或其他类型时不猜，直接拒绝解析。

### Hxv4 中的 SCN

```text
python -m python.engines.kirikiri_hxv4_text extract "游戏/scn.xp3" "新的提取目录" --exe "游戏/启动程序.exe"
python -m python.engines.kirikiri_hxv4_text pack "提取目录" "新的打包目录"
```

该入口静态读取 EXE 配置，不执行游戏代码；复用共享 SCN 契约，同时维护 Hx 成员身份与加密封包。不能用普通 `kirikiri_extract pack` 的明文中间包代替。名称恢复、非 SCN 资源、预算与认证要求详见 [Hxv4 子页](kirikiri/hxv4.md)。

## 有限 KS 接口

[语义区间模块](../python/engines/kirikiri.py) 接收已经正确解码的 `str`，不负责文件 I/O、编码探测或完整 TJS/KAG 宏解释。

- 支持 `#名字`、标签标题及普通文本；已知行内标签为 `[r]`、`[l]`、`[p]`、`[cm]`、`[ns]`、`[nse]`。
- `[iscript]` 和宏块作为不透明内容保留，必须闭合；其他独立 `@` 命令不提取，未知行内标签拒绝。Ruby、复杂属性和动态表达式不属于该子集。
- `name_variable`（如 `$str20`）只读；相邻多个名字按顺序保留，标签标题不混同正文。调用层另行确认姓名与对白的关联。
- 替换使用原始字符区间，保留标签、空白和换行。译文不得注入标签、NUL、物理换行或行命令前缀；不修改标签名、宏名、跳转与资源参数。
- 保留源编码、BOM 和换行，不隐式统一转为 UTF-16，也不使用有损编码。字符下标不能当作文件字节偏移。

```python
from python.engines.kirikiri import kag_spans, patch_kag
text = '#Alice\r\nHello[r]world[l]\r\n'
fields = kag_spans(text)
assert [f.kind for f in fields] == ['name', 'message', 'message']
patched = patch_kag(text, {1: '你好'})
assert patched == '#Alice\r\n你好[r]world[l]\r\n'
```

对于符合 `nm/np/exlink` 宏语义的文本，应直接使用 [KAG 批处理工作流](kirikiri/kag-text.md)，其中包含编码保留、页面分组、控制码和封包验证。其他宏先按定义适配，不因名称相同就套用既有方言。

## 回填、补丁与交付

`gt_input` 保存非空剧本的原文 JSON，姓名在正文上方；译文按同名放入 `gt_output`。`original` 和 `metadata` 保存基准与定位，`reports` 记录输入、覆盖关系、统计及验证。回填重新解析原脚本，核对源哈希、原文 JSON、manifest、条数、姓名槽和控制码；缺失译文保留原文，未知文件名不猜配。纯数组仍需保持顺序，不能保证检测无 ID 的等长重排。

普通 SCN 流程的 `rebuilt/roundtrip/scenario.xp3` 是经真实 parser/writer 生成的剧情包；可选 `smoke-test` 是变长验证产物。它们不包含完整媒体资源，不能覆盖整个原资源包。原文脚本逐字节往返与新归档逐成员解包一致是两个验证层次，需分别报告。

回注优先检查 [patch.xp3 增量补丁流程](kirikiri/workflow.md#译文回注优先使用-patchxp3-增量补丁)：确认挂载位置、编号、优先级及成员路径，只选实际变化的资源。**增量补丁内所有成员一律平铺在根目录、只用 basename 加完整扩展名；脚本与字体、配置、图片等非脚本资源都一样，都不保留原包的目录结构。**不能把任意 `scenario.xp3` 改名就当作正确补丁；Hxv4 还需核对根目录哈希和 Poly1305 认证。外部 `.sig` 是否参与加载另行确认，不把归档认证和外部签名混为一谈。

交付说明原文往返、中文变长、重封包读回和游戏显示各自的实际状态。建议先测试容易触发的少量正文与选项，再验证存档恢复。缺字或方框时提醒用户检查、必要时替换 `data.xp3` 中实际使用的字体，具体做法见通用工作流。

默认由 agent 接收同名 `gt_output` 后执行回写和打包，不只提供命令让用户自行操作。所有产物写入新目录，原游戏文件保持只读；部署与启动沿用主流程授权边界。

中文缺字、字体选择与覆盖关系见[字体排查流程](kirikiri/workflow.md#中文缺字与字体选择)。使用 `appconfig.tjs` / `ENV_GameName` 的加载链，另见[窗口标题与配置文字](kirikiri/workflow.md#窗口标题与配置文字appconfigtjs)。

## 验证与维护

- 批处理回归：[test_kirikiri_extract.py](../tests/test_kirikiri_extract.py)、[多语言 SCN](../tests/test_kirikiri_multilang.py)、[类型化定位回写](../tests/test_kirikiri_structural.py)、[Hxv4 文本](../tests/test_kirikiri_hxv4_text.py)。有限 KS 回归位于 `tests/test_engines_primary.py`。
- 新索引变体放归档适配器，密码放过滤器，KAG 标签放语义方言，SCN tuple 放共享 parser/writer；复用 manifest、导出和回填流程，不按游戏名新建脚本。
- 出处与许可见 [Kirikiri 算法来源](../provenance/kirikiri-sources.json)；有限 KS 接口改编自 VNTextPatch-net8 的 MIT 实现，SCN 语义参考 msg-tool 的 GPL-3.0-or-later 实现。使用本 Skill 不需要访问这些外部仓库。
