# Hxv4：解密、名称恢复与重封包

Hxv4 在标准 XP3 File 索引之外保存加密名称表；File 中的短 Unicode 名称是内部 ID。处理顺序为：静态取得配置 → 验证索引认证 → 解密正文 → 核验候选名称 → 按内层格式回填。

## 选择入口

| 目标 | 入口 |
|---|---|
| 恢复、核验候选名 | [kirikiri_hxv4_names.py](../../python/archives/kirikiri_hxv4_names.py) |
| 解密资源、回填已重建的资源字节 | [kirikiri_hxv4_archive.py](../../python/archives/kirikiri_hxv4_archive.py) |
| 自动从 PSB/TJS 静态结构收集候选名 | [kirikiri_hxv4_recover.py](../../python/engines/kirikiri_hxv4_recover.py) |
| 提取与回写已支持的 PSB SCN 对白 | [kirikiri_hxv4_text.py](../../python/engines/kirikiri_hxv4_text.py) |

仅需 Python 标准库，不执行游戏 EXE、DLL 或 TJS。普通 `kirikiri_extract` 没有 Hx 密钥上下文，不能代替专用入口。

## 配置与名称核验

- 静态读取 EXE 的 `TEXT/127`、`STARTUP.TJS`、`BOOTSTRAP`，定位 BRES salt，解密资源并提取 TJS 常量配置。只有通过最终 Hx 索引认证的配置才可采用。
- 静态 PE 解析按可选头格式处理 PE32 与 PE32+（`ImageBase` 宽度、数据目录位置、资源目录三层结构）。salt 扫描中的 `mov dword ptr [imm32],…` 形式只能编码 32 位地址，因此只对 PE32 生效；PE32+ 样本改用 `V2Link`/`forcedataxp3` 布局锚点，锚点未命中时不产出候选。未知壳、变形资源和非字面组合参数仍可能无法处理，应报告失败位置。
- 名称恢复依赖候选，不是逆哈希。候选可来自已解密资源引用、人工清单或可读补丁索引；必须重新计算文件名和目录哈希，未匹配者保持未解析。
- 文件名与目录名使用不同哈希：文件名用 BLAKE2s-256，目录用 SipHash24，输入均为小写 UTF-16LE 加同一域/盐；目录末尾 `/` 参与哈希，根目录为空串。不能恢复原始大小写，也不能将这一规则套到不同盐、不同域或不同算法的变体。
- 哈希域/额外字符串不一定是 `xp3hnp`：启动脚本把 media name 传给 `CompoundStorageMedia`（常形如 `bootstrapPrefix.split(":")[0]`，否则回退默认 `"xp3hnp"`，也可能为空）。路径和文件名使用同一个域，输入是 `UTF-16LE(name) + UTF-16LE(domain)`，没有分隔符。换样本时先从 `STARTUP.TJS` 确认，不要硬编码。
- `System.bootStrap` 返回的 octet 在部分样本中只被复制、`key_len` 仍为 0，实际是**无 key** 的 SipHash/BLAKE2s；不能仅凭接口有 key 参数就按 keyed hash 计算，先核对实现或已知向量。
- 正文在 segment 解压后按成员逻辑偏移过滤，明文 Adler-32 必须匹配。名称验证与正文校验分别记录。

## 已支持 SCN：提取与回写

```text
python -m python.engines.kirikiri_hxv4_text extract "游戏/scn.xp3" "新的提取目录" --exe "游戏/启动程序.exe"
python -m python.engines.kirikiri_hxv4_text pack "提取目录" "新的打包目录"
```

默认目录候选为根目录、`scn/`、`scenario/`；其他目录用 `--paths` 明确提供。`--language-index` 选择已有语言槽。当前文本入口只处理直接 PSB 的已知 SCN 方言，不自动把 MDF、TJS 或图像 PSB 当作对白。

姓名回注默认开启：显式显示名为 null 时允许改写字符串说话者 `who`。内部 ID 方言或需要保持共享说话者不变的多语言脚本使用 `--no-speaker-name`；旧目录沿用提取时的策略，启用新默认需重新提取。详细规则见[姓名策略](../kirikiri.md#说话者字段作为显示名默认开启)。

正文定位与回写沿用[统一 SCN 入口](../kirikiri.md#文本定位与回写规则)：已知方言按严格规则回写，未知形状自动退回类型化前缀定位，未验证的派生字段与不可写行在报告中单列。Hx 静态密钥、认证、名称核验和预算检查照常执行。

单资源上限 32 MiB，超限成员在解密前跳过；累计实际读取/解密资源超过 384 MiB 时停止。**大文件不一定是媒体**：有超限、未映射成员或无法解析的 PSB 时，`scan_complete=false`，必须交代未检查范围，不能声称全剧情提取完整。诊断和预算在 `reports/hxv4.json`，回填报告沿用 `source_scan_complete`。

| 结果位置 | 用途 |
|---|---|
| `gt_input / gt_output` | 平铺原文 JSON / 同名译文 |
| `original / metadata` | SCN 基准、定位、控制码与回填契约 |
| `reports/extraction.json` | 共享 SCN 流程的来源与统计 |
| `reports/hxv4.json` | 原始 EXE/归档哈希、Hx 身份、诊断与封包验证 |
| `rebuilt/roundtrip`、`smoke-test` | 明文中间测试包 |
| `rebuilt/hx-roundtrip`、`hx-smoke-test` | 保留身份的 Hx 加密测试包 |

smoke-test 带测试前缀，不是正式译文。正式 `pack` 需原始档案仍可读取；它校验源档案、成员身份、原文和 manifest，再复用共享 SCN writer，生成 Hx `scenario.xp3`。该包仅含脚本，不能替换完整 `data.xp3`。

## 资源级处理与候选名称

```text
python -m python.engines.kirikiri_hxv4_names "游戏/scn.xp3" --exe "游戏/启动程序.exe" --names "候选文件名.txt" --output "新的名称目录"
python -m python.engines.kirikiri_hxv4_names "游戏/scn.xp3" --exe "游戏/启动程序.exe" --candidate-archive "游戏/已有补丁.xp3" --output "另一个名称目录"
python -m python.engines.kirikiri_hxv4_candidates "游戏/data.xp3" --exe "游戏/启动程序.exe" --output "新的候选目录"
python -m python.archives.kirikiri_hxv4_names "游戏/scn.xp3" --exe "游戏/启动程序.exe" --names "候选目录/candidates.txt" --output "新的名称目录"
python -m python.engines.kirikiri_hxv4_recover "游戏/scn.xp3" --exe "游戏/启动程序.exe" --output "新的资源目录"
python -m python.archives.kirikiri_hxv4_archive "游戏/scn.xp3" --exe "游戏/启动程序.exe" --names-report "名称目录/report.json" --output "新的解密目录"
python -m python.archives.kirikiri_hxv4_archive "游戏/scn.xp3" --exe "游戏/启动程序.exe" --replacements "已重建资源目录" --output "新的封包目录"
```

- `--names` 接受 UTF-8 或带 BOM 的 UTF-16，一行一个候选名；`--candidate-archive` 只从标准/eliF 索引收集名称，不采用补丁正文。参数可重复，目录候选用 `--paths`。
- `--domain` 指定哈希域/media name，默认 `xp3hnp`；换样本时从 `STARTUP.TJS` 的 `CompoundStorageMedia` 读取，实际可能为空或其它字符串。路径和文件名必须使用同一个域。
- `kirikiri_hxv4_candidates` 只读小成员（默认单成员 8 MiB、累计 384 MiB），从 PSB/TJS 常量、SimpleCrypt 文本表（场景列表、差分映射）、普通表 token 和 `psb://` 引用中收集候选，输出 `candidates.txt` 与 `report.json`。候选只对源包核验；跨包使用时仍由目标包的名称哈希决定是否命中。
- 候选扫描报告中的 `scan_complete=false`、`skipped_oversize_members`、`skipped_unmapped_members` 必须如实保留；跨包合并 `candidates.txt` 后再对目标包跑 `kirikiri_hxv4_names`。目录默认预注册常见 Kirikiri 目录，也可用 `--paths` 覆盖。
- 多个源包分别扫描后合并去重即可；候选文件只是名字列表，跨包使用时仍由目标包的 `(path_hash, file_hash)` 决定是否命中。
- 名称输出含 `report.json` 和 `HxNames.lst`，只记录哈希匹配的名称；名称报告必须对应同一源档案，已有映射仍重新核验。
- 自动候选收集支持严格解析的 PSB v2/v3（含有界 MDF/zlib 外壳）和 TJS2100 常量，尝试原名及 `.ks.scn/.txt.scn` 形式；失败单独报告。
- TJS 常量也可能引用 CSV/数据表；完整候选流程见下文[从 TJS 与数据表扩展候选](#从-tjs-与数据表扩展候选)。
- 真名资源保存在 `original/resources/`；未解析名称保存在 `original/unresolved/<目录哈希>/<文件哈希>.bin`。身份与阶段状态见 `metadata/report.json`，新加密包在 `repacked/`。这些输出不是对白 JSON。
- `--replacements` 按报告 `file` 的相对路径配对，例如 `resources/main.ks.scn`。资源必须已完成语义重建及 MDF 等外壳恢复；未提供成员保留原文，未匹配文件或目录逃逸拒绝。
- 资源 writer 保留成员全集及 ID/key/名称哈希，不新增身份；生成后重读索引并逐成员核对明文。预算为单资源 32 MiB、累计 384 MiB。

### 从 TJS 与数据表扩展候选

名称哈希只认最终 basename，候选可以来自包内脚本常量及它们引用的数据表。通用顺序是先收集“能产生其他名字”的成员，再收集纯资源；当前内置入口只覆盖 TJS/PSB，其余阶段需要按格式补解析器后接入：

1. EXE 内嵌 `STARTUP.TJS` 的字符串池；启动脚本常引用随后要挂载的脚本或表。
2. `data.xp3` 内 TJS 字符串池（含未被指令引用的常量）。先跑 `kirikiri_tjs_decompile --mode strings`；它只列被引用的常量，需要更全的池时按对象读取或结合反汇编。
3. SCN：先按已知名尝试 `!scnlist.txt`（根目录、`scenario/`、`scn/`），逐行取首个 tab 字段并去掉 `/`、`\`、`>` 前缀；由场景名生成 `.scn`、`.txt.scn` 以及 `scn/`、`scenario/` 变体。场景列表不可用时再扫描 SCN PSB 常量池。
4. 纯文本成员：引号内字符串和文件形态的 token；CSV/INI 等表既提供自身名称，也可能列出资源名。
5. PBD 图层：`pbd_stem + "_" + layer_id + ".tlg"`；`layer_id` 本身是文件名时直接采用。
6. TLGref/TLGqoi 等容器内嵌的引用字符串。
7. 最后导出剩余成员；未解析目录/文件名用大写十六进制占位，并与已还原成员分开统计。

TJS 常量引用 `.csv`、`.dat`、`.tjs` 等表名时，按名定位并解开其外层（SimpleCrypt `fe fe <mode> ff fe`、MDF/zlib 或明文），再按实际文本编码读表。表中的名字通常是逻辑名，不等于最终 basename：显示前缀可能不在存储名里，一条记录也可能对应正文、缩略图、变体或包描述文件等多个成员，并可能同时存在 `.dref`、`.tlg`、`.png` 等扩展名。逐条生成变体后重新计算名称哈希，不能把表名直接当文件名。

提示清洗与变体：

- 去引号、括号和首尾标点，`\` 转 `/`，`|` 后为效果名时只取前段，`#`/`@` 标签截断；拒绝纯数字、空白/控制字符、`?<>` 和超长 token。
- 目录提示以 `/` 结尾；文件提示取叶名并小写。无扩展名且像资源 stem 时，按常见扩展名表生成变体；带路径的提示同时注册目录和文件。
- 扩展名补全可能发生在 TJS/KAG/资源管理器层，而不是存储层：`bgm01` 可能实际存为 `bgm01.opus`，音频循环旁路还可能追加 `.sli`（`bgm01.opus.sli`）。裸逻辑名要按运行时扩展名生成变体；只有确认是存储层特例的 `.sli` 才单独追加。
- CG 列表单元格可能带 `?解锁标记`、`|组合`、`*基础项`、`<x:y:pos>` 等语法；另有差分映射表把逻辑 tag 映射到基础文件 + diff tag。先拆分和映射，再把基础文件与 diff 组合当候选，不能把整个单元格当文件名。
- 提取后保存每条成员的 `(pathname_hash, filename_hash, archive, output)` 清单；按哈希查清单可以避免跨包同名歧义，也便于核对候选是否真的命中。
- 预注册常用目录（根、`data/`、`system/`、`scenario/`、`scn/`、`image/`、`evimage/`、`fgimage/`、`bgimage/`、`thum/`、`sound/`、`bgm/`、`voice/`、`video/`、`font/`、`plugin/`、`k2compat/`、`main/` 等），未知目录保留哈希。
- `path_hash` 只决定目录；目录未知时仍可先核验 basename。目录候选用 `--paths` 传入并保留尾部 `/`，它参与哈希，不要先规范化掉。
- 匹配以 `(path_hash, file_hash)` 为单位；同一组合命中多个成员时跳过，不按顺序猜。哈希匹配只证明候选等于存储名，未知部分不能用路径哈希代替文件名。
- 候选注册要确定、去重；同一哈希重复出现时保留一个，避免不同扫描顺序导致输出抖动。

适用边界：

- 当前候选扫描已覆盖 PSB/TJS 常量、SimpleCrypt 文本表/场景列表/差分映射、普通文本 token、`psb://` 引用、常见扩展名和默认目录；EXE 内嵌 `STARTUP.TJS` 独立扫描、PBD 图层和 TLGref/TLGqoi 二进制解析尚未接入，遇到这些来源需要按格式补解析器。
- 只读取小体积脚本和表成员，避免为了找名字解密整包媒体；单成员 32 MiB、累计 384 MiB 的预算仍适用。
- 表里没有的名字（纯图像、视频、Live2D 资源等）不会因为 TJS 反编译而出现；`names_resolved < index_entries` 时必须如实报告未解析范围。
- TJS 反编译被拒绝不代表 `strings` 不可用；保留反汇编和常量清单，不要为了凑名字猜文件名。
- 外部补丁索引或他人整理清单是独立来源，不能当作原包证据；混用时必须单独标注来源与阶段。

## Hxv4 扁平 patch.xp3

**补丁内所有成员一律平铺存放在根目录（`path_hash("")`），只使用 basename 加完整扩展名。脚本、字体、配置、图片、音频等一切资源都没有例外，也不以该资源在原包中的目录为转移**：原来在 `font/` 下的字体、在 `scenario/` 下的剧本，进补丁后同样是根目录下的 basename 成员。原目录哈希只描述它在原包里的位置；补丁是独立归档，把原目录哈希带进来会让成员落空。

这是最容易出错的一条，落地时要逐成员核对，而不是按资源类型分别处理：

| 资源在原包中的位置 | 补丁成员名的写法 | 常见错误 |
|---|---|---|
| 包根目录（如剧本包里的 `*.txt.scn`） | `foo.txt.scn` | 无 |
| 子目录（如 `font/…`、`scenario/…`、`data/…`） | 同样只用 basename：`font.otf`、`history.ks` | 按原结构放进 `font/`、`scenario/`，实际覆盖不到 |

通用挂载与变化筛选见 [补丁工作流](workflow.md#译文回注优先使用-patchxp3-增量补丁)。Hxv4 还需核对 EXE 是否通过 `CompoundStorageMedia` 接管存储，追踪 `parseArchiveIndex/mount/entryDomain/pathHash/assignFiles` 的引用与失败分支；可用 [TJS 静态检查器](../../python/engines/kirikiri_tjs_inspect.py) 和 [TJS 反编译阅读](tjs.md)。

1. 校验译文并重建脚本，只选择相对原文实际变化的资源。
2. 使用经哈希核验的原 basename 和完整扩展名，拒绝同名冲突；JSON 文件名与内部 ID 不能代替真实资源名。
3. 调用 [build_flat_patch](../../python/archives/kirikiri_hxv4_payload.py)，保留成员 ID、key 与文件名哈希。该函数强制 basename 输入（名字含 `/` 或 `\` 直接拒绝），并在写入时把每个成员的目录哈希统一改成 `path_hash("")`；不要绕过它手工改 `path_hash`。
4. 生成加密正文、名称表和有效 Poly1305 标签，在新目录保存 `patch.xp3`。
5. 重读索引认证，**确认全部成员的 `path_hash` 都等于 `path_hash("")`**，再核对身份、明文、译文及非文本结构，最后测试实际加载。

“扁平”指 **Hx 名称表映射到根目录**；标准 File 索引仍保留内部 ID。不能仅改文件名、保留原 `scn/`（或 `font/`、`scenario/`）哈希，或改成普通明文 XP3。只有“整体替换整个原包”的做法才保留原包目录结构，那是另一种产物，不是本节的增量补丁。

### 确认挂载目录、文件名与优先级

补丁的文件名、放置目录和编号规则由作品自己的启动脚本决定，不能照搬示例或套用其它作品的编号。静态确认顺序：

1. **EXE 内嵌启动脚本**：`TEXT/127` 给出 BRES 根，`STARTUP.TJS` 与 `BOOTSTRAP` 解密后取 TJS 常量（`kirikiri_hxv4_static` 的 `PE` / `bres` / `tjs_strings`）。这一步通常只看到默认路径与 `addAutoPath` 的调用形式，很少直接列出游戏自己的包名。
2. **入口包内的加载脚本**：由默认路径找到入口归档，按常量/正则定位其加载逻辑，读出实际使用的文件名模式、扫描目录、排序方式与覆盖顺序。
3. `--candidate-archive` / 名称恢复只给出可能的资源名，不能代替上面两步。

记录时至少覆盖：

| 需要确认 | 常见形态（举例，非固定约定） |
|---|---|
| 文件名与编号 | 固定名，或按编号排序取用；同名补丁不能并存时编号决定谁生效 |
| 扫描目录 | 程序目录，或脚本里显式拼出的路径；必须读到拼接用的变量来源 |
| 覆盖顺序 | 后挂载者优先，或显式比较版本号/编号 |
| 门槛与中断 | 存在“当前版本”文件时可能只加载高于它的补丁；也存在遇到缺号即停止探测的循环 |

只有全部确认后才决定补丁文件名与放置位置；部署后完全退出再启动，从修改过的段落验证。

### 非脚本资源一并进补丁

字体、配置、图片、音频等非脚本资源的路径处理与脚本**完全相同**：平铺到根目录、只用 basename，**不继承原包的目录哈希**（字体不要写回 `font/`，剧本不要写回 `scenario/`）。按资源类型区别对待是错的。

- 只需核验两件事：basename 与完整扩展名通过名称哈希校验（`name_hash(name) == entry['name_hash']`），以及正文确实是要替换的那个资源。
- 目录哈希**不要**从原 entry 继承。`build_flat_patch` 会拒绝带目录分隔符的名字，并把目录哈希统一改为 `path_hash("")`。
- 打包后逐个重读，确认每个成员的 `path_hash` 均为 `path_hash("")` 且明文与输入一致。

`changed_members` 是 `(original_entry, rebuilt_resource_bytes, verified_basename)` 列表；`key_package` 必须来自已验证配置：

```python
from pathlib import Path
from python.archives.kirikiri_hxv4 import derive
from python.archives.kirikiri_hxv4_payload import build_flat_patch
from python.common.safety import write_new_tree

keys = derive(key_package)
patch = build_flat_patch(changed_members, keys, hx_flags=original_hx_flags)
write_new_tree(Path(new_output_directory), [("patch.xp3", patch)])
```

`kirikiri_hxv4_text pack` 当前保留完整脚本集合及原目录，**不是变化成员的根目录补丁命令**；还需额外筛选并调用上述 API，没有独立扁平补丁 CLI。部署后完全退出再启动，从修改段落检查，避免缓存或旧存档误导判断。

### 认证与外部签名

Hx 索引前 16 字节是 ChaCha20-Poly1305 认证标签，不是保留区；随包 reader 强制验证，writer 同步生成。错误密钥、标签或密文均拒绝。

外部 `.sig` 与 Hx 标签无关；遇到 RSA-PSS/SHA-256 数字签名时，生成新签名需要对应私钥，不能复制旧签名冒充有效。补丁不生效先检查挂载、路径和 Hx 认证，再确定是否存在外部验签要求。
