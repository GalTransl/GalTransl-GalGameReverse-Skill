# Unity TMP 字体构建与接入方法

本页是 TextMeshPro 字体的调查、构建和接入方法论；当前随包工具尚未实现 TMP 烘焙器或通用字体资源替换器。完成剧情回写不等于完成字体适配，也不能把现有 Utage book writer 套用到 TMP 对象。

## 先确认用的是哪套字体

从实际缺字的文本组件追踪引用：`TextMeshProUGUI` / `TextMeshPro` → TMP FontAsset → Material → atlas Texture2D，同时检查局部 fallback、TMP 全局设置和材质预设。记录容器及每个引用的 `(fileID, pathID)`，跨文件引用还要解析外部表；不能只按字体名字或资源发现顺序选“主字体”。

普通 `UnityEngine.UI.Text`、Utage 自定义文本组件等可能使用 Unity Font，而不是 TMP。先确认组件和渲染路径，不因为游戏使用 Unity 就构建 TMP。对话、标题、菜单和 ruby 注音也可能使用不同字体。

| 症状 | 优先检查 |
|---|---|
| 特定字显示方框 | 字符覆盖、fallback 链、实际选用字体 |
| 显示成另一个正常汉字 | Unicode 到 glyph index 的对应关系、是否只换过源字体 |
| 字体碎片或重复纹理块 | glyphRect、atlas 页索引、纹理数据是否来自同一套构建 |
| 粉色文字/矩形 | shader、材质与目标渲染管线 |
| 只有部分界面缺字 | 不同组件、字体或材质预设的引用 |
| 资源损坏或加载失败 | Unity/TMP 序列化版本、容器、偏移和外部引用 |

## 选择修复路径

- **追加 fallback**：目标的 fallback 查找链可用时，优先保留原字体，为缺字添加匹配的 TMP FontAsset。单独放一个 TTF 或 bundle 到游戏目录不会自动接入查找链，必须确认资源引用或加载器。
- **重建静态 TMP**：按明确字符集烘焙 character/glyph 表、SDF atlas 和材质，适合确定译文范围的资源替换。
- **动态 TMP**：依赖可用的源 Font 和目标运行时的动态填图能力。不能只把 `m_AtlasPopulationMode` 改成 Dynamic 就宣称支持中文；还要检查 source Font、图集容量、多图集与 fallback 行为。

Mono 与 IL2CPP 影响运行时插件的接入方式；静态字体资产是否兼容仍取决于实际 Unity/TMP 版本与资源布局。不要把 Mono 插件的适用范围扩大到 IL2CPP。

**动态字体也可能已经保存非空 character/glyph 表。只替换源 TTF/Font，会让旧 glyph index 指向新字体的其他字形，产生“正常汉字但显示错误”的结果。** 应完整重建匹配的数据，或使用经过验证的清表与重新填图流程，不能靠修改译文或伪造字符别名掩盖问题。

## 准备字符集与字体源

1. 从已校验的最终回写文本收集 Unicode code point：同名 `gt_output` 有译文时取译文，否则取原文。还要覆盖保留的姓名、选项、UI、数字、标点、日文和实际变量展开值。共用字体时，考虑保留原字体覆盖，避免修好剧情却破坏其他界面。
2. 按真实文本语法排除不显示的控制信息。不要用“删掉所有尖括号内容”替代解析：ruby 属性中可能有可见注音，变量标签本身不是最终显示值。变量值未知时记录覆盖缺口，并补充代表性运行数据。
3. 按 Unicode 标量去重，不按 UTF-16 单个 `char` 拆分非 BMP 字符。不把换行、制表符当作普通字形；保留所需空格和组合标记。变体选择符、组合序列和 shaping 需要额外验证，单字符表覆盖不能证明这些序列正确。
4. 保存 UTF-8 字符集文件、code point 清单、输入范围与 SHA-256。先构建小规模试注字符集，再扩充全量，避免一开始盲目烘焙整个 CJK 区段。
5. 选择覆盖所需字符的 TTF/OTF；TTC、可变字体或特殊 face 先确认 FontEngine 支持并明确选择的 face。记录字体来源、版本、SHA-256 和许可；未核实再分发许可的字体不放入仓库或公开产物。

## 从源字体构建 TMP 资产

使用独立、干净的 Unity Editor 工程，记录精确 Editor 版本、TMP package 版本和构建平台；优先与目标一致。相同大版本只能作为候选，不能证明 raw MonoBehaviour 可直接互换。不要导入和执行游戏提供的脚本来完成烘焙。

构建顺序：

1. 导入源 Font，并准备所需 TMP shader/资源。通过 Font Asset Creator 或该版本 Editor API 创建字体资产；字符来源选前一步的字符集，避免误选仅 ASCII 的默认集合。
2. 明确 sampling point size、padding、SDF render mode、atlas 宽高及页数预算。先以目标字体的清晰度、描边和实际显示字号为参考；这些参数共同决定图集容量与材质采样，不能单独替换 atlas 后沿用不匹配的参数。
3. 将所需 code point 加入字体，检查缺失列表。源字体缺字与图集容量不足要分别处理：前者换源字体或增加 fallback，后者调整尺寸、采样或分成多字体/多页；不能把失败字符映射到任意已有字形来凑覆盖率。
4. 需要自动化时，可围绕对应版本的 `TMP_FontAsset.CreateFontAsset`、`TryAddCharacters(uint[], out uint[], ...)` 组织 Editor 构建。先确认版本接口；在临时 Dynamic 资产中填充后转 Static 是一种候选流程，转换后仍需保存、重新加载并验证全部表与 atlas。
5. 单图集放不下时，只有确认目标支持多图集、相应页索引及材质切换后才启用。否则拆分为 fallback 字体。不要把多页 donor 简化为一张贴图，或丢掉非零 `atlasIndex` 的字形。
6. 保存完整 FontAsset、配套材质、所有 atlas 页；Static 资产不应依赖运行时继续补字。重新加载工程中的资产，检查 character table、glyph table、metrics、glyphRect、atlas 页及材质引用，再按确认的接入方式构建候选 AssetBundle。

没有匹配 Editor、TMP package 或源字体时，保留字符集与明确的构建参数，说明缺少哪个构建条件；不得把准备好配置写成“已生成可用字体”。本页没有提供可直接运行的构建脚本。

## 接入原游戏资源

新建 AssetBundle 不会自动替代游戏字体；先确定采用显式加载与 fallback 接入，还是重建原资源对象。容器和 TMP schema 不完整时继续研究，不直接进行字节搜索替换。

资源级替换应将下列内容作为配套数据处理：

- character table 的 Unicode → glyph index、glyph table 的 metrics/rect/atlasIndex、face metrics；
- 全部 atlas 页及其尺寸、格式、mip、色彩空间、平台数据与内联/流式状态；
- 材质中的 atlas 引用、纹理尺寸、SDF gradient scale 与相关采样参数。

保留目标对象身份、MonoScript、FontAsset/Material/Texture 的既有引用关系。PPtr 重映射必须核对完整 `(fileID, pathID)` 和所属文件，不能只按同一个整数 PathID 全局替换。新增长度或对象时由理解该容器的 writer 修复索引、大小和偏移。

保留目标 shader 前要确认它能解释 donor 的 SDF 模式和材质参数；不盲目搬入另一个渲染管线的 shader，也不把保留目标 shader 当作兼容性保证。多材质预设、粗斜体字体引用、fallback 链等也需重新核对。

流式 atlas 要同步处理完整像素 payload、stream offset/size/path 与 Texture2D 字段。仅验证字节数相同不足以证明纹理正确；需要确认格式、页序、glyphRect 和实际渲染。

## 验证与交付

先在新目录构建单字体候选，重读容器和字体对象：

1. 所需字符都有明确 character entry，引用的 glyph 存在；正常空格可能没有可见矩形，不应仅因零尺寸而判坏。
2. glyph 的 atlasIndex 有效，rect 位于对应页内；字体 metrics、图集及材质属于同次构建。合法 cmap 可能让多个 Unicode 共用一个字形，应核对来源，不能把所有共用索引都判错，也不能伪造别名冒充缺字修复。
3. 名称、对象身份、MonoScript、外部引用与非目标对象保持预期；材质、atlas 页、fallback 的引用全部可解析。
4. 分别报告“字符集准备、Editor 烘焙、资源接入、离线回读、游戏显示”的完成状态。Editor 保存成功或容器可重读，均不能代替游戏渲染验证。

小规模显示测试应覆盖中文、保留日文、标点、数字、ruby、描边、换行与长句，以及实际共用字体的界面。重新启动游戏避免旧 atlas 缓存干扰，检查字形、错字、裁切、行距和日志；异常时恢复已有备份，不叠加猜测性修改。

构建报告放游戏结果目录，记录 Unity/TMP 版本、平台、源字体与字符集哈希、采样/padding/SDF 模式、atlas 尺寸/页数、缺失字符、目标引用、输出哈希和未验证项。文档与仓库不记录逐游戏验收或包含游戏文本/字体二进制。

默认由 agent 准备字符集、组织构建和生成候选；依赖齐备后实际执行，不只把命令交给用户。覆盖原游戏、安装运行时插件和启动游戏沿用主流程授权边界。只在需要字体源、版本或工具位置等缺失信息时向用户索取对应信息。
