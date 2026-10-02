# Silky / Silkys：MAP 全索引与 UTF-16 指针修复

## 能力边界
- 引擎 ID：`silky`。
- 参考模块：[python/engines/silky.py](../python/engines/silky.py)。
- 本实现专门处理 VN 对应的 `count + (index, absoluteOffset)[]` MAP。
- 不是 SExtractor 的四分区 MAP，也不是 Silkys/AI6WIN 的 MES。
- 在明确选择此方言后，支持空项、乱序索引、别名及变长文本回填。

## 识别证据
- `.map` 没有在此方言中被证明存在统一魔数，后缀不能独立认定格式。
- 文件首 u32 count 后应有 count 组各八字节的记录。
- 每组是原始 index 与绝对字符串位置。
- 字符串为 UTF-16LE，以对齐的双零码元结束。
- 所有指针应位于索引表之后、偶数字节对齐且处于文件范围内。
- 如果输入更符合四组 offset/count 的结构，应切换方言而非自动猜修。

## 格式方言与关键差异
- VN `SilkysMapScript` 是一张 count/index/offset 表。
- SExtractor `extract_Silky_map.py` 的 Manager 固定四个 section。
- 后者每个 section 有自己的 offset/count 和指针数组。
- 两者的索引布局不同，不能混用算法或共享一个无参数 reader。
- Silkys `.mes` 包含字节码、系统调用和跳转地址，又是另一类格式。
- 本参考不对三类文件做盲目的自动探测。

## 容器到剧本路线
1. 确认 ARC/MFG 等容器的实际索引和解码方案。
2. GARbro-Mod `ArcFormats/Silky/ArcARC.cs`、`ArcMFG.cs` 可作资源层线索。
3. 取出 MAP 后以全表合法性验证本方言，而非只抽第一条文本。
4. 保存原 row、index、offset 与原文件哈希。
5. 回填后重新读全表，核对所有项，包括没有翻译的空项。
- 不提供 ARC 封包器，也不承诺松散文件优先加载。

## 源码与算法对应
- 主来源：`VNTextPatch-net8`，MIT。
- 提交：`d9c0fab7b72fdcf87d674ef12a84d3829c9188be`。
- 路径：`VNTextPatch.Shared/Scripts/Silkys/SilkysMapScript.cs`。
- `Load/GetStrings` 证明 count/index/offset 与 UTF-16LE 字符串结构。
- `VNTextPatch.Shared/Util/BinaryPatcher.cs` 证明区间变化与地址映射思路。
- 对照来源：`SExtractor/src/extract_Silky_map.py` 的 Manager/Section。
- 对照提交：`8d8d976fd04ae54e7c677705af937273d04a376a`，GPL-3.0。
- 对照仅用于区分方言，Python 没有复用其 manager/global 状态。

## 不照搬 VN 的具体问题
- VN Load 只把非空字符串位置加入 `_messageOffsets`。
- WritePatched 最后却按 `_messageOffsets.Count` 更新表中前 N 个地址。
- 当原表中夹有空项时，这不等于全部真实指针位置。
- 某个前部文本增长后，后面的空项和非空项地址都可能需要变化。
- Python 保存每个表行并更新每一行，绝不使用过滤后计数代替原索引。
- 原 index 可不连续、可乱序；不能重新编号为 0..N-1。

## Python 接口与示例
```python
from python.engines.silky import read_map, patch_map
rows = read_map(data)
# 以原表行号选择，不以 rows[row].index 当作数组位置。
patched = patch_map(data, {rows[0].row: '变长文本'})
again = read_map(patched)
assert [r.index for r in again] == [r.index for r in rows]
```
- `read_map(bytes) -> tuple[Entry, ...]` 包括所有空项。
- `Entry` 保留 row、index、offset、end、text。
- `patch_map(bytes, {原表row: str}) -> bytes`。
- 没有修改时保留表、字符串、间隙和尾部字节。

## name / message 映射
- 原 MAP 表只提供 index 与文本，没有本地人物名类型标记。
- 不能把短字符串自动判断成人名，也不能把一个 index 当姓名 ID。
- 默认作为 message 候选；如有外部姓名上下文，应放只读元数据。
- 多个名字、同内容不同 row 和空字符串都必须保留身份。
- 别名意味着不同表行指向同一字符串地址，不等于可随意去重记录。

## 回填、长度与控制码
- 先按物理地址排序唯一字符串区间，再逐段复制及替换。
- 所有未知间隙和尾部保持原始 bytes，不扫描它们猜测隐藏指针。
- 最后按完整表行更新绝对 offset，原 index 不变。
- 共享地址要求所有别名的有效结果一致，部分改动导致冲突即拒绝。
- 内部/后缀指针被拒绝，避免指向变长字符串中间。
- UTF-16 终止检测按两字节对齐，不能用任意字节位置的双零搜索。
- 支持合法非 BMP 字符，拒绝孤立代理项、嵌入 NUL 和地址溢出。

## 部署条件
- 必须明确选择本文 MAP 方言，并独立确认没有额外隐藏地址表。
- MAP 编码可表达某个汉字，不等于运行时字体能显示该字形。
- 不改变未知控制文本约定，必要时在公共翻译层约束控制码。
- 文件写出、原包保护、路径与 manifest 均交由父 Skill。

## 验证与缺口
- 合成测试覆盖非连续 index、空项夹在中间、全指针增长修复。
- 覆盖表行物理乱序、尾部保留、非 BMP、别名冲突与一致别名。
- 覆盖内部指针、未终止串和空改动逐字节一致。
- 测试位置：`tests/test_engines_primary.py` 中 `SilkyTests`。
- 未实现四分区 MAP、MES VM 或加密归档。
- 没有商业素材和引擎运行测试，不能外推所有 Silkys 作品。
