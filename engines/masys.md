# Masys / MEG 表达式字符串

> 能力层级：`expression-string-cipher`。这是独立算法参考，不是完整引擎支持承诺。

## 使用入口

- 模块：`python/engines/masys.py`。
- 调用者显式传入 bytes / str；导入不读取文件、不启动游戏。
- 返回数据在内存中，路径检查与安全输出由调用方统一处理。

## 识别与版本证据

- 完整MEG源码检查前三字节MEG并跳过32字节头。
- 本接口输入不是整MEG，而是由VM可靠定界的一条表达式。
- 表达式00结束，atom62有u16长度和字符串字节；不能全文搜索62。

## 从容器到脚本

- MGS等归档 → MEG脚本 → 根据opcode参数模式找到表达式 → crypt_expression。
- 参考内置已读到的表达式atom宽度，不导入opcodelist也不依赖sys.path。
- 字符串key必须显式传入；本参考不内置项目默认key。

## 对白与 name / message 映射

- 字符串atom可以是对白、变量或资源；必须结合上层opcode判断name/message。
- 整数0x62006200等包含62字节仍为整数，不应被解密。
- 独立表达式返回同结构bytes，不自动导出翻译清单。

## 回填、偏移与控制码

- 只XOR atom62的正文，不改u16长度和其它操作数。
- 每一个字符串从key位置0开始循环，多个atom不续接key计数。
- 此算法用于等长壳转换；变长翻译必须由MEG assembler重算结构和分支。

## 部署先决条件

- 空key、空表达式、未知token、截断操作数和尾随数据拒绝。
- 不使用上游未知opcode自由表达式回退来假装全VM解析。

## 诚实边界

- 不支持整MEG自动定位、全指令组装或跳转重定位。
- 通用byte替换不能替代该token解析器。

## Python 调用

在 skill 根目录可使用如下接口；变量均由调用方提供，示例不自动读写磁盘。

```python
from python.engines import masys
plain_expr = masys.crypt_expression(expression_bytes, supplied_key)
stored_expr = masys.crypt_expression(plain_expr, supplied_key)
```

## 源码、许可与改写

- SExtractor 固定提交：`8d8d976fd04ae54e7c677705af937273d04a376a`。
- 参考改写按仓库 GPL-3.0-only 分发；许可文本和逐文件来源见 `provenance/tools-a.json`。
- 直接依据：`tools/Masys/meg_crypt.py`。
- 源码符号：`walk_and_crypt`, `xor_buf`, `EXPR_ATOM`, `EXPR_OPS`。
- GARbro-Mod 补充提交：`bc26d991ef5cdc0e1ecb32122ee9a48c3375750c`（文件头 MIT）。
- 补充结构来源：`ArcFormats/Masys/ArcMGS.cs`，不作为运行时导入。
- 改写去除路径/GUI/全局变量耦合，保留算法并增加严格边界；不加载.pyd或外部exe。

## 验证与交付检查

- 合成表达式同时包含整数和两个字符串，核对只改字符串及key重置。
- 截断字符串与空key拒绝。
- 合成测试：`python -B -m unittest discover -s tests -p test_engines_tools_a.py -v`。
- 测试仅覆盖这里声明的算法层；上游真实样本成功数字不能代替本参考验证。
- 部署前还需空往返、字段范围、控制码与目标加载器核对；本次未启动商业游戏。
- 保留原始档备份，输出到新位置；归档成员名始终是不可信输入。
