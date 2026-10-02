# Leaf / KCAP、SDT

> 能力层级：`container-index-raw-pack`。这是独立算法参考，不是完整引擎支持承诺。

## 使用入口

- 模块：`python/archives/leaf.py`。
- 调用者显式传入 bytes / str；导入不读取文件、不启动游戏。
- 返回数据在内存中，路径检查与安全输出由调用方统一处理。

## 识别与版本证据

- KCAP魔数及u32count；此变体每项36字节。
- u32flag、24字节名字、u32offset、u32size。
- 脚本候选为.sdt；Leaf存在多种包版本，不能由厂商名统配。

## 从容器到脚本

- KCAP → index返回stored与flag → 有压缩时需要LZSS块解码 → SDT VM。
- 压缩成员有packed_size/unpacked_size两DWORD子头；当前模块不解码该分支。
- pack_raw用于明文字节，flag固定0；SDT assembler/disassembler仅作为后续源码路线。

## 对白与 name / message 映射

- 归档名不是角色名；SDT须按具体opcode/操作数选择message和name。
- 不把资源名、跳转标签或整个SDT二进制作为翻译文本。
- 共享字符串引用需在脚本层处理，不能用容器偏移替代。

## 回填、偏移与控制码

- raw分支按当前名字和payload重算36字节索引及绝对offset。
- 名字最多23字节留NUL；不截断或替换非法字符。
- FFFFFFFF等不能凭直觉当删除标记；参考明确拒绝源码所见CCCCCCCC删除项。

## 部署先决条件

- 只有确认加载器支持flag=0时才考虑以raw替换压缩成员。
- 不提供可直接写入游戏目录的IO函数。

## 诚实边界

- 没有SDT全指令表和跳转重定位；未声称完整Leaf往返。
- 压缩档改raw不是byte-exact重压缩。

## Python 调用

在 skill 根目录可使用如下接口；变量均由调用方提供，示例不自动读写磁盘。

```python
from python.archives import leaf
entries = leaf.index(pak_bytes)
new_pak = leaf.pack_raw([('test.sdt', b'synthetic')])
```

## 源码、许可与改写

- SExtractor 固定提交：`8d8d976fd04ae54e7c677705af937273d04a376a`。
- 参考改写按仓库 GPL-3.0-only 分发；许可文本和逐文件来源见 `provenance/tools-a.json`。
- 直接依据：`tools/Leaf/pak_tool.py`。
- 源码符号：`parse_pak`, `extract_payload`, `lzss_literal_compress`。
- GARbro-Mod 补充提交：`bc26d991ef5cdc0e1ecb32122ee9a48c3375750c`（文件头 MIT）。
- 补充结构来源：`ArcFormats/Leaf/ArcPAK.cs`，不作为运行时导入。
- 改写去除路径/GUI/全局变量耦合，保留算法并增加严格边界；不加载.pyd或外部exe。

## 验证与交付检查

- 合成KCAP检查固定项宽、flag=0、绝对offset和payload。
- 缺头/截断目录拒绝。
- 合成测试：`python -B -m unittest discover -s tests -p test_engines_tools_a.py -v`。
- 测试仅覆盖这里声明的算法层；上游真实样本成功数字不能代替本参考验证。
- 部署前还需空往返、字段范围、控制码与目标加载器核对；本次未启动商业游戏。
- 保留原始档备份，输出到新位置；归档成员名始终是不可信输入。
