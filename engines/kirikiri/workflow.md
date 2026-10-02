# Kirikiri 通用工作流

格式分流和批处理入口见 [引擎页](../kirikiri.md)。本页用于定位失败层、适配新方言和制作补丁。

## 从证据选择下一步

| 现象 | 下一步 |
|---|---|
| XP3 索引无法解析 | 检查索引版本、跳转块、名称表和段范围 |
| 索引可读，正文 Adler-32 不符 | 检查过滤器、参数、成员偏移与解压顺序 |
| 校验通过，PSB/KAG 解析失败 | 研究内层封装或脚本方言，不继续盲换密钥 |
| 脚本可读，语义/缓存校验失败 | 比较正常与异常记录，补齐字段和派生规则 |
| 回读正确，游戏未显示修改 | 检查补丁挂载、资源名、优先级及认证 |
| 修改生效，但中文缺字 | 检查实际字体及其字符覆盖 |

标准索引的 `plain` 标签不表示正文必然明文；`0x80000000` 标志也不能确定加密算法。参数取自已确认的配置或已知明文恢复，至少验证两个不同内容成员，再校验全部选中脚本。

## 可执行探测流程

从项目根目录执行 [kirikiri_probe.py](../../python/engines/kirikiri_probe.py)：

```text
python -m python.engines.kirikiri_probe "游戏/data.xp3" --members "scenario/*.ks"
python -m python.engines.kirikiri_probe "游戏/data.xp3" --members "scenario/*.ks" --recover-akabei-png
python -m python.engines.kirikiri_probe "游戏/data.xp3" --members "scenario/*.ks" --filter-spec "filter.json" --verify-repack
```

- 默认最多检查 512 个成员、64 MiB 明文。超限时缩小成员范围，不无界载入媒体包。
- `--recover-akabei-png` 最多取 8 个、各不超过 8 MiB 的 PNG，以完整 Adler-32 和 PNG CRC 验证种子；至少两个不同明文哈希通过才报告候选。候选不会自动启用，核对后写入过滤器配置。
- `--verify-repack` 重建内存归档并逐成员读回，只验证容器/过滤器，不验证对白回填或游戏加载。
- 配置只含算法名和参数，例如 `{"algorithm":"akabei","seed":798088789}`；示例 seed 不能直接用于其他归档。

已支持的 SCN 可直接使用过滤配置：

```text
python -m python.engines.kirikiri_extract extract "游戏目录" "新的提取目录" --archives data.xp3 --filter-spec filter.json --verify-edits
python -m python.engines.kirikiri_extract pack "提取目录" "新的打包目录"
```

一次调用使用同一配置，回填沿用报告中的配置。独立过滤器 writer 输出标准 File 索引；eliF 输入使用它时需明确 `--output-format plain`。`senren-cx` 适配器不能再叠加独立过滤器；Hxv4 走 [专用流程](hxv4.md)。

## SCN 常见语义差异

| 结构或错误 | 处理规则 |
|---|---|
| `SCN derived text mismatch` | 比较正文、speech/search 缓存和长度，按错误中的成员、scene/text/cache 定位；不删除校验或保留旧缓存 |
| 字面括号 `\[文字]` | 保护 `\[` 与结束 `]`，内文可译；按显示的括号重建长度/缓存。当前只接受单行、闭合、无嵌套和内嵌控制码的形式 |
| ruby 读音去中点或去两端全角空格 | 仅当源缓存精确匹配时记录 `strip_ruby_dot` / `trim_ruby_space`，回写沿用；不清除正文或注音内部空格 |
| 带长度的多语言 tuple 末尾为整数零 | 保留尾字段，按字段类型判断布局，不把 voice 列表误当语言数组 |
| `[display, "%i1&资源名;", 1, alt]` | 第四项导出为 `image-alt`；只改 alt，保留图片引用、图元计数与其他字段 |
| `phonechat` 历史快照 | 当前原样保留；需证明与正文的绑定及恢复逻辑后才能同步翻译 |

无 `text`、无 `language` 的选项只有以下结构可作为非文本记录保留：

- 仅含非负整数 `selidx`。
- 至少包含 `selidx/storage/target`，只允许额外出现 `button/close`。`storage` 必须等于所属 SCN 的 `name`；`target` 为 `*` 加 1–255 个字母、数字、下划线、点或连字符（允许日文）；`button` 为 1–32 个 ASCII 字母、数字、下划线、点或连字符；`close` 只允许布尔节点或字符串 `true/false`。

空对象、布尔索引、负索引、未知字段或缺少必要字段均拒绝。这些记录在语言选择前识别，位置和键集记入 `skipped_structural_choices`；带 `language` 的记录仍须验证所选显示字段。按钮图像/UI 中的文字另行检查。

## 适配新文本方言的方法

1. **固定失败层。** 保存源哈希、成员、版本和字段位置，收集正常/异常记录，统计全部结构差异。不要只修第一条报错。
2. **确认显示语义。** KAG 静态核对宏定义中的姓名、清名、分页、换行、选项和 ruby；SCN 按字段类型和关系区分正文、显示名、内部 ID、voice、长度与缓存。未知附加字段不能任意忽略。
3. **列出写入依赖。** 确认长度单位、缓存转换、共享字符串及其他语言/历史副本的引用。不能仅按文本相等绑定，也不能沿用过期缓存。
4. **扩展正确模块。** 索引变体进归档层，密码进过滤器，标签进 KAG 语义层，tuple 进 SCN parser/writer；复用导出与 manifest，不新增按游戏名分派的脚本。
5. **验证读写两端。** 补合成正反例和旧方言回归，完成原文往返、中文变长、重新解析、非文本结构比对及重封包读回。格式规范化产生的差异须能解释；游戏显示单独验证。

KAG 词法需区分 ruby 中的单引号与属性引号，`[[` 表示字面左括号；脚本块不执行，动态表达式不作为可写姓名。字符/字节偏移分开，保留源编码、BOM 和换行。

### 过滤器接口

[kirikiri_filters.transform](../../python/archives/kirikiri_filters.py) 的签名为 `transform(data, checksum, spec, offset=0, encrypt=False)`。checksum 是明文 Adler-32，offset 是整个成员的逻辑偏移；配置拒绝未知字段、布尔值冒充整数和超界参数。

[kirikiri_filtered.py](../../python/archives/kirikiri_filtered.py) 统一处理分段解压、逻辑偏移过滤、合并、校验与封包。新算法若作用于压缩字节、修改文件头或跨成员维护状态，需另建适配器。`stripe` 加解密方向不同，不能将所有过滤器视为对称 XOR；回写使用新明文 checksum。

## 译文回注：优先使用 patch.xp3 增量补丁

1. **确认挂载。** 静态检查 `startup.tjs`、初始化脚本及必要的 EXE 启动资源，追踪 `useArchiveIfExists`、`Storages.addAutoPath` 等调用及分支。确定补丁搜索目录、覆盖顺序、编号与缺号终止条件；只出现文件名字符串不足以证明会加载。
2. **筛选变化成员。** 按 manifest 校验 `gt_output`，先完成脚本回填，再与原始资源比较。仅将真正变化的文件加入补丁。
3. **确定路径。** 常见 `patch.xp3>` 根目录挂载使用原 basename 和完整扩展名，不保留 `scenario/`、`scn/`。若目标按完整路径查找则保留路径；同名冲突不能合并。Hxv4 还需修改名称表的目录哈希。
4. **使用匹配的 writer。** 普通 XP3、独立过滤器、Cx/Hx 分别使用对应实现。不能把 `scenario.xp3` 简单改名当作补丁。
5. **验证成品。** 在新结果目录生成补丁，重读索引、认证和全部成员，核对名称、变化集合、译文及非文本结构。
6. **测试加载。** 在授权范围内部署到已确认的位置，保留已有补丁；完全退出后重启并进入修改段落，必要时从新游戏开始以避开存档缓存。不生效时按位置/编号、挂载条件、优先级、名称、格式、认证的顺序排查。

[Hxv4 扁平补丁](hxv4.md#hxv4-扁平-patchxp3) 使用 `build_flat_patch` 保留成员身份、调整根目录哈希并生成 Poly1305 标签。普通 SCN/Hxv4 文本 `pack` 输出可能包含完整脚本集合和原目录，仍需变化筛选与路径适配；不要虚构 `--patch` 或 `--flatten` 参数。KAG 的 `--flat` 用法见 [KAG 页面](kag-text.md)。

**交付时最后提醒用户**：显示缺字、方框或部分字符空白时，考虑替换 `data.xp3` 中实际使用的字体。先确认字体资源和加载方式，再生成替换补丁或新包，不直接覆盖原包。

## 验证与交付

归档、解密、语义提取、回填、补丁加载和游戏显示分别报告。回归覆盖坏参数/校验、截断、预算、跨段偏移、加解密方向、变长文本和未修改数据；KAG token 拼接应恢复完整输入，语义回填还需比较代码、控制、资源和非目标语言。

```text
python -m unittest discover -s tests -p "test_kirikiri*.py" -q
python tools/check_skill.py
```

运行报告只放结果目录。按主流程交付概况表和具体试注建议；译文放回同名 `gt_output` 后由 agent 回写。误改 `gt_input` 时先保存修改，再从可靠原始数据恢复，不改 manifest 绕过检查。
