# ARCX 工具目录 / SCX.ARC 顺序记录

> 能力层级：`container-unpack`。这是独立算法参考，不是完整引擎支持承诺。

## 使用入口

- 模块：`python/archives/arcx.py`。
- 调用者显式传入 bytes / str；导入不读取文件、不启动游戏。
- 返回数据在内存中，路径检查与安全输出由调用方统一处理。

## 识别与版本证据

- tools脚本只跳过16字节头，并未校验魔数；不能凭目录名伪造识别结论。
- 必须显式传variant='tools-sequential'，由调用方确认来源及布局。
- GARbro的ARCX魔数对应固定100字节文件名+28字节字段索引，不是tools的顺序记录布局。

## 从容器到脚本

- SCX.ARC → 顺序成员头 → 有名资源块 → 可选LZSS → 明文字节。
- 每个记录有total_size、name_len、header_size、packed_size、unpacked_size五个u32。
- 压缩标志在记录+0x1B；下一记录地址=当前地址+total_size。

## 对白与 name / message 映射

- 该工具仅证实容器和压缩层；解封出的文本还需对应脚本语法解析。
- 文件名和内容均不自动认作name/message；不得把路径或标签送去翻译。
- 上层用稳定成员序号和脚本内定位键关联译文。

## 回填、偏移与控制码

- LZSS使用4096字节环、初始写指针0xFEE、低位优先控制位，1为字面量。
- 回引用offset=lo|((hi&0xF0)<<4)，长度=(hi&15)+3，支持重叠复制。
- libs/lzss/lzss.c确认Padding=0；不加载同目录.pyd。
- 参考实现只解封；完整回封还需保留原16字节头及更新三种长度字段。

## 部署先决条件

- 压缩总输出默认限制64MiB，可由调用方显式调整。
- 越界记录、截断token、超出声明长度及尾随压缩数据报错，不回退成伪明文。

## 诚实边界

- 不声称兼容GARbro固定索引变体或所有同名ARC。
- 当前未实现SCX指令解析及引擎部署验证。

## Python 调用

在 skill 根目录可使用如下接口；变量均由调用方提供，示例不自动读写磁盘。

```python
from python.archives import arcx
members = arcx.unpack(archive_bytes, variant='tools-sequential')
plain = arcx.lzss(b'\x03AB\xEE\xF3', 8)
```

## 源码、许可与改写

- SExtractor 固定提交：`8d8d976fd04ae54e7c677705af937273d04a376a`。
- 参考改写按仓库 GPL-3.0-only 分发；许可文本和逐文件来源见 `provenance/tools-a.json`。
- 直接依据：`tools/ARCX/arc_unpack.py`。
- 直接依据：`tools/ARCX/arc_pack.py`。
- 直接依据：`libs/lzss/lzss.c`。
- 源码符号：`unpack_arc_file`, `pack_arc`, `lzss_decompress`, `Padding`。
- GARbro-Mod 补充提交：`bc26d991ef5cdc0e1ecb32122ee9a48c3375750c`（文件头 MIT）。
- 补充结构来源：`ArcFormats/ArcARCX.cs`，不作为运行时导入。
- 补充结构来源：`ArcFormats/LzssStream.cs`，不作为运行时导入。
- 改写去除路径/GUI/全局变量耦合，保留算法并增加严格边界；不加载.pyd或外部exe。

## 验证与交付检查

- 合成测试包含字面量、初始零字典、重叠回引用与尺寸上限。
- 合成顺序资源记录可解封；错误变体显式拒绝。
- 合成测试：`python -B -m unittest discover -s tests -p test_engines_tools_a.py -v`。
- 测试仅覆盖这里声明的算法层；上游真实样本成功数字不能代替本参考验证。
- 部署前还需空往返、字段范围、控制码与目标加载器核对；本次未启动商业游戏。
- 保留原始档备份，输出到新位置；归档成员名始终是不可信输入。
