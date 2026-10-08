# AGSI / SB2

> 能力层级：`script-pool-rebuild`。这是独立算法参考，不是完整引擎支持承诺。

## 使用入口

- 模块：`python/engines/agsi.py`。
- 调用者显式传入 bytes / str；导入不读取文件、不启动游戏。
- 返回数据在内存中，路径检查与安全输出由调用方统一处理。

## 识别与版本证据

- SB 文件魔数为 SB2 空格，固定头长 0x2C。
- 头部第3个u32为CODE字节数，第9个为CSTR条目数（从0计数）。
- 九段依次为 CODE、TTBL、两份FTBL、VTBL、CSTR、CDBL、两份DBG_。

## 从容器到脚本

- 外层资源包不在本模块范围；先取得完整SB2字节。
- split_sb2 根据各段专用记录数和长度读取，不能把段标签当搜索分隔符。
- CSTR先有count×8的offset/size表，再有nibble交换过的字符串池。

## PAK 归档格式资料

这是 GARbro-Mod 归档源码的布局补充，不改变现有 SB2 模块能力；没有随包 PAK reader/writer。来源和许可见 [记录](../provenance/garbro-archive-notes.json)。

`PACK` 头长 12 字节：`+4 i32 count`，`+8 i32 record_size`，条目长需大于 `0x10` 且不超过 `0x100`。索引从 12 开始，数据基址 `D=12+count*record_size`。条目前 16 字节依次为 `u32 unpacked_size, u32 stored_size, i32 method, u32 relative_offset`，随后 `record_size-16` 字节 CP932 NUL 名称；实际偏移为 `D+relative_offset`。

若原头不为 PACK，从文件倒数第 9、6 字节取 k1、k2；`shift=k2&7`，0 改为 1，对 12 字节依次 `rol8(byte,shift) XOR k1`，k1 每次加 1 并截为 u8。还原后必须匹配 PACK 和结构预算。加密索引用 seed=7524 的 GARbro MT，每字节取一次 u32 key，`shift=key&7`（0 改为 1），解密为 `rol8(byte,shift) XOR (key&255)`。

这里的 MT 初始化不是 Python `random.seed`：624 个 u32 状态，每轮取 seed 高 16 位，再执行 `seed=69069*seed+1`，拼接新 seed 高 16 位作为状态低 16 位，再推进一次 seed；全部 u32 溢出。状态更新采用 MT19937 的 M=397、`0x9908B0DF`，按数组原地顺序 twist；输出依次 XOR `>>11`、`<<7 & 0x9D2C5680`、`<<15 & 0xEFC60000`、`>>18`。不能换成不同播种算法的 MT。

| method | 解码 |
|---|---|
| 0 / 3 | stored / DES 后 stored |
| 1 / 4 | RLE / DES 后 RLE；**来源 RLE 实际未实现** |
| 2 / 5 | MSB 位流 LZ / DES 后 MSB 位流 LZ |
| 6 / 7 | 通常字节控制 LZSS / DES 后通常字节控制 LZSS |

DES 密钥为显式提供的 8 字节参数，不能依赖未随包的 GUI 方案数据库。采用 DES-ECB；成员尺寸大于 1024 时先解密 1032 字节，否则解密整个成员；输入必须符合 8 字节块边界。普通成员的解密前缀末 4 字节给出有效 header_size，校验它不超过解密缓冲和声明解压大小；剩余未加密尾部接到该前缀后，再按 method 解压。名为 `Copyright.Dat` 的结构分支用条目 unpacked_size 作为有效大小，不能把它当普通前缀拼接。

method 2/5 的窗口为 4096 个零字节，初始写入位置 1；MSB 先取 1 bit，1 为后续 8 bit literal，0 为 12 bit 窗口起点加 4 bit 长度，长度再加 2，环绕窗口逐字节重叠复制。method 6/7 的窗口初始为零、写位置 `0xFEE`，控制字节低位先读，1 为 literal，0 为两个字节 lo/hi，回指 `lo|((hi&0xF0)<<4)`，长度 `(hi&15)+3`。

有界实现须精确读取所有字段、验证输出长度、拒绝未知 method 和截断流。来源 `CanWrite=false`；SB2 字符串池能回写不代表 PAK 能回封。

## 对白与 name / message 映射

- Mess$is、MessC$s 是上游对白候选API；Cmd1$s至Cmd5$s对应选择。
- FTBL_1可提供API地址，82+u32是PUSH_STR，C6+u32是CALL；字节扫描不是完整反汇编。
- Talk$s、Voice$s不能自动当正式name；参考仅按已核准CSTR index注入。
- 调用方提供(index, 原文, 译文)，保留资源路径和变量字符串，不从所有CSTR猜台词。

## 回填、偏移与控制码

- 每条size含结尾NUL；offset以池首为基址，重建时按现有index顺序重新累计。
- 只交换字符串池的高低4bit，索引表不交换。
- 不改CODE，不增删CSTR；旧原文不匹配、内嵌NUL、共享index译文冲突一律拒绝。
- 上游inject会对重复冲突last-wins，本参考刻意收紧为错误。

## 部署先决条件

- 输入必须是本段顺序的SB2；已知非连续/别名池布局不自动推断。
- 严格cp932编码；换码页必须先确认字库和引擎读取能力。

## 诚实边界

- 不提供全VM解释、API上下文证明或外层包重新部署。
- 仅有合成段测试，不把上游真实样本报告算作本参考验证。

## Python 调用

在 skill 根目录可使用如下接口；变量均由调用方提供，示例不自动读写磁盘。

```python
from python.engines import agsi
new_sb = agsi.inject_sb2(sb_bytes, [(0, 'A', 'LONG')])
entries = agsi.read_cstr(cstr_bytes, count=2)
```

## 源码、许可与改写

- SExtractor 固定提交：`8d8d976fd04ae54e7c677705af937273d04a376a`。
- 参考改写按仓库 GPL-3.0-only 分发；许可文本和逐文件来源见 `provenance/tools-a.json`。
- 直接依据：`tools/AGSI/agsi_common.py`。
- 直接依据：`tools/AGSI/agsi_sb_tool.py`。
- 直接依据：`tools/AGSI/agsi_inject.py`。
- 源码符号：`swap_nibble_bytes`, `read_cstr_decode`, `rebuild_cstr_files`, `parse_segments`, `inject`。
- 改写去除路径/GUI/全局变量耦合，保留算法并增加严格边界；不加载.pyd或外部exe。

## 验证与交付检查

- 已测试CSTR offset/size、nibble自反、共享引用冲突、过期原文。
- 已测试SB2空注入逐字节一致、CODE和尾部保持及变长池重建。
- 合成测试：`python -B -m unittest discover -s tests -p test_engines_tools_a.py -v`。
- 测试仅覆盖这里声明的算法层；上游真实样本成功数字不能代替本参考验证。
- 部署前还需空往返、字段范围、控制码与目标加载器核对；本次未启动商业游戏。
- 保留原始档备份，输出到新位置；归档成员名始终是不可信输入。
