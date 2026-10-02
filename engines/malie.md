# Malie / 2008 UTF16 与 data5 EXEC

> 能力层级：`versioned-script-pool-rebuild`。这是独立算法参考，不是完整引擎支持承诺。

## 使用入口

- 模块：`python/engines/malie.py`。
- 调用者显式传入 bytes / str；导入不读取文件、不启动游戏。
- 返回数据在内存中，路径检查与安全输出由调用方统一处理。

## 识别与版本证据

- 解壳后的EXEC没有统一魔数；必须显式fmt，不根据游戏年份自动猜。
- utf16-2008-v0：u32 ident_count前缀，seg5池在纯offset消息表之前。
- data5-v1：u16零头、无count标识符链，以STRING_FLAG识别后续ident；带不透明尾部。
- data5-v2：v0风格前段，随后off/len消息表，再seg5池，无尾部。

## 从容器到脚本

- LIBP等外包/加密EXEC → 已由可靠路径得到EXEC明文 → parse(fmt) → 消息池。
- Camellia、外包key、DLL加速和EXE操作均未移植；无合法key则停在外壳。
- String长度高位80000000是flag，真正字节长需去掉高位；VarType按链读至tag=0。

## 对白与 name / message 映射

- 消息表index可作为稳定ID；UTF-16正文混有voice、ruby、分页等控制。
- 不能把语音名当name；常量池seg3也不全是对白。
- 本模块只接受完整message bytes，不进行自动name/message切割或控制码清洗。

## 回填、偏移与控制码

- v1/v2的pair offset和length均为seg5内字节位置，不是字符数或seg3+seg5地址。
- 上游顶部旧注释与实际message_raw有冲突，本参考采用实际解析/访问代码。
- 所有ident/func/label/seg3/CODE前缀原样保留；只重排连续消息池及其索引。
- 共享/重叠/有缝池拒绝；不让简单重建误伤别名引用。
- op51必须额外读u8；2008版未知>51拒绝，data5版按来源允许默认零宽opcode。

## 部署先决条件

- 标签必须落在指令边界；截断指令、奇数字节消息、未知fmt均报错。
- 本参考保留所有传入控制码，不照搬上游某项目删除中间特效的策略。

## 诚实边界

- 未提供消息token重写、语音/注音重构或所有旧版Malie VM。
- data5不透明尾部原样保留，但其外层校验/签名语义仍需部署验证。

## Python 调用

在 skill 根目录可使用如下接口；变量均由调用方提供，示例不自动读写磁盘。

```python
from python.engines import malie
fmt = 'data5-v2'  # 按实际布局选定后，整个流程保持同一fmt
report = malie.selftest(exec_plain, fmt=fmt)
image = malie.parse(exec_plain, fmt=fmt)
new_exec = malie.rebuild_messages(exec_plain, raw_messages, fmt=fmt)
```

## 源码、许可与改写

- SExtractor 固定提交：`8d8d976fd04ae54e7c677705af937273d04a376a`。
- 参考改写按仓库 GPL-3.0-only 分发；许可文本和逐文件来源见 `provenance/tools-a.json`。
- 直接依据：`tools/Malie/light社08年UTF16新版/malie_fmt.py`。
- 直接依据：`tools/Malie/light社08年UTF16新版/malie_selftest.py`。
- 直接依据：`tools/Malie/light社12年data5/malie_fmt.py`。
- 直接依据：`tools/Malie/light社12年data5/malie_selftest.py`。
- 源码符号：`ExecImage`, `Reader`, `OPERAND_WIDTHS`, `message_raw`, `main`。
- GARbro-Mod 补充提交：`bc26d991ef5cdc0e1ecb32122ee9a48c3375750c`（文件头 MIT）。
- 补充结构来源：`ArcFormats/Malie/ArcLIB.cs`，不作为运行时导入。
- 改写去除路径/GUI/全局变量耦合，保留算法并增加严格边界；不加载.pyd或外部exe。

## 验证与交付检查

- 三种fmt均有合成空往返和变长pool偏移测试，CODE与尾部保持。
- 单独测试op51宽度、data5新增opcode门禁；没有运行上游真实游戏自测。
- 合成测试：`python -B -m unittest discover -s tests -p test_engines_tools_a.py -v`。
- 测试仅覆盖这里声明的算法层；上游真实样本成功数字不能代替本参考验证。
- 部署前还需空往返、字段范围、控制码与目标加载器核对；本次未启动商业游戏。
- 保留原始档备份，输出到新位置；归档成员名始终是不可信输入。
