# DigitalWorks / BunBun TAK

> 能力层级：`text-instruction-codec`。这是独立算法参考，不是完整引擎支持承诺。

## 使用入口

- 模块：`python/engines/digitalworks.py`。
- 调用者显式传入 bytes / str；导入不读取文件、不启动游戏。
- 返回数据在内存中，路径检查与安全输出由调用方统一处理。

## 识别与版本证据

- TAK.BIN容器本身无稳定魔数；源码的索引位于EXE，不应移植游戏专用地址。
- 单条文本指令头为A8/AA、00、u16 identifier。
- A8对应NAME，AA对应MSG，结束指令分别A9/AB。

## 从容器到脚本

- 包/TAK.BIN → 经独立核准索引取得脚本 → 可选LZS外壳 → 单条文本指令。
- 本模块从已定界的文本指令开始，不读取EXE也不使用上游硬编码索引偏移。
- LZS解压和整脚本分割在本参考外。

## 对白与 name / message 映射

- A8的正文为name，AA的正文为message；identifier原样传递。
- 不要从文件名或音频命令推断说话人。
- 模块不把整脚本线性扫描的偶然A8/AA字节误当文本起点。

## 回填、偏移与控制码

- 正文要求偶数字节，4字节头后按4字节对齐，必要时补两个00。
- 尾随A9/AB四字节指令保持其类别。
- AC是16bit绝对跳转；本模块不重定位全脚本，变长指令不能直接原地拼回TAK。

## 部署先决条件

- 严格cp932，单字节ASCII导致奇数长度时拒绝而非静默损坏边界。
- 正文在双字节边界不能与结束opcode冲突。

## 诚实边界

- 范围是单条文本指令codec，不是整TAK.BIN回封器。
- 不提供任何商业EXE补丁、硬编码偏移或游戏字库。

## Python 调用

在 skill 根目录可使用如下接口；变量均由调用方提供，示例不自动读写磁盘。

```python
from python.engines import digitalworks
raw = digitalworks.encode_text_instruction('message', 1, 'Ａ')
kind, identifier, text = digitalworks.decode_text_instruction(raw)
```

## 源码、许可与改写

- SExtractor 固定提交：`8d8d976fd04ae54e7c677705af937273d04a376a`。
- 参考改写按仓库 GPL-3.0-only 分发；许可文本和逐文件来源见 `provenance/tools-a.json`。
- 直接依据：`tools/DigitalWorks/文本工具(反编译与写回)/tak_text.py`。
- 源码符号：`disassemble`, `encode_text`, `lzs_decompress`。
- GARbro-Mod 补充提交：`bc26d991ef5cdc0e1ecb32122ee9a48c3375750c`（文件头 MIT）。
- 补充结构来源：`ArcFormats/DigitalWorks/ArcBIN.cs`，不作为运行时导入。
- 改写去除路径/GUI/全局变量耦合，保留算法并增加严格边界；不加载.pyd或外部exe。

## 验证与交付检查

- 合成全角字符测试NAME/MSG和2/4字节正文的对齐。
- 奇数长度正文与非法结束结构拒绝。
- 合成测试：`python -B -m unittest discover -s tests -p test_engines_tools_a.py -v`。
- 测试仅覆盖这里声明的算法层；上游真实样本成功数字不能代替本参考验证。
- 部署前还需空往返、字段范围、控制码与目标加载器核对；本次未启动商业游戏。
- 保留原始档备份，输出到新位置；归档成员名始终是不可信输入。
