# 启动与区域：游戏在非日文系统上无法运行时的处理

本页处理**提取之前**的问题：游戏在非日文区域 Windows 上启动即崩溃、黑屏、闪退。

> **适用性说明（先读）**
> 这**不是所有游戏都会遇到的问题**。多数现代游戏、以及已经做过区域或编码处理的版本，在非日文系统上可以直接运行。
> 区域导致的启动崩溃**主要集中在「按原始发行版安装的老游戏」** —— 这类版本用 ANSI/CP932 处理文件名、
> 路径与配置，且未做任何区域无关化处理。
> 因此：**先确认游戏是否真的起不来**（能正常运行就直接跳过本页），
> 不要把它当成必做前置步骤。本页只在游戏无法启动时使用。

本页只处理**本机运行环境**问题，不涉及游戏数据格式。区域问题排除后，再回到 [识别指南](detection.md)。

## 先分清三类启动失败

| 类别 | 典型表现 | 处理 |
|---|---|---|
| **区域/编码**（本页重点，多见于老游戏原始安装版） | 双击 → 报错弹窗 → 黑屏 → 自动退出；或直接闪退；异常码 `0xC0000005`，故障模块 = 游戏自身 EXE，**偏移固定（确定性）** | 见下文 |
| 依赖缺失 | 提示缺少 DLL | 检查 DirectX / VC 运行库 / 音频库等依赖 |
| 安装与介质 | 安装阶段就失败 | 见 [介质安装](#三介质安装mdfmds-等) |

**判定区域问题最快的一条证据**：看游戏在"文档"目录下建的存档夹名。
老游戏普遍用 ANSI/CP932 处理文件名与配置；在非日文区域下，存档夹名会出现乱码
（例如 `データ` 变成 `僨乕僞`）。**出现乱码即坐实区域问题**，不必继续猜。
若存档夹名正常、游戏仍崩溃，则应先怀疑其他因素（见第一节）。

## 一、先排除非区域因素（便宜且可逆）

按顺序做，每步都可回退：

1. **显卡**：`Get-CimInstance Win32_VideoController`。仅部分老核显不满足；现代独显/核显通常无碍。
2. **运行库**：扫 EXE 依赖的 DLL 是否齐全（如 `d3dx9_*`、`d3d9`、`dinput8`、`X3DAudio*`）。
3. **光盘校验**：挂上镜像再试；挂与不挂表现相同 → 不是校验问题。
4. **安装路径**：用 ASCII 目录建 junction 测试（`New-Item -ItemType Junction`），排除日文路径影响。
5. **补丁**：换回原始 EXE 测试，排除已装补丁。
6. **兼容模式**：在 `AppCompatFlags\Layers` 设兼容模式测试。

以上都无关，再进入区域问题。

## 二、区域问题的修复（不改系统区域、不重启）

**推荐做法**：用 Locale Emulator 以 ja-JP 区域启动游戏，不修改系统设置、不需要重启。

1. 获取 Locale Emulator（`Locale.Emulator.2.5.0.1.zip`）。
2. 解压。⚠️ 该 zip 可能**缺少** `LECommonLibrary.dll` / `LEContextMenuHandler.dll`，
   需运行 LEUpdater/LEInstaller 补齐（或从完整包取），否则 LEProc 会报 .NET `FileNotFoundException`。
3. 在 **LEProc.exe 同目录**写 `LEConfig.xml`（配置路径 = 程序目录，**不是** `%APPDATA%`）：

```xml
<?xml version="1.0" encoding="utf-8"?>
<LEConfig>
  <Profiles>
    <Profile Name="Run in Japanese" Guid="PUT-A-GUID-HERE" MainMenu="true">
      <Parameter></Parameter><Location>ja-JP</Location><Timezone>Tokyo Standard Time</Timezone>
      <RunAsAdmin>false</RunAsAdmin><RedirectRegistry>true</RedirectRegistry>
      <IsAdvancedRedirection>false</IsAdvancedRedirection><RunWithSuspend>false</RunWithSuspend>
    </Profile>
  </Profiles>
</LEConfig>
```

4. 启动：`LEProc.exe -runas <上面的 GUID> "<游戏exe>"`；或 `LEProc.exe "<游戏exe>"` 走默认 ja-JP。
5. **验收**：进程存活、事件日志无新崩溃、存档夹名变为正确日文（不再是乱码）。

> 改系统区域为日文同样可行，但**需要重启**，且影响全局 → 优先 Locale Emulator。

## 三、介质安装（MDF/MDS 等）

- rar 里的 `*.mdf` / `*.mds` **不是 ISO**，新版系统自带挂载不认。
- **免管理员**：7-Zip 可直接读取 `.mdf`（UDF）抽出文件，运行其中的安装程序。
  安装阶段可绕过虚拟光驱；末尾出现的 "Headers Error" 属私有尾部数据，不影响。
- **需要光盘校验时**：装 WinCDEmu（`/UNATTENDED` 静默装驱动），
  再用 `batchmnt64.exe "<image.mdf>"` 分配盘符（会自动认配对的 `.mds`）。
- MDF/MDS 必须**成对**且放在同一目录。

## 四、引擎日志（决定性证据）

许多日文引擎会在存档目录写文本日志，是定位崩溃阶段的第一手材料。

- 位置：`<我的文档>\<游戏名> SAVE*\` 下，常见 `device.log`、`error.log`、`setting.ini`。
- **编码常为 UTF-16LE**：必须用 `bytes.decode('utf-16')` 读，用 utf-8/cp932 会得到乱码。
- `device.log` 若显示图形/输入/声音初始化**全部成功** → 崩溃发生在**数据加载阶段**，而不是设备初始化。
- `error.log` 中的 `...読み込み失敗[...]`、`ID out of range[...]` 多为区域/数据读写被破坏的表象，
  不要当作独立的格式错误处理。

## 五、与转码路线的关系（重要）

仓库主推**保留原编码（如 CP932）+ 字符替换 / 运行时 hook** 的中文回注路线（见 [JIS 替换](jis-substitution.md)）。
需要注意这套路线有一个**隐含前提**：

> 若游戏脚本在非日文区域下按系统 ANSI 代码页（CP_ACP）解码，
> 原本合法的 CP932 字节序列会被解成非法序列，游戏**在启动阶段即失败**。
> 也就是说，**保留 CP932 不等于游戏能运行** —— 用户可能仍需要区域修复或转区才能启动。

因此：

- 走"保留原编码"路线时，**先确认游戏已经能正常启动**（本页第一至四节），再做提取与回填。
- 若游戏无法在用户环境下启动，可考虑 [UTF-16 重编码路线](encoding-and-control-codes.md)：
  把脚本整体转为带 BOM 的目标编码。该路线与"保留原编码 + hook"路线**互斥**，
  二选一，不要在同一份产物上叠加。
- 具体选择取决于引擎的实际解码路径：**沿调用路径核对实现，不按名称或扩展名推断**。

## 六、边界

- 本页**只在游戏无法启动时**使用。游戏能正常运行就不要套用本节流程，
  更不要为了"预防"而预先修改系统区域或重编码脚本。
- 启动游戏、安装运行时组件需要用户明确授权；本页只提供诊断与修复方法。
- 修改系统区域、安装驱动会影响全局，部署前应向用户说明并可回退。
- 本页结论来自真实样本上的实测，不含逐游戏参数；具体路径与日志名以实际样本为准。
