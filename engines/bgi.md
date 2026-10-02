# BGI / Ethornell：有界索引、DSC 编解码与标准 V1 往返

## 能力分层

引擎 ID：`bgi`。全部使用随包纯 Python 3.11+ 标准库；无需 GalTransl、插件、上游 executable 或仓库。

| 阶段 | 接口 | 范围与拒绝条件 |
|---|---|---|
| 包目录 | `archives.bgi.read_index(stream, ...)` | `PackFile    `、`BURIKO ARC20`；只读头/索引，不读 payload，因此不受大视频尺寸影响 |
| 成员探测 | `probe_member(stream, index, entry)` | 最多读 `0x220` 字节，只判断封装/头部线索，不判定对白 |
| 选中成员 | `read_member(..., max_stored_size=...)` | 只读单成员 stored bytes；该行不透明 `extra` 字节另从原 `IndexEntry` 保留 |
| 解码 | `decode_member(entry, max_output_size=..., max_symbols=...)` | raw 或 DSC；有界纯 Python DSC，不支持 BSE、image，不把 DSC 标成剧本 |
| 压缩 | `archives.bgi_dsc.encode(data, seed=..., verify=True)` | `DSC FORMAT 1.00` 写入器；确定性、有界，返回前用同一解码器自检 |
| V1 解析 | `engines.bgi.scan_v1(data, profile=...)` | 核心内联字段 + 通用栈指令布局，自动校验头/代码边界与引用/目标；布局范围外或边界歧义则整体拒绝 |
| 翻译导出 | `export_v1(analysis)` | `rows, locators, name_policies`，按消息/选项事件顺序导出，不是字符串池倾倒 |
| 解码后回填 | `patch_v1(data, replacements, profile=..., ...)` | 按 operand offset 追加改译文并更新已证明指针，返回前重新解析 |
| 重封包 | `archives.bgi_writer.build_archive(members, version=..., verify=True)` / `pack_member(...)` | 重建 `.arc`，只替换已校验译文成员，其余（含每行 `extra`）逐字节复制；不编码 BSE/图像 |

模块：[archives/bgi.py](../python/archives/bgi.py)、[archives/bgi_dsc.py](../python/archives/bgi_dsc.py)、[archives/bgi_writer.py](../python/archives/bgi_writer.py)、[engines/bgi.py](../python/engines/bgi.py)、[engines/bgi_v1_opcodes.py](../python/engines/bgi_v1_opcodes.py)。

**本族没有批量入口。** 按阶段调用上面的函数，循环、输出结构与命名由 agent 按目标游戏的实际情况决定——固定流水线不可能适配每个游戏的包结构与命名习惯。参数与调用示例见本页 [分阶段 API 与示例](#分阶段-api-与示例)，来源链和文件映射见 [交换目录与来源链](#交换目录与来源链)。公共预算与状态约定见 [Python API 指南](../guides/python-reference-api.md)。

## 识别与文件名

- `BurikoCompiledScriptVer1.00\0` 是 28 字节 V1 强证据，但仍须结构校验。无后缀成员也要检查；VN 的 `.bgi` 只是适配入口名称，不是游戏的统一命名规则。
- GARbro 的部分读取路径会在解压失败时回退原始字节；这种返回值不能当作解码成功。本包的有界解码遇错拒绝，不把密文或压缩流交给 V1 parser。
- 容器、压缩封装、编译剧本是三层。`DSC FORMAT 1.00` 不是 zlib，也不能证明解码后是脚本；`raw`/`dsc` 都不等于剧本，解码结果必须重新分类。
- 不按扩展名筛掉全部系统资源。`sysgrp` 可混有无后缀/带后缀成员，`system` 可含 `framework._bs`；不能推断所有 UI 都在 `._bp`。
- 归档索引行在 v2 里名字字段后还有**不透明字节**（`stride 0x80 - name 0x60 - u32×2 = 24` 字节），本包原样保留为 `IndexEntry.extra`。两个参考实现都忽略它们、语义未知；重封包时清零会让输出与原包不再逐字节相同。
- **索引里的名字就是剧本名**（GARbro 显示的也是它）。导出物、报告与译文一律用这个名字，不要引入 `m000004` 这类内部序号：序号对翻译者没有意义，而真名一直在索引里。
- Ver0、无头 V1、BP、BSI 不是本标准 V1 profile。仅找到 CP932 字符串或相似 opcode 不足以复用 writer。

## 标准 V1 的头与代码边界

1. 签名后 u32 `headerSize` 包含自身，`code_base = 28 + headerSize`，不是固定 32。头内 `referencedScripts` 与 labels 按布局读取并校验范围。
2. V1 opcode 与地址操作数按小端 32 位解释；字符串地址相对 `code_base`。`scan_v1` 返回 `Analysis(...)` 含 `code_length`，调用者不必猜测。
3. 默认使用下述 `core-inline-u16-stack-v1` 布局，字符串池起点、指令边界、targets、终止位置与头部 labels 必须交叉一致。追加译文后仍重新确定边界，不能复用缓存长度掩盖错误。
4. 这些是**所选 profile 的结构约束，不是完整 VM 形式证明**。布局范围外的指令、截断操作数、非法目标、代码/池冲突、无法唯一确定边界等都阻挡整个成员；不得仅输出失败前的文本再标成功。

### 通用 V1 指令布局：先区分内联字段与栈参数

实现位于 [bgi_v1_opcodes.py](../python/engines/bgi_v1_opcodes.py)。不要按游戏逐项扩充数百条调用编号的白名单。标准 V1 是栈式指令流：多数调用的参数由前面的指令准备，调用本身没有内联字段；提取对白不必完整模拟音频、图像等调用。

| 指令 | 紧随 opcode 的内联字段（均为 u32） |
|---|---|
| `0000/0002/0008/0009/000A/0017/0019/003F/007E` | 1 个整数 |
| `0001` | 1 个相对代码地址 |
| `0003` | 1 个相对字符串地址 |
| `007B` | 3 个整数 |
| `007F` | 2 个整数（源行记录） |

默认布局保留已知核心指令（`0000..007F`）的宽度，未知核心编号仍拒绝；`0080..FFFF` 按一个 u32 的栈指令处理，编号不需要逐项注册。这是限定在**有头 V1、高 16 位为零**的兼容约定，不是对任意字节流使用空模板。`boundary.opcode_layout` 记录布局，`stack_extension_opcodes` 记录未在旧表中列出的编号；仅有布局规则不能证明调用的返回值或副作用。

旧 `explicit565/explicit568` profile 与白名单冻结保留，供已有 manifest 回写；新提取用默认 profile。不要修改旧 manifest 的 `engine.variant` 来绕过失败。新布局与旧布局都保留跳转落点、字符串引用、候选终点唯一性及预算检查。

遇到失败时先按层定位：`unsupported_opcode` 是未知核心指令或超出布局范围；`boundary_unknown` 是代码/池边界证据冲突；`semantic_unsupported` 是对白参数或旧方言尚未覆盖。后两者不应通过增加零操作数条目处理。检查重复上下文中的参数设置、源行记录、引用与标签；若发现内联字段不同，建立独立方言及测试，不能吞掉后继指令。成功扫描到终点本身不能证明宽度正确。

新方言需验证后继调试字段、跳转落点和文本事件，做原文往返及变长回填。解析为零对白时核对消息指令用途，不把遗漏文本记成 `empty`。若静态检查 EXE，先确认运行时指令集与归档脚本一致，紧凑字节指令表不能直接套到 V1 的 u32 指令流。

## 事件 profile

| profile | 形态 | 语义 |
|---|---|---|
| `engines.bgi.PROFILE`（默认） | `literal-events-v1` | 只有当 name/body 是**可证明的相邻字面量**时才导出；任何未建模的算术/载入/调用会把待定引用窗口标记为不可证明并让该成员整体拒绝 |
| `engines.bgi.PROFILE_VNTEXTPATCH` | `vntextpatch-events-v1` | 复刻 VNTextPatch `EthornellV1Disassembler` 的分组：`0003` 压栈，`0140/0143` 取栈顶为正文、其下为姓名，`001C` 弹出被调用名并在其为 `_SelectEx/_SelectExtend` 时把剩余栈全部当选项，`007E/007F/00FE` 与终止清栈。**不做值/污染跟踪** |

- 后者是**更弱的证据等级**，不是更强的兼容性。选定后要跟着 manifest 走（`engine.variant`），回填用同一 profile 重新校验，否则启发式导出会被当成已证明行写回。
- 两个 profile 都保留 `0x0145/0x014E/0x01B5`（旧消息/ruby/flush 方言）的语义拒绝：它们的宽度已知，事件读写尚未接入，不能静默丢掉相关文本。msg-tool 有对应的反序消息、ruby 和清栈处理；这里不能将其误写为“上游也忽略”。
- `PROFILE_EXPLICIT` / `PROFILE_EXPLICIT_VNTEXTPATCH` 与带 `565` 的常量保留旧布局及对应事件策略。必须从 manifest 读取完整 profile，不能根据常量的当前默认值猜测旧产物策略。

## name / message 与回填身份

- `export_v1` 按事件配对 name + message，选择项按事件顺序保留。旁白省略 `name`；不能把两个独立的 name/message 列表简单 zip。
- 空姓名保持 Internal，不伪造可写姓名槽。内部函数名、资源路径、标签等不交给翻译器。动态姓名/变量不假装已解析成固定人名，不能按上一句猜配。
- `Reference.operand` 是**原文件中的地址操作数字节偏移**；replacements 以 operand 为键，不以原文、池序号或数组下标为键。
- 重复文本与共享池引用各保留自己的 locator；同一原串可按引用得到不同译文。细则见 [交换契约](../guides/roundtrip-contract.md)。

## `patch_v1` 的保真边界

只在完整 `scan_v1` 成功后允许修改。先严格编码，拒绝 NUL、不可表示字符、超限/溢出及未知或 Internal operand。只追加实际改变的译文并更新其已证明指针；旧 pool、header/labels、内部字符串及其余代码不移动、不重建，因此未改字符串的原 bytes 得以保留（CP932 解码再编码不保证一一对应）。

回填前先做**原文往返**：用原文 JSON 同时充当"译文"，真实过一遍 writer 并重新解析，通过后再用译文——直接复制原文件不算往返验证。返回前自动重新解析；调用者仍需验证译文、非文本差异、源哈希与 manifest。

`patch_v1` 默认严格按 CP932 编码；部分中文汉字可直接表示，但不可表示的简体字会触发 `encoding_error`。中文回注优先考虑随包 [JIS 替换](../guides/jis-substitution.md)：由调用层用同一个替换会话校验真实中文，并将 `codec.encode(text).decode("cp932")` 得到的代理文本交给 `patch_v1`；重解析后用 `codec.display()` 核对真实译文。先预留未改显示文本，冲突、缺映射、控制码变化均拒绝。脚本资源名和内部字符串不做替换。

当前叶子 writer 不自动生成 JIS 配置；调用层须在全部校验通过后将 `codec.artifacts()` 与脚本一并放入新结果目录，并告知 hook/字体用法。先核对实际游戏进程位数：仓库的 `winmm.dll` 是 x86，64 位程序应使用兼容构建或匹配映射的替换字体，调用 `artifacts(include_hook=False)` 排除不兼容 DLL。不能仅改 `encoding='utf-8'` 就声称完成转换，因为它也参与原脚本解析；改变注入编码须另行确认加载器和字符串读写规则。

## DSC 与归档写回

- `bgi_dsc.encode` 产生合法的 `DSC FORMAT 1.00` 成员：与解码器共用同一密钥流、同一 MSB 位序、12 位距离字段（因此**距离 1 不可表示**，匹配器跳过它）。贪心 LZSS + Huffman；码深过大时退回 512 项深度 9 的完备码。默认 `verify=True`，返回前用包内解码器还原并比对。
- `bgi_writer.build_archive` 只生成 `read_index` 认得的布局：签名、u32 计数、定长 name/offset/size 行（offset 相对索引末尾）、按调用者顺序存放成员。默认 `verify=True`，会用包内读取器重读一遍再返回。
- 重建已有归档时**只重新 `encode` 被改过的成员**，其余原样透传 stored bytes 与 `entry.extra`。这样恒等重建可以与原 `.arc` **逐字节相同**；只有被替换的成员字节才变化。
- **重封包不等于游戏可运行。** 只保证容器布局、成员字节与 DSC 编解码自洽；加载优先级、无后缀命名、字体、存读档与分支都未验证。

## 部署与加载：BGI 支持免封包

**BGI/Ethornell 支持松散脚本优先**：把翻译后的脚本按引擎期望的名字放进游戏目录，游戏会直接读磁盘上的脚本，不必回到 `.arc`。所以常见终点是解码后的 V1 脚本本身；重封包只在"要与原包布局一致""不想在游戏目录留松散文件"时才用。


仍需使用前确认，**不要凭空填充**：

- **目录与文件名。** 归档成员是无后缀的（`days_01`、`flow`）。候选证据互相不一致：VNTextPatch 用 `*.bgi`，而引擎自身的 `scrctrl._bp` 出现 `%sScript\CVTD\` 这类路径片段——只是线索，不是命名规则。松散文件名猜错会**静默不生效**（游戏照用包内旧脚本），所以不要自动化猜名。
- **优先级与缓存。** 松散文件与 `.arc` 成员的优先顺序，以及 `BGI.gdb`/`BGI.hvl`、`builddata._bp`、`loadwithbuild._bp` 是否覆盖松散脚本，都未验证。
- **部署仍需授权。** 覆盖游戏文件属于写操作；先备份、先在副本上试，不要把"格式自洽"当成"已加载成功"。

## 旧 API 不变

- `archives.bgi.inspect(data)` 仍返回带 stored bytes 的 `Entry` 列表，受旧整包/成员预算约束；`require_plain(entry)` 仍拒绝 DSC/BSE。用它失败不等于目录不可索引；新任务改用显式索引/解码路线，而非放大内存限额读取整包。
- `scan_v1_subset(data, code_length, encoding)` 仍仅接受 `0000/0003/0140/0143/0160/001B/00F4`，要求外部证明的代码长度。
- `patch_v1_pool` 是旧子集的全引用池重建/去重算法，仍要求池完整覆盖；不要与新 `patch_v1` 的追加策略混用。

## 分阶段 API 与示例

[归档模块](../python/archives/bgi.py) 接收 seekable 二进制流。下面的限额均为显式关键字参数，字节数不是字符数。

| 接口 | 返回/约束 |
|---|---|
| `read_index(stream, name_encoding='cp932', max_entries=..., max_index_size=..., max_archive_size=None)` | `ArchiveIndex(version, archive_size, index_end, index_sha256, entries)`；只读头/索引，entries 含 `ordinal/name/offset/size/extra`，不含 payload |
| `probe_member(stream, index, entry)` | `MemberProbe(codec, unpacked_size, header)`；最多读 `0x220` 字节，不解码 |
| `read_member(stream, index, entry, max_stored_size=...)` | `Entry`，含选中成员的 `stored_data`；索引行 `extra` 留在原 `IndexEntry`，须另行保留 |
| `decode_member(entry, max_output_size=..., max_symbols=...)` | raw/DSC 解码 bytes；有界 [bgi_dsc.py](../python/archives/bgi_dsc.py)，不支持 BSE/image，不做剧本分类 |

从 `index.entries` 原对象选择 entry，源流须保持不变。`index_sha256` 只覆盖头和索引，不是 payload/全包摘要。`max_archive_size=None` 允许大包只读目录，但索引条数/字节仍有限额；成员大小与实际解码输出在后续阶段检查。

[剧本模块](../python/engines/bgi.py) 的标准 profile：

| 接口 | 返回/约束 |
|---|---|
| `scan_v1(data, encoding='cp932', ...)` | `Analysis(code_base, code_length, references, events, profile, boundary)`；自动读取标准头/引用脚本/标签并交叉验证边界，不需外传 `code_length` |
| `export_v1(analysis)` | `(rows, locators, name_policies)`；事件级 name/message 配对及选择顺序，空名 Internal，动态变量不假装已解决 |
| `patch_v1(data, replacements, encoding='cp932', max_output_size=...)` | 新 bytes；键为原地址操作数 offset，只追加改变的译文/更新已证明指针，旧池/非文本保留，返回前自动重解析 |

opcode、边界和事件证据以本页的标准 V1 与 profile 章节为准；保存实际返回的 `profile`/`boundary`，回填必须沿用同一 profile。旧子集 API 的限制见 [旧 API 不变](#旧-api-不变)。

### 分阶段示例

每个候选成员的顺序是 `probe → read → decode → scan_v1 → export_v1`；解码后回填用 `patch_v1`；选择 DSC 外壳路线时才继续 `bgi_dsc.encode`，归档重建另用 `bgi_writer`。

```python
from pathlib import Path
from python.archives.bgi import decode_member, probe_member, read_index, read_member
from python.engines.bgi import PROFILE, export_v1, patch_v1, scan_v1


def open_archive(archive_path):
    """Keep the stream seekable and unmodified; only the header/index is read."""
    stream = Path(archive_path).open("rb")
    try:
        index = read_index(stream, name_encoding="cp932", max_entries=100_000,
                           max_index_size=16 << 20, max_archive_size=None)
    except Exception:
        stream.close()
        raise
    return stream, index  # caller closes the stream after processing entries


def extract_one(stream, index, entry, profile=PROFILE):
    if probe_member(stream, index, entry).codec not in ("raw", "dsc"):
        return None                                   # BSE/image: not this route
    stored = read_member(stream, index, entry, max_stored_size=64 << 20)
    raw = decode_member(stored, max_output_size=64 << 20, max_symbols=64 << 20)   # one explicit unwrap
    if not raw.startswith(b"BurikoCompiledScriptVer1.00\0"):
        return None                                   # decoded is not the same as "is a script"
    analysis = scan_v1(raw, encoding="cp932", profile=profile)
    rows, locators, policies = export_v1(analysis)    # raises instead of returning a partial set
    return raw, analysis, rows, locators, policies


def rebuild(raw, proven_replacements, profile=PROFILE):
    # Keys are operand byte offsets from export_v1's locators, never row indexes.
    return patch_v1(raw, proven_replacements, encoding="cp932", profile=profile)
```

### DSC 预算

**`max_symbols` 不要低于 `max_output_size`。** DSC 每个符号至少产出 1 字节，模块内部也已强制 `symbol_count <= output_size`；符号上限更低时它只会先触发，把本可分类的大成员（图片包里很常见）报成"预算超限、没处理"。三个解码入口的默认值已对齐 64 MiB，要调就一起调。

索引、单成员与累计预算同时设置，详见 [公共预算分层](../guides/python-reference-api.md#预算分层)。本例仅演示一个成员，不负责批次累计预算、manifest 校验或安全发布。

## 交换目录与来源链

沿用 [交换契约](../guides/roundtrip-contract.md)，本族的回填基准是**解码后的原始 V1 bytes**，不能把 DSC stored bytes 当作同一源。

```text
gt_input/haru_open_01.json           # 平铺，优先用索引中的真实剧本名
gt_output/                          # 接收同名平铺译文
original/<归档id>/m<ordinal>.bin     # 解码后的原始 V1
metadata/<归档id>/m<ordinal>.json    # manifest，不交给翻译器修改
reports/                            # 每个成员的结论、原因与文件映射
```

- 相同 basename 冲突时才附加归档 id；生成的文件名仍须通过路径/重名校验，必要时继续消歧。记录剧本真名到输出文件名的映射，回填只认映射，不从文件名猜身份。
- 归档 id 与 ordinal 属于该次输入集合；内部存储可以用它们定位，翻译交接与用户报告仍使用剧本真名。
- 保存归档路径、成员 ordinal/name/offset/size/codec、索引指纹与解码基准的关联。`index_sha256` 只覆盖头/索引，不能代替 payload 或原始 V1 的 SHA-256。
- `export_v1` 返回的 locator 使用原始 operand offset。回填前重新解析原始 V1 并核对 locator；不能信任可编辑 sidecar 给出的任意偏移。
- V1 解析完整且 `rows` 为空时记为 `empty`（可能是纯系统/函数脚本），不生成翻译 JSON，也不为它生成逐成员 `original`/`metadata`；在报告中保留来源与解析结论。解析失败不能归为 `empty`。
- 失败成员不发布部分 JSON；批次状态与计数遵循 [成员结论约定](../guides/python-reference-api.md#每个成员的结论怎么记)。BSE 等未实现封装若无法判定内层，应记为 `blocked`，不能仅凭封装把它当作非目标。
- 重跑时明确输入归档目录或指定归档集合，排除所有输出目录，避免把上次提取结果再次当作输入；不要靠删除旧产物解决输入范围问题。

## 分阶段验收

按本页接口逐层记录结果，真实样本与游戏运行证据另列；DSC 与归档写回通过只说明格式自洽。

- **索引与解码**：只读目录不载入全部 payload；核对索引哈希范围、最多 `0x220` 字节的小头探测、stored/decoded/symbol 与累计预算。DSC 解码后重新分类，不按 `sysgrp`、`system` 名称或后缀推断所有 UI 位置。
- **标准 V1**：交叉核对头、标签、引用、代码与 pool 边界，保存实际布局和扩展编号。通用栈布局解决调用编号覆盖；未知核心字段与未支持的文本语义仍需独立适配。
- **导出**：核对姓名/正文事件配对、旁白、选项顺序、Internal/动态姓名限制与 operand 定位。严格 profile 与启发式 profile 分别报告，不能混算证明等级。
- **回填**：原文真实经过 parser/writer；再测变长、多字节、共享串分译、编码失败和输出预算。比较旧 pool、header/labels、Internal 与非文本代码，只有已证明指针与追加译文允许变化；自动重解析不等于运行验证。
- **批次**：每个成员记录阶段、状态、原因与产物。部分成功标为 `partial`，不把 blocked/skipped/non_target 混入成功；本族未提供批量 CLI，调用者若实现 CLI，应以非零退出码表示未完成批次，同时交付完整成功成员。


## 来源与继续研究

- VNTextPatch-net8 `d9c0fab7b72fdcf87d674ef12a84d3829c9188be`，MIT：`EthornellV1Disassembler.cs`、`EthornellScript.cs`，用于指令宽度、消息事件及指针语义。
- msg-tool `f72716cee88554d40c1cdface2812493b14ca653`，GPL-3.0-or-later：`src/scripts/bgi/` 的 archive/parser/script 与 `dsc.rs` 的 `DscDecoder/DscEncoder` 语义；BP、BSI 等注册证据不表示本包已移植。
- GARbro-Mod `bc26d991ef5cdc0e1ecb32122ee9a48c3375750c`，MIT：`ArcFormats/Ethornell/ArcBGI.cs`，归档与 DSC 相关算法。改编归属见源码头及 [NOTICE](../provenance/NOTICE.md)。
- 本包新增的 DSC 写入器、归档写入器与两个 profile 是独立 Python 实现，不是上游逐行转写；模块 docstring 记录各自依据。

未知条目处理：查随包资料与样本结构 → 补齐有依据的算法并保留既有许可通知 → 合成正负例验证 → 在新目录重试。停止不安全发布，但继续有界只读研究。详见 [增补指南](../guides/extending-engines.md)。

## 验证等级与未覆盖项

必须分别记录 index、probe、decode、scan、export、原文回填、变长回填、DSC 重压缩、重封包与加载的证据；索引成员数不等于有效脚本数，出现 JSON 不等于整包成功。人工测试见 [test_bgi_v1.py](../tests/test_bgi_v1.py)，本次运行结果只保存在游戏结果目录。

仍有限制：无头 V1、V0、BP、BSI、BSE/图像编码、BSE 重打包、任意 VM 行为/动态姓名解析、混合编码的自动转换、自动部署 JIS hook/字体，以及**游戏运行验证**。不要为提高成功数而跳过未知 opcode、把预算超限算成已验证，或吞掉解码错误。
