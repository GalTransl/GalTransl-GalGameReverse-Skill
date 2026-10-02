# KAG 文本：nm / np / exlink 方言

入口：[kirikiri_kag_extract.py](../../python/engines/kirikiri_kag_extract.py)；语义层：[kirikiri_kag_text.py](../../python/engines/kirikiri_kag_text.py)。仅用于符合下述宏语义的 KAG 文本，PSB/SCN 走 [引擎页](../kirikiri.md) 的对应入口。

## 适用条件

| 项目 | 规则 |
|---|---|
| 编码 | UTF-8 或 UTF-16LE/BE BOM；保留编码、BOM 和换行，无 BOM/CP932 不自动猜测 |
| 姓名与分页 | `@nm t="显示姓名"` 设置姓名，`[np]` 结束一页并清名；姓名不跨页继承 |
| 正文 | 多行合成一条 message，物理换行映射为 JSON `\n`；保留 `[r]` 及已知行内控制 |
| 选项 | 只写 `@exlink txt="选项"` 的 txt，不改 target、voice、exp 等属性 |
| ruby | `[漢字'よみ]` 的基底可译，注音与顺序保留；`[・]` 为保护标记 |
| 非目标内容 | 命令行、标签、脚本块、宏定义和注释不导出；对白注释按原物理行插回 |

先核对宏定义，同名宏不保证同义。动态属性和未知行内语法拒绝；系统 UI、动态生成文本及其他方言需单独适配。

## 提取与打包

先确认索引、过滤器和成员范围。当前入口拒绝跨归档同路径覆盖与平铺 JSON 重名；需要先明确选择有效来源。

```text
python -m python.engines.kirikiri_kag_extract extract "游戏目录" "新的提取目录" --archives data.bin arc/extra.xp3 --members "scenario/*.ks" "01*.ks" --filter-spec "过滤器.json"
python -m python.engines.kirikiri_kag_extract pack "提取目录" "新的打包目录"
python -m python.engines.kirikiri_kag_extract pack "提取目录" "新的扁平补丁目录" --flat
```

提取生成 `gt_input/gt_output/original/metadata/reports`、原文 roundtrip 和中文前缀 smoke-test；后者不是正式译文。回填校验源哈希、原文与 manifest、条数、姓名、控制码、ruby 和换行，重读脚本并比较非文本结构，再按原过滤器封包、逐成员读回。缺少译文的成员保持原样。

| 打包方式 | 输出 |
|---|---|
| 默认 | 保留原成员目录的 `scenario.xp3` |
| `--flat` | 根目录成员的 `patch.xp3` |

两者均为脚本专用包，不能覆盖含系统/媒体的完整原包。`--flat` 只改变路径，不表示只包含变化成员；补丁挂载、已有补丁优先级与增量筛选按 [通用工作流](workflow.md#译文回注优先使用-patchxp3-增量补丁) 处理。

译文按同名放回 `gt_output` 后由 agent 回写。缺字时检查实际字体和归档资源；普通 TTF 不能仅改名当作 TFT。
