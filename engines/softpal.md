# Softpal：PAC 解包与 Sv20 / TEXT.DAT / POINT.DAT

## 能力边界
- 引擎 ID：`softpal`。
- 参考模块：[python/engines/softpal.py](../python/engines/softpal.py)。
- 归档模块：[python/archives/softpal.py](../python/archives/softpal.py)，支持 PAC v1 两种名字宽度及 Amuse Craft `PAC ` v2；VAFS 尚未实现。
- 实现已知文本操作数读取、POINT 标签换算、TEXT 追加与操作数更新。
- 文本操作数由调用者的完整反汇编提供，不是本模块扫描猜测出来。
- 不支持任意 Sv20 VM、加密 TEXT 或无证据的双文件改写。

## 识别证据
- 代码文件以 `Sv20` 开头，VN 入口扩展名为 `.src`。
- `script.src` 是常见代码文件名；同目录 `TEXT.DAT` 与 `POINT.DAT` 是必需的配套证据。必须核对实际头部与引用，不能只按文件名判定，也不能丢失文本表和地址表。
- `POINT.DAT` 开头 16 字节为 `$POINT_LIST_****`。
- 正文通常不直接存于 SRC，而由 SRC 的地址操作数引用 TEXT。
- 缺少配套文件时应报告材料不足，不能把 SRC 字节扫成假文本。
- 后缀 DAT 通用性很高，不是 Softpal 唯一标志。

## 格式方言
- Sv20 代码基址为 0x0C。
- POINT 头后是 u32 代码相对标签；VN 读取后加 0x0C 并反序。
- 文本操作数指向 TEXT 内的一条记录起点。
- 记录起点后有四字节元数据，真正 cstring 从 `address + 4` 开始。
- 正文换行为 `<br>`。
- Python 只接受 TEXT 首字节 `_` 的明确未加密形式。
- VN 会把该字节直接改成 `_`；这不是可泛化的解密证明。
- 本参考不会仅修改标志就宣称已解密。

## 容器到剧本路线
1. 根据容器证据确认 PAC/VAFS 或外置资源路线。
2. PAC 使用本页只读接口；GARbro-Mod `ArcFormats/Softpal/ArcPAC.cs` 为已移植来源，`ArcVAFS.cs` 仍仅作线索。
3. 同一来源批次提取 SRC、TEXT、POINT，保持文件关联。
4. 先验证 POINT 标签，再对 SRC 全量反汇编找出真实文字操作数。
5. 将批准的操作数及角色结构交给本参考局部算法。
- 不接受来自不同游戏版本或不同归档批次的三份配套文件。
- 三份文件必须作为一组记录原始哈希和部署目标。

## PAC 索引与成员外壳

| 参数 | 签名与 count | 目录起点 | 固定名字宽度 |
|---|---|---|---|
| `version=1, name_size=16` | 无魔数，`u32 count` 在 0 | `0x3FE` | 16 字节 |
| `version=1, name_size=32` | 同上 | `0x3FE` | 32 字节 |
| `version=2` | `PAC `，`u32 count` 在 8 | `0x804` | 32 字节 |

目录项为固定宽度名字、`u32 stored_size`、`u32 absolute_offset`，默认严格 CP932。首成员偏移必须等于 `index_start + count * (name_size + 8)`，其余项逐一检查放置范围；版本、布局、名字、条目数和目录预算同时成立才返回。旧格式没有魔数，不自动套上其他引擎的 PAC。

```python
from pathlib import Path
from python.archives.softpal import read_index, read_member, decode_member

with Path("game/data.pac").open("rb") as stream:
    index = read_index(stream, version=2)
    paired = [e for e in index.entries
              if e.name.upper() in ("SCRIPT.SRC", "TEXT.DAT", "POINT.DAT")]
    # 本例只取 stored；保持同一归档和成员身份，单独核对每个外壳。
    originals = {e.name: read_member(stream, index, e, max_stored_size=64 << 20)
                 for e in paired}
```

- `read_index` 只读头部和目录，跳过头部保留区，不读取大资源正文；默认 `max_entries=100000`、`max_index_size=16 MiB`（含保留区）。两个流接口恢复位置并支持短读。
- `read_member` 返回 stored bytes，不依据首字节或扩展名自动解密。成员必须是该索引的原对象，读取时检查文件大小未变；同大小修改不会被发现，调用者须保持归档不变。
- `decode_member(stored, codec="raw")` 原样返回；`codec="script-dollar"` 仅用于已证明是非图片/音频的 `$` 脚本成员。上游按资源类型过滤，本实现由调用者明确选择，避免误改 `$` 开头的资源。
- `script-dollar` 保留前 16 字节；之后每个完整小端 u32 的最低字节先 ROL8，shift 从 4 开始逐组加 1（模 8），再把整个 u32 XOR `0x084DF873 ^ 0xFF987DEE = 0xF7D5859D`；不足四字节的尾部原样保留。默认 `max_output_size=64 MiB`。
- 该解码**保留 `$` 头标志**，不自动将 TEXT.DAT 的首字节改成 `_`。现有脚本接口仅接受已证明的 `_` 明文方言；不能靠改标志让它通过检查，必须另外证明 TEXT 布局/加密状态与完整 VM 操作数。
- 批量选取配套文件也须检查缺失/同名/来源，按剩余总预算逐项读取和解码；归档接口不写盘，使用公共 `write_new_tree` 输出到新目录。

没有 PAC writer、VAFS/音频重建或完整 Sv20 反汇编。来源及 MIT 声明见 [common-archives-v1.json](../provenance/common-archives-v1.json)，[合成测试](../tests/test_archives_common_engines.py)覆盖三个 PAC 布局、多字节名、`$` 固定向量、轮转计数回绕、原头尾保留及异常/预算拒绝；未做真实 PAC 游戏样本和运行验证。

## 源码与算法对应
- 来源：`VNTextPatch-net8`，MIT。
- 提交：`d9c0fab7b72fdcf87d674ef12a84d3829c9188be`。
- 路径：`VNTextPatch.Shared/Scripts/Softpal/SoftpalScript.cs`。
- `ReadPointDat` 对应标签解析与反序。
- `GetStrings` 对应 operand -> TEXT address+4 与 `<br>` 转换。
- `WritePatched` 对应追加四字节零元数据、字符串、改写代码地址。
- `SoftpalDisassembler.cs` 提供 CodeOffset 及 VM 上下文寻找字符串的证据。
- 本 Python 不移植其栈、变量和用户函数识别，不隐瞒此缺口。

## Python 接口与示例
```python
from python.engines.softpal import read_text_records, append_text_records
# operands 必须由完整 disassembler 证明，而非搜索 TEXT 地址获得。
operands = ((12, 'message'), (16, 'context_name'))
records = read_text_records(code, text_dat, operands)
new_code, new_text, same_point = append_text_records(
    code, text_dat, point_dat, operands, {12: '新正文\n第二行'})
assert same_point == point_dat
```
- `point_labels(bytes, code_size) -> tuple[int, ...]`。
- `read_text_records` 返回 operand、kind、address、text。
- `append_text_records` 返回新的三个内存对象，不修改磁盘。
- replacements 的键是原代码文件的操作数字节位置。

## name / message 映射
- role 接收 name、message、choice、context_name。
- role 必须来自真实指令上下文，不按字符串内容长度推断。
- context_name 保留在读取结果但禁止回填。
- `$str20` 类名字变量也禁止变为显示名。
- 一个 TEXT 地址被多个引用共享时，各引用身份仍然独立保留。
- 某条正文改动采用新记录，不意外修改共享地址的另一条名字或正文。
- 多人名应保存在调用层上下文列表，不使用单个字符串覆盖其来源。

## 回填、长度与偏移
- 保留原 TEXT 所有 bytes，在尾部追加新记录。
- 新记录为 u32 零值 + 严格编码 cstring。
- SRC 中只有指定的四字节地址操作数变化，代码长度不变。
- POINT 原样返回，标签无需因文本长度增长重新定位。
- 正文实际换行转换成 `<br>`，不做自动排版。
- 拒绝未知角色、重复/重叠操作数、越界地址和未终止字符串。
- 拒绝 NUL、不兼容 cstring 编码与 u32 地址溢出。
- 不保证未提供的操作数清单完整；该证明明确由调用层承担。

## 部署条件
- 新 SRC 必须与新 TEXT 同时部署，不能只替换其中一个。
- POINT 虽然不变也应纳入原版本校验，防止跨版本混用。
- 若 TEXT 实际加密，先单独证明解码及重新编码要求。
- 原版可能缓存资源；应验证确实加载新配套文件。
- 输出事务、备份、回滚、manifest 与路径安全由父 Skill 公共层实现。
- 模块不运行游戏，不下载字库，不调用原库插件。

## 验证与缺口
- 合成测试验证 POINT 反序和 0x0C 基址。
- 验证追加记录地址、原 TEXT 前缀不变、未改操作数不变。
- 验证 `<br>` 与显示换行的往返。
- 验证 context_name、未证明操作数和加密标志输入的拒绝。
- 测试位置：`tests/test_engines_primary.py` 中 `SoftpalTests`。
- 尚未实现完整 VM、用户消息函数识别、加密文本或资源封包。
- 局部算法通过不代表操作数清单正确，不能宣称全量 writer。
- 没有商业素材、外部工具或运行时验证。
