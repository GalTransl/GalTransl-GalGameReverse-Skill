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
