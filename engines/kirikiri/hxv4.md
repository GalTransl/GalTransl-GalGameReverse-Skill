# Hxv4：静态解密、名称恢复与重封包

名称证据入口：[kirikiri_hxv4_names.py](../../python/archives/kirikiri_hxv4_names.py)（旧 engines 命令保留兼容入口）。归档入口：[kirikiri_hxv4_archive.py](../../python/archives/kirikiri_hxv4_archive.py)。后者已实现纯静态正文解密、候选名核验及保留原始身份的加密重封包；这是资源归档阶段，归档命令不生成对白 JSON；已知 PSB SCN 使用下述独立文本流程。

## 为什么不一定需要动态调试

标准 `File` 记录的短 Unicode 名称是内部 ID。`Hxv4` 扩展指向另一份加密索引，包含目录哈希、文件名哈希、成员 ID 与成员密钥。两层必须分开：

1. 从 EXE 的 `TEXT/127`、`STARTUP.TJS`、`BOOTSTRAP` 资源提取配置候选。
2. 静态定位 BRES salt，ChaCha8 解密资源，解析 TJS 常量表；不执行 TJS 指令。配置候选来自常量，必须由后续加密索引校验确认，不能因为字符串含 Copyright 就认定正确。
3. 解析 BOOTSTRAP 内的 PARAMS、WARNING、UNIQUE 和 upperKey；用 Argon2i、SHA3、BLAKE2s、HChaCha20 派生索引参数。
4. 先验证 Hx 索引前 16 字节的 Poly1305 认证标签，再 ChaCha20 解密，通过有界 zlib 解压及对象结构校验，将哈希记录与原始 File ID 对齐。
5. 对候选名称重新计算哈希；仅精确匹配者进入结果。文件名使用 BLAKE2s，目录使用零密钥 SipHash-2-4，已验证盐为 `xp3hnp`，输入为小写字符串加盐的 UTF-16LE。大小写信息无法从哈希独立恢复。

这不是任意哈希的逆运算。候选可来自已经解密的 SCN/TJS 资源引用、目录文件名、人工清单、已有工具日志或补丁索引；这些只提供候选，不是可信映射。找不到候选时保持未解析，不能用猜名填满成功统计。其他盐或派生变体需要独立证据，不能由“同是 Hxv4”推断通用。

当前 PE 解析范围为 PE32、明确的资源层次；salt 使用代码赋值、V2Link、forcedataxp3 周边候选，逐项验证 BRES/TJS 和最终索引。未知壳、PE64、变形资源、非字面组合的 bootstrap 参数可能无法提取；应报告失败层，不加载未知 DLL 回避解析。

## 使用

运行只需要 Python 标准库。固定参数的 Argon2i（v1.3、p=1、m=8 KiB、t=3、64 字节输出）、ChaCha、哈希与结构解析均在项目内实现。不依赖 argon2-cffi，也不调用参考项目的二进制文件。

```text
python -m python.engines.kirikiri_hxv4_names "游戏/scn.xp3" --exe "游戏/原版.exe" --names "候选文件名.txt" --output "新的名称证据目录"
python -m python.engines.kirikiri_hxv4_names "游戏/scn.xp3" --exe "游戏/原版.exe" --candidate-archive "游戏/已有补丁.xp3" --output "另一个新的名称证据目录"
```

`--names` 支持带 BOM 的 UTF-16 或 UTF-8，一行一个候选文件名；`--candidate-archive` 仅从可读的标准/eliF 索引收集候选文件名，不读取或采用补丁正文。参数可重复。目录候选用 `--paths` 指定，默认核对根目录空字符串。

输出目录必须不存在，包含 `report.json` 和 `HxNames.lst`。报告保留源 EXE/归档 SHA-256、候选来源、配置、原成员 ID/哈希、匹配数及未匹配项；不移动、改名、覆盖任何原文件。`HxNames.lst` 只写经过重新计算验证的 `HASH:name`。当前接口一次处理一个归档，不把多个版本的名称表不加区分地混用。

## 参考项目的准确作用

- `hxv4_unhash_tools`：先假定资源已经解包/解密，再从多种资源收集候选名并计算哈希，最后恢复名称。它的 Python 包装依赖哈希 DLL，并不自行解决正文解密。本次只参考流程，未复制无明确许可的实现或运行其 DLL。
- `KrkrExtractForCxdecV2Extra/CxdecKeyStatic`：PE/BRES/配置提取部分与本路线相符；但 `FilterManager.cpp` 会把 BOOTSTRAP 写入临时 DLL，经 `LoadLibraryW` 后调用构造器、BootstrapDerive、ArchiveDerive 等原生函数。“无需启动游戏/Frida”并非“完全不执行游戏代码”。本次仅只读对照该 AGPL 项目，未复制代码或执行此路径。
- 本项目派生算法依据 msg-tool 的 GPL-3.0-or-later 实现，并用其公开测试向量核对；Hx 索引布局同时参考 GARbro-Mod 的 MIT 实现。具体提交与使用范围见 [算法出处](../../provenance/kirikiri-sources.json)。

回归覆盖 ChaCha/HChaCha、SipHash、文件名哈希、上游密钥派生向量、合成加密索引、错误密钥、截断输入和未匹配候选。`test_kirikiri_hxv4.py` 包含标准库 Argon2i 派生与上游固定向量的一致性测试，不需要外部依赖或跳过测试。

普通 `kirikiri_extract` 仍拒绝 Hxv4：普通入口未接入 Hx 密钥上下文，需使用 `kirikiri_hxv4_text`；不能把名称表套上 Akabei 或 Senren writer。MDF/PSB 能解析不代表所有 SCN 语义方言均能安全回填。

## Cxdec_Tools 带来的可用实现

参考 `Cxdec_Tools` 提交 `c25804340610bdfb9e971e3b6bd23b8abd52797a`（MIT，通知随包保留于 [kirikiri-cxdec-tools-MIT.txt](../../provenance/kirikiri-cxdec-tools-MIT.txt)）。其 `hxv4_shellcode.rs` 名称虽含 shellcode，实际构建有限 Cx 运算并用解释器求值，没有调用游戏机器码。`hxv4_compute.rs` 给出成员 key、16 字节 header、split position 与两个 span 的对称 XOR 规则。名称恢复则仍是从已解密 SCN/TJS/资源引用获取候选后比对哈希，不是无条件逆哈希。

本次将这些算法接入 [kirikiri_hxv4_payload.py](../../python/archives/kirikiri_hxv4_payload.py)，复用现有 Cx 表达式解释器，不按游戏写专用脚本。派生过程增加 SHAKE256 控制表、PARAMS 分支排列与 Hx 随机数；id 的 bit32 决定是否混入全局 filter key。过滤发生在 XP3 segment 解压之后，位置是整个资源的逻辑偏移。解密后的 Adler32 必须与原索引一致。

```text
python -m python.engines.kirikiri_hxv4_recover "游戏/scn.xp3" --exe "游戏/原版.exe" --output "游戏/游戏名_extract"
python -m python.archives.kirikiri_hxv4_archive "游戏/scn.xp3" --exe "游戏/原版.exe" --names-report "名称证据/report.json" --output "游戏/游戏名_extract_2"
python -m python.archives.kirikiri_hxv4_archive "游戏/scn.xp3" --exe "游戏/原版.exe" --replacements "已重建资源目录" --output "游戏/游戏名_extract_3"
```

分层：`archives/kirikiri_hxv4_archive.py` 仅处理归档，不导入脚本层；`engines/kirikiri_hxv4_recover.py` 负责自动解析 PSB/TJS 候选并调用归档接口。不需要脚本扫描时，直接用 archives 命令；需要已有名称时传 `--names-report`。

每次输出必须是不存在的新目录。`original/resources/` 保存经过哈希核验真名的原始资源；缺少文件名或目录名时，保留在 `original/unresolved/<目录哈希>/<文件哈希>.bin`。`metadata/report.json` 记录身份、源/重建哈希和各阶段验证状态。`repacked/` 保存新加密归档，生成后重新解析索引并逐成员比较明文和 ID/key/名称哈希。没有 `gt_input`，这批资源不能直接当作 GalTransl 对白 JSON。

自动候选只读取严格解析的 PSB v2/v3（含有界 MDF/zlib 外壳）和 TJS2100 常量，尝试原名以及 `.ks.scn` / `.txt.scn` 形式。不会执行脚本，解析失败单独记录，不影响已通过校验和的原始资源保存。可额外提供同一源档案的名称证据报告；报告中的名字仍重新计算哈希，不信任已有映射。

`--replacements` 用报告中 `file` 的相对路径配对，例如 `resources/main.ks.scn`。传入文件必须已经完成其内部格式的合法重建，包括 MDF 外壳；该接口只负责资源字节的加密封包，不承担对白语义、跳转或 PSB 长度修复。不存在的目录、未匹配文件和逃出目录的链接会拒绝；未提供的成员保持原文。writer 保留原始 ID、成员 key、名称/目录哈希，拒绝未映射成员或重复身份，不生成新的成员身份；CLI 保留源档案成员全集。

预算：单资源 32 MiB、累计资源 384 MiB；大媒体档案需另行设计流式处理，不能关闭限制硬跑。PRNG 新旧分支及控制表 XOR 标志的边界见随包测试。

## Hxv4 PSB SCN 对白结果目录

[通用文本流程](../../python/engines/kirikiri_hxv4_text.py) 的 `extract` 静态检查指定归档，核验明文 Adler32，从可解析 PSB 的 `name` 字段产生候选，并对文件名、目录分别重新计算哈希。默认目录候选为根目录、`scn/`、`scenario/`；末尾 `/` 是哈希输入的一部分。新目录用 `--paths` 提供准确候选，未知哈希不猜配。当前文本流程仅接受直接 PSB 的已知 SCN 方言，不自动把 MDF/TJS/图像 PSB 当作对白。

成员按单资源预算筛选：默认超过 32 MiB 的成员**在解密前跳过**，累计预算只统计实际读取/解密的成员字节，默认超过 384 MiB 仍然硬停止。单个大成员因此不会阻断预算内的 SCN，但**大小不能证明它是媒体，跳过后也无法确认其中是否含剧情**。

`reports/hxv4.json` 的 `diagnostics` 记录超限成员的 ID、大小、名称/目录哈希和原因，另提供 `skipped_oversize_members`、`skipped_oversize_bytes` 与 `scan_limits`。有超限、未映射成员或无法解析的 PSB 时，`scan_complete=false`；CLI 会显示此状态和诊断数量，pack 报告沿用 `source_scan_complete`。此时仅交付已确认脚本，必须提醒用户未检查范围，不能声称全剧情提取完整。即便没有诊断，当前流程的范围仍只是直接 PSB SCN，不代表覆盖其它脚本格式。后续需靠有界格式识别或单独适配缩小缺口，不能将预算阈值当作文件类型规则。

```text
python -m python.engines.kirikiri_hxv4_text extract "游戏/data.xp3" "游戏/游戏名_extract" --exe "游戏/启动程序.exe"
python -m python.engines.kirikiri_hxv4_text pack "游戏/游戏名_extract" "游戏/游戏名_extract/packed_1"
```

生成的 `gt_input` 是平铺的 GalTransl JSON，译文放回同名 `gt_output`。原文、定位、控制码及译文校验复用 `kirikiri_extract`，没有另一套按游戏名分派的语义 writer。内部用真实生成的明文脚本 XP3 对接共享流程，其来源在 `reports/extraction.json`；原版 EXE/档案哈希、原始 Hx ID/key/名称哈希、诊断与最终封包验证在 `reports/hxv4.json`，两个阶段不能混为一谈。

`rebuilt/roundtrip` 和 `rebuilt/smoke-test` 是明确保留的明文中间测试包；`rebuilt/hx-roundtrip` 和 `rebuilt/hx-smoke-test` 才是保留原身份的 Hx 加密测试包。smoke-test 的每条正文带测试前缀，不能当成实际译文补丁。实际翻译后执行本节 `pack`，它先核验原版归档和成员身份、原始脚本、manifest/JSON，再调用共享语义 writer 并生成最终 Hx `scenario.xp3`。原始游戏档案需仍可读取。未处理资源留在原游戏中，脚本专用包不能直接替换整个 data.xp3；本工具不签名或部署，不保证加载顺序。

## Hxv4 扁平 patch.xp3

### 先确认真实加载链路

KAG 层发现 `patch.xp3` 或 `addAutoPath` 只能说明存在补丁入口，还要检查 EXE 的启动资源是否接管存储系统：

- 检查 `useArchiveIfExists` 的调用、搜索路径、根目录挂载方式和编号补丁的循环终止条件。
- 若使用 `CompoundStorageMedia`，继续追踪 `parseArchiveIndex`、`mount`、`entryDomain`、`pathHash` / `assignFiles`，确认 Hx 索引如何加入搜索域及挂载失败分支。

使用 [kirikiri_tjs_inspect.py](../../python/engines/kirikiri_tjs_inspect.py) 静态检查常量、对象、指令和跳转边界；不执行 TJS 或加载游戏 DLL。

### 正确的补丁构建流程

1. 按原始 manifest 校验 `gt_output`，用对应 SCN writer 重建 PSB；保留控制码、长度/缓存和非文本结构。只选择相对原始资源真正改变的成员，不把整个 data.xp3 或未改动剧情塞进补丁。
2. 每个成员使用经过哈希核验的原始 basename，保留完整扩展名，例如 `00_01_アバンタイトル.txt.scn`。拒绝同名冲突，不用 JSON 文件名或内部 ID 猜资源名。
3. 调用 [kirikiri_hxv4_payload.build_flat_patch](../../python/archives/kirikiri_hxv4_payload.py)。保留原成员 ID、key、文件名哈希；将目录哈希改为根目录 `path_hash("")`，当前 `xp3hnp` 盐下为 `94D4A97C61498621`。不要保留原 `scn/` 的目录哈希 `0FD3480DDD67B91E`。
4. 生成 Hxv4 加密正文及加密名称表，必须生成有效 Poly1305 标签。保存为新结果目录中的 `patch.xp3`。
5. 用严格 reader 重新验证索引认证、根目录哈希、ID/key/文件名哈希以及明文逐字节一致；再解析 PSB，确认文本等于译文，非文本结构不变。工具验证与实机验证分别记录。

这里“扁平”指 **Hx 名称表映射到根目录**。标准 File 索引里的短 Unicode 名称仍是内部 ID，不应改写成可读 basename。不能把带 `scn/` 哈希的 `scenario.xp3` 简单改名为 `patch.xp3`，也不能改成无 Hx 名称表的普通明文 XP3。

接口示例；`key_package` 来自已验证的静态配置，`changed_members` 是已完成语义回填的 `(original_entry, rebuilt_resource_bytes, verified_basename)` 列表：

```python
from pathlib import Path
from python.archives.kirikiri_hxv4 import derive
from python.archives.kirikiri_hxv4_payload import build_flat_patch
from python.common.safety import write_new_tree

keys = derive(key_package)
patch = build_flat_patch(changed_members, keys, hx_flags=original_hx_flags)
write_new_tree(Path(new_output_directory), [("patch.xp3", patch)])
```

`kirikiri_hxv4_text pack` 当前输出的是保留原身份/目录的完整脚本集合，**不是上述 changed-only 根目录补丁命令**。制作 `patch.xp3` 时必须额外筛选变化成员并调用 `build_flat_patch`；当前没有独立的扁平补丁 CLI，不要虚构参数。`gt_input` 是原文基准，正常只编辑 `gt_output`。若用户误改了原文 JSON，先核验原始 SCN 与原档案一致，再在临时副本重建基准，不覆盖用户文件或关闭契约检查。

测试时完全退出游戏，把最终 `patch.xp3` 放到启动程序同目录，从新游戏进入已修改段落，避免旧存档或已缓存脚本造成误判。部署须在用户授权范围内；结果目录中的脚本补丁不能替换整个 `data.xp3`。

### Poly1305 认证标签与外部 .sig 的区别

Hx 索引前 16 字节是认证标签，不是保留区。Hx 使用 ChaCha20-Poly1305：按 Hx flags 选择派生 index key/nonce，counter=0 的前 32 字节产生 Poly1305 一次性密钥；counter=1 开始是索引密文。AAD 为空，认证输入为密文、16 字节对齐零填充、两个 LE64 长度（0 和密文长度）；将计算出的标签前置。当前 reader 默认强制认证，错误密钥、标签或密文均拒绝，writer 同步生成标签。

外部 `.sig` 是 `SHA256/PSS/RSA` 数字签名，需要发行方对应私钥；它与可由现有 Hx 派生参数计算的 Poly1305 标签无关。不能把补丁未生效一律归因于缺少 `.sig`，也不应复制原签名或伪造签名文件。是否强制外部验签需独立判断。
