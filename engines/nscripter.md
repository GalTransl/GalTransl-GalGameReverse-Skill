# NScripter：容器可回写，文本仍须词法与命令边界审核

## 能力边界
- 独立参考实现见 `../python/archives/nscripter.py`，仅依赖 Python 标准库。
- 已实现 `nscript.dat` 双向 XOR、SAR 读写、未加密 NSA 的 raw/NBZ 读写。
- 没有声称实现完整 NScripter/ONScripter 语法分析器或所有运行时方言。
- 没有插件、原仓库运行时、外部解包程序、在线服务依赖。
- 解包成功不等于对白提取成功，更不等于游戏能加载译文。
- 所有档案成员名都不可信；模块只返回记录，落盘交给调用者的安全输出器。

## 识别证据与真实结构
- `nscript.dat` 没有固定 magic；参考源码按文件名识别，不按解密后的可打印率识别。
- 每个字节与 `0x84` XOR，解码与编码是同一操作，不增删长度。
- 普通 `0.txt`、`00.txt` 等脚本不能仅凭扩展名套 XOR。
- 主对白可能位于 SAR/NSA 包外的独立脚本；先检查 `nscript.dat`、`0.txt` 等入口，不能把资源包字符串或命令参数全部当成对白。
- SAR 也没有固定 magic：开头为 BE `u16 count`、BE `u32 data_base`。
- SAR 索引自偏移 6 开始，每项是 CP932 的 NUL 结尾名、BE `u32 relative_offset`、BE `u32 size`。
- SAR 成员绝对位置等于 `data_base + relative_offset`。
- NSA 基本头相同，但名称后是 `u8 compression`、BE `u32 offset/packed_size/unpacked_size`。
- 某些 NSA 头前有两个零字节；此时 `data_base` 相对真正头起点计算。
- NSA 方法 `0` 为原始内容，`1` 为 SPB，`2` 为 LZSS，`4` 为 NBZ。
- 本实现明确拒绝 `1/2` 和未知方法，不移植许可边界不清的历史压缩段。
- NBZ 是 BE `u32` 解压长度加一个 bzip2 流，不是整个成员直接喂给 bzip2。
- 与源码一致，`.nbz` 后缀即便标为方法 0，也触发 NBZ 处理。
- 方法 4 要求索引解压长度与 NBZ 头一致。
- 方法 0 的 `.nbz` 允许索引长度记录压缩容器长度或 NBZ 解压长度；其余不一致拒绝。
- 不支持密码加密 NSA、自动猜密码、非标准索引填充或未知变体。

## 从字节到文本的流程
1. 保存原档案、原成员、解密后字节的哈希和大小，全部工作在可丢弃副本上。
2. 根据文件名、运行时类型、档案结构确定是否应做 XOR。
3. 先尝试项目已确认的 CP932 等编码，严格解码；不能用 `errors="ignore"` 掩盖损坏。
4. 编码选择来自项目证据，不能把所有脚本都强制改为 UTF-8。
5. 保留 BOM、有无最终换行、CRLF/LF、空行、缩进和原始字节区间。
6. 输出候选文本前完成状态扫描；不确定行进入人工审核队列，而非批量翻译。

## 词法边界：设计要求，不是已交付的完整解析器
- 扫描器至少需要：命令、引号字符串、注释、文本、标签五类状态。
- `*define`、`*start` 及其他 `*label` 是结构边界，不是对白。
- `;` 注释应结合所在状态识别；不能在任意文本里一刀切截断。
- `:` 的命令分隔作用只能在已确认的命令上下文、引号外处理。
- `mov $0,"text"` 中的字符串可能是变量、路径或 UI；不能把所有引号内容视为对话。
- `bg`、音频、图片、存档、路径、标签参数应进入非翻译参数类别。
- `select "选项",*label` 等选择命令需要命令签名：只替换显示串，保留目标标签。
- 自定义 `defsub` 和别名命令必须有签名；未知命令的字符串默认不改。
- “行首非 ASCII”可以辅助发现日文文本，却不足以判断英文对白或命令参数。
- 反引号英文文本模式及其他方言必须单独确认，不能用一个正则承诺全覆盖。
- `@`、`\` 常见于等待/换页控制，应作为保护 token，而不是普通标点。
- `!w`、`!s`、颜色标记、行连接等控制语法依运行时核对，不在本参考里猜测重写。
- `$20`、`%20`、别名变量（例如 `$str20`）原样保留，不按看似姓名的内容展开或替换。
- `[...]`、姓名框、旁白标记可能由游戏自定义；没有证据不能自动拆为角色名。
- 连续文本行的合并必须理解等待/换页边界；不能把换行当通用句子分隔符。

## JSON 映射建议
- 下例是词法审核后的交换格式建议；档案模块本身不自动产生这些对白记录。
- `span` 使用解密后、重新编码前的原始字节半开区间，不能使用 Python 字符索引冒充。
- `source_sha256` 绑定整份解密脚本；`source` 和保护 token 用于回填前二次校验。
```json
{
  "id": "nscript.dat:dialogue:0001",
  "file": "nscript.dat",
  "kind": "dialogue",
  "encoding": "cp932",
  "span": {"start": 128, "end": 142},
  "source": "原文候选",
  "translation": "",
  "source_sha256": "<解密后整份脚本的 SHA256>",
  "context": {"label": "*start"},
  "protected": ["$str20", "\\"]
}
```
- 示例区间仅示意，不对应所示字符串；实际区间必须由扫描器从原字节计算。
- 同样文本出现两次要保留不同 ID；不按原文字面值去重或全局 replace。
- 路径、标签、条件表达式、命令名、不可翻译参数另列为不可变结构证据。

## Python 函数示例
```python
from python.archives.nscripter import (
    xor_nscript, extract_sar, extract_nsa, build_sar, build_nsa,
)

def decrypt_script(encrypted: bytes) -> str:
    return xor_nscript(encrypted).decode("cp932", errors="strict")

def encode_reviewed_script(reviewed: str) -> bytes:
    return xor_nscript(reviewed.encode("cp932", errors="strict"))

def rebuild_plain_nsa(archive: bytes) -> bytes:
    members = extract_nsa(archive)
    # 仅重建无 NBZ 的示例；压缩成员需要明确选择方法，不可悄悄改语义。
    if any(m.compression != "none" for m in members):
        raise ValueError("this example preserves only uncompressed members")
    return build_nsa([(m.name, m.data) for m in members], compression=0)
```
- `extract_sar/extract_nsa` 返回 `Entry(name, data, offset, stored_size, compression)` 列表。
- `build_sar/build_nsa` 返回新档案 bytes；`build_nsa(compression=4)` 对全部输入做 NBZ。
- `decode_nbz` 可单独验证 NBZ；它限制解压长度并拒绝截断、尾随和拼接压缩流。
- Writer 使用严格 CP932、拒绝重复名字、NUL、超大索引；不承诺原档案逐字节相同。

## 回填与部署
1. 校验文件哈希、源区间字节、占位符计数与控制 token 顺序，任何漂移都停止。
2. 对不重叠区间按字节位置降序替换，只修改确认可翻译的文本 token。
3. 原编码严格预检；字体缺字、中文不在 CP932、运行时编码不兼容是部署问题，不应静默替字。
4. 明文脚本保留原换行和编码；确认是 `nscript.dat` 才重新 XOR。
5. 原本 loose script、SAR、NSA 的优先级由目标运行时决定，不能默认新包一定覆盖旧包。
6. 保存原包，输出到新位置；使用安全路径验证并拒绝重复归一化名、越界路径、链接绕过。
7. 空译回填应字节恒等；有译文则比较不可变区间、标签引用、命令参数及档案成员集合。
8. 在用户允许的测试副本人工验证开场、分支、选择、存读档和跨页，不覆盖原游戏。

## 验证证据与未覆盖项
- `../tests/test_archives.py` 的 `NScripterTests` 使用人工最小档案，不依赖真实游戏。
- 覆盖已知 XOR 字节、CRLF 还原、BE SAR、NSA 双零前缀、NBZ 长度和后缀识别。
- 覆盖 raw/NBZ writer 回读、空成员、SPB/LZSS 拒绝、短包、越界、重复名和输出预算。
- 未进行真实游戏运行、编码迁移、对白语法全量验证或付费 API 调用。
- 档案能力的测试不能作为自定义命令或中文字体可用的证据。

## 相对源码出处与许可
- GARbro-Mod `ArcFormats/NScripter/Script.cs`：`NSOpener.ConvertFrom/ConvertBack`，XOR `0x84`。
- GARbro-Mod `ArcFormats/NScripter/ArcSAR.cs`：`SarOpener.TryOpen/Create`，BE 索引和 writer。
- GARbro-Mod `ArcFormats/NScripter/ArcNSA.cs`：`ReadIndex/UnpackEntry/Create`，方法码与 NBZ 入口。
- 三者均核对提交 `bc26d991ef5cdc0e1ecb32122ee9a48c3375750c`；文件头 MIT 许可。
- Python 模块保留相应许可声明；完整来源和验证矩阵见 `../provenance/archives.json`。
- 词法方案是本文保守设计要求，不能归因于只做容器/XOR 的 GARbro 脚本类。
