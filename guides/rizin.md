# rizin 简易指南：只读静态分析游戏 EXE

随包 [rizin](../assets/rizin/README.md)（0.10.0，Windows x86/x64 精简版）用于回答提取和回注时“EXE 里到底怎么做”的问题：剧本按哪个码页解码、读哪些包和补丁包、用什么常量解密、字体 charset 从哪里来。它只是证据来源，结论仍要用 Python 实现和样本往返验证。

## 安全约定

- **只做静态分析。** 不用 `-d`（调试器会运行游戏）、不用 `-w`（写文件），不用 `!`/`#!` 等执行外部命令的语句。
- 固定加 `-N`（不读用户 rc 配置）、`-q -c '命令'`（批处理后退出）、`-e cfg.sandbox=true`（禁止写文件与外部命令）、`-e scr.color=0`。
- 游戏目录只读，直接分析原文件即可；不需要复制，也不要修改。
- 加壳或保护的 EXE（UPX、Enigma、VMProtect、Steam DRM 的 `.bind` 等，字节探测的 `packing.suspected`）先说明情况，不要运行程序去脱壳。
- 分析可能很慢：小型引擎约数秒，大型 EXE 可达数十秒到数分钟；批量调用设超时。

## 调用方式

```text
assets/rizin/bin/rizin.exe -N -q -e cfg.sandbox=true -e scr.color=0 -c "iI; ii~MultiByteToWideChar" "游戏目录/game.exe"
```

- **Git Bash：** 先 `export MSYS_NO_PATHCONV=1`，否则以 `/` 开头的命令（如 `/z`、`/x`）会被改写成 Windows 路径。PowerShell、cmd 与 Python `subprocess` 不受影响。
- **噪音：** `aaa` 时出现的 `config-hold: failed to get 'esil.nonull'`、`Cannot peek memory`、`var_rename` 警告来自上游，不影响结果，可把 stderr 丢弃。
- **0.10 写法：** 列标志用 `fl~名字`（不是 `f~`），搜字符串用 `/z`（不是 `/ `）。不确定的命令先 `命令?` 查看帮助。
- **完整文档：** 本页未覆盖的命令、分析配置和输出格式可查官方手册 [The Rizin Handbook](https://book.rizin.re/)（需联网，按需查阅）。手册部分章节对应旧版本或含调试、写入用法，命令以随包版本 `命令?` 的输出为准，并仍遵守上方安全约定。
- Python 代码中用 [rizin_probe.py](../python/common/rizin_probe.py) 的 `find_rizin()` / `run()` 调用：它固定只读与沙盒参数、带超时，并按分隔符拆分各命令的输出。

## 常用命令

| 命令 | 用途 |
|---|---|
| `iI` / `iS` | 位数、架构 / 节表 |
| `ii` / `iij` | 导入表（`iij` 的 `plt` 是 IAT 地址） |
| `iz` / `iz~关键字` | 数据节中的字符串（含地址），可 grep |
| `aaa` | 完整分析；`axt`、`afl`、`pdf` 依赖它（只用 `aa` 时找不到导入调用） |
| `axt @ 地址` / `axtj` / `axtq` | 谁引用了该地址（导入、字符串、函数） |
| `afl` / `afl~关键字` | 函数列表 |
| `pdf @ 函数` / `pdfj` | 反汇编整个函数，跳转表会标注 `case` |
| `pd N @ 地址` / `pd -N @ 地址` | 向后 / 向前反汇编 N 条 |
| `pdj` | 指令 JSON；立即数以 `disasm` 文本为准，`val` 字段对 `0xffffffff` 等值不可靠 |
| `/z 文本` / `/x 十六进制` | 搜字符串 / 原始字节，命中地址可再接 `axt` |
| `命令 @@c:axtq @ 地址` | 对每个引用点执行同一命令（如 `pd -8 @@c:axtq @ 地址`） |

## 配方

### 1. 运行时码页

先用公共入口，它在 Windows 上会自动调用 rizin：

```text
python -m python.common.jis_workflow codepage "游戏目录/game.exe"
```

看 `rizin.conversion_calls`：`purpose: path` 的调用是路径转换，与剧本无关；`codepage_source: caller-argument`/`unresolved` 的调用需要往上追：

```text
aaa; pdf @ <conversion_calls[].function>      # 看 CodePage 来自哪个参数/寄存器
aaa; axt @ <该函数>                            # 找调用方
aaa; pd -8 @ <调用方地址>                       # 看调用方压入/设置的值（xor edx,edx 即 0 = CP_ACP）
```

`getacp_calls[].acp_branch` 为真时用 `pdf @ <所在函数>` 可直接看到 `case 932/936/949/950` 对应的 charset。

### 2. 读哪些包、补丁包规则

```text
iz~.pak            # 换成实际扩展名，如 .fpk/.xp3/.arc；找 patch*、update、%02d 等模式串
aaa; axt @ <字符串地址>
aaa; pdf @ <引用函数>
```

模式串（如 `patch*.xxx`、`update%02d.xxx`）和它所在函数里的循环、排序逻辑，是“补丁包是否被加载、按什么顺序覆盖”的直接证据；把结论写进引擎页的加载规则，不要只凭目录里已有的文件猜。

### 3. 密钥与解密循环

```text
/x <已知文件头的十六进制>        # 找校验或解析该格式的代码附近
/z <包名或错误提示>              # 如 "decrypt"、"key"、读包失败的提示
aaa; axt @ <命中地址>; pdf @ <函数>
```

在函数中找固定常量、`xor`/`rol`/`add` 循环和表查找。常量要和样本解密结果相互印证；推出来的算法写进 `python/archives/` 并补合成测试，不要在文档里留“猜测值”。

### 4. 日文字符串

`iz` 默认只列 ASCII/UTF-16。CP932 文本先在 Python 中转成十六进制再搜：

```text
python -c "print('セーブ'.encode('cp932').hex())"
... -c "/x <上面的十六进制>"
```

### 5. 字体与 charset

`ii~Font` 列出 `CreateFontA/W`、`CreateFontIndirectA/W`、`D3DXCreateFont*`；`codepage` 输出的 `rizin.font_calls` 给出调用点，`CreateFontA/W` 的 charset 为立即数时一并解出（`0x01` 为 `DEFAULT_CHARSET`，按 ACP 解释 A 接口文本）。

## 局限

- 静态分析看不到运行时才确定的值：经函数指针、虚表、`GetProcAddress` 或延迟加载的调用，以及加壳代码，都需要另找证据。
- `aaa` 的函数边界和类型推断可能出错；关键结论回到 `pd` 原始指令核对。
- 结论只说明 EXE 的行为，不代表格式实现正确；最终以 Python reader/writer 的样本往返和游戏实测为准。
