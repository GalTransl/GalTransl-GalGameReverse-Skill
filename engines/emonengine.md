# EmonEngine / EME

> 能力层级：`script-container-pack`。这是独立算法参考，不是完整引擎支持承诺。

## 使用入口

- 模块：`python/archives/emonengine.py`。
- 调用者显式传入 bytes / str；导入不读取文件、不启动游戏。
- 返回数据在内存中，路径检查与安全输出由调用方统一处理。

## 识别与版本证据

- 头部RREDATA 空格，末4字节是成员数。
- 尾部count×0x60索引之前有40字节密钥区。
- 此参考仅处理全零密钥、Subtype=3的剧本分支。

## 从容器到脚本

- 已确认的明文脚本 → 全字面量LZSS → 12字节零子头 → EME文件。
- 0x40..0x43记录frame=0x1000及init-distance=0x12。
- GARbro换算写指针为frame-init=0xFEE；未实现加密索引。

## 对白与 name / message 映射

- EME名字是资源名，不是角色name；内部脚本仍需专门文本解析。
- 保留输入成员次序，不把图片音频当Subtype=3打包。
- 参考不会从脚本二进制中猜测message。

## 回填、偏移与控制码

- 索引+0x4C为压缩长度，+0x50为明文长度，+0x54为12字节子头起点。
- 压缩长度不含12字节子头，后续offset必须包含子头总开销。
- 全字面量1-bit标志替换.pyd压缩依赖，保持合法流而非相同压缩字节。

## 部署先决条件

- 生成零密钥档需目标加载器支持该路径；不能推断所有游戏均接受。
- 分段脚本压缩、非零密钥、图片音频及其它Subtype不在支持范围。

## 诚实边界

- 没有全EME解密器，zero_key_index只检查本子集。
- 档案可增大，缓冲区和部署接受性尚未实机验证。

## Python 调用

在 skill 根目录可使用如下接口；变量均由调用方提供，示例不自动读写磁盘。

```python
from python.archives import emonengine
archive = emonengine.pack_scripts([('test.bin', b'synthetic')])
records = emonengine.zero_key_index(archive)
```

## 源码、许可与改写

- SExtractor 固定提交：`8d8d976fd04ae54e7c677705af937273d04a376a`。
- 参考改写按仓库 GPL-3.0-only 分发；许可文本和逐文件来源见 `provenance/tools-a.json`。
- 直接依据：`tools/EmonEngine/eme_pack.py`。
- 源码符号：`Arc.pack`, `Arc.encrypt`。
- GARbro-Mod 补充提交：`bc26d991ef5cdc0e1ecb32122ee9a48c3375750c`（文件头 MIT）。
- 补充结构来源：`ArcFormats/EmonEngine/ArcEME.cs`，不作为运行时导入。
- 改写去除路径/GUI/全局变量耦合，保留算法并增加严格边界；不加载.pyd或外部exe。

## 验证与交付检查

- 合成测试核对Subtype、起点、子头与未压缩长度。
- 生成流经独立的LZSS reader还原；非零密钥会拒绝。
- 合成测试：`python -B -m unittest discover -s tests -p test_engines_tools_a.py -v`。
- 测试仅覆盖这里声明的算法层；上游真实样本成功数字不能代替本参考验证。
- 部署前还需空往返、字段范围、控制码与目标加载器核对；本次未启动商业游戏。
- 保留原始档备份，输出到新位置；归档成员名始终是不可信输入。
