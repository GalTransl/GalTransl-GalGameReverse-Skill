# 随包 rizin（Windows x86/x64 精简版）

用于只读静态分析游戏 EXE，例如判定运行时码页、定位读包与解密代码。用法见 [rizin 简易指南](../../guides/rizin.md)；`python -m python.common.jis_workflow codepage` 在 Windows 上默认自动调用。

## 来源

| 项目 | 内容 |
|---|---|
| 源码 | <https://github.com/xd2333/rizin>（`dev` 分支，提交 `47cc7c6e26a3ab8c3f4671494a2e95a22d0969ad` “Add windows-only build profile”） |
| 上游 | [rizinorg/rizin](https://github.com/rizinorg/rizin)，版本 0.10.0；精简改动之前的上游提交为 `4162458dc4fc61c6e78c90fd80cbc31e03641444` |
| 精简内容 | `-Dwindows_only=true`：只保留 x86 架构、PE/COFF/PDB 格式与 Windows 调试器相关插件，去掉其他架构、非 Windows 格式、远程/归档 IO 插件和无关工具 |
| 构建 | MSVC 19.44 x64，meson 1.12.1；`--buildtype=release -Dportable=true -Dwindows_only=true -Denable_tests=false -Denable_rz_test=false -Denable_benchmarks=false -Denable_doc=false -Duse_gpl=false` |
| 压缩 | `bin/` 下全部 EXE/DLL 用 UPX 5.2.1 `--best --lzma` 压缩（约 11 MB → 3.4 MB），分析结果与未压缩版一致，每次调用多约 0.3 秒解压开销。若安全软件拦截，可用 `upx -d` 还原后同步更新 `SHA256SUMS` |

必须用 `-Dportable=true` 构建：否则安装前缀会写死在 DLL 中，换目录后找不到 `share/` 数据（类型库、调用约定、格式定义），`aaa` 的参数和导入函数签名会缺失。

## 目录

```text
bin/       rizin.exe、rz-bin.exe、rz-asm.exe 及 rz_*-0.10.dll（x64 进程，可分析 x86 与 x64 PE）
share/     运行时数据，只保留 arch、flag、format、magic、opcodes、reg、syscall、types 中 Windows/x86 相关部分
SHA256SUMS bin/ 下各文件的哈希，测试据此校验，替换二进制时同步更新
LICENSES/  上游 COPYING、COPYING.LESSER 及源码树中引用的全部 SPDX 许可文本
```

精简后的 `share/` 已与完整安装比对，常用分析命令输出一致。只有 64 位 Windows 上可运行；其他系统需另行安装 rizin 并用 `--rizin <路径>` 或环境变量 `GALTRANSL_RIZIN` 指定，`GALTRANSL_RIZIN=off` 可禁用。

## 许可

rizin 整体按 LGPL-3.0-only 分发（`LICENSES/COPYING.LESSER` 与 `COPYING`），部分组件另有 `LICENSES/` 中列出的许可；构建关闭了 GPL 组件（`-Duse_gpl=false`）。本包只把它作为独立可执行程序调用，不链接进 Python 代码；对应源码见上方仓库与提交。替换为自行构建的同版本 rizin 时保持相同目录结构即可。
