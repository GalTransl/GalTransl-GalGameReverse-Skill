# Unity 文本定位流程与停止条件

本页说明在 Unity 游戏里找剧情文本的顺序。先运行 [只读扫描](../../python/engines/unity_scan.py)，再按下面的顺序逐步排除；每一步都写明什么情况下继续、什么情况下停止并报告。扫描不执行游戏代码、不写游戏目录，输出放结果目录。

```text
python -m python.engines.unity_scan "/game" --output "/work/unity_scan"
```

`scan.json` 的主要字段：`containers`（每个 `.assets`/serialized 文件或 UnityFS 包，以及包内每个 serialized 节点）、`streaming_assets`、`il2cpp_metadata`、`summary`、`budget`。`partial: true` 表示有容器因预算或错误没有扫完，先看 `budget.exhausted` 和各项 `error`，不要把“没扫到”当成“没有文本”。

## 1. StreamingAssets

StreamingAssets 里的文件按原样随游戏发布，常见 JSON、CSV、自定义脚本、SQLite 或独立 bundle。扫描对其中的非 Unity 文件给出编码猜测、熵和少量预览，对其中的 UnityFS 包按容器处理。

- 继续：只有第三方库自带文件（播放器、插件说明、服务配置等）或没有文本。
- 停止并转入对应格式：发现剧情样式的文本文件或数据库。这些不是 Unity 容器，按其实际格式另行适配，不走 TextAsset 工作区。

## 2. `*_Data` 下的 bundle 与 assets

依次看 `*_Data` 根目录的 `resources.assets`、`sharedassets*.assets`、`level*`、`globalgamemanagers*`，以及任意位置的 UnityFS 包（常见 `data.unity3d`、`Data/*.unity3d`、无扩展名文件、`.bundle`）。扫描报告容器版本、TypeTree 有无、对象类别统计和包内节点。

- 对象类别帮助判断资源性质：大量 `AudioClip`/`VideoClip`/`Texture2D`/`Sprite` 而几乎没有 `TextAsset`、文本类 MonoBehaviour 时，文本可能烘焙在图像或视频里。
- 停止并报告：UnityFS 版本不在 6–8、出现未知 flags（可能加密）、serialized 版本不在 17–22、big-endian 或 LZHAM。这些需要补齐容器证据，不能绕过。
- `.resS`/`.resource` 是贴图、音频、视频的原始数据，不含 serialized 对象；体积再大也不作为文本候选。

## 3. TextAsset 名称与编码

`textassets` 列出每个 TextAsset 的 `name`、`size`、`encoding`（`ascii`/`utf-8`/`utf-8-sig`/`utf-16le`/`utf-16be`/`cp932`/`binary`/`empty`）、`entropy` 和预览。

- 优先看名字成批出现、按章节/日期/角色编号命名、编码为文本且体积为几 KB 到几十 KB 的一组 TextAsset。通常它们集中在单独的剧情包里。
- 区分剧情与配置：行尾断行字符表、商店配置、语音/动作/模型列表等也是文本 TextAsset，但不是对白。列表类表格（例如语音或台词清单）是否被显示需要在游戏逻辑中确认，不要默认翻译。
- 找到后用 [TextAsset 工作区](../unity.md#textasset-整段替换) 原样提取并做原文往返；整段替换只验证容器层，剧情翻译还需要该脚本方言的 parser。
- `binary` 且熵 ≥ 7.5 的 TextAsset 会标 `suspected: encrypted-or-compressed`，转第 6 步。

### TextAsset 行式剧本的观察

已见到一类以 TextAsset 发布的行式剧本（UTF-8，可能带 BOM、CRLF）：

- `***命令_参数` 行是演出命令（背景、立绘、特效、场景跳转等），整行保留。
- `//` 开头是注释。
- 剧情块之间用空行分隔；块首行可能是 `显示名(语音ID)` 或单独的 `显示名`，后接正文；对白常用 `『』` 或 `「」` 包住，正文可跨多行（续行可能以全角空格缩进）。
- 无姓名的块是旁白，也可能多行折行。

块首行究竟是姓名还是单行旁白，不能只靠字形判断（独白可以有姓名而没有括号），也不知道折行是否被引擎合并、命令行中的参数是否会显示。确认这些需要读游戏的脚本解释逻辑（Mono 程序集可静态阅读 IL，不加载执行）。在拿到这条证据前，随包只提供整段替换，不发布这一方言的 gt_input 导出。

## 4. MonoBehaviour 类名

扫描读取每个 MonoBehaviour 头部（GameObject、enabled、MonoScript PPtr、`m_Name`），再通过本文件或其他已扫描文件中的 MonoScript 解析出 `命名空间.类名`，给出类名统计 `monobehaviour_classes`、未解析数 `monobehaviour_unresolved` 和最大的 20 个对象（含名称、类名、头部 4 KiB 内 CJK 字符数）。

- 留意数据表类脚本（ScriptableObject、表格导入生成的 `Entity_*` 一类、`*Data`/`*Table`/`*Scenario`），以及已知剧情框架类（例如 Utage 的 `AdvImportBook`，转 [Utage 路线](../unity.md#utage-book-profile)）。
- UI 组件（`Text`、`TextMeshProUGUI`、`UILabel` 等）通常只放界面文字；它们的字段布局需要 TypeTree 或程序集元数据才能完整解析。
- 大对象里只有资源键（场景、图片、语音编号）而没有自然语言文字时，说明剧情文字不在这里。
- 停止并报告：候选类的字段布局没有 TypeTree，也无法从程序集静态元数据确认。不要靠可打印字符串反推字段位置去写回。

## 5. global-metadata 字面量（不支持）

IL2CPP 游戏的 `il2cpp_data/Metadata/global-metadata.dat` 存放代码里的字符串字面量。扫描只报告它的存在和大小，**不解析**，也不提供写回：修改它需要同步 IL2CPP 的字符串索引和代码引用，且常有版本差异或加密。

- 只有在前几步都确认没有文本资产、且有证据表明剧情写在代码字面量里时，才把它列为候选，并明确告知用户当前不支持。

## 6. 高熵对象（疑似加密）

TextAsset 或其他对象为二进制、熵接近 8、没有可识别魔数时，可能被游戏自行加密或压缩。

- 停止并报告：列出对象名、大小、熵和所在容器。不要猜密钥、不要按字节搜索替换；密钥或算法需要从用户提供的输入或静态程序分析中取得证据后再补实现。

## 报告要点

按主流程用表格说明：扫描范围与 `partial` 状态、命中的容器与对象、编码、数量、是否完成原文往返，以及未覆盖的候选（例如只在图像/视频中出现文字、只存在于 global-metadata、疑似加密）。实际游戏名、路径和逐对象记录只放结果目录。
