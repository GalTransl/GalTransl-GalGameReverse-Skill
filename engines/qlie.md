# QLIE：PACK 3.0/3.1 解包、ImoScripter 对白与模板重封包

目录输出遵循 [公共安全写出约定](../guides/python-reference-api.md#安全写出示例)：父目录须已存在，目标须不存在或为可复用的已有目录（不含同名产物或非空结果目录）；文件和链接拒绝。

## 路线选择

引擎 ID：`qlie`。容器版本与脚本方言分别判定，按下表加载代码。

| 阶段 | 实现与范围 |
|---|---|
| PACK 3.0 / 3.1 | [qlie.py](../python/archives/qlie.py)：有界索引；3.0 为 CP932 文件名与 `legacy`/`key-file`/`keyed`，3.1 为 UTF-16LE 文件名与 `pack-key`/`default-key`；按版本校验密文 checksum，`1PC FF` 字节对解压 |
| EXE 密钥资源 | [qlie_keys.py](../python/archives/qlie_keys.py)：静态解析 PE 的 `RCDATA/TFORM1/ IconKeyImage`（3.0 keyed）与 `RCDATA/RESKEY`（3.1 可选外部 key），不运行 EXE、不脱壳、不实例化 Delphi 对象 |
| ImoScripter 多行方言 | [qlie_imos.py](../python/engines/qlie_imos.py)：`FormatType=1`、`ReturnCode=[n]`，空行分句、姓名与选项、居中文字、可逆回填 |
| 提取入口 | [qlie_extract.py](../python/engines/qlie_extract.py)：明确指定包；按包尾版本与包内 key 成员逐包判定模式（或 `--mode`），只在需要时读取 EXE/key，生成平铺 JSON、原件、manifest 和报告 |
| PACK 重建 | [qlie_writer.py](../python/archives/qlie_writer.py)：以原始 `FilePackVer3.0 + HashVer1.3` 或 `FilePackVer3.1 + HashVer1.4` 为模板替换已有成员，重写偏移/长度/密文校验 |
| 译文打包入口 | [qlie_repack.py](../python/engines/qlie_repack.py)：从 `gt_output` 校验、回填、生成新 PACK；支持原文整包往返 |
| 旧文本字段 API | [qlie.py](../python/engines/qlie.py)：有限 `id,name,message`、独立姓名、`^select` 的字符范围 API；下文保留说明 |

PACK 1.x/2.x、未知 hash 版本、新建或删除成员、重命名、任意脚本 VM 尚不支持。writer 只支持 **3.0/3.1 原包模板重建**，版本之间不互相转换。

## PACK 3.0 与密钥链

1. 尾部 28 字节是 `FilePackVer3.0\0\0`、条数、64 位索引偏移。`read_index(stream)` 只读索引和包尾密钥材料；不把整个包或大语音成员装入内存。
2. 名称是按包内 ArcKey 解密后的 CP932 字节。`Entry.raw_name` 保存**解密后的名称字节**，这是 keyed 解密的输入；不能错用密文名称。仍须通过 `validate_names` 才能写盘。
3. API 的 `mode` 必须显式传入：`legacy` 不带外部密钥；`key-file` 使用 key 文件；`keyed` 同时使用 key 文件和 256 字节 IconKeyImage。仅发现 `key.fkey` 不证明单密钥模式足够。CLI 的 `auto` 只在包内有 key 成员时选 `keyed`；没有时要求显式 `--mode legacy` 或 `key-file`。
4. `keyed` 模式按外部 key 文件与 EXE 图标密钥 → 包内 key 成员 → 后续成员建立密钥链。每个包的内部 key 单独解码，不跨包复用。
5. `read_member` 先核对**存储密文**的 QLIE checksum，再解密，再严格解压。压缩头错误常提示密钥模式/图标错误；禁止把解压失败的密文当原文返回。
6. ArcKey 从末尾 `0x41c` 处的 256 字节生成。QLIE 使用 64-word 的 MT 变体、MMX 分 lane 加法和明文反馈，不等同于标准 MT19937 或对称地调用 decrypt 两遍。末尾不足 8 字节不加密，checksum 也只覆盖完整 qword；另用完整 SHA-256 保存输入身份。

只从用户提供的游戏中静态读取密钥。`game_key_from_pe(bytes)` 不扫描进程，不加载可执行文件，也不附带任何游戏密钥。先限制 EXE 大小；不支持的 PE/Delphi 结构报错。

## PACK 3.1

包尾同为 28 字节（`FilePackVer3.1\0\0`、条数、64 位索引偏移），与 3.0 的差异：

| 项目 | 3.1 规则 |
|---|---|
| ArcKey | 末尾 `0x41c` 处 256 字节的 3.1 checksum（16 位 lane 加 `0xA35793A7A35793A7`，每轮 32 位 lane 循环左移 3，最后两组有符号 16 位乘积求和）再 `& 0x0FFFFFFF` |
| 文件名 | u16 为**字符数**（≤ 0x100），随后 UTF-16LE；按字符数和 ArcKey 生成 16 位 XOR 序列，对称加解密。`Entry.raw_name` 为解密后的 UTF-16LE 字节 |
| 成员 checksum | 对**存储密文**计算 3.1 checksum，与索引对比 |
| 加密方式 | `encryption=1`：只由文件名、长度、ArcKey 生成 32 项表，无外部 key；`encryption=2`：再异或由 key 扩展出的 0x400 字节表。两者都用明文反馈，末尾不足 8 字节不加密 |
| 压缩 | 与 3.0 相同的 `1PC FF` 字节对流 |
| 名称查找表 | `HashVer1.4`：68 字节头（256 桶、条数、条数×4、存储长度、压缩标志、32 字节保留）；数据以 legacy 密码、ArcKey `0x428` 加密，压缩标志 1 时再为 `1PC`，0 时只加密（单独制作的补丁包可见）。每桶 u32 个数，项为 UTF-16LE 名称、指向 u32 序号数组的 u64 偏移和名称哈希 |

**密钥来源与模式**（`--mode auto` 的判定依据）：

1. 包内有且仅有一个 `pack_keyfile_kfueheish15538fa9or.key` 成员 → `pack-key`。该成员先解密，其明文作为同包后续 method 2 成员的 key；每包单独解，不跨包复用。
2. 该成员为 `encryption=1` 时**不需要任何外部 key**，也不需要 EXE；为 `encryption=2` 时需要外部 key：`--key-file`、缺省的 `DLL/key.fkey`，或 `--exe` 中的 `RCDATA/RESKEY`。都没有时报错，不猜。
3. 包内没有 key 成员 → `default-key`：method 2 使用内置的 0x400 字节表。
4. 判定只是候选。成员必须通过 checksum、严格 `1PC` 头/长度和脚本解码；内置表或错 key 会在解压处失败，不返回密文。可用 `--mode` 显式覆盖，但必须属于该包版本。

参考实现只在找到 `key.fkey` 或 EXE `RESKEY` 时才启用包内 key 链，否则用内置表。EXE 加壳时 `RESKEY` 可能只在资源目录中有名字、数据不在文件里；只要包内 key 成员是 method 1，它解出的 key 就足以让成员通过校验，而内置表会失败。因此以包内结构加解码结果为准，`RESKEY` 只作“启用包内 key”的旁证，此时不读取也不要求。

**EXE 被改过时**：目录中 `<名>.exe` 与 `<名>.exe.org` 同在时，`.org` 通常是原版（补丁常改导入表以加载注入 DLL）。只有确实需要 EXE（3.0 keyed、3.1 method 2 包内 key）时才读取；传入当前 EXE 而旁边有内容不同的 `.org` 时，提取器拒绝并提示显式传 `--exe "<名>.exe.org"`；两者相同则记录 `identical`。报告 `exe_check` 记录选择与哈希。需要人工核对时，只比较两个文件的差异字节所在区域（导入表、代码段或资源段），资源段一致才说明密钥材料相同。`RESKEY`/`TFORM1` 数据位于加壳后的虚拟区段时 `pe_rcdata` 明确报错，不脱壳、不运行 EXE。

**覆盖包与交付**：同一路径出现在多个包里（例如编号较大的补丁包重复了较早包中的图片），报告 `overlaps` 列出数量和示例。补丁包与其备份副本哈希相同、成员是旧包的子集时，可判断它是覆盖包；修改剧本时改**实际生效**的那份，并在游戏中确认。默认交付仍是生成与原包同名的新 PACK（只重建含译文的包），由用户替换；不改其他包、不新建覆盖包。

**脚本编码**：3.1 包中剧本与配置通常是带 BOM 的 UTF-16LE，可直接写中文，不走 CP932 JIS 代理；少数无 BOM 的系统文件按 CP932 严格解码。正文中的 `[rb,本文,注音]` 注音标签当前不支持，含它的脚本整份标记 `failed` 并给出原因，不导出部分结果；此时用 `--members` 先处理其他剧本。

## 提取工作区

在 Skill 根目录运行，替换 `GAME`、`NEW_EXTRACT` 为实际路径：

```text
python -B -m python.engines.qlie_extract "GAME" "NEW_EXTRACT" --archives GameData/story.pack GameData/update.pack
python -B -m python.engines.qlie_extract "GAME" "NEW_EXTRACT" --exe "game.exe" --key-file "DLL/key.fkey" --archives GameData/story.pack
```

- `--mode auto`（默认）按包判定，报告 `archives[]` 记录 `pack_version`、`mode`、`mode_evidence` 与 `key_source`；判定只决定试用的密钥链，成功仍以 checksum、严格解压和脚本解码为准。显式 `--mode` 必须与包版本匹配，否则报错。
- `--exe`、`--key-file` 只在密钥链需要时读取：3.0 `keyed` 需要两者（`--key-file` 缺省为 `DLL/key.fkey`）；3.1 仅在包内 key 成员为 method 2 时需要外部 key。缺 key 文件、EXE 资源不可静态读取、模式与版本不符时给出明确错误并以退出码 2 结束，不输出 traceback。
- `--members` 用大小写不敏感的 glob（`/` 路径）只选部分 `.s`，便于少量试注；`.txt` 配套文件仍全部读取作为方言证据。

`NEW_EXTRACT` 按主 Skill 约定选游戏下不存在的 `<游戏名>_extract`。可直接把 `NEW_EXTRACT/gt_input` 导入 GalTransl，翻译结果放回 `NEW_EXTRACT/gt_output`，保持同名与条目顺序。

- 提取器只解出 `.s`、配套 `.txt` 和内部 key，媒体只读索引；累计脚本输出默认 64 MiB。完整包 SHA-256 以流方式计算。
- 脚本编码按成员判定：以 `FF FE` 开头为带 BOM 的 UTF-16LE，否则严格 CP932；两者都要求原文重新编码后逐字节一致。manifest 的 `encoding` 与设置中的 `bom` 记录该结果，回填按原编码与 BOM 写回。
- 同名/同路径剧本跨包时保留每个版本，不擅自断言包加载优先级；文件名冲突才加 `__aNN_mNNNNN` 后缀。报告记录精确来源及输出名。
- `.txt` 保存在 `original` 供核对配置，不泛化为对白。汉化 EXE 的外部覆盖数据（例如 `.cn`、`.1/.2`）未解析；此路线只导出所选 PACK 内的剧本，不推断其语言或补丁状态。

## ImoScripter 多行方言与回填

`avg/projectsetting.txt` 的 `FormatType=1`、`avg/setting.txt` 的 `ReturnCode=[n]` 是进入此路线的证据；下列规则不适用于 FormatType=0。

- 姓名和正文只在同一空行分隔句中结合；空行后姓名清空，旁白不会继承上一人物。语音行 `％...％` 和控制行不送翻译。孤立姓名、句内未知控制流和未知文本标签报错。
- `【身份名＠显示名】` 导出显示名。译名写回时保留原身份名，避免改变按身份名查找的语音音量设置；例如 `【Alice】` 翻译后为 `【Alice＠艾丽丝】`。变量姓名为上下文只读。`＠` 不是多人名分隔符。
- `[spd,0][pc,文字][spd]` 只导出 `文字`，回填保留外部指令；不能把整段 `pc` 当不可翻译标签，否则会遗漏诗句。当前支持独立 pc 文本行，不支持与普通正文混排的复杂 pc。
- 同一句的连续物理正文行合并为一个 JSON `message`，用换行分隔。多物理行回填可以比原文少：只删除句尾多余的 `message` 物理行，`pc` 行不能删除，也不能新增物理行。单物理行的显示换行转换为 `[n]`。保留原缩进、CRLF、语音和全部非文本字节。仅含一个全角空格的显示间隔不产生空消息。
- `^select,` 后每个选项各一条，空选项也保留；不把 `^selectset1`、`^selectjmp` 的控制参数当选项。选项/pc 文本不得引入 ASCII 逗号、物理换行或新标签。
- `^savetext,标题,...` 的第一个简单参数导出独立存档标题行；后续参数、前导缩进及尾部空白原样保留。标题不得新增逗号、换行或标签；嵌套标签参数布局拒绝，不猜逗号归属。
- 存档标题命令不清空当前句的姓名，也不拆分其前后的正文；正文仍按原空行边界分组，标题独立定位回填。
- parser 重新从原件生成定位，与 manifest 中的定位对比；不信任任意 sidecar 偏移。回填后重新解析并比对全部 name/message。
- 当前 parser 标识为 `qlie-imos-multi/2`。旧工作区须从可靠原件重新提取到新目录，保留已有译文并核对新增标题的位置；不改 manifest 或按旧序号直接套用。多物理行支持减少尾部 message 行后，旧 metadata 的 `physical_multiline` 设置也不再匹配，同样需要重新提取。

```python
from python.engines.qlie_imos import rows, patch
source = '【Alice】\r\n％voice01％\r\nHello\r\n\r\nNarration\r\n'
translated = rows(source)
translated[0] = {'name': 'エリス', 'message': 'Longer\nmessage'}
rebuilt = patch(source, translated)
assert '【Alice＠エリス】' in rebuilt
assert rows(rebuilt) == translated
```

## 从 gt_output 打包

译文按同名文件放回 `gt_output` 后告诉 agent，由 agent 执行校验与打包。

```text
python -B -m python.engines.qlie_repack "GAME" "NEW_EXTRACT" "NEW_REBUILT"
```

打包按提取报告中逐包记录的版本、模式和 key 来源重建密钥链，并核对用到的 EXE/key 文件哈希未变；旧版 `qlie-extract/1` 报告按 3.0 keyed、CP932 处理。输出为 `NEW_REBUILT/GameData/story.pack` 等**原归档同名文件**和 `reports/repack.json`，只重建含译文的包；同包内没有译文的成员按原密文复制。空翻译目录、未知文件名、原件或 manifest 被修改、译文条数/字段/控制结构错误均会拒绝，不生成冒充成功的包。

```text
python -B -m python.engines.qlie_repack "GAME" "NEW_EXTRACT" "NEW_ROUNDTRIP" --source-roundtrip
```

`--source-roundtrip` 使用原文 JSON，所有 `.s`（包括空系统脚本）提交给 writer。相同原文仍经过解密→保留原压缩流→重新加密及索引重建；不是整包直接复制。生成后比较原包与重建包的哈希。

writer 的明确边界：

- 文件名、索引顺序、条数、内部 key 保持不变。`HashVer1.3` 的 256 桶查找表逐项验证“名称→序号数组”对应后原样保留；其中的 64 位值指向序号数组，不是资源的绝对文件偏移。
- 修改成员以**未压缩、原加密模式**重新存储，并更新 payload 偏移、存储/解码长度、密文 checksum 和包尾索引偏移。不实现 BPE 优化压缩，因此新包可能略大；未修改成员保留原压缩密文。
- 底层 `rebuild(source, destination, replacements, mode=..., key_file=..., game_key=...)` 支持流式复制媒体，`destination` 必须是独立、空的可读写流。调用者以 `x+b` 创建新文件并负责失败清理。便捷 CLI 为安全使用 `write_new_tree`，限制单原包 128 MiB、整个产物 256 MiB；更大包按流式 API 单独处理。
- CLI 按原脚本编码严格写回：CP932 脚本不会偷偷转 CP936、损失字符或安装字符隧道，中文回注走 [JIS 公共流程](../guides/jis-substitution.md)；UTF-16LE 脚本可直接写入中文，不需要 JIS 代理。归档算法可保存任意 bytes，不能由此推断游戏支持对应文本编码或字体。
- 新包须完整重新解包，核对脚本语义及未改成员字节；通过不等于游戏加载、补丁优先级、字体和选项跳转已验证。

## 旧文本字段 API（不同方言）

下面仅适用于原 [python/engines/qlie.py](../python/engines/qlie.py) 的 `qlie_fields` / `patch_qlie`，不要把它与上面的 ImoScripter 分句/显示别名规则混用。输入是正确解码的 `str`。

## 识别证据
- `.pack` 资源、`.s` 成员与 QLIE 行语法是组合证据。
- `【名字】` 独立行、`id,名字,正文`、`^select,选项...` 是文本线索。
- `@`、`^`、反斜线、全角 `％` 起始行可能是命令，不当普通正文。
- 一个逗号分隔文件不必然是 QLIE，需结合容器与执行环境。
- 只按文件中出现 NUL 推测 UTF-16 是启发式，不应代替严格解码。
- 验证多条文本、选择和控制行，检查字段数量是否稳定。

## 格式方言
- VN 的 reader 用“含 NUL”选择 UTF-16，否则使用 Shift-JIS。
- Python 不继承该自动探测，也不默认启用 SJIS tunnel。
- `[n]` 是本方言的显示换行表示。
- `^select,` 后的逗号分隔项都保留，包括空选项字段。
- `^savetext,` 的第一个简单参数作为 `save-title` 字段提取和回填；后续参数保留，标题不能加入逗号、换行或新控制标签。
- `id,名字,正文` 只把前两处逗号当结构，正文可包含其他逗号。
- bracket-name 行只提取 `【】` 内部文本。
- 空白缩进与行尾空白保留，不使用 trim 后的错误原始偏移。
- 其他命令行原样保留但不宣称理解其参数。

## 源码与算法对应
- 来源：`VNTextPatch-net8`，MIT。
- 提交：`d9c0fab7b72fdcf87d674ef12a84d3829c9188be`。
- 路径：`VNTextPatch.Shared/Scripts/QlieScript.cs`。
- `GetRanges` 对应命令行排除、bracket name、CSV-like 对话字段。
- `GetCommandArgumentRanges` 对应选择文本。
- `GetTextForRead/GetTextForWrite` 对应 `[n]` 与显示换行。
- Python 修正 trim 后没有回加前导空白而错位的风险。
- 不移植自动换行和私有字符隧道，输出编码由调用者决定。

## Python 接口与示例
```python
from python.engines.qlie import qlie_fields, patch_qlie
src = '  【Alice】  \r\nid,Bob,Hello[n]world\r\n^select,Yes,,No\r\n'
fields = qlie_fields(src)
assert fields[2].text == 'Hello\nworld'
changed = patch_qlie(src, {0: 'Ann', 2: 'New\nline', 4: 'Maybe'})
assert changed.startswith('  【Ann】  \r\n')
```
- `Field` 保留 start/end/kind/raw/text/writable。
- replacements 用原字段序号，不能以译文内容定位。
- `patch_qlie(str, dict[int, str]) -> str` 保留外层语法。
- 字节编码、BOM 和文件写出都在叶模块外。

## name / message 映射
- 独立 bracket name 和内联逗号名字都产生 name 字段。
- 默认不推测独立姓名会影响后面多少条正文。
- 相邻多个人物名均保留，不覆盖为一个值。
- `$str20` 这样的名字变量作为只读字段保留。
- 选择是 choice，空选项也保留稳定身份。
- 调用层可以按字段来源建立上下文，但不可借此强制回填只读变量。

## 回填、长度与控制码
- 替换按字符范围从后向前执行，原缩进和 CRLF 不变。
- 显示层换行转换成 `[n]`，不插入新的物理脚本行。
- 除 `[n]` 外的方括号控制标签序列必须与原字段一致。
- 名字中不允许逗号、换行或新的 `【】` 分隔符。
- 选择文本中的逗号被拒绝，防止增加选项数量。
- 以命令前缀开头的译文拒绝，避免普通文本变成指令行。
- 再解析并核对字段角色序列，拒绝因译文出现 CSV 结构而产生的新字段。
- 没有二进制脚本地址重定位；容器长度和校验属于独立层。

## 部署条件
- 必须确认引擎实际接受的字符编码与字体范围。
- 使用 UTF-16 或字符隧道的方案需要运行时证据，不能由本函数自动承诺。
- PACK 文件名、路径编码和补丁优先级都影响是否真正加载。
- 先用一条正文与一条选择测试，再扩大范围。
- 选择分隔结构保持正确仍需验证点击后实际剧情去向。
- 最终写出、备份和 manifest 使用父 Skill 的公共流程。

## 旧字段 API 验证与缺口
- 合成测试覆盖缩进名字、内联姓名、带换行正文和空选择。
- 验证替换后原缩进/行尾不变、选择数量保持正确。
- 覆盖逗号注入、姓名变量和把普通行变成对话结构的拒绝。
- 测试位置：`tests/test_engines_primary.py` 中 `TextDialectTests`。
- 旧字段 API 本身不处理资源加密或压缩；容器能力见页首。
- 控制标签形状检查不等于完整 QLIE 语法分析。
- 合成测试不携带商业素材，无游戏运行验证。

## 新增实现来源与测试

- PACK 索引、checksum、名称密码、MT、3.1 的 `EncryptionV3_1` 与 pack_keyfile 链、`1PC`：GARbro-Mod 提交 `bc26d991ef5cdc0e1ecb32122ee9a48c3375750c`，`ArcFormats/Qlie/ArcQLIE.cs`、`Encryption.cs`、`QlieMersenneTwister.cs`。静态图标资源定位另参考 `DelphiDeserializer.cs`。保留源作者与 [MIT 通知](../provenance/licenses/MIT-GARbro.txt)。Python 增加边界、循环压缩表拒绝、严格编码与显式密钥模式。
- HashVer1.3 头结构交叉核对 msg-tool 提交 `f72716cee88554d40c1cdface2812493b14ca653` 的 `src/scripts/qlie/archive/pack/types.rs`；HashVer1.4 布局交叉核对其 `v31.rs`，未复制代码，详见 [3.1 出处](../provenance/qlie-pack31.json)。新增模板 writer/语义提取按本项目 GPL-3.0-or-later 许可。
- 存档标题语义参考 msg-tool，Python 仅替换第一个参数的原始范围，保留其他参数；来源见 [文本字段来源](../provenance/common-text-fields.json)。
- [tests/test_qlie.py](../tests/test_qlie.py) 使用纯合成 PE/DFM、key、PACK、脚本，覆盖两种物理顺序、原文/变长重建、加密向量、坏 checksum、错误 key、BPE 循环/预算、查找表错误、显示姓名和 pc、manifest 定位篡改及不覆盖输出；3.1 另覆盖固定加密/名称/checksum 向量、method 2 包内 key 需外部 key、压缩与未压缩 HashVer1.4、UTF-16 BOM 脚本的自动模式提取→变长中文回填→读回、原文整包逐字节往返、错误模式、未知版本、缺 key 文件与 EXE 被改时的 CLI 报错。

```text
python -B -m unittest discover -s tests -p test_qlie.py -v
```
