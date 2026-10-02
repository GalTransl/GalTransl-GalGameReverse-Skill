# Melonpan / WCW TTD

## 模块分工

| 层 | 模块与接口 |
|---|---|
| 归档 | [archives/melonpan.py](../python/archives/melonpan.py)：`index` |
| 脚本 | [engines/melonpan.py](../python/engines/melonpan.py)：`script_xor` |

按下述版本与阶段限制调用；成员 codec 或索引子集不等于完整解包器。

> 能力层级：`container-index-script-xor`。这是独立算法参考，不是完整引擎支持承诺。

## 使用入口

- 模块：`python/engines/melonpan.py`。
- 调用者显式传入 bytes / str；导入不读取文件、不启动游戏。
- 返回数据在内存中，路径检查与安全输出由调用方统一处理。

## 识别与版本证据

- WCW前三字节签名，+4是count，+8保留字段；索引从12开始。
- 每项size、offset、unknown各u32，再跟统一固定宽名字。
- 记录宽度=(首payload偏移-12)/count；必须整除且边界有效。

## 从容器到脚本

- TTD → 索引及stored → 若DSFF头则另解LZSS → 已确认剧本再XOR FF。
- GARbro对应实现实际在Legacy/Melonpan，不是ArcFormats/Morning的.FRC格式。
- DSFF长8字节，LZSS初始写指针0xFF0，与通用0xFEE不同。

## 对白与 name / message 映射

- 名字字段是资源名，不是对白name；XOR解壳并不提供脚本语义。
- name/message需要已确认的剧本命令规则，不能直接把所有文本串视作台词。
- unknown字段不可根据看起来像数字就改写。

## 回填、偏移与控制码

- index只提取存储切片，保留unknown与name_width便于后续重建。
- script_xor明确用于已确认脚本层，操作自反，不能对整个TTD乱套。
- 参考没有重压缩DSFF或回封TTD；上游packer需要原档保存字段。

## 部署先决条件

- 首次offset推断只能在整个目录都通过边界检查后接受。
- 没有压缩库依赖，不调用上游全目录写文件接口。

## 诚实边界

- 不能把同扩展名Morning TTD套用此实现。
- 未声称完成脚本文本往返和部署。

## Python 调用

在 skill 根目录可使用如下接口；变量均由调用方提供，示例不自动读写磁盘。

```python
from python.engines import melonpan
from python.archives import melonpan as melonpan_archive
entries = melonpan_archive.index(ttd_bytes)
plain_script = melonpan.script_xor(confirmed_script_bytes)
```

## 源码、许可与改写

- SExtractor 固定提交：`8d8d976fd04ae54e7c677705af937273d04a376a`。
- 参考改写按仓库 GPL-3.0-only 分发；许可文本和逐文件来源见 `provenance/tools-a.json`。
- 直接依据：`tools/Melonpan/ttd_pack.py`。
- 直接依据：`tools/Melonpan/xorff.py`。
- 源码符号：`parse_ttd`, `xor_file`。
- GARbro-Mod 补充提交：`bc26d991ef5cdc0e1ecb32122ee9a48c3375750c`（文件头 MIT）。
- 补充结构来源：`Legacy/Melonpan/ArcTTD.cs`，不作为运行时导入。
- 改写去除路径/GUI/全局变量耦合，保留算法并增加严格边界；不加载.pyd或外部exe。

## 验证与交付检查

- 独立合成WCW验证宽度推导、unknown保留与payload切片。
- XOR已验证固定字节向量，目录越界拒绝。
- 合成测试：`python -B -m unittest discover -s tests -p test_engines_tools_a.py -v`。
- 测试仅覆盖这里声明的算法层；上游真实样本成功数字不能代替本参考验证。
- 部署前还需空往返、字段范围、控制码与目标加载器核对；本次未启动商业游戏。
- 保留原始档备份，输出到新位置；归档成员名始终是不可信输入。
