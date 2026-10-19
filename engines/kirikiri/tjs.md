# TJS2 编译字节码的只读反编译

本页说明如何从 `TJS2100` 字节码恢复可读的 TJS2 源码，用于理解脚本逻辑、定位字符串常量和核对现有补丁。它是阅读工具，不是原工程源码的还原，也不提供字节码 writer。

## 识别与安全边界

- 文件头为 `TJS2100\0`，随后是 u32 文件长度、`DATA` 块和 `OBJS` 块。`.tjs` 扩展名不能证明文件已编译；源码文本、SimpleCrypt 包装和该格式要分别判断。
- 解析有界：文件上限 32 MiB，指令、常量池和跳转目标越界即报错。未知 opcode、未知常量类型、无法证明的跳转形状不会被猜测。
- 只读：不执行脚本、不加载游戏、不覆盖输入；输出只写入新目录或 `xb` 新文件。
- 不重建字节码。字符串池、代码区和对象布局都没有 writer，因此**不能**把反编译结果或改过的字符串直接塞回编译脚本；编译 TJS 的正文回填仍属未支持能力。

## 命令

```text
python -m python.engines.kirikiri_tjs_decompile "游戏/scenario.tjs" --mode info
python -m python.engines.kirikiri_tjs_decompile "游戏/scenario.tjs" --mode strings
python -m python.engines.kirikiri_tjs_decompile "游戏/scenario.tjs" -o 新的目录/scenario.tjs
python -m python.engines.kirikiri_tjs_decompile "游戏/scripts" -r -o "新的目录/tjs-source"
python -m python.engines.kirikiri_tjs_decompile "游戏/scenario.tjs" --mode disasm
```

| 参数 | 用途 |
|---|---|
| `--mode info` | 对象表：ID、名称、上下文、父对象、参数个数、代码长度、字符串常量数 |
| `--mode strings` | 列出被指令引用的字符串常量及对象、地址和 opcode；用于在反编译失败时先定位文本 |
| `--mode decompile`（默认） | 输出重建的 TJS2 源码 |
| `--mode disasm` | 输出指令级反汇编；未知形状的最终依据 |
| `-o` | 文件模式写出单个文件；目录模式必须给出不存在的新目录 |
| `-r` / `-f` | 递归子目录；输出平铺到同一目录 |
| `--encoding` | `utf-8`（默认）、`utf-8-bom`、`utf-16le-bom`、`shift_jis`、`gbk` |

`utf-16le-bom` 只是让结果接近 Kirikiri 常见源码编码，不代表已经能编译或加载。批处理遇到无法重建的成员会继续处理其他成员，以非零状态结束，并逐文件报告对象名和地址。

## 能重建的形状

| 构造 | 说明 |
|---|---|
| 常量、局部变量、参数 | 参数按 `arg0…`，其余局部变量按 `localN`；字节码不保存原名 |
| 赋值与表达式 | 算术、位运算、比较、逻辑取反、`typeof`、`isvalid`、`delete`、`invalidate`、`instanceof`、`incontextof` |
| 属性与调用 | 直接/间接属性读写、`&` 属性引用、方法调用、`new`、普通函数调用 |
| 数组字面量 | 编译器用 `new Array()` 加连续 `SPIS`/`INC` 填充的常量数组（含尾部空槽）；非常量元素仍拒绝 |
| 分支 | `if` / `else`；`else if` 输出为嵌套的 `else { if … }`。连续的 `&&` 守卫保留为嵌套 `if`，短路 `||` 链合并为一个条件 |
| 循环 | 前置条件 `while`、`do … while`、`break`、`continue`；条件位于循环头的常见布局 |
| 异常 | `try { … } catch (localN) { … }`，包括无接收变量的 catch |
| 对象 | 顶层脚本、`function`、`class extends`、类成员 `var`、`property` 的 getter/setter |

`switch` 在本实现中**不重建**。TJS2 的 `switch` 会编译成比较链加跳转，case 体可能依次落入下一个 case；没有完整证据时把比较链改写成 if 链会改变落入语义，因此统一拒绝并保留反汇编。

## 明确拒绝的形状

以下情况抛出 `Unsupported`，消息带对象名和代码地址：

- 条件图出口多于两个（典型为 `switch`/多路分派），或条件块在多个前驱处合并。
- `with` 块、字典字面量、非常量元素数组的延迟填充、`argc == -2` 的展开实参、`EVAL`、`EEXP`。
- 使用 `*` 的折叠/无名参数列表（TJS2 的 `function f(a, *)` 形式）；参数名和数组绑定不可靠，直接拒绝。
- 条件块内出现赋值、属性写、调用之外的语句，或读取未定义的临时寄存器。
- 临时寄存器上的 `INC`/`DEC`；无法确定它对应哪个源码变量，输出 `1++` 一类无效语句比拒绝更有害。
- 循环条件包含无法折入表达式的副作用，或前向跳转既不是 `break`/`continue` 也不是外层结构隐含的跳过。
- 对象头字段越界、跳转目标不是指令边界（编译器把跳过跳转指向代码区末尾的情况单独允许）。

不要手工修改反编译结果后声称已回填。需要修改编译脚本时，先确认该加载入口是否接受源码；只有确认接受时，才可用明文源码替换并重新验证，字节码本身没有 writer。

## 常量作为资源线索

常量不只有对白：脚本可能以文件名形式引用 CSV、数据表、插件或其他脚本。即使完整反编译被拒绝，`--mode strings` 仍能列出这些名字。

字符串池可能包含未被指令引用的常量；`--mode strings` 只列被引用的。需要更全的候选时，按对象读取整个字符串池或结合反汇编核对。常量传播和字符串拼接只能辅助阅读，不能据此生成池中不存在的名字；候选仍须逐个用名称哈希核验。

遇到 `.csv`/`.dat`/`.tjs` 等表名时，可按名提取对应成员，再判断其外层是 SimpleCrypt、MDF 还是明文；解开后把表中的资源名作为其他包的候选，并逐个用名称哈希核验。表中名称通常是逻辑名，前缀、扩展名和一条记录对应的多个成员都要按实际存储生成变体，不能直接把表名当文件名。

`STARTUP.TJS` 里的 `System.bootStrap` / `CompoundStorageMedia` 字符串还能给出 Hx 的 mediaName（哈希域），它不一定等于默认的 `xp3hnp`；看到这类对象时应把实际字符串记下来，再用于路径/文件名哈希。

这一流程用于 Hx 名称恢复时，具体顺序和边界见 [Hxv4 的候选扩展](hxv4.md#从-tjs-与数据表扩展候选)。常量只能提供候选，不能证明成员可写；回填仍取决于对应 writer。

## 命名与语义损失

- 参数、局部变量和临时寄存器名称不可恢复；条件中的临时值尽量内联，无法内联时以“未定义临时寄存器”错误拒绝，不生成占位变量。
- 注释、空白、默认参数、`true`/`false` 的原始书写形式和运算符结合顺序不可恢复。数值布尔可能显示为 `1`/`0`；比较取反会改写为 `<=`、`>=`、`!=` 等等价形式。
- 编译器的函数注册序言可能显示为 `this.name = name;` 或 `&this.name = …;`；类成员注册会跳过，成员变量显示为 `var name = …;`。
- 嵌套在其他函数中的命名函数只可能以引用名出现，其定义不保证写出；需要完整阅读时使用反汇编核对。
- `#`、`$`、`%` 等 TJS 运算符按源码形式保留；解析器不执行表达式。

## 验证与维护

```text
python -m unittest tests.test_kirikiri_tjs_decompile -v
python -m unittest discover -s tests -p "test_kirikiri*.py" -q
python tools/check_skill.py
```

现有回归全部使用合成字节码，覆盖表达式、局部变量、`if/else`、`while`、`do-while`、`||` 条件链、类成员与方法、property 访问器、`try/catch`、赋值结果复用、无结果调用的保留、`strings`/`info` 模式以及未知 opcode 与折叠参数的拒绝。**没有**使用真实游戏的全部脚本验证，也没有编译 TJS 后运行显示；上游项目自述的验证结果不转移到本实现。

指令编码、条件标志和编译器布局的出处与许可见 [TJS 来源记录](../../provenance/kirikiri-tjs.json)。阅读本页不需要访问外部仓库。
