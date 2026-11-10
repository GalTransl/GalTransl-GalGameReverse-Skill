# 随包 UIF winmm.dll

用户指定纳入仓库的 SExtractor `tools/UIF/winmm.dll` 原样副本，保留外部参考项目原文件。仅作为输出资源复制，不加载执行。

定位：JIS 回注默认使用 [CialloHook](../ciallohook/README.md)（`--hook auto`）；UIF 只作 **CialloHook 无法加载时的手动兜底**（仅 32 位），用 `--hook uif-x86`（兼容别名 `x86`）或 `artifacts(hook="uif")` 显式选择。UIF 不能转区：引擎未确认固定按 CP932 解码时，需用户自行以日文区域（ACP 932）运行；`--force-cp932 on` 与 UIF 组合会被拒绝。

- 来源：https://github.com/satan53x/SExtractor/blob/8d8d976fd04ae54e7c677705af937273d04a376a/tools/UIF/winmm.dll
- 大小：351232 字节；PE Machine `0x014c`，x86（32 位）。
- SHA-256：`b83f896edd06662078eadd5ea7970ab5bfd320cd8ec319e72b1455473c897e41`
- 改版源码：https://github.com/satan53x/UniversalInjectorFramework
- 原版源码：https://github.com/AtomCrafty/UniversalInjectorFramework
- 上游配套说明原样保存在 [UPSTREAM-README.md](UPSTREAM-README.md)。默认字符替换 hook 函数为 TextOutA/W、GetGlyphOutlineA/W；可按游戏渲染路径配置 `hook_functions`。

上游 UIF 两个仓库根目录均未发现独立 LICENSE，GitHub license 元数据为 null；本仓库不据 SExtractor 的 GPL 将此第三方二进制重新标为 GPL。该文件是用户指定的既有工具副本；来源项目提交仅标识提供该二进制的版本，不代表已知其编译源码提交。

选择 UIF 时，JIS `artifacts(hook="uif")` 将 DLL 与配置放在同一新结果目录，校验固定哈希。agent 可直接随结果交付，无需另外请求同意复制；不意味着安装进游戏或执行 DLL。没有 x64 UIF；已有其他 hook 的方案可用 `artifacts(include_hook=False)` 排除 DLL。SystemC、ExHIBIT 既有的内联 JIS 接口仍固定附带 UIF。

交付时提醒用户：对于匹配的 32 位游戏，将结果中的 `winmm.dll` 与 `uif_config.json` 一起放到实际游戏 EXE 目录，按引擎规则部署脚本/补丁，再测试修改的对白及未修改 UI。已有同名文件先检查合并，不盲目覆盖；不保证每个游戏都会加载 winmm 代理。普通字体与替换字体的选择见公共 JIS 指南。
