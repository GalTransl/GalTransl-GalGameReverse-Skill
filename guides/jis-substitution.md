# CP932 中文回注：公共 JSON JIS 流程

确认**脚本正文**使用 CP932 后，中文回注优先走本页的公共流程。不要为了 JIS 给每个引擎增加 codec 参数、专用开关、冲突检查和 hook 配置生成逻辑。引擎只负责原有的文本语义、长度/偏移、加密和归档读写；公共层负责 JSON 中真实中文与 CP932 代理字符的转换及显示核对。

## 入口与适用条件

- [jis_workflow.py](../python/common/jis_workflow.py)：通用 `prepare` / `finalize` CLI，以及不依赖引擎的 `prepare_translations` API。没有引擎分支或注册表，不修改全局 codec。
- [jis_substitution.py](../python/common/jis_substitution.py)：SExtractor 固定映射、冲突检测、可选私用字符分配、配置及 hook 产物。仅依赖标准库，无需安装外部项目。
- 工作区采用主 Skill 的 `original/metadata/reports/gt_input/gt_output` 结构；引擎接受 UTF-8 的最小 name/names/message JSON，并已有严格 CP932 writer 与真实重提取能力。
- 必须确认**存储编码**。JSON 本身是 UTF-8，某些 manifest 的 encoding 也是交换层 UTF-8；都不能代替脚本编码证据。严格 shift_jis、UTF-8、UTF-16、GBK 不使用此流程，Kirikiri PSB/SCN 不因 XP3 文件名编码而触发它。
- 原脚本已使用 UIF 替换或 tunneling 时先识别原映射。工作区声明已有 source/target 字符表或已启用旧映射时，公共准备器拒绝直接叠加；应先制定合并/还原方案。游戏目录已有 hook 也需检查，不能用新子集配置覆盖仍在使用的旧映射。

## Agent 完成的四步

1. **准备工作副本。** 读取原 `gt_input` 和用户 `gt_output`，预留所有已导出的原文与译文中的直接字符；有已解码的系统文本、姓名表、UI 或控制参数时，一并作为 `extra_texts` 输入用于冲突检查。只转换译文 JSON 的显示字段，不转换文件名、资源路径或整份二进制脚本。原文、manifest、源资源和用户译文保持不变。
2. **调用原引擎打包器。** 给它公共目录中的 `workspace/`，把重建资源写入另一个新目录。原 writer 继续校验源哈希、条数、姓名可写性、控制语法、实际字节长度、标签/偏移并加密封包。JIS JSON 转换成功不等于引擎回写成功。
3. **真正重新提取。** 用原引擎提取器读取上一步实际生成的资源，得到完整的 `gt_input`，包括未翻译文件。不能直接拿准备目录里的代理 JSON 当作资源回读结果；只输出有变化成员的补丁，需在只读验证副本中补齐未变成员再提取。
4. **公共核对与交付。** `finalize` 检查准备目录快照未变、重提取的文件集合/行/姓名与预期代理文本一致，再反向还原并比对真实中文；未翻译文本也必须不变。全部通过后才在新交付目录发布重建资源、映射、配置和兼容 hook。

以下命令供 agent 执行，不默认交给用户手动运行：

```text
python -m python.common.jis_workflow prepare "原工作区" "新的JIS准备目录" --encoding cp932 --hook x86
```

然后调用对应引擎原有的打包和提取命令：输入 `新的JIS准备目录/workspace`，输出新的重建目录，再把实际资源提取到新的回读目录。最后：

```text
python -m python.common.jis_workflow finalize "新的JIS准备目录" "重建资源目录" "回读目录/gt_input" "新的交付目录"
```

`--hook x86` 仅在确认实际主程序为 32 位后使用；默认 `none` 不选 DLL。`--extra-text` 可重复指定额外已解码的 UTF-8 文本。准备器复制标准工作区四个来源目录，跳过旧 `rebuilt/`；当前文件/总字节预算为 128/512 MiB，超限明确报错，不使用硬链接、符号链接或覆盖用户目录来规避复制。

SystemC、ExHibit 已有的内联 JIS 接口保留兼容；走公共准备流程时关闭其自动处理（例如 `--jis-mode off`）。不要照这些旧接口再为其他引擎复制一套。特殊工作区可调用下面的公共 API 组织已有 parser/writer，仍不需要改引擎的编码函数。

## 固定映射与冲突处理

默认 `--proxy-policy fixed` 使用随包 SExtractor 2999 项固定映射：保留无损 CP932 字符，只替换无法编码且表中存在的中文。代理字若也出现在原文/译文的直接字符中则报错；未知汉字、emoji、不可逆 CP932 别名也报错，不截断、不填空格。

若固定映射与未翻译日文冲突，并选择使用兼容 hook，可重新准备一个结果，指定 `--proxy-policy unused`。它仍优先用固定映射，只为冲突字分配未占用的 CP932 私用字符 `U+E000..U+E757`。先收集整批原文、译文及额外文本，再按字符排序分配，所有文件共享同一映射，不受文件处理顺序影响；不会在字节写出后改变映射，池耗尽则报错。

这是本项目的自定义扩展，**不再兼容 SExtractor 固定日繁/JIS 替换字体**。报告会写 `remapped_count`、`custom_chinese_to_proxy` 和 `preset_font_compatible=false`。必须使用本批配置对应的 hook，或按本批映射定制字体。私用字符能离线编码不代表游戏的渲染和 hook 已实测，仍先小规模试注。

全部原文的保守预留可能拒绝已完全被替换的代理字；有证据证明不再使用时才缩小预留范围。未知外部 UI、其他归档和旧补丁仍需补充文本清单与运行测试，不能把本次扫描当成全游戏显示保证。

## 公共 API

```python
from python.common.jis_workflow import prepare_translations

plan = prepare_translations(
    original_rows_by_filename, translated_rows_by_filename,
    encoding="cp932", extra_texts=decoded_ui_texts,
    proxy_policy="fixed",  # 有冲突且使用专用配置时可选 unused
)
# plan.stored 是代理文本；只在独立工作副本中供原有引擎 writer 使用。
# 原 writer 校验、重建、再从真实产物提取后：
verification = plan.verify(actual_reextracted_rows_by_filename)
# 与重建资源一起通过 write_new_tree 发布到新目录。
artifacts = plan.codec.artifacts(include_hook=True)  # 已确认 x86 时
```

`plan.original`、`plan.translated` 保留真实文本，`plan.stored` 仅含提供译文的文件；verify 要求所有原文文件的实际回读。转换不会修改原输入对象或原 manifest。纯 API 不自动识别已有游戏映射，由调用方先完成检查。低层 `JisSubstitution` 与公共契约的 `text_codec` 接口仍可供既有集成使用，但不再作为每个新引擎的必改步骤。

## 目录与身份

| 准备目录内容 | 用途 |
|---|---|
| `workspace/original`、`metadata`、`reports`、`gt_input` | 原来源逐字节复制，原引擎正常读取 |
| `workspace/gt_output` | 只供 writer 使用的代理译文 |
| `chinese/` | 此次真实中文译文副本 |
| `support/` | 待核对的配置/hook，准备阶段不视为可部署产物 |
| `jis-plan.json` | 文件集合、准备快照哈希、映射策略与状态 |

最终交付保留重建资源的相对路径，并增加 `reports/jis-workflow.json`，分别记录存储文本核对、中文还原核对和运行时未验证状态。相同条数的译文重排仍不能靠普通 JSON 自动识别，必须保持原顺序。`finalize` 依赖 agent 提供真正的引擎回读，不自行猜归档格式，也不以自身 JSON 互转冒充重封包验证。

## 用户下一步与显示部署

发生实际字符替换时，公共流程在**最终交付目录**输出：

- `uif_config.json`：source 是 CP932 代理日文/私用字符，target 是真实中文；tunneling 关闭。方向不可颠倒。
- `jis-mapping.json`：固定表版本、实际映射、私用字符分配、固定字体兼容性与冲突清单。
- `winmm.dll`：已选择 x86 时附带仓库固定哈希的 [UIF 工具](../assets/uif/README.md)，与配置在一起；不自动安装或执行。
- `JIS-部署说明.txt`：本批 hook/字体条件与显示测试步骤；不生成字体。

agent 最终必须给出实际目录和操作说明。使用兼容 UIF 的 `winmm.dll` 代理时，将匹配游戏位数的 DLL 与本批配置放到实际游戏 EXE 目录，再按引擎既有规则部署资源；已有同名文件先检查、备份或合并，不叠加两次替换。恢复中文后，游戏还须选用包含中文字形的普通字体。

只有 `preset_font_compatible=true` 且预设字体冲突清单为空时，才考虑映射版本匹配的 SExtractor `WenQuanYi_cnjp.ttf` / `MSGothic_WenQuanYi_cnjp.ttf`，并让游戏实际选用。普通日文/繁体字体不能还原代理字。使用 unused 私用字符映射时，上述固定预设字体不可用；选择本批 hook 配置或定制字体。不要同时开启 hook 字符还原和替换字体。

让用户先测试一个开场文件或前几句，检查对白、姓名、选项、未改日文、标点和换行。显示结果反馈后再由 agent 调整映射、字体或经证实支持的编码方案；回写与配置准备由 agent 执行。覆盖游戏、安装 hook/字体、启动游戏沿用主 Skill 授权边界。

## 来源与验证

固定表和低层语义的来源见 [jis-substitution.json](../provenance/jis-substitution.json)，私用字符规划和 JSON 公共流程为本项目新增实现。测试位于 [test_jis_substitution.py](../tests/test_jis_substitution.py) 与 [test_jis_workflow.py](../tests/test_jis_workflow.py)：覆盖冲突、稳定分配、快照篡改、姓名/多人名、引擎控制码拒绝，以及两个不同引擎的原 writer、重提取和公共交付。游戏运行记录只放各游戏结果目录。
