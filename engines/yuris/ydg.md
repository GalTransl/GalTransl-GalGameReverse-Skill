# YDG 图片与 CP932 字库页面

## 路线与依赖

YDG 是 YU-RIS 图片资源，不是 YBN 剧情字节码。先按 [YU-RIS 主流程](../yuris.md) 解包到新目录，再处理选中的图片或字体资源目录。

| 模块 | 能力 |
|---|---|
| [yuris_ydg.py](../../python/engines/yuris_ydg.py) | 格式 100、可变头长度、QOI/WebP 分块、RGBA 解码与模板回填 |
| [yuris_font.py](../../python/engines/yuris_font.py) | 明确 CP932 页序、网格、字形映射、加粗/描边/阴影及符号定位 |
| [yuris_ydg_workflow.py](../../python/engines/yuris_ydg_workflow.py) | 批量提取、PNG 回封、字库重建、原件与定位校验、新目录输出 |

图片转换需要支持 QOI/WebP 的 Pillow；字体重建另需 fonttools。当前验证环境为 Pillow 12.3.0、fonttools 4.66.1；缺依赖时给出错误，不影响原 YBN 流程导入。运行前可安装：

```text
python -m pip install Pillow fonttools
```

随包不带 GUI、原生加速 DLL、字体文件或第二份日繁字表。算法来源及授权见 [来源记录](../../provenance/yuris-ydg.json)。

## 识别与结构

- 文件头必须是 `YDG\0YU-RIS\0\0`，`0x0C` 的格式版本为 100。
- `0x10` 为头部长度，`0x14` 为文件总长度；当前支持头长度 `0x24..0x1000`，头扩展字节保留。画布宽高位于 `0x20/0x22`，均为 u16。
- 分块数位于头长度指定的位置，其后每项 16 字节：`u32 offset / u32 size / u16 x / u16 height / u32 reserved`。低 16 位是横向坐标，不视为类型标志；最后四字节含义未知，保留原值。
- 按分块表顺序累计纵坐标，解码块宽加 `x` 不得超出画布，块高须等于表中高度，总高须等于画布。未覆盖的边缘为透明，回填不能在那里添加无法由原分块表示的像素。
- 分块编码由 `qoif` 或 `RIFF...WEBP` 判断，不按扩展名或首块推断全部块。QOI 通道数、colorspace、终止标记、opcode 消耗长度及像素总量检查；WebP 检查 RIFF 长度、画布预算及单帧约束。
- 分块不得重叠或越界；表顺序与实际存储顺序可以不同。单文件最多 128 MiB、画布最多 8192×8192 且不超过 16M 像素；批量最多 1024 文件、累计输入和产物分别不超过 256 MiB。

## 提取与 PNG 回封

```text
python -m python.engines.yuris_ydg_workflow extract "<解包目录>/images" "<新图片工作区>"
python -m python.engines.yuris_ydg_workflow pack "<图片工作区>" "<新YDG结果目录>"
python -m python.engines.yuris_ydg_workflow pack "<图片工作区>" "<新YDG结果目录>" --images "<修改后的PNG目录>"
```

`extract` 可选单文件或递归目录。批量输出位于扫描目录之外；目录内存在旧提取工作区时拒绝，防止重复处理产物。每个文件保留相对路径：

```text
<图片工作区>/
  original/<原相对路径>.ydg
  images/<原相对路径>.ydg.png
  metadata/<原相对路径>.ydg.png.ydg.json
  reports/extraction.json
```

sidecar 与报告绑定原件 SHA-256、尺寸、分块定位和编码信息。回封先重新解析原件，再比对元数据；PNG 文件集合和尺寸必须一致。上游工具的旧 sidecar 不作为本流程的可信回填基准，应从原 YDG 重新提取。

writer 保留原头、表中坐标和保留字段、分块物理顺序、块间空隙与尾部；只更新变化块的编码字节、偏移、长度和文件总长。未改块保留原压缩流，原文仍经过解析、图像裁切及表重建并逐字节核对。修改块保持原编码类型，WebP 使用无损且保留透明像素 RGB 的编码。RGB QOI 块不能新增 alpha。

`pack` 输出原相对路径的 YDG 和 `reports/repack.json`。发布前重新解码，核对整张 RGBA 与 PNG 相同；任何文件失败都不发布结果目录。结果目录已存在时拒绝，不覆盖原游戏或旧结果。

## 字库识别与页序

字体文件名需匹配 `fnt_sSIZE_nPAGE.ydg`；普通 YDG 不自动当作字体。当前 CP932 页序 profile 来自工具的明确规则：

- lead bytes 按 `81..9F`、`E0..F0`、`FA..FC` 排列，只给至少一个可解码字符的 lead 编页号，页号从 1 开始。
- 每页 trail 按 `40..7E`、`80..FC` 排列，共 188 个位置；非法字节对保留空槽，不删除后重排。页 1 从 `8140` 开始。
- 这不是任意发行版的通用字体索引。`F1..F9`、单字节字体页、其他 lead 顺序或自定义字表需补充 profile 证据；现有代理字不在该 profile 中时拒绝，不能把 PUA 映射写入错误页面。
- 网格、字号、偏移及样式由配置指定，不能将一个资源的参数推广为默认。所有 CP932 位置必须有槽位，完整网格不得超出原图。

## 字库重建

先提取只包含目标字体页的工作区，再由 agent 核对网格和映射并执行：

```text
python -m python.engines.yuris_ydg_workflow font "<字体工作区>" "<新字体结果目录>" --font "<授权字体文件>.ttf" --config "<字体配置>.json" --mapping "<JIS结果>/jis-mapping.json" --mapped-only
```

配置示例为人工网格，必须按原图测量后替换：

```json
{
  "grid": {
    "font_size": 12,
    "cell_w": 24,
    "cell_h": 24,
    "columns": 19,
    "rows": 10,
    "offset_x": 0,
    "offset_y": 0
  },
  "style": {
    "bold": 0,
    "outline": 1,
    "shadow_x": 1,
    "shadow_y": 1,
    "fill": [255, 255, 255, 255],
    "outline_color": [0, 0, 0, 255],
    "shadow_color": [0, 0, 0, 128]
  },
  "symbol_rules": {
    "。": {"align": "bottom", "dx": 0, "dy": 0}
  }
}
```

- 不同字号可用 `grids` 替代 `grid`，键为文件名 `sSIZE` 的十进制 SIZE；没有对应配置时拒绝。`styles` 可按字体页相对父目录覆盖默认 `style`，不根据目录名自动猜加粗或阴影。
- `symbol_rules` 以实际目标字为键，可指定 `glyph`（显式替代字形）、整数 `dx/dy` 和 `align`（`baseline/center/bottom/left`）。只有明确规则才替代符号，不自动把缺字画成中点。
- `--mapping` 接收单字 `目标中文 -> CP932代理字` 字典、公共流程的 `jis-mapping.json`，或已启用 `character_substitution` 的 UIF 配置。重复代理、非稳定 CP932、profile 中无对应槽均拒绝。
- `--jis-preset` 使用随包公共 JIS 字表并核对哈希；不复制上游字表。它与 `--mapping` 互斥。完整预设可能影响原有日文/UI，优先用公共流程本次生成的映射。
- `--mapped-only` 只重绘映射涉及的槽，其余像素保留；省略则重绘有效 CP932 槽，仍保留非法字节对槽。每个相对目录内的每个字号分别校验页面覆盖，必须覆盖全部映射代理，否则整批拒绝。
- 使用字体 cmap 检查缺字，并检查字形及样式是否超出格子；缺字、空字形、裁切风险不静默降级。字号和符号位置不合适时修改配置后输出另一个新目录。
- 输出包括原相对路径 YDG、`preview/` PNG 和 `reports/font.json`，记录字节槽、目标字、字体哈希与配置。字体授权由使用者提供；不附带或安装字体。

## 与剧情、封包衔接

字库映射须与同批 YBN 的代理编码一致。已存在 `character_substitution` hook 时先核对实际渲染路径，避免同一代理同时被 hook 和字体二次替换。图像字库不保证会经过系统文字 API，须少量试注确认实际加载资源。

YDG 输出是资源回填结果，不自动推断 YPF 的版本或加载优先级。已确认 v482 时可用 [yuris_482.pack_archive](../../python/archives/yuris_482.py) 替换原成员，并重新解包核对 YDG、非目标成员及校验；其他版本不得套用该 writer。默认由 agent 在新结果目录完成回封及打包。

## 验证与限制

[test_yuris_ydg.py](../../tests/test_yuris_ydg.py) 使用合成 QOI/WebP/YDG 和生成的矩形字体，覆盖原文 parser/writer 往返、变长分块、中文 glyph 重绘、像素重解析、头扩展、保留字段、间隙、尾部、非法布局/截断/预算、manifest 篡改和不覆盖输出；另验证变长 YDG 进入 v482 YPF 后重新解包，非目标成员压缩流与归档尾部保持原样。

这些验证不包含商业游戏资源。尚未验证游戏字体页序、图像加载优先级、存档/UI 排版及游戏显示；未知 YDG 版本、动态纹理布局、动画 WebP 和其他字体 profile 不声明支持。
