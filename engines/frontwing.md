# FrontWing / FRONTWING_ADV CSB

> 能力层级：`script-node-rebuild`。这是独立算法参考，不是完整引擎支持承诺。

## 使用入口

- 模块：`python/engines/frontwing.py`。
- 调用者显式传入 bytes / str；导入不读取文件、不启动游戏。
- 返回数据在内存中，路径检查与安全输出由调用方统一处理。

## 识别与版本证据

- CSB小端魔数0x63736200，对应字节00 62 73 63。
- +4为header_size，+8为node_count；节点8字节头。
- 节点含u16 type、u16 argc、4字节未知字段，再跟u16长度前缀参数。

## 从容器到脚本

- 外层资源包需独立核准；不同FrontWing包格式不可互换。
- 本参考从CSB明文字节开始，按node_count顺序读参数。
- 原节点头的4字节未知值和文件尾保留，不像上游builder统一写零。

## 对白与 name / message 映射

- 0x16 SET且参数0为$Msg时，参数1是message。
- 往前最多7节点找$Name SET，获得name候选；这是上游启发，不是控制流证明。
- $str20等变量名字保持变量，不改写成人名。
- 上游还识别system\DoSelect调用；本参考未实现选择肢或name注入。

## 回填、偏移与控制码

- 按节点index回填$Msg参数，重算u16字符串长度，不增加节点。
- 保留原字符串是否以NUL结束；拒绝内嵌NUL和65535字节溢出。
- 不全局替换相同字节；非$Msg节点拒绝作为目标。

## 部署先决条件

- 严格cp932；切换gbk需要字库与解释器先决证据。
- 变量/表达式型$Msg需要更丰富语法识别，不应直接翻译。

## 诚实边界

- name回溯只是候选；没有整VM跳转或分支求值。
- 不覆盖FrontWing所有年代/引擎。

## Python 调用

在 skill 根目录可使用如下接口；变量均由调用方提供，示例不自动读写磁盘。

```python
from python.engines import frontwing
rows = frontwing.extract(csb_bytes)
new_csb = frontwing.replace_messages(csb_bytes, {1: 'synthetic'})
```

## 源码、许可与改写

- SExtractor 固定提交：`8d8d976fd04ae54e7c677705af937273d04a376a`。
- 参考改写按仓库 GPL-3.0-only 分发；许可文本和逐文件来源见 `provenance/tools-a.json`。
- 直接依据：`tools/FrontWing/csb_extract.py`。
- 直接依据：`tools/FrontWing/csb_inject.py`。
- 源码符号：`parse_csb`, `extract`, `build_csb`, `inject`。
- GARbro-Mod 补充提交：`bc26d991ef5cdc0e1ecb32122ee9a48c3375750c`（文件头 MIT）。
- 补充结构来源：`ArcFormats/FrontWing/ArcDAT.cs`，不作为运行时导入。
- 改写去除路径/GUI/全局变量耦合，保留算法并增加严格边界；不加载.pyd或外部exe。

## 验证与交付检查

- 合成CSB测试$Msg定位、$str20保留、未知字段和尾部保留。
- 空回填byte-exact，变长参数和错误节点拒绝已测试。
- 合成测试：`python -B -m unittest discover -s tests -p test_engines_tools_a.py -v`。
- 测试仅覆盖这里声明的算法层；上游真实样本成功数字不能代替本参考验证。
- 部署前还需空往返、字段范围、控制码与目标加载器核对；本次未启动商业游戏。
- 保留原始档备份，输出到新位置；归档成员名始终是不可信输入。
