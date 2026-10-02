# IKURA / MPX、ISF

> 能力层级：`container-mpx-roundtrip`。这是独立算法参考，不是完整引擎支持承诺。

## 使用入口

- 模块：`python/archives/ikura.py`。
- 调用者显式传入 bytes / str；导入不读取文件、不启动游戏。
- 返回数据在内存中，路径检查与安全输出由调用方统一处理。

## 识别与版本证据

- 本模块识别SM2MPX10八字节签名，+8为count，索引从32开始。
- 20字节项含12字节ASCII名字、u32绝对offset、u32size。
- 早期DRS是另一布局，不能让无魔数输入自动落入DRS猜测。

## 从容器到脚本

- MPX → ISF/SNR等成员stored → 可能的SECRETFILTER外壳 → 脚本语义。
- 源码提供基于调用方secret的ISF外壳算法，但本参考只实现MPX容器层。
- 不会从EXE扫描密钥，也不会携带任何游戏secret。

## 对白与 name / message 映射

- ISF内部name/message需ISF_FILE等解析依据，成员名不是说话人。
- 被加密的成员始终作为stored传递，不冒充解密后的对白。
- 建立脚本定位键必须在正确解壳之后。

## 回填、偏移与控制码

- 按原索引次序和原12字节名字字段重算绝对offset和size。
- 32字节原头保留；成员数量不能变。
- 正文壳的重加密、控制码和脚本跳转不由MPX重建器处理。

## 部署先决条件

- 只接受本新版MPX，不把所有IKURA归档强行视为该版。
- 如果正文仍有secret filter，需要额外合法密钥和算法层确认。

## 诚实边界

- 不覆盖DRS、ISF AST或加密脚本写回。
- 外壳成员可往返不代表文本层已完成。

## Python 调用

在 skill 根目录可使用如下接口；变量均由调用方提供，示例不自动读写磁盘。

```python
from python.archives import ikura
entries = ikura.unpack_mpx(mpx_bytes)
new_mpx = ikura.rebuild_mpx(mpx_bytes, stored_payloads)
```

## 源码、许可与改写

- SExtractor 固定提交：`8d8d976fd04ae54e7c677705af937273d04a376a`。
- 参考改写按仓库 GPL-3.0-only 分发；许可文本和逐文件来源见 `provenance/tools-a.json`。
- 直接依据：`tools/IKURA/ikura_decryptor.py`。
- 源码符号：`unpack_mpx`, `unpack_drs`, `handle_isf_xor`。
- GARbro-Mod 补充提交：`bc26d991ef5cdc0e1ecb32122ee9a48c3375750c`（文件头 MIT）。
- 补充结构来源：`ArcFormats/Ikura/ArcDRS.cs`，不作为运行时导入。
- 改写去除路径/GUI/全局变量耦合，保留算法并增加严格边界；不加载.pyd或外部exe。

## 验证与交付检查

- 合成SM2MPX10检查20字节索引和绝对offset。
- 变长成员重建保留32字节头并更新size。
- 合成测试：`python -B -m unittest discover -s tests -p test_engines_tools_a.py -v`。
- 测试仅覆盖这里声明的算法层；上游真实样本成功数字不能代替本参考验证。
- 部署前还需空往返、字段范围、控制码与目标加载器核对；本次未启动商业游戏。
- 保留原始档备份，输出到新位置；归档成员名始终是不可信输入。
