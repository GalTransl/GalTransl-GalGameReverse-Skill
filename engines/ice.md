# ICE / 索引字表文本流

> 能力层级：`message-token-codec`。这是独立算法参考，不是完整引擎支持承诺。

## 使用入口

- 模块：`python/engines/ice.py`。
- 调用者显式传入 bytes / str；导入不读取文件、不启动游戏。
- 返回数据在内存中，路径检查与安全输出由调用方统一处理。

## 识别与版本证据

- 文本流无独立魔数，必须先由脚本指令识别消息区。
- 源码op68/69为消息，71/72为名字，74为即时文本。
- System.grp中的字符表参与解释；不能直接把token字节按cp932解码。

## 从容器到脚本

- GRP资源 → 脚本指令定位 → 索引字符/控制码token → 调用方提供字表映射。
- 本模块保留token级别，不包含GRP HDJ解压或全VM指令表。
- GARbro Ice/ScriptISD是邻近格式证据，不代表此opcode版本普适。

## 对白与 name / message 映射

- name/message由承载opcode确定，不由字表索引决定。
- E7/E8是自动名字/变量插入，不可翻译成固定人名。
- 保留换行/分页的参数字节、颜色起止和EC终止符。

## 回填、偏移与控制码

- 单字节字符index< E7或==E9；F7..FF前缀配下一字节形成256..2559索引。
- EA/EB带参数，ED ED复位，ED..F6颜色；encode_tokens保持这些结构。
- 禁止2560以上索引，避免依赖上游EXE补丁扩展到4863的私有条件。

## 部署先决条件

- 需要调用方合法取得字表；没有字表也可无损保留token，不能生成猜测文本。
- 文本流必须有EC终止且无尾随字节。

## 诚实边界

- 不改EXE、不扩字库、不提供相对跳转重定位。
- 纯token往返不等于全脚本注入或字体可显示。

## Python 调用

在 skill 根目录可使用如下接口；变量均由调用方提供，示例不自动读写磁盘。

```python
from python.engines import ice
tokens = ice.tokenize(message_bytes)
same = ice.encode_tokens(tokens)
```

## 源码、许可与改写

- SExtractor 固定提交：`8d8d976fd04ae54e7c677705af937273d04a376a`。
- 参考改写按仓库 GPL-3.0-only 分发；许可文本和逐文件来源见 `provenance/tools-a.json`。
- 直接依据：`tools/ICE/ice_op.py`。
- 源码符号：`Charset.encode_idx`, `tokenize`, `seg_to_str`, `str_to_bytes`。
- GARbro-Mod 补充提交：`bc26d991ef5cdc0e1ecb32122ee9a48c3375750c`（文件头 MIT）。
- 补充结构来源：`ArcFormats/Ice/ScriptISD.cs`，不作为运行时导入。
- 改写去除路径/GUI/全局变量耦合，保留算法并增加严格边界；不加载.pyd或外部exe。

## 验证与交付检查

- 合成混合流覆盖多字节index、插入、带参换行、颜色复位和EC。
- 截断token及未打补丁时不可编码的索引拒绝。
- 合成测试：`python -B -m unittest discover -s tests -p test_engines_tools_a.py -v`。
- 测试仅覆盖这里声明的算法层；上游真实样本成功数字不能代替本参考验证。
- 部署前还需空往返、字段范围、控制码与目标加载器核对；本次未启动商业游戏。
- 保留原始档备份，输出到新位置；归档成员名始终是不可信输入。
