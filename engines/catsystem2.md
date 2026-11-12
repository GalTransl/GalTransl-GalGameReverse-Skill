# CatSystem2：KIF/INT、CST 对话与安全提取

默认输出可复用已存在的目录；遇到同名产物、非空结果目录、文件或链接时换名。显式指定输出目录时遵循 [公共安全写出约定](../guides/python-reference-api.md#安全写出示例)，父目录须已存在，目标须不存在或为可复用的已有目录（不含同名产物或非空结果目录）。

## 能力边界
- 引擎 ID：`catsystem2`。
- CST 模块：[python/engines/catsystem2.py](../python/engines/catsystem2.py)。
- INT 模块：[python/archives/catsystem2_int.py](../python/archives/catsystem2_int.py)。
- 批量入口：[python/engines/catsystem2_extract.py](../python/engines/catsystem2_extract.py)（提取，及 `pack` / `readback` 子命令）。
- 补丁包：[python/engines/catsystem2_pack.py](../python/engines/catsystem2_pack.py)。
- 支持 KIF/INT 索引、加密成员解密、EXE 口令恢复、CatScene 解析、`name/message` 与选择文本导出、追加回填，以及明文/加密 INT 写出和只含改动 CST 的 `updateNN.int` 补丁包。
- 0x30 只支持已识别选择命令的文字参数；不支持任意命令改写、CSTL、多语言表或已证明可用的松散 CST 部署。补丁包加载顺序尚未经游戏内验证，见[补丁包命名与加载顺序](#补丁包命名与加载顺序)。

## 识别证据
- INT 文件头为 `KIF\0`。加密包首索引槽名为明文 `__key__.dat`。
- CST 文件头八字节为 `CatScene`，后跟 compressedLength、uncompressedLength 两个 u32。
- compressedLength=0 表示外层未压缩；其他情况内容是 zlib 流。
- `.cst` 是剧本线索；`.cstl` 是另一路格式，不可混用。
- `.int` 容器与 CST 成员必须分层识别；不对密文或压缩 bytes 直接搜日文。

## 推荐提取入口
```text
python -B -m python.engines.catsystem2_extract "D:\Games\title"
python -B -m python.engines.catsystem2_extract "D:\Games\title" --exe "D:\Games\title\cs2.exe"
python -B -m python.engines.catsystem2_extract "D:\Games\title" --archive scene.int --archive update01.int
```
- 默认流式扫描游戏根目录的 `*.int`，不把多 GB 归档整体读入内存。
- 默认从 `cs2.exe` 的 `V_CODE2/DATA` 资源恢复口令；只解析 PE 资源，不执行 EXE。
- 按“普通包在前、数字 `updateNN.int` 在后”建立覆盖集；后包同名成员生效，并在报告中记录替换关系。
- 输出到新的 `<游戏名>_extract/`；已存在时自动选择 `_2`、`_3`，绝不覆盖。
- `gt_input/` 只写有对话的 UTF-8 JSON；`original/` 保存解密后的原 CST；`metadata/` 保存 manifest；`reports/` 保存归档、覆盖、空脚本和失败项。
- `gt_output/` 是 GalTransl 译文回填目录。

## INT/KIF 加密路线
- 加密索引记录从 0x50 开始，每条 0x48 字节；0 号槽是 `__key__.dat`，真实成员从 1 开始。
- 归档 seed 位于 0x4C；`MT(seed).rand()` 的小端 4 字节构造 Blowfish key。
- 先对 storedOffset 加成员序号 `i`，再与 size 一起 Blowfish 解密。
- 成员数据使用同一 Blowfish 做小端 ECB 解密，只处理 `size//8*8`，尾部不足 8 字节保持原样。
- INT 口令的 CRC32-normal key 只用于恢复文件名，不参与成员偏移、大小或内容解密。
- 没有口令时仍可取得成员范围并探测/解密内容；此时文件名为稳定序号占位，`name_known=False`，不能推断跨包同名覆盖。
- EXE 资源树按“类型 → 名称 → 语言”读取；优先日文 0x411，再取英文 0x409 或首个有效语言叶子。
- 0x48 的 u32（`__key__.dat` 槽的 offset 字段）含义未知，reader 不使用；`read_int` 将它与 seed 记入 `IntArchive.key_slot` / `seed`。
- 参考：GARbro `ArcFormats/CatSystem/ArcINT.cs`、`ArcFormats/Blowfish.cs`（MIT）；msg-tool `src/scripts/cat_system/archive/int.rs`、`int_password.rs`、`twister.rs`（GPL-3.0-or-later）。

## INT 写出
- `write_int(members, encrypted=..., password=/key=, seed=, key_slot=, record_prefix=, name_size=)` 按给定顺序把 `[(成员名, bytes)]` 写成新包，不读取或修改任何原包。加密包与 reader 互逆：文件名按 `key+i` 重新播种的 MT 做字母替换；offset/size 经 Blowfish 加密后 offset 减去序号；数据按小端 ECB 加密 `size//8*8` 字节，尾部原样。
- 写出后 `verify_int` 用 `read_int` / `read_member` 逐成员读回，比对名称、顺序、字节和布局，不一致即报错。
- 成员名须为 CP932、无路径分隔符和 NUL，编码后小于名字段（加密 0x40；明文 0x20 或 0x40）。大小写不敏感重名、`__key__.dat`、空列表、非 bytes 数据、超出成员数/单成员/总量预算、u32 越界参数均拒绝。加密包必须提供口令或 key；明文包不接受 seed/key。
- 成员布局只接受两种已观察形式，由 `detect_int_layout` 识别；空洞、重叠、乱序、尾随数据等其他布局拒绝，不猜：
  - **record-prefixed**（加密包）：索引后每个成员 i 之前是索引记录 i-1 存储形式的逐字节副本（首个成员前为 `__key__.dat` 槽），成员按序号首尾相接，末成员结束于文件尾。所检查的真实加密包全部符合，加密写出默认采用。
  - **contiguous**（明文包）：成员紧接索引首尾相接，与真实明文更新包及 GARbro 明文 writer 一致。
- 真实加密包经 `read_int` → `detect_int_layout` → 复制 seed、0x48 字段和布局 → `write_int` 原样重写，可逐字节复现原文件，包括数千成员的剧本包和更新包；没有额外填充、对齐或排序规则。超大明文包只核对了索引和布局。
- 未指定 seed/0x48 字段时由内容哈希确定性派生；`pack` 始终复制模板包的这两个值。0x48 是否被运行时检查未知。

## INT Python 接口
```python
from python.archives.catsystem2_int import (
    extract_exe_password, probe_int, probe_member, read_int, read_member,
)
password = extract_exe_password("game/cs2.exe")
archive = read_int("game/scene.int", password=password)
entry = archive.entries[0]
assert probe_member("game/scene.int", entry, archive.cipher, max_bytes=8) == b"CatScene"
data = read_member("game/scene.int", entry, archive.cipher)
```
- 写出：`write_int([("scene.cst", data)], encrypted=True, password=password, seed=archive.seed, key_slot=archive.key_slot)`。
- `probe_int`、`read_int`、`probe_member`、`read_member`、`detect_int_layout`、`verify_int` 均接受 bytes、路径或可寻址二进制流。
- `read_int` 只读取索引；`read_member` 只读取选中成员。
- 对外部流不关闭；路径和内部 BytesIO 由函数自行关闭。
- 始终设置成员数、索引大小、单成员和累计输出预算。

## CST 结构
- 解压后前 16 字节是四个小端 u32：dataLength、clearScreenCount、字符串索引相对位置、字符串池相对位置。
- 两个相对位置均加 16 得到绝对位置；索引项数为 `(poolOffset-indexOffset)/4`。
- 索引地址相对字符串池，每条记录为 `01 type cstring`。
- 允许 type：02、03、20、21、30、F0、F1；未知类型拒绝。
- `read_cst` 同时核对外层大小、zlib 结束状态、内层长度、索引边界、记录标记和类型。

## 对话导出与回填
```python
from python.engines.catsystem2 import export_cst, patch_dialogue, read_cst
scene = read_cst(data)
exported = export_cst(scene)
translated = [dict(row) for row in exported.rows]
patched = patch_dialogue(data, exported, translated)
assert patched == data
```
- `export_cst` 按 msg-tool 语义将 0x21 暂存为下一条非空 0x20 的姓名，不合并连续正文槽。
- locator 保存 `message_record`、可选 `name_record` 和跨过的命令记录。
- `$str20` 一类动态姓名标记为 `context`，禁止翻译；普通姓名标记为 `writable`。
- `ID＠表示名`（全角 ＠）只导出 ＠ 之后的显示名供翻译，`ID＠` 存入 locator 的 `name_prefix`，回填时原样拼回；译名不得为空或增删 ＠。＠ 后为空的姓名整体作 `context`。旧工作区导出的是整串姓名，与当前导出不一致时 `pack` 拒绝并要求重新提取，不改 manifest 绕过。
- 引擎字面 `\n` 导出为 JSON 换行，回填时还原；`\@`、`\p` 等控制符数量受保护。换行可以比原文少，但不能新增或跨控制符移动，避免合并后的排版和等待位置变化。
- 以 `\n` 开头的消息是同一文本框内的续行，在正文中很常见。译文开头的换行数必须与原文相同；去掉或新增开头换行会静默改变排版，`patch_dialogue` 拒绝。
- 振假名 `[漢字/かな]` 按受保护语法处理：译文可以保留、改写或删除整组注音，但方括号必须组成两侧非空、不含 `/` 和方括号的 `[底字/注音]`；去掉控制符和合法注音后剩余的方括号须与原文一致。
- 连续姓名、末尾悬空姓名、姓名跨命令均写入导出诊断，不静默假装语义确定。
- 续行条目与字体控制也须按记录和控制语法保留；不能因为正文可读就合并条目或清除字体码。
- 完整匹配 `数字 标识符 文本` 的 0x30 选择命令导出独立、无姓名的 `message`；locator 的 `choice_span` 标记文字范围。选择不会消耗等待下一条正文的姓名，命令数字、标识符和原分隔空白保留。其他 0x30 指令不进入译文。
- 选择文字保持原始控制符表示，包括字面 `\n`；不套用 0x20 正文的换行转换。原有控制符数量受保护。
- `patch_dialogue` 校验条数、字段、context 姓名和控制码，再调用 `patch_cst`。
- `patch_cst` 修改 0x20/0x21，或已识别 0x30 的选择文字；选择替换值仅含文字，不含命令前缀，禁止空文字、前导空白、物理换行及 NUL。新字符串追加到 pool 尾部并改目标索引。全部值未变时返回原 bytes；`patch_dialogue` 校验来源并重新提取结果比对译文。
- 原 `excluded_choices` 字段保留兼容，已支持的选择不再排除。旧提取目录含选择命令时须重新导出，不修改 manifest 绕过条数和定位校验。

## 输出与覆盖规则
- 有真实文件名时，以规范化成员名作为覆盖身份；数字 `updateNN.int` 中后出现的同名成员覆盖基础包。
- 无法恢复文件名时，不跨归档猜测覆盖关系，输出序号名并在报告标记 `names_recovered=false`。
- `gt_input/` 平铺并使用剧本真名；只有 basename 冲突时附加归档名和成员序号。
- manifest 的 `sources[].path` 直接指向输出树中的 `original/.../*.cst`；原归档名、成员名和序号保存在 locator。
- 单成员失败不冒充成功，记录到 `reports/outputs.json`；归档索引失败也记录后继续其他包。

## 补丁包命名与加载顺序
- **证据**：EXE 中有宽字符串 `update??.INT`，用于枚举更新包；`config/startup.xml` 的 `<INT>` 只列基础包，不列 update 包。真实更新包中大量 CST 与基础包同名且为新版内容，说明 update 包覆盖基础包同名成员（强证据）。多个 update 包之间“编号大者优先”是推断：`??` 为两位，按名称枚举时与数字顺序一致，但所查样本只有一个 update 包含剧本，**待游戏内验证**。
- **命名**：新包使用两位编号 `updateNN.int`，NN 默认取游戏目录与工作区中现有最高编号 +1；编号超过 99、与现有文件同名或不高于现有最高编号时拒绝。提取器的覆盖规则与此一致（普通包在前，数字 update 包按编号在后）。
- 新包只含改动成员并使用成员真名，部署时放到游戏 EXE 同目录，不覆盖任何原包。若游戏内未生效，先核对加载顺序，再考虑其他部署方式。

## 封包与回读
```text
python -B -m python.engines.catsystem2_extract pack "工作区" "新的补丁目录" [--readback "新的回读目录"] [--number NN] [--game "游戏目录"] [--exe cs2.exe | --password 口令] [--translations 目录]
python -B -m python.engines.catsystem2_extract readback "工作区" "补丁目录" "新的回读目录" [--game "游戏目录"]
```
- `pack` 读取 `gt_output`（或 `--translations`）中的同名 JSON，未知文件名直接拒绝；经 `validate_translation` 与 `patch_dialogue` 全部校验后，只收录字节有变化的 CST，以成员真名按名称排序写入新的 `updateNN.int`。未改动的译文记入 `unchanged_translation_files`；没有任何改动时不生成空包。
- 游戏目录默认取工作区 `reports/summary.json` 的 `game_root`，只读：核对模板包 SHA-256 与提取时一致；口令默认从 `cs2.exe` 恢复，并用模板包的成员名验证。模板为改动成员来源包中加载顺序最后者；加密方式、布局、seed 和 0x48 字段均复制自模板。
- 游戏中已登记 update 包的大小须与工作区一致；工作区未扫描的 update 包会读取索引，若含本次要替换的成员则拒绝（否则会用旧版内容覆盖新版），需重新提取。
- 生成后用 `read_int` / `read_member` 读回，逐一比对名称和字节，并重新解析每个 CST 核对译文行。补丁目录只有 `updateNN.int`、`reports/verification.json` 和 `README.txt`；输出不得位于工作区或游戏目录内。
- `readback`（或 `pack --readback`）从工作区原 CST 出发，叠加新包中的同名成员，重新导出完整 `gt_input` 到单独的新目录；新包成员必须都是工作区已导出的脚本，且包名须排在工作区所有归档之后。

## CP932 中文：JIS 四步
```text
python -m python.common.jis_workflow arch "游戏目录/cs2.exe"
python -m python.common.jis_workflow prepare "工作区" "JIS准备目录" --encoding cp932 --proxy-policy unused --hook <按位数> --exe "游戏目录/cs2.exe"
python -B -m python.engines.catsystem2_extract pack "JIS准备目录/workspace" "补丁目录" --readback "回读目录"
python -m python.common.jis_workflow finalize "JIS准备目录" "补丁目录" "回读目录/gt_input" "交付目录"
```
- 准备目录的 `workspace/reports/summary.json` 保留原 `game_root`，`pack` 照常读取游戏目录的模板包和口令；游戏目录变动时用 `--game` 指定。
- `finalize` 发布整个补丁目录，交付物是 `updateNN.int` 及报告、映射和 hook，而不是序号命名的松散 CST；回读目录不得放进补丁目录。

## 部署条件与缺口
- 明文/加密 INT writer 与补丁包已实现，经 reader 读回和 CST 重解析；游戏加载顺序与显示未经运行验证。
- CP932 不能直接编码任意简体中文；需要字体、编码扩展或映射方案，不能使用 `errors="ignore"/"replace"`。
- 清屏元数据只保留，不声称理解所有版本结构；0x48 字段的运行时含义未知。
- 其他选择布局、CSTL、多语言表和游戏内加载仍需版本证据。

## 验证
- 合成测试：`tests/test_engines_primary.py` 的 `CatSystemTests` 与 `tests/test_catsystem2.py`。
- 覆盖压缩/未压缩 CST、追加重定向、动态姓名、`ID＠表示名`、续行换行、振假名语法、控制码、选择文字与命令前缀保留、PE32/PE32+ 三层资源、加密/明文 INT 读写（与独立构造的样例逐字节一致、两种布局、CP932 多字节名）、writer 反例、无密码内容探测、路径/流输入、更新包覆盖、`pack` 只收改动成员与真名、编号、错误口令、未扫描 update 包冲突、回读，以及 JIS `finalize` 交付 `updateNN.int`。文本字段来源见 [记录](../provenance/common-text-fields.json)。
- 封包与回读通过不代表已验证游戏加载顺序、字体覆盖或显示。
