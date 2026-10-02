# HCSystem / PACK

> 能力层级：`container-index-raw-pack`。这是独立算法参考，不是完整引擎支持承诺。

## 使用入口

- 模块：`python/archives/hcsystem.py`。
- 调用者显式传入 bytes / str；导入不读取文件、不启动游戏。
- 返回数据在内存中，路径检查与安全输出由调用方统一处理。

## 识别与版本证据

- 头部PACK、u32 count、索引加密标志；索引从0x0C开始。
- 每项0x4C字节，前0x40字节为UTF-16LE名字。
- 后面依次为未压缩长度、压缩长度、绝对offset。

## 从容器到脚本

- PAK → 根据标志交换索引nibble → 成员stored字节。
- packed_size=0表示无压缩；否则源码用4096字节、空格填充的LZSS。
- 参考只提供索引读取和raw包生成，不把压缩stored自动当明文。

## 对白与 name / message 映射

- UTF-16名字是archive member name，不能当角色name。
- 只有脚本成员经语法解析后才生成message；此目录的工具不提供该层。
- 非文本资源保持原始内容，不能一起用raw文本规则处理。

## 回填、偏移与控制码

- pack_raw写packed_size=0，依据所有名字和payload重算offset。
- 索引加密只交换每字节高低nibble，与CSTR文本池不是同一层。
- 名字最多31个UTF-16码元并留NUL；拒绝截断，避免同名碰撞。

## 部署先决条件

- raw分支兼容性来自上游工具，最终游戏接受性仍需验证。
- 压缩成员改成raw会变大；谨慎检查读取缓存和磁盘预算。

## 诚实边界

- 不支持本模块直接LZSS解码或脚本文本注入。
- 新包生成不是原压缩档的逐字节回放。

## Python 调用

在 skill 根目录可使用如下接口；变量均由调用方提供，示例不自动读写磁盘。

```python
from python.archives import hcsystem
entries = hcsystem.index(pak_bytes)
new_pak = hcsystem.pack_raw([('test.bin', b'synthetic')])
```

## 源码、许可与改写

- SExtractor 固定提交：`8d8d976fd04ae54e7c677705af937273d04a376a`。
- 参考改写按仓库 GPL-3.0-only 分发；许可文本和逐文件来源见 `provenance/tools-a.json`。
- 直接依据：`tools/HCSystem/hcsystem_pak_tool.py`。
- 源码符号：`crypt_index`, `read_index`, `build_index`, `cmd_pack`。
- GARbro-Mod 补充提交：`bc26d991ef5cdc0e1ecb32122ee9a48c3375750c`（文件头 MIT）。
- 补充结构来源：`ArcFormats/HCSystem/ArcPAK.cs`，不作为运行时导入。
- 改写去除路径/GUI/全局变量耦合，保留算法并增加严格边界；不加载.pyd或外部exe。

## 验证与交付检查

- 合成测试验证UTF-16名字、0x4C项宽、起点及nibble索引。
- 超长名字与截断头拒绝。
- 合成测试：`python -B -m unittest discover -s tests -p test_engines_tools_a.py -v`。
- 测试仅覆盖这里声明的算法层；上游真实样本成功数字不能代替本参考验证。
- 部署前还需空往返、字段范围、控制码与目标加载器核对；本次未启动商业游戏。
- 保留原始档备份，输出到新位置；归档成员名始终是不可信输入。
