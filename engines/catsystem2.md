# CatSystem2：KIF/INT、CST 对话与安全提取

## 能力边界
- 引擎 ID：`catsystem2`。
- CST 模块：[python/engines/catsystem2.py](../python/engines/catsystem2.py)。
- INT 模块：[python/archives/catsystem2_int.py](../python/archives/catsystem2_int.py)。
- 批量入口：[python/engines/catsystem2_extract.py](../python/engines/catsystem2_extract.py)。
- 支持 KIF/INT 索引、加密成员解密、EXE 口令恢复、CatScene 解析、`name/message` 与选择文本导出、追加回填。
- 0x30 只支持已识别选择命令的文字参数；不支持任意命令改写、CSTL、多语言表、加密 INT 重封包或已证明可用的松散部署。

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
- 参考：GARbro `ArcFormats/CatSystem/ArcINT.cs`、`ArcFormats/Blowfish.cs`（MIT）；msg-tool `src/scripts/cat_system/archive/int.rs`、`int_password.rs`、`twister.rs`（GPL-3.0-or-later）。

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
- `probe_int`、`read_int`、`probe_member`、`read_member` 均接受 bytes、路径或可寻址二进制流。
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
- 引擎字面 `\n` 导出为 JSON 换行，回填时还原；`\@`、`\p` 等控制符和换行计数受保护。
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

## 部署条件与缺口
- 当前完整往返边界止于解密后的 CST；尚无 encrypted INT writer。
- 翻译后先用 `patch_dialogue` 做逐文件重读与字段比对，再研究该版本的补丁包或松散加载优先级。
- CP932 不能直接编码任意简体中文；需要字体、编码扩展或映射方案，不能使用 `errors="ignore"/"replace"`。
- 清屏元数据只保留，不声称理解所有版本结构。
- 其他选择布局、CSTL、多语言表和游戏内加载仍需版本证据。

## 验证
- 合成测试：`tests/test_engines_primary.py` 的 `CatSystemTests` 与 `tests/test_catsystem2.py`。
- 覆盖压缩/未压缩 CST、追加重定向、动态姓名、控制码、选择文字与命令前缀保留、PE32/PE32+ 三层资源、加密/明文 INT、无密码内容探测、路径/流输入和更新包覆盖。文本字段来源见 [记录](../provenance/common-text-fields.json)。
- CST 回填通过不代表已验证游戏加载、字体覆盖或 encrypted INT 重封包。
