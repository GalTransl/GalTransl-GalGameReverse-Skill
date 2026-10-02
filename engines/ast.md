# AST / ARC1、ARC2

> 能力层级：`container-index`。这是独立算法参考，不是完整引擎支持承诺。

## 使用入口

- 模块：`python/archives/ast.py`。
- 调用者显式传入 bytes / str；导入不读取文件、不启动游戏。
- 返回数据在内存中，路径检查与安全输出由调用方统一处理。

## 识别与版本证据

- 识别ARC1或ARC2魔数，随后u32成员数。
- 索引变长：u32绝对offset、u32未压缩size、u8名字字节数、cp932名字。
- ARC2名字逐字节XOR FF；ARC1名字不作该变换。

## 从容器到脚本

- dat等容器 → index() → 原存储payload及声明解压长度。
- tools列出.adv、.anm、.db需压缩，正文先XOR FF再LZSS。
- GARbro补充ARC2解压环初始填FF，解压后再XOR FF；PNG另有壳处理。

## 对白与 name / message 映射

- 参考返回容器成员，不把.adv全文件当一条message。
- 语句命令、参数、说话人绑定须由对应AST文本规则识别；该目录没有VM文本解析。
- name目前仅表示archive member name，不是角色名。

## 回填、偏移与控制码

- stored保持压缩字节，不能对它直接做cp932替换。
- 真实封包必须重算变长索引及成员起点；本模块未提供封包器。
- 按相邻offset求存储长度，末项到EOF；不把未压缩size用作磁盘切片长度。

## 部署先决条件

- 参考采用严格连续、单调有效offset子集；GARbro的零offset空槽不在范围。
- 不依赖上游pylzss旧版本，因本模块只实现索引。

## 诚实边界

- 并未实现AST压缩/编码层，不能把返回stored称为明文。
- 不是完整AST文本往返插件。

## Python 调用

在 skill 根目录可使用如下接口；变量均由调用方提供，示例不自动读写磁盘。

```python
from python.archives import ast
entries = ast.index(archive_bytes)
stored = entries[0]['stored']
```

## 源码、许可与改写

- SExtractor 固定提交：`8d8d976fd04ae54e7c677705af937273d04a376a`。
- 参考改写按仓库 GPL-3.0-only 分发；许可文本和逐文件来源见 `provenance/tools-a.json`。
- 直接依据：`tools/AST/arc2_pack.py`。
- 源码符号：`pack`, `xorBytes`。
- GARbro-Mod 补充提交：`bc26d991ef5cdc0e1ecb32122ee9a48c3375750c`（文件头 MIT）。
- 补充结构来源：`ArcFormats/ArcAST.cs`，不作为运行时导入。
- 改写去除路径/GUI/全局变量耦合，保留算法并增加严格边界；不加载.pyd或外部exe。

## 验证与交付检查

- 合成ARC2索引验证名字XOR、绝对offset和未压缩size分离。
- 缺头/越界索引会拒绝。
- 合成测试：`python -B -m unittest discover -s tests -p test_engines_tools_a.py -v`。
- 测试仅覆盖这里声明的算法层；上游真实样本成功数字不能代替本参考验证。
- 部署前还需空往返、字段范围、控制码与目标加载器核对；本次未启动商业游戏。
- 保留原始档备份，输出到新位置；归档成员名始终是不可信输入。
