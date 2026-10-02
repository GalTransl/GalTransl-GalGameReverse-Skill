# M no Violet / DAT、CScript

## 模块分工

| 层 | 模块与接口 |
|---|---|
| 归档 | [archives/mnoviolet.py](../python/archives/mnoviolet.py)：`index` |
| 脚本 | [engines/mnoviolet.py](../python/engines/mnoviolet.py)：`script_header` |

按下述版本与阶段限制调用；成员 codec 或索引子集不等于完整解包器。

> 能力层级：`container-index-script-header`。这是独立算法参考，不是完整引擎支持承诺。

## 使用入口

- 模块：`python/engines/mnoviolet.py`。
- 调用者显式传入 bytes / str；导入不读取文件、不启动游戏。
- 返回数据在内存中，路径检查与安全输出由调用方统一处理。

## 识别与版本证据

- DAT无固定魔数，u32count后为固定宽名字及size/offset。
- 只接受100、68、44字节三种名字字段，且首offset需等于完整目录末尾。
- 若有多个宽度满足条件会拒绝歧义，而非按猜测顺序接受。

## 从容器到脚本

- DAT → name_width与stored列表 → 脚本24字节压缩头 → 另解LZSS → VM。
- 支持的脚本头前16字节为0，随后packed_size、unpacked_size。
- script_header只验证/拆头，不把压缩字节当已解码正文。

## 对白与 name / message 映射

- 上游mnv_script有更高层VM路线；本参考不导入它或附带的游戏script.dat。
- 归档名字不是角色name；opcode识别后才可分类message。
- 保持成员次序和原变量，不从资源命名猜角色映射。

## 回填、偏移与控制码

- 此模块未实现DAT重新打包或VM组装；返回bytes有明确stored标记。
- 目录宽度和offset不能因翻译后名字变化而自动扩展。
- 脚本压缩长度应等于存储长度减24，拒绝截断或额外字节。

## 部署先决条件

- 本源码LZSS字典初始零、写指针0xFEE；若补解码需沿用该配置。
- 未加载目录随附的商业游戏script.dat与script_info.dat。

## 诚实边界

- 不把与CScript的别名关系当作所有格式都等同。
- 没有完整文本往返与引擎启动验证。

## Python 调用

在 skill 根目录可使用如下接口；变量均由调用方提供，示例不自动读写磁盘。

```python
from python.engines import mnoviolet
from python.archives import mnoviolet as mnoviolet_archive
name_width, entries = mnoviolet_archive.index(dat_bytes)
compressed, size = mnoviolet.script_header(script_stored)
```

## 源码、许可与改写

- SExtractor 固定提交：`8d8d976fd04ae54e7c677705af937273d04a376a`。
- 参考改写按仓库 GPL-3.0-only 分发；许可文本和逐文件来源见 `provenance/tools-a.json`。
- 直接依据：`tools/MnoViolet/mnv_tool.py`。
- 源码符号：`find_name_size`, `read_entries`, `is_script_payload`。
- GARbro-Mod 补充提交：`bc26d991ef5cdc0e1ecb32122ee9a48c3375750c`（文件头 MIT）。
- 补充结构来源：`ArcFormats/MnoViolet/ArcMnoViolet.cs`，不作为运行时导入。
- 改写去除路径/GUI/全局变量耦合，保留算法并增加严格边界；不加载.pyd或外部exe。

## 验证与交付检查

- 三种名字宽度均有合成索引测试。
- 24字节脚本头的尺寸检查和truncation拒绝已覆盖。
- 合成测试：`python -B -m unittest discover -s tests -p test_engines_tools_a.py -v`。
- 测试仅覆盖这里声明的算法层；上游真实样本成功数字不能代替本参考验证。
- 部署前还需空往返、字段范围、控制码与目标加载器核对；本次未启动商业游戏。
- 保留原始档备份，输出到新位置；归档成员名始终是不可信输入。
