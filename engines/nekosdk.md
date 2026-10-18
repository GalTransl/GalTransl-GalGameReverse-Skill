# NekoSDK：ADVSCRIPT2 显示与日志记录

## 明确的支持范围
- 本页对应 `Engine_NekoSDK`，源码检查 `NEKOSDK_ADVSCRIPT2`。
- 这是一段 18 字节脚本头，不是外层 NEKOPACK 容器 magic。
- 源预设后缀 `.txt`，但内容实际包含二进制长度与命令记录。
- 因而不能用普通逐行文本编辑器保存整个文件。
- 本模块只提取 `[テキスト表示]` 和 `[ログ追加]` 两类记录。
- **选择项未处理**，这是源预设明确注明的限制，也保留在此参考中。
- 不把“对话全部提取”扩大为“游戏全部可见文本提取”。
- NekoSDK、NekoNovel、Nekopack 名称相近，也不能共享判定规则。

## 容器和目录识别
- GARbro-Mod 的 `NekoSDK/ArcPAK.cs` 识别 `NEKOPACK4`。
- 它还按偏移九的字符 `A/S` 选择两种索引区布局。
- 每条索引的名称长度、名称字节及 offset/size 都参与解包。
- 名称字节按**有符号** byte 累加得到 key，解码 offset/size。
- 成员头部分字节另用 `size/8+0x22` 派生 key 处理，再 zlib 解压。
- 容器层现由 [nekopack.py](../python/archives/nekopack.py) 独立实现，见下节；脚本层不从容器推断。
- 应先保留提取后成员的完整相对路径与加解密阶段记录。
- 仅有 `.txt` 或 NEKOPACK 字样不足以证明成员是 ADVSCRIPT2。

## NEKOPACK4 容器
- 头部 14 字节：`NEKOPACK4`、模式字节 `A`(0x41) 或 `S`(0x53)、偏移 10 的 `u32` 索引长度。
- 模式 `A` 索引自 14 起；模式 `S` 自 10 起，且索引区后再有 12 字节才到成员数据。
- 索引记录：`u32` 名称长度（含一个结尾 NUL；0 结束索引）、CP932 名称、`u32` offset、`u32` size。
- offset 与 size 都 XOR 同一个 key：名称字节（含 NUL）的**有符号**求和；NUL 贡献 0，所以两种写法等价。
- 成员前四字节再 XOR 滚动 key `size // 8 + 34`（每字节左移 3 位，按 32 位截断），其后是 zlib 流，末尾 `u32` 为解压后长度。
- `size` 包含尾部 4 字节，不含头部那 4 字节的异或结果之外的开销。
- `read_member` 要求解压结果长度与尾字段一致、流正好结束且无尾随数据。
- `build_pak` 只写模式 `A`：保留调用方给定名称顺序，压缩级别 9，然后重新打开并逐成员比对。
- 模式 `S` 只读：参考实现的打包路径未生成该变体，不按推测写回。
- 名称宽度上限 256、条数上限 100000；越界一律报错。
- 不做：成员路径层级（参考实现只取文件名）、名称重名检测之外的排序、`.txt` 之外的脚本语义。

## 命令定位算法
- [extract_fields](../python/engines/nekosdk.py#L31) 首先校验脚本头。
- 两个命令名字按 CP932 编码后在字节流中定位。
- 该命令名字前四字节是命令字符串总长度。
- 本参考支持不含 NUL 的命令名字长度，或包含单个终止 NUL 的长度。
- 声明长度必须与这个已知命令标记精确吻合。
- 命令起点不允许倒退进入文件 magic。
- 已解析字符串内部若出现相同命令标记，不再当作新记录重复解析。
- 其余未知命令和间隙原样保留，不假装完整反汇编。
- 与简单 regex 分段相比，这些检查避免常见长度/重叠误匹配。

## name 与 message 布局
- 命令字符串之后依次是 name 和 message 两个长度前缀字符串。
- 每个字段格式为 LE32 length，加 length 个字节。
- length **包含末尾 NUL**，最小合法值为一。
- 捕获跨度只包含可见原字节，不包含四字节长度和 NUL。
- 空 name 在格式中仍占一个 NUL，不能删除整个字段。
- Field.role 明确区分 name/message，Field.raw 保留原 bytes。
- Field.length_offset 指向 LE32，start/end 指向原始文本跨度。
- 所有 offset 都是解包后的脚本成员内字节位置。
- 多行 message 可以含真实 CRLF，不能按它再次切断二进制记录。
- 源预设提示应换用其他翻译段落分隔符，避免与实际 CRLF 冲突。
- 普通 NUL 不允许出现在字段内部，以免混淆长度与字符串结束。

## 编码与控制保护
- 命令名字固定按 CP932 匹配；台词编码则由调用方严格指定。
- 不翻译 `[テキスト表示]` / `[ログ追加]` 的命令本体。
- 不把日志记录自动去重为显示记录，它们可能处于不同执行位置。
- 可见 name 可以翻译，但角色资源 ID 或其他命令参数不能套同一策略。
- leaf 不执行注释、脚本表达式或内容中的任何命令。
- 编码失败应检查目标字库、代码页与替换规则，不得 ignore。
- 翻译文本中的 CRLF、标签及控制变量仍需上层逐项保护。

## 局部写回
- [replace_fields](../python/engines/nekosdk.py#L66) 的键是本次解析得到的字段序号。
- 从后往前替换，避免先修改 name 后令 message 的旧 offset 失效。
- 每项重新写 LE32 `len(encoded_translation)+1` 与终止 NUL。
- 除已选字段外，原脚本头、未知命令、选择字节和间隙都保留。
- 这是源 ADVSCRIPT2 已知局部字段布局的 writer，不含外部容器地址修复。
- 没有声称解析未知版本的全局跳转或外部字符串引用。
- 若目标变体存在此类地址，须先补充格式验证，不能照用变长。
- 不截断长译文，也不默默填充来伪装成功。
- 调用方应重新 extract_fields 校验长度、条目顺序与未修改字段。

## 调用示意
```python
from python.archives.nekopack import build_pak, open_pak, read_member
from python.engines import nekosdk

archive = open_pak(pak_bytes)
script = read_member(pak_bytes, archive.entries[0])
fields = nekosdk.extract_fields(script)
# 筛选 name/message；选择项不在 fields 中。
result = nekosdk.replace_fields(script, {verified_field: encoded_translation})
rebuilt = build_pak({"script.txt": result})
```
- 空 fields 不等于该游戏没有文本；可能命令版本不同。
- 输入/输出均无文件访问，公共层负责安全写盘和归档。

## 部署与缺口
- 完成局部修改后用 `build_pak` 重建容器；成员顺序与名称必须与原始索引一致，否则游戏可能找不到资源。
- 本页没有提供通用补丁包名称或保证免封包可运行。
- 源未处理的选择项需要独立调查，不能交付时省略此事实。
- 测试合成了 display 命令、空隙、name/message 与不透明 choice 尾部。
- 验证变长时两个 length 正确，choice 原字节不丢，no-op 字节一致。
- 测试还拒绝错误 magic、超界长度和内嵌 NUL。
- 容器测试覆盖模式 A 往返、名称 checksum、成员滚动 key、模式 S 索引边界与越界拒绝：
  见 [test_neko_age_archives.py](../tests/test_neko_age_archives.py)。
- 无商业游戏样本、实际引擎运行或真实容器往返验证。
- 未实现日志/选择完整语义、模式 S 写回、未知命令重定位和字库修改。

## 来源与许可
- SExtractor commit `8d8d976fd04ae54e7c677705af937273d04a376a`。
- 来源：`src/extract_NekoSDK.py` 的 `readFileDataImp/parseImp/replaceOnceImp`。
- 另核实 `src/engine.ini` 对选择项及 CRLF 的警告。
- [固定源码](https://github.com/satan53x/SExtractor/blob/8d8d976fd04ae54e7c677705af937273d04a376a/src/extract_NekoSDK.py)。
- 容器线索：GARbro-Mod `bc26d991ef5cdc0e1ecb32122ee9a48c3375750c` 的 `ArcFormats/NekoSDK/ArcPAK.cs`。
- 容器实现另参考翻译肋手 v4.9D 的 `GameRes.NEKOSDK.ArcPAK`（GARbro 派生），独立改写为有界解析；
  其 `Pack` 写入的固定索引长度占位值不复制，由本模块按实际索引长度计算。
- GARbro 文件带 MIT 许可头；Python 改编按 SExtractor GPLv3 标 GPL-3.0-only。
- 详细验证与阶段清单见 [provenance](../provenance/sextractor-core.json)。
