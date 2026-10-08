# 脚本与字库格式研究资料

以下补充来自用户提供的工程备忘录，按格式改写，出处、源文件哈希和纠错记录见[来源清单](../provenance/translation-engineering-notes.json)。除注明与随包算法交叉核对的部分外，仅为文档证据；没有据此新增运行代码、真实样本往返或游戏验证。

| 格式与入口 | 新增资料 | 实现边界 |
|---|---|---|
| [GLib / BCS、GMS、FDT2](../engines/glib/formats.md) | 三层布局、池校验、压缩读取预算、位图字库 | 归档有 GARbro 算法资料；脚本与字库无随包 reader/writer |
| [ISM / ISA、脚本](../engines/ism/formats.md) | 归档版本冲突、入口/switch/姓名引用、变长外壳 | 缺完整 VM 与脚本 codec 定义 |
| [Kogado / IN10、KGO](../engines/kogado/in10.md) | 三段、栈引用、Text/Ruby/Select、等待与文本槽 | 缺完整 opcode 和记录定义 |
| [TUITUI / SPT60、SBY、FF DAT](../engines/tuitui/spt60.md) | 入口与变长指令、4bpp 字库、保护区域 | 缺表达式指令集及 DAT RLE 定义 |
| [KAAS / ID](../engines/kaas/id.md) | 表索引 VM、u16 文本、正文/选项分隔 | 字节序例子已纠错，完整 VM 及控制布局待核 |
| [CD / RIO 路线](../engines/xuse/cd.md) | 分离 sub_block、长签名、XOR53、尾 MD5 | 来源归类为 XUSE，实际家族须按结构核对；不同于 GD/DLL |
| [Triangle / SD](../engines/triangle.md#整文件-vm-研究条件) | 读取 helper、条件表、嵌入数据边界 | 现有 Python 只支持孤立文本/选项指令 |
| [ICE / 字表](../engines/ice.md#字表与显示链研究条件) | 字表端序、缓冲容量、多渲染器一致性 | 现有 Python 仅 token codec，不扩字表或改 EXE |
| [MED / 加密成员](../engines/med/encrypted-members.md) | Fudegaki 相位、已知明文候选与共享池隔离 | 当前工作流仍只支持明文 MDN0 profile |
| [Malie / EXEC](../engines/malie/exec-research.md) | PE 外壳、UTF-16 控制、常量池引用升级 | 现有 Python 仅页内声明的明文消息池重建 |

共用规则见[VM 分析](../guides/vm-analysis.md)、[分行与字节预算](../guides/encoding-and-control-codes.md#分行策略与字节预算)及[结构覆盖检查](../guides/validation-and-deployment.md#提取合理性与结构覆盖)。按候选格式读取，不要求每次任务浏览全部研究页。新增格式实现须补齐当前样本证据及有界正反例，不能以本表或来源中的工具名代替算法。
