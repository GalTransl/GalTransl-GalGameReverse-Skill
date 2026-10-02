# Entis GLS：SRCXML 多语言消息与选择属性

## 能力边界
- 引擎 ID：`entis-gls`，Python 模块名 `entis_gls`。
- 参考模块：[python/engines/entis_gls.py](../python/engines/entis_gls.py)。
- 实现 `xscript/code/msg` 及 `select/menu` 属性文本的语义 XML 往返。
- 不是 CSX 字节码 writer，不把 XML 重序列化承诺为逐字节一致。
- 使用 Python 标准库 ElementTree；不加载外部实体、不访问网络。

## 识别证据
- `.srcxml` 与 `xscript` 根元素是直接线索。
- `code` 下的 `msg` 带 name/text 或带语言后缀的同类属性。
- `select` 下 `menu` 的 text 属性是选择文本。
- Entis 资源容器或可执行文件痕迹不能把任意 XML 自动认成剧本。
- `.csx` 是另一组版本化代码格式，不应送进 XML parser。
- 本参考要求无命名空间的 `xscript` 根，其他结构明确拒绝或保持非目标内容。

## 格式方言
- 无语言后缀时使用 `name`、`text`。
- 指定语言 `ja` 时使用 `name_ja`、`text_ja`。
- 自动识别只在候选节点中出现至多一种后缀时成立。
- 同时存在多种语言必须明确选择，禁止按属性顺序随意决定。
- 指定语言缺失 text 属性时拒绝，不回退翻译另一种语言。
- 选择先出现时，语言从 menu 属性读取，而不是错误地只看 select 属性。
- 空 name 显示为 None，但保留该属性存在且可写的事实。
- 没有 name 属性的正文不自动补出姓名槽位。

## 容器到剧本路线
1. 先识别 NOA/DAT 等资源格式，再按成员签名寻找 SRCXML。
2. GARbro-Mod `ArcFormats/Entis/ArcNOA.cs` 是 Entis GLS 容器线索。
3. 严格解码 XML，明确源编码和目标语言。
4. 提取目标属性与稳定记录序号，其他语言/语音/ID 保持原样。
5. 重序列化、重新解析后按实际运行时约定编码并部署。
- 本叶模块不提供 NOA writer，也不认为改后缀即可将 CSX 转为 SRCXML。

## 源码与算法对应
- 来源：`msg-tool`，GPL-3.0-or-later。
- 提交：`f72716cee88554d40c1cdface2812493b14ca653`。
- 路径：`src/scripts/entis_gls/srcxml.rs`。
- `SrcXmlScript::extract_messages` 对应 msg/select/menu 遍历与语言属性选择。
- `SrcXmlScript::import_messages` 对应定向修改 name/text 属性。
- Python 使用严格 XML，不采用 xml5ever 的错误恢复结果继续写回。
- Python 修正菜单先出现的语言探测，并拒绝多语言歧义。
- 不继承原实现可能忽略多余译文的问题；未知序号和字段都拒绝。

## Python 接口与示例
```python
from python.engines.entis_gls import extract_srcxml, patch_srcxml
xml = '<xscript><code><msg name_ja="A" text_ja="旧" text_en="old"/></code></xscript>'
records = extract_srcxml(xml, language='ja')
out = patch_srcxml(xml, {0: {'message': '新 & 文', 'name': 'B'}}, language='ja')
assert extract_srcxml(out, 'ja')[0].message == '新 & 文'
assert 'text_en="old"' in out
```
- `extract_srcxml(str, language=None) -> tuple[Message, ...]`。
- `patch_srcxml(str, {index: {'message': ..., 'name': ...}}, language=None) -> str`。
- Message 保存 kind、属性名、name_writable，而不是只留自由文案。
- 空改动直接返回原 str；有改动输出语义等价的 XML 字符串。

## name / message 映射
- msg.name 是本地姓名字段，menu 没有人名写入通道。
- 缺少 name 属性时 `name_writable=False`，拒绝凭上下文创建姓名。
- 多人名若原来就是属性内容，按原字符串保留，不自动拆成单人。
- 额外解析出的上下文名单应放公共 manifest，不能覆盖原属性模型。
- 每个 menu 是独立 choice；空 text 仍保留记录。
- 不翻译 voice、jump、ID、目标语言之外的属性或非目标节点文本。

## 回填、长度与控制码
- XML 属性转义由 ElementTree 完成，不手工替换 `&` 后二次转义。
- 允许合法 XML 字符；NUL、非法低控制字符、代理项等拒绝。
- 不处理 DTD/ENTITY；输入遇到这类声明即拒绝。
- 输出会规范化属性引号、实体拼写、自闭合元素等词法形式。
- 文档内部注释和处理指令保留；文档外声明不承诺逐字节保持。
- 未实现 SRCXML 到 CSX 编译，XML 本身没有二进制偏移表可修复。
- 返回前重新解析输出，检查 XML 结构与目标语言属性仍然成立。
- 调用层负责 XML 声明、文件编码和容器大小更新。

## 部署条件
- 先确认游戏实际加载 SRCXML 源文件，还是只使用已编译 CSX。
- 如果只有 CSX 执行路线，必须补上真正编译/反汇编方案，不能假称已闭环。
- 替换后需验证正文、名字、选项和语言切换。
- 游戏自己的文本控制语法应原样保留在属性值中。
- 所有磁盘写入、manifest 与原文件保护由父 Skill 公共层完成。

## 验证与缺口
- 合成测试覆盖普通 msg/menu、空名空文、语言选择与其他语言保留。
- 覆盖菜单先出现的自动语言识别与 XML `&`/引号转义往返。
- 覆盖注释保留、多语言歧义、缺属性、DTD 和非法字符拒绝。
- 测试位置：`tests/test_engines_primary.py` 中 `EntisTests`。
- 不支持命名空间方言、任意 XML 恢复、CSX v1/v2 或容器回封。
- 32 MiB 字符串上限是参考防护，不代表所有生产环境资源策略。
- 没有商业资产、网络、外部工具或运行时验证。
