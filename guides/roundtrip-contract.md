# JSON、独立 manifest 与回填身份

## 翻译 JSON 的最小交集

```json
[
  {"name": "向导", "message": "正文"},
  {"message": "旁白"}
]
```

- 顶层有序数组，每条是对象，`message` 为字符串，`name` 可省略。
- UTF-8 输出；真实换行、字面量 `\n` 和控制标签须分开处理，由引擎适配器负责转换。
- 不输出翻译缓存的 `pre_src`、`pre_dst`、LLM响应对象或反汇编 Custom JSON。
- 不能按原文去重；相同正文可能处于不同场景、不同说话人和不同引用位置。
- 空字符串、姓名缺失与姓名为空应按具体格式保留；不要任意“清理无用条目”。
- `names: ["甲", "乙"]` 是 GalTransl/VNTextPatch 的多人名兼容扩展，不是所有外部工具都支持。基线使用可选字符串 `name`；需要多人名时明确采用扩展，保留姓名槽数量。不能只取首个名字或合并成不可逆字符串。

[contract.py](../python/common/contract.py) 提供严格 JSON 读取、基础格式校验和 sidecar 生成。不读取游戏、不选择引擎、不把原始 bytes 自动变成对白。

## 独立工作区

目录名可自定，推荐结构（`gt_input`/`gt_output` 是 GalTransl 的交接约定：前者是导入项，后者接收译好的结果）：
```text
work/
  gt_input/       # 只含提交翻译的 JSON；平铺、文件名=剧本名；交给翻译器 / 导入 GalTransl
  gt_output/      # 接收译好的结果；同名平铺，回填按文件名配对
  original/       # 原文件副本；保留容器链及多文件配套
  metadata/       # manifest、控制码映射；不交给翻译器修改
  rebuilt/        # 通过校验后生成的新脚本
  reports/        # 数量、哈希、结构与部署验证
```

`gt_input` **平铺、不放子目录、不放没有对白的文件**：解析成功但零可翻译行的成员记为 `empty`，不进入翻译队列；在报告保留来源、阶段与结论。能取得真实剧本名时，优先用经过安全校验的真名；未知名称或 basename 冲突时用可追溯的占位/消歧名称，并保存来源到文件名的明确映射，不从输出名字猜回填位置。

保留游戏原件不动。不要依赖 SExtractor 的 `ctrl/all.orig.json` 或 GalTransl 的缓存目录；它们不是本 Skill 的前置条件。`gt_output` 里的内容是用户提供的，**不是可信输入**：回填前仍必须按 manifest 校验源哈希、条数、顺序与姓名槽。

## manifest 必须保存什么

`make_manifest()` 的基础 schema 为 `galgame-roundtrip/1`：

| 字段 | 意义 |
|---|---|
| `engine.id/variant/reference` | 引擎、确切方言和参考实现版本；不能只写 `.bin` |
| `sources[]` | 相对路径、原始大小、SHA-256；多文件引擎全部纳入 |
| `translation.count/source_rows_sha256` | 原文导出的条数与规范化摘要 |
| `translation.order` | 明确要求保持顺序，并记录等长重排不可检测 |
| `records[].id/position` | 元数据中的稳定条目标识及数组位置 |
| `records[].locator` | **真实解析器提供**的节点、指令、文本表或字节区间 |
| `records[].name_policy` | `absent`、`context` 或 `writable` |
| `records[].message_tokens` | 从源消息提取的受保护字面量，不是可执行正则 |
| `encoding/settings` | 当前引用实现使用的文本编码及引擎参数 |

实际引擎可在 `settings`/`locator` 中记录 BOM、换行、原字节、opcode、引用列表、池基址、压缩/加密、分段或辅助文件信息；必须使用有版本、可校验的 JSON 数据结构。manifest 本身也不可信，不能 `eval` 内容、按它的绝对路径任意读写，或无验证接受地址。

## 最小集成示例（不是游戏格式解析器）

下面假定真实引擎解析器已经找到文本节点，不用伪造 offset；`[[TOKEN]]` 只是人工示例的受保护标记，不代表任何引擎语法：
```python
from python.common.contract import make_manifest, validate_translation

sources = {"scenario/intro.txt": b"original fixture"}
rows = [{"name": "Guide", "message": "hello[[TOKEN]]world"}]
locators = [{"kind": "fixture-node", "node": 0}]
manifest = make_manifest(
    engine="synthetic-example", variant="not-a-game-format", reference="example-1",
    sources=sources, rows=rows, locators=locators, encoding="utf-8",
    name_policies=["context"], protected_tokens=[["[[TOKEN]]"]],
)
translated = [{"name": "Guide", "message": "你好[[TOKEN]]世界"}]
validated = validate_translation(manifest, sources, rows, translated)
# 下一步必须由实际引擎 writer 按已校验的 locator 重建结构。
```

`context` 人名只能辅助翻译，不能随正文改写；外部提供、间接引用或动态解析的姓名，应回到其真实定义处，另用已证明的 writer 处理。可写的人名必须由 parser 明确标记 `writable`。

## 不能承诺的自动校验

纯 name/message 数组没有条目身份。sidecar 的 ID 留在原位置，但译文 JSON 若被**等长重排**，校验器无法知道字符串属于哪个旧位置。源哈希、原文摘要和相同条数都解决不了此问题。

因此：
- 翻译全过程必须保留文件对应关系、数组顺序、记录数量和姓名槽。
- 需要拆分/合并/重排时，用显式 ID 映射机制控制翻译过程，再还原为原顺序；禁止用正文相似度猜配。
- `validate_translation()` 是必要的基础校验，不是游戏语义验证。它只比较列出的字面量控制码数量；控制码的顺序、嵌套、转义和禁止新增的命令还需引擎检查。
- 单个 manifest 的 `encoding` 只是基础校验编码。混合编码、多池编码、特殊长度单位要由适配器补充；不能据此擅自把 CP932 游戏改成 UTF-8。

## 来源链与批次发布

保存原归档、成员身份、解码层次与回填基准之间的关联；多文件配套全部纳入来源校验。索引或目录摘要只证明它实际覆盖的范围，不能替代成员内容及回填基准的 SHA-256。

locator 必须与重新解析的原始输入核对；不能信任可编辑 sidecar 的任意地址。共享文本的每次引用仍有独立身份，不能因原文相同就覆盖另一位置的译文。

只给成功成员发布 JSON/manifest；成员 `blocked` 不允许保留失败前的部分行当成成功产物。批次可有 `partial`，必须列明成功、blocked、skipped、non_target，不能因存在若干导出文件就宣称整个包完成。`empty` 也须单独计数；输入枚举必须排除本次及历史输出目录，避免把产物再次作为游戏输入。

## 回填发布前

确认 source 文件集合/哈希不变 → original JSON 摘要不变 → translated 条数/字段/槽位有效 → 编码可表示 → 控制语法有效 → 完整重定位/长度/校验 → 重新解析 → 比对非文本数据 → 输出副本。

失败时保留原文件及上一次有效输出，报告首个明确原因和受影响条目；不要默认“跳过错误继续写成品”。
