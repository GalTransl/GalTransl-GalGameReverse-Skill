# Ivory / fAGS OCB

> 能力层级：`script-section-cipher`。这是独立算法参考，不是完整引擎支持承诺。

## 使用入口

- 模块：`python/engines/ivory.py`。
- 调用者显式传入 bytes / str；导入不读取文件、不启动游戏。
- 返回数据在内存中，路径检查与安全输出由调用方统一处理。

## 识别与版本证据

- OCB顶层fAGS魔数及u32总长；各子节有tag、section_size、header_size。
- cTEX承载文本池，cCOD承载字节码及跳转表。
- 外层PK与其它Ivory资源不能直接当fAGS解析。

## 从容器到脚本

- PK等归档 → OCB → sections → 按节头seed调用crypt解除正文壳。
- cTEX seed在节+12；cCOD seed在+16，不能把两类头混用。
- 返回节原始字节，调用方保留未知头与节顺序。

## 对白与 name / message 映射

- 解密文本池中的字符串未必都是台词；必须结合cCOD引用。
- name/message分类不能仅凭字符串内容或出现次序。
- 上游FFN/FFn是换行，FFS/FFs是空格控制；本cipher不改这些字节。

## 回填、偏移与控制码

- 每DWORD按seed轮转索引生成32组key；根据key的位对差异交换相邻bit。
- 加密先XOR后置换，解密先置换后XOR，顺序不能互换。
- 不足4字节的尾部保留；仅加解密不改变长度或偏移。

## 部署先决条件

- seed由调用方从正确节头提供，严格u32；无内置游戏key。
- 节边界要求12<=header_size<=section_size且不超顶层声明长度。

## 诚实边界

- 不实现cCOD完整解析、变长文本池引用修正或跳转表重建。
- cipher往返成功只证明外壳，不证明完整文本部署。

## Python 调用

在 skill 根目录可使用如下接口；变量均由调用方提供，示例不自动读写磁盘。

```python
from python.engines import ivory
sections = ivory.sections(ocb_bytes)
plain = ivory.crypt(payload_bytes, seed)
stored = ivory.crypt(plain, seed, encrypt=True)
```

## 源码、许可与改写

- SExtractor 固定提交：`8d8d976fd04ae54e7c677705af937273d04a376a`。
- 参考改写按仓库 GPL-3.0-only 分发；许可文本和逐文件来源见 `provenance/tools-a.json`。
- 直接依据：`tools/Ivory/OCB.py`。
- 源码符号：`generate_keys`, `process_data`, `parse_fags_sections`, `decode_ctex_from_raw`, `decode_ccod_from_raw`。
- GARbro-Mod 补充提交：`bc26d991ef5cdc0e1ecb32122ee9a48c3375750c`（文件头 MIT）。
- 补充结构来源：`ArcFormats/Ivory/ArcPK.cs`，不作为运行时导入。
- 改写去除路径/GUI/全局变量耦合，保留算法并增加严格边界；不加载.pyd或外部exe。

## 验证与交付检查

- seed=1的独立bit-pair期望向量验证不只是自反测试。
- 跨32组key轮转、DWORD余数及fAGS节解析已测试。
- 合成测试：`python -B -m unittest discover -s tests -p test_engines_tools_a.py -v`。
- 测试仅覆盖这里声明的算法层；上游真实样本成功数字不能代替本参考验证。
- 部署前还需空往返、字段范围、控制码与目标加载器核对；本次未启动商业游戏。
- 保留原始档备份，输出到新位置；归档成员名始终是不可信输入。
