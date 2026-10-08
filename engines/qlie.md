# QLIE：PACK 3.0 解包、ImoScripter 对白与模板重封包

## 路线选择

引擎 ID：`qlie`。容器版本与脚本方言分别判定，按下表加载代码。

| 阶段 | 实现与范围 |
|---|---|
| PACK 3.0 | [qlie.py](../python/archives/qlie.py)：有界索引、CP932 文件名、三种显式密钥模式、密文校验、`1PC FF` 字节对解压 |
| 图标密钥 | [qlie_keys.py](../python/archives/qlie_keys.py)：静态解析 PE 的 `RCDATA/TFORM1/ IconKeyImage`，不运行 EXE、不实例化 Delphi 对象 |
| ImoScripter 多行方言 | [qlie_imos.py](../python/engines/qlie_imos.py)：`FormatType=1`、`ReturnCode=[n]`，空行分句、姓名与选项、居中文字、可逆回填 |
| 提取入口 | [qlie_extract.py](../python/engines/qlie_extract.py)：明确指定包、EXE、key，生成平铺 JSON、原件、manifest 和报告 |
| PACK 重建 | [qlie_writer.py](../python/archives/qlie_writer.py)：以原始 `FilePackVer3.0 + HashVer1.3` 为模板替换已有成员，重写偏移/长度/密文校验 |
| 译文打包入口 | [qlie_repack.py](../python/engines/qlie_repack.py)：从 `gt_output` 校验、回填、生成新 PACK；支持原文整包往返 |
| 旧文本字段 API | [qlie.py](../python/engines/qlie.py)：有限 `id,name,message`、独立姓名、`^select` 的字符范围 API；下文保留说明 |

PACK 1.x/2.x/3.1、未知 hash 版本、新建或删除成员、重命名、任意脚本 VM 尚不支持。writer 只支持 **3.0 原包模板重建**，不能将其他版本的布局直接套用。

## PACK 3.0 与密钥链

1. 尾部 28 字节是 `FilePackVer3.0\0\0`、条数、64 位索引偏移。`read_index(stream)` 只读索引和包尾密钥材料；不把整个包或大语音成员装入内存。
2. 名称是按包内 ArcKey 解密后的 CP932 字节。`Entry.raw_name` 保存**解密后的名称字节**，这是 keyed 解密的输入；不能错用密文名称。仍须通过 `validate_names` 才能写盘。
3. `mode` 必须显式指定：`legacy` 不带外部密钥；`key-file` 使用 key 文件；`keyed` 同时使用 key 文件和 256 字节 IconKeyImage。仅发现 `key.fkey` 不证明单密钥模式足够。
4. `keyed` 模式按外部 key 文件与 EXE 图标密钥 → 包内 key 成员 → 后续成员建立密钥链。每个包的内部 key 单独解码，不跨包复用。
5. `read_member` 先核对**存储密文**的 QLIE checksum，再解密，再严格解压。压缩头错误常提示密钥模式/图标错误；禁止把解压失败的密文当原文返回。
6. ArcKey 从末尾 `0x41c` 处的 256 字节生成。QLIE 使用 64-word 的 MT 变体、MMX 分 lane 加法和明文反馈，不等同于标准 MT19937 或对称地调用 decrypt 两遍。末尾不足 8 字节不加密，checksum 也只覆盖完整 qword；另用完整 SHA-256 保存输入身份。

只从用户提供的游戏中静态读取密钥。`game_key_from_pe(bytes)` 不扫描进程，不加载可执行文件，也不附带任何游戏密钥。先限制 EXE 大小；不支持的 PE/Delphi 结构报错。

## 提取工作区

在 Skill 根目录运行，替换 `GAME`、`NEW_EXTRACT` 为实际路径：

```text
python -B -m python.engines.qlie_extract "GAME" "NEW_EXTRACT" --exe "game.exe" --key-file "DLL/key.fkey" --archives GameData/story.pack GameData/update.pack
```

`NEW_EXTRACT` 按主 Skill 约定选游戏下不存在的 `<游戏名>_extract`。可直接把 `NEW_EXTRACT/gt_input` 导入 GalTransl，翻译结果放回 `NEW_EXTRACT/gt_output`，保持同名与条目顺序。

- 提取器只解出 `.s`、配套 `.txt` 和内部 key，媒体只读索引；累计脚本输出默认 64 MiB。完整包 SHA-256 以流方式计算。
- 同名/同路径剧本跨包时保留每个版本，不擅自断言包加载优先级；文件名冲突才加 `__aNN_mNNNNN` 后缀。报告记录精确来源及输出名。
- `.txt` 保存在 `original` 供核对配置，不泛化为对白。汉化 EXE 的外部覆盖数据（例如 `.cn`、`.1/.2`）未解析；此路线只导出所选 PACK 内的剧本，不推断其语言或补丁状态。

## ImoScripter 多行方言与回填

`avg/projectsetting.txt` 的 `FormatType=1`、`avg/setting.txt` 的 `ReturnCode=[n]` 是进入此路线的证据；下列规则不适用于 FormatType=0。

- 姓名和正文只在同一空行分隔句中结合；空行后姓名清空，旁白不会继承上一人物。语音行 `％...％` 和控制行不送翻译。孤立姓名、句内未知控制流和未知文本标签报错。
- `【身份名＠显示名】` 导出显示名。译名写回时保留原身份名，避免改变按身份名查找的语音音量设置；例如 `【Alice】` 翻译后为 `【Alice＠艾丽丝】`。变量姓名为上下文只读。`＠` 不是多人名分隔符。
- `[spd,0][pc,文字][spd]` 只导出 `文字`，回填保留外部指令；不能把整段 `pc` 当不可翻译标签，否则会遗漏诗句。当前支持独立 pc 文本行，不支持与普通正文混排的复杂 pc。
- 同一句的连续物理正文行合并为一个 JSON `message`，用换行分隔；多物理行回填须保持行数。单物理行的显示换行转换为 `[n]`。保留原缩进、CRLF、语音和全部非文本字节。仅含一个全角空格的显示间隔不产生空消息。
- `^select,` 后每个选项各一条，空选项也保留；不把 `^selectset1`、`^selectjmp` 的控制参数当选项。选项/pc 文本不得引入 ASCII 逗号、物理换行或新标签。
- `^savetext,标题,...` 的第一个简单参数导出独立存档标题行；后续参数、前导缩进及尾部空白原样保留。标题不得新增逗号、换行或标签；嵌套标签参数布局拒绝，不猜逗号归属。
- 存档标题命令不清空当前句的姓名，也不拆分其前后的正文；正文仍按原空行边界分组，标题独立定位回填。
- parser 重新从原件生成定位，与 manifest 中的定位对比；不信任任意 sidecar 偏移。回填后重新解析并比对全部 name/message。
- 当前 parser 标识为 `qlie-imos-multi/2`。旧工作区须从可靠原件重新提取到新目录，保留已有译文并核对新增标题的位置；不改 manifest 或按旧序号直接套用。

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

输出为 `NEW_REBUILT/GameData/story.pack` 等**原归档同名文件**和 `reports/repack.json`，只重建含译文的包；同包内没有译文的成员按原密文复制。空翻译目录、未知文件名、原件或 manifest 被修改、译文条数/字段/控制结构错误均会拒绝，不生成冒充成功的包。

```text
python -B -m python.engines.qlie_repack "GAME" "NEW_EXTRACT" "NEW_ROUNDTRIP" --source-roundtrip
```

`--source-roundtrip` 使用原文 JSON，所有 `.s`（包括空系统脚本）提交给 writer。相同原文仍经过解密→保留原压缩流→重新加密及索引重建；不是整包直接复制。生成后比较原包与重建包的哈希。

writer 的明确边界：

- 文件名、索引顺序、条数、内部 key 保持不变。`HashVer1.3` 的 256 桶查找表逐项验证“名称→序号数组”对应后原样保留；其中的 64 位值指向序号数组，不是资源的绝对文件偏移。
- 修改成员以**未压缩、原加密模式**重新存储，并更新 payload 偏移、存储/解码长度、密文 checksum 和包尾索引偏移。不实现 BPE 优化压缩，因此新包可能略大；未修改成员保留原压缩密文。
- 底层 `rebuild(source, destination, replacements, mode=..., key_file=..., game_key=...)` 支持流式复制媒体，`destination` 必须是独立、空的可读写流。调用者以 `x+b` 创建新文件并负责失败清理。便捷 CLI 为安全使用 `write_new_tree`，限制单原包 128 MiB、整个产物 256 MiB；更大包按流式 API 单独处理。
- 当前 CLI 严格使用 CP932。它不会偷偷转 CP936、损失字符或安装字符隧道；CP932 不可编码的中文需先独立验证运行时编码/字体方案。归档算法可保存任意 bytes，不能由此推断游戏支持对应文本编码。
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

- PACK 索引、checksum、名称密码、MT 和 `1PC`：GARbro-Mod 提交 `bc26d991ef5cdc0e1ecb32122ee9a48c3375750c`，`ArcFormats/Qlie/ArcQLIE.cs`、`Encryption.cs`、`QlieMersenneTwister.cs`。静态图标资源定位另参考 `DelphiDeserializer.cs`。保留源作者与 [MIT 通知](../provenance/licenses/MIT-GARbro.txt)。Python 增加边界、循环压缩表拒绝、严格编码与显式密钥模式。
- HashVer1.3 头结构交叉核对 msg-tool 提交 `f72716cee88554d40c1cdface2812493b14ca653` 的 `src/scripts/qlie/archive/pack/types.rs`；其 `v31.rs` 是另一版本，不直接移植。新增模板 writer/语义提取按本项目 GPL-3.0-or-later 许可。
- 存档标题语义参考 msg-tool，Python 仅替换第一个参数的原始范围，保留其他参数；来源见 [文本字段来源](../provenance/common-text-fields.json)。
- [tests/test_qlie.py](../tests/test_qlie.py) 使用纯合成 PE/DFM、key、PACK、脚本，覆盖两种物理顺序、原文/变长重建、加密向量、坏 checksum、错误 key、BPE 循环/预算、查找表错误、显示姓名和 pc、manifest 定位篡改及不覆盖输出。

```text
python -B -m unittest discover -s tests -p test_qlie.py -v
```
