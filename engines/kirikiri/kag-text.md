# KAG 明文剧本：Alter nm / np / exlink 方言

适用于已核对宏语义的 KAG `.ks`，不用于 PSB/SCN。入口 [kirikiri_kag_extract.py](../../python/engines/kirikiri_kag_extract.py)，语义层 [kirikiri_kag_text.py](../../python/engines/kirikiri_kag_text.py)，复用 KAG 词法器、公共翻译契约和 XP3 过滤器。按格式特征而非游戏标题分派。

## 识别与范围

- BOM 确定 UTF-16LE/BE 或 UTF-8，保留编码、BOM、CRLF/LF。无 BOM 或 CP932 不自动猜测。
- 已核对 `@nm t="显示姓名"`、`[np]` 结束一页并清除姓名、`[r]` 换行、`@exlink txt="选项"` 的宏语义。同名宏在别的游戏中仍需核对。
- 多行对白合成一条 `name/message`，物理换行在 JSON 中为 `\n`；`[r]`、已知音效/等待/字体等行内命令必须原样保留。独立行命令、标签、脚本块、宏定义不作为正文。姓名不跨页面继承。
- 只写姓名 `t` 和选项 `txt` 的引用字面值，voice、target、exp 等其他属性不变；动态属性拒绝，不执行表达式。
- `[漢字'よみ]` 的基底可译，注音和顺序保留；`[・]` 是保护标记。未知行内语法拒绝。对白中的注释不进 JSON，按原物理行插回。
- 不自动翻译系统宏、UI、动态生成文本或其他 KAG 方言；选择 scenario 目录不等于包含所有游戏 UI。

## Agent 执行流程

先确定索引、过滤器和输入范围。跨归档同路径覆盖、平铺 JSON 重名均拒绝，不能猜测加载顺序。过滤配置仅存算法和参数，不执行游戏提供的 TJS。

```text
python -m python.engines.kirikiri_kag_extract extract "游戏目录" "新的提取目录" --archives data.bin arc/extra.xp3 --members "scenario/*.ks" "01*.ks" --filter-spec "过滤器.json"
python -m python.engines.kirikiri_kag_extract pack "提取目录" "新的打包目录"
python -m python.engines.kirikiri_kag_extract pack "提取目录" "新的扁平补丁目录" --flat
```

提取产物是标准 `gt_input`、`gt_output`、`original`、`metadata`、`reports`，以及 `rebuilt/roundtrip` 与 `rebuilt/smoke-test`。smoke 为中文前缀变长测试，不能当实际译文使用。pack 将未提供译文的成员保持原样，使用原过滤器，封包后逐成员读回。`--flat` 生成根目录成员的 `patch.xp3`，否则保留成员目录生成 `scenario.xp3`；两者均是脚本专用包，**不能覆盖含系统/图像的完整 data.bin**。

源哈希、原文 JSON/manifest、条数、姓名槽、控制码、ruby、物理换行和非文本结构必须通过校验。回写重新解析并逐段比较文本区间之外的内容，不依赖偏移不变。未使用有损编码、截断或原位覆写。交付后由 agent 接收同名 `gt_output` 并执行回写，不把命令交给用户手动运行。

已有同名补丁先核对挂载关系。游戏缺字时检查实际选用的字体及归档中的字体资源，不能将普通 TTF 改名当作 TFT。
