# 独立 Python 参考 API

## 包布局与调用方式

运行环境：Python 3.11+。在 Skill 根目录下使用 `from python.engines.<name> import ...` 或 `from python.archives.<name> import ...`。从其他目录集成时，将 Skill 根加入调用环境的模块搜索路径；不要把原上游仓库加入路径。

`python/engines/` 与 `python/archives/` 是**有限格式参考集合**，不是统一接口的自动处理器。文件名、公开函数和类可查询 [引擎目录](../catalog/engines.json)；函数参数和限制以模块及引擎页为准。相同扩展名或相似函数名不保证同样布局、语义或预算。

大多数叶子函数接收 bytes/str/结构对象及显式参数，返回新结构或 bytes，不直接写游戏文件。不要对内存返回值的存在作过度解释：`inspect` 可能返回原始压缩数据，字符串池函数可能尚未处理 VM 引用。

## 公共层

| 模块 | 主要接口 | 不负责的事情 |
|---|---|---|
| [binary.py](../python/common/binary.py) | `Reader`, `checked_slice`, `bounded_zlib`, `Edit`, `apply_edits`, `OffsetMap`, `relocate_u32` | 引擎识别、opcode推断、完整重定位、校验/外壳重建 |
| [contract.py](../python/common/contract.py) | `load_json`, `validate_rows`, `dump_rows`, `make_manifest`, `validate_translation` | 从脚本寻找对白、检测等长译文重排、全部控制语法/混合编码 |
| [safety.py](../python/common/safety.py) | `Limits`, `logical_path`, `validate_names`, `write_new_tree` | 约束调用前已经发生的内存分配、抵抗能并发替换可信目录的恶意进程 |
| [detect.py](../python/detect.py) | `detect_directory` / CLI；`candidates` 与 `candidate_stats` | 完整解析器、全格式识别、密钥匹配、自动选择writer |

不强制让每个已独立化的叶子模块依赖公共层；这样单个算法也能阅读和试验。但写出前仍必须套用统一契约和安全规则，不能因叶子函数没有文件 IO 就跳过验证。

## 安全写出示例

```python
from pathlib import Path
from python.common.safety import Limits, write_new_tree

# 假设真正的格式 parser 已在限额内解压，且未把重名 entry 丢进字典。
entries = [("scenario/example.txt", b"synthetic example")]
# 父目录必须已经存在且可信，目的目录必须尚不存在。
# 下面只演示调用，不会在阅读/import本文件时执行。
# write_new_tree(Path("/existing/work/new-output"), entries,
#                Limits(max_file_bytes=16 * 1024 * 1024))
```

`write_new_tree()` 先验证所有名字和预算、在临时同级目录中生成，再只发布到新的目的目录；拒绝替换已有路径。使用普通用户拥有的工作目录，避免链接/重解析点。该函数不是文件系统沙箱，也不应被用来覆盖原游戏。

## 预算分层

逐层设限，不要只设一个总数；参数名和计量单位以具体引擎模块为准：

| 层 | 控制对象 |
|---|---|
| 枚举/索引 | 输入文件数、归档数、成员数、索引字节与扫描深度 |
| 单成员 | 存储字节、解码字节、解码算法的符号/步数与结构项数 |
| 累计 | 已解码字节总量、产物总字节（含 original/JSON/metadata/report） |

索引有界不等于流程无限流式：选中成员、解码 bytes、JSON 与待发布集合仍可能驻留内存。预算必须在分配与实际产出阶段检查，单项上限不能替代累计上限。不同计量单位的限额不能机械设成相同数值；按对应算法验证关系。超限要如实报告，不能截断文本后称成功。

## 每个成员的结论怎么记

不要只报总数。每个成员至少记录来源、已到达阶段、状态、原因及产物；可用以下状态约定：

| 状态 | 含义 |
|---|---|
| `success` | 报告所指阶段完整成功；提取成功不代表回填或加载成功 |
| `empty` | 完整解析与语义导出通过，但零可翻译行；保留诊断，不生成翻译文件 |
| `blocked` | 格式、语义、编码或必要条件无法验证；不发布失败前的部分 JSON |
| `non_target` | 按实际检查的内容确认不属于目标范围，不能与成功导出混算 |
| `skipped` | 因预算或明确筛选策略未完成检查，必须记原因，不能计入已验证 |

不支持的封装不等于已确认的非目标；需要内层内容才能判断时，应报告被阻挡。批次部分完成须标 `partial` 并列出上述分类，不能因为有几个输出文件就称整包成功。

## 交换目录与翻译交接

输出根遵循 [主流程](../SKILL.md) 的 `<游戏名>_extract/` 约定；其中 `gt_input/` 为平铺的原文 JSON，`gt_output/` 接收同名译文。原始回填基准、配套文件、manifest 与报告放在各自目录，不交给翻译器修改。

仅有可翻译行的成员进入翻译队列。文件命名、冲突消歧、来源链与回填身份遵循 [交换契约](roundtrip-contract.md)；引擎要求的专有字段与目录映射见引擎页。明确输入范围并排除本次与历史输出目录，避免重跑时自我枚举；保留已有产物，使用新的输出目录。

叶子算法与公共层的衔接顺序见 [导出与回填集成步骤](worked-roundtrip.md)。这些规则不是统一批量 API；调用者仍需选定具体 parser、writer 和安全边界。

## 增补新引擎

按 [增补指南](extending-engines.md) 核实来源与许可、记录布局和限制、实现有界算法、补充正负例及往返验证，再更新引擎页和来源记录。

直接使用随包 `catalog/*.json`；提取、回填与适配不要求重建来源目录或访问外部源码。
