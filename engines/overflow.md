# Overflow：TextRes / Log XML 方言

## 能力边界
- 状态：`partial / decoded-text-roundtrip`。
- Python：`python/engines/overflow.py`。
- 实现的是资源编号关联的 XML 文本层，不是整个 Overflow 家族。
- 不把任意 XML 文本节点或任意字符串当作对白。
- 不需要原仓库、GalTransl、插件、缓存或外部运行库。

## 识别与输入
- 输入为已经正确解码的 XML 字符串，根节点必须是 `Script`。
- 可见文本资源采用 `TextRes NO="编号"`。
- 对话使用 `Log NAME="名字编号" MESS="正文编号"`。
- 检查资源编号唯一性、引用存在性及单纯文本节点。
- 明确拒绝 DTD、实体声明和混合子节点内容。
- 输入上限八百万字符，避免无边界 XML 处理。

## 容器到剧本
- 上游这一工具目录另有 OBJ、SCR 和其他 XML 变体。
- 这些变体不自动转换成这里的 `Script` 方言。
- 必须先由已验证的容器/反编译流程拿到该方言 XML。
- 本模块不读取磁盘，也不运行任何解包器。
- 外部导出器若修改资源编号，必须重新提取，不能复用旧定位。

## 提取 name / message
- `extract_xml` 按每个 `Log` 的出现顺序输出记录。
- `name_id`、`message_id` 才是回填键，文本内容不是定位依据。
- `NAME` 缺省时输出空名字，不猜角色。
- 相同正文编号出现多次仍保留每次引用，便于核查共享关系。
- 未被 `Log` 引用的图片路径和系统资源不导出。
- 本实现没有上游按正文编号去重造成的上下文丢失。

## 回填机制
- `rewrite_xml` 接收 `{资源编号: 新文本}`。
- 只允许写入已被 `Log` 引用的名字/正文资源。
- 同一共享编号只能有一个译文，调用方应先解决上下文冲突。
- 使用 XML 序列化进行字符转义，不是二进制字符串替换。
- 不修改编号或节点之间的引用，因此没有二进制地址修正。
- XML 格式、空标签写法、声明和缩进可能变化。
- 空替换表返回原始字符串；有修改不保证字节级一致。
- 禁止 XML 不允许的低位控制字符，换行/制表符可保留。

## Python 示例
```python
from python.engines.overflow import extract_xml, rewrite_xml
xml = '<Script><TextRes NO="1">試験</TextRes><Log MESS="1"/></Script>'
records = extract_xml(xml)
rebuilt = rewrite_xml(xml, {records[0]["message_id"]: "合成試験"})
assert extract_xml(rebuilt)[0]["message"] == "合成試験"
```
- 返回值是 Unicode XML；落盘编码和 XML 声明由调用者明确决定。
- 不应把此示例误用于 `RESOURCE/CREATE` 型 XML。

## 部署条件与缺失阶段
- 缺少原始容器解包、二进制剧本反编译以及再编译。
- 缺少 Overflow 其他 OBJ/SCR 版本的本页实现。
- 缺少名字表之外的选择肢语义和内联控制码词法。
- 字体、编码、游戏内换行效果和存档兼容性均未验证。
- 不把“XML 可往返”宣传为“任意该厂作品可直接部署”。

## 来源、许可与证据
- 来源仓库：SExtractor，提交 `8d8d976fd04ae54e7c677705af937273d04a376a`。
- 主要源码：`tools/Overflow/MISS EACH OTHER/script_xml_text.py`。
- 对照阅读：`tools/Overflow/README.md`、其他 XML 方言脚本。
- 上游署名：瑜瑜、Steins;Gate；保留 SExtractor 贡献者归属。
- 按来源仓库 GPL-3.0 许可处理；本参考为独立的函数化改编。
- 已测试：共享编号、多次引用、XML 转义、重复/悬空引用拒绝。
- 测试文件：`tests/test_engines_tools_b.py`，全部为合成 XML。
- 没有游戏运行、商业台词、网络或付费 API 测试。
