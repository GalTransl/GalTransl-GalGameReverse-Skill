# NEJII / CDT、144字节BIN

## 模块分工

| 层 | 模块与接口 |
|---|---|
| 归档 | [archives/nejii.py](../python/archives/nejii.py)：`index`、`pack_raw` |
| 脚本 | [engines/nejii.py](../python/engines/nejii.py)：`extract_records`、`replace_record` |

按下述版本与阶段限制调用；成员 codec 或索引子集不等于完整解包器。

> 能力层级：`container-raw-pack-fixed-record-text`。这是独立算法参考，不是完整引擎支持承诺。

## 使用入口

- 模块：`python/engines/nejii.py`。
- 调用者显式传入 bytes / str；导入不读取文件、不启动游戏。
- 返回数据在内存中，路径检查与安全输出由调用方统一处理。

## 识别与版本证据

- CDT尾部12字节为RK1 NUL、count、index_offset；不是文件头魔数。
- 每项32字节：16字节ASCII名、packed_size、unpacked_size、flag、offset。
- 脚本BIN由144字节定长记录组成，余数字节拒绝。

## 从容器到脚本

- CDT → stored成员 → 若压缩需另解LZSS → BIN记录。
- 参考提供raw归档生成、目录解析及明确文本opcode的记录提取。
- 早期cdt_pack只针对图片；文本路线由同目录nejii_tool额外确认。

## 对白与 name / message 映射

- 64为dialog、6A为name、69为chapter，正文从记录+1开始。
- name只与最多5条记录后的下一dialog配对，配对后清空；是源码启发。
- 上游选择肢在+65使用启发识别，本参考不猜该分支。

## 回填、偏移与控制码

- dialog正文槽129字节，name/chapter槽143字节；保留终止NUL空间。
- replace_record只更新该槽，dialog+130的换行flag及其后控制字段不变。
- 超长译文拒绝，不继承上游截断字符串的策略，也不变动总记录数。

## 部署先决条件

- cp932默认严格；使用gbk前必须验证目标字体/编码。
- 压缩成员reader未实现，stored不是明文；raw封包须确认目标支持。

## 诚实边界

- name回溯不是控制流证明；不支持全部选择/章节语义。
- 固定槽回填不能让译文无限增长。

## Python 调用

在 skill 根目录可使用如下接口；变量均由调用方提供，示例不自动读写磁盘。

```python
from python.engines import nejii
from python.archives import nejii as nejii_archive
rows = nejii.extract_records(bin_bytes)
new_bin = nejii.replace_record(bin_bytes, 1, 'synthetic')
new_cdt = nejii_archive.pack_raw([('test.BIN', new_bin)])
```

## 源码、许可与改写

- SExtractor 固定提交：`8d8d976fd04ae54e7c677705af937273d04a376a`。
- 参考改写按仓库 GPL-3.0-only 分发；许可文本和逐文件来源见 `provenance/tools-a.json`。
- 直接依据：`tools/NEJII/cdt_pack.py`。
- 直接依据：`tools/NEJII/nejii_tool.py`。
- 源码符号：`pack_cdt`, `parse_cdt`, `parse_records`, `inject_bin`。
- GARbro-Mod 补充提交：`bc26d991ef5cdc0e1ecb32122ee9a48c3375750c`（文件头 MIT）。
- 补充结构来源：`ArcFormats/Nejii/ArcCDT.cs`，不作为运行时导入。
- 改写去除路径/GUI/全局变量耦合，保留算法并增加严格边界；不加载.pyd或外部exe。

## 验证与交付检查

- 合成CDT尾索引、BIN说话人绑定与定长回填已测试。
- 保留dialog flag并验证超长译文拒绝。
- 合成测试：`python -B -m unittest discover -s tests -p test_engines_tools_a.py -v`。
- 测试仅覆盖这里声明的算法层；上游真实样本成功数字不能代替本参考验证。
- 部署前还需空往返、字段范围、控制码与目标加载器核对；本次未启动商业游戏。
- 保留原始档备份，输出到新位置；归档成员名始终是不可信输入。
