# Succubus：RIFF / VFA1 事件式归档

## 能力边界
- 状态：`partial / container-only`。
- Python：`python/archives/succubus.py`。
- 当前实现 VFA 包的真实 chunk、目录事件和数据偏移重建。
- 不实现字库图片、ARC1 变体或文本 VM。
- 不依赖原工具的 `grp.vfa`、`index.json` 或隐式文件 IO。

## 识别与顶层结构
- 开头为 `RIFF`，随后 u32 长度，form 为 `VFA1`。
- RIFF 长度必须恰好等于总文件长度减 8。
- 当前只接受固定 chunk 顺序：`hdri`、`data`、`dent`。
- 每个 chunk 使用四字节 tag、u32 payload 大小、payload。
- `hdri` 长十六字节，后八字节必须为 `dentdata`。
- 这是来源明确写出的无通用 word-padding 方言。
- 不套用任意 WAV/AVI RIFF 对齐规则改变原始结构。

## dent 目录事件
- `dir ` 事件携带 UTF-16LE NUL 目录名字。
- 后续 `file` 事件在当前目录语境中解释。
- 文件事件由 UTF-16LE NUL 名字与十六字节元数据构成。
- 元数据为 u32 offset、length、stamp、flags。
- offset 相对于 `data` chunk payload，不是文件绝对地址。
- 本实现保留目录事件顺序、stamp 和 flags。
- 解析函数返回事件列表，不拼接或写入不可信路径。

## 容器到剧本
- 来源用该工具处理资源包，不证明每个成员都是剧本。
- `parse_vfa` 将 file 的 bytes 放在事件的 `data` 字段。
- 调用者必须单独识别文本成员。
- 目录名字和文件名字不是角色 name。
- 当前没有 name/message 提取或剧本指令修正 API。

## 回填算法
- `build_vfa` 按原目录事件重新累计 data 内容。
- 每个 file 重新生成相对数据偏移和成员长度。
- 更新 dent/data 的 chunk 大小和最外层 RIFF 大小。
- 原始 hdri 作为显式参数传入，不默认覆盖未知版本字段。
- 当前要求连续不重叠成员，未索引尾部会拒绝。
- 成员中的控制码、文字编码和图像内容完全由调用方提供。

## Python 示例
```python
from python.archives.succubus import parse_vfa, build_vfa
obj = parse_vfa(vfa_bytes)
# 在单独确认成员类型与内部 writer 后，修改目标 file 事件的 data。
rebuilt = build_vfa(obj["entries"], header=obj["header"])
assert rebuilt == vfa_bytes  # 对本模块接受的规范布局
```
- 不写 `index.json`，返回的结构就是调用者的显式中间数据。

## 有界错误检查
- 检查所有 chunk/事件尺寸和 UTF-16 双字节终止符。
- 目录/文件类型、元数据长度不符直接失败。
- 事件数上限十万，非法 NUL 名字不允许重新封包。
- 奇数 data payload 可以往返，不误插入对齐字节。
- 没有静默把未知 dent tag 当成文件的行为。

## 部署条件与缺失阶段
- 缺少 ARC1 DATA 索引型包的本页实现。
- 缺少 VFA 非规范 chunk 顺序、未知扩展和重叠成员变体。
- 缺少剧本文本语义、字库图片修改及字体生成。
- 文件名与目录连接语义要由外部部署器进行安全检查。
- 未验证游戏重载、文件优先级和字形布局。

## 来源、许可与测试
- SExtractor 提交 `8d8d976fd04ae54e7c677705af937273d04a376a`。
- `tools/Succubus/VFA包处理工具/extract.py`。
- `tools/Succubus/VFA包处理工具/repack.py`。
- 其他路线证据：`tools/Succubus/arc_DATA_pack.py`、README。
- VFA 上游署名 这位同学；来源仓库 GPL-3.0。
- 去除了原脚本 import 时 IO 和固定目录资源。
- 合成测试覆盖事件顺序、元数据、奇数数据、变长偏移与截断。
- 测试：`tests/test_engines_tools_b.py`，无真实游戏资料。
