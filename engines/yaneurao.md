# Yaneurao：Itufuru 长度字符串指令

## 识别与边界
- 本页只对应 msg-tool 的 Yaneurao Itufuru 分支。
- 不应把引擎品牌名等同于统一二进制格式。
- 来源没有用通用扩展名列表识别此剧本分支。
- 本 Python 单元必须从已确认的指令边界开始读取。
- 不提供在任意字节流里搜索 `02 00` 的“通用提取器”。
- 有效字符串指令包含小端 u16 opcode 与小端 u16 长度。
- 长度计入最后一个 NUL 字节。

## 容器与剧本
- 来源容器代码与剧本代码同在 `yaneurao/itufuru/` 子目录。
- `archive.rs` 与本页依据的 `script.rs` 是分离阶段。
- 本模块输入是容器已解出的剧本字节或单条指令。
- 归档索引、压缩方式和资源提取不在本模块能力内。
- 新生成的 record 不是完整脚本、更不是完整归档。

## 源码依据
- 仓库：msg-tool。
- 固定版本：`f72716cee88554d40c1cdface2812493b14ca653`。
- 许可：GPL-3.0-or-later。
- 文件：`src/scripts/yaneurao/itufuru/script.rs`。
- 符号：`ItufuruScript::new`、`extract_messages`、`import_messages`。
- 来源确认普通文本 opcode `0x02`，选项 opcode `0x1e`。
- 文件名、背景、声音字符串 opcode 分别为 `0x01/0x13/0x27`。
- 后三类被读取用于辨别结构，但不应导出为对白。

## Python 接口
- 模块：[yaneurao.py](../python/engines/yaneurao.py)。
- `read_record(data, offset=0, encoding="cp932") -> dict`。
- 返回 `opcode/text/role/offset/end`，end 为排他字节偏移。
- `write_record(opcode, text, encoding="cp932") -> bytes`。
- writer 只接受 `0x02/0x1e`，明确拒绝资源字符串 opcode。
- 接口不操作文件、不启动其他程序、不依赖来源 Rust crate。

## 使用示例
```python
from python.engines.yaneurao import write_record, read_record
record = write_record(0x02, "本文")
parsed = read_record(record)
assert parsed["text"] == "本文\n"
choice = write_record(0x1e, "選択肢")
assert read_record(choice)["role"] == "message"
```

## 输入输出契约
- 输入偏移小于零、头部不足四字节都会失败。
- 长度必须至少为 3，以匹配来源接受范围。
- 实际 NUL 必须正好位于声明长度的最后一字节。
- 字符串内部 NUL 被拒绝，防止长度与 C 字符串语义分叉。
- 普通文本的 NUL 前一个字节必须是 LF。
- 读取不会擅自补 LF；坏输入应暴露。
- 构建 `0x02` 时，缺少结尾 LF 则显式补一个。
- 构建 `0x1e` 时不会额外追加换行。
- 返回的是这一个 record 的完整编码字节。

## name/message 与姓名
- 来源把两种可翻译字符串都导出成 `name=None` 的 message。
- 本接口也没有人物表或专门姓名 opcode 的发现算法。
- 文本里的姓名不能仅凭“短句”推断成独立 name 字段。
- 上层若拆开姓名，必须记录可逆的分隔及原始字符串关系。
- 最安全的默认行为是保留整条文本，不删除引号或控制串。
- 资源类返回 `role="resource"`，不得进入普通翻译队列。

## 回填结构与编码
- 字节数以编码结果计算，不按 Python 字符数写入。
- 上限为 65535 字节，已经包含终止 NUL。
- 超长会报错，不继承来源强制转换 u16 可能产生的回绕。
- 默认 CP932，未实现自定义 SJIS tunnel 编码。
- 不能编码的中文应让上层制定字体/编码方案，不能静默替换。
- LF 是该普通文本记录的结构条件，不能删掉。
- 其他变量、控制符和选项语义由调用方保留并校验。

## 未完成阶段
- 来源整文件扫描具有候选识别与回退行为，本模块没有移植该扫描。
- 没有完整 opcode 表，因而不能证明任意偏移是指令开始。
- 没有跨指令引用或跳转地址的重定位器。
- 只有长度字段局部重建，不能据此保证整文件变长回填安全。
- 如需整脚本 writer，先补完结构遍历及地址证据。
- 不允许用通用二进制字符串替换绕过这些缺口。

## 验证状态
- 合成测试覆盖文本/选项、长度含 NUL 与普通文本自动 LF。
- 覆盖资源角色区分，确保 writer 不翻译路径。
- 覆盖截断、未知 opcode、缺 LF、NUL 冲突与 u16 超限。
- 测试文件：[test_engines_secondary.py](../tests/test_engines_secondary.py)。
- 当前结论为局部 record 算法通过，不是完整游戏往返通过。
- 未使用真实游戏文件，未访问付费模型接口。
